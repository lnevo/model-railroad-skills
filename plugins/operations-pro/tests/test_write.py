"""Write actions and the transaction, against copies of the demo railroad.

JMRI-backed tests run only where JMRI is installed. They hold the writers to real JMRI:
it must load what was written, and a JMRI save must keep it.
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

import ops_actions  # noqa: E402
import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
import ops_store  # noqa: E402
from ops_store import Doc, Refused  # noqa: E402

DEMO = ROOT / "tests" / "fixtures" / "demo" / "operations"

# One plan that uses most actions, for the JMRI read-back.
EVERYTHING = [
    {"action": "add_car_type", "name": "Autorack", "like": "Flatcar"},
    {"action": "add_load", "name": "Autos", "types": ["Autorack"], "priority": "High", "hazardous": True},
    {"action": "add_load", "name": "Racks", "types": ["Autorack"], "load_type": "Empty"},
    {"action": "add_location", "name": "Harbor Point", "directions": "East/West"},
    {"action": "add_track", "location": "Harbor Point", "name": "Harbor Yard", "type": "Yard", "length": 300,
     "moves": 7},
    {"action": "add_track", "location": "Harbor Point", "name": "Harbor CI", "type": "Interchange", "length": 200},
    {"action": "add_industry", "location": "Harbor Point", "name": "Auto Plant", "length": 200,
     "alternate": "Harbor Yard",
     "lines": [{"type": "Autorack", "receive": "Racks", "ship": "Autos"},
               {"type": "Autorack", "receive": "Autos", "ship": "Racks", "wait": 2, "count": 2}]},
    {"action": "add_track", "location": "Harbor Point", "name": "Storage", "type": "Spur", "length": 200},
    {"action": "mirror_schedule", "spur": "Storage", "location": "Harbor Point", "sources": ["Auto Plant"]},
    {"action": "add_route", "name": "Harbor Turn",
     "stops": [{"location": "Brackwater", "direction": "East", "max_moves": 8},
               {"location": "Harbor Point", "direction": "East", "local_moves": False},
               {"location": "Brackwater", "direction": "West", "drops": True}]},
    {"action": "update_stop", "route": "Harbor Turn", "stop": 3, "max_length": 800},
    {"action": "add_train", "name": "H1", "route": "Harbor Turn", "description": "Harbor job",
     "roads": {"option": "Include", "names": ["BVR"]}, "depart_hour": "09"},
    {"action": "add_train", "name": "H2", "route": "Harbor Turn", "like": "BV1"},
    {"action": "set_train_skips", "train": "H2", "stops": ["Harbor Point"]},
    {"action": "setup_interchange", "track": "Harbor CI", "location": "Harbor Point", "set_out_by": ["H1"],
     "pulled_by": ["H2"], "routed_only": True, "destinations": ["Brackwater"]},
    {"action": "update_track", "track": "Auto Plant", "location": "Harbor Point", "reservation_factor": 80,
     "roads": {"option": "Exclude", "names": ["QXR"]}, "loads": {"option": "Include", "names": ["Autos", "Racks"]},
     "priority": "High", "blocking_order": 2, "ignore_used_percent": 25, "load_options": ["disable_load_change"]},
    {"action": "add_car", "road": "BVR", "number": "9001", "type": "Autorack", "length": 89, "location": "Harbor Point",
     "track": "Harbor Yard", "color": "Silver", "owner": "New Owner", "built": "1965"},
    {"action": "add_car", "road": "BVR", "number": "9002", "type": "Autorack", "length": 89, "location": "Harbor Point",
     "track": "Harbor Yard", "load": "Racks",
     "return_when_empty": {"destination": "Harbor Point", "track": "Auto Plant", "load": "Racks"}},
    {"action": "set_kernel", "name": "Racks Pair", "cars": ["BVR9001", "BVR9002"], "lead": "BVR9001"},
    {"action": "set_track_moves", "moves": {"Harbor Yard": 12}},
    {"action": "setup_custom_staging", "track": "West Stage 1", "location": "West Staging"},
    {"action": "set_active_day", "name": "Tuesday"},
    {"action": "set_option", "group": "router", "name": "carRoutingViaStaging", "value": True},
]


class Case(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ops = Path(self.temp.name) / "operations"
        shutil.copytree(DEMO, self.ops)
        env = mock.patch.dict(os.environ, {"OPS_PLAN_DIR": str(Path(self.temp.name) / "plans")})
        env.start()
        self.addCleanup(env.stop)
        stopped = mock.patch.object(ops_store, "running_jmri", return_value=[])
        stopped.start()
        self.addCleanup(stopped.stop)

    def plan(self, *actions):
        return ops_store.plan(self.ops, list(actions))

    def edit(self, *actions):
        return ops_store.apply(self.plan(*actions)["plan_id"])

    def rr(self):
        return ops_data.load(self.ops)

    def track(self, name):
        return self.rr().find_track(name)

    def snapshot(self):
        return {p.name: p.read_bytes() for p in self.ops.glob("*.xml")}


class RoundTrip(Case):
    def test_unedited_files_render_byte_for_byte(self):
        for path in self.ops.glob("*.xml"):
            self.assertEqual(Doc(path).render(), path.read_bytes(), path.name)

    def test_windows_line_endings_survive_an_edit(self):
        path = self.ops / "OperationsCarRoster.xml"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
        self.assertEqual(Doc(path).render(), path.read_bytes())
        self.edit({"action": "add_car_type", "name": "Autorack"})
        self.assertNotIn(b"\n", path.read_bytes().replace(b"\r\n", b""))


class Transaction(Case):
    ADD = {"action": "add_car_type", "name": "Autorack", "like": "Flatcar"}

    def test_plan_leaves_files_alone_and_shows_only_real_changes(self):
        before = self.snapshot()
        result = self.plan(self.ADD)
        self.assertEqual(self.snapshot(), before)
        added = [x for x in result["diff"].splitlines() if x.startswith(("+", "-")) and x[1:3] not in ("++", "--")]
        self.assertTrue(all("Autorack" in line for line in added), added)

    def test_apply_writes_only_changed_files_and_keeps_a_backup_jmri_can_see(self):
        before = self.snapshot()
        result = self.edit(self.ADD)
        self.assertEqual(sorted(result["files"]), ["OperationsCarRoster.xml", "OperationsLocationRoster.xml"])
        self.assertEqual(self.snapshot()["OperationsRouteRoster.xml"], before["OperationsRouteRoster.xml"])
        saved = self.ops / "backups" / result["backup"]
        self.assertEqual({p.name: p.read_bytes() for p in saved.glob("*.xml")}, before)

    def test_refused_while_jmri_runs(self):
        result = self.plan(self.ADD)
        with mock.patch.object(ops_store, "running_jmri", return_value=["java jmri.jar"]):
            with self.assertRaisesRegex(Refused, "JMRI is running"):
                ops_store.apply(result["plan_id"])
        self.assertIn("Autorack".encode(), (Path(os.environ["OPS_PLAN_DIR"]) / result["plan_id"] / "after"
                                            / "OperationsCarRoster.xml").read_bytes())
        self.assertNotIn(b"Autorack", (self.ops / "OperationsCarRoster.xml").read_bytes())

    def test_process_detection(self):
        listing = "/usr/bin/java -cp /Applications/JMRI/jmri.jar apps.gui3.dp3.PanelPro\n/bin/zsh\nvim notes-jmri.txt\n"
        self.assertEqual(len(REAL_RUNNING(listing)), 1)

    def test_refused_if_files_changed_after_the_plan(self):
        result = self.plan(self.ADD)
        path = self.ops / "OperationsTrainRoster.xml"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(Refused, "changed after"):
            ops_store.apply(result["plan_id"])

    def test_a_plan_is_used_once(self):
        result = self.plan(self.ADD)
        ops_store.apply(result["plan_id"])
        with self.assertRaisesRegex(Refused, "No plan"):
            ops_store.apply(result["plan_id"])

    def test_refused_while_a_train_is_built(self):
        path = self.ops / "OperationsTrainRoster.xml"
        path.write_text(path.read_text().replace('built="false"', 'built="true"', 1))
        with self.assertRaisesRegex(Refused, "BV1"):
            self.plan(self.ADD)

    def test_audit_failure_after_writing_restores_every_file(self):
        before = self.snapshot()
        result = self.plan(self.ADD)
        real = ops_store._audit
        calls = []

        def worse(directory):
            calls.append(directory)
            keys, findings = real(directory)
            if len(calls) == 2:
                bad = {"rule": "x", "severity": "error", "subject": "s", "message": "broken", "fix": {}}
                return keys | {("x", "s", "broken")}, findings + [bad]
            return keys, findings

        with mock.patch.object(ops_store, "_audit", worse):
            with self.assertRaisesRegex(Refused, "Change undone"):
                ops_store.apply(result["plan_id"])
        self.assertEqual(self.snapshot(), before)

    def test_a_plan_adding_audit_errors_is_blocked(self):
        result = self.plan({"action": "update_track", "track": "Ashgrove Feed Mill", "schedule": "Elevator"})
        self.assertTrue(result["blocked"])
        with self.assertRaisesRegex(Refused, "blocked"):
            ops_store.apply(result["plan_id"])
        self.assertTrue(ops_store.apply(result["plan_id"], allow_new_errors=True)["applied"])

    def test_restore_returns_the_set_and_saves_the_state_it_replaced(self):
        before = self.snapshot()
        result = self.edit(self.ADD)
        changed = self.snapshot()
        restored = ops_store.restore(self.ops, result["backup"])
        self.assertEqual(self.snapshot(), before)
        saved = self.ops / "backups" / restored["backup_of_previous_state"]
        self.assertEqual({p.name: p.read_bytes() for p in saved.glob("*.xml")}, changed)
        self.assertEqual(ops_store.backups(self.ops)[0]["folder"], "backups")

    def test_restore_refuses_a_path(self):
        with self.assertRaises(Refused):
            ops_store.restore(self.ops, "../../somewhere")

    def test_session_path_refuses_setup_actions(self):
        with self.assertRaisesRegex(Refused, "needs ops_plan"):
            ops_store.quick(self.ops, [self.ADD])

    def test_failing_action_leaves_nothing_behind(self):
        before = self.snapshot()
        with self.assertRaisesRegex(Refused, "Action 2"):
            self.plan(self.ADD, {"action": "add_car_type", "name": "Autorack"})
        self.assertEqual(self.snapshot(), before)


REAL_RUNNING = ops_store.running_jmri


class Preserved(Case):
    def test_moves_survive_adding_a_track(self):
        self.edit({"action": "set_track_moves", "moves": {"Ashgrove Feed Mill": 40}})
        self.edit({"action": "add_track", "location": "Ashgrove", "name": "New Spur", "type": "Spur", "length": 100})
        self.assertEqual(self.track("Ashgrove Feed Mill").moves, 40)

    def test_moves_survive_changing_a_schedule(self):
        self.edit({"action": "set_track_moves", "moves": {"Ashgrove Feed Mill": 40}})
        plan = self.plan({"action": "update_track", "track": "Ashgrove Feed Mill", "schedule": "Elevator"})
        ops_store.apply(plan["plan_id"], allow_new_errors=True)
        track = self.track("Ashgrove Feed Mill")
        self.assertEqual(track.moves, 40)
        self.assertEqual(track.item_id, "6c1")

    def test_guard_catches_a_moves_change_no_action_declared(self):
        editor = ops_actions.Editor(self.ops)
        editor.tracks()[0].set("moves", "99")
        with self.assertRaisesRegex(Refused, "moves"):
            ops_actions.guard(editor)

    def test_guard_catches_a_derived_car_field(self):
        editor = ops_actions.Editor(self.ops)
        editor.cars()[0].set("destinationId", "1")
        with self.assertRaisesRegex(Refused, "destinationId"):
            ops_actions.guard(editor)

    def test_guard_catches_train_state(self):
        editor = ops_actions.Editor(self.ops)
        editor.trains()[0].set("built", "true")
        with self.assertRaisesRegex(Refused, "built"):
            ops_actions.guard(editor)

    def test_car_destination_cannot_be_set(self):
        with self.assertRaisesRegex(Refused, "Unknown car field"):
            self.plan({"action": "update_car", "car": "BVR1001", "destinationId": "1"})


class TrapsAreRefused(Case):
    def check(self, track, message, **fields):
        with self.assertRaisesRegex(Refused, message):
            self.plan({"action": "update_track", "track": track, **fields})

    def test_settings_a_track_type_ignores(self):
        self.check("Brackwater Yard A", "Yards ignore", pickup={"option": "trains", "names": ["BV1"]})
        self.check("Brackwater Yard A", "Yards ignore", drop={"option": "trains", "names": ["BV1"]})
        self.check("Brackwater Yard A", "only spurs|Only spurs", schedule="Elevator")
        self.check("Brackwater Yard A", "Only spurs", alternate="Brackwater Yard B")
        self.check("Ashgrove Feed Mill", "interchange and staging", destinations={"option": "All"})
        self.check("Ashgrove Feed Mill", "interchange and staging", only_final_destination=True)
        self.check("Ashgrove Feed Mill", "staging tracks only", ship_loads={"option": "All"})

    def test_interchange_alternate_refused(self):
        self.edit({"action": "add_track", "location": "Ashgrove", "name": "New CI", "type": "Interchange",
                   "length": 100})
        self.check("Ashgrove Feed Mill", "leaves car routing", alternate="New CI")


class Chains(Case):
    def test_add_type_follows_the_model_type_and_registers_it(self):
        self.edit({"action": "add_car_type", "name": "Autorack", "like": "Boxcar"})
        rr = self.rr()
        self.assertIn("Autorack", rr.car_types)
        for track in rr.tracks.values():
            self.assertEqual("Boxcar" in track.types, "Autorack" in track.types, track.name)
        for train in rr.trains.values():
            self.assertEqual("Boxcar" in train.types, "Autorack" in train.types, train.name)

    def test_new_train_joins_train_lists_on_its_route_only(self):
        self.edit({"action": "add_train", "name": "N1", "route": "Main East"})
        rr = self.rr()
        new = rr.find_train("N1")
        stops = {s.location_id for s in rr.routes[new.route_id].stops}
        for track in rr.tracks.values():
            for option, ids in ((track.drop_option, track.drop_ids), (track.pickup_option, track.pickup_ids)):
                if option == "trains":
                    self.assertEqual(new.id in ids, track.location_id in stops, track.name)

    def test_exclude_destinations_store_accepted_ids(self):
        rr = self.rr()
        interchange = next(t for t in rr.tracks.values() if t.is_interchange)
        self.edit({"action": "update_track", "track": interchange.id,
                   "destinations": {"option": "Exclude", "names": ["Tolvern"]}})
        track = self.rr().tracks[interchange.id]
        tolvern = rr.find_location("Tolvern").id
        self.assertNotIn(tolvern, track.destination_ids)
        self.assertFalse(track.accepts_destination(tolvern))
        self.assertTrue(track.accepts_destination(rr.find_location("Ashgrove").id))

    def test_rename_load_reaches_cars_schedules_and_pairs(self):
        # Acid already has an audit error, which comes back under the new name.
        plan = self.plan({"action": "rename_load", "old": "Acid", "new": "Sulfuric"})
        ops_store.apply(plan["plan_id"], allow_new_errors=True)
        trains = (self.ops / "OperationsTrainRoster.xml").read_text()
        self.assertIn("Tank &amp; Sulfuric", trains)
        self.assertNotIn("Tank &amp; Acid", trains)

    def test_rename_location_updates_stored_names(self):
        self.edit({"action": "rename_location", "location": "Ashgrove", "new": "Ash Grove"})
        self.assertNotIn('name="Ashgrove"', (self.ops / "OperationsRouteRoster.xml").read_text())

    def test_replace_lines_keeps_ids_unique_and_repoints_tracks(self):
        self.edit({"action": "replace_schedule_lines", "schedule": "Mill Receiving",
                   "lines": [{"type": "Boxcar", "receive": "Grain", "ship": "Feed"}]})
        self.assertEqual(self.track("Ashgrove Feed Mill").item_id, "1c3")

    def test_delete_refuses_while_used(self):
        with self.assertRaisesRegex(Refused, "Still used"):
            self.plan({"action": "delete_track", "track": "Tolvern Yard"})
        with self.assertRaisesRegex(Refused, "Still on"):
            self.plan({"action": "delete_schedule", "schedule": "Mill Receiving"})
        with self.assertRaisesRegex(Refused, "Still used"):
            self.plan({"action": "delete_route", "route": "Main East"})

    def test_split_kernel_refused(self):
        rr = self.rr()
        cars = list(rr.cars.values())
        first = cars[0]
        other = next(c for c in cars if c.track_id != first.track_id and c.track_id)
        with self.assertRaisesRegex(Refused, "same track"):
            self.plan({"action": "set_kernel", "name": "K", "cars": [first.id, other.id]})

    def test_session_place_and_clear(self):
        rr = self.rr()
        car = next(c for c in rr.cars.values() if not c.kernel and c.type == "Boxcar")
        yard = rr.find_track("Brackwater Yard A")
        ops_store.quick(self.ops, [
            {"action": "place_car", "car": car.id, "location": "Brackwater", "track": yard.name},
            {"action": "clear_final_destination", "car": car.id}])
        moved = self.rr().cars[car.id]
        self.assertEqual((moved.track_id, moved.fd_id), (yard.id, ""))
        self.assertEqual(self.rr().tracks[yard.id].moves, yard.moves)

    def test_every_action_documents_itself(self):
        for name, entry in ops_actions.ACTIONS.items():
            self.assertTrue(entry["help"], name)

    def test_everything_plan_runs_in_python(self):
        result = self.plan(*EVERYTHING)
        self.assertTrue(result["changed"])


class Chain5(Case):
    """Convert a default-load spur to custom loads: the worked example in references/loads-and-schedules.md."""
    PLAN = [
        {"action": "add_schedule", "name": "Team Track Loads",
         "lines": [{"type": "Boxcar", "receive": "Feed", "ship": "Mty", "count": 2}]},
        {"action": "update_track", "track": "Brackwater Team Track", "location": "Brackwater",
         "schedule": "Team Track Loads", "schedule_mode": "sequential"},
    ]

    def test_two_actions_in_one_plan_give_the_spur_a_schedule(self):
        before = self.track("Brackwater Team Track")
        self.assertEqual(before.schedule_id, "")
        plan = self.plan(*self.PLAN)
        self.assertFalse(plan["blocked"])
        ops_store.apply(plan["plan_id"])
        rr = self.rr()
        after = rr.find_track("Brackwater Team Track")
        schedule = next(s for s in rr.schedules.values() if s.name == "Team Track Loads")
        self.assertEqual(after.schedule_id, schedule.id)
        self.assertEqual(after.item_id, schedule.items[0].id)

    def test_update_track_alone_cannot_name_a_schedule_that_does_not_exist_yet(self):
        with self.assertRaises(Refused):
            self.plan(self.PLAN[1])

    @unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
    def test_jmri_keeps_the_converted_spur(self):
        self.edit(*self.PLAN)
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        self.assertEqual(result["log_errors"], [])
        theirs = ops_data.load(keep).find_track("Brackwater Team Track")
        mine = self.rr().find_track("Brackwater Team Track")
        self.assertEqual((theirs.schedule_id, theirs.item_id), (mine.schedule_id, mine.item_id))
        self.assertNotEqual(theirs.schedule_id, "")


class ReviewFixes(Case):
    """Findings from the write-lane review, each held to the JMRI source it cites."""

    def rewrite(self, name, old, new):
        path = self.ops / name
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def raw_track(self, name):
        root = ET.parse(self.ops / "OperationsLocationRoster.xml").getroot()
        return next(t for t in root.iter("track") if t.get("name") == name)

    # 1. Custom staging: Car.java:935-955, TBC:633-637, 547-557.
    def test_custom_staging_empties_default_loads_and_keeps_other_bits(self):
        self.rewrite("OperationsLocationRoster.xml", 'name="West Stage 1" trackType="Staging" dir="3" length="500" moves="0"',
                     'name="West Stage 1" trackType="Staging" dir="3" length="500" moves="0" loadOptions="128"')
        self.edit({"action": "setup_custom_staging", "track": "West Stage 1"})
        track = self.raw_track("West Stage 1")
        self.assertEqual(int(track.get("loadOptions")), 2 | 8 | 16 | 32 | 128)
        self.assertEqual(track.get("carShipLoadOption"), "Exclude")
        self.assertEqual([e.get("name") for e in track.findall("carShipLoads/carLoad")], ["L", "Mty"])
        self.assertIn("fails the build", ops_actions.ACTIONS["setup_custom_staging"]["help"])

    def test_custom_staging_can_keep_shipping_empties(self):
        self.edit({"action": "setup_custom_staging", "track": "West Stage 2", "local_route_only": True,
                   "any_staging": False, "ship_empties": True})
        track = self.raw_track("West Stage 2")
        self.assertEqual(int(track.get("loadOptions")), 2 | 4 | 16)
        self.assertEqual([e.get("name") for e in track.findall("carShipLoads/carLoad")], ["L"])
        self.edit({"action": "setup_custom_staging", "track": "West Stage 2", "ship_loads": ["Feed"],
                   "ship_empties": True})
        track = self.raw_track("West Stage 2")
        self.assertEqual(track.get("carShipLoadOption"), "Include")
        self.assertEqual([e.get("name") for e in track.findall("carShipLoads/carLoad")], ["Feed", "Mty"])

    def test_spur_load_options_replace_only_the_spur_group(self):
        self.edit({"action": "update_track", "track": "Ashgrove Feed Mill", "load_options": ["disable_load_change"]})
        self.edit({"action": "update_track", "track": "Ashgrove Feed Mill", "load_options": ["quick_service"]})
        self.assertEqual(self.raw_track("Ashgrove Feed Mill").get("loadOptions"), "128")

    # 2. Roads: trains/Xml.java:44-49, 63, 72; Train.java:4031-4036; RollingStock:1445.
    def test_rename_road_reaches_train_road_fields_and_refuses_engine_roads(self):
        with self.assertRaisesRegex(Refused, "Engines still carry road BV"):
            self.plan({"action": "rename_road", "old": "BV", "new": "BX"})
        self.rewrite("OperationsCarRoster.xml", '<road name="QXR" />', '<road name="QXR" />\n    <road name="PRR" />')
        # First occurrences are both on BV1.
        self.rewrite("OperationsTrainRoster.xml", 'engineRoad=""', 'engineRoad="PRR" leg2Road="PRR"')
        self.rewrite("OperationsTrainRoster.xml", 'cabooseRoad=""', 'cabooseRoad="PRR"')
        self.rewrite("OperationsTrainRoster.xml", '<carLoad name="Tank &amp; Acid" />\n      </carLoads>\n    </train>',
                     '<carLoad name="Tank &amp; Acid" />\n      </carLoads>\n      <locoRoads>\n'
                     '        <locoRoad name="PRR" />\n      </locoRoads>\n    </train>')
        self.edit({"action": "rename_road", "old": "PRR", "new": "PX"})
        trains = (self.ops / "OperationsTrainRoster.xml").read_text()
        self.assertNotIn("PRR", trains)
        self.assertIn('engineRoad="PX" leg2Road="PX"', trains)
        self.assertIn('cabooseRoad="PX"', trains)
        self.assertIn('<locoRoad name="PX" />', trains)
        self.assertIn('<road name="PX" />', (self.ops / "OperationsCarRoster.xml").read_text())

    # 3. Moves guard is per track.
    def test_moves_guard_allows_only_the_tracks_an_action_named(self):
        editor = ops_actions.Editor(self.ops)
        editor.run([{"action": "set_track_moves", "moves": {"Ashgrove Feed Mill": 40}}])
        ops_actions.guard(editor)
        editor.track("Ashgrove Cannery").set("moves", "9")
        with self.assertRaisesRegex(Refused, "moves on Ashgrove Cannery"):
            ops_actions.guard(editor)
        editor = ops_actions.Editor(self.ops)
        editor.run([{"action": "add_track", "location": "Ashgrove", "name": "New Spur", "type": "Spur", "length": 50,
                     "moves": 3}])
        editor.track("Ashgrove Cannery").set("moves", "9")
        with self.assertRaisesRegex(Refused, "moves on Ashgrove Cannery"):
            ops_actions.guard(editor)

    # 4. delete_train: TrainSchedule.java:120, AutomationItem.java:446.
    def test_delete_train_leaves_day_schedules_and_refuses_automations(self):
        self.rewrite("OperationsTrainRoster.xml", '<schedule id="1" name="Monday" />',
                     '<schedule id="1" name="Monday" trainIds="1,3,6" />')
        self.edit({"action": "delete_train", "train": "T10"})
        trains = (self.ops / "OperationsTrainRoster.xml").read_text()
        self.assertIn('<schedule id="1" name="Monday" trainIds="1,6" />', trains)
        self.rewrite("OperationsTrainRoster.xml", "</schedules>",
                     '</schedules>\n  <automations>\n    <automation id="1" name="Nightly" comment="">\n'
                     '      <item id="1c1" sequenceId="1" name="Build" actionCode="0" trainId="6" />\n'
                     '    </automation>\n  </automations>')
        with self.assertRaisesRegex(Refused, "Automations still use it: Nightly"):
            self.plan({"action": "delete_train", "train": "T30"})

    # 5. Engines hold locationId too: RollingStock:1474.
    def test_delete_location_sees_engines(self):
        editor = ops_actions.Editor(self.ops)
        place = editor.location("Ashgrove-North")
        for track in place.findall("track"):
            place.remove(track)
        engine = editor.engines()[0]
        engine.set("locationId", place.get("id"))
        engine.attrib.pop("secLocationId")
        with self.assertRaisesRegex(Refused, f"engine {engine.get('id')}"):
            ops_actions.delete_location(editor, "Ashgrove-North")

    # 6. Kernels: TBB:1213-1231.
    def test_kernel_needs_tracks_and_compares_split_names(self):
        with self.assertRaisesRegex(Refused, "need a track; none on: BVR3003"):
            self.plan({"action": "set_kernel", "name": "K", "cars": ["BVR1001", "BVR3003"]})
        self.edit({"action": "add_track", "location": "Brackwater", "name": "Dock-1", "type": "Yard", "length": 200},
                  {"action": "add_track", "location": "Brackwater", "name": "Dock-2", "type": "Yard", "length": 200},
                  {"action": "add_car", "road": "BVR", "number": "7001", "type": "Boxcar", "length": 40,
                   "location": "Brackwater", "track": "Dock-1"},
                  {"action": "add_car", "road": "BVR", "number": "7002", "type": "Boxcar", "length": 40,
                   "location": "Brackwater", "track": "Dock-2"},
                  {"action": "set_kernel", "name": "Docks", "cars": ["BVR7001", "BVR7002"]})
        self.assertEqual(self.rr().cars["BVR7002"].kernel, "Docks")

    # 7. Numbers JMRI parses: RouteLocation:612-655, ScheduleItem:347-351, ScheduleTableModel:412.
    def test_numeric_fields_are_checked(self):
        with self.assertRaisesRegex(Refused, "max_moves must be a whole number"):
            self.plan({"action": "update_stop", "route": "Main East", "stop": 1, "max_moves": "lots"})
        with self.assertRaisesRegex(Refused, "random must be Off or 10 to 100"):
            self.plan({"action": "update_stop", "route": "Main East", "stop": 1, "random": 25})
        with self.assertRaisesRegex(Refused, "random must be blank or one of"):
            self.plan({"action": "add_schedule", "name": "S", "lines": [{"type": "Boxcar", "random": 33}]})
        with self.assertRaisesRegex(Refused, "wait must be a whole number"):
            self.plan({"action": "add_schedule", "name": "S", "lines": [{"type": "Boxcar", "wait": 1.5}]})
        self.assertTrue(self.plan({"action": "update_stop", "route": "Main East", "stop": 1, "max_moves": "9",
                                   "random": "20"})["changed"])

    # 8. delete_schedule checks cars under its lines, like replace_schedule_lines.
    def test_delete_schedule_refuses_while_a_car_travels_under_a_line(self):
        self.rewrite("OperationsCarRoster.xml", 'load="Grain" />', 'load="Grain" scheduleId="5c1" />')
        with self.assertRaisesRegex(Refused, "Cars are on their way"):
            self.plan({"action": "delete_schedule", "schedule": "Unused Siding Plan"})

    # 9. Transaction edges.
    def test_interrupt_during_apply_restores_and_reraises(self):
        before = self.snapshot()
        result = self.plan(Transaction.ADD)
        real = ops_store._audit
        calls = []

        def interrupted(directory):
            calls.append(directory)
            if len(calls) == 2:
                raise KeyboardInterrupt
            return real(directory)

        with mock.patch.object(ops_store, "_audit", interrupted):
            with self.assertRaises(KeyboardInterrupt):
                ops_store.apply(result["plan_id"])
        self.assertEqual(self.snapshot(), before)

    def test_failed_replace_leaves_no_temporary_file(self):
        before = self.snapshot()
        result = self.plan(Transaction.ADD)
        real = os.replace

        def once(*args):
            os.replace = real
            raise OSError("disk full")

        with mock.patch.object(os, "replace", once):
            with self.assertRaisesRegex(Refused, "disk full"):
                ops_store.apply(result["plan_id"])
        self.assertEqual(list(self.ops.glob(".*.opspro.tmp")), [])
        self.assertEqual(self.snapshot(), before)

    def test_failed_restore_names_the_files_already_replaced(self):
        result = self.plan(Transaction.ADD)
        with mock.patch.object(ops_store, "_audit", side_effect=[ops_store._audit(self.ops), RuntimeError("boom")]):
            with mock.patch.object(ops_store, "_restore_set", side_effect=OSError("locked")):
                with self.assertRaisesRegex(Refused, "Already replaced: OperationsCarRoster.xml, "
                                                     "OperationsLocationRoster.xml"):
                    ops_store.apply(result["plan_id"])

    # 10. Cosmetic.
    def test_add_location_writes_no_ops_and_remove_types_tolerates_no_types(self):
        self.edit({"action": "add_location", "name": "Bare", "types": []},
                  {"action": "add_track", "location": "Bare", "name": "Bare Spur", "type": "Spur", "length": 50,
                   "types": []},
                  {"action": "update_track", "track": "Bare Spur", "remove_types": ["Boxcar"]},
                  {"action": "update_location", "location": "Bare", "remove_types": ["Boxcar"]})
        root = ET.parse(self.ops / "OperationsLocationRoster.xml").getroot()
        bare = next(x for x in root.iter("location") if x.get("name") == "Bare")
        self.assertIsNone(bare.get("ops"))


# ---- Engines and divisions ---------------------------------------------------------------
# One plan for the engine and division actions, kept apart from EVERYTHING for the JMRI read-back.
ENGINE_PLAN = [
    {"action": "add_engine_type", "name": "Road Diesel", "like": "Diesel"},
    {"action": "add_engine", "road": "BV", "number": "201", "model": "GP38", "type": "Diesel",
     "location": "Brackwater", "track": "Brackwater Yard A", "owner": "BV", "built": "1970"},
    {"action": "add_engine", "road": "BV", "number": "202", "model": "GP38", "location": "Brackwater",
     "track": "Brackwater Yard A"},
    {"action": "add_engine", "road": "BVR", "number": "301", "model": "C628", "type": "Road Diesel", "length": 69,
     "hp": 2750, "weight_tons": 195, "b_unit": False, "location": "Tolvern", "track": "Tolvern Yard",
     "comment": "Leased"},
    {"action": "update_engine_model", "model": "GP38", "hp": 2100},
    {"action": "set_consist", "name": "Pair", "engines": ["BV201", "BV202"], "number": 21},
    {"action": "update_engine", "engine": "BVR301", "out_of_service": True, "value": "12"},
    {"action": "add_division", "name": "East End", "comment": "east of the river"},
    {"action": "add_division", "name": "West End"},
    {"action": "set_location_division", "division": "East End", "locations": ["Brackwater", "Tolvern"]},
    {"action": "set_location_division", "division": "West End", "locations": ["Ashgrove"]},
    {"action": "update_division", "division": "West End", "name": "Valley", "comment": "renamed"},
    {"action": "set_car_division", "division": "East End", "cars": ["BVR1001"]},
    {"action": "set_load_type", "load": "Cinders", "load_type": "Load"},
    {"action": "update_train", "train": "T30", "loco_roads": {"option": "Include", "names": ["BV", "BVR"]}},
]


def _engine_xml(folder):
    return ET.parse(Path(folder) / "OperationsEngineRoster.xml").getroot()


class Engines(Case):
    def engine(self, identity):
        return next(e for e in _engine_xml(self.ops).iter("engine") if e.get("id") == identity)

    def test_the_engine_plan_runs_and_keeps_moves(self):
        before = {t.id: t.moves for t in self.rr().tracks.values()}
        self.edit(*ENGINE_PLAN)
        rr = self.rr()
        self.assertEqual({t.id: t.moves for t in rr.tracks.values()}, before)
        self.assertEqual(rr.engines["BV201"].consist, "Pair")
        self.assertTrue(rr.engines["BV201"].lead)
        self.assertEqual(rr.engines["BVR301"].type, "Road Diesel")
        self.assertIn("Road Diesel", rr.engine_types)
        self.assertEqual(sorted(rr.divisions.values()), ["East End", "Valley"])
        self.assertEqual(rr.find_location("Ashgrove").division_id,
                         next(i for i, n in rr.divisions.items() if n == "Valley"))
        self.assertTrue(rr.cars["BVR1001"].division_id)

    def test_a_model_keeps_one_value_on_every_engine(self):
        # Engine.java: setHp, setLength, setTypeName and setWeightTons go to EngineModels.
        self.edit(*ENGINE_PLAN[:3])
        for identity in ("BV201", "BV202"):
            engine = self.engine(identity)
            self.assertEqual((engine.get("hp"), engine.get("length"), engine.get("weightTons")), ("2000", "59", "125"))
        with self.assertRaisesRegex(Refused, "one value per model"):
            self.plan({"action": "add_engine", "road": "BV", "number": "203", "model": "GP38", "hp": 1500})
        with self.assertRaisesRegex(Refused, "update_engine_model"):
            self.plan({"action": "update_engine", "engine": "BV201", "hp": 1500})
        self.edit({"action": "update_engine_model", "model": "GP38", "hp": 2100, "length": 60})
        self.assertEqual({self.engine(i).get("hp") for i in ("BV201", "BV202")}, {"2100"})
        self.assertIn("60", [e.get("value") for e in _engine_xml(self.ops).iter("length")])

    def test_engine_fields_are_checked(self):
        cases = [
            ({"model": ""}, "needs a model"),
            ({"model": "New1"}, "give its type and length"),
            ({"model": "New1", "type": "Steam", "length": 50}, "Unknown locomotive type"),
            ({"model": "New1", "type": "Diesel", "length": "long"}, "length must be a whole number"),
            ({"model": "New1", "type": "Diesel", "length": 50, "hp": "big"}, "hp must be a whole number"),
            ({"model": "GP38", "location": "Brackwater"}, "both location and track"),
            ({"model": "GP38", "b_unit": "yes"}, "b_unit is true or false"),
        ]
        for fields, message in cases:
            with self.assertRaisesRegex(Refused, message):
                self.plan({"action": "add_engine", "road": "BV", "number": "9", **fields})
        with self.assertRaisesRegex(Refused, "does not take Steam"):
            self.plan({"action": "add_engine_type", "name": "Steam"},
                      {"action": "add_engine", "road": "BV", "number": "9", "model": "Mogul", "type": "Steam",
                       "length": 60, "location": "Brackwater", "track": "Brackwater Yard A"})
        with self.assertRaisesRegex(Refused, "at most 10"):
            self.plan({"action": "add_engine", "road": "BV", "number": "12345678901", "model": "GP38"})
        with self.assertRaisesRegex(Refused, "already exists"):
            self.plan({"action": "add_engine", "road": "BV", "number": "101", "model": "GP9"})

    def test_types_rename_and_delete_follow_tracks_and_trains(self):
        with self.assertRaisesRegex(Refused, "is a car type"):
            self.plan({"action": "add_engine_type", "name": "Boxcar"})
        with self.assertRaisesRegex(Refused, "is a locomotive type"):
            self.plan({"action": "add_car_type", "name": "Diesel"})
        self.edit({"action": "add_engine_type", "name": "Steam", "like": "Diesel"})
        text = (self.ops / "OperationsLocationRoster.xml").read_text()
        self.assertEqual(text.count('<locoType name="Steam" />'), text.count('<locoType name="Diesel" />'))
        self.edit({"action": "rename_engine_type", "old": "Steam", "new": "Steam-heavy"})
        text = (self.ops / "OperationsLocationRoster.xml").read_text()
        self.assertNotIn('"Steam"', text)
        self.assertEqual(text.count('<locoType name="Steam-heavy" />'), text.count('<locoType name="Diesel" />'))
        with self.assertRaisesRegex(Refused, "Engines still have type Diesel"):
            self.plan({"action": "delete_engine_type", "name": "Diesel"})
        self.edit({"action": "delete_engine_type", "name": "Steam-heavy"})
        for name in ("OperationsLocationRoster.xml", "OperationsTrainRoster.xml"):
            self.assertNotIn("Steam", (self.ops / name).read_text())
        with self.assertRaisesRegex(Refused, "refills an empty list"):
            ops_actions._keep_one(ops_actions.Editor(self.ops), "types", "type")

    def test_model_rename_reaches_trains_and_delete_refuses_while_used(self):
        self.edit({"action": "rename_engine_model", "old": "GP9", "new": "GP9m"})
        self.assertEqual(self.rr().engines["BV101"].length, "56")
        self.assertEqual({e.get("model") for e in _engine_xml(self.ops).iter("engine")}, {"GP9m"})
        self.assertIn('engineModel="GP9m"', (self.ops / "OperationsTrainRoster.xml").read_text())
        with self.assertRaisesRegex(Refused, "Still used by: BV101"):
            self.plan({"action": "delete_engine_model", "model": "GP9m"})
        with self.assertRaisesRegex(Refused, "No engine has model"):
            self.plan({"action": "update_engine_model", "model": "SD45", "hp": 4000})

    def test_consists_place_and_delete(self):
        self.edit(*ENGINE_PLAN[:3])
        with self.assertRaisesRegex(Refused, "same track"):
            self.plan({"action": "set_consist", "name": "C", "engines": ["BV201", "BV101"]})
        self.edit({"action": "set_consist", "name": "Pair", "engines": ["BV201", "BV202"], "lead": "BV202"})
        lead, other = self.engine("BV202"), self.engine("BV201")
        self.assertEqual((lead.get("leadConsist"), lead.get("blocking"), other.get("blocking")), ("true", "1", "2"))
        self.assertIsNone(lead.get("consistNum"))
        with self.assertRaisesRegex(Refused, "Place the lead"):
            ops_store.quick(self.ops, [{"action": "place_engine", "engine": "BV201", "location": "Tolvern",
                                        "track": "Tolvern Yard"}])
        with self.assertRaisesRegex(Refused, "consist Pair first"):
            self.plan({"action": "delete_engine", "engine": "BV201"})
        ops_store.quick(self.ops, [{"action": "place_engine", "engine": "BV202", "location": "Tolvern",
                                    "track": "Tolvern Yard"}])
        tolvern = self.rr().find_track("Tolvern Yard").id
        self.assertEqual({self.rr().engines[i].track_id for i in ("BV201", "BV202")}, {tolvern})
        with self.assertRaisesRegex(Refused, "needs ops_plan"):
            ops_store.quick(self.ops, [{"action": "delete_engine", "engine": "BV201"}])
        self.edit({"action": "clear_consist", "name": "Pair"}, {"action": "delete_engine", "engine": "BV201"})
        self.assertNotIn("BV201", self.rr().engines)
        self.assertIsNone(self.engine("BV202").get("blocking"))
        self.assertEqual(list(_engine_xml(self.ops).iter("consist")), [])

    def test_engine_on_a_train_is_left_alone(self):
        self.rewrite_engine('locationId="4" secLocationId="4s1"', 'locationId="4" secLocationId="4s1" trainId="1" '
                            'destinationId="5"')
        for item in ({"action": "update_engine", "engine": "BV101", "comment": "x"},
                     {"action": "update_engine_model", "model": "GP9", "hp": 1800},
                     {"action": "delete_engine", "engine": "BV101"}):
            with self.assertRaisesRegex(Refused, "assigned to a train"):
                self.plan(item)

    def rewrite_engine(self, old, new):
        path = self.ops / "OperationsEngineRoster.xml"
        text = path.read_text()
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1))

    def test_a_railroad_without_an_engine_file_gets_jmris_defaults(self):
        (self.ops / "OperationsEngineRoster.xml").unlink()
        result = self.edit({"action": "add_engine", "road": "BV", "number": "1", "model": "SW8",
                            "location": "Brackwater", "track": "Brackwater Yard A"})
        self.assertIn("OperationsEngineRoster.xml", result["files"])
        root = _engine_xml(self.ops)
        self.assertEqual(len(root.findall("./models/model")), 27)
        self.assertIn("Switcher", [t.get("name") for t in root.findall("./types/type")])
        engine = root.find("./engines/engine")
        self.assertEqual((engine.get("type"), engine.get("length"), engine.get("hp")), ("Diesel", "44", "800"))

    def test_a_failed_apply_removes_a_file_it_created(self):
        (self.ops / "OperationsEngineRoster.xml").unlink()
        before = self.snapshot()
        result = self.plan({"action": "add_engine_type", "name": "Steam-new"})
        with mock.patch.object(ops_store, "_audit", side_effect=[ops_store._audit(self.ops), RuntimeError("boom")]):
            with self.assertRaisesRegex(Refused, "Change undone"):
                ops_store.apply(result["plan_id"])
        self.assertEqual(self.snapshot(), before)


class Divisions(Case):
    def test_delete_clears_locations_and_cars(self):
        self.edit(*ENGINE_PLAN[7:13])
        result = self.edit({"action": "delete_division", "division": "East End"})
        self.assertIn("cleared on 2 locations, 1 cars", result["summary"][0])
        rr = self.rr()
        self.assertEqual(list(rr.divisions.values()), ["Valley"])
        self.assertEqual(rr.cars["BVR1001"].division_id, "")
        self.assertEqual(rr.find_location("Brackwater").division_id, "")

    def test_names_and_load_types_are_checked(self):
        self.edit({"action": "add_division", "name": "East"})
        with self.assertRaisesRegex(Refused, "already exists"):
            self.plan({"action": "add_division", "name": "East"})
        with self.assertRaisesRegex(Refused, "at most 25"):
            self.plan({"action": "add_division", "name": "x" * 26})
        with self.assertRaisesRegex(Refused, "No division"):
            self.plan({"action": "set_location_division", "division": "Nowhere", "locations": ["Ashgrove"]})
        with self.assertRaisesRegex(Refused, "fixed"):
            self.plan({"action": "set_load_type", "load": "Mty", "load_type": "Load"})
        with self.assertRaisesRegex(Refused, "Load or Empty"):
            self.plan({"action": "set_load_type", "load": "Grain", "load_type": "empty"})
        self.edit({"action": "set_location_division", "division": "East", "locations": ["Ashgrove"]})
        self.assertIn('name="Ashgrove" divisionId="1"', (self.ops / "OperationsLocationRoster.xml").read_text())
        self.edit({"action": "set_location_division", "division": None, "locations": ["Ashgrove"]})
        self.assertNotIn("divisionId", (self.ops / "OperationsLocationRoster.xml").read_text())

    def test_a_kernel_follows_its_car(self):
        self.edit({"action": "add_division", "name": "East"},
                  {"action": "add_car", "road": "BVR", "number": "7001", "type": "Boxcar", "length": 40,
                   "location": "Brackwater", "track": "Brackwater Yard A"},
                  {"action": "add_car", "road": "BVR", "number": "7002", "type": "Boxcar", "length": 40,
                   "location": "Brackwater", "track": "Brackwater Yard A"},
                  {"action": "set_kernel", "name": "K", "cars": ["BVR7001", "BVR7002"]},
                  {"action": "set_car_division", "division": "East", "cars": ["BVR7002"]})
        rr = self.rr()
        self.assertTrue(rr.cars["BVR7001"].division_id)
        self.assertEqual(rr.cars["BVR7001"].division_id, rr.cars["BVR7002"].division_id)


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealJmri(Case):
    def read_back(self):
        """JMRI loads the files and saves them. Anything it would drop shows up here."""
        keep = Path(self.temp.name) / "saved"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"save": True}, keep)
        return result, keep

    def test_every_action_survives_a_jmri_load_and_save(self):
        self.edit(*EVERYTHING)
        ours = self.rr()
        result, keep = self.read_back()
        self.assertEqual(result["log_errors"], [])
        theirs = ops_data.load(keep)
        for field in ("cars", "locations", "routes", "trains", "schedules", "tracks"):
            self.assertEqual(sorted(getattr(ours, field)), sorted(getattr(theirs, field)), field)
        new_tracks = [t for t in ours.tracks.values() if ours.locations[t.location_id].name == "Harbor Point"]
        self.assertEqual(len(new_tracks), 4)
        for track in new_tracks:
            other = theirs.tracks[track.id]
            for attr in vars(track):
                if attr != "types":
                    self.assertEqual(getattr(track, attr), getattr(other, attr), f"{track.name}.{attr}")
            self.assertEqual(sorted(track.types), sorted(other.types), track.name)
        for name in ("H1", "H2"):
            mine, jmri = ours.find_train(name), theirs.find_train(name)
            for attr in vars(mine):
                if attr != "types":
                    self.assertEqual(getattr(mine, attr), getattr(jmri, attr), f"{name}.{attr}")
        for name in ("Auto Plant Schedule", "Storage Mirror"):
            mine = next(s for s in ours.schedules.values() if s.name == name)
            self.assertEqual(mine, theirs.schedules[mine.id])
        route = next(r for r in ours.routes.values() if r.name == "Harbor Turn")
        self.assertEqual(route, theirs.routes[route.id])
        for car in ("BVR9001", "BVR9002"):
            self.assertEqual(ours.cars[car], theirs.cars[car])
        self.assertEqual({x.name: x.load_type for x in ours.loads["Autorack"]},
                         {x.name: x.load_type for x in theirs.loads["Autorack"]})
        self.assertEqual(ours.active_schedule, theirs.active_schedule)
        self.assertEqual(ours.tracks[new_tracks[0].id].moves, 12)
        stage, jmri_stage = ours.find_track("West Stage 1"), theirs.tracks[ours.find_track("West Stage 1").id]
        self.assertEqual(stage.load_options, 2 | 8 | 16 | 32)
        self.assertEqual((stage.load_options, stage.raw_ship_option, sorted(stage.ship_loads)),
                         (jmri_stage.load_options, jmri_stage.raw_ship_option, sorted(jmri_stage.ship_loads)))

    # ---- Engines and divisions in real JMRI.
    def test_engines_and_divisions_survive_a_jmri_load_and_save(self):
        self.edit(*ENGINE_PLAN)
        ours = self.rr()
        result, keep = self.read_back()
        self.assertEqual(result["log_errors"], [])
        theirs = ops_data.load(keep)
        self.assertEqual(ours.engines, theirs.engines)
        self.assertEqual(ours.divisions, theirs.divisions)
        self.assertEqual(sorted(ours.engine_types), sorted(theirs.engine_types))
        self.assertEqual(sorted(ours.engine_models), sorted(theirs.engine_models))
        self.assertEqual(ours.consists, theirs.consists)
        self.assertEqual({x.id: x.division_id for x in ours.locations.values()},
                         {x.id: x.division_id for x in theirs.locations.values()})
        self.assertEqual({c.id: c.division_id for c in ours.cars.values()},
                         {c.id: c.division_id for c in theirs.cars.values()})
        self.assertEqual({x.name: x.load_type for x in ours.loads["Hopper"]},
                         {x.name: x.load_type for x in theirs.loads["Hopper"]})
        mine, jmri = _engine_xml(self.ops), _engine_xml(keep)
        for engine in ("BV201", "BV202", "BVR301"):
            self.assertEqual(next(e.attrib for e in mine.iter("engine") if e.get("id") == engine),
                             next(e.attrib for e in jmri.iter("engine") if e.get("id") == engine), engine)
        types = lambda root: sorted(  # noqa: E731
            (t.get("id"), x.get("name")) for t in root.iter("track") for x in t.findall("types/locoType"))
        self.assertEqual(types(ET.parse(self.ops / "OperationsLocationRoster.xml").getroot()),
                         types(ET.parse(keep / "OperationsLocationRoster.xml").getroot()))
        roads = lambda folder: [  # noqa: E731
            (t.get("locoRoadOption"), [r.get("name") for r in t.findall("locoRoads/locoRoad")])
            for t in ET.parse(Path(folder) / "OperationsTrainRoster.xml").getroot().iter("train")]
        self.assertEqual(roads(self.ops), roads(keep))
        self.assertIn(("Include", ["BV", "BVR"]), roads(keep))

    def test_a_new_engine_file_holds_what_jmri_writes_for_none(self):
        (self.ops / "OperationsEngineRoster.xml").unlink()
        _, keep = self.read_back()
        editor = ops_actions.Editor(self.ops)
        ops_actions._engine_root(editor)
        mine = ET.fromstring(editor.docs[ops_actions.ENGINE_FILE].render())
        jmri = _engine_xml(keep)
        for path, attr in (("./models/model", "name"), ("./types/type", "name"), ("./lengths/length", "value")):
            self.assertEqual([e.get(attr) for e in mine.findall(path)], [e.get(attr) for e in jmri.findall(path)],
                             path)

    def test_a_train_takes_a_new_consist(self):
        self.edit(*ENGINE_PLAN[:3], {"action": "set_consist", "name": "Pair", "engines": ["BV201", "BV202"]},
                  {"action": "update_train", "train": "T10", "engines": "2", "engine_model": "GP38"})
        keep = Path(self.temp.name) / "built"
        keep.mkdir()
        result = ops_jmri.run_worker(self.ops, {"build": True, "save": True}, keep)
        self.assertTrue(result["builds"]["T10"]["built"], result["builds"]["T10"]["message"])
        engines = {e.get("id"): e for e in _engine_xml(keep).iter("engine")}
        self.assertEqual({engines[i].get("trainId") for i in ("BV201", "BV202")}, {self.rr().find_train("T10").id})

    def test_a_file_saved_by_jmri_renders_byte_for_byte(self):
        _, keep = self.read_back()
        for path in keep.glob("*.xml"):
            self.assertEqual(Doc(path).render(), path.read_bytes(), path.name)

    def test_build_check_sees_a_broken_train(self):
        result = self.plan({"action": "update_stop", "route": "Main East", "stop": 1, "pickups": False})
        check = ops_jmri.build_check(result["plan_id"], 2)
        self.assertEqual(check["jmri"][:4], "5.16")
        self.assertTrue(check["changed"] or check["possibly_changed"] or check["now_fail"])

    def test_build_check_finds_no_change_from_an_unused_type(self):
        result = self.plan({"action": "add_car_type", "name": "Autorack"})
        check = ops_jmri.build_check(result["plan_id"], 6)
        self.assertEqual(check["changed"], {})
        self.assertEqual((check["now_fail"], check["now_build"]), ([], []))

    def test_dry_run_builds_terminates_and_leaves_files_alone(self):
        before = self.snapshot()
        result = ops_jmri.dry_run(self.ops)
        self.assertEqual(self.snapshot(), before)
        built = [r for r in result["builds"].values() if r["built"]]
        self.assertTrue(built)
        self.assertTrue(all(r.get("terminated") for r in built))

    def test_deliver_car_runs_the_schedule_like_set_car(self):
        rr = self.rr()
        mill = rr.find_track("Ashgrove Feed Mill")
        car = next(c for c in rr.cars.values() if c.type == "Boxcar" and c.load == "Grain"
                   and not c.kernel and not c.train_id and c.track_id != mill.id)
        result = ops_jmri.deliver_car(self.ops, car.id, "Ashgrove", mill.name)
        self.assertTrue(result["applied"])
        after = self.rr().cars[car.id]
        self.assertEqual(after.track_id, mill.id)
        self.assertEqual(after.load, "Feed")
        self.assertEqual(self.rr().tracks[mill.id].moves, mill.moves)


if __name__ == "__main__":
    unittest.main()
