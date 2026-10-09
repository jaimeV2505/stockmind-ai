import unittest

import numpy as np
import pandas as pd

from stockmind_patterns import DISCLAIMER, Match, PatternIndex, dtw_distance, shape_of, summarize


def make_bars(close, start="2020-01-01", spread=0.004, volume=None):
    c = np.asarray(close, float)
    o = np.r_[c[0], c[:-1]]
    idx = pd.date_range(start, periods=len(c), freq="D", tz="UTC")
    v = np.full(len(c), 1e6) if volume is None else volume
    return pd.DataFrame({"open": o, "high": np.maximum(o, c) * (1 + spread), "low": np.minimum(o, c) * (1 - spread),
                         "close": c, "volume": v}, index=idx)


def walk(n, seed, vol=0.012):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0.0002, vol, n)))


def universe(n=420, symbols=("AAA", "BBB", "CCC", "DDD"), seed0=0):
    return {s: make_bars(walk(n, seed0 + i)) for i, s in enumerate(symbols)}


class TestShape(unittest.TestCase):
    def test_scale_and_vol_invariance(self):
        c = walk(40, 1)
        s1 = shape_of(c)
        np.testing.assert_allclose(s1, shape_of(c * 7.3))                            # price-scale invariant
        lc = np.log(c)
        stretched = np.exp(lc[0] + 2.5 * (lc - lc[0]))                               # all log moves x2.5
        np.testing.assert_allclose(s1, shape_of(stretched), atol=1e-9)              # volatility-normalised
        self.assertEqual(s1[0], 0.0)

    def test_flat_window_is_none_and_garbage_rejected(self):
        self.assertIsNone(shape_of([100.0] * 10))
        for bad in ([100, np.nan, 101], [100, 0, 101], [1, 2], [[1, 2, 3]]):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                shape_of(bad)

    def test_volume_component(self):
        c, v = walk(20, 2), np.linspace(1e5, 1e6, 20)
        self.assertEqual(len(shape_of(c, v, 0.5)), 40)
        with self.assertRaises(ValueError):
            shape_of(c, None, 0.5)


class TestDTW(unittest.TestCase):
    def test_identity_symmetry_and_time_warp_invariance(self):
        a = np.sin(np.linspace(0, 6, 30))
        self.assertEqual(dtw_distance(a, a), 0.0)
        b = np.cos(np.linspace(0, 6, 25))
        self.assertAlmostEqual(dtw_distance(a, b), dtw_distance(b, a))
        self.assertEqual(dtw_distance([0, 1, 2], [0, 1, 1, 2]), 0.0)                # pure time-stretch costs nothing

    def test_never_worse_than_lockstep_l1(self):
        rng = np.random.default_rng(0)
        for _ in range(20):
            a, b = rng.normal(size=25), rng.normal(size=25)
            self.assertLessEqual(dtw_distance(a, b) * 50, np.abs(a - b).sum() + 1e-9)

    def test_band_behaviour(self):
        a, b = np.sin(np.linspace(0, 6, 30)), np.sin(np.linspace(0.8, 6.8, 30))
        self.assertGreaterEqual(dtw_distance(a, b, band=1), dtw_distance(a, b))     # tighter band cannot be cheaper
        with self.assertRaises(ValueError):
            dtw_distance([1, 2, 3], [1, 2, 3, 4, 5, 6], band=1)
        with self.assertRaises(ValueError):
            dtw_distance([], [1.0])

    def test_stretched_copy_closer_than_reversed(self):
        a = np.r_[np.linspace(0, 3, 15), np.linspace(3, 1, 15)]
        stretched = np.interp(np.linspace(0, 29, 24), np.arange(30), a)
        self.assertLess(dtw_distance(a, stretched), dtw_distance(a, a[::-1]))


