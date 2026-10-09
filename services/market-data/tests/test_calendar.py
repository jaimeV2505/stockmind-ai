import unittest
from datetime import date, datetime, timezone

from stockmind_marketdata import (
    DemoProvider, Timeframe, expected_intraday_opens_utc, is_early_close, is_trading_day,
    session_close_utc, session_open_utc, trading_days, validate_series,
)
from stockmind_marketdata.calendar import easter, holidays

UTC = timezone.utc


class TestEaster(unittest.TestCase):
    def test_known_dates(self):
        self.assertEqual(easter(2024), date(2024, 3, 31))
        self.assertEqual(easter(2025), date(2025, 4, 20))
        self.assertEqual(easter(2026), date(2026, 4, 5))
        self.assertEqual(easter(2038), date(2038, 4, 25))  # latest possible Easter


class TestHolidays(unittest.TestCase):
    def test_2026_full_list(self):
        self.assertEqual(sorted(holidays(2026)), [
            date(2026, 1, 1), date(2026, 1, 19), date(2026, 2, 16), date(2026, 4, 3), date(2026, 5, 25),
            date(2026, 6, 19), date(2026, 7, 3), date(2026, 9, 7), date(2026, 11, 26), date(2026, 12, 25)])

    def test_weekend_observance(self):
        self.assertFalse(is_trading_day(date(2022, 6, 20)))   # Juneteenth Sunday -> Monday
        self.assertFalse(is_trading_day(date(2021, 7, 5)))    # Jul 4 Sunday -> Monday
        self.assertFalse(is_trading_day(date(2026, 7, 3)))    # Jul 4 Saturday -> Friday
        self.assertTrue(is_trading_day(date(2021, 12, 31)))   # Jan 1 2022 Saturday: Friday stays OPEN
        self.assertFalse(is_trading_day(date(2022, 12, 26)))  # Christmas Sunday -> Monday

    def test_juneteenth_only_from_2022(self):
        self.assertTrue(is_trading_day(date(2021, 6, 18)))
        self.assertFalse(is_trading_day(date(2023, 6, 19)))

    def test_ad_hoc_closures(self):
        self.assertFalse(is_trading_day(date(2025, 1, 9)))
        self.assertFalse(is_trading_day(date(2012, 10, 29)))

    def test_weekends_closed_and_range_enforced(self):
        self.assertFalse(is_trading_day(date(2026, 10, 10)))
        with self.assertRaises(ValueError):
            is_trading_day(date(2011, 1, 3))

    def test_annual_trading_day_counts(self):
        # Widely cited figures: 2023 -> 250, 2024 -> 252 trading days.
        self.assertEqual(len(trading_days(date(2023, 1, 1), date(2023, 12, 31))), 250)
        self.assertEqual(len(trading_days(date(2024, 1, 1), date(2024, 12, 31))), 252)


class TestSessions(unittest.TestCase):
    def test_early_closes(self):
        for d in (date(2026, 11, 27), date(2026, 12, 24), date(2025, 7, 3), date(2024, 7, 3), date(2018, 12, 24)):
            self.assertTrue(is_early_close(d), d)
        self.assertFalse(is_early_close(date(2026, 7, 2)))   # Jul 3 is the holiday that year: no early close
        self.assertFalse(is_early_close(date(2026, 12, 23)))
        self.assertFalse(is_early_close(date(2026, 11, 26)))  # closed, not early

    def test_session_times_across_dst(self):
        self.assertEqual(session_open_utc(date(2026, 3, 6)), datetime(2026, 3, 6, 14, 30, tzinfo=UTC))
        self.assertEqual(session_open_utc(date(2026, 3, 9)), datetime(2026, 3, 9, 13, 30, tzinfo=UTC))
        self.assertEqual(session_close_utc(date(2026, 3, 9)), datetime(2026, 3, 9, 20, 0, tzinfo=UTC))
        self.assertEqual(session_close_utc(date(2026, 11, 27)), datetime(2026, 11, 27, 18, 0, tzinfo=UTC))  # 13:00 EST

    def test_non_trading_day_raises(self):
        with self.assertRaises(ValueError):
            session_open_utc(date(2026, 11, 26))
        with self.assertRaises(ValueError):
            session_close_utc(date(2026, 10, 10))

    def test_expected_bar_counts(self):
        self.assertEqual(len(expected_intraday_opens_utc(date(2026, 3, 9), Timeframe.M5)), 78)
        self.assertEqual(len(expected_intraday_opens_utc(date(2026, 3, 9), Timeframe.M15)), 26)
        self.assertEqual(len(expected_intraday_opens_utc(date(2026, 3, 9), Timeframe.M1)), 390)
        self.assertEqual(len(expected_intraday_opens_utc(date(2026, 11, 27), Timeframe.M5)), 42)  # early close
        with self.assertRaises(NotImplementedError):
            expected_intraday_opens_utc(date(2026, 3, 9), Timeframe.H1)


