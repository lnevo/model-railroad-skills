"""Fixes from the real-problem scenarios: each test fails without its fix.

Real JMRI tests run only where JMRI is installed.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import operations_pro  # noqa: E402
import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
import ops_report  # noqa: E402
import ops_router  # noqa: E402
import scenario_reports  # noqa: E402
import ops_store  # noqa: E402
from ops_store import Refused  # noqa: E402

DEMO = ROOT / "tests" / "fixtures" / "demo" / "operations"
TOOLS = {t.name: t for t in operations_pro.tools()}

# A railroad from nothing: staging at both ends and a train between them, as SKILL.md starts one.
FROM_NOTHING = [
    {"action": "add_location", "name": "West Stage"},
    {"action": "add_track", "location": "West Stage", "name": "WS1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Millton"},
    {"action": "add_track", "location": "Millton", "name": "Millton Yard", "type": "Yard", "length": 400},
    {"action": "add_location", "name": "East Stage"},
    {"action": "add_track", "location": "East Stage", "name": "ES1", "type": "Staging", "length": 400},
    {"action": "add_route", "name": "Main East",
     "stops": [{"location": "West Stage", "direction": "East"}, {"location": "Millton", "direction": "East"},
               {"location": "East Stage", "direction": "East"}]},
    {"action": "add_train", "name": "E1", "route": "Main East"},
    {"action": "add_car", "road": "AB", "number": "101", "type": "Boxcar", "length": 40, "location": "West Stage",
     "track": "WS1"},
]


class Folder(unittest.TestCase):
    """A scratch Operations folder, empty or a copy of the demo."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ops = Path(self.temp.name) / "operations"
        env = mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(Path(self.temp.name) / "plans")})
        env.start()
        self.addCleanup(env.stop)
        stopped = mock.patch.object(ops_store, "running_jmri", return_value=[])
        stopped.start()
        self.addCleanup(stopped.stop)

    def demo(self):
        shutil.copytree(DEMO, self.ops)

    def edit(self, *actions, allow=False):
        return ops_store.apply(ops_store.plan(self.ops, list(actions))["plan_id"], allow_new_errors=allow)

    def rr(self):
        return ops_data.load(self.ops)


class EmptyFolder(Folder):
    """1: SKILL.md starts a railroad from an empty Operations folder."""

    def test_an_empty_folder_reads_as_the_empty_railroad(self):
        self.ops.mkdir()
        rr = self.rr()
        self.assertEqual((rr.locations, rr.cars, rr.trains), ({}, {}, {}))
        self.assertIn("Boxcar", rr.car_types)
        self.assertEqual(sorted(rr.days), [str(n) for n in range(1, 8)])

    def test_build_from_nothing_writes_all_six_files(self):
        self.ops.mkdir()
        result = self.edit(*FROM_NOTHING)
        self.assertEqual(sorted(result["files"]), sorted(ops_store.FILES))
        rr = self.rr()
        self.assertEqual(sorted(x.name for x in rr.locations.values()), ["East Stage", "Millton", "West Stage"])
        self.assertEqual(rr.find_train("E1").name, "E1")
        self.assertEqual(ops_gates.Gates(rr).audit()["counts"]["error"], 0)

    def test_a_profile_without_operations_uses_its_operations_folder(self):
        profile = Path(self.temp.name) / "My Railroad.jmri"
        (profile / "profile").mkdir(parents=True)
        ops_store.apply(ops_store.plan(profile, FROM_NOTHING[:2])["plan_id"])
        self.assertTrue((profile / "operations" / "OperationsLocationRoster.xml").is_file())

    def test_a_folder_holding_other_things_is_not_taken_for_an_empty_railroad(self):
        other = Path(self.temp.name) / "Documents"
        other.mkdir()
        (other / "letter.txt").write_text("x")
        with self.assertRaisesRegex(FileNotFoundError, "holds other things"):
            ops_data.load(other)

    def test_a_folder_that_lost_one_file_is_still_refused_for_a_plan(self):
        self.demo()
        (self.ops / "OperationsLocationRoster.xml").unlink()
        with self.assertRaisesRegex(FileNotFoundError, "ops_restore"):
            ops_store.plan(self.ops, [{"action": "add_car_type", "name": "Autorack"}])


