"""Fixes from the real-problem scenarios: each test fails without its fix.

Real JMRI tests run only where JMRI is installed.
"""
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

import operations_pro  # noqa: E402
import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
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


if __name__ == "__main__":
    unittest.main()
