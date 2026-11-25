#!/usr/bin/env bash
# Run the test files, each in its own process.
#   SHARD=i/N  run only shard i of N. Files are dealt out by their usual time,
#              slowest first to the lightest shard, so every file is in exactly
#              one shard and the shards take about the same time. CI uses 3.
#   JOBS=n     files at a time within the run (default 1). A CI runner slows every
#              file about 3x at 4 at once, so CI splits across runners instead.
# Fails if any file fails, or if fewer tests ran than discover finds in the run's files.
set -euo pipefail
cd "$(dirname "$0")/.."

JOBS="${JOBS:-1}"
PY="${PYTHON:-python3}"
SHARD="${SHARD:-1/1}"
i="${SHARD%/*}"; n="${SHARD#*/}"
case "$i$n" in *[!0-9]*|"") echo "SHARD must be i/N, got $SHARD" >&2; exit 2 ;; esac
if [ "$i" -lt 1 ] || [ "$i" -gt "$n" ]; then echo "SHARD must be i/N with 1 <= i <= N, got $SHARD" >&2; exit 2; fi

# Seconds per file on a CI runner (2026-11-25, 4 at once); a file not listed counts 1.
WEIGHTS="test_le_labels:73 test_le:32 test_unsettled_columns:31 test_cache:28 test_le_prefs:25
test_slots:20 test_orient_fallback:13 test_solve_limits:12 test_le_masts:10 test_cats:9
test_drawing:8 test_rows:4 test_solver_speed:4 test_turnbacks:4 test_detail:3 test_track_labels:3
test_fold:2 test_xover_slide:2"

files=()
while IFS= read -r f; do files+=("$f"); done < <("$PY" - "$i" "$n" "$WEIGHTS" <<'EOF'
import pathlib, sys
i, n, weights = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3]
w = dict((k, int(v)) for k, v in (p.split(":") for p in weights.split()))
names = sorted(p.stem for p in pathlib.Path("tests").glob("test_*.py"))
order = sorted(names, key=lambda f: (-w.get(f, 1), f))
load, shards = [0] * n, [[] for _ in range(n)]
for f in order:
    k = min(range(n), key=lambda s: (load[s], s))
    load[k] += w.get(f, 1)
    shards[k].append(f)
print("\n".join(shards[i - 1]))
EOF
)
[ "${#files[@]}" -gt 0 ] || { echo "shard $SHARD has no files"; exit 1; }

logs="$(mktemp -d)"
trap 'rm -rf "$logs"' EXIT

start=$SECONDS
printf '%s\n' "${files[@]}" | xargs -P "$JOBS" -I{} sh -c '
  t0=$(date +%s)
  if "$1" -m unittest discover -s tests -p "$2.py" >"$3/$2.log" 2>&1; then r=ok; else r=FAILED; fi
  echo "$r $(( $(date +%s) - t0 ))s" >"$3/$2.status"
' _ "$PY" {} "$logs"

ran=0; failed=0
for f in "${files[@]}"; do
  status="$(cat "$logs/$f.status" 2>/dev/null || echo "FAILED no status")"
  c="$(sed -n 's/^Ran \([0-9]*\) tests\{0,1\} in .*/\1/p' "$logs/$f.log" | tail -1)"
  ran=$(( ran + ${c:-0} ))
  echo "$f: $status, ${c:-0} tests"
  case "$status" in ok*) ;; *) failed=1; cat "$logs/$f.log" ;; esac
done

want="$("$PY" - "${files[@]}" <<'EOF'
import sys, unittest
sys.path.insert(0, "tests")
def count(s):
    return sum(count(t) for t in s) if isinstance(s, unittest.TestSuite) else 1
print(sum(count(unittest.defaultTestLoader.discover("tests", pattern=f + ".py")) for f in sys.argv[1:]))
EOF
)"
echo "Shard $SHARD: ran $ran tests in $(( SECONDS - start ))s, $JOBS at a time (discover finds $want in these files)"
if [ "$ran" -lt "$want" ]; then echo "FAILED: fewer tests ran than discover finds"; exit 1; fi
if [ "$failed" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "OK"
