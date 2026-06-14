"""Per-tenant notification channel: the /notifications endpoints, URL
validation (SSRF allowlist), the test-send, and the per-account resolver."""

import httpx
import pytest

from app.config import Settings
from app.models import Account
from app.notifications import NullNotifier, WebhookNotifier, notifier_for_account

SLACK = "https://hooks.slack.com/services/T000/B000/XXXXXXXXXXXX"
DISCORD = "https://discord.com/api/webhooks/123456789/abcdefg"


# --- endpoint round-trip ----------------------------------------------------


def test_get_defaults_to_null(client, auth_headers):
    resp = client.get("/notifications", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"webhook_url": None}


def test_put_then_get_round_trip(client, auth_headers):
    put = client.put(
        "/notifications", json={"webhook_url": SLACK}, headers=auth_headers
    )
    assert put.status_code == 200
    assert put.json()["webhook_url"] == SLACK
    got = client.get("/notifications", headers=auth_headers)
    assert got.json()["webhook_url"] == SLACK


def test_put_accepts_discord(client, auth_headers):
    resp = client.put(
        "/notifications", json={"webhook_url": DISCORD}, headers=auth_headers
    )
    assert resp.status_code == 200


def test_put_null_clears_the_channel(client, auth_headers):
    client.put("/notifications", json={"webhook_url": SLACK}, headers=auth_headers)
    resp = client.put(
        "/notifications", json={"webhook_url": None}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json()["webhook_url"] is None


@pytest.mark.parametrize(
    "bad",
    [
        "http://hooks.slack.com/services/x",  # not https
        "https://evil.example.com/webhook",  # host not allowlisted
        "https://localhost/hook",  # SSRF: loopback
        "https://169.254.169.254/latest/meta-data",  # SSRF: cloud metadata
        "not-a-url",
    ],
)
def test_put_rejects_invalid_or_unsafe_urls(client, auth_headers, bad):
    resp = client.put("/notifications", json={"webhook_url": bad}, headers=auth_headers)
    assert resp.status_code == 422


# --- the test-send ----------------------------------------------------------


def test_test_endpoint_without_url(client, auth_headers):
    resp = client.post("/notifications/test", headers=auth_headers)
    assert resp.json() == {"ok": False, "detail": "No webhook URL configured."}


def test_test_endpoint_sends_to_saved_url(client, auth_headers, monkeypatch):
    client.put("/notifications", json={"webhook_url": SLACK}, headers=auth_headers)
    calls: list[str] = []

    class _Resp:
        def raise_for_status(self) -> None:
            return None

    def fake_post(url, json, timeout):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr("app.notifications.httpx.post", fake_post)
    resp = client.post("/notifications/test", headers=auth_headers)
    assert resp.json()["ok"] is True
    assert calls == [SLACK]


def test_test_endpoint_reports_delivery_failure(client, auth_headers, monkeypatch):
    client.put("/notifications", json={"webhook_url": SLACK}, headers=auth_headers)

    def fake_post(url, json, timeout):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr("app.notifications.httpx.post", fake_post)
    resp = client.post("/notifications/test", headers=auth_headers)
    body = resp.json()
    assert body["ok"] is False
    assert "failed" in body["detail"].lower()


# --- per-account resolver + precedence --------------------------------------


def test_resolver_prefers_the_accounts_own_url(db_session, account_id):
    acct = db_session.get(Account, account_id)
    acct.notify_webhook_url = SLACK
    db_session.commit()
    # Even with a global env URL set, the account's own URL wins.
    n = notifier_for_account(
        db_session, account_id, Settings(notify_webhook_url=DISCORD)
    )
    assert isinstance(n, WebhookNotifier)
    assert n._url == SLACK


def test_resolver_falls_back_to_global_env(db_session, account_id):
    n = notifier_for_account(
        db_session, account_id, Settings(notify_webhook_url=DISCORD)
    )
    assert isinstance(n, WebhookNotifier)
    assert n._url == DISCORD


def test_resolver_is_null_when_neither_is_set(db_session, account_id):
    n = notifier_for_account(db_session, account_id, Settings(notify_webhook_url=""))
    assert isinstance(n, NullNotifier)
