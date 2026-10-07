from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, or_
from typing import Optional
from app.database import get_db
from app.models.ad import FacebookAd, InstagramPost, SocialComment
from app.scrapers.facebook import FacebookAdsScraper, FacebookPageScraper
from app.scrapers.instagram import InstagramGraphScraper, InstagramWebScraper
from app.analyzers.nlp_analyzer import analyze_comments_batch, extract_keywords, is_price_inquiry
from app.analyzers.trend_scorer import score_facebook_ad, score_instagram_post

router = APIRouter(prefix="/api/ads", tags=["Ads & Social"])


@router.get("/facebook/trending")
async def get_trending_fb_ads(db: AsyncSession = Depends(get_db), limit: int = Query(20, ge=1, le=100)):
    q = select(FacebookAd).order_by(desc(FacebookAd.trending_score)).limit(limit)
    result = await db.execute(q)
    ads = result.scalars().all()
    return {"data": [_ad_to_dict(a) for a in ads], "total": len(ads)}


@router.get("/facebook/search")
async def search_facebook_ads(
    keyword: str = Query(..., min_length=2),
    country: str = Query("VN"),
    db: AsyncSession = Depends(get_db),
    save: bool = Query(True),
):
    scraper = FacebookAdsScraper()
    try:
        ads = await scraper.search_ads(keyword, country=country, limit=50)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Loi Meta API: {str(e)}")

    for ad in ads:
        body = ad.get("ad_creative_body") or ""
        title = ad.get("ad_creative_title") or ""
        full_text = f"{title} {body}"
        # Proxy: ad copy that uses price-attracting language (e.g. "gia ban",
        # "inbox gia", "lien he shop") predicts higher price-inquiry comment rate.
        ad["price_inquiry_ratio"] = 0.20 if is_price_inquiry(full_text) else 0.0
        ad["trending_score"] = score_facebook_ad(ad)
        ad["keywords"] = extract_keywords(full_text, top_n=8)
        ad["product_keywords"] = _detect_product_keywords(full_text)

    if save:
        await _upsert_ads(db, ads)
    return {
        "keyword": keyword,
        "data": sorted(ads, key=lambda x: x.get("trending_score", 0), reverse=True),
        "total": len(ads),
    }


