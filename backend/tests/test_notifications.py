from app.config import Settings, get_settings
from app.main import app
from app.notifications import (
    AlertEvent,
    NullNotifier,
    build_payload,
    format_message,
    get_notifier,
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
