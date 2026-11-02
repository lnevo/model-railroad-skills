"""Train legs, engine move counts, delete_load, the rename_load merge check, pool minimums, route stop
times and ops_backup_now. Python tests against copies of the demo railroad, and real JMRI 5.16 where
it is installed: it must load and keep what was written, and build with it as intended.
"""
import hashlib
import json
import sys
import tempfile
import textwrap
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_actions  # noqa: E402
import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
import operations_pro  # noqa: E402
from ops_gates import Gates  # noqa: E402
from ops_store import Refused  # noqa: E402
from test_write import Case  # noqa: E402


def leg(**fields):
    return {"action": "set_train_leg", **fields}


CHANGE_AT_BRACKWATER = leg(train="BV1", leg=2, locos="change", start="Brackwater", engines=1, model="GP9")


class Extras(Case):
    def run_actions(self, *actions):
        """Run on the files directly, past the plan's audit gate, and return the editor's lines."""
        editor = ops_actions.Editor(self.ops)
        lines = editor.run(list(actions))
        for doc in editor.docs.values():
            if doc.changed:
                doc.path.write_bytes(doc.render())
        return lines

    def refused(self, *actions) -> str:
        with self.assertRaises(Refused) as caught:
            ops_actions.Editor(self.ops).run(list(actions))
        return str(caught.exception)

    def train(self, name):
        return self.rr().find_train(name)

    def raw_train(self, name):
        root = ET.parse(self.ops / "OperationsTrainRoster.xml").getroot()
        return next(t for t in root.iter("train") if t.get("name") == name)