class TestIndexOutcomes(unittest.TestCase):
    def test_forward_outcomes_hand_computed(self):
        close = np.array([100, 101, 103, 102, 104, 105, 107, 106, 110, 108, 112, 111, 115, 113, 118, 116, 120, 119, 125, 123.0])
        b = make_bars(close, spread=0.01)
        idx = PatternIndex(window=8, horizon=3)
        self.assertEqual(idx.add_symbol("X", b), len(close) - 3 - 8 + 1)             # only windows with a full horizon
        w = idx.windows("X")[0]                                                     # window ends at bar 7 (close 106)
        self.assertEqual((w.end_idx, w.start_ts, w.end_ts, w.outcome_end_ts),
                         (7, b.index[0], b.index[7], b.index[10]))
        self.assertAlmostEqual(w.forward_return, 112 / 106 - 1)                    # close[10] = 112
        self.assertAlmostEqual(w.mfe, 112 * 1.01 / 106 - 1)                        # bar-10 high = 112*1.01 (max over bars 8..10)
        self.assertAlmostEqual(w.mae, 106 * 0.99 / 106 - 1)                        # bar-8 low = min(106,110)*0.99
        self.assertIsNone(w.regime)                                                # < 50 bars of history

    def test_stride_and_validation(self):
        b = make_bars(walk(100, 3))
        self.assertLess(PatternIndex(10, 5, stride=5).add_symbol("S", b), PatternIndex(10, 5).add_symbol("S", b))
        idx = PatternIndex(10, 5)
        idx.add_symbol("S", b)
        with self.assertRaises(ValueError):
            idx.add_symbol("S", b)                                                  # duplicate symbol
        bad = b.copy()
        bad.iloc[5, 3] = np.nan
        with self.assertRaises(ValueError):
            PatternIndex(10, 5).add_symbol("N", bad)
        for kw in (dict(window=4), dict(horizon=0), dict(stride=0)):
            with self.assertRaises(ValueError):
                PatternIndex(**{"window": 10, "horizon": 5, **kw})


class TestLeakageRules(unittest.TestCase):
    WINDOW, HORIZON = 30, 10

    def build(self, data):
        idx = PatternIndex(self.WINDOW, self.HORIZON)
        for s, b in data.items():
            idx.add_symbol(s, b)
        return idx

    def test_outcomes_known_and_no_self_overlap(self):
        data = universe()
        idx = self.build(data)
        for t in (150, 250, 380):
            as_of = data["AAA"].index[t]
            q_start = data["AAA"].index[t - self.WINDOW + 1]
            ms = idx.query("AAA", data["AAA"], k=12, as_of=as_of, min_separation=1)
            self.assertTrue(ms)
            for m in ms:
                self.assertLessEqual(m.outcome_end, as_of, "outcome was not yet known at query time")
                if m.symbol == "AAA":
                    self.assertLess(m.outcome_end, q_start, "own-symbol match overlaps the query window")

    def test_future_data_cannot_change_the_answer(self):
        """Index + query built from data truncated at as_of must equal the full-data answer."""
        data = universe()
        for t in (160, 260, 340):
            as_of = data["AAA"].index[t]
            full = self.build(data).query("AAA", data["AAA"], k=8, as_of=as_of)
            cut = {s: b.loc[:as_of] for s, b in data.items()}
            trunc = self.build(cut).query("AAA", cut["AAA"], k=8)
            self.assertEqual(full, trunc, f"as_of index {t}: future data leaked into the result")
            self.assertEqual(summarize(full), summarize(trunc))

    def test_min_separation_enforced(self):
        data = universe()
        ms = self.build(data).query("AAA", data["AAA"], k=15, as_of=data["AAA"].index[380], min_separation=20)
        by = {}
        for m in ms:
            by.setdefault(m.symbol, []).append(m.end_idx)
        for sym, ends in by.items():
            ends.sort()
            self.assertTrue(all(b - a >= 20 for a, b in zip(ends, ends[1:])), f"{sym}: {ends}")

    def test_same_regime_filter_uses_causal_label(self):
        data = universe()
        as_of = data["AAA"].index[300]
        ms = self.build(data).query("AAA", data["AAA"], k=10, as_of=as_of, same_regime=True)
        close = data["AAA"]["close"].loc[:as_of]
        q_regime = "up" if close.iloc[-1] > close.rolling(50).mean().iloc[-1] else "down"
        self.assertTrue(ms)
        self.assertTrue(all(m.regime == q_regime for m in ms))
        with self.assertRaises(ValueError):
            self.build(data).query("AAA", data["AAA"].iloc[:40], k=3, same_regime=True)

    def test_deterministic(self):
        data = universe()
        idx = self.build(data)
        a = idx.query("AAA", data["AAA"], k=6, as_of=data["AAA"].index[300])
        self.assertEqual(a, idx.query("AAA", data["AAA"], k=6, as_of=data["AAA"].index[300]))

    def test_query_validation(self):
        data = universe()
        idx = self.build(data)
        with self.assertRaises(ValueError):
            idx.query("AAA", data["AAA"].iloc[:20], k=3)                             # shorter than the window
        flat = make_bars(np.full(60, 100.0))
        with self.assertRaises(ValueError):
            idx.query("AAA", flat, k=3)                                              # no variation to normalise
        with self.assertRaises(ValueError):
            idx.query("AAA", data["AAA"], k=0)


