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


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (FastAPI dependency-friendly)."""
    return Settings()
