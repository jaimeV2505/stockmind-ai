"""Alpaca Market Data v2 DAILY-bars adapter (stdlib only, injectable transport). See ADR-0013.

HONESTY NOTE: written against Alpaca's documented response shape from memory and verified ONLY against fixtures in the test-suite.
The first real call may reveal differences: every deviation fails LOUDLY (ProviderDataError) instead of being "fixed up" silently.

Behaviour guarantees (each tested):
- Missing credentials => ProviderConfigError before any request. No fallback to simulated data, ever.
- Daily bar stamps must be midnight US/Eastern; they are re-stamped to the session OPEN (09:30 ET) as the Candle contract requires (audit H-7).
- Bars of sessions that have not closed yet are DROPPED and counted (audit H-4), never returned as complete.
- Bars on non-trading days, duplicates, non-finite / inconsistent OHLC, wrong symbol echo => ProviderDataError (no partial/guessed data).
- 429/5xx/network errors retry with exponential backoff (Retry-After honoured, capped); 401/403 never retry; redirects are refused;
  only https://data.alpaca.markets is allowed; response size is capped; secrets are only ever sent as headers and never put in error text.
"""
from __future__ import annotations

import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timezone
from typing import Callable, Mapping, Sequence

from .calendar import is_trading_day, session_close_utc, session_open_utc, to_market_time
from .models import AdjustmentStatus, Candle, DataMode, Timeframe

ALLOWED_HOSTS = frozenset({"data.alpaca.markets"})
MAX_BODY = 5_000_000
_SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,9}$")
_ADJUSTMENTS = {"raw": AdjustmentStatus.RAW, "split": AdjustmentStatus.SPLIT_ADJUSTED, "all": AdjustmentStatus.FULLY_ADJUSTED}


class ProviderError(Exception):
    """Base class. Messages never contain credentials."""


class ProviderConfigError(ProviderError):
    pass


