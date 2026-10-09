import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from stockmind_alerts import AlertRule, Channel, Kind, evaluate, trigger_from_signal
from stockmind_signals import Evidence, new_signal
from stockmind_ta import rsi

UTC = timezone.utc


def bars_from(close, volume=None):
    c = np.asarray(close, float)
    v = np.full(len(c), 1000.0) if volume is None else np.asarray(volume, float)
    return pd.DataFrame({"open": c, "high": c, "low": c, "close": c, "volume": v},
                        index=pd.date_range("2026-01-02", periods=len(c), freq="D", tz="UTC"))


def rule(kind=Kind.PRICE_CROSS, **kw):
    base = dict(id="r1", user_id="u1", symbol="NVDA", kind=kind, channels=(Channel.IN_APP,), direction="above", threshold=100.0)
    base.update(kw)
    return AlertRule(**base)


class TestRuleValidation(unittest.TestCase):
    def test_rejects_bad_rules(self):
        for kw in (dict(threshold=0), dict(threshold=float("nan")), dict(threshold=None), dict(symbol="nvda"),
                   dict(direction="sideways"), dict(channels=()), dict(channels=(Channel.EMAIL, Channel.EMAIL)),
                   dict(cooldown=timedelta(seconds=-1)), dict(id=""), dict(kind=Kind.RSI_THRESHOLD, threshold=100.0)):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                rule(**kw)

    def test_signal_rule_needs_no_threshold(self):
        self.assertEqual(rule(Kind.SIGNAL, threshold=None).kind, Kind.SIGNAL)


class TestPriceCross(unittest.TestCase):
    def test_edge_triggered_above(self):
        self.assertIsNotNone(evaluate(rule(), bars_from([98, 99, 101])))
        self.assertIsNone(evaluate(rule(), bars_from([101, 102, 103])))      # already above: no repeat alert
        self.assertIsNone(evaluate(rule(), bars_from([97, 98, 99])))         # not reached
        self.assertIsNotNone(evaluate(rule(), bars_from([99, 100.0])))       # touching the level counts (prev < thr <= cur)

    def test_edge_triggered_below(self):
        r = rule(direction="below")
        self.assertIsNotNone(evaluate(r, bars_from([102, 100.0])))           # prev > thr >= cur
        self.assertIsNone(evaluate(r, bars_from([99, 98])))

    def test_reason_and_evidence_explain_the_alert(self):
        t = evaluate(rule(), bars_from([98, 99, 101]))
        self.assertIn("crossed above 100.00", t.reason)
        self.assertIn("101.00", t.reason)
        self.assertEqual(dict(t.evidence)["previous_close"], 99.0)
        self.assertEqual(t.bar_ts, pd.Timestamp("2026-01-04", tz="UTC"))
        self.assertEqual(t.event_key, "r1:2026-01-04T00:00:00+00:00")

    def test_disabled_missing_or_nan_never_fires(self):
        self.assertIsNone(evaluate(rule(enabled=False), bars_from([98, 101])))
        self.assertIsNone(evaluate(rule(), bars_from([101])))
        self.assertIsNone(evaluate(rule(), bars_from([98, np.nan])))
        self.assertIsNone(evaluate(rule(), bars_from([np.nan, 101])))
        self.assertIsNone(evaluate(rule(), bars_from([98, np.inf])))         # bad data must never look like a crossing
        self.assertIsNone(evaluate(rule(direction="below"), bars_from([102, -np.inf])))

    def test_naive_index_rejected(self):
        b = bars_from([98, 101])
        b.index = b.index.tz_localize(None)
        with self.assertRaises(ValueError):
            evaluate(rule(), b)


class TestRSIAndVolume(unittest.TestCase):
    def setUp(self):
        self.close = np.r_[np.linspace(100, 70, 25), np.linspace(70, 78, 6)]
        self.bars = bars_from(self.close)
        r = rsi(self.bars["close"], 14)
        self.prev, self.cur = float(r.iloc[-2]), float(r.iloc[-1])

    def test_rsi_cross_up_only_when_threshold_between_prev_and_cur(self):
        mid = round((self.prev + self.cur) / 2, 4)
        self.assertGreater(self.cur, self.prev)
        self.assertIsNotNone(evaluate(rule(Kind.RSI_THRESHOLD, threshold=mid), self.bars))
        self.assertIsNone(evaluate(rule(Kind.RSI_THRESHOLD, threshold=self.cur + 5), self.bars))
        self.assertIsNone(evaluate(rule(Kind.RSI_THRESHOLD, threshold=max(self.prev - 5, 1)), self.bars))  # already above

    def test_rsi_needs_history(self):
        self.assertIsNone(evaluate(rule(Kind.RSI_THRESHOLD, threshold=50), self.bars.iloc[:10]))

    def test_volume_spike(self):
        vol = np.r_[np.full(25, 1000.0), 3000.0]
        b = bars_from(np.full(26, 50.0), vol)
        t = evaluate(rule(Kind.VOLUME_SPIKE, threshold=2.5), b)
        self.assertIsNotNone(t)
        self.assertEqual(dict(t.evidence)["relative_volume"], 3.0)
        self.assertIsNone(evaluate(rule(Kind.VOLUME_SPIKE, threshold=3.5), b))
        self.assertIsNone(evaluate(rule(Kind.VOLUME_SPIKE, threshold=2.5), b.iloc[:15]))


class TestSignalRule(unittest.TestCase):
    def sig(self, **kw):
        base = dict(symbol="NVDA", strategy_id="bullish_breakout", strategy_version="1.0.0+abc", timeframe="1d",
                    trigger_ts=datetime(2026, 10, 9, 20, tzinfo=UTC), supporting=(Evidence("close", 101.0),))
        base.update(kw)
        return new_signal(**base)

    def test_matching_and_filters(self):
        r = rule(Kind.SIGNAL, threshold=None)
        t = trigger_from_signal(r, self.sig())
        self.assertIsNotNone(t)
        self.assertIn("bullish_breakout", t.reason)
        self.assertIsNone(trigger_from_signal(r, self.sig(symbol="AMD")))
        self.assertIsNone(trigger_from_signal(rule(Kind.SIGNAL, threshold=None, strategy_id="ma_crossover"), self.sig()))
        self.assertIsNotNone(trigger_from_signal(rule(Kind.SIGNAL, threshold=None, strategy_id="bullish_breakout"), self.sig()))
        self.assertIsNone(trigger_from_signal(rule(Kind.SIGNAL, threshold=None, enabled=False), self.sig()))
        self.assertIsNone(trigger_from_signal(rule(), self.sig()))           # wrong rule kind


if __name__ == "__main__":
    unittest.main()
