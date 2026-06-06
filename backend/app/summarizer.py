from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert


@dataclass
class AlertContext:
    """The facts handed to a summarizer to describe an incident."""

    workload_name: str
    rule: str
    severity: str
    message: str
    sample_count: int
    error_rate: float
    p95_ms: float | None


def _render_context(ctx: AlertContext) -> str:
    p95 = f"{round(ctx.p95_ms)}ms" if ctx.p95_ms is not None else "n/a"
    return (
        f"Workload: {ctx.workload_name}\n"
        f"Alert rule: {ctx.rule} (severity: {ctx.severity})\n"
        f"Detail: {ctx.message}\n"
        f"Recent window: {ctx.sample_count} samples, "
        f"p95 latency {p95}, error rate {ctx.error_rate:.0%}"
    )


class Summarizer(Protocol):
    def summarize(self, ctx: AlertContext) -> str: ...


class TemplateSummarizer:
    """Deterministic, no-API fallback. Keeps the stack runnable with no key."""

    def summarize(self, ctx: AlertContext) -> str:
        p95 = f"{round(ctx.p95_ms)}ms" if ctx.p95_ms is not None else "n/a"
        return (
            f"[{ctx.severity.upper()}] {ctx.workload_name}: {ctx.rule} fired — "
            f"{ctx.message}. Over the last {ctx.sample_count} samples, p95 latency "
            f"was {p95} and the error rate was {ctx.error_rate:.0%}. "
            f"Investigate the workload's recent behavior."
        )


class ClaudeSummarizer:
    """Generates summaries via the Anthropic API (Claude Haiku 4.5).

    Resilient by construction: a short timeout plus one SDK retry. Any failure
    propagates to the caller, which leaves Alert.summary NULL (backfilled later).
    """

    _SYSTEM = (
        "You are an SRE assistant. Given an alert and recent metric context, "
        "write a concise 1-2 sentence plain-English incident summary for an "
        "on-call engineer: what happened and a likely area to look at. "
        "Respond with the summary only, no preamble."
    )

    def __init__(self, api_key: str, model: str, timeout: float = 5.0) -> None:
        import anthropic  # lazy import so the template path needs no dependency

        self._client = anthropic.Anthropic(
            api_key=api_key, timeout=timeout, max_retries=1
        )
        self._model = model

    def summarize(self, ctx: AlertContext) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=150,
            system=self._SYSTEM,
            messages=[{"role": "user", "content": _render_context(ctx)}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()


def get_summarizer() -> Summarizer:
    """Use Claude when an API key is configured, else the no-key template."""
    settings = get_settings()
    if settings.anthropic_api_key:
        return ClaudeSummarizer(settings.anthropic_api_key, settings.summary_model)
    return TemplateSummarizer()


def generate_and_store_summary(
    alert_id: int,
    ctx: AlertContext,
    summarizer: Summarizer,
    session_factory: Callable[[], Session],
) -> None:
    """Background task: summarize and persist. Never raises — on failure the
    alert's summary simply stays NULL so ingestion is never affected."""
    try:
        summary = summarizer.summarize(ctx)
    except Exception:
        return

    db = session_factory()
    try:
        alert = db.get(Alert, alert_id)
        if alert is not None:
            alert.summary = summary
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
