from pydantic import BaseModel, field_validator


class SummarizerKeyOut(BaseModel):
    """What the browser is allowed to see about the tenant's Gemini key — never
    the key itself. Returning only "is one set" plus a short masked hint means
    the secret can't leak through the network tab even to the account's own
    users (and certainly not across tenants)."""

    gemini_key_set: bool
    # Last 4 chars of the stored key, so a user can recognise which key is set
    # without the value ever leaving the server.
    gemini_key_hint: str | None = None


class SummarizerKeyIn(BaseModel):
    # Null/empty clears the key — summaries then fall back to the $0 template.
    gemini_api_key: str | None = None

    @field_validator("gemini_api_key")
    @classmethod
    def _clean(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        # A light sanity check: real Gemini keys are ~39 chars and start "AIza".
        # We keep it loose (not an exact format match) so we don't break if
        # Google tweaks the format — the real validation is whether it works.
        if len(v) < 20 or len(v) > 100:
            raise ValueError("That doesn't look like a Gemini API key.")
        return v


def masked_key(key: str | None) -> SummarizerKeyOut:
    """Build the browser-safe view of a stored key."""
    return SummarizerKeyOut(
        gemini_key_set=bool(key),
        gemini_key_hint=key[-4:] if key else None,
    )
