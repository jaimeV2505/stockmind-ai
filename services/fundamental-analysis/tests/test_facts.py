import unittest
from datetime import date, datetime, timezone

from stockmind_fundamentals import (
    Fact, FactStore, Reading, ScoreConfig, Status, fundamental_score, net_margin, pe_ratio, revenue_growth_yoy,
)

UTC = timezone.utc


def dt(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=UTC)


def fact(metric, value, period_end, filed, ptype="FY", source="SEC EDGAR 10-K test", symbol="ACME"):
    return Fact(symbol, metric, value, period_end, ptype, filed, source)


class TestFactValidation(unittest.TestCase):
    def test_rejects_impossible_or_unattributed_facts(self):
        for kw in (dict(filed=dt(2025, 12, 30), period_end=date(2025, 12, 31)),                  # filed before period end
                   dict(source=" "), dict(value=float("nan")), dict(value=float("inf")), dict(value=True), dict(ptype="TTM")):
            args = dict(metric="revenue", value=1.0, period_end=date(2025, 12, 31), filed=dt(2026, 2, 1))
            args.update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                fact(**args)
        with self.assertRaises(ValueError):
            Fact("A", "revenue", 1.0, date(2025, 12, 31), "FY", datetime(2026, 2, 1), "s")        # naive filed_at

    def test_duplicate_filing_rejected_but_restatement_allowed(self):
        s = FactStore()
        s.add(fact("revenue", 100, date(2025, 12, 31), dt(2026, 2, 1)))
        s.add(fact("revenue", 90, date(2025, 12, 31), dt(2026, 6, 1)))
        with self.assertRaises(ValueError):
            s.add(fact("revenue", 95, date(2025, 12, 31), dt(2026, 2, 1)))


class TestPointInTime(unittest.TestCase):
    def setUp(self):
        self.s = FactStore()
        self.s.add(fact("revenue", 100.0, date(2024, 12, 31), dt(2025, 2, 10)))
        self.s.add(fact("revenue", 130.0, date(2025, 12, 31), dt(2026, 2, 12, 21)))
        self.s.add(fact("revenue", 120.0, date(2025, 12, 31), dt(2026, 7, 1)))             # restatement

    def test_nothing_is_visible_before_it_was_filed(self):
        self.assertEqual(self.s.known_at("ACME", "revenue", date(2025, 12, 31), "FY", dt(2026, 2, 12, 20)).status, Status.UNAVAILABLE)
        self.assertEqual(self.s.latest("ACME", "revenue", "FY", dt(2025, 1, 1)).status, Status.UNAVAILABLE)

    def test_filing_instant_is_inclusive(self):
        self.assertEqual(self.s.known_at("ACME", "revenue", date(2025, 12, 31), "FY", dt(2026, 2, 12, 21)).value, 130.0)

    def test_restatement_invisible_until_filed(self):
        self.assertEqual(self.s.known_at("ACME", "revenue", date(2025, 12, 31), "FY", dt(2026, 6, 30)).value, 130.0)
        self.assertEqual(self.s.known_at("ACME", "revenue", date(2025, 12, 31), "FY", dt(2026, 7, 1)).value, 120.0)

    def test_latest_period_depends_on_the_as_of_time(self):
        self.assertEqual(self.s.latest("ACME", "revenue", "FY", dt(2026, 1, 15)).fact.period_end, date(2024, 12, 31))
        self.assertEqual(self.s.latest("ACME", "revenue", "FY", dt(2026, 3, 1)).fact.period_end, date(2025, 12, 31))

    def test_growth_uses_only_facts_known_at_the_time(self):
        g1 = revenue_growth_yoy(self.s, "ACME", dt(2026, 3, 1))
        g2 = revenue_growth_yoy(self.s, "ACME", dt(2026, 8, 1))
        self.assertAlmostEqual(g1.value, 0.30)                      # 130/100 before the restatement
        self.assertAlmostEqual(g2.value, 0.20)                      # 120/100 after
        self.assertEqual(revenue_growth_yoy(self.s, "ACME", dt(2026, 1, 15)).status, Status.UNAVAILABLE)  # no prior year yet

    def test_future_facts_never_change_a_past_reading(self):
        before = revenue_growth_yoy(self.s, "ACME", dt(2026, 3, 1))
        self.s.add(fact("revenue", 999.0, date(2026, 12, 31), dt(2027, 2, 1)))
        self.assertEqual(revenue_growth_yoy(self.s, "ACME", dt(2026, 3, 1)), before)

    def test_naive_query_time_rejected(self):
        with self.assertRaises(ValueError):
            self.s.latest("ACME", "revenue", "FY", datetime(2026, 3, 1))


