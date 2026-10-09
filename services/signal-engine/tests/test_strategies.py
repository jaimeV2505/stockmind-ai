import unittest
from datetime import timezone

import numpy as np
import pandas as pd

from stockmind_signals import (
    BullishBreakout, MovingAverageCrossover, NoSignal, OversoldRecovery, Signal, SignalRegistry, StrategyRegistry,
    decide, default_registry, scan,
)


def bars_from(close, volume=None, high=None, low=None, start="2024-01-02"):
    c = np.asarray(close, float)
    n = len(c)
    v = np.full(n, 1000.0) if volume is None else np.asarray(volume, float)
    h = c + 0.5 if high is None else np.asarray(high, float)
    l = c - 0.5 if low is None else np.asarray(low, float)
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(h, np.maximum(o, c)), np.minimum(l, np.minimum(o, c))
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": v},
                        index=pd.date_range(start, periods=n, freq="D", tz="UTC"))


def random_bars(n=300, seed=1):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    return bars_from(c, rng.uniform(5e5, 2e6, n), c * (1 + np.abs(rng.normal(0, .006, n))), c * (1 - np.abs(rng.normal(0, .006, n))))


def pure_rsi(c, n=14):
    d = [c[i] - c[i - 1] for i in range(1, len(c))]
    g, l = [max(x, 0.0) for x in d], [max(-x, 0.0) for x in d]
    ag, al = sum(g[:n]) / n, sum(l[:n]) / n
    out = [np.nan] * n + [100 - 100 / (1 + ag / al) if al else 100.0]
    for i in range(n, len(d)):
        ag, al = (ag * (n - 1) + g[i]) / n, (al * (n - 1) + l[i]) / n
        out.append(100 - 100 / (1 + ag / al) if al else 100.0)
    return np.array(out)


class TestOversoldRecovery(unittest.TestCase):
    def setUp(self):
        self.close = np.r_[np.linspace(100, 62, 26), np.linspace(62, 95, 20)]
        self.bars = bars_from(self.close)

    def test_entry_at_independently_computed_crossing(self):
        r = pure_rsi(list(self.close))
        expected = [i for i in range(1, len(r)) if r[i - 1] < 30 <= r[i]]
        self.assertEqual(len(expected), 1)
        entries, exits = OversoldRecovery().flags(self.bars)
        self.assertEqual(list(np.flatnonzero(entries)), expected)
        first_exit = [i for i in range(len(r)) if r[i] >= 55]
        self.assertEqual(list(np.flatnonzero(exits)), first_exit)

    def test_no_entry_without_oversold_condition(self):
        bars = bars_from(np.linspace(100, 130, 60))
        self.assertFalse(OversoldRecovery().flags(bars)[0].any())

    def test_param_validation(self):
        for kw in (dict(oversold=60), dict(rsi_n=1), dict(exit_level=100), dict(oversold=0)):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                OversoldRecovery(**kw)


class TestMACrossover(unittest.TestCase):
    def test_cross_points_match_independent_sma(self):
        close = np.r_[np.linspace(100, 70, 40), np.linspace(70, 120, 50), np.linspace(120, 80, 40)]
        bars = bars_from(close)
        f, s = 5, 15
        sma = lambda w: np.r_[[np.nan] * (w - 1), np.convolve(close, np.ones(w) / w, mode="valid")]  # noqa: E731
        sf, ss = sma(f), sma(s)
        up = [i for i in range(1, len(close)) if sf[i - 1] <= ss[i - 1] and sf[i] > ss[i]]
        dn = [i for i in range(1, len(close)) if sf[i - 1] >= ss[i - 1] and sf[i] < ss[i]]
        self.assertTrue(up and dn)
        entries, exits = MovingAverageCrossover(f, s).flags(bars)
        self.assertEqual(list(np.flatnonzero(entries)), up)
        self.assertEqual(list(np.flatnonzero(exits)), dn)

    def test_validation(self):
        with self.assertRaises(ValueError):
            MovingAverageCrossover(50, 20)


