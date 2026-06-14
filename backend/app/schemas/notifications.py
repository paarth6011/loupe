from urllib.parse import urlparse

from pydantic import BaseModel, field_validator

# The webhook URL is tenant-supplied, so on a multi-tenant host it is an SSRF
# vector: a crafted URL could target cloud metadata (169.254.169.254), localhost,
# or RFC1918 infra, with alert delivery / the test endpoint as the request. Since
# the feature is specifically Slack/Discord, we sidestep SSRF entirely by
# allowlisting their public webhook hosts (https only) rather than trying to
# block private ranges. The operator's global NOTIFY_WEBHOOK_URL env var is
# trusted and stays unrestricted (it supports generic webhooks for self-host).
_ALLOWED_HOSTS = {"hooks.slack.com", "discord.com", "discordapp.com"}


def validate_webhook_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Webhook URL must use https.")
    host = (parsed.hostname or "").lower()
    if host not in _ALLOWED_HOSTS:
        raise ValueError(
            "Webhook URL must be a Slack (hooks.slack.com) or "
            "Discord (discord.com / discordapp.com) webhook."
        )
    return url


class NotificationSettings(BaseModel):
    # Null clears the channel (notifications off for this account).
    webhook_url: str | None = None

    @field_validator("webhook_url")
    @classmethod
    def _check_url(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        return validate_webhook_url(v)