class ProcessDetection(unittest.TestCase):
    """2: only a real JMRI program counts, not this plugin's scratch runs or a command naming jmri.jar."""

    REAL = ["/Library/Java/JavaVirtualMachines/jdk/bin/java -Xdock:name=PanelPro -Xmx1g -cp .:/Applications/JMRI/"
            "jmri.jar:/Applications/JMRI/lib/jython.jar apps.PanelPro.PanelPro",
            "/usr/bin/java -cp /opt/JMRI/jmri.jar apps.gui3.dp3.DecoderPro3",
            '"C:\\Program Files\\Eclipse Adoptium\\bin\\javaw.exe" -Djmri.prefsdir="C:\\Users\\A B\\JMRI" -cp '
            '"C:\\Program Files\\JMRI\\jmri.jar" apps.PanelPro.PanelPro',
            "java -Djava.awt.headless=true -cp /home/a/JMRI/jmri.jar apps.JmriFaceless"]
    NOT = ["java -Djava.awt.headless=true -Duser.home=/var/folders/q/T/opspro-k2j1 -Djmri.prefsdir=/var/folders/q/T/"
           "opspro-k2j1 -cp /Applications/JMRI/jmri.jar org.python.util.jython /plugin/servers/jmri_worker.py",
           "java -Duser.home=/tmp/opspro-live-x1 -Djmri.prefsdir=/tmp/opspro-live-x1 -cp /Applications/JMRI/jmri.jar"
           " apps.JmriFaceless",
           '"C:\\Java\\bin\\java.exe" -Duser.home="C:\\Users\\A B\\AppData\\Local\\Temp\\opspro-z9" -cp jmri.jar '
           "apps.JmriFaceless",
           "java -cp /Applications/JMRI/jmri.jar org.python.util.jython tests/jmri_oracle.py",
           "/bin/zsh -c java -cp /Applications/JMRI/jmri.jar apps.PanelPro.PanelPro",
           "/bin/bash /Applications/JMRI/PanelPro.app/Contents/MacOS/StartJMRI",
           "grep jmri.jar", "vim notes-jmri.jar.txt", "python3 tools/ops/check.py --jar jmri.jar",
           "/usr/bin/java -cp /Applications/JMRI/lib/JavaVersionCheckWindow.jar apps.JavaVersionCheckWindow"]

    def test_real_jmri_programs_count(self):
        self.assertEqual(len(ops_store.running_jmri("\n".join(self.REAL))), len(self.REAL))

    def test_scratch_runs_shells_and_tools_do_not(self):
        self.assertEqual(ops_store.running_jmri("\n".join(self.NOT)), [])


class BrokenFiles(Folder):
    """5: backups, restore and the audit must work on the broken folder they exist for."""

    def setUp(self):
        super().setUp()
        self.demo()
        self.edit({"action": "add_car_type", "name": "Autorack", "like": "Flatcar"})
        self.set = ops_store.backups(self.ops)[0]["set"]
        self.good = (self.ops / "backups" / self.set / "OperationsLocationRoster.xml").read_bytes()

    def lose(self):
        (self.ops / "OperationsLocationRoster.xml").unlink()

    def corrupt(self):
        (self.ops / "OperationsLocationRoster.xml").write_bytes(self.good[:700])

    def test_backups_list_on_a_folder_missing_a_file(self):
        self.lose()
        sets = ops_store.backups(self.ops)
        self.assertIn(self.set, [s["set"] for s in sets])

    def test_single_file_restore_brings_back_a_lost_file(self):
        self.lose()
        result = ops_store.restore(self.ops, self.set, file="OperationsLocationRoster.xml")
        self.assertEqual(result["files"], ["OperationsLocationRoster.xml"])
        self.assertEqual((self.ops / "OperationsLocationRoster.xml").read_bytes(), self.good)
        self.assertIn(b"Autorack", (self.ops / "OperationsCarRoster.xml").read_bytes())  # left as it was

    def test_whole_set_restore_works_on_an_unreadable_file(self):
        self.corrupt()
        ops_store.restore(self.ops, self.set)
        self.assertEqual((self.ops / "OperationsLocationRoster.xml").read_bytes(), self.good)
        saved = ops_store.backups(self.ops)
        self.assertTrue(any(s["set"].startswith("opspro_before-restore") for s in saved))

    def test_a_backup_file_that_will_not_parse_is_refused(self):
        source = self.ops / "backups" / self.set / "OperationsLocationRoster.xml"
        source.write_bytes(self.good[:500])
        with self.assertRaisesRegex(Refused, "will not parse"):
            ops_store.restore(self.ops, self.set, file="OperationsLocationRoster.xml")

    def test_audit_reports_a_missing_file(self):
        self.lose()
        found = TOOLS["ops_audit"].run({"ops_dir": str(self.ops)})["findings"]
        self.assertEqual([(f["rule"], f["subject"]) for f in found if f["rule"].startswith("file-")],
                         [("file-missing", "OperationsLocationRoster.xml")])
        self.assertEqual(found[0]["severity"], "error")

    def test_audit_reports_an_unreadable_file(self):
        self.corrupt()
        found = TOOLS["ops_audit"].run({"ops_dir": str(self.ops)})["findings"]
        self.assertIn(("file-unreadable", "OperationsLocationRoster.xml"), [(f["rule"], f["subject"]) for f in found])

    def test_restore_tool_takes_a_file(self):
        self.lose()
        TOOLS["ops_restore"].run({"ops_dir": str(self.ops), "set": self.set, "file": "OperationsLocationRoster.xml"})
        self.assertEqual(TOOLS["ops_audit"].run({"ops_dir": str(self.ops)})["counts"]["error"],
                         ops_gates.Gates(ops_data.load(self.ops)).audit()["counts"]["error"])


