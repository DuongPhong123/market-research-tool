from fastapi import APIRouter, Query
from app.scrapers.tiktok import TikTokAdsScraper, _DEMO_TIKTOK_ADS
from app.scrapers.google_trends import GoogleTrendsScraper

router = APIRouter(prefix="/api/tiktok", tags=["TikTok & Google Trends"])

_tt = TikTokAdsScraper()
_gt = GoogleTrendsScraper()


@router.get("/trending-ads")
async def get_tiktok_trending(
    keyword: str = Query("", description="Filter keyword"),
    country: str = Query("VN"),
    limit: int = Query(20, ge=1, le=50),
):
    api_error = None
    ads = []
    try:
        ads = await _tt.search_ads(keyword, country=country, limit=limit)
    except Exception as e:
        api_error = str(e)

    if not ads:
        demo = _tt.get_demo_ads(keyword, limit)
        return {"keyword": keyword, "data": demo, "total": len(demo), "demo": True,
                "hint": "Dang hien thi du lieu DEMO. Du lieu that lay tu TikTok Creative Center."}

    return {"keyword": keyword, "data": ads, "total": len(ads)}


@router.get("/google-trends")
async def get_google_trends(geo: str = Query("VN"), limit: int = Query(15, ge=5, le=30)):
    results = await _gt.get_trending_searches(geo=geo, limit=limit)
    demo = not results or (results and results[0].get("source", "").endswith("_demo"))
    return {"data": results, "total": len(results), "geo": geo, "demo": demo}


@router.get("/google-trends/interest")
async def get_keyword_interest(keyword: str = Query(..., min_length=2), geo: str = Query("VN")):
    return await _gt.get_interest_over_time(keyword, geo=geo)


@router.get("/google-trends/related")
async def get_related_keywords(keyword: str = Query(..., min_length=2), geo: str = Query("VN")):
    related = await _gt.get_related_queries(keyword, geo=geo)
    return {"keyword": keyword, "related": related}
