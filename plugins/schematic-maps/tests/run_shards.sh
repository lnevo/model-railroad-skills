#!/usr/bin/env bash
# Run one shard of the test files in one process: SHARD=i/N (default 1/1, every file).
# Files are dealt out by their usual CI time, slowest first to the lightest shard,
# so every file is in exactly one shard and the shards take about the same time.
# CI runs 3 shards on 3 runners: 4 files at once on one runner slowed every file
# about 3x, and a process per file rebuilt the shared example each time.
# Fails if any test fails or a file does not import, or if a weight names no test file.
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-python3}"
SHARD="${SHARD:-1/1}"

# Seconds per file on a CI runner, run alone one after another (2026-11-24); a file
# not listed counts 1. test_le_labels (41 s alone) is weighted 70 so it has a shard
# to itself: next to other files in one process its shard took 63-64 s in two runs
# (cause not checked). A single runner's time swings about 2x, so balance on several runs.
WEIGHTS="test_le_labels:70 test_le:21 test_unsettled_columns:18 test_le_prefs:16 test_cache:15
test_slots:12 test_orient_fallback:8 test_solve_limits:6 test_cats:6 test_le_masts:5 test_drawing:5
test_solver_speed:3 test_xover_slide:2 test_turnbacks:2 test_rows:2 test_detail:2"

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
stale = sorted(set(w) - set(names))
if stale:
    sys.exit(f"WEIGHTS names files that are not in tests/: {' '.join(stale)}")
load, shards = [0] * n, [[] for _ in range(n)]
for f in sorted(names, key=lambda f: (-w.get(f, 1), f)):
    k = min(range(n), key=lambda s: (load[s], s))
    load[k] += w.get(f, 1)
    shards[k].append(f)
files = shards[i - 1]
if not files:
    sys.exit(f"shard {shard} has no files")
print(f"Shard {shard}: {' '.join(files)}", flush=True)

loader = unittest.defaultTestLoader
suite = unittest.TestSuite(loader.discover("tests", pattern=f + ".py") for f in files)
start = time.monotonic()
result = unittest.TextTestRunner(verbosity=1).run(suite)
print(f"Shard {shard}: ran {result.testsRun} tests in {time.monotonic() - start:.0f}s")
sys.exit(0 if result.wasSuccessful() else 1)
EOF
