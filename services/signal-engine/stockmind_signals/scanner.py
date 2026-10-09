"""Universe scanner (pure function). Deterministic: sorted symbols x sorted strategies; one bad symbol never aborts a scan."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import pandas as pd

from .lifecycle import NoSignal, Signal, SignalRegistry
from .strategies import Strategy, decide


@dataclass(frozen=True)
class ScanResult:
    decisions: tuple[Signal | NoSignal, ...]
    errors: tuple[tuple[str, str, str], ...]   # (symbol, strategy id@version, message)
    created: int                               # new signals stored in the registry
    duplicates: int                            # signals already known (idempotent re-scan)

    @property
    def signals(self) -> tuple[Signal, ...]:
        return tuple(d for d in self.decisions if isinstance(d, Signal))


def scan(universe: Mapping[str, pd.DataFrame], strategies: Sequence[Strategy], timeframe: str,
         registry: SignalRegistry | None = None) -> ScanResult:
    decisions: list[Signal | NoSignal] = []
    errors: list[tuple[str, str, str]] = []
    created = dup = 0
    for symbol in sorted(universe):
        for strat in sorted(strategies, key=lambda s: (s.id, s.version_tag)):
            try:
                d = decide(strat, universe[symbol], symbol, timeframe)
            except (ValueError, KeyError, TypeError, AttributeError, IndexError) as e:  # bad input for this symbol only
                errors.append((symbol, f"{strat.id}@{strat.version_tag}", f"{type(e).__name__}: {e}"))
                continue
            if isinstance(d, Signal) and registry is not None:
                stored, is_new = registry.add(d)
                created += is_new
                dup += not is_new
                d = stored
            decisions.append(d)
    return ScanResult(tuple(decisions), tuple(errors), created, dup)
