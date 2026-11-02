"""Run the tests by file, some at a time, and say what took longest.

  python3 tests/run.py            every test, as unittest discover does
  python3 tests/run.py fast       no real JMRI and a sample of the router answers: run this while working
  python3 tests/run.py --jobs 4   more files at once (default 2); each file can start four JVMs of its own

Run every test before merging: only those hold the plugin to real JMRI.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

TESTS = Path(__file__).resolve().parent
# In fast mode a test file runs as it would where JMRI is not installed, so the tests that need it skip.
ONE_FILE = """
import sys, unittest
sys.path.insert(0, {servers!r})
import ops_jmri
if {fast!r}:
    ops_jmri.jmri_home = lambda: None
sys.exit(not unittest.main(module=None, argv=["run", {name!r}], exit=False, verbosity=0).result.wasSuccessful())
"""


def run_file(path: Path, fast: bool) -> tuple[str, int, float, str]:
    started = time.monotonic()
    env = dict(os.environ, OPS_TESTS_FAST="1" if fast else "")
    code = ONE_FILE.format(servers=str(TESTS.parent / "servers"), fast=fast, name=path.stem)
    with tempfile.TemporaryDirectory(prefix="opspro-run-") as plans:  # plan folders stay apart between files
        done = subprocess.run([sys.executable, "-c", code], cwd=TESTS, capture_output=True, text=True,
                              env=dict(env, OPS_PLAN_DIR=plans))
    return path.stem, done.returncode, time.monotonic() - started, done.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", choices=("all", "fast"), default="all")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    started = time.monotonic()
    files = sorted(TESTS.glob("test_*.py"))
    with ThreadPoolExecutor(max(args.jobs, 1)) as pool:
        results = list(pool.map(lambda path: run_file(path, args.mode == "fast"), files))
    failed = [r for r in results if r[1]]
    for name, _, seconds, _ in sorted(results, key=lambda r: -r[2])[:5]:
        print(f"{seconds:6.1f}s {name}")
    for name, _, _, errors in failed:
        print(f"\nFAILED {name}\n{errors[-4000:]}")
    print(json.dumps({"files": len(files), "failed": [r[0] for r in failed], "seconds": round(time.monotonic() - started)}))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
