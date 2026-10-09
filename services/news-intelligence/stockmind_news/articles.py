"""News article model, URL canonicalisation (+ SSRF-style rejection), de-duplication, ticker association, event heuristics.

NOTE: URL checks are LEXICAL. DNS rebinding / hostnames that resolve to private addresses are NOT detectable offline;
any fetcher must additionally resolve and re-check the IP at connection time (ADR-0011).
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping, Sequence
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING = re.compile(r"^(utm_.*|fbclid|gclid|dclid|msclkid|mc_cid|mc_eid|igshid|yclid|_hsenc|_hsmi)$", re.I)
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".lan", ".home", ".corp", ".intranet")


def canonical_url(url: str) -> str:
    if not isinstance(url, str) or not url.strip() or len(url) > 2048:
        raise ValueError("url must be a non-empty string up to 2048 characters")
    try:
        p = urlsplit(url.strip())
        port = p.port
    except ValueError as e:
        raise ValueError(f"malformed url: {e}") from e
    if p.scheme.lower() not in ("http", "https"):
        raise ValueError("only http/https urls are accepted")
    if p.username is not None or p.password is not None or "@" in p.netloc:
        raise ValueError("urls with embedded credentials are rejected")
    host = (p.hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError("url has no host")
    if port not in (None, 80, 443):
        raise ValueError("non-standard ports are rejected")
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES) or "." not in host and ":" not in host:
        raise ValueError("internal hostnames are rejected")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if re.fullmatch(r"[0-9a-fx.]+", host):                       # decimal/octal/hex IPv4 tricks such as 2130706433, 0x7f.1
            raise ValueError("numeric host forms are rejected") from None
    else:
        if not ip.is_global:
            raise ValueError("non-public IP addresses are rejected")
    q = sorted((k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not _TRACKING.match(k))
    path = re.sub(r"/{2,}", "/", p.path) or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    netloc = host if ":" not in host else f"[{host}]"
    return urlunsplit((p.scheme.lower(), netloc, path, urlencode(q), ""))


@dataclass(frozen=True)
class Article:
    title: str
    source: str
    url: str
    published_at: datetime       # when the publisher says it was published
    ingested_at: datetime        # when WE received it (never conflate the two)
    body: str = ""
    tickers_hint: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.title.strip() or not self.source.strip():
            raise ValueError("title and source are required (source attribution)")
        for n in ("published_at", "ingested_at"):
            v = getattr(self, n)
            if v.tzinfo is None or v.utcoffset() != timedelta(0):
                raise ValueError(f"{n} must be a timezone-aware UTC datetime")
        if self.ingested_at < self.published_at:
            raise ValueError("an article cannot be ingested before it was published")
        canonical_url(self.url)

    @property
    def canonical(self) -> str:
        return canonical_url(self.url)

    @property
    def id(self) -> str:
        return hashlib.sha256(self.canonical.encode()).hexdigest()[:16]


def normalize_title(title: str) -> tuple[str, ...]:
    t = unicodedata.normalize("NFKC", title).lower()
    return tuple(re.sub(r"[^\w]+", " ", t).split())


def _bigrams(t: tuple[str, ...]) -> set[tuple[str, str]]:
    return set(zip(t, t[1:]))


def _jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a | b else 0.0


def _similar(a: tuple[str, ...], b: tuple[str, ...], threshold: float) -> bool:
    """Same story iff the word sets overlap strongly AND the word ORDER agrees (bigram overlap).
    Word-set overlap alone merges opposite stories such as 'Apple sues Google' / 'Google sues Apple'."""
    if not a or not b:
        return False
    if min(len(a), len(b)) < 4:
        return a == b                                            # short titles: exact match only (avoid false merges)
    return _jaccard(set(a), set(b)) >= threshold and _jaccard(_bigrams(a), _bigrams(b)) >= 0.5


@dataclass(frozen=True)
class DedupResult:
    kept: tuple[Article, ...]
    duplicates: dict[str, str]                 # duplicate article id -> kept article id
    also_reported_by: dict[str, tuple[str, ...]]  # kept id -> other sources carrying the same story


def dedupe(articles: Sequence[Article], window: timedelta = timedelta(hours=48), threshold: float = 0.8) -> DedupResult:
    kept: list[Article] = []
    dups: dict[str, str] = {}
    extra: dict[str, set[str]] = {}
    for a in sorted(articles, key=lambda x: (x.published_at, x.canonical, x.title)):   # deterministic, input-order independent
        target = None
        for k in kept:
            same_url = a.canonical == k.canonical
            same_story = abs(a.published_at - k.published_at) <= window and _similar(
                normalize_title(a.title), normalize_title(k.title), threshold)
            if same_url or same_story:
                target = k
                break
        if target is None:
            kept.append(a)
        else:
            dups[a.id] = target.id
            if a.source != target.source:
                extra.setdefault(target.id, set()).add(a.source)
    return DedupResult(tuple(kept), dups, {k: tuple(sorted(v)) for k, v in extra.items()})


@dataclass(frozen=True)
class TickerMatch:
    symbol: str
    via: str          # "cashtag" | "hint" | "alias"
    evidence: str


_CASHTAG = re.compile(r"(?<![A-Za-z0-9$])\$([A-Z]{1,5}(?:\.[A-Z])?)(?![A-Za-z0-9])")


def associate(article: Article, universe: Mapping[str, Sequence[str]]) -> list[TickerMatch]:
    """Link an article to symbols in `universe` (symbol -> company-name aliases). Never invents a symbol outside the universe;
    bare upper-case words (e.g. 'IT', 'A') are NOT treated as tickers."""
    text = f"{article.title}\n{article.body}"
    found: dict[str, TickerMatch] = {}
    for m in _CASHTAG.finditer(text):
        if m.group(1) in universe:
            found.setdefault(m.group(1), TickerMatch(m.group(1), "cashtag", m.group(0)))
    for h in article.tickers_hint:
        if h in universe:
            found.setdefault(h, TickerMatch(h, "hint", h))
    for sym, aliases in universe.items():
        if sym in found:
            continue
        for al in aliases:
            if len(al.strip()) >= 4 and re.search(rf"(?<!\w){re.escape(al.strip())}(?!\w)", text, re.I):
                found[sym] = TickerMatch(sym, "alias", al)
                break
    return [found[s] for s in sorted(found)]


_EVENT_RULES = {
    "earnings": r"\b(earnings|quarterly results|q[1-4] results|eps|guidance|revenue (beat|miss))\b",
    "merger_acquisition": r"\b(acquire[sd]?|acquisition|merger|takeover|buyout|to buy)\b",
    "regulatory": r"\b(sec|ftc|doj|antitrust|investigation|lawsuit|fine[sd]?|regulator|subpoena|approval)\b",
    "executive_change": r"\b(ceo|cfo|coo|chairman|steps? down|resigns?|appoint(s|ed)?|names new)\b",
    "product": r"\b(launch(es|ed)?|unveil(s|ed)?|announces? new|releases?)\b",
    "macro": r"\b(fed|fomc|inflation|cpi|interest rates?|jobs report|gdp|tariffs?)\b",
}


def classify_events(article: Article) -> tuple[str, ...]:
    """HEURISTIC keyword labels (deterministic, no LLM). Treat as hints, not facts."""
    text = f"{article.title} {article.body}".lower()
    return tuple(sorted(k for k, rx in _EVENT_RULES.items() if re.search(rx, text)))