class TrainLegs(Extras):
    def test_loco_change_writes_what_the_window_saves(self):
        self.edit(CHANGE_AT_BRACKWATER)
        raw = self.raw_train("BV1")
        self.assertEqual({k: raw.get(k) for k in ("leg2Options", "leg2Engines", "leg2Model", "leg2Road",
                                                  "leg2CabooseRoad", "leg2Start")},
                         {"leg2Options": "1", "leg2Engines": "1", "leg2Model": "GP9", "leg2Road": "",
                          "leg2CabooseRoad": "", "leg2Start": "1r3"})
        self.assertIsNone(raw.get("leg2End"))
        self.assertEqual(self.train("BV1").legs, [{"leg": 2, "options": 1, "engines": "1", "model": "GP9", "road": "",
                                                    "caboose_road": "", "start": "1r3", "end": ""}])

    def test_option_bits(self):
        self.run_actions(leg(train="BV1", leg=2, locos="helpers", start=2, end="Tolvern", engines="Auto HPT"),
                         leg(train="X99", leg=2, caboose="remove", start="Brackwater"),
                         leg(train="BV2", leg=3, locos="add", start="Ashgrove", engines=2, caboose="change"))
        self.assertEqual(self.raw_train("BV1").get("leg2Options"), "2")
        self.assertEqual(self.raw_train("BV1").get("leg2End"), "1r4")
        self.assertEqual(self.raw_train("X99").get("leg2Options"), "8")
        self.assertEqual(self.raw_train("X99").get("leg2Engines"), "0")
        self.assertEqual(self.raw_train("BV2").get("leg3Options"), str(16 | 12))

    def test_clear_removes_every_leg_attribute(self):
        self.run_actions(CHANGE_AT_BRACKWATER, leg(train="BV1", leg=2))
        self.assertFalse([k for k in self.raw_train("BV1").attrib if k.startswith("leg2")])

    def test_refusals_follow_the_window(self):
        cases = {
            "leg must be 2 or 3": leg(train="BV1", leg=1, locos="change", start=3, engines=1),
            "Helpers need end": leg(train="BV1", leg=2, locos="helpers", start=2, engines=1),
            "needs start": leg(train="BV1", leg=2, locos="change", engines=1),
            "ignores end": leg(train="BV1", leg=2, locos="change", start=2, end=4, engines=1),
            "must come after start": leg(train="BV1", leg=2, locos="add", start=4, end=2, engines=1),
            "0 would do nothing": leg(train="BV1", leg=2, locos="change", start=2, engines=0),
            "Auto is not offered": leg(train="BV1", leg=2, locos="change", start=2, engines="Auto"),
            "leg 3 count as a number": leg(train="BV1", leg=3, locos="add", start=3, engines="Auto HPT"),
            "no caboose to remove": leg(train="BV1", leg=2, caboose="remove", start=2),
            "departing staging cannot remove": leg(train="BV1", leg=2, locos="remove", start=2, engines=1),
            "caboose-only leg takes no engines": leg(train="X99", leg=2, caboose="change", start=2, engines=1),
            "no caboose choice beside helpers": leg(train="BV1", leg=2, locos="helpers", caboose="remove", start=2,
                                                    end=3, engines=1),
            "would be dropped": leg(train="BV1", leg=2, start=2),
            "Unknown locomotive model": leg(train="BV1", leg=2, locos="change", start=2, engines=1, model="ZZ9"),
            "has road": leg(train="BV1", leg=2, locos="change", start=2, engines=1, road="QQ"),
            "No caboose has road": leg(train="X99", leg=2, caboose="change", start=2, caboose_road="ZZ"),
            "start is the departure": leg(train="BV1", leg=2, locos="change", start=1, engines=1),
            "no stop": leg(train="BV1", leg=2, locos="change", start="Quarry Staging", engines=1),
        }
        for words, action in cases.items():
            with self.subTest(words):
                self.assertIn(words, self.refused(action))

    def test_leg_three_must_start_after_leg_two(self):
        self.assertIn("Leg 3 must start after leg 2", self.refused(
            CHANGE_AT_BRACKWATER, leg(train="BV1", leg=3, locos="change", start="Ashgrove", engines=1)))
        self.run_actions(CHANGE_AT_BRACKWATER, leg(train="BV1", leg=3, locos="change", start="Tolvern", engines=1))

    def test_leg_three_removes_a_caboose_added_on_leg_two(self):
        self.run_actions(leg(train="BV1", leg=2, caboose="change", start=2),
                         leg(train="BV1", leg=3, caboose="remove", start=4))
        self.assertEqual(self.raw_train("BV1").get("leg3Options"), "8")

    def test_model_type_must_be_serviced(self):
        self.run_actions({"action": "update_train", "train": "BV1", "remove_types": ["Diesel"]})
        self.assertIn("does not service locomotive model GP9", self.refused(CHANGE_AT_BRACKWATER))

    def test_route_change_clears_legs(self):
        lines = self.run_actions(CHANGE_AT_BRACKWATER, {"action": "set_train_route", "train": "BV1",
                                                         "route": "Main West"})
        self.assertIn("Legs cleared: 2", lines[1])
        self.assertIsNone(self.raw_train("BV1").get("leg2Options"))
        lines = self.run_actions(CHANGE_AT_BRACKWATER, {"action": "set_train_route", "train": "BV1",
                                                         "route": "Main West"})  # The route it has now.
        self.assertNotIn("Legs cleared", lines[1])
        self.assertEqual(self.raw_train("BV1").get("leg2Options"), "1")

    def test_model_rename_and_delete_follow_legs(self):
        self.run_actions(CHANGE_AT_BRACKWATER)
        self.assertIn("train BV1", self.refused({"action": "delete_engine_model", "model": "GP9"}))
        self.run_actions({"action": "rename_engine_model", "old": "GP9", "new": "GP9m"})
        self.assertEqual(self.raw_train("BV1").get("leg2Model"), "GP9m")


class EngineMoves(Extras):
    def test_read_and_write(self):
        self.assertEqual(self.rr().engines["BV101"].moves, 0)
        self.run_actions({"action": "set_engine_moves", "moves": {"BV 101": -5, "bv102": "7"}})
        engines = self.rr().engines
        self.assertEqual((engines["BV101"].moves, engines["BV102"].moves), (-5, 7))
        rows = {r["id"]: r for r in operations_pro.list_items({"ops_dir": str(self.ops), "type": "engines"})}
        self.assertEqual(rows["BV102"]["moves"], 7)

    def test_refusals(self):
        self.assertIn("No engine", self.refused({"action": "set_engine_moves", "moves": {"XX 1": 1}}))
        self.assertIn("whole number", self.refused({"action": "set_engine_moves", "moves": {"BV101": "many"}}))

    def test_moves_are_not_a_session_change(self):
        self.assertFalse(ops_actions.ACTIONS["set_engine_moves"]["session"])


