"""The items left open after the showcase reviews, each held on a scratch copy of the showcase.

No test here starts JMRI. Where a real build settled a scenario, the test says what that build did.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_data  # noqa: E402
from ops_gates import Gates  # noqa: E402
from test_gate_review import Review, Xml  # noqa: E402

WEST = "1"  # West Staging


def stop(xml, train_name, index):
    train = next(t for t in xml.root("trains").iter("train") if t.get("name") == train_name)
    route_id = train.find("route").get("id")
    route = next(r for r in xml.root("routes").iter("route") if r.get("id") == route_id)
    return route.findall("location")[index]


def train_of(xml, name):
    return next(t for t in xml.root("trains").iter("train") if t.get("name") == name)


def findings(folder, rule):
    return [f for f in Gates(ops_data.load(folder)).audit()["findings"] if f["rule"] == rule]


def drop_type(xml, location, kind):
    place = next(p for p in xml.root("locations").iter("location") if p.get("name") == location)
    types = place.find("types")
    types.remove(next(t for t in types if t.get("name") == kind))


class CabooseLength(Review):
    def test_a_caboose_is_not_counted_with_the_rival_it_replaces(self):
        """Real build: LOCAL-H took one caboose under a 50 foot limit that one caboose fits."""
        def tight(xml):
            stop(xml, "LOCAL-H", 0).set("maxTrainLength", "50")
        out = self.why_not(self.scenario(tight), "JFN 1301", "Carrow", None, "LOCAL-H")
        self.assertNotEqual(self.gate(out, "D9")["status"], "fail")

    def test_a_rival_still_counts_for_an_ordinary_car(self):
        def tight(xml):
            stop(xml, "LOCAL-H", 1).set("maxTrainLength", "50")
        out = Gates(ops_data.load(self.scenario(tight))).why_not("TEMX 1", "Oakhaven", None, "LOCAL-H", False)
        self.assertEqual(self.gate(out, "D9")["status"], "fail")


class AggressiveMoves(Review):
    @staticmethod
    def aggressive(xml):
        next(xml.root("setup").iter("buildOptions")).set("aggressive", "true")

    def competitors(self, folder):
        gates = Gates(ops_data.load(folder))
        train = next(t for t in gates.rr.trains.values() if t.name == "THRU")
        stops = gates.rr.stops(train)
        car = next(c for c in gates.rr.cars.values() if c.location_id == stops[0].location_id)
        return gates._move_competitors(car, train, stops, stops[0], stops[-1])

    def test_later_stops_compete_in_a_multiple_pass_build(self):
        """TB:312-316 and 400-409: every pass walks the route, so later stops' cars can arrive first."""
        self.assertGreater(self.competitors(self.scenario(self.aggressive)), self.competitors(self.copy()))

    def test_a_train_built_normally_keeps_route_order(self):
        def normal(xml):
            self.aggressive(xml)
            train_of(xml, "THRU").set("buildNormal", "true")
        self.assertEqual(self.competitors(self.scenario(normal)), self.competitors(self.copy()))


class ManualLineRebuild(Review):
    def test_a_car_on_this_train_still_matches_its_line(self):
        """Real build: LOCAL-H rebuilt with TEMX 1 already on it, and manual build offered the car to its line again."""
        def built(xml):
            car = next(c for c in xml.root("cars").iter("car") if c.get("roadName") == "TEMX" and c.get("roadNumber") == "1")
            car.set("trainId", train_of(xml, "LOCAL-H").get("id"))
            car.set("destinationId", car.get("locationId"))
        out = self.why_not(self.scenario(built), "TEMX 1", "Oakhaven", None, "LOCAL-H")
        self.assertIn("1m1", self.gate(out, "B19")["reason"])

    def test_a_car_on_another_train_does_not(self):
        def taken(xml):
            car = next(c for c in xml.root("cars").iter("car") if c.get("roadName") == "TEMX" and c.get("roadNumber") == "1")
            car.set("trainId", train_of(xml, "THRU").get("id"))
        out = self.why_not(self.scenario(taken), "TEMX 1", "Oakhaven", None, "LOCAL-H")
        self.assertNotIn("1m1", self.gate(out, "B19")["reason"])


class LegCaboose(Review):
    def leg(self, train, stop_name, change):
        folder = self.copy([{"action": "set_train_leg", "train": train, "leg": 2, "start": stop_name,
                             "caboose": change}])
        return folder

    def test_adding_where_no_caboose_can_stand(self):
        """Real build: LOCAL-B failed, as Brae takes no caboose and none was there."""
        self.assertIn("pick up", findings(self.leg("LOCAL-B", "Brae", "change"), "leg-caboose-stop")[0]["message"])

    def test_a_stop_that_takes_cabooses_is_quiet(self):
        self.assertEqual(findings(self.leg("LOCAL-H", "Hollis Mill", "change"), "leg-caboose-stop"), [])

    def test_removing_where_none_can_be_set_out(self):
        """Real build: failed, as the caboose could not be set out at Hollis Mill."""
        folder = self.leg("LOCAL-H", "Hollis Mill", "remove")
        xml = Xml(folder)
        drop_type(xml, "Hollis Mill", "Caboose")
        xml.save()
        self.assertIn("set out", findings(folder, "leg-caboose-stop")[0]["message"])


class EmptyStaging(Review):
    @staticmethod
    def empty_west(xml):
        for car in list(xml.root("cars").iter("car")):
            if car.get("locationId") == WEST:
                xml.root("cars").find("cars").remove(car)
        for engine in list(xml.root("engines").iter("engine")):
            if engine.get("locationId") == WEST:
                xml.root("engines").find("engines").remove(engine)

    def test_an_empty_track_a_train_can_refill_is_a_warning(self):
        blocked = [f for f in findings(self.scenario(self.empty_west), "staging-departure-blocked")
                   if "stands empty" in f["message"]]
        self.assertTrue(blocked)
        self.assertEqual({f["severity"] for f in blocked}, {"warning"})

    def test_with_no_train_arriving_it_stays_an_error(self):
        def stranded(xml):
            self.empty_west(xml)
            for train in xml.root("trains").iter("train"):
                if train.get("name") not in ("CUSTOM", "MIXED", "MODE"):
                    train.set("build", "false")
        found = findings(self.scenario(stranded), "staging-departure-blocked")
        self.assertTrue(found)
        self.assertNotIn("stands empty", " ".join(f["message"] for f in found))


class ActionCode(Review):
    def code(self, value):
        def bad(xml):
            next(xml.root("trains").iter("automation")).find("item").set("actionCode", value)
        return findings(self.scenario(bad), "file-number")

    def test_decode_forms_pass(self):
        for value in ("0x3", "#3", "03", "3"):
            self.assertEqual(self.code(value), [], value)

    def test_what_decode_throws_on_is_found(self):
        for value in ("", "0xZZ", "09", "three", "0x80000000"):
            self.assertTrue(self.code(value), value)


if __name__ == "__main__":
    unittest.main()
