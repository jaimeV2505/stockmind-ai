import unittest
from datetime import datetime, timezone

from stockmind_entitlements import (
    DEFAULT_LIMITS, EntitlementError, Plan, Principal, Role, UsageMeter, check_quota, require_feature, require_role,
)
from stockmind_entitlements.core import FEATURE_FLAGS, QUOTA_FEATURES

UTC = timezone.utc


class TestQuota(unittest.TestCase):
    def test_boundaries(self):
        self.assertTrue(check_quota(Plan.FREE, "active_alerts", 2).allowed)           # 2 + 1 <= 3
        d = check_quota(Plan.FREE, "active_alerts", 3)
        self.assertFalse(d.allowed)
        self.assertEqual((d.limit, d.used), (3, 3))
        self.assertIn("3/3", d.reason)
        self.assertFalse(check_quota(Plan.FREE, "active_alerts", 1, requested=3).allowed)   # would exceed
        self.assertTrue(check_quota(Plan.FREE, "active_alerts", 0, requested=3).allowed)

    def test_unlimited_admin_plan(self):
        self.assertTrue(check_quota(Plan.ADMIN, "backtests_per_day", 10 ** 9).allowed)

    def test_plans_are_monotonic(self):
        order = [Plan.FREE, Plan.PRO, Plan.PREMIUM, Plan.ADMIN]
        for f in QUOTA_FEATURES + ("history_days",):
            vals = [float("inf") if DEFAULT_LIMITS[p][f] is None else DEFAULT_LIMITS[p][f] for p in order]
            self.assertEqual(vals, sorted(vals), f)
        scan = [DEFAULT_LIMITS[p]["scanner_min_interval_minutes"] for p in order]
        self.assertEqual(scan, sorted(scan, reverse=True))                           # higher plan = faster scans
        for f in FEATURE_FLAGS:
            flags = [DEFAULT_LIMITS[p][f] for p in order]
            self.assertEqual(flags, sorted(flags))                                   # a feature never disappears on upgrade

    def test_fail_closed(self):
        for plan, feat in (("GOLD", "active_alerts"), (None, "active_alerts"), (Plan.PRO, "nonexistent"), ("free", "active_alerts")):
            with self.subTest(plan=plan, feat=feat):
                self.assertFalse(check_quota(plan, feat, 0).allowed)
        self.assertFalse(check_quota(Plan.PRO, "csv_export", 0).allowed)             # flag used as quota
        self.assertTrue(check_quota("PRO", "active_alerts", 0).allowed)              # canonical string accepted

    def test_invalid_numbers(self):
        for u, r in ((-1, 1), (0, 0), (0, -2), (True, 1)):
            with self.subTest(u=u, r=r), self.assertRaises(ValueError):
                check_quota(Plan.PRO, "active_alerts", u, r)

    def test_feature_flags(self):
        self.assertFalse(require_feature(Plan.FREE, "pattern_intelligence").allowed)
        self.assertTrue(require_feature(Plan.PREMIUM, "pattern_intelligence").allowed)
        self.assertFalse(require_feature(Plan.PREMIUM, "active_alerts").allowed)     # a quota is not a flag
        self.assertFalse(require_feature("BOGUS", "csv_export").allowed)
        with self.assertRaises(EntitlementError):
            require_feature(Plan.FREE, "csv_export").raise_if_denied()


class TestRoles(unittest.TestCase):
    def test_admin_endpoints_require_role_not_plan(self):
        self.assertFalse(require_role(Principal("u", Plan.ADMIN, Role.USER), Role.ADMIN).allowed)   # plan ADMIN != admin access
        self.assertTrue(require_role(Principal("u", Plan.FREE, Role.ADMIN), Role.ADMIN).allowed)
        self.assertFalse(require_role(Principal("u", Plan.FREE, "ADMIN"), Role.ADMIN).allowed)      # untyped role string rejected


class TestUsageMeter(unittest.TestCase):
    P = Principal("u1", Plan.FREE)

    def test_consume_until_limit_then_deny_without_counting(self):
        m, now = UsageMeter(), datetime(2026, 10, 9, 12, tzinfo=UTC)
        results = [m.try_consume(self.P, "ai_analyses_per_day", now).allowed for _ in range(7)]
        self.assertEqual(results, [True] * 5 + [False] * 2)
        self.assertEqual(m.used("u1", "ai_analyses_per_day", now), 5)                # denied calls are not recorded

    def test_resets_at_utc_midnight_and_is_per_user_and_feature(self):
        m = UsageMeter()
        late = datetime(2026, 10, 9, 23, 59, 59, tzinfo=UTC)
        for _ in range(5):
            m.try_consume(self.P, "ai_analyses_per_day", late)
        self.assertFalse(m.try_consume(self.P, "ai_analyses_per_day", late).allowed)
        self.assertTrue(m.try_consume(self.P, "ai_analyses_per_day", datetime(2026, 10, 10, 0, 0, tzinfo=UTC)).allowed)
        self.assertTrue(m.try_consume(Principal("u2", Plan.FREE), "ai_analyses_per_day", late).allowed)
        self.assertTrue(m.try_consume(self.P, "backtests_per_day", late).allowed)
        self.assertEqual(m.next_reset(late), datetime(2026, 10, 10, tzinfo=UTC))

    def test_timezone_aware_day_boundary(self):
        from zoneinfo import ZoneInfo
        m = UsageMeter()
        ny = datetime(2026, 10, 9, 22, 0, tzinfo=ZoneInfo("America/New_York"))       # = 02:00 UTC on Oct 10
        m.try_consume(self.P, "backtests_per_day", ny)
        self.assertEqual(m.used("u1", "backtests_per_day", datetime(2026, 10, 10, 3, tzinfo=UTC)), 1)
        with self.assertRaises(ValueError):
            m.used("u1", "backtests_per_day", datetime(2026, 10, 10))


if __name__ == "__main__":
    unittest.main()
