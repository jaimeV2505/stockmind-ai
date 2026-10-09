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


# --------------------------------------------------------------------------------------
# Batch 2 (session 2)
# --------------------------------------------------------------------------------------

def adx(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.DataFrame:
    """Wilder's ADX / +DI / -DI.

    Convention: TR and DM are both undefined on bar 0 (DM needs a prior bar), so Wilder smoothing is seeded at
    bar n (mean of bars 1..n). ADX = Wilder-smoothed DX, first value at bar 2n-1. Ratios are scale-free so the
    mean-seed form is equivalent to Wilder's original sum-seed form.
    """
    _check_n(n)
    up, down = high.diff(), -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index).where(up.notna())
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index).where(down.notna())
    tr = true_range(high, low, close).where(up.notna())
    s_tr, s_p, s_m = _wilder(tr, n), _wilder(plus_dm, n), _wilder(minus_dm, n)
    plus_di = 100.0 * s_p / s_tr
    minus_di = 100.0 * s_m / s_tr
    denom = plus_di + minus_di
    dx = (100.0 * (plus_di - minus_di).abs() / denom).where(denom != 0, 0.0).where(plus_di.notna())
    return pd.DataFrame({"plus_di": plus_di, "minus_di": minus_di, "adx": _wilder(dx, n)})


def cci(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20) -> pd.Series:
    """Lambert's CCI: (TP - SMA(TP)) / (0.015 * mean absolute deviation). Flat window (MAD=0) -> 0."""
    _check_n(n)
    tp = (high + low + close) / 3.0
    mean = sma(tp, n)
    x = tp.to_numpy(dtype=float)
    mad = np.full(len(x), np.nan)
    if len(x) >= n:
        win = np.lib.stride_tricks.sliding_window_view(x, n)
        mad[n - 1:] = np.abs(win - win.mean(axis=1, keepdims=True)).mean(axis=1)
    mad = pd.Series(mad, index=close.index)
    out = (tp - mean) / (0.015 * mad)
    return out.where(mad != 0, 0.0).where(mad.notna())


def keltner(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 20, atr_n: int = 10,
            mult: float = 2.0) -> pd.DataFrame:
    """Keltner Channels: EMA(close, n) +/- mult * ATR(atr_n)."""
    mid = ema(close, n)
    width = mult * atr(high, low, close, atr_n)
    return pd.DataFrame({"mid": mid, "upper": mid + width, "lower": mid - width})


def historical_volatility(close: pd.Series, n: int = 20, periods_per_year: int = 252) -> pd.Series:
    """Annualised close-to-close volatility as a FRACTION (0.25 = 25%). Sample std (ddof=1) of log returns."""
    _check_n(n)
    if n < 2:
        raise ValueError("n must be >= 2")
    logret = np.log(close / close.shift(1))
    return logret.rolling(n, min_periods=n).std(ddof=1) * np.sqrt(periods_per_year)


def mfi(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series, n: int = 14) -> pd.Series:
    """Money Flow Index. Bars where typical price is unchanged contribute to neither side.
    No negative flow -> 100; no flow at all -> 50 (convention)."""
    _check_n(n)
    tp = (high + low + close) / 3.0
    raw = tp * volume
    d = tp.diff()
    pos = raw.where(d > 0, 0.0).where(d.notna())
    neg = raw.where(d < 0, 0.0).where(d.notna())
    p = pos.rolling(n, min_periods=n).sum()
    m = neg.rolling(n, min_periods=n).sum()
    out = 100.0 - 100.0 / (1.0 + p / m)
    out = out.where(m != 0, 100.0)
    out = out.where(~((m == 0) & (p == 0)), 50.0)
    return out.where(p.notna())


def stoch_rsi(close: pd.Series, rsi_n: int = 14, stoch_n: int = 14, k: int = 3, d: int = 3) -> pd.DataFrame:
    """Stochastic RSI on a 0-100 scale. Raw %K is UNDEFINED (NaN) when RSI is constant over the window."""
    r = rsi(close, rsi_n)
    lo = r.rolling(stoch_n, min_periods=stoch_n).min()
    hi = r.rolling(stoch_n, min_periods=stoch_n).max()
    span = hi - lo
    raw = (100.0 * (r - lo) / span).where(span > 0)
    kk = sma(raw, k)
    return pd.DataFrame({"raw": raw, "k": kk, "d": sma(kk, d)})


def vwap(high: pd.Series, low: pd.Series, close: pd.Series, volume: pd.Series,
         session: pd.Series) -> pd.Series:
    """Session-anchored VWAP: cumulative sum(TP*vol)/sum(vol), reset whenever `session` changes.
    `session` is a label aligned to the bars (e.g. the US/Eastern trade date). Zero cumulative volume -> NaN."""
    tp = (high + low + close) / 3.0
    pv = (tp * volume).groupby(session).cumsum()
    vv = volume.groupby(session).cumsum()
    return (pv / vv).where(vv > 0)


def swing_points(high: pd.Series, low: pd.Series, k: int = 2) -> pd.DataFrame:
    """Causal fractal pivots. A pivot high at bar i needs high[i] strictly greater than the k bars on EACH side,
    so it is only knowable at bar i+k. The pivot price is therefore reported on its CONFIRMATION bar (i+k) and
    `*_bars_ago` (= k) says where it really occurred. Ties do not form pivots. Never plot at confirmation bar."""
    _check_n(k)
    h, l = high.to_numpy(dtype=float), low.to_numpy(dtype=float)
    n = len(h)
    ph = np.full(n, np.nan)
    pl = np.full(n, np.nan)
    for i in range(k, n - k):
        left_h, right_h = h[i - k:i], h[i + 1:i + k + 1]
        if h[i] > left_h.max() and h[i] > right_h.max():
            ph[i + k] = h[i]
        left_l, right_l = l[i - k:i], l[i + 1:i + k + 1]
        if l[i] < left_l.min() and l[i] < right_l.min():
            pl[i + k] = l[i]
    idx = high.index
    return pd.DataFrame({
        "pivot_high": ph, "pivot_high_bars_ago": np.where(np.isnan(ph), np.nan, float(k)),
        "pivot_low": pl, "pivot_low_bars_ago": np.where(np.isnan(pl), np.nan, float(k)),
    }, index=idx)
