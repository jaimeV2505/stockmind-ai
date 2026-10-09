# StockMind AI — web (Next.js, App Router)

Current scope: a **read-only demo** of the engines' output on **simulated** data. There is no login, database, live provider or API yet.
Every page shows a data-mode banner; if the data snapshot is missing or invalid the UI shows an error — it never invents prices.

## Run locally
```bash
cd apps/web
npm install
npm run dev          # http://localhost:3000  (redirects to /es; /en for English)
npm run typecheck    # tsc --noEmit (real @types/react + next)
npm test             # node --test lib/*.test.ts (pure logic + snapshot validation)
npm run build        # production build
```
The data lives in `data/demo-snapshot.json`, produced from the Python engines:
```bash
python3 ../../scripts/export_demo_snapshot.py          # regenerate
python3 ../../scripts/export_demo_snapshot.py --check  # fail if the committed file is stale
```

## Real data (end-of-day, Alpaca)
By default the site serves the simulated demo. To serve real data follow `docs/operations/real-market-data.md` (private repo, Alpaca keys as GitHub secrets,
`STOCKMIND_DATA=market` + `SITE_PASSWORD` in Vercel). With `STOCKMIND_DATA=market` the site is password-protected and returns 503 if no strong password is set.

## Deploy on Vercel
1. Import the GitHub repo. **Root Directory = `apps/web`**. Framework preset: Next.js (auto-detected). No environment variables are needed.
2. Build command / output: defaults. Node 20.x or 22.x.
3. After the first deploy, open `/es` and `/es/stock/SIMA` and confirm the orange SIMULATED banner is visible.

The Python backend (API, workers) is NOT deployed on Vercel; it is not part of this app yet.

## Status of verification (read this before trusting it)
Verified offline in the authoring sandbox: `lib/` type-checks under `tsc --strict` and passes `node --test`; every component was compiled with the
TypeScript API, rendered with real React 19 against the real snapshot and opened in headless Chromium at 1280px and 390px (layout, overflow,
accessibility basics, data-mode labelling, overlay toggles). **`next build` has NOT been run** (no network to install Next.js) and the TSX has not
been type-checked against the real `@types/react`: expect the first build to possibly surface type errors or config tweaks. Interactions that need
client-side JS (checkbox toggles, localStorage persistence) are only verified through their pure logic and server rendering, not in a browser.