class TestRecallOfPlantedPattern(unittest.TestCase):
    def test_planted_v_shape_is_found_in_another_symbol(self):
        n, W, H = 420, 30, 10
        v = np.r_[np.full(15, -0.010), np.full(15, 0.010)]                           # clean V over 30 bars
        fwd = np.full(H, 0.010)                                                      # followed by +10.5% over the horizon

        def series(seed, plant_end, with_forward):
            rng = np.random.default_rng(seed)
            r = rng.normal(0.0002, 0.012, n)
            r[plant_end - W + 1:plant_end + 1] = v + rng.normal(0, 0.0015, W)
            if with_forward:
                r[plant_end + 1:plant_end + 1 + H] = fwd
            return make_bars(100 * np.exp(np.cumsum(r)))

        data = {"AAA": make_bars(walk(n, 21)), "CCC": make_bars(walk(n, 22)),
                "BBB": series(5, 229, True), "QQQ": series(6, 359, False)}
        idx = PatternIndex(W, H)
        for s, b in data.items():
            idx.add_symbol(s, b)
        qbars = data["QQQ"].iloc[:360]                                               # as_of = end of the planted V
        ms = idx.query("QQQ", qbars, k=3)
        best = ms[0]
        self.assertEqual(best.symbol, "BBB")
        self.assertLessEqual(abs(best.end_idx - 229), 2)
        self.assertGreater(best.similarity, ms[-1].similarity - 1e-12)
        self.assertGreater(best.forward_return, 0.08)                                # its known forward outcome (+~10%)


class TestSummarize(unittest.TestCase):
    @staticmethod
    def fm(fr, mfe=0.05, mae=-0.03, sym="X", end=0):
        t = pd.Timestamp("2020-01-01", tz="UTC")
        return Match(sym, end, t, t, t, 0.5, 0.67, fr, mfe, mae, None)

    def test_hand_computed_small_sample(self):
        s = summarize([self.fm(f) for f in (-0.02, 0.01, 0.03, 0.05)])
        self.assertEqual(s["n"], 4)
        self.assertAlmostEqual(s["median_forward_return"], 0.02)
        self.assertAlmostEqual(s["mean_forward_return"], 0.0175)
        self.assertEqual(s["share_positive"], 0.75)
        self.assertIsNone(s["ci_median_95"])                                         # n < 30: no CI
        text = " ".join(s["notes"])
        self.assertIn(DISCLAIMER, s["notes"])
        self.assertIn("very small sample", text)
        self.assertIn("no confidence interval", text)
        self.assertNotIn("probability_of_success", s)

    def test_no_matches_is_insufficient_evidence(self):
        s = summarize([])
        self.assertEqual(s["n"], 0)
        self.assertTrue(any("INSUFFICIENT EVIDENCE" in n for n in s["notes"]))

    def test_ci_only_with_enough_samples_and_is_seeded(self):
        rng = np.random.default_rng(0)
        ms = [self.fm(float(x)) for x in rng.normal(0.01, 0.05, 40)]
        a, b = summarize(ms, seed=3), summarize(ms, seed=3)
        self.assertEqual(a["ci_median_95"], b["ci_median_95"])
        lo, hi = a["ci_median_95"]
        self.assertLessEqual(lo, a["median_forward_return"] + 1e-9)
        self.assertGreaterEqual(hi, a["median_forward_return"] - 1e-9)
        self.assertEqual(a["worst_mae"], -0.03)


if __name__ == "__main__":
    unittest.main()
