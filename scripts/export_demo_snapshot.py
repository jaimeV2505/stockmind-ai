#!/usr/bin/env python3
"""Export a deterministic, SIMULATED snapshot from the real engines for the web app (apps/web/data/demo-snapshot.json).

Everything in the output is produced by the Python engines in this repo on `DemoProvider` data (symbols SIMA..SIME are fictional
on purpose). It is NOT market data. The web app must always label it as simulated.
Usage:  python scripts/export_demo_snapshot.py [--check]    (--check: fail if the committed file differs from a fresh export)
"""
from __future__ import annotations

import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for svc in (ROOT / "services").iterdir():
    sys.path.insert(0, str(svc))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from stockmind_backtest import BacktestConfig, run_backtest  # noqa: E402
from stockmind_marketdata import DataMode, DemoProvider, Timeframe, validate_series  # noqa: E402
from stockmind_patterns import PatternIndex, summarize  # noqa: E402
from stockmind_risk import atr_stop, position_size, risk_reward  # noqa: E402
from stockmind_signals import NoSignal, Signal, default_registry, decide  # noqa: E402
from stockmind_ta import atr, bollinger, ema, macd, rsi, sma  # noqa: E402

OUT = ROOT / "apps" / "web" / "data" / "demo-snapshot.json"
SYMBOLS = {"SIMA": "Simulated Co A", "SIMB": "Simulated Co B", "SIMC": "Simulated Co C", "SIMD": "Simulated Co D", "SIME": "Simulated Co E"}
NOW = datetime(2026, 10, 9, 23, 0, tzinfo=timezone.utc)      # fixed => deterministic output
SHOW = 252                                                   # bars shown in the UI (warm-up bars before that feed the indicators)
CFG = BacktestConfig("none (simulated data)", 100_000.0, 0.95, 1.0, 5.0, 5.0, 0.08)


def clean(x, nd=6):
    """float -> rounded float; NaN/inf -> None (strict JSON has no NaN)."""
    if x is None:
        return None
    x = float(x)
    return round(x, nd) if math.isfinite(x) else None


def series(s: pd.Series, nd=6):
    return [clean(v, nd) for v in s.tail(SHOW).to_numpy()]


def frame(symbol: str) -> pd.DataFrame:
    cs = DemoProvider(seed=11, now=NOW).get_candles(symbol, Timeframe.D1, datetime(2025, 1, 2, tzinfo=timezone.utc), datetime(2026, 10, 8, tzinfo=timezone.utc))
    rep = validate_series(cs)
    assert rep.ok and all(c.data_mode is DataMode.SIMULATED for c in cs), rep
    return pd.DataFrame({k: [getattr(c, k) for c in cs] for k in ("open", "high", "low", "close", "volume")},
                        index=pd.DatetimeIndex([c.market_ts for c in cs]))