class NewPlaces(Folder):
    """3: new locations and tracks take locomotive types, as JMRI's do; terminal staging that refuses a type
    the train carries is an audit error. 6: negative move counts. 7: a deleted track's id is not reused."""

    def setUp(self):
        super().setUp()
        self.demo()
        self.edit({"action": "set_option", "group": "buildOptions", "name": "stagingRestrictionEnabled",
                   "value": True}, allow=True)  # The demo turns it off; its own trains then trip it.

    def test_a_new_location_and_track_take_every_car_and_locomotive_type(self):
        self.edit({"action": "add_location", "name": "Far Stage"},
                  {"action": "add_track", "location": "Far Stage", "name": "FS1", "type": "Staging", "length": 300})
        rr = self.rr()
        location = next(x for x in rr.locations.values() if x.name == "Far Stage")
        extras = ops_gates.Extras(rr.directory)
        self.assertIn("Diesel", extras.types[location.id])
        self.assertIn("Diesel", extras.types[rr.find_track("FS1").id])
        self.assertTrue(set(rr.car_types) <= set(location.types))

    def test_terminal_staging_that_refuses_a_train_type_is_an_error(self):
        result = ops_store.plan(self.ops, [
            {"action": "add_location", "name": "Far Stage", "types": ["Boxcar"]},
            {"action": "add_track", "location": "Far Stage", "name": "FS1", "type": "Staging", "length": 300},
            {"action": "add_route", "name": "To Far", "stops": [{"location": "Brackwater"},
                                                                {"location": "Far Stage"}]},
            {"action": "add_train", "name": "F9", "route": "To Far"}])
        found = [f for f in result["new_findings"] if f["rule"] == "terminal-staging-refuses-train"]
        self.assertEqual([f["subject"] for f in found], ["F9"])
        self.assertIn("does not take type", found[0]["message"])
        self.assertTrue(result["blocked"])

    def test_the_finding_goes_when_the_set_out_list_names_the_train(self):
        self.edit({"action": "add_location", "name": "Far Stage", "types": ["Boxcar"]},
                  {"action": "add_track", "location": "Far Stage", "name": "FS1", "type": "Staging", "length": 300},
                  {"action": "add_route", "name": "To Far", "stops": [{"location": "Brackwater"},
                                                                      {"location": "Far Stage"}]},
                  {"action": "add_train", "name": "F9", "route": "To Far"}, allow=True)
        result = ops_store.plan(self.ops, [{"action": "update_track", "track": "FS1",
                                            "drop": {"option": "trains", "names": ["F9"]}}])
        self.assertEqual(result["findings_resolved"], 1)

    def test_negative_move_counts_are_allowed(self):
        self.edit({"action": "set_track_moves", "moves": {"Ashgrove Feed Mill": -100}})
        self.assertEqual(self.rr().find_track("Ashgrove Feed Mill").moves, -100)
        with self.assertRaisesRegex(Refused, "at most"):
            ops_store.plan(self.ops, [{"action": "set_track_moves", "moves": {"Ashgrove Feed Mill": 2 ** 31}}])

    def test_a_deleted_tracks_id_is_not_given_to_the_next_track(self):
        self.edit({"action": "add_track", "location": "Ashgrove", "name": "Temp", "type": "Spur", "length": 100})
        old = self.rr().find_track("Temp").id
        self.edit({"action": "delete_track", "track": "Temp"})
        self.edit({"action": "add_track", "location": "Ashgrove", "name": "Team", "type": "Spur", "length": 100})
        self.assertNotEqual(self.rr().find_track("Team").id, old)

    def test_delete_then_add_in_one_plan_gets_a_new_id_and_keeps_moves(self):
        self.edit({"action": "add_track", "location": "Ashgrove", "name": "Temp", "type": "Spur", "length": 100,
                   "moves": 9})
        old = self.rr().find_track("Temp").id
        self.edit({"action": "delete_track", "track": "Temp"},
                  {"action": "add_track", "location": "Ashgrove", "name": "Team", "type": "Spur", "length": 100})
        track = self.rr().find_track("Team")
        self.assertNotEqual(track.id, old)
        self.assertEqual(track.moves, 0)


class TrainValues(Folder):
    """4: train values JMRI would refuse or crash on are refused."""

    def setUp(self):
        super().setUp()
        self.demo()

    def refused(self, **fields):
        with self.assertRaises(Refused):
            ops_store.plan(self.ops, [{"action": "update_train", "train": "BV1", **fields}])

    def test_bad_values_are_refused(self):
        for fields in ({"engines": "AUTO HPT"}, {"engines": "auto"}, {"engines": "7"}, {"engines": "-1"},
                       {"requires": "4"}, {"requires": 3}, {"depart_hour": "24"}, {"depart_minute": "x"},
                       {"built_start": "1950s"}):
            self.refused(**fields)

    def test_jmri_values_are_written_as_jmri_writes_them(self):
        self.edit({"action": "update_train", "train": "T10", "engines": "Auto", "requires": "caboose",
                   "depart_hour": 7, "depart_minute": "5", "built_start": "1950"}, allow=True)
        raw = ops_gates.Extras(self.ops).train[self.rr().find_train("T10").id]
        self.assertEqual((raw["numberEngines"], raw["requires"], raw["departHour"], raw["departMinute"],
                          raw["builtStartYear"]), ("Auto", "1", "07", "05", "1950"))

    def test_auto_hpt_is_refused_from_staging_as_edit_train_does(self):
        departs = next(t for t in self.rr().trains.values()
                       if self.rr().locations[self.rr().stops(t)[0].location_id].is_staging)
        with self.assertRaisesRegex(Refused, "does not depart staging"):
            ops_store.plan(self.ops, [{"action": "update_train", "train": departs.name, "engines": "Auto HPT"}])


