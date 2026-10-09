"""Point-in-time fundamentals. Every fact carries BOTH the period it describes and the moment it became public (`filed_at`).
A query "as of ts" only ever sees facts with filed_at <= ts: restatements are invisible until filed (no look-ahead).

Three distinct non-values, never conflated with a number:
  UNAVAILABLE     - source reported nothing / no filing yet            (NOT zero, NOT negative)
  NOT_MEANINGFUL  - the ratio is mathematically defined but economically meaningless (P/E of a loss-maker, growth off a <=0 base)
  OK              - a real value, which may legitimately be NEGATIVE (e.g. net loss)
Source attribution (`source`) is mandatory; the engine never fills a missing metric.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Mapping


class Status(str, Enum):
    OK = "OK"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_MEANINGFUL = "NOT_MEANINGFUL"


@dataclass(frozen=True)
class Fact:
    symbol: str
    metric: str                  # e.g. "revenue", "net_income", "eps"
    value: float | None          # None = reported as not available
    period_end: date
    period_type: str             # "FY" | "Q"
    filed_at: datetime           # UTC: when it became publicly available
    source: str                  # e.g. "SEC EDGAR 10-K 0000320193-26-000012"

    def __post_init__(self) -> None:
        if self.period_type not in ("FY", "Q"):
            raise ValueError("period_type must be 'FY' or 'Q'")
        if not self.symbol or not self.metric or not self.source.strip():
            raise ValueError("symbol, metric and source are required")
        if self.filed_at.tzinfo is None or self.filed_at.utcoffset() != timedelta(0):
            raise ValueError("filed_at must be a timezone-aware UTC datetime")
        if self.filed_at.date() < self.period_end:
            raise ValueError("a filing cannot be published before its period ends")
        if self.value is not None and (isinstance(self.value, bool) or not isinstance(self.value, (int, float)) or not math.isfinite(self.value)):
            raise ValueError("value must be a finite number or None")


@dataclass(frozen=True)
class Reading:
    status: Status
    value: float | None = None
    fact: Fact | None = None
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.status is Status.OK


_UNAVAILABLE = Reading(Status.UNAVAILABLE, note="no data available as of the requested time")


class FactStore:
    def __init__(self) -> None:
        self._facts: dict[tuple[str, str, str], list[Fact]] = {}

    def add(self, fact: Fact) -> None:
        bucket = self._facts.setdefault((fact.symbol, fact.metric, fact.period_type), [])
        if any(f.period_end == fact.period_end and f.filed_at == fact.filed_at for f in bucket):
            raise ValueError("a fact for this period was already filed at exactly this time")
        bucket.append(fact)

    def _visible(self, symbol: str, metric: str, ptype: str, ts: datetime) -> list[Fact]:
        if ts.tzinfo is None:
            raise ValueError("naive datetimes are not accepted")
        return [f for f in self._facts.get((symbol, metric, ptype), []) if f.filed_at <= ts]

    @staticmethod
    def _reading(fact: Fact | None) -> Reading:
        if fact is None:
            return _UNAVAILABLE
        if fact.value is None:
            return Reading(Status.UNAVAILABLE, None, fact, "source reported no value")
        return Reading(Status.OK, float(fact.value), fact)

    def known_at(self, symbol: str, metric: str, period_end: date, ptype: str, ts: datetime) -> Reading:
        """Value of a SPECIFIC period as known at `ts` (latest filing/restatement published by then)."""
        cands = [f for f in self._visible(symbol, metric, ptype, ts) if f.period_end == period_end]
        return self._reading(max(cands, key=lambda f: f.filed_at) if cands else None)

    def latest(self, symbol: str, metric: str, ptype: str, ts: datetime) -> Reading:
        """Most recent period (by period_end) that had been filed by `ts`, with its latest filing as of `ts`."""
        vis = self._visible(symbol, metric, ptype, ts)
        if not vis:
            return _UNAVAILABLE
        end = max(f.period_end for f in vis)
        return self._reading(max((f for f in vis if f.period_end == end), key=lambda f: f.filed_at))


def _prior_year(d: date) -> date:
    try:
        return d.replace(year=d.year - 1)
    except ValueError:                       # Feb 29
        return d.replace(year=d.year - 1, day=28)


def revenue_growth_yoy(store: FactStore, symbol: str, ts: datetime, ptype: str = "FY") -> Reading:
    cur = store.latest(symbol, "revenue", ptype, ts)
    if not cur.ok:
        return Reading(Status.UNAVAILABLE, note=f"latest revenue: {cur.note or cur.status.value}")
    prev = store.known_at(symbol, "revenue", _prior_year(cur.fact.period_end), ptype, ts)
    if not prev.ok:
        return Reading(Status.UNAVAILABLE, note="prior-year revenue not available")
    if prev.value <= 0:
        return Reading(Status.NOT_MEANINGFUL, note="prior-year revenue <= 0")
    return Reading(Status.OK, cur.value / prev.value - 1, cur.fact, f"{cur.fact.period_end} vs {prev.fact.period_end}")


def net_margin(store: FactStore, symbol: str, ts: datetime, ptype: str = "FY") -> Reading:
    ni = store.latest(symbol, "net_income", ptype, ts)
    if not ni.ok:
        return Reading(Status.UNAVAILABLE, note="net income not available")
    rev = store.known_at(symbol, "revenue", ni.fact.period_end, ptype, ts)
    if not rev.ok:
        return Reading(Status.UNAVAILABLE, note="revenue for the same period not available")
    if rev.value <= 0:
        return Reading(Status.NOT_MEANINGFUL, note="revenue <= 0")
    return Reading(Status.OK, ni.value / rev.value, ni.fact, f"period {ni.fact.period_end}")      # negative margins are real values


def pe_ratio(store: FactStore, symbol: str, ts: datetime, price: float, ptype: str = "FY") -> Reading:
    if isinstance(price, bool) or not math.isfinite(price) or price <= 0:
        raise ValueError("price must be a finite number > 0")
    eps = store.latest(symbol, "eps", ptype, ts)
    if not eps.ok:
        return Reading(Status.UNAVAILABLE, note="EPS not available")
    if eps.value <= 0:
        return Reading(Status.NOT_MEANINGFUL, note="EPS <= 0: a P/E would be meaningless (never reported as negative)")
    return Reading(Status.OK, price / eps.value, eps.fact, f"EPS {eps.value} for period {eps.fact.period_end}")


@dataclass(frozen=True)
class ScoreConfig:
    # metric -> (weight, bad_value, good_value); score is linear between bad and good, clamped to [0, 1]. bad/good order sets direction.
    components: Mapping[str, tuple[float, float, float]] = field(default_factory=lambda: {
        "revenue_growth_yoy": (0.35, 0.0, 0.20),
        "net_margin": (0.35, 0.0, 0.20),
        "pe": (0.30, 40.0, 12.0),          # lower is better
    })
    min_weight_available: float = 0.5

    def __post_init__(self) -> None:
        if not self.components or not 0 < self.min_weight_available <= 1:
            raise ValueError("invalid score configuration")
        for name, (w, bad, good) in self.components.items():
            if w <= 0 or bad == good or not all(math.isfinite(x) for x in (w, bad, good)):
                raise ValueError(f"invalid component {name!r}")


@dataclass(frozen=True)
class ScoreResult:
    score: float | None                  # 0..100, or None when evidence is insufficient
    components: tuple[tuple[str, float, float], ...]   # (metric, value, component score 0..1)
    missing: tuple[str, ...]
    explanation: tuple[str, ...]


def fundamental_score(readings: Mapping[str, Reading], cfg: ScoreConfig | None = None) -> ScoreResult:
    cfg = cfg or ScoreConfig()
    total = sum(w for w, _, _ in cfg.components.values())
    used, acc, comps, missing, why = 0.0, 0.0, [], [], []
    for name in sorted(cfg.components):
        w, bad, good = cfg.components[name]
        r = readings.get(name)
        if r is None or r.status is Status.UNAVAILABLE:
            missing.append(name)
            why.append(f"{name}: unavailable ({r.note if r else 'not provided'}); excluded, NOT treated as zero")
            continue
        used += w
        if r.status is Status.NOT_MEANINGFUL:
            comps.append((name, float("nan"), 0.0))
            why.append(f"{name}: not meaningful ({r.note}); scored 0 for this component")
            continue
        s = min(1.0, max(0.0, (r.value - bad) / (good - bad)))
        acc += w * s
        comps.append((name, r.value, s))
        why.append(f"{name}: {r.value:.4g} -> {s:.2f} (0 at {bad:g}, 1 at {good:g}), weight {w:g}")
    if used / total < cfg.min_weight_available:
        why.append(f"only {used / total:.0%} of the weight is available (< {cfg.min_weight_available:.0%}): INSUFFICIENT DATA, no score")
        return ScoreResult(None, tuple(comps), tuple(missing), tuple(why))
    return ScoreResult(100.0 * acc / used, tuple(comps), tuple(missing), tuple(why))
