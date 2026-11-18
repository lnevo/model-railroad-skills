"""Share real JMRI builds between the test processes of one tests/run.py run.

ops_build_state already keeps each build batch (every enabled train, or one train alone, RUNS times) for the
life of one process. Each test file runs in a process of its own, so files that ask about the same folder used
to build it again: about a fifth of all JVM starts in a full run. run.py points OPS_SHARED_BUILDS at a folder
it makes for that run and removes at the end; install() then keeps each batch there, so the first process to
need it builds it with real JMRI and the others read that result. A lock per batch makes a second process wait
for the first instead of building the same thing beside it. Nothing outlives the run, so a code or fixture
change is always built fresh.

Each call in one process gets a batch of its own, as it would without sharing: the second call for the same
folder and job in a process (build_check's after sample of an unchanged folder, say) reads the second batch kept
for that key, never the first, so two samples one process compares stay independent JMRI builds.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

try:
    import fcntl
except ImportError:  # Windows: no flock, so run.py does not share builds there.
    fcntl = None

ENV = "OPS_SHARED_BUILDS"
SUPPORTED = fcntl is not None


def _key(directory: Path, job: dict, runs: int) -> str:
    """Everything that decides a batch: the files, the job, the run count, the JMRI install and the worker."""
    import ops_build_state
    import ops_jmri
    home = ops_jmri.jmri_home()
    jar = (home / "jmri.jar").stat() if home else None
    parts = [ops_build_state._digest(directory), json.dumps(job, sort_keys=True), str(runs),
             f"{home}|{jar.st_size}|{jar.st_mtime_ns}" if jar else "no JMRI",
             hashlib.sha256(Path(ops_jmri.WORKER).read_bytes()).hexdigest()]
    return hashlib.sha256("\n".join(parts).encode()).hexdigest()


def install(folder: Path) -> None:
    """Make ops_build_state.run_builds keep its batches in folder, shared by every process given the same one."""
    import ops_build_state
    if not SUPPORTED:
        raise RuntimeError("shared builds need fcntl.flock, which this platform does not have")
    if not folder.is_dir():
        raise RuntimeError(f"{ENV} names {folder}, which is not a folder")
    build = ops_build_state.run_builds
    calls: dict[str, int] = {}  # this process's calls so far, per key

    def shared(directory: Path, job: dict, runs: int) -> list[dict]:
        key = _key(directory, job, runs)
        calls[key] = calls.get(key, 0) + 1
        key = f"{key}-{calls[key]}"
        saved = folder / f"{key}.json"
        with open(folder / f"{key}.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)  # released when the file closes
            if saved.is_file():
                return json.loads(saved.read_text(encoding="utf-8"))
            results = build(directory, job, runs)
            scratch = saved.with_suffix(f".{os.getpid()}")
            scratch.write_text(json.dumps(results), encoding="utf-8")
            scratch.replace(saved)
            return results

    ops_build_state.run_builds = shared
