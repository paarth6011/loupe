"""Ingestion API key generation and verification.

Keys are high-entropy random tokens, so a plain SHA-256 hash (not bcrypt) is the
right store: fast to check on every ingest, and there's nothing to brute-force.
"""

import hashlib
import secrets
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApiKey

KEY_PREFIX = "loupe_sk_"
_PREFIX_DISPLAY_LEN = len(KEY_PREFIX) + 6  # loupe_sk_ + 6 chars shown in the UI


def _hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_key() -> tuple[str, str, str]:
    """Return (plaintext, display_prefix, hash) for a fresh key."""
    raw = KEY_PREFIX + secrets.token_urlsafe(24)
    return raw, raw[:_PREFIX_DISPLAY_LEN], _hash(raw)


def verify_ingest_key(db: Session, raw: str) -> ApiKey | None:
    """Return the matching non-revoked key (stamping last_used_at), else None."""
    if not raw:
        return None
    key = db.scalars(
        select(ApiKey).where(ApiKey.key_hash == _hash(raw), ApiKey.revoked_at.is_(None))
    ).first()
    if key is not None:
        key.last_used_at = datetime.now(timezone.utc)
        db.commit()
    return key