class CarFixes(Folder):
    """11: deliver_car follows Set Car; return-when loads may stand alone."""

    def setUp(self):
        super().setUp()
        self.demo()

    def test_delivering_a_car_to_the_track_it_is_on_is_refused(self):
        rr = self.rr()
        car = next(c for c in rr.cars.values() if c.track_id in rr.tracks and not c.train_id and not c.destination_id)
        track = rr.tracks[car.track_id]
        with self.assertRaisesRegex(Refused, "only when the track"):
            ops_jmri.deliver_car(self.ops, car.id, rr.locations[track.location_id].name, track.name)

    def test_a_return_when_empty_load_needs_no_destination(self):
        rr = self.rr()
        car = next(c for c in rr.cars.values() if not c.rwe_load)
        kind_loads = [x.name for x in rr.loads.get(car.type, []) if not rr.is_default_load(x.name)]
        load = kind_loads[0] if kind_loads else "Scrap"
        if not kind_loads:
            self.edit({"action": "add_load", "name": load, "types": [car.type]})
        self.edit({"action": "update_car", "car": car.id, "return_when_empty": {"load": load}})
        raw = ops_gates.Extras(self.ops).car[car.id]
        self.assertEqual(raw.get("rweLoad"), load)
        self.assertNotIn("rweDestId", raw)

    def test_a_track_without_its_destination_is_refused(self):
        car = next(iter(self.rr().cars))
        with self.assertRaisesRegex(Refused, "needs its destination"):
            ops_store.plan(self.ops, [{"action": "update_car", "car": car,
                                       "return_when_loaded": {"track": "Tolvern Yard"}}])


STUCK_TYPE = [  # A tank car on departure staging that no track on the route takes.
    {"action": "add_location", "name": "West Staging", "types": ["Boxcar", "Tank Oil"]},
    {"action": "add_track", "location": "West Staging", "name": "West 1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Falls", "types": ["Boxcar"]},
    {"action": "add_track", "location": "Falls", "name": "Falls Yard", "type": "Yard", "length": 400},
    {"action": "add_location", "name": "East Staging", "types": ["Boxcar"]},
    {"action": "add_track", "location": "East Staging", "name": "East 1", "type": "Staging", "length": 400},
    {"action": "add_route", "name": "Through", "stops": [{"location": "West Staging"}, {"location": "Falls"},
                                                         {"location": "East Staging"}]},
    {"action": "add_train", "name": "W1", "route": "Through"},
    {"action": "set_option", "group": "buildOptions", "name": "stagingRestrictionEnabled", "value": False},
    {"action": "add_car", "road": "BX", "number": "1", "type": "Boxcar", "length": 40, "location": "West Staging",
     "track": "West 1"},
    {"action": "add_car", "road": "TX", "number": "2", "type": "Tank Oil", "length": 40, "location": "West Staging",
     "track": "West 1"},
]
STUCK_LOAD = [  # A gondola on departure staging refused by load at one yard and by type at the other.
    {"action": "add_location", "name": "West Staging", "types": ["Boxcar", "Gondola"]},
    {"action": "add_track", "location": "West Staging", "name": "WS 1", "type": "Staging", "length": 400},
    {"action": "add_location", "name": "Junction", "types": ["Boxcar", "Gondola"]},
    {"action": "add_track", "location": "Junction", "name": "Junction Yard 1", "type": "Yard", "length": 400,
     "loads": {"option": "Include", "names": ["L"]}},
    {"action": "add_track", "location": "Junction", "name": "Junction Yard 2", "type": "Yard", "length": 400,
     "types": ["Boxcar"]},
    {"action": "add_route", "name": "Transfer", "stops": [{"location": "West Staging", "direction": "East"},
                                                          {"location": "Junction", "direction": "East"}]},
    {"action": "add_train", "name": "W1", "route": "Transfer"},
    {"action": "add_car", "road": "WC", "number": "10", "type": "Boxcar", "length": 40, "location": "West Staging",
     "track": "WS 1"},
    {"action": "add_car", "road": "WC", "number": "12", "type": "Gondola", "length": 50, "location": "West Staging",
     "track": "WS 1"},
]
PARKED = [  # A car parked on a spur before its schedule was added.
    {"action": "add_location", "name": "Alden"},
    {"action": "add_track", "location": "Alden", "name": "Alden Yard", "type": "Yard", "length": 400},
    {"action": "add_location", "name": "Birch"},
    {"action": "add_track", "location": "Birch", "name": "Birch Mill", "type": "Spur", "length": 300},
    {"action": "add_load", "name": "Flour", "types": ["Boxcar"]},
    {"action": "add_route", "name": "Run", "stops": [{"location": "Alden"}, {"location": "Birch"},
                                                     {"location": "Alden"}]},
    {"action": "add_train", "name": "F2", "route": "Run"},
    {"action": "add_car", "road": "AB", "number": "50", "type": "Boxcar", "length": 40, "location": "Birch",
     "track": "Birch Mill"},
    {"action": "add_schedule", "name": "Mill", "lines": [{"type": "Boxcar", "receive": "E", "ship": "Flour"}]},
    {"action": "update_track", "track": "Birch Mill", "schedule": "Mill"},
]


