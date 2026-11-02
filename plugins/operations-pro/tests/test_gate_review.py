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
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_data  # noqa: E402
from ops_gates import Gates  # noqa: E402
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


class AssignedDestination(Review):
    """A car with an assigned destination takes checkCarForDestination, not the default search (TBC:1496-1506)."""

    @staticmethod
    def assigned(x):
        x.car("SWYX1").attrib.update(destinationId="13", secDestinationId="13s4")

    def test_drops_off_does_not_stop_a_local_move(self):
        """Real build: SWYX 1 assigned to the train, Sawyer Team to Sawyer Warehouse, with set outs off."""
        def change(x):
            self.assigned(x)
            x.stop("11r1").set("drops", "no")
        out = self.why_not(self.scenario(change), "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "D1")["status"], "pass")
        self.assertTrue(out["can_move"], out["first_failure"])

    def test_local_moves_off_stops_it(self):
        """Real build: no local moves at location (Sawyer) for car (SWYX 1), though it has no final destination."""
        def change(x):
            self.assigned(x)
            x.stop("11r1").set("localMoves", "no")
        out = self.why_not(self.scenario(change), "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "D5")["status"], "fail")
        self.assertFalse(out["can_move"])

    def test_the_default_search_keeps_its_rules(self):
        """No assigned destination: set outs off stops the car and D5 only looks at a final destination."""
        out = self.why_not(self.scenario(lambda x: x.stop("11r1").set("drops", "no")),
                           "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "D1")["status"], "fail")
        out = self.why_not(self.scenario(lambda x: x.stop("11r1").set("localMoves", "no")),
                           "SWYX 1", "Sawyer", "Sawyer Warehouse", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "D5")["status"], "pass")


class DropDirection(Review):
    def test_terminal_staging_has_no_track_direction_test(self):
        """Real build: JFN 611 delivered to East Mixed with the track West only, the train running East. tryStaging
        calls car.checkDestination and nothing else (TBC:1818-1819, TBB:2588)."""
        def change(x):
            for track in ("2s1", "2s2", "2s3", "2s4"):
                x.track(track).set("dir", "2")
        out = self.why_not(self.scenario(change), "JFN 611", "East Staging", "East Mixed", "MIXED")
        self.assertEqual(self.gate(out, "D14")["status"], "pass")
        self.assertTrue(out["can_move"], out["first_failure"])

    def test_a_switcher_ignores_the_alternate_direction_rule(self):
        """checkDropTrainDirection returns true for a local switcher before the alternate test (TBB:1620-1622)."""
        def change(x):
            x.car("SWYX1").attrib.update(nextDestId="13", nextDestTrackId="13s4")
            x.track("13s4").attrib.update(alternative="13s6", dir="1")
            x.track("13s6").set("dir", "2")
        out = self.why_not(self.scenario(change), "SWYX 1", "Sawyer", "Sawyer Yard 2", "SAWYER SWITCHER")
        self.assertEqual(self.gate(out, "D14")["status"], "pass")

    def test_a_road_train_still_needs_the_alternate_direction_rule(self):
        def change(x):
            x.car("JFN5901").attrib.update(locationId="3", secLocationId="3s1", nextDestId="9", nextDestTrackId="9s6")
            x.track("9s6").set("dir", "2")
            x.track("9s5").set("dir", "1")
        out = self.why_not(self.scenario(change), "JFN 5901", "Oakhaven", "Plant Overflow", "LOCAL-H")
        self.assertEqual(self.gate(out, "D14")["status"], "fail")


def turn_ends_at_carrow(x):
    """TURN out of West Staging with Turn A as it stands, ending at Carrow so no terminal track is in question."""
    stop = x.stop("17r3")
    stop.attrib.update(name="Carrow", locationId="3")
    x.car("HZMX9").attrib.update(locationId="3", secLocationId="3s1")


def pooled(x, order):
    """Turn A and Turn B in one pool, Turn A's cars arrived in 2026 and Turn B's one car in 2020."""
    turn_ends_at_carrow(x)
    for track in ("1s5", "1s6"):
        x.track(track).attrib.update(pool="P", order=order, minLength="0")
    for car in x.root("cars").findall("./cars/car"):
        if car.get("secLocationId") == "1s5":
            car.set("date", "06/01/2026 10:00:00")
    x.add_car("TSTX901", "TRNX1", roadNumber="901", secLocationId="1s6", date="01/01/2020 10:00:00")


class StagingPool(Review):
    def test_fifo_departs_the_track_that_filled_first(self):
        """Real build: Turn A rejected, the train departs Turn B and takes TRNX 901 (TBB:1763, 1974-2029)."""
        folder = self.scenario(lambda x: pooled(x, "FIFO"))
        gates = Gates(ops_data.load(folder))
        self.assertTrue(any("first" in p for p in gates.staging_problems(
            gates.rr.find_train("TURN"), gates.rr.find_track("Turn A"))))
        self.assertEqual(self.gate(self.why_not(folder, "TRNX 1", "Linden", None, "TURN"), "B20")["status"], "fail")
        out = self.why_not(folder, "TRNX 901", "Linden", None, "TURN")
        self.assertEqual(self.gate(out, "A8")["status"], "pass")
        self.assertEqual(self.gate(out, "B20")["status"], "pass")

    def test_lifo_departs_the_track_that_filled_last(self):
        folder = self.scenario(lambda x: pooled(x, "LIFO"))
        self.assertEqual(self.gate(self.why_not(folder, "TRNX 1", "Linden", None, "TURN"), "B20")["status"], "pass")
        self.assertEqual(self.gate(self.why_not(folder, "TRNX 901", "Linden", None, "TURN"), "B20")["status"], "fail")

    def test_mixed_dates_are_left_to_the_build(self):
        """checkStagingPool reads the first car listed, and the list order is the builder's."""
        def change(x):
            pooled(x, "FIFO")
            x.add_car("TSTX902", "TRNX1", roadNumber="902", secLocationId="1s6", date="01/01/2030 10:00:00")
        out = self.why_not(self.scenario(change), "TRNX 1", "Linden", None, "TURN")
        self.assertEqual(self.gate(out, "A8")["status"], "not_checked")

    def test_no_pool_ignores_the_service_order(self):
        """Track.getServiceOrder answers Normal for staging outside a pool (Track:1850)."""
        def change(x):
            turn_ends_at_carrow(x)
            for track in ("1s5", "1s6"):
                x.track(track).set("order", "FIFO")
        out = self.why_not(self.scenario(change), "TRNX 1", "Linden", None, "TURN")
        self.assertEqual(self.gate(out, "A8")["status"], "pass")


if __name__ == "__main__":
    unittest.main()
