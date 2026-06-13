import time
from datetime import datetime, timedelta, timezone

import bcrypt
import httpx
from jose import JWTError, jwt

from app.config import get_settings

_settings = get_settings()

# Supabase signs end-user tokens with an asymmetric key by default (ES256, key
# type ECC P-256; RS256 is also possible). We verify against the project's
# published JWKS rather than a shared secret. The keys are public and rotate
# rarely, so cache them and only refetch on expiry or an unknown `kid` (which is
# what a rotation looks like from here).
_SUPABASE_JWKS_ALGS = ["ES256", "RS256"]
_JWKS_TTL_SECONDS = 600
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0


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


def _jwks_url() -> str | None:
    base = _settings.supabase_url
    if not base:
        return None
    return base.rstrip("/") + "/auth/v1/.well-known/jwks.json"


def _fetch_jwks(force: bool = False) -> dict | None:
    """Return the project's JWKS, cached. On a fetch failure serve the stale copy
    (verification still works while Supabase has a transient blip)."""
    global _jwks_cache, _jwks_fetched_at
    url = _jwks_url()
    if url is None:
        return None
    now = time.monotonic()
    fresh = _jwks_cache is not None and now - _jwks_fetched_at < _JWKS_TTL_SECONDS
    if fresh and not force:
        return _jwks_cache
    try:
        resp = httpx.get(url, timeout=5.0)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
    except (httpx.HTTPError, ValueError):
        return _jwks_cache  # may be None on the very first fetch
    return _jwks_cache


def _find_jwk(jwks: dict, kid: str | None) -> dict | None:
    keys = jwks.get("keys", [])
    for key in keys:
        if key.get("kid") == kid:
            return key
    # No kid match (or token carried none): only safe to assume the lone key.
    return keys[0] if (kid is None and len(keys) == 1) else None


def _decode_supabase_jwks(token: str) -> dict | None:
    try:
        kid = jwt.get_unverified_header(token).get("kid")
    except JWTError:
        return None
    jwks = _fetch_jwks()
    key = _find_jwk(jwks, kid) if jwks else None
    if key is None:
        # Unknown kid usually means the signing key rotated — refetch once.
        jwks = _fetch_jwks(force=True)
        key = _find_jwk(jwks, kid) if jwks else None
    if key is None:
        return None
    try:
        return jwt.decode(
            token,
            key,
            algorithms=_SUPABASE_JWKS_ALGS,
            audience=_settings.supabase_jwt_aud,
        )
    except JWTError:
        return None


def decode_supabase_token(token: str) -> dict | None:
    """Verify a Supabase-issued access token and return its claims, else None.

    The frontend authenticates end users with Supabase Auth and forwards
    Supabase's JWT; we verify it and require the ``authenticated`` audience. The
    returned ``sub`` (a UUID) is the stable id we map to a Loupe account; we also
    surface ``email`` for display.

    Two verification modes (see ``Settings``): if ``supabase_url`` is set we
    verify asymmetric tokens (ES256/RS256) against the project's JWKS — the
    modern Supabase default; otherwise we fall back to the legacy shared HS256
    secret. With neither configured this returns None, so the self-host admin
    path is unaffected.
    """
    if _settings.supabase_url:
        return _decode_supabase_jwks(token)

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
