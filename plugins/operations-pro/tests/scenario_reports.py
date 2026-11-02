"""Small railroads, built from an empty folder with the plugin's own actions, whose real JMRI 5.16
build reports test the report reader on failures the demo does not have.

SCENARIOS names each one: its actions, how many JMRI sessions (build, terminate, save) run first,
and the train whose report is kept. main() writes tests/fixtures/reports/NAME.txt; test_report.py
reads those files, so it needs no JMRI. Needs JMRI installed (JMRI_HOME if not found).

  python3 tests/scenario_reports.py [NAME ...]
"""
import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_jmri  # noqa: E402
import ops_store  # noqa: E402

OUT = ROOT / "tests" / "fixtures" / "reports"


def cars(road, first, count, kind, length, location, track, **extra):
    return [{"action": "add_car", "road": road, "number": str(first + i), "type": kind, "length": length,
             "location": location, "track": track, **extra} for i in range(count)]


# A turn whose caboose track is an interchange with Pick ups Any: each session's caboose comes back to
# it, set out by the same route, so after three sessions none can be picked up (B6).
CABOOSE_TURN = [
    {"action": "add_location", "name": "Alden", "directions": "East/West"},
    {"action": "add_track", "location": "Alden", "name": "Alden Yard", "type": "Yard", "length": 600},
    {"action": "add_track", "location": "Alden", "name": "Caboose Track", "type": "Interchange", "length": 200},
    {"action": "add_location", "name": "Brook", "directions": "East/West"},
    {"action": "add_track", "location": "Brook", "name": "Brook Siding", "type": "Yard", "length": 300},
    {"action": "add_route", "name": "Brook Turn", "stops": [
        {"location": "Alden", "direction": "East"}, {"location": "Brook", "direction": "East"},
        {"location": "Alden", "direction": "West"}]},
    {"action": "add_train", "name": "BT", "route": "Brook Turn", "requires": "caboose"},
    {"action": "update_track", "track": "Alden Yard", "remove_types": ["Caboose"]},
    *cars("AR", 101, 4, "Boxcar", 40, "Alden", "Alden Yard"),
    *cars("AR", 901, 3, "Caboose", 30, "Alden", "Caboose Track"),
    *({"action": "update_car", "car": f"AR{n}", "caboose": True} for n in (901, 902, 903)),
]

# The same turn with its caboose track a yard that serves only westbound trains (C9).
CABOOSE_DIRECTION = [dict(a, type="Yard", directions="West") if a.get("name") == "Caboose Track" else a
                     for a in CABOOSE_TURN]

