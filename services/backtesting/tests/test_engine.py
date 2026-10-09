import unittest
from dataclasses import replace

import numpy as np
import pandas as pd

from stockmind_backtest import BacktestConfig, run_backtest


def bars_from(opens, closes, highs=None, lows=None, start="2020-01-01"):
    o, c = np.array(opens, float), np.array(closes, float)
    h = np.array(highs, float) if highs is not None else np.maximum(o, c) + 0.5
    l = np.array(lows, float) if lows is not None else np.minimum(o, c) - 0.5
    idx = pd.date_range(start, periods=len(o), freq="D", tz="UTC")
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c}, index=idx)


def flags(n, *true_at):
    s = np.zeros(n, dtype=bool)
    s[list(true_at)] = True
    return s


def F(df, *at):
    return pd.Series(flags(len(df), *at), index=df.index)


def cfg(**kw):
    base = dict(price_adjustment="split_adjusted", initial_capital=1000.0, slippage_bps=0.0)
    base.update(kw)
    return BacktestConfig(**base)


OPENS = [10, 11, 12, 13, 14, 15]
CLOSES = [10.5, 11.5, 12.5, 13.5, 14.5, 15.5]


class TestExecutionTiming(unittest.TestCase):
    def test_signal_executes_at_next_open_hand_computed(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 1), F(b, 3), cfg())
        (t,) = r.trades
        self.assertEqual((t.entry_idx, t.exit_idx, t.exit_reason), (2, 4, "signal"))   # signal@1 -> open@2; exit@3 -> open@4
        self.assertEqual((t.entry_price, t.exit_price, t.shares), (12.0, 14.0, 83))     # floor(1000/12)=83
        self.assertAlmostEqual(t.pnl, 166.0)                                            # (14-12)*83
        self.assertAlmostEqual(r.equity.iloc[-1], 1166.0)
        self.assertAlmostEqual(r.equity.iloc[1], 1000.0)                                # nothing held before the fill bar

    def test_costs_and_slippage_hand_computed(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 1), F(b, 3), cfg(slippage_bps=100, commission_per_trade=1.0))
        (t,) = r.trades
        self.assertAlmostEqual(t.entry_price, 12.12)          # 12 * 1.01
        self.assertAlmostEqual(t.exit_price, 13.86)           # 14 * 0.99
        self.assertEqual(t.shares, 82)                        # floor((1000-1)/12.12)
        self.assertAlmostEqual(t.costs, 2.0)
        self.assertAlmostEqual(t.pnl, (13.86 - 12.12) * 82 - 2.0)
        self.assertAlmostEqual(r.equity.iloc[-1], 1000.0 + t.pnl)

    def test_last_bar_signal_ignored(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 5), None, cfg())
        self.assertEqual(len(r.trades), 0)
        self.assertTrue(any("last bar" in w for w in r.warnings))

    def test_end_of_data_close(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 1), None, cfg(slippage_bps=50))
        (t,) = r.trades
        self.assertEqual((t.exit_reason, t.exit_idx), ("end_of_data", 5))
        self.assertAlmostEqual(t.exit_price, 15.5 * (1 - 0.005))
        self.assertAlmostEqual(r.equity.iloc[-1], 1000.0 + t.pnl)

    def test_entries_ignored_while_in_position(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 0, 1, 2), None, cfg())
        self.assertEqual(len(r.trades), 1)
        self.assertEqual(r.trades[0].entry_idx, 1)

    def test_no_flip_when_exit_and_entry_coincide(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 0, 2), F(b, 2), cfg())
        (t,) = r.trades                                   # entered at 1, exit flag@2 -> exits at open 3, entry flag dropped
        self.assertEqual((t.entry_idx, t.exit_idx, t.exit_reason), (1, 3, "signal"))
        self.assertEqual(r.equity.iloc[3], r.equity.iloc[5])  # flat afterwards

    def test_unaffordable_entry_skipped_with_warning(self):
        b = bars_from(OPENS, CLOSES)
        r = run_backtest(b, F(b, 1), None, cfg(initial_capital=5.0))
        self.assertEqual(len(r.trades), 0)
        self.assertTrue(any("skipped" in w for w in r.warnings))


