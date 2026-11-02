"""The core write actions hold to what JMRI 5.16 can read back, through the MCP tools (ops_plan, ops_apply,
ops_session, ops_restore) on copies of the demo railroad.

Numbers JMRI parses with Integer.parseInt, names its windows refuse, legs copied across routes, exact car
ids, Set Car's forgotten last route, and the Add Car window's checks. JMRI-backed tests run only where JMRI
is installed.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import mcp_stdio  # noqa: E402
import operations_pro  # noqa: E402
import ops_actions  # noqa: E402
import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402

DEMO = ROOT / "tests" / "fixtures" / "demo" / "operations"
LOCATIONS, ROUTES, TRAINS, CARS, SETUP = ops_store.FILES[:5]
TOOLS = {t.name: t for t in operations_pro.tools()}


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ops = Path(self.temp.name) / "operations"
        shutil.copytree(DEMO, self.ops)
        for patch in (mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(Path(self.temp.name) / "plans")}),
                      mock.patch.object(ops_store, "running_jmri", return_value=[])):
            patch.start()
            self.addCleanup(patch.stop)

    def call(self, name, **arguments):
        message = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                   "params": {"name": name, "arguments": {"ops_dir": str(self.ops), **arguments}}}
        result = mcp_stdio.handle(json.loads(json.dumps(message)), "operations-pro", TOOLS)["result"]
        text = result["content"][0]["text"]
        return {"error": text} if result.get("isError") else json.loads(text)

    def plan(self, *actions):
        return self.call("ops_plan", actions=list(actions))

    def apply(self, *actions, accept=False):
        planned = self.plan(*actions)
        self.assertNotIn("error", planned)
        return self.call("ops_apply", plan_id=planned["plan_id"], accept_new_errors=accept)

    def refused(self, *actions, says=""):
        planned = self.plan(*actions)
        self.assertIn("error", planned, f"{actions} was not refused")
        self.assertIn(says, planned["error"])
        return planned["error"]

    def element(self, file, tag, **attrs):
        for node in ET.parse(self.ops / file).getroot().iter(tag):
            if all(node.get(k) == v for k, v in attrs.items()):
                return node
        return None

    def audit(self):
        return self.call("ops_audit")["findings"]


def _lines(count=1, wait=0):
    return [{"type": "Boxcar", "receive": "Mty", "count": count, "wait": wait}]


class Numbers(Case):
    """F1 and F2: only numbers JMRI parses reach the files."""

    def test_schedule_count_or_wait_beyond_java_int_is_refused(self):
        self.refused({"action": "add_schedule", "name": "Big", "lines": _lines(count=10 ** 12)}, says="2147483647")
        self.refused({"action": "add_schedule", "name": "Long", "lines": _lines(wait="2147483648")}, says="2147483647")
        lines = [{"type": "Boxcar", "receive": "Mty", "count": 3000000000}]
        self.refused({"action": "replace_schedule_lines", "schedule": "Mill Receiving", "lines": lines})
        self.refused({"action": "add_schedule", "name": "Half", "lines": _lines(count=2.5)}, says="whole number")
        self.assertTrue(self.apply({"action": "add_schedule", "name": "Most",
                                    "lines": _lines(count=2 ** 31 - 1, wait="7")})["applied"])
        item = self.element(LOCATIONS, "schedule", name="Most").find("item")
        self.assertEqual((item.get("count"), item.get("wait")), ("2147483647", "7"))

    def test_audit_flags_a_file_jmri_cannot_load(self):
        path = self.ops / LOCATIONS
        text = path.read_text("utf-8")
        start = text.index('<item id="', text.index("<schedules"))
        at = text.index('count="', start) + len('count="')
        path.write_text(text[:at] + "3000000000" + text[text.index('"', at):], "utf-8")
        found = [f for f in self.audit() if f["rule"] == "file-number"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["severity"], "error")
        self.assertIn("count='3000000000'", found[0]["message"])

    def test_track_numbers_must_be_ints_jmri_reads(self):
        for value in (312.5, True, 3000000000, "40ft"):
            self.refused({"action": "update_track", "track": "Tolvern Yard", "length": value}, says="length")
        self.refused({"action": "update_track", "track": "Tolvern Yard", "blocking_order": "abc"})
        self.refused({"action": "update_track", "track": "Ashgrove Feed Mill", "reservation_factor": True})
        self.refused({"action": "add_track", "location": "Tolvern", "name": "Flt", "type": "Spur", "length": 312.5})
        self.apply({"action": "update_track", "track": "Tolvern Yard", "length": "500", "blocking_order": 2.0})
        track = self.element(LOCATIONS, "track", name="Tolvern Yard")
        self.assertEqual((track.get("length"), track.get("blockingOrder")), ("500", "2"))

    def test_car_stop_and_setting_numbers(self):
        for fields in ({"length": "40ft"}, {"length": 40.5}, {"blocking": "abc"}):
            self.assertIn("error", self.call("ops_session", actions=[{"action": "update_car", "car": "BVR1001",
                                                                     **fields}]))
        self.refused({"action": "update_stop", "route": "Ashgrove Turn", "stop": 1, "max_moves": 10 ** 10})
        self.refused({"action": "set_option", "group": "settings", "name": "maxEngines", "value": "lots"})
        self.refused({"action": "set_option", "group": "settings", "name": "trainLength", "value": "1000.5"})
        self.refused({"action": "set_option", "group": "settings", "name": "hpt", "value": "fast"})
        self.apply({"action": "set_option", "group": "settings", "name": "maxEngines", "value": "5"},
                   {"action": "set_option", "group": "settings", "name": "hpt", "value": 1.5})
        settings = self.element(SETUP, "settings")
        self.assertEqual((settings.get("maxEngines"), settings.get("hpt")), ("5", "1.5"))

    def test_the_parser_reads_what_jmri_reads(self):
        path = self.ops / LOCATIONS
        track = self.element(LOCATIONS, "track", name="Tolvern Yard")
        text = path.read_text("utf-8")
        at = text.index(f'<track id="{track.get("id")}"')
        text = text[:at] + text[at:].replace(f'length="{track.get("length")}"', 'length="3000000000"', 1)
        path.write_text(text, "utf-8")
        self.assertEqual(ops_data.load(self.ops).tracks[track.get("id")].length, 0)  # JMRI's parseInt fails: 0.
        self.assertEqual(ops_data._int("12.5", 7), 7)
        self.assertEqual(ops_data._int("+12"), 12)


class Names(Case):
    """F3 and F6: names JMRI's windows refuse, or that break a file name."""

    def test_names_that_break_files_or_are_blank(self):
        self.refused({"action": "add_train", "name": "Ashgrove/Tolvern Turn", "route": "Ashgrove Turn"},
                     says="file names")
        self.refused({"action": "add_location", "name": "Mill/Elevator"}, says="file names")
        for name in ("", "   ", "X" * 40):
            self.refused({"action": "add_location", "name": name})
        self.refused({"action": "add_route", "name": "", "stops": [{"location": "Brackwater"}]}, says="blank")
        self.refused({"action": "rename_train", "train": "T10", "new": ""}, says="blank")
        self.refused({"action": "rename_track", "track": "Tolvern Yard", "new": " "}, says="blank")
        planned = self.plan({"action": "add_train", "name": "No. 22", "route": "Ashgrove Turn"})
        self.assertNotIn("error", planned)  # "." is only a window rule: such a train builds.

    def test_and_in_a_type_or_load_is_refused(self):
        self.refused({"action": "add_car_type", "name": "Flat & Bulkhead", "like": "Flatcar"}, says="&")
        self.refused({"action": "add_load", "name": "Ore & Rock", "types": ["Hopper"]}, says="&")
        self.refused({"action": "rename_car_type", "old": "Flatcar", "new": "Flat & Co"}, says="&")

    def test_rename_load_follows_a_pair_whose_type_holds_and(self):
        """A file from elsewhere may already hold such a type; the pair is matched on its end."""
        editor = ops_actions.Editor(self.ops)
        editor.register("types", "type", "Flat & Bulkhead")
        loads = editor.section(editor.car_root, "loads")
        holder = ET.SubElement(loads, "load", {"type": "Flat & Bulkhead"})
        ET.SubElement(holder, "carLoad", {"name": "Lumber", "loadType": "Load"})
        track = editor.track("Tolvern Yard")
        track.set("carLoadOption", "Include")
        ET.SubElement(ET.SubElement(track, "carLoads"), "carLoad", {"name": "Flat & Bulkhead & Lumber"})
        for name, doc in editor.docs.items():
            if doc.changed:
                (self.ops / name).write_bytes(doc.render())
        self.apply({"action": "rename_load", "old": "Lumber", "new": "Timber", "car_type": "Flat & Bulkhead"},
                   accept=True)
        filters = [e.get("name") for e in self.element(LOCATIONS, "track", name="Tolvern Yard").iter("carLoad")]
        self.assertEqual(filters, ["Flat & Bulkhead & Timber"])


