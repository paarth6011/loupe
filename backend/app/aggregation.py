import re
from datetime import datetime, timedelta, timezone

_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}
_WINDOW_RE = re.compile(r"^(\d+)([smhd])$")


def parse_window(window: str) -> timedelta:
    """Parse a compact duration like '15m', '1h', '24h', '7d' into a timedelta."""
    match = _WINDOW_RE.match(window.strip())
    if not match:
        raise ValueError(f"invalid window {window!r}; use e.g. 15m, 1h, 24h, 7d")
    value, unit = int(match.group(1)), match.group(2)
    if value <= 0:
        raise ValueError("window must be a positive duration")
    return timedelta(seconds=value * _UNIT_SECONDS[unit])


def percentile(values: list[int | float], pct: float) -> float | None:
    """Linear-interpolation percentile (matches numpy's default). None if empty."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    rank = (len(ordered) - 1) * (pct / 100)
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    if low == high:
        return float(ordered[low])
    return ordered[low] + (ordered[high] - ordered[low]) * (rank - low)


def as_utc(dt: datetime) -> datetime:
    """Treat naive timestamps (SQLite) as UTC; pass through aware ones (Postgres)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def window_start(dialect_name: str, delta: timedelta) -> datetime:
    """Lower time bound for a window, normalized for the DB dialect so it can be
    compared in SQL.

    Postgres keeps tz-aware UTC timestamps; SQLite stores naive UTC strings
    (from CURRENT_TIMESTAMP), so we hand it a naive UTC bound to compare against.
    """
    start = datetime.now(timezone.utc) - delta
    return start.replace(tzinfo=None) if dialect_name == "sqlite" else start
