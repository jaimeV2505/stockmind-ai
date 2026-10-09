import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from stockmind_marketdata import (
    AdjustmentStatus, Candle, DataMode, DemoProvider, MarketDataProvider, Timeframe,
    session_close_utc, session_open_utc, to_market_time, validate_series,
)

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def make(**kw):
    base = dict(symbol="AAPL", exchange="NASDAQ", timeframe=Timeframe.D1,
                market_ts=datetime(2026, 1, 5, 14, 30, tzinfo=UTC), ingested_at=NOW,
                source="alpaca", currency="USD", adjustment=AdjustmentStatus.RAW,
                data_mode=DataMode.HISTORICAL, open=10.0, high=11.0, low=9.0, close=10.5, volume=100.0)
    base.update(kw)
    return Candle(**base)


class TestCandle(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(make().close, 10.5)

    def test_rejects_naive_and_non_utc(self):
        with self.assertRaises(ValueError):
            make(market_ts=datetime(2026, 1, 5, 9, 30))
        from zoneinfo import ZoneInfo
        with self.assertRaises(ValueError):
            make(market_ts=datetime(2026, 1, 5, 9, 30, tzinfo=ZoneInfo("America/New_York")))

    def test_rejects_bad_ohlc_and_volume(self):
        with self.assertRaises(ValueError):
            make(high=9.5)
        with self.assertRaises(ValueError):
            make(low=10.8)
        with self.assertRaises(ValueError):
            make(volume=-1)

    def test_simulated_must_be_labelled(self):
        with self.assertRaises(ValueError):
            make(data_mode=DataMode.SIMULATED, source="alpaca")


class TestTimezones(unittest.TestCase):
    def test_dst_shift_2026(self):
        # US DST starts Sunday 2026-03-08: Fri 03-06 is EST (UTC-5), Mon 03-09 is EDT (UTC-4)
        self.assertEqual(session_open_utc(date(2026, 3, 6)), datetime(2026, 3, 6, 14, 30, tzinfo=UTC))
        self.assertEqual(session_open_utc(date(2026, 3, 9)), datetime(2026, 3, 9, 13, 30, tzinfo=UTC))
        self.assertEqual(session_close_utc(date(2026, 3, 9)), datetime(2026, 3, 9, 20, 0, tzinfo=UTC))

    def test_to_market_time(self):
        self.assertEqual(to_market_time(datetime(2026, 7, 1, 13, 30, tzinfo=UTC)).hour, 9)
        with self.assertRaises(ValueError):
            to_market_time(datetime(2026, 7, 1, 13, 30))


class TestQuality(unittest.TestCase):
    def series(self):
        return list(DemoProvider(now=NOW).get_candles(
            "TEST", Timeframe.D1, datetime(2026, 3, 2, tzinfo=UTC), datetime(2026, 3, 13, tzinfo=UTC)))

    def test_clean_series_ok(self):
        self.assertTrue(validate_series(self.series()).ok)

    def test_detects_duplicate(self):
        s = self.series()
        s.append(s[0])
        self.assertTrue(validate_series(s).duplicates)

    def test_detects_missing_day_and_holiday_exemption(self):
        s = self.series()
        removed = s.pop(3)
        gap = to_market_time(removed.market_ts).date()
        self.assertEqual(validate_series(s).missing_dates, [gap])
        self.assertTrue(validate_series(s, holidays=[gap]).ok)

    def test_detects_out_of_order_and_mixed_modes(self):
        s = self.series()
        s[2], s[3] = s[3], s[2]
        self.assertTrue(validate_series(s).out_of_order)
        s = self.series()
        s[0] = replace(s[0], data_mode=DataMode.HISTORICAL, source="alpaca")
        self.assertTrue(validate_series(s).mixed_modes)


class TestDemoProvider(unittest.TestCase):
    def test_always_labelled_simulated(self):
        p = DemoProvider(now=NOW)
        self.assertIsInstance(p, MarketDataProvider)
        self.assertTrue(p.is_simulated)
        cs = p.get_candles("X", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC))
        self.assertTrue(cs)
        self.assertTrue(all(c.data_mode is DataMode.SIMULATED and c.source == "demo-simulated" for c in cs))

    def test_deterministic_per_seed_and_symbol(self):
        a = DemoProvider(seed=1, now=NOW).get_candles("X", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))
        b = DemoProvider(seed=1, now=NOW).get_candles("X", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))
        c = DemoProvider(seed=1, now=NOW).get_candles("Y", Timeframe.D1, datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))
        self.assertEqual(a, b)
        self.assertNotEqual([x.close for x in a], [x.close for x in c])

    def test_intraday_not_supported_explicitly(self):
        with self.assertRaises(NotImplementedError):
            DemoProvider(now=NOW).get_candles("X", Timeframe.M5, NOW, NOW)


if __name__ == "__main__":
    unittest.main()
