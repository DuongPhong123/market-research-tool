import logging
import httpx

logger = logging.getLogger(__name__)

TIKTOK_CC_URL = "https://ads.tiktok.com/creative_radar_api/v1/top_ads/v2/list"

_DEMO_TIKTOK_ADS = [
    {"id": "tt_demo_001", "brand_name": "ROMAND Vietnam", "video_info": {"duration": 15, "cover": ""}, "ad_title": "Son Lì Zero Gram Matte #17 – HOT nhất TikTok Shop!", "cost": "10-20M", "country_code": "VN", "industry": "Beauty", "likes": 45200, "comments": 3100, "shares": 8900, "trending_score": 0.95, "keywords": ["son môi", "romand", "matte", "tiktok shop"]},
    {"id": "tt_demo_002", "brand_name": "Korean Fashion VN", "video_info": {"duration": 30, "cover": ""}, "ad_title": "Váy Linen Cổ V Form A – Mặc Là Xinh!", "cost": "5-10M", "country_code": "VN", "industry": "Fashion", "likes": 38700, "comments": 2400, "shares": 6200, "trending_score": 0.91, "keywords": ["váy đầm", "hàn quốc", "linen", "ootd"]},
    {"id": "tt_demo_003", "brand_name": "ANESSA Official VN", "video_info": {"duration": 20, "cover": ""}, "ad_title": "Kem Chống Nắng ANESSA SPF50+ – Kiềm Dầu 8 Tiếng!", "cost": "15-30M", "country_code": "VN", "industry": "Beauty", "likes": 62100, "comments": 4500, "shares": 12300, "trending_score": 0.97, "keywords": ["kem chống nắng", "anessa", "spf50", "skincare"]},
    {"id": "tt_demo_004", "brand_name": "Klairs Vietnam", "video_info": {"duration": 25, "cover": ""}, "ad_title": "Serum Vitamin C Klairs – 30 Ngày Da Sáng Rõ Rệt!", "cost": "8-15M", "country_code": "VN", "industry": "Beauty", "likes": 29300, "comments": 1870, "shares": 5100, "trending_score": 0.87, "keywords": ["serum", "vitamin c", "klairs", "sáng da"]},
    {"id": "tt_demo_005", "brand_name": "Túi Xách Canvas VN", "video_info": {"duration": 12, "cover": ""}, "ad_title": "Túi Tote Canvas 12 Màu – Đựng Vừa Laptop 15.6 Inch!", "cost": "3-7M", "country_code": "VN", "industry": "Fashion Accessories", "likes": 51400, "comments": 5600, "shares": 14200, "trending_score": 0.93, "keywords": ["túi tote", "canvas", "laptop", "đi học"]},
    {"id": "tt_demo_006", "brand_name": "Philips Vietnam", "video_info": {"duration": 45, "cover": ""}, "ad_title": "Nồi Chiên Không Dầu Philips – Chiên Giòn Không Cần Dầu Ăn!", "cost": "20-40M", "country_code": "VN", "industry": "Home Appliances", "likes": 73500, "comments": 6200, "shares": 18900, "trending_score": 0.98, "keywords": ["nồi chiên không dầu", "philips", "đồ gia dụng"]},
    {"id": "tt_demo_007", "brand_name": "ZARA Vietnam", "video_info": {"duration": 20, "cover": ""}, "ad_title": "BST Thu Đông 2024 – Blazer Oversize Đang HOT!", "cost": "25-50M", "country_code": "VN", "industry": "Fashion", "likes": 88200, "comments": 7300, "shares": 22100, "trending_score": 0.99, "keywords": ["zara", "blazer", "thu đông", "công sở"]},
    {"id": "tt_demo_008", "brand_name": "Hada Labo Vietnam", "video_info": {"duration": 18, "cover": ""}, "ad_title": "Nước Hoa Hồng Hada Labo – Cấp Ẩm Tầng Sâu Như Da Em Bé!", "cost": "12-25M", "country_code": "VN", "industry": "Beauty", "likes": 44600, "comments": 3200, "shares": 9800, "trending_score": 0.89, "keywords": ["hada labo", "nước hoa hồng", "cấp ẩm", "skincare nhật"]},
]


class TikTokAdsScraper:
    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Content-Type": "application/json",
        "Referer": "https://ads.tiktok.com/business/creativecenter/",
    }

    async def get_trending_ads(self, country: str = "VN", period: int = 7, industry: str = "", limit: int = 20) -> list[dict]:
        payload = {"page": 1, "limit": min(limit, 20), "period": period, "country_code": country,
                   "industry_id": industry, "creative_type": "", "objective_type": ""}
        try:
            async with httpx.AsyncClient(timeout=15.0, headers=self.HEADERS) as client:
                resp = await client.post(TIKTOK_CC_URL, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("code") == 0:
                        materials = data.get("data", {}).get("materials", [])
                        if materials:
                            return [self._normalize(m) for m in materials[:limit]]
        except Exception as e:
            logger.warning(f"TikTok Creative Center error: {e}")
        return []

    def _normalize(self, raw: dict) -> dict:
        video = raw.get("video_info") or {}
        return {
            "id": str(raw.get("material_id", "")),
            "brand_name": raw.get("brand_name") or raw.get("advertiser_name") or "",
            "ad_title": raw.get("ad_title") or (raw.get("voice_over_texts") or [""])[0],
            "video_info": {"duration": video.get("duration", 0), "cover": video.get("vid_cover_url") or ""},
            "cost": raw.get("cost") or "",
            "country_code": raw.get("country_code") or "VN",
            "industry": raw.get("industry_key") or "",
            "likes": raw.get("like_count") or 0,
            "comments": raw.get("comment_count") or 0,
            "shares": raw.get("share_count") or 0,
            "trending_score": round(min(1.0, ((raw.get("like_count") or 0) / 100000)), 2),
            "keywords": [],
        }

    async def search_ads(self, keyword: str, country: str = "VN", limit: int = 20) -> list[dict]:
        ads = await self.get_trending_ads(country=country, limit=50)
        if not ads:
            kw_lower = keyword.lower()
            demo = [a for a in _DEMO_TIKTOK_ADS if any(kw_lower in k for k in a.get("keywords", []))]
            return (demo or _DEMO_TIKTOK_ADS)[:limit]
        kw_lower = keyword.lower()
        filtered = [a for a in ads if kw_lower in (a.get("ad_title") or "").lower() or kw_lower in (a.get("brand_name") or "").lower()]
        return (filtered or ads)[:limit]

    def get_demo_ads(self, keyword: str = "", limit: int = 20) -> list[dict]:
        if keyword:
            kw_lower = keyword.lower()
            filtered = [a for a in _DEMO_TIKTOK_ADS if any(kw_lower in k for k in a.get("keywords", []))]
            return (filtered or _DEMO_TIKTOK_ADS)[:limit]
        return _DEMO_TIKTOK_ADS[:limit]
