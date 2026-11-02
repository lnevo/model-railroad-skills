"""Showcase batch B: Brae and Dunmere industries, the fiddle yard, the kernel, the day-dock track, LCL and R17.

Cases: U01, U02, U03, U08, U09, U10, U13 (kernel), U14 (tracks), U22 (LCL), R17.

The railroad is the skeleton plus build/20_b.json, replayed by examples/showcase/build.py into temporary folders.
Days belong to batch F, so the day half of U14 is proved on a scratch copy that adds them (needs-integration).
Real JMRI tests run only where JMRI is installed. SESSIONS holds CHAINS copies, each run through
SESSIONS_PER_CHAIN consecutive sessions (build, terminate, save, copy the saved files forward).
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "showcase"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402

CHAINS = 3
SESSIONS_PER_CHAIN = 3
NEEDS_JMRI = unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")

_spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

_tmp = None
BASE = None
SESSIONS = []  # SESSIONS[chain][session] = {"builds", "rr", "manifest"}
DAYS = {}


def make_base(root: Path) -> Path:
    """The skeleton and batch B, replayed alone."""
    out = root / "ops"
    shutil.copytree(build.SERVERS / "blank", out)
    for path in build.numbered(20):
        if path.name.startswith(("00", "20")):
            for index, step in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
                build.run_step(out, step, f"{path.name} step {index}")
    return out


def run_chain(base: Path, root: Path, name: str, sessions: int) -> list:
    folder = root / name
    shutil.copytree(base, folder)
    done = []
    for number in range(1, sessions + 1):
        keep = root / f"{name}.s{number}"
        keep.mkdir()
        result = ops_jmri.run_worker(folder, {"build": True, "terminate": True, "save": True}, keep)
        for file in ops_store.FILES:
            if (keep / file).is_file():
                shutil.copy2(keep / file, folder / file)
        manifest = keep / "manifests" / "train (LOCAL-B).txt"
        done.append({"builds": result["builds"], "log_errors": result.get("log_errors"),
                     "rr": ops_data.load(keep),
                     "manifest": manifest.read_text(encoding="utf-8") if manifest.is_file() else ""})
    return done


def setUpModule():
    global _tmp, BASE, SESSIONS
    _tmp = tempfile.TemporaryDirectory(prefix="showcase-b-")
    root = Path(_tmp.name)
    BASE = make_base(root)
    if not ops_jmri.jmri_home():
        return
    with mock.patch.object(ops_store, "running_jmri", return_value=[]):
        with ThreadPoolExecutor(CHAINS) as pool:
            SESSIONS = list(pool.map(lambda i: run_chain(BASE, root, f"chain{i}", SESSIONS_PER_CHAIN),
                                     range(1, CHAINS + 1)))


def tearDownModule():
    if _tmp is not None:
        _tmp.cleanup()


def where(rr, car: str):
    """(location, track, load, final destination track or location) of a car, e.g. where(rr, 'JFN 101')."""
    road, number = car.rsplit(" ", 1)
    c = rr.cars[road + number]
    track = rr.tracks.get(c.track_id)
    final = rr.tracks.get(c.fd_track_id)
    if final is None and c.fd_id in rr.locations:
        final = rr.locations[c.fd_id]
    return (rr.locations[c.location_id].name, track.name if track else None, c.load, final.name if final else "")


def track_type(rr, location: str, name: str) -> str:
    return next(t.type for t in rr.tracks.values() if t.name == name and rr.locations[t.location_id].name == location)


def each_chain(session: int):
    """The state after the numbered session (1 to SESSIONS_PER_CHAIN), one per chain."""
    return [chain[session - 1] for chain in SESSIONS]


class Shipped(unittest.TestCase):
    """What the build file itself leaves, before any session."""

    def setUp(self):
        self.rr = ops_data.load(BASE)

    def test_audit_empty(self):
        self.assertEqual(ops_gates.Gates(self.rr).audit()["findings"], [])

    def test_u02_delivered_car_carries_the_cannery_load(self):
        self.assertEqual(where(self.rr, "JFN 201"), ("Brae", "Brae Cannery", "Canned", "Grocery Dock"))

    def test_u03_delivered_cars_carry_lumber(self):
        for car in ("JFN 301", "JFN 302"):
            self.assertEqual(where(self.rr, car), ("Brae", "Brae Lumber", "Lumber", "Lumber Dealer"))

    def test_u01_delivered_hopper_carries_feed(self):
        self.assertEqual(where(self.rr, "JFN 102"), ("Brae", "Brae Feed Mill", "Feed", "Dunmere Dairy"))

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
class Sessions(unittest.TestCase):
    def test_clean_sessions(self):
        for chain in SESSIONS:
            for session in chain:
                self.assertEqual(session["log_errors"], [])
                for train in ("LOCAL-B", "FIDDLE JOB"):
                    self.assertTrue(session["builds"][train]["built"], train)

    def test_u01_hopper_goes_to_the_dairy_and_the_empty_returns_to_the_mill(self):
        for s in each_chain(1):
            self.assertEqual(where(s["rr"], "JFN 102"), ("Dunmere", "Dunmere Dairy", "E", ""))
            # The empty E hopper takes the later stop's yard: Dunmere Yard also takes it, and the builder
            # alternates between the mill and the yard (the mill has already one car waiting to leave).
            self.assertEqual(where(s["rr"], "JFN 101")[:3], ("Dunmere", "Dunmere Yard", "E"))
        for s in each_chain(3):
            self.assertEqual(where(s["rr"], "JFN 101"), ("Brae", "Brae Feed Mill", "Feed", "Dunmere Dairy"))

    def test_u02_canned_goods_reach_the_grocery_dock(self):
        for s in each_chain(1):
            self.assertEqual(where(s["rr"], "JFN 201"), ("Dunmere", "Grocery Dock", "E", ""))
            self.assertIn("Set out JFN 201 Boxcar 40' Canned to Grocery Dock", s["manifest"])

    def test_u03_lumber_and_the_wanderers(self):
        for s in each_chain(1):
            for car in ("JFN 301", "JFN 302"):
                self.assertEqual(where(s["rr"], car), ("Dunmere", "Lumber Dealer", "E", ""))
        for session in range(1, SESSIONS_PER_CHAIN + 1):
            for s in each_chain(session):
                for car in ("WNDR 1", "WNDR 2"):
                    location, track, _, _ = where(s["rr"], car)
                    self.assertEqual(track_type(s["rr"], location, track), "Yard", (session, car, track))

    def test_u08_fiddle_yard_chain(self):
        tools = parts_at_depot = parts_waiting = south_visits = 0
        cars = [f"JFN 80{n}" for n in range(1, 7)]
        for s in each_chain(1):
            for car in cars:
                location, track, load, final = where(s["rr"], car)
                self.assertEqual(location, "Fiddle")
                if track == "Fiddle North":
                    self.assertEqual((load, final), ("Parts", "Parts Depot"))
                else:
                    self.assertEqual(track, "Fiddle South")
                    south_visits += 1
        self.assertGreater(south_visits, 0)
        for session in (2, 3):
            for s in each_chain(session):
                for car in cars:
                    location, track, load, final = where(s["rr"], car)
                    if track == "Fiddle South" and load == "Tools":
                        self.assertEqual(final, "Tool Depot")
        for s in each_chain(SESSIONS_PER_CHAIN):
            chain_parts = 0
            for car in cars:
                location, track, load, final = where(s["rr"], car)
                if track == "Parts Depot":
                    chain_parts += 1
                    self.assertEqual(load, "E")
                parts_waiting += load == "Parts"
                tools += load == "Tools"
            self.assertGreaterEqual(chain_parts, 1, "every chain has delivered a parts car by session 3")
            parts_at_depot += chain_parts
        self.assertGreater(parts_at_depot, tools)

    def test_u09_one_car_per_fifty_foot_elevator(self):
        for s in each_chain(1):
            self.assertEqual({where(s["rr"], "JFN 901")[1], where(s["rr"], "JFN 902")[1]},
                             {"Elevator A", "Elevator B"})
            self.assertEqual(where(s["rr"], "JFN 901")[2], "E")

    def test_u10_two_freight_houses_print_one_name(self):
        for s in each_chain(1):
            self.assertEqual(where(s["rr"], "FRHX 1")[:2], ("Dunmere", "Freight House"))
            self.assertEqual(where(s["rr"], "JFN 1001")[:2], ("Dunmere", "Freight House-(2)"))
            self.assertIn("Set out FRHX 1 Boxcar 40' E to Freight House [U10]", s["manifest"])
            self.assertIn("Set out JFN 1001 Boxcar 40' Crates to Freight House [U10]", s["manifest"])
            self.assertNotIn("Freight House-(2)", s["manifest"])

    def test_u13_kernel_moves_together(self):
        for session in (1, 2, 3):
            for s in each_chain(session):
                spots = {where(s["rr"], f"KRNX {n}")[:2] for n in (1, 2, 3)}
                self.assertEqual(spots, {("Dunmere", "Dunmere Team")}, session)
        for s in each_chain(1):
            for n in (1, 2, 3):
                self.assertIn(f"Set out KRNX {n} Boxcar 40' E to Dunmere Team", s["manifest"])

    def test_u14_tracks_half(self):
        for s in each_chain(1):
            self.assertEqual(where(s["rr"], "DAYX 1")[:2], ("Dunmere", "Tuesday Dock"))

    def test_u22_lcl_car_rides_and_returns(self):
        for session in (1, 2, 3):
            for s in each_chain(session):
                self.assertEqual(where(s["rr"], "LCLX 1")[:2], ("Carrow", "Carrow LCL Dock"))
        for s in each_chain(1):
            self.assertIn("Pick up LCLX 1 Boxcar 40' from Carrow LCL Dock", s["manifest"])
            self.assertIn("Set out LCLX 1 Boxcar 40' to Carrow LCL Dock", s["manifest"])

    def test_r17_outside_track_flips_the_load_both_ways(self):
        for s in each_chain(1):
            self.assertEqual(where(s["rr"], "OUTX 1"), ("Brae", "Brae Outside", "L", ""))
            self.assertEqual(where(s["rr"], "OUTX 2"), ("Carrow", "Carrow Outside Lead", "E", ""))
        for s in each_chain(2):
            self.assertEqual(where(s["rr"], "OUTX 2"), ("Brae", "Brae Outside", "L", ""))
            self.assertEqual(where(s["rr"], "OUTX 1"), ("Carrow", "Carrow Outside Lead", "E", ""))


class WhyNot(unittest.TestCase):
    """Reads only: ops_why_not with real_build false, on the shipped files."""

    def why(self, car, destination, track, train="LOCAL-B", folder=None):
        import operations_pro
        return operations_pro.why_not({"ops_dir": str(folder or BASE), "car": car, "destination": destination,
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
        copy = Path(_tmp.name) / "nopass"
        shutil.copytree(BASE, copy)
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_store.quick(copy, [{"action": "update_car", "car": "LCLX 1", "passenger": False}])
        result = self.why("LCLX 1", "Carrow", "Carrow LCL Dock", folder=copy)
        self.assertEqual(result["first_failure"]["gate"], "D4")

    def test_r17_outside_track_takes_the_empty(self):
        self.assertTrue(self.why("OUTX 1", "Brae", "Brae Outside")["can_move"])


@NEEDS_JMRI
class WithDays(unittest.TestCase):
    """U14, the day half: needs batch F's days, so a scratch copy adds them (needs-integration)."""

    @classmethod
    def setUpClass(cls):
        root = Path(_tmp.name)
        cls.copy = root / "days"
        shutil.copytree(BASE, cls.copy)
        names = [t.name for t in ops_data.load(cls.copy).trains.values()]
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            plan = ops_store.plan(cls.copy, [
                {"action": "add_default_days"},
                {"action": "set_line_days", "schedule": "Tuesday Dock", "line": 1, "setout_day": "Tuesday"},
                {"action": "set_day_trains", "day": "Tuesday", "trains": names},
                {"action": "set_day_trains", "day": "Saturday",
                 "trains": ["SWAP-E", "SWAP-W", "EAST FREIGHT", "HOP OUT", "NORTH JOB", "VALLEY FLYER"]},
                {"action": "set_active_day", "name": "Tuesday"}, {"action": "apply_day", "day": "Tuesday"}])
            ops_store.apply(plan["plan_id"], False)
        cls.chain = run_chain(cls.copy, root, "days-chain", 1)[0]

    def test_tuesday_dock_takes_the_car_on_tuesday(self):
        self.assertEqual(where(self.chain["rr"], "DAYX 1")[:2], ("Dunmere", "Tuesday Dock"))
        report = self.chain["builds"]["LOCAL-B"]["report_text"]
        self.assertIn("Active schedule: Tuesday", report)

    def test_saturday_stops_local_b_and_closes_the_dock(self):
        import operations_pro
        copy = Path(_tmp.name) / "saturday"
        shutil.copytree(self.copy, copy)
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            plan = ops_store.plan(copy, [{"action": "set_active_day", "name": "Saturday"},
                                         {"action": "apply_day", "day": "Saturday"}])
            ops_store.apply(plan["plan_id"], False)
        result = operations_pro.why_not({"ops_dir": str(copy), "car": "DAYX 1", "destination": "Dunmere",
                                         "track": "Tuesday Dock", "train": "LOCAL-B", "real_build": False})
        gates = {g["gate"]: g["status"] for g in result["gates"]}
        self.assertEqual((gates["A1"], gates["F1"]), ("fail", "fail"))


if __name__ == "__main__":
    unittest.main()
