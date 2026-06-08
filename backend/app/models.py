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


class Workload(Base):
    __tablename__ = "workloads"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
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

    id: Mapped[int] = mapped_column(primary_key=True)
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
    )  # "threshold" | "zscore"
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
