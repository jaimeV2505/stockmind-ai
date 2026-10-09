"""End-to-end: simulated bars -> strategy flags -> backtest -> risk sizing. Uses DemoProvider => results are SIMULATED."""
import unittest
from datetime import datetime, timezone

import pandas as pd

from stockmind_backtest import BacktestConfig, run_backtest
from stockmind_marketdata import DataMode, DemoProvider, Timeframe, validate_series
from stockmind_risk import atr_stop, position_size, risk_reward
from stockmind_signals import default_registry, scan
from stockmind_ta import atr

UTC = timezone.utc


def demo_frame(symbol, seed=7):
    cs = DemoProvider(seed=seed, now=datetime(2026, 10, 9, 23, tzinfo=UTC)).get_candles(
        symbol, Timeframe.D1, datetime(2024, 1, 2, tzinfo=UTC), datetime(2026, 9, 30, tzinfo=UTC))
    assert validate_series(cs).ok and all(c.data_mode is DataMode.SIMULATED for c in cs)
    return pd.DataFrame({k: [getattr(c, k) for c in cs] for k in ("open", "high", "low", "close", "volume")},
                        index=pd.DatetimeIndex([c.market_ts for c in cs]))


class TestPipeline(unittest.TestCase):
    def test_every_strategy_runs_through_the_backtester(self):
        bars = demo_frame("DEMO")
        cfg = BacktestConfig("none (simulated data)", 100_000.0, 0.95, 1.0, 5.0, 5.0, 0.08)
        for strat in default_registry().active():
            e, x = strat.flags(bars)
            r = run_backtest(bars, e, x, cfg)
            self.assertTrue(r.simulated and r.metrics["simulated"], strat.id)
            self.assertAlmostEqual(sum(t.pnl for t in r.trades), r.equity.iloc[-1] - 100_000.0, places=6)
            again = run_backtest(bars, e, x, cfg)
            self.assertEqual(r.config_hash, again.config_hash)

    def test_scan_then_size_a_hypothetical_trade(self):
        universe = {s: demo_frame(s, seed=i) for i, s in enumerate(("AAA", "BBB", "CCC"))}
        res = scan(universe, default_registry().active(), "1d")
        self.assertEqual(len(res.decisions) + len(res.errors), 9)
        self.assertEqual(res.errors, ())
        b = universe["AAA"]
        entry = float(b["close"].iloc[-1])
        stop = atr_stop(entry, float(atr(b["high"], b["low"], b["close"]).iloc[-1]), 2.0)
        p = position_size(100_000, 0.01, entry, stop)
        self.assertGreater(p.shares, 0)
        self.assertLessEqual(p.risk_amount, 1000.0 + 1e-6)
        self.assertGreater(risk_reward(entry, stop, entry + 3 * (entry - stop)), 2.99)


if __name__ == "__main__":
    unittest.main()
