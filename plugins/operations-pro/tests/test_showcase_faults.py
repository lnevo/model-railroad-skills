"""Faults the showcase build found in the tools, each held on a scratch copy of the showcase.

The real JMRI behaviour each test states was checked against JMRI 5.16 source and a real build; the source
reference sits beside the code it holds. No test here starts JMRI, so the file runs anywhere.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "showcase" / "operations"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_store  # noqa: E402
from ops_gates import Gates  # noqa: E402


class Faults(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="showcase-faults-")
        cls.addClassCleanup(cls.tmp.cleanup)
        for patch in (mock.patch.object(ops_store, "running_jmri", lambda *a, **k: []),
                      mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(Path(cls.tmp.name) / "plans")})):
            patch.start()
            cls.addClassCleanup(patch.stop)
        cls.count = 0

    def copy(self, actions=()) -> Path:
        type(self).count += 1
        dest = Path(self.tmp.name) / f"copy{self.count}"
        shutil.copytree(SHOWCASE, dest, ignore=shutil.ignore_patterns("backups", "buildstatus"))
        if actions:
            ops_store.apply(ops_store.plan(dest, list(actions))["plan_id"], True)
        return dest

    def why_not(self, folder, car, destination, track=None, train=None):
        return Gates(ops_data.load(folder)).why_not(car, destination, track, train, False)

    @staticmethod
    def gate(out, code):
        return next(g for g in out["gates"] if g["gate"] == code)


class RouterGates(Faults):
    def test_local_moves_off_does_not_stop_a_custom_load_on_a_switcher(self):
        """U04: the router refuses the local move, the car falls to the train's own route (TBC:578-592)."""
        copy = self.copy([{"action": "update_stop", "route": "SAWYER SWITCHER", "stop": 1, "local_moves": False}])
        out = self.why_not(copy, "JFN 401", "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER")
        self.assertTrue(out["can_move"])
        self.assertIsNone(out["first_failure"])
        self.assertEqual(self.gate(out, "G3")["status"], "pass")
        self.assertIn("own route", self.gate(out, "G3")["reason"])

    def test_a_final_destination_still_needs_the_router(self):
        """The fall through is for a custom load with no final destination: a car with one stays held."""
        copy = self.copy([{"action": "update_stop", "route": "SAWYER SWITCHER", "stop": 1, "local_moves": False}])
        rr = ops_data.load(copy)
        car = rr.find_car("JFN 401")
        car.fd_id, car.fd_track_id = rr.find_location("Sawyer").id, rr.find_track("Sawyer Pasta Plant").id
        out = Gates(rr).why_not(car, "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER", False)
        self.assertFalse(out["can_move"])


class StagingReturn(Faults):
    def test_a_car_left_in_staging_is_said_to_stay(self):
        """U22: JMRI logs Leave car in staging and makes a local move, Turn A to Turn B (TBC:1904-1914)."""
        out = self.why_not(self.copy([{"action": "update_car", "car": "HZMX 9", "passenger": False}]),
                           "HZMX 9", "West Staging", "Turn B", "TURN")
        self.assertTrue(out["can_move"])
        self.assertTrue(any("does not ride" in note for note in out["notes"]), out["notes"])

    def test_a_passenger_car_rides(self):
        out = self.why_not(SHOWCASE, "HZMX 9", "West Staging", "Turn B", "TURN")
        self.assertTrue(out["can_move"])
        self.assertEqual(out["notes"], [])


class Chains(Faults):
    def test_a_car_the_router_can_chain_has_no_first_failure(self):
        for car, place, track, train in (("JFN 5401", "Northwood", "Northwood Steel", "LOCAL-H"),
                                         ("JFN 5501", "Linden", "Linden Pier", None)):
            with self.subTest(car=car):
                out = self.why_not(SHOWCASE, car, place, track, train)
                self.assertTrue(out["can_move"])
                self.assertFalse(out["direct"])
                self.assertIsNone(out["first_failure"])
                self.assertIn(out["direct_failure"]["gate"], ("D1", "D14"))

    def test_a_failure_stays_first_failure_when_the_car_cannot_move(self):
        out = self.why_not(self.copy([{"action": "update_track", "location": "Ferris Junction", "track": "Ferris Relay",
                                       "destinations": {"option": "Include", "locations": ["Linden"]}}]),
                           "JFN 5401", "Northwood", "Northwood Steel", "LOCAL-H")
        self.assertFalse(out["can_move"])
        self.assertIsNotNone(out["first_failure"])


