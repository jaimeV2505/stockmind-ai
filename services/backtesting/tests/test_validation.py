import unittest
from dataclasses import dataclass

import numpy as np
import pandas as pd

from stockmind_backtest import BacktestConfig, expand_grid, parameter_sensitivity, run_backtest, walk_forward


@dataclass(frozen=True)
class SMACross:
    """Test-local strategy (pure pandas, independent of stockmind_ta / stockmind_signals): fast SMA crosses slow SMA."""
    fast: int
    slow: int

    def flags(self, bars):
        f = bars["close"].rolling(self.fast).mean()
        s = bars["close"].rolling(self.slow).mean()
        up = ((f.shift(1) <= s.shift(1)) & (f > s)).astype(bool)
        dn = ((f.shift(1) >= s.shift(1)) & (f < s)).astype(bool)
        return up, dn


factory = lambda p: SMACross(**p)  # noqa: E731
GRID = {"fast": [2, 3, 5], "slow": [8, 12]}
CFG = BacktestConfig("split_adjusted", 100_000.0, 1.0, 0.0, 5.0, 5.0, None)


def market(n=400, seed=11):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0002, 0.012, n)) + 0.12 * np.sin(2 * np.pi * t / 22))
    o = np.r_[c[0], c[:-1]]
    h, l = np.maximum(o, c) * 1.004, np.minimum(o, c) * 0.996
    return pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "volume": 1e6},
                        index=pd.date_range("2022-01-03", periods=n, freq="D", tz="UTC"))


class TestGrid(unittest.TestCase):
    def test_expand_grid_deterministic_and_validated(self):
        g = expand_grid({"b": [1, 2], "a": [10, 20]})
        self.assertEqual(g[0], {"a": 10, "b": 1})
        self.assertEqual(len(g), 4)
        for bad in ({}, {"a": []}):
            with self.assertRaises(ValueError):
                expand_grid(bad)


