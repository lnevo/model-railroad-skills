"""Showcase batch C: the Hollis Mill and Oakhaven cases, proved in real headless JMRI 5.16.

Cases: U05 (track move counts), U11 (spur balance), U13 (caboose), U16 (manual build line), U19 (track pool),
U24 (RIP track), R01 (one train), R03 and R04 (first hops), R09 (alternate and forward to yard).

The railroad is replayed from build/00_skeleton.json and build/30_c.json on a copy of servers/blank. R03 and R04
need objects that batches D and E build (the Linden pipe yard, Ferris Relay, Northwood Steel), so the copy gets
temporary stand-ins and then build/55_c.json, the steps that wait for them. Stage 4 replaces the stand-ins with the
real objects and keeps the assertions.
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

# Stand-ins for other batches' objects, on the scratch copy only (never shipped by batch C).
STANDIN = [{"plan": [
    {"action": "add_schedule", "name": "Pipe Yard Receiving",
     "lines": [{"type": "Gondola", "receive": "Pipe", "ship": "E"}]},
    {"action": "add_track", "location": "Linden", "name": "Linden Pipe Yard", "type": "Spur", "length": 200,
     "types": ["Gondola"], "schedule": "Pipe Yard Receiving"},
    {"action": "add_track", "location": "Ferris Junction", "name": "Ferris Relay", "type": "Interchange",
     "length": 300, "types": ["Coilcar"]},
    {"action": "setup_interchange", "track": "Ferris Relay", "location": "Ferris Junction",
     "set_out_by": ["EAST FREIGHT"], "pulled_by": ["NORTH JOB"]},
    {"action": "add_schedule", "name": "Steel Receiving", "lines": [{"type": "Coilcar", "receive": "Coil", "ship": "E"}]},
    {"action": "add_track", "location": "Northwood", "name": "Northwood Steel", "type": "Spur", "length": 150,
     "types": ["Coilcar"], "schedule": "Steel Receiving"}]}]

_state: dict = {}


def _builder():
    spec = importlib.util.spec_from_file_location("showcase_build", SHOWCASE / "build.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _steps(name: str) -> list:
    return json.loads((SHOWCASE / "build" / name).read_text(encoding="utf-8"))


def make_railroad(dest: Path, standins: bool = True) -> None:
    """Skeleton, batch C, then (on request) the stand-ins and batch C's integration steps."""
    builder = _builder()
    shutil.copytree(ROOT / "servers" / "blank", dest, dirs_exist_ok=True)
    plan = _steps("00_skeleton.json") + _steps("30_c.json")
    if standins:
        plan += STANDIN + _steps("55_c.json")
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


