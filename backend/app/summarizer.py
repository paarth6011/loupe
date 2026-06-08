import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Alert

# Shared instruction for every model-backed summarizer (Claude, Ollama, …).
_SYSTEM_PROMPT = (
    "You are an SRE assistant. Given an alert and recent metric context, "
    "write a concise 1-2 sentence plain-English incident summary for an "
    "on-call engineer: what happened and a likely area to look at. "
    "Respond with the summary only, no preamble."
)


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
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _render_context(ctx)}],
        )
        return "".join(
            block.text for block in response.content if block.type == "text"
        ).strip()


class OllamaSummarizer:
    """Generates summaries via a local Ollama server — $0 and fully offline.

    Same resilience contract as ClaudeSummarizer: a bounded timeout, and any
    failure propagates so the background task leaves Alert.summary NULL. Local
    models can be slow, but summarization runs off the ingest path, so a slow
    response never blocks a metric write.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def summarize(self, ctx: AlertContext) -> str:
        import httpx  # lazy import; only the Ollama path needs it

        response = httpx.post(
            f"{self._base_url}/api/chat",
            json={
                "model": self._model,
                "stream": False,
                "messages": [
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _render_context(ctx)},
                ],
                # Cap output so a chatty local model stays terse.
                "options": {"num_predict": 150},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()


def get_summarizer() -> Summarizer:
    """Pick a summarizer from SUMMARY_PROVIDER, defaulting to the safe path.

    "auto" keeps the original behavior (Claude if a key exists, else template);
    "template"/"ollama"/"claude" force a specific backend. "claude" without a key
    degrades to the template rather than failing — summaries are best-effort.
    """
    settings = get_settings()
    provider = settings.summary_provider.strip().lower()

    if provider == "template":
        return TemplateSummarizer()
    if provider == "ollama":
        return OllamaSummarizer(settings.ollama_url, settings.ollama_model)
    if provider == "claude":
        if not settings.anthropic_api_key:
            logging.getLogger("uvicorn.error").warning(
                "SUMMARY_PROVIDER=claude but no ANTHROPIC_API_KEY; "
                "using the template summarizer."
            )
            return TemplateSummarizer()
        return ClaudeSummarizer(settings.anthropic_api_key, settings.summary_model)

    # "auto" (default): Claude when a key is present, else the no-key template.
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
