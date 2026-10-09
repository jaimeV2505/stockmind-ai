"""Provider-independent market data domain model (Phase 0 foundation)."""
from .models import (
    AdjustmentStatus,
    Candle,
    DataMode,
    Timeframe,
)
from .provider import MarketDataProvider
from .demo import DemoProvider
from .quality import QualityReport, validate_series
from .calendar import to_market_time, session_open_utc, session_close_utc

__all__ = [
    "AdjustmentStatus", "Candle", "DataMode", "Timeframe", "MarketDataProvider",
    "DemoProvider", "QualityReport", "validate_series",
    "to_market_time", "session_open_utc", "session_close_utc",
]
