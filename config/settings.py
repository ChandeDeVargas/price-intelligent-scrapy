"""
Central settings — loaded from environment variables / .env file.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Database
    database_url: str = "sqlite:///./price_intelligence.db"

    # Scraping
    scrape_delay: int = 2
    scrape_concurrent_request: int = 4
    scrape_interval_hours: int = 6

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_secret_key: str = "dev-secret-change-in-production"

    # Notifications (populated on Day 6)
    smtp_host: str = "smtp.gamil.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notification_from: str = ""
    webhook_url: str = ""

    # Price alert defaults
    default_price_drop_treshold: float = 5.0

@lru_cache
def get_settings() -> Settings:
    return Settings()