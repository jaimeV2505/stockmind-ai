"""Regression tests for the session-3 audit findings (see docs/progress/audit-2026-10-09.md)."""
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone

from stockmind_marketdata import (
    AdjustmentStatus, Candle, DataMode, DemoProvider, Timeframe, is_early_close, is_trading_day,
    session_open_utc, trading_days, validate_series,
)
from stockmind_marketdata import calendar as cal

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 12, 0, tzinfo=UTC)


def make(**kw):
    base = dict(symbol="AAPL", exchange="NASDAQ", timeframe=Timeframe.D1,
                market_ts=datetime(2026, 1, 5, 14, 30, tzinfo=UTC), ingested_at=NOW,
                source="alpaca", currency="USD", adjustment=AdjustmentStatus.RAW,
                data_mode=DataMode.HISTORICAL, open=10.0, high=11.0, low=9.0, close=10.5, volume=100.0)
    base.update(kw)
    return Candle(**base)


def real_series(symbol="AAA", start=(2026, 3, 2), end=(2026, 3, 13), now=NOW):
    cs = DemoProvider(now=now).get_candles(symbol, Timeframe.D1, datetime(*start, tzinfo=UTC), datetime(*end, tzinfo=UTC))
    return [replace(c, source="alpaca", data_mode=DataMode.HISTORICAL, exchange="NASDAQ") for c in cs]


class TestA01CandleInputIntegrity(unittest.TestCase):
    def test_rejects_non_finite_numbers(self):
        for field in ("open", "high", "low", "close", "volume"):
            for bad in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(field=field, bad=bad), self.assertRaises(ValueError):
                    make(**{field: bad})

    def test_rejects_non_numeric_and_bool(self):
        for bad in ("10", None, True):
            with self.subTest(bad=bad), self.assertRaises((ValueError, TypeError)):
                make(close=bad)

    def test_rejects_bad_identifiers(self):
        for kw in (dict(symbol="aapl"), dict(symbol=""), dict(symbol="A" * 11), dict(symbol="AA PL"),
                   dict(currency="dollars"), dict(currency="usd"), dict(source=""), dict(exchange="")):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                make(**kw)

    def test_accepts_realistic_symbols(self):
        for s in ("AAPL", "BRK.B", "BF-B", "A"):
            self.assertEqual(make(symbol=s).symbol, s)

    def test_cannot_be_ingested_before_it_opened(self):
        with self.assertRaises(ValueError):
            make(ingested_at=datetime(2026, 1, 5, 14, 29, tzinfo=UTC))

    def test_key_distinguishes_exchange(self):
        self.assertNotEqual(make(exchange="NASDAQ").key, make(exchange="NYSE").key)


class TestA02CalendarTypeSafety(unittest.TestCase):
    def test_datetime_rejected_everywhere(self):
        xmas = datetime(2026, 12, 25, 12, 0)
        for fn in (is_trading_day, is_early_close, session_open_utc):
            with self.subTest(fn=fn.__name__), self.assertRaises(TypeError):
                fn(xmas)
        with self.assertRaises(TypeError):
            trading_days(xmas, date(2026, 12, 31))

    def test_holiday_table_is_immutable(self):
        with self.assertRaises(TypeError):
            cal.holidays(2026)[date(2026, 3, 3)] = "injected"
        self.assertTrue(is_trading_day(date(2026, 3, 3)))

    def test_more_annual_trading_day_anchors(self):
        for year, n in ((2019, 252), (2020, 253), (2021, 252), (2022, 251)):
            self.assertEqual(len(trading_days(date(year, 1, 1), date(year, 12, 31))), n, year)


class TestA04QualityScope(unittest.TestCase):
    def test_multi_symbol_or_exchange_input_rejected(self):
        a, b = real_series("AAA"), real_series("BBB")
        with self.assertRaises(ValueError):
            validate_series(sorted(a + b, key=lambda c: c.market_ts))
        with self.assertRaises(ValueError):
            validate_series([a[0], replace(a[1], exchange="NYSE")])

    def test_mixed_sources_and_adjustments_flagged(self):
        s = real_series("AAA")
        self.assertTrue(validate_series([s[0], replace(s[1], source="fmp")]).mixed_provenance)
        self.assertTrue(validate_series([s[0], replace(s[1], adjustment=AdjustmentStatus.FULLY_ADJUSTED)]).mixed_provenance)
        self.assertFalse(validate_series(s).mixed_provenance)

    def test_misaligned_daily_timestamp_flagged(self):
        s = real_series("AAA")
        shifted = [replace(c, market_ts=c.market_ts.replace(hour=0, minute=0)) for c in s]  # midnight-UTC stamps
        rep = validate_series(shifted)
        # Monday 00:00 UTC is Sunday in New York -> "unexpected date"; the rest are "misaligned". Nothing passes silently.
        self.assertEqual(len(rep.misaligned_ts) + len(rep.unexpected_dates), len(s))
        self.assertTrue(rep.misaligned_ts)
        self.assertFalse(rep.ok)
        self.assertTrue(validate_series(s).ok)


class TestA05IncompleteBars(unittest.TestCase):
    def test_bar_close_and_freshness(self):
        d = date(2026, 3, 2)
        self.assertEqual(cal.bar_close_utc(Timeframe.D1, session_open_utc(d)), datetime(2026, 3, 2, 21, 0, tzinfo=UTC))
        early = date(2026, 11, 27)
        self.assertEqual(cal.bar_close_utc(Timeframe.D1, session_open_utc(early)), datetime(2026, 11, 27, 18, 0, tzinfo=UTC))
        c = make(market_ts=session_open_utc(d), ingested_at=datetime(2026, 3, 2, 22, 0, tzinfo=UTC))
        self.assertEqual(c.freshness().total_seconds(), 3600)  # ingested 1h after the 16:00 ET close
        with self.assertRaises(NotImplementedError):
            cal.bar_close_utc(Timeframe.H1, session_open_utc(d))

    def test_forming_daily_bar_flagged_incomplete(self):
        s = real_series("AAA", end=(2026, 3, 6))
        forming = replace(s[-1], ingested_at=s[-1].market_ts.replace(hour=19, minute=0))  # 14:00 ET same day, before close
        rep = validate_series(s[:-1] + [forming])
        self.assertEqual(rep.incomplete, [len(s) - 1])
        self.assertFalse(rep.ok)
        self.assertTrue(validate_series(s).ok)

    def test_demo_provider_never_emits_future_or_forming_bars(self):
        now = datetime(2026, 3, 4, 17, 0, tzinfo=UTC)   # Wed 12:00 ET: Wed's bar still forming
        cs = DemoProvider(now=now).get_candles("X", Timeframe.D1, datetime(2026, 3, 2, tzinfo=UTC),
                                               datetime(2026, 3, 10, tzinfo=UTC))
        self.assertEqual([c.market_ts.date() for c in cs], [date(2026, 3, 2), date(2026, 3, 3)])
        self.assertTrue(all(cal.bar_close_utc(c.timeframe, c.market_ts) <= now for c in cs))


if __name__ == "__main__":
    unittest.main()
