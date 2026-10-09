import json
import unittest
from datetime import date, datetime, time, timezone
from urllib.parse import parse_qs, urlsplit

from stockmind_marketdata import (
    AlpacaDailyBars, DataMode, ProviderAuthError, ProviderConfigError, ProviderDataError, ProviderError, ProviderUnavailable,
    Timeframe, trading_days, validate_series,
)
from stockmind_marketdata.calendar import ET, session_open_utc

UTC = timezone.utc
NOW = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)         # after Friday's close
START, END = datetime(2026, 9, 1, tzinfo=UTC), datetime(2026, 10, 9, 23, tzinfo=UTC)   # END is an INSTANT: 19:00 ET on Friday Oct 9


def stamp(d: date) -> str:
    """Alpaca-style daily stamp: midnight US/Eastern expressed in UTC."""
    return datetime.combine(d, time(0), tzinfo=ET).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def bar(d: date, base: float = 100.0, **over):
    b = {"t": stamp(d), "o": base, "h": base + 2, "l": base - 1, "c": base + 1, "v": 1_000_000, "n": 5000, "vw": base}
    b.update(over)
    return b


def days(a=date(2026, 9, 1), z=date(2026, 10, 9)):
    return trading_days(a, z)


class FakeTransport:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, url, headers):
        self.calls.append((url, dict(headers)))
        r = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(r, Exception):
            raise r
        return r


def ok(bars, token=None, symbol="AAPL"):
    return 200, {}, json.dumps({"bars": bars, "symbol": symbol, "next_page_token": token}).encode()


def provider(*responses, **kw):
    slept = []
    t = FakeTransport(*responses)
    p = AlpacaDailyBars("KEY123", "SECRET456", transport=t, clock=lambda: NOW, sleep=slept.append, **kw)
    return p, t, slept


class TestConfig(unittest.TestCase):
    def test_missing_credentials_fail_before_any_request(self):
        for k, s in ((None, "x"), ("x", None), ("", "x"), ("x", "")):
            with self.assertRaises(ProviderConfigError):
                AlpacaDailyBars(k, s, transport=FakeTransport(ok([])))

    def test_only_the_official_https_host_is_allowed(self):
        for url in ("http://data.alpaca.markets", "https://evil.example.com", "https://data.alpaca.markets:8443", "https://user@data.alpaca.markets",
                    "https://data.alpaca.markets.evil.com"):
            with self.subTest(url=url), self.assertRaises(ProviderConfigError):
                AlpacaDailyBars("k", "s", base_url=url)
        for kw in (dict(feed="otc"), dict(adjustment="dividend")):
            with self.assertRaises(ValueError):
                AlpacaDailyBars("k", "s", **kw)

    def test_only_daily_bars_and_valid_symbols(self):
        p, t, _ = provider(ok([]))
        with self.assertRaises(NotImplementedError):
            p.get_candles("AAPL", Timeframe.M5, START, END)
        for bad in ("aapl", "", "AA PL", "A/B", "../x"):
            with self.assertRaises(ValueError):
                p.get_candles(bad, Timeframe.D1, START, END)
        with self.assertRaises(ValueError):
            p.get_candles("AAPL", Timeframe.D1, datetime(2026, 1, 1), END)
        self.assertEqual(t.calls, [])


