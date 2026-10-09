# CLAUDE.md — StockMind AI engineering memory

The repository is the source of truth, not chat history. Start with `docs/progress/current-state.md` and
`docs/progress/next-tasks.md`. The original product spec is `docs/product/MASTER_PROMPT.md` (add it if missing).

## Non-negotiable rules
- Never claim a feature works unless implemented AND tested. Update `current-state.md` honestly after each session.
- Never fabricate data, statistics, backtest results, deployments or test outcomes.
- Simulated data is always labelled (`DataMode.SIMULATED`, source ends in `-simulated`) and never substitutes silently for live data.
- Indicators are deterministic math (numpy/pandas). LLMs only explain/summarise; they never compute numbers, execute trades, or override risk rules.
- All indicator code must be causal (no look-ahead); the causal tests (many truncation cut points) must cover every new indicator. Sparse/pivot-style signals are reported on their confirmation bar (ADR-0006).
- Before trusting new tests, mutation-check them: plant a bug, confirm a test fails, restore.
- Session/close helpers raise on non-trading days (ADR-0005); never fabricate sessions. Calendar functions take `date`, never `datetime`.
- Validate at the boundary and reject, don't repair (ADR-0007). Indicators propagate NaN; never skip or fill bars silently.
- Code must work on pandas>=2.2 AND pandas 3 (read-only `.to_numpy()` views: copy before writing).
- The latest audit is `docs/progress/audit-2026-10-09.md`; its open findings are the priority backlog.
- No secrets in git. No real trading in the initial release. No billing activation without explicit approval.
- Timestamps: timezone-aware UTC internally; convert to America/New_York only for market-session logic.

## Commands
`make test` (pytest) · `make test-stdlib` (no pytest needed) · `make db-up` (local Postgres+pgvector)

## Conventions
Python 3.12, ruff, type hints. Services live under `services/<name>/stockmind_<pkg>/` with tests beside them.
Every architectural decision gets an ADR in `docs/adr/`.