@router.post("/facebook/analyze-comments")
async def analyze_facebook_comments(
    keyword: str = Query(...),
    max_posts: int = Query(5, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    page_scraper = FacebookPageScraper()
    all_comments = await page_scraper.crawl_keyword_comments(keyword, max_posts=max_posts, max_comments_per_post=100)
    if not all_comments:
        return {
            "keyword": keyword,
            "message": "Khong lay duoc comments. Kiem tra Facebook Access Token.",
            "analysis": {},
        }

    analysis = analyze_comments_batch(all_comments)
    await _save_comments(db, all_comments)

    # Use real price_inquiry_pct from comments to update trending_score of ads
    # that were previously scraped for this same keyword.
    real_ratio = analysis.get("price_inquiry_pct", 0) / 100
    if real_ratio > 0:
        await _update_ads_price_inquiry(db, keyword, real_ratio)

    return {
        "keyword": keyword,
        "total_comments": len(all_comments),
        "analysis": analysis,
        "sample_comments": all_comments[:10],
    }


@router.get("/instagram/hashtag")
async def search_instagram_hashtag(
    hashtag: str = Query(...),
    db: AsyncSession = Depends(get_db),
    use_api: bool = Query(False),
):
    if use_api:
        scraper = InstagramGraphScraper()
        posts = await scraper.get_hashtag_top_media(hashtag, limit=30)
    else:
        scraper = InstagramWebScraper()
        posts = await scraper.scrape_hashtag(hashtag, max_posts=20)

    if not posts:
        return {"hashtag": hashtag, "data": [], "message": "Khong lay duoc data Instagram"}

    for post in posts:
        caption = post.get("caption") or ""
        # Seller captions like "comment 'gia' to order", "inbox for price" signal
        # that buyers will flood comments with price inquiries.
        post["price_inquiry_ratio"] = 0.25 if is_price_inquiry(caption) else 0.0
        post["trending_score"] = score_instagram_post(post)
        post["keywords"] = extract_keywords(caption, top_n=5)

    posts_sorted = sorted(posts, key=lambda x: x.get("trending_score", 0), reverse=True)
    await _upsert_ig_posts(db, posts_sorted)
    return {"hashtag": hashtag, "data": posts_sorted, "total": len(posts_sorted)}


@router.get("/comments/analysis")
async def get_comments_analysis(
    source: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    q = select(SocialComment)
    if source:
        q = q.where(SocialComment.source == source)
    q = q.limit(500)
    result = await db.execute(q)
    comments = result.scalars().all()
    comments_dict = [
        {"source": c.source, "post_id": c.post_id, "content": c.content, "author": c.author, "likes": c.likes}
        for c in comments
    ]
    if keyword:
        comments_dict = [c for c in comments_dict if keyword.lower() in (c.get("content") or "").lower()]
    analysis = analyze_comments_batch(comments_dict)
    return {"total_comments": len(comments_dict), "analysis": analysis}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _update_ads_price_inquiry(db: AsyncSession, keyword: str, ratio: float) -> None:
    """Recalculate trending_score for ads matching keyword using real comment ratio."""
    q = select(FacebookAd).where(
        or_(
            FacebookAd.ad_creative_body.ilike(f"%{keyword}%"),
            FacebookAd.ad_creative_title.ilike(f"%{keyword}%"),
        )
    )
    result = await db.execute(q)
    ads = result.scalars().all()
    for ad_obj in ads:
        ad_dict = _ad_to_dict(ad_obj)
        ad_dict["price_inquiry_ratio"] = ratio
        ad_obj.trending_score = score_facebook_ad(ad_dict)
    if ads:
        await db.commit()


def _detect_product_keywords(text: str) -> list[str]:
    import re
    patterns = [r'"([^"]{3,30})"', r"'([^']{3,30})'", r"(?:san pham|SP|combo|set|kit)\s+([A-Za-z\s]{3,25})"]
    found = []
    for pattern in patterns:
        found.extend(re.findall(pattern, text, re.IGNORECASE))
    return list(set(found))[:5]


async def _upsert_ads(db: AsyncSession, ads: list[dict]):
    for ad in ads:
        if not ad.get("ad_id"):
            continue
        existing = await db.execute(select(FacebookAd).where(FacebookAd.ad_id == ad["ad_id"]))
        obj = existing.scalar_one_or_none()
        if obj:
            for k, v in ad.items():
                if hasattr(obj, k) and v is not None:
                    setattr(obj, k, v)
        else:
            obj = FacebookAd(**{k: v for k, v in ad.items() if hasattr(FacebookAd, k)})
            db.add(obj)
    await db.commit()


async def _upsert_ig_posts(db: AsyncSession, posts: list[dict]):
    for post in posts:
        if not post.get("post_id"):
            continue
        existing = await db.execute(select(InstagramPost).where(InstagramPost.post_id == post["post_id"]))
        obj = existing.scalar_one_or_none()
        if obj:
            for k, v in post.items():
                if hasattr(obj, k) and v is not None:
                    setattr(obj, k, v)
        else:
            obj = InstagramPost(**{k: v for k, v in post.items() if hasattr(InstagramPost, k)})
            db.add(obj)
    await db.commit()


async def _save_comments(db: AsyncSession, comments: list[dict]):
    for c in comments:
        if not c.get("comment_id"):
            continue
        existing = await db.execute(select(SocialComment).where(SocialComment.comment_id == c["comment_id"]))
        if not existing.scalar_one_or_none():
            obj = SocialComment(**{k: v for k, v in c.items() if hasattr(SocialComment, k)})
            db.add(obj)
    await db.commit()


def _ad_to_dict(a: FacebookAd) -> dict:
    return {
        "ad_id": a.ad_id, "page_name": a.page_name,
        "ad_creative_body": a.ad_creative_body, "ad_creative_title": a.ad_creative_title,
        "spend_min": a.spend_min, "spend_max": a.spend_max,
        "impressions_min": a.impressions_min, "impressions_max": a.impressions_max,
        "delivery_start": str(a.delivery_start) if a.delivery_start else None,
        "delivery_stop": str(a.delivery_stop) if a.delivery_stop else None,
        "platforms": a.platforms, "trending_score": a.trending_score, "keywords": a.keywords,
    }
