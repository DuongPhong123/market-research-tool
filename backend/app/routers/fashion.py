"""
Fashion router — women's fashion market research endpoints.
Target: female shoppers aged 22–35 on Shopee Vietnam.
"""
import asyncio
import logging
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional

from app.database import get_db
from app.models.product import ShopeeProduct
from app.scrapers.shopee import ShopeeAffiliateScraper
from app.scrapers.facebook import FacebookAdsScraper, FacebookPageScraper
from app.scrapers.instagram import InstagramWebScraper
from app.analyzers.fashion_analyzer import (
    FASHION_SUBCATEGORIES, FASHION_SEARCH_KEYWORDS, ALL_FASHION_KEYWORDS,
    STYLE_TRENDS, PRICE_SEGMENT_LABELS,
    analyze_fashion_comments_batch, score_product_for_fashion,
    classify_price_segment, detect_styles, has_buy_signal,
)
from app.analyzers.nlp_analyzer import extract_keywords, is_price_inquiry
from app.analyzers.trend_scorer import score_shopee_product, score_facebook_ad, score_instagram_post

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fashion", tags=["Fashion - Thoi trang nu"])


# ---------------------------------------------------------------------------
# GET /api/fashion/subcategories
# ---------------------------------------------------------------------------

@router.get("/subcategories")
async def list_subcategories():
    """List all trackable women's fashion subcategories."""
    return {
        "subcategories": [
            {"key": k, "label": v, "keywords": FASHION_SEARCH_KEYWORDS.get(k, [])}
            for k, v in FASHION_SUBCATEGORIES.items()
        ]
    }


# ---------------------------------------------------------------------------
# GET /api/fashion/trending
# ---------------------------------------------------------------------------

