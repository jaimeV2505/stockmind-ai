#!/usr/bin/env python3
"""Export a snapshot from the real engines for the web app.

  demo   (default): deterministic SIMULATED data (symbols SIMA..SIME are fictional)  -> apps/web/data/demo-snapshot.json
  market          : REAL end-of-day bars from Alpaca (needs ALPACA_API_KEY / ALPACA_API_SECRET) -> apps/web/data/market-snapshot.json
                    Fails loudly (exit != 0, nothing written) on missing/rejected credentials, provider outage or if no symbol passes the
                    data-quality gate. There is NO fallback to simulated data. Symbols that fail validation are listed in meta.excluded.

Usage:
  python scripts/export_demo_snapshot.py [--check]                       # demo; --check fails if the committed file is stale
  python scripts/export_demo_snapshot.py --source market [--symbols SPY,NVDA] [--feed iex|sip] [--years 3]
  python scripts/export_demo_snapshot.py --source market --fake-market --out /tmp/x.json   # DEV ONLY: synthetic Alpaca-shaped responses
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for svc in (ROOT / "services").iterdir():
    sys.path.insert(0, str(svc))

import pandas as pd  # noqa: E402

from stockmind_backtest import BacktestConfig, run_backtest  # noqa: E402
from stockmind_marketdata import (  # noqa: E402
    AlpacaDailyBars, DataMode, DemoProvider, ProviderAuthError, ProviderConfigError, ProviderDataError, ProviderError, ProviderUnavailable, Timeframe,
    validate_series,
)
from stockmind_marketdata.calendar import ET, to_market_time, trading_days  # noqa: E402
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


def to_frame(cs) -> pd.DataFrame:
    return pd.DataFrame({k: [getattr(c, k) for c in cs] for k in ("open", "high", "low", "close", "volume")},
                        index=pd.DatetimeIndex([c.market_ts for c in cs]))


def frame(symbol: str) -> pd.DataFrame:
    cs = DemoProvider(seed=11, now=NOW).get_candles(symbol, Timeframe.D1, datetime(2025, 1, 2, tzinfo=timezone.utc), datetime(2026, 10, 8, tzinfo=timezone.utc))
    rep = validate_series(cs)
    assert rep.ok and all(c.data_mode is DataMode.SIMULATED for c in cs), rep
    return to_frame(cs)


def ts(t) -> str:
    return pd.Timestamp(t).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%SZ")


def symbol_payload(s: str, name: str, b: pd.DataFrame, index: PatternIndex, strategies, exchange: str, cfg: BacktestConfig) -> dict:
    c, h, l = b["close"], b["high"], b["low"]
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
        r = run_backtest(shown, en_w, ex_w, cfg)
        backtests.append({
            "strategy": st.id, "version": st.version_tag, "simulated": True, "config_hash": r.config_hash,
            "config": {"initial_capital": cfg.initial_capital, "position_fraction": cfg.position_fraction, "commission_per_trade": cfg.commission_per_trade,
                        "slippage_bps": cfg.slippage_bps, "stop_loss_fraction": cfg.stop_loss_fraction, "price_adjustment": cfg.price_adjustment},
            "metrics": {k: (clean(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else x) for k, x in r.metrics.items()},
            "equity": [clean(x, 2) for x in r.equity.to_numpy()], "warnings": list(r.warnings),
            "trades": [{"entry": ts(t.entry_ts), "exit": ts(t.exit_ts), "entry_price": clean(t.entry_price), "exit_price": clean(t.exit_price),
                        "shares": t.shares, "pnl": clean(t.pnl, 2), "reason": t.exit_reason} for t in r.trades]})
    matches = index.query(s, b, k=8)
    summ = summarize(matches)
    last, a = float(c.iloc[-1]), float(atr(h, l, c, 14).iloc[-1])
    stop = atr_stop(last, a, 2.0)
    ps = position_size(100_000, 0.01, last, stop)
    return {
        "symbol": s, "name": name, "currency": "USD", "exchange": exchange,
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
    }


def build() -> dict:
    bars = {s: frame(s) for s in SYMBOLS}
    index = PatternIndex(window=30, horizon=10)
    for s, b in bars.items():
        index.add_symbol(s, b)
    strategies = default_registry().active()
    out_symbols = [symbol_payload(s, name, bars[s], index, strategies, "SIM", CFG) for s, name in SYMBOLS.items()]
    return {
        "schema_version": 1,
        "meta": {"mode": "simulated", "data_source": "demo-simulated", "generated_at": ts(NOW), "as_of": out_symbols[0]["candles"][-1]["t"],
                 "timeframe": "1d", "bars_shown": SHOW, "symbols_are_fictional": True,
                 "note": "Produced by the stockmind Python engines on deterministic simulated data. Not market data. Not investment advice."},
        "symbols": out_symbols,
    }


MIN_BARS = SHOW + 60     # shown bars + indicator warm-up / pattern window headroom


def build_market(provider, universe: dict, start: datetime, end: datetime, now: datetime) -> dict:
    """Real-data snapshot. Provider-wide failures (auth, outage, config) PROPAGATE; a symbol-level data problem excludes that symbol (listed)."""
    frames, excluded = {}, []
    for sym in universe:
        try:
            cs = list(provider.get_candles(sym, Timeframe.D1, start, end))
        except ProviderDataError as e:
            excluded.append({"symbol": sym, "reason": f"provider data rejected: {e}"})
            continue
        if len(cs) < MIN_BARS:
            excluded.append({"symbol": sym, "reason": f"insufficient history: {len(cs)} completed daily bars, need {MIN_BARS}"})
            continue
        rep = validate_series(cs)
        if not rep.ok:
            excluded.append({"symbol": sym, "reason": f"data-quality gate failed: {len(rep.missing_dates)} missing session(s), {len(rep.unexpected_dates)} unexpected, "
                                                       f"{len(rep.duplicates)} duplicate(s), {len(rep.incomplete)} incomplete, mixed provenance={rep.mixed_provenance}"})
            continue
        frames[sym] = to_frame(cs)
    if not frames:
        raise ProviderDataError("no symbol passed the data-quality gate: " + "; ".join(f"{e['symbol']}: {e['reason']}" for e in excluded))
    index = PatternIndex(window=30, horizon=10)
    for s, b in frames.items():
        index.add_symbol(s, b)
    cfg = BacktestConfig(f"{provider.adjustment}-adjusted ({provider.source})", 100_000.0, 0.95, 1.0, 5.0, 5.0, 0.08)
    strategies = default_registry().active()
    out = [symbol_payload(s, universe[s], frames[s], index, strategies, provider.exchange, cfg) for s in frames]
    as_of = min(sym["candles"][-1]["t"] for sym in out)
    return {
        "schema_version": 1,
        "meta": {"mode": "delayed", "data_source": provider.source, "feed": provider.feed, "adjustment": provider.adjustment,
                 "generated_at": ts(now), "as_of": as_of, "timeframe": "1d", "bars_shown": SHOW, "symbols_are_fictional": False,
                 "excluded": excluded,
                 "note": f"End-of-day bars from Alpaca (feed: {provider.feed}; the IEX feed is not the consolidated tape, so volumes are lower than the market total). "
                         "Indicators, signals, backtests and patterns computed by the stockmind engines. Not investment advice."},
        "symbols": out,
    }


def fake_transport(universe_symbols):
    """DEV ONLY: serves Alpaca-shaped daily bars (midnight-ET stamps) from a seeded random walk. 'GAPX' has missing sessions on purpose."""
    from urllib.parse import parse_qs, urlsplit

    def transport(url, headers):
        u = urlsplit(url)
        sym = u.path.split("/")[3]
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        start = datetime.strptime(q["start"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        end = datetime.strptime(q["end"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        rng = random.Random(f"fake-alpaca:{sym}")
        price, bars = 100.0 + rng.random() * 100, []
        days = trading_days(to_market_time(start).date(), to_market_time(end).date())
        for i, d in enumerate(days):
            o = price
            c = max(1.0, o * (1 + rng.gauss(0.0004, 0.014)))
            h, l = max(o, c) * (1 + abs(rng.gauss(0, 0.004))), min(o, c) * (1 - abs(rng.gauss(0, 0.004)))
            price = c
            if sym == "GAPX" and 300 < i < 306:
                continue
            t = datetime.combine(d, datetime.min.time(), tzinfo=ET).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            bars.append({"t": t, "o": round(o, 4), "h": round(h, 4), "l": round(l, 4), "c": round(c, 4), "v": int(rng.uniform(5e5, 3e6)), "n": 1, "vw": round(c, 4)})
        return 200, {}, json.dumps({"bars": bars, "symbol": sym, "next_page_token": None}).encode()

    return transport


def dumps(obj: dict) -> str:
    return json.dumps(obj, indent=None, separators=(",", ":"), allow_nan=False, ensure_ascii=False) + "\n"


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(text)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=("demo", "market"), default="demo")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out")
    ap.add_argument("--symbols")
    ap.add_argument("--universe", default=str(ROOT / "config" / "universe.json"))
    ap.add_argument("--feed", choices=("iex", "sip"), default="iex")
    ap.add_argument("--years", type=float, default=3.0)
    ap.add_argument("--fake-market", action="store_true", help="DEV ONLY: synthetic Alpaca-shaped transport; requires --out outside apps/web/data")
    a = ap.parse_args(argv)

    if a.source == "demo":
        text = dumps(build())
        if a.check:
            if not OUT.exists():
                print("snapshot missing")
                return 1
            ok = _close(json.loads(OUT.read_text()), json.loads(text))
            print("snapshot up to date" if ok else "snapshot DIFFERS from a fresh export: run scripts/export_demo_snapshot.py")
            return 0 if ok else 1
        out = Path(a.out) if a.out else OUT
        _write_atomic(out, text)
        print(f"wrote {out} ({len(text) / 1024:.0f} KB)")
        return 0

    if a.check:
        print("--check applies to the demo snapshot only")
        return 2
    universe = json.loads(Path(a.universe).read_text())
    if a.symbols:
        wanted = [x.strip().upper() for x in a.symbols.split(",") if x.strip()]
        universe = {s: universe.get(s, s) for s in wanted}            # unknown symbol: name = the symbol itself, never an invented name
    if a.fake_market:
        out = Path(a.out or "")
        if not a.out or str(out.resolve()).startswith(str((ROOT / "apps" / "web" / "data").resolve())):
            print("--fake-market needs --out outside apps/web/data (a synthetic snapshot must never be mistaken for real data)")
            return 2
        universe = {**universe, "GAPX": "Gap test symbol (excluded on purpose)"}
        provider = AlpacaDailyBars("fake", "fake", feed=a.feed, transport=fake_transport(universe), sleep=lambda s: None)
    else:
        out = Path(a.out) if a.out else ROOT / "apps" / "web" / "data" / "market-snapshot.json"
        try:
            provider = AlpacaDailyBars(os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_API_SECRET"), feed=a.feed)
        except ProviderConfigError as e:
            print(f"ERROR: {e}")
            return 2
    now = datetime.now(timezone.utc)
    try:
        snap = build_market(provider, universe, now - timedelta(days=int(365.25 * a.years)), now, now)
    except (ProviderAuthError, ProviderConfigError) as e:
        print(f"ERROR (credentials): {e}")
        return 2
    except ProviderUnavailable as e:
        print(f"ERROR (provider unavailable): {e}")
        return 3
    except ProviderError as e:
        print(f"ERROR: {e}")
        return 1
    if a.fake_market:
        snap["meta"]["data_source"] = "fake-alpaca-dev"
        snap["meta"]["note"] = "DEVELOPMENT FIXTURE produced by a synthetic transport. NOT market data."
    _write_atomic(out, dumps(snap))
    print(f"wrote {out}: {len(snap['symbols'])} symbol(s), excluded: {[e['symbol'] for e in snap['meta']['excluded']] or 'none'}")
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