class RouteStops(Case):
    """F4: a new stop gets the route window's defaults."""

    def test_new_stops_take_setup_direction_length_and_staging_moves(self):
        self.apply({"action": "set_option", "group": "settings", "name": "trainDirection", "value": 12},
                   {"action": "set_option", "group": "settings", "name": "trainLength", "value": 600})
        planned = self.plan({"action": "add_route", "name": "North Job",
                             "stops": [{"location": "West Staging"}, {"location": "Brackwater"},
                                       {"location": "Brackwater", "direction": "South", "max_moves": 3}]})
        self.assertNotIn("error", planned)
        added = [line[1:].strip() for line in planned["diff"].splitlines() if line.startswith("+") and "r1\"" in line
                 or line.startswith("+") and ('r2"' in line or 'r3"' in line)]
        stops = [ET.fromstring(line if line.endswith("/>") else line + "</location>") for line in added
                 if line.startswith("<location ")]
        self.assertEqual([(s.get("trainDirection"), s.get("maxTrainLength"), s.get("maxCarMoves")) for s in stops],
                         [("4", "600", "50"), ("4", "600", "5"), ("8", "600", "3")])


class LikeTrains(Case):
    """F5: a train copied onto another route does not keep the source route's leg stops."""

    def add_leg(self):
        self.apply({"action": "set_train_leg", "train": "T10", "leg": 2, "caboose": "change", "start": 2},
                   accept=True)
        self.assertIsNotNone(self.element(TRAINS, "train", name="T10").get("leg2Start"))

    def test_like_on_another_route_clears_the_legs(self):
        self.add_leg()
        planned = self.plan({"action": "add_train", "name": "T10copy", "route": "Tolvern Job", "like": "T10"})
        self.assertIn("Legs 2 of T10", " ".join(planned["summary"]))
        self.call("ops_apply", plan_id=planned["plan_id"])
        copy = self.element(TRAINS, "train", name="T10copy")
        self.assertEqual([a for a in copy.attrib if a.startswith(("leg2", "leg3"))], [])

    def test_like_on_the_same_route_keeps_them(self):
        self.add_leg()
        route = self.element(TRAINS, "train", name="T10").find("route").get("name")
        self.apply({"action": "add_train", "name": "T10b", "route": route, "like": "T10"}, accept=True)
        self.assertEqual(self.element(TRAINS, "train", name="T10b").get("leg2Start"),
                         self.element(TRAINS, "train", name="T10").get("leg2Start"))

    def test_audit_flags_a_leg_stop_not_on_the_route(self):
        self.add_leg()
        path = self.ops / TRAINS
        start = self.element(TRAINS, "train", name="T10").get("leg2Start")
        path.write_text(path.read_text("utf-8").replace(f'leg2Start="{start}"', 'leg2Start="99r9"'), "utf-8")
        found = [f for f in self.audit() if f["rule"] == "leg-stop"]
        self.assertEqual([(f["severity"], f["subject"]) for f in found], [("error", "T10")])


