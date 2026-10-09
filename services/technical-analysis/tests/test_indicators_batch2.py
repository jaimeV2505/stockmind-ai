import math
import unittest

import numpy as np
import pandas as pd

from stockmind_ta import (
    adx, cci, historical_volatility, keltner, mfi, rsi, stoch_rsi, swing_points, vwap, atr, ema,
)


def ohlc(n=300, seed=3):
    rng = np.random.default_rng(seed)
    close = pd.Series(100 + rng.normal(0, 1, n).cumsum())
    high = close + rng.uniform(0.1, 1.0, n)
    low = close - rng.uniform(0.1, 1.0, n)
    vol = pd.Series(rng.uniform(1e5, 2e5, n))
    return high, low, close, vol


def ref_adx_wilder_original(h, l, c, n=14):
    """Wilder's original running-SUM formulation, plain Python (independent of the library's mean-seed form)."""
    h, l, c = list(h), list(l), list(c)
    tr, pdm, mdm = [], [], []
    for i in range(1, len(h)):
        tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        up, dn = h[i] - h[i - 1], l[i - 1] - l[i]
        pdm.append(up if (up > dn and up > 0) else 0.0)
        mdm.append(dn if (dn > up and dn > 0) else 0.0)
    s_tr, s_p, s_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dx = []

    def push():
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx.append(0.0 if pdi + mdi == 0 else 100 * abs(pdi - mdi) / (pdi + mdi))
        return pdi, mdi
    last = push()
    for i in range(n, len(tr)):
        s_tr = s_tr - s_tr / n + tr[i]
        s_p = s_p - s_p / n + pdm[i]
        s_m = s_m - s_m / n + mdm[i]
        last = push()
    adx_v = [sum(dx[:n]) / n]
    for x in dx[n:]:
        adx_v.append((adx_v[-1] * (n - 1) + x) / n)
    return last, adx_v


class TestADX(unittest.TestCase):
    def test_matches_wilder_original_formulation(self):
        h, l, c, _ = ohlc()
        out = adx(h, l, c, 14)
        (pdi_last, mdi_last), ref = ref_adx_wilder_original(h, l, c, 14)
        self.assertEqual(out["adx"].first_valid_index(), 2 * 14 - 1)
        np.testing.assert_allclose(out["adx"].dropna().to_numpy(), ref, atol=1e-9)
        self.assertAlmostEqual(out["plus_di"].iloc[-1], pdi_last, places=9)
        self.assertAlmostEqual(out["minus_di"].iloc[-1], mdi_last, places=9)

    def test_bounds_and_strong_trend(self):
        h, l, c, _ = ohlc()
        v = adx(h, l, c).dropna()
        self.assertTrue(((v["adx"] >= 0) & (v["adx"] <= 100)).all())
        x = pd.Series(np.arange(1.0, 120.0))           # relentless uptrend
        t = adx(x + 0.5, x - 0.5, x).iloc[-1]
        self.assertGreater(t["adx"], 90)
        self.assertGreater(t["plus_di"], t["minus_di"])

    def test_flat_market_no_division_error(self):
        f = pd.Series([10.0] * 80)
        out = adx(f + 1, f - 1, f)
        self.assertEqual(out["adx"].dropna().iloc[-1], 0.0)


class TestCCI(unittest.TestCase):
    def test_hand_value(self):
        # tp series 1..5, n=5: mean 3, MAD = (2+1+0+1+2)/5 = 1.2, CCI = (5-3)/(0.015*1.2)
        s = pd.Series([1.0, 2, 3, 4, 5])
        self.assertAlmostEqual(cci(s, s, s, 5).iloc[-1], 2 / (0.015 * 1.2), places=9)

    def test_flat_is_zero_and_warmup_nan(self):
        s = pd.Series([7.0] * 30)
        out = cci(s, s, s, 20)
        self.assertTrue(out.iloc[:19].isna().all())
        self.assertTrue((out.iloc[19:] == 0.0).all())


class TestKeltnerHV(unittest.TestCase):
    def test_keltner_composition(self):
        h, l, c, _ = ohlc()
        k = keltner(h, l, c, 20, 10, 2.0)
        np.testing.assert_allclose(k["upper"].dropna() - k["mid"].dropna().loc[k["upper"].dropna().index],
                                   2.0 * atr(h, l, c, 10).loc[k["upper"].dropna().index])
        self.assertTrue((k.dropna()["upper"] > k.dropna()["lower"]).all())

    def test_hv_constant_growth_is_zero(self):
        c = pd.Series(100 * 1.01 ** np.arange(60))
        self.assertAlmostEqual(historical_volatility(c, 20).iloc[-1], 0.0, places=9)

    def test_hv_hand_value(self):
        c = pd.Series([100.0, 101.0, 100.0, 102.0, 101.0])
        r = np.log(c / c.shift(1)).dropna().to_numpy()
        expected = r.std(ddof=1) * math.sqrt(252)
        self.assertAlmostEqual(historical_volatility(c, 4).iloc[-1], expected, places=12)

    def test_hv_rejects_n1(self):
        with self.assertRaises(ValueError):
            historical_volatility(pd.Series([1.0, 2.0]), 1)


