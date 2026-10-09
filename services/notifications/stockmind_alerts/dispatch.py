"""Delivery engine: idempotency, cooldown, quiet hours, retry with exponential backoff, dead-letter. Pure + injected clock.

Guarantee: AT-LEAST-ONCE delivery with a stable idempotency key (`Delivery.key`) handed to the sender so the provider/DB can
de-duplicate. A crash between a successful send and the status write can still cause one duplicate: that residual window
cannot be closed without an atomic provider acknowledgement and is documented in ADR-0011.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime, time, timedelta, timezone
from enum import Enum
from typing import Callable, Mapping
from zoneinfo import ZoneInfo

from .rules import AlertRule, Channel, Trigger


class DeliveryStatus(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DEAD = "DEAD"          # dead-letter: retries exhausted or permanent failure
    SKIPPED = "SKIPPED"    # channel not configured: visible to operators, never silently lost


class PermanentDeliveryError(Exception):
    """Raise from a sender when retrying cannot help (e.g. invalid chat id, unsubscribed address)."""


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time
    tz: str

    def __post_init__(self) -> None:
        ZoneInfo(self.tz)  # raises on unknown zone
        if self.start == self.end:
            raise ValueError("start and end must differ (an empty/24h window is ambiguous)")

    def _local(self, utc_dt: datetime) -> datetime:
        if utc_dt.tzinfo is None:
            raise ValueError("naive datetimes are not accepted")
        return utc_dt.astimezone(ZoneInfo(self.tz))

    def contains(self, utc_dt: datetime) -> bool:
        t = self._local(utc_dt).time()
        return (self.start <= t < self.end) if self.start < self.end else (t >= self.start or t < self.end)

    def next_end(self, utc_dt: datetime) -> datetime:
        """First instant strictly after `utc_dt` at which the quiet window ends (local wall-clock, DST-aware)."""
        zone = ZoneInfo(self.tz)
        local = self._local(utc_dt)
        for day_offset in (0, 1, 2):
            cand = datetime.combine(local.date() + timedelta(days=day_offset), self.end, tzinfo=zone).astimezone(timezone.utc)
            if cand > utc_dt:
                return cand
        raise AssertionError("unreachable")


@dataclass(frozen=True)
class Delivery:
    key: str                       # idempotency key: "<rule>:<bar_ts>|<channel>"
    event_key: str
    rule_id: str
    user_id: str
    channel: Channel
    reason: str                    # the "why" shown to the user
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: int = 0
    next_attempt_at: datetime | None = None
    last_error: str | None = None
    created_at: datetime | None = None
    evidence: tuple = ()


Sender = Callable[[Delivery], None]


class Dispatcher:
    def __init__(self, senders: Mapping[Channel, Sender], max_attempts: int = 5, base_delay: timedelta = timedelta(seconds=30),
                 max_delay: timedelta = timedelta(hours=1), quiet: Mapping[str, QuietHours] | None = None) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self.senders, self.max_attempts, self.base_delay, self.max_delay = dict(senders), max_attempts, base_delay, max_delay
        self.quiet = dict(quiet or {})
        self.deliveries: dict[str, Delivery] = {}
        self._events: set[str] = set()
        self._last_fired: dict[str, datetime] = {}
        self.suppressed: list[tuple[str, str]] = []     # (event_key, reason): observability for "why didn't I get an alert"

    # ---- submission -------------------------------------------------------------------
    def submit(self, rule: AlertRule, trigger: Trigger, now: datetime) -> list[Delivery]:
        if trigger.rule_id != rule.id:
            raise ValueError("trigger does not belong to this rule")
        if not rule.enabled:
            self.suppressed.append((trigger.event_key, "disabled"))
            return []
        if trigger.event_key in self._events:                       # idempotent: same bar/signal never alerts twice
            self.suppressed.append((trigger.event_key, "duplicate_event"))
            return []
        last = self._last_fired.get(rule.id)
        if last is not None and now - last < rule.cooldown:
            self.suppressed.append((trigger.event_key, "cooldown"))
            return []
        self._events.add(trigger.event_key)
        self._last_fired[rule.id] = now
        out = []
        for ch in rule.channels:
            d = Delivery(f"{trigger.event_key}|{ch.value}", trigger.event_key, rule.id, rule.user_id, ch, trigger.reason,
                         next_attempt_at=self._after_quiet(rule.user_id, ch, now), created_at=now, evidence=trigger.evidence)
            self.deliveries[d.key] = d
            out.append(d)
        return out

    def _after_quiet(self, user_id: str, ch: Channel, at: datetime) -> datetime:
        q = self.quiet.get(user_id)
        if ch is Channel.IN_APP or q is None or not q.contains(at):   # in-app is never interruptive: exempt
            return at
        return q.next_end(at)

    # ---- processing -------------------------------------------------------------------
    def _backoff(self, key: str, attempts: int) -> timedelta:
        raw = min(self.max_delay, self.base_delay * (2 ** (attempts - 1)))
        h = int.from_bytes(hashlib.sha256(f"{key}:{attempts}".encode()).digest()[:4], "big") / 2 ** 32
        return raw * (0.9 + 0.2 * h)                               # deterministic +-10% jitter (no thundering herd, testable)

    def run_due(self, now: datetime) -> list[Delivery]:
        due = sorted((d for d in self.deliveries.values()
                      if d.status is DeliveryStatus.PENDING and d.next_attempt_at is not None and d.next_attempt_at <= now),
                     key=lambda d: (d.next_attempt_at, d.key))
        done = []
        for d in due:
            sender = self.senders.get(d.channel)
            if sender is None:
                d = replace(d, status=DeliveryStatus.SKIPPED, last_error="channel not configured")
            else:
                deferred = self._after_quiet(d.user_id, d.channel, now)
                if deferred > now:                                  # quiet hours began since scheduling: defer, do not burn an attempt
                    d = replace(d, next_attempt_at=deferred)
                    self.deliveries[d.key] = d
                    continue
                d = self._attempt(d, sender, now)
            self.deliveries[d.key] = d
            done.append(d)
        return done

    def _attempt(self, d: Delivery, sender: Sender, now: datetime) -> Delivery:
        attempts = d.attempts + 1
        try:
            sender(replace(d, attempts=attempts))
            return replace(d, status=DeliveryStatus.SENT, attempts=attempts, next_attempt_at=None, last_error=None)
        except PermanentDeliveryError as e:
            return replace(d, status=DeliveryStatus.DEAD, attempts=attempts, next_attempt_at=None, last_error=self._err(e))
        except Exception as e:  # noqa: BLE001 - any sender failure is retried
            if attempts >= self.max_attempts:
                return replace(d, status=DeliveryStatus.DEAD, attempts=attempts, next_attempt_at=None, last_error=self._err(e))
            return replace(d, attempts=attempts, next_attempt_at=now + self._backoff(d.key, attempts), last_error=self._err(e))

    @staticmethod
    def _err(e: Exception) -> str:
        return f"{type(e).__name__}: {str(e)[:200]}"                # bounded; senders must not put secrets in messages

    def stats(self) -> dict[str, int]:
        out = {s.value: 0 for s in DeliveryStatus}
        for d in self.deliveries.values():
            out[d.status.value] += 1
        return out
