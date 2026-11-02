"""Train schedule days and manifest formats: the write actions, against copies of the demo railroad.

JMRI-backed tests run only where JMRI is installed: JMRI 5.16 loads what was written and saves
it, and our parser must read the same values back from JMRI's save.
"""
import shutil
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_data  # noqa: E402
import ops_gates  # noqa: E402
import ops_jmri  # noqa: E402
import ops_paperwork  # noqa: E402
import operations_pro  # noqa: E402
from ops_store import Refused  # noqa: E402
from test_write import Case  # noqa: E402  Only the base class: importing a test class would run it twice.

TRAIN_FILE = "OperationsTrainRoster.xml"
SETUP_FILE = "Operations.xml"

DAYS_PLAN = [
    {"action": "add_day", "name": "Wednesday", "comment": "Midweek", "trains": ["BV1", "T10"]},
    {"action": "add_day", "name": "Thursday"},
    {"action": "update_day", "day": "Thursday", "name": "Market Day", "comment": "Busy"},
    {"action": "set_day_trains", "day": "Monday", "trains": ["BV1", "BV2", "T30"]},
    {"action": "set_day_trains", "day": "Monday", "add": ["Y20"], "remove": ["BV2"]},
    {"action": "set_day_trains", "day": "Market Day", "from_build": True},
    {"action": "set_active_day", "name": "Wednesday"},
    {"action": "apply_day"},
    {"action": "set_line_days", "schedule": "Mill Receiving", "line": 1, "setout_day": "Monday",
     "pickup_day": "Market Day"},
]
MANIFEST_PLAN = [
    {"action": "set_manifest_options", "format": "two_column_track", "orientation": "landscape", "font_size": 12,
     "duplex": "two-sided-long-edge", "pickup_color": "#FF0000", "drop_color": "#663300", "local_color": "#123456",
     "tabs": True, "tab_length": 10, "manifest_tab_length": 5, "print_loads_and_empties": True,
     "print_valid": False, "use_12hr_format": True, "hazardous_message": "(HAZMAT)", "header_line_2": False,
     "logo": "preference:logo.png", "save_manifests": True, "csv_manifest": True,
     "switch_list_page": "per_visit", "switch_list_real_time": False, "missing_car_comment": "Look for these",
     "print_preview": True, "print_build_report": True},
    {"action": "set_manifest_format", "line": "pickup_car", "prefix": "PU",
     "fields": ["Road", "Number", "Tab", "Type", " ", "Load Type", "Destination"]},
    {"action": "set_manifest_format", "line": "drop_engine", "fields": ["Road", "Number", "Model", "HP"]},
    {"action": "set_manifest_format", "line": "missing_car", "fields": ["Road", "Number", "Last Location"]},
    {"action": "set_manifest_options", "switch_list_same_as_manifest": False, "switch_list_orientation": "portrait"},
    {"action": "set_manifest_format", "line": "switch_list_local", "prefix": "MV", "fields": ["Road", "Number"]},
    {"action": "set_manifest_text", "group": "manifest", "key": "valid", "text": "Good for {0}"},
    {"action": "set_manifest_text", "group": "manifest", "key": "trainTerminates", "text": "Ends at {0}, it''s done"},
    {"action": "set_manifest_text", "group": "switch_list", "key": "holdCar", "text": "Hold {1} {0}"},
    {"action": "set_manifest_text", "group": "header", "key": "road", "text": "Rd'"},
    {"action": "set_train_manifest", "train": "BV1", "railroad_name": "Lakeshore Lines", "logo": "preference:bv1.png",
     "show_times": False},
]


