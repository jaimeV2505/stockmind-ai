import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from stockmind_signals import (
    Evidence, IllegalTransition, NoSignal, SignalRegistry, Status, new_signal, transition,
)
from stockmind_signals.lifecycle import ALLOWED

UTC = timezone.utc
T0 = datetime(2026, 10, 9, 14, 30, tzinfo=UTC)
EV = (Evidence("rsi14", 31.2, "oversold"),)


def sig(**kw):
    base = dict(symbol="NVDA", strategy_id="oversold_recovery", strategy_version="1.0.0", timeframe="1d",
                trigger_ts=T0, supporting=EV)
    base.update(kw)
    return new_signal(**base)


def in_state(target: Status):
    s = sig()
    paths = {
        Status.WATCHING: [], Status.AWAITING_CONFIRMATION: [Status.AWAITING_CONFIRMATION],
        Status.CONFIRMED: [Status.AWAITING_CONFIRMATION, Status.CONFIRMED],
        Status.INVALIDATED: [Status.INVALIDATED], Status.EXPIRED: [Status.EXPIRED],
        Status.CLOSED: [Status.AWAITING_CONFIRMATION, Status.CONFIRMED, Status.CLOSED],
    }
    for i, to in enumerate(paths[target], 1):
        s = transition(s, to, T0 + timedelta(minutes=i), "test")
    return s


class TestCreation(unittest.TestCase):
    def test_starts_watching_with_creation_event(self):
        s = sig()
        self.assertEqual(s.status, Status.WATCHING)
        self.assertEqual(len(s.events), 1)
        self.assertIsNone(s.events[0].from_status)

    def test_requires_evidence_and_utc(self):
        with self.assertRaises(ValueError):
            sig(supporting=())
        with self.assertRaises(ValueError):
            sig(trigger_ts=datetime(2026, 10, 9, 14, 30))
        from zoneinfo import ZoneInfo
        with self.assertRaises(ValueError):
            sig(trigger_ts=datetime(2026, 10, 9, 10, 30, tzinfo=ZoneInfo("America/New_York")))

    def test_no_signal_is_a_first_class_outcome(self):
        n = NoSignal("NVDA", "oversold_recovery", "1.0.0", "1d", T0, "RSI not oversold; insufficient evidence")
        self.assertIn("insufficient", n.reason)


class TestTransitions(unittest.TestCase):
    def test_exhaustive_transition_matrix(self):
        for src in Status:
            for dst in Status:
                s = in_state(src)
                with self.subTest(src=src.value, dst=dst.value):
                    at = s.events[-1].at + timedelta(minutes=1)
                    if dst in ALLOWED[src]:
                        self.assertEqual(transition(s, dst, at, "r").status, dst)
                    else:
                        with self.assertRaises(IllegalTransition):
                            transition(s, dst, at, "r")

    def test_terminal_states(self):
        for st in (Status.INVALIDATED, Status.EXPIRED, Status.CLOSED):
            self.assertTrue(in_state(st).is_terminal)
        self.assertFalse(in_state(Status.CONFIRMED).is_terminal)

    def test_immutable_and_audited(self):
        a = sig()
        b = transition(a, Status.AWAITING_CONFIRMATION, T0 + timedelta(hours=1), "price above resistance")
        self.assertEqual(a.status, Status.WATCHING)
        self.assertEqual(len(a.events), 1)
        self.assertEqual((len(b.events), b.events[-1].from_status, b.events[-1].reason),
                         (2, Status.WATCHING, "price above resistance"))

    def test_time_order_reason_and_tz_enforced(self):
        s = sig()
        with self.assertRaises(ValueError):
            transition(s, Status.EXPIRED, T0 - timedelta(seconds=1), "late")
        with self.assertRaises(ValueError):
            transition(s, Status.EXPIRED, T0 + timedelta(seconds=1), "  ")
        with self.assertRaises(ValueError):
            transition(s, Status.EXPIRED, datetime(2026, 10, 10), "naive")


class TestIdempotency(unittest.TestCase):
    def test_key_stable_and_sensitive(self):
        self.assertEqual(sig().key, sig().key)
        for kw in (dict(symbol="AMD"), dict(strategy_id="x"), dict(strategy_version="1.0.1"),
                   dict(timeframe="1h"), dict(trigger_ts=T0 + timedelta(days=1))):
            with self.subTest(kw=kw):
                self.assertNotEqual(sig().key, sig(**kw).key)

    def test_key_ignores_evidence_and_status(self):
        moved = transition(sig(), Status.EXPIRED, T0 + timedelta(minutes=1), "x")
        self.assertEqual(sig().key, moved.key)
        self.assertEqual(sig().key, replace(sig(), supporting=(Evidence("macd", 1.0),)).key)

    def test_registry_dedupes(self):
        reg = SignalRegistry()
        first, created1 = reg.add(sig())
        second, created2 = reg.add(sig(supporting=(Evidence("other", 2.0),)))
        self.assertEqual((created1, created2, len(reg)), (True, False, 1))
        self.assertIs(second, first)
        _, created3 = reg.add(sig(strategy_version="1.1.0"))   # new strategy version = new signal
        self.assertTrue(created3)
        self.assertEqual(len(reg), 2)

    def test_registry_update(self):
        reg = SignalRegistry()
        s, _ = reg.add(sig())
        reg.update(transition(s, Status.EXPIRED, T0 + timedelta(minutes=1), "x"))
        self.assertEqual(reg.add(sig())[0].status, Status.EXPIRED)
        with self.assertRaises(KeyError):
            reg.update(sig(symbol="ZZZ"))


if __name__ == "__main__":
    unittest.main()
