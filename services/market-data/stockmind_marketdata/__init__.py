"""Provider-independent market data domain model (Phase 0 foundation)."""
from .models import (
    AdjustmentStatus,
    Candle,
    DataMode,
    Timeframe,
)
from .provider import MarketDataProvider
from .alpaca import (
    AlpacaDailyBars, ProviderAuthError, ProviderConfigError, ProviderDataError, ProviderError, ProviderUnavailable,
)
from .demo import DemoProvider
from .quality import QualityReport, validate_series
from .calendar import (
    expected_intraday_opens_utc, is_early_close, is_trading_day, session_close_utc,
    session_open_utc, to_market_time, trading_days,
)

__all__ = [
    "AlpacaDailyBars", "ProviderAuthError", "ProviderConfigError", "ProviderDataError", "ProviderError", "ProviderUnavailable",
    "AdjustmentStatus", "Candle", "DataMode", "Timeframe", "MarketDataProvider",
    "DemoProvider", "QualityReport", "validate_series",
    "to_market_time", "session_open_utc", "session_close_utc", "is_trading_day", "is_early_close",
    "trading_days", "expected_intraday_opens_utc",
]
