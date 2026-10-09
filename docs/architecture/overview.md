# Architecture overview
Modular monolith API (FastAPI) + separately scalable workers; Next.js web on Vercel; Supabase Postgres/Auth/RLS.
Domain logic lives in framework-free packages under `services/` (pure functions/dataclasses, trivially testable).
`apps/*` only wire services to HTTP/queues. Continuous scanners never run on Vercel serverless.
Status: only `services/technical-analysis` and `services/market-data` exist. See current-state.md.
