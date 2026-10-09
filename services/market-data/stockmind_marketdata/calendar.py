"""US Eastern time handling. Regular session only (09:30-16:00 ET).

LIMITATION: early closes (13:00 ET) and exchange holidays are NOT modelled yet.
A real NYSE calendar is a Phase 1 task (see docs/progress/next-tasks.md).
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)


def to_market_time(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not accepted")
    return dt.astimezone(ET)


def session_open_utc(d: date) -> datetime:
    return datetime.combine(d, REGULAR_OPEN, tzinfo=ET).astimezone(timezone.utc)


def session_close_utc(d: date) -> datetime:
    return datetime.combine(d, REGULAR_CLOSE, tzinfo=ET).astimezone(timezone.utc)