class TestBreakout(unittest.TestCase):
    def scenario(self, close_jump=105.0, vol_jump=3000.0, n=40):
        close = np.full(n, 100.0)
        high = np.full(n, 101.0)
        vol = np.full(n, 1000.0)
        close[30], high[30], vol[30] = close_jump, close_jump + 1, vol_jump
        return bars_from(close, vol, high, np.full(n, 99.0))

    def test_entry_only_on_breakout_bar(self):
        e, _ = BullishBreakout().flags(self.scenario())
        self.assertEqual(list(np.flatnonzero(e)), [30])

    def test_needs_volume_confirmation(self):
        self.assertFalse(BullishBreakout().flags(self.scenario(vol_jump=1000.0))[0].any())

    def test_equal_to_prior_high_is_not_a_breakout(self):
        self.assertFalse(BullishBreakout().flags(self.scenario(close_jump=101.0))[0].any())   # strict >

    def test_exit_below_prior_low(self):
        close = np.full(60, 100.0)
        close[45] = 90.0
        e, x = BullishBreakout().flags(bars_from(close, high=np.full(60, 101.0), low=np.full(60, 99.0)))
        self.assertEqual(list(np.flatnonzero(x)), [45])


def choppy_bars(n=360, seed=2):
    """Oscillating market (period ~45 bars + noise + volume bursts): produces oversold dips, crossovers and breakouts."""
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    c = 100 + 14 * np.sin(2 * np.pi * t / 45) + rng.normal(0, 1.2, n)
    vol = rng.uniform(5e5, 1e6, n) * np.where(rng.random(n) < 0.12, 3.0, 1.0)
    return bars_from(c, vol, c + np.abs(rng.normal(0, .8, n)), c - np.abs(rng.normal(0, .8, n)))


class TestCausality(unittest.TestCase):
    """Truncate at regular cuts AND exactly at every trigger bar: sparse signals hide look-ahead at arbitrary cuts
    (a single-cut / every-7-bars version of this test missed a planted look-ahead; see audit notes)."""

    MIN_EVENTS = 3

    def test_flags_never_depend_on_future_bars(self):
        for bars in (choppy_bars(), random_bars(320, seed=4)):
            for strat in (OversoldRecovery(), MovingAverageCrossover(10, 30), BullishBreakout(15, 1.2, 8)):
                fe, fx = strat.flags(bars)
                n = len(bars)
                events = list(np.flatnonzero(fe)) + list(np.flatnonzero(fx))
                cuts = set(range(strat.min_bars + 5, n, 7)) | {i + d for i in events for d in (0, 1) if i + d > strat.min_bars}
                for cut in sorted(cuts):
                    pe, px = strat.flags(bars.iloc[:cut])
                    np.testing.assert_array_equal(fe.iloc[:cut].to_numpy(), pe.to_numpy(), err_msg=f"{strat.id} entries @{cut}")
                    np.testing.assert_array_equal(fx.iloc[:cut].to_numpy(), px.to_numpy(), err_msg=f"{strat.id} exits @{cut}")

    def test_the_causality_data_actually_exercises_every_strategy(self):
        """Guard against a vacuous causality test: each strategy must fire entries AND exits on the choppy series."""
        bars = choppy_bars()
        for strat in (OversoldRecovery(), MovingAverageCrossover(10, 30), BullishBreakout(15, 1.2, 8)):
            fe, fx = strat.flags(bars)
            self.assertGreaterEqual(int(fe.sum()), self.MIN_EVENTS, f"{strat.id}: only {int(fe.sum())} entries")
            self.assertGreaterEqual(int(fx.sum()), self.MIN_EVENTS, f"{strat.id}: only {int(fx.sum())} exits")

    def test_flags_are_plain_bool_and_nan_safe(self):
        bars = random_bars(120)
        bars.iloc[50, bars.columns.get_loc("close")] = np.nan
        for strat in (OversoldRecovery(), MovingAverageCrossover(), BullishBreakout()):
            e, x = strat.flags(bars)
            self.assertEqual((e.dtype, x.dtype), (bool, bool))


