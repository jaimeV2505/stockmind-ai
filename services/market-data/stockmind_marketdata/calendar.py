"""NYSE regular-session calendar (rule-based) and US-Eastern helpers. See ADR-0005.

Scope / LIMITATIONS (also in docs/progress/current-state.md):
- Supported years: 2012-2100. Rules: standard NYSE holidays + weekend observance + early closes
  (day after Thanksgiving, Dec 24, Jul 3) + a hand-maintained list of ad hoc closures (AD_HOC_CLOSURES).
- The ad hoc list is maintained from memory of public events and MUST be reviewed against the official NYSE
  holiday page before commercial use; future unscheduled closures need manual addition.
- Regular session only (09:30-16:00 ET, early close 13:00). Pre/post-market sessions are not modelled.
- Intraday expected-bar generation supports 1m/5m/15m (9:30 divides evenly). 1h is deliberately unsupported:
  provider hourly-bar alignment conventions differ and must be confirmed per provider.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

from .models import Timeframe

ET = ZoneInfo("America/New_York")
REGULAR_OPEN = time(9, 30)
REGULAR_CLOSE = time(16, 0)
EARLY_CLOSE = time(13, 0)
MIN_YEAR, MAX_YEAR = 2012, 2100

# Unscheduled full-day closures: Hurricane Sandy (2012-10-29/30), national day of mourning for
# G.H.W. Bush (2018-12-05) and J. Carter (2025-01-09).
AD_HOC_CLOSURES = frozenset({date(2012, 10, 29), date(2012, 10, 30), date(2018, 12, 5), date(2025, 1, 9)})

_INTRADAY_MINUTES = {Timeframe.M1: 1, Timeframe.M5: 5, Timeframe.M15: 15}


def to_market_time(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not accepted")
    return dt.astimezone(ET)


def easter(year: int) -> date:
    """Gregorian Easter Sunday (anonymous / Meeus algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    d = date(year, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(year: int, month: int, weekday: int) -> date:
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def _check_year(year: int) -> None:
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError(f"NYSE calendar supports {MIN_YEAR}-{MAX_YEAR}, got {year}")


@lru_cache(maxsize=None)
def holidays(year: int) -> dict[date, str]:
    """Full-day NYSE closures falling in `year` (observed dates)."""
    _check_year(year)
    h: dict[date, str] = {}
    ny = date(year, 1, 1)
    if ny.weekday() != 5:  # Saturday Jan 1: NYSE does NOT close the preceding Friday
        h[_observed(ny)] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    h[easter(year) - timedelta(days=2)] = "Good Friday"
    h[_last_weekday(year, 5, 0)] = "Memorial Day"
    if year >= 2022:
        h[_observed(date(year, 6, 19))] = "Juneteenth"
    h[_observed(date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(date(year, 12, 25))] = "Christmas Day"
    for d in AD_HOC_CLOSURES:
        if d.year == year:
            h[d] = "Unscheduled closure"
    return {d: n for d, n in h.items() if d.year == year}


def is_trading_day(d: date) -> bool:
    _check_year(d.year)
    return d.weekday() < 5 and d not in holidays(d.year)


def is_early_close(d: date) -> bool:
    if not is_trading_day(d):
        return False
    if d == _nth_weekday(d.year, 11, 3, 4) + timedelta(days=1):  # day after Thanksgiving
        return True
    if d == date(d.year, 12, 24):
        return True
    if d == date(d.year, 7, 3) and date(d.year, 7, 4).weekday() < 5:
        return True
    return False


def _require_trading_day(d: date) -> None:
    if not is_trading_day(d):
        raise ValueError(f"{d} is not an NYSE trading day")


def session_open_utc(d: date) -> datetime:
    _require_trading_day(d)
    return datetime.combine(d, REGULAR_OPEN, tzinfo=ET).astimezone(timezone.utc)


def session_close_utc(d: date) -> datetime:
    _require_trading_day(d)
    t = EARLY_CLOSE if is_early_close(d) else REGULAR_CLOSE
    return datetime.combine(d, t, tzinfo=ET).astimezone(timezone.utc)


def trading_days(start: date, end: date) -> list[date]:
    out, d = [], start
    while d <= end:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def expected_intraday_opens_utc(d: date, timeframe: Timeframe) -> list[datetime]:
    """Bar open times (UTC) expected for a trading day. 1m/5m/15m only."""
    if timeframe not in _INTRADAY_MINUTES:
        raise NotImplementedError(f"expected bars not supported for {timeframe.value}")
    step = timedelta(minutes=_INTRADAY_MINUTES[timeframe])
    t, close = session_open_utc(d), session_close_utc(d)
    out = []
    while t < close:
        out.append(t)
        t += step
    return out
