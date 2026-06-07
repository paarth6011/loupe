"""Loupe SDK — instrument your LLM calls in two lines.

from loupe import track
client = track(anthropic.Anthropic(), workload="support-bot")
# use `client` exactly as before; calls are now observed
"""

from loupe.reporter import Reporter
from loupe.tracking import track

__all__ = ["track", "Reporter"]
