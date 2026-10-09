"""Alert rule evaluation (pure, edge-triggered on the LAST COMPLETED bar). Never fires on missing/insufficient data."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum

import pandas as pd

from stockmind_ta import relative_volume, rsi

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")


class Channel(str, Enum):
    IN_APP = "in_app"
    PUSH = "push"
    EMAIL = "email"
    TELEGRAM = "telegram"


class Kind(str, Enum):
    PRICE_CROSS = "price_cross"
    RSI_THRESHOLD = "rsi_threshold"
    VOLUME_SPIKE = "volume_spike"
    SIGNAL = "signal"


@dataclass(frozen=True)
class AlertRule:
    id: str
    user_id: str
    symbol: str
    kind: Kind
    channels: tuple[Channel, ...]
    direction: str = "above"                 # "above" | "below" (ignored for VOLUME_SPIKE / SIGNAL)
    threshold: float | None = None
    cooldown: timedelta = timedelta(0)
    enabled: bool = True
    strategy_id: str | None = None           # SIGNAL rules only

    def __post_init__(self) -> None:
        if not self.id or not self.user_id:
            raise ValueError("id and user_id are required")
        if not _SYMBOL_RE.match(self.symbol):
            raise ValueError(f"invalid symbol {self.symbol!r}")
        if not self.channels or len(set(self.channels)) != len(self.channels):
            raise ValueError("channels must be non-empty and unique")
        if self.direction not in ("above", "below"):
            raise ValueError("direction must be 'above' or 'below'")
        if self.cooldown < timedelta(0):
            raise ValueError("cooldown must be >= 0")
        if self.kind is Kind.SIGNAL:
            return
        t = self.threshold
        if t is None or isinstance(t, bool) or not math.isfinite(t) or t <= 0:
            raise ValueError("threshold must be a finite number > 0")
        if self.kind is Kind.RSI_THRESHOLD and not 0 < t < 100:
            raise ValueError("RSI threshold must be in (0, 100)")


@dataclass(frozen=True)
class Trigger:
    rule_id: str
    symbol: str
    bar_ts: pd.Timestamp                      # the completed bar (or signal bar) that caused the alert
    reason: str                               # human-readable "why" shown in the UI
    evidence: tuple[tuple[str, float | str], ...] = ()

    @property
    def event_key(self) -> str:
        return f"{self.rule_id}:{self.bar_ts.isoformat()}"


def _cross(prev: float, cur: float, thr: float, direction: str) -> bool:
    return (prev < thr <= cur) if direction == "above" else (prev > thr >= cur)


def _finite(*xs: float) -> bool:
    return all(isinstance(x, (int, float)) and math.isfinite(x) for x in xs)


def evaluate(rule: AlertRule, bars: pd.DataFrame) -> Trigger | None:
    """Evaluate the LAST completed bar. Returns None unless the condition newly occurred on it."""
    if not rule.enabled or rule.kind is Kind.SIGNAL:
        return None
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("bars index must be a tz-aware DatetimeIndex")
    ts = bars.index[-1]
    close = bars["close"]
    if rule.kind is Kind.PRICE_CROSS:
        if len(bars) < 2:
            return None
        prev, cur = float(close.iloc[-2]), float(close.iloc[-1])
        if _finite(prev, cur) and _cross(prev, cur, rule.threshold, rule.direction):
            return Trigger(rule.id, rule.symbol, ts,
                           f"{rule.symbol} close {cur:.2f} crossed {rule.direction} {rule.threshold:.2f} (previous close {prev:.2f})",
                           (("close", cur), ("previous_close", prev), ("threshold", rule.threshold)))
    elif rule.kind is Kind.RSI_THRESHOLD:
        if len(bars) < 16:
            return None
        r = rsi(close, 14)
        prev, cur = float(r.iloc[-2]), float(r.iloc[-1])
        if _finite(prev, cur) and _cross(prev, cur, rule.threshold, rule.direction):
            return Trigger(rule.id, rule.symbol, ts,
                           f"{rule.symbol} RSI(14) {cur:.1f} crossed {rule.direction} {rule.threshold:.1f} (previous {prev:.1f})",
                           (("rsi", round(cur, 2)), ("previous_rsi", round(prev, 2)), ("threshold", rule.threshold)))
    elif rule.kind is Kind.VOLUME_SPIKE:
        if len(bars) < 22:
            return None
        rv = float(relative_volume(bars["volume"], 20).iloc[-1])
        if _finite(rv) and rv >= rule.threshold:
            return Trigger(rule.id, rule.symbol, ts,
                           f"{rule.symbol} volume is {rv:.2f}x its 20-bar average (threshold {rule.threshold:.2f}x)",
                           (("relative_volume", round(rv, 2)), ("threshold", rule.threshold)))
    return None


def trigger_from_signal(rule: AlertRule, signal) -> Trigger | None:
    """SIGNAL rules fire when a matching strategy signal exists. The event key is the signal's idempotency key."""
    if not rule.enabled or rule.kind is not Kind.SIGNAL or signal.symbol != rule.symbol:
        return None
    if rule.strategy_id is not None and signal.strategy_id != rule.strategy_id:
        return None
    ev = ", ".join(f"{e.name}={e.value}" for e in signal.supporting)
    t = Trigger(rule.id, rule.symbol, pd.Timestamp(signal.trigger_ts),
                f"{signal.strategy_id} signal on {signal.symbol} ({signal.timeframe}): {ev}",
                tuple((e.name, e.value) for e in signal.supporting))
    return t
