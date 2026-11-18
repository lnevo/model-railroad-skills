"""Run the tests by file, some at a time, showing progress and the time left.

  python3 tests/run.py            every test, as unittest discover does
  python3 tests/run.py fast       no real JMRI and a sample of the router answers: run this while working
  python3 tests/run.py test_router test_write       only those files, for the area you are changing
  python3 tests/run.py fast test_router             those files without real JMRI
  python3 tests/run.py --jobs 6   more files at once (default half the cores, at least 2); each can start four JVMs
  python3 tests/run.py status     where a run is now, from any other shell or session

A progress line prints every 15 seconds and as each file ends. The time left comes from what each file took
last time, scaled by how this run is going, so a busy machine moves the estimate rather than breaking it.
Every test's seconds go to tests-all.json or tests-fast.json beside the status file, slowest first.
The longest files start first. A test class that took over SPLIT_CLASS seconds last time runs in a process of its
own, beside the rest of its file, unless the file has a setUpModule. The files of one run share their real JMRI
builds (shared_builds.py), so splitting a file costs no extra builds.
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
from typing import NamedTuple

import shared_builds

TESTS = Path(__file__).resolve().parent
TICK = 15  # seconds between progress lines
DONE = "@@test-done"
MAX_JOBS = 4  # by default: four processes can start sixteen JVMs at once, enough to fill a machine's memory
SPLIT_CLASS = 20  # seconds: a test class slower than this last time gets a process of its own
RUN_STATE = Path(tempfile.gettempdir()) / "operations-pro-tests"
STATUS = RUN_STATE / "status.json"
# In fast mode a test file runs as it would where JMRI is not installed, so the tests that need it skip.
# only and skip name test classes; a test that failed to load always runs, so its error is reported.
ONE_FILE = """
import os, sys, time, unittest
from pathlib import Path
sys.path.insert(0, {servers!r})
import ops_jmri
if {fast!r}:
    ops_jmri.jmri_home = lambda: None
if os.environ.get("OPS_SHARED_BUILDS"):
    import shared_builds
    shared_builds.install(Path(os.environ["OPS_SHARED_BUILDS"]))
class Result(unittest.TextTestResult):
    def startTest(self, test):
        self.began = time.monotonic()
        super().startTest(test)
    def stopTest(self, test):
        super().stopTest(test)
        print({done!r}, round(time.monotonic() - self.began, 2), test.id(), flush=True)
def flat(suite):
    for test in suite:
        yield from flat(test) if isinstance(test, unittest.TestSuite) else [test]
def wanted(test):
    name = type(test).__name__
    if isinstance(test, unittest.loader._FailedTest):
        return True
    return ({only!r} is None or name in {only!r}) and name not in {skip!r}
# loadTestsFromName turns a module that will not import into a failed test, so the error is counted and shown
suite = unittest.TestSuite(t for t in flat(unittest.defaultTestLoader.loadTestsFromName({name!r})) if wanted(t))
runner = unittest.TextTestRunner(resultclass=Result, verbosity=0)
sys.exit(not runner.run(suite).wasSuccessful())
"""


def clock(seconds: float) -> str:
    minutes, seconds = divmod(round(seconds), 60)
    return f"{minutes}m{seconds:02d}s" if minutes else f"{seconds}s"


class Progress:
    """How far a run has got. A file's weight is its seconds last time, or its test count at the average rate."""

    def __init__(self, counts: dict[str, int], history: dict[str, dict]):
        self.lock = threading.Lock()
        self.started = time.monotonic()
        self.timings: list[tuple[float, str]] = []
        self.ran: list[tuple[str, float, str]] = []  # unit name, seconds, test id: which process paid for each test
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

    def tested(self, name: str, seconds: float = 0.0, test: str = "") -> None:
        with self.lock:
            self.files[name]["done"] += 1
            self.timings.append((seconds, test))
            self.ran.append((name, seconds, test))

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