class Loads(Extras):
    def test_delete_an_unused_load(self):
        self.run_actions({"action": "add_load", "name": "Junk", "types": ["Boxcar", "Hopper"]})
        self.run_actions({"action": "delete_load", "name": "Junk", "car_type": "Boxcar"})
        loads = self.rr().loads
        self.assertNotIn("Junk", [x.name for x in loads["Boxcar"]])
        self.assertIn("Junk", [x.name for x in loads["Hopper"]])
        self.run_actions({"action": "delete_load", "name": "Junk"})
        self.assertNotIn("Junk", [x.name for x in self.rr().loads.get("Hopper", [])])

    def test_last_custom_load_of_a_type_removes_its_element(self):
        self.run_actions({"action": "add_car_type", "name": "Tankette"},
                         {"action": "add_load", "name": "Ice", "types": ["Tankette"]},
                         {"action": "delete_load", "name": "Ice"})
        root = ET.parse(self.ops / "OperationsCarRoster.xml").getroot()
        self.assertNotIn("Tankette", [e.get("type") for e in root.findall("./loads/load")])

    def test_delete_refused_while_named(self):
        text = self.refused({"action": "delete_load", "name": "Feed"})
        self.assertIn("car BVR1004", text)
        self.assertIn("schedule Mill Receiving", text)
        self.assertIn("track Lakeshore Interchange load list", text)
        self.assertIn("default load", self.refused({"action": "delete_load", "name": "Mty"}))
        self.assertIn("No load", self.refused({"action": "delete_load", "name": "Nothing"}))

    def test_plain_list_entry_counts_only_when_no_other_type_keeps_the_load(self):
        self.run_actions({"action": "add_load", "name": "Junk", "types": ["Boxcar", "Hopper"]},
                         {"action": "update_track", "track": "Brackwater Yard A",
                          "loads": {"option": "Include", "names": ["Junk"]}})
        self.run_actions({"action": "delete_load", "name": "Junk", "car_type": "Boxcar"})
        self.assertIn("Brackwater Yard A load list", self.refused({"action": "delete_load", "name": "Junk"}))

    def test_train_load_list_and_manual_line_block_it(self):
        self.run_actions({"action": "add_load", "name": "Junk", "types": ["Boxcar"]},
                         {"action": "update_train", "train": "BV1",
                          "loads": {"option": "Include", "names": ["Boxcar & Junk"]}})
        self.assertIn("train BV1 load list", self.refused({"action": "delete_load", "name": "Junk"}))

    def test_rename_onto_an_existing_load_needs_merge(self):
        self.run_actions({"action": "add_load", "name": "Junk", "types": ["Boxcar"], "priority": "High"})
        self.assertIn("pass merge true", self.refused({"action": "rename_load", "old": "Junk", "new": "Feed"}))
        before = [dict(e.attrib) for e in ET.parse(self.ops / "OperationsCarRoster.xml").getroot().iter("carLoad")
                  if e.get("name") == "Feed"]
        lines = self.run_actions({"action": "rename_load", "old": "Junk", "new": "Feed", "merge": True})
        self.assertIn("Merged", lines[0])
        after = [dict(e.attrib) for e in ET.parse(self.ops / "OperationsCarRoster.xml").getroot().iter("carLoad")
                 if e.get("name") == "Feed"]
        self.assertEqual(before, after)
        self.assertNotIn("Junk", [x.name for x in self.rr().loads["Boxcar"]])

    def test_rename_to_a_new_name_still_works(self):
        self.run_actions({"action": "rename_load", "old": "Feed", "new": "Mixed Feed"})
        self.assertIn("Mixed Feed", [x.name for x in self.rr().loads["Boxcar"]])


class Pools(Extras):
    def test_refused_when_minimums_exceed_lengths(self):
        self.run_actions({"action": "update_track", "track": "Brackwater Yard A", "pool": {"name": "P", "min_length": 300}})
        text = self.refused({"action": "update_track", "track": "Brackwater Yard B",
                             "pool": {"name": "P", "min_length": 500}})
        self.assertIn("add up to 800, more than its tracks' 700", text)
        self.assertIn("whole number", self.refused({"action": "update_track", "track": "Brackwater Yard B",
                                                    "pool": {"name": "P", "min_length": "lots"}}))

    def test_shortening_a_pool_track_is_checked_too(self):
        self.run_actions({"action": "update_track", "track": "Brackwater Yard A", "pool": {"name": "P", "min_length": 300}},
                         {"action": "update_track", "track": "Brackwater Yard B", "pool": {"name": "P", "min_length": 300}})
        self.assertIn("Minimum > Length", self.refused({"action": "update_track", "track": "Brackwater Yard B",
                                                        "length": 100}))
        self.assertIn("Minimum > Length", self.refused({"action": "add_track", "location": "Brackwater", "name": "C",
                                                        "type": "Yard", "length": 10,
                                                        "pool": {"name": "P", "min_length": 200}}))

    def test_an_existing_bad_pool_is_a_finding_and_does_not_block_other_changes(self):
        self.write_bad_pool()
        findings = [f for f in Gates(self.rr()).audit()["findings"] if f["rule"] == "pool-minimum-over-length"]
        self.assertEqual(len(findings), 1)
        self.assertIn("add up to 800, more than its tracks' 700", findings[0]["message"])
        self.run_actions({"action": "update_track", "track": "Brackwater Yard A", "priority": "High"})
        self.run_actions({"action": "update_track", "track": "Brackwater Yard A", "pool": {"name": "P", "min_length": 100}})
        self.assertFalse([f for f in Gates(self.rr()).audit()["findings"] if f["rule"] == "pool-minimum-over-length"])

    def write_bad_pool(self):
        path = self.ops / "OperationsLocationRoster.xml"
        text = path.read_text(encoding="utf-8")
        for track, minimum in (("Brackwater Yard A", 400), ("Brackwater Yard B", 400)):
            text = text.replace(f'name="{track}" ', f'name="{track}" pool="P" minLength="{minimum}" ', 1)
        path.write_text(text, encoding="utf-8")


