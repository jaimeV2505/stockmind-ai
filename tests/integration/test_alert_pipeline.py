"""End-to-end (pure logic): scan -> signal -> alert rule -> dispatcher -> delivery, with plan limits. SIMULATED bars."""
import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from stockmind_alerts import AlertRule, Channel, DeliveryStatus, Dispatcher, Kind, evaluate, trigger_from_signal
from stockmind_entitlements import Plan, Principal, check_quota
from stockmind_signals import BullishBreakout, SignalRegistry, scan

UTC = timezone.utc


def breakout_frame():
    n = 40
    close = np.full(n, 100.0)
    high = np.full(n, 101.0)
    vol = np.full(n, 1000.0)
    close[30], high[30], vol[30] = 105.0, 106.0, 3000.0
    idx = pd.date_range("2026-03-02", periods=31, freq="D", tz="UTC")
    return pd.DataFrame({"open": close[:31], "high": np.maximum(high[:31], close[:31]), "low": np.full(31, 99.0),
                         "close": close[:31], "volume": vol[:31]}, index=idx)


class TestAlertPipeline(unittest.TestCase):
    def test_signal_to_delivery_is_explained_and_idempotent_across_rescans(self):
        sent = []
        disp = Dispatcher({Channel.IN_APP: lambda d: sent.append(d)})
        rule = AlertRule("r-sig", "u1", "AAA", Kind.SIGNAL, (Channel.IN_APP,), strategy_id="bullish_breakout")
        registry = SignalRegistry()
        now = datetime(2026, 4, 5, 12, tzinfo=UTC)
        for rescan in range(3):                                              # a scheduler may run the same scan repeatedly
            res = scan({"AAA": breakout_frame()}, [BullishBreakout()], "1d", registry)
            for sig in res.signals:
                t = trigger_from_signal(rule, sig)
                if t:
                    disp.submit(rule, t, now + timedelta(minutes=rescan))
            disp.run_due(now + timedelta(minutes=rescan))
        self.assertEqual(len(registry), 1)
        self.assertEqual(len(sent), 1)                                       # one signal => exactly one notification
        self.assertEqual(disp.deliveries[sent[0].key].status, DeliveryStatus.SENT)
        self.assertIn("bullish_breakout", sent[0].reason)                    # the UI can show WHY
        self.assertTrue(any(name == "breakout_level" for name, _ in sent[0].evidence))
        self.assertEqual([r for _, r in disp.suppressed].count("duplicate_event"), 2)

    def test_plan_limit_gates_rule_creation_server_side(self):
        free = Principal("u1", Plan.FREE)
        active = []
        results = []
        for i in range(5):
            d = check_quota(free.plan, "active_alerts", len(active))
            results.append(d.allowed)
            if d.allowed:
                active.append(AlertRule(f"r{i}", free.user_id, "AAA", Kind.PRICE_CROSS, (Channel.IN_APP,), threshold=100.0 + i))
        self.assertEqual(results, [True, True, True, False, False])
        self.assertEqual(len(active), 3)
        self.assertTrue(check_quota(Plan.PRO, "active_alerts", 3).allowed)

    def test_price_rule_cooldown_across_two_crossings(self):
        sent = []
        disp = Dispatcher({Channel.EMAIL: lambda d: sent.append(d.key)})
        rule = AlertRule("r-px", "u1", "AAA", Kind.PRICE_CROSS, (Channel.EMAIL,), threshold=100.0, cooldown=timedelta(days=3))
        close = [98.0, 101.0, 99.0, 102.0]                                   # crosses above twice on consecutive days
        idx = pd.date_range("2026-03-02", periods=4, freq="D", tz="UTC")
        fired = 0
        for k in range(2, 5):
            bars = pd.DataFrame({"open": close[:k], "high": close[:k], "low": close[:k], "close": close[:k], "volume": 1.0}, index=idx[:k])
            t = evaluate(rule, bars)
            if t:
                fired += len(disp.submit(rule, t, idx[k - 1].to_pydatetime()))
        self.assertEqual(fired, 1)                                           # first cross alerts; the second (2 days later) is inside the 3-day cooldown
        self.assertTrue(any(r == "cooldown" for _, r in disp.suppressed))


if __name__ == "__main__":
    unittest.main()