class TestRequestAndMapping(unittest.TestCase):
    def test_request_shape_and_secrets_only_in_headers(self):
        p, t, _ = provider(ok([bar(d) for d in days()]))
        p.get_candles("AAPL", Timeframe.D1, START, END)
        (url, headers), = t.calls
        u = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.assertEqual((u.scheme, u.hostname, u.path), ("https", "data.alpaca.markets", "/v2/stocks/AAPL/bars"))
        self.assertEqual((q["timeframe"], q["feed"], q["adjustment"], q["sort"], q["limit"]), ("1Day", "iex", "split", "asc", "10000"))
        self.assertEqual(q["start"], "2026-09-01T00:00:00Z")
        self.assertEqual((headers["APCA-API-KEY-ID"], headers["APCA-API-SECRET-KEY"]), ("KEY123", "SECRET456"))
        self.assertNotIn("KEY123", url)
        self.assertNotIn("SECRET456", url)

    def test_bars_become_valid_session_open_candles(self):
        ds = days()
        p, _, _ = provider(ok([bar(d, 100 + i) for i, d in enumerate(ds)]))
        cs = p.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual(len(cs), len(ds))
        for c, d in zip(cs, ds):
            self.assertEqual(c.market_ts, session_open_utc(d))              # re-stamped to 09:30 ET (DST-aware)
            self.assertEqual((c.source, c.data_mode, c.exchange, c.currency), ("alpaca-iex", DataMode.HISTORICAL, "US", "USD"))
            self.assertEqual(c.ingested_at, NOW)
        self.assertTrue(validate_series(cs).ok, validate_series(cs))          # passes our own quality gate
        self.assertEqual(p.last_dropped_forming, 0)

    def test_dst_stamps_map_to_the_right_session(self):
        for d in (date(2026, 3, 6), date(2026, 3, 9), date(2026, 11, 2), date(2026, 11, 6)):   # around both 2026 DST changes
            p = AlpacaDailyBars("k", "s", transport=FakeTransport(ok([bar(d)])), clock=lambda: datetime(2026, 12, 1, tzinfo=UTC), sleep=lambda s: None)
            (c,) = p.get_candles("AAPL", Timeframe.D1, datetime(2026, 3, 1, tzinfo=UTC), datetime(2026, 11, 8, 23, tzinfo=UTC))
            self.assertEqual(c.market_ts, session_open_utc(d), d)
        self.assertEqual(stamp(date(2026, 3, 6)), "2026-03-06T05:00:00Z")
        self.assertEqual(stamp(date(2026, 3, 9)), "2026-03-09T04:00:00Z")

    def test_feed_and_adjustment_are_reflected_in_the_candle_labels(self):
        p, _, _ = provider(ok([bar(date(2026, 10, 8))]), feed="sip", adjustment="all")
        (c,) = p.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual((c.source, c.adjustment.value), ("alpaca-sip", "fully_adjusted"))

    def test_empty_result_is_empty_not_an_error(self):
        p, _, _ = provider((200, {}, b'{"bars": null, "symbol": "AAPL", "next_page_token": null}'))
        self.assertEqual(p.get_candles("AAPL", Timeframe.D1, START, END), [])

    def test_pagination_collects_every_page_and_detects_loops(self):
        ds = days()
        a, b = ds[:10], ds[10:]
        p, t, _ = provider(ok([bar(d) for d in a], token="p2"), ok([bar(d) for d in b]))
        self.assertEqual(len(p.get_candles("AAPL", Timeframe.D1, START, END)), len(ds))
        self.assertIn("page_token=p2", t.calls[1][0])
        loop, _, _ = provider(ok([bar(ds[0])], token="same"), ok([bar(ds[1])], token="same"))
        with self.assertRaisesRegex(ProviderDataError, "pagination loop"):
            loop.get_candles("AAPL", Timeframe.D1, START, END)
        endless, _, _ = provider(*[ok([bar(ds[i])], token=f"t{i}") for i in range(5)], max_pages=3)
        with self.assertRaisesRegex(ProviderDataError, "pages"):
            endless.get_candles("AAPL", Timeframe.D1, START, END)


class TestCompleteness(unittest.TestCase):
    def test_a_forming_session_is_dropped_and_counted(self):
        midday = datetime(2026, 10, 9, 17, 0, tzinfo=UTC)                  # 13:00 ET Friday: session still open
        t = FakeTransport(ok([bar(d) for d in days()]))
        p = AlpacaDailyBars("k", "s", transport=t, clock=lambda: midday, sleep=lambda s: None)
        cs = p.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual(cs[-1].market_ts, session_open_utc(date(2026, 10, 8)))
        self.assertEqual(p.last_dropped_forming, 1)
        self.assertTrue(validate_series(cs).ok)

    def test_end_is_an_instant_not_a_calendar_date(self):
        # 2026-10-09T00:00Z is still Oct 8 in New York, so Friday's session is (correctly) outside the window
        ds = days()
        p, _, _ = provider(ok([bar(d) for d in ds]))
        cs = p.get_candles("AAPL", Timeframe.D1, START, datetime(2026, 10, 9, tzinfo=UTC))
        self.assertEqual(cs[-1].market_ts, session_open_utc(date(2026, 10, 8)))

    def test_results_are_filtered_to_the_requested_window_and_sorted(self):
        ds = days()
        p, _, _ = provider(ok([bar(d) for d in reversed(ds)]))
        cs = p.get_candles("AAPL", Timeframe.D1, datetime(2026, 9, 14, tzinfo=UTC), datetime(2026, 9, 18, 23, tzinfo=UTC))
        self.assertEqual([c.market_ts for c in cs], [session_open_utc(d) for d in trading_days(date(2026, 9, 14), date(2026, 9, 18))])


