import asyncio
import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from app.config import settings
from app.database import AsyncSessionLocal
from app.scrapers.shopee import ShopeeAffiliateScraper
from app.scrapers.facebook import FacebookAdsScraper
from app.analyzers.trend_scorer import score_shopee_product, score_facebook_ad
from app.analyzers.nlp_analyzer import extract_keywords

logger = logging.getLogger(__name__)

DEFAULT_KEYWORDS = [
    "kem duong da", "son moi", "nuoc hoa", "giam can", "collagen",
    "ao thun", "quan jean", "giay the thao", "tui xach", "dong ho",
    "dien thoai phu kien", "tai nghe bluetooth", "sac du phong",
    "do gia dung", "noi chien khong dau",
]

scheduler = AsyncIOScheduler(timezone="Asia/Ho_Chi_Minh")


async def crawl_shopee_trending():
    from app.models.trend import CrawlLog
    started = datetime.now()
    logger.info("Bat dau crawl Shopee trending...")

    async with AsyncSessionLocal() as db:
        log = CrawlLog(source="shopee", status="running")
        db.add(log)
        await db.commit()

        try:
            scraper = ShopeeAffiliateScraper()
            total = 0

            products = await scraper.get_trending_products(limit=100)
            for p in products:
                p["trending_score"] = score_shopee_product(p)
                p["keywords"] = extract_keywords(p.get("name") or "", top_n=5)

            from app.routers.products import _upsert_products
            await _upsert_products(db, products)
            total += len(products)

            for kw in DEFAULT_KEYWORDS[:8]:
                try:
                    kw_products = await scraper.search_products(kw, limit=15)
                    for p in kw_products:
                        p["trending_score"] = score_shopee_product(p)
                    await _upsert_products(db, kw_products)
                    total += len(kw_products)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Loi crawl keyword '{kw}': {e}")

            duration = (datetime.now() - started).total_seconds()
            log.status = "success"
            log.records_fetched = total
            log.finished_at = datetime.now()
            log.duration_seconds = duration
            await db.commit()
            logger.info(f"Crawl Shopee xong: {total} san pham ({duration:.1f}s)")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.finished_at = datetime.now()
            await db.commit()
            logger.error(f"Crawl Shopee loi: {e}")


async def crawl_facebook_ads():
    from app.models.trend import CrawlLog
    started = datetime.now()
    logger.info("Bat dau crawl Facebook Ads...")

    async with AsyncSessionLocal() as db:
        log = CrawlLog(source="facebook", status="running")
        db.add(log)
        await db.commit()

        try:
            scraper = FacebookAdsScraper()
            total = 0

            for kw in DEFAULT_KEYWORDS[:6]:
                try:
                    ads = await scraper.search_ads(kw, country="VN", limit=30)
                    for ad in ads:
                        ad["trending_score"] = score_facebook_ad(ad)
                        body = f"{ad.get('ad_creative_title', '')} {ad.get('ad_creative_body', '')}"
                        ad["keywords"] = extract_keywords(body, top_n=6)

                    from app.routers.ads import _upsert_ads
                    await _upsert_ads(db, ads)
                    total += len(ads)
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.warning(f"Loi crawl FB ads '{kw}': {e}")

            duration = (datetime.now() - started).total_seconds()
            log.status = "success"
            log.records_fetched = total
            log.finished_at = datetime.now()
            log.duration_seconds = duration
            await db.commit()
            logger.info(f"Crawl Facebook Ads xong: {total} ads ({duration:.1f}s)")

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)
            log.finished_at = datetime.now()
            await db.commit()
            logger.error(f"Crawl Facebook Ads loi: {e}")


async def update_keywords_job():
    async with AsyncSessionLocal() as db:
        from app.routers.trends import update_trend_keywords
        result = await update_trend_keywords(db)
        logger.info(f"{result['message']}")


def setup_scheduler():
    interval = settings.crawl_interval_hours
    scheduler.add_job(crawl_shopee_trending, IntervalTrigger(hours=interval), id="shopee_crawl", replace_existing=True)
    scheduler.add_job(crawl_facebook_ads, IntervalTrigger(hours=interval), id="fb_crawl", replace_existing=True)
    scheduler.add_job(update_keywords_job, IntervalTrigger(hours=interval + 0.1), id="kw_update", replace_existing=True)
    logger.info(f"Scheduler da setup: crawl moi {interval}h")
