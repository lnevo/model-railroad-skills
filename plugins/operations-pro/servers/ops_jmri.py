"""Run real JMRI on a scratch copy: the build check, dry runs and Set Car with a schedule.

JMRI never sees the live folder here. Each run gets its own home folder, so it cannot
touch the user's profile or preferences.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import ops_report
from ops_data import load
from ops_store import FILES, Refused, plans_root, quick

SEARCH = ("/Applications/JMRI", "/opt/JMRI", "/usr/local/JMRI", "~/JMRI", r"C:\Program Files\JMRI", r"C:\JMRI")
WORKER = Path(__file__).with_name("jmri_worker.py")
TESTED = "5.16"
TIMEOUT = 300
LOG_ERRORS = 40  # lines kept; a refused build order logs one for each train
SUMMARY_CARS = 25  # cars listed per train in a dry run summary


def jmri_home() -> Path | None:
    for text in (os.environ.get("JMRI_HOME"), *SEARCH):
        if text and (Path(text).expanduser() / "jmri.jar").is_file():
            return Path(text).expanduser()
    return None


def java_command() -> str:
    home = os.environ.get("JAVA_HOME")
    return str(Path(home) / "bin" / "java") if home else "java"


def _refused_before_build(name: str, row: dict, log_errors: list[str]) -> str:
    """Train.build returns before any report when checkBuildOrder refuses (Train:3193-3196): status Error, no
    failure flag, and only a log line says why (TrainManager:1107-1118)."""
    if row["built"] or row["failed"] or row["message"] != "Error":
        return ""
    line = next((e for e in log_errors if f"Train ({name}) departs" in e), "")
    why = line.split(" ERROR ", 1)[-1] if line else "no log line names it"
    return f"Build on time refused this train before building, so there is no report: {why}. See gate A2."


def run_worker(source: Path, job: dict, keep: Path | None = None) -> dict:
    """Copy the files from source and run one job. With keep, leave the saved files and build reports there."""
    home = jmri_home()
    if home is None:
        raise Refused("JMRI was not found. Set JMRI_HOME to the folder holding jmri.jar.")
    with tempfile.TemporaryDirectory(prefix="opspro-") as scratch:
        root = Path(scratch)
        operations = root / "operations"
        operations.mkdir()
        for name in FILES:
            if (source / name).is_file():
                shutil.copy2(source / name, operations / name)
        output = root / "result.json"
        # Jython finds Java packages by scanning named jars, so a wildcard will not do.
        jars = [home / "jmri.jar", *sorted((home / "lib").glob("*.jar"))]
        classpath = os.pathsep.join(str(jar) for jar in jars)
        command = [java_command(), "-Djava.awt.headless=true", f"-Duser.home={root}", f"-Djmri.prefsdir={root}",
                   f"-Dops.home={root}", f"-Dpython.cachedir={root / 'jython-cache'}", "-Dpython.cachedir.skip=false", f"-Dworker.out={output}", f"-Dworker.job={json.dumps(job)}",
                   "-cp", classpath, "org.python.util.jython", str(WORKER)]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=TIMEOUT, cwd=root)
        except subprocess.TimeoutExpired as exc:
            raise Refused(f"JMRI did not finish in {TIMEOUT} seconds") from exc
        except OSError as exc:
            raise Refused(f"Could not start Java: {exc}") from exc
        if not output.is_file():
            raise Refused("JMRI stopped without a result: " + (done.stderr or done.stdout)[-800:])
        result = json.loads(output.read_text(encoding="utf-8"))
        result["log_errors"] = [line[:240] for line in (done.stdout + done.stderr).splitlines()
                                if " ERROR " in line or "Exception" in line][:LOG_ERRORS]
        for name, row in result.get("builds", {}).items():
            report = Path(row.pop("report", "") or "/nonexistent")
            text = report.read_text(encoding="utf-8", errors="replace") if report.is_file() else ""
            row["report_text"], row["report_tail"] = text, text[-1500:]
            refused = _refused_before_build(name, row, result["log_errors"])
            if refused:
                row["refused_before_build"] = refused
        if keep is not None:
            for name in FILES:
                if (operations / name).is_file():
                    shutil.copy2(operations / name, keep / name)
            if (operations / "buildstatus").is_dir():
                shutil.copytree(operations / "buildstatus", keep / "buildstatus", dirs_exist_ok=True)
            if (operations / "manifests").is_dir():  # Manifest formats: what JMRI printed with them.
                shutil.copytree(operations / "manifests", keep / "manifests", dirs_exist_ok=True)
        return result


DETAILS = ("summary", "normal", "full")


def attach_report(row: dict, detail: str = "summary") -> dict:
    """Replace a build's raw report text with the build report reader's answer.

    detail: summary (the default: outcome and the plain-language findings), normal (also
    stops, excluded cars and each car's story) or full, as ops_explain_build gives them.
    The old character tail stays only when there is no report to read.
    """
    if detail not in DETAILS:
        raise Refused(f"detail must be one of: {', '.join(DETAILS)}")
    text, tail = row.pop("report_text", ""), row.pop("report_tail", "")
    try:
        explained = ops_report.explain(text, detail="full" if detail == "full" else "normal") if text else None
    except Exception as exc:  # a report this reader cannot parse still has its tail
        explained = None
        row["report_note"] = f"The build report could not be read ({exc}); showing the end of it."
    if explained is None:
        row["report_tail"] = tail
        return row
    if detail == "summary":
        explained = {k: explained[k] for k in ("train", "built_on", "outcome", "summary")}
    row["report"] = explained
    return row


def _outcome(result: dict) -> dict:
    return {name: {"built": row["built"], "cars": row["cars"]} for name, row in result["builds"].items()}


def _version_note(result: dict) -> list[str]:
    version = result.get("version", "")
    return [] if version.startswith(TESTED) else [f"Rules were checked on JMRI {TESTED}; this is {version}."]


def _sample(source: Path, runs: int) -> list[dict]:
    with ThreadPoolExecutor(max_workers=min(runs, 4)) as pool:
        return list(pool.map(lambda _: run_worker(source, {"build": True}), range(runs)))


def _variants(results: list[dict]) -> dict[str, list[dict]]:
    """Each train's distinct outcomes across the runs, without repeats."""
    found: dict[str, list[dict]] = {}
    for result in results:
        for name, row in _outcome(result).items():
            if row not in found.setdefault(name, []):
                found[name].append(row)
    return found


def build_check(plan_id: str, runs: int = 4) -> dict:
    """Build every enabled train several times before and after a plan, on copies, and compare.

    The builder makes random choices, so one run proves little. A train counts as changed
    only if none of its results after the plan appeared before it. A partial overlap is
    reported as possibly_changed, and rare outcomes can still be missed.
    """
    folder = plans_root() / plan_id
    if not (folder / "plan.json").is_file():
        raise Refused(f"No plan {plan_id}")
    if not 1 <= runs <= 20:
        raise Refused("runs must be 1 to 20")
    manifest = json.loads((folder / "plan.json").read_text(encoding="utf-8"))
    before_runs = _sample(Path(manifest["ops_dir"]), runs)
    after_runs = _sample(folder / "after", runs)
    before, after = _variants(before_runs), _variants(after_runs)
    changed, possibly = {}, {}
    for name in sorted(set(before) | set(after)):
        old, new = before.get(name, []), after.get(name, [])
        shared = [row for row in new if row in old]
        if not shared:
            changed[name] = {"before": old, "after": new}
        elif len(shared) != len(new) or len(shared) != len(old):
            possibly[name] = {"only_before": [r for r in old if r not in new],
                              "only_after": [r for r in new if r not in old]}
    built = lambda rows: any(r["built"] for r in rows)  # noqa: E731
    last = after_runs[-1]
    return {"jmri": last["version"], "runs_each_side": runs,
            "now_fail": sorted(n for n in before if built(before[n]) and not built(after.get(n, []))),
            "now_build": sorted(n for n in after if built(after[n]) and not built(before.get(n, []))),
            "varies_by_itself": sorted(n for n, rows in before.items() if len(rows) > 1),
            "changed": changed, "possibly_changed": possibly,
            "failures_after": {n: r.get("refused_before_build") or r["message"] for n, r in last["builds"].items()
                                if r["failed"] or r.get("refused_before_build")},
            "jmri_log_errors": last["log_errors"], "notes": _version_note(last)}


def dry_run(directory: str | Path, terminate: bool = True, detail: str = "summary") -> dict:
    """A whole session on a copy: build all, terminate all, report. The real files are not touched."""
    result = run_worker(load(directory).directory, {"build": True, "terminate": terminate})
    builds = {name: attach_report(row, detail) for name, row in result["builds"].items()}
    return {"jmri": result["version"], "builds": builds, "jmri_log_errors": result["log_errors"],
            "notes": _version_note(result)}


CAR_ATTRS = ("load", "wait", "pickupId", "scheduleId", "nextDestId", "nextDestTrackId", "nextLoad", "routePath",
             "locationId", "secLocationId")


def deliver_car(directory: str | Path, car: str, location: str, track: str) -> dict:
    """Set a car on a track and run its schedule the way Set Car does, using JMRI on a copy.

    A JMRI save regenerates whole files, so only what the delivery changed is taken back.
    """
    rr = load(directory)
    target = rr.find_car(car)
    if target.train_id or target.destination_id:
        raise Refused(f"{target} is assigned to a train. Reset or terminate that train first.")
    here = rr.tracks.get(target.track_id)
    if here is not None and here.name == track and rr.locations[here.location_id].name == location:
        # CarSetFrame.applySchedule (CarSetFrame:600-604) runs only when the track changes.
        raise Refused(f"{target} is already on {track}, and Set Car applies a schedule only when the track "
                      "changes. To load a car parked there before the schedule was added, set its load with "
                      "ops_session update_car, or deliver it to another track and back.")
    with tempfile.TemporaryDirectory(prefix="opspro-saved-") as saved:
        keep = Path(saved)
        result = run_worker(rr.directory, {"car": target.id, "location": location, "track": track, "save": True}, keep)
        if result.get("refused"):
            raise Refused(result["refused"])
        new_car = next(c for c in ET.parse(keep / FILES[3]).getroot().findall("./cars/car")
                       if c.get("id") == target.id)
        tracks = {t.get("id"): t for t in ET.parse(keep / FILES[0]).getroot().iter("track")}
        items = {i.get("id"): i for i in ET.parse(keep / FILES[0]).getroot().iter("item")}

    def prepare(editor) -> tuple[list[str], tuple[str, ...]]:
        element = editor.car(target.id)
        editor.clear_last_route(element)  # RollingStockSetFrame:476-479; the worker calls setLocation only.
        for attr in CAR_ATTRS:
            element.attrib.pop(attr, None)
            if new_car.get(attr):
                element.set(attr, new_car.get(attr))
        place = editor.location(location)
        spur = editor._one(place.findall("track"), track, "track")
        fresh = tracks[spur.get("id")]
        for attr in ("itemId", "itemCount"):
            if fresh.get(attr) is not None:
                spur.set(attr, fresh.get(attr))
        for item in editor.loc_root.iter("item"):
            if item.get("id") in items:
                item.set("hits", items[item.get("id")].get("hits", "0"))
        return [f"{target} set on {track}: load is now {new_car.get('load', rr.default_empty)}."], (target.id,)

    return quick(directory, [], prepare=prepare)

