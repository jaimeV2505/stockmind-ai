# Next tasks (ordered)

1. [BLOCKED: needs network] Run `make test` under real pytest and `ruff check .`; fix findings; confirm CI green after first push.
2. [BLOCKED: needs TA-Lib] Add a CI job cross-validating every indicator (sma, ema, rsi, macd, atr, bollinger, roc, obv, adx, cci, mfi, stochrsi)
   against TA-Lib with documented tolerances; replace the loose RSI sanity test. Optionally cross-check the NYSE calendar against
   `exchange_calendars` in CI and verify `AD_HOC_CLOSURES` against nyse.com.
3. Remaining Phase 2 indicators: Supertrend, Ichimoku (chikou = plot-only, ADR-0006), MA-crossover detection, SMA/EMA preset sets (20/50/100/200, 9/20/50/100/200).
4. Market structure on top of `swing_points`: support/resistance zones, HH/HL/LH/LL classification, break of structure, consolidation zones, breakout/retest.
   Must use confirmation-bar semantics.
5. Multi-timeframe: causal resampling of 1m->5m/15m/1h/1d with completed-bar-only alignment (no partial-bar leakage) + tests.
6. Alpaca adapter (mocked HTTP tests, rate limiting, retries, entitlement -> `DataMode`) behind `MarketDataProvider`;
   `MARKET_DATA_MODE` switch that fails loudly and never falls back to demo.
7. Phase 1: Supabase schema + RLS migrations (`database/`), FastAPI app (`apps/api`), Next.js app (`apps/web`), auth, explorer with Lightweight Charts.
8. Add `docs/product/MASTER_PROMPT.md` (original spec; user-supplied).
