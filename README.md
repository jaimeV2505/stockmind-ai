# StockMind AI

AI-assisted stock **research and analytics** platform (not investment advice; no trade execution).
Status: **Phase 0 complete in part** — see `docs/progress/current-state.md` for exactly what exists.

## Run the tests
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```
No pytest? `make test-stdlib` (= `scripts/run_stdlib_tests.sh`) runs every service's suite with `unittest` and prints a per-service summary.

## Layout
`services/*` = pure-Python domain modules (framework-free). `apps/*` = deployables (not yet implemented).
Read `CLAUDE.md` first when continuing work.
