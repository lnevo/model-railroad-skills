"""Faults found by building a whole railroad from a blank folder with these tools. Only RealJmri starts JMRI."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import operations_pro  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_actions import ACTIONS, Editor, field_list  # noqa: E402
from ops_store import Refused  # noqa: E402

SHOWCASE = ROOT / "examples" / "showcase" / "operations"
START = [
    {"action": "add_car_type", "name": "Tank"},
    {"action": "add_car_type", "name": "Ore Jenny"},
    {"action": "add_load", "types": ["Tank"], "name": "Acid"},
    {"action": "add_location", "name": "Ashby"},
    {"action": "add_location", "name": "Brook"},
    {"action": "add_track", "location": "Ashby", "name": "Ashby Yard", "type": "Yard", "length": 500},
    {"action": "add_track", "location": "Brook", "name": "Brook Yard", "type": "Yard", "length": 500},
]
LINES = [{"type": "Tank", "receive": "E", "ship": "Acid"}]


class Blank(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.ed = Editor(Path(scratch.name))
        self.ed.run(START)

    def run_one(self, action, **fields):
        return self.ed.run([{"action": action, **fields}])[0]


class Flags(Blank):
    def stop(self, value):
        self.run_one("add_route", name=f"R {value}", stops=[{"location": "Ashby", "pickups": value, "drops": value}])
        return self.ed.route(f"R {value}").find("location")

    def test_yes_and_no_text_is_read_as_it_says(self):
        self.assertEqual(self.stop("no").get("pickups"), "no")
        self.assertEqual(self.stop("yes").get("drops"), "yes")
        self.assertEqual(self.stop(False).get("pickups"), "no")

    def test_other_text_is_refused_not_read_as_yes(self):
        with self.assertRaisesRegex(Refused, "pickups.*true or false"):
            self.stop("nope")

    def test_a_train_flag_given_as_text_false_stays_false(self):
        self.run_one("add_route", name="R1", stops=[{"location": "Ashby"}])
        self.run_one("add_train", name="T1", route="R1", to_terminal="false")
        self.assertEqual(self.ed.train("T1").get("toTerminal"), "false")

    def test_a_car_flag_given_as_text_false_stays_off(self):
        self.run_one("add_car", road="AB", number="1", type="Tank", length=40, hazardous="false")
        self.assertIsNone(self.ed.car("AB1").get("hazardous"))


class Industries(Blank):
    def test_a_second_spur_of_the_same_name_is_told_to_name_its_schedule(self):
        self.run_one("add_industry", location="Ashby", name="Unload", length=100, lines=LINES)
        with self.assertRaisesRegex(Refused, "schedule"):
            self.run_one("add_industry", location="Brook", name="Unload", length=100, lines=LINES)

    def test_a_schedule_name_gives_each_industry_its_own_lines(self):
        self.run_one("add_industry", location="Ashby", name="Unload", length=100, lines=LINES)
        self.run_one("add_industry", location="Brook", name="Unload", length=100, lines=LINES, schedule="Brook Unload")
        self.assertEqual(self.ed.track("Unload", "Brook").get("schedule"), "Brook Unload")
        self.assertNotEqual(self.ed.track("Unload", "Brook").get("scheduleId"),
                            self.ed.track("Unload", "Ashby").get("scheduleId"))

    def test_sharing_a_schedule_is_asked_for_and_takes_no_lines(self):
        self.run_one("add_industry", location="Ashby", name="Unload", length=100, lines=LINES)
        self.run_one("add_industry", location="Brook", name="Unload", length=100, types=["Tank"],
                     schedule="Unload Schedule", share_schedule=True)
        self.assertEqual(self.ed.track("Unload", "Brook").get("scheduleId"),
                         self.ed.track("Unload", "Ashby").get("scheduleId"))
        with self.assertRaisesRegex(Refused, "lines"):
            self.run_one("add_industry", location="Ashby", name="Other", length=100, lines=LINES,
                         schedule="Unload Schedule", share_schedule=True)

    def test_pick_up_and_set_out_lists_go_in_one_step(self):
        self.run_one("add_route", name="R1", stops=[{"location": "Ashby"}])
        self.run_one("add_train", name="T1", route="R1")
        self.run_one("add_industry", location="Ashby", name="Unload", length=100, lines=LINES,
                     pickup={"option": "trains", "names": ["T1"]}, drop={"option": "trains", "names": ["T1"]})
        track = self.ed.track("Unload")
        self.assertEqual((track.get("pickupOption"), track.get("dropOption")), ("trains", "trains"))

    def test_hold_custom_with_no_schedule_says_why_and_what_to_do(self):
        """Track.store writes the flag only with a schedule (Track:2935-2943), so JMRI would drop it on save."""
        with self.assertRaisesRegex(Refused, "add_industry"):
            self.run_one("add_track", location="Ashby", name="Bare", type="Spur", length=100, hold_custom=True)

    def test_a_schedule_mode_still_needs_a_schedule(self):
        with self.assertRaisesRegex(Refused, "need a schedule"):
            self.run_one("add_track", location="Ashby", name="Bare", type="Spur", length=100, schedule_mode="match")


class Interchanges(Blank):
    def setUp(self):
        super().setUp()
        self.run_one("add_location", name="Cross")
        self.run_one("add_track", location="Cross", name="Swap", type="Interchange", length=200)
        self.run_one("add_route", name="R1", stops=[{"location": "Cross"}])
        self.run_one("add_train", name="T1", route="R1")

    def test_the_track_list_shape_works_here_too(self):
        self.run_one("setup_interchange", track="Swap", set_out_by={"option": "trains", "names": ["T1"]},
                     pulled_by={"option": "excludeTrains", "names": ["T1"]},
                     destinations={"option": "Include", "names": ["Ashby"]})
        track = self.ed.track("Swap")
        self.assertEqual((track.get("dropOption"), track.get("pickupOption")), ("trains", "excludeTrains"))
        self.assertEqual(track.get("trackDestinationOption"), "Include")

    def test_destinations_can_say_all(self):
        self.run_one("setup_interchange", track="Swap", destinations=["Ashby"])
        self.run_one("setup_interchange", track="Swap", destinations={"option": "All"})
        self.assertIn(self.ed.track("Swap").get("trackDestinationOption"), (None, "All"))

    def test_plain_lists_still_work(self):
        self.run_one("setup_interchange", track="Swap", set_out_by=["T1"])
        self.assertEqual(self.ed.track("Swap").get("dropOption"), "trains")


class Setup(Blank):
    def test_the_railroad_name_can_be_set_on_a_blank_file(self):
        self.run_one("set_option", group="railroad", name="name", value="Ashby & Brook")
        operations = self.ed.docs["Operations.xml"].root.find("operations")
        self.assertEqual(operations[0].tag, "railRoad")
        self.assertEqual(operations[0].get("name"), "Ashby & Brook")
        self.run_one("set_option", group="railRoad", name="name", value="Second")
        self.assertEqual(len(operations.findall("railRoad")), 1)
        self.assertEqual(operations[0].get("name"), "Second")

    def test_scale_takes_the_name_on_the_settings_window(self):
        self.run_one("set_option", group="settings", name="scale", value="HOn3")
        settings = self.ed.docs["Operations.xml"].root.find("./operations/settings")
        self.assertEqual(settings.get("scale"), "4")
        self.run_one("set_option", group="settings", name="scale", value="g 1/24")
        self.assertEqual(settings.get("scale"), "12")
        self.run_one("set_option", group="settings", name="scale", value=6)
        self.assertEqual(settings.get("scale"), "6")

    def test_an_unknown_scale_lists_the_names(self):
        with self.assertRaisesRegex(Refused, "HOn3"):
            self.run_one("set_option", group="settings", name="scale", value="H0")

    def test_a_scale_number_jmri_does_not_have_is_refused(self):
        with self.assertRaisesRegex(Refused, "HOn3"):
            self.run_one("set_option", group="settings", name="scale", value=13)

    def test_startup_automation_none_clears_it(self):
        self.run_one("add_automation", name="Night", steps=[{"do": "counter"}])
        self.run_one("set_startup_automation", automation="Night")
        self.assertIn("No automation", self.run_one("set_startup_automation", automation="None"))

    def test_an_automation_called_none_can_still_be_chosen(self):
        self.run_one("add_automation", name="None", steps=[{"do": "counter"}])
        self.assertIn("will run", self.run_one("set_startup_automation", automation="None"))


class Cars(Blank):
    def setUp(self):
        super().setUp()
        self.run_one("add_car", road="AB", number="1", type="Tank", length=40)

    def test_a_car_type_can_be_changed(self):
        self.run_one("update_car", car="AB1", type="Ore Jenny")
        self.assertEqual(self.ed.car("AB1").get("type"), "Ore Jenny")

    def test_a_custom_load_the_new_type_lacks_is_refused(self):
        self.run_one("update_car", car="AB1", load="Acid")
        with self.assertRaisesRegex(Refused, "Acid"):
            self.run_one("update_car", car="AB1", type="Ore Jenny")

    def test_type_and_load_change_together_whatever_the_order(self):
        self.run_one("update_car", car="AB1", load="Acid")
        self.run_one("update_car", car="AB1", load="E", type="Ore Jenny")
        self.assertEqual((self.ed.car("AB1").get("type"), self.ed.car("AB1").get("load")), ("Ore Jenny", "E"))

    def test_a_track_that_refuses_the_new_type_refuses_the_change(self):
        self.run_one("add_track", location="Ashby", name="Tanks", type="Spur", length=100, types=["Tank"])
        self.run_one("place_car", car="AB1", location="Ashby", track="Tanks")
        with self.assertRaisesRegex(Refused, "does not take Ore Jenny"):
            self.run_one("update_car", car="AB1", type="Ore Jenny")
        self.run_one("update_car", car="AB1", type="Ore Jenny", force=True)


class Help(unittest.TestCase):
    def test_every_action_list_is_json(self):
        self.assertEqual(len(json.loads(json.dumps(operations_pro.action_help({})))), len(ACTIONS))
        json.dumps(operations_pro.action_help({"session_only": True}))

    def test_update_car_lists_what_it_takes(self):
        names = {row["name"] for row in field_list("update_car")}
        self.assertLessEqual({"type", "load", "force", "return_when_empty", "return_when_loaded"}, names)

    def test_add_car_lists_load(self):
        self.assertIn("load", {row["name"] for row in field_list("add_car")})

    def test_a_track_given_as_the_location_says_which_is_which(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        ed = Editor(Path(scratch.name))
        ed.run(START)
        with self.assertRaisesRegex(Refused, "Ashby Yard is a track at Ashby"):
            ed.run([{"action": "add_engine", "road": "AB", "number": "1", "model": "GP38",
                     "location": "Ashby Yard", "track": "Ashby Yard"}])


class Listing(unittest.TestCase):
    def rows(self, kind, **more):
        return operations_pro.list_items({"ops_dir": str(SHOWCASE), "type": kind, **more})

    def test_settings_are_listed(self):
        out = self.rows("settings")
        self.assertIn("buildOptions", out)
        self.assertIn("router", out)
        self.assertIn("railroad", out)

    def test_settings_filter_by_group(self):
        self.assertEqual(set(self.rows("settings", filter="router")), {"railroad", "router"})

    def test_cars_carry_names_beside_ids(self):
        car = next(c for c in self.rows("cars") if c["location_id"])
        self.assertTrue(car["location"])
        self.assertTrue(car["track"])
        self.assertNotEqual(car["location"], car["location_id"])

    def test_the_car_filter_matches_a_location_name(self):
        car = next(c for c in self.rows("cars") if c["location_id"])
        found = self.rows("cars", filter=car["location"])
        self.assertTrue(found)
        self.assertTrue(all(car["location"].lower() in c["location"].lower() or car["location"].lower()
                            in " ".join(str(v) for v in c.values()).lower() for c in found))

    def test_trains_show_what_the_edit_window_shows(self):
        train = self.rows("trains")[0]
        self.assertLessEqual({"description", "departs", "comment", "route", "engine_road", "engine_model"}, set(train))
        self.assertRegex(train["departs"], r"^\d\d:\d\d$")

    def test_tracks_show_locomotive_types(self):
        self.assertTrue(any(t["loco_types"] for t in self.rows("tracks")))

    def test_no_type_says_what_is_wanted(self):
        with self.assertRaisesRegex(ValueError, "type must be one of"):
            operations_pro.list_items({"ops_dir": str(SHOWCASE)})


class Output(unittest.TestCase):
    def test_a_long_plan_counts_findings_per_rule(self):
        findings = [{"rule": "load-no-train", "severity": "error", "subject": str(n), "message": f"m{n}"} for n in range(9)]
        findings.append({"rule": "other", "severity": "warning", "subject": "x", "message": "m"})
        out = operations_pro.brief_plan({"new_findings": findings, "changed": True})
        self.assertEqual(out["new_findings_by_rule"]["load-no-train"]["count"], 9)
        self.assertEqual(out["new_findings_by_rule"]["load-no-train"]["example"], "m0")
        self.assertEqual(len(out["new_findings"]), 1)
        self.assertEqual(out["new_findings"][0]["rule"], "other")

    def test_a_short_plan_stays_as_it_was(self):
        result = {"new_findings": [{"rule": "r", "severity": "error", "subject": "s", "message": "m"}], "changed": True}
        self.assertEqual(operations_pro.brief_plan(result), result)

    def test_failing_only_drops_the_gates_not_checked(self):
        gates = [{"status": s} for s in ("pass", "fail", "not_checked", "not_checked")]
        out = operations_pro._brief({"gates": gates, "router": {}, "other_trains": []})
        self.assertEqual(out["gates"], [{"status": "fail"}])
        self.assertEqual((out["gates_passed"], out["gates_not_checked"]), (1, 2))

    def test_the_first_apply_on_a_blank_folder_says_why_there_is_no_backup(self):
        with tempfile.TemporaryDirectory() as scratch:
            planned = ops_store.plan(scratch, [{"action": "add_car_type", "name": "Tank"}])
            out = ops_store.apply(planned["plan_id"], True)
        self.assertNotIn("backup", out)
        self.assertIn("nothing to back up", out["backup_note"])


class LogLines(unittest.TestCase):
    def test_the_overflow_line_is_counted_not_listed(self):
        lines = ["2026 ERROR - Schedule missing for car (AB 1) to spur (Ashby, Off Spot) [main]", "2026 ERROR - Real"]
        errors, notes = ops_jmri.split_log(lines)
        self.assertEqual(errors, ["2026 ERROR - Real"])
        self.assertEqual(notes[0]["count"], 1)
        self.assertIn("alternate", notes[0]["means"])


class Order(unittest.TestCase):
    def test_every_shape_comes_to_one_step(self):
        self.assertEqual(ops_jmri.order_steps(["A", ["B", "C"], {"trains": ["A"], "terminate": False}], {"A", "B", "C"}, True),
                         [{"trains": ["A"], "terminate": True}, {"trains": ["B", "C"], "terminate": True},
                          {"trains": ["A"], "terminate": False}])

    def test_an_unknown_train_is_named(self):
        with self.assertRaisesRegex(Refused, "NOPE"):
            ops_jmri.order_steps(["NOPE"], {"A"}, True)

    def test_an_empty_order_is_refused(self):
        with self.assertRaises(Refused):
            ops_jmri.order_steps([], {"A"}, True)

    def test_a_train_built_and_left_built_cannot_be_built_again_later(self):
        with self.assertRaisesRegex(Refused, "still built"):
            ops_jmri.order_steps([{"trains": ["A"], "terminate": False}, "A"], {"A"}, True)


@unittest.skipUnless(ops_jmri.jmri_home(), "needs JMRI")
class RealJmri(unittest.TestCase):
    def copy(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        folder = Path(scratch.name) / "operations"
        shutil.copytree(SHOWCASE, folder)
        return folder

    def test_an_order_hands_cars_from_one_step_to_the_next(self):
        """Each swap train takes the cars the other left, which a build from one start state can never show."""
        out = ops_jmri.dry_run(SHOWCASE, order=[["SWAP-E", "SWAP-W"], ["SWAP-E", "SWAP-W"]])
        first, second = [s["trains"]["SWAP-E"] for s in out["steps"]]
        self.assertTrue(first["terminated"])
        self.assertTrue(first["cars"][0].startswith("SWPX1 "))
        self.assertTrue(second["cars"][0].startswith("SWPX11 "))
        self.assertEqual(second["set_outs"], {"East Staging / East Swap": 6})
        self.assertIn("report", second)

    def test_a_startup_automation_finishes_first_and_is_listed(self):
        folder = self.copy()
        ops_store.quick(folder, [], prepare=lambda ed: (ed.run([
            {"action": "update_automation", "automation": "Evening Session", "steps": [
                {"do": "build_train", "train": "LOCAL-B"}, {"do": "terminate_train", "train": "LOCAL-B"}]},
            {"action": "set_startup_automation", "automation": "Evening Session"}]), ()))
        out = ops_jmri.dry_run(folder, trains=["LOCAL-H"])
        trace = out["startup_automation"]
        self.assertEqual(trace["name"], "Evening Session")
        self.assertEqual([(s["train"], s["ran"], s["ok"]) for s in trace["steps"]],
                         [("LOCAL-B", True, True), ("LOCAL-B", True, True)])
        self.assertEqual(list(out["builds"]), ["LOCAL-H"])

    def test_jmri_keeps_the_railroad_name_and_scale(self):
        folder = self.copy()
        ops_store.quick(folder, [], prepare=lambda ed: (ed.run([
            {"action": "set_option", "group": "railroad", "name": "name", "value": "Ashby & Brook"},
            {"action": "set_option", "group": "settings", "name": "scale", "value": "N"}]), ()))
        keep = folder.parent / "kept"
        keep.mkdir()
        ops_jmri.run_worker(folder, {"save": True}, keep)
        out = operations_pro.list_items({"ops_dir": str(keep), "type": "settings", "filter": "settings"})
        self.assertEqual((out["railroad"], out["settings"]["scale"]), ("Ashby & Brook", "2"))


if __name__ == "__main__":
    unittest.main()
