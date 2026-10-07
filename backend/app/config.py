from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    shopee_app_id: str = ""
    shopee_secret_key: str = ""

    facebook_access_token: str = ""
    facebook_app_id: str = ""
    facebook_app_secret: str = ""

    database_url: str = "sqlite+aiosqlite:///./data/market_research.db"
    secret_key: str = "change-this-secret-key"

    crawl_interval_hours: int = 6
    max_products_per_crawl: int = 100

    http_proxy: Optional[str] = None
    https_proxy: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
