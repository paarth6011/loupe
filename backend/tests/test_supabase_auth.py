"""Supabase end-user auth: token verification + just-in-time provisioning.

These run on SQLite and need no real Supabase project. We sign tokens the way
Supabase would — both the legacy shared HS256 secret and the modern asymmetric
ES256/JWKS default — and assert the backend verifies them (and rejects bad ones)
and stands up the tenant on first sight.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from jose import jwk, jwt
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


def test_provisioning_relinks_recreated_supabase_account(db_session: Session) -> None:
    # The user deletes and recreates their Supabase account: same (verified)
    # email, brand-new `sub`. Provisioning must re-link the existing Loupe
    # account to the new id, NOT insert a duplicate-email row (which violates the
    # unique constraint and 500s every authenticated request).
    email = "recreated@example.com"
    old_sub = str(uuid.uuid4())
    first = deps._provision_supabase_user(
        db_session, auth.decode_supabase_token(_make_token(sub=old_sub, email=email))
    )
    assert first is not None

    new_sub = str(uuid.uuid4())
    relinked = deps._provision_supabase_user(
        db_session, auth.decode_supabase_token(_make_token(sub=new_sub, email=email))
    )
    assert relinked is not None
    # Same user row and tenant — their data is preserved, just re-pointed.
    assert relinked.id == first.id
    assert relinked.account_id == first.account_id
    assert relinked.supabase_user_id == new_sub

    # Exactly one user for that email; no orphan account from a failed insert.
    assert (
        db_session.scalar(
            select(func.count()).select_from(User).where(User.email == email)
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


# --- Asymmetric ES256 / JWKS path (the modern Supabase default) -------------


def _es256_keypair(kid: str) -> tuple[str, dict]:
    """Return (private PEM, public JWK with kid) for an ES256 (P-256) key."""
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub_pem = priv.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    jwk_dict = jwk.construct(pub_pem, "ES256").to_dict()
    jwk_dict["kid"] = kid
    # Some jose versions return bytes for the JWK fields; normalize to str so it
    # round-trips like a real JWKS document would.
    return priv_pem, {
        k: (v.decode() if isinstance(v, bytes) else v) for k, v in jwk_dict.items()
    }


def _make_es256_token(priv_pem: str, *, kid: str, sub: str, email: str) -> str:
    claims = {
        "sub": sub,
        "aud": _AUD,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(claims, priv_pem, algorithm="ES256", headers={"kid": kid})


@pytest.fixture
def _jwks_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # supabase_url set → decode_supabase_token takes the JWKS path regardless of
    # the shared secret.
    monkeypatch.setattr(auth._settings, "supabase_url", "https://proj.supabase.co")


def test_jwks_token_verified(monkeypatch: pytest.MonkeyPatch, _jwks_mode: None) -> None:
    kid = "key-1"
    priv_pem, pub_jwk = _es256_keypair(kid)
    monkeypatch.setattr(auth, "_fetch_jwks", lambda force=False: {"keys": [pub_jwk]})

    sub = str(uuid.uuid4())
    token = _make_es256_token(priv_pem, kid=kid, sub=sub, email="ec@example.com")
    claims = auth.decode_supabase_token(token)
    assert claims is not None
    assert claims["sub"] == sub
    assert claims["email"] == "ec@example.com"


def test_jwks_signature_must_match_published_key(
    monkeypatch: pytest.MonkeyPatch, _jwks_mode: None
) -> None:
    kid = "key-1"
    signing_pem, _ = _es256_keypair(kid)
    _, other_pub_jwk = _es256_keypair(kid)  # JWKS serves a DIFFERENT key, same kid
    monkeypatch.setattr(
        auth, "_fetch_jwks", lambda force=False: {"keys": [other_pub_jwk]}
    )

    token = _make_es256_token(
        signing_pem, kid=kid, sub=str(uuid.uuid4()), email="x@example.com"
    )
    assert auth.decode_supabase_token(token) is None


def test_jwks_unavailable_rejects(
    monkeypatch: pytest.MonkeyPatch, _jwks_mode: None
) -> None:
    # JWKS can't be fetched (e.g. Supabase unreachable, empty cache) → reject.
    priv_pem, _ = _es256_keypair("key-1")
    monkeypatch.setattr(auth, "_fetch_jwks", lambda force=False: None)
    token = _make_es256_token(
        priv_pem, kid="key-1", sub=str(uuid.uuid4()), email="x@example.com"
    )
    assert auth.decode_supabase_token(token) is None