class ServiceAll(Faults):
    def test_the_setting_changes_the_answer(self):
        """R14: with the stop short of moves, off holds the car (R:282-286) and on sends it part way (R:307-315)."""
        notes = {}
        for flag in (False, True):
            copy = self.copy([{"action": "update_stop", "route": "EAST FREIGHT", "stop": 3, "max_moves": 1},
                              {"action": "update_train", "train": "EAST FREIGHT", "service_all": flag}])
            notes[flag] = self.why_not(copy, "JFN 6402", "Linden", "Linden Glazier", "EAST FREIGHT")["notes"]
        self.assertTrue(any("stays where it is" in n for n in notes[False]), notes[False])
        self.assertTrue(any("part way" in n for n in notes[True]), notes[True])

    def test_no_note_for_a_car_without_a_final_destination(self):
        out = self.why_not(SHOWCASE, "HZMX 9", "West Staging", "Turn B", "TURN")
        self.assertFalse([n for n in out["notes"] if "service all" in n.lower()])


class SameBuild(Faults):
    def test_room_taken_by_cars_bound_for_the_same_track_is_open(self):
        """R09: four 44 foot cars aim at a 100 foot spur, so room depends on who the build takes first."""
        out = self.why_not(SHOWCASE, "JFN 5901", "Oakhaven", "Oakhaven Plant", "LOCAL-H")
        gate = self.gate(out, "E9")
        self.assertEqual(gate["status"], "not_checked")
        self.assertIn("3 other cars", gate["reason"])
        self.assertTrue(out["can_move"])

    def test_room_is_a_pass_when_nothing_else_targets_the_track(self):
        out = self.why_not(SHOWCASE, "JFN 401", "Sawyer", "Sawyer Pasta Plant", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "E9")["status"], "pass")


class LocoChange(Faults):
    def test_no_room_at_the_change_stop_leaves_a8_open(self):
        """U13 b: the locomotive leaving staging fits no track at the change stop, so West Mode cannot depart."""
        copy = self.copy([{"action": "update_track", "location": "Brae", "track": "Brae Engine Track",
                           "ignore_used_percent": 0}])
        gate = self.gate(self.why_not(copy, "MODX 1", "East Staging", None, "MODE"), "A8")
        self.assertEqual(gate["status"], "not_checked")
        self.assertIn("Brae", gate["reason"])

    def test_room_at_the_change_stop_passes(self):
        self.assertEqual(self.gate(self.why_not(SHOWCASE, "MODX 1", "East Staging", None, "MODE"), "A8")["status"],
                         "pass")


class AuditSample(Faults):
    def test_a_road_list_does_not_raise_a_false_warning(self):
        """F1: the sample car was the first of the type in the file, so the answer followed file order."""
        rules = [(f["rule"], f["subject"]) for f in Gates(ops_data.load(SHOWCASE)).audit()["findings"]]
        for subject in ("Fiddle North", "Fiddle South", "Grain Co Loads"):
            self.assertNotIn(("single-destination-schedule", subject), rules)

    def test_a_road_nobody_can_reach_still_warns(self):
        rr = ops_data.load(SHOWCASE)
        gates = Gates(rr)
        with mock.patch.object(gates, "route_path", return_value=None):
            rules = [(f["rule"], f["subject"]) for f in gates.audit()["findings"]]
        self.assertIn(("single-destination-schedule", "Grain Co Loads"), rules)


class StagingCause(Faults):
    def test_an_occupied_terminal_track_is_named(self):
        """F6: the closest refusal is the occupied terminal track, not the first spur on the route."""
        copy = self.copy()
        plan = ops_store.plan(copy, [{"action": "update_track", "location": "East Staging", "track": "East Swap",
                                      "ignore_used_percent": 0}])
        message = next(f["message"] for f in plan["new_findings"] if f["rule"] == "staging-departure-blocked")
        self.assertIn("East Swap", message)
        self.assertIn("D12", message)
        self.assertNotIn("Carrow Packing", message)