class TestDistinctNonValues(unittest.TestCase):
    def store(self, **vals):
        s = FactStore()
        for m, v in vals.items():
            s.add(fact(m, v, date(2025, 12, 31), dt(2026, 2, 12)))
        return s

    def test_none_is_unavailable_not_zero_and_not_negative(self):
        s = self.store(revenue=None)
        r = s.latest("ACME", "revenue", "FY", dt(2026, 3, 1))
        self.assertEqual((r.status, r.value), (Status.UNAVAILABLE, None))

    def test_net_loss_is_a_real_negative_value(self):
        s = self.store(revenue=200.0, net_income=-50.0)
        m = net_margin(s, "ACME", dt(2026, 3, 1))
        self.assertEqual(m.status, Status.OK)
        self.assertAlmostEqual(m.value, -0.25)

    def test_margin_edge_cases(self):
        self.assertEqual(net_margin(self.store(net_income=10.0), "ACME", dt(2026, 3, 1)).status, Status.UNAVAILABLE)    # revenue missing
        self.assertEqual(net_margin(self.store(revenue=0.0, net_income=10.0), "ACME", dt(2026, 3, 1)).status, Status.NOT_MEANINGFUL)
        self.assertEqual(net_margin(self.store(revenue=100.0, net_income=None), "ACME", dt(2026, 3, 1)).status, Status.UNAVAILABLE)

    def test_pe_is_never_negative(self):
        s = self.store(eps=-1.2)
        r = pe_ratio(s, "ACME", dt(2026, 3, 1), price=50.0)
        self.assertEqual((r.status, r.value), (Status.NOT_MEANINGFUL, None))
        self.assertAlmostEqual(pe_ratio(self.store(eps=2.5), "ACME", dt(2026, 3, 1), 50.0).value, 20.0)
        self.assertEqual(pe_ratio(self.store(eps=0.0), "ACME", dt(2026, 3, 1), 50.0).status, Status.NOT_MEANINGFUL)
        self.assertEqual(pe_ratio(FactStore(), "ACME", dt(2026, 3, 1), 50.0).status, Status.UNAVAILABLE)
        for bad in (0, -5, float("nan"), True):
            with self.assertRaises(ValueError):
                pe_ratio(self.store(eps=2.5), "ACME", dt(2026, 3, 1), bad)

    def test_growth_off_non_positive_base_is_not_meaningful(self):
        s = FactStore()
        s.add(fact("revenue", -5.0, date(2024, 12, 31), dt(2025, 2, 1)))
        s.add(fact("revenue", 50.0, date(2025, 12, 31), dt(2026, 2, 1)))
        self.assertEqual(revenue_growth_yoy(s, "ACME", dt(2026, 3, 1)).status, Status.NOT_MEANINGFUL)

    def test_leap_day_prior_period(self):
        s = FactStore()
        s.add(fact("revenue", 100.0, date(2023, 2, 28), dt(2023, 4, 1)))
        s.add(fact("revenue", 110.0, date(2024, 2, 29), dt(2024, 4, 1)))
        self.assertAlmostEqual(revenue_growth_yoy(s, "ACME", dt(2024, 5, 1)).value, 0.10)


class TestScore(unittest.TestCase):
    def R(self, v):
        return Reading(Status.OK, v)

    def test_hand_computed_score(self):
        r = {"revenue_growth_yoy": self.R(0.10), "net_margin": self.R(0.20), "pe": self.R(26.0)}
        res = fundamental_score(r)
        # growth 0.5*0.35 + margin 1.0*0.35 + pe (40-26)/(40-12)=0.5*0.30
        self.assertAlmostEqual(res.score, 100 * (0.175 + 0.35 + 0.15))
        self.assertEqual(res.missing, ())
        self.assertEqual(len(res.explanation), 3)

    def test_clamping_and_direction(self):
        res = fundamental_score({"revenue_growth_yoy": self.R(5.0), "net_margin": self.R(-3.0), "pe": self.R(2.0)})
        self.assertAlmostEqual(res.score, 100 * (0.35 * 1 + 0.35 * 0 + 0.30 * 1))

    def test_unavailable_is_excluded_but_not_meaningful_scores_zero(self):
        base = {"revenue_growth_yoy": self.R(0.20), "net_margin": self.R(0.20)}
        unavail = fundamental_score({**base, "pe": Reading(Status.UNAVAILABLE, note="no EPS")})
        nm = fundamental_score({**base, "pe": Reading(Status.NOT_MEANINGFUL, note="EPS <= 0")})
        self.assertAlmostEqual(unavail.score, 100.0)                      # renormalised over available weight
        self.assertEqual(unavail.missing, ("pe",))
        self.assertAlmostEqual(nm.score, 100 * 0.70)                      # loss-maker earns nothing for valuation
        self.assertTrue(any("NOT treated as zero" in e for e in unavail.explanation))

    def test_insufficient_data_gives_no_score(self):
        res = fundamental_score({"pe": self.R(10.0)})                     # only 30% of the weight
        self.assertIsNone(res.score)
        self.assertTrue(any("INSUFFICIENT DATA" in e for e in res.explanation))
        self.assertIsNone(fundamental_score({}).score)

    def test_config_validation_and_custom_weights(self):
        for comps in ({}, {"x": (0.0, 0, 1)}, {"x": (1.0, 5, 5)}, {"x": (1.0, float("nan"), 1)}):
            with self.assertRaises(ValueError):
                ScoreConfig(components=comps)
        cfg = ScoreConfig(components={"net_margin": (1.0, 0.0, 0.5)})
        self.assertAlmostEqual(fundamental_score({"net_margin": self.R(0.25)}, cfg).score, 50.0)


if __name__ == "__main__":
    unittest.main()
