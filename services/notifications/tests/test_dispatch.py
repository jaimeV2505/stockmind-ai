import unittest
from datetime import datetime, time, timedelta, timezone

import pandas as pd

from stockmind_alerts import (
    AlertRule, Channel, DeliveryStatus, Dispatcher, Kind, PermanentDeliveryError, QuietHours, Trigger,
)

UTC = timezone.utc
T0 = datetime(2026, 10, 9, 14, 0, tzinfo=UTC)


def rule(**kw):
    base = dict(id="r1", user_id="u1", symbol="NVDA", kind=Kind.PRICE_CROSS, channels=(Channel.EMAIL,), threshold=100.0)
    base.update(kw)
    return AlertRule(**base)


def trig(day=9, rule_id="r1"):
    return Trigger(rule_id, "NVDA", pd.Timestamp(2026, 10, day, tz="UTC"), "NVDA crossed above 100", (("close", 101.0),))


class Recorder:
    def __init__(self, fail_times=0, exc=RuntimeError("boom")):
        self.calls, self.fail_times, self.exc = [], fail_times, exc

    def __call__(self, d):
        self.calls.append((d.key, d.attempts))
        if len(self.calls) <= self.fail_times:
            raise self.exc


class TestSubmit(unittest.TestCase):
    def test_creates_one_delivery_per_channel_with_why(self):
        disp = Dispatcher({})
        out = disp.submit(rule(channels=(Channel.EMAIL, Channel.TELEGRAM, Channel.IN_APP)), trig(), T0)
        self.assertEqual(sorted(d.channel.value for d in out), ["email", "in_app", "telegram"])
        self.assertTrue(all(d.reason == "NVDA crossed above 100" and d.status is DeliveryStatus.PENDING for d in out))
        self.assertEqual(len({d.key for d in out}), 3)

    def test_same_event_is_idempotent(self):
        disp = Dispatcher({Channel.EMAIL: Recorder()})
        self.assertEqual(len(disp.submit(rule(), trig(), T0)), 1)
        self.assertEqual(disp.submit(rule(), trig(), T0 + timedelta(minutes=5)), [])
        self.assertEqual(len(disp.deliveries), 1)
        self.assertEqual(disp.suppressed[-1][1], "duplicate_event")

    def test_cooldown_between_distinct_events(self):
        disp = Dispatcher({})
        r = rule(cooldown=timedelta(hours=1))
        self.assertEqual(len(disp.submit(r, trig(9), T0)), 1)
        self.assertEqual(disp.submit(r, trig(10), T0 + timedelta(minutes=59, seconds=59)), [])
        self.assertEqual(disp.suppressed[-1][1], "cooldown")
        self.assertEqual(len(disp.submit(r, trig(11), T0 + timedelta(hours=1))), 1)   # boundary: exactly the cooldown elapsed

    def test_suppressed_event_is_not_consumed(self):
        disp = Dispatcher({})
        r = rule(cooldown=timedelta(hours=1))
        disp.submit(r, trig(9), T0)
        disp.submit(r, trig(10), T0 + timedelta(minutes=10))                       # suppressed by cooldown
        self.assertEqual(len(disp.submit(r, trig(10), T0 + timedelta(hours=2))), 1)  # same event may fire once cooldown is over

    def test_disabled_rule_and_wrong_trigger(self):
        disp = Dispatcher({})
        self.assertEqual(disp.submit(rule(enabled=False), trig(), T0), [])
        with self.assertRaises(ValueError):
            disp.submit(rule(), trig(rule_id="other"), T0)


