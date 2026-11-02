"""Engine division, control limits, manifest and switch list creator paths, and the Trains window's build
messages and table action. Python tests against copies of the demo railroad, and real JMRI 5.16 where it is
installed: it must load and keep what was written, and a save must read back the same values.
"""
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_actions  # noqa: E402
import ops_jmri  # noqa: E402
from ops_store import Refused  # noqa: E402
from test_extras import Extras  # noqa: E402

DIVISIONS = ({"action": "add_division", "name": "North"}, {"action": "add_division", "name": "South"})
EVERYTHING = (
    *DIVISIONS,
    {"action": "set_engine_division", "division": "South", "engines": ["BV101", "BV102"]},
    {"action": "set_engine_division", "division": "North", "engines": ["BV102"]},
    {"action": "set_control_limits", "max_len_attribute": 16, "max_len_train_name": 30, "max_len_road_number": 8,
     "report_font_size": 12, "report_font_name": "Serif", "excel_wait_time": 60, "disable_print_if_custom": True,
     "speed_hpt": 40, "show_clones": False, "days": 14},
    {"action": "set_manifest_creator", "creator": "manifest", "directory": "csvOut", "program": "Mine.xlsx",
     "common_file": "Names.txt"},
    {"action": "set_manifest_creator", "creator": "switch_list", "directory": "csvSwitch"},
    {"action": "set_train_options", "build_messages": False, "train_action": "Terminate"})


def raw(path, query):
    return ET.parse(path).getroot().find(query)


class More(Extras):
    def engine(self, name):
        return next(e for e in ET.parse(self.ops / "OperationsEngineRoster.xml").getroot().iter("engine")
                    if e.get("id") == name)


class EngineDivision(More):
    def test_set_and_clear(self):
        self.run_actions(*DIVISIONS, {"action": "set_engine_division", "division": "South", "engines": ["BV101"]})
        self.assertEqual(self.engine("BV101").get("divisionId"), "2")
        self.assertEqual(self.rr().engines["BV101"].division_id, "2")
        self.assertIsNone(self.engine("BV102").get("divisionId"))
        self.run_actions({"action": "set_engine_division", "division": None, "engines": ["BV101"]})
        self.assertIsNone(self.engine("BV101").get("divisionId"))

    def test_attribute_sits_where_jmri_writes_it(self):
        self.run_actions(*DIVISIONS, {"action": "set_engine_division", "division": "North", "engines": ["BV101"]})
        keys = list(self.engine("BV101").attrib)
        self.assertLess(keys.index("locationId"), keys.index("divisionId"))
        self.assertLess(keys.index("divisionId"), keys.index("moves"))

    def test_refusals(self):
        self.assertIn("No division", self.refused({"action": "set_engine_division", "division": "Nowhere",
                                                    "engines": ["BV101"]}))
        self.assertIn("No engine", self.refused(*DIVISIONS, {"action": "set_engine_division", "division": "North",
                                                              "engines": ["ZZ9"]}))


class ControlLimits(More):
    def control(self, query):
        return raw(self.ops / "Operations.xml", f"./control/{query}")

    def test_written_where_control_store_puts_them(self):
        self.run_actions(EVERYTHING[4])
        self.assertEqual(self.control("maximumStringLengths/max_len_string_attibute").get("length"), "16")
        self.assertEqual(self.control("maximumStringLengths/max_len_string_train_name").get("length"), "30")
        self.assertEqual(self.control("reports").get("fontSize"), "12")
        self.assertEqual(self.control("actions").get("excelWaitTime"), "60")
        self.assertEqual(self.control("printOptions").get("disablePrintIfCustom"), "true")
        self.assertEqual(self.control("speedHpt").get("MPH"), "40")
        self.assertEqual(self.control("display").get("showClones"), "false")
        self.assertEqual(self.control("days").get("length"), "14")

    def test_read_model_and_name_limits_follow(self):
        self.run_actions(EVERYTHING[4])
        manifest = self.rr().manifest
        self.assertEqual(manifest["control max_len_train_name"].value, "30")
        self.assertTrue(manifest["control max_len_train_name"].in_file)
        self.assertEqual(manifest["control max_len_route_name"].value, "25")
        self.assertEqual(manifest["control speed_hpt"].value, "40")
        editor = ops_actions.Editor(self.ops)
        self.assertEqual(editor.name_limit("train"), 30)

    def test_refusals(self):
        for fields, word in (({}, "at least one"), ({"nope": 1}, "Unknown"), ({"max_len_attribute": 0}, "less than"),
                             ({"max_len_attribute": "x"}, "whole"), ({"report_font_size": 30}, "5 to 18"),
                             ({"speed_hpt": 0}, "less than"), ({"show_clones": "yes"}, "true or false")):
            self.assertIn(word, self.refused({"action": "set_control_limits", **fields}), fields)

    def test_a_file_with_no_control_section_gets_one_with_every_length(self):
        self.assertIsNone(raw(self.ops / "Operations.xml", "./control"))  # The demo has none.
        self.run_actions({"action": "set_control_limits", "max_len_route_name": 40, "days": 7})
        self.assertEqual(self.control("maximumStringLengths/max_len_string_route_name").get("length"), "40")
        self.assertEqual(self.control("maximumStringLengths/max_len_string_attibute").get("length"), "12")
        self.assertEqual(self.control("days").get("length"), "7")