class TestMFI(unittest.TestCase):
    def test_hand_value(self):
        # tp = close (h=l=c). flows: up bar vol 100@11 (+1100), down bar vol 50@10 (-500), up bar vol 200@12 (+2400)
        c = pd.Series([10.0, 11.0, 10.0, 12.0])
        v = pd.Series([1.0, 100.0, 50.0, 200.0])
        out = mfi(c, c, c, v, 3)
        self.assertAlmostEqual(out.iloc[-1], 100 - 100 / (1 + 3500 / 500), places=9)
        self.assertTrue(out.iloc[:3].isna().all())

    def test_extremes(self):
        up = pd.Series(np.arange(1.0, 40.0))
        self.assertEqual(mfi(up, up, up, pd.Series([10.0] * 39), 14).iloc[-1], 100.0)
        flat = pd.Series([5.0] * 40)
        self.assertEqual(mfi(flat, flat, flat, pd.Series([10.0] * 40), 14).iloc[-1], 50.0)


class TestStochRSI(unittest.TestCase):
    def test_range_and_definition(self):
        _, _, c, _ = ohlc()
        s = stoch_rsi(c).dropna()
        self.assertTrue(((s["raw"] >= -1e-9) & (s["raw"] <= 100 + 1e-9)).all())
        r = rsi(c, 14)
        i = len(c) - 1
        w = r.iloc[i - 13:i + 1]
        self.assertAlmostEqual(stoch_rsi(c)["raw"].iloc[i], 100 * (r.iloc[i] - w.min()) / (w.max() - w.min()))

    def test_undefined_when_rsi_constant(self):
        out = stoch_rsi(pd.Series(np.arange(1.0, 80.0)))   # RSI pinned at 100
        self.assertTrue(out["raw"].isna().all())


class TestVWAP(unittest.TestCase):
    def test_resets_each_session(self):
        h = l = c = pd.Series([10.0, 20.0, 30.0, 40.0])
        v = pd.Series([1.0, 3.0, 1.0, 1.0])
        sess = pd.Series(["a", "a", "b", "b"])
        out = vwap(h, l, c, v, sess)
        self.assertAlmostEqual(out.iloc[0], 10.0)
        self.assertAlmostEqual(out.iloc[1], (10 * 1 + 20 * 3) / 4)
        self.assertAlmostEqual(out.iloc[2], 30.0)                      # reset
        self.assertAlmostEqual(out.iloc[3], 35.0)

    def test_zero_volume_nan(self):
        s = pd.Series([5.0, 5.0])
        out = vwap(s, s, s, pd.Series([0.0, 2.0]), pd.Series(["a", "a"]))
        self.assertTrue(math.isnan(out.iloc[0]))
        self.assertAlmostEqual(out.iloc[1], 5.0)


class TestSwingPoints(unittest.TestCase):
    def test_pivot_emitted_at_confirmation_bar(self):
        high = pd.Series([1.0, 2, 5, 3, 2, 1, 2, 3, 4])
        low = pd.Series([0.5, 1.5, 4.5, 2.5, 1.5, 0.2, 1.5, 2.5, 3.5])
        sp = swing_points(high, low, k=2)
        self.assertEqual(sp["pivot_high"].dropna().to_dict(), {4: 5.0})      # pivot at bar 2, known at bar 4
        self.assertEqual(sp["pivot_high_bars_ago"].dropna().to_dict(), {4: 2.0})
        self.assertEqual(sp["pivot_low"].dropna().to_dict(), {7: 0.2})       # pivot at bar 5, known at bar 7
        self.assertTrue(sp["pivot_high"].iloc[:4].isna().all())             # nothing known earlier

    def test_ties_make_no_pivot(self):
        high = pd.Series([1.0, 3, 3, 1, 0, 0, 0])
        sp = swing_points(high, high - 0.1, k=1)
        self.assertEqual(len(sp["pivot_high"].dropna()), 0)


class TestBatch2NoLookahead(unittest.TestCase):
    """Truncate at MANY cut points: sparse signals (pivots) can hide look-ahead at any single cut."""

    @staticmethod
    def _compute(h, l, c, v, sess, sl):
        hh, ll, cc, vv, ss = h[sl], l[sl], c[sl], v[sl], sess[sl]
        out = {"cci": cci(hh, ll, cc), "hv": historical_volatility(cc), "mfi": mfi(hh, ll, cc, vv),
               "vwap": vwap(hh, ll, cc, vv, ss)}
        for name, df in (("adx", adx(hh, ll, cc)), ("kc", keltner(hh, ll, cc)),
                         ("srsi", stoch_rsi(cc)), ("swing", swing_points(hh, ll, 2))):
            for col in df.columns:
                out[f"{name}_{col}"] = df[col]
        return out

    def test_causal_at_many_cuts(self):
        h, l, c, v = ohlc(320, seed=11)
        sess = pd.Series(np.arange(len(c)) // 20)
        full = self._compute(h, l, c, v, sess, slice(None))
        n_pivots = int(full["swing_pivot_high"].notna().sum() + full["swing_pivot_low"].notna().sum())
        self.assertGreater(n_pivots, 20)   # the data must actually exercise the sparse signal
        for cut in range(100, 320, 3):
            part = self._compute(h, l, c, v, sess, slice(0, cut))
            for name, s in part.items():
                np.testing.assert_allclose(full[name].iloc[:cut].to_numpy(), s.to_numpy(),
                                           equal_nan=True, err_msg=f"{name} @cut={cut}")


if __name__ == "__main__":
    unittest.main()
