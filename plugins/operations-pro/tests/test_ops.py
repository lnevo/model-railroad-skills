"""Gates and audit against the demo railroad. Each fault in the fixture has a test.

jmri_oracle.json is what real JMRI 5.16 said about the same files; tests/jmri_oracle.py
regenerates it. The oracle tests hold this code to JMRI rather than to our reading of it.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = ROOT / "servers"
DEMO = ROOT / "tests" / "fixtures" / "demo"
sys.path.insert(0, str(SERVERS))

import ops_data  # noqa: E402
from ops_gates import FAIL, GATES, Gates  # noqa: E402

OPS = DEMO / "operations"


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rr = ops_data.load(OPS)
        cls.gates = Gates(cls.rr)

    def failed(self, car, destination, track=None, train=None):
        result = self.gates.why_not(car, destination, track, train)
        return {g["gate"] for g in result["gates"] if g["status"] == FAIL}


class ParserTests(Base):
    def test_counts_match_jmri(self):
        oracle = json.loads((DEMO / "jmri_oracle.json").read_text())
        rr = self.rr
        self.assertEqual((len(rr.cars), len(rr.engines), len(rr.locations), len(rr.routes), len(rr.trains)),
                         (oracle["cars"], oracle["engines"], oracle["locations"], oracle["routes"], oracle["trains"]))

    def test_default_loads_come_from_the_file(self):
        self.assertEqual((self.rr.default_empty, self.rr.default_load), ("Mty", "L"))

    def test_missing_file_is_named(self):
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaisesRegex(FileNotFoundError, "OperationsCarRoster.xml"):
                ops_data.load(empty)

    def test_parent_folder_is_accepted(self):
        self.assertEqual(len(ops_data.load(DEMO).cars), len(self.rr.cars))

    def test_used_length_is_rebuilt_with_couplers(self):
        self.assertEqual(self.rr.used_length(self.rr.tracks["1s5"]), 88)

    def test_split_name_needs_number_or_parenthesis(self):
        self.assertEqual(ops_data.split_name("Town-2"), "Town")
        self.assertEqual(ops_data.split_name("Town-(yard)"), "Town")
        self.assertEqual(ops_data.split_name("Town-yard"), "Town-yard")

    def test_built_range_is_exclusive(self):
        train = self.rr.find_train("BV2")
        self.assertFalse(train.accepts_built("1980"))
        self.assertFalse(train.accepts_built("1950"))
        self.assertTrue(train.accepts_built("1979"))
        self.assertTrue(train.accepts_built("3-79"))

    def test_exclude_filter_list_holds_accepted_ids(self):
        track = self.rr.tracks["1s4"]
        self.assertEqual(track.destination_option, "Exclude")
        self.assertTrue(track.accepts_destination("3"))
        self.assertFalse(track.accepts_destination("6"))


class AgainstRealJmri(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.oracle = json.loads((DEMO / "jmri_oracle.json").read_text())

    def test_check_destination_matches_every_car_and_track(self):
        for car_id, row in self.oracle["destination"].items():
            for track_id, status in row.items():
                track = self.rr.tracks[track_id]
                ok, gate = self.gates.destination_status(
                    self.rr.cars[car_id], self.rr.locations[track.location_id], track)
                with self.subTest(car=car_id, track=track.name, jmri=status, gate=gate):
                    self.assertEqual(ok, status == "okay")

    def test_is_serviceable_matches_every_car_and_train(self):
        for car_id, row in self.oracle["serviceable"].items():
            for train_id, status in row.items():
                results = self.gates.serviceable(self.rr.cars[car_id], self.rr.trains[train_id])
                with self.subTest(car=car_id, train=train_id):
                    self.assertEqual(not any(g["status"] == FAIL for g in results), status)

    def test_every_car_jmri_assigned_passes_the_gates(self):
        builds = self.oracle["builds"]
        for train, build in builds.items():
            for line in build["cars"]:
                car, name = line.split(" > ")
                track = self.rr.find_track(name)
                with self.subTest(train=train, car=car, track=name):
                    self.assertEqual(self.failed(car, track.location_id, track.id, train), set())

    def test_trains_build_except_the_one_the_audit_predicts(self):
        failed = {k for k, v in self.oracle["builds"].items() if v["failed"]}
        predicted = {f["subject"] for f in self.gates.audit()["findings"]
                     if f["rule"] == "staging-departure-blocked"}
        self.assertEqual(failed, {"X99"})
        self.assertEqual(predicted, failed)

    def test_router_path_is_the_one_jmri_chose(self):
        self.assertIn("QXR3018 > Lakeshore Interchange", self.oracle["builds"]["T10"]["cars"])
        path = self.gates.route_path(self.rr.find_car("QXR3018"), self.rr.tracks["3s2"])
        self.assertEqual([p["train"] for p in path], ["T10", "T30"])
        self.assertEqual(path[0]["to"], "Brackwater, Lakeshore Interchange")


class WhyNotShape(Base):
    def test_gates_come_back_in_code_order(self):
        result = self.gates.why_not("BVR1001", "Tolvern")
        self.assertEqual([g["gate"] for g in result["gates"]], list(GATES))

    def test_clear_car_can_move(self):
        result = self.gates.why_not("BVR 1001", "Tolvern", "Tolvern Yard")
        self.assertTrue(result["can_move"])
        self.assertTrue(result["direct"])
        self.assertEqual(result["train"], "BV1")
        self.assertIsNone(result["first_failure"])

    def test_failure_names_reason_screen_and_setting(self):
        result = self.gates.why_not("BVR3001", "Tolvern")
        failure = result["first_failure"]
        self.assertEqual(failure["gate"], "B3")
        self.assertFalse(result["can_move"])
        self.assertIn("out of service", failure["reason"])
        self.assertEqual(failure["fix"], {"screen": "Set Car", "setting": "Out of Service"})

    def test_every_gate_has_a_fix(self):
        for code, (test, screen, setting) in GATES.items():
            with self.subTest(gate=code):
                self.assertTrue(test and screen and setting)

    def test_gates_decided_only_by_a_build_are_not_guessed(self):
        result = self.gates.why_not("BVR1001", "Tolvern")
        status = {g["gate"]: g["status"] for g in result["gates"]}
        self.assertEqual(status["A2"], "not_checked")
        self.assertEqual(status["D18"], "not_checked")

    def test_other_trains_are_summarised(self):
        result = self.gates.why_not("BVR1001", "Tolvern")
        self.assertTrue(any(row["train"] == "T10" and row["first_failure"] for row in result["other_trains"]))

    def test_default_load_is_not_routed(self):
        result = self.gates.why_not("BVR1001", "Tolvern")
        self.assertIn("router never runs", result["routing"])
        self.assertIsNone(result["router_path"])

    def test_car_with_final_destination_chains_trains(self):
        result = self.gates.why_not("QXR3018", "Tolvern", "Tolvern Yard")
        self.assertFalse(result["direct"])
        self.assertTrue(result["can_move"])
        self.assertEqual(len(result["router_path"]), 2)

    def test_router_does_not_excuse_an_out_of_service_car(self):
        car = self.rr.at(self.rr.find_car("QXR3018"), "2", "2s1")
        car.fd_id, car.fd_track_id, car.out_of_service = "3", "3s2", True
        self.assertFalse(self.gates.why_not(car, "Tolvern", "Tolvern Yard")["can_move"])

    def test_unknown_names_are_refused(self):
        with self.assertRaises(KeyError):
            self.gates.why_not("NOPE1", "Tolvern")
        with self.assertRaises(KeyError):
            self.gates.why_not("BVR1001", "Nowhere")


class GateFaults(Base):
    """One deliberate fault each: car, destination, and optionally track and train."""

    def assert_fails(self, gate, car, destination, track=None, train=None):
        self.assertIn(gate, self.failed(car, destination, track, train))

    def test_b0_car_with_no_location(self):
        self.assert_fails("B0", "BVR3004", "Tolvern")

    def test_b0_location_not_on_any_route(self):
        self.assert_fails("B0", "BVR3013", "Tolvern")

    def test_b1_car_with_no_track(self):
        self.assert_fails("B1", "BVR3003", "Tolvern")

    def test_b2_location_unknown(self):
        self.assert_fails("B2", "BVR3002", "Tolvern")

    def test_b3_out_of_service(self):
        self.assert_fails("B3", "BVR3001", "Tolvern")

    def test_b6_same_route_at_open_interchange(self):
        self.assert_fails("B6", "BVR3006", "Ashgrove", train="T10")

    def test_b7_track_pick_up_list(self):
        self.assert_fails("B7", "BVR3019", "Brackwater", train="T10")

    def test_b8_interchange_with_no_exit(self):
        self.assert_fails("B8", "BVR3007", "Ashgrove", train="T10")

    def test_b9_train_refuses_road(self):
        self.assert_fails("B9", "QXR3009", "Tolvern", train="BV1")

    def test_b10_train_refuses_type(self):
        self.assert_fails("B10", "BVR4001", "Tolvern")

    def test_b11_train_refuses_owner(self):
        self.assert_fails("B11", "BVR3008", "Ashgrove", train="T10")

    def test_b12_built_on_the_boundary(self):
        self.assert_fails("B12", "BVR3005", "Brackwater", train="BV2")

    def test_b13_train_refuses_type_and_load(self):
        self.assert_fails("B13", "BVR4003", "Tolvern")

    def test_b14_fred_car_on_a_train_without_fred(self):
        self.assert_fails("B14", "BVR3010", "Tolvern")

    def test_b15_pick_up_day(self):
        self.assert_fails("B15", "BVR3012", "Tolvern")

    def test_b16_wait_count(self):
        self.assert_fails("B16", "BVR3011", "Tolvern")

    def test_b18_split_kernel(self):
        self.assert_fails("B18", "BVR3013", "Tolvern")

    def test_b20_car_on_staging_track_that_cannot_depart(self):
        self.assert_fails("B20", "BVR6001", "Brackwater", train="X99")

    def test_a8_departure_staging_blocked(self):
        self.assert_fails("A8", "BVR6001", "Brackwater", train="X99")

    def test_c4_stop_direction_against_location(self):
        self.assert_fails("C4", "BVR3005", "Brackwater", train="BV2")

    def test_c9_track_direction(self):
        self.assert_fails("C9", "BVR4005", "Tolvern", train="BV1")

    def test_c10_staging_ship_refuses_load(self):
        self.assert_fails("C10", "BVR6002", "Brackwater", train="X99")

    def test_c10_generator_covers_the_default_empty(self):
        self.assertNotIn("C10", self.failed("BVR6001", "Brackwater", train="X99"))

    def test_d1_destination_behind_the_car(self):
        self.assert_fails("D1", "BVR1001", "Ashgrove", train="BV1")

    def test_d3_stop_with_no_moves(self):
        self.assert_fails("D3", "BVR6001", "Brackwater", train="X99")

    def test_d6_departure_filter(self):
        self.assert_fails("D6", "BVR3006", "West Staging", train="BV2")

    def test_g12_no_chain_of_trains(self):
        self.assert_fails("G12", "BVR3015", "Quarry Staging")

    def test_d7_location_refuses_type(self):
        self.assert_fails("D7", "BVR3017", "Ashgrove", train="T10")

    def test_d15_track_set_out_list(self):
        self.assert_fails("D15", "BVR1002", "Ashgrove", "Ashgrove Cannery", "T10")

    def test_e2_location_refuses_type(self):
        self.assert_fails("E2", "BVR3017", "Ashgrove", "Ashgrove Feed Mill", "T10")

    def test_e3_no_track_takes_reefers(self):
        self.assert_fails("E3", "BVR4002", "Tolvern", "Tolvern Yard")

    def test_e4_track_refuses_road(self):
        self.assert_fails("E4", "QXR3009", "Brackwater", "Brackwater Yard A", "Y20")

    def test_e6_filter_refuses_final_destination(self):
        self.assert_fails("E6", "BVR3015", "Brackwater", "Lakeshore Interchange", "Y20")

    def test_e7_routed_track(self):
        self.assert_fails("E7", "BVR1001", "Tolvern", "Tolvern Interchange")

    def test_e8_track_refuses_type_and_load(self):
        self.assert_fails("E8", "BVR3015", "Brackwater", "Lakeshore Interchange", "Y20")

    def test_e9_track_full(self):
        result = self.gates.why_not("BVR1001", "Brackwater", "Brackwater Team Track", "Y20")
        gate = next(g for g in result["gates"] if g["gate"] == "E9")
        self.assertEqual(gate["status"], FAIL)
        self.assertIn("full", gate["reason"])

    def test_e9_car_longer_than_track(self):
        result = self.gates.why_not("BVR4001", "Brackwater", "Brackwater Team Track", "Y20")
        gate = next(g for g in result["gates"] if g["gate"] == "E9")
        self.assertIn("longer", gate["reason"])

    def test_e10_custom_load_at_unscheduled_spur(self):
        self.assert_fails("E10", "BVR1003", "Brackwater", "Brackwater Team Track", "Y20")

    def test_e10_sequential_schedule_uses_only_the_current_line(self):
        self.assert_fails("F2", "BVR1004", "Ashgrove", "Ashgrove Cannery", "BV1")

    def test_f4_match_schedule_refuses_load(self):
        self.assert_fails("F4", "BVR1001", "Ashgrove", "Ashgrove Feed Mill", "T10")

    def test_g1_router_load_test(self):
        self.assert_fails("G1", "BVR4003", "Tolvern")

    def test_yard_ignores_pick_up_list(self):
        track = self.rr.tracks["1s2"]
        self.assertEqual((track.raw_pickup_option, track.pickup_ids), ("trains", ["3"]))
        self.assertNotIn("B7", self.failed("BVR1003", "Ashgrove", train="BV2"))

    def test_spur_ignores_routed_flag_and_ship_options(self):
        track = self.rr.tracks["1s5"]
        self.assertTrue(track.raw_only_fd)
        self.assertFalse(track.only_fd)
        self.assertEqual(track.ship_option, "All")


class AuditFaults(Base):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.report = cls.gates.audit()

    def assert_found(self, rule, subject):
        hits = [f for f in self.report["findings"] if f["rule"] == rule and f["subject"] == subject]
        self.assertTrue(hits, f"{rule} did not flag {subject}")
        self.assertTrue(hits[0]["fix"]["screen"] and hits[0]["fix"]["setting"])

    def test_type_no_train(self):
        self.assert_found("type-no-train", "Flatcar")

    def test_type_no_track(self):
        self.assert_found("type-no-track", "Reefer")

    def test_load_no_train(self):
        self.assert_found("load-no-train", "Tank Acid")

    def test_load_no_track(self):
        self.assert_found("load-no-track", "Scalecar Weights")

    def test_load_no_receiver(self):
        self.assert_found("load-no-receiver", "Gondola Scrap")

    def test_single_receiver_load(self):
        self.assert_found("single-receiver-load", "Boxcar Grain")

    def test_routing_gap(self):
        self.assert_found("routing-gap", "Boxcar Feed")

    def test_single_destination_schedule(self):
        self.assert_found("single-destination-schedule", "Coal Dock")

    def test_schedule_unused(self):
        self.assert_found("schedule-unused", "Unused Siding Plan")

    def test_yard_pick_up_list(self):
        self.assert_found("yard-pickup-list", "Brackwater Yard B")

    def test_yard_set_out_list(self):
        self.assert_found("yard-drop-list", "Brackwater Yard B")

    def test_destinations_on_yard(self):
        self.assert_found("destinations-ignored", "Tolvern Yard")

    def test_routed_on_spur(self):
        self.assert_found("only-fd-ignored", "Brackwater Team Track")

    def test_ship_options_on_spur(self):
        self.assert_found("ship-option-ignored", "Brackwater Team Track")

    def test_schedule_on_yard(self):
        self.assert_found("schedule-on-non-spur", "Tolvern Yard")

    def test_alternate_on_yard(self):
        self.assert_found("alternate-ignored", "Brackwater Yard A")

    def test_interchange_as_alternate(self):
        self.assert_found("interchange-as-alternate", "Tolvern Interchange")

    def test_interchange_no_exit(self):
        self.assert_found("interchange-no-exit", "Quarry Interchange")

    def test_custom_empty_flagged_load(self):
        self.assert_found("custom-empty-flagged-load", "Boxcar MTY")

    def test_load_flagged_empty(self):
        self.assert_found("load-flagged-empty", "Hopper Cinders")

    def test_renamed_default_collision(self):
        self.assert_found("renamed-default-collision", "Boxcar MTY")

    def test_blank_receive_on_staging_fed_spur(self):
        self.assert_found("blank-receive-on-staging-fed-spur", "Tolvern Scrap Shed")

    def test_generator_no_target(self):
        self.assert_found("generator-no-target", "Quarry Stage 1")

    def test_staging_ship_excludes_empty(self):
        self.assert_found("staging-ship-excludes-empty", "Quarry Stage 1")

    def test_staging_departure_blocked(self):
        self.assert_found("staging-departure-blocked", "X99")

    def test_caboose_road_mismatch(self):
        self.assert_found("caboose-road-mismatch", "X99")

    def test_route_direction_mismatch(self):
        self.assert_found("route-direction-mismatch", "Main West, Tolvern")

    def test_track_direction_unserved(self):
        self.assert_found("track-direction-unserved", "Brackwater Old Spur")

    def test_route_stop_dead(self):
        self.assert_found("route-stop-dead", "Quarry Extra, Brackwater")

    def test_list_stale_id(self):
        self.assert_found("list-stale-id", "Ashgrove Cannery")

    def test_train_not_on_list(self):
        self.assert_found("train-not-on-list", "Ashgrove Cannery")

    def test_built_boundary(self):
        self.assert_found("built-boundary", "BVR 3005")

    def test_rwe_to_unscheduled_spur(self):
        self.assert_found("rwe-to-unscheduled-spur", "BVR 3016")

    def test_kernel_split(self):
        self.assert_found("kernel-split", "Pair")

    def test_car_unplaced(self):
        self.assert_found("car-unplaced", "BVR 3003")

    def test_car_on_refusing_track(self):
        self.assert_found("car-on-refusing-track", "BVR 4002")

    def test_location_unserved(self):
        self.assert_found("location-unserved", "Ashgrove-North")

    def test_hyphen_no_split(self):
        self.assert_found("hyphen-no-split", "Ashgrove-North")

    def test_switcher_local_off(self):
        self.assert_found("switcher-local-off", "Y20")

    def test_healthy_things_stay_quiet(self):
        subjects = {f["subject"] for f in self.report["findings"]}
        self.assertNotIn("Boxcar", subjects)
        self.assertNotIn("BV1", subjects)
        self.assertNotIn("Brackwater Yard A", {f["subject"] for f in self.report["findings"]
                                               if f["rule"] != "alternate-ignored"})


def call(env, *messages):
    lines = "".join(json.dumps(m) + "\n" for m in messages)
    out = subprocess.run([sys.executable, str(SERVERS / "operations_pro.py")], input=lines, text=True,
                         capture_output=True, env={**os.environ, **env}, timeout=30, check=True)
    return [json.loads(line) for line in out.stdout.splitlines()]


def tool(name, arguments, request_id=2):
    return {"jsonrpc": "2.0", "id": request_id, "method": "tools/call",
            "params": {"name": name, "arguments": arguments}}


INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}


class ServerTests(unittest.TestCase):
    env = {"OPS_DIR": str(OPS)}

    def text(self, response):
        return response["result"]["content"][0]["text"]

    def test_lists_read_only_tools(self):
        out = call(self.env, INIT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = out[1]["result"]["tools"]
        self.assertEqual({t["name"] for t in tools}, {"ops_why_not", "ops_audit", "ops_list"})
        self.assertTrue(all(t["annotations"]["readOnlyHint"] for t in tools))

    def test_why_not_over_the_wire(self):
        out = call(self.env, INIT, tool("ops_why_not", {"car": "BVR3001", "destination": "Tolvern"}))
        self.assertEqual(json.loads(self.text(out[1]))["first_failure"]["gate"], "B3")

    def test_audit_over_the_wire(self):
        out = call(self.env, INIT, tool("ops_audit", {}))
        self.assertGreater(json.loads(self.text(out[1]))["counts"]["error"], 0)

    def test_every_list_type(self):
        for kind in ("locations", "tracks", "schedules", "routes", "trains", "cars", "engines", "loads"):
            out = call(self.env, INIT, tool("ops_list", {"type": kind}))
            with self.subTest(kind=kind):
                self.assertNotIn("isError", out[1]["result"])
                self.assertTrue(json.loads(self.text(out[1])))

    def test_ops_dir_argument_beats_nothing_set(self):
        out = call({"OPS_DIR": ""}, INIT, tool("ops_audit", {"ops_dir": str(OPS)}))
        self.assertNotIn("isError", out[1]["result"])

    def test_no_directory_is_a_clear_error(self):
        out = call({"OPS_DIR": ""}, INIT, tool("ops_audit", {}))
        self.assertTrue(out[1]["result"]["isError"])
        self.assertIn("OPS_DIR", self.text(out[1]))

    def test_nothing_writes_to_the_operations_directory(self):
        before = {p.name: p.stat().st_mtime_ns for p in OPS.iterdir()}
        call(self.env, INIT, tool("ops_audit", {}))
        self.assertEqual({p.name: p.stat().st_mtime_ns for p in OPS.iterdir()}, before)

    def test_plugin_stays_stdlib_only(self):
        allowed = {"__future__", "collections", "dataclasses", "json", "os", "pathlib", "re", "sys",
                   "typing", "xml", "mcp_stdio", "ops_data", "ops_gates"}
        for path in SERVERS.glob("*.py"):
            for line in path.read_text().splitlines():
                words = line.split()
                if len(words) > 1 and words[0] in ("import", "from") and not line.startswith(" "):
                    with self.subTest(file=path.name):
                        self.assertIn(words[1].split(".")[0], allowed)


if __name__ == "__main__":
    unittest.main()
