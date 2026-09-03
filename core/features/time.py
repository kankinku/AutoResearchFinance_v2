from __future__ import annotations

from datetime import datetime, timezone


def to_utc(value: datetime) -> datetime:
    """Normalize an aware timestamp to UTC without accepting ambiguous input."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamp timezone is required")
    return value.astimezone(timezone.utc)
