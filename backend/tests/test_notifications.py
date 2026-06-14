from app.config import Settings, get_settings
from app.main import app
from app.notifications import (
    AlertEvent,
    NullNotifier,
    build_discord_payload,
    build_payload,
    build_slack_payload,
    format_message,
    get_notifier,
    payload_for_url,
)


def _event(status="firing", severity="critical"):
    return AlertEvent(
        status=status,
        alert_id=1,
        workload="cloudflare",
        rule="high_latency",
        severity=severity,
        message="latency 1384ms exceeded threshold 1000ms",
    )


def test_format_message_firing_and_resolved():
    firing = format_message(_event(status="firing"))
    assert "high_latency" in firing and "cloudflare" in firing
    resolved = format_message(_event(status="resolved"))
    assert "RESOLVED" in resolved


def test_payload_targets_slack_and_discord():
    payload = build_payload(_event())
    # Slack uses `text`, Discord uses `content`; both present + structured fields.
    assert payload["text"] == payload["content"]
    assert payload["alert"]["rule"] == "high_latency"
    assert payload["event"] == "firing"


def test_get_notifier_is_null_without_url():
    # No NOTIFY_WEBHOOK_URL configured in tests -> notifications disabled.
    assert isinstance(get_notifier(), NullNotifier)


SLACK_URL = "https://hooks.slack.com/services/T/B/X"
DISCORD_URL = "https://discord.com/api/webhooks/1/abc"


def test_slack_payload_is_a_colored_block_kit_attachment():
    payload = build_slack_payload(_event(severity="critical"))
    attachment = payload["attachments"][0]
    assert attachment["color"] == "#dc2626"  # critical -> red
    assert any("high_latency" in str(b) for b in attachment["blocks"])
    # A plain-text fallback for non-block clients / notifications.
    assert "high_latency" in payload["text"]


def test_discord_payload_is_a_colored_embed():
    payload = build_discord_payload(_event(severity="warning"))
    embed = payload["embeds"][0]
    assert embed["color"] == int("f59e0b", 16)  # warning -> amber, as int
    assert "high_latency" in embed["title"]
    assert "cloudflare" in str(embed["fields"])
    # Untrusted content must never ping a channel.
    assert payload["allowed_mentions"] == {"parse": []}


def test_resolved_event_is_green_with_no_message_body():
    slack = build_slack_payload(_event(status="resolved"))
    discord = build_discord_payload(_event(status="resolved"))
    assert slack["attachments"][0]["color"] == "#16a34a"
    assert discord["embeds"][0]["color"] == int("16a34a", 16)
    assert "description" not in discord["embeds"][0]


def test_payload_dispatch_by_url_host():
    event = _event()
    assert "attachments" in payload_for_url(SLACK_URL, event)  # Slack
    assert "embeds" in payload_for_url(DISCORD_URL, event)  # Discord
    # An unknown/generic host falls back to the combined plain payload.
    assert "content" in payload_for_url("https://example.com/hook", event)


def test_slack_escapes_untrusted_fields():
    # workload is attacker-influenced (set via an ingest key); mrkdwn control
    # chars must be escaped so a crafted name can't inject Slack markup.
    event = AlertEvent(
        status="firing",
        alert_id=1,
        workload="<b>&you",
        rule="r",
        severity="info",
        message="m",
    )
    blob = str(build_slack_payload(event)["attachments"][0]["blocks"])
    assert "&lt;b&gt;&amp;you" in blob
    assert "<b>" not in blob


def _post_metric(client, headers, **overrides):
    body = {"workload": "notify-wl", "latency_ms": 100, "status": "ok"}
    body.update(overrides)
    return client.post("/metrics", json=body, headers=headers)


def test_ingest_notifies_on_alert_open(client, auth_headers, notifier):
    _post_metric(client, auth_headers, latency_ms=5000)  # opens high_latency
    firing = [e for e in notifier.events if e.status == "firing"]
    assert any(e.rule == "high_latency" for e in firing)


def test_no_notification_without_alert(client, auth_headers, notifier):
    _post_metric(client, auth_headers, latency_ms=100)  # normal, no alert
    assert notifier.events == []


def test_ingest_notifies_on_alert_resolve(client, auth_headers, notifier):
    app.dependency_overrides[get_settings] = lambda: Settings(
        error_rate_window=3, error_rate_min_samples=3, latency_threshold_ms=1000
    )
    try:
        _post_metric(client, auth_headers, latency_ms=5000)  # open
        for _ in range(3):  # recover -> resolve
            _post_metric(client, auth_headers, latency_ms=50)
        assert any(e.status == "resolved" for e in notifier.events)
    finally:
        del app.dependency_overrides[get_settings]
