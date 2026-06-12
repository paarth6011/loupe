from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import get_settings

_settings = get_settings()


def _bcrypt_bytes(plain: str) -> bytes:
    # bcrypt only considers the first 72 bytes of a password; encode and truncate
    # to that limit so longer secrets hash without raising.
    return plain.encode("utf-8")[:72]


# A stream ticket is a narrow, short-lived credential for the SSE endpoint.
# Because EventSource can't set headers, it must travel in the URL query string,
# so it is deliberately limited: it expires in seconds and carries this scope,
# which the admin endpoints reject (see decode_token) — limiting the blast
# radius if it ever leaks into a proxy/access log or browser history.
STREAM_SCOPE = "stream"
_STREAM_TICKET_TTL_SECONDS = 60

# The single-role MVP admin password is supplied as plaintext via env; hash it
# once at import so credential checks go through bcrypt verification.
_ADMIN_PASSWORD_HASH = bcrypt.hashpw(
    _bcrypt_bytes(_settings.admin_password), bcrypt.gensalt()
).decode("ascii")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_bcrypt_bytes(plain), hashed.encode("ascii"))


def authenticate(username: str, password: str) -> bool:
    """Validate credentials against the configured single admin user."""
    if username != _settings.admin_username:
        return False
    return verify_password(password, _ADMIN_PASSWORD_HASH)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=_settings.access_token_expire_minutes
    )
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def create_stream_ticket(subject: str, account_id: int) -> str:
    """Mint a short-lived, read-only ticket for the SSE stream (see STREAM_SCOPE).

    The ticket carries the viewer's ``account_id`` so the stream can be scoped to
    one tenant — EventSource has no other way to convey it.
    """
    expire = datetime.now(timezone.utc) + timedelta(seconds=_STREAM_TICKET_TTL_SECONDS)
    payload = {
        "sub": subject,
        "exp": expire,
        "scope": STREAM_SCOPE,
        "account_id": account_id,
    }
    return jwt.encode(payload, _settings.jwt_secret, algorithm=_settings.jwt_algorithm)


def _decode(token: str) -> dict | None:
    try:
        return jwt.decode(
            token, _settings.jwt_secret, algorithms=[_settings.jwt_algorithm]
        )
    except JWTError:
        return None


def decode_token(token: str) -> str | None:
    """Return the subject of a *general-purpose* access token, else None.

    Scoped tokens (e.g. stream tickets) are rejected here so a narrow, URL-borne
    credential can never be replayed against the admin/ingest endpoints.
    """
    payload = _decode(token)
    if payload is None or payload.get("scope") is not None:
        return None
    return payload.get("sub")


def decode_stream_ticket(token: str) -> str | None:
    """Return the subject of a valid stream ticket, else None."""
    payload = _decode(token)
    if payload is None or payload.get("scope") != STREAM_SCOPE:
        return None
    return payload.get("sub")


def decode_stream_ticket_account(token: str) -> int | None:
    """Return the tenant ``account_id`` carried by a valid stream ticket, else
    None (invalid/expired ticket, wrong scope, or a pre-tenancy ticket)."""
    payload = _decode(token)
    if payload is None or payload.get("scope") != STREAM_SCOPE:
        return None
    return payload.get("account_id")


def decode_supabase_token(token: str) -> dict | None:
    """Verify a Supabase-issued access token and return its claims, else None.

    The frontend authenticates end users with Supabase Auth and forwards
    Supabase's JWT. Supabase signs these HS256 with the project's JWT secret, so
    we verify with that secret and require the ``authenticated`` audience. The
    returned ``sub`` (a UUID) is the stable id we map to a Loupe account; we also
    surface ``email`` for display. Returns None when no Supabase secret is
    configured, so the self-host admin path is unaffected.
    """
    secret = _settings.supabase_jwt_secret
    if not secret:
        return None
    try:
        return jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience=_settings.supabase_jwt_aud,
        )
    except JWTError:
        return None
