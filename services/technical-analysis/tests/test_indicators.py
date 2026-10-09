import math
import unittest

import numpy as np
import pandas as pd

from stockmind_ta import atr, bollinger, ema, macd, obv, relative_volume, roc, rsi, sma, true_range

# Sample closes modelled on the widely circulated Wilder RSI(14) worked example.
# CAUTION: SC_RSI was typed from memory (no network when written) and is NOT a verified reference.
# It differs from our output by <= 0.07, systematically, which is consistent with the original
# spreadsheet using unrounded closes. It is used only as a loose sanity check (tolerance 0.1).
# Authoritative validation = independent implementation below + TA-Lib cross-check in CI (see next-tasks).
SC_CLOSE = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
            45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45,
            45.78, 45.35, 44.03, 44.18, 44.22, 44.57, 43.42, 42.66, 43.13]
SC_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42,
          39.99, 41.46, 41.87, 45.46, 37.30, 33.08, 37.77]


class TestMovingAverages(unittest.TestCase):
    def test_sma_known(self):
        out = sma(pd.Series([1.0, 2, 3, 4, 5]), 3)
        self.assertTrue(out.iloc[:2].isna().all())
        self.assertEqual(out.iloc[2:].tolist(), [2.0, 3.0, 4.0])

    def test_ema_seed_and_recursion(self):
        out = ema(pd.Series(np.arange(1.0, 11.0)), 3)
        self.assertTrue(out.iloc[:2].isna().all())
        self.assertAlmostEqual(out.iloc[2], 2.0)        # SMA seed
        self.assertAlmostEqual(out.iloc[3], 3.0)        # 4*.5 + 2*.5
        self.assertAlmostEqual(out.iloc[9], 9.0)        # linear ramp lags by 1

    def test_invalid_period(self):
        with self.assertRaises(ValueError):
            sma(pd.Series([1.0]), 0)


class TestRSI(unittest.TestCase):
    @staticmethod
    def _pure_python_wilder_rsi(c, n=14):
        """Independent reference: plain Python, no pandas, written separately from the library code."""
        d = [c[i] - c[i - 1] for i in range(1, len(c))]
        g = [max(x, 0.0) for x in d]
        l = [max(-x, 0.0) for x in d]
        ag, al = sum(g[:n]) / n, sum(l[:n]) / n
        out = [100 - 100 / (1 + ag / al)]
        for i in range(n, len(d)):
            ag = (ag * (n - 1) + g[i]) / n
            al = (al * (n - 1) + l[i]) / n
            out.append(100 - 100 / (1 + ag / al))
        return out

    def test_matches_independent_wilder_implementation(self):
        out = rsi(pd.Series(SC_CLOSE), 14)
        self.assertTrue(out.iloc[:14].isna().all())
        ref = self._pure_python_wilder_rsi(SC_CLOSE)
        np.testing.assert_allclose(out.iloc[14:].to_numpy(), ref, rtol=0, atol=1e-9)

    def test_first_value_hand_computed(self):
        # first 14 changes: avg gain = 0.2386, avg loss = 0.1 -> RS = 2.3857 -> RSI = 70.46
        first = rsi(pd.Series(SC_CLOSE), 14).iloc[14]
        d = np.diff(SC_CLOSE)[:14]
        rs = d.clip(min=0).mean() / (-d).clip(min=0).mean()
        self.assertAlmostEqual(first, 100 - 100 / (1 + rs), places=9)

    def test_loose_sanity_vs_recalled_published_values(self):
        got = rsi(pd.Series(SC_CLOSE), 14).iloc[14:].tolist()
        self.assertEqual(len(got), len(SC_RSI))
        for g, e in zip(got, SC_RSI):
            self.assertAlmostEqual(g, e, delta=0.1)

    def test_all_gains_is_100_and_flat_is_50(self):
        self.assertAlmostEqual(rsi(pd.Series(np.arange(1.0, 40.0)), 14).iloc[-1], 100.0)
        self.assertAlmostEqual(rsi(pd.Series([10.0] * 40), 14).iloc[-1], 50.0)

    def test_bounds(self):
        rng = np.random.default_rng(0)
        out = rsi(pd.Series(100 + rng.normal(0, 1, 500).cumsum()), 14).dropna()
        self.assertTrue(((out >= 0) & (out <= 100)).all())


