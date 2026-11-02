"""Showcase batch A: staging cases U06, U07, U12, U13 (consist, loco change), U22 (hazmat, buffer and kernel on TURN), R19.

The railroad is the skeleton plus build/10_a.json, replayed by examples/showcase/build.py into temporary folders.
Brae Depot and Dunmere Depot belong to batch B, so U06 gets stand-ins here (scratch copies only, never shipped);
stage 4 replaces them with the real ones and the assertions that need them are marked needs-integration.

Real JMRI tests run only where JMRI is installed. SESSIONS holds CHAINS copies, each run through
SESSIONS_PER_CHAIN consecutive sessions (build, terminate, save, copy the saved files forward).
"""
import importlib.util
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
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402

CHAINS = 3
SESSIONS_PER_CHAIN = 2
NEEDS_JMRI = unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
BATCH = 10

_spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)

STAND_INS = [  # batch B's depots, reduced to what U06 needs
    {"action": "add_industry", "location": "Brae", "name": "Brae Depot", "length": 200,
     "lines": [{"type": "Boxcar", "receive": "Machinery", "ship": "E"}]},
    {"action": "add_industry", "location": "Dunmere", "name": "Dunmere Depot", "length": 200,
     "lines": [{"type": "Boxcar", "receive": "Machinery", "ship": "E"}]},
]
DEPOTS = {"Brae Depot", "Dunmere Depot"}

_tmp = None
BASE = None
SESSIONS = []  # SESSIONS[chain][session] = {"builds", "rr", "manifests"}


def make_base(root: Path, stand_ins: bool = True) -> Path:
    """The skeleton and batch A, replayed alone, plus the stand-ins."""
    out = root / "ops"
    shutil.copytree(build.SERVERS / "blank", out)
    for path in build.numbered(BATCH):
        if path.name.startswith(("00", "10")):
            import json
            for index, step in enumerate(json.loads(path.read_text(encoding="utf-8")), 1):
                build.run_step(out, step, f"{path.name} step {index}")
    if stand_ins:
        plan = ops_store.plan(out, STAND_INS)
        ops_store.apply(plan["plan_id"], True)
    return out


def run_chain(start: Path, label: str) -> list[dict]:
    work = Path(tempfile.mkdtemp(prefix=f"chain-{label}-"))
    for name in ops_store.FILES:
        if (start / name).is_file():
            shutil.copy2(start / name, work / name)
    sessions = []
    for index in range(SESSIONS_PER_CHAIN):
        keep = work / f"keep{index}"
        keep.mkdir()
        result = ops_jmri.run_worker(work, {"build": True, "terminate": True, "save": True}, keep)
        manifests = {}
        if (keep / "manifests").is_dir():
            for path in (keep / "manifests").glob("train (*).txt"):
                manifests[path.stem[7:-1]] = path.read_text(encoding="utf-8")
        for name in ops_store.FILES:
            if (keep / name).is_file():
                shutil.copy2(keep / name, work / name)
        sessions.append({"builds": result["builds"], "log_errors": result["log_errors"], "manifests": manifests,
                         "rr": ops_data.load(keep)})
    return sessions


def setUpModule():
    global _tmp, BASE
    if not ops_jmri.jmri_home():
        return
    _tmp = tempfile.TemporaryDirectory(prefix="showcase-a-")
    patch = mock.patch.object(ops_store, "running_jmri", lambda *a, **k: [])
    patch.start()
    BASE = make_base(Path(_tmp.name))
    SESSIONS.extend(ThreadPoolExecutor(CHAINS).map(lambda n: run_chain(BASE, str(n)), range(CHAINS)))
    patch.stop()


def tearDownModule():
    if _tmp is not None:
        _tmp.cleanup()


def cars(session: dict, train: str) -> dict:
    """Car id to (location, track) from the build's own list, for one train."""
    out = {}
    for row in session["builds"][train]["cars"]:
        who, where = row.split(" > ")
        location, track = where.split(" / ")
        out[who] = (location, track)
    return out


def where_is(session: dict, what: str) -> tuple[str, str]:
    """Saved location and track of a car or engine after the session."""
    rr = session["rr"]
    thing = rr.cars.get(what) or rr.engines.get(what)
    track = rr.tracks[thing.track_id]
    return rr.locations[track.location_id].name, track.name


def final_track(session: dict, car: str) -> str:
    rr = session["rr"]
    return rr.tracks[rr.cars[car].fd_track_id].name if rr.cars[car].fd_track_id else ""


