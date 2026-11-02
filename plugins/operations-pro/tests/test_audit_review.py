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


if __name__ == "__main__":
    unittest.main()