class Days(Case):
    def train_xml(self):
        return ET.parse(self.ops / TRAIN_FILE).getroot()

    def test_a_new_day_takes_the_next_id_and_jmris_train_list_form(self):
        self.edit({"action": "add_day", "name": "Wednesday", "trains": ["BV1", "T10"]})
        day = next(d for d in self.train_xml().iter("schedule") if d.get("name") == "Wednesday")
        self.assertEqual((day.get("id"), day.get("trainIds"), day.get("comment")), ("3", "1,3,", None))
        self.assertEqual(self.rr().days["3"].trains, ["1", "3"])

    def test_delete_train_writes_the_train_list_in_jmris_form(self):
        self.edit({"action": "add_day", "name": "Wednesday", "trains": ["BV1", "T10", "T30"]})
        self.edit({"action": "delete_train", "train": "T10"})
        day = next(d for d in self.train_xml().iter("schedule") if d.get("name") == "Wednesday")
        self.assertEqual(day.get("trainIds"), "1,6,")

    def test_a_day_deleted_by_hand_is_audited_as_any_day(self):
        text = (self.ops / "OperationsCarRoster.xml").read_text()
        (self.ops / "OperationsCarRoster.xml").write_text(text.replace('pickupId="2"', 'pickupId="42"', 1))
        hits = [f for f in ops_gates.Gates(self.rr()).audit()["findings"] if f["rule"] == "day-stale-id"]
        self.assertEqual([f["subject"] for f in hits], ["BVR 3012"])

    def test_names_are_checked(self):
        for name, why in (("Monday", "already exists"), ("  ", "needs a name"),
                          ("Any", "set_line_days .Any. would name this schedule")):
            with self.assertRaisesRegex(Refused, why):
                self.plan({"action": "add_day", "name": name})
        with self.assertRaisesRegex(Refused, "No train"):
            self.plan({"action": "add_day", "name": "Friday", "trains": ["Nope"]})

    def test_active_day_goes_where_jmri_reads_it_last(self):
        self.edit({"action": "set_active_day", "name": "Tuesday"})
        root = self.train_xml()
        self.assertEqual(root.find("trainScheduleOptions").get("activeId"), "2")
        self.assertEqual(root.find("./options/trainScheduleOptions").get("activeId"), "2")
        self.assertEqual(self.rr().active_schedule, "2")
        self.edit({"action": "set_active_day", "name": "any"})
        self.assertEqual(self.rr().active_schedule, "ANY")
        with self.assertRaisesRegex(Refused, "No train schedule"):
            self.plan({"action": "set_active_day", "name": "Sunday"})

    def test_the_root_active_id_wins_when_both_are_present(self):
        # TrainManager:1320 reads the old place, then TrainScheduleManager.load the root one.
        text = (self.ops / TRAIN_FILE).read_text()
        (self.ops / TRAIN_FILE).write_text(text.replace("  <schedules>", '  <trainScheduleOptions activeId="2" />\n'
                                                                           "  <schedules>", 1))
        self.assertEqual(self.rr().active_schedule, "2")

    def test_train_lists_and_apply(self):
        self.edit(*DAYS_PLAN)
        rr = self.rr()
        days = {d.name: d for d in rr.days.values()}
        ids = lambda names: [rr.find_train(n).id for n in names]  # noqa: E731
        self.assertEqual(days["Monday"].trains, ids(["BV1", "T30", "Y20"]))
        self.assertEqual(days["Wednesday"].trains, ids(["BV1", "T10"]))
        self.assertEqual(days["Market Day"].comment, "Busy")
        self.assertEqual(len(days["Market Day"].trains), len(rr.trains))  # Every demo train had Build on.
        self.assertEqual({t.name for t in rr.trains.values() if t.build}, {"BV1", "T10"})
        self.assertTrue(days["Wednesday"].active)
        item = rr.schedules["1"].items[0]
        self.assertEqual((item.setout_day, item.pickup_day), (days["Monday"].id, days["Market Day"].id))

    def test_apply_needs_one_active_day(self):
        self.edit({"action": "set_active_day", "name": "Any"})
        with self.assertRaisesRegex(Refused, "No single day is active"):
            self.plan({"action": "apply_day"})
        self.edit({"action": "apply_day", "day": "Tuesday"})
        self.assertFalse(any(t.build for t in self.rr().trains.values()))

    def test_schedule_lines_refuse_an_unknown_day(self):
        with self.assertRaisesRegex(Refused, "No train schedule 'Friday'"):
            self.plan({"action": "add_schedule", "name": "Late", "lines": [{"type": "Boxcar", "setout_day": "Friday"}]})
        with self.assertRaisesRegex(Refused, "No train schedule"):
            self.plan({"action": "set_line_days", "schedule": "Mill Receiving", "line": "1c1", "setout_day": "Friday"})
        with self.assertRaisesRegex(Refused, "Give setout_day"):
            self.plan({"action": "set_line_days", "schedule": "Mill Receiving", "line": 1})

    def test_delete_refuses_users_and_cleans_up_the_rest(self):
        with self.assertRaisesRegex(Refused, "last train schedule"):
            self.plan({"action": "delete_day", "day": "Monday"}, {"action": "delete_day", "day": "Tuesday"})
        self.edit({"action": "set_line_days", "schedule": "Cannery Line", "line": 2, "pickup_day": "Tuesday"},
                  {"action": "set_active_day", "name": "Tuesday"})
        with self.assertRaisesRegex(Refused, "Schedule lines use it in: Cannery Line"):
            self.plan({"action": "delete_day", "day": "Tuesday"})
        self.edit({"action": "delete_day", "day": "Tuesday", "clear_lines": True})
        rr = self.rr()
        self.assertEqual([d.name for d in rr.days.values()], ["Monday"])
        self.assertEqual(rr.schedules["2"].items[1].pickup_day, "")
        self.assertEqual(rr.cars["BVR3012"].pickup_day, "")  # Its pick up day was Tuesday.
        self.assertEqual(rr.active_schedule, "")

    def test_delete_refuses_automations_and_manual_builds(self):
        text = (self.ops / TRAIN_FILE).read_text()
        (self.ops / TRAIN_FILE).write_text(text.replace(
            "</schedules>", '</schedules>\n  <automations>\n    <automation id="1" name="Nightly" comment="">\n'
            '      <item id="1c1" sequenceId="1" actionCode="0" trainScheduleId="2" />\n'
            "    </automation>\n  </automations>"))
        with self.assertRaisesRegex(Refused, "automation Nightly"):
            self.plan({"action": "delete_day", "day": "Tuesday"})

    def test_default_days_and_an_empty_file(self):
        self.edit({"action": "add_default_days"})
        self.assertEqual([d.name for d in self.rr().days.values()],
                         ["Monday", "Tuesday", "Sunday", "Wednesday", "Thursday", "Friday", "Saturday"])

    def test_build_gate_says_when_a_day_disagrees_with_the_build_box(self):
        self.edit({"action": "set_day_trains", "day": "Monday", "trains": ["BV1"]})
        gates = ops_gates.Gates(self.rr())
        detail = lambda name: gates._train_gates(self.rr().find_train(name))[0][0]["reason"]  # noqa: E731
        self.assertIn("active day Monday does not list it, so Apply (apply_day) would turn Build off", detail("BV2"))
        self.assertNotIn("Apply", detail("BV1"))

    def test_days_list(self):
        rows = operations_pro.list_items({"ops_dir": str(self.ops), "type": "days"})
        self.assertEqual([(r["name"], r["active"]) for r in rows], [("Monday", True), ("Tuesday", False)])


