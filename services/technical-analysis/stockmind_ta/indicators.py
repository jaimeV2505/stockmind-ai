"""Deterministic indicator implementations (numpy/pandas, no TA-Lib dependency; see ADR-0003).

Conventions (all documented because they differ between vendors):
- Every function is CAUSAL: value at bar t depends only on bars <= t (tested in test_no_lookahead).
- Warm-up bars are NaN, never back-filled.
- EMA is seeded with the SMA of the first `n` valid values (classic convention).
- RSI / ATR use Wilder smoothing: first value = simple mean, then (prev*(n-1)+x)/n.
- Bollinger uses population standard deviation (ddof=0).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _check_n(n: int) -> None:
    if not isinstance(n, int) or n < 1:
        raise ValueError("period must be a positive integer")


def sma(s: pd.Series, n: int) -> pd.Series:
    _check_n(n)
    return s.rolling(n, min_periods=n).mean()


def _recursive_smooth(s: pd.Series, n: int, alpha: float) -> pd.Series:
    """Seed with the mean of the first n valid values, then out[t] = out[t-1] + alpha*(x[t]-out[t-1])."""
    x = s.to_numpy(dtype=float)
    out = np.full(len(x), np.nan)
    valid = np.flatnonzero(~np.isnan(x))
    if len(valid) < n:
        return pd.Series(out, index=s.index)
    first = valid[0]
    seed_idx = first + n - 1
    out[seed_idx] = x[first:seed_idx + 1].mean()
    for t in range(seed_idx + 1, len(x)):
        out[t] = out[t - 1] + alpha * (x[t] - out[t - 1])
    return pd.Series(out, index=s.index)


def ema(s: pd.Series, n: int) -> pd.Series:
    _check_n(n)
    return _recursive_smooth(s, n, 2.0 / (n + 1))


def _wilder(s: pd.Series, n: int) -> pd.Series:
    return _recursive_smooth(s, n, 1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    _check_n(n)
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)
    # first diff is NaN, so Wilder seed lands at index n
    avg_gain = _wilder(gain, n)
    avg_loss = _wilder(loss, n)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_loss != 0, 100.0)                       # no losses -> 100
    out = out.where(~((avg_loss == 0) & (avg_gain == 0)), 50.0)  # flat -> 50 (convention)
    return out.where(avg_gain.notna())


def macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    if fast >= slow:
        raise ValueError("fast must be < slow")
    line = ema(close, fast) - ema(close, slow)
    sig = ema(line, signal)
    return pd.DataFrame({"macd": line, "signal": sig, "hist": line - sig})


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1, skipna=True)
    return tr  # first bar: prev_close NaN -> falls back to high-low


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    _check_n(n)
    return _wilder(true_range(high, low, close), n)


def bollinger(close: pd.Series, n: int = 20, k: float = 2.0) -> pd.DataFrame:
    _check_n(n)
    mid = sma(close, n)
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    return pd.DataFrame({"mid": mid, "upper": mid + k * sd, "lower": mid - k * sd})


def roc(close: pd.Series, n: int = 12) -> pd.Series:
    _check_n(n)
    return (close / close.shift(n) - 1.0) * 100.0


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    direction = np.sign(close.diff()).fillna(0.0)
    return (direction * volume).cumsum()


def relative_volume(volume: pd.Series, n: int = 20) -> pd.Series:
    """Volume / mean volume of the PREVIOUS n bars (current bar excluded to avoid self-dilution)."""
    _check_n(n)
    return volume / sma(volume, n).shift(1)
