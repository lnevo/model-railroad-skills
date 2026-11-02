"""The showcase railroad, whole: every case of examples/showcase/GUIDE.md asserted on the shipped folder.

The shipped folder is examples/showcase/operations/. It is copied into three chains, and each chain runs three
consecutive real JMRI sessions (build every train, terminate, save, carry the saved files forward). A deterministic
case asserts in every chain; the random one (U08) asserts over the union. Experiments ("Try this") run on scratch
copies with real JMRI and are asserted too. JMRI-backed tests skip where JMRI is not installed.

Sections: general checks, then one class per group of cases (A staging, B Brae and Dunmere, C Hollis and Oakhaven,
D Ferris, Northwood and Pell Creek, E Hop, Kessock, Sawyer, oil and passenger, F days, automation, paperwork,
on-time order and backups). Run time is about five minutes.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "showcase"
SHOWCASE = EXAMPLE / "operations"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_gates import Gates  # noqa: E402
from ops_store import Refused  # noqa: E402

CHAINS = 3
SESSIONS_PER_CHAIN = 3
NEEDS_JMRI = unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
JMRI = NEEDS_JMRI

# Findings the audit may keep, each intended; GUIDE.md "Intended findings" gives the reason for every one.
INTENDED_FINDINGS = {
    ("warning", "staging-ship-excludes-empty", "West Custom"),     # U06: an all-custom staging track
    ("info", "train-not-on-list", "Ferris Transfer"),              # R07: the pick up list names one route
}

_spec = importlib.util.spec_from_file_location("showcase_build", EXAMPLE / "build.py")
showcase_build = importlib.util.module_from_spec(_spec)
_real_running_jmri = ops_store.running_jmri
_spec.loader.exec_module(showcase_build)  # build.py replaces running_jmri for its own use...
ops_store.running_jmri = _real_running_jmri  # ...so put the real one back for the rest of the suite
build = showcase_build

_tmp = None
TMP = None
BASE = SHOWCASE
SESSIONS = []  # SESSIONS[chain][session] = {"result", "builds", "log_errors", "keep", "rr", "manifests", "cars", "built"}
_state = {}


def run_session_chain(source: Path, work: Path, sessions: int = SESSIONS_PER_CHAIN) -> list:
    """Run consecutive sessions on a copy of source, carrying the saved files forward."""
    current = work / "current"
    shutil.copytree(source, current, ignore=shutil.ignore_patterns("backups", "buildstatus"))
    out = []
    for number in range(1, sessions + 1):
        keep = work / f"s{number}"
        keep.mkdir(parents=True)
        result = ops_jmri.run_worker(current, {"build": True, "terminate": True, "save": True}, keep)
        manifests = {}
        if (keep / "manifests").is_dir():
            for path in (keep / "manifests").glob("train (*).txt"):
                manifests[path.stem[7:-1]] = path.read_text(encoding="utf-8", errors="replace")
        for name in ops_store.FILES:
            if (keep / name).is_file():
                shutil.copy2(keep / name, current / name)
        out.append({"result": result, "builds": result["builds"], "log_errors": result["log_errors"], "keep": keep,
                    "rr": ops_data.load(keep), "manifests": manifests,
                    "cars": {k: v["cars"] for k, v in result["builds"].items()},
                    "built": {k: v["built"] for k, v in result["builds"].items()}})
    return out


run_chain = None  # set below for the scratch-copy experiments (batch E's name for it)


def _experiment_chain(source: Path, work: Path, sessions: int = SESSIONS_PER_CHAIN) -> list:
    work.mkdir(parents=True, exist_ok=True)
    return run_session_chain(source, work, sessions)


run_chain = _experiment_chain


def _fresh(path: Path) -> Path:
    path.mkdir(parents=True)
    return path


def setUpModule():
    global _tmp, TMP
    _tmp = tempfile.TemporaryDirectory(prefix="showcase-")
    TMP = Path(_tmp.name)
    _state["temp"] = _tmp
    _state["full"] = _state["shipped"] = SHOWCASE
    patch = mock.patch.object(ops_store, "running_jmri", lambda *a, **k: [])
    patch.start()
    _state["patch"] = patch
    env = mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(TMP / "plans")})
    env.start()
    _state["env"] = env
    if ops_jmri.jmri_home():
        with ThreadPoolExecutor(CHAINS) as pool:
            chains = list(pool.map(lambda n: run_session_chain(SHOWCASE, TMP / f"chain{n}"), range(CHAINS)))
        SESSIONS.extend(chains)
        _state["chains"] = SESSIONS


def tearDownModule():
    for key in ("patch", "env"):
        if key in _state:
            _state[key].stop()
    _tmp.cleanup()


def variant(name: str, actions: list) -> Path:
    """A scratch copy of the shipped folder with one plan applied; experiments live here, never in the shipped folder."""
    dest = TMP / name
    shutil.copytree(SHOWCASE, dest, ignore=shutil.ignore_patterns("backups", "buildstatus"))
    plan = ops_store.plan(dest, actions)
    ops_store.apply(plan["plan_id"], True)
    return dest


def why_not(folder: Path, car: str, destination: str, track=None, train=None) -> dict:
    return Gates(ops_data.load(folder)).why_not(car, destination, track, train, False)


# ---------------------------------------------------------------- staging: U06 U07 U12 U13 U22 R19
DEPOTS = {"Brae Depot", "Dunmere Depot"}


def a_cars(session: dict, train: str) -> dict:
    """Car id to (location, track) from the build's own list, for one train."""
    out = {}
    for row in session["builds"][train]["cars"]:
        who, where = row.split(" > ")
        location, track = where.split(" / ")
        out[who] = (location, track)
    return out


def a_where_is(session: dict, what: str) -> tuple[str, str]:
    """Saved location and track of a car or engine after the session."""
    rr = session["rr"]
    thing = rr.cars.get(what) or rr.engines.get(what)
    track = rr.tracks[thing.track_id]
    return rr.locations[track.location_id].name, track.name


def a_final_track(session: dict, car: str) -> str:
    rr = session["rr"]
    return rr.tracks[rr.cars[car].fd_track_id].name if rr.cars[car].fd_track_id else ""


