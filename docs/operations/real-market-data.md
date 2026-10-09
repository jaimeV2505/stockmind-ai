# Going from demo to real end-of-day data (Alpaca) — runbook (PUBLIC repository variant)

## Why the data never goes into git
Alpaca states that its API data cannot be redistributed (support article "Can I redistribute Alpaca API data via my platform?" — "you cannot redistribute Alpaca API data")
and its Terms limit the content to personal, non-commercial use. This repository is PUBLIC, so committing bars would redistribute them. Therefore:
- `apps/web/data/market-snapshot*.json` is git-ignored; `tests/integration/test_repo_policy.py` fails CI if one is ever tracked, or if the data workflow gains a
  commit/push/artifact/cache step, write permission or a pull_request trigger.
- The workflow `.github/workflows/market-data.yml` exports the data on the Actions runner, builds the Next.js app WITH it and deploys that build straight to Vercel.
  The data only exists on the runner (deleted at the end) and inside the password-protected deployment.
- The site is behind HTTP Basic auth (`apps/web/middleware.ts`). With `STOCKMIND_DATA=market` and no strong `SITE_PASSWORD` it answers 503.
- Actions logs of a public repo are public: the exporter prints only counts/symbols/errors, never bars or keys.
Personal use only: the Vercel Hobby plan and Alpaca's terms are non-commercial. Showing this to other people would need a data licence that allows display.

## What you get
Completed daily bars, delayed, from Alpaca's IEX feed (NOT the consolidated tape: lower volumes). Indicators, signals, backtests and patterns come from the Python engines.
No intraday, real-time, fundamentals or news yet. The adapter was verified only against fixtures: the first real run is the real test (failures are loud by design).

## One-time setup (in this order)
1. **Alpaca**: Paper Trading view -> "Your API Keys" -> Generate New Keys. Copy Key ID and Secret immediately (the secret is shown once). Never paste them in chat or files.
2. **Vercel token and IDs**
   - Token: Vercel -> Account Settings -> Tokens -> Create (scope: your account/team, expiry of your choice).
   - Project ID: Vercel -> project `stockmind-ai` -> Settings -> General -> "Project ID".
   - Org/Team ID: Vercel -> Team Settings -> General -> "Team ID" (for a personal account use the ID shown under Settings -> General of your account).
3. **GitHub secrets** (repo -> Settings -> Secrets and variables -> Actions): `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `VERCEL_TOKEN`, `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID`.
4. **Push this version first** (it contains `apps/web/vercel.json`, which turns OFF Git-triggered deployments for `main`; from then on production is deployed only by the workflow).
5. **Vercel -> project -> Settings -> Environment Variables (Production)**: `STOCKMIND_DATA=market`, `SITE_PASSWORD=<random, >= 12 chars>`, optional `SITE_USER` (default `stockmind`).
   Set these AFTER step 4: a Git-triggered build in market mode would have no data file.
6. **Actions -> "Market data refresh and deploy" -> Run workflow.** Read the log: step "Export market snapshot" lists the symbols written and any EXCLUDED with the reason;
   the policy steps fail with an explicit message if a secret or an env var is missing.
7. Open the production URL: the browser asks for user/password; the banner must read "DATOS REALES DE FIN DE DÍA, CON RETRASO. Fuente: alpaca-iex".

## Everyday operation
- Scheduled 22:30 UTC Mon-Fri. Code changes no longer deploy on push: run the workflow manually to ship them (or merge and wait for the next schedule).
- Edit `config/universe.json` to change the symbols (ticker -> company name; unknown tickers show the ticker as the name), push, run the workflow.
- Rotate keys: change the GitHub secrets (and the Vercel env var for the password), run the workflow.
- Local run (never commit the output): `ALPACA_API_KEY=... ALPACA_API_SECRET=... python3 scripts/export_demo_snapshot.py --source market`, then
  `cd apps/web && STOCKMIND_DATA=market SITE_PASSWORD=some-long-password npm run dev`.
- Exit codes of the exporter: 0 ok, 1 no symbol passed the data-quality gate / other, 2 missing or rejected credentials, 3 provider unavailable. It never writes a partial or simulated file.

## Known limits / not verified
Never run against the real Alpaca API or the real Vercel CLI flow (`vercel pull/build/deploy --prebuilt` from the repo root with Root Directory = apps/web is written from the
public CLI conventions, unverified); `vercel@latest` is unpinned; IEX volumes; split-adjusted prices only; daily bars only; survivorship bias; Basic auth is a stop-gap, not accounts.
If the first run fails, send the failing step's log text (it contains no keys).
