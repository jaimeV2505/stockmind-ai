import unittest

from stockmind_risk import Side, atr_stop, position_size, risk_reward


class TestStopsAndRR(unittest.TestCase):
    def test_atr_stop(self):
        self.assertAlmostEqual(atr_stop(100, 2.5, 2.0), 95.0)
        self.assertAlmostEqual(atr_stop(100, 2.5, 2.0, Side.SHORT), 105.0)

    def test_atr_stop_rejects_garbage(self):
        for args in ((100, 60, 2.0), (-1, 1, 1), (100, 0, 2), (100, float("nan"), 2), (100, 1, True)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                atr_stop(*args)

    def test_risk_reward(self):
        self.assertAlmostEqual(risk_reward(100, 95, 110), 2.0)
        self.assertAlmostEqual(risk_reward(100, 105, 90, Side.SHORT), 2.0)
        self.assertAlmostEqual(risk_reward(100, 95, 102.5), 0.5)

    def test_wrong_geometry_rejected(self):
        for args in ((100, 105, 110, Side.LONG), (100, 95, 95, Side.LONG), (100, 95, 90, Side.SHORT),
                     (100, 100, 110, Side.LONG)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                risk_reward(*args)


class TestPositionSize(unittest.TestCase):
    def test_risk_binding(self):
        p = position_size(100_000, 0.01, 100, 95)
        self.assertEqual((p.shares, p.binding_constraint), (200, "risk"))
        self.assertAlmostEqual(p.risk_amount, 1000.0)
        self.assertAlmostEqual(p.notional, 20_000.0)

    def test_position_cap_binding(self):
        p = position_size(100_000, 0.01, 100, 99.9, max_position_fraction=0.10)
        self.assertEqual((p.shares, p.binding_constraint), (100, "position_cap"))

    def test_liquidity_binding(self):
        p = position_size(100_000, 0.01, 100, 95, adv_shares=10_000, max_adv_fraction=0.01)
        self.assertEqual((p.shares, p.binding_constraint), (100, "liquidity"))

    def test_float_noise_does_not_lose_a_share(self):
        # 100 * 0.29 / 1 == 28.999999999999996 in binary floating point
        self.assertEqual(position_size(100, 0.29, 2, 1).shares, 29)

    def test_short_side(self):
        self.assertEqual(position_size(100_000, 0.01, 100, 105, Side.SHORT).shares, 200)

    def test_too_small_gives_zero_not_error(self):
        p = position_size(100, 0.01, 100, 90)
        self.assertEqual((p.shares, p.risk_amount, p.notional), (0, 0.0, 0.0))

    def test_validation(self):
        for kw in (dict(risk_fraction=0), dict(risk_fraction=1.5), dict(risk_fraction=float("nan")),
                   dict(equity=0), dict(stop=101), dict(max_position_fraction=2), dict(adv_shares=0)):
            base = dict(equity=100_000, risk_fraction=0.01, entry=100, stop=95)
            base.update(kw)
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                position_size(**base)


if __name__ == "__main__":
    unittest.main()
