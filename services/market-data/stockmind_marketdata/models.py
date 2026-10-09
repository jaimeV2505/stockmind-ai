"""Candle model. Every candle carries the provenance fields required by the product spec."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


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
        for name in ("market_ts", "ingested_at"):
            v = getattr(self, name)
            if v.tzinfo is None or v.utcoffset() is None:
                raise ValueError(f"{name} must be timezone-aware")
            if v.utcoffset() != timedelta(0):
                raise ValueError(f"{name} must be normalised to UTC")
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
        """Idempotency key: one candle per (symbol, timeframe, open time, source, adjustment)."""
        return (self.symbol, self.timeframe, self.market_ts, self.source, self.adjustment)

    def freshness(self) -> timedelta:
        """Lag between the candle's nominal close and when we ingested it (negative = still forming)."""
        return self.ingested_at - (self.market_ts + self.timeframe.nominal_delta)


def utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc)
