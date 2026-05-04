"""Application configuration loaded from environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────
    environment: Literal["development", "staging", "production"] = "development"
    cors_origins: list[str] = ["http://localhost:3000"]

    # ── Nexus AI (OpenAI-compatible) ─────────────────────────
    nexus_api_key: str = ""
    nexus_api_base_url: str = "https://api.openai.com/v1"
    nexus_model: str = "gpt-4o"

    # ── Groq (fast inference fallback) ───────────────────────
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    # ── Market Data APIs ─────────────────────────────────────
    # Polygon.io — real-time + historical equities & options
    polygon_api_key: str = ""
    polygon_base_url: str = "https://api.polygon.io"

    # Alpha Vantage — free historical OHLCV fallback
    alpha_vantage_api_key: str = ""
    alpha_vantage_base_url: str = "https://www.alphavantage.co/query"

    # Tradier — options chains (free sandbox available)
    tradier_api_key: str = ""
    tradier_base_url: str = "https://sandbox.tradier.com/v1"  # swap for api.tradier.com in prod

    # ── Event Intelligence APIs ──────────────────────────────
    # Alpha Vantage NEWS_SENTIMENT uses ALPHA_VANTAGE_API_KEY when available.
    news_api_key: str = ""
    news_api_base_url: str = "https://newsapi.org/v2"
    twitter_bearer_token: str = ""
    social_sentiment_api_url: str = ""
    social_sentiment_api_key: str = ""
    event_intelligence_autostart: bool = False
    event_intelligence_interval_seconds: int = 900
    event_intelligence_symbols: list[str] = ["SPY", "QQQ", "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META"]

    # ── Database ─────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./nexus_trader.db"

    # ── Auth ─────────────────────────────────────────────────
    jwt_secret_key: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7  # 1 week


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
