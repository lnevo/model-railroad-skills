"""Gate faults a review against the JMRI 5.16 source found, each held on a scratch copy of the showcase.

Every scenario here was also built in real JMRI 5.16 and the test states what that build did; the source
reference sits beside it. No test here starts JMRI, so the file runs anywhere.
"""
import copy as deepcopy
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

from test_showcase_faults import Faults  # noqa: E402

FILES = {"locations": "OperationsLocationRoster.xml", "cars": "OperationsCarRoster.xml",
         "engines": "OperationsEngineRoster.xml", "routes": "OperationsRouteRoster.xml",
         "trains": "OperationsTrainRoster.xml", "setup": "Operations.xml"}


class Xml:
    """The showcase files of one copy, open for the small edits a scenario needs."""

    def __init__(self, folder: Path):
        self.folder = folder
        self.trees = {key: ET.parse(folder / name) for key, name in FILES.items()}

    def root(self, key):
        return self.trees[key].getroot()

    def car(self, car_id):
        return self.root("cars").find(f"./cars/car[@id='{car_id}']")

    def track(self, track_id):
        return self.root("locations").find(f".//track[@id='{track_id}']")

    def stop(self, stop_id):
        return self.root("routes").find(f".//location[@id='{stop_id}']")

    def train(self, train_id):
        return self.root("trains").find(f"./trains/train[@id='{train_id}']")

    def engine(self, engine_id):
        return self.root("engines").find(f"./engines/engine[@id='{engine_id}']")

    def options(self, **values):
        self.root("setup").find(".//buildOptions").attrib.update(values)

    def add_car(self, car_id, like, **values):
        new = deepcopy.deepcopy(self.car(like))
        new.set("id", car_id)
        new.attrib.update(values)
        self.root("cars").find("./cars").append(new)
        return new

    def save(self):
        for key, name in FILES.items():
            self.trees[key].write(self.folder / name, encoding="UTF-8", xml_declaration=True)


class Review(Faults):
    def scenario(self, change) -> Path:
        folder = self.copy()
        xml = Xml(folder)
        change(xml)
        xml.save()
        return folder


class PickUps(Review):
    def test_pick_ups_off_holds_a_car_the_what_if_calls_local(self):
        """Real build: Pick ups not allowed for SWYX 1, 0 cars moved. The car has no destination, so
        Car.isLocalMove is false whatever is asked (TBC:498-500, Car:619-622)."""
        folder = self.scenario(lambda x: x.stop("11r1").set("pickups", "no"))
        out = self.why_not(folder, "SWYX 1", "Sawyer", None, "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "C6")["status"], "fail")
        self.assertFalse(out["can_move"])

    def test_an_assigned_local_destination_passes(self):
        def change(x):
            x.stop("11r1").set("pickups", "no")
            x.car("SWYX1").attrib.update(destinationId="13", secDestinationId="13s4")
        out = self.why_not(self.scenario(change), "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "C6")["status"], "pass")

    def test_a_final_destination_at_the_stop_passes(self):
        def change(x):
            x.stop("11r1").set("pickups", "no")
            x.car("SWYX1").attrib.update(nextDestId="13", nextDestTrackId="13s4")
        out = self.why_not(self.scenario(change), "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "C6")["status"], "pass")


if __name__ == "__main__":
    unittest.main()