def parse_timing(text: str) -> tuple[float, str] | None:
    """A test's seconds and name from its done line; a test's own output can come before the marker."""
    if DONE not in text:
        return None
    seconds, name = text.split(DONE, 1)[1].split()
    return float(seconds), name


class Unit(NamedTuple):
    """One process: a test file, or some of its classes. only and skip are class names, or None for no limit."""
    name: str
    stem: str
    only: tuple[str, ...] | None = None
    skip: tuple[str, ...] = ()


def plan_units(path: Path, past: dict) -> list[Unit]:
    """The file whole, or each class that took over SPLIT_CLASS seconds last time on its own and the rest together.

    The rest is every class not split off, read by unittest at run time, so a class added since still runs."""
    classes = past.get("classes", {})
    slow = sorted(name for name, (seconds, _) in classes.items() if seconds > SPLIT_CLASS)
    if not slow or re.search(r"^def setUpModule", path.read_text(), re.M):
        return [Unit(path.stem, path.stem)]
    return [*(Unit(f"{path.stem}.{name}", path.stem, (name,)) for name in slow),
            Unit(f"{path.stem} (rest)", path.stem, skip=tuple(slow))]


def unit_history(unit: Unit, past: dict) -> dict:
    """What a unit took last time, from its file's history: the file, its class, or the file less its split classes."""
    classes = past.get("classes", {})
    if unit.only is None and not unit.skip:
        return past
    picked = [row for name, row in classes.items() if (unit.only is None or name in unit.only)
              and name not in unit.skip]
    return {"seconds": sum(r[0] for r in picked), "tests": sum(r[1] for r in picked)} if picked else {}


def run_file(unit: Unit, fast: bool, progress: Progress, builds: str = "") -> tuple[str, int, float, str]:
    progress.start(unit.name)
    started = time.monotonic()
    code = ONE_FILE.format(servers=str(TESTS.parent / "servers"), fast=fast, name=unit.stem, done=DONE,
                           only=None if unit.only is None else set(unit.only), skip=set(unit.skip))
    other = []
    with tempfile.TemporaryDirectory(prefix="opspro-run-") as plans:  # plan folders stay apart between files
        env = dict(os.environ, OPS_TESTS_FAST="1" if fast else "", OPS_PLAN_DIR=plans, OPS_SHARED_BUILDS=builds)
        with subprocess.Popen([sys.executable, "-c", code], cwd=TESTS, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT) as process:
            for text in process.stdout:
                timing = parse_timing(text)
                if timing:
                    progress.tested(unit.name, *timing)
                else:
                    other.append(text)
    progress.finish(unit.name, process.returncode == 0)
    return unit.name, process.returncode, time.monotonic() - started, "".join(other)


def load_history(mode: str) -> dict:
    try:
        return json.loads((RUN_STATE / f"history-{mode}.json").read_text())
    except (OSError, ValueError):
        return {}


def save_history(mode: str, units: list[Unit], results: list, progress: Progress) -> None:
    """Each file's seconds (its units added up), tests, and each class's seconds and tests from the test ids."""
    RUN_STATE.mkdir(exist_ok=True)
    history = load_history(mode)  # a run of some files keeps the times of the others
    took = {name: seconds for name, _, seconds, _ in results}
    classes: dict[str, dict[str, list]] = {}
    stems = {unit.name: unit.stem for unit in units}
    for name, seconds, test in progress.ran:
        parts = test.split(".")
        if len(parts) < 3:  # not module.Class.test, so no class to time
            continue
        # filed under the file whose process ran it: a class imported into another file is timed there too
        row = classes.setdefault(stems.get(name, parts[0]), {}).setdefault(parts[1], [0.0, 0])
        row[0], row[1] = round(row[0] + seconds, 2), row[1] + 1
    for stem in {unit.stem for unit in units}:
        mine = [unit.name for unit in units if unit.stem == stem]
        history[stem] = {"seconds": round(sum(took[name] for name in mine), 1),
                         "tests": sum(progress.files[name]["tests"] for name in mine),
                         "classes": classes.get(stem, {})}
    (RUN_STATE / f"history-{mode}.json").write_text(json.dumps(history))


