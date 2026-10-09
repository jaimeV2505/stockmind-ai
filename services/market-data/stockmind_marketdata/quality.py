"""Data-quality validation: duplicates, ordering, provenance, completeness, gaps and misaligned bars.

Scope: ONE symbol/exchange and ONE timeframe per call (raises otherwise: pooling series masks gaps).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Sequence

from .calendar import (
    bar_close_utc, expected_intraday_opens_utc, is_trading_day, session_open_utc, to_market_time, trading_days,
)
from .models import Candle, Timeframe

_INTRADAY = (Timeframe.M1, Timeframe.M5, Timeframe.M15)


@dataclass
class QualityReport:
    duplicates: list[tuple] = field(default_factory=list)
    out_of_order: list[int] = field(default_factory=list)
    missing_dates: list[date] = field(default_factory=list)         # 1d: trading days with no candle
    unexpected_dates: list[date] = field(default_factory=list)      # 1d: candles on non-trading days
    misaligned_ts: list[datetime] = field(default_factory=list)     # 1d: stamp != session open (risk of off-by-one-day)
    missing_intraday: list[datetime] = field(default_factory=list)  # intraday: expected bar opens absent
    unexpected_ts: list[datetime] = field(default_factory=list)     # intraday: bars outside the session grid
    incomplete: list[int] = field(default_factory=list)             # indexes of bars still forming when ingested
    mixed_modes: bool = False        # live/delayed/historical/simulated combined in one series
    mixed_provenance: bool = False   # more than one source or adjustment status in one series
    gap_check_performed: bool = False  # False => timeframe has no gap/completeness checks yet (1h, 1w): NOT a clean bill

    @property
    def ok(self) -> bool:
        return not (self.duplicates or self.out_of_order or self.missing_dates or self.unexpected_dates
                    or self.misaligned_ts or self.missing_intraday or self.unexpected_ts or self.incomplete
                    or self.mixed_modes or self.mixed_provenance)


def validate_series(candles: Sequence[Candle], holidays: Iterable[date] = ()) -> QualityReport:
    """Validate a single-symbol, single-exchange, single-timeframe series against the NYSE regular-session calendar.

    `holidays` = extra dates exempt from missing-candle detection (e.g. a provider-specific closure).
    Bars still forming at ingestion are reported in `incomplete`: callers must drop them before computing indicators.
    Gap/completeness checks run for 1d, 1m, 5m, 15m; for 1h and 1w they do NOT (see `gap_check_performed`).
    """
    rep = QualityReport()
    if not candles:
        return rep
    if len({(c.symbol, c.exchange) for c in candles}) != 1:
        raise ValueError("validate_series expects exactly one symbol/exchange")
    tfs = {c.timeframe for c in candles}
    if len(tfs) != 1:
        raise ValueError("validate_series expects a single timeframe")
    tf = next(iter(tfs))

    seen: set[tuple] = set()
    for i, c in enumerate(candles):
        if c.key in seen:
            rep.duplicates.append(c.key)
        seen.add(c.key)
        if i and c.market_ts < candles[i - 1].market_ts:
            rep.out_of_order.append(i)
    rep.mixed_modes = len({c.data_mode for c in candles}) > 1
    rep.mixed_provenance = len({(c.source, c.adjustment) for c in candles}) > 1

    exempt = set(holidays)
    if tf is Timeframe.D1:
        rep.gap_check_performed = True
        have = {to_market_time(c.market_ts).date() for c in candles}
        rep.unexpected_dates = sorted(d for d in have if not is_trading_day(d))
        for d in trading_days(min(have), max(have)):
            if d not in have and d not in exempt:
                rep.missing_dates.append(d)
        for i, c in enumerate(candles):
            d = to_market_time(c.market_ts).date()
            if not is_trading_day(d):
                continue
            if c.market_ts != session_open_utc(d):
                rep.misaligned_ts.append(c.market_ts)
            if c.ingested_at < bar_close_utc(tf, c.market_ts):
                rep.incomplete.append(i)
    elif tf in _INTRADAY:
        rep.gap_check_performed = True
        have_ts = {c.market_ts for c in candles}
        days = {to_market_time(ts).date() for ts in have_ts}
        expected: set[datetime] = set()
        for d in trading_days(min(days), max(days)):
            if d not in exempt:
                expected.update(expected_intraday_opens_utc(d, tf))
        rep.missing_intraday = sorted(expected - have_ts)
        rep.unexpected_ts = sorted(have_ts - expected)
        rep.incomplete = [i for i, c in enumerate(candles) if c.ingested_at < bar_close_utc(tf, c.market_ts)]
    return rep
