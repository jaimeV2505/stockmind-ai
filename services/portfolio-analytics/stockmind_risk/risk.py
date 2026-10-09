"""Deterministic risk calculations (research tooling only; no order placement).

All functions validate their inputs and raise ValueError on impossible geometry (e.g. a long stop above entry)
instead of returning a plausible-looking number.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

_EPS = 1e-9  # guards floor() against float noise such as 49.999999999


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


def _pos(name: str, v: float) -> None:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0:
        raise ValueError(f"{name} must be a finite number > 0, got {v!r}")


def atr_stop(entry: float, atr: float, multiple: float = 2.0, side: Side = Side.LONG) -> float:
    """Stop REFERENCE = entry -/+ multiple * ATR."""
    for n, v in (("entry", entry), ("atr", atr), ("multiple", multiple)):
        _pos(n, v)
    stop = entry - multiple * atr if side is Side.LONG else entry + multiple * atr
    if stop <= 0:
        raise ValueError("ATR stop would be at or below zero: ATR too large relative to price")
    return stop


def _risk_per_share(entry: float, stop: float, side: Side) -> float:
    _pos("entry", entry)
    _pos("stop", stop)
    r = entry - stop if side is Side.LONG else stop - entry
    if r <= 0:
        raise ValueError(f"stop {stop} is on the wrong side of entry {entry} for a {side.value} position")
    return r


def risk_reward(entry: float, stop: float, target: float, side: Side = Side.LONG) -> float:
    """Reward/risk ratio. Target must lie beyond entry in the trade direction."""
    risk = _risk_per_share(entry, stop, side)
    _pos("target", target)
    reward = target - entry if side is Side.LONG else entry - target
    if reward <= 0:
        raise ValueError("target must be beyond entry in the trade direction")
    return reward / risk


@dataclass(frozen=True)
class PositionSize:
    shares: int
    risk_amount: float      # loss if the stop fills exactly at the stop (no gap, no slippage)
    notional: float
    binding_constraint: str  # "risk" | "position_cap" | "liquidity"


def position_size(
    equity: float, risk_fraction: float, entry: float, stop: float, side: Side = Side.LONG,
    max_position_fraction: float = 1.0, adv_shares: float | None = None, max_adv_fraction: float = 0.01,
) -> PositionSize:
    """Whole-share size = min(risk budget, concentration cap, liquidity cap).

    risk_fraction: fraction of equity risked (0.01 = 1%). Liquidity cap = max_adv_fraction of average daily volume.
    NOTE: real losses can exceed `risk_amount` on gaps/slippage; see gap-risk warnings (not yet implemented).
    """
    _pos("equity", equity)
    for n, v in (("risk_fraction", risk_fraction), ("max_position_fraction", max_position_fraction)):
        _pos(n, v)
        if v > 1:
            raise ValueError(f"{n} must be <= 1")
    per_share = _risk_per_share(entry, stop, side)
    caps = {
        "risk": math.floor(equity * risk_fraction / per_share + _EPS),
        "position_cap": math.floor(equity * max_position_fraction / entry + _EPS),
    }
    if adv_shares is not None:
        _pos("adv_shares", adv_shares)
        _pos("max_adv_fraction", max_adv_fraction)
        caps["liquidity"] = math.floor(adv_shares * max_adv_fraction + _EPS)
    binding = min(caps, key=lambda k: (caps[k], list(caps).index(k)))
    shares = max(0, caps[binding])
    return PositionSize(shares, shares * per_share, shares * entry, binding)