class StopTimes(Extras):
    def test_written_and_listed(self):
        self.run_actions({"action": "update_stop", "route": "Main East", "stop": "Brackwater", "depart_time": "11:30",
                          "wait": 25})
        routes = operations_pro.list_items({"ops_dir": str(self.ops), "type": "routes"})
        stop = next(s for r in routes if r["name"] == "Main East" for s in r["stops"] if s["name"] == "Brackwater")
        self.assertEqual((stop["depart_time"], stop["wait"]), ("11:30", 25))

    def test_bad_time_refused(self):
        for value in ("11:3", "24:00", "noon"):
            self.assertIn("HH:MM", self.refused({"action": "update_stop", "route": "Main East", "stop": 2,
                                                 "depart_time": value}))
        self.assertIn("HH:MM", self.refused({"action": "add_route", "name": "R",
                                             "stops": [{"location": "Brackwater", "depart_time": "7:00"}]}))

    def test_help_names_the_fields(self):
        for name in ("add_route", "update_stop"):
            self.assertIn("depart_time", ops_actions.ACTIONS[name]["help"])
            self.assertIn("wait", ops_actions.ACTIONS[name]["help"])


class BackupNow(Extras):
    def test_takes_a_set_apply_style(self):
        result = operations_pro.backup_now({"ops_dir": str(self.ops)})
        folder = self.ops / "backups" / result["backup"]
        self.assertTrue(result["backup"].startswith("opspro_manual_"))
        for name in result["files"]:
            self.assertEqual((folder / name).read_bytes(), (self.ops / name).read_bytes())
        listed = [b["set"] for b in ops_store.backups(self.ops)]
        self.assertIn(result["backup"], listed)

    def test_works_on_a_folder_that_will_not_parse(self):
        (self.ops / "OperationsLocationRoster.xml").write_text("<operations-config><broken", encoding="utf-8")
        result = operations_pro.backup_now({"ops_dir": str(self.ops)})
        self.assertIn("OperationsLocationRoster.xml", result["files"])

    def test_running_jmri_is_a_note_not_a_refusal(self):
        with mock.patch.object(ops_store, "running_jmri", return_value=["java -jar jmri.jar"]):
            result = operations_pro.backup_now({"ops_dir": str(self.ops)})
        self.assertTrue(any("JMRI is running" in n for n in result["notes"]))

    def test_tool_is_listed(self):
        self.assertIn("ops_backup_now", [t.name for t in operations_pro.tools()])


