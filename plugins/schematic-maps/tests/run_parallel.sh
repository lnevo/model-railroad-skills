#!/usr/bin/env bash
# Run each test file in its own process, JOBS at a time (default: the CPU count),
# the slowest files first so none waits at the end behind the quick ones.
# Same tests as `python -m unittest discover -s tests`; fails if any file fails
# or if the files together ran fewer tests than one discover finds.
set -euo pipefail
cd "$(dirname "$0")/.."

JOBS="${JOBS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || echo 4)}"
PY="${PYTHON:-python3}"
# Slowest first, from CI's --durations list (2026-11-25); the rest follow by name.
SLOW="test_le_labels test_unsettled_columns test_le_prefs test_cache test_le test_orient_fallback test_solve_limits test_slots test_le_masts"

logs="$(mktemp -d)"
trap 'rm -rf "$logs"' EXIT

files=()
for f in $SLOW; do [ -f "tests/$f.py" ] && files+=("$f"); done
for p in tests/test_*.py; do
  f="$(basename "$p" .py)"
  case " $SLOW " in *" $f "*) ;; *) files+=("$f") ;; esac
done

start=$SECONDS
printf '%s\n' "${files[@]}" | xargs -P "$JOBS" -I{} sh -c '
  t0=$(date +%s)
  if "$1" -m unittest discover -s tests -p "$2.py" >"$3/$2.log" 2>&1; then r=ok; else r=FAILED; fi
  echo "$r $(( $(date +%s) - t0 ))s" >"$3/$2.status"
' _ "$PY" {} "$logs"

ran=0; failed=0
for f in "${files[@]}"; do
  status="$(cat "$logs/$f.status" 2>/dev/null || echo "FAILED no status")"
  n="$(sed -n 's/^Ran \([0-9]*\) tests\{0,1\} in .*/\1/p' "$logs/$f.log" | tail -1)"
  ran=$(( ran + ${n:-0} ))
  echo "$f: $status, ${n:-0} tests"
  case "$status" in ok*) ;; *) failed=1; cat "$logs/$f.log" ;; esac
done

want="$("$PY" -c 'import sys, unittest; sys.path.insert(0, "tests")
def count(s):
    return sum(count(t) for t in s) if isinstance(s, unittest.TestSuite) else 1
print(count(unittest.defaultTestLoader.discover("tests")))')"
echo "Ran $ran tests in $(( SECONDS - start ))s with $JOBS jobs (discover finds $want)"
if [ "$ran" -lt "$want" ]; then echo "FAILED: fewer tests ran than discover finds"; exit 1; fi
if [ "$failed" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "OK"