class TestWalkForward(unittest.TestCase):
    def test_fold_geometry(self):
        b = market(100)
        r = walk_forward(b, factory, {"fast": [3], "slow": [10]}, CFG, train_bars=40, test_bars=20, min_train_trades=0)
        self.assertEqual([f.fold for f in r.folds], [0, 1, 2])
        for k, f in enumerate(r.folds):
            a = 20 * k
            self.assertEqual((f.train_start, f.train_end), (b.index[a], b.index[a + 39]))
            self.assertEqual((f.test_start, f.test_end), (b.index[a + 40], b.index[a + 59]))
            self.assertGreater(f.test_start, f.train_end)                      # strictly after training data
        starts = [f.test_start for f in r.folds]
        ends = [f.test_end for f in r.folds]
        self.assertTrue(all(ends[i] < starts[i + 1] for i in range(2)))      # test windows do not overlap

    def test_test_data_never_influences_selection(self):
        b = market(300)
        base = walk_forward(b, factory, GRID, CFG, 100, 40)
        self.assertTrue(all(f.skipped_reason is None for f in base.folds))
        reacted = []
        for k, f0 in enumerate(base.folds):
            poisoned = b.copy()
            win = (poisoned.index >= f0.test_start) & (poisoned.index <= f0.test_end)
            rng = np.random.default_rng(100 + k)
            poisoned.loc[win, "close"] = b.loc[win, "close"].to_numpy() * rng.uniform(0.6, 1.4, win.sum())
            poisoned.loc[win, "open"] = poisoned.loc[win, "close"].shift(1).fillna(poisoned.loc[win, "close"].iloc[0])
            poisoned.loc[win, "high"] = poisoned.loc[win, ["open", "close"]].max(axis=1) * 1.01
            poisoned.loc[win, "low"] = poisoned.loc[win, ["open", "close"]].min(axis=1) * 0.99
            f1 = walk_forward(poisoned, factory, GRID, CFG, 100, 40).folds[k]
            self.assertEqual(f1.selected_params, f0.selected_params, f"fold {k}: selection changed")
            self.assertEqual(f1.in_sample_score, f0.in_sample_score)
            reacted.append(f1.oos_total_return != f0.oos_total_return)
        self.assertTrue(any(reacted))     # the OOS numbers DO see the test data; only the selection must not

    def test_future_data_after_the_fold_cannot_change_it(self):
        b = market(300)
        full = walk_forward(b, factory, GRID, CFG, 100, 40)
        cut = full.folds[1].test_end
        trunc = walk_forward(b.loc[:cut], factory, GRID, CFG, 100, 40)
        for f_full, f_tr in zip(full.folds[:2], trunc.folds[:2]):
            self.assertEqual(f_full.selected_params, f_tr.selected_params)
            self.assertEqual(f_full.oos_total_return, f_tr.oos_total_return)

    def test_pooling_and_warnings(self):
        r = walk_forward(market(400), factory, GRID, CFG, 100, 40)
        p = r.pooled
        rets = [f.oos_total_return for f in r.folds if f.oos_result is not None]
        self.assertTrue(rets)
        self.assertAlmostEqual(p["oos_compounded_return"], float(np.prod([1 + x for x in rets]) - 1))
        self.assertEqual(p["oos_n_trades"], sum(f.oos_n_trades for f in r.folds))
        self.assertTrue(r.simulated and p["simulated"])
        self.assertTrue(any("selected in-sample from 6 candidates" in w for w in r.warnings))
        self.assertEqual(any("out-of-sample trades" in w for w in r.warnings), p["oos_n_trades"] < 30)

    def test_fold_is_skipped_and_reported_when_nothing_qualifies(self):
        r = walk_forward(market(200), factory, GRID, CFG, 60, 20, min_train_trades=10_000)
        self.assertTrue(all(f.skipped_reason == "no_eligible_params" for f in r.folds))
        self.assertEqual(r.pooled["n_folds_evaluated"], 0)
        self.assertIsNone(r.pooled["oos_compounded_return"])
        self.assertTrue(any("skipped" in w for w in r.warnings))

    def test_exact_ties_resolve_to_the_first_candidate_in_grid_order(self):
        ignore_dummy = lambda p: SMACross(p["fast"], p["slow"])  # noqa: E731  ("dummy" cannot change any result)
        r = walk_forward(market(300), ignore_dummy, {"dummy": [1, 2, 3], "fast": [3], "slow": [8]}, CFG, 100, 40)
        self.assertTrue(r.folds and all(f.skipped_reason is None for f in r.folds))
        self.assertEqual({f.selected_params["dummy"] for f in r.folds}, {1})

    def test_deterministic(self):
        a = walk_forward(market(), factory, GRID, CFG, 100, 40)
        b = walk_forward(market(), factory, GRID, CFG, 100, 40)
        self.assertEqual([f.selected_params for f in a.folds], [f.selected_params for f in b.folds])
        self.assertEqual(a.pooled, b.pooled)

    def test_oos_equals_a_direct_backtest_of_the_chosen_params(self):
        b = market(300)
        r = walk_forward(b, factory, GRID, CFG, 100, 40)
        f = r.folds[0]
        hist = b.loc[f.train_start:f.test_end]
        en, ex = SMACross(**f.selected_params).flags(hist)
        te = b.loc[f.test_start:f.test_end]
        direct = run_backtest(te, en.loc[te.index], ex.loc[te.index], CFG)
        self.assertEqual(direct.config_hash, f.oos_result.config_hash)
        self.assertEqual(direct.metrics["total_return"], f.oos_total_return)

    def test_argument_validation(self):
        b = market(100)
        for kw in (dict(train_bars=10, test_bars=20), dict(train_bars=40, test_bars=2), dict(train_bars=90, test_bars=20),
                   dict(train_bars=40, test_bars=20, step_bars=0), dict(train_bars=40, test_bars=20, objective="vibes")):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                walk_forward(b, factory, GRID, CFG, **kw)


class TestSensitivity(unittest.TestCase):
    def test_table_matches_direct_runs_and_is_labelled(self):
        b = market(400)
        s = parameter_sensitivity(b, factory, GRID, CFG)
        self.assertEqual(len(s.table), 6)
        row = s.table[(s.table.fast == 5) & (s.table.slow == 12)].iloc[0]
        en, ex = SMACross(5, 12).flags(b)
        direct = run_backtest(b, en, ex, CFG)
        self.assertAlmostEqual(row["total_return"], direct.metrics["total_return"])
        self.assertEqual(row["n_trades"], direct.metrics["n_trades"])
        m = s.summary
        self.assertTrue(m["worst"] <= m["median"] <= m["best"])
        self.assertTrue(s.simulated and m["simulated"])
        self.assertTrue(any("in-sample only" in w for w in s.warnings))

    def test_undefined_metric_cells_are_nan_not_zero(self):
        s = parameter_sensitivity(market(150), factory, {"fast": [3], "slow": [140]}, CFG, objective="profit_factor")
        self.assertTrue(s.table["profit_factor"].isna().all())
        self.assertIsNone(s.summary["best"])


if __name__ == "__main__":
    unittest.main()