# Runs under JMRI's jython: JMRI's own backup code lists the set and restores it.
BACKUP_PROBE = textwrap.dedent('''
    import json, os, shutil
    import java
    from jmri.util import FileUtil
    home = java.lang.System.getProperty("ops.home")
    FileUtil.setUserFilesPath(None, home + "/")
    job = json.loads(java.lang.System.getProperty("worker.job"))
    from jmri.jmrit.operations.setup.backup import DefaultBackup
    target = os.path.join(home, "operations", "backups", os.path.basename(job["set"]))
    shutil.copytree(job["set"], target)
    path = os.path.join(home, "operations", "OperationsCarRoster.xml")
    with open(path, "w") as handle:
        handle.write("changed")
    backup = DefaultBackup()
    out = {"sets": list(backup.getBackupSetList())}
    backup.restoreFilesFromSetName(os.path.basename(job["set"]))
    with open(path) as handle:
        out["restored"] = handle.read()
    with open(java.lang.System.getProperty("worker.out"), "w") as handle:
        json.dump(out, handle)
    java.lang.System.exit(0)
''')


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmriExtras(Extras):
    def saved(self):
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        return ops_data.load(keep), keep

    def test_everything_survives_a_jmri_load_and_save(self):
        self.write_pool_and_load()
        self.run_actions(
            CHANGE_AT_BRACKWATER,
            leg(train="BV1", leg=3, locos="helpers", start="Tolvern", end="East Staging", engines=2),
            leg(train="X99", leg=2, caboose="remove", start="Brackwater"),
            leg(train="BV2", leg=2, locos="add", start="Brackwater", end="Ashgrove", engines=1, caboose="change"),
            {"action": "set_engine_moves", "moves": {"BV101": 12, "BV102": -3}},
            {"action": "update_stop", "route": "Main East", "stop": "Ashgrove", "depart_time": "11:30", "wait": 25},
            {"action": "delete_load", "name": "Junk"})
        ours = self.rr()
        theirs, keep = self.saved()
        for name in ("BV1", "BV2", "X99"):
            self.assertEqual(ours.find_train(name).legs, theirs.find_train(name).legs, name)
        self.assertEqual(len(ours.find_train("BV1").legs), 2)
        self.assertEqual({e.id: e.moves for e in ours.engines.values()}, {e.id: e.moves for e in theirs.engines.values()})
        self.assertEqual(ours.routes, theirs.routes)
        self.assertEqual({k: sorted(x.name for x in v) for k, v in ours.loads.items()},
                         {k: sorted(x.name for x in v) for k, v in theirs.loads.items()})
        mine = {t.get("id"): t.get("minLength") for t in
                ET.parse(self.ops / "OperationsLocationRoster.xml").getroot().iter("track") if t.get("pool")}
        jmri = {t.get("id"): t.get("minLength") for t in
                ET.parse(keep / "OperationsLocationRoster.xml").getroot().iter("track") if t.get("pool")}
        self.assertEqual(mine, jmri)  # Track.load keeps minimums that exceed the pool, with no error.
        self.assertEqual(len([f for f in Gates(theirs).audit()["findings"]
                              if f["rule"] == "pool-minimum-over-length"]), 1)

    def write_pool_and_load(self):
        Pools.write_bad_pool(self)
        self.run_actions({"action": "add_load", "name": "Junk", "types": ["Boxcar"]})

    def test_jmri_changes_locomotives_where_the_leg_says(self):
        self.run_actions(CHANGE_AT_BRACKWATER)
        row = ops_jmri.run_worker(self.ops, {"build": True})["builds"]["BV1"]
        self.assertTrue(row["built"], row["message"])
        report = row["report_text"]
        self.assertIn("Locomotive change at (Brackwater), departs with 1 loco(s), model (GP9)", report)
        self.assertIn("Loco (BV 101) assigned to train, departs (West Staging)", report)
        self.assertIn("Loco (BV 103) assigned to train, departs (Brackwater)", report)

    def test_engine_moves_pick_the_locomotive(self):
        picked = {}
        for rested in ("BV103", "BV104"):
            self.setUp()
            self.run_actions({"action": "update_train", "train": "T10", "engines": 1, "engine_model": "GP9"},
                             {"action": "add_engine", "road": "BV", "number": "104", "model": "GP9",
                              "location": "Brackwater", "track": "Brackwater Yard B"},
                             {"action": "set_engine_moves", "moves": {rested: 50}})
            row = ops_jmri.run_worker(self.ops, {"build": True})["builds"]["T10"]
            self.assertTrue(row["built"], row["message"])
            picked[rested] = [n for n in ("BV 103", "BV 104")
                              if f"Loco ({n}) assigned to train" in row["report_text"]]
        self.assertEqual(picked, {"BV103": ["BV 104"], "BV104": ["BV 103"]})

    def test_jmri_backup_window_lists_and_restores_the_set(self):
        name = operations_pro.backup_now({"ops_dir": str(self.ops)})["backup"]
        with tempfile.TemporaryDirectory() as scratch:
            probe = Path(scratch) / "probe.py"
            probe.write_text(BACKUP_PROBE, encoding="utf-8")
            with mock.patch.object(ops_jmri, "WORKER", probe):
                result = ops_jmri.run_worker(self.ops, {"set": str(self.ops / "backups" / name)})
        self.assertIn(name, result["sets"])
        self.assertEqual(hashlib.sha256(result["restored"].encode("utf-8")).hexdigest(),
                         hashlib.sha256((self.ops / "OperationsCarRoster.xml").read_text(encoding="utf-8")
                                        .encode("utf-8")).hexdigest())


if __name__ == "__main__":
    unittest.main()