@router.get("/trending")
async def get_fashion_trending(
    subcategory: Optional[str] = Query(None, description="Key tu FASHION_SUBCATEGORIES, e.g. vay_dam"),
    limit: int = Query(30, ge=5, le=100),
    min_price: float = Query(0),
    max_price: float = Query(5_000_000),
    db: AsyncSession = Depends(get_db),
):
    """
    Sweep Shopee for trending women's fashion products.
    Without subcategory: sweeps all subcategories (slower, ~15s).
    With subcategory: fast single-category search.
    """
    scraper = ShopeeAffiliateScraper()

    if subcategory:
        keywords = FASHION_SEARCH_KEYWORDS.get(subcategory)
        if not keywords:
            raise HTTPException(404, detail=f"Khong tim thay subcategory: {subcategory}")
        # Search all keywords in the subcategory, deduplicate
        seen: set[str] = set()
        products: list[dict] = []
        per_kw = max(10, limit // len(keywords))
        for kw in keywords:
            batch = await scraper.search_products(kw, limit=per_kw)
            for p in batch:
                if p["item_id"] and p["item_id"] not in seen:
                    seen.add(p["item_id"])
                    products.append(p)
        label = FASHION_SUBCATEGORIES[subcategory]
    else:
        products = await scraper.get_trending_public(limit=limit * 2)
        label = "Tat ca danh muc"

    # Filter by price range
    products = [
        p for p in products
        if min_price <= (p.get("price_min") or 0) <= max_price
    ]

    # Score with fashion-specific scorer
    for p in products:
        p["trending_score"]  = score_shopee_product(p)
        p["fashion_score"]   = score_product_for_fashion(p)
        p["price_segment"]   = PRICE_SEGMENT_LABELS.get(classify_price_segment(p.get("price_min") or 0), "")
        p["styles"]          = detect_styles(p.get("name") or "")

    products.sort(key=lambda x: x.get("fashion_score", 0), reverse=True)
    products = products[:limit]

    # Persist to DB
    await _upsert_products(db, products)

    return {
        "subcategory": subcategory or "all",
        "label": label,
        "total": len(products),
        "data": products,
        "price_range": {"min": min_price, "max": max_price},
    }


# ---------------------------------------------------------------------------
# GET /api/fashion/search
# ---------------------------------------------------------------------------

@router.get("/search")
async def fashion_search(
    keyword: str = Query(..., min_length=2),
    subcategory: Optional[str] = Query(None),
    limit: int = Query(20, ge=5, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Search Shopee for a fashion keyword with fashion-specific scoring."""
    scraper = ShopeeAffiliateScraper()
    products = await scraper.search_products(keyword, limit=limit)

    if not products:
        return {"keyword": keyword, "data": [], "message": "Khong tim thay san pham"}

    for p in products:
        p["trending_score"] = score_shopee_product(p)
        p["fashion_score"]  = score_product_for_fashion(p)
        p["price_segment"]  = PRICE_SEGMENT_LABELS.get(classify_price_segment(p.get("price_min") or 0), "")
        p["styles"]         = detect_styles(p.get("name") or "")

    products.sort(key=lambda x: x.get("fashion_score", 0), reverse=True)
    await _upsert_products(db, products)

    return {
        "keyword": keyword,
        "subcategory": subcategory,
        "total": len(products),
        "data": products,
    }


# ---------------------------------------------------------------------------
# POST /api/fashion/analyze-keyword
# ---------------------------------------------------------------------------

@router.post("/analyze-keyword")
async def analyze_fashion_keyword(
    keyword: str = Query(..., min_length=2),
    max_comments: int = Query(50, ge=10, le=200),
    db: AsyncSession = Depends(get_db),
):
    """
    Cross-platform deep analysis for one fashion keyword.
    Returns: top Shopee products + Facebook ads + Instagram posts +
             NLP insights from real comments tuned for 22-35 female buyers.
    """
    shopee_scraper = ShopeeAffiliateScraper()
    fb_ads_scraper = FacebookAdsScraper()
    fb_page_scraper = FacebookPageScraper()
    ig_scraper = InstagramWebScraper()

    # Run platform scrapes in parallel
    shopee_task = shopee_scraper.search_products(keyword, limit=20)
    fb_ads_task = fb_ads_scraper.search_ads(keyword, country="VN", limit=20)
    ig_task     = ig_scraper.scrape_hashtag(keyword.replace(" ", ""), max_posts=10)
    fb_cmt_task = fb_page_scraper.crawl_keyword_comments(keyword, max_posts=3, max_comments_per_post=max_comments // 3)

    results = await asyncio.gather(shopee_task, fb_ads_task, ig_task, fb_cmt_task, return_exceptions=True)
    shopee_products, fb_ads, ig_posts, fb_comments = results

    if isinstance(shopee_products, Exception):
        shopee_products = []
    if isinstance(fb_ads, Exception):
        fb_ads = []
    if isinstance(ig_posts, Exception):
        ig_posts = []
    if isinstance(fb_comments, Exception):
        fb_comments = []

    # Score all sources
    for p in shopee_products:
        p["trending_score"] = score_shopee_product(p)
        p["fashion_score"]  = score_product_for_fashion(p)
        p["price_segment"]  = PRICE_SEGMENT_LABELS.get(classify_price_segment(p.get("price_min") or 0), "")

    for ad in fb_ads:
        body = f"{ad.get('ad_creative_title','')} {ad.get('ad_creative_body','')}"
        ad["price_inquiry_ratio"] = 0.20 if is_price_inquiry(body) else 0.0
        ad["trending_score"] = score_facebook_ad(ad)

    for post in ig_posts:
        caption = post.get("caption") or ""
        post["price_inquiry_ratio"] = 0.25 if is_price_inquiry(caption) else 0.0
        post["trending_score"]  = score_instagram_post(post)
        post["styles"]          = detect_styles(caption)
        post["keywords"]        = extract_keywords(caption, top_n=5)

    # Fashion NLP on FB comments
    comment_insights = analyze_fashion_comments_batch(fb_comments)

    # Top-level trend signal: how many platforms show this keyword is hot
    platforms_hot = sum([
        1 if any(p.get("fashion_score", 0) >= 50 for p in shopee_products) else 0,
        1 if any(a.get("trending_score", 0) >= 50 for a in fb_ads) else 0,
        1 if any(p.get("trending_score", 0) >= 50 for p in ig_posts) else 0,
    ])

    # Trending styles from IG captions + comments
    all_text = " ".join([
        (p.get("caption") or "") for p in ig_posts
    ] + [
        (c.get("content") or "") for c in fb_comments
    ])
    trending_styles = detect_styles(all_text)

    # Keywords from all comment/caption text
    trending_keywords = extract_keywords(all_text, top_n=20)

    # Persist Shopee products
    if shopee_products:
        await _upsert_products(db, shopee_products)

    return {
        "keyword": keyword,
        "trend_signal": {
            "platforms_hot": platforms_hot,
            "verdict": (
                "DANG VIRAL" if platforms_hot >= 3 else
                "CO TREND" if platforms_hot == 2 else
                "THEO DOI THEM" if platforms_hot == 1 else
                "CHUA RO RANG"
            ),
            "trending_styles": trending_styles[:5],
            "trending_keywords": trending_keywords[:15],
        },
        "shopee": {
            "total": len(shopee_products),
            "top_products": sorted(shopee_products, key=lambda x: x.get("fashion_score", 0), reverse=True)[:5],
        },
        "facebook_ads": {
            "total": len(fb_ads),
            "top_ads": sorted(fb_ads, key=lambda x: x.get("trending_score", 0), reverse=True)[:5],
        },
        "instagram": {
            "total": len(ig_posts),
            "top_posts": sorted(ig_posts, key=lambda x: x.get("trending_score", 0), reverse=True)[:5],
        },
        "comment_insights": comment_insights,
    }


# ---------------------------------------------------------------------------
# GET /api/fashion/keywords
# ---------------------------------------------------------------------------

@router.get("/keywords")
async def get_fashion_keywords(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(30, ge=5, le=100),
):
    """
    Return ranked fashion keyword list with Shopee product counts from DB.
    Use to identify which keywords have the most data / highest trending products.
    """
    from sqlalchemy import func
    keyword_scores: list[dict] = []

    for kw in ALL_FASHION_KEYWORDS:
        q = (
            select(func.count(), func.avg(ShopeeProduct.trending_score))
            .where(ShopeeProduct.name.ilike(f"%{kw.split()[0]}%"))
        )
        result = await db.execute(q)
        count, avg_score = result.one()
        keyword_scores.append({
            "keyword": kw,
            "product_count": count or 0,
            "avg_trending_score": round(avg_score or 0, 1),
            "styles": detect_styles(kw),
        })

    keyword_scores.sort(key=lambda x: (x["avg_trending_score"], x["product_count"]), reverse=True)

    return {
        "total_keywords": len(keyword_scores),
        "data": keyword_scores[:limit],
        "style_taxonomy": {k: len(v) for k, v in STYLE_TRENDS.items()},
    }


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _upsert_products(db: AsyncSession, products: list[dict]):
    from app.models.product import ShopeeProduct
    for p in products:
        if not p.get("item_id"):
            continue
        existing = await db.execute(select(ShopeeProduct).where(ShopeeProduct.item_id == p["item_id"]))
        obj = existing.scalar_one_or_none()
        if obj:
            old_sold = obj.sold or 0
            p["sold_delta"] = max((p.get("sold") or 0) - old_sold, 0)
            for k, v in p.items():
                if hasattr(obj, k) and v is not None:
                    setattr(obj, k, v)
        else:
            obj = ShopeeProduct(**{k: v for k, v in p.items() if hasattr(ShopeeProduct, k)})
            db.add(obj)
    await db.commit()
