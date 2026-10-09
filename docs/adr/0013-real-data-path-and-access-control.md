# ADR-0013 Real end-of-day data path, explicit data selection and fail-closed access control
Decision: real data enters through `AlpacaDailyBars` (stdlib HTTP, injectable transport, fail-loud parsing: midnight-ET stamps re-stamped to the session open, forming
sessions dropped, non-trading-day/duplicate/invalid bars rejected, redirects refused, only data.alpaca.markets). `scripts/export_demo_snapshot.py --source market` runs
the engines and writes `market-snapshot.json`; symbols failing the data-quality gate are EXCLUDED and listed in `meta.excluded`; provider-wide failures abort with a
distinct exit code and write nothing. There is NO fallback to simulated data anywhere. The web app serves exactly one snapshot, chosen by `STOCKMIND_DATA`
(unknown value = error; a simulated file can never be served as market data, nor the reverse). A daily GitHub Action refreshes the snapshot and refuses to run in a public repo.
Access: with `STOCKMIND_DATA=market` the middleware requires HTTP Basic credentials and answers 503 unless `SITE_PASSWORD` is set and >= 12 chars (constant-time compare).
When data cannot be loaded the banner claims NO origin ("unavailable").
Why a pipeline instead of live calls from Vercel: indicators/backtests/patterns live in Python; running them per request needs a Python service we do not have yet.
Trade-offs / risks: data is end-of-day only; the snapshot is committed to a (private) repo; Basic auth is not user management; the Alpaca contract is verified only
against fixtures written from the public docs; IEX volumes are not consolidated. Future: FastAPI service + DB + real auth + SIP/licensed feed + intraday.
