import logging
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Account

_SEVERITY_EMOJI = {"critical": "🔴", "warning": "🟠", "info": "🔵"}

# Per-severity accent colour for the Slack attachment stripe / Discord embed bar.
# Resolved events are always green regardless of the original severity.
_SEVERITY_COLOR = {
    "critical": "#dc2626",
    "warning": "#f59e0b",
    "info": "#3b82f6",
}
_RESOLVED_COLOR = "#16a34a"
_DEFAULT_COLOR = "#6b7280"


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
    """A single generic payload that renders in Slack (`text`), Discord
    (`content`), and carries structured fields for generic webhook receivers.

    Used for the self-host `NOTIFY_WEBHOOK_URL`, whose target may be anything;
    Slack and Discord webhooks get the richer native payloads below."""
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


def _color_hex(event: AlertEvent) -> str:
    if event.status == "resolved":
        return _RESOLVED_COLOR
    return _SEVERITY_COLOR.get(event.severity, _DEFAULT_COLOR)


def _title(event: AlertEvent) -> str:
    if event.status == "resolved":
        return f"✅ Resolved: {event.rule}"
    emoji = _SEVERITY_EMOJI.get(event.severity, "⚠️")
    return f"{emoji} {event.severity.upper()}: {event.rule}"


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _slack_escape(value: str) -> str:
    # workload/message are attacker-influenced (set via an ingest key), so escape
    # the three characters Slack treats as mrkdwn control chars before embedding.
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_slack_payload(event: AlertEvent) -> dict:
    """Slack Block Kit: a coloured attachment stripe (by severity) with the rule
    as a header and workload/severity fields."""
    workload = _slack_escape(_truncate(event.workload, 1000))
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{_slack_escape(_title(event))}*"},
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Workload*\n{workload}"},
                {
                    "type": "mrkdwn",
                    "text": f"*Severity*\n{_slack_escape(event.severity)}",
                },
            ],
        },
    ]
    if event.status != "resolved":
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": _slack_escape(_truncate(event.message, 2900)),
                },
            }
        )
    return {
        # Plain-text fallback for notifications, screen readers, and clients that
        # don't render blocks.
        "text": format_message(event),
        "attachments": [{"color": _color_hex(event), "blocks": blocks}],
    }


def build_discord_payload(event: AlertEvent) -> dict:
    """Discord embed: a coloured bar (by severity) with the rule as title and
    workload/severity fields."""
    embed: dict = {
        "title": _truncate(_title(event), 256),
        "color": int(_color_hex(event).lstrip("#"), 16),
        "fields": [
            {
                "name": "Workload",
                "value": _truncate(event.workload or "—", 1024),
                "inline": True,
            },
            {
                "name": "Severity",
                "value": _truncate(event.severity or "—", 1024),
                "inline": True,
            },
        ],
    }
    if event.status != "resolved":
        embed["description"] = _truncate(event.message, 4096)
    return {
        "embeds": [embed],
        # Untrusted content must never ping a channel (@everyone/@here).
        "allowed_mentions": {"parse": []},
    }


def payload_for_url(url: str, event: AlertEvent) -> dict:
    """Pick the native payload for the webhook's platform, by URL host. Slack and
    Discord want different shapes (`attachments`/`blocks` vs `embeds`); anything
    else (the generic self-host target) gets the combined plain payload."""
    host = (urlparse(url).hostname or "").lower()
    if host.endswith("slack.com"):
        return build_slack_payload(event)
    if (
        host == "discord.com"
        or host == "discordapp.com"
        or host.endswith(".discord.com")
    ):
        return build_discord_payload(event)
    return build_payload(event)


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
            payload = payload_for_url(self._url, event)
            httpx.post(self._url, json=payload, timeout=self._timeout)
        except httpx.HTTPError as exc:
            logging.getLogger("uvicorn.error").warning(
                "alert notification failed: %s", exc
            )

    def send_test(self, event: AlertEvent) -> None:
        """Like notify() but lets failures propagate, so the test endpoint can
        report whether delivery actually worked."""
        payload = payload_for_url(self._url, event)
        resp = httpx.post(self._url, json=payload, timeout=self._timeout)
        resp.raise_for_status()


def get_notifier() -> Notifier:
    url = get_settings().notify_webhook_url
    return WebhookNotifier(url) if url else NullNotifier()


def notifier_for_account(db: Session, account_id: int, settings: Settings) -> Notifier:
    """Resolve the notifier for one tenant. Precedence: the account's own webhook
    URL, else the global NOTIFY_WEBHOOK_URL (the self-host default), else a no-op.

    On the hosted product the operator leaves NOTIFY_WEBHOOK_URL empty, so a
    tenant with no URL configured gets NullNotifier — never the operator's
    webhook. The URL is read here (on the request's pinned session) and captured
    into the notifier, so background delivery needs no DB/account context.
    """
    url = db.scalar(select(Account.notify_webhook_url).where(Account.id == account_id))
    if url:
        return WebhookNotifier(url)
    if settings.notify_webhook_url:
        return WebhookNotifier(settings.notify_webhook_url)
    return NullNotifier()
