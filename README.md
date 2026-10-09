# StockMind AI

AI-assisted stock **research and analytics** platform (not investment advice; no trade execution).
Status: **Phase 0 complete in part** — see `docs/progress/current-state.md` for exactly what exists.

## Run the tests
```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```
No pytest? `make test-stdlib` runs the same suites with `unittest`.

## Layout
`services/*` = pure-Python domain modules (framework-free). `apps/*` = deployables (not yet implemented).
Read `CLAUDE.md` first when continuing work.