class TestDecide(unittest.TestCase):
    def breakout_bars(self):
        return TestBreakout().scenario().iloc[:31]       # last bar = breakout bar

    def test_signal_with_evidence_at_last_bar(self):
        b = self.breakout_bars()
        s = decide(BullishBreakout(), b, "NVDA", "1d")
        self.assertIsInstance(s, Signal)
        self.assertEqual(s.trigger_ts, b.index[-1].to_pydatetime())
        self.assertEqual(s.trigger_ts.tzinfo, timezone.utc)
        names = [e.name for e in s.supporting]
        self.assertEqual(names, ["breakout_level", "close", "relative_volume"])
        self.assertEqual(s.supporting[0].value, 101.0)
        self.assertEqual(s.strategy_version, BullishBreakout().version_tag)

    def test_no_signal_reasons(self):
        b = self.breakout_bars()
        n = decide(BullishBreakout(), b.iloc[:10], "NVDA", "1d")
        self.assertIsInstance(n, NoSignal)
        self.assertIn("insufficient history", n.reason)
        self.assertIn("no entry trigger", decide(BullishBreakout(), b.iloc[:25], "NVDA", "1d").reason)
        nan_last = b.copy()
        nan_last.iloc[-1, nan_last.columns.get_loc("volume")] = np.nan
        self.assertIn("missing values", decide(BullishBreakout(), nan_last, "NVDA", "1d").reason)

    def test_parameterisations_never_collide(self):
        b = self.breakout_bars()
        s1 = decide(BullishBreakout(), b, "NVDA", "1d")
        s2 = decide(BullishBreakout(lookback=21), b, "NVDA", "1d")
        self.assertIsInstance(s1, Signal)
        self.assertIsInstance(s2, Signal)
        self.assertNotEqual(s1.key, s2.key)
        self.assertEqual(s1.key, decide(BullishBreakout(), b, "NVDA", "1d").key)


class TestRegistry(unittest.TestCase):
    def test_register_versions_enable_disable(self):
        reg = StrategyRegistry()
        s = MovingAverageCrossover()
        reg.register(s)
        with self.assertRaises(ValueError):
            reg.register(MovingAverageCrossover(5, 10))          # same id+version: must bump version, not overwrite
        reg.set_enabled(s.id, s.version, False)
        self.assertEqual(reg.active(), [])
        self.assertEqual([en for _, en in reg.all()], [False])
        reg.set_enabled(s.id, s.version, True)
        self.assertEqual(reg.active(), [s])
        with self.assertRaises(KeyError):
            reg.get("nope")
        with self.assertRaises(KeyError):
            reg.set_enabled("nope", "1.0.0", True)

    def test_latest_version_is_numeric_not_lexicographic(self):
        reg = StrategyRegistry()
        a = MovingAverageCrossover()
        b = type("V10", (MovingAverageCrossover,), {"version": "1.10.0"})()
        c = type("V9", (MovingAverageCrossover,), {"version": "1.9.0"})()
        for s in (a, c, b):
            reg.register(s)
        self.assertEqual(reg.get("ma_crossover").version, "1.10.0")

    def test_default_registry_has_three(self):
        self.assertEqual(len(default_registry().active()), 3)


class TestScanner(unittest.TestCase):
    def universe(self):
        good = TestBreakout().scenario().iloc[:31]
        flat = bars_from(np.full(40, 100.0), np.full(40, 1000.0), np.full(40, 101.0), np.full(40, 99.0))
        broken = good.drop(columns=["volume"])
        return {"ZZZ": flat, "AAA": good, "BAD": broken}

    def test_results_errors_and_determinism(self):
        strats = [BullishBreakout(), MovingAverageCrossover(10, 20)]
        r1 = scan(self.universe(), strats, "1d")
        r2 = scan(dict(reversed(list(self.universe().items()))), list(reversed(strats)), "1d")
        self.assertEqual(r1.decisions, r2.decisions)                       # order-independent
        # the 100 -> 105 jump is BOTH a volume breakout and an SMA10/SMA20 upward cross: two legitimate signals, one symbol
        self.assertEqual([(s.symbol, s.strategy_id) for s in r1.signals],
                         [("AAA", "bullish_breakout"), ("AAA", "ma_crossover")])
        self.assertEqual({e[0] for e in r1.errors}, {"BAD"})              # one bad symbol never aborts the scan
        self.assertEqual(len(r1.decisions), 4)                             # AAA+ZZZ x 2 strategies; BAD errored

    def test_idempotent_with_registry(self):
        reg = SignalRegistry()
        first = scan(self.universe(), [BullishBreakout()], "1d", reg)
        second = scan(self.universe(), [BullishBreakout()], "1d", reg)
        self.assertEqual((first.created, first.duplicates, second.created, second.duplicates), (1, 0, 0, 1))
        self.assertEqual(len(reg), 1)

    def test_scan_never_manufactures_signals(self):
        flat = bars_from(np.full(100, 50.0), np.full(100, 500.0), np.full(100, 50.5), np.full(100, 49.5))
        res = scan({"FLAT": flat}, default_registry().active(), "1d")
        self.assertEqual(res.signals, ())
        self.assertTrue(all(isinstance(d, NoSignal) for d in res.decisions))


if __name__ == "__main__":
    unittest.main()
