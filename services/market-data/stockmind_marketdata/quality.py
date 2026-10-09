"""Data-quality validation: duplicates, ordering, missing daily candles."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Iterable, Sequence

from .calendar import to_market_time
from .models import Candle, Timeframe


@dataclass
class QualityReport:
    duplicates: list[tuple] = field(default_factory=list)
    out_of_order: list[int] = field(default_factory=list)
    missing_dates: list[date] = field(default_factory=list)
    mixed_modes: bool = False

    @property
    def ok(self) -> bool:
        return not (self.duplicates or self.out_of_order or self.missing_dates or self.mixed_modes)


def validate_series(
    candles: Sequence[Candle], holidays: Iterable[date] = ()
) -> QualityReport:
    """Validate a single-symbol, single-timeframe series.

    Missing-candle detection is implemented for 1d only (weekdays minus supplied holidays).
    Intraday gap detection is NOT implemented yet.
    """
    rep = QualityReport()
    seen: set[tuple] = set()
    for i, c in enumerate(candles):
        if c.key in seen:
            rep.duplicates.append(c.key)
        seen.add(c.key)
        if i and c.market_ts < candles[i - 1].market_ts:
            rep.out_of_order.append(i)
    # Real, delayed and simulated candles must never be silently combined.
    rep.mixed_modes = len({c.data_mode for c in candles}) > 1

    if candles and all(c.timeframe is Timeframe.D1 for c in candles):
        have = {to_market_time(c.market_ts).date() for c in candles}
        hol = set(holidays)
        d, last = min(have), max(have)
        while d <= last:
            if d.weekday() < 5 and d not in hol and d not in have:
                rep.missing_dates.append(d)
            d += timedelta(days=1)
    return rep
