"""Candle model. Every candle carries the provenance fields required by the product spec."""
from __future__ import annotations

import math
import numbers
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")   # e.g. AAPL, BRK.B, BF-B. Adapters must normalise.
_CURRENCY_RE = re.compile(r"^[A-Z]{3}$")


class Timeframe(str, Enum):
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    H1 = "1h"
    D1 = "1d"
    W1 = "1w"

    @property
    def nominal_delta(self) -> timedelta:
        return {
            Timeframe.M1: timedelta(minutes=1),
            Timeframe.M5: timedelta(minutes=5),
            Timeframe.M15: timedelta(minutes=15),
            Timeframe.H1: timedelta(hours=1),
            Timeframe.D1: timedelta(days=1),
            Timeframe.W1: timedelta(weeks=1),
        }[self]


class AdjustmentStatus(str, Enum):
    RAW = "raw"
    SPLIT_ADJUSTED = "split_adjusted"
    FULLY_ADJUSTED = "fully_adjusted"  # splits + dividends


class DataMode(str, Enum):
    """Entitlement / delay status. SIMULATED must never be mixed silently with real data."""
    LIVE = "live"
    DELAYED = "delayed"
    HISTORICAL = "historical"
    SIMULATED = "simulated"


@dataclass(frozen=True)
class Candle:
    symbol: str
    exchange: str
    timeframe: Timeframe
    market_ts: datetime      # candle OPEN time, timezone-aware, stored in UTC
    ingested_at: datetime    # when WE received it, timezone-aware, UTC
    source: str              # provider id, e.g. "alpaca", "demo-simulated"
    currency: str
    adjustment: AdjustmentStatus
    data_mode: DataMode
    open: float
    high: float
    low: float
    close: float
    volume: float

    def __post_init__(self) -> None:
        # identifiers: reject (never silently normalise) so bad adapter output is caught at the boundary
        if not isinstance(self.symbol, str) or not _SYMBOL_RE.match(self.symbol):
            raise ValueError(f"invalid symbol {self.symbol!r} (expected upper-case, e.g. 'AAPL', 'BRK.B')")
        if not isinstance(self.exchange, str) or not self.exchange.strip() or self.exchange != self.exchange.strip():
            raise ValueError("exchange must be a non-empty, trimmed string")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if not isinstance(self.currency, str) or not _CURRENCY_RE.match(self.currency):
            raise ValueError(f"invalid currency {self.currency!r} (expected ISO-4217 upper-case, e.g. 'USD')")
        # numbers: finite reals only. NaN/inf would pass every ordering comparison below (all False) and poison indicators.
        for name in ("open", "high", "low", "close", "volume"):
            v = getattr(self, name)
            if isinstance(v, bool) or not isinstance(v, numbers.Real):
                raise ValueError(f"{name} must be a real number, got {type(v).__name__}")
            if not math.isfinite(v):
                raise ValueError(f"{name} must be finite, got {v!r}")
        for name in ("market_ts", "ingested_at"):
            v = getattr(self, name)
            if not isinstance(v, datetime) or v.tzinfo is None or v.utcoffset() is None:
                raise ValueError(f"{name} must be a timezone-aware datetime")
            if v.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be normalised to UTC")
        if self.ingested_at < self.market_ts:
            raise ValueError("a candle cannot be ingested before its open time (clock skew or fabricated data)")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be >= open, close and low")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be <= open, close and high")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("prices must be positive")
        if self.volume < 0:
            raise ValueError("volume must be >= 0")
        if self.data_mode is DataMode.SIMULATED and not self.source.endswith("-simulated"):
            raise ValueError("simulated candles must have a source ending in '-simulated'")

    @property
    def key(self) -> tuple:
        """Idempotency key: one candle per (symbol, exchange, timeframe, open time, source, adjustment)."""
        return (self.symbol, self.exchange, self.timeframe, self.market_ts, self.source, self.adjustment)

    def freshness(self) -> timedelta:
        """Lag between the bar's real close (session-aware, early closes included) and ingestion.
        Negative means the bar was still forming when ingested. Supported for 1m/5m/15m/1d only."""
        from .calendar import bar_close_utc  # local import: calendar imports this module
        return self.ingested_at - bar_close_utc(self.timeframe, self.market_ts)


def utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)
