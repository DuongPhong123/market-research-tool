import math
from datetime import datetime, timedelta


def score_shopee_product(product: dict) -> float:
    sold = product.get("sold") or 0
    sold_delta = product.get("sold_delta") or 0
    rating = product.get("rating") or 0
    review_count = product.get("review_count") or 0
    liked_count = product.get("liked_count") or 0
    commission_rate = product.get("commission_rate") or 0

    sold_score = min(math.log1p(sold) / math.log1p(10000), 1.0)
    growth_score = min(sold_delta / max(sold, 1), 1.0) if sold_delta > 0 else 0.0
    rating_score = (rating - 1) / 4 if rating >= 1 else 0.0
    review_score = min(math.log1p(review_count) / math.log1p(500), 1.0)
    like_score = min(math.log1p(liked_count) / math.log1p(1000), 1.0)
    commission_score = min(commission_rate / 20, 1.0)

    score = (
        sold_score * 0.30 + growth_score * 0.25 + rating_score * 0.15
        + review_score * 0.15 + like_score * 0.10 + commission_score * 0.05
    )
    return round(score * 100, 2)


def score_facebook_ad(ad: dict) -> float:
    spend_max = ad.get("spend_max") or 0
    impressions_max = ad.get("impressions_max") or 0
    delivery_start = ad.get("delivery_start")
    delivery_stop = ad.get("delivery_stop")

    spend_score = min(math.log1p(spend_max) / math.log1p(100_000_000), 1.0)
    imp_score = min(math.log1p(impressions_max) / math.log1p(10_000_000), 1.0)

    freshness_score = 0.5
    if delivery_start:
        try:
            start = datetime.fromisoformat(str(delivery_start).replace("Z", "+00:00"))
            days_running = (datetime.now(start.tzinfo) - start).days
            freshness_score = max(1.0 - days_running / 90, 0.1)
        except Exception:
            pass

    is_active = delivery_stop is None
    active_bonus = 0.2 if is_active else 0.0

    score = spend_score * 0.40 + imp_score * 0.30 + freshness_score * 0.20 + active_bonus * 0.10
    return round(min(score, 1.0) * 100, 2)


def score_instagram_post(post: dict) -> float:
    likes = post.get("likes_count") or 0
    comments = post.get("comments_count") or 0
    post_date = post.get("post_date")

    engagement = likes + comments * 3
    eng_score = min(math.log1p(engagement) / math.log1p(50000), 1.0)
    total = likes + comments
    comment_ratio = comments / total if total > 0 else 0
    ratio_score = min(comment_ratio * 5, 1.0)

    freshness_score = 0.5
    if post_date:
        try:
            if isinstance(post_date, (int, float)):
                dt = datetime.fromtimestamp(post_date)
            else:
                dt = datetime.fromisoformat(str(post_date))
            days_old = (datetime.now() - dt.replace(tzinfo=None)).days
            freshness_score = max(1.0 - days_old / 14, 0.0)
        except Exception:
            pass

    score = eng_score * 0.50 + ratio_score * 0.20 + freshness_score * 0.30
    return round(score * 100, 2)


def calculate_keyword_velocity(keyword: str, frequency_now: int, frequency_prev: int) -> float:
    if frequency_prev == 0:
        return float(frequency_now) if frequency_now > 0 else 0.0
    return round(frequency_now / frequency_prev, 3)


def rank_products_for_affiliate(products: list[dict]) -> list[dict]:
    for p in products:
        trending = p.get("trending_score") or 0
        commission = p.get("commission_rate") or 0
        price = p.get("price_min") or p.get("price") or 0
        price_bonus = 0
        if 100_000 <= price <= 500_000:
            price_bonus = 10
        elif 50_000 <= price <= 1_000_000:
            price_bonus = 5
        comm_bonus = min(commission * 2, 20)
        p["affiliate_score"] = round(trending + price_bonus + comm_bonus, 2)
    return sorted(products, key=lambda x: x.get("affiliate_score", 0), reverse=True)