class StaticTests(unittest.TestCase):
    def test_batch_file_replays_with_its_locomotives(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(ops_store, "running_jmri", lambda *a, **k: []):
                out = make_base(Path(tmp), stand_ins=False)
            rr = ops_data.load(out)
            for engine in ("JFN51", "JFN52", "JFN53", "JFN54", "JFN55", "JFN56", "JFN57"):
                self.assertIn(engine, rr.engines)
            self.assertEqual(rr.engines["JFN51"].consist, "West Pair")
            self.assertEqual(rr.engines["JFN53"].consist, "East Pair")


@NEEDS_JMRI
class SessionTests(unittest.TestCase):
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
            self.assertEqual(cars(s1, "CUSTOM"), {f"JFN{n}": ("Carrow", "Carrow Yard") for n in range(601, 605)})
            for n in range(601, 605):
                self.assertEqual(s1["rr"].cars[f"JFN{n}"].load, "Machinery")
                self.assertIn(final_track(s1, f"JFN{n}"), DEPOTS)
            # MIXED: the boxcars go to a depot with Machinery; the gondola has no load and leaves as an empty.
            self.assertTrue(s1["builds"]["MIXED"]["built"])
            mixed = cars(s1, "MIXED")
            for n in (611, 612, 613):
                self.assertIn(mixed[f"JFN{n}"][1], DEPOTS)
                self.assertIn(f"JFN {n} Boxcar 40' Machinery", s1["manifests"]["MIXED"])
            self.assertEqual(mixed["JFN614"], ("East Staging", "East Mixed"))
            self.assertNotIn("JFN 614 Gondola 40' Machinery", s1["manifests"]["MIXED"])
            # Both departure tracks are empty afterwards, as they must be.
            for n in list(range(601, 605)) + list(range(611, 615)):
                self.assertNotIn(where_is(s1, f"JFN{n}")[1], {"West Custom", "West Mixed"})

    def test_u07_staging_swap(self):
        for chain in SESSIONS:
            s1, s2 = chain[0], chain[1]
            self.assertTrue(s1["builds"]["SWAP-E"]["built"] and s1["builds"]["SWAP-W"]["built"])
            self.assertEqual(cars(s1, "SWAP-E"), {f"SWPX{n}": ("East Staging", "East Swap") for n in range(1, 7)})
            self.assertEqual(cars(s1, "SWAP-W"), {f"SWPX{n}": ("West Staging", "West Swap") for n in range(11, 17)})
            self.assertEqual(s1["builds"]["SWAP-E"]["departure_track"], "West Swap")
            self.assertEqual(s1["builds"]["SWAP-W"]["departure_track"], "East Swap")
            # Session 2: the same trip the other way.
            self.assertEqual(cars(s2, "SWAP-E"), {f"SWPX{n}": ("East Staging", "East Swap") for n in range(11, 17)})
            self.assertEqual(cars(s2, "SWAP-W"), {f"SWPX{n}": ("West Staging", "West Swap") for n in range(1, 7)})

    def test_u12_staging_train_normal_mode(self):
        for chain in SESSIONS:
            s1 = chain[0]
            build_row = s1["builds"]["MODE"]
            self.assertTrue(build_row["built"])
            placed = cars(s1, "MODE")
            self.assertEqual(len(placed), 5)
            at_yard = [c for c, w in placed.items() if w == ("Brae", "Brae Stockyard")]
            at_east = [c for c, w in placed.items() if w == ("East Staging", "East Mode")]
            # The loco change takes two of Brae's three moves, so one car fits there; the rest go to staging.
            self.assertEqual((len(at_yard), len(at_east)), (1, 4))
            for n in range(1, 6):
                self.assertNotEqual(where_is(s1, f"MODX{n}")[1], "West Mode")

    def test_u12_aggressive_mode_makes_no_difference(self):
        plan = ops_store.plan(BASE, [{"action": "set_option", "group": "buildOptions", "name": "aggressive",
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
            self.assertEqual(where_is(s1, "JFN51"), ("East Staging", "East Swap"))
            self.assertEqual(where_is(s1, "JFN53"), ("West Staging", "West Swap"))
            self.assertEqual(sorted(s2["builds"]["SWAP-E"]["engines"]), ["JFN53", "JFN54"])
            manifest = s1["manifests"]["MODE"]
            self.assertIn("Locomotive change at Brae", manifest)
            self.assertIn("Set out JFN 55 GP9 to Brae Engine Track", manifest)
            self.assertIn("Pick up JFN 56 GP9 from Brae Engine Track", manifest)
            self.assertIn("Set out JFN 56 GP9 to East Mode", manifest)
            self.assertEqual(where_is(s1, "JFN55"), ("Brae", "Brae Engine Track"))
            self.assertEqual(where_is(s1, "JFN56"), ("East Staging", "East Mode"))
            self.assertEqual(where_is(s1, "JFN57"), ("Carrow", "Carrow Yard"))  # the spare never moves

    def test_u22_hazmat_buffer_and_kernel_on_turn(self):
        for chain in SESSIONS:
            s1 = chain[0]
            placed = cars(s1, "TURN")
            for n in (1, 2, 3):
                self.assertEqual(placed[f"HZMX{n}"], ("Linden", "Linden Refinery"))
            for n in (11, 12, 13):
                self.assertEqual(placed[f"HZMX{n}"], ("Linden", "Linden Steel"))
            self.assertEqual(placed["HZMX9"], ("West Staging", "Turn B"))
            manifest = s1["manifests"]["TURN"]
            picks = [line for line in manifest.splitlines() if line.startswith(" [ ] Pick up")]
            self.assertIn("HZMX 9 Buffer", picks[0])  # the buffer is the first car out of staging
            self.assertIn("HZMX 3 Tank Gas 40' L (Hazardous)", manifest)
            self.assertEqual(s1["rr"].cars["HZMX9"].passenger, True)

    def test_r19_staging_to_staging_turn(self):
        for chain in SESSIONS:
            s1, s2 = chain[0], chain[1]
            self.assertEqual(s1["builds"]["TURN"]["departure_track"], "Turn A")
            placed = cars(s1, "TURN")
            self.assertEqual(placed["TRNX1"], ("Linden", "Linden Team"))
            self.assertEqual(placed["TRNX2"], ("Linden", "Linden Team"))
            self.assertEqual(placed["TRNX3"], ("West Staging", "Turn B"))
            # Session 2: the turn leaves from Turn B and ends on Turn A.
            self.assertEqual(s2["builds"]["TURN"]["departure_track"], "Turn B")
            back = cars(s2, "TURN")
            self.assertEqual(back["TRNX1"], ("West Staging", "Turn A"))
            self.assertEqual(back["TRNX2"], ("West Staging", "Turn A"))
            self.assertEqual(back["TRNX3"], ("Linden", "Linden Team"))


if __name__ == "__main__":
    unittest.main()