@NEEDS_JMRI
class StagingCases(unittest.TestCase):
    def test_chains_ran_clean(self):
        self.assertEqual(len(SESSIONS), CHAINS)
        for chain in SESSIONS:
            for session in chain:
                self.assertEqual(session["log_errors"], [])

    def test_u06_generated_custom_loads(self):
        for chain in SESSIONS:
            s1 = chain[0]
            # CUSTOM: every car leaves West Custom with Machinery and a depot as final destination.
            self.assertTrue(s1["builds"]["CUSTOM"]["built"])
            self.assertEqual(s1["builds"]["CUSTOM"]["departure_track"], "West Custom")
            self.assertEqual(a_cars(s1, "CUSTOM"), {f"JFN{n}": ("Carrow", "Carrow Yard") for n in range(601, 605)})
            for n in range(601, 605):
                self.assertEqual(s1["rr"].cars[f"JFN{n}"].load, "Machinery")
                self.assertIn(a_final_track(s1, f"JFN{n}"), DEPOTS)
            # MIXED: the boxcars go to a depot with Machinery; the gondola has no load and leaves as an empty.
            self.assertTrue(s1["builds"]["MIXED"]["built"])
            mixed = a_cars(s1, "MIXED")
            for n in (611, 612, 613):
                self.assertIn(mixed[f"JFN{n}"][1], DEPOTS)
                self.assertIn(f"JFN {n} Boxcar 40' Machinery", s1["manifests"]["MIXED"])
            self.assertEqual(mixed["JFN614"], ("East Staging", "East Mixed"))
            self.assertNotIn("JFN 614 Gondola 40' Machinery", s1["manifests"]["MIXED"])
            # Both departure tracks are empty afterwards, as they must be.
            for n in list(range(601, 605)) + list(range(611, 615)):
                self.assertNotIn(a_where_is(s1, f"JFN{n}")[1], {"West Custom", "West Mixed"})

    def test_u07_staging_swap(self):
        for chain in SESSIONS:
            s1, s2 = chain[0], chain[1]
            self.assertTrue(s1["builds"]["SWAP-E"]["built"] and s1["builds"]["SWAP-W"]["built"])
            self.assertEqual(a_cars(s1, "SWAP-E"), {f"SWPX{n}": ("East Staging", "East Swap") for n in range(1, 7)})
            self.assertEqual(a_cars(s1, "SWAP-W"), {f"SWPX{n}": ("West Staging", "West Swap") for n in range(11, 17)})
            self.assertEqual(s1["builds"]["SWAP-E"]["departure_track"], "West Swap")
            self.assertEqual(s1["builds"]["SWAP-W"]["departure_track"], "East Swap")
            # Session 2: the same trip the other way.
            self.assertEqual(a_cars(s2, "SWAP-E"), {f"SWPX{n}": ("East Staging", "East Swap") for n in range(11, 17)})
            self.assertEqual(a_cars(s2, "SWAP-W"), {f"SWPX{n}": ("West Staging", "West Swap") for n in range(1, 7)})

    def test_u12_staging_train_normal_mode(self):
        for chain in SESSIONS:
            s1 = chain[0]
            build_row = s1["builds"]["MODE"]
            self.assertTrue(build_row["built"])
            placed = a_cars(s1, "MODE")
            self.assertEqual(len(placed), 5)
            at_yard = [c for c, w in placed.items() if w == ("Brae", "Brae Stockyard")]
            at_east = [c for c, w in placed.items() if w == ("East Staging", "East Mode")]
            # One car goes to Brae and the builder sends the rest on to staging. The loco change uses no moves.
            self.assertEqual((len(at_yard), len(at_east)), (1, 4))
            for n in range(1, 6):
                self.assertNotEqual(a_where_is(s1, f"MODX{n}")[1], "West Mode")

    def test_u12_aggressive_mode_makes_no_difference(self):
        plan = ops_store.plan(SHOWCASE, [{"action": "set_option", "group": "buildOptions", "name": "aggressive",
                                      "value": True}])
        result = ops_jmri.build_check(plan["plan_id"], runs=2)
        self.assertNotIn("MODE", result["now_fail"])
        self.assertNotIn("MODE", result["changed"])

    def test_u13_consists_and_loco_change(self):
        for chain in SESSIONS:
            s1, s2 = chain[0], chain[1]
            self.assertEqual(sorted(s1["builds"]["SWAP-E"]["engines"]), ["JFN51", "JFN52"])
            self.assertEqual(sorted(s1["builds"]["SWAP-W"]["engines"]), ["JFN53", "JFN54"])
            # The consists arrive on the other end's track and leave from it next session.
            self.assertEqual(a_where_is(s1, "JFN51"), ("East Staging", "East Swap"))
            self.assertEqual(a_where_is(s1, "JFN53"), ("West Staging", "West Swap"))
            self.assertEqual(sorted(s2["builds"]["SWAP-E"]["engines"]), ["JFN53", "JFN54"])
            manifest = s1["manifests"]["MODE"]
            self.assertIn("Locomotive change at Brae", manifest)
            self.assertIn("Set out JFN 55 GP9 to Brae Engine Track", manifest)
            self.assertIn("Pick up JFN 56 GP9 from Brae Engine Track", manifest)
            self.assertIn("Set out JFN 56 GP9 to East Mode", manifest)
            self.assertEqual(a_where_is(s1, "JFN55"), ("Brae", "Brae Engine Track"))
            self.assertEqual(a_where_is(s1, "JFN56"), ("East Staging", "East Mode"))
            self.assertEqual(a_where_is(s1, "JFN57"), ("Carrow", "Carrow Yard"))  # the spare never moves

    def test_u22_hazmat_buffer_and_kernel_on_turn(self):
        for chain in SESSIONS:
            s1 = chain[0]
            placed = a_cars(s1, "TURN")
            for n in (1, 2, 3):
                self.assertEqual(placed[f"HZMX{n}"], ("Linden", "Linden Refinery"))
            for n in (11, 12, 13):
                self.assertEqual(placed[f"HZMX{n}"], ("Linden", "Linden Steel"))
            self.assertEqual(placed["HZMX9"], ("West Staging", "Turn B"))
            manifest = s1["manifests"]["TURN"]
            picks = [line for line in manifest.splitlines() if "Pick up" in line]
            self.assertIn("HZMX 9 Buffer", picks[0])  # the buffer is the first car out of staging
            self.assertIn("HZMX 3 Tank Gas 40' L (Hazardous)", manifest)
            self.assertEqual(s1["rr"].cars["HZMX9"].passenger, True)

    def test_r19_staging_to_staging_turn(self):
        for chain in SESSIONS:
            s1, s2 = chain[0], chain[1]
            self.assertEqual(s1["builds"]["TURN"]["departure_track"], "Turn A")
            placed = a_cars(s1, "TURN")
            self.assertEqual(placed["TRNX1"], ("Linden", "Linden Team"))
            self.assertEqual(placed["TRNX2"], ("Linden", "Linden Team"))
            self.assertEqual(placed["TRNX3"], ("West Staging", "Turn B"))
            # Session 2: the turn leaves from Turn B and ends on Turn A.
            self.assertEqual(s2["builds"]["TURN"]["departure_track"], "Turn B")
            back = a_cars(s2, "TURN")
            self.assertEqual(back["TRNX1"], ("West Staging", "Turn A"))
            self.assertEqual(back["TRNX2"], ("West Staging", "Turn A"))
            self.assertEqual(back["TRNX3"], ("Linden", "Linden Team"))


# ---------------------------------------------------------------- Brae and Dunmere: U01 U02 U03 U08 U09 U10 U13 U14 U22 R17
def b_where(rr, car: str):
    """(location, track, load, final destination track or location) of a car, e.g. b_where(rr, 'JFN 101')."""
    road, number = car.rsplit(" ", 1)
    c = rr.cars[road + number]
    track = rr.tracks.get(c.track_id)
    final = rr.tracks.get(c.fd_track_id)
    if final is None and c.fd_id in rr.locations:
        final = rr.locations[c.fd_id]
    return (rr.locations[c.location_id].name, track.name if track else None, c.load, final.name if final else "")


def b_track_type(rr, location: str, name: str) -> str:
    return next(t.type for t in rr.tracks.values() if t.name == name and rr.locations[t.location_id].name == location)


def b_each_chain(session: int):
    """The state after the numbered session (1 to SESSIONS_PER_CHAIN), one per chain."""
    return [chain[session - 1] for chain in SESSIONS]


class BraeDunmereShipped(unittest.TestCase):
    """What the build file itself leaves, before any session."""

    def setUp(self):
        self.rr = ops_data.load(SHOWCASE)


    def test_u02_delivered_car_carries_the_cannery_load(self):
        self.assertEqual(b_where(self.rr, "JFN 201"), ("Brae", "Brae Cannery", "Canned", "Grocery Dock"))

    def test_u03_delivered_cars_carry_lumber(self):
        for car in ("JFN 301", "JFN 302"):
            self.assertEqual(b_where(self.rr, car), ("Brae", "Brae Lumber", "Lumber", "Lumber Dealer"))

    def test_u01_delivered_hopper_carries_feed(self):
        self.assertEqual(b_where(self.rr, "JFN 102"), ("Brae", "Brae Feed Mill", "Feed", "Dunmere Dairy"))

    def test_u09_one_schedule_two_tracks(self):
        schedules = [s for s in self.rr.schedules.values() if s.name == "Grain Receiving"]
        self.assertEqual(len(schedules), 1)
        tracks = [t for t in self.rr.tracks.values() if t.name in ("Elevator A", "Elevator B")]
        self.assertEqual(len(tracks), 2)
        self.assertEqual({t.schedule_id for t in tracks}, {schedules[0].id})

    def test_u08_virtual_spur_schedules(self):
        by_name = {s.name: s for s in self.rr.schedules.values()}
        self.assertEqual(by_name["Fiddle South"].items[0].random, "25")
        self.assertEqual(by_name["Fiddle South"].items[0].wait, 1)
        self.assertEqual(by_name["Fiddle North"].items[0].random, "")

    def test_u10_split_pair_is_two_tracks(self):
        names = {t.name for t in self.rr.tracks.values() if t.name.startswith("Freight House")}
        self.assertEqual(names, {"Freight House", "Freight House-(2)"})

    def test_u13_kernel_members_and_lead(self):
        members = sorted(c.id for c in self.rr.cars.values() if c.kernel == "Brae Set")
        self.assertEqual(members, ["KRNX1", "KRNX2", "KRNX3"])
        self.assertTrue(self.rr.cars["KRNX1"].lead)


