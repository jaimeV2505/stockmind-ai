# Going from demo to real end-of-day data (Alpaca) — runbook

## What this does and does not give you
Daily bars (completed sessions only), delayed, from Alpaca's **IEX feed** (free plan): NOT the consolidated tape, so volume and the occasional OHLC differ
from other sources. Indicators, signals, backtests and patterns are computed by the Python engines. No intraday, no real-time, no fundamentals/news yet.

## Licensing — read before publishing anything
Provider terms generally forbid redistributing market data publicly. Therefore: (1) the GitHub repo must be PRIVATE (the refresh workflow refuses to run
otherwise); (2) the Vercel site is protected by HTTP Basic auth, enforced in `middleware.ts` — with `STOCKMIND_DATA=market` and no strong `SITE_PASSWORD`
the site answers 503; (3) the Hobby plan is personal/non-commercial only. A public or paid product needs a data licence that permits display/redistribution.

## One-time setup
1. Create an Alpaca account (paper trading is enough for market data) and generate an API key + secret. Never paste them in chat, code or commits.
2. GitHub -> repo -> Settings -> General -> Danger Zone -> **Change visibility -> Private**.
3. GitHub -> Settings -> Secrets and variables -> Actions -> add `ALPACA_API_KEY` and `ALPACA_API_SECRET`.
4. Run the workflow once: Actions -> "Market data refresh" -> Run workflow. Check the log: it lists the symbols written and any EXCLUDED with the reason.
   If it fails on the first real call, send the log: the adapter was only verified against fixtures, and any difference fails loudly by design.
5. Edit `config/universe.json` to choose symbols (it maps ticker -> company name; unknown tickers show the ticker as the name).
6. Vercel -> Project -> Settings -> Environment Variables (Production): `STOCKMIND_DATA=market`, `SITE_PASSWORD=<long random>`, optional `SITE_USER`. Redeploy.
7. Open the site: browser asks for user/password; banner must read "DATOS REALES DE FIN DE DÍA, CON RETRASO. Fuente: alpaca-iex".

## Local run (optional)
```bash
export ALPACA_API_KEY=...  ALPACA_API_SECRET=...
python3 scripts/export_demo_snapshot.py --source market --symbols SPY,NVDA     # writes apps/web/data/market-snapshot.json
cd apps/web && STOCKMIND_DATA=market SITE_PASSWORD=some-long-password npm run dev
```
Exit codes of the exporter: 0 ok, 1 no symbol passed the quality gate / other error, 2 missing or rejected credentials, 3 provider unavailable.
It never writes a partial or simulated file on failure.

## Operating notes
- The scheduled job runs 22:30 UTC Mon-Fri. On market holidays the data simply repeats (no commit if unchanged).
- Data freshness is shown on every page ("Datos hasta"). If the job fails, the site keeps serving the last good snapshot: check Actions for failures.
- Rotating keys: update the two secrets; nothing else changes.

## Known limits / not verified
Adapter never called against the real API; IEX volumes; split-adjusted prices only (no dividends); daily timeframe only; no delisted symbols (survivorship bias in
pattern statistics); Basic auth is a stop-gap, not user accounts; SPY/QQQ are ETFs, not the index values.