class ManifestFormats(Case):
    def setup_xml(self):
        return ET.parse(self.ops / SETUP_FILE).getroot().find("operations")

    def test_options_are_checked(self):
        for fields, why in (({"colour": "red"}, "Unknown manifest options"),
                            ({"format": "three_column"}, "format must be one of"),
                            ({"font_size": 30}, "5 to 18"), ({"tab_length": 0}, "less than 1"),
                            ({"pickup_color": "teal"}, "colour must be"), ({"tabs": "yes"}, "true or false"),
                            ({"duplex": "both"}, "duplex must be one of"), ({"font": " "}, "font name"),
                            ({"switch_list_orientation": "landscape"}, "same as the manifest")):
            with self.assertRaisesRegex(Refused, why, msg=str(fields)):
                self.plan({"action": "set_manifest_options", **fields})

    def test_values_are_written_as_jmri_writes_them(self):
        self.edit({"action": "set_manifest_options", "pickup_color": "#ff0000", "drop_color": "#ABCDEF",
                   "orientation": "half_page", "switch_list_page": "per_train", "logo": "x.png"})
        ops = self.setup_xml()
        # A new element holds JMRI's default for every setting in it, as a JMRI save writes it.
        self.assertEqual(ops.find("manifestColors").attrib, {"pickupEngineColor": "black", "dropEngineColor": "black",
                                                             "pickupColor": "red", "dropColor": "#ABCDEF",
                                                             "localColor": "black"})
        self.assertEqual(ops.find("pageOrientation").attrib, {"manifest": "4.25 x 11", "switchList": "4.25 x 11"})
        self.assertEqual((ops.find("switchList").get("pageFormat"), ops.find("switchList").get("pageMode")),
                         ("pagePerTrain", "true"))
        self.edit({"action": "set_manifest_options", "switch_list_page": "normal", "logo": ""})
        ops = self.setup_xml()
        self.assertNotIn("pageMode", ops.find("switchList").attrib)
        self.assertIsNone(ops.find("manifestLogo"))
        names = [c.tag for c in ops]
        known = [n for n in names if n in ops_paperwork.SETUP_ORDER]
        self.assertEqual(known, sorted(known, key=ops_paperwork.SETUP_ORDER.index))

    def test_format_lines_are_checked(self):
        for action, why in (({"line": "pickup_car", "fields": ["Road", "Colour"]}, "'Colour' is not a field"),
                            ({"line": "pickup_car", "fields": ["Road", "Tab"]}, "need tabs on"),
                            ({"line": "pickup_engine", "fields": ["Road", "Load"]}, "'Load' is not a field"),
                            ({"line": "pickup_car", "fields": [" "]}, "at least one field"),
                            ({"line": "missing_car", "prefix": "X"}, "no prefix"),
                            ({"line": "switch_list_local", "fields": ["Road"]}, "same format as the manifest"),
                            ({"line": "pickup"}, "line must be one of")):
            with self.assertRaisesRegex(Refused, why, msg=str(action)):
                self.plan({"action": "set_manifest_format", **action})
        self.edit({"action": "set_manifest_options", "tabs": True},
                  {"action": "set_manifest_format", "line": "pickup_car", "fields": ["road", "Tab", "number"]})
        ops = self.setup_xml()
        self.assertEqual(ops.find("pickupCarFormat").get("setting"), "Road,Tab,Number,")
        # Same as manifest is on, so the switch list copy follows, as a JMRI save would write it.
        self.assertEqual(ops.find("switchListPickupCarFormat").attrib, ops.find("pickupCarFormat").attrib)

    def test_texts_are_checked_as_jmri_formats_them(self):
        for key, text, why in (("valid", "Valid {0", "numbered argument"), ("valid", "Valid {3}", "fills only {0}"),
                               ("valid", "Don't {0}", "write '' for an apostrophe")):
            with self.assertRaisesRegex(Refused, why):
                self.plan({"action": "set_manifest_text", "group": "manifest", "key": key, "text": text})
        with self.assertRaisesRegex(Refused, "No manifest text"):
            self.plan({"action": "set_manifest_text", "group": "manifest", "key": "nope", "text": "x"})
        self.edit({"action": "set_manifest_text", "group": "manifest", "key": "to", "text": "it's to"},
                  {"action": "set_manifest_text", "group": "manifest", "key": "valid", "text": "'{'{0}'}'"})
        self.assertEqual(self.rr().manifest_texts["manifest"]["to"], "it's to")
        self.edit({"action": "set_manifest_text", "group": "manifest", "key": "to"})
        root = ET.parse(self.ops / SETUP_FILE).getroot()
        self.assertEqual([c.tag for c in root.find("manifestTextStrings")], ["valid"])

    def test_train_manifest_and_list(self):
        self.edit({"action": "set_train_manifest", "train": "BV1", "railroad_name": "Lakeshore Lines",
                   "show_times": False})
        rr = self.rr()
        self.assertEqual(rr.train_manifests[rr.find_train("BV1").id],
                         ops_data.TrainManifest("BV1", "Lakeshore Lines", "", False))
        self.edit({"action": "set_train_manifest", "train": "BV1", "railroad_name": ""})
        self.assertIsNone(ET.parse(self.ops / TRAIN_FILE).getroot().find("./trains/train/railRoad"))
        rows = {r["name"]: r for r in operations_pro.list_items({"ops_dir": str(self.ops), "type": "manifest"})}
        self.assertEqual(rows["font_size"], {"name": "font_size", "value": "10", "in_file": False})
        self.assertEqual(rows["pickup_car"]["value"]["fields"][:2], ["Road", "Number"])
        self.assertEqual(rows["text header road"]["value"], "Road")


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmriDaysAndManifests(Case):
    def read_back(self, job=None, source=None):
        keep = Path(self.temp.name) / f"saved{len(list(Path(self.temp.name).glob('saved*')))}"
        keep.mkdir()
        result = ops_jmri.run_worker(source or self.ops, job or {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        return result, keep

    def test_days_survive_a_jmri_load_and_save(self):
        self.edit(*DAYS_PLAN)
        ours = self.rr()
        _, keep = self.read_back()
        theirs = ops_data.load(keep)
        self.assertEqual(ours.days, theirs.days)
        self.assertEqual(ours.active_schedule, theirs.active_schedule)
        self.assertEqual({t.id: t.build for t in ours.trains.values()}, {t.id: t.build for t in theirs.trains.values()})
        self.assertEqual(ours.schedules["1"].items, theirs.schedules["1"].items)

    def test_a_day_set_on_a_file_jmri_saved_is_the_one_jmri_reads(self):
        # A JMRI save holds the active id at the root; one written only under options would be overridden.
        _, keep = self.read_back()
        shutil.rmtree(self.ops)
        shutil.copytree(keep, self.ops)
        self.edit({"action": "set_active_day", "name": "Tuesday"})
        _, again = self.read_back()
        self.assertEqual(ops_data.load(again).active_schedule, "2")

    def test_a_deleted_day_leaves_nothing_behind_in_jmri(self):
        self.edit({"action": "set_line_days", "schedule": "Cannery Line", "line": 2, "setout_day": "Tuesday"},
                  {"action": "set_active_day", "name": "Tuesday"},
                  {"action": "delete_day", "day": "Tuesday", "clear_lines": True})
        ours = self.rr()
        _, keep = self.read_back()
        theirs = ops_data.load(keep)
        self.assertEqual((ours.days, ours.active_schedule), (theirs.days, theirs.active_schedule))
        self.assertEqual(ours.schedules["2"].items, theirs.schedules["2"].items)
        self.assertEqual(theirs.cars["BVR3012"].pickup_day, "")

    def test_a_train_deleted_from_a_day_list_survives_a_jmri_save(self):
        self.edit({"action": "add_day", "name": "Wednesday", "trains": ["BV1", "T10", "T30"]},
                  {"action": "delete_train", "train": "T10"})
        ours = self.rr()
        _, keep = self.read_back()
        theirs = ops_data.load(keep)
        self.assertEqual(ours.days, theirs.days)
        day = next(d for d in ET.parse(keep / TRAIN_FILE).getroot().iter("schedule") if d.get("name") == "Wednesday")
        self.assertEqual(day.get("trainIds"), "1,6,")

    def test_manifest_formats_survive_a_jmri_load_and_save(self):
        self.edit(*MANIFEST_PLAN)
        ours = self.rr()
        _, keep = self.read_back()
        theirs = ops_data.load(keep)
        for name, setting in ours.manifest.items():
            self.assertEqual(setting.value, theirs.manifest[name].value, name)
        self.assertEqual(ours.manifest_texts, theirs.manifest_texts)
        self.assertEqual(ours.train_manifests, theirs.train_manifests)
        # Everything we wrote JMRI kept as written, attribute by attribute.
        mine, jmri = ET.parse(self.ops / SETUP_FILE).getroot(), ET.parse(keep / SETUP_FILE).getroot()
        for node in mine.find("operations"):
            other = jmri.find(f"operations/{node.tag}")
            self.assertIsNotNone(other, node.tag)
            for attr, value in node.attrib.items():
                self.assertEqual(other.get(attr), value, f"{node.tag}.{attr}")

    def test_jmri_prints_the_manifest_with_the_new_formats(self):
        self.edit({"action": "set_manifest_format", "line": "pickup_car", "prefix": "GRAB",
                   "fields": ["Road", "Number", "Load Type"]},
                  {"action": "set_manifest_text", "group": "manifest", "key": "valid", "text": "Good for {0}"},
                  {"action": "set_train_manifest", "train": "BV1", "railroad_name": "Lakeshore Lines"})
        result, keep = self.read_back({"build": True})
        self.assertTrue(result["builds"]["BV1"]["built"])
        text = (keep / "manifests" / "train (BV1).txt").read_text(encoding="utf-8", errors="replace")
        self.assertIn("Lakeshore Lines", text)
        self.assertIn("Good for ", text)
        self.assertRegex(text, r"GRAB\s+BVR\s+\d+\s+(Load|Empty)")


if __name__ == "__main__":
    unittest.main()