def split_names(names: list[str]) -> tuple[str, list[str]]:
    """The mode, if the first name is one, and the test files asked for."""
    if names and names[0] in ("all", "fast", "status"):
        return names[0], names[1:]
    return "all", names


def choose_files(every: list[Path], wanted: list[str]) -> list[Path]:
    """The test files named, with or without .py; all of them if none are."""
    if not wanted:
        return every
    stems = [Path(name).stem for name in wanted]
    unknown = sorted(set(stems) - {path.stem for path in every})
    if unknown:
        raise ValueError(f"no test file named {', '.join(unknown)}")
    return [path for path in every if path.stem in stems]


def default_jobs() -> int:
    """Half the cores, from two to MAX_JOBS: each process can run four JVMs, and JVM start-up is most of the work."""
    return min(MAX_JOBS, max(2, (os.cpu_count() or 2) // 2))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", metavar="all|fast|status|test_file")
    parser.add_argument("--jobs", type=int, default=default_jobs())
    args = parser.parse_args()
    args.mode, wanted = split_names(args.names)
    if args.mode == "status":
        return show_status()
    every = sorted(TESTS.glob("test_*.py"))
    try:
        files = choose_files(every, wanted)
    except ValueError as exc:
        parser.error(str(exc))
    history = load_history(args.mode)
    units = [unit for path in files for unit in plan_units(path, history.get(path.stem, {}))]
    counts = {}
    for path in files:
        mine = [unit for unit in units if unit.stem == path.stem]
        total = len(re.findall(r"^\s+def test_", path.read_text(), re.M))
        for unit in mine:  # last time's count, or else the file's own count shared out
            past = unit_history(unit, history.get(path.stem, {}))
            counts[unit.name] = past.get("tests") or max(total // len(mine), 1)
    progress = Progress(counts, {unit.name: unit_history(unit, history.get(unit.stem, {})) for unit in units})
    units.sort(key=lambda unit: -progress.files[unit.name]["weight"])  # longest first, so none starts last
    report(progress)
    shared = args.mode != "fast" and shared_builds.SUPPORTED
    if args.mode != "fast" and not shared:
        print("Real JMRI builds are not shared between files here (no fcntl), so files may build the same folder.")
    with tempfile.TemporaryDirectory(prefix="opspro-builds-") as builds:
        with ThreadPoolExecutor(max(args.jobs, 1)) as pool:
            running = {pool.submit(run_file, unit, args.mode == "fast", progress, builds if shared else "")
                       for unit in units}
            pending, results = running, []
            while pending:
                finished, pending = wait(pending, timeout=TICK, return_when="FIRST_COMPLETED")
                results += [f.result() for f in finished]
                report(progress)
    failed = [r for r in results if r[1]]
    save_history(args.mode, units, results, progress)
    print("Slowest:", ", ".join(f"{name} {clock(seconds)}" for name, _, seconds, _ in
                                sorted(results, key=lambda r: -r[2])[:5]))
    slowest = sorted(progress.timings, reverse=True)
    if not wanted:  # the profile stays a whole run's
        (RUN_STATE / f"tests-{args.mode}.json").write_text(json.dumps(slowest))
    print("Slowest tests:", ", ".join(f"{test.split('.', 1)[-1]} {seconds:.0f}s" for seconds, test in slowest[:5]))
    for name, _, _, output in failed:
        print(f"\nFAILED {name}\n{output[-4000:]}")
    snapshot = progress.snapshot()
    print(f"{'FAILED' if failed else 'PASSED'}: {snapshot['tests_done']} tests in {clock(snapshot['elapsed'])}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
