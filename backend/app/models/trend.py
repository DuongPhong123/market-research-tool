from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class TrendKeyword(Base):
    __tablename__ = "trend_keywords"

    id = Column(Integer, primary_key=True)
    keyword = Column(String(300), unique=True, nullable=False)
    frequency = Column(Integer, default=1)
    sources = Column(JSON)
    trend_score = Column(Float, default=0.0)
    velocity = Column(Float, default=0.0)
    category_guess = Column(String(200))
    first_seen = Column(DateTime, server_default=func.now())
    last_seen = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_kw_trend", "trend_score"),
        Index("idx_kw_velocity", "velocity"),
    )


class TrendReport(Base):
    __tablename__ = "trend_reports"

    id = Column(Integer, primary_key=True)
    report_date = Column(DateTime, server_default=func.now())
    top_shopee_products = Column(JSON)
    top_fb_ads = Column(JSON)
    top_ig_posts = Column(JSON)
    top_keywords = Column(JSON)
    top_pain_points = Column(JSON)
    categories_trend = Column(JSON)
    summary = Column(Text)
    created_at = Column(DateTime, server_default=func.now())


class CrawlLog(Base):
    __tablename__ = "crawl_logs"

    id = Column(Integer, primary_key=True)
    source = Column(String(50))
    status = Column(String(20))
    records_fetched = Column(Integer, default=0)
    error_message = Column(Text)
    started_at = Column(DateTime, server_default=func.now())
    finished_at = Column(DateTime)
    duration_seconds = Column(Float)
