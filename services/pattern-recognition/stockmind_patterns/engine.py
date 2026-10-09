"""Historical pattern similarity engine (numpy/pandas only). See ADR-0010.

Leakage / bias rules enforced here (each has a test):
  1. A candidate is eligible only if its forward OUTCOME was already known at query time (`outcome_end_ts <= as_of`).
  2. For the query's own symbol the candidate must END ITS OUTCOME before the query window starts (no overlap, no self-match).
  3. Greedy per-symbol minimum separation between returned matches (overlapping-sample inflation).
  4. Regime labels are causal (use only bars up to the window end).
  5. Prices must be pre-adjusted for splits/dividends (not verifiable here; callers' responsibility).
Survivorship bias: the index only knows the symbols it is given. Include delisted/failed names or the statistics are biased.
Similarity is a distance transform, NOT a probability; `share_positive` is a descriptive frequency, never a calibrated win rate.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import numpy as np
import pandas as pd

DISCLAIMER = ("Similarity scores are uncalibrated distances, not probabilities. Historical outcomes are descriptive "
              "statistics of past, correlated samples and do not predict future returns.")
_COLS = ("open", "high", "low", "close", "volume")
_REGIME_SMA = 50


def shape_of(close: Sequence[float], volume: Sequence[float] | None = None, volume_weight: float = 0.0) -> np.ndarray | None:
    """Trend shape: (log price - first log price) / std(log returns). Scale- and volatility-invariant.
    Returns None for a window with no variation (cannot be volatility-normalised)."""
    c = np.asarray(close, dtype=float)
    if c.ndim != 1 or c.size < 3 or not np.isfinite(c).all() or (c <= 0).any():
        raise ValueError("close must be a 1-D array of >= 3 finite positive values")
    lc = np.log(c)
    sigma = float(np.std(np.diff(lc), ddof=1))
    if not math.isfinite(sigma) or sigma <= 1e-12:
        return None
    out = (lc - lc[0]) / sigma
    if volume_weight > 0:
        if volume is None:
            raise ValueError("volume required when volume_weight > 0")
        lv = np.log1p(np.asarray(volume, dtype=float))
        sd = lv.std()
        out = np.concatenate([out, volume_weight * ((lv - lv.mean()) / sd if sd > 0 else np.zeros_like(lv))])
    return out


def dtw_distance(a: Sequence[float], b: Sequence[float], band: int | None = None) -> float:
    """Dynamic Time Warping with |x-y| cost and an optional Sakoe-Chiba band, normalised by (len(a)+len(b))."""
    x, y = np.asarray(a, float), np.asarray(b, float)
    n, m = len(x), len(y)
    if n == 0 or m == 0:
        raise ValueError("empty sequence")
    if band is not None and band < abs(n - m):
        raise ValueError("band must be >= |len(a) - len(b)|")
    w = max(n, m) if band is None else band
    inf = float("inf")
    prev = [inf] * (m + 1)
    prev[0] = 0.0
    for i in range(1, n + 1):
        cur = [inf] * (m + 1)
        lo, hi = max(1, i - w), min(m, i + w)
        for j in range(lo, hi + 1):
            cur[j] = abs(x[i - 1] - y[j - 1]) + min(prev[j], cur[j - 1], prev[j - 1])
        prev = cur
    return prev[m] / (n + m)


@dataclass(frozen=True)
class Window:
    symbol: str
    end_idx: int
    start_ts: pd.Timestamp
    end_ts: pd.Timestamp
    outcome_end_ts: pd.Timestamp
    forward_return: float
    mfe: float            # max favourable excursion over the horizon (>= 0 typically)
    mae: float            # max adverse excursion over the horizon (<= 0 typically)
    regime: str | None
    shape: np.ndarray = field(compare=False, repr=False)


@dataclass(frozen=True)
class Match:
    symbol: str
    end_idx: int
    window_start: pd.Timestamp
    window_end: pd.Timestamp
    outcome_end: pd.Timestamp
    distance: float       # normalised DTW on trend shapes (lower = more similar)
    similarity: float     # 1/(1+distance): monotone transform, UNCALIBRATED
    forward_return: float
    mfe: float
    mae: float
    regime: str | None


def _check_bars(bars: pd.DataFrame) -> None:
    if any(c not in bars.columns for c in _COLS):
        raise ValueError(f"bars need columns {_COLS}")
    if not isinstance(bars.index, pd.DatetimeIndex) or bars.index.tz is None:
        raise ValueError("bars index must be a tz-aware DatetimeIndex")
    if not bars.index.is_monotonic_increasing or not bars.index.is_unique:
        raise ValueError("bars index must be strictly increasing")
    v = bars[list(_COLS)].to_numpy(dtype=float)
    if not np.isfinite(v).all() or (bars[["open", "high", "low", "close"]].to_numpy(dtype=float) <= 0).any():
        raise ValueError("bars must be finite with positive prices")


def _regimes(close: pd.Series) -> list[str | None]:
    sma = close.rolling(_REGIME_SMA, min_periods=_REGIME_SMA).mean()   # causal: uses bars <= t only
    return [None if np.isnan(s) else ("up" if c > s else "down") for c, s in zip(close.to_numpy(), sma.to_numpy())]


class PatternIndex:
    def __init__(self, window: int = 30, horizon: int = 10, volume_weight: float = 0.0, stride: int = 1) -> None:
        if window < 8 or horizon < 1 or stride < 1 or volume_weight < 0:
            raise ValueError("require window >= 8, horizon >= 1, stride >= 1, volume_weight >= 0")
        self.window, self.horizon, self.volume_weight, self.stride = window, horizon, volume_weight, stride
        self._by_symbol: dict[str, list[Window]] = {}

    def add_symbol(self, symbol: str, bars: pd.DataFrame) -> int:
        _check_bars(bars)
        if symbol in self._by_symbol:
            raise ValueError(f"{symbol} already indexed")
        close, high, low = (bars[k].to_numpy(float) for k in ("close", "high", "low"))
        vol = bars["volume"].to_numpy(float)
        regimes = _regimes(bars["close"])
        out: list[Window] = []
        w, h = self.window, self.horizon
        for e in range(w - 1, len(bars) - h, self.stride):      # only windows whose full forward horizon exists
            shp = shape_of(close[e - w + 1:e + 1], vol[e - w + 1:e + 1], self.volume_weight)
            if shp is None:
                continue
            out.append(Window(symbol, e, bars.index[e - w + 1], bars.index[e], bars.index[e + h],
                              close[e + h] / close[e] - 1, high[e + 1:e + h + 1].max() / close[e] - 1,
                              low[e + 1:e + h + 1].min() / close[e] - 1, regimes[e], shp))
        self._by_symbol[symbol] = out
        return len(out)

    def windows(self, symbol: str) -> list[Window]:
        return list(self._by_symbol[symbol])

    def query(self, symbol: str, bars: pd.DataFrame, k: int = 10, as_of: pd.Timestamp | None = None,
              same_regime: bool = False, min_separation: int | None = None, prefilter: int | None = None,
              band: int | None = None) -> list[Match]:
        _check_bars(bars)
        if k < 1:
            raise ValueError("k must be >= 1")
        q = bars if as_of is None else bars.loc[:as_of]
        if len(q) < self.window:
            raise ValueError(f"need at least {self.window} bars up to as_of, have {len(q)}")
        as_of_ts = q.index[-1]
        qwin = q.iloc[-self.window:]
        qshape = shape_of(qwin["close"].to_numpy(float), qwin["volume"].to_numpy(float), self.volume_weight)
        if qshape is None:
            raise ValueError("query window has no price variation")
        q_start = qwin.index[0]
        q_regime = _regimes(q["close"])[-1]
        if same_regime and q_regime is None:
            raise ValueError(f"same_regime needs >= {_REGIME_SMA} bars of history")

        cands: list[Window] = []
        for sym, ws in self._by_symbol.items():
            for c in ws:
                if c.outcome_end_ts > as_of_ts:                                   # rule 1: outcome not yet known
                    continue
                if sym == symbol and c.outcome_end_ts >= q_start:                 # rule 2: overlap / self-match
                    continue
                if same_regime and c.regime != q_regime:
                    continue
                cands.append(c)
        if not cands:
            return []
        mat = np.vstack([c.shape for c in cands])
        euclid = np.sqrt(((mat - qshape) ** 2).sum(axis=1))
        keep = np.argsort(euclid, kind="stable")[: (prefilter or max(10 * k, 50))]
        scored = sorted(((dtw_distance(qshape, cands[i].shape, band), cands[i]) for i in keep),
                        key=lambda t: (t[0], t[1].symbol, t[1].end_idx))
        sep = self.window if min_separation is None else min_separation
        chosen: list[tuple[float, Window]] = []
        for d, c in scored:                                                       # rule 3: greedy per-symbol separation
            if all(not (c.symbol == o.symbol and abs(c.end_idx - o.end_idx) < sep) for _, o in chosen):
                chosen.append((d, c))
            if len(chosen) == k:
                break
        return [Match(c.symbol, c.end_idx, c.start_ts, c.end_ts, c.outcome_end_ts, d, 1.0 / (1.0 + d),
                      c.forward_return, c.mfe, c.mae, c.regime) for d, c in chosen]


def summarize(matches: Iterable[Match], n_boot: int = 2000, seed: int = 0) -> dict:
    ms = list(matches)
    n = len(ms)
    notes = [DISCLAIMER, "Matches drawn from the same calendar period are correlated; the effective sample is smaller than n."]
    if n == 0:
        return {"n": 0, "notes": notes + ["no historical matches: INSUFFICIENT EVIDENCE"], "ci_median_95": None}
    fr = np.array([m.forward_return for m in ms])
    mfe = np.array([m.mfe for m in ms])
    mae = np.array([m.mae for m in ms])
    ci = None
    if n >= 30:
        rng = np.random.default_rng(seed)
        meds = np.median(rng.choice(fr, size=(n_boot, n), replace=True), axis=1)
        ci = (float(np.percentile(meds, 2.5)), float(np.percentile(meds, 97.5)))
    else:
        notes.append(f"n={n} < 30: no confidence interval is reported (sample too small to justify one)")
    if n < 10:
        notes.append("very small sample: treat the statistics as anecdotal")
    q = np.percentile(fr, [10, 25, 75, 90])
    return {
        "n": n, "median_forward_return": float(np.median(fr)), "mean_forward_return": float(fr.mean()),
        "q10": float(q[0]), "q25": float(q[1]), "q75": float(q[2]), "q90": float(q[3]),
        "share_positive": float((fr > 0).mean()),         # fraction with forward_return > 0 at the horizon; descriptive only
        "median_mfe": float(np.median(mfe)), "median_mae": float(np.median(mae)),
        "worst_mae": float(mae.min()), "ci_median_95": ci, "n_symbols": len({m.symbol for m in ms}), "notes": notes,
    }
