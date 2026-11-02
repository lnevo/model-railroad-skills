"""Showcase batch D: the Ferris Junction, Pell Creek and Northwood cases, proved in real headless JMRI 5.16.

Cases: R02 (two trains through an interchange), R04 (the second and third hops of three), R06 (Destinations filter
as a gate), R07 (pick ups by route), R08 (Routed interchange), R10 (overflow handled by a pool), R16 (hyphen
location pair), U21 (home division).

The railroad is replayed from build/00_skeleton.json and build/40_d.json on a copy of servers/blank. R04's first hop
(Hollis Coil Mill, Carrow Relay, LOCAL-H with a caboose) is batch C's, and the staging terminal of EAST FREIGHT (the
Hop) is batch E's, so the copy gets temporary stand-ins. Stage 4 replaces them with the real objects and keeps the
assertions.
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_gates import Gates  # noqa: E402

SHOWCASE = ROOT / "examples" / "showcase"
CHAINS = 3
SESSIONS_PER_CHAIN = 3

# Stand-ins for other batches' objects, on the scratch copy only (never shipped by batch D).
STANDIN = [{"plan": [
    {"action": "add_track", "location": "East Staging", "name": "Hop", "type": "Staging", "length": 400,
     "pickup": {"option": "trains", "names": ["HOP OUT"]}, "drop": {"option": "trains", "names": ["EAST FREIGHT"]},
     "only_final_destination": True, "ignore_used_percent": 100},
    {"action": "add_track", "location": "Hollis Mill", "name": "Hollis Coil Mill", "type": "Spur", "length": 150,
     "types": ["Coilcar"]},
    {"action": "add_schedule", "name": "Coil Mill Loads",
     "lines": [{"type": "Coilcar", "receive": "E", "ship": "Coil", "destination": "Northwood",
                "track": "Northwood Steel"}]},
    {"action": "update_track", "track": "Hollis Coil Mill", "location": "Hollis Mill", "schedule": "Coil Mill Loads",
     "schedule_mode": "match"},
    {"action": "add_track", "location": "Carrow", "name": "Carrow Relay", "type": "Yard", "length": 300,
     "types": ["Coilcar"], "loads": {"option": "Include", "names": ["Coil"]}},
    {"action": "add_car", "road": "JFN", "number": "1301", "type": "Caboose", "length": 40, "location": "Carrow",
     "track": "Carrow Yard", "caboose": True},
    {"action": "add_car", "road": "JFN", "number": "5401", "type": "Coilcar", "length": 50, "location": "Carrow",
     "track": "Carrow Yard"}], "accept_new_errors": True},
    {"deliver": {"car": "JFN 5401", "location": "Hollis Mill", "track": "Hollis Coil Mill"}}]

_state: dict = {}


def _builder():
    spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _steps(name: str) -> list:
    return json.loads((SHOWCASE / "build" / name).read_text(encoding="utf-8"))


def make_railroad(dest: Path, standins: bool = True) -> None:
    builder = _builder()
    shutil.copytree(ROOT / "servers" / "blank", dest, dirs_exist_ok=True)
    plan = _steps("00_skeleton.json") + _steps("40_d.json") + (STANDIN if standins else [])
    for index, step in enumerate(plan, 1):
        builder.run_step(dest, step, f"step {index}")


def _chain(source: Path, root: Path, name: str) -> list:
    """Three consecutive sessions, each started from the files the last one saved."""
    current = root / name / "current"
    shutil.copytree(source, current)
    sessions = []
    for number in range(1, SESSIONS_PER_CHAIN + 1):
        keep = root / name / f"s{number}"
        keep.mkdir(parents=True)
        result = ops_jmri.run_worker(current, {"build": True, "terminate": True, "save": True}, keep)
        for filename in ops_store.FILES:
            if (keep / filename).is_file():
                shutil.copy2(keep / filename, current / filename)
        sessions.append({"result": result, "keep": keep, "rr": ops_data.load(keep)})
    return sessions


def setUpModule():
    if not ops_jmri.jmri_home():
        return
    temp = tempfile.TemporaryDirectory()
    _state["temp"] = temp
    root = Path(temp.name)
    env = mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(root / "plans")})
    env.start()
    _state["env"] = env
    stopped = mock.patch.object(ops_store, "running_jmri", return_value=[])
    stopped.start()
    _state["stopped"] = stopped
    full = root / "full"
    make_railroad(full)
    _state["full"] = full
    shipped = root / "shipped"
    make_railroad(shipped, standins=False)
    _state["shipped"] = shipped
    with ThreadPoolExecutor(CHAINS) as pool:
        names = [f"chain{n}" for n in range(1, CHAINS + 1)]
        _state["chains"] = list(pool.map(lambda n: _chain(full, root / "runs", n), names))


def tearDownModule():
    for key in ("stopped", "env"):
        if key in _state:
            _state[key].stop()
    if "temp" in _state:
        _state["temp"].cleanup()


def where(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    place = rr.locations[car.location_id].name
    track = rr.tracks[car.track_id].name if car.track_id in rr.tracks else ""
    return f"{place} / {track}"


def final_dest(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    if car.fd_track_id not in rr.tracks:
        return ""
    return f"{rr.locations[car.fd_id].name} / {rr.tracks[car.fd_track_id].name}"


def why(folder, car, destination, track=None, train=None):
    return Gates(ops_data.load(folder)).why_not(car, destination, track, train, False)


def gate(result, name: str) -> dict:
    return next(g for g in result["gates"] if g["gate"] == name)


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class ShowcaseBatchD(unittest.TestCase):
    def sessions(self, number: int):
        return [chain[number - 1] for chain in _state["chains"]]

    def carried(self, session, train: str) -> list:
        row = session["result"]["builds"][train]
        self.assertTrue(row["built"], f"{train}: {row['message']}")
        return row["cars"]

    def test_batch_audit_has_no_error_or_warning(self):
        audit = Gates(ops_data.load(_state["shipped"])).audit()
        self.assertEqual(audit["counts"]["error"], 0)
        self.assertEqual(audit["counts"]["warning"], 0)
        # Intended: every interchange that names its trains leaves the other calling trains off its lists.
        self.assertEqual({f["rule"] for f in audit["findings"]}, {"train-not-on-list"})
        self.assertEqual({f["severity"] for f in audit["findings"]}, {"info"})

    def test_sessions_log_no_errors(self):
        for number in range(1, SESSIONS_PER_CHAIN + 1):
            for session in self.sessions(number):
                self.assertEqual(session["result"]["log_errors"], [])

    # R02: two trains through an interchange.
    def test_r02_two_trains_through_interchange(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("JFN5201 > Ferris Junction / Ferris Exchange", self.carried(s1, "EAST FREIGHT"))
            self.assertEqual(where(s1["rr"], "JFN5201"), "Ferris Junction / Ferris Exchange")
            self.assertEqual(s1["rr"].cars["JFN5201"].load, "Produce")
            self.assertEqual(final_dest(s1["rr"], "JFN5201"), "Northwood / Cold Store")
            self.assertIn("JFN5201 > Northwood / Cold Store", self.carried(s2, "NORTH JOB"))
            self.assertEqual(where(s2["rr"], "JFN5201"), "Northwood / Cold Store")
        route = why(_state["shipped"], "JFN 5201", "Northwood", "Cold Store", "EAST FREIGHT")["router"]["route"]
        self.assertEqual(route["how"], "two trains through interchange Ferris Exchange")
        self.assertEqual([p["train"] for p in route["path"]], ["EAST FREIGHT", "NORTH JOB"])

    # R04, second and third hops. The first hop (LOCAL-H to Carrow Relay) is batch C's: needs-integration.
    def test_r04_three_trains_second_and_third_hops(self):
        for chain in _state["chains"]:
            s1, s2, s3 = (chain[i] for i in range(3))
            self.assertEqual(where(s1["rr"], "JFN5401"), "Carrow / Carrow Relay")  # stand-in first hop
            self.assertIn("JFN5401 > Ferris Junction / Ferris Relay", self.carried(s2, "EAST FREIGHT"))
            self.assertEqual(where(s2["rr"], "JFN5401"), "Ferris Junction / Ferris Relay")
            self.assertIn("JFN5401 > Northwood / Northwood Steel", self.carried(s3, "NORTH JOB"))
            self.assertEqual(where(s3["rr"], "JFN5401"), "Northwood / Northwood Steel")
        route = why(_state["full"], "JFN 5401", "Northwood", "Northwood Steel", "EAST FREIGHT")["router"]["route"]
        self.assertTrue(route["how"].startswith("3 trains"), route["how"])
        self.assertEqual([p["train"] for p in route["path"]], ["LOCAL-H", "EAST FREIGHT", "NORTH JOB"])

    # R06: the Destinations filter on Ferris Gate admits Pell Creek only, so the car cannot be sent to Northwood.
    def test_r06_destinations_filter_gate(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("GTEX1 > Pell Creek-(yard) / Pell Tank Track", self.carried(s1, "NORTH JOB"))
            self.assertEqual(where(s1["rr"], "GTEX1"), "Pell Creek-(yard) / Pell Tank Track")
            self.assertEqual(where(s2["rr"], "GTEX1"), "Ferris Junction / Ferris Gate")  # the set outs admit it
            report = s1["result"]["builds"]["NORTH JOB"]["report_text"]
            self.assertIn("Destination (Northwood) not serviced by departure track (Ferris Gate)", report)
        refused = why(_state["shipped"], "GTEX 1", "Northwood", "Gate Yard", "NORTH JOB")
        self.assertEqual(gate(refused, "D6")["status"], "fail")
        self.assertFalse(refused["can_move"])
        allowed = why(_state["shipped"], "GTEX 1", "Pell Creek-(yard)", "Pell Tank Track", "NORTH JOB")
        self.assertEqual(gate(allowed, "D6")["status"], "pass")

    # R07: pick ups named by route, so the train that set the car out can pull it back.
    def test_r07_pick_up_by_route(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertIn("XFRX1 > Ferris Junction / Ferris Transfer", self.carried(s1, "NORTH JOB"))
            self.assertEqual(where(s1["rr"], "XFRX1"), "Ferris Junction / Ferris Transfer")
            self.assertIn("XFRX1 > Northwood / Northwood Shed", self.carried(s2, "NORTH JOB"))
            self.assertEqual(where(s2["rr"], "XFRX1"), "Northwood / Northwood Shed")
        after = why(self.sessions(1)[0]["keep"], "XFRX 1", "Northwood", "Northwood Shed", "NORTH JOB")
        self.assertEqual(gate(after, "B6")["status"], "pass")
        self.assertTrue(after["can_move"])

    # R08: Routed on an interchange takes the routed car and refuses the plain empty.
    def test_r08_routed_interchange(self):
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            self.assertEqual(where(s1["rr"], "JFN5801"), "Ferris Junction / Ferris Routed")
            self.assertEqual(where(s1["rr"], "BOXX1"), "Ferris Junction / Ferris Yard")
            self.assertEqual(where(s2["rr"], "JFN5801"), "Northwood / Routed Siding")
            self.assertEqual(s2["rr"].cars["JFN5801"].load, "E")
            self.assertEqual(where(s2["rr"], "BOXX1"), "Ferris Junction / Ferris Yard")
        plain = why(_state["shipped"], "BOXX 1", "Ferris Junction", "Ferris Routed", "EAST FREIGHT")
        self.assertEqual(gate(plain, "E7")["status"], "fail")
        routed = why(_state["shipped"], "JFN 5801", "Ferris Junction", "Ferris Routed", "EAST FREIGHT")
        self.assertEqual(gate(routed, "E7")["status"], "pass")

    # R10: a pool of two 120 ft interchanges takes five 44 ft cars (220 ft); the cars then go on together.
    def test_r10_pool_takes_the_overflow(self):
        cars = [f"OAKX{n}" for n in range(1, 6)]
        for chain in _state["chains"]:
            s1, s2 = chain[0], chain[1]
            placed = [where(s1["rr"], c) for c in cars]
            self.assertTrue(all(p in ("Ferris Junction / Ferris Pool 1", "Ferris Junction / Ferris Pool 2")
                                for p in placed), placed)
            counts = {p: placed.count(p) for p in set(placed)}
            self.assertGreater(max(counts.values()) * 44, 120, counts)  # one track holds more than its own length
            for car in cars:
                self.assertEqual(where(s2["rr"], car), "Northwood / Grain Elevator")
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
                self.assertEqual(where(s1["rr"], car), "Pell Creek-(industries) / Pell Brickworks")
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
            self.assertEqual(final_dest(s1["rr"], "NWRX1"), "Northwood / Northwood Yard")
            self.assertEqual(final_dest(s1["rr"], "NWRX2"), "Northwood / Northwood Yard")
            self.assertEqual(final_dest(s1["rr"], "NWRX3"), "Northwood / Malt House")
            self.assertEqual(where(s2["rr"], "NWRX1"), "Northwood / Northwood Yard")
            self.assertEqual(where(s2["rr"], "NWRX2"), "Northwood / Northwood Yard")
            self.assertEqual(where(s2["rr"], "NWRX3"), "Northwood / Malt House")
            self.assertEqual(s2["rr"].cars["NWRX3"].load, "E")
        route = why(_state["shipped"], "NWRX 1", "Northwood", "Northwood Yard", "EAST FREIGHT")["router"]["route"]
        self.assertEqual(route["how"], "two trains through yard Ferris Yard")


if __name__ == "__main__":
    unittest.main()