@NEEDS_JMRI
class BraeDunmereSessions(unittest.TestCase):
    def test_clean_sessions(self):
        for chain in SESSIONS:
            for session in chain:
                self.assertEqual(session["log_errors"], [])
                for train in ("LOCAL-B", "FIDDLE JOB"):
                    self.assertTrue(session["builds"][train]["built"], train)

    def test_u01_hopper_goes_to_the_dairy_and_the_empty_returns_to_the_mill(self):
        for s in b_each_chain(1):
            self.assertEqual(b_where(s["rr"], "JFN 102"), ("Dunmere", "Dunmere Dairy", "E", ""))
            # Observed on the merged railroad in every chain: the empty hopper reaches the mill, which loads it with
            # Feed for the dairy. (Built alone, batch B saw it go to Dunmere Yard instead.)
            self.assertEqual(b_where(s["rr"], "JFN 101"), ("Brae", "Brae Feed Mill", "Feed", "Dunmere Dairy"))
        for s in b_each_chain(2):
            self.assertEqual(b_where(s["rr"], "JFN 101")[:3], ("Dunmere", "Dunmere Dairy", "E"))

    def test_u02_canned_goods_reach_the_grocery_dock(self):
        for s in b_each_chain(1):
            self.assertEqual(b_where(s["rr"], "JFN 201"), ("Dunmere", "Grocery Dock", "E", ""))
            self.assertIn("Set out JFN 201 Boxcar 40' Canned to Grocery Dock", s["manifests"]["LOCAL-B"])

    def test_u03_lumber_and_the_wanderers(self):
        for s in b_each_chain(1):
            for car in ("JFN 301", "JFN 302"):
                self.assertEqual(b_where(s["rr"], car), ("Dunmere", "Lumber Dealer", "E", ""))
        for session in range(1, SESSIONS_PER_CHAIN + 1):
            for s in b_each_chain(session):
                for car in ("WNDR 1", "WNDR 2"):
                    location, track, _, _ = b_where(s["rr"], car)
                    self.assertEqual(b_track_type(s["rr"], location, track), "Yard", (session, car, track))

    def test_u08_fiddle_yard_chain(self):
        tools = parts_at_depot = parts_waiting = south_visits = 0
        cars = [f"JFN 80{n}" for n in range(1, 7)]
        for s in b_each_chain(1):
            for car in cars:
                location, track, load, final = b_where(s["rr"], car)
                self.assertEqual(location, "Fiddle")
                if track == "Fiddle North":
                    self.assertEqual((load, final), ("Parts", "Parts Depot"))
                else:
                    self.assertEqual(track, "Fiddle South")
                    south_visits += 1
        self.assertGreater(south_visits, 0)
        for session in (2, 3):
            for s in b_each_chain(session):
                for car in cars:
                    location, track, load, final = b_where(s["rr"], car)
                    if track == "Fiddle South" and load == "Tools":
                        self.assertEqual(final, "Tool Depot")
        for s in b_each_chain(SESSIONS_PER_CHAIN):
            chain_parts = 0
            for car in cars:
                location, track, load, final = b_where(s["rr"], car)
                if track == "Parts Depot":
                    chain_parts += 1
                    self.assertEqual(load, "E")
                parts_waiting += load == "Parts"
                tools += load == "Tools"
            self.assertGreaterEqual(chain_parts, 1, "every chain has delivered a parts car by session 3")
            parts_at_depot += chain_parts
        self.assertGreater(parts_at_depot, tools)

    def test_u09_one_car_per_fifty_foot_elevator(self):
        for s in b_each_chain(1):
            self.assertEqual({b_where(s["rr"], "JFN 901")[1], b_where(s["rr"], "JFN 902")[1]},
                             {"Elevator A", "Elevator B"})
            self.assertEqual(b_where(s["rr"], "JFN 901")[2], "E")

    def test_u10_two_freight_houses_print_one_name(self):
        for s in b_each_chain(1):
            self.assertEqual(b_where(s["rr"], "FRHX 1")[:2], ("Dunmere", "Freight House"))
            self.assertEqual(b_where(s["rr"], "JFN 1001")[:2], ("Dunmere", "Freight House-(2)"))
            self.assertIn("Set out FRHX 1 Boxcar 40' E to Freight House [U10]", s["manifests"]["LOCAL-B"])
            self.assertIn("Set out JFN 1001 Boxcar 40' Crates to Freight House [U10]", s["manifests"]["LOCAL-B"])
            self.assertNotIn("Freight House-(2)", s["manifests"]["LOCAL-B"])

    def test_u13_kernel_moves_together(self):
        for session in (1, 2, 3):
            for s in b_each_chain(session):
                spots = {b_where(s["rr"], f"KRNX {n}")[:2] for n in (1, 2, 3)}
                self.assertEqual(spots, {("Dunmere", "Dunmere Team")}, session)
        for s in b_each_chain(1):
            for n in (1, 2, 3):
                self.assertIn(f"Set out KRNX {n} Boxcar 40' E to Dunmere Team", s["manifests"]["LOCAL-B"])

    def test_u14_tracks_half(self):
        for s in b_each_chain(1):
            self.assertEqual(b_where(s["rr"], "DAYX 1")[:2], ("Dunmere", "Tuesday Dock"))

    def test_u22_lcl_car_rides_and_returns(self):
        for session in (1, 2, 3):
            for s in b_each_chain(session):
                self.assertEqual(b_where(s["rr"], "LCLX 1")[:2], ("Carrow", "Carrow LCL Dock"))
        for s in b_each_chain(1):
            self.assertIn("Pick up LCLX 1 Boxcar 40' from Carrow LCL Dock", s["manifests"]["LOCAL-B"])
            self.assertIn("Set out LCLX 1 Boxcar 40' to Carrow LCL Dock", s["manifests"]["LOCAL-B"])

    def test_r17_outside_track_flips_the_load_both_ways(self):
        for s in b_each_chain(1):
            self.assertEqual(b_where(s["rr"], "OUTX 1"), ("Brae", "Brae Outside", "L", ""))
            self.assertEqual(b_where(s["rr"], "OUTX 2"), ("Carrow", "Carrow Outside Lead", "E", ""))
        for s in b_each_chain(2):
            self.assertEqual(b_where(s["rr"], "OUTX 2"), ("Brae", "Brae Outside", "L", ""))
            self.assertEqual(b_where(s["rr"], "OUTX 1"), ("Carrow", "Carrow Outside Lead", "E", ""))


class BraeDunmereWhyNot(unittest.TestCase):
    """Reads only: ops_why_not with real_build false, on the shipped files."""

    def why(self, car, destination, track, train="LOCAL-B", folder=None):
        import operations_pro
        return operations_pro.why_not({"ops_dir": str(folder or SHOWCASE), "car": car, "destination": destination,
                                       "track": track, "train": train, "real_build": False})

    def test_u01_feed_mill_takes_the_empty_hopper(self):
        self.assertTrue(self.why("JFN 101", "Brae", "Brae Feed Mill")["can_move"])

    def test_u08_random_line_is_not_checked(self):
        gates = {g["gate"]: g for g in self.why("JFN 801", "Fiddle", "Fiddle South", "FIDDLE JOB")["gates"]}
        self.assertEqual(gates["F5"]["status"], "not_checked")

    def test_u10_crates_house_refuses_the_empty(self):
        result = self.why("FRHX 1", "Dunmere", "Freight House-(2)")
        self.assertFalse(result["can_move"])
        self.assertIn("E10", result["first_failure"]["reason"] + str(result["gates"]))

    def test_u22_lcl_needs_the_passenger_flag(self):
        self.assertTrue(self.why("LCLX 1", "Carrow", "Carrow LCL Dock")["can_move"])
        copy = TMP / "nopass"
        shutil.copytree(SHOWCASE, copy, ignore=shutil.ignore_patterns("backups", "buildstatus"))
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_store.quick(copy, [{"action": "update_car", "car": "LCLX 1", "passenger": False}])
        result = self.why("LCLX 1", "Carrow", "Carrow LCL Dock", folder=copy)
        self.assertEqual(result["first_failure"]["gate"], "D4")

    def test_r17_outside_track_takes_the_empty(self):
        self.assertTrue(self.why("OUTX 1", "Brae", "Brae Outside")["can_move"])