class NewFindings(Folder):
    """12: audit findings for traps the scenarios hit with no warning."""

    def findings(self, actions, rule=None):
        if not self.ops.exists():
            self.ops.mkdir()
        self.edit(*actions, allow=True)
        found = ops_gates.Gates(self.rr()).audit()["findings"]
        return [f for f in found if rule is None or f["rule"] == rule]

    def test_a_staging_car_type_no_track_on_the_route_takes(self):
        found = self.findings(STUCK_TYPE, "staging-type-unserved")
        self.assertEqual([f["subject"] for f in found], ["West 1"])
        self.assertIn("TX 2", found[0]["message"])

    def test_a_staging_car_no_track_takes_blocks_departure(self):
        found = self.findings(STUCK_LOAD, "staging-departure-blocked")
        self.assertEqual([f["severity"] for f in found], ["error"])
        self.assertIn("WC 12", found[0]["message"])

    def test_a_train_with_build_off_is_not_blocked(self):
        self.demo()
        before = [f for f in ops_gates.Gates(self.rr()).audit()["findings"] if f["rule"] == "staging-departure-blocked"]
        self.assertIn("X99", [f["subject"] for f in before])
        after = self.findings([{"action": "update_train", "train": "X99", "build": False}], "staging-departure-blocked")
        self.assertNotIn("X99", [f["subject"] for f in after])

    def test_a_home_division_no_one_can_reach_from_staging(self):
        found = self.findings(scenario_reports.DIVISION_EMPTIES, "staging-division-unreachable")
        self.assertEqual(len(found), 1)
        self.assertIn("VR 100", found[0]["message"])
        fixed = self.findings([{"action": "set_location_division", "division": "North", "locations": ["East Stage"]}],
                              "staging-division-unreachable")
        self.assertEqual(fixed, [])

    def test_caboose_on_an_interchange_at_both_ends_of_a_turn(self):
        self.assertEqual(len(self.findings(scenario_reports.CABOOSE_TURN, "caboose-interchange-same-route")), 1)

    def test_caboose_track_direction(self):
        found = self.findings(scenario_reports.CABOOSE_DIRECTION, "caboose-track-direction")
        self.assertEqual([f["subject"] for f in found], ["Caboose Track"])

    def test_a_parked_car_with_a_schedule_line_never_applied(self):
        found = self.findings(PARKED, "schedule-not-applied")
        self.assertEqual([f["subject"] for f in found], ["AB 50"])

    def test_a_staging_car_type_the_route_takes_is_quiet(self):
        actions = [dict(a, types=["Boxcar", "Tank Oil"]) if a.get("name") == "Falls" and a["action"] == "add_location"
                   else a for a in STUCK_TYPE]
        self.assertEqual(self.findings(actions, "staging-type-unserved"), [])

    def test_a_car_parked_with_the_load_the_schedule_ships_is_quiet(self):
        actions = [dict(a, load="Flour") if a["action"] == "add_car" else a for a in PARKED]
        self.assertEqual(self.findings(actions, "schedule-not-applied"), [])

    def test_staging_departure_warns_when_only_one_track_is_stuck(self):
        actions = STUCK_LOAD + [
            {"action": "add_track", "location": "West Staging", "name": "WS 2", "type": "Staging", "length": 400},
            {"action": "add_car", "road": "WC", "number": "11", "type": "Boxcar", "length": 40,
             "location": "West Staging", "track": "WS 2"}]
        found = self.findings(actions, "staging-departure-blocked")
        self.assertEqual([f["severity"] for f in found], ["warning"])
        self.assertIn("WC 12", found[0]["message"])

    def test_interchange_exit_by_load(self):
        found = self.findings([
            {"action": "add_location", "name": "Junction"},
            {"action": "add_track", "location": "Junction", "name": "Junction CI", "type": "Interchange",
             "length": 400},
            {"action": "add_location", "name": "Millton"},
            {"action": "add_track", "location": "Millton", "name": "Millton Yard", "type": "Yard", "length": 400},
            {"action": "add_location", "name": "Eastport"},
            {"action": "add_track", "location": "Eastport", "name": "Eastport Yard", "type": "Yard", "length": 400,
             "loads": {"option": "Include", "names": ["L"]}},
            {"action": "add_route", "name": "J", "stops": [{"location": "Junction"}, {"location": "Millton"},
                                                           {"location": "Eastport"}]},
            {"action": "add_train", "name": "J3", "route": "J"},
            {"action": "setup_interchange", "track": "Junction CI", "destinations": ["Eastport"]},
            {"action": "add_car", "road": "NS", "number": "106", "type": "Boxcar", "length": 40,
             "location": "Junction", "track": "Junction CI"}], "interchange-no-exit")
        self.assertEqual([f["severity"] for f in found], ["warning"])
        self.assertIn("Boxcar with E", found[0]["message"])

    def test_interchange_exit_by_type(self):
        found = self.findings([
            {"action": "add_location", "name": "Junction"},
            {"action": "add_track", "location": "Junction", "name": "Junction CI", "type": "Interchange",
             "length": 400},
            {"action": "add_location", "name": "Millton"},
            {"action": "add_track", "location": "Millton", "name": "Millton Yard", "type": "Yard", "length": 400},
            {"action": "add_location", "name": "Eastport"},
            {"action": "add_track", "location": "Eastport", "name": "Eastport Yard", "type": "Yard", "length": 400,
             "types": ["Boxcar"]},
            {"action": "update_location", "location": "Eastport", "remove_types": ["Tank Veg"]},
            {"action": "add_route", "name": "J", "stops": [{"location": "Junction"}, {"location": "Millton"},
                                                           {"location": "Eastport"}]},
            {"action": "add_train", "name": "J3", "route": "J"},
            {"action": "setup_interchange", "track": "Junction CI", "destinations": ["Eastport"]},
            {"action": "add_car", "road": "NS", "number": "105", "type": "Tank Veg", "length": 40,
             "location": "Junction", "track": "Junction CI"},
            {"action": "add_car", "road": "NS", "number": "106", "type": "Boxcar", "length": 40,
             "location": "Junction", "track": "Junction CI"}], "interchange-no-exit")
        self.assertEqual([f["severity"] for f in found], ["warning"])
        self.assertIn("Tank Veg", found[0]["message"])
        self.assertNotIn("Boxcar", found[0]["message"])


