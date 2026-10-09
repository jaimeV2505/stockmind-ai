# Next tasks (ordered) — see docs/progress/audit-2026-10-09.md for finding IDs

1. [BLOCKED: needs network] On a networked machine: `pip install -e ".[dev]"`, `ruff check .`, `pytest`, push, confirm both CI matrix legs (py3.12 latest; py3.11 pandas 2.2/numpy 1.26). Fix findings. (H-6, M-5)
2. [BLOCKED: needs TA-Lib] CI job cross-validating indicators vs TA-Lib; cross-check calendar vs `exchange_calendars`; verify `AD_HOC_CLOSURES` on nyse.com. (M-7, M-8)
3. Decide + implement ingestion gap-repair/re-seed policy for recursive indicators; adapter contract-test suite built on `validate_series`. (M-6)
4. Pin GitHub Actions by SHA; add pip-audit + gitleaks; re-author git identity. (M-9, L-4)
5. Remaining Phase 2 indicators/logic: Supertrend, Ichimoku (chikou plot-only, ADR-0006), MA-cross detection, S/R zones & market structure on `swing_points`, causal multi-timeframe resampling.
6. Alpaca adapter (mocked HTTP tests, rate limiting, retries, entitlement -> `DataMode`; normalises to ADR-0007 rules); `MARKET_DATA_MODE` must fail loudly, never fall back to demo.
7. Phase 1: Supabase schema + RLS **with policy tests**, FastAPI + authz/entitlement tests, Next.js app.
8. Performance: vectorise/numba Wilder smoothing + `swing_points` before intraday universe scans (L-3). Bound `missing_intraday` output (L-6).
9. Add `docs/product/MASTER_PROMPT.md` (original spec; user-supplied). Legal: data licences, EU/Swedish regulatory opinion, GDPR.