# ---------------------------------------------------------------- Hollis Mill and Oakhaven: U05 U11 U13 U16 U19 U24 R01 R03 R04 R09
def cd_where(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    place = rr.locations[car.location_id].name
    track = rr.tracks[car.track_id].name if car.track_id in rr.tracks else ""
    return f"{place} / {track}"


def c_final_track(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    return rr.tracks[car.fd_track_id].name if car.fd_track_id in rr.tracks else ""


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class HollisOakhavenCases(unittest.TestCase):
    def sessions(self, number: int):
        return [chain[number - 1] for chain in _state["chains"]]

    def built(self, session, train: str) -> dict:
        row = session["result"]["builds"][train]
        self.assertTrue(row["built"], f"{train}: {row['message']}")
        return row

    def test_clean_builds_have_no_log_errors(self):
        for number in range(1, SESSIONS_PER_CHAIN + 1):
            for session in self.sessions(number):
                self.assertEqual(session["result"]["log_errors"], [])
                self.built(session, "LOCAL-H")

    # U05: the track with the lowest move count takes the cars; priority does not.
    def test_u05_lowest_move_count_wins_over_priority(self):
        for session in self.sessions(1):
            for number in (501, 502, 503):
                self.assertEqual(cd_where(session["rr"], f"GNDX{number}"), "Hollis Mill / Hollis Track 2")
        why = Gates(ops_data.load(_state["full"])).why_not("GNDX501", "Hollis Mill", None, "LOCAL-H", False)
        self.assertTrue(why["can_move"])
        order = why["track_order"]
        self.assertLess(order.index("Hollis Track 2"), order.index("Hollis Track 1"))
        tracks = {t.name: t for t in ops_data.load(_state["full"]).tracks.values()}
        self.assertEqual((tracks["Hollis Track 1"].moves, tracks["Hollis Track 2"].moves), (100, 0))

    # U11: a two-spot spur with planned pick ups takes new cars while the same train pulls the old ones.
    def test_u11_spur_in_balance(self):
        for chain in _state["chains"]:
            s1, s2, s3 = (chain[i]["rr"] for i in range(3))
            first = {c for c in ("MILX1101", "MILX1102", "MILX1103", "MILX1104")
                     if cd_where(s1, c) == "Hollis Mill / Mill Spur"}
            self.assertEqual(len(first), 2)
            for car in first:
                self.assertEqual(s1.cars[car].load, "Flour")
                self.assertEqual(c_final_track(s1, car), "Bakery")
            for car in {"MILX1101", "MILX1102", "MILX1103", "MILX1104"} - first:
                self.assertEqual(cd_where(s1, car), "Carrow / Carrow Mill Lead")
            # S2: the first pair reaches the bakery and the second pair takes their places on the mill spur.
            for car in first:
                self.assertEqual(cd_where(s2, car), "Oakhaven / Bakery")
                self.assertEqual(s2.cars[car].load, "E")
            second = {"MILX1101", "MILX1102", "MILX1103", "MILX1104"} - first
            for car in second:
                self.assertEqual(cd_where(s2, car), "Hollis Mill / Mill Spur")
                self.assertEqual(s2.cars[car].load, "Flour")
            # S3: the second pair reaches the bakery and the first pair is back on the lead.
            for car in second:
                self.assertEqual(cd_where(s3, car), "Oakhaven / Bakery")
            for car in first:
                self.assertEqual(cd_where(s3, car), "Carrow / Carrow Mill Lead")

    # U13: a train that requires a caboose takes exactly one and returns it to the caboose track.
    def test_u13_caboose_rides_and_returns(self):
        for number in range(1, SESSIONS_PER_CHAIN + 1):
            for session in self.sessions(number):
                rr = session["rr"]
                row = self.built(session, "LOCAL-H")
                cabooses = [c for c in row["cars"] if c.startswith("JFN130")]
                self.assertEqual(len(cabooses), 1, row["cars"])
                self.assertIn("> Carrow / Carrow Caboose Track", cabooses[0])
                for car in ("JFN1301", "JFN1302"):
                    self.assertEqual(cd_where(rr, car), "Carrow / Carrow Caboose Track")
        manifest = (self.sessions(1)[0]["keep"] / "manifests" / "train (LOCAL-H).txt").read_text()
        self.assertIn("caboose", manifest)
        self.assertEqual(manifest.count("Caboose 40'"), 2)  # one pick up and one set out

    # U16: a manual build line takes the named car first, and the train delivers it.
    def test_u16_manual_build_line(self):
        for session in self.sessions(1):
            row = self.built(session, "LOCAL-H")
            self.assertIn("TEMX1 > Oakhaven / Oakhaven Team", row["cars"])
            self.assertIn("Manual build line id 1m1 was able to assign to train (LOCAL-H) 1 of 1", row["report_text"])
            self.assertEqual(cd_where(session["rr"], "TEMX1"), "Oakhaven / Oakhaven Team")
        lines = ops_data.read_manual_builds(_state["full"])
        self.assertEqual(len(lines), 1)

    # U19: a pool lends length between its tracks, so Pool 1 holds more than its own 100 feet.
    def test_u19_track_pool(self):
        for session in self.sessions(1):
            rr = session["rr"]
            places = [cd_where(rr, f"POOX{n}") for n in range(1901, 1907)]
            self.assertEqual(sorted(places), ["Hollis Mill / Hollis Pool 1"] * 3 + ["Hollis Mill / Hollis Pool 2"] * 3)
            tracks = {t.name: t for t in rr.tracks.values()}
            one, two = tracks["Hollis Pool 1"], tracks["Hollis Pool 2"]
            self.assertGreater(one.length, 100)   # lent by Pool 2
            self.assertLessEqual(one.length, 150)  # the pool maximum
            self.assertGreaterEqual(two.length, 100)  # the pool minimum
            self.assertEqual(one.length + two.length, 400)

    # U24: a RIP track keeps the load; a plain spur would turn L into E.
    def test_u24_rip_track_keeps_the_load(self):
        for session in self.sessions(1):
            rr = session["rr"]
            self.assertEqual(cd_where(rr, "RIPX1"), "Carrow / Carrow RIP")
            self.assertEqual(rr.cars["RIPX1"].load, "L")
        tracks = {t.name: t for t in ops_data.load(_state["full"]).tracks.values()}
        self.assertNotEqual(tracks["Carrow RIP"].load_options, 0)

    # R01: one train direct to a spur; the schedule turns the peas into an empty on arrival.
    def test_r01_one_train_direct(self):
        for session in self.sessions(1):
            rr = session["rr"]
            self.assertEqual(cd_where(rr, "JFN5101"), "Oakhaven / Oakhaven Cannery")
            self.assertEqual(rr.cars["JFN5101"].load, "E")
        why = Gates(ops_data.load(_state["full"])).why_not("JFN5101", "Oakhaven", "Oakhaven Cannery", "LOCAL-H", False)
        self.assertTrue(why["can_move"])
        self.assertEqual(why["router"]["route"]["how"], "single train")

    # R03 (first hop; the second hop needs batch E's Linden pipe yard, here a stand-in): two trains through a yard.
    def test_r03_two_trains_through_a_yard(self):
        for chain in _state["chains"]:
            self.assertEqual(cd_where(chain[0]["rr"], "JFN5301"), "Carrow / Carrow Transfer")
            self.assertEqual(cd_where(chain[1]["rr"], "JFN5301"), "Linden / Linden Pipe Yard")
            self.assertIn("JFN5301 > Linden / Linden Pipe Yard", chain[1]["result"]["builds"]["EAST FREIGHT"]["cars"])
        why = Gates(ops_data.load(_state["full"])).why_not(
            "JFN5301", "Linden", "Linden Pipe Yard", "LOCAL-H", False)
        self.assertEqual(why["router"]["route"]["how"], "two trains through yard Carrow Transfer")

    # R04 (first hop; the later hops need batch D's Ferris Relay and Northwood Steel, here stand-ins).
    def test_r04_chain_of_three_trains(self):
        for chain in _state["chains"]:
            self.assertEqual(cd_where(chain[0]["rr"], "JFN5401"), "Carrow / Carrow Relay")
            self.assertEqual(cd_where(chain[1]["rr"], "JFN5401"), "Ferris Junction / Ferris Relay")
            self.assertEqual(cd_where(chain[2]["rr"], "JFN5401"), "Northwood / Northwood Steel")
        why = Gates(ops_data.load(_state["full"])).why_not(
            "JFN5401", "Northwood", "Northwood Steel", "LOCAL-H", False)
        route = why["router"]["route"]
        self.assertEqual(route["how"], "3 trains")
        self.assertEqual([hop["train"] for hop in route["path"]], ["LOCAL-H", "EAST FREIGHT", "NORTH JOB"])

    # R09: a full spur sends the next car to its alternate, and the one after to a yard at the destination.
    def test_r09_alternate_then_yard(self):
        for chain in _state["chains"]:
            rr = chain[0]["rr"]
            places = sorted(cd_where(rr, f"JFN{n}") for n in range(5901, 5905))
            self.assertEqual(places, ["Oakhaven / Oakhaven Plant"] * 2 + ["Oakhaven / Oakhaven Yard", "Oakhaven / Plant Overflow"])
            report = chain[0]["result"]["builds"]["LOCAL-H"]["report_text"]
            self.assertRegex(report, r"Delivering car \(JFN 59\d\d\) to alternate track \(Plant Overflow\)")
            self.assertRegex(report, r"Sending car \(JFN 59\d\d\) to yard \(Oakhaven, Oakhaven Yard\)")


# ---------------------------------------------------------------- Ferris, Northwood, Pell Creek: R02 R04 R06 R07 R08 R10 R16 U21
def d_final_dest(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    if car.fd_track_id not in rr.tracks:
        return ""
    return f"{rr.locations[car.fd_id].name} / {rr.tracks[car.fd_track_id].name}"


def d_why(folder, car, destination, track=None, train=None):
    return Gates(ops_data.load(folder)).why_not(car, destination, track, train, False)


def d_gate(result, name: str) -> dict:
    return next(g for g in result["gates"] if g["gate"] == name)


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class FerrisNorthwoodCases(unittest.TestCase):
    def sessions(self, number: int):
        return [chain[number - 1] for chain in _state["chains"]]

    def carried(self, session, train: str) -> list:
        row = session["result"]["builds"][train]
        self.assertTrue(row["built"], f"{train}: {row['message']}")
        return row["cars"]


    def test_sessions_log_no_errors(self):
        for number in range(1, SESSIONS_PER_CHAIN + 1):
            for session in self.sessions(number):
                self.assertEqual(session["result"]["log_errors"], [])

    # R02: two trains through an interchange.
    def test_r02_two_trains_through_interchange(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("JFN5201 > Ferris Junction / Ferris Exchange", self.carried(s1, "EAST FREIGHT"))
            self.assertEqual(cd_where(s1["rr"], "JFN5201"), "Ferris Junction / Ferris Exchange")
            self.assertEqual(s1["rr"].cars["JFN5201"].load, "Produce")
            self.assertEqual(d_final_dest(s1["rr"], "JFN5201"), "Northwood / Cold Store")
            self.assertIn("JFN5201 > Northwood / Cold Store", self.carried(s2, "NORTH JOB"))
            self.assertEqual(cd_where(s2["rr"], "JFN5201"), "Northwood / Cold Store")
        route = d_why(_state["shipped"], "JFN 5201", "Northwood", "Cold Store", "EAST FREIGHT")["router"]["route"]
        self.assertEqual(route["how"], "two trains through interchange Ferris Exchange")
        self.assertEqual([p["train"] for p in route["path"]], ["EAST FREIGHT", "NORTH JOB"])

    # R04, second and third hops. The first hop (LOCAL-H to Carrow Relay) is batch C's: needs-integration.
    def test_r04_three_trains_second_and_third_hops(self):
        for chain in _state["chains"]:
            s1, s2, s3 = (chain[i] for i in range(3))
            self.assertEqual(cd_where(s1["rr"], "JFN5401"), "Carrow / Carrow Relay")  # stand-in first hop
            self.assertIn("JFN5401 > Ferris Junction / Ferris Relay", self.carried(s2, "EAST FREIGHT"))
            self.assertEqual(cd_where(s2["rr"], "JFN5401"), "Ferris Junction / Ferris Relay")
            self.assertIn("JFN5401 > Northwood / Northwood Steel", self.carried(s3, "NORTH JOB"))
            self.assertEqual(cd_where(s3["rr"], "JFN5401"), "Northwood / Northwood Steel")
        route = d_why(_state["full"], "JFN 5401", "Northwood", "Northwood Steel", "LOCAL-H")["router"]["route"]
        self.assertTrue(route["how"].startswith("3 trains"), route["how"])
        self.assertEqual([p["train"] for p in route["path"]], ["LOCAL-H", "EAST FREIGHT", "NORTH JOB"])

    # R06: the Destinations filter on Ferris Gate admits Pell Creek only, so the car cannot be sent to Northwood.
    def test_r06_destinations_filter_gate(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("GTEX1 > Pell Creek-(yard) / Pell Tank Track", self.carried(s1, "NORTH JOB"))
            self.assertEqual(cd_where(s1["rr"], "GTEX1"), "Pell Creek-(yard) / Pell Tank Track")
            self.assertEqual(cd_where(s2["rr"], "GTEX1"), "Ferris Junction / Ferris Gate")  # the set outs admit it
            report = s1["result"]["builds"]["NORTH JOB"]["report_text"]
            self.assertIn("Destination (Northwood) not serviced by departure track (Ferris Gate)", report)
        refused = d_why(_state["shipped"], "GTEX 1", "Northwood", "Gate Yard", "NORTH JOB")
        self.assertEqual(d_gate(refused, "D6")["status"], "fail")
        self.assertFalse(refused["can_move"])
        allowed = d_why(_state["shipped"], "GTEX 1", "Pell Creek-(yard)", "Pell Tank Track", "NORTH JOB")
        self.assertEqual(d_gate(allowed, "D6")["status"], "pass")

    # R07: pick ups named by route, so the train that set the car out can pull it back.
    def test_r07_pick_up_by_route(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("XFRX1 > Ferris Junction / Ferris Transfer", self.carried(s1, "NORTH JOB"))
            self.assertEqual(cd_where(s1["rr"], "XFRX1"), "Ferris Junction / Ferris Transfer")
            self.assertIn("XFRX1 > Northwood / Northwood Shed", self.carried(s2, "NORTH JOB"))
            self.assertEqual(cd_where(s2["rr"], "XFRX1"), "Northwood / Northwood Shed")
        after = d_why(self.sessions(1)[0]["keep"], "XFRX 1", "Northwood", "Northwood Shed", "NORTH JOB")
        self.assertEqual(d_gate(after, "B6")["status"], "pass")
        self.assertTrue(after["can_move"])

    # R08: Routed on an interchange takes the routed car and refuses the plain empty.
    def test_r08_routed_interchange(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertEqual(cd_where(s1["rr"], "JFN5801"), "Ferris Junction / Ferris Routed")
            self.assertEqual(cd_where(s1["rr"], "BOXX1"), "Ferris Junction / Ferris Yard")
            self.assertEqual(cd_where(s2["rr"], "JFN5801"), "Northwood / Routed Siding")
            self.assertEqual(s2["rr"].cars["JFN5801"].load, "E")
            self.assertEqual(cd_where(s2["rr"], "BOXX1"), "Ferris Junction / Ferris Yard")
        plain = d_why(_state["shipped"], "BOXX 1", "Ferris Junction", "Ferris Routed", "EAST FREIGHT")
        self.assertEqual(d_gate(plain, "E7")["status"], "fail")
        routed = d_why(_state["shipped"], "JFN 5801", "Ferris Junction", "Ferris Routed", "EAST FREIGHT")
        self.assertEqual(d_gate(routed, "E7")["status"], "pass")

    # R10: a pool of two 120 ft interchanges takes five 44 ft cars (220 ft); the cars then go on together.
    def test_r10_pool_takes_the_overflow(self):
        cars = [f"OAKX{n}" for n in range(1, 6)]
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            placed = [cd_where(s1["rr"], c) for c in cars]
            self.assertTrue(all(p in ("Ferris Junction / Ferris Pool 1", "Ferris Junction / Ferris Pool 2")
                                for p in placed), placed)
            counts = {p: placed.count(p) for p in set(placed)}
            self.assertGreater(max(counts.values()) * 44, 120, counts)  # one track holds more than its own length
            for car in cars:
                self.assertEqual(cd_where(s2["rr"], car), "Northwood / Grain Elevator")
        rr = ops_data.load(_state["shipped"])
        pools = {t.name: t for t in rr.tracks.values() if t.name.startswith("Ferris Pool")}
        self.assertEqual({t.pool for t in pools.values()}, {"Ferris Pool"})

    # R16: two locations print as one place and work as two.
    def test_r16_hyphen_pair(self):
        names = {l.name for l in ops_data.load(_state["shipped"]).locations.values()}
        self.assertTrue({"Pell Creek-(yard)", "Pell Creek-(industries)"} <= names)
        for chain in _state["chains"]:
            s1 = chain[0]
            rows = self.carried(s1, "PELL SWITCHER")
            for car in ("PELC1", "PELC2"):
                self.assertIn(f"{car} > Pell Creek-(industries) / Pell Brickworks", rows)
                self.assertEqual(cd_where(s1["rr"], car), "Pell Creek-(industries) / Pell Brickworks")
            text = (s1["keep"] / "manifests" / "train (PELL SWITCHER).txt").read_text()
            self.assertIn("Scheduled work at Pell Creek, departure time 13:30", text)
            self.assertNotIn("(industries)", text)
            self.assertNotIn("(yard)", text)

    # U21: a home division sends the empties to a home yard and the load to the home spur, through a yard hop.
    def test_u21_home_division(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            rows = self.carried(s1, "EAST FREIGHT")
            for car in ("NWRX1", "NWRX2", "NWRX3"):
                self.assertIn(f"{car} > Ferris Junction / Ferris Yard", rows)
            self.assertEqual(d_final_dest(s1["rr"], "NWRX1"), "Northwood / Northwood Yard")
            self.assertEqual(d_final_dest(s1["rr"], "NWRX2"), "Northwood / Northwood Yard")
            self.assertEqual(d_final_dest(s1["rr"], "NWRX3"), "Northwood / Malt House")
            self.assertEqual(cd_where(s2["rr"], "NWRX1"), "Northwood / Northwood Yard")
            self.assertEqual(cd_where(s2["rr"], "NWRX2"), "Northwood / Northwood Yard")
            self.assertEqual(cd_where(s2["rr"], "NWRX3"), "Northwood / Malt House")
            self.assertEqual(s2["rr"].cars["NWRX3"].load, "E")
        route = d_why(_state["shipped"], "NWRX 1", "Northwood", "Northwood Yard", "EAST FREIGHT")["router"]["route"]
        self.assertEqual(route["how"], "two trains through yard Ferris Yard")


# ---------------------------------------------------------------- Hop, Kessock, Sawyer, oil, directions, passenger: R05 R11 R12 R13 R14 R15 R18 R03 U04 U18
class HopKessockSawyerCases(unittest.TestCase):
    def sessions(self, number: int, train: str):
        """The cars the train moved in session number (1 based), once per chain."""
        return [chain[number - 1]["cars"].get(train, []) for chain in SESSIONS]



    @JMRI
    def test_R05_route_through_staging(self):
        for chain in SESSIONS:
            self.assertIn("JFN5501 > East Staging / Hop", chain[0]["cars"]["EAST FREIGHT"])
            self.assertIn("JFN5502 > Carrow / Carrow Yard", chain[0]["cars"]["HOP OUT"])
            self.assertIn("JFN5501 > Linden / Linden Pier", chain[1]["cars"]["HOP OUT"])
        route = why_not(SHOWCASE, "JFN 5501", "Linden", "Linden Pier")["router"]["route"]
        self.assertEqual(route["how"], "two trains through staging Hop")

    @JMRI
    def test_R05_experiment_staging_routing_off(self):
        copy = variant("r05_off", [{"action": "set_option", "group": "router", "name": "carRoutingViaStaging",
                                    "value": False}])
        out = why_not(copy, "JFN 5501", "Linden", "Linden Pier")
        self.assertEqual(out["router"]["route"]["status"], "could not route car")
        self.assertEqual(out["gates"][-1]["gate"], "G12")
        self.assertEqual(out["gates"][-1]["status"], "fail")
        session = run_chain(copy, _fresh(TMP / "r05_off_run"), 1)[0]
        self.assertNotIn("JFN5501 > East Staging / Hop", session["cars"]["EAST FREIGHT"])

    @JMRI
    def test_R11_ad_track_and_switcher(self):
        for chain in SESSIONS:
            self.assertEqual(sorted(chain[0]["cars"]["KESSOCK TRANSFER"]),
                             [f"KESX{n} > Kessock / Kessock A/D" for n in range(1, 5)])
            moved = chain[1]["cars"]["KESSOCK SWITCHER"]
            self.assertEqual(len(moved), 4)
            self.assertTrue(all(c.split(" > ")[1] in ("Kessock / Kessock Class 1", "Kessock / Kessock Class 2")
                                for c in moved))
            self.assertEqual(sum("Class 1" in c for c in moved), 2)

    @JMRI
    def test_R11_experiment_local_interchange_off(self):
        state = SESSIONS[0][0]["keep"]
        copy = TMP / "r11_off"
        shutil.copytree(state, copy)
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            plan = ops_store.plan(copy, [{"action": "set_option", "group": "buildOptions",
                                          "name": "allowLocalInterchange", "value": False}])
            ops_store.apply(plan["plan_id"], True)
        out = why_not(copy, "KESX 1", "Kessock", "Kessock Class 1", "KESSOCK SWITCHER")
        self.assertEqual(out["first_failure"]["gate"], "D19")
        rules = {f["rule"] for f in Gates(ops_data.load(copy)).audit()["findings"]}
        self.assertIn("switcher-local-off", rules)

    @JMRI
    def test_R12_local_switcher_spur_and_yard(self):
        for chain in SESSIONS:
            cars = chain[0]["cars"]["SAWYER SWITCHER"]
            self.assertIn("SWYX1 > Sawyer / Sawyer Warehouse", cars)
            self.assertIn("SWYX2 > Sawyer / Sawyer Yard 2", cars)
        self.assertTrue(why_not(SHOWCASE, "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")["can_move"])

    @JMRI
    def test_R12_experiment_local_spur_off(self):
        copy = variant("r12_off", [{"action": "set_option", "group": "buildOptions", "name": "allowLocalSpur",
                                    "value": False}])
        out = why_not(copy, "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(out["first_failure"]["gate"], "D19")
        cars = run_chain(copy, _fresh(TMP / "r12_off_run"), 1)[0]["cars"]["SAWYER SWITCHER"]
        self.assertNotIn("SWYX1 > Sawyer / Sawyer Warehouse", cars)
        self.assertIn("SWYX2 > Sawyer / Sawyer Yard 2", cars)  # yard to yard has its own option

    @JMRI
    def test_R13_through_car_rules(self):
        for chain in SESSIONS:
            cars = chain[0]["cars"]["THRU"]
            self.assertIn("OILX1 > Dunmere / Dunmere Oil", cars)
            self.assertIn("OILX2 > Ferris Junction / Ferris Yard", cars)
        self.assertEqual(why_not(SHOWCASE, "OILX 1", "Ferris Junction", None, "THRU")["first_failure"]["gate"], "D10")
        self.assertEqual(why_not(SHOWCASE, "OILX 2", "Dunmere", None, "THRU")["first_failure"]["gate"], "D11")

    @JMRI
    def test_R13_experiment_allow_through(self):
        copy = variant("r13_on", [{"action": "update_train", "train": "THRU", "allow_through_cars": True}])
        self.assertTrue(why_not(copy, "OILX 1", "Ferris Junction", None, "THRU")["can_move"])
        cars = run_chain(copy, _fresh(TMP / "r13_run"), 1)[0]["cars"]["THRU"]
        self.assertIn("OILX1 > Ferris Junction / Ferris Yard", cars)

    @JMRI
    def test_R14_service_all_differs(self):
        """Reworded: shipped, both cars reach Linden Glazier. With Linden down to one move the two settings differ."""
        for chain in SESSIONS:
            cars = chain[0]["cars"]["EAST FREIGHT"]
            self.assertIn("JFN6401 > Linden / Linden Glazier", cars)
            self.assertIn("JFN6402 > Linden / Linden Glazier", cars)
        outcome = {}
        for flag in (False, True):
            copy = variant(f"r14_{flag}", [{"action": "update_stop", "route": "EAST FREIGHT", "stop": 3, "max_moves": 1},
                                           {"action": "update_train", "train": "EAST FREIGHT", "service_all": flag}])
            outcome[flag] = run_chain(copy, _fresh(TMP / f"r14_{flag}_run"), 1)[0]["cars"]["EAST FREIGHT"]
        self.assertNotIn("JFN6401 > Linden / Linden Glazier", outcome[False])
        self.assertFalse([c for c in outcome[False] if c.startswith("JFN640")])
        self.assertIn("JFN6402 > Ferris Junction / Ferris Yard", outcome[True])
        self.assertIn("JFN6401 > Carrow / Carrow Yard", outcome[True])

    @JMRI
    def test_R15_directions_as_a_filter(self):
        for chain in SESSIONS:
            self.assertFalse([c for c in chain[0]["cars"]["EAST FREIGHT"] if c.startswith("WSTX1")])
            self.assertIn("WSTX1 > Carrow / Carrow West Lead", chain[0]["cars"]["HOP OUT"])
        self.assertEqual(why_not(SHOWCASE, "WSTX 1", "Carrow", None, "EAST FREIGHT")["direct_failure"]["gate"], "C9")
        self.assertIsNone(why_not(SHOWCASE, "WSTX 1", "Carrow", None, "HOP OUT")["first_failure"])

    @JMRI
    def test_R15_experiment_both_directions(self):
        copy = variant("r15_both", [{"action": "update_track", "track": "Linden Westside", "location": "Linden",
                                     "directions": "East/West"}])
        answer = why_not(copy, "WSTX 1", "Carrow", None, "EAST FREIGHT")
        self.assertNotEqual((answer["first_failure"] or answer["direct_failure"] or {}).get("gate"), "C9")
        session = run_chain(copy, _fresh(TMP / "r15_run"), 1)[0]
        self.assertIn("WSTX1 > East Staging / Hop", session["cars"]["EAST FREIGHT"])



    @JMRI
    def test_U04_local_move_within_sawyer(self):
        for chain in SESSIONS:
            self.assertIn("JFN401 > Sawyer / Sawyer Pasta Plant", chain[0]["cars"]["SAWYER SWITCHER"])
        out = why_not(SHOWCASE, "JFN 401", "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER")
        self.assertTrue(out["can_move"])
        self.assertIsNone(out["first_failure"])

    @JMRI
    def test_U04_experiment_no_pickups_no_local(self):
        copy = variant("u04_off", [{"action": "update_stop", "route": "SAWYER SWITCHER", "stop": 1,
                                    "local_moves": False, "pickups": False}])
        out = why_not(copy, "JFN 401", "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER")
        self.assertEqual(out["first_failure"]["gate"], "C2")
        cars = run_chain(copy, _fresh(TMP / "u04_run"), 1)[0]["cars"]["SAWYER SWITCHER"]
        self.assertEqual(cars, [])

    @JMRI
    def test_U18_blocking_order(self):
        for chain in SESSIONS:
            text = chain[0]["manifests"]["VALLEY FLYER"]
            order = [int(line.split("FLYX")[1].split()[0]) for line in text.splitlines() if "Pick up FLYX" in line]
            self.assertEqual(order, [1, 2, 3, 4, 5])
            self.assertEqual(sorted(chain[0]["cars"]["VALLEY FLYER"]),
                             [f"FLYX{n} > Northwood / Northwood Station" for n in range(1, 6)])

    @JMRI
    def test_U18_experiment_negative_blocking_leads(self):
        copy = TMP / "u18_lead"
        shutil.copytree(SHOWCASE, copy)
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_store.quick(copy, [{"action": "update_car", "car": "FLYX 5", "blocking": -9}])
        run = _fresh(TMP / "u18_run")
        run_chain(copy, run, 1)
        text = (run / "s1" / "manifests" / "train (VALLEY FLYER).txt").read_text(encoding="utf-8")
        order = [int(line.split("FLYX")[1].split()[0]) for line in text.splitlines() if "Pick up FLYX" in line]
        self.assertEqual(order[0], 5)


# ---------------------------------------------------------------- cases that only exist on the merged railroad
def m_where(rr, car_id):
    car = rr.cars[car_id]
    track = rr.tracks[car.track_id]
    return f"{rr.locations[track.location_id].name} / {track.name}"


@NEEDS_JMRI
class MergedCases(unittest.TestCase):
    def test_every_train_builds_in_session_one_and_staging_trains_run_out_after(self):
        """'Every train builds' is the shipped state. Staging trains consume their departure track, so later
        sessions name which trains then have nothing to run."""
        for chain in SESSIONS:
            for session in chain:
                self.assertEqual(session["log_errors"], [])
            self.assertEqual([t for t, row in chain[0]["builds"].items() if not row["built"]], [])
            self.assertEqual(sorted(t for t, row in chain[1]["builds"].items() if not row["built"]),
                             ["CUSTOM", "MIXED", "MODE"])
            self.assertEqual(sorted(t for t, row in chain[2]["builds"].items() if not row["built"]),
                             ["CUSTOM", "HOP OUT", "MIXED", "MODE"])

    def test_u06_second_session_local_b_delivers_the_custom_cars_to_the_depot(self):
        for chain in SESSIONS:
            s1, s2 = chain[0]["rr"], chain[1]["rr"]
            self.assertEqual(m_where(s1, "JFN601"), "Carrow / Carrow Yard")
            self.assertEqual(m_where(s2, "JFN601"), "Brae / Brae Depot")
            self.assertEqual(s2.cars["JFN601"].load, "E")

    def test_r03_two_trains_through_yard_with_the_real_pipe_yard(self):
        for chain in SESSIONS:
            self.assertIn("JFN5301 > Linden / Linden Pipe Yard", chain[1]["builds"]["EAST FREIGHT"]["cars"])
            self.assertEqual(m_where(chain[1]["rr"], "JFN5301"), "Linden / Linden Pipe Yard")

    def test_r04_first_hop_with_the_real_objects(self):
        for chain in SESSIONS:
            self.assertIn("JFN5401 > Carrow / Carrow Relay", chain[0]["builds"]["LOCAL-H"]["cars"])

    def test_r08_staging_half_hop_takes_only_routed_cars(self):
        refused = why_not(SHOWCASE, "BOXX 1", "East Staging", "Hop", "EAST FREIGHT")
        gates = {g["gate"]: g for g in refused["gates"]}
        self.assertEqual(gates["E7"]["status"], "fail")
        self.assertFalse(refused["can_move"])
        routed = {g["gate"]: g for g in why_not(SHOWCASE, "JFN 5501", "East Staging", "Hop", "EAST FREIGHT")["gates"]}
        self.assertEqual(routed["E7"]["status"], "pass")
        for chain in SESSIONS:
            self.assertEqual(m_where(chain[0]["rr"], "BOXX1"), "Ferris Junction / Ferris Yard")

    def test_r18_descriptive_interchange_second_half(self):
        for chain in SESSIONS:
            self.assertEqual(m_where(chain[0]["rr"], "CNXX1"), "Linden / Northern Connection")
            self.assertIn(m_where(chain[1]["rr"], "CNXX1"), ("West Staging / Turn A", "West Staging / Turn B"))

    def test_u14_day_car_reaches_tuesday_dock_on_tuesday(self):
        for chain in SESSIONS:
            self.assertEqual(m_where(chain[0]["rr"], "DAYX1"), "Dunmere / Tuesday Dock")

    def test_local_h_carries_its_caboose_and_the_fiddle_job_runs_first(self):
        times = {t.name: t for t in ops_data.load(SHOWCASE).trains.values()}
        for chain in SESSIONS:
            local_h = chain[0]["builds"]["LOCAL-H"]
            self.assertTrue(local_h["built"])
            self.assertTrue(any(c.startswith("JFN130") for c in local_h["cars"]))
            for n in range(801, 807):
                self.assertEqual(m_where(chain[0]["rr"], f"JFN{n}").split(" / ")[0], "Fiddle")

    def test_shared_sinks_are_where_default_cars_end_up(self):
        """Fiddle yard and Carrow Box Factory take default-E boxcars in later sessions; cases assert session one."""
        for chain in SESSIONS:
            self.assertEqual(m_where(chain[0]["rr"], "WNDR1").split(" / ")[1], "Dunmere Yard")


# ---------------------------------------------------------------- days, automation, paperwork, on-time order, backups: U14 U15 U17 U20 U23
TUESDAY = ["CUSTOM", "MIXED", "SWAP-E", "SWAP-W", "MODE", "LOCAL-B", "FIDDLE JOB", "LOCAL-H", "KESSOCK TRANSFER",
           "KESSOCK SWITCHER", "SAWYER SWITCHER", "EAST FREIGHT", "THRU", "NORTH JOB", "PELL SWITCHER", "HOP OUT",
           "TURN", "VALLEY FLYER"]
SATURDAY = ["SWAP-E", "SWAP-W", "EAST FREIGHT", "HOP OUT", "NORTH JOB", "VALLEY FLYER"]
# What builds while the automation runs on its own thread: enough work to outlast its five steps.
OTHERS = [t for t in TUESDAY if t not in ("LOCAL-H", "LOCAL-B", "MODE", "SWAP-E", "SWAP-W")]


class FCase(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)

    def copy(self, name="ops"):
        target = Path(self.work.name) / name
        shutil.copytree(SHOWCASE, target, ignore=shutil.ignore_patterns("backups", "buildstatus"))
        return target

    def edit(self, folder, actions):
        plan = ops_store.plan(folder, actions)
        ops_store.apply(plan["plan_id"], True)

    def gate(self, folder, code, car="DAYX 1", destination="Dunmere", track="Tuesday Dock", train="LOCAL-B"):
        result = Gates(ops_data.load(folder)).why_not(car, destination, track, train, real_build=False)
        return next(g for g in result["gates"] if g["gate"] == code)


class DaysCases(FCase):
    def test_days_list_and_active_day(self):
        import operations_pro
        days = {d["name"]: d for d in operations_pro.list_items({"type": "days", "ops_dir": str(SHOWCASE)})}
        listed = operations_pro.list_items({"type": "trains", "ops_dir": str(SHOWCASE)})
        names = {t["id"]: t["name"] for t in listed}
        self.assertEqual(sorted(names[i] for i in days["Tuesday"]["trains"]), sorted(TUESDAY))
        self.assertEqual(sorted(names[i] for i in days["Saturday"]["trains"]), sorted(SATURDAY))
        self.assertEqual([n for n, d in days.items() if d["active"]], ["Tuesday"])
        self.assertTrue(all(t["build"] for t in listed))  # apply_day Tuesday left every Build box on

    def test_u14_tuesday_line_passes_and_saturday_fails(self):
        folder = self.copy()
        self.assertEqual(self.gate(folder, "A1")["status"], "pass")
        self.assertEqual(self.gate(folder, "F1")["status"], "pass")
        self.edit(folder, [{"action": "set_active_day", "name": "Saturday"}, {"action": "apply_day", "day": "Saturday"}])
        self.assertEqual(self.gate(folder, "A1")["status"], "fail")
        self.assertEqual(self.gate(folder, "F1")["status"], "fail")

    @NEEDS_JMRI
    def test_u14_report_header_and_saturday_build(self):
        report = SESSIONS[0][0]["builds"]["LOCAL-B"]["report_text"]
        self.assertIn("Active schedule: Tuesday", report)
        self.assertEqual(sorted(SESSIONS[0][0]["builds"]), sorted(TUESDAY))
        folder = self.copy()
        self.edit(folder, [{"action": "set_active_day", "name": "Saturday"}, {"action": "apply_day", "day": "Saturday"}])
        saturday = ops_jmri.run_worker(folder, {"build": True})
        self.assertEqual(sorted(saturday["builds"]), sorted(SATURDAY))
        self.assertIn("Active schedule: Saturday", saturday["builds"]["SWAP-E"]["report_text"])


class AutomationCases(FCase):
    def test_u15_steps_and_refusal(self):
        folder = self.copy()
        autos = {a["name"]: a for a in ops_data.read_automations(folder)}
        steps = lambda name: [s["do"] for s in autos[name]["steps"]]  # noqa: E731
        self.assertEqual(steps("Evening Session"), ["build_train", "build_train", "run_automation",
                                                    "wait_for_train_to_terminate", "terminate_train"])
        self.assertEqual(steps("Close Out"), ["terminate_train"])
        self.assertFalse(any(a["startup"] for a in autos.values()))
        with self.assertRaises(Refused) as caught:
            ops_store.plan(folder, [{"action": "update_automation", "automation": "Evening Session", "steps": [
                {"do": "build_train", "train": "LOCAL-H"}, {"do": "message_yes_no", "message": "Continue?"}]}])
        self.assertIn("allow_dialogs", str(caught.exception))

    @NEEDS_JMRI
    def test_u15_jmri_runs_it_at_load(self):
        folder = self.copy()
        self.edit(folder, [{"action": "set_startup_automation", "automation": "Evening Session"}])
        keep = Path(self.work.name) / "kept"
        # Test-harness race, not a railroad fault: the automation runs on its own thread and run_worker saves as soon
        # as its own job ends. Building the other trains keeps the worker alive, but a loaded machine can still save
        # before the last step: try up to three times for a save that came after it. What ran is asserted exactly.
        for _ in range(3):
            shutil.rmtree(keep, ignore_errors=True)
            keep.mkdir()
            ops_jmri.run_worker(folder, {"save": True, "build": True, "only": OTHERS}, keep)
            autos = {a["name"]: a for a in ops_data.read_automations(keep)}
            if autos["Evening Session"]["steps"][-1]["ran"]:
                break
        self.assertEqual([(s["do"], s["ran"], s["successful"]) for s in autos["Evening Session"]["steps"]],
                         [("build_train", True, True), ("build_train", True, True), ("run_automation", True, True),
                          ("wait_for_train_to_terminate", True, True), ("terminate_train", True, True)])
        self.assertTrue(autos["Close Out"]["steps"][0]["ran"])
        built = {t.name: t.built for t in ops_data.load(keep).trains.values()}
        self.assertFalse(built["LOCAL-H"])
        self.assertFalse(built["LOCAL-B"])

    @NEEDS_JMRI
    def test_u15_wait_after_own_terminate_never_finishes(self):
        folder = self.copy()
        self.edit(folder, [
            {"action": "update_automation", "automation": "Evening Session", "steps": [
                {"do": "build_train", "train": "LOCAL-B"}, {"do": "terminate_train", "train": "LOCAL-B"},
                {"do": "wait_for_train_to_terminate", "train": "LOCAL-B"}, {"do": "terminate_train", "train": "LOCAL-H"}]},
            {"action": "set_startup_automation", "automation": "Evening Session"}])
        keep = Path(self.work.name) / "kept"
        keep.mkdir()
        ops_jmri.run_worker(folder, {"save": True, "build": True, "only": OTHERS}, keep)
        steps = next(a for a in ops_data.read_automations(keep) if a["name"] == "Evening Session")["steps"]
        self.assertEqual([s["ran"] for s in steps], [True, True, False, False])


class PaperworkCases(FCase):
    def test_u17_settings_in_the_file(self):
        import operations_pro
        rr = ops_data.load(SHOWCASE)
        self.assertEqual(rr.manifest_texts["manifest"]["valid"], "Conductor''s copy, valid {0}")
        options = {o["name"]: o["value"] for o in operations_pro.list_items({"type": "manifest", "ops_dir": str(SHOWCASE)})}
        self.assertEqual((options["pickup_color"], options["drop_color"], options["local_color"]),
                         ("red", "blue", "green"))
        self.assertEqual(options["pickup_car"]["fields"], ["Road", "Number", "Type", "Length", "Load", "Track"])
        self.assertEqual(options["train LOCAL-B"]["railroad_name"], "Brae Branch Lines")
        self.assertEqual(options["train LOCAL-H"]["railroad_name"], "")

    def test_u17_unmatched_brace_is_refused(self):
        with self.assertRaises(Refused) as caught:
            ops_store.plan(SHOWCASE, [{"action": "set_manifest_text", "group": "manifest", "key": "valid",
                                       "text": "Valid {0"}])
        self.assertIn("a { must open a numbered argument", str(caught.exception))

    @NEEDS_JMRI
    def test_u17_jmri_prints_it(self):
        local_b = SESSIONS[0][0]["manifests"]["LOCAL-B"]
        fiddle = SESSIONS[0][0]["manifests"]["FIDDLE JOB"]
        self.assertTrue(local_b.startswith("Brae Branch Lines"))
        self.assertNotIn("Brae Branch Lines", fiddle)
        for text in (local_b, fiddle):
            self.assertIn("Conductor's copy, valid ", text)
            self.assertNotIn("''", text)
        picks = [l for l in local_b.splitlines() if "Pick up" in l]
        sets = [l for l in local_b.splitlines() if "Set out" in l]
        self.assertTrue(picks and all(l.startswith('<FONT color="red"> [ ] Pick up') for l in picks))
        self.assertTrue(sets and all(l.startswith('<FONT color="blue"> [ ] Set out') for l in sets))
        self.assertTrue(all(re.search(r" (from|to) [^<]+</FONT>$", l) or "Machinery" in l for l in picks[:1]))


class OnTimeCases(FCase):
    def _on_time_copy(self, late_hour=None):
        folder = self.copy()
        actions = [{"action": "set_option", "group": "buildOptions", "name": "onTime", "value": True}]
        if late_hour:
            actions.append({"action": "update_train", "train": "LOCAL-B", "depart_hour": late_hour})
        self.edit(folder, actions)
        return folder

    def test_u20_ships_with_on_time_off(self):
        self.assertNotIn(ops_data.load(SHOWCASE).option("buildOptions", "onTime"), (True, "true"))
        times = {t.name: t for t in ops_data.load(SHOWCASE).trains.values()}
        self.assertTrue(times["LOCAL-B"].name)

    @NEEDS_JMRI
    def test_u20_earlier_train_aborts_after_a_later_one(self):
        folder = self._on_time_copy()
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        first = ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        self.assertTrue(first["builds"]["LOCAL-H"]["built"])
        gate = self.gate(saved, "A2")
        self.assertEqual(gate["status"], "fail")
        self.assertIn("LOCAL-B departs at minute 540; last built train LOCAL-H departs at minute 600", gate["reason"])
        row = ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})["builds"]["LOCAL-B"]
        self.assertFalse(row["built"])
        self.assertEqual(row["message"], "Error")  # JMRI aborts before it writes a report
        self.assertEqual(row["report_text"], "")

    @NEEDS_JMRI
    def test_u20_later_departure_time_builds(self):
        folder = self._on_time_copy(late_hour=11)
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        self.assertEqual(self.gate(saved, "A2")["status"], "pass")
        self.assertTrue(ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})["builds"]["LOCAL-B"]["built"])

    @NEEDS_JMRI
    def test_u20_same_order_works_when_on_time_is_off(self):
        folder = self.copy()
        saved = Path(self.work.name) / "saved"
        saved.mkdir()
        ops_jmri.run_worker(folder, {"build": True, "only": ["LOCAL-H"], "save": True}, saved)
        self.assertTrue(ops_jmri.run_worker(saved, {"build": True, "only": ["LOCAL-B"]})["builds"]["LOCAL-B"]["built"])


class BackupCases(FCase):
    def test_u23_shipped_folder_holds_one_manual_set(self):
        sets = ops_store.backups(SHOWCASE)
        self.assertEqual(len(sets), 1, sets)
        self.assertTrue(sets[0]["set"].startswith("opspro_manual_"))
        self.assertTrue(sets[0].get("complete", True))

    def test_u23_backup_delete_restore(self):
        folder = self.copy()
        before = Gates(ops_data.load(folder)).audit()["findings"]
        made = ops_store.backup(folder, "manual")
        name = made if isinstance(made, str) else made.get("backup", made.get("set"))
        self.assertIn(str(name), [s["set"] for s in ops_store.backups(folder)])
        self.edit(folder, [{"action": "delete_car", "car": "DAYX 1"}])
        self.assertNotIn("DAYX1", ops_data.load(folder).cars)
        ops_store.restore(folder, str(name), "backups")
        self.assertIn("DAYX1", ops_data.load(folder).cars)
        self.assertEqual(Gates(ops_data.load(folder)).audit()["findings"], before)


# ---------------------------------------------------------------- whole-railroad checks
def _signature(rr):
    import dataclasses
    out = {}
    for key, value in vars(rr).items():
        if key == "directory":
            continue
        out[key] = dataclasses.asdict(value) if dataclasses.is_dataclass(value) else value
    return repr(out)


GUIDE = EXAMPLE / "GUIDE.md"


def guide_pointers() -> dict:
    """Case code -> backticked names in that case's Find it line(s), read from GUIDE.md."""
    text = GUIDE.read_text(encoding="utf-8")
    found = {}
    for block in re.split(r"\n(?=### [UR]\d\d\b)", text):
        head = re.match(r"### ([UR]\d\d)\b", block)
        if not head:
            continue
        names = []
        for line in block.splitlines():
            if line.startswith("**Find it:**"):
                names += [n for n in re.findall(r"`([^`]+)`", line) if not n.endswith("/")]
        found[head.group(1)] = names
    return found


def database_names(rr) -> set:
    names = {l.name for l in rr.locations.values()} | {t.name for t in rr.tracks.values()}
    names |= {s.name for s in rr.schedules.values()} | {r.name for r in rr.routes.values()}
    names |= {t.name for t in rr.trains.values()}
    names |= {c.id for c in rr.cars.values()} | {str(c) for c in rr.cars.values()}
    names |= {e.id for e in rr.engines.values()} | {f"{e.road} {e.number}" for e in rr.engines.values()}
    names |= {n for n in getattr(rr, "loads", {}) and [x.name for v in rr.loads.values() for x in v]}
    names |= {k.name for k in getattr(rr, "kernels", {}).values()} if isinstance(getattr(rr, "kernels", None), dict) else set()
    names |= {c.kernel for c in rr.cars.values() if c.kernel}
    names |= {t.pool for t in rr.tracks.values() if t.pool}
    names |= {getattr(d, "name", d) for d in rr.divisions.values()}
    names |= {d.name for d in getattr(rr, "days", {}).values()} if isinstance(getattr(rr, "days", None), dict) else set()
    names |= {a["name"] for a in ops_data.read_automations(SHOWCASE)}
    return names


def xml_tags() -> dict:
    """Case code -> set of 'element:name' for every object whose comment starts a [Uxx] or [Rxx] tag, read from the XML."""
    import xml.etree.ElementTree as ET
    found = {}
    for name in ops_store.FILES:
        for el in ET.parse(SHOWCASE / name).getroot().iter():
            comment = el.get("comment") or ""
            for code in re.findall(r"\[([UR]\d\d)\]", comment):
                who = el.get("name") or el.get("id", "")
                found.setdefault(code, set()).add(f"{el.tag}:{who}")
    return found


def car_comments() -> dict:
    import xml.etree.ElementTree as ET
    root = ET.parse(SHOWCASE / "OperationsCarRoster.xml").getroot()
    return {el.get("roadName", "") + el.get("roadNumber", ""): el.get("comment") or "" for el in root.iter("car")}


class WholeRailroad(unittest.TestCase):
    def test_audit_empty(self):
        findings = Gates(ops_data.load(SHOWCASE)).audit()["findings"]
        kept = {(f["severity"], f["rule"], f["subject"]) for f in findings}
        self.assertEqual(kept, INTENDED_FINDINGS)
        infos = [f for f in findings if f["severity"] == "info"]
        self.assertEqual(len(infos), 2)  # Ferris Transfer: two other routes call there
        self.assertEqual(sum(f["severity"] == "error" for f in findings), 0)

    @NEEDS_JMRI
    def test_loads_and_saves_unchanged(self):
        keep = TMP / "saved-again"
        keep.mkdir()
        result = ops_jmri.run_worker(SHOWCASE, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        self.assertEqual(_signature(ops_data.load(keep)), _signature(ops_data.load(SHOWCASE)))

    @NEEDS_JMRI
    def test_clean_build(self):
        (TMP / "clean").mkdir()
        result = ops_jmri.run_worker(SHOWCASE, {"build": True}, TMP / "clean")
        self.assertEqual(result["log_errors"], [])
        self.assertEqual(sorted(result["builds"]), sorted(TUESDAY))
        for name, row in result["builds"].items():
            self.assertTrue(row["built"], f"{name}: {row['message']}")
            self.assertFalse(row["failed"], name)
        shipped = {p.name for p in (SHOWCASE / "buildstatus").glob("train (*).txt")}
        self.assertEqual(shipped, {f"train ({t}).txt" for t in TUESDAY})
        for p in (SHOWCASE / "buildstatus").glob("train (*).txt"):
            self.assertNotIn("Build Failed", p.read_text(encoding="utf-8", errors="replace")[:400], p.name)

    def test_active_day_and_no_built_trains(self):
        rr = ops_data.load(SHOWCASE)
        self.assertEqual([d.name for d in rr.days.values() if d.active] if isinstance(rr.days, dict) else [],
                         ["Tuesday"])
        self.assertFalse(any(t.built for t in rr.trains.values()))

    def test_check_pointers(self):
        pointers = guide_pointers()
        known = database_names(ops_data.load(SHOWCASE))
        tags = set(xml_tags())
        missing = {code: [n for n in names if n not in known] for code, names in pointers.items()}
        self.assertEqual({k: v for k, v in missing.items() if v}, {})
        self.assertEqual([c for c, n in pointers.items() if not n and c != "U23"], [], "a guide case with no Find it names")
        # U23 is the backups folder, which has no object to tag.
        self.assertEqual(sorted(set(pointers) - tags - {"U23"}), [], "a guide case with no tagged object")
        self.assertEqual(sorted(tags - set(pointers)), [], "a tagged object whose code is not in the guide")

    def test_banned_words(self):
        words = [w.strip() for w in os.environ.get("OPS_BANNED_TERMS", "").split(",") if w.strip()]
        listing = Path(os.environ.get("OPS_BANNED_WORDS_FILE",
                                      Path.home() / ".config" / "model-railroad-skills" / "banned_words.txt")).expanduser()
        if listing.is_file():
            words += [w.strip() for w in listing.read_text().splitlines() if w.strip() and not w.startswith("#")]
        if not words:
            self.skipTest("no banned words: set OPS_BANNED_TERMS or OPS_BANNED_WORDS_FILE")
        banned = re.compile("|".join(map(re.escape, words)), re.I)
        for path in EXAMPLE.rglob("*"):
            if path.is_file() and path.suffix in {".xml", ".md", ".json", ".py", ".txt", ".csv"} \
                    and "backups" not in path.parts and "__pycache__" not in path.parts:
                self.assertIsNone(banned.search(path.read_text(encoding="utf-8", errors="replace")), str(path))
        self.assertIsNone(banned.search(Path(__file__).read_text(encoding="utf-8")), "this test file")

    @NEEDS_JMRI
    def test_isolation(self):
        """After session 1 every tagged car sits on a track its case names, or on a yard, interchange or staging
        track. Tracks cannot carry comments, so the map is the guide's Find it lines."""
        pointers = guide_pointers()
        comments = car_comments()
        rr0 = ops_data.load(SHOWCASE)
        track_names = {t.name for t in rr0.tracks.values()}
        loose = {t.name for t in rr0.tracks.values() if t.type in ("Yard", "Interchange", "Staging")}
        checked = 0
        for chain in SESSIONS:
            rr = chain[0]["rr"]
            for car in rr.cars.values():
                codes = re.findall(r"\[([UR]\d\d)\]", comments.get(car.id, ""))
                if not codes:
                    continue
                self.assertIn(car.track_id, rr.tracks, f"{car.id} has no track")
                track = rr.tracks[car.track_id].name
                allowed = loose | {n for c in codes for n in pointers.get(c, []) if n in track_names}
                self.assertIn(track, allowed, f"{car.id} {codes} ended on {track}")
                checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
