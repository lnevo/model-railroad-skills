#!/usr/bin/env bash
# Run one shard of the test files in one process: SHARD=i/N (default 1/1, every file).
# Files are dealt out by their usual CI time, slowest first to the lightest shard,
# so every file is in exactly one shard and the shards take about the same time.
# CI runs 3 shards on 3 runners: 4 files at once on one runner slowed every file
# about 3x, and a process per file rebuilt the shared example each time.
# Fails if any test fails, or if fewer tests ran than discover finds in the shard's files.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
SHARD="${SHARD:-1/1}"

# Seconds per file on a CI runner (2026-11-25, 4 at once); a file not listed counts 1.
WEIGHTS="test_le_labels:73 test_le:32 test_unsettled_columns:31 test_cache:28 test_le_prefs:25
test_slots:20 test_orient_fallback:13 test_solve_limits:12 test_le_masts:10 test_cats:9
test_drawing:8 test_rows:4 test_solver_speed:4 test_turnbacks:4 test_detail:3 test_track_labels:3
test_fold:2 test_xover_slide:2"

exec "$PY" - "$SHARD" "$WEIGHTS" <<'EOF'
import pathlib, sys, time, unittest

shard, weights = sys.argv[1], sys.argv[2]
try:
    i, n = (int(x) for x in shard.split("/"))
    assert 1 <= i <= n
except (ValueError, AssertionError):
    sys.exit(f"SHARD must be i/N with 1 <= i <= N, got {shard}")

w = dict((k, int(v)) for k, v in (p.split(":") for p in weights.split()))
names = sorted(p.stem for p in pathlib.Path("tests").glob("test_*.py"))
load, shards = [0] * n, [[] for _ in range(n)]
for f in sorted(names, key=lambda f: (-w.get(f, 1), f)):
    k = min(range(n), key=lambda s: (load[s], s))
    load[k] += w.get(f, 1)
    shards[k].append(f)
files = shards[i - 1]
if not files:
    sys.exit(f"shard {shard} has no files")
print(f"Shard {shard}: {' '.join(files)}", flush=True)

def count(s):
    return sum(count(t) for t in s) if isinstance(s, unittest.TestSuite) else 1

loader = unittest.defaultTestLoader
suite = unittest.TestSuite(loader.discover("tests", pattern=f + ".py") for f in files)
want = count(suite)
start = time.monotonic()
result = unittest.TextTestRunner(verbosity=1).run(suite)
print(f"Shard {shard}: ran {result.testsRun} tests in {time.monotonic() - start:.0f}s "
      f"(discover finds {want} in these files)")
if result.testsRun < want:
    sys.exit("FAILED: fewer tests ran than discover finds")
sys.exit(0 if result.wasSuccessful() else 1)
EOF
