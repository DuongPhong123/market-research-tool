from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func
from app.database import get_db
from app.models.trend import TrendKeyword, TrendReport
from app.models.product import ShopeeProduct
from app.models.ad import FacebookAd, InstagramPost, SocialComment
from app.analyzers.nlp_analyzer import analyze_comments_batch
from collections import Counter

router = APIRouter(prefix="/api/trends", tags=["Trends"])


@router.get("/keywords")
async def get_trending_keywords(
    db: AsyncSession = Depends(get_db),
    limit: int = Query(30, ge=5, le=100),
    min_velocity: float = Query(0.0),
):
    q = select(TrendKeyword).order_by(desc(TrendKeyword.trend_score))
    if min_velocity > 0:
        q = q.where(TrendKeyword.velocity >= min_velocity)
    q = q.limit(limit)
    result = await db.execute(q)
    keywords = result.scalars().all()
    return {
        "data": [
            {"keyword": k.keyword, "frequency": k.frequency, "trend_score": k.trend_score,
             "velocity": k.velocity, "sources": k.sources, "category_guess": k.category_guess,
             "first_seen": str(k.first_seen) if k.first_seen else None}
            for k in keywords
        ]
    }


@router.get("/summary")
async def get_trend_summary(db: AsyncSession = Depends(get_db)):
    shopee_q = select(ShopeeProduct).order_by(desc(ShopeeProduct.trending_score)).limit(10)
    shopee_result = await db.execute(shopee_q)
    top_products = [
        {"name": p.name, "score": p.trending_score, "sold": p.sold, "url": p.affiliate_url or p.product_url}
        for p in shopee_result.scalars().all()
    ]
    fb_q = select(FacebookAd).order_by(desc(FacebookAd.trending_score)).limit(10)
    fb_result = await db.execute(fb_q)
    top_ads = [
        {"page_name": a.page_name, "title": a.ad_creative_title,
         "body_preview": (a.ad_creative_body or "")[:100], "spend_max": a.spend_max, "score": a.trending_score}
        for a in fb_result.scalars().all()
    ]
    ig_q = select(InstagramPost).order_by(desc(InstagramPost.trending_score)).limit(10)
    ig_result = await db.execute(ig_q)
    top_ig = [
        {"username": p.username, "caption_preview": (p.caption or "")[:100],
         "likes": p.likes_count, "comments": p.comments_count, "score": p.trending_score, "url": p.post_url}
        for p in ig_result.scalars().all()
    ]
    kw_q = select(TrendKeyword).order_by(desc(TrendKeyword.trend_score)).limit(20)
    kw_result = await db.execute(kw_q)
    top_keywords = [{"keyword": k.keyword, "score": k.trend_score, "velocity": k.velocity} for k in kw_result.scalars().all()]
    comments_q = select(SocialComment).limit(500)
    comments_result = await db.execute(comments_q)
    comments = [{"content": c.content} for c in comments_result.scalars().all()]
    pain_analysis = analyze_comments_batch(comments) if comments else {}
    shopee_count = (await db.execute(func.count(ShopeeProduct.id))).scalar() or 0
    fb_ad_count = (await db.execute(func.count(FacebookAd.id))).scalar() or 0
    ig_post_count = (await db.execute(func.count(InstagramPost.id))).scalar() or 0
    comment_count = (await db.execute(func.count(SocialComment.id))).scalar() or 0
    return {
        "stats": {"shopee_products": shopee_count, "facebook_ads": fb_ad_count,
                  "instagram_posts": ig_post_count, "social_comments": comment_count},
        "top_shopee_products": top_products, "top_facebook_ads": top_ads,
        "top_instagram_posts": top_ig, "top_keywords": top_keywords,
        "community_insights": {
            "overall_sentiment": pain_analysis.get("overall_sentiment"),
            "sentiment_label": pain_analysis.get("sentiment_label"),
            "top_pain_points": pain_analysis.get("top_pain_points", []),
            "hot_keywords": pain_analysis.get("top_keywords", []),
        },
    }


@router.post("/update-keywords")
async def update_trend_keywords(db: AsyncSession = Depends(get_db)):
    keyword_sources: dict[str, dict] = {}
    sp_result = await db.execute(select(ShopeeProduct.name, ShopeeProduct.keywords))
    for name, kws in sp_result:
        words = (kws or []) + (name or "").lower().split()
        for w in words:
            if len(w) >= 3:
                if w not in keyword_sources:
                    keyword_sources[w] = {"shopee": 0, "facebook": 0, "instagram": 0}
                keyword_sources[w]["shopee"] += 1
    fb_result = await db.execute(select(FacebookAd.keywords, FacebookAd.product_keywords))
    for kws, pkws in fb_result:
        for w in (kws or []) + (pkws or []):
            if len(w) >= 3:
                if w not in keyword_sources:
                    keyword_sources[w] = {"shopee": 0, "facebook": 0, "instagram": 0}
                keyword_sources[w]["facebook"] += 1
    ig_result = await db.execute(select(InstagramPost.hashtags, InstagramPost.keywords))
    for tags, kws in ig_result:
        for w in (tags or []) + (kws or []):
            if len(w) >= 3:
                if w not in keyword_sources:
                    keyword_sources[w] = {"shopee": 0, "facebook": 0, "instagram": 0}
                keyword_sources[w]["instagram"] += 1
    updated = 0
    for word, sources in keyword_sources.items():
        total_freq = sum(sources.values())
        if total_freq < 1:
            continue
        trend_score = sources["shopee"] * 0.4 + sources["facebook"] * 0.4 + sources["instagram"] * 0.2
        existing = await db.execute(select(TrendKeyword).where(TrendKeyword.keyword == word))
        obj = existing.scalar_one_or_none()
        if obj:
            prev_freq = obj.frequency or 1
            obj.frequency = total_freq
            obj.sources = sources
            obj.trend_score = trend_score
            obj.velocity = round(total_freq / prev_freq, 3)
        else:
            obj = TrendKeyword(keyword=word, frequency=total_freq, sources=sources, trend_score=trend_score, velocity=1.0)
            db.add(obj)
        updated += 1
    await db.commit()
    return {"message": f"Cap nhat {updated} tu khoa trending"}
