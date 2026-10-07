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

_DEMO_FB_ADS = [
    {"ad_id": "fb_demo_001", "page_name": "Váy Đầm Hàn Quốc – Korean Style VN", "ad_creative_body": "🌸 SALE SỐC! Váy đầm linen cổ V tay ngắn – form suông vintage cực xinh. Chất liệu cao cấp, mặc mát quanh năm. Giảm 40% hôm nay! Nhận hàng 2-3 ngày 🚚", "ad_creative_title": "Váy Đầm Linen Cổ V – Phong Cách Hàn Quốc", "spend_min": 5000, "spend_max": 10000, "impressions_min": 80000, "impressions_max": 150000, "delivery_start": "2024-10-01", "delivery_stop": None, "platforms": ["facebook", "instagram"], "trending_score": 0.87, "keywords": ["váy đầm", "hàn quốc", "linen", "sale", "vintage"], "price_inquiry_ratio": 0.35},
    {"ad_id": "fb_demo_002", "page_name": "Son Môi ROMAND Việt Nam Official", "ad_creative_body": "💄 Son lì ROMAND Zero Gram Matte – lên màu chuẩn, không khô môi, bền 8 tiếng. #17 Beige Nude đang HOT nhất 2024. Order ngay hôm nay – free ship toàn quốc!", "ad_creative_title": "ROMAND Zero Gram Matte Lip – #17 HOT TREND", "spend_min": 8000, "spend_max": 15000, "impressions_min": 120000, "impressions_max": 200000, "delivery_start": "2024-09-15", "delivery_stop": None, "platforms": ["facebook", "instagram", "audience_network"], "trending_score": 0.92, "keywords": ["son môi", "romand", "matte", "beige", "hot trend"], "price_inquiry_ratio": 0.28},
    {"ad_id": "fb_demo_003", "page_name": "Kem Chống Nắng ANESSA VN", "ad_creative_body": "☀️ ANESSA Perfect UV SPF50+ PA++++ – Bảo vệ da tối đa khỏi tia UV. Kiềm dầu, không bết dính. Bestseller Nhật Bản 15 năm liên tiếp. Mua 1 tặng 1 mini 20ml!", "ad_creative_title": "Kem Chống Nắng ANESSA – Chống UV Tối Đa SPF50+", "spend_min": 12000, "spend_max": 25000, "impressions_min": 200000, "impressions_max": 350000, "delivery_start": "2024-10-01", "delivery_stop": None, "platforms": ["facebook"], "trending_score": 0.89, "keywords": ["kem chống nắng", "anessa", "spf50", "nhật bản", "uv"], "price_inquiry_ratio": 0.22},
    {"ad_id": "fb_demo_004", "page_name": "Túi Xách Nữ – BagStyle VN", "ad_creative_body": "👜 Túi tote canvas 2 ngăn tiện ích – đựng vừa laptop 15.6inch. 12 màu hot, chất canvas dày dặn không nhăn. Giá chỉ từ 95k – MIỄN SHIP đơn 200k 🎀", "ad_creative_title": "Túi Tote Canvas Cao Cấp – 12 Màu Hot 2024", "spend_min": 3000, "spend_max": 7000, "impressions_min": 50000, "impressions_max": 90000, "delivery_start": "2024-09-20", "delivery_stop": None, "platforms": ["facebook", "instagram"], "trending_score": 0.78, "keywords": ["túi tote", "canvas", "laptop", "miễn ship"], "price_inquiry_ratio": 0.41},
    {"ad_id": "fb_demo_005", "page_name": "Serum Vitamin C – Klairs Việt Nam", "ad_creative_body": "✨ Klairs Freshly Juiced Vitamin C 5% – Sáng da, mờ thâm, chống oxy hóa. Phù hợp mọi loại da kể cả da nhạy cảm. 35ml dùng được 3-4 tháng. Combo 2 chai giảm 20%!", "ad_creative_title": "Serum Vitamin C Klairs – Sáng Da Mờ Thâm", "spend_min": 6000, "spend_max": 12000, "impressions_min": 90000, "impressions_max": 160000, "delivery_start": "2024-10-05", "delivery_stop": None, "platforms": ["facebook", "instagram"], "trending_score": 0.84, "keywords": ["serum", "vitamin c", "klairs", "sáng da", "mờ thâm"], "price_inquiry_ratio": 0.19},
    {"ad_id": "fb_demo_006", "page_name": "Nồi Chiên Không Dầu Philips VN", "ad_creative_body": "🍗 Philips HD9252 4.1L – Chiên giòn không dầu, tiết kiệm 90% dầu ăn. Công nghệ Rapid Air lưu thông nhiệt đều. Bảo hành 2 năm. Đặt hôm nay giảm 500k + tặng sách nấu ăn!", "ad_creative_title": "Nồi Chiên Không Dầu Philips 4.1L – Giảm 500k", "spend_min": 15000, "spend_max": 30000, "impressions_min": 250000, "impressions_max": 400000, "delivery_start": "2024-09-01", "delivery_stop": None, "platforms": ["facebook"], "trending_score": 0.81, "keywords": ["nồi chiên không dầu", "philips", "bảo hành", "tiết kiệm dầu"], "price_inquiry_ratio": 0.15},
    {"ad_id": "fb_demo_007", "page_name": "Thời Trang Nữ ZARA VN", "ad_creative_body": "👗 BST Thu Đông 2024 đã ra mắt! Áo khoác blazer oversize, quần jean ống rộng, váy midi – style công sở chuẩn Âu. Hàng về liên tục, size S-XL. Shop tại 45 Bà Triệu, HN & online!", "ad_creative_title": "ZARA Thu Đông 2024 – Thời Trang Công Sở Âu Mỹ", "spend_min": 20000, "spend_max": 40000, "impressions_min": 350000, "impressions_max": 600000, "delivery_start": "2024-10-01", "delivery_stop": None, "platforms": ["facebook", "instagram", "messenger"], "trending_score": 0.95, "keywords": ["zara", "thu đông", "blazer", "công sở", "hà nội"], "price_inquiry_ratio": 0.31},
    {"ad_id": "fb_demo_008", "page_name": "Collagen Shiseido Official VN", "ad_creative_body": "💊 Collagen Shiseido Enriched 126 viên – Dùng 84 ngày thấy da căng mịn rõ rệt. Hàng chính hãng Nhật Bản nhập khẩu. Combo 2 hộp giảm 15% + tặng kem dưỡng mini!", "ad_creative_title": "Collagen Shiseido Nhật – 84 Ngày Da Căng Mịn", "spend_min": 10000, "spend_max": 20000, "impressions_min": 150000, "impressions_max": 250000, "delivery_start": "2024-09-10", "delivery_stop": None, "platforms": ["facebook", "instagram"], "trending_score": 0.86, "keywords": ["collagen", "shiseido", "nhật bản", "da căng mịn", "84 ngày"], "price_inquiry_ratio": 0.24},
]