REPORTS = ROOT / "tests" / "fixtures" / "reports"  # Real JMRI 5.16 reports; tests/scenario_reports.py makes them.


class ReportFixes(unittest.TestCase):
    """8 and 9: what ops_explain_build says for failures the demo does not have."""

    def summary(self, name, **kw):
        return ops_report.explain_file(REPORTS / f"{name}.txt", **kw)

    def test_a_staging_departure_refusal_names_the_car(self):
        result = self.summary("staging_car_type")
        text = " ".join(result["summary"])
        self.assertIn("KC 2", text)
        self.assertIn("Tank Oil", text)
        rows = [r for r in result["staging"]["departure"] if r["kind"] == "rejected"]
        self.assertEqual([r["key"] for r in rows], ["buildStagingDepartCarType"])
        self.assertIn("Car types", rows[0]["fix"])

    def test_departure_staging_failure_does_not_point_at_the_pick_ups_list(self):
        for name in ("aggressive_length", "division_empties"):
            text = " ".join(self.summary(name)["summary"])
            self.assertNotIn("Pick ups list", text, name)
            self.assertIn("stuck car's own refusals", text, name)

    def test_aggressive_staging_failure_names_normal_mode(self):
        self.assertIn("stagingTryNormal", " ".join(self.summary("aggressive_length")["summary"]))

    def test_the_decisive_refusal_is_named_not_the_most_frequent(self):
        line = next(x for x in self.summary("aggressive_length")["summary"] if x.startswith("GR 700"))
        self.assertIn("decided by D9", line)  # E9 is refused more often, at Hill

    def test_cars_the_moves_never_reached_are_not_called_refused(self):
        lines = [x for x in self.summary("moves_out")["summary"] if x.startswith("AB 100")]
        self.assertNotIn("no track on the route took it", lines[0])
        self.assertIn("moves were used up", lines[0])

    def test_a_division_failure_is_c12_without_a_custom_load_note(self):
        result = self.summary("division_empties", car="VR 100")
        refused = result["story"]["attempts"][0]["refused"]
        self.assertFalse([r for r in refused if "custom load" in r], refused)
        self.assertIn("home division", " ".join(refused))
        line = next(x for x in self.summary("division_empties")["summary"] if x.startswith("VR 100"))
        self.assertIn("decided by C12", line)

    def test_a_missing_caboose_headline_follows_the_cause(self):
        for name, gate in (("caboose_same_route", "B6"), ("caboose_direction", "C9")):
            summary = self.summary(name)["summary"]
            self.assertIn(f"Fix that, not Requires: {gate}:", summary[1], name)

    def test_engines_not_found_has_a_gate_and_fix(self):
        failure = self.summary("no_engines")["outcome"]["failure"][-1]
        self.assertEqual(failure["gate"], "A9")
        self.assertIn("Locomotives", failure["fix"])

    def test_every_line_of_these_reports_is_read(self):
        for path in sorted(REPORTS.glob("*.txt")):
            report = ops_report.parse(path.read_text(encoding="utf-8"))
            self.assertEqual((report["unparsed"], report.get("unhandled", [])), ([], []), path.name)
        failure = self.summary("aggressive_length")["outcome"]["failure"][0]
        self.assertEqual(failure["cars"], ["GR 702", "GR 701", "GR 700"])

    def test_fix_texts_name_the_working_levers(self):
        self.assertIn("planned pick ups", ops_gates.GATES["E9"][2])
        self.assertIn("aggressive", ops_gates.GATES["E9"][2])
        self.assertIn("set outs plus the pick ups", ops_gates.GATES["E9"][2])
        self.assertIn("planned pick ups", ops_gates.GATES["A7"][2])
        self.assertNotIn("Pick ups list", ops_gates.GATES["B20"][2])


