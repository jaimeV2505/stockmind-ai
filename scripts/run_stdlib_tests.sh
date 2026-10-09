#!/usr/bin/env bash
# Runs every service's tests with the stdlib runner (no pytest needed). Exit code != 0 if anything fails.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONDONTWRITEBYTECODE=1
export PYTHONPATH="$(printf '%s:' "$ROOT"/services/*/ | sed 's:/:/:g; s/:$//')"
status=0; total=0
for t in services/*/tests tests/integration; do
  [ -d "$t" ] || continue
  out="$(python3 -m unittest discover -s "$t" 2>&1)"; rc=$?
  n="$(printf '%s' "$out" | sed -n 's/^Ran \([0-9]*\) tests.*/\1/p' | tail -1)"
  printf '%-45s %s tests  %s\n' "$t" "${n:-0}" "$([ $rc -eq 0 ] && echo OK || echo FAILED)"
  [ $rc -eq 0 ] || { printf '%s\n' "$out" | tail -25; status=1; }
  total=$((total + ${n:-0}))
done
echo "TOTAL: $total tests, exit status $status"
exit $status