class Cars(Case):
    """F7, F8 and F9."""

    def test_car_lookup_is_exact(self):
        self.apply({"action": "add_car", "road": "bvr", "number": "1001", "type": "Boxcar", "length": 40})
        self.call("ops_session", actions=[{"action": "update_car", "car": "bvr1001", "color": "Blue"}])
        self.assertEqual(self.element(CARS, "car", id="bvr1001").get("color"), "Blue")
        self.assertEqual(self.element(CARS, "car", id="BVR1001").get("color"), "Red")
        error = self.call("ops_session", actions=[{"action": "update_car", "car": "Bvr 1001", "color": "Blue"}])
        self.assertIn("Did you mean BVR1001", error["error"])
        self.refused({"action": "delete_car", "car": "Bvr1001"}, says="Did you mean")

    def test_place_car_forgets_the_last_route_and_delete_route_goes_through(self):
        self.assertEqual(self.element(CARS, "car", id="BVR3006").get("lastRouteId"), "3")
        done = self.call("ops_session", actions=[{"action": "place_car", "car": "BVR3006", "location": "Brackwater",
                                                  "track": "Quarry Interchange", "force": True}])
        self.assertTrue(done.get("applied"), done)
        self.assertIsNone(self.element(CARS, "car", id="BVR3006").get("lastRouteId"))

    def test_delete_route_clears_the_last_route_instead_of_refusing(self):
        route = self.element(ROUTES, "route", id="3").get("name")
        users = [t.get("name") for t in ET.parse(self.ops / TRAINS).getroot().iter("train")
                 if t.find("route") is not None and t.find("route").get("id") == "3"]
        planned = self.plan(*[{"action": "delete_train", "train": n} for n in users],
                            {"action": "delete_route", "route": route})
        self.assertNotIn("error", planned)
        self.assertIn("BVR3006", " ".join(planned["summary"]))

    def test_add_car_makes_the_add_car_window_checks(self):
        base = {"action": "add_car", "road": "BVR", "type": "Tank", "length": 40, "location": "Ashgrove"}
        self.refused({**base, "number": "8"}, says="track")
        self.refused({**base, "number": "10", "type": "Gondola", "track": "Ashgrove Feed Mill"},
                     says="does not take Gondola")  # The track takes it, the location does not.
        self.refused({**base, "number": "9", "type": "Boxcar", "length": 400, "track": "Ashgrove Feed Mill"},
                     says="force")
        planned = self.plan({**base, "number": "9", "type": "Boxcar", "length": 400, "track": "Ashgrove Feed Mill",
                             "force": True})
        self.assertNotIn("error", planned)


