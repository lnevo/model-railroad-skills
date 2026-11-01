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