STAGING_CAR_TYPE = [
    {"action": "add_location", "name": "KC Staging", "types": ["Boxcar", "Tank Oil"]},
    {"action": "add_track", "location": "KC Staging", "name": "KC 6", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Lynn", "types": ["Boxcar", "Tank Oil"]},
    {"action": "add_track", "location": "Lynn", "name": "Lynn Yard", "type": "Yard", "length": 600},
    {"action": "add_route", "name": "Local East", "stops": [{"location": "KC Staging", "direction": "East"},
                                                            {"location": "Lynn", "direction": "East"}]},
    {"action": "add_train", "name": "ML", "route": "Local East", "remove_types": ["Tank Oil"]},
    *cars("KC", 1, 1, "Boxcar", 40, "KC Staging", "KC 6"),
    *cars("KC", 2, 1, "Tank Oil", 40, "KC Staging", "KC 6"),
]

# Aggressive mode fills the train at Hill before the staging cars are placed; the staging cars then
# fail on train length (D9), though the yard at Hill refuses them for room (E9) more often.
AGGRESSIVE_LENGTH = [
    {"action": "add_location", "name": "Gate Staging", "types": ["Hopper"]},
    {"action": "add_track", "location": "Gate Staging", "name": "Gate 1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Hill", "types": ["Hopper"]},
    {"action": "add_track", "location": "Hill", "name": "Hill Yard", "type": "Yard", "length": 0},
    {"action": "add_track", "location": "Hill", "name": "Hill Elevator", "type": "Spur", "length": 400,
     "loads": {"option": "Include", "names": ["L"]}},
    {"action": "add_location", "name": "Iron", "types": ["Hopper"]},
    {"action": "add_track", "location": "Iron", "name": "Iron Yard", "type": "Yard", "length": 800},
    {"action": "add_route", "name": "Grain Run", "stops": [
        {"location": "Gate Staging", "direction": "East", "max_moves": 7, "max_length": 400},
        {"location": "Hill", "direction": "East", "max_moves": 10, "max_length": 400},
        {"location": "Iron", "direction": "East", "max_moves": 10}]},
    {"action": "add_train", "name": "G1", "route": "Grain Run"},
    {"action": "set_option", "group": "buildOptions", "name": "aggressive", "value": True},
    {"action": "set_option", "group": "buildOptions", "name": "stagingTryNormal", "value": False},
    *cars("GR", 700, 7, "Hopper", 40, "Gate Staging", "Gate 1"),
    *cars("GR", 800, 7, "Hopper", 40, "Hill", "Hill Elevator", load="L"),
]

# A full swap with planned pick ups but too few moves: the last cars are never tried.
MOVES_OUT = [
    {"action": "add_location", "name": "Alden", "types": ["Boxcar"]},
    {"action": "add_track", "location": "Alden", "name": "Alden Yard", "type": "Yard", "length": 330,
     "ignore_used_percent": 100},
    {"action": "add_location", "name": "Birch", "types": ["Boxcar"]},
    {"action": "add_track", "location": "Birch", "name": "Birch Mill", "type": "Spur", "length": 330,
     "ignore_used_percent": 100},
    {"action": "add_route", "name": "Birch Turn", "stops": [
        {"location": "Alden", "direction": "East", "max_moves": 5},
        {"location": "Birch", "direction": "East", "max_moves": 5},
        {"location": "Alden", "direction": "West", "max_moves": 5}]},
    {"action": "add_train", "name": "T1", "route": "Birch Turn"},
    *cars("AB", 100, 7, "Boxcar", 40, "Alden", "Alden Yard"),
    *cars("AB", 200, 7, "Boxcar", 40, "Birch", "Birch Mill"),
]

# Empties with a home division that no location on the train's reach belongs to.
DIVISION_EMPTIES = [
    {"action": "add_location", "name": "West Stage"},
    {"action": "add_track", "location": "West Stage", "name": "WS1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Millton"},
    {"action": "add_track", "location": "Millton", "name": "Millton Yard", "type": "Yard", "length": 400},
    {"action": "add_track", "location": "Millton", "name": "Millton Mill", "type": "Spur", "length": 200},
    {"action": "add_location", "name": "East Stage"},
    {"action": "add_track", "location": "East Stage", "name": "ES1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Northfield"},
    {"action": "add_track", "location": "Northfield", "name": "Northfield Yard", "type": "Yard", "length": 400},
    {"action": "add_route", "name": "Main East", "stops": [
        {"location": "West Stage", "direction": "East"}, {"location": "Millton", "direction": "East"},
        {"location": "East Stage", "direction": "East"}]},
    {"action": "add_train", "name": "E1", "route": "Main East"},
    *cars("VR", 100, 2, "Boxcar", 40, "West Stage", "WS1"),
    {"action": "add_division", "name": "Valley"},
    {"action": "add_division", "name": "North"},
    {"action": "set_location_division", "division": "Valley", "locations": ["West Stage", "Millton", "East Stage"]},
    {"action": "set_location_division", "division": "North", "locations": ["Northfield"]},
    {"action": "set_car_division", "division": "North", "cars": ["VR100", "VR101"]},
]

# A train that asks for two locomotives where there are none.
NO_ENGINES = [
    {"action": "add_location", "name": "Alden"},
    {"action": "add_track", "location": "Alden", "name": "Alden Yard", "type": "Yard", "length": 400},
    {"action": "add_location", "name": "Birch"},
    {"action": "add_track", "location": "Birch", "name": "Birch Yard", "type": "Yard", "length": 400},
    {"action": "add_route", "name": "Run", "stops": [{"location": "Alden"}, {"location": "Birch"}]},
    {"action": "add_train", "name": "P2", "route": "Run", "engines": "2"},
    *cars("AB", 1, 2, "Boxcar", 40, "Alden", "Alden Yard"),
]

# name: (actions, sessions before the kept build, train)
SCENARIOS = {
    "caboose_same_route": (CABOOSE_TURN, 3, "BT"),
    "caboose_direction": (CABOOSE_DIRECTION, 0, "BT"),
    "staging_car_type": (STAGING_CAR_TYPE, 0, "ML"),
    "aggressive_length": (AGGRESSIVE_LENGTH, 0, "G1"),
    "moves_out": (MOVES_OUT, 0, "T1"),
    "division_empties": (DIVISION_EMPTIES, 0, "E1"),
    "no_engines": (NO_ENGINES, 0, "P2"),
}


def build(name: str, keep: Path) -> str:
    """Make the railroad in keep, run its sessions, build once more and return the train's report."""
    actions, sessions, train = SCENARIOS[name]
    with mock.patch.object(ops_store, "running_jmri", return_value=[]), \
            mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(keep.parent / f"{name}-plans")}):
        ops_store.apply(ops_store.plan(keep, actions)["plan_id"], allow_new_errors=True)
    for _ in range(sessions):
        ops_jmri.run_worker(keep, {"build": True, "terminate": True, "save": True}, keep)
    if (keep / "buildstatus").is_dir():
        shutil.rmtree(keep / "buildstatus")
    ops_jmri.run_worker(keep, {"build": True}, keep)
    return (keep / "buildstatus" / f"train ({train}).txt").read_text(encoding="utf-8")


def main(names: list[str]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="opspro-scenarios-") as scratch:
        for name in names or SCENARIOS:
            keep = Path(scratch) / name / "operations"
            keep.mkdir(parents=True)
            (OUT / f"{name}.txt").write_text(build(name, keep), encoding="utf-8")
            print(name, "written")


if __name__ == "__main__":
    main(sys.argv[1:])
