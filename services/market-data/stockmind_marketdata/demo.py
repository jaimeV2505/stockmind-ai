"""Deterministic simulated provider. Output is ALWAYS labelled SIMULATED; it is never a fallback."""
from __future__ import annotations

import math
import random
from datetime import date, datetime, timedelta, timezone
from typing import Sequence

from .calendar import is_trading_day, session_open_utc, to_market_time
from .models import AdjustmentStatus, Candle, DataMode, Timeframe


class DemoProvider:
    provider_id = "demo-simulated"
    is_simulated = True

    def __init__(self, seed: int = 42, start_price: float = 100.0, now: datetime | None = None):
        self._seed = seed
        self._start_price = start_price
        self._now = now or datetime.now(timezone.utc)

    def get_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Sequence[Candle]:
        if timeframe is not Timeframe.D1:
            raise NotImplementedError("DemoProvider supports 1d only")
        rng = random.Random(f"{self._seed}:{symbol}")
        price = self._start_price
        out: list[Candle] = []
        d = to_market_time(start).date()
        last = to_market_time(end).date()
        while d <= last:
            if is_trading_day(d):
                ret = rng.gauss(0.0004, 0.015)
                o = price
                c = max(0.01, o * math.exp(ret))
                hi = max(o, c) * (1 + abs(rng.gauss(0, 0.005)))
                lo = min(o, c) * (1 - abs(rng.gauss(0, 0.005)))
                vol = max(1.0, rng.gauss(1_000_000, 200_000))
                out.append(Candle(
                    symbol=symbol, exchange="SIM", timeframe=timeframe,
                    market_ts=session_open_utc(d), ingested_at=self._now,
                    source=self.provider_id, currency="USD",
                    adjustment=AdjustmentStatus.RAW, data_mode=DataMode.SIMULATED,
                    open=o, high=hi, low=lo, close=c, volume=vol,
                ))
                price = c
            d += timedelta(days=1)
        return out
