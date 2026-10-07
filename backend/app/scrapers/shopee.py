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

    async def get_trending_public(self, keyword: str = "", limit: int = 50) -> list[dict]:
        """Public Shopee search sorted by sales — no affiliate credentials needed.

        When keyword is empty, sweeps across popular product categories to
        build a broader trending list (deduped by item_id).
        """
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
                        return [self._normalize_search_item(i) for i in resp.json().get("items", []) if i]
            except Exception as e:
                logger.debug(f"Public search failed for '{kw}': {e}")
            return []

        if keyword:
            return await _fetch(keyword, limit)

        # No keyword: sweep popular categories, collect up to `limit` unique products
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
            await asyncio.sleep(0.3)   # polite crawl delay
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
        params = {
            "by": "relevancy", "keyword": keyword, "limit": limit,
            "newest": 0, "order": "desc",
            "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH", "version": 2,
        }
        headers = self._browser_headers(f"https://shopee.vn/search?keyword={keyword}")
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    items = data.get("items") or []
                    return [self._normalize_search_item(i) for i in items if i]
                logger.warning(f"Shopee search HTTP {resp.status_code} for '{keyword}'")
        except Exception as e:
            logger.warning(f"Shopee search error for '{keyword}': {e}")
        return []

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
