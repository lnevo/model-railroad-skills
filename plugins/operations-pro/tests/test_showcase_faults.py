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
