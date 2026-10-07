from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Boolean, Index
from sqlalchemy.sql import func
from app.database import Base


class ShopeeProduct(Base):
    __tablename__ = "shopee_products"

    id = Column(Integer, primary_key=True)
    item_id = Column(String(50), unique=True, nullable=False)
    shop_id = Column(String(50))
    name = Column(Text)
    category = Column(String(200))
    price = Column(Float)
    price_min = Column(Float)
    price_max = Column(Float)
    sold = Column(Integer, default=0)
    sold_delta = Column(Integer, default=0)
    rating = Column(Float)
    review_count = Column(Integer, default=0)
    liked_count = Column(Integer, default=0)
    shop_name = Column(String(200))
    image_url = Column(Text)
    product_url = Column(Text)
    affiliate_url = Column(Text)
    commission_rate = Column(Float)
    is_shopee_mall = Column(Boolean, default=False)
    trending_score = Column(Float, default=0.0)
    keywords = Column(JSON)
    first_seen = Column(DateTime, server_default=func.now())
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_trending_score", "trending_score"),
        Index("idx_category", "category"),
        Index("idx_sold", "sold"),
    )


class ShopeeReview(Base):
    __tablename__ = "shopee_reviews"

    id = Column(Integer, primary_key=True)
    item_id = Column(String(50), nullable=False, index=True)
    review_id = Column(String(100), unique=True)
    author = Column(String(200))
    rating = Column(Integer)
    content = Column(Text)
    sentiment_score = Column(Float)
    keywords = Column(JSON)
    created_at = Column(DateTime)
    crawled_at = Column(DateTime, server_default=func.now())
