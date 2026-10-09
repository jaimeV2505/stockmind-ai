# Next tasks (ordered)

1. Run `make test` with real pytest; run `ruff check .`; fix findings. Run CI once pushed.
2. Cross-validate every indicator against TA-Lib (CI job) with tolerances; replace the loose RSI sanity test.
3. Remaining Phase 2 indicators: ADX, Supertrend, Ichimoku, Stoch RSI, CCI, Keltner, historical vol, VWAP, MFI, swing/S&R.
4. Real NYSE calendar (holidays, early closes); intraday gap detection; weekly candles.
5. Alpaca adapter (+ mocked tests, rate limiting, retries) behind `MarketDataProvider`; `MARKET_DATA_MODE` switch that fails loudly, never falls back to demo.
6. Phase 1: Supabase schema + RLS migrations (database/), FastAPI app (apps/api), Next.js app (apps/web), auth, explorer with Lightweight Charts.
7. Add this repo's `docs/product/MASTER_PROMPT.md` (original spec).
