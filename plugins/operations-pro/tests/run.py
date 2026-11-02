"""Run the tests by file, some at a time, showing progress and the time left.

  python3 tests/run.py            every test, as unittest discover does
  python3 tests/run.py fast       no real JMRI and a sample of the router answers: run this while working
  python3 tests/run.py --jobs 4   more files at once (default 2); each file can start four JVMs of its own
  python3 tests/run.py status     where a run is now, from any other shell or session

A progress line prints every 15 seconds and as each file ends. The time left comes from what each file took
last time, scaled by how this run is going, so a busy machine moves the estimate rather than breaking it.
Run every test before merging: only those hold the plugin to real JMRI.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TICK = 15  # seconds between progress lines
DONE = "@@test-done"
RUN_STATE = Path(tempfile.gettempdir()) / "operations-pro-tests"
STATUS = RUN_STATE / "status.json"
# In fast mode a test file runs as it would where JMRI is not installed, so the tests that need it skip.
ONE_FILE = """
import sys, unittest
sys.path.insert(0, {servers!r})
import ops_jmri
if {fast!r}:
    ops_jmri.jmri_home = lambda: None
class Result(unittest.TextTestResult):
    def stopTest(self, test):
        super().stopTest(test)
        print({done!r}, flush=True)
runner = unittest.TextTestRunner(resultclass=Result, verbosity=0)
sys.exit(not unittest.main(module=None, argv=["run", {name!r}], exit=False, testRunner=runner).result.wasSuccessful())
"""


def clock(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


class Progress:
    """How far a run has got. A file's weight is its seconds last time, or its test count at the average rate."""

    def __init__(self, counts: dict[str, int], history: dict[str, dict]):
        self.lock = threading.Lock()
        self.started = time.monotonic()
        known = [h["seconds"] / max(h["tests"], 1) for h in history.values() if h.get("seconds")]
        rate = sum(known) / len(known) if known else 1.0
        self.files = {}
        for name, count in counts.items():
            past = history.get(name, {})
            tests = past.get("tests") or count
            self.files[name] = {"tests": tests, "done": 0, "weight": max(past.get("seconds") or tests * rate, 0.01),
                                "state": "waiting"}

    def start(self, name: str) -> None:
        with self.lock:
            self.files[name]["state"] = "running"

    def tested(self, name: str) -> None:
        with self.lock:
            self.files[name]["done"] += 1

    def finish(self, name: str, ok: bool) -> None:
        with self.lock:
            row = self.files[name]
            row["state"], row["tests"] = "passed" if ok else "failed", row["done"]

    def seconds_left(self, elapsed: float) -> float | None:
        """Work left at the speed of the work done so far; None until there is any."""
        done = total = 0.0
        for row in self.files.values():
            finished = row["state"] in ("passed", "failed")
            share = 1.0 if finished else min(row["done"] / max(row["tests"], 1), 0.95)
            done += row["weight"] * share
            total += row["weight"]
        return elapsed * (total - done) / done if done else None

    def snapshot(self) -> dict:
        with self.lock:
            elapsed = time.monotonic() - self.started
            rows = self.files.values()
            left = self.seconds_left(elapsed)
            return {"tests_done": sum(r["done"] for r in rows), "tests": sum(r["tests"] for r in rows),
                    "files_done": sum(r["state"] in ("passed", "failed") for r in rows), "files": len(self.files),
                    "failed": [n for n, r in self.files.items() if r["state"] == "failed"],
                    "running": [n for n, r in self.files.items() if r["state"] == "running"],
                    "elapsed": round(elapsed), "seconds_left": None if left is None else round(left),
                    "updated": time.time()}


def line(s: dict) -> str:
    left = "time left unknown" if s["seconds_left"] is None else f"about {clock(s['seconds_left'])} left"
    bad = f", FAILED {', '.join(s['failed'])}" if s["failed"] else ""
    running = f", running {', '.join(s['running'])}" if s["running"] else ""
    return (f"[{s['tests_done']}/{s['tests']} tests, {s['files_done']}/{s['files']} files] "
            f"{clock(s['elapsed'])} so far, {left}{bad}{running}")


def report(progress: Progress) -> None:
    snapshot = progress.snapshot()
    print(line(snapshot), flush=True)
    RUN_STATE.mkdir(exist_ok=True)
    scratch = STATUS.with_suffix(f".{os.getpid()}")
    scratch.write_text(json.dumps({**snapshot, "pid": os.getpid()}))
    scratch.replace(STATUS)  # a reader never sees half a file


def show_status() -> int:
    if not STATUS.is_file():
        print("No test run has reported yet.")
        return 1
    state = json.loads(STATUS.read_text())
    age = clock(time.time() - state["updated"])
    if state["files_done"] == state["files"]:
        print(f"Last run ended {age} ago: {line(state)}")
    else:
        print(f"{line(state)} (reported {age} ago)")
    return 0


def run_file(path: Path, fast: bool, progress: Progress) -> tuple[str, int, float, str]:
    progress.start(path.stem)
    started = time.monotonic()
    code = ONE_FILE.format(servers=str(TESTS.parent / "servers"), fast=fast, name=path.stem, done=DONE)
    other = []
    with tempfile.TemporaryDirectory(prefix="opspro-run-") as plans:  # plan folders stay apart between files
        env = dict(os.environ, OPS_TESTS_FAST="1" if fast else "", OPS_PLAN_DIR=plans)
        with subprocess.Popen([sys.executable, "-c", code], cwd=TESTS, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            for text in process.stdout:
                if text.rstrip().endswith(DONE):
                    progress.tested(path.stem)
                else:
                    other.append(text)
    progress.finish(path.stem, process.returncode == 0)
    return path.stem, process.returncode, time.monotonic() - started, "".join(other)


def load_history(mode: str) -> dict:
    try:
        return json.loads((RUN_STATE / f"history-{mode}.json").read_text())
    except (OSError, ValueError):
        return {}


def save_history(mode: str, results: list, progress: Progress) -> None:
    RUN_STATE.mkdir(exist_ok=True)
    history = {name: {"seconds": round(seconds, 1), "tests": progress.files[name]["tests"]}
               for name, _, seconds, _ in results}
    (RUN_STATE / f"history-{mode}.json").write_text(json.dumps(history))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("mode", nargs="?", choices=("all", "fast", "status"), default="all")
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.mode == "status":
        return show_status()
    files = sorted(TESTS.glob("test_*.py"))
    counts = {p.stem: len(re.findall(r"^\s+def test_", p.read_text(), re.M)) for p in files}
    progress = Progress(counts, load_history(args.mode))
    report(progress)
    with ThreadPoolExecutor(max(args.jobs, 1)) as pool:
        running = {pool.submit(run_file, path, args.mode == "fast", progress) for path in files}
        pending, results = running, []
        while pending:
            finished, pending = wait(pending, timeout=TICK, return_when="FIRST_COMPLETED")
            results += [f.result() for f in finished]
            report(progress)
    failed = [r for r in results if r[1]]
    save_history(args.mode, results, progress)
    print("Slowest:", ", ".join(f"{name} {clock(seconds)}" for name, _, seconds, _ in
                                sorted(results, key=lambda r: -r[2])[:5]))
    for name, _, _, output in failed:
        print(f"\nFAILED {name}\n{output[-4000:]}")
    snapshot = progress.snapshot()
    print(f"{'FAILED' if failed else 'PASSED'}: {snapshot['tests_done']} tests in {clock(snapshot['elapsed'])}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