def final_track(rr, car_id: str) -> str:
    car = rr.cars[car_id]
    return rr.tracks[car.fd_track_id].name if car.fd_track_id in rr.tracks else ""


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class ShowcaseBatchC(unittest.TestCase):
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
                self.assertEqual(where(session["rr"], f"GNDX{number}"), "Hollis Mill / Hollis Track 2")
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
                     if where(s1, c) == "Hollis Mill / Mill Spur"}
            self.assertEqual(len(first), 2)
            for car in first:
                self.assertEqual(s1.cars[car].load, "Flour")
                self.assertEqual(final_track(s1, car), "Bakery")
            for car in {"MILX1101", "MILX1102", "MILX1103", "MILX1104"} - first:
                self.assertEqual(where(s1, car), "Carrow / Carrow Mill Lead")
            # S2: the first pair reaches the bakery and the second pair takes their places on the mill spur.
            for car in first:
                self.assertEqual(where(s2, car), "Oakhaven / Bakery")
                self.assertEqual(s2.cars[car].load, "E")
            second = {"MILX1101", "MILX1102", "MILX1103", "MILX1104"} - first
            for car in second:
                self.assertEqual(where(s2, car), "Hollis Mill / Mill Spur")
                self.assertEqual(s2.cars[car].load, "Flour")
            # S3: the second pair reaches the bakery and the first pair is back on the lead.
            for car in second:
                self.assertEqual(where(s3, car), "Oakhaven / Bakery")
            for car in first:
                self.assertEqual(where(s3, car), "Carrow / Carrow Mill Lead")

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
                    self.assertEqual(where(rr, car), "Carrow / Carrow Caboose Track")
        manifest = (self.sessions(1)[0]["keep"] / "manifests" / "train (LOCAL-H).txt").read_text()
        self.assertIn("caboose", manifest)
        self.assertEqual(manifest.count("Caboose 40'"), 2)  # one pick up and one set out

    # U16: a manual build line takes the named car first, and the train delivers it.
    def test_u16_manual_build_line(self):
        for session in self.sessions(1):
            row = self.built(session, "LOCAL-H")
            self.assertIn("TEMX1 > Oakhaven / Oakhaven Team", row["cars"])
            self.assertIn("Manual build line id 1m1 was able to assign to train (LOCAL-H) 1 of 1", row["report_text"])
            self.assertEqual(where(session["rr"], "TEMX1"), "Oakhaven / Oakhaven Team")
        lines = ops_data.read_manual_builds(_state["full"])
        self.assertEqual(len(lines), 1)

    # U19: a pool lends length between its tracks, so Pool 1 holds more than its own 100 feet.
    def test_u19_track_pool(self):
        for session in self.sessions(1):
            rr = session["rr"]
            places = [where(rr, f"POOX{n}") for n in range(1901, 1907)]
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
            self.assertEqual(where(rr, "RIPX1"), "Carrow / Carrow RIP")
            self.assertEqual(rr.cars["RIPX1"].load, "L")
        tracks = {t.name: t for t in ops_data.load(_state["full"]).tracks.values()}
        self.assertNotEqual(tracks["Carrow RIP"].load_options, 0)

    # R01: one train direct to a spur; the schedule turns the peas into an empty on arrival.
    def test_r01_one_train_direct(self):
        for session in self.sessions(1):
            rr = session["rr"]
            self.assertEqual(where(rr, "JFN5101"), "Oakhaven / Oakhaven Cannery")
            self.assertEqual(rr.cars["JFN5101"].load, "E")
        why = Gates(ops_data.load(_state["full"])).why_not("JFN5101", "Oakhaven", "Oakhaven Cannery", "LOCAL-H", False)
        self.assertTrue(why["can_move"])
        self.assertEqual(why["router"]["route"]["how"], "single train")

    # R03 (first hop; the second hop needs batch E's Linden pipe yard, here a stand-in): two trains through a yard.
    def test_r03_two_trains_through_a_yard(self):
        for chain in _state["chains"]:
            self.assertEqual(where(chain[0]["rr"], "JFN5301"), "Carrow / Carrow Transfer")
            self.assertEqual(where(chain[1]["rr"], "JFN5301"), "Linden / Linden Pipe Yard")
            self.assertIn("JFN5301 > Linden / Linden Pipe Yard", chain[1]["result"]["builds"]["EAST FREIGHT"]["cars"])
        why = Gates(ops_data.load(_state["full"])).why_not(
            "JFN5301", "Linden", "Linden Pipe Yard", "LOCAL-H", False)
        self.assertEqual(why["router"]["route"]["how"], "two trains through yard Carrow Transfer")

    # R04 (first hop; the later hops need batch D's Ferris Relay and Northwood Steel, here stand-ins).
    def test_r04_chain_of_three_trains(self):
        for chain in _state["chains"]:
            self.assertEqual(where(chain[0]["rr"], "JFN5401"), "Carrow / Carrow Relay")
            self.assertEqual(where(chain[1]["rr"], "JFN5401"), "Ferris Junction / Ferris Relay")
            self.assertEqual(where(chain[2]["rr"], "JFN5401"), "Northwood / Northwood Steel")
        why = Gates(ops_data.load(_state["full"])).why_not(
            "JFN5401", "Northwood", "Northwood Steel", "LOCAL-H", False)
        route = why["router"]["route"]
        self.assertEqual(route["how"], "3 trains")
        self.assertEqual([hop["train"] for hop in route["path"]], ["LOCAL-H", "EAST FREIGHT", "NORTH JOB"])

    # R09: a full spur sends the next car to its alternate, and the one after to a yard at the destination.
    def test_r09_alternate_then_yard(self):
        for chain in _state["chains"]:
            rr = chain[0]["rr"]
            places = sorted(where(rr, f"JFN{n}") for n in range(5901, 5905))
            self.assertEqual(places, ["Oakhaven / Oakhaven Plant"] * 2 + ["Oakhaven / Oakhaven Yard", "Oakhaven / Plant Overflow"])
            report = chain[0]["result"]["builds"]["LOCAL-H"]["report_text"]
            self.assertRegex(report, r"Delivering car \(JFN 59\d\d\) to alternate track \(Plant Overflow\)")
            self.assertRegex(report, r"Sending car \(JFN 59\d\d\) to yard \(Oakhaven, Oakhaven Yard\)")


if __name__ == "__main__":
    unittest.main()
