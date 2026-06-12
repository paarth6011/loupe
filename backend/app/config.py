from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure development defaults. Allowed in dev; refused in production.
INSECURE_JWT_SECRET = "change-me-in-prod"
INSECURE_ADMIN_PASSWORD = "admin"


class Settings(BaseSettings):
    """Application configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Secure by default: "prod" refuses insecure defaults at boot. Opt into the
    # convenient-but-insecure dev mode explicitly (ENVIRONMENT=dev) — the local
    # Compose stack and the test suite do exactly that. A deployment that simply
    # forgets to set this therefore fails closed instead of silently enabling
    # dev-login and accepting the placeholder JWT secret.
    environment: str = "prod"

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

    # Cap on auto-created workloads (any valid ingest key can mint one by name).
    # 0 disables the cap.
    max_workloads: int = 1000

    # Reject ingest samples whose client-supplied `ts` is further than this many
    # seconds in the future. An unbounded future timestamp lets a holder of an
    # ingest key push samples past the retention cutoff (so they're never pruned)
    # or fabricate not-yet-happened history. A small window absorbs ordinary
    # clock drift between the source and the server. 0 disables the check.
    ingest_max_future_skew_seconds: int = 300

    # Alerting thresholds (evaluated on ingest)
    latency_threshold_ms: int = 1000
    error_rate_threshold: float = 0.5  # fraction of recent samples that are errors
    error_rate_window: int = 20  # number of most-recent samples to consider
    error_rate_min_samples: int = 5  # need at least this many before evaluating rate

    # LLM-specific alerting thresholds. These rules read the LLM sample fields
    # (cost_usd, tokens, error_type) and stay dormant for HTTP-only workloads,
    # where those fields are null.
    cost_per_request_threshold_usd: float = 1.0  # a single call over this is unusual
    token_per_request_threshold: int = 100_000  # tokens (in+out) for one call
    rate_limit_threshold: float = 0.2  # fraction of recent calls that are 429s
    rate_limit_min_samples: int = 5  # need at least this many before evaluating

    # Data retention. 0 disables pruning (keep forever). When > 0, samples older
    # than this many days are deleted; a background sweep runs every
    # retention_sweep_hours. Resolved alerts older than the cutoff go too.
    retention_days: int = 0
    retention_sweep_hours: int = 24

    # Statistical anomaly detection (rolling-window z-score, per workload+metric).
    # Learns each workload's own baseline instead of using a fixed threshold.
    anomaly_recent_samples: int = 5  # newest calls compared against the baseline
    anomaly_baseline_window: int = 100  # max older calls used to learn the baseline
    anomaly_min_baseline: int = 20  # need at least this many baseline calls to judge
    anomaly_z_threshold: float = 3.0  # std-devs above baseline before firing

    # Redis cache (Phase 2)
    redis_url: str = "redis://redis:6379/0"
    summary_cache_ttl_seconds: int = 15

    # LLM incident summaries (Phase 2). Empty key -> template fallback.
    # Which summarizer to use:
    #   "auto"     -> Claude if an API key is set, else the $0 template (default)
    #   "template" -> always the deterministic, no-API template
    #   "claude"   -> Anthropic API (falls back to template if no key)
    #   "ollama"   -> a local Ollama server ($0, offline)
    summary_provider: str = "auto"
    anthropic_api_key: str = ""
    summary_model: str = "claude-haiku-4-5"
    # Local Ollama (used when summary_provider="ollama"). From inside Docker, a
    # host-run Ollama is typically http://host.docker.internal:11434.
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Alert notifications. Empty -> notifications disabled (NullNotifier).
    # Works with Slack / Discord / generic webhook receivers.
    notify_webhook_url: str = ""

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
