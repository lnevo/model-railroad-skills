"""Refusal paths for the group modules: a parameter of the wrong type, range or name is refused with a
Refused message, never a crash (AttributeError, TypeError) and never written as 'None' or an empty list.
Table driven against a copy of the demo railroad; each row names the action, its arguments and the message."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))
sys.path.insert(0, str(ROOT / "tests"))

import ops_actions  # noqa: E402
from ops_store import Refused  # noqa: E402
from test_write import Case  # noqa: E402

TWO_STOPS = [{"location": "Brackwater", "direction": "East"}, {"location": "Tolvern", "direction": "East"}]
LINE = {"type": "Boxcar", "receive": "E", "ship": "L"}
PLACE = [{"action": "place_engine", "engine": "BV101", "location": "Tolvern", "track": "Tolvern Yard"},
         {"action": "place_engine", "engine": "BV102", "location": "Tolvern", "track": "Tolvern Yard"}]

# (action, arguments, text the refusal must contain, actions to run first)
ROWS = [
    ("add_startup_script", {"path": None}, "path must be text", []),
    ("add_startup_script", {"path": "  "}, "cannot be blank", []),
    ("add_car_type", {"name": 5}, "must be text", []),
    ("add_car_type", {"name": "Autorack", "like": "Nope"}, "Unknown type", []),
    ("add_load", {"name": "Autos", "types": []}, "cannot be empty", []),
    ("add_load", {"name": "Autos", "types": "Boxcar"}, "list of names", []),
    ("add_load", {"name": "Autos", "types": ["Boxcar"], "drop_comment": 5}, "must be text", []),
    ("rename_car_type", {"old": "Tank", "new": None}, "must be text", []),
    ("rename_load", {"old": 5, "new": "Coal2"}, "must be text", []),
    ("rename_road", {"old": "QXR", "new": ""}, "cannot be blank", []),
    ("add_car", {"road": "NEW", "number": None, "type": "Boxcar", "length": 40}, "must be text", []),
    ("add_car", {"road": "NEW", "number": "1", "type": "Boxcar", "length": -4}, "less than", []),
    ("add_car", {"road": "NEW", "number": "1", "type": "Boxcar", "length": 10 ** 12}, "at most", []),
    ("add_car", {"road": "NEW", "number": "1", "type": "Boxcar", "length": 40, "color": None}, "must be text", []),
    ("update_car", {"car": None, "length": 50}, "as text", []),
    ("update_car", {"car": "BVR1001", "owner": ["x"]}, "text or a number", []),
    ("place_car", {"car": 5, "location": "Brackwater", "track": "Brackwater Yard B"}, "as text", []),
    ("clear_final_destination", {"car": ["BVR1001"]}, "as text", []),
    ("set_kernel", {"name": None, "cars": ["BVR1001", "BVR1002"]}, "must be text", []),
    ("set_kernel", {"name": "K1", "cars": "BVR1001"}, "list of names", []),
    ("clear_kernel", {"name": "Nope"}, "No kernel", []),
    ("clear_kernel", {"name": 5}, "must be text", []),
    ("delete_car", {"car": None}, "as text", []),
    ("add_engine_type", {"name": None}, "must be text", []),
    ("add_engine_type", {"name": "Steam", "like": 5}, "must be text", []),
    ("rename_engine_type", {"old": "Diesel", "new": 5}, "must be text", []),
    ("delete_engine_type", {"name": "Nope"}, "Unknown locomotive type", []),
    ("add_engine", {"road": None, "number": "5", "model": "GP9"}, "must be text", []),
    ("add_engine", {"road": "NEW", "number": None, "model": "GP9"}, "must be text", []),
    ("add_engine", {"road": "NEW", "number": "5", "model": 7}, "must be text", []),
    ("update_engine", {"engine": 5, "model": "GP9"}, "must be text", []),
    ("update_engine", {"engine": "BV101", "built": None}, "text or a number", []),
    ("update_engine_model", {"model": ["GP9"], "length": 60}, "must be text", []),
    ("rename_engine_model", {"old": "GP9", "new": None}, "must be text", []),
    ("delete_engine_model", {"model": "Nope"}, "Unknown model", []),
    ("place_engine", {"engine": None, "location": "Tolvern", "track": "Tolvern Yard"}, "must be text", []),
    ("delete_engine", {"engine": ["BV101"]}, "must be text", []),
    ("set_consist", {"name": None, "engines": ["BV101", "BV102"]}, "must be text", PLACE),
    ("set_consist", {"name": "C1", "engines": 5}, "list of names", PLACE),
    ("set_consist", {"name": "C1", "engines": ["BV101", "BV102"], "number": -3}, "less than", PLACE),
    ("clear_consist", {"name": "Nope"}, "No consist", []),
    ("clear_consist", {"name": None}, "must be text", []),
    ("add_division", {"name": "D1", "comment": 5}, "must be text", []),
    ("add_division", {"name": None}, "must be text", []),
    ("update_division", {"division": "D1", "name": None}, "Nothing to change", [{"action": "add_division", "name": "D1"}]),
    ("delete_division", {"division": "Nope"}, "No division", []),
    ("set_location_division", {"division": None, "locations": []}, "cannot be empty", []),
    ("set_location_division", {"division": None, "locations": "Brackwater"}, "list of names", []),
    ("set_car_division", {"division": None, "cars": []}, "cannot be empty", []),
    ("set_load_type", {"load": None, "load_type": "Load"}, "must be text", []),
    ("set_load_type", {"load": "Coal", "load_type": "Heavy"}, "Load or Empty", []),
    ("add_location", {"name": "Newtown", "types": "Boxcar"}, "list of names", []),
    ("add_location", {"name": "Newtown", "directions": 99}, "0 to 15", []),
    ("add_location", {"name": "Newtown", "directions": True}, "Directions must be", []),
    ("add_location", {"name": "Newtown", "comment": 5}, "must be text", []),
    ("update_location", {"location": "Brackwater", "directions": -1}, "0 to 15", []),
    ("update_location", {"location": "Brackwater", "add_types": "Boxcar"}, "list of names", []),
    ("update_location", {"location": "Brackwater", "comment": ["x"]}, "must be text", []),
    ("rename_location", {"location": "Ashgrove", "new": None}, "must be text", []),
    ("add_track", {"location": "Ashgrove", "name": "NewT", "type": "Spur", "length": -1}, "less than", []),
    ("add_track", {"location": "Ashgrove", "name": "NewT", "type": "Spur", "length": 1.5}, "whole number", []),
    ("add_track", {"location": "Ashgrove", "name": "NewT", "type": "Siding", "length": 100}, "type must be", []),
    ("add_track", {"location": "Ashgrove", "name": "NewT", "type": "Spur", "length": 100, "types": 5}, "list of names", []),
    ("update_track", {"track": "Ashgrove Feed Mill", "roads": "Include"}, "must be an object", []),
    ("update_track", {"track": "Ashgrove Feed Mill", "roads": {"option": "Include", "names": "BVR"}}, "list of names", []),
    ("update_track", {"track": "Ashgrove Feed Mill", "load_options": "generate"}, "list of names", []),
    ("update_track", {"track": "Ashgrove Feed Mill", "pool": ["x"]}, "must be an object", []),
    ("update_track", {"track": "Ashgrove Feed Mill", "directions": 16}, "0 to 15", []),
    ("rename_track", {"track": "Ashgrove Feed Mill", "new": 5}, "must be text", []),
    ("delete_track", {"track": None}, "as text", []),
    ("delete_location", {"location": None}, "as text", []),
    ("set_track_moves", {"moves": {}}, "at least one", []),
    ("set_track_moves", {"moves": [["Tolvern Yard", 5]]}, "must be an object", []),
    ("set_track_moves", {"moves": {"Tolvern Yard": 10 ** 12}}, "at most", []),
    ("reset_moves", {"location": "Nope"}, "No location", []),
    ("add_schedule", {"name": "S1", "lines": []}, "at least one line", []),
    ("add_schedule", {"name": "S1", "lines": [LINE], "comment": None}, "must be text", []),
    ("add_schedule", {"name": "S1", "lines": ["Boxcar"]}, "list of objects", []),
    ("add_schedule", {"name": "S1", "lines": [{"receive": "E"}]}, "Unknown car type", []),
    ("add_schedule", {"name": "S1", "lines": [{**LINE, "ship": 5}]}, "must be text", []),
    ("add_schedule", {"name": "S1", "lines": [{**LINE, "count": 0}]}, "less than", []),
    ("replace_schedule_lines", {"schedule": "Mill Receiving", "lines": None}, "list of objects", []),
    ("rename_schedule", {"schedule": "Mill Receiving", "new": ""}, "cannot be blank", []),
    ("delete_schedule", {"schedule": None}, "as text", []),
    ("add_industry", {"location": "Ashgrove", "name": None, "length": 100, "lines": [LINE]}, "must be text", []),
    ("add_industry", {"location": "Ashgrove", "name": "Ind", "length": 100, "lines": [5]}, "list of objects", []),
    ("add_industry", {"location": "Ashgrove", "name": "Ind", "length": -5, "lines": [LINE]}, "less than", []),
    ("mirror_schedule", {"spur": "Ashgrove Cannery", "sources": "Ashgrove Feed Mill"}, "list of names", []),
    ("mirror_schedule", {"spur": "Ashgrove Cannery", "sources": ["Ashgrove Feed Mill"], "name": 5}, "must be text", []),
    ("setup_custom_staging", {"track": "West Stage 1", "ship_loads": "Coal"}, "list of names", []),
    ("setup_custom_staging", {"track": "West Stage 1", "ship_loads": ["Nope"]}, "Unknown load", []),
    ("setup_interchange", {"track": "Quarry Interchange", "set_out_by": "BV1"}, "list of names", []),
    ("setup_interchange", {"track": "Quarry Interchange", "destinations": [5]}, "list of names", []),
    ("add_route", {"name": "R9", "stops": None}, "list of objects", []),
    ("add_route", {"name": "R9", "stops": ["Brackwater"]}, "list of objects", []),
    ("add_route", {"name": "R9", "stops": TWO_STOPS, "comment": 5}, "must be text", []),
    ("add_route", {"name": "R9", "stops": [{"location": "Brackwater", "max_moves": -1}]}, "less than", []),
    ("add_route", {"name": "R9", "stops": [{"location": "Brackwater", "comment": 5}]}, "must be text", []),
    ("update_stop", {"route": "Main East", "stop": True, "max_moves": 5}, "location name or a position", []),
    ("update_stop", {"route": "Main East", "stop": 1}, "Nothing to change", []),
    ("update_stop", {"route": "Main East", "stop": 99, "max_moves": 5}, "stops", []),
    ("rename_route", {"route": "Main East", "new": None}, "must be text", []),
    ("delete_route", {"route": None}, "as text", []),
    ("add_train", {"name": "NT", "route": "Main East", "like": 5}, "must be text", []),
    ("add_train", {"name": "NT", "route": "Main East", "roads": "BVR"}, "must be an object", []),
    ("add_train", {"name": "NT", "route": "Main East", "description": None}, "must be text", []),
    ("update_train", {"train": "BV1", "add_types": "Boxcar"}, "list of names", []),
    ("update_train", {"train": "BV1", "depart_hour": 99}, "0 to 23", []),
    ("update_train", {"train": "BV1", "comment": 5}, "must be text", []),
    ("set_train_route", {"train": "BV1", "route": None}, "as text", []),
    ("set_train_skips", {"train": "BV1", "stops": "Tolvern"}, "list of names", []),
    ("set_train_skips", {"train": "BV1", "stops": None}, "list of names", []),
    ("rename_train", {"train": "BV1", "new": 5}, "must be text", []),
    ("delete_train", {"train": None}, "as text", []),
    ("set_active_day", {"name": 5}, "as text", []),
    ("set_active_day", {"name": ["Tuesday"]}, "as text", []),
    ("set_train_leg", {"train": "BV1", "leg": 2, "locos": ["change"]}, "locos must be", []),
    ("set_train_leg", {"train": "BV1", "leg": 4}, "leg must be 2 or 3", []),
    ("set_train_leg", {"train": "BV1", "leg": 2, "locos": "change", "start": "Brackwater", "model": 5}, "must be text", []),
    ("set_engine_moves", {"moves": {}}, "at least one", []),
    ("set_engine_moves", {"moves": {"BV101": 1.5}}, "whole number", []),
    ("set_engine_moves", {"moves": {"BV101": 10 ** 12}}, "at most", []),
    ("delete_load", {"name": None}, "must be text", []),
    ("delete_load", {"name": "Coal", "car_type": 5}, "must be text", []),
    ("set_manual_build", {"train": "BV1", "lines": "Boxcar"}, "list of objects", []),
    ("set_manual_build", {"train": "BV1", "lines": [None]}, "list of objects", []),
    ("set_manual_build", {"train": "BV1", "lines": [{"type": "Boxcar"}], "comment": 5}, "must be text", []),
    ("delete_manual_build", {"train": "BV1"}, "no manual build", []),
    ("add_automation", {"name": "A1", "steps": [5]}, "must be an object", []),
    ("add_automation", {"name": "A1", "steps": []}, "at least one step", []),
    ("add_automation", {"name": None, "steps": [{"do": "halt"}]}, "needs a name", []),
    ("update_automation", {"automation": "Nope", "name": "A2"}, "No automation", []),
    ("delete_automation", {"automation": 5}, "automation", []),
    ("set_startup_automation", {"automation": ["A1"]}, "as text", []),
    ("set_engine_division", {"division": 5, "engines": ["BV101"]}, "by name or id as text", []),
    ("set_control_limits", {"bogus": 1}, "Unknown control values", []),
    ("set_manifest_creator", {"directory": 5}, "must be text", []),
    ("set_manifest_creator", {"creator": "nope"}, "creator must be one of", []),
    ("set_train_options", {"train_action": 5}, "train_action must be one of", []),
]


class Refusals(Case):
    def test_every_row_is_refused_with_its_message(self):
        for name, args, text, before in ROWS:
            with self.subTest(action=name, args=args):
                editor = ops_actions.Editor(self.ops)
                if before:
                    editor.run(before)
                with self.assertRaises(Refused) as caught:
                    ops_actions.ACTIONS[name]["run"](editor, **args)
                self.assertIn(text.lower(), str(caught.exception).lower())

    def test_every_group_action_has_a_refusal_row(self):
        skipped = {"add_station_track"}
        covered = {row[0] for row in ROWS}
        import ops_actions_setup
        setup = {n for n, e in ops_actions.ACTIONS.items() if e["run"].__module__ == ops_actions_setup.__name__}
        missing = sorted(set(ops_actions.ACTIONS) - covered - setup - skipped)
        self.assertEqual(missing, [])


if __name__ == "__main__":
    unittest.main()