class TestDelivery(unittest.TestCase):
    def test_success_marks_sent_once_and_passes_idempotency_key(self):
        rec = Recorder()
        disp = Dispatcher({Channel.EMAIL: rec})
        (d,) = disp.submit(rule(), trig(), T0)
        done = disp.run_due(T0)
        self.assertEqual([x.status for x in done], [DeliveryStatus.SENT])
        self.assertEqual(rec.calls, [(d.key, 1)])
        self.assertEqual(disp.run_due(T0 + timedelta(days=1)), [])                  # never sent twice
        self.assertEqual(len(rec.calls), 1)

    def test_retry_with_exponential_backoff_then_success(self):
        rec = Recorder(fail_times=2)
        disp = Dispatcher({Channel.EMAIL: rec}, base_delay=timedelta(seconds=30))
        (d,) = disp.submit(rule(), trig(), T0)
        disp.run_due(T0)
        s1 = disp.deliveries[d.key]
        delay1 = (s1.next_attempt_at - T0).total_seconds()
        self.assertEqual((s1.status, s1.attempts), (DeliveryStatus.PENDING, 1))
        self.assertTrue(27 <= delay1 <= 33, delay1)                                 # 30s +-10%
        self.assertEqual(disp.run_due(T0 + timedelta(seconds=10)), [])               # not due yet
        t2 = s1.next_attempt_at
        disp.run_due(t2)
        s2 = disp.deliveries[d.key]
        delay2 = (s2.next_attempt_at - t2).total_seconds()
        self.assertTrue(54 <= delay2 <= 66, delay2)                                 # 60s +-10%: doubled
        disp.run_due(s2.next_attempt_at)
        s3 = disp.deliveries[d.key]
        self.assertEqual((s3.status, s3.attempts), (DeliveryStatus.SENT, 3))
        self.assertEqual([k for k, _ in rec.calls], [d.key] * 3)                    # same idempotency key every attempt
        self.assertEqual([a for _, a in rec.calls], [1, 2, 3])

    def test_backoff_is_capped_and_deterministic(self):
        disp = Dispatcher({}, base_delay=timedelta(seconds=30), max_delay=timedelta(minutes=10))
        self.assertLessEqual(disp._backoff("k", 20), timedelta(minutes=11))
        self.assertEqual(disp._backoff("k", 3), disp._backoff("k", 3))
        self.assertNotEqual(disp._backoff("k", 3), disp._backoff("other", 3))

    def test_dead_letter_after_max_attempts(self):
        rec = Recorder(fail_times=99)
        disp = Dispatcher({Channel.EMAIL: rec}, max_attempts=3)
        (d,) = disp.submit(rule(), trig(), T0)
        now = T0
        for _ in range(10):
            disp.run_due(now)
            now += timedelta(hours=2)
        final = disp.deliveries[d.key]
        self.assertEqual((final.status, final.attempts), (DeliveryStatus.DEAD, 3))
        self.assertEqual(len(rec.calls), 3)                                         # exactly max_attempts tries, then stops
        self.assertIn("RuntimeError: boom", final.last_error)
        self.assertEqual(disp.stats()["DEAD"], 1)

    def test_permanent_error_goes_straight_to_dead_letter(self):
        rec = Recorder(fail_times=99, exc=PermanentDeliveryError("chat not found"))
        disp = Dispatcher({Channel.TELEGRAM: rec})
        (d,) = disp.submit(rule(channels=(Channel.TELEGRAM,)), trig(), T0)
        disp.run_due(T0)
        self.assertEqual((disp.deliveries[d.key].status, disp.deliveries[d.key].attempts), (DeliveryStatus.DEAD, 1))

    def test_unconfigured_channel_is_skipped_visibly_and_does_not_block_others(self):
        rec = Recorder()
        disp = Dispatcher({Channel.EMAIL: rec})                                      # telegram has no sender
        disp.submit(rule(channels=(Channel.EMAIL, Channel.TELEGRAM)), trig(), T0)
        disp.run_due(T0)
        s = disp.stats()
        self.assertEqual((s["SENT"], s["SKIPPED"], s["PENDING"]), (1, 1, 0))

    def test_error_text_is_bounded(self):
        rec = Recorder(fail_times=1, exc=RuntimeError("x" * 5000))
        disp = Dispatcher({Channel.EMAIL: rec})
        (d,) = disp.submit(rule(), trig(), T0)
        disp.run_due(T0)
        self.assertLessEqual(len(disp.deliveries[d.key].last_error), 230)

    def test_invalid_configuration(self):
        with self.assertRaises(ValueError):
            Dispatcher({}, max_attempts=0)


