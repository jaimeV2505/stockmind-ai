#!/usr/bin/env bash
# Offline web verification (no Next.js, no network): strict tsc on lib/, node tests, snapshot reproducibility, and the render harness
# (real React + headless Chromium). Needs globally installed typescript, react, react-dom, playwright (set NODE_GLOBAL if elsewhere).
# This does NOT replace `npm run typecheck && npm run build` on a networked machine.
set -euo pipefail
cd "$(dirname "$0")/../apps/web"
G="${NODE_GLOBAL:-$(npm root -g)}"
echo "== snapshot reproducible =="; python3 ../../scripts/export_demo_snapshot.py --check
echo "== tsc --strict on lib/ =="
node "$G/typescript/bin/tsc" --ignoreConfig --noEmit --strict --target es2022 --lib es2023,dom --module esnext --moduleResolution bundler \
  --allowImportingTsExtensions --isolatedModules --skipLibCheck lib/types.ts lib/snapshot.ts lib/i18n.ts lib/format.ts lib/chart.ts lib/summary.ts lib/notes.ts
echo "tsc: 0 errors"
echo "== node --test =="; node --test "lib/*.test.ts" 2>&1 | grep -E "^(not ok|ok)|^# (tests|pass|fail)"
echo "== render + browser checks =="; NODE_PATH="$G" node scripts/render-check.mjs "$@"
