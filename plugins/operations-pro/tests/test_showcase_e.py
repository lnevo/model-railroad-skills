"""Showcase batch E (build/50_e.json), proved in real headless JMRI 5.16.

The railroad under test is servers/blank plus build/00_skeleton.json plus build/50_e.json, replayed by
examples/showcase/build.py without the merge step. Other batches are not present, so cases that need
their objects (R03's Oakhaven Foundry, R18's TURN staging tracks) are proved on a scratch copy with a
temporary stand-in and marked needs-integration in RESULTS.md; stage 4 asserts the full chain.

Three copies each run three sessions (build, terminate, save) in parallel, as PLAN.md section 7 says.
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
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_gates import Gates  # noqa: E402

CHAINS, SESSIONS_PER_CHAIN = 3, 3
JMRI = unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")

_spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
showcase_build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(showcase_build)

TMP: Path
BASE: Path
SESSIONS: list  # SESSIONS[chain][session] = {"cars": {train: [car strings]}, "built": {...}, "manifests": {train: text}}


def replay(dest: Path, files=("00_skeleton.json", "50_e.json")) -> Path:
    shutil.copytree(ROOT / "servers" / "blank", dest, dirs_exist_ok=True)
    for name in files:
        for index, step in enumerate(json.loads((SHOWCASE / "build" / name).read_text(encoding="utf-8")), 1):
            showcase_build.run_step(dest, step, f"{name} step {index}")
    return dest


def run_chain(source: Path, work: Path, sessions: int = SESSIONS_PER_CHAIN) -> list:
    """Run consecutive sessions on a copy, carrying the saved files forward."""
    shutil.copytree(source, work / "cur")
    out = []
    for number in range(1, sessions + 1):
        keep = work / f"s{number}"
        keep.mkdir()
        result = ops_jmri.run_worker(work / "cur", {"build": True, "terminate": True, "save": True}, keep)
        manifests = {}
        for path in (keep / "manifests").glob("*"):
            manifests[path.name] = path.read_text(encoding="utf-8", errors="replace")
        out.append({"cars": {k: v["cars"] for k, v in result["builds"].items()},
                    "built": {k: v["built"] for k, v in result["builds"].items()},
                    "log_errors": result["log_errors"], "manifests": manifests})
        for name in ops_store.FILES:
            if (keep / name).is_file():
                shutil.copy2(keep / name, work / "cur" / name)
    return out


def setUpModule():
    global TMP, BASE, SESSIONS
    TMP = Path(tempfile.mkdtemp(prefix="showcase-e-"))
    with mock.patch.object(ops_store, "running_jmri", return_value=[]):
        BASE = replay(TMP / "base")
    SESSIONS = []
    if ops_jmri.jmri_home():
        with ThreadPoolExecutor(max_workers=CHAINS) as pool:
            futures = [pool.submit(run_chain, BASE, _fresh(TMP / f"chain{n}")) for n in range(CHAINS)]
            SESSIONS = [f.result() for f in futures]


def _fresh(path: Path) -> Path:
    path.mkdir(parents=True)
    return path


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


def variant(name: str, actions: list) -> Path:
    """A scratch copy of the base with one plan applied; experiments and stand-ins live here, never in the build file."""
    dest = TMP / name
    shutil.copytree(BASE, dest)
    with mock.patch.object(ops_store, "running_jmri", return_value=[]):
        plan = ops_store.plan(dest, actions)
        ops_store.apply(plan["plan_id"], True)
    return dest


def why_not(folder: Path, car: str, destination: str, track=None, train=None) -> dict:
    return Gates(ops_data.load(folder)).why_not(car, destination, track, train, False)


class ShowcaseE(unittest.TestCase):
    def sessions(self, number: int, train: str):
        """The cars the train moved in session number (1 based), once per chain."""
        return [chain[number - 1]["cars"].get(train, []) for chain in SESSIONS]

    def test_chains_ran_clean(self):
        for chain in SESSIONS:
            for session in chain:
                self.assertEqual(session["log_errors"], [])

    def test_audit_only_known_findings(self):
        findings = Gates(ops_data.load(BASE)).audit()["findings"]
        # Batch A adds the staging tracks that clear the errors; the infos are the lists R05, R11, R13 and U18 rely on.
        other = [f for f in findings if f["rule"] not in ("train-not-on-list", "terminal-staging-refuses-train",
                                                          "staging-departure-blocked")]
        self.assertEqual(other, [])

    @JMRI
    def test_R05_route_through_staging(self):
        for chain in SESSIONS:
            self.assertIn("JFN5501 > East Staging / Hop", chain[0]["cars"]["EAST FREIGHT"])
            self.assertIn("JFN5502 > Carrow / Carrow Yard", chain[0]["cars"]["HOP OUT"])
            self.assertIn("JFN5501 > Linden / Linden Pier", chain[1]["cars"]["HOP OUT"])
        route = why_not(BASE, "JFN 5501", "Linden", "Linden Pier")["router"]["route"]
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
        state = TMP / "chain0" / "s1"
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
        self.assertTrue(why_not(BASE, "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")["can_move"])

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
        self.assertEqual(why_not(BASE, "OILX 1", "Ferris Junction", None, "THRU")["first_failure"]["gate"], "D10")
        self.assertEqual(why_not(BASE, "OILX 2", "Dunmere", None, "THRU")["first_failure"]["gate"], "D11")

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
        self.assertEqual(why_not(BASE, "WSTX 1", "Carrow", None, "EAST FREIGHT")["first_failure"]["gate"], "C9")
        self.assertIsNone(why_not(BASE, "WSTX 1", "Carrow", None, "HOP OUT")["first_failure"])

    @JMRI
    def test_R15_experiment_both_directions(self):
        copy = variant("r15_both", [{"action": "update_track", "track": "Linden Westside", "location": "Linden",
                                     "directions": "East/West"}])
        self.assertNotEqual(why_not(copy, "WSTX 1", "Carrow", None, "EAST FREIGHT")["first_failure"]["gate"], "C9")
        session = run_chain(copy, _fresh(TMP / "r15_run"), 1)[0]
        self.assertIn("WSTX1 > East Staging / Hop", session["cars"]["EAST FREIGHT"])

    @JMRI
    def test_R18_first_half_descriptive_interchange(self):
        """needs-integration: TURN's tracks are batch A's. Here: EAST FREIGHT sets the car out; a stand-in TURN pulls it."""
        for chain in SESSIONS:
            self.assertIn("CNXX1 > Linden / Northern Connection", chain[0]["cars"]["EAST FREIGHT"])
        stand_in = []
        for name in ("Turn A", "Turn B"):
            stand_in += [{"action": "add_track", "location": "West Staging", "name": name, "type": "Staging",
                          "length": 400},
                         {"action": "update_track", "track": name, "location": "West Staging",
                          "pickup": {"option": "trains", "names": ["TURN"]},
                          "drop": {"option": "trains", "names": ["TURN"]}, "ignore_used_percent": 100}]
        stand_in += [{"action": "add_track", "location": "Linden", "name": "Standin Dock", "type": "Spur",
                      "length": 100, "types": ["Boxcar"], "roads": {"option": "Include", "names": ["STND"]}},
                     {"action": "add_car", "road": "STND", "number": "1", "type": "Boxcar", "length": 40,
                      "location": "West Staging", "track": "Turn A"},
                     {"action": "add_car", "road": "STND", "number": "2", "type": "Boxcar", "length": 40,
                      "location": "West Staging", "track": "Turn B"}]
        copy = variant("r18_standin", stand_in)
        chain = run_chain(copy, _fresh(TMP / "r18_run"), 2)
        pulled = [c for c in chain[1]["cars"]["TURN"] if c.startswith("CNXX1")]
        self.assertEqual(len(pulled), 1)
        self.assertTrue(pulled[0].split(" > ")[1].startswith("West Staging / Turn"))

    @JMRI
    def test_R03_pipe_yard_half(self):
        """needs-integration: Oakhaven Foundry and Carrow Transfer are batch C's. A stand-in foundry at Carrow ships Pipe."""
        copy = variant("r03_standin", [
            {"action": "add_industry", "location": "Carrow", "name": "Standin Foundry", "length": 150,
             "lines": [{"type": "Gondola", "receive": "E", "ship": "Pipe", "destination": "Linden",
                        "track": "Linden Pipe Yard"}]},
            {"action": "add_car", "road": "JFN", "number": "5301", "type": "Gondola", "length": 40,
             "location": "Carrow", "track": "Carrow Yard"}])
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_jmri.deliver_car(copy, "JFN 5301", "Carrow", "Standin Foundry")
        session = run_chain(copy, _fresh(TMP / "r03_run"), 1)[0]
        self.assertIn("JFN5301 > Linden / Linden Pipe Yard", session["cars"]["EAST FREIGHT"])

    @JMRI
    def test_U04_local_move_within_sawyer(self):
        for chain in SESSIONS:
            self.assertIn("JFN401 > Sawyer / Sawyer Pasta Plant", chain[0]["cars"]["SAWYER SWITCHER"])
        out = why_not(BASE, "JFN 401", "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER")
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
            text = chain[0]["manifests"]["train (VALLEY FLYER).txt"]
            order = [int(line.split("FLYX")[1].split()[0]) for line in text.splitlines() if "Pick up FLYX" in line]
            self.assertEqual(order, [1, 2, 3, 4, 5])
            self.assertEqual(sorted(chain[0]["cars"]["VALLEY FLYER"]),
                             [f"FLYX{n} > Northwood / Northwood Station" for n in range(1, 6)])

    @JMRI
    def test_U18_experiment_negative_blocking_leads(self):
        copy = TMP / "u18_lead"
        shutil.copytree(BASE, copy)
        with mock.patch.object(ops_store, "running_jmri", return_value=[]):
            ops_store.quick(copy, [{"action": "update_car", "car": "FLYX 5", "blocking": -9}])
        run = _fresh(TMP / "u18_run")
        run_chain(copy, run, 1)
        text = (run / "s1" / "manifests" / "train (VALLEY FLYER).txt").read_text(encoding="utf-8")
        order = [int(line.split("FLYX")[1].split()[0]) for line in text.splitlines() if "Pick up FLYX" in line]
        self.assertEqual(order[0], 5)


if __name__ == "__main__":
    unittest.main()