def ts(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def build() -> dict:
    bars = {s: frame(s) for s in SYMBOLS}
    index = PatternIndex(window=30, horizon=10)
    for s, b in bars.items():
        index.add_symbol(s, b)
    strategies = default_registry().active()
    out_symbols = []
    for s, name in SYMBOLS.items():
        b = bars[s]
        c, h, l, v = b["close"], b["high"], b["low"], b["volume"]
        shown = b.tail(SHOW)
        bb, mc = bollinger(c, 20, 2.0), macd(c)
        ind = {"ema20": series(ema(c, 20)), "ema50": series(ema(c, 50)), "sma200": series(sma(c, 200)),
               "bb_upper": series(bb["upper"]), "bb_lower": series(bb["lower"]), "rsi14": series(rsi(c, 14), 3),
               "macd": series(mc["macd"]), "macd_signal": series(mc["signal"]), "macd_hist": series(mc["hist"]),
               "atr14": series(atr(h, l, c, 14))}
        decisions, backtests, markers = [], [], []
        for st in strategies:
            d = decide(st, b, s, "1d")
            if isinstance(d, Signal):
                decisions.append({"strategy": st.id, "version": st.version_tag, "kind": "signal", "as_of": ts(d.trigger_ts), "status": d.status.value,
                                  "supporting": [{"name": e.name, "value": e.value, "note": e.note} for e in d.supporting],
                                  "contradicting": [{"name": e.name, "value": e.value, "note": e.note} for e in d.contradicting]})
            else:
                assert isinstance(d, NoSignal)
                decisions.append({"strategy": st.id, "version": st.version_tag, "kind": "no_signal", "as_of": ts(d.as_of), "reason": d.reason})
            en, ex = st.flags(b)
            en_w, ex_w = en.tail(SHOW), ex.tail(SHOW)
            for i, t in enumerate(shown.index):           # entry flags only: level-type exit flags fire on many consecutive bars (noise)
                if en_w.iloc[i]:
                    markers.append({"t": ts(t), "strategy": st.id, "type": "entry_flag"})
            r = run_backtest(shown, en_w, ex_w, CFG)
            backtests.append({
                "strategy": st.id, "version": st.version_tag, "simulated": True, "config_hash": r.config_hash,
                "config": {"initial_capital": CFG.initial_capital, "position_fraction": CFG.position_fraction, "commission_per_trade": CFG.commission_per_trade,
                            "slippage_bps": CFG.slippage_bps, "stop_loss_fraction": CFG.stop_loss_fraction, "price_adjustment": CFG.price_adjustment},
                "metrics": {k: (clean(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x) for k, x in r.metrics.items()},
                "equity": [clean(x, 2) for x in r.equity.to_numpy()], "warnings": list(r.warnings),
                "trades": [{"entry": ts(t.entry_ts), "exit": ts(t.exit_ts), "entry_price": clean(t.entry_price), "exit_price": clean(t.exit_price),
                            "shares": t.shares, "pnl": clean(t.pnl, 2), "reason": t.exit_reason} for t in r.trades]})
        matches = index.query(s, b, k=8)
        summ = summarize(matches)
        last, a = float(c.iloc[-1]), float(atr(h, l, c, 14).iloc[-1])
        stop = atr_stop(last, a, 2.0)
        ps = position_size(100_000, 0.01, last, stop)
        out_symbols.append({
            "symbol": s, "name": name, "currency": "USD", "exchange": "SIM",
            "candles": [{"t": ts(t), "o": clean(r_.open, 4), "h": clean(r_.high, 4), "l": clean(r_.low, 4), "c": clean(r_.close, 4), "v": round(float(r_.volume))}
                        for t, r_ in zip(shown.index, shown.itertuples())],
            "indicators": ind, "decisions": decisions, "markers": markers, "backtests": backtests,
            "patterns": {"window": index.window, "horizon": index.horizon, "as_of": ts(b.index[-1]),
                         "matches": [{"symbol": m.symbol, "window_start": ts(m.window_start), "window_end": ts(m.window_end), "outcome_end": ts(m.outcome_end),
                                      "distance": clean(m.distance), "similarity": clean(m.similarity), "forward_return": clean(m.forward_return),
                                      "mfe": clean(m.mfe), "mae": clean(m.mae), "regime": m.regime} for m in matches],
                         "summary": {k: (clean(x) if isinstance(x, float) else ([clean(y) for y in x] if isinstance(x, tuple) else x)) for k, x in summ.items()}},
            "risk_example": {"equity": 100_000, "risk_fraction": 0.01, "entry": clean(last, 4), "atr14": clean(a, 4), "atr_multiple": 2.0, "stop": clean(stop, 4),
                             "shares": ps.shares, "risk_amount": clean(ps.risk_amount, 2), "notional": clean(ps.notional, 2), "binding": ps.binding_constraint,
                             "reward_risk_at_3R": clean(risk_reward(last, stop, last + 3 * (last - stop)), 2)},
        })
    return {
        "schema_version": 1,
        "meta": {"mode": "simulated", "data_source": "demo-simulated", "generated_at": ts(NOW), "as_of": out_symbols[0]["candles"][-1]["t"],
                 "timeframe": "1d", "bars_shown": SHOW, "symbols_are_fictional": True,
                 "note": "Produced by the stockmind Python engines on deterministic simulated data. Not market data. Not investment advice."},
        "symbols": out_symbols,
    }


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=None, separators=(",", ":"), allow_nan=False, ensure_ascii=False) + "\n"


def main() -> int:
    text = dumps(build())
    if "--check" in sys.argv:
        if not OUT.exists():
            print("snapshot missing")
            return 1
        a, b = json.loads(OUT.read_text()), json.loads(text)
        ok = _close(a, b)
        print("snapshot up to date" if ok else "snapshot DIFFERS from a fresh export: run scripts/export_demo_snapshot.py")
        return 0 if ok else 1
    OUT.write_text(text)
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text) / 1024:.0f} KB)")
    return 0


def _close(a, b, tol=1e-3) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= tol * max(1.0, abs(a), abs(b))
    return a == b


if __name__ == "__main__":
    raise SystemExit(main())
