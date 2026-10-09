"""Server-side entitlement + authorisation rules. FAIL CLOSED: unknown plan/feature/limit => denied.

The numbers below are ILLUSTRATIVE DEFAULTS, not a pricing decision. `None` = unlimited.
Role (authorisation) is deliberately separate from Plan (quota): Plan.ADMIN gives unlimited quotas but NOT admin-endpoint access.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Mapping


class Plan(str, Enum):
    FREE = "FREE"
    PRO = "PRO"
    PREMIUM = "PREMIUM"
    ADMIN = "ADMIN"


class Role(str, Enum):
    USER = "USER"
    ADMIN = "ADMIN"


class EntitlementError(Exception):
    def __init__(self, decision: "Decision") -> None:
        super().__init__(decision.reason)
        self.decision = decision


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str
    limit: int | None = None
    used: int | None = None

    def raise_if_denied(self) -> None:
        if not self.allowed:
            raise EntitlementError(self)


@dataclass(frozen=True)
class Principal:
    user_id: str
    plan: Plan
    role: Role = Role.USER


Limit = int | bool | None
DEFAULT_LIMITS: dict[Plan, dict[str, Limit]] = {
    Plan.FREE:    dict(watchlist_items=10,  active_alerts=3,   backtests_per_day=3,   ai_analyses_per_day=5,
                       history_days=365,  scanner_min_interval_minutes=60, advanced_indicators=False, pattern_intelligence=False, csv_export=False),
    Plan.PRO:     dict(watchlist_items=50,  active_alerts=25,  backtests_per_day=25,  ai_analyses_per_day=50,
                       history_days=1825, scanner_min_interval_minutes=15, advanced_indicators=True,  pattern_intelligence=False, csv_export=True),
    Plan.PREMIUM: dict(watchlist_items=200, active_alerts=100, backtests_per_day=100, ai_analyses_per_day=200,
                       history_days=7300, scanner_min_interval_minutes=5,  advanced_indicators=True,  pattern_intelligence=True,  csv_export=True),
    Plan.ADMIN:   dict(watchlist_items=None, active_alerts=None, backtests_per_day=None, ai_analyses_per_day=None,
                       history_days=None, scanner_min_interval_minutes=1, advanced_indicators=True,  pattern_intelligence=True,  csv_export=True),
}
QUOTA_FEATURES = ("watchlist_items", "active_alerts", "backtests_per_day", "ai_analyses_per_day")
FEATURE_FLAGS = ("advanced_indicators", "pattern_intelligence", "csv_export")


def _limit(plan: Plan | str, feature: str, limits: Mapping[Plan, Mapping[str, Limit]]):
    try:
        p = plan if isinstance(plan, Plan) else Plan(plan)
    except ValueError:
        return False, Decision(False, f"unknown plan {plan!r}")
    if p not in limits or feature not in limits[p]:
        return False, Decision(False, f"no entitlement defined for {feature!r} on {p.value}")
    return True, limits[p][feature]


def check_quota(plan: Plan | str, feature: str, used: int, requested: int = 1,
                limits: Mapping[Plan, Mapping[str, Limit]] = DEFAULT_LIMITS) -> Decision:
    """Would `used + requested` stay within the plan's limit?"""
    if isinstance(used, bool) or isinstance(requested, bool) or used < 0 or requested < 1:
        raise ValueError("used must be >= 0 and requested >= 1")
    ok, lim = _limit(plan, feature, limits)
    if not ok:
        return lim
    if lim is None:
        return Decision(True, "unlimited", None, used)
    if isinstance(lim, bool):
        return Decision(False, f"{feature} is a feature flag, not a quota")
    if used + requested > lim:
        return Decision(False, f"{feature} limit reached ({used}/{lim})", lim, used)
    return Decision(True, "within limit", lim, used)


def require_feature(plan: Plan | str, feature: str, limits: Mapping[Plan, Mapping[str, Limit]] = DEFAULT_LIMITS) -> Decision:
    ok, v = _limit(plan, feature, limits)
    if not ok:
        return v
    if v is True:
        return Decision(True, "enabled")
    return Decision(False, f"{feature} is not included in this plan")  # False, None-as-quota, ints: not a flag => denied


def require_role(principal: Principal, role: Role) -> Decision:
    if not isinstance(principal.role, Role):
        return Decision(False, "invalid role")
    return Decision(principal.role is role, "role ok" if principal.role is role else f"requires role {role.value}")


class UsageMeter:
    """Per-user daily counters (UTC day). `try_consume` is check-and-increment in one step; the persisted version must use an
    atomic conditional UPDATE/INSERT to stay race-free under concurrency (documented in ADR-0011)."""

    def __init__(self, limits: Mapping[Plan, Mapping[str, Limit]] = DEFAULT_LIMITS) -> None:
        self.limits = limits
        self._counts: dict[tuple[str, str, str], int] = {}

    @staticmethod
    def _day(now: datetime) -> str:
        if now.tzinfo is None:
            raise ValueError("naive datetimes are not accepted")
        return now.astimezone(timezone.utc).date().isoformat()

    def used(self, user_id: str, feature: str, now: datetime) -> int:
        return self._counts.get((user_id, feature, self._day(now)), 0)

    def try_consume(self, principal: Principal, feature: str, now: datetime, amount: int = 1) -> Decision:
        d = check_quota(principal.plan, feature, self.used(principal.user_id, feature, now), amount, self.limits)
        if d.allowed:
            k = (principal.user_id, feature, self._day(now))
            self._counts[k] = self._counts.get(k, 0) + amount
        return d

    def next_reset(self, now: datetime) -> datetime:
        d = now.astimezone(timezone.utc).date() + timedelta(days=1)
        return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
