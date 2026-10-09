# Current state (update every session)

Last updated: 2026-10-09 · Session 3 = independent audit + hardening (claude.ai sandbox: no network, no pytest/ruff/TA-Lib/Docker, no GitHub access)

**Read `docs/progress/audit-2026-10-09.md` first. Verdict: NOT production-ready.**

## Implemented
- Monorepo skeleton (directories per spec; unimplemented ones hold `.gitkeep` only).
- `services/technical-analysis` (`stockmind_ta`), 18 indicators:
  - Session 1: sma, ema, rsi, macd, true_range, atr, bollinger, roc, obv, relative_volume.
  - Session 2: adx (+DI/-DI), cci, keltner, historical_volatility, mfi, stoch_rsi, vwap (session-anchored), swing_points (causal pivots, ADR-0006).
- `services/market-data` (`stockmind_marketdata`):
  - `Candle` model with provenance fields + validation; `Timeframe` / `AdjustmentStatus` / `DataMode`; `MarketDataProvider` protocol.
  - `DemoProvider` (always SIMULATED, 1d only, trading days only).
  - NYSE calendar (ADR-0005): holidays, early closes, 2012-2100, strict session open/close in UTC, trading-day listing,
    expected intraday bar grid for 1m/5m/15m.
  - `validate_series`: duplicates, ordering, mixed data modes, missing/unexpected daily candles, missing/unexpected intraday bars.
- Repo plumbing: `pyproject.toml`, `Makefile`, `docker-compose.yml` (Postgres+pgvector only), `.env.example`,
  `.github/workflows/ci.yml`, CLAUDE.md, docs, ADRs 0001-0006.

## Tests (stdlib `unittest`, Python 3.12.3, numpy 2.4.4, pandas 3.0.2; run at end of session 3)
- technical-analysis: **45 passed**. market-data: **43 passed**. Total 88, 0 failures.
- Session-3 regression tests were run against the unfixed code first: 20 failures; 0 after the fixes.
- Mutation-checked: a planted look-ahead in `swing_points` and a planted wrong DM rule in ADX were both detected
  (the first was initially MISSED by a single-cut causality test; tests now truncate at many cut points).
- Independent references: RSI (pure-Python Wilder), ADX (Wilder's original running-sum form), plus hand-computed CCI/MFI/VWAP/HV/OBV/Bollinger.
- Calendar anchors: Easter 2024/2025/2026/2038, full 2026 holiday list, 2023 = 250 and 2024 = 252 trading days, weekend-observance edge cases.

## NOT verified / known limitations
- `pytest`, `ruff`, Docker and the GitHub Actions workflow have **never been run** (tooling unavailable in both sessions).
- No indicator has been cross-validated against TA-Lib or any third-party library yet (only independent re-implementations).
  The "published RSI example" values are from memory and used only as a loose sanity check (delta 0.1).
- NYSE `AD_HOC_CLOSURES` (2012-10-29/30, 2018-12-05, 2025-01-09) and the early-close rules are from memory; verify against the
  official NYSE calendar. Calendar is regular-session only; 1h and 1w gap detection NOT implemented (`gap_check_performed=False`).
- Not yet implemented: Supertrend, Ichimoku, SMA 100/200 convenience sets, moving-average cross detection, support/resistance zones,
  market-structure (BOS, HH/HL), patterns, multi-timeframe aggregation, and everything in Phases 1-6 (web, API, auth, DB, providers,
  scanner, signals, backtester, news, alerts).
- No real provider adapter. Nothing deployed. Not pushed to GitHub (no access from the authoring sandbox).

## Session 3 hardening (details in the audit report)
- Candle: finite/valid-identifier/ingest-time validation; `key` includes exchange. `freshness()` now session-aware.
- Calendar: `date`-only API (datetime -> TypeError), immutable holiday table, `bar_close_utc`.
- Quality: single symbol/exchange/timeframe; flags mixed provenance, forming bars, misaligned 1d stamps.
- Indicators: OBV/VWAP/relative_volume NaN-safety; numpy-int periods accepted.
- Repo: CI-breaking packaging fixed (install verified in fresh venv), ruff config, tzdata dep, CI version matrix, compose DB bound to loopback.

## Behaviour changes in sessions 2-3
- `session_open_utc` / `session_close_utc` raise `ValueError` on non-trading days (previously nominal). `DemoProvider` skips holidays and emits only completed sessions.
- Calendar functions raise `TypeError` for `datetime`. `Candle` rejects previously accepted malformed data. `validate_series` raises on multi-symbol input.
- `Candle.key` gained `exchange` (no persisted keys exist yet).
  No external consumers existed, so no migration needed (ADR-0005).

## Blockers / external actions
- Need an environment with network + pytest/ruff/TA-Lib (Claude Code locally, or CI) to close next-tasks #1-#2.
- Provider credentials and data licences (Alpaca/Polygon/FMP/EDGAR); Supabase and Vercel projects: not created.
- `docs/product/MASTER_PROMPT.md` (original spec) is referenced by CLAUDE.md but not in the repo; the user must add it.