class TestStops(unittest.TestCase):
    def setUp(self):
        self.o = [10, 11, 12, 12.5, 13, 13]
        self.c = [10.5, 11.5, 12.5, 12.0, 13, 13]

    def test_intrabar_stop_fills_at_stop(self):
        b = bars_from(self.o, self.c, lows=[9.5, 10.5, 11.5, 10.0, 12.5, 12.5])
        r = run_backtest(b, F(b, 1), None, cfg(stop_loss_fraction=0.10))   # entry 12 -> stop 10.8
        (t,) = r.trades
        self.assertEqual((t.exit_reason, t.exit_idx), ("stop", 3))
        self.assertAlmostEqual(t.exit_price, 10.8)

    def test_gap_through_stop_fills_at_open(self):
        o = [10, 11, 12, 10.0, 13, 13]
        b = bars_from(o, [10.5, 11.5, 12.5, 10.2, 13, 13], lows=[9.5, 10.5, 11.5, 9.5, 12.5, 12.5])
        r = run_backtest(b, F(b, 1), None, cfg(stop_loss_fraction=0.10))
        self.assertAlmostEqual(r.trades[0].exit_price, 10.0)   # worse than the 10.8 stop

    def test_stop_hit_on_entry_bar(self):
        b = bars_from(self.o, self.c, lows=[9.5, 10.5, 10.0, 11.5, 12.5, 12.5])
        r = run_backtest(b, F(b, 1), None, cfg(stop_loss_fraction=0.10))
        (t,) = r.trades
        self.assertEqual((t.entry_idx, t.exit_idx, t.exit_reason), (2, 2, "stop"))
        self.assertAlmostEqual(t.exit_price, 10.8)

    def test_stop_slippage_applies(self):
        b = bars_from(self.o, self.c, lows=[9.5, 10.5, 11.5, 10.0, 12.5, 12.5])
        r = run_backtest(b, F(b, 1), None, cfg(stop_loss_fraction=0.10, slippage_bps=100))
        # entry fill 12*1.01 = 12.12 -> stop 12.12*0.9 = 10.908 -> stop fill 10.908*0.99 = 10.79892
        self.assertAlmostEqual(r.trades[0].entry_price, 12.12)
        self.assertAlmostEqual(r.trades[0].exit_price, 10.79892)


class TestMetrics(unittest.TestCase):
    def test_drawdown_and_equity_path_hand_computed(self):
        o = [100, 100, 100, 100]
        c = [100, 80, 50, 90]
        b = bars_from(o, c, highs=[101] * 4, lows=[49] * 4)
        r = run_backtest(b, F(b, 0), None, cfg())      # 10 shares @100
        np.testing.assert_allclose(r.equity.to_numpy(), [1000, 800, 500, 900])
        self.assertAlmostEqual(r.metrics["max_drawdown"], -0.5)
        self.assertAlmostEqual(r.metrics["total_return"], -0.1)
        self.assertAlmostEqual(r.metrics["buy_hold_return"], -0.1)

    def test_profit_factor_and_expectancy(self):
        o = [10, 10, 12, 12, 9, 9, 9, 9]
        b = bars_from(o, o, highs=[13] * 8, lows=[8] * 8)
        r = run_backtest(b, F(b, 0, 3), F(b, 1, 5), cfg(initial_capital=1000))
        # trade1: buy@10 (100 sh) sell@12 => +200 ; trade2: cash 1200, buy@12? (flag@3 -> open@4=9) sell@9 => 0
        self.assertEqual(len(r.trades), 2)
        self.assertEqual(r.metrics["win_rate"], 0.5)
        self.assertIsNone(r.metrics["profit_factor"])       # no losing trade -> undefined, never inf
        self.assertAlmostEqual(r.metrics["expectancy"], 100.0)

    def test_undefined_metrics_are_none(self):
        b = bars_from(OPENS, CLOSES)
        m = run_backtest(b, F(b, 1), F(b, 3), cfg()).metrics
        self.assertIsNone(m["sharpe"])      # < 30 bars
        self.assertIsNone(m["cagr"])        # < 1 year
        self.assertTrue(m["simulated"])

    def test_every_result_labelled_simulated(self):
        b = bars_from(OPENS, CLOSES)
        self.assertTrue(run_backtest(b, F(b, 1), None, cfg()).simulated)


def random_market(n=300, seed=5):
    rng = np.random.default_rng(seed)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.015, n)))
    o = np.r_[c[0], c[:-1]] * (1 + rng.normal(0, 0.003, n))
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.004, n)))
    l = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.004, n)))
    return bars_from(o, c, h, l)


