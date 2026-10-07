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


class ShopeeAffiliateScraper:
    BASE_URL = "https://open-api.affiliate.shopee.vn/graphql"
    SHOP_URL = "https://shopee.vn/api/v4"

    def __init__(self):
        self.app_id = settings.shopee_app_id
        self.secret_key = settings.shopee_secret_key

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

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(self.BASE_URL, content=payload_str, headers=headers)
            resp.raise_for_status()
            data = resp.json()

        nodes = data.get("data", {}).get("productOfferV2", {}).get("nodes", [])
        return [self._normalize_product(n) for n in nodes]

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
        params = {"by": "relevancy", "keyword": keyword, "limit": limit, "newest": 0, "order": "desc", "page_type": "search", "scenario": "PAGE_GLOBAL_SEARCH", "version": 2}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": f"https://shopee.vn/search?keyword={keyword}"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url, params=params, headers=headers)
            if resp.status_code == 200:
                items = resp.json().get("items", [])
                return [self._normalize_search_item(i) for i in items if i]
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
        return {
            "item_id": str(basic.get("itemid") or basic.get("item_id") or ""),
            "shop_id": str(basic.get("shopid") or basic.get("shop_id") or ""),
            "name": basic.get("name") or "",
            "price_min": (basic.get("price_min") or basic.get("price") or 0) / 100000,
            "price_max": (basic.get("price_max") or basic.get("price") or 0) / 100000,
            "sold": basic.get("historical_sold") or basic.get("sold") or 0,
            "rating": basic.get("item_rating", {}).get("rating_star") or 0,
            "review_count": basic.get("item_rating", {}).get("rating_count", [0])[0] if basic.get("item_rating") else 0,
            "liked_count": basic.get("liked_count") or 0,
            "shop_name": "",
            "image_url": basic.get("image") or "",
            "affiliate_url": "",
            "commission_rate": 0,
            "is_shopee_mall": basic.get("shopee_verified") or False,
            "product_url": f"https://shopee.vn/product/{basic.get('shopid', '')}/{basic.get('itemid', '')}",
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