class TestCalendarQuality(unittest.TestCase):
    NOW = datetime(2026, 12, 1, tzinfo=UTC)

    def test_demo_series_across_thanksgiving_is_clean(self):
        cs = DemoProvider(now=self.NOW).get_candles(
            "X", Timeframe.D1, datetime(2026, 11, 20, tzinfo=UTC), datetime(2026, 11, 30, tzinfo=UTC))
        from stockmind_marketdata import to_market_time
        days = [to_market_time(c.market_ts).date() for c in cs]
        self.assertNotIn(date(2026, 11, 26), days)                 # Thanksgiving skipped by the provider
        self.assertIn(date(2026, 11, 25), days)
        self.assertIn(date(2026, 11, 27), days)
        rep = validate_series(cs)
        self.assertTrue(rep.ok, rep)
        self.assertTrue(rep.gap_check_performed)

    def test_candle_on_holiday_flagged_unexpected(self):
        from dataclasses import replace
        cs = list(DemoProvider(now=self.NOW).get_candles(
            "X", Timeframe.D1, datetime(2026, 11, 23, tzinfo=UTC), datetime(2026, 11, 27, tzinfo=UTC)))
        cs.insert(3, replace(cs[2], market_ts=datetime(2026, 11, 26, 14, 30, tzinfo=UTC)))
        self.assertEqual(validate_series(cs).unexpected_dates, [date(2026, 11, 26)])

    def _intraday(self, tf):
        from stockmind_marketdata import AdjustmentStatus, Candle, DataMode
        return [Candle(symbol="X", exchange="NASDAQ", timeframe=tf, market_ts=t, ingested_at=self.NOW,
                       source="alpaca", currency="USD", adjustment=AdjustmentStatus.RAW,
                       data_mode=DataMode.HISTORICAL, open=10, high=11, low=9, close=10, volume=1)
                for t in expected_intraday_opens_utc(date(2026, 3, 9), tf)]

    def test_intraday_full_day_clean_then_gap_and_stray_bar(self):
        from dataclasses import replace
        cs = self._intraday(Timeframe.M5)
        self.assertTrue(validate_series(cs).ok)
        dropped = cs.pop(10)
        rep = validate_series(cs)
        self.assertEqual(rep.missing_intraday, [dropped.market_ts])
        cs.append(replace(cs[-1], market_ts=datetime(2026, 3, 9, 20, 0, tzinfo=UTC)))  # 16:00 ET bar: after close
        self.assertEqual(validate_series(cs).unexpected_ts, [datetime(2026, 3, 9, 20, 0, tzinfo=UTC)])

    def test_unsupported_timeframe_reports_no_gap_check(self):
        from dataclasses import replace
        c = self._intraday(Timeframe.M5)[0]
        rep = validate_series([replace(c, timeframe=Timeframe.H1)])
        self.assertFalse(rep.gap_check_performed)
        self.assertTrue(rep.ok)  # nothing detected, but NOT a clean bill of health


if __name__ == "__main__":
    unittest.main()