class TestQuietHours(unittest.TestCase):
    NY = "America/New_York"

    def test_overnight_window_boundaries(self):
        q = QuietHours(time(22, 0), time(7, 0), self.NY)
        # 2026-10-09 is EDT (UTC-4): 22:00 local = 02:00 UTC next day; 07:00 local = 11:00 UTC
        self.assertFalse(q.contains(datetime(2026, 10, 10, 1, 59, tzinfo=UTC)))     # 21:59 local
        self.assertTrue(q.contains(datetime(2026, 10, 10, 2, 0, tzinfo=UTC)))       # 22:00 local: start inclusive
        self.assertTrue(q.contains(datetime(2026, 10, 10, 10, 59, tzinfo=UTC)))     # 06:59 local
        self.assertFalse(q.contains(datetime(2026, 10, 10, 11, 0, tzinfo=UTC)))     # 07:00 local: end exclusive

    def test_same_day_window_and_validation(self):
        q = QuietHours(time(13, 0), time(15, 0), "UTC")
        self.assertTrue(q.contains(datetime(2026, 1, 1, 14, tzinfo=UTC)))
        self.assertFalse(q.contains(datetime(2026, 1, 1, 15, tzinfo=UTC)))
        self.assertTrue(q.contains(datetime(2026, 1, 1, 13, 0, tzinfo=UTC)))        # start inclusive (same-day window)
        self.assertFalse(q.contains(datetime(2026, 1, 1, 12, 59, 59, tzinfo=UTC)))
        for args in ((time(8), time(8), "UTC"), (time(8), time(9), "Mars/Base")):
            with self.assertRaises(Exception):
                QuietHours(*args)
        with self.assertRaises(ValueError):
            q.contains(datetime(2026, 1, 1, 14))

    def test_next_end_is_dst_aware(self):
        q = QuietHours(time(22, 0), time(7, 0), self.NY)
        # Saturday night before the 2026-03-08 spring-forward: at 01:00 EST (06:00 UTC) the window ends 07:00 EDT = 11:00 UTC (not 12:00)
        self.assertEqual(q.next_end(datetime(2026, 3, 8, 6, 0, tzinfo=UTC)), datetime(2026, 3, 8, 11, 0, tzinfo=UTC))
        # normal winter day: 07:00 EST = 12:00 UTC
        self.assertEqual(q.next_end(datetime(2026, 1, 15, 6, 0, tzinfo=UTC)), datetime(2026, 1, 15, 12, 0, tzinfo=UTC))
        # inside the evening part: ends tomorrow morning
        self.assertEqual(q.next_end(datetime(2026, 1, 15, 4, 0, tzinfo=UTC)), datetime(2026, 1, 15, 12, 0, tzinfo=UTC))

    def test_deferral_non_interruptive_channels_only(self):
        q = {"u1": QuietHours(time(22, 0), time(7, 0), self.NY)}
        night = datetime(2026, 10, 10, 4, 0, tzinfo=UTC)                             # 00:00 local
        rec_mail, rec_app = Recorder(), Recorder()
        disp = Dispatcher({Channel.EMAIL: rec_mail, Channel.IN_APP: rec_app}, quiet=q)
        disp.submit(rule(channels=(Channel.EMAIL, Channel.IN_APP)), trig(), night)
        disp.run_due(night)
        self.assertEqual((len(rec_app.calls), len(rec_mail.calls)), (1, 0))          # in-app immediate, email held
        self.assertEqual(disp.run_due(night + timedelta(hours=6, minutes=59)), [])   # 06:59 local: still quiet
        done = disp.run_due(datetime(2026, 10, 10, 11, 0, tzinfo=UTC))               # 07:00 local
        self.assertEqual([d.status for d in done], [DeliveryStatus.SENT])
        self.assertEqual(disp.deliveries[done[0].key].attempts, 1)                    # deferral did not burn an attempt

    def test_quiet_hours_beginning_after_scheduling_defers_retry(self):
        q = {"u1": QuietHours(time(22, 0), time(7, 0), "UTC")}
        rec = Recorder(fail_times=1)
        disp = Dispatcher({Channel.EMAIL: rec}, quiet=q, base_delay=timedelta(minutes=30))
        start = datetime(2026, 5, 1, 21, 50, tzinfo=UTC)
        (d,) = disp.submit(rule(), trig(), start)
        disp.run_due(start)                                                          # fails; retry scheduled ~21:50+30m = 22:20 (quiet)
        retry_at = disp.deliveries[d.key].next_attempt_at
        self.assertTrue(q["u1"].contains(retry_at))
        disp.run_due(retry_at)                                                       # must NOT send during quiet hours
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(disp.deliveries[d.key].next_attempt_at, datetime(2026, 5, 2, 7, 0, tzinfo=UTC))


if __name__ == "__main__":
    unittest.main()
