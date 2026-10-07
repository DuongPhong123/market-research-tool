from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from typing import Optional
from app.database import get_db
from app.models.product import ShopeeProduct, ShopeeReview
from app.scrapers.shopee import ShopeeAffiliateScraper
from app.analyzers.nlp_analyzer import analyze_comments_batch
from app.analyzers.trend_scorer import score_shopee_product

router = APIRouter(prefix="/api/products", tags=["Products"])


@router.get("/trending")
async def get_trending_products(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    min_score: float = Query(0.0),
):
    q = select(ShopeeProduct).order_by(desc(ShopeeProduct.trending_score))
    if category:
        q = q.where(ShopeeProduct.category == category)
    if min_score > 0:
        q = q.where(ShopeeProduct.trending_score >= min_score)
    q = q.limit(limit)
    result = await db.execute(q)
    products = result.scalars().all()
    return {"data": [_product_to_dict(p) for p in products], "total": len(products)}


@router.get("/search")
async def search_and_analyze(
    keyword: str = Query(..., min_length=2),
    db: AsyncSession = Depends(get_db),
    save: bool = Query(True),
):
    scraper = ShopeeAffiliateScraper()
    products = await scraper.search_products(keyword, limit=30)
    if not products:
        return {"data": [], "keyword": keyword, "message": "Khong tim thay san pham"}
    for p in products:
        p["trending_score"] = score_shopee_product(p)
    if save:
        await _upsert_products(db, products)
    return {
        "keyword": keyword,
        "data": sorted(products, key=lambda x: x.get("trending_score", 0), reverse=True),
        "total": len(products),
    }


@router.get("/{item_id}/reviews")
async def get_product_reviews(
    item_id: str,
    shop_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=10, le=200),
):
    scraper = ShopeeAffiliateScraper()
    reviews = await scraper.get_product_reviews(item_id, shop_id, limit=limit)
    if not reviews:
        return {"item_id": item_id, "analysis": {}, "reviews": []}
    analysis = analyze_comments_batch(reviews)
    return {"item_id": item_id, "analysis": analysis, "reviews": reviews[:20]}


@router.post("/crawl")
async def trigger_crawl(keywords: list[str], db: AsyncSession = Depends(get_db)):
    scraper = ShopeeAffiliateScraper()
    total_saved = 0
    for kw in keywords[:10]:
        try:
            products = await scraper.search_products(kw, limit=20)
            for p in products:
                p["trending_score"] = score_shopee_product(p)
            await _upsert_products(db, products)
            total_saved += len(products)
        except Exception:
            continue
    try:
        trending = await scraper.get_trending_products(limit=50)
        for p in trending:
            p["trending_score"] = score_shopee_product(p)
        await _upsert_products(db, trending)
        total_saved += len(trending)
    except Exception:
        pass
    return {"message": f"Da crawl xong, luu {total_saved} san pham", "saved": total_saved}


async def _upsert_products(db: AsyncSession, products: list[dict]):
    for p in products:
        if not p.get("item_id"):
            continue
        existing = await db.execute(select(ShopeeProduct).where(ShopeeProduct.item_id == p["item_id"]))
        obj = existing.scalar_one_or_none()
        if obj:
            old_sold = obj.sold or 0
            new_sold = p.get("sold") or 0
            p["sold_delta"] = max(new_sold - old_sold, 0)
            for k, v in p.items():
                if hasattr(obj, k) and v is not None:
                    setattr(obj, k, v)
        else:
            obj = ShopeeProduct(**{k: v for k, v in p.items() if hasattr(ShopeeProduct, k)})
            db.add(obj)
    await db.commit()


def _product_to_dict(p: ShopeeProduct) -> dict:
    return {
        "item_id": p.item_id, "name": p.name, "category": p.category,
        "price_min": p.price_min, "price_max": p.price_max,
        "sold": p.sold, "sold_delta": p.sold_delta, "rating": p.rating,
        "review_count": p.review_count, "shop_name": p.shop_name,
        "image_url": p.image_url, "affiliate_url": p.affiliate_url,
        "commission_rate": p.commission_rate, "trending_score": p.trending_score,
        "product_url": p.product_url,
    }
