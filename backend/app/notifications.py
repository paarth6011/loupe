import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import get_settings

_SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🔵"}


@dataclass
class AlertEvent:
    status: str  # "firing" | "resolved"
    alert_id: int
    workload: str
    rule: str
    severity: str
    message: str


def format_message(event: AlertEvent) -> str:
    if event.status == "resolved":
        return f"✅ [RESOLVED] {event.rule} on {event.workload}"
    emoji = _SEVERITY_EMOJI.get(event.severity, "⚠️")
    return (
        f"{emoji} [{event.severity.upper()}] {event.rule} on {event.workload} "
        f"— {event.message}"
    )


def build_payload(event: AlertEvent) -> dict:
    """A single payload that renders in Slack (`text`), Discord (`content`), and
    carries structured fields for generic webhook receivers."""
    text = format_message(event)
    return {
        "text": text,
        "content": text,
        "event": event.status,
        "alert": {
            "id": event.alert_id,
            "workload": event.workload,
            "rule": event.rule,
            "severity": event.severity,
            "message": event.message,
        },
    }


class Notifier(Protocol):
    def notify(self, event: AlertEvent) -> None: ...


class NullNotifier:
    """No-op notifier used when no webhook URL is configured."""

    def notify(self, event: AlertEvent) -> None:
        return None


class WebhookNotifier:
    """POSTs alert events to a configured webhook URL. Never raises — a failed
    notification must not affect ingestion."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self._url = url
        self._timeout = timeout

    def notify(self, event: AlertEvent) -> None:
        try:
            httpx.post(self._url, json=build_payload(event), timeout=self._timeout)
        except httpx.HTTPError as exc:
            logging.getLogger("uvicorn.error").warning(
                "alert notification failed: %s", exc
            )


def get_notifier() -> Notifier:
    url = get_settings().notify_webhook_url
    return WebhookNotifier(url) if url else NullNotifier()
