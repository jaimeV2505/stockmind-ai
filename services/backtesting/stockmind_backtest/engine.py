"""Single-symbol, long-only, daily-or-intraday bar backtester. See ADR-0008 for the execution conventions.

EVERY result is SIMULATED (`BacktestResult.simulated` is always True) and says nothing about future performance.

Execution conventions (the temporal-correctness contract):
- An entry/exit flag at bar t is assumed computed from information available at the CLOSE of bar t.
  It executes at the OPEN of bar t+1. A flag on the last bar can never execute and is ignored.
- Buys fill at open*(1+slippage); sells at price*(1-slippage). Commission = fixed + bps*notional, on both legs.
- One position at a time. Entry flags while in position are ignored. If exit and entry flags coincide, the exit
  executes and the entry is dropped (no flip on the same bar).
- Optional protective stop (fraction below the entry fill) is checked from the entry bar onward using the bar LOW.
  A gap through the stop fills at the OPEN (worse), otherwise at the stop. Slippage applies to stop fills.
- Any position still open after the last bar is closed at the last close (slippage + commission), reason "end_of_data".
- Prices MUST already be adjusted for splits/dividends; corporate actions are NOT modelled (declared in config).
- The engine does not and cannot verify that the caller's flags are themselves free of look-ahead.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class BacktestConfig:
    price_adjustment: str                 # REQUIRED label, e.g. "split_adjusted": documents what the caller supplied
    initial_capital: float = 100_000.0
    position_fraction: float = 1.0        # fraction of cash invested per entry (0, 1]
    commission_per_trade: float = 0.0     # fixed, per leg
    commission_bps: float = 0.0           # of notional, per leg
    slippage_bps: float = 5.0             # adverse, per leg
    stop_loss_fraction: float | None = None  # e.g. 0.05 -> stop 5% below the entry fill
    periods_per_year: int | None = 252    # for Sharpe/CAGR scaling; None disables Sharpe

    def validate(self) -> None:
        if not self.price_adjustment.strip():
            raise ValueError("price_adjustment must state how prices were adjusted")
        if not (math.isfinite(self.initial_capital) and self.initial_capital > 0):
            raise ValueError("initial_capital must be > 0")
        if not (0 < self.position_fraction <= 1):
            raise ValueError("position_fraction must be in (0, 1]")
        for n in ("commission_per_trade", "commission_bps", "slippage_bps"):
            v = getattr(self, n)
            if not (math.isfinite(v) and v >= 0):
                raise ValueError(f"{n} must be >= 0")
        if self.stop_loss_fraction is not None and not (0 < self.stop_loss_fraction < 1):
            raise ValueError("stop_loss_fraction must be in (0, 1)")
        if self.periods_per_year is not None and self.periods_per_year < 1:
            raise ValueError("periods_per_year must be >= 1")


@dataclass(frozen=True)
class Trade:
    entry_ts: pd.Timestamp
    exit_ts: pd.Timestamp
    entry_price: float     # fill, after slippage
    exit_price: float      # fill, after slippage
    shares: int
    costs: float           # commissions only (slippage is inside the fill prices)
    pnl: float             # net of commissions and slippage
    exit_reason: str       # "signal" | "stop" | "end_of_data"
    entry_idx: int
    exit_idx: int


@dataclass(frozen=True)
class BacktestResult:
    trades: tuple[Trade, ...]
    equity: pd.Series                       # mark-to-market at each bar's close
    metrics: dict
    config_hash: str                        # config + data + flags fingerprint (reproducibility)
    config: BacktestConfig
    simulated: bool = True
    warnings: tuple[str, ...] = field(default=())


def _validate_inputs(bars: pd.DataFrame, entries: pd.Series, exits: pd.Series | None) -> None:
    need = {"open", "high", "low", "close"}
    if not need.issubset(bars.columns):
        raise ValueError(f"bars must have columns {sorted(need)}")
    if len(bars) < 2:
        raise ValueError("need at least 2 bars")
    idx = bars.index
    if not isinstance(idx, pd.DatetimeIndex) or idx.tz is None:
        raise ValueError("bars index must be a timezone-aware DatetimeIndex")
    if not idx.is_monotonic_increasing or not idx.is_unique:
        raise ValueError("bars index must be strictly increasing and unique")
    ohlc = bars[["open", "high", "low", "close"]].to_numpy(dtype=float)
    if not np.isfinite(ohlc).all() or (ohlc <= 0).any():
        raise ValueError("OHLC must be finite and positive (no NaN/inf/zero): clean or reject the data first")
    o, h, l, c = ohlc.T
    if (h < np.maximum(np.maximum(o, c), l)).any() or (l > np.minimum(np.minimum(o, c), h)).any():
        raise ValueError("inconsistent OHLC bars (high/low violated)")
    for name, s in (("entries", entries), ("exits", exits)):
        if s is None:
            continue
        if not s.index.equals(idx):
            raise ValueError(f"{name} must be indexed exactly like bars")
        if s.dtype != bool:
            raise ValueError(f"{name} must be a boolean Series (NaN/ints not accepted)")


def _fingerprint(bars: pd.DataFrame, entries: pd.Series, exits: pd.Series | None, cfg: BacktestConfig) -> str:
    h = hashlib.sha256()
    h.update(json.dumps(asdict(cfg), sort_keys=True).encode())
    h.update(",".join(t.isoformat() for t in bars.index).encode())  # unit-independent across pandas versions
    h.update(np.ascontiguousarray(bars[["open", "high", "low", "close"]].to_numpy(dtype="float64")).tobytes())
    h.update(np.packbits(entries.to_numpy()).tobytes())
    h.update(b"-" if exits is None else np.packbits(exits.to_numpy()).tobytes())
    return h.hexdigest()


def run_backtest(bars: pd.DataFrame, entries: pd.Series, exits: pd.Series | None = None,
                 config: BacktestConfig | None = None) -> BacktestResult:
    if config is None:
        raise ValueError("config is required (price_adjustment must be declared explicitly)")
    config.validate()
    _validate_inputs(bars, entries, exits)

    n = len(bars)
    op, hi, lo, cl = (bars[k].to_numpy(dtype=float) for k in ("open", "high", "low", "close"))
    ent = entries.to_numpy()
    ext = exits.to_numpy() if exits is not None else np.zeros(n, dtype=bool)
    slip = config.slippage_bps / 1e4
    cbps = config.commission_bps / 1e4
    fixed = config.commission_per_trade

    cash = config.initial_capital
    shares = 0
    entry_fill = entry_comm = 0.0
    entry_idx = -1
    stop = None
    trades: list[Trade] = []
    equity = np.empty(n)
    warnings: list[str] = []
    skipped = 0
    pend_entry = pend_exit = False

    def close_position(i: int, raw_price: float, reason: str) -> None:
        nonlocal cash, shares, stop
        fill = raw_price * (1 - slip)
        notional = shares * fill
        comm = fixed + cbps * notional
        cash += notional - comm
        pnl = (fill - entry_fill) * shares - entry_comm - comm
        trades.append(Trade(bars.index[entry_idx], bars.index[i], entry_fill, fill, shares, entry_comm + comm,
                            pnl, reason, entry_idx, i))
        shares, stop = 0, None

    for i in range(n):
        if shares > 0 and pend_exit:
            close_position(i, op[i], "signal")
        elif shares == 0 and pend_entry:
            fill = op[i] * (1 + slip)
            budget = cash * config.position_fraction
            qty = int(math.floor((budget - fixed) / (fill * (1 + cbps)) + 1e-9)) if budget > fixed else 0
            if qty >= 1:
                notional = qty * fill
                entry_comm = fixed + cbps * notional
                cash -= notional + entry_comm
                shares, entry_fill, entry_idx = qty, fill, i
                stop = fill * (1 - config.stop_loss_fraction) if config.stop_loss_fraction else None
            else:
                skipped += 1
        if shares > 0 and stop is not None and lo[i] <= stop:
            close_position(i, op[i] if op[i] <= stop else stop, "stop")
        equity[i] = cash + shares * cl[i]
        pend_entry, pend_exit = bool(ent[i]) and i < n - 1, bool(ext[i]) and i < n - 1

    if shares > 0:
        close_position(n - 1, cl[n - 1], "end_of_data")
        equity[n - 1] = cash
    if skipped:
        warnings.append(f"{skipped} entry signal(s) skipped: not enough cash for one share after costs")
    if ent[-1] or ext[-1]:
        warnings.append("signal on the last bar ignored: no next bar to execute on")

    eq = pd.Series(equity, index=bars.index, name="equity")
    return BacktestResult(tuple(trades), eq, _metrics(bars, eq, trades, config),
                          _fingerprint(bars, entries, exits, config), config, True, tuple(warnings))


def _metrics(bars: pd.DataFrame, eq: pd.Series, trades: list[Trade], cfg: BacktestConfig) -> dict:
    end = float(eq.iloc[-1])
    pnl = np.array([t.pnl for t in trades])
    wins, losses = pnl[pnl > 0], pnl[pnl < 0]
    peak = eq.cummax()
    years = (eq.index[-1] - eq.index[0]).total_seconds() / (365.25 * 86400)
    rets = eq.pct_change().dropna()
    sharpe = None
    if cfg.periods_per_year and len(rets) >= 30 and rets.std(ddof=1) > 0:
        sharpe = float(rets.mean() / rets.std(ddof=1) * math.sqrt(cfg.periods_per_year))
    held = sum(t.exit_idx - t.entry_idx + 1 for t in trades)
    return {
        "simulated": True,
        "initial_capital": cfg.initial_capital,
        "final_equity": end,
        "total_return": end / cfg.initial_capital - 1,
        "cagr": (end / cfg.initial_capital) ** (1 / years) - 1 if years >= 1 and end > 0 else None,  # needs >= 1 year
        "n_trades": len(trades),
        "win_rate": float(len(wins) / len(trades)) if trades else None,
        "avg_win": float(wins.mean()) if len(wins) else None,
        "avg_loss": float(losses.mean()) if len(losses) else None,
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else None,  # undefined without losses
        "expectancy": float(pnl.mean()) if len(pnl) else None,
        "max_drawdown": float(((eq - peak) / peak).min()),
        "exposure": held / len(eq),
        "sharpe": sharpe,  # rf = 0, sample std, needs >= 30 bars; scale assumes periods_per_year bars/year
        "buy_hold_return": float(bars["close"].iloc[-1] / bars["close"].iloc[0] - 1),  # frictionless benchmark
        "total_costs": float(sum(t.costs for t in trades)),
    }
