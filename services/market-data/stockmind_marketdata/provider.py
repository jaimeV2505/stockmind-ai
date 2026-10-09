from __future__ import annotations

from datetime import datetime
from typing import Protocol, Sequence, runtime_checkable

from .models import Candle, Timeframe


@runtime_checkable
class MarketDataProvider(Protocol):
    """Provider-independent interface. Alpaca / Polygon-compatible / FMP adapters implement this."""

    provider_id: str
    is_simulated: bool

    def get_candles(
        self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime
    ) -> Sequence[Candle]: ...