class Creators(More):
    def creator(self, tag):
        node = raw(self.ops / "OperationsTrainRoster.xml", f"./options/{tag}")
        return [(c.tag, c.get("name")) for c in node]

    def test_all_three_children_in_jmri_order(self):
        self.run_actions(EVERYTHING[5], EVERYTHING[6])
        self.assertEqual(self.creator("manifestCreator"), [("directory", "csvOut"), ("runFile", "Mine.xlsx"),
                                                           ("commonFile", "Names.txt")])
        self.assertEqual(self.creator("switchlistCreator"), [("directory", "csvSwitch"), ("runFile", "MC4JMRI.xls"),
                                                             ("commonFile", "CSVFilesFile.txt")])
        shown = self.rr().manifest
        self.assertEqual(shown["creator manifest"].value,
                         {"directory": "csvOut", "program": "Mine.xlsx", "common_file": "Names.txt"})

    def test_defaults_shown_when_file_has_none(self):
        shown = self.rr().manifest["creator switch_list"]
        self.assertEqual(shown.value["directory"], "csvSwitchLists")

    def test_refusals(self):
        for fields, word in (({}, "at least one"), ({"directory": "../x"}, "Operations folder"),
                             ({"program": "a/b.xls"}, "plain file name"), ({"common_file": " "}, "blank"),
                             ({"creator": "other", "program": "a"}, "creator must be")):
            self.assertIn(word, self.refused({"action": "set_manifest_creator", **fields}), fields)


class TrainOptions(More):
    def test_written_and_read(self):
        self.run_actions(EVERYTHING[7])
        node = raw(self.ops / "OperationsTrainRoster.xml", "./options/trainOptions")
        self.assertEqual((node.get("buildMessages"), node.get("trainAction")), ("false", "Terminate"))
        shown = self.rr().manifest
        self.assertEqual((shown["build_messages"].value, shown["train_action"].value), ("false", "Terminate"))

    def test_refusals(self):
        self.assertIn("one of Move", self.refused({"action": "set_train_options", "train_action": "Run"}))
        self.assertIn("true or false", self.refused({"action": "set_train_options", "build_messages": "no"}))
        self.assertIn("Give", self.refused({"action": "set_train_options"}))


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmriMore(More):
    def test_everything_survives_a_jmri_load_and_save(self):
        self.run_actions(*EVERYTHING)
        theirs, keep = self.saved()
        for name in ("BV101", "BV102"):
            self.assertEqual(self.engine(name).get("divisionId"),
                             next(e for e in ET.parse(keep / "OperationsEngineRoster.xml").getroot().iter("engine")
                                  if e.get("id") == name).get("divisionId"), name)
        self.assertEqual(theirs.engines["BV102"].division_id, "1")
        self.assertEqual(theirs.engines["BV101"].division_id, "2")
        mine, jmri = self.ops / "Operations.xml", keep / "Operations.xml"
        for query in ("./control/maximumStringLengths", "./control/reports", "./control/actions",
                      "./control/printOptions", "./control/speedHpt", "./control/display", "./control/days"):
            self.assertEqual(ET.tostring(raw(mine, query)).split(), ET.tostring(raw(jmri, query)).split(), query)
        for tag in ("manifestCreator", "switchlistCreator", "trainOptions"):
            query = f"./options/{tag}"
            left = raw(self.ops / "OperationsTrainRoster.xml", query)
            right = raw(keep / "OperationsTrainRoster.xml", query)
            if tag == "trainOptions":  # The demo's file holds no other trainOptions attributes; JMRI adds them.
                self.assertEqual({k: right.get(k) for k in left.attrib}, dict(left.attrib))
                continue
            self.assertEqual(ET.tostring(left).split(), ET.tostring(right).split(), tag)

    def saved(self):
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        import ops_data
        return ops_data.load(keep), keep


if __name__ == "__main__":
    unittest.main()