class TestFailLoudly(unittest.TestCase):
    def assertRejects(self, bars, msg, **kw):
        p, _, _ = provider(ok(bars), **kw)
        with self.assertRaisesRegex(ProviderDataError, msg):
            p.get_candles("AAPL", Timeframe.D1, START, END)

    def test_bad_bars_are_rejected_not_repaired(self):
        d = date(2026, 10, 8)
        self.assertRejects([bar(date(2026, 9, 5))], "non-trading day")                       # Saturday
        self.assertRejects([bar(date(2026, 9, 7))], "non-trading day")                       # Labor Day
        self.assertRejects([bar(d), bar(d)], "duplicate")
        self.assertRejects([bar(d, h=90.0)], "high must be")                                  # high below low
        self.assertRejects([bar(d, c=-1.0)], "positive|low must|high must")
        self.assertRejects([bar(d, v=-5)], "volume")
        self.assertRejects([bar(d, o="100")], "non-numeric")
        self.assertRejects([bar(d, o=True)], "non-numeric")
        self.assertRejects([{"t": stamp(d), "o": 1, "h": 2, "l": 1, "c": 1}], "malformed")     # no volume
        self.assertRejects([{"o": 1}], "malformed")
        self.assertRejects(["junk"], "not an object")
        self.assertRejects([bar(d, t="2026-10-08T13:30:00Z")], "not midnight")                 # intraday-style stamp: convention changed
        self.assertRejects([bar(d, t="2026-10-08T00:00:00")], "no timezone")
        self.assertRejects([bar(d, t="garbage")], "malformed")

    def test_structural_garbage(self):
        for body, msg in ((b"not json", "valid JSON"), (b"[]", "JSON object"), (b'{"bars": 5}', "list or null"), (b'{"bars":[{"t":"x","o":NaN}]}', "non-standard JSON constant"),
                          (b'{"bars":[], "symbol":"MSFT"}', "expected 'AAPL'"), (b"\xff\xfe", "valid JSON")):
            p, _, _ = provider((200, {}, body))
            with self.subTest(body=body[:20]), self.assertRaisesRegex(ProviderDataError, msg):
                p.get_candles("AAPL", Timeframe.D1, START, END)

    def test_oversized_body_rejected(self):
        p, _, _ = provider((200, {}, b" " * 5_000_001))
        with self.assertRaisesRegex(ProviderDataError, "larger"):
            p.get_candles("AAPL", Timeframe.D1, START, END)


class TestRetries(unittest.TestCase):
    def test_429_then_success_honours_retry_after(self):
        ds = days()
        p, t, slept = provider((429, {"Retry-After": "7"}, b""), ok([bar(d) for d in ds]))
        self.assertEqual(len(p.get_candles("AAPL", Timeframe.D1, START, END)), len(ds))
        self.assertEqual((len(t.calls), slept), (2, [7.0]))

    def test_5xx_and_network_errors_back_off_exponentially_then_give_up(self):
        slept = []
        tr = FakeTransport((503, {}, b""))
        p = AlpacaDailyBars("k", "s", transport=tr, clock=lambda: NOW, sleep=slept.append, max_retries=3)
        with self.assertRaises(ProviderUnavailable) as cm:
            p.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual((len(tr.calls), slept), (4, [1.0, 2.0, 4.0]))
        self.assertNotIn("SECRET", str(cm.exception))
        net = FakeTransport(TimeoutError("slow"))
        with self.assertRaises(ProviderUnavailable):
            AlpacaDailyBars("k", "s", transport=net, clock=lambda: NOW, sleep=lambda s: None, max_retries=1).get_candles("AAPL", Timeframe.D1, START, END)

    def test_auth_and_client_errors_never_retry(self):
        for status, exc in ((401, ProviderAuthError), (403, ProviderAuthError), (400, ProviderError), (404, ProviderError), (422, ProviderError)):
            p, t, slept = provider((status, {}, b'{"message":"nope"}'))
            with self.subTest(status=status), self.assertRaises(exc) as cm:
                p.get_candles("AAPL", Timeframe.D1, START, END)
            self.assertEqual((len(t.calls), slept), (1, []))
            self.assertNotIn("SECRET456", str(cm.exception))

    def test_redirects_are_refused_and_retry_after_is_clamped(self):
        p, t, _ = provider((302, {"Location": "https://evil.example.com"}, b""))
        with self.assertRaisesRegex(ProviderDataError, "redirect"):
            p.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual(len(t.calls), 1)
        p2, _, slept = provider((429, {"retry-after": "99999"}, b""), ok([]))
        p2.get_candles("AAPL", Timeframe.D1, START, END)
        self.assertEqual(slept, [60.0])


if __name__ == "__main__":
    unittest.main()
