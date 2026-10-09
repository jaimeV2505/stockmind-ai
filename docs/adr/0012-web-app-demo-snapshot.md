# ADR-0012 Web app v0: read-only demo over a deterministic simulated snapshot
Decision: `apps/web` is a Next.js (App Router, TS strict) app that renders `data/demo-snapshot.json`, exported by `scripts/export_demo_snapshot.py`
from the REAL Python engines (indicators, strategies, backtester, pattern index, risk) on DemoProvider data. Symbols are fictional (SIMA-SIME) so no
simulated number is ever attributed to a real company. The snapshot is validated at runtime (`lib/snapshot.ts`); an invalid/missing snapshot renders an
error state, never fallback data. A data-mode banner is rendered on every page; backtests are tagged simulated. Locale is the ROOT dynamic segment
(`/es`, `/en`; `/` redirects to `/es`) so `<html lang>` is correct. Domain logic lives in `lib/` (pure TS, testable with `node --test`); components are thin.
Deliberate shortcuts (to be revisited): charts are dependency-free SVG instead of TradingView Lightweight Charts; plain CSS instead of Tailwind/shadcn;
no TanStack Query/Zod/auth/DB (nothing dynamic to fetch yet); `.ts` extension imports (needed by `node --test`; if Next rejects them, switch to extensionless
imports and run tests through a loader). The snapshot is committed so Vercel builds without Python.
Verification gap: `next build`, `tsc` against real React types, and client-side interactivity were NOT exercised offline (see apps/web/README.md).
