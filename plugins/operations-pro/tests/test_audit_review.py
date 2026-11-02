"""Faults a review of the audit rules and the build report reader found, each held without starting JMRI.

Every audit scenario here was run through a real JMRI 5.16 build, and the source reference sits beside the
test: a copy of the showcase, edited in its XML the way the owner of a railroad could leave it.
"""
import copy as deepcopy
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = ROOT / "examples" / "showcase" / "operations"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_report  # noqa: E402
import ops_store  # noqa: E402
from ops_gates import Gates  # noqa: E402


def parsed(*lines):
    """Walk a synthetic snippet of report lines, written as JMRI 5.16 prints them."""
    return ops_report.parse("".join(line + "\n" for line in lines))


class ReportReader(unittest.TestCase):
    def test_sequential_mode_refusal_is_e10(self):
        """Track.java:2153 prints getScheduleModeName, which is "Sequential" with a capital (Track:564-568)."""
        status = ("schedule (Rev) in Sequential mode, car (A 1) type(Boxcar) schedule() road(A) load(E) "
                  "does not match: type(Boxcar) schedule() road() receive(Coal)")
        self.assertEqual(ops_report.status_gate(status)[0], "E10")

    FRED_ROAD = ("1- Train (LOCAL-B) requires car with FRED, road (UP) departing (Carrow) destination (Carrow)",
                 "5- Car (BOXX 999) has a FRED, road (BOXX) at location (Carrow, Carrow Yard)",
                 "7- Exclude car (BOXX 999) at (Carrow, Carrow Yard) type (Boxcar)  (F) train doesn't service road (BOXX)",
                 "1- Train (LOCAL-B) requires FRED, can't meet requirements at departure (Carrow) and/or "
                 "termination (Carrow)",
                 "1- Build failed for train (LOCAL-B)")

    def test_fred_wrong_road_is_the_required_road_not_the_road_option(self):
        """TBC:270 reuses buildExcludeCarWrongRoad for a car that is not the road the train asks for; TBB:908,
        the same text, is the Road option. Only the first follows buildCarHasFRED, and there the fix is the
        required road, not B9."""
        report = parsed(*self.FRED_ROAD)
        self.assertEqual(report["excluded_cars"][0]["gate"], "B17")
        summary = " ".join(ops_report.explain("\n".join(self.FRED_ROAD) + "\n")["summary"])
        self.assertNotIn("B9", summary)
        self.assertIn("road UP", summary)

    def test_a_road_option_refusal_stays_b9(self):
        report = parsed("7- Exclude car (BOXX 999) at (Carrow, Carrow Yard) type (Boxcar)  (F) train doesn't "
                        "service road (BOXX)")
        self.assertEqual(report["excluded_cars"][0]["gate"], "B9")

    def test_a_normal_mode_retry_is_not_a_failure(self):
        """TB:512 announces a second attempt; only a later error or buildFailedMsg fails the build."""
        report = parsed("1- *** Build Failed using Aggressive Mode try again using Normal Mode ***",
                        "1- Train (CUSTOM) built with 3 cars")
        self.assertEqual(report["outcome"]["failure"], [])


if __name__ == "__main__":
    unittest.main()
