import asyncio
import json
import logging
import re
from typing import Optional
import httpx
from playwright.async_api import async_playwright
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v18.0"


class InstagramGraphScraper:
    def __init__(self):
        self.token = settings.facebook_access_token

    async def get_hashtag_id(self, hashtag: str) -> Optional[str]:
        ig_user_id = await self._get_ig_user_id()
        if not ig_user_id:
            return None
        params = {"access_token": self.token, "user_id": ig_user_id, "q": hashtag.lstrip("#")}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/ig_hashtag_search", params=params)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return data[0]["id"] if data else None
        return None

    async def _get_ig_user_id(self) -> Optional[str]:
        params = {"access_token": self.token, "fields": "instagram_business_account{id}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/me/accounts", params=params)
            if resp.status_code == 200:
                pages = resp.json().get("data", [])
                for page in pages:
                    ig = page.get("instagram_business_account")
                    if ig:
                        return ig["id"]
        return None

    async def get_hashtag_top_media(self, hashtag: str, limit: int = 30) -> list[dict]:
        hashtag_id = await self.get_hashtag_id(hashtag)
        if not hashtag_id:
            logger.warning(f"Khong lay duoc ID cho hashtag #{hashtag}, dung web scraper thay the")
            return []
        ig_user_id = await self._get_ig_user_id()
        params = {
            "access_token": self.token, "user_id": ig_user_id, "limit": limit,
            "fields": "id,caption,like_count,comments_count,media_type,media_url,permalink,timestamp",
        }
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/{hashtag_id}/top_media", params=params)
            if resp.status_code == 200:
                return [self._normalize_post(p, hashtag) for p in resp.json().get("data", [])]
        return []

    async def get_post_comments(self, media_id: str, limit: int = 50) -> list[dict]:
        params = {"access_token": self.token, "fields": "id,text,username,like_count,timestamp", "limit": limit}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(f"{GRAPH_URL}/{media_id}/comments", params=params)
            if resp.status_code == 200:
                return [
                    {"source": "instagram", "post_id": media_id, "comment_id": c.get("id", ""),
                     "content": c.get("text") or "", "author": c.get("username") or "An danh", "likes": c.get("like_count") or 0}
                    for c in resp.json().get("data", [])
                ]
        return []

    def _normalize_post(self, raw: dict, hashtag: str) -> dict:
        caption = raw.get("caption") or ""
        return {
            "post_id": raw.get("id", ""), "caption": caption,
            "hashtags": re.findall(r"#(\w+)", caption),
            "likes_count": raw.get("like_count") or 0,
            "comments_count": raw.get("comments_count") or 0,
            "media_type": raw.get("media_type") or "IMAGE",
            "media_url": raw.get("media_url") or "",
            "post_url": raw.get("permalink") or "",
            "post_date": raw.get("timestamp"),
            "source_hashtag": hashtag,
        }


class InstagramWebScraper:
    @retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=2, min=3, max=15))
    async def scrape_hashtag(self, hashtag: str, max_posts: int = 20) -> list[dict]:
        hashtag = hashtag.lstrip("#")
        posts = []
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            ctx = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
            )
            page = await ctx.new_page()
            try:
                await page.goto(f"https://www.instagram.com/explore/tags/{hashtag}/", wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                content = await page.content()
                posts = self._parse_hashtag_page(content, hashtag)
                if not posts:
                    post_links = await page.query_selector_all("article a[href*='/p/']")
                    for link in post_links[:max_posts]:
                        href = await link.get_attribute("href")
                        if href:
                            post_data = await self._scrape_single_post(ctx, f"https://www.instagram.com{href}")
                            if post_data:
                                posts.append(post_data)
                            await asyncio.sleep(1.5)
            except Exception as e:
                logger.error(f"Loi scrape Instagram #{hashtag}: {e}")
            finally:
                await browser.close()
        return posts[:max_posts]

    async def _scrape_single_post(self, ctx, url: str) -> Optional[dict]:
        page = await ctx.new_page()
        try:
            await page.goto(url, timeout=20000, wait_until="domcontentloaded")
            await asyncio.sleep(2)
            caption = ""
            try:
                caption_el = await page.query_selector("div[data-testid='post-comment-root'] span")
                if caption_el:
                    caption = await caption_el.inner_text()
            except Exception:
                pass
            post_id = re.search(r"/p/([^/]+)/", url)
            return {
                "post_id": post_id.group(1) if post_id else "",
                "caption": caption, "hashtags": re.findall(r"#(\w+)", caption),
                "likes_count": 0, "comments_count": 0,
                "media_type": "IMAGE", "media_url": "", "post_url": url, "post_date": None,
            }
        except Exception as e:
            logger.error(f"Loi scrape post {url}: {e}")
            return None
        finally:
            await page.close()

    def _parse_hashtag_page(self, html: str, hashtag: str) -> list[dict]:
        matches = re.findall(r"window\.__additionalDataLoaded\('.*?',(\{.*?\})\);", html)
        posts = []
        for match in matches:
            try:
                data = json.loads(match)
                edges = data.get("data", {}).get("hashtag", {}).get("edge_hashtag_to_media", {}).get("edges", [])
                for edge in edges:
                    node = edge.get("node", {})
                    caption_edges = node.get("edge_media_to_caption", {}).get("edges", [])
                    caption = caption_edges[0]["node"]["text"] if caption_edges else ""
                    posts.append({
                        "post_id": node.get("id", ""), "caption": caption,
                        "hashtags": re.findall(r"#(\w+)", caption),
                        "likes_count": node.get("edge_liked_by", {}).get("count") or 0,
                        "comments_count": node.get("edge_media_to_comment", {}).get("count") or 0,
                        "media_type": "VIDEO" if node.get("is_video") else "IMAGE",
                        "media_url": node.get("thumbnail_src") or node.get("display_url") or "",
                        "post_url": f"https://www.instagram.com/p/{node.get('shortcode', '')}/",
                        "post_date": node.get("taken_at_timestamp"), "source_hashtag": hashtag,
                    })
            except Exception:
                continue
        return posts
