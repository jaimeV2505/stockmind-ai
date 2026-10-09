# ADR-0005 Rule-based NYSE calendar; calendar-strict session functions
Decision: compute NYSE holidays from rules (fixed dates + weekend observance, nth-weekday, Good Friday via Easter algorithm,
Juneteenth from 2022) plus a hand-maintained `AD_HOC_CLOSURES` set; early closes (day after Thanksgiving, Dec 24, Jul 3 when
Jul 4 is a weekday). Supported years 2012-2100 (raises outside). `session_open_utc` / `session_close_utc` now RAISE on non-trading
days (behaviour change vs session 1, where they were nominal; no external callers existed). Quality validation is calendar-driven.
Rationale: no network dependency, deterministic, testable; avoids silently fabricating sessions on closed days.
Consequences / risks: ad hoc list is from memory and unverified against nyse.com; unscheduled future closures need manual entry;
pre/post-market and 1h/1w bar alignment are unmodelled (reports `gap_check_performed=False`, never "clean").
Alternatives rejected: `pandas_market_calendars` / `exchange_calendars` (good, but a heavy dependency; reconsider as a CI
cross-check, see next-tasks).
