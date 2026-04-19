"""Shared GUI utility helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Union


def fmt_dt(value: Union[str, datetime, None]) -> str:
    """Convert a date value to a human-readable local-time string.

    Accepts:
    - An RFC 2822 string (e.g. feedparser's ``entry.published``)
    - A ``datetime`` object (naive assumed UTC, aware converted)
    - ``None`` / empty string → returns ``""``

    Returns strings like ``"19/04/2026 4:00 PM"``.
    """
    if not value:
        return ""

    dt: datetime | None = None

    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, str):
        # Try RFC 2822 (feedparser published strings)
        try:
            from email.utils import parsedate_to_datetime

            dt = parsedate_to_datetime(value)
        except Exception:
            pass

        # Fallback: ISO 8601
        if dt is None:
            for fmt in (
                "%Y-%m-%dT%H:%M:%S%z",
                "%Y-%m-%dT%H:%M:%SZ",
            ):
                try:
                    dt = datetime.strptime(value, fmt)
                    break
                except ValueError:
                    continue

        # SQLite stores timestamps as UTC without timezone info;
        # attach UTC so conversion to local time works correctly.
        if dt is None:
            for fmt in (
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
            ):
                try:
                    dt = datetime.strptime(value, fmt).replace(
                        tzinfo=timezone.utc
                    )
                    break
                except ValueError:
                    continue

    if dt is None:
        return value if isinstance(value, str) else ""

    # Convert to local time
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    # else leave naive (assumed already local)

    # Build date/time string, stripping leading zeros portably (Windows-safe)
    day = str(dt.day)
    month = dt.strftime("%m")
    year = dt.strftime("%Y")
    hour = str(dt.hour % 12 or 12)
    minute = dt.strftime("%M")
    ampm = "AM" if dt.hour < 12 else "PM"
    return f"{day}/{month}/{year} {hour}:{minute} {ampm}"
