# Next tasks (ordered)

> Real data path is built but UNVERIFIED against Alpaca: follow docs/operations/real-market-data.md; the first real run is the test. Send the Actions log if it fails.


> Web app v0 exists (apps/web). FIRST ACTION on a networked machine: `cd apps/web && npm install && npm run typecheck && npm test && npm run build`; fix whatever the real
> Next/React types and build surface, commit `package-lock.json`, then import into Vercel (Root Directory = apps/web).


> Session 6 completed the pure-logic modules for alerts, entitlements, news safety and fundamentals. Everything below that needs network, a database,
> credentials or Node is BLOCKED in the authoring sandbox and should be done with Claude Code on a networked machine.
 — see docs/progress/audit-2026-10-09.md for finding IDs

0. Run the new suites too: `pip install -e ".[dev]" && pytest` now covers 6 services + tests/integration (pytest/ruff/CI still never executed).
1. [BLOCKED: needs network] On a networked machine: `pip install -e ".[dev]"`, `ruff check .`, `pytest`, push, confirm both CI matrix legs (py3.12 latest; py3.11 pandas 2.2/numpy 1.26). Fix findings. (H-6, M-5)
2. [BLOCKED: needs TA-Lib] CI job cross-validating indicators vs TA-Lib; cross-check calendar vs `exchange_calendars`; verify `AD_HOC_CLOSURES` on nyse.com. (M-7, M-8)
3. Decide + implement ingestion gap-repair/re-seed policy for recursive indicators; adapter contract-test suite built on `validate_series`. (M-6)
4. Pin GitHub Actions by SHA; add pip-audit + gitleaks; re-author git identity. (M-9, L-4)
5. DONE in session 5: strategies v1 + registry + scanner, walk-forward/sensitivity, pattern engine. Next in this area: the 7 remaining default strategies, short side + portfolio-level backtests, multiple-testing correction, market-structure/chart-pattern detectors with fit statistics, ingestion-side gap policy.
5b. Remaining Phase 2 indicators/logic: Supertrend, Ichimoku (chikou plot-only, ADR-0006), MA-cross detection, S/R zones & market structure on `swing_points`, causal multi-timeframe resampling.
6. Alpaca adapter (mocked HTTP tests, rate limiting, retries, entitlement -> `DataMode`; normalises to ADR-0007 rules); `MARKET_DATA_MODE` must fail loudly, never fall back to demo.
6b. DONE (session 5): pattern engine. Next: persistence of window features (pgvector) and async indexing worker once Postgres/Redis are available.
7. [BLOCKED here: needs network, Node, Docker, Postgres] Milestone 1 of the full-stack prompt: Supabase schema + RLS migrations + RLS **with policy tests**, FastAPI + authz/entitlement tests, Next.js app.
8. Performance: vectorise/numba Wilder smoothing + `swing_points` before intraday universe scans (L-3). Bound `missing_intraday` output (L-6).
9. Add `docs/product/MASTER_PROMPT.md` (original spec; user-supplied). Legal: data licences, EU/Swedish regulatory opinion, GDPR.
10. Provider-facing work (needs credentials/network): Alpaca adapter, EDGAR/FMP fundamentals ingestion (-> `FactStore`), news provider + LLM client wrapping `build_prompt`/`validate_analysis`,
    email/Telegram/web-push senders implementing `Dispatcher` senders (honour the idempotency key). Each adapter: contract tests + recorded fixtures, then a real-service smoke test.
11. Persistence: SQL migrations mirroring ADR-0011 (UNIQUE(event_key, channel), conditional status UPDATE, atomic usage counters), RLS policies with policy tests.
12. Remaining strategies (7), short side, portfolio-level backtests, multiple-testing correction, market-structure detectors.
13. Load/soak/failure-injection tests and a property-based layer (hypothesis) once dependencies can be installed.
14. Web: swap SVG chart for Lightweight Charts, add Tailwind/shadcn, Playwright e2e (toggle persistence, locale switch, mobile nav), axe/Lighthouse, eslint, security headers/CSP review.
15. Web: replace the snapshot with a typed API client once `apps/api` exists (keep the validator; keep the data-mode banner; keep error-not-fallback behaviour).
