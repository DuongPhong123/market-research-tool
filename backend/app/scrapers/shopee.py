import hashlib
import hmac
import time
import asyncio
import logging
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

logger = logging.getLogger(__name__)

# Popular Vietnamese product keywords used for public-API trending sweep
_TRENDING_KEYWORDS = [
    "son moi", "kem chong nang", "serum", "nuoc hoa hong",
    "quan ao nu", "giay dep", "tui xach", "phu kien toc",
    "do gia dung", "thuc pham chuc nang",
    "vay dam", "blazer nu", "quan jean nu", "ao thun", "skincare",
    "cushion phan nen", "mat na duong da", "dau goi dau", "sua rua mat", "toner",
]

# Demo products for when Shopee API is blocked — realistic Vietnamese market data
_DEMO_PRODUCTS = [
    {"item_id": "demo_001", "shop_id": "d001", "name": "Son môi lì ROMAND Zero Gram Matte Lip #17 Beige Nude", "price_min": 180, "price_max": 220, "sold": 15420, "rating": 4.9, "review_count": 3218, "liked_count": 8940, "shop_name": "ROMAND Official Store", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d001/demo_001", "category": "Son môi", "sold_delta": 245},
    {"item_id": "demo_002", "shop_id": "d002", "name": "Kem chống nắng Anessa Perfect UV Sunscreen SPF50+ PA++++ 60g", "price_min": 380, "price_max": 420, "sold": 28650, "rating": 4.8, "review_count": 6421, "liked_count": 19800, "shop_name": "ANESSA Official VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d002/demo_002", "category": "Kem chống nắng", "sold_delta": 512},
    {"item_id": "demo_003", "shop_id": "d003", "name": "Serum Vitamin C Klairs Freshly Juiced Vitamin Drop 35ml", "price_min": 290, "price_max": 350, "sold": 12300, "rating": 4.7, "review_count": 2890, "liked_count": 7650, "shop_name": "Dear Klairs Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d003/demo_003", "category": "Serum dưỡng da", "sold_delta": 188},
    {"item_id": "demo_004", "shop_id": "d004", "name": "Nước tẩy trang Bioderma Sensibio H2O 500ml cho da nhạy cảm", "price_min": 290, "price_max": 310, "sold": 35200, "rating": 4.9, "review_count": 8920, "liked_count": 24500, "shop_name": "Bioderma Vietnam", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d004/demo_004", "category": "Tẩy trang", "sold_delta": 620},
    {"item_id": "demo_005", "shop_id": "d005", "name": "Áo thun oversize basic unisex cotton 100% thoáng mát", "price_min": 85, "price_max": 120, "sold": 48900, "rating": 4.7, "review_count": 12400, "liked_count": 31200, "shop_name": "BASICS VN Store", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": False, "product_url": "https://shopee.vn/product/d005/demo_005", "category": "Áo thun", "sold_delta": 890},
    {"item_id": "demo_006", "shop_id": "d006", "name": "Giày thể thao nữ Nike Air Force 1 Low trắng chính hãng", "price_min": 2100, "price_max": 2500, "sold": 5680, "rating": 4.8, "review_count": 1890, "liked_count": 12300, "shop_name": "Nike Official Store", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d006/demo_006", "category": "Giày thể thao", "sold_delta": 95},
    {"item_id": "demo_007", "shop_id": "d007", "name": "Túi tote canvas basic nhiều màu đựng laptop A4", "price_min": 95, "price_max": 150, "sold": 67800, "rating": 4.6, "review_count": 18900, "liked_count": 45200, "shop_name": "Bag & Accessories", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": False, "product_url": "https://shopee.vn/product/d007/demo_007", "category": "Túi xách", "sold_delta": 1250},
    {"item_id": "demo_008", "shop_id": "d008", "name": "Viên uống collagen Shiseido Enriched Collagen 126 viên", "price_min": 850, "price_max": 950, "sold": 9870, "rating": 4.8, "review_count": 2340, "liked_count": 7890, "shop_name": "Shiseido Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d008/demo_008", "category": "Thực phẩm chức năng", "sold_delta": 165},
    {"item_id": "demo_009", "shop_id": "d009", "name": "Nồi chiên không dầu Philips HD9252 4.1L XXL chính hãng", "price_min": 1890, "price_max": 2100, "sold": 7650, "rating": 4.7, "review_count": 2100, "liked_count": 8900, "shop_name": "Philips Official Store", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d009/demo_009", "category": "Đồ gia dụng", "sold_delta": 125},
    {"item_id": "demo_010", "shop_id": "d010", "name": "Cushion Laneige Neo Cushion Matte SPF42 PA++ 15g", "price_min": 420, "price_max": 490, "sold": 19800, "rating": 4.8, "review_count": 4560, "liked_count": 13400, "shop_name": "LANEIGE Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d010/demo_010", "category": "Kem nền", "sold_delta": 340},
    {"item_id": "demo_011", "shop_id": "d011", "name": "Bộ dưỡng tóc TRESemmé Keratin Smooth Shampoo + Conditioner 400ml", "price_min": 165, "price_max": 200, "sold": 32400, "rating": 4.6, "review_count": 7800, "liked_count": 21000, "shop_name": "Unilever Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d011/demo_011", "category": "Chăm sóc tóc", "sold_delta": 580},
    {"item_id": "demo_012", "shop_id": "d012", "name": "Quần jean nữ ống rộng lưng cao xanh đậm phong cách Hàn Quốc", "price_min": 195, "price_max": 260, "sold": 41200, "rating": 4.7, "review_count": 9800, "liked_count": 28900, "shop_name": "Korean Fashion VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": False, "product_url": "https://shopee.vn/product/d012/demo_012", "category": "Quần jean", "sold_delta": 720},
    {"item_id": "demo_013", "shop_id": "d013", "name": "Mặt nạ đất sét Innisfree Super Volcanic Pore Clay Mask 100ml", "price_min": 210, "price_max": 250, "sold": 16700, "rating": 4.7, "review_count": 3890, "liked_count": 11200, "shop_name": "Innisfree Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d013/demo_013", "category": "Mặt nạ", "sold_delta": 290},
    {"item_id": "demo_014", "shop_id": "d014", "name": "Dép xỏ ngón nữ thời trang Havaianas Brasil Brazil Original", "price_min": 290, "price_max": 350, "sold": 22300, "rating": 4.5, "review_count": 5670, "liked_count": 15800, "shop_name": "Havaianas VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d014/demo_014", "category": "Dép", "sold_delta": 410},
    {"item_id": "demo_015", "shop_id": "d015", "name": "Nước hoa hồng Hada Labo Gokujyun Premium Lotion 170ml", "price_min": 175, "price_max": 210, "sold": 29800, "rating": 4.8, "review_count": 6700, "liked_count": 19500, "shop_name": "HADA LABO Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d015/demo_015", "category": "Nước hoa hồng", "sold_delta": 530},
    {"item_id": "demo_016", "shop_id": "d016", "name": "Máy rửa mặt Foreo Luna mini 3 sạch sâu massage da mặt", "price_min": 1950, "price_max": 2200, "sold": 4320, "rating": 4.8, "review_count": 980, "liked_count": 6700, "shop_name": "FOREO Official", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d016/demo_016", "category": "Dụng cụ làm đẹp", "sold_delta": 72},
    {"item_id": "demo_017", "shop_id": "d017", "name": "Váy linen cổ V tay ngắn dáng suông vintage thương hiệu nội địa", "price_min": 165, "price_max": 225, "sold": 38700, "rating": 4.7, "review_count": 9200, "liked_count": 26400, "shop_name": "LINEN STORY VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": False, "product_url": "https://shopee.vn/product/d017/demo_017", "category": "Váy đầm", "sold_delta": 680},
    {"item_id": "demo_018", "shop_id": "d018", "name": "Combo 3 hộp Bột matcha Nhật Bản Ito En Matcha Green Tea 100g", "price_min": 280, "price_max": 320, "sold": 18900, "rating": 4.6, "review_count": 4200, "liked_count": 12300, "shop_name": "Japan Import Food", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": False, "product_url": "https://shopee.vn/product/d018/demo_018", "category": "Thực phẩm", "sold_delta": 320},
    {"item_id": "demo_019", "shop_id": "d019", "name": "Kem dưỡng ẩm Cetaphil Moisturizing Cream 250g da khô nhạy cảm", "price_min": 190, "price_max": 230, "sold": 24600, "rating": 4.8, "review_count": 5870, "liked_count": 16800, "shop_name": "Cetaphil Official VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d019/demo_019", "category": "Kem dưỡng ẩm", "sold_delta": 430},
    {"item_id": "demo_020", "shop_id": "d020", "name": "Tai nghe không dây Sony WF-1000XM5 chống ồn chủ động ANC", "price_min": 5500, "price_max": 6200, "sold": 3120, "rating": 4.9, "review_count": 780, "liked_count": 9800, "shop_name": "Sony Store VN", "image_url": "", "affiliate_url": "", "commission_rate": 0, "is_shopee_mall": True, "product_url": "https://shopee.vn/product/d020/demo_020", "category": "Điện tử", "sold_delta": 52},
]


class ShopeeAffiliateScraper:
    BASE_URL = "https://open-api.affiliate.shopee.vn/graphql"
    SHOP_URL = "https://shopee.vn/api/v4"

    def __init__(self):
        self.app_id = settings.shopee_app_id
        self.secret_key = settings.shopee_secret_key

    def _has_affiliate_credentials(self) -> bool:
        """Return True only when real credentials are configured."""
        placeholder = ("your_app_id_here", "your_secret_key_here", "", None)
        return (
            str(self.app_id or "") not in placeholder
            and str(self.secret_key or "") not in placeholder
        )

    def _sign(self, payload: str) -> str:
        return hmac.new(
            self.secret_key.encode("utf-8"),
            payload.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def _build_headers(self, payload: str) -> dict:
        timestamp = int(time.time())
        sign_str = f"{self.app_id}{timestamp}{payload}"
        return {
            "Content-Type": "application/json",
            "Authorization": f"SHA256 Credential={self.app_id},Timestamp={timestamp},Signature={self._sign(sign_str)}",
        }

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def get_trending_products(self, keyword: str = "", category_id: int = 0, limit: int = 50, sort_type: int = 2) -> list[dict]:
        # Use public API when affiliate credentials are not yet approved
        if not self._has_affiliate_credentials():
            logger.info("Affiliate key not configured — using public Shopee API for trending")
            return await self.get_trending_public(keyword=keyword, limit=limit)

        query = """
        query getProductOffers($keyword: String, $categoryId: Int, $limit: Int, $sortType: Int) {
          productOfferV2(
            listType: OFFER_LIST_TYPE_BEST_SELLER,
            keyword: $keyword,
            categoryId: $categoryId,
            limit: $limit,
            sortType: $sortType
          ) {
            nodes {
              itemId shopId productName commissionRate offerLink
              sellerCommissionRate shopName isOnSale priceMin priceMax
              ratingStar sales imageUrl catId shopType
            }
          }
        }
        """
        variables = {"keyword": keyword, "categoryId": category_id, "limit": limit, "sortType": sort_type}
        import json
        payload_str = json.dumps({"query": query, "variables": variables}, separators=(",", ":"))
        headers = self._build_headers(payload_str)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(self.BASE_URL, content=payload_str, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
            if nodes:
                return [self._normalize_product(n) for n in nodes]
        except Exception as e:
            logger.warning(f"Affiliate API error, falling back to public: {e}")

        return await self.get_trending_public(keyword=keyword, limit=limit)

    def _browser_headers(self, referer: str = "https://shopee.vn/") -> dict:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer,
            "x-api-source": "pc",
            "x-requested-with": "XMLHttpRequest",
            "x-shopee-language": "vi",
            "Connection": "keep-alive",
        }

    def _demo_products_for_keyword(self, keyword: str, limit: int) -> list[dict]:
        """Return demo products matching keyword, or all demo products if no match."""
        kw = keyword.lower().strip()
        if not kw:
            return _DEMO_PRODUCTS[:limit]
        matched = [p for p in _DEMO_PRODUCTS if kw in p["name"].lower() or kw in p.get("category", "").lower()]
        if not matched:
            # Fallback: return all demo products (keyword may be transliterated/English)
            matched = _DEMO_PRODUCTS
        return matched[:limit]

    async def get_trending_public(self, keyword: str = "", limit: int = 50) -> list[dict]:
        """Public Shopee search sorted by sales. Falls back to demo data if blocked."""
        headers = self._browser_headers()

        async def _fetch(kw: str, n: int) -> list[dict]:
            url = f"{self.SHOP_URL}/search/search_items"
            params = {
                "by": "sales", "keyword": kw, "limit": min(n, 50),
                "newest": 0, "order": "desc",
                "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
            }
            try:
                async with httpx.AsyncClient(timeout=20.0) as client:
                    resp = await client.get(url, params=params, headers=headers)
                    if resp.status_code == 200:
                        body = resp.json()
                        items = body.get("items") or []
                        if items:
                            return [self._normalize_search_item(i) for i in items if i]
                    logger.debug(f"Shopee public search HTTP {resp.status_code} for '{kw}'")
            except Exception as e:
                logger.debug(f"Public search failed for '{kw}': {e}")
            return []

        if keyword:
            results = await _fetch(keyword, limit)
            if results:
                return results
            logger.info(f"Shopee blocked for '{keyword}' — using demo data")
            return self._demo_products_for_keyword(keyword, limit)

        # No keyword: sweep popular categories
        seen: set[str] = set()
        results: list[dict] = []
        per_kw = max(10, limit // len(_TRENDING_KEYWORDS))
        for kw in _TRENDING_KEYWORDS:
            batch = await _fetch(kw, per_kw)
            for item in batch:
                if item["item_id"] and item["item_id"] not in seen:
                    seen.add(item["item_id"])
                    results.append(item)
                    if len(results) >= limit:
                        return results
            await asyncio.sleep(0.3)

        if not results:
            logger.info("Shopee blocked for trending sweep — using demo data")
            return _DEMO_PRODUCTS[:limit]
        return results

    async def get_product_reviews(self, item_id: str, shop_id: str, limit: int = 50, offset: int = 0) -> list[dict]:
        url = f"{self.SHOP_URL}/item/get_ratings"
        params = {"itemid": item_id, "shopid": shop_id, "limit": limit, "offset": offset, "filter": 0, "type": 0}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://shopee.vn/product/{shop_id}/{item_id}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                ratings = resp.json().get("data", {}).get("ratings", [])
                return [self._normalize_review(r, item_id) for r in ratings]
        return []

    async def search_products(self, keyword: str, limit: int = 30) -> list[dict]:
        url = f"{self.SHOP_URL}/search/search_items"
        headers = self._browser_headers(f"https://shopee.vn/search?keyword={keyword}")
        page_size = 30
        max_pages = 3 if limit > 30 else 1
        results: list[dict] = []
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                for page in range(max_pages):
                    newest = page * page_size
                    params = {
                        "by": "relevancy", "keyword": keyword, "limit": page_size,
                        "newest": newest, "order": "desc",
                        "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
                    }
                    resp = await client.get(url, params=params, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        items = data.get("items") or []
                        results.extend([self._normalize_search_item(i) for i in items if i])
                        if len(items) < page_size:
                            break  # no more pages
                        if len(results) >= limit:
                            break
                        if page < max_pages - 1:
                            await asyncio.sleep(0.3)
                    else:
                        logger.warning(f"Shopee search HTTP {resp.status_code} for '{keyword}' page {page+1}")
                        break
            if results:
                return results[:limit]
        except Exception as e:
            logger.warning(f"Shopee search error for '{keyword}': {e}")

        logger.info(f"Shopee search blocked for '{keyword}' — using demo data")
        return self._demo_products_for_keyword(keyword, limit)

    async def get_flash_sale_products(self) -> list[dict]:
        promo_url = f"{self.SHOP_URL}/flash_sale/get_all_sessions"
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://shopee.vn/"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            promo_resp = await client.get(promo_url, headers=headers)
            if promo_resp.status_code != 200:
                return []
            sessions = promo_resp.json().get("data", {}).get("sessions", [])
            if not sessions:
                return []
            active = next((s for s in sessions if s.get("status") == 1), sessions[0])
            promotion_id = active.get("promotionid")
            url = f"{self.SHOP_URL}/flash_sale/flash_sale_batch_get_items"
            resp = await client.get(url, params={"promotionid": promotion_id, "limit": 50, "offset": 0}, headers=headers)
            if resp.status_code == 200:
                items = resp.json().get("data", {}).get("items", [])
                return [self._normalize_product(i) for i in items]
        return []

    def _normalize_product(self, raw: dict) -> dict:
        return {
            "item_id": str(raw.get("itemId") or raw.get("item_id") or raw.get("itemid", "")),
            "shop_id": str(raw.get("shopId") or raw.get("shop_id") or raw.get("shopid", "")),
            "name": raw.get("productName") or raw.get("name") or "",
            "price_min": (raw.get("priceMin") or raw.get("price_min") or 0) / 100000,
            "price_max": (raw.get("priceMax") or raw.get("price_max") or 0) / 100000,
            "sold": raw.get("sales") or raw.get("sold") or raw.get("historical_sold") or 0,
            "rating": raw.get("ratingStar") or raw.get("rating_star") or 0,
            "shop_name": raw.get("shopName") or raw.get("shop_name") or "",
            "image_url": raw.get("imageUrl") or raw.get("image") or "",
            "affiliate_url": raw.get("offerLink") or "",
            "commission_rate": raw.get("commissionRate") or raw.get("sellerCommissionRate") or 0,
            "is_shopee_mall": raw.get("shopType") == 1,
            "product_url": f"https://shopee.vn/product/{raw.get('shopId', '')}/{raw.get('itemId', '')}",
        }

    def _normalize_search_item(self, raw: dict) -> dict:
        basic = raw.get("item_basic") or raw
        item_rating = basic.get("item_rating") or {}
        rating_count = item_rating.get("rating_count")
        review_count = rating_count[0] if isinstance(rating_count, list) and rating_count else 0
        item_id = str(basic.get("itemid") or basic.get("item_id") or "")
        shop_id = str(basic.get("shopid") or basic.get("shop_id") or "")
        return {
            "item_id": item_id,
            "shop_id": shop_id,
            "name": basic.get("name") or "",
            "price_min": (basic.get("price_min") or basic.get("price") or 0) / 100000,
            "price_max": (basic.get("price_max") or basic.get("price") or 0) / 100000,
            "sold": basic.get("historical_sold") or basic.get("sold") or 0,
            "rating": item_rating.get("rating_star") or 0,
            "review_count": review_count,
            "liked_count": basic.get("liked_count") or 0,
            "shop_name": basic.get("shop_name") or "",
            "image_url": basic.get("image") or "",
            "affiliate_url": "",
            "commission_rate": 0,
            "is_shopee_mall": basic.get("shopee_verified") or False,
            "product_url": f"https://shopee.vn/product/{shop_id}/{item_id}",
        }

    def _normalize_review(self, raw: dict, item_id: str) -> dict:
        return {
            "item_id": item_id,
            "review_id": str(raw.get("cmtid") or raw.get("id") or ""),
            "author": raw.get("author_username") or raw.get("username") or "An danh",
            "rating": raw.get("rating_star") or raw.get("rating") or 0,
            "content": raw.get("comment") or raw.get("content") or "",
            "created_at": raw.get("ctime"),
        }
