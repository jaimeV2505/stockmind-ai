# Current state (update every session)

Last updated: 2026-10-09 · Session 7 = web app v0 (apps/web); Session 6 = alerts, entitlements, news safety, point-in-time fundamentals (see docs/progress/reliability-evidence.md); Session 5 = strategies/scanner, walk-forward, pattern engine; Session 4 = quant engines (risk, signal lifecycle, backtester); Session 3 = independent audit + hardening (claude.ai sandbox: no network, no pytest/ruff/TA-Lib/Docker, no GitHub access)

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

## Tests (stdlib `unittest` via `make test-stdlib`, Python 3.12.3, numpy 2.4.4, pandas 3.0.2; run at end of session 6)
- 280 passed, 0 failed (technical-analysis 45, market-data 43, risk 11, signal-engine 32, backtesting 33, pattern-recognition 19, notifications 29,
  entitlements 10, news-intelligence 33, fundamental-analysis 20, integration 5). Stable under 5 PYTHONHASHSEED values and 4 TZ settings.
- Mutation-checked (plant a bug, confirm a test fails, restore): backtester (4 bugs), strategies (4), walk-forward (3), pattern engine (6) -- all caught.
  Two real test-quality problems were found this way and fixed: causality tests that were vacuous because the data produced no entry
  events (OversoldRecovery had 0 entries), and an untested tie-break rule. Causality tests now (a) require a minimum number of events and
  (b) truncate exactly at every trigger bar. NOTE: stale `.pyc` caches can make mutation runs lie; run with `PYTHONDONTWRITEBYTECODE=1`.

- Lint: `ruff` has STILL never been run. An AST-based sweep approximating ruff's default rules (E4/E7/E9/F) found and fixed 8x E702 (semicolons), 1x E731, 1 E701-style stub, and unused imports/locals. It is an approximation: expect some residual ruff findings on the first real run.

## Session 9: public-repo data policy (ADR-0014)
- Alpaca forbids redistributing its data; the repo is public, so market data is never committed: workflow now exports -> builds -> deploys to Vercel from Actions
  (`.github/workflows/market-data.yml`), git-ignored snapshot, Git-triggered deploys of `main` disabled (`apps/web/vercel.json`), `dynamicParams=false` on stock pages.
- `tests/integration/test_repo_policy.py` enforces it (7 tests; 11 planted violations caught). Workflow embedded policy script tested with synthetic env files.
- NOT verified: the Vercel CLI sequence, the real Alpaca API, a real Actions run. Python tests: 317; web: 17 + 12-page browser harness.

## Session 8 additions: real-data path (see ADR-0013, docs/operations/real-market-data.md)
- `AlpacaDailyBars` adapter (19 fixture tests, 16 planted bugs caught), exporter `--source market` (fail-loud, excludes symbols that fail the quality gate, exit codes 0/1/2/3),
  `config/universe.json`, daily workflow `.github/workflows/market-data.yml` (refuses to run in a public repo), web: delayed/real banner, excluded-symbols panel, mode-aware copy,
  explicit `STOCKMIND_DATA` selection, fail-closed Basic-auth middleware, "unavailable" banner that claims no data origin.
- Tests: Python 284 -> see `make test-stdlib`; web: 17 node tests + browser harness over 12 pages x 2 viewports incl. real-data mode (produced by the real pipeline on a SYNTHETIC transport).
  13 planted web/access defects caught; 2 survivors analysed (one redundant guard now pinned by message, one timing property that cannot be unit-tested).
- NEVER exercised: the real Alpaca API (no network/keys here), a real private-repo workflow run, Vercel with env vars/middleware.

## Session 7 additions: `apps/web` (Next.js demo, see ADR-0012 and apps/web/README.md)
- Pages: `/es|en` dashboard (symbols table, explicit NO SIGNAL state), `/es|en/stock/[symbol]` (candlestick SVG chart, EMA/SMA/Bollinger/volume/RSI/MACD toggles
  persisted in localStorage, entry-flag markers, strategy decisions, simulated backtests with equity curves and trades, historical-pattern matches with
  disclaimers, risk example), `/es|en/method`. Mode banner on every page; error state on invalid data; real 404 for unknown symbols.
- Data: `scripts/export_demo_snapshot.py` -> `apps/web/data/demo-snapshot.json` (deterministic, 5 fictional symbols, 252 daily bars each); a Python test keeps it reproducible.
- Verified offline: `lib/` under `tsc --strict` (0 errors) + 9 `node --test` tests; all components rendered with real React 19 and opened in headless
  Chromium (7 pages x desktop/mobile): no horizontal overflow, banner present, one h1, tables captioned, svg labelled, toggles add/remove overlays, no NaN/undefined leaks.
  The render harness itself was mutation-checked (11 planted UI defects, all caught). Two real defects were found by looking at screenshots (clipped axis label,
  untranslated engine text) and fixed.
- NOT verified: `next build` (no network), TSX against real `@types/react`, client-side interactivity in a browser, Lighthouse/axe, real Vercel deploy.
- NOT built: auth, DB, API, live data, Lightweight Charts, Tailwind/shadcn, TanStack Query, scanner/alerts/portfolio/admin UI, PWA, e2e (Playwright) suite.

## Session 6 additions (pure logic only; no I/O, no providers, no LLM calls, no DB)
- `stockmind_alerts`: rule evaluation (price cross, RSI threshold, volume spike, strategy signal) with human-readable "why"; `Dispatcher` with idempotency,
  cooldown, quiet hours (DST-aware), retries with exponential backoff, dead-letter, SKIPPED for unconfigured channels (ADR-0011).
- `stockmind_entitlements`: FREE/PRO/PREMIUM/ADMIN limits (illustrative numbers), fail-closed checks, feature flags, role vs plan, daily `UsageMeter`.
- `stockmind_news`: Article model, canonical URLs with SSRF-style rejection, order-aware dedupe, ticker association (no invented symbols), heuristic event labels,
  untrusted-text sanitiser + injection flags, prompt builder with sentinel, strict LLM-output validator (sources/tickers must come from our own data).
- `stockmind_fundamentals`: point-in-time fact store, UNAVAILABLE / NOT_MEANINGFUL / OK semantics, growth/margin/P-E, explainable configurable score.
- `scripts/run_stdlib_tests.sh` (used by `make test-stdlib`) runs every service's tests with one command.
- Still NOT implemented: provider adapters (Alpaca/Polygon/FMP/EDGAR), LLM client, push/email/Telegram senders, persistence, API, web UI, auth, admin,
  Stripe, workers/queues, observability, deployment, remaining 7 default strategies, shorts, portfolio-level backtests.

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
