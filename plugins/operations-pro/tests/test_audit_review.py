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

    def test_a_b_unit_line_is_read(self):
        """TBE:342 prints BuildEngineBunit when no single locomotive will do (bundle line 895)."""
        report = parsed("5- Locomotive (JFN 5) at (Carrow, Carrow Yard) is a B unit")
        self.assertEqual(report["unparsed"], [])
        self.assertEqual(report["engines"]["available"], ["Locomotive (JFN 5) at (Carrow, Carrow Yard) is a B unit"])

    def test_a_train_leaving_the_terminal_track_is_a_terminal_note(self):
        """TBB:2074 prints this from checkTerminateStagingTrack, about a train still on the arrival track."""
        report = parsed("1- Train terminates into staging at (East Staging), there are 2 tracks",
                        "5- Train on staging track (East Stage 1) is scheduled to depart")
        self.assertEqual([r["key"] for r in report["staging"]["departure"]], [])
        self.assertIn("buildStagingTrackDepart", [r["key"] for r in report["staging"]["terminal"]])


FILES = {"locations": "OperationsLocationRoster.xml", "cars": "OperationsCarRoster.xml",
         "engines": "OperationsEngineRoster.xml", "trains": "OperationsTrainRoster.xml",
         "routes": "OperationsRouteRoster.xml"}


class Edits:
    """The showcase's XML files, edited by hand, as an owner or an old JMRI could leave them."""

    def __init__(self, folder: Path):
        self.folder, self.trees = folder, {}

    def root(self, name: str) -> ET.Element:
        if name not in self.trees:
            self.trees[name] = ET.parse(self.folder / FILES[name])
        return self.trees[name].getroot()

    def track(self, track_id: str) -> ET.Element:
        return self.root("locations").find(f".//track[@id='{track_id}']")

    def location(self, location_id: str) -> ET.Element:
        return self.root("locations").find(f".//location[@id='{location_id}']")

    def train(self, name: str) -> ET.Element:
        return self.root("trains").find(f".//train[@name='{name}']")

    def car(self, car_id: str) -> ET.Element:
        return self.root("cars").find(f".//car[@id='{car_id}']")

    def add_car(self, base: str, car_id: str, **attributes) -> ET.Element:
        cars = self.root("cars").find("cars")
        car = deepcopy.deepcopy(self.car(base))
        car.attrib.update(id=car_id, roadNumber=car_id[-3:], comment="", **attributes)
        for name in ("destinationId", "secDestinationId", "finalDestinationId", "finalDestTrackId"):
            car.attrib.pop(name, None)
        cars.append(car)
        return car

    @staticmethod
    def drop_type(element: ET.Element, kind: str) -> None:
        types = element.find("types")
        for entry in [e for e in types if e.get("name") == kind]:
            types.remove(entry)

    def add_schedule(self, schedule_id: str, track_id: str, lines: list[tuple[str, str, str]], **line_attrs) -> None:
        schedule = ET.SubElement(self.root("locations").find("schedules"), "schedule",
                                 {"id": schedule_id, "name": "Review " + schedule_id})
        for n, (kind, receive, ship) in enumerate(lines, 1):
            ET.SubElement(schedule, "item", {
                "id": f"{schedule_id}c{n}", "sequenceId": str(n), "type": kind, "road": "", "load": receive,
                "ship": ship, "count": "1", "wait": "0", "random": "", "hits": "0", **line_attrs})
        self.track(track_id).attrib.update(schedule="Review " + schedule_id, scheduleId=schedule_id, scheduleMode="1",
                                           itemId=f"{schedule_id}c1", itemCount="1", length="2000")

    def save(self) -> None:
        for name, tree in self.trees.items():
            tree.write(self.folder / FILES[name], encoding="UTF-8", xml_declaration=True)


class AuditCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="audit-review-")
        cls.addClassCleanup(cls.tmp.cleanup)
        patch = mock.patch.object(ops_store, "running_jmri", lambda *a, **k: [])
        patch.start()
        cls.addClassCleanup(patch.stop)
        cls.count = 0

    def edits(self) -> Edits:
        type(self).count += 1
        dest = Path(self.tmp.name) / f"copy{self.count}"
        shutil.copytree(SHOWCASE, dest, ignore=shutil.ignore_patterns("backups", "buildstatus"))
        return Edits(dest)

    @staticmethod
    def findings(edits: Edits, rule: str) -> list[dict]:
        edits.save()
        return [f for f in Gates(ops_data.load(edits.folder, True)).audit()["findings"] if f["rule"] == rule]


class BuiltTrains(AuditCase):
    def test_a_built_train_is_reset_first_so_its_own_cars_do_not_block_it(self):
        """Train.build resets the train before building (Train:3197), so a rebuild of CUSTOM succeeded."""
        edits = self.edits()
        train = edits.train("CUSTOM")
        train.set("built", "true")
        for car in edits.root("cars").iter("car"):
            if car.get("secLocationId") == "1s1":
                car.attrib.update(trainId=train.get("id"), routeLocationId="1r1")
        self.assertEqual([f for f in self.findings(edits, "staging-departure-blocked") if f["subject"] == "CUSTOM"], [])


if __name__ == "__main__":
    unittest.main()
