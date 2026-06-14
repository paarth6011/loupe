import logging
from dataclasses import dataclass
from typing import Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Account

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

    def send_test(self, event: AlertEvent) -> None:
        """Like notify() but lets failures propagate, so the test endpoint can
        report whether delivery actually worked."""
        resp = httpx.post(self._url, json=build_payload(event), timeout=self._timeout)
        resp.raise_for_status()


def get_notifier() -> Notifier:
    url = get_settings().notify_webhook_url
    return WebhookNotifier(url) if url else NullNotifier()


def notifier_for_account(
    db: Session, account_id: int, settings: Settings
) -> Notifier:
    """Resolve the notifier for one tenant. Precedence: the account's own webhook
    URL, else the global NOTIFY_WEBHOOK_URL (the self-host default), else a no-op.

    On the hosted product the operator leaves NOTIFY_WEBHOOK_URL empty, so a
    tenant with no URL configured gets NullNotifier — never the operator's
    webhook. The URL is read here (on the request's pinned session) and captured
    into the notifier, so background delivery needs no DB/account context.
    """
    url = db.scalar(
        select(Account.notify_webhook_url).where(Account.id == account_id)
    )
    if url:
        return WebhookNotifier(url)
    if settings.notify_webhook_url:
        return WebhookNotifier(settings.notify_webhook_url)
    return NullNotifier()
