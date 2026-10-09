"""Regression tests for the session-3 audit findings (see docs/progress/audit-2026-10-09.md)."""
import unittest

import numpy as np
import pandas as pd

from stockmind_ta import adx, atr, ema, macd, obv, relative_volume, rsi, sma, vwap


class TestA06NaNNeverSilentlyDropped(unittest.TestCase):
    def test_obv_propagates_nan(self):
        close = pd.Series(np.arange(1.0, 21.0))
        close.iloc[10] = np.nan
        out = obv(close, pd.Series([10.0] * 20))
        self.assertTrue(out.iloc[:10].notna().all())
        self.assertTrue(out.iloc[10:].isna().all())     # fail closed: no clean-looking number after a gap

    def test_obv_unchanged_on_clean_data(self):
        c = pd.Series([10.0, 11.0, 10.5, 10.5, 12.0])
        v = pd.Series([100.0, 200.0, 150.0, 120.0, 300.0])
        self.assertEqual(obv(c, v).tolist(), [0.0, 200.0, 50.0, 50.0, 350.0])

    def test_vwap_nan_poisons_rest_of_session_only(self):
        n = 30
        x = pd.Series(np.arange(1.0, n + 1))
        vol = pd.Series([10.0] * n)
        vol.iloc[12] = np.nan
        sess = pd.Series([0] * 10 + [1] * 10 + [2] * 10)
        out = vwap(x, x, x, vol, sess)
        self.assertTrue(out.iloc[10:12].notna().all())   # session 1 before the bad bar: fine
        self.assertTrue(out.iloc[12:20].isna().all())    # rest of session 1: NaN, not a silently skewed number
        self.assertTrue(out.iloc[20:].notna().all())     # next session resets cleanly

    def test_vwap_rejects_missing_session_labels(self):
        s = pd.Series([1.0, 2.0])
        with self.assertRaises(ValueError):
            vwap(s, s, s, pd.Series([1.0, 1.0]), pd.Series([0.0, np.nan]))


class TestNaNContractForOtherIndicators(unittest.TestCase):
    """Documented contract: recursive indicators stay NaN after a NaN input (fail closed); rolling ones recover."""

    def setUp(self):
        self.x = pd.Series(np.arange(1.0, 61.0))
        self.x.iloc[20] = np.nan

    def test_recursive_stay_nan(self):
        for name, s in (("ema", ema(self.x, 5)), ("rsi", rsi(self.x, 5)),
                        ("macd", macd(self.x, 3, 6, 3)["macd"])):
            self.assertTrue(s.iloc[21:].isna().all(), name)
        h, l, c = self.x + 1, self.x - 1, self.x
        self.assertTrue(atr(h, l, c, 5).iloc[21:].isna().all())
        self.assertTrue(adx(h, l, c, 5)["adx"].iloc[21:].isna().all())

    def test_rolling_recover_after_window(self):
        out = sma(self.x, 5)
        self.assertTrue(out.iloc[20:25].isna().all())
        self.assertTrue(out.iloc[25:].notna().all())


class TestA08A13Misc(unittest.TestCase):
    def test_relative_volume_zero_baseline_is_nan_not_inf(self):
        out = relative_volume(pd.Series([0.0] * 25 + [5.0]), 20)
        self.assertTrue(np.isnan(out.iloc[-1]))
        self.assertFalse(np.isinf(out.dropna()).any())

    def test_numpy_integer_periods_accepted_bool_rejected(self):
        x = pd.Series(np.arange(1.0, 11.0))
        self.assertEqual(sma(x, np.int64(5)).iloc[-1], sma(x, 5).iloc[-1])
        with self.assertRaises(ValueError):
            sma(x, True)
        with self.assertRaises(ValueError):
            sma(x, 2.5)


if __name__ == "__main__":
    unittest.main()
