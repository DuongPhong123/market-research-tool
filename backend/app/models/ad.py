from sqlalchemy import Column, String, Integer, Float, DateTime, Text, JSON, Index
from sqlalchemy.sql import func
from app.database import Base


class FacebookAd(Base):
    __tablename__ = "facebook_ads"

    id = Column(Integer, primary_key=True)
    ad_id = Column(String(100), unique=True, nullable=False)
    page_id = Column(String(100))
    page_name = Column(String(300))
    ad_creative_body = Column(Text)
    ad_creative_title = Column(Text)
    ad_creative_link_url = Column(Text)
    ad_creative_image_url = Column(Text)
    currency = Column(String(10))
    spend_min = Column(Integer)
    spend_max = Column(Integer)
    impressions_min = Column(Integer)
    impressions_max = Column(Integer)
    delivery_start = Column(DateTime)
    delivery_stop = Column(DateTime)
    platforms = Column(JSON)
    regions = Column(JSON)
    languages = Column(JSON)
    demographics = Column(JSON)
    keywords = Column(JSON)
    product_keywords = Column(JSON)
    engagement_estimate = Column(Float)
    trending_score = Column(Float, default=0.0)
    first_seen = Column(DateTime, server_default=func.now())
    last_updated = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("idx_fb_trending", "trending_score"),
        Index("idx_fb_page", "page_id"),
        Index("idx_fb_delivery", "delivery_start"),
    )


class InstagramPost(Base):
    __tablename__ = "instagram_posts"

    id = Column(Integer, primary_key=True)
    post_id = Column(String(100), unique=True, nullable=False)
    username = Column(String(200))
    caption = Column(Text)
    hashtags = Column(JSON)
    likes_count = Column(Integer, default=0)
    comments_count = Column(Integer, default=0)
    media_type = Column(String(20))
    media_url = Column(Text)
    post_url = Column(Text)
    post_date = Column(DateTime)
    keywords = Column(JSON)
    product_mentions = Column(JSON)
    sentiment_score = Column(Float)
    trending_score = Column(Float, default=0.0)
    crawled_at = Column(DateTime, server_default=func.now())

    __table_args__ = (
        Index("idx_ig_trending", "trending_score"),
        Index("idx_ig_hashtag", "hashtags"),
    )


class SocialComment(Base):
    __tablename__ = "social_comments"

    id = Column(Integer, primary_key=True)
    source = Column(String(20))
    post_id = Column(String(100), index=True)
    comment_id = Column(String(100), unique=True)
    content = Column(Text)
    author = Column(String(200))
    likes = Column(Integer, default=0)
    sentiment_score = Column(Float)
    keywords = Column(JSON)
    pain_points = Column(JSON)
    product_mentions = Column(JSON)
    crawled_at = Column(DateTime, server_default=func.now())
