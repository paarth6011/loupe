"""Per-tenant Gemini key (BYOK) for incident summaries: the /summarizer/key
endpoints, the masked read (the key never leaves the server), and the
per-account summarizer resolver + precedence."""

from app.config import Settings
from app.models import Account
from app.summarizer import GeminiSummarizer, TemplateSummarizer, summarizer_for_account

KEY = "AIzaSyA-fake-but-plausible-gemini-key-123"


# --- endpoint round-trip ----------------------------------------------------


def test_get_defaults_to_unset(client, auth_headers):
    resp = client.get("/summarizer/key", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == {"gemini_key_set": False, "gemini_key_hint": None}


def test_requires_auth(client):
    assert client.get("/summarizer/key").status_code == 401


def test_put_then_get_returns_masked_never_the_key(client, auth_headers):
    put = client.put(
        "/summarizer/key", json={"gemini_api_key": KEY}, headers=auth_headers
    )
    assert put.status_code == 200
    body = put.json()
    # Only "is set" + last-4 hint come back — never the key itself.
    assert body == {"gemini_key_set": True, "gemini_key_hint": KEY[-4:]}
    assert KEY not in put.text

    got = client.get("/summarizer/key", headers=auth_headers)
    assert got.json()["gemini_key_set"] is True
    assert KEY not in got.text


def test_put_null_clears_the_key(client, auth_headers):
    client.put("/summarizer/key", json={"gemini_api_key": KEY}, headers=auth_headers)
    resp = client.put(
        "/summarizer/key", json={"gemini_api_key": None}, headers=auth_headers
    )
    assert resp.status_code == 200
    assert resp.json() == {"gemini_key_set": False, "gemini_key_hint": None}


def test_put_rejects_implausible_key(client, auth_headers):
    resp = client.put(
        "/summarizer/key", json={"gemini_api_key": "short"}, headers=auth_headers
    )
    assert resp.status_code == 422


# --- per-account resolver + precedence --------------------------------------


def test_resolver_uses_the_accounts_own_key(db_session, account_id):
    acct = db_session.get(Account, account_id)
    acct.gemini_api_key = KEY
    db_session.commit()
    # Even with a global env key set, the account's own key wins.
    s = summarizer_for_account(
        db_session, account_id, Settings(gemini_api_key="AIza-global")
    )
    assert isinstance(s, GeminiSummarizer)
    assert s._api_key == KEY


def test_resolver_falls_back_to_global_env(db_session, account_id):
    s = summarizer_for_account(
        db_session, account_id, Settings(gemini_api_key="AIza-global")
    )
    assert isinstance(s, GeminiSummarizer)
    assert s._api_key == "AIza-global"


def test_resolver_is_template_when_no_key_anywhere(db_session, account_id):
    # Hosted default: operator leaves the env empty, tenant has no key -> template,
    # never the operator's key.
    s = summarizer_for_account(
        db_session, account_id, Settings(summary_provider="auto", gemini_api_key="")
    )
    assert isinstance(s, TemplateSummarizer)
