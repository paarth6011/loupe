from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://cloudops:cloudops@db:5432/cloudops"

    # Auth
    jwt_secret: str = "change-me-in-prod"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Single-role MVP admin user
    admin_username: str = "admin"
    admin_password: str = "admin"

    # Alerting thresholds (evaluated on ingest)
    latency_threshold_ms: int = 1000
    error_rate_threshold: float = 0.5  # fraction of recent samples that are errors
    error_rate_window: int = 20  # number of most-recent samples to consider
    error_rate_min_samples: int = 5  # need at least this many before evaluating rate

    # Redis cache (Phase 2)
    redis_url: str = "redis://redis:6379/0"
    summary_cache_ttl_seconds: int = 15


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (FastAPI dependency-friendly)."""
    return Settings()