class Restore(Case):
    """F10: a whole-set restore says which files the set did not hold (JMRI's Restore copies what is there)."""

    def test_restore_names_the_files_it_left(self):
        handmade = self.ops / "backups" / "handmade"
        handmade.mkdir(parents=True)
        for name in ops_data.REQUIRED:
            shutil.copy2(self.ops / name, handmade / name)
        result = self.call("ops_restore", set="handmade")
        self.assertIn(SETUP, result["not_restored"])
        self.assertIn(SETUP, result["note"])


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmri(Case):
    def read_back(self, job=None):
        keep = Path(self.temp.name) / "saved"
        keep.mkdir(exist_ok=True)
        return ops_jmri.run_worker(self.ops, job or {"save": True}, keep), keep

    def test_largest_count_and_normalised_numbers_load_and_save(self):
        """F1 and F2: what the plan lets through, JMRI loads with no error and saves unchanged."""
        self.apply({"action": "add_schedule", "name": "Most", "lines": _lines(count=2 ** 31 - 1, wait="9")},
                   {"action": "update_track", "track": "Tolvern Yard", "length": 312.0, "blocking_order": "3"},
                   {"action": "update_stop", "route": "Ashgrove Turn", "stop": 1, "max_moves": "7"},
                   {"action": "set_option", "group": "settings", "name": "maxEngines", "value": "5"}, accept=True)
        self.call("ops_session", actions=[{"action": "update_car", "car": "BVR1001", "length": "44",
                                           "blocking": 2}])
        result, keep = self.read_back()
        self.assertEqual(result["log_errors"], [])
        theirs = ET.parse(keep / LOCATIONS).getroot()
        item = next(s for s in theirs.iter("schedule") if s.get("name") == "Most").find("item")
        self.assertEqual((item.get("count"), item.get("wait")), ("2147483647", "9"))
        track = next(t for t in theirs.iter("track") if t.get("name") == "Tolvern Yard")
        self.assertEqual((track.get("length"), track.get("blockingOrder")), ("312", "3"))
        car = next(c for c in ET.parse(keep / CARS).getroot().iter("car") if c.get("id") == "BVR1001")
        self.assertEqual((car.get("length"), car.get("blocking")), ("44", "2"))
        self.assertEqual(ET.parse(keep / SETUP).getroot().find("./operations/settings").get("maxEngines"), "5")

    def test_one_more_than_java_int_stops_jmri_loading(self):
        """F1: why the bound sits there. A count of 2147483648, written by hand, stops JMRI loading the
        location file with an uncaught NumberFormatException (the plugin's worker then has no result)."""
        path = self.ops / LOCATIONS
        text = path.read_text("utf-8")
        start = text.index('<item id="', text.index("<schedules"))
        at = text.index('count="', start) + len('count="')
        path.write_text(text[:at] + "2147483648" + text[text.index('"', at):], "utf-8")
        with self.assertRaises(ops_store.Refused) as caught:
            self.read_back()
        self.assertIn("NumberFormatException", str(caught.exception))

    def test_a_train_copied_onto_another_route_builds(self):
        """F5: the copy had kept T10's leg stop and failed with "change location missing"."""
        self.apply({"action": "set_train_leg", "train": "T10", "leg": 2, "caboose": "change", "start": 2},
                   accept=True)
        self.apply({"action": "add_train", "name": "T10copy", "route": "Tolvern Job", "like": "T10"}, accept=True)
        result, _ = self.read_back({"build": True})
        self.assertTrue(result["builds"]["T10copy"]["built"], result["builds"]["T10copy"])

    def test_deliver_car_forgets_the_last_route(self):
        """F8: as Set Car does."""
        result = self.call("ops_deliver_car", car="BVR3006", location="Brackwater", track="Quarry Interchange")
        self.assertTrue(result.get("applied"), result)
        self.assertIsNone(self.element(CARS, "car", id="BVR3006").get("lastRouteId"))


if __name__ == "__main__":
    unittest.main()
