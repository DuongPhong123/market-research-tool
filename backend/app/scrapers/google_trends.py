import asyncio
import logging
from typing import Optional
import httpx
import xml.etree.ElementTree as ET

logger = logging.getLogger(__name__)

_DEMO_TRENDING = [
    "váy đầm hàn quốc", "kem chống nắng anessa", "son môi romand", "nồi chiên không dầu philips",
    "serum vitamin c klairs", "túi tote canvas", "blazer oversize nữ", "collagen shiseido nhật",
    "giày sneaker nike", "đầm maxi boho", "skincare routine ban đêm", "toner hàn quốc innisfree",
    "quần jeans ống rộng", "áo thun uniqlo", "mặt nạ dưỡng da jm solution"
]

_DEMO_RELATED = {
    "son môi": ["son romand", "son lì", "son bóng", "son dưỡng innisfree", "son mac"],
    "váy đầm": ["váy linen", "váy hàn quốc", "đầm dự tiệc", "váy midi", "váy oversize"],
    "kem chống nắng": ["kem chống nắng anessa", "kem chống nắng skin aqua", "kem chống nắng rohto"],
}


class GoogleTrendsScraper:
    TRENDING_RSS = "https://trends.google.com/trends/trendingsearches/daily/rss?geo={geo}"

    async def get_trending_searches(self, geo: str = "VN", limit: int = 20) -> list[dict]:
        try:
            async with httpx.AsyncClient(timeout=10.0, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.get(self.TRENDING_RSS.format(geo=geo))
                if resp.status_code == 200:
                    root = ET.fromstring(resp.text)
                    trends = []
                    for item in root.findall(".//item"):
                        title_el = item.find("title")
                        traffic_el = item.find("{https://trends.google.com/trends/api/xml_enums}approx_traffic")
                        if title_el is not None:
                            trends.append({
                                "keyword": title_el.text or "",
                                "traffic": traffic_el.text if traffic_el is not None else "",
                                "source": "google_trends",
                            })
                    if trends:
                        return trends[:limit]
        except Exception as e:
            logger.warning(f"Google Trends RSS error: {e}")
        # Demo fallback
        return [{"keyword": kw, "traffic": f"{(20-i)*1000:,}+", "source": "google_trends_demo"}
                for i, kw in enumerate(_DEMO_TRENDING[:limit])]

    async def get_interest_over_time(self, keyword: str, geo: str = "VN") -> dict:
        try:
            from pytrends.request import TrendReq
            loop = asyncio.get_event_loop()
            def _fetch():
                pt = TrendReq(hl="vi-VN", tz=420, timeout=(10, 25))
                pt.build_payload([keyword], cat=0, timeframe="now 7-d", geo=geo)
                df = pt.interest_over_time()
                if df is not None and not df.empty and keyword in df.columns:
                    return [{"date": str(idx.date()), "value": int(row[keyword])} for idx, row in df.iterrows()]
                return []
            data = await loop.run_in_executor(None, _fetch)
            return {"keyword": keyword, "data": data, "geo": geo}
        except Exception as e:
            logger.warning(f"pytrends interest error: {e}")
            import random
            demo_data = [{"date": f"2024-10-{i+1:02d}", "value": random.randint(40, 100)} for i in range(7)]
            return {"keyword": keyword, "data": demo_data, "geo": geo, "demo": True}

    async def get_related_queries(self, keyword: str, geo: str = "VN") -> list[str]:
        try:
            from pytrends.request import TrendReq
            loop = asyncio.get_event_loop()
            def _fetch():
                pt = TrendReq(hl="vi-VN", tz=420, timeout=(10, 25))
                pt.build_payload([keyword], cat=0, timeframe="now 7-d", geo=geo)
                rq = pt.related_queries()
                results = []
                if keyword in rq and rq[keyword].get("top") is not None:
                    for _, row in rq[keyword]["top"].iterrows():
                        results.append(row["query"])
                return results[:10]
            return await loop.run_in_executor(None, _fetch)
        except Exception as e:
            logger.warning(f"pytrends related error: {e}")
            kw_lower = keyword.lower()
            for k, v in _DEMO_RELATED.items():
                if k in kw_lower:
                    return v
            return [f"{keyword} giá rẻ", f"{keyword} chính hãng", f"mua {keyword} ở đâu", f"{keyword} review", f"{keyword} tốt nhất"]