PRIORITY = [  # Two yard tracks at Dover; JMRI fills the one with the lower move count.
    {"action": "add_location", "name": "Alden", "types": ["Boxcar"]},
    {"action": "add_track", "location": "Alden", "name": "Alden Yard", "type": "Yard", "length": 600},
    {"action": "add_location", "name": "Dover", "types": ["Boxcar"]},
    {"action": "add_track", "location": "Dover", "name": "Dover A", "type": "Yard", "length": 600},
    {"action": "add_track", "location": "Dover", "name": "Dover B", "type": "Yard", "length": 600, "moves": 5},
    {"action": "add_route", "name": "Dover Run", "stops": [{"location": "Alden", "direction": "East", "max_moves": 6},
                                                           {"location": "Dover", "direction": "East", "max_moves": 6}]},
    {"action": "add_train", "name": "D1", "route": "Dover Run"},
    {"action": "add_car", "road": "AB", "number": "300", "type": "Boxcar", "length": 40, "location": "Alden",
     "track": "Alden Yard"},
]


class WhyNotFixes(Folder):
    """10: ops_why_not follows JMRI where it chose differently."""

    def build(self, actions):
        self.ops.mkdir()
        self.edit(*actions, allow=True)
        return ops_gates.Gates(self.rr())

    def test_a_home_division_car_cannot_go_where_the_division_search_never_sends_it(self):
        gates = self.build(scenario_reports.DIVISION_EMPTIES)
        result = gates.why_not("VR100", "East Stage", train="E1")
        self.assertFalse(result["can_move"])
        c12 = next(g for g in result["gates"] if g["gate"] == "C12")
        self.assertEqual(c12["status"], "fail")
        self.assertIn("Northfield Yard", c12["reason"])

    def test_with_no_track_named_the_lowest_moves_track_is_chosen(self):
        gates = self.build(PRIORITY)
        self.assertEqual(gates.why_not("AB300", "Dover")["track"], "Dover A")
        self.edit({"action": "set_track_moves", "moves": {"Dover A": 100}})
        result = ops_gates.Gates(self.rr()).why_not("AB300", "Dover")
        self.assertEqual(result["track"], "Dover B")
        self.assertEqual(result["track_order"], ["Dover B", "Dover A"])

    def test_a_scheduled_track_comes_first(self):
        gates = self.build(PRIORITY + [
            {"action": "add_track", "location": "Dover", "name": "Dover Mill", "type": "Spur", "length": 300,
             "moves": 50},
            {"action": "add_schedule", "name": "Mill", "lines": [{"type": "Boxcar", "receive": "E", "ship": "L"}]},
            {"action": "update_track", "track": "Dover Mill", "schedule": "Mill"}])
        self.assertEqual(gates.track_order(self.rr().find_location("Dover"))[0].name, "Dover Mill")

    def test_d6_names_the_filter_list(self):
        self.demo()
        rr = self.rr()
        track = next(t for t in rr.tracks.values() if t.destination_option != "All")
        reason = ops_gates.Gates(rr)._filter_reason(track, rr.locations[next(iter(rr.locations))])
        self.assertIn("lets cars go only to", reason)

    def test_d4_offers_the_passenger_exemption(self):
        self.demo()
        rr = self.rr()
        car = next(c for c in rr.cars.values() if not c.passenger and not c.caboose and not c.fred
                   and c.location_id and c.track_id)
        here = rr.locations[car.location_id]
        result = ops_gates.Gates(rr).why_not(car.id, here.name)
        d4 = next(g for g in result["gates"] if g["gate"] == "D4")
        if d4["status"] == "fail":
            self.assertIn("passenger", d4["reason"])
        self.assertIn("Passenger", ops_gates.GATES["D4"][2])


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmriFromNothing(Folder):
    def test_jmri_loads_and_saves_a_railroad_built_from_an_empty_folder(self):
        self.ops.mkdir()
        self.edit(*FROM_NOTHING)
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        ours, theirs = self.rr(), ops_data.load(keep)
        for field in ("cars", "locations", "routes", "trains", "tracks"):
            self.assertEqual(sorted(getattr(ours, field)), sorted(getattr(theirs, field)), field)
        self.assertEqual(sorted(ours.car_types), sorted(theirs.car_types))

    def test_a_train_into_new_staging_builds_with_jmris_staging_check_on(self):
        """3: before, the new staging took no locomotive types, and JMRI refused it (A7, type Diesel)."""
        self.ops.mkdir()
        self.edit(*FROM_NOTHING)
        self.assertTrue(self.rr().option("buildOptions", "stagingRestrictionEnabled", False))
        result = ops_jmri.run_worker(self.ops, {"build": True})
        self.assertTrue(result["builds"]["E1"]["built"], result["builds"]["E1"].get("report_tail"))

    def test_the_terminal_staging_finding_matches_jmri(self):
        self.ops.mkdir()
        actions = [dict(a, types=["Boxcar"]) if a.get("name") == "East Stage" else a for a in FROM_NOTHING]
        result = ops_store.plan(self.ops, actions)
        self.assertIn("terminal-staging-refuses-train", [f["rule"] for f in result["new_findings"]])
        ops_store.apply(result["plan_id"], allow_new_errors=True)
        build = ops_jmri.run_worker(self.ops, {"build": True})["builds"]["E1"]
        self.assertFalse(build["built"])
        self.assertIn("does not accept type", build["report_text"])


    def test_jmri_takes_the_track_why_not_names(self):
        """10: the track ops_why_not names with none given is the one JMRI's build sends the car to."""
        self.ops.mkdir()
        self.edit(*PRIORITY, {"action": "set_track_moves", "moves": {"Dover A": 100}}, allow=True)
        named = ops_gates.Gates(self.rr()).why_not("AB300", "Dover")["track"]
        for _ in range(2):
            cars = ops_jmri.run_worker(self.ops, {"build": True})["builds"]["D1"]["cars"]
            self.assertEqual([c for c in cars if c.startswith("AB300")], [f"AB300 > Dover / {named}"], cars)


    def test_jmri_keeps_a_return_when_empty_load_with_no_destination(self):
        self.ops.mkdir()
        self.edit(*FROM_NOTHING, {"action": "add_load", "name": "Rails", "types": ["Boxcar"]},
                  {"action": "update_car", "car": "AB101", "return_when_empty": {"load": "Rails"}}, allow=True)
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        self.assertEqual(ops_gates.Extras(keep).car["AB101"].get("rweLoad"), "Rails")


    def test_jmri_fails_where_the_staging_findings_say(self):
        """12: the railroads behind staging-type-unserved and the per-car staging-departure-blocked fail in JMRI."""
        for actions in (STUCK_TYPE, STUCK_LOAD):
            with self.subTest(actions=actions[-1]["number"]):
                if self.ops.exists():
                    shutil.rmtree(self.ops)
                self.ops.mkdir()
                self.edit(*actions, allow=True)
                build = ops_jmri.run_worker(self.ops, {"build": True})["builds"]["W1"]
                self.assertFalse(build["built"])
                self.assertIn("could not find destinations", build["report_text"])

    def test_jmri_never_applies_the_schedule_to_the_parked_car(self):
        self.ops.mkdir()
        self.edit(*PARKED, allow=True)
        result = ops_jmri.run_worker(self.ops, {"build": True, "terminate": True, "save": True}, self.ops)
        self.assertTrue(result["builds"]["F2"]["built"], result["builds"]["F2"].get("report_tail"))
        self.assertEqual(self.rr().cars["AB50"].load, "E")