class TestInvariants(unittest.TestCase):
    def test_accounting_identity_sum_of_pnl_equals_equity_change(self):
        rng = np.random.default_rng(1)
        for seed in range(5):
            b = random_market(seed=seed)
            en = pd.Series(rng.random(len(b)) < 0.08, index=b.index)
            ex = pd.Series(rng.random(len(b)) < 0.08, index=b.index)
            r = run_backtest(b, en, ex, BacktestConfig("split_adjusted", 50_000, 0.9, 1.0, 5.0, 7.0, 0.04))
            self.assertTrue(len(r.trades) > 0)
            self.assertAlmostEqual(sum(t.pnl for t in r.trades), r.equity.iloc[-1] - 50_000, places=6)
            self.assertGreaterEqual(r.equity.min(), 0)

    def test_reproducible_and_hash_sensitivity(self):
        b = random_market()
        rng = np.random.default_rng(2)
        en = pd.Series(rng.random(len(b)) < 0.1, index=b.index)
        c = BacktestConfig("split_adjusted")
        r1, r2 = run_backtest(b, en, None, c), run_backtest(b.copy(), en.copy(), None, c)
        self.assertEqual(r1.config_hash, r2.config_hash)
        pd.testing.assert_series_equal(r1.equity, r2.equity)
        self.assertEqual(r1.trades, r2.trades)
        b2 = b.copy()
        b2.iloc[100, b2.columns.get_loc("close")] *= 1.0001
        self.assertNotEqual(r1.config_hash, run_backtest(b2, en, None, c).config_hash)
        self.assertNotEqual(r1.config_hash, run_backtest(b, en, None, replace(c, slippage_bps=6.0)).config_hash)
        en2 = en.copy()
        en2.iloc[50] = not en2.iloc[50]
        self.assertNotEqual(r1.config_hash, run_backtest(b, en2, None, c).config_hash)

    def test_future_bars_cannot_change_the_past(self):
        """Truncating the data must not change anything that happened strictly before the cut."""
        b = random_market(260, seed=9)
        rng = np.random.default_rng(3)
        en = pd.Series(rng.random(len(b)) < 0.1, index=b.index)
        ex = pd.Series(rng.random(len(b)) < 0.1, index=b.index)
        c = BacktestConfig("split_adjusted", 100_000, 1.0, 1.0, 5.0, 5.0, 0.05)
        full = run_backtest(b, en, ex, c)
        for cut in range(40, 260, 11):
            part = run_backtest(b.iloc[:cut], en.iloc[:cut], ex.iloc[:cut], c)
            np.testing.assert_allclose(full.equity.iloc[:cut - 1].to_numpy(), part.equity.iloc[:cut - 1].to_numpy(),
                                       err_msg=f"equity @cut={cut}")
            sig = lambda r: [(t.entry_idx, t.exit_idx, t.exit_reason, round(t.pnl, 9)) for t in r.trades if t.exit_idx < cut - 1]
            self.assertEqual(sig(full), sig(part), f"trades @cut={cut}")


class TestInputValidation(unittest.TestCase):
    def setUp(self):
        self.b = bars_from(OPENS, CLOSES)

    def run_(self, bars=None, en=None, ex=None, config="default"):
        bars = self.b if bars is None else bars
        en = F(bars, 1) if en is None else en
        c = cfg() if config == "default" else config
        return run_backtest(bars, en, ex, c)

    def test_bad_data_rejected(self):
        bad_nan = self.b.copy(); bad_nan.iloc[2, 3] = np.nan
        bad_zero = self.b.copy(); bad_zero.iloc[2, 0] = 0.0
        bad_hl = self.b.copy(); bad_hl.iloc[2, 1] = 1.0
        naive = self.b.copy(); naive.index = naive.index.tz_localize(None)
        unsorted = self.b.iloc[::-1]
        dup = self.b.copy(); dup.index = [dup.index[0]] * len(dup)
        for name, d in dict(nan=bad_nan, zero=bad_zero, hl=bad_hl, naive=naive, unsorted=unsorted, dup=dup).items():
            with self.subTest(name), self.assertRaises(ValueError):
                self.run_(bars=d, en=pd.Series(flags(len(d), 1), index=d.index))
        one = self.b.iloc[:1]
        with self.assertRaises(ValueError):
            self.run_(bars=one, en=pd.Series([False], index=one.index))

    def test_bad_flags_rejected(self):
        with self.assertRaises(ValueError):
            self.run_(en=pd.Series([0, 1, 0, 0, 0, 0], index=self.b.index))           # ints, not bool
        with self.assertRaises(ValueError):
            self.run_(en=pd.Series(flags(6, 1), index=self.b.index + pd.Timedelta(days=1)))  # misaligned
        with self.assertRaises(ValueError):
            self.run_(ex=pd.Series([True, False], index=self.b.index[:2]))

    def test_bad_config_rejected(self):
        for kw in (dict(initial_capital=0), dict(position_fraction=0), dict(position_fraction=1.1),
                   dict(slippage_bps=-1), dict(commission_bps=float("nan")), dict(stop_loss_fraction=1.0),
                   dict(stop_loss_fraction=0.0), dict(price_adjustment=" "), dict(periods_per_year=0)):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.run_(config=cfg(**kw))
        with self.assertRaises(ValueError):
            self.run_(config=None)


if __name__ == "__main__":
    unittest.main()
