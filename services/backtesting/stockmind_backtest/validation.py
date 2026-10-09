"""Out-of-sample validation: walk-forward and in-sample parameter sensitivity. SIMULATED results only. See ADR-0009.

Protocol per fold (rolling window, non-overlapping test windows by default):
  1. choose parameters ONLY from the fold's train window (flags computed from the train window alone);
  2. evaluate the chosen parameters on the immediately following test window, with flags computed from train+test
     history (causal, so test flags only see data up to each bar) and a fresh, flat backtest on the test bars;
  3. test data never influences selection (tested by poisoning the test window).
Folds are independent (each starts with `initial_capital`); pooled compounding across folds is reported separately.
Selecting from N candidates makes every in-sample number optimistic: judge the strategy on OOS figures only.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence

import numpy as np
import pandas as pd

from .engine import BacktestConfig, BacktestResult, run_backtest

OBJECTIVES = ("total_return", "expectancy", "profit_factor", "sharpe", "win_rate", "max_drawdown")


class FlagProducer(Protocol):
    def flags(self, bars: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
        ...


Factory = Callable[[Mapping[str, Any]], FlagProducer]


def expand_grid(grid: Mapping[str, Sequence[Any]]) -> list[dict[str, Any]]:
    if not grid or any(len(v) == 0 for v in grid.values()):
        raise ValueError("grid must be non-empty and every parameter needs at least one value")
    keys = sorted(grid)
    return [dict(zip(keys, combo)) for combo in itertools.product(*(grid[k] for k in keys))]


def _score(res: BacktestResult, objective: str, min_trades: int) -> float | None:
    v = res.metrics.get(objective)
    if v is None or res.metrics["n_trades"] < min_trades or not math.isfinite(v):
        return None
    return float(v)


def _run(bars: pd.DataFrame, flags_bars: pd.DataFrame, factory: Factory, params: Mapping[str, Any],
         config: BacktestConfig) -> BacktestResult:
    """Flags from `flags_bars` (a superset ending at bars' last bar), backtest on the trailing `len(bars)` rows."""
    en, ex = factory(params).flags(flags_bars)
    en, ex = en.iloc[-len(bars):], ex.iloc[-len(bars):]
    return run_backtest(bars, en, ex, config)


@dataclass(frozen=True)
class FoldResult:
    fold: int
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    selected_params: dict | None
    in_sample_score: float | None
    oos_score: float | None
    oos_n_trades: int
    oos_total_return: float | None
    skipped_reason: str | None
    oos_result: BacktestResult | None = None


@dataclass(frozen=True)
class WalkForwardResult:
    folds: tuple[FoldResult, ...]
    n_candidates: int
    objective: str
    pooled: dict
    warnings: tuple[str, ...] = field(default=())
    simulated: bool = True


def walk_forward(bars: pd.DataFrame, factory: Factory, grid: Mapping[str, Sequence[Any]], config: BacktestConfig,
                 train_bars: int, test_bars: int, step_bars: int | None = None, objective: str = "total_return",
                 min_train_trades: int = 3) -> WalkForwardResult:
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {OBJECTIVES}")
    if train_bars < 30 or test_bars < 5:
        raise ValueError("train_bars must be >= 30 and test_bars >= 5")
    step = test_bars if step_bars is None else step_bars   # explicit 0 must fail, not silently become the default
    if step < 1:
        raise ValueError("step_bars must be >= 1")
    if len(bars) < train_bars + test_bars:
        raise ValueError(f"need at least {train_bars + test_bars} bars, have {len(bars)}")
    candidates = expand_grid(grid)

    folds: list[FoldResult] = []
    for k, a in enumerate(range(0, len(bars) - train_bars - test_bars + 1, step)):
        tr = bars.iloc[a:a + train_bars]
        te = bars.iloc[a + train_bars:a + train_bars + test_bars]
        hist = bars.iloc[a:a + train_bars + test_bars]
        best, best_score = None, None
        for params in candidates:                          # deterministic order; ties keep the first
            sc = _score(_run(tr, tr, factory, params, config), objective, min_train_trades)
            if sc is not None and (best_score is None or sc > best_score):
                best, best_score = params, sc
        base = dict(fold=k, train_start=tr.index[0], train_end=tr.index[-1], test_start=te.index[0], test_end=te.index[-1])
        if best is None:
            folds.append(FoldResult(**base, selected_params=None, in_sample_score=None, oos_score=None, oos_n_trades=0,
                                    oos_total_return=None, skipped_reason="no_eligible_params", oos_result=None))
            continue
        oos = _run(te, hist, factory, best, config)
        folds.append(FoldResult(**base, selected_params=dict(best), in_sample_score=best_score,
                                oos_score=_score(oos, objective, 0), oos_n_trades=oos.metrics["n_trades"],
                                oos_total_return=oos.metrics["total_return"], skipped_reason=None, oos_result=oos))
    return WalkForwardResult(tuple(folds), len(candidates), objective, _pool(folds), _warn(folds, len(candidates)))


def _pool(folds: Sequence[FoldResult]) -> dict:
    ok = [f for f in folds if f.oos_result is not None]
    trades = [t for f in ok for t in f.oos_result.trades]
    pnl = np.array([t.pnl for t in trades])
    rets = [f.oos_total_return for f in ok]
    ins = [f.in_sample_score for f in ok if f.in_sample_score is not None]
    oos = [f.oos_score for f in ok if f.oos_score is not None]
    return {
        "n_folds": len(folds), "n_folds_evaluated": len(ok), "n_folds_skipped": len(folds) - len(ok),
        "oos_n_trades": len(trades),
        "oos_win_rate": float((pnl > 0).mean()) if len(pnl) else None,
        "oos_total_pnl": float(pnl.sum()) if len(pnl) else 0.0,
        "oos_compounded_return": float(np.prod([1 + r for r in rets]) - 1) if rets else None,  # folds chained, reinvested
        "oos_folds_positive": int(sum(r > 0 for r in rets)),
        "mean_in_sample_score": float(np.mean(ins)) if ins else None,
        "mean_oos_score": float(np.mean(oos)) if oos else None,
        "simulated": True,
    }


def _warn(folds: Sequence[FoldResult], n_candidates: int) -> tuple[str, ...]:
    w = []
    p = _pool(folds)
    if n_candidates > 1:
        w.append(f"parameters were selected in-sample from {n_candidates} candidates: in-sample scores are optimistically "
                 "biased; judge only the out-of-sample results")
    if p["n_folds_skipped"]:
        w.append(f"{p['n_folds_skipped']} fold(s) skipped: no parameter set met the minimum in-sample trade count")
    if p["oos_n_trades"] < 30:
        w.append(f"only {p['oos_n_trades']} out-of-sample trades: statistically weak, do not infer a reliable edge")
    if p["n_folds_evaluated"] < 5:
        w.append(f"only {p['n_folds_evaluated']} evaluated fold(s): little evidence of consistency across regimes")
    return tuple(w)


@dataclass(frozen=True)
class SensitivityResult:
    table: pd.DataFrame        # one row per parameter combination (in-sample, FULL sample)
    summary: dict
    warnings: tuple[str, ...]
    simulated: bool = True


def parameter_sensitivity(bars: pd.DataFrame, factory: Factory, grid: Mapping[str, Sequence[Any]],
                          config: BacktestConfig, objective: str = "total_return") -> SensitivityResult:
    """In-sample landscape over the grid. A robust strategy shows a broad plateau, not one lucky cell."""
    if objective not in OBJECTIVES:
        raise ValueError(f"objective must be one of {OBJECTIVES}")
    rows = []
    for params in expand_grid(grid):
        r = _run(bars, bars, factory, params, config)
        v = r.metrics.get(objective)
        rows.append({**params, "n_trades": r.metrics["n_trades"], objective: float(v) if v is not None else np.nan})
    table = pd.DataFrame(rows)
    vals = table[objective].dropna()
    summary = {
        "objective": objective, "n_cells": len(table), "n_defined": int(vals.size),
        "best": float(vals.max()) if vals.size else None, "median": float(vals.median()) if vals.size else None,
        "worst": float(vals.min()) if vals.size else None,
        "share_positive": float((vals > 0).mean()) if vals.size else None,
        "simulated": True,
    }
    warn = ["in-sample only: this describes parameter robustness, not out-of-sample performance"]
    if summary["share_positive"] is not None and summary["share_positive"] < 0.5:
        warn.append("fewer than half of the parameter cells are positive: the best cell is likely noise")
    return SensitivityResult(table, summary, tuple(warn))
