from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure development defaults. Allowed in dev; refused in production.
INSECURE_JWT_SECRET = "change-me-in-prod"
INSECURE_ADMIN_PASSWORD = "admin"


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "dev" (default) allows insecure defaults; "prod"/"production" refuses them.
    environment: str = "dev"

    # Database
    database_url: str = "postgresql+psycopg://cloudops:cloudops@db:5432/cloudops"

    # Comma-separated allowed CORS origins (frontend URL in prod).
    cors_origins: str = "http://localhost:5173"

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

    # LLM incident summaries (Phase 2). Empty key -> template fallback.
    anthropic_api_key: str = ""
    summary_model: str = "claude-haiku-4-5"

    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"prod", "production"}

    def insecure_defaults(self) -> list[str]:
        """Return human-readable descriptions of any insecure default in use."""
        problems: list[str] = []
        if self.jwt_secret == INSECURE_JWT_SECRET:
            problems.append("JWT_SECRET is the insecure default")
        if self.admin_password == INSECURE_ADMIN_PASSWORD:
            problems.append("ADMIN_PASSWORD is the insecure default 'admin'")
        return problems


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor (FastAPI dependency-friendly)."""
    return Settings()
