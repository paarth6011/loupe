from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    false,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Account(Base):
    """A tenant. Every domain row belongs to exactly one account, and
    cross-account access is blocked by Postgres row-level security (see the
    0010 migration and docs/multi-tenancy.md)."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(32), nullable=False, server_default="free")
    # Per-tenant Slack/Discord webhook for alert notifications. Null -> fall back
    # to the global NOTIFY_WEBHOOK_URL (self-host) or send nothing (hosted). Set
    # via the dashboard; validated to an https Slack/Discord host (see
    # schemas/notifications.py) so a tenant-supplied URL can't be an SSRF vector.
    notify_webhook_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class User(Base):
    """An authenticated principal belonging to one account. ``id`` is the
    subject the access token resolves to; the token also carries ``account_id``
    so each request runs scoped to a single tenant."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The stable link to the Supabase Auth user (their JWT `sub`, a UUID). This,
    # not email, is what we look up by — email can change in Supabase, the id
    # cannot. Null for non-Supabase principals (e.g. the self-host admin).
    supabase_user_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, index=True, nullable=True
    )
    # Mirrored from the token for display; nullable because non-email providers
    # (OAuth/phone) may omit it. Unique still holds (Postgres allows many NULLs).
    email: Mapped[str | None] = mapped_column(
        String(320), unique=True, index=True, nullable=True
    )
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="owner"
    )  # "owner" | "member"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    account: Mapped["Account"] = relationship(back_populates="users")


class Workload(Base):
    __tablename__ = "workloads"

    # Workload names are unique *per account*, not globally — two tenants may
    # each have a "support-bot". Row-level security keeps one account from ever
    # seeing another's, so the name only needs to be unique within the account.
    __table_args__ = (
        UniqueConstraint("account_id", "name", name="uq_workload_account_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When true, this workload appears on the public, no-auth status page.
    public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=false()
    )

    samples: Mapped[list["MetricSample"]] = relationship(
        back_populates="workload", cascade="all, delete-orphan"
    )
    alerts: Mapped[list["Alert"]] = relationship(
        back_populates="workload", cascade="all, delete-orphan"
    )
    monitors: Mapped[list["Monitor"]] = relationship(
        back_populates="workload", cascade="all, delete-orphan"
    )


class MetricSample(Base):
    __tablename__ = "metric_samples"

    # Window/aggregation queries all filter "workload_id == ? AND ts >= ?", which
    # the two single-column indexes serve poorly; this composite covers them.
    # The (account_id, ts) index covers account-wide windows (e.g. /metrics/cost)
    # that span every workload in a tenant.
    __table_args__ = (
        Index("ix_samples_workload_ts", "workload_id", "ts"),
        Index("ix_samples_account_ts", "account_id", "ts"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True, nullable=False
    )
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # "ok" | "error"
    tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)  # legacy total

    # LLM-workload fields (all nullable; HTTP probes leave them empty).
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    operation: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # e.g. "rate_limit" | "timeout" | "content_filter"
    error_type: Mapped[str | None] = mapped_column(String(32), nullable=True)

    workload: Mapped["Workload"] = relationship(back_populates="samples")


class Alert(Base):
    __tablename__ = "alerts"

    # Enforce the dedup invariant in the DB: at most one *unresolved* alert per
    # (workload, rule). Without this, concurrent ingests race and create
    # duplicate open alerts (and duplicate notifications/summaries). A partial
    # unique index lets a new alert open again once the prior one is resolved.
    __table_args__ = (
        Index(
            "uq_open_alert_per_rule",
            "workload_id",
            "rule",
            unique=True,
            sqlite_where=text("resolved_at IS NULL"),
            postgresql_where=text("resolved_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(String(512), nullable=False)
    severity: Mapped[str] = mapped_column(
        String(16), nullable=False, default="warning"
    )  # "info" | "warning" | "critical"
    # Which detector raised this alert, for explainability.
    detector: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="threshold"
    )  # "threshold" | "zscore" | "seasonal"
    # Plain-English incident summary, populated asynchronously by the LLM.
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    workload: Mapped["Workload"] = relationship(back_populates="alerts")


class ApiKey(Base):
    """A revocable ingestion credential for `POST /metrics`.

    Only a SHA-256 hash of the key is stored; the plaintext is shown once at
    creation and never again. ``prefix`` keeps a short, non-secret slice for
    display so a key can be recognised in the UI.
    """

    __tablename__ = "api_keys"

    id: Mapped[int] = mapped_column(primary_key=True)
    # The ingestion boundary: a key belongs to one account, so POST /metrics with
    # this key stamps account_id on the sample (and any auto-created workload).
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    prefix: Mapped[str] = mapped_column(String(32), nullable=False)
    key_hash: Mapped[str] = mapped_column(
        String(64), unique=True, index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class Monitor(Base):
    """A per-workload override for one alert rule.

    At most one row per (workload, rule). ``threshold`` is null to keep the
    global default; a non-null value overrides it. ``enabled`` false mutes the
    rule for this workload (and resolves any of its open alerts on next ingest).
    """

    __tablename__ = "monitors"
    __table_args__ = (UniqueConstraint("workload_id", "rule", name="uq_monitor_rule"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    workload: Mapped["Workload"] = relationship(back_populates="monitors")


class BaselineProfile(Base):
    """A seasonal (time-of-day) baseline for one workload + metric + hour bucket.

    The rolling-window z-score (see detection.py) compares recent calls to the
    immediately-preceding ones, so a workload with a daily rhythm — e.g. always
    slow at 9am — either false-positives every morning (narrow window) or needs a
    window so wide it reacts slowly and hides real spikes (wide window). This
    table breaks that trade-off: a background job (see baselines.py) precomputes a
    robust baseline (median + MAD) per *hour of day* from recent history, so the
    detector compares 9am traffic to *this workload's typical 9am*, not to the
    quieter calls just before it.

    One row per (workload, metric, bucket); ``bucket`` is the UTC hour-of-day
    (0–23). Recomputed in full each refresh, so rows are disposable derived state.
    """

    __tablename__ = "baseline_profiles"
    __table_args__ = (
        UniqueConstraint(
            "workload_id", "metric", "bucket", name="uq_baseline_wl_metric_bucket"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workload_id: Mapped[int] = mapped_column(
        ForeignKey("workloads.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric: Mapped[str] = mapped_column(String(16), nullable=False)  # "latency"|"cost"
    bucket: Mapped[int] = mapped_column(Integer, nullable=False)  # UTC hour-of-day 0–23
    # Robust baseline: median as the center, MAD×1.4826 as a std-equivalent scale.
    center: Mapped[float] = mapped_column(Float, nullable=False)
    scale: Mapped[float] = mapped_column(Float, nullable=False)
    n: Mapped[int] = mapped_column(Integer, nullable=False)  # samples behind it
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