class ProviderAuthError(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


class ProviderDataError(ProviderError):
    pass


Transport = Callable[[str, Mapping[str, str]], "tuple[int, Mapping[str, str], bytes]"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):  # noqa: D401 - refuse to follow redirects (could leave the allowed host)
        return None


def urllib_transport(url: str, headers: Mapping[str, str], timeout: float = 20.0) -> tuple[int, Mapping[str, str], bytes]:
    opener = urllib.request.build_opener(_NoRedirect)
    req = urllib.request.Request(url, headers=dict(headers))
    try:
        with opener.open(req, timeout=timeout) as r:
            return r.status, {k.lower(): v for k, v in r.headers.items()}, r.read(MAX_BODY + 1)
    except urllib.error.HTTPError as e:
        return e.code, {k.lower(): v for k, v in (e.headers or {}).items()}, e.read(10_000)


def _reject_constant(c: str):
    raise ProviderDataError(f"non-standard JSON constant {c} in provider response")


class AlpacaDailyBars:
    provider_id = "alpaca"
    is_simulated = False

    def __init__(self, key_id: str | None, secret: str | None, feed: str = "iex", adjustment: str = "split", exchange: str = "US",
                 transport: Transport | None = None, clock: Callable[[], datetime] | None = None,
                 sleep: Callable[[float], None] = time.sleep, base_url: str = "https://data.alpaca.markets",
                 max_retries: int = 4, max_pages: int = 50) -> None:
        if not key_id or not secret:
            raise ProviderConfigError("Alpaca credentials missing: set ALPACA_API_KEY and ALPACA_API_SECRET (no simulated fallback exists)")
        if feed not in ("iex", "sip"):
            raise ValueError("feed must be 'iex' or 'sip'")
        if adjustment not in _ADJUSTMENTS:
            raise ValueError(f"adjustment must be one of {sorted(_ADJUSTMENTS)}")
        u = urllib.parse.urlsplit(base_url)
        if u.scheme != "https" or u.hostname not in ALLOWED_HOSTS or u.username or u.port not in (None, 443):
            raise ProviderConfigError("base_url must be https://data.alpaca.markets")
        self.feed, self.adjustment, self.exchange = feed, adjustment, exchange
        self.source = f"alpaca-{feed}"
        self._base = f"https://{u.hostname}"
        self._headers = {"APCA-API-KEY-ID": key_id, "APCA-API-SECRET-KEY": secret, "Accept": "application/json"}
        self._transport = transport or urllib_transport
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._sleep, self._max_retries, self._max_pages = sleep, max_retries, max_pages
        self.last_dropped_forming = 0

    # ---- HTTP ---------------------------------------------------------------------------------------------------------------
    def _get(self, url: str) -> bytes:
        last = "unknown error"
        for attempt in range(self._max_retries + 1):
            retry_after = None
            try:
                status, headers, body = self._transport(url, self._headers)
            except (OSError, TimeoutError) as e:
                last = f"network error {type(e).__name__}"
            else:
                if status == 200:
                    if len(body) > MAX_BODY:
                        raise ProviderDataError("response larger than the allowed maximum")
                    return body
                if status in (401, 403):
                    raise ProviderAuthError(f"HTTP {status}: credentials rejected or not entitled to feed '{self.feed}'")
                if 300 <= status < 400:
                    raise ProviderDataError(f"unexpected redirect (HTTP {status}) refused")
                if status != 429 and status < 500:
                    raise ProviderError(f"HTTP {status} from provider")
                last = f"HTTP {status}"
                ra = {k.lower(): v for k, v in headers.items()}.get("retry-after", "")
                retry_after = float(ra) if ra.strip().isdigit() else None
            if attempt == self._max_retries:
                raise ProviderUnavailable(f"provider unavailable after {self._max_retries + 1} attempts ({last})")
            self._sleep(min(60.0, retry_after if retry_after is not None else min(30.0, 2.0 ** attempt)))
        raise AssertionError("unreachable")

    # ---- public API -----------------------------------------------------------------------------------------------------------
    def get_candles(self, symbol: str, timeframe: Timeframe, start: datetime, end: datetime) -> Sequence[Candle]:
        """`start`/`end` are INSTANTS (tz-aware). A session is included when its New York trading date lies between the New York dates of
        start and end, so `end=2026-10-09T00:00Z` (= Oct 8, 20:00 ET) excludes Oct 9: pass a time late in the day, or `now`."""
        if timeframe is not Timeframe.D1:
            raise NotImplementedError("AlpacaDailyBars supports 1d only")
        if not _SYMBOL.match(symbol):
            raise ValueError(f"invalid symbol {symbol!r}")
        if start.tzinfo is None or end.tzinfo is None or end < start:
            raise ValueError("start/end must be timezone-aware with end >= start")
        first, last = to_market_time(start).date(), to_market_time(end).date()
        now = self._clock()
        raw: list[Mapping] = []
        token, seen = None, set()
        for _ in range(self._max_pages):
            q = {"timeframe": "1Day", "start": start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                 "end": end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "adjustment": self.adjustment,
                 "feed": self.feed, "limit": "10000", "sort": "asc"}
            if token:
                q["page_token"] = token
            doc = self._json(self._get(f"{self._base}/v2/stocks/{urllib.parse.quote(symbol)}/bars?{urllib.parse.urlencode(q)}"))
            if "symbol" in doc and doc["symbol"] != symbol:
                raise ProviderDataError(f"provider answered for {doc['symbol']!r}, expected {symbol!r}")
            bars = doc.get("bars")
            if bars is not None and not isinstance(bars, list):
                raise ProviderDataError("'bars' must be a list or null")
            raw.extend(bars or [])
            token = doc.get("next_page_token")
            if not token:
                break
            if token in seen:
                raise ProviderDataError("pagination loop detected")
            seen.add(token)
        else:
            raise ProviderDataError(f"more than {self._max_pages} pages: refusing to continue")
        out, dropped, days = [], 0, set()
        for b in raw:
            c = self._bar(b, symbol, now)
            d = to_market_time(c[0]).date() if c else None
            if c is None:
                dropped += 1
                continue
            if d in days:
                raise ProviderDataError(f"{symbol}: duplicate daily bar for {d}")
            days.add(d)
            if first <= d <= last:
                out.append(c[1])
        self.last_dropped_forming = dropped
        return sorted(out, key=lambda x: x.market_ts)

    # ---- parsing ----------------------------------------------------------------------------------------------------------------
    @staticmethod
    def _json(body: bytes) -> Mapping:
        try:
            doc = json.loads(body.decode("utf-8"), parse_constant=_reject_constant)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise ProviderDataError(f"response is not valid JSON ({type(e).__name__})") from e
        if not isinstance(doc, dict):
            raise ProviderDataError("response must be a JSON object")
        return doc

    def _bar(self, b: Mapping, symbol: str, now: datetime):
        """Returns (stamp, Candle), or None for a session that has not closed yet. Raises ProviderDataError on anything odd."""
        if not isinstance(b, dict):
            raise ProviderDataError(f"{symbol}: bar is not an object")
        try:
            ts = datetime.fromisoformat(str(b["t"]).replace("Z", "+00:00"))
            vals = [b[k] for k in ("o", "h", "l", "c", "v")]
        except (KeyError, ValueError) as e:
            raise ProviderDataError(f"{symbol}: malformed bar ({type(e).__name__}: {e})") from e
        if ts.tzinfo is None:
            raise ProviderDataError(f"{symbol}: bar timestamp has no timezone")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in vals):
            raise ProviderDataError(f"{symbol}: non-numeric or non-finite OHLCV in bar {b['t']}")
        local = to_market_time(ts)
        if (local.hour, local.minute, local.second) != (0, 0, 0):
            raise ProviderDataError(f"{symbol}: daily bar stamped {b['t']} is not midnight US/Eastern: provider convention changed, refusing to guess the date")
        d: date = local.date()
        if not is_trading_day(d):
            raise ProviderDataError(f"{symbol}: bar on non-trading day {d}")
        if session_close_utc(d) > now:
            return None                                                # still forming: never presented as complete
        o, h, l, c, v = (float(x) for x in vals)
        try:
            candle = Candle(symbol, self.exchange, Timeframe.D1, session_open_utc(d), now, self.source, "USD",
                            _ADJUSTMENTS[self.adjustment], DataMode.HISTORICAL, o, h, l, c, v)
        except ValueError as e:
            raise ProviderDataError(f"{symbol} {d}: {e}") from e
        return ts, candle
