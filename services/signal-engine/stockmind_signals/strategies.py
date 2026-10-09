"""Deterministic, versioned, CAUSAL strategies: bars in -> boolean entry/exit flags out (+ evidence).

A flag at bar t uses only bars <= t (tested at many truncation cut points). Flags are meant for
`stockmind_backtest.run_backtest`, which executes them at the NEXT bar's open (ADR-0008).
Warm-up bars and NaN inputs yield False (no trigger), never a fabricated signal.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import ClassVar

import pandas as pd

from stockmind_ta import adx, relative_volume, rsi, sma

from .lifecycle import Evidence, NoSignal, Signal, new_signal

_COLS = ("open", "high", "low", "close", "volume")


def _check_bars(bars: pd.DataFrame) -> None:
    missing = [c for c in _COLS if c not in bars.columns]
    if missing:
        raise ValueError(f"bars missing columns {missing}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("bars index must be a timezone-aware DatetimeIndex")


class Strategy:
    """Base class. Subclasses are frozen dataclasses whose fields ARE the parameters."""

    id: ClassVar[str]
    version: ClassVar[str]

    @property
    def min_bars(self) -> int:  # pragma: no cover - overridden
        raise NotImplementedError

    def flags(self, bars: pd.DataFrame) -> tuple[pd.Series, pd.Series]:  # pragma: no cover - overridden
        raise NotImplementedError

    def evidence(self, bars: pd.DataFrame) -> tuple[tuple[Evidence, ...], tuple[Evidence, ...]]:  # pragma: no cover
        raise NotImplementedError

    def config(self) -> dict:
        return {"id": self.id, "version": self.version, "params": asdict(self)}  # type: ignore[call-overload]

    @property
    def config_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.config(), sort_keys=True).encode()).hexdigest()[:8]

    @property
    def version_tag(self) -> str:
        """Code version + parameter fingerprint. Used in signal keys so different parameterisations never dedupe together."""
        return f"{self.version}+{self.config_hash}"


def _cross_up(a: pd.Series, b) -> pd.Series:
    b_prev = b.shift(1) if isinstance(b, pd.Series) else b
    return ((a.shift(1) <= b_prev) & (a > b)).astype(bool)


@dataclass(frozen=True)
class OversoldRecovery(Strategy):
    """Long when RSI crosses back UP through `oversold`; exit when RSI reaches `exit_level`."""
    id: ClassVar[str] = "oversold_recovery"
    version: ClassVar[str] = "1.0.0"
    rsi_n: int = 14
    oversold: float = 30.0
    exit_level: float = 55.0

    def __post_init__(self) -> None:
        if self.rsi_n < 2 or not (0 < self.oversold < self.exit_level < 100):
            raise ValueError("require rsi_n >= 2 and 0 < oversold < exit_level < 100")

    @property
    def min_bars(self) -> int:
        return self.rsi_n + 2

    def flags(self, bars):
        _check_bars(bars)
        r = rsi(bars["close"], self.rsi_n)
        entries = ((r.shift(1) < self.oversold) & (r >= self.oversold)).astype(bool)
        return entries, (r >= self.exit_level).astype(bool)

    def evidence(self, bars):
        r = rsi(bars["close"], self.rsi_n)
        sup = (Evidence("rsi", round(float(r.iloc[-1]), 2), f"crossed up through {self.oversold}"),
               Evidence("rsi_prev", round(float(r.iloc[-2]), 2), "previous bar, below threshold"))
        con = []
        if len(bars) >= 200 and bars["close"].iloc[-1] < sma(bars["close"], 200).iloc[-1]:
            con.append(Evidence("trend", "below SMA200", "recovery against the long-term trend"))
        rv = relative_volume(bars["volume"], 20).iloc[-1]
        if rv == rv and rv < 1.0:
            con.append(Evidence("relative_volume", round(float(rv), 2), "below-average volume"))
        return sup, tuple(con)


@dataclass(frozen=True)
class MovingAverageCrossover(Strategy):
    """Long when the fast SMA crosses above the slow SMA; exit on the opposite cross."""
    id: ClassVar[str] = "ma_crossover"
    version: ClassVar[str] = "1.0.0"
    fast: int = 20
    slow: int = 50

    def __post_init__(self) -> None:
        if not (1 <= self.fast < self.slow):
            raise ValueError("require 1 <= fast < slow")

    @property
    def min_bars(self) -> int:
        return self.slow + 2

    def flags(self, bars):
        _check_bars(bars)
        f, s = sma(bars["close"], self.fast), sma(bars["close"], self.slow)
        entries = _cross_up(f, s)
        exits = ((f.shift(1) >= s.shift(1)) & (f < s)).astype(bool)
        return entries, exits

    def evidence(self, bars):
        c = bars["close"]
        f, s = sma(c, self.fast).iloc[-1], sma(c, self.slow).iloc[-1]
        sup = (Evidence(f"sma{self.fast}", round(float(f), 4), "fast average crossed above slow"),
               Evidence(f"sma{self.slow}", round(float(s), 4)))
        a = adx(bars["high"], bars["low"], c, 14)["adx"].iloc[-1]
        con = (Evidence("adx", round(float(a), 2), "weak trend (ADX < 20): crossovers whipsaw"),) if a == a and a < 20 else ()
        return sup, con


@dataclass(frozen=True)
class BullishBreakout(Strategy):
    """Long when close exceeds the prior `lookback`-bar high on >= `min_rel_volume` x average volume;
    exit when close falls below the prior `exit_lookback`-bar low."""
    id: ClassVar[str] = "bullish_breakout"
    version: ClassVar[str] = "1.0.0"
    lookback: int = 20
    min_rel_volume: float = 1.5
    exit_lookback: int = 10

    def __post_init__(self) -> None:
        if self.lookback < 2 or self.exit_lookback < 2 or self.min_rel_volume <= 0:
            raise ValueError("require lookback >= 2, exit_lookback >= 2, min_rel_volume > 0")

    @property
    def min_bars(self) -> int:
        return max(self.lookback, self.exit_lookback) + 2

    def flags(self, bars):
        _check_bars(bars)
        prior_high = bars["high"].rolling(self.lookback, min_periods=self.lookback).max().shift(1)
        rv = relative_volume(bars["volume"], self.lookback)
        entries = ((bars["close"] > prior_high) & (rv >= self.min_rel_volume)).astype(bool)
        prior_low = bars["low"].rolling(self.exit_lookback, min_periods=self.exit_lookback).min().shift(1)
        return entries, (bars["close"] < prior_low).astype(bool)

    def evidence(self, bars):
        ph = bars["high"].rolling(self.lookback).max().shift(1).iloc[-1]
        rv = relative_volume(bars["volume"], self.lookback).iloc[-1]
        sup = (Evidence("breakout_level", round(float(ph), 4), f"prior {self.lookback}-bar high"),
               Evidence("close", round(float(bars["close"].iloc[-1]), 4)),
               Evidence("relative_volume", round(float(rv), 2), f">= {self.min_rel_volume}"))
        r = rsi(bars["close"], 14).iloc[-1]
        con = (Evidence("rsi", round(float(r), 2), "overbought (>80): breakout may be extended"),) if r == r and r > 80 else ()
        return sup, con


def decide(strategy: Strategy, bars: pd.DataFrame, symbol: str, timeframe: str) -> Signal | NoSignal:
    """Evaluate the LAST completed bar. Returns NoSignal (with a reason) unless the entry condition fired."""
    _check_bars(bars)
    as_of = bars.index[-1].tz_convert("UTC").to_pydatetime()
    no = lambda why: NoSignal(symbol, strategy.id, strategy.version_tag, timeframe, as_of, why)  # noqa: E731
    if len(bars) < strategy.min_bars:
        return no(f"insufficient history: need {strategy.min_bars} bars, have {len(bars)}")
    last = bars.iloc[-1][list(_COLS)]
    if last.isna().any():
        return no("last bar has missing values; refusing to evaluate")
    entries, _ = strategy.flags(bars)
    if not bool(entries.iloc[-1]):
        return no("no entry trigger on the last completed bar")
    sup, con = strategy.evidence(bars)
    return new_signal(symbol, strategy.id, strategy.version_tag, timeframe, as_of, sup, con)


class StrategyRegistry:
    """Versioned registry with enable/disable. Key = (id, version); parameters live on the instance."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Strategy] = {}
        self._disabled: set[tuple[str, str]] = set()

    def register(self, strategy: Strategy, enabled: bool = True) -> None:
        key = (strategy.id, strategy.version)
        if key in self._items:
            raise ValueError(f"{key} already registered: bump the strategy version instead of overwriting")
        self._items[key] = strategy
        if not enabled:
            self._disabled.add(key)

    @staticmethod
    def _vkey(v: str) -> tuple[int, ...]:
        return tuple(int(p) for p in v.split("."))

    def get(self, strategy_id: str, version: str | None = None) -> Strategy:
        cands = {v: s for (i, v), s in self._items.items() if i == strategy_id}
        if not cands:
            raise KeyError(strategy_id)
        v = version or max(cands, key=self._vkey)
        return cands[v]

    def set_enabled(self, strategy_id: str, version: str, enabled: bool) -> None:
        key = (strategy_id, version)
        if key not in self._items:
            raise KeyError(key)
        (self._disabled.discard if enabled else self._disabled.add)(key)

    def active(self) -> list[Strategy]:
        return [s for k, s in sorted(self._items.items()) if k not in self._disabled]

    def all(self) -> list[tuple[Strategy, bool]]:
        return [(s, k not in self._disabled) for k, s in sorted(self._items.items())]


def default_registry() -> StrategyRegistry:
    reg = StrategyRegistry()
    for s in (OversoldRecovery(), MovingAverageCrossover(), BullishBreakout()):
        reg.register(s)
    return reg
