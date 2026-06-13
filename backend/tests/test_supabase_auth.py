"""Supabase end-user auth: token verification + just-in-time provisioning.

These run on SQLite and need no real Supabase project — we sign tokens with a
test secret the way Supabase would (HS256, ``authenticated`` audience) and assert
the backend verifies them and stands up the tenant on first sight.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import auth, deps
from app.models import Account, User

_SECRET = "test-supabase-jwt-secret-value"
_AUD = "authenticated"


@pytest.fixture(autouse=True)
def _supabase_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    # auth.py captures settings at import; point its verifier at a known secret.
    monkeypatch.setattr(auth._settings, "supabase_jwt_secret", _SECRET)
    monkeypatch.setattr(auth._settings, "supabase_jwt_aud", _AUD)


def _make_token(
    *, sub: str, email: str | None = None, secret: str = _SECRET, ttl_s: int = 3600
) -> str:
    claims: dict = {
        "sub": sub,
        "aud": _AUD,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=ttl_s),
    }
    if email is not None:
        claims["email"] = email
    return jwt.encode(claims, secret, algorithm="HS256")


def test_valid_token_returns_claims() -> None:
    sub = str(uuid.uuid4())
    claims = auth.decode_supabase_token(_make_token(sub=sub, email="a@example.com"))
    assert claims is not None
    assert claims["sub"] == sub
    assert claims["email"] == "a@example.com"


def test_wrong_secret_rejected() -> None:
    token = _make_token(sub=str(uuid.uuid4()), secret="not-the-real-secret")
    assert auth.decode_supabase_token(token) is None


def test_expired_token_rejected() -> None:
    token = _make_token(sub=str(uuid.uuid4()), ttl_s=-10)
    assert auth.decode_supabase_token(token) is None


def test_no_secret_configured_disables_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Empty secret is how self-host turns the Supabase path off entirely.
    monkeypatch.setattr(auth._settings, "supabase_jwt_secret", "")
    assert auth.decode_supabase_token(_make_token(sub=str(uuid.uuid4()))) is None


def test_provisioning_creates_account_and_user(db_session: Session) -> None:
    sub = str(uuid.uuid4())
    claims = auth.decode_supabase_token(_make_token(sub=sub, email="new@example.com"))
    assert claims is not None

    user = deps._provision_supabase_user(db_session, claims)
    assert user is not None
    assert user.supabase_user_id == sub
    assert user.email == "new@example.com"
    assert user.role == "owner"

    account = db_session.get(Account, user.account_id)
    assert account is not None
    assert account.name == "new@example.com"


def test_provisioning_is_idempotent_per_sub(db_session: Session) -> None:
    sub = str(uuid.uuid4())
    claims = auth.decode_supabase_token(_make_token(sub=sub, email="dup@example.com"))
    assert claims is not None

    first = deps._provision_supabase_user(db_session, claims)
    second = deps._provision_supabase_user(db_session, claims)
    assert first is not None and second is not None
    assert first.id == second.id
    assert first.account_id == second.account_id

    # No duplicate account/user from the second authenticated request.
    assert (
        db_session.scalar(
            select(func.count()).select_from(User).where(User.supabase_user_id == sub)
        )
        == 1
    )


def test_resolve_bearer_scopes_to_provisioned_tenant(db_session: Session) -> None:
    sub = str(uuid.uuid4())
    token = _make_token(sub=sub, email="resolve@example.com")

    current = deps._resolve_bearer(db_session, token)
    assert current is not None
    assert current.email == "resolve@example.com"

    user = db_session.scalar(select(User).where(User.supabase_user_id == sub))
    assert user is not None
    assert current.account_id == user.account_id