class TestVolatility(unittest.TestCase):
    def test_true_range_first_bar_uses_high_low(self):
        h, l, c = pd.Series([10.0, 12.0]), pd.Series([8.0, 9.0]), pd.Series([9.0, 11.0])
        tr = true_range(h, l, c)
        self.assertEqual(tr.iloc[0], 2.0)
        self.assertEqual(tr.iloc[1], 3.0)  # max(3, |12-9|=3, |9-9|=0)

    def test_true_range_gap(self):
        h, l, c = pd.Series([10.0, 20.0]), pd.Series([9.0, 18.0]), pd.Series([10.0, 19.0])
        self.assertEqual(true_range(h, l, c).iloc[1], 10.0)  # |20-10|

    def test_atr_hand_computed(self):
        # constant TR of 2 -> ATR is 2 from index n-1 on
        h = pd.Series([11.0] * 10)
        l = pd.Series([9.0] * 10)
        c = pd.Series([10.0] * 10)
        out = atr(h, l, c, 5)
        self.assertTrue(out.iloc[:4].isna().all())
        self.assertTrue(np.allclose(out.iloc[4:], 2.0))

    def test_bollinger_known(self):
        out = bollinger(pd.Series(np.arange(1.0, 21.0)), 20, 2.0)
        sd = math.sqrt((20 ** 2 - 1) / 12)  # population std of 1..20
        self.assertAlmostEqual(out["mid"].iloc[-1], 10.5)
        self.assertAlmostEqual(out["upper"].iloc[-1], 10.5 + 2 * sd)
        self.assertAlmostEqual(out["lower"].iloc[-1], 10.5 - 2 * sd)

    def test_bollinger_constant_collapses(self):
        out = bollinger(pd.Series([5.0] * 30), 20).dropna()
        self.assertTrue((out["upper"] == out["lower"]).all())


class TestMomentumVolume(unittest.TestCase):
    def test_macd_structure(self):
        rng = np.random.default_rng(1)
        close = pd.Series(100 + rng.normal(0, 1, 200).cumsum())
        m = macd(close)
        self.assertEqual(m["macd"].first_valid_index(), 25)          # slow-1
        self.assertEqual(m["signal"].first_valid_index(), 33)        # slow-1 + signal-1
        v = m.dropna()
        self.assertTrue(np.allclose(v["hist"], v["macd"] - v["signal"]))

    def test_macd_rejects_bad_periods(self):
        with self.assertRaises(ValueError):
            macd(pd.Series([1.0] * 50), fast=26, slow=12)

    def test_roc(self):
        self.assertAlmostEqual(roc(pd.Series([100.0, 110.0, 121.0]), 1).iloc[-1], 10.0)

    def test_obv(self):
        c = pd.Series([10.0, 11.0, 10.5, 10.5, 12.0])
        v = pd.Series([100.0, 200.0, 150.0, 120.0, 300.0])
        self.assertEqual(obv(c, v).tolist(), [0.0, 200.0, 50.0, 50.0, 350.0])

    def test_relative_volume_excludes_current_bar(self):
        v = pd.Series([100.0] * 5 + [300.0])
        self.assertAlmostEqual(relative_volume(v, 5).iloc[-1], 3.0)


class TestNoLookahead(unittest.TestCase):
    """Value at bar t must be identical whether or not future bars exist."""

    def test_all_indicators_are_causal(self):
        rng = np.random.default_rng(7)
        n, cut = 300, 220
        close = pd.Series(100 + rng.normal(0, 1, n).cumsum())
        high, low = close + rng.uniform(0.1, 1, n), close - rng.uniform(0.1, 1, n)
        vol = pd.Series(rng.uniform(1e5, 2e5, n))

        def compute(sl):
            c, h, l, v = close[sl], high[sl], low[sl], vol[sl]
            return {
                "sma": sma(c, 20), "ema": ema(c, 20), "rsi": rsi(c), "atr": atr(h, l, c),
                "roc": roc(c), "obv": obv(c, v), "rvol": relative_volume(v),
                **{f"macd_{k}": s for k, s in macd(c).items()},
                **{f"bb_{k}": s for k, s in bollinger(c).items()},
            }

        full = compute(slice(None))
        for cut_at in range(60, n, 7):   # many cut points, not one (see batch-2 note on sparse signals)
            part = compute(slice(0, cut_at))
            for name, s in part.items():
                np.testing.assert_allclose(full[name].iloc[:cut_at].to_numpy(), s.to_numpy(),
                                           equal_nan=True, err_msg=f"{name} @cut={cut_at}")


if __name__ == "__main__":
    unittest.main()
