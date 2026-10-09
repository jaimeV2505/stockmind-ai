# Reliability evidence (what is actually established, and what is not)

"99% reliable" is not a property that can be asserted from unit tests. This file records the evidence that exists and the evidence that is missing.

## Established in the authoring sandbox (Python 3.12, numpy 2.4.4, pandas 3.0.2; stdlib unittest)
| Area | Tests | Evidence beyond "tests pass" |
|---|---|---|
| technical-analysis | 45 | independent re-implementations (RSI, ADX), hand calculations, causality at many cut points |
| market-data | 43 | audit findings H-1..H-7 reproduced then fixed; calendar anchors (annual trading-day counts 2019-2024) |
| risk | 11 | geometry validation, float-noise guard |
| signal-engine | 32 | strategy flags equal independently computed crossings; causality with guaranteed events; 4 planted look-aheads caught |
| backtesting | 33 | hand-computed fills/costs/drawdown; accounting identity; truncation causality; walk-forward poison test; 7 planted bugs caught |
| pattern-recognition | 19 | planted-pattern recall; leakage rules; 6 planted leaks caught |
| notifications (alerts) | 29 | dispatcher timeline tests (backoff, DLQ, quiet hours across DST); 17 planted bugs caught, 2 real gaps closed, 1 equivalent mutant verified |
| entitlements | 10 | fail-closed matrix, boundaries, daily reset; 5 planted bugs caught |
| news-intelligence | 33 | SSRF-style URL rejection, injection/hijack simulation, strict output schema; 30 planted bugs caught; found a real order-insensitive dedupe flaw and a false-positive detector |
| fundamental-analysis | 20 | point-in-time visibility, restatements, non-value semantics; 13 planted bugs caught |
| integration | 5 | scan -> signal -> alert -> delivery idempotent across re-scans; plan limits; strategies -> backtest -> sizing |
Total: **280 tests**, stable under 5 PYTHONHASHSEED values and 4 TZ settings. About 100 deliberate bugs were planted; every survivor was analysed (3 were real test gaps and were fixed, 2 were equivalent mutants).

## NOT established (and why "99%" cannot be claimed)
1. pytest, ruff, CI, Docker, Postgres, Redis, Node: never executed (no network in the sandbox). Residual lint/test-runner surprises are expected.
2. No indicator has been cross-validated against TA-Lib or any third-party library; RSI "published" values were recalled from memory.
3. No real market data, provider, LLM, SMTP/Telegram/push endpoint, DB or UI has ever been exercised. Everything above uses simulated or synthetic data.
4. No load, soak, concurrency or failure-injection testing; no fuzzing; no property-based testing library (hypothesis) available.
5. Strategies are textbook rules with NO demonstrated edge; backtests on simulated data prove mechanics only. Nothing here is a validated trading strategy.
6. Security review of anything network-facing is impossible: nothing network-facing exists.
7. Licensing, MiFID II / Finansinspektionen analysis and GDPR processes are undone.
Honest framing: the pure-logic core has strong verification for ITS OWN specification. Whether the specification is right for production (data quirks, provider behaviour, market reality) is untested.
