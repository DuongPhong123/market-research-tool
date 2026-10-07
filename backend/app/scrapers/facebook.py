import asyncio
import logging
from datetime import datetime
from typing import Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

logger = logging.getLogger(__name__)

ADS_LIBRARY_URL = "https://graph.facebook.com/v18.0/ads_archive"
GRAPH_URL = "https://graph.facebook.com/v18.0"


class FacebookAdsScraper:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.facebook_access_token

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def search_ads(self, search_terms: str, country: str = "VN", ad_type: str = "ALL", limit: int = 50, active_status: str = "ACTIVE") -> list[dict]:
        params = {
            "access_token": self.token,
            "ad_type": ad_type,
            "ad_reached_countries": country,
            "search_terms": search_terms,
            "ad_active_status": active_status,
            "limit": limit,
            "fields": ",".join([
                "id", "page_id", "page_name", "ad_creative_bodies", "ad_creative_link_titles",
                "ad_creative_link_descriptions", "ad_creative_link_captions",
                "ad_delivery_start_time", "ad_delivery_stop_time", "currency",
                "spend", "impressions", "publisher_platforms", "languages",
                "target_ages", "target_gender", "target_locations",
            ]),
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(ADS_LIBRARY_URL, params=params)
            resp.raise_for_status()
            data = resp.json()

        ads = data.get("data", [])
        result = [self._normalize_ad(a) for a in ads]

        next_cursor = data.get("paging", {}).get("cursors", {}).get("after")
        if next_cursor and len(result) < limit:
            more = await self._fetch_next_page(params, next_cursor, limit - len(result))
            result.extend(more)

        return result

    async def _fetch_next_page(self, params: dict, cursor: str, limit: int) -> list[dict]:
        params = {**params, "after": cursor, "limit": min(limit, 50)}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(ADS_LIBRARY_URL, params=params)
            if resp.status_code == 200:
                return [self._normalize_ad(a) for a in resp.json().get("data", [])]
        return []

    async def search_ads_by_page(self, page_id: str, limit: int = 30) -> list[dict]:
        params = {
            "access_token": self.token, "ad_type": "ALL", "search_page_ids": page_id,
            "ad_active_status": "ALL", "limit": limit,
            "fields": "id,page_id,page_name,ad_creative_bodies,ad_creative_link_titles,spend,impressions,ad_delivery_start_time,publisher_platforms",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(ADS_LIBRARY_URL, params=params)
            resp.raise_for_status()
            return [self._normalize_ad(a) for a in resp.json().get("data", [])]

    def _normalize_ad(self, raw: dict) -> dict:
        bodies = raw.get("ad_creative_bodies") or []
        titles = raw.get("ad_creative_link_titles") or []
        spend = raw.get("spend") or {}
        impressions = raw.get("impressions") or {}
        return {
            "ad_id": str(raw.get("id", "")),
            "page_id": str(raw.get("page_id", "")),
            "page_name": raw.get("page_name") or "",
            "ad_creative_body": bodies[0] if bodies else "",
            "ad_creative_title": titles[0] if titles else "",
            "ad_creative_link_url": (raw.get("ad_creative_link_captions") or [""])[0],
            "currency": raw.get("currency") or "VND",
            "spend_min": int(spend.get("lower_bound") or 0),
            "spend_max": int(spend.get("upper_bound") or 0),
            "impressions_min": int(impressions.get("lower_bound") or 0),
            "impressions_max": int(impressions.get("upper_bound") or 0),
            "delivery_start": raw.get("ad_delivery_start_time"),
            "delivery_stop": raw.get("ad_delivery_stop_time"),
            "platforms": raw.get("publisher_platforms") or [],
            "languages": raw.get("languages") or [],
            "demographics": {"ages": raw.get("target_ages"), "gender": raw.get("target_gender")},
            "regions": raw.get("target_locations") or [],
        }


class FacebookPageScraper:
    def __init__(self, token: Optional[str] = None):
        self.token = token or settings.facebook_access_token

    async def search_pages(self, keyword: str, limit: int = 10) -> list[dict]:
        params = {"access_token": self.token, "q": keyword, "type": "page", "limit": limit, "fields": "id,name,fan_count,category,about"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/search", params=params)
            if resp.status_code == 200:
                return resp.json().get("data", [])
        return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def get_page_posts(self, page_id: str, limit: int = 30, days_back: int = 7) -> list[dict]:
        from datetime import timedelta
        since = int((datetime.now() - timedelta(days=days_back)).timestamp())
        params = {
            "access_token": self.token, "limit": limit, "since": since,
            "fields": "id,message,story,created_time,reactions.summary(true),comments.summary(true),shares",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/{page_id}/posts", params=params)
            if resp.status_code == 200:
                return resp.json().get("data", [])
        return []

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=8))
    async def get_post_comments(self, post_id: str, limit: int = 100, sort: str = "ranked") -> list[dict]:
        params = {
            "access_token": self.token, "limit": limit, "filter": "stream", "order": sort,
            "fields": "id,message,created_time,like_count,comment_count,from{name}",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/{post_id}/comments", params=params)
            if resp.status_code == 200:
                comments = resp.json().get("data", [])
                return [self._normalize_comment(c, post_id, "facebook") for c in comments]
        return []

    async def crawl_keyword_comments(self, keyword: str, max_posts: int = 10, max_comments_per_post: int = 50) -> list[dict]:
        pages = await self.search_pages(keyword, limit=5)
        all_comments = []
        for page in pages:
            posts = await self.get_page_posts(page["id"], limit=max_posts)
            for post in posts:
                comments = await self.get_post_comments(post["id"], limit=max_comments_per_post)
                all_comments.extend(comments)
                await asyncio.sleep(0.5)
        return all_comments

    def _normalize_comment(self, raw: dict, post_id: str, source: str) -> dict:
        return {
            "source": source, "post_id": post_id,
            "comment_id": raw.get("id", ""),
            "content": raw.get("message") or "",
            "author": (raw.get("from") or {}).get("name") or "An danh",
            "likes": raw.get("like_count") or 0,
        }
