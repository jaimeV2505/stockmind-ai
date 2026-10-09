# Current state (update every session)

Last updated: 2026-10-09 · Session 5 = strategies/scanner, walk-forward, pattern engine; Session 4 = quant engines (risk, signal lifecycle, backtester); Session 3 = independent audit + hardening (claude.ai sandbox: no network, no pytest/ruff/TA-Lib/Docker, no GitHub access)

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

## Tests (stdlib `unittest`, Python 3.12.3, numpy 2.4.4, pandas 3.0.2; run at end of session 5)
- technical-analysis 45 · market-data 43 · portfolio-analytics (risk) 11 · signal-engine 32 · backtesting 33 · pattern-recognition 19 ·
  tests/integration 2 → **185 passed, 0 failed**.
- Mutation-checked (plant a bug, confirm a test fails, restore): backtester (4 bugs), strategies (4), walk-forward (3), pattern engine (6) -- all caught.
  Two real test-quality problems were found this way and fixed: causality tests that were vacuous because the data produced no entry
  events (OversoldRecovery had 0 entries), and an untested tie-break rule. Causality tests now (a) require a minimum number of events and
  (b) truncate exactly at every trigger bar. NOTE: stale `.pyc` caches can make mutation runs lie; run with `PYTHONDONTWRITEBYTECODE=1`.

- Lint: `ruff` has STILL never been run. An AST-based sweep approximating ruff's default rules (E4/E7/E9/F) found and fixed 8x E702 (semicolons), 1x E731, 1 E701-style stub, and unused imports/locals. It is an approximation: expect some residual ruff findings on the first real run.

## Session 5 additions (framework-free, pure Python; still NOT exposed through any API/UI/DB)
- `stockmind_signals.strategies`: OversoldRecovery, MovingAverageCrossover, BullishBreakout (v1.0.0), each deterministic, causal, parameter-validated,
  with supporting/contradicting evidence; `decide()` returns a Signal or a NoSignal with a reason (insufficient history / no trigger / bad last bar);
  signals carry `version_tag = version+param-hash` so different parameterisations never share an idempotency key; `StrategyRegistry`
  (versioned, enable/disable, numeric version ordering, no overwrite); `scan()` over a universe (deterministic order, per-symbol error isolation, idempotent with the registry).
- `stockmind_backtest.validation`: `walk_forward` and `parameter_sensitivity` per ADR-0009.
- `stockmind_patterns`: shape normalisation, DTW, PatternIndex (forward return/MFE/MAE/regime), leakage-safe query, `summarize` per ADR-0010.
- `tests/integration`: strategies -> backtest -> risk sizing on SIMULATED demo data (accounting identity, reproducibility hash).
- Still unimplemented in this area: short side / multi-symbol portfolio backtests, more strategies (trend continuation, consolidation breakout, bearish
  breakdown, earnings volatility monitoring, high relative volume), multiple-testing corrections, market-structure detectors (BOS, S/R zones, chart patterns),
  pgvector-backed similarity search, gap-risk/earnings warnings, correlation and sector exposure.

## Session 4 additions (framework-free, pure Python; NOT yet exposed through any API/UI/DB)
- `services/portfolio-analytics/stockmind_risk`: ATR stop reference, risk/reward with geometry validation, whole-share position sizing
  (min of risk budget / concentration cap / liquidity cap, reports the binding constraint).
- `services/signal-engine/stockmind_signals`: lifecycle state machine (WATCHING/AWAITING_CONFIRMATION/CONFIRMED/INVALIDATED/EXPIRED/CLOSED),
  immutable audited transitions, `NoSignal`, deterministic idempotency key (symbol, strategy id+version, timeframe, trigger ts), in-memory registry
  defining the persistence contract. Exhaustive transition-matrix test.
- `services/backtesting/stockmind_backtest`: single-symbol long-only engine per ADR-0008, metrics (return, CAGR>=1y, win rate, PF, drawdown,
  expectancy, exposure, Sharpe>=30 bars, buy&hold benchmark), reproducibility hash, accounting-identity and truncation-causality tests.
- NOT implemented: strategies themselves (no strategy produces flags yet), scanner, shorts, portfolio-level/multi-symbol backtests,
  walk-forward/OOS splits, parameter sensitivity, pattern engine, gap-risk/earnings warnings, correlation/sector exposure.

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
