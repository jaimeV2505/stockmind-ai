# Current state (update every session)

Last updated: 2026-10-09 · Session 1 (Phase 0, claude.ai sandbox, no network, no GitHub access)

## Implemented
- Monorepo skeleton (directories per spec; unimplemented ones hold `.gitkeep` only).
- `services/technical-analysis` (`stockmind_ta`): sma, ema, rsi, macd, true_range, atr, bollinger, roc, obv, relative_volume.
- `services/market-data` (`stockmind_marketdata`): `Candle` model with required provenance fields and validation,
  `Timeframe`/`AdjustmentStatus`/`DataMode` enums, `MarketDataProvider` protocol, deterministic `DemoProvider`
  (always SIMULATED, 1d only), series quality validation (duplicates, ordering, missing daily candles, mixed modes),
  US-Eastern/DST session helpers (regular session only).
- Repo plumbing: `pyproject.toml`, `Makefile`, `docker-compose.yml` (Postgres+pgvector only), `.env.example`,
  `.github/workflows/ci.yml`, CLAUDE.md, docs, ADRs 0001–0004.

## Tests (run in sandbox with stdlib unittest, Python 3.12.3, numpy 2.4.4, pandas 3.0.2)
- technical-analysis: 19 tests pass. market-data: 13 tests pass.
- Includes a no-look-ahead (causality) test across all indicators, and an independent pure-Python RSI cross-check.

## NOT verified / known limitations
- `pytest`, `ruff`, Docker, and the GitHub Actions workflow have **never been run** (no network/tooling in the authoring sandbox).
- RSI "published example" values were typed from memory and differ from our output by <=0.07; they are only a loose
  sanity check (delta 0.1). Indicators have NOT yet been cross-validated against TA-Lib or another trusted library.
- No real provider adapter exists (Alpaca/Polygon/FMP/EDGAR). No NYSE holiday/early-close calendar. Intraday gap detection missing.
- Nothing else in the spec exists yet: no web app, API, auth, database schema, scanner, signals, backtester, news, alerts.
- Nothing is deployed. Not pushed to GitHub by the authoring session.

## Blockers / external actions
- Provider credentials and data licences (see docs/security/security-model.md and docs/product/requirements.md).
- Supabase project, Vercel project: not created.