if __name__ == "__main__":
    unittest.main()


class HomeDivisionSearch(Folder):
    """C12's search against the Try lines real JMRI 5.16 wrote while building the same railroad
    (tests/scenario_reports.py division_search_*): which track each car is offered first, and in what order."""

    def build(self, actions):
        self.ops.mkdir()
        self.edit(*actions, allow=True)
        return ops_gates.Gates(self.rr())

    @staticmethod
    def jmri_tries(report: str) -> dict[str, list[str]]:
        tries: dict[str, list[str]] = {}
        car = None
        for line in report.splitlines():
            head = re.search(r"Car \((\w+ \d+)\) type \(.*home division", line)
            if head:
                car = head.group(1).replace(" ", "")
                tries[car] = []
            found = re.search(r"Try (\w+) \(([^,]+), ([^)]+)\) division \(\w+\) for car \((\w+ \d+)\)", line)
            if found and car:
                tries[car].append(f"{found.group(1)} {found.group(2)}, {found.group(3)}")
        return tries

    def check(self, name: str, actions):
        report = (Path(__file__).resolve().parent / "fixtures" / "reports" / f"{name}.txt").read_text(encoding="utf-8")
        wanted = self.jmri_tries(report)
        self.assertEqual(sorted(wanted), ["DV1", "DV2", "DV3", "DV4", "DV5", "DV6"])
        gates = self.build(actions)
        train = gates.rr.find_train("DS")
        for car_id, expected in wanted.items():
            car = gates.rr.cars[car_id]
            search = ops_router.find_division_destination(gates, car, train)
            # A Try line is written after the checks in front of it: a yard or staging track's room, a
            # spur's status. A track's name carries its type in JMRI's line.
            got = []
            for entry in search["tried"]:
                if entry["kind"] == "Spur":
                    printed = not entry["result"].startswith(("refused", "full", "same", "car is", "through", "local"))
                else:
                    printed = entry["result"] == "chosen" or entry["result"].startswith("router")
                if printed:
                    got.append(f"{entry['kind'].lower()} {entry['track']}")
            with self.subTest(car=car_id):
                self.assertEqual(got, expected)

    def test_a_train_ending_in_staging_tries_staging_first(self):
        self.check("division_search_staged", scenario_reports.DIVISION_SEARCH_STAGED)

    def test_a_train_ending_at_a_yard_tries_yards_first(self):
        self.check("division_search_open", scenario_reports.DIVISION_SEARCH_OPEN)
