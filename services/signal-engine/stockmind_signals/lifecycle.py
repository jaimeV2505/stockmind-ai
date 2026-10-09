"""Signal lifecycle state machine + idempotency key (framework-free; the DB unique constraint will mirror `key`).

A strategy may return `NoSignal` (explicit "insufficient evidence"); a dashboard must never be padded with invented signals.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from enum import Enum


class Status(str, Enum):
    WATCHING = "WATCHING"
    AWAITING_CONFIRMATION = "AWAITING_CONFIRMATION"
    CONFIRMED = "CONFIRMED"
    INVALIDATED = "INVALIDATED"
    EXPIRED = "EXPIRED"
    CLOSED = "CLOSED"


ALLOWED: dict[Status, frozenset[Status]] = {
    Status.WATCHING: frozenset({Status.AWAITING_CONFIRMATION, Status.INVALIDATED, Status.EXPIRED}),
    Status.AWAITING_CONFIRMATION: frozenset({Status.CONFIRMED, Status.INVALIDATED, Status.EXPIRED}),
    Status.CONFIRMED: frozenset({Status.CLOSED, Status.INVALIDATED}),
    Status.INVALIDATED: frozenset(),
    Status.EXPIRED: frozenset(),
    Status.CLOSED: frozenset(),
}
TERMINAL = frozenset(s for s, nxt in ALLOWED.items() if not nxt)


class IllegalTransition(ValueError):
    pass


def _check_utc(name: str, dt: datetime) -> None:
    if not isinstance(dt, datetime) or dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")


@dataclass(frozen=True)
class Evidence:
    name: str                 # e.g. "rsi14"
    value: float | str
    note: str = ""


@dataclass(frozen=True)
class SignalEvent:
    from_status: Status | None
    to_status: Status
    at: datetime
    reason: str


@dataclass(frozen=True)
class NoSignal:
    symbol: str
    strategy_id: str
    strategy_version: str
    timeframe: str
    as_of: datetime
    reason: str  # why there is no signal / insufficient evidence


@dataclass(frozen=True)
class Signal:
    symbol: str
    strategy_id: str
    strategy_version: str
    timeframe: str
    trigger_ts: datetime
    status: Status
    supporting: tuple[Evidence, ...]
    contradicting: tuple[Evidence, ...] = ()
    events: tuple[SignalEvent, ...] = field(default=())

    @property
    def key(self) -> str:
        """Idempotency key: the same strategy version firing on the same bar for the same symbol is ONE signal."""
        raw = "|".join((self.symbol, self.strategy_id, self.strategy_version, self.timeframe,
                        self.trigger_ts.isoformat()))
        return hashlib.sha256(raw.encode()).hexdigest()

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL


def new_signal(symbol: str, strategy_id: str, strategy_version: str, timeframe: str, trigger_ts: datetime,
               supporting: tuple[Evidence, ...], contradicting: tuple[Evidence, ...] = ()) -> Signal:
    _check_utc("trigger_ts", trigger_ts)
    if not supporting:
        raise ValueError("a signal requires supporting evidence; return NoSignal instead")
    ev = SignalEvent(None, Status.WATCHING, trigger_ts, "created")
    return Signal(symbol, strategy_id, strategy_version, timeframe, trigger_ts, Status.WATCHING,
                  tuple(supporting), tuple(contradicting), (ev,))


def transition(sig: Signal, to: Status, at: datetime, reason: str) -> Signal:
    """Pure function: returns a NEW signal with the event appended; never mutates."""
    _check_utc("at", at)
    if not reason.strip():
        raise ValueError("a transition requires a reason (audit trail)")
    if to not in ALLOWED[sig.status]:
        raise IllegalTransition(f"{sig.status.value} -> {to.value} is not allowed")
    if at < sig.events[-1].at:
        raise ValueError("transition time precedes the previous event")
    return replace(sig, status=to, events=sig.events + (SignalEvent(sig.status, to, at, reason),))


class SignalRegistry:
    """In-memory reference for the persistence contract: add() is idempotent on Signal.key."""

    def __init__(self) -> None:
        self._by_key: dict[str, Signal] = {}

    def add(self, sig: Signal) -> tuple[Signal, bool]:
        """Returns (stored_signal, created). A duplicate returns the EXISTING signal and created=False."""
        existing = self._by_key.get(sig.key)
        if existing is not None:
            return existing, False
        self._by_key[sig.key] = sig
        return sig, True

    def update(self, sig: Signal) -> None:
        if sig.key not in self._by_key:
            raise KeyError("unknown signal")
        self._by_key[sig.key] = sig

    def __len__(self) -> int:
        return len(self._by_key)