_DEMO_IG_POSTS = [
    {"post_id": "ig_demo_001", "username": "koreanfashionvn", "caption": "✨ Váy linen tay bồng mới về cực xinh! Form dáng A-line tôn dáng, chất linen cao cấp mặc mát. DM để đặt hàng nha cả nhà 💕 #vaydamhanquoc #thoitrangnu #linendress #ootdvietnam #fashionvn", "hashtags": ["vaydamhanquoc", "thoitrangnu", "linendress", "ootdvietnam", "fashionvn"], "likes_count": 8420, "comments_count": 312, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_001/", "post_date": None, "source_hashtag": "vaydamhanquoc", "trending_score": 0.91, "keywords": ["váy linen", "hàn quốc", "dm đặt hàng"], "price_inquiry_ratio": 0.45},
    {"post_id": "ig_demo_002", "username": "romand.vietnam", "caption": "💄 Son lì Zero Gram Matte #17 đang là màu hot nhất mùa thu! Lên màu chuẩn, không khô môi, bền cả ngày. Tag bạn thân để đi mua cùng nào 🍂 #sonmoi #romand #matte #beautyvietnam #makeupreview", "hashtags": ["sonmoi", "romand", "matte", "beautyvietnam", "makeupreview"], "likes_count": 15600, "comments_count": 890, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_002/", "post_date": None, "source_hashtag": "sonmoi", "trending_score": 0.95, "keywords": ["son lì", "romand", "matte", "mùa thu"], "price_inquiry_ratio": 0.38},
    {"post_id": "ig_demo_003", "username": "anessa.vietnam.official", "caption": "☀️ Bảo vệ da khỏi tia UV với Anessa Perfect UV SPF50+ PA++++ – sản phẩm chống nắng bán chạy nhất Nhật Bản 15 năm! Kiềm dầu, bền bỉ dưới nắng hè. Combo Anessa tháng 10 giảm 20% 🌸 #kemchongnang #anessa #skincarevietnam #beautytips #spf50", "hashtags": ["kemchongnang", "anessa", "skincarevietnam", "beautytips", "spf50"], "likes_count": 22300, "comments_count": 1240, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_003/", "post_date": None, "source_hashtag": "kemchongnang", "trending_score": 0.93, "keywords": ["chống nắng", "anessa", "spf50", "nhật bản"], "price_inquiry_ratio": 0.29},
    {"post_id": "ig_demo_004", "username": "streetstyle.hanoi", "caption": "🌿 Outfit đi làm ngày thu – áo blazer oversize + quần ống rộng = combo công sở chuẩn Âu! Link mua trong bio nha mn 🔗 #ootdhanoi #thoitrangcongso #blazer #streetstyle #fashionista", "hashtags": ["ootdhanoi", "thoitrangcongso", "blazer", "streetstyle", "fashionista"], "likes_count": 11200, "comments_count": 456, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_004/", "post_date": None, "source_hashtag": "thoitrangnu", "trending_score": 0.83, "keywords": ["blazer", "công sở", "thu đông", "ootd"], "price_inquiry_ratio": 0.31},
    {"post_id": "ig_demo_005", "username": "klairs_vietnam", "caption": "✨ Serum Vitamin C 5% từ Klairs – sáng da mờ thâm không kích ứng! Phù hợp cả da nhạy cảm. Dùng buổi tối trước kem dưỡng nha mn 🌙 Review sau 30 ngày: da sáng rõ rệt! #serumvitaminc #klairs #skincareroutine #csakin #beautyvn", "hashtags": ["serumvitaminc", "klairs", "skincareroutine", "csakin", "beautyvn"], "likes_count": 9870, "comments_count": 623, "media_type": "VIDEO", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_005/", "post_date": None, "source_hashtag": "skincare", "trending_score": 0.88, "keywords": ["serum", "vitamin c", "sáng da", "klairs"], "price_inquiry_ratio": 0.22},
    {"post_id": "ig_demo_006", "username": "tuixach.canvas.vn", "caption": "👜 Túi tote canvas hot nhất tháng 10! 12 màu, chất dày, đựng vừa laptop 15.6inch. Mẫu mới về liên tục, order nhanh kẻo hết hàng nha! DM = giá sỉ 🛍️ #tuixach #canvasbag #tuicampus #fashionaccessories #handbagvn", "hashtags": ["tuixach", "canvasbag", "tuicampus", "fashionaccessories", "handbagvn"], "likes_count": 18900, "comments_count": 2100, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_006/", "post_date": None, "source_hashtag": "tuixach", "trending_score": 0.89, "keywords": ["túi tote", "canvas", "laptop", "12 màu"], "price_inquiry_ratio": 0.52},
    {"post_id": "ig_demo_007", "username": "hadalabo.vn", "caption": "💧 Nước hoa hồng Hada Labo Gokujyun Premium – cấp ẩm tầng sâu, da căng mịn như da em bé! Best seller skincare Nhật dùng được cho mọi loại da. Bottle 170ml xài được 3 tháng 🇯🇵 #hadalabo #nuochoahong #skincarejapan #duongda #beautyvietnam", "hashtags": ["hadalabo", "nuochoahong", "skincarejapan", "duongda", "beautyvietnam"], "likes_count": 14500, "comments_count": 780, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_007/", "post_date": None, "source_hashtag": "skincare", "trending_score": 0.87, "keywords": ["nước hoa hồng", "hada labo", "nhật bản", "cấp ẩm"], "price_inquiry_ratio": 0.18},
    {"post_id": "ig_demo_008", "username": "nike.vietnam.official", "caption": "👟 Nike Air Force 1 Low trắng – classic không bao giờ lỗi mốt! Pair với mọi outfit từ casual đến semi-formal. Available tại Nike Store Hà Nội và HCM + mua online tại link bio 🤍 #nike #airforce1 #sneakers #giaytheothao #sneakervietnam", "hashtags": ["nike", "airforce1", "sneakers", "giaytheothao", "sneakervietnam"], "likes_count": 31200, "comments_count": 1890, "media_type": "IMAGE", "media_url": "", "post_url": "https://www.instagram.com/p/ig_demo_008/", "post_date": None, "source_hashtag": "giay", "trending_score": 0.92, "keywords": ["nike", "air force 1", "sneaker", "trắng"], "price_inquiry_ratio": 0.27},
]


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
    fb_token: Optional[str] = Query(None, description="Facebook Access Token tu UI (override .env)"),
    db: AsyncSession = Depends(get_db),
    save: bool = Query(True),
):
    scraper = FacebookAdsScraper(token=fb_token)
    api_error = None
    ads = []
    try:
        ads = await scraper.search_ads(keyword, country=country, limit=50)
    except Exception as e:
        api_error = str(e)

    # Fallback to demo data when API fails or returns empty
    if not ads:
        kw = keyword.lower()
        demo = [a for a in _DEMO_FB_ADS if kw in (a.get("ad_creative_body") or "").lower() or kw in (a.get("ad_creative_title") or "").lower() or kw in " ".join(a.get("keywords") or [])]
        if not demo:
            demo = _DEMO_FB_ADS
        return {
            "keyword": keyword,
            "data": demo,
            "total": len(demo),
            "demo": True,
            "error": api_error,
            "hint": "Dang hien thi du lieu DEMO. De xem du lieu that: vao tab Cai dat → huong dan lay Facebook Token co quyen ads_read",
        }

    for ad in ads:
        body = ad.get("ad_creative_body") or ""
        title = ad.get("ad_creative_title") or ""
        full_text = f"{title} {body}"
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
    fb_token: Optional[str] = Query(None, description="Facebook Access Token tu UI (override .env)"),
    db: AsyncSession = Depends(get_db),
):
    page_scraper = FacebookPageScraper(token=fb_token)
    all_comments = await page_scraper.crawl_keyword_comments(keyword, max_posts=max_posts, max_comments_per_post=100)
    if not all_comments:
        return {
            "keyword": keyword,
            "message": "Khong lay duoc comments. Kiem tra Facebook Access Token.",
            "analysis": {},
        }

    analysis = analyze_comments_batch(all_comments)
    await _save_comments(db, all_comments)

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
    posts = []
    scrape_error = None
    try:
        if use_api:
            scraper = InstagramGraphScraper()
            posts = await scraper.get_hashtag_top_media(hashtag, limit=30)
        else:
            scraper = InstagramWebScraper()
            posts = await scraper.scrape_hashtag(hashtag, max_posts=20)
    except Exception as e:
        scrape_error = str(e)

    if not posts:
        kw = hashtag.lower().lstrip("#")
        demo = [p for p in _DEMO_IG_POSTS if kw in " ".join(p.get("hashtags", [])).lower() or kw in (p.get("caption") or "").lower()]
        if not demo:
            demo = _DEMO_IG_POSTS
        return {
            "hashtag": hashtag,
            "data": demo,
            "total": len(demo),
            "demo": True,
            "error": scrape_error,
            "hint": "Dang hien thi du lieu DEMO. Instagram yeu cau dang nhap nen khong scrape duoc tu server.",
        }

    for post in posts:
        caption = post.get("caption") or ""
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


async def _update_ads_price_inquiry(db: AsyncSession, keyword: str, ratio: float) -> None:
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
