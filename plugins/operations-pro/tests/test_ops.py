"""Gates and audit against the demo railroad. Each fault in the fixture has a test.

jmri_oracle.json is what real JMRI 5.16 said about the same files; tests/jmri_oracle.py
regenerates it. The oracle tests hold this code to JMRI rather than to our reading of it.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from dataclasses import replace
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
        """A folder with no roster file is a railroad from nothing; one that lost a file is refused."""
        with tempfile.TemporaryDirectory() as empty:
            for name in ops_data.REQUIRED[:3]:
                (Path(empty) / name).write_bytes((DEMO / "operations" / name).read_bytes())
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


class OracleChecks:
    """What real JMRI 5.16 answered for one fixture, held against the gates. FIXTURE names the folder."""
    FIXTURE = DEMO

    @classmethod
    def setUpClass(cls):
        cls.rr = ops_data.load(cls.FIXTURE / "operations")
        cls.gates = Gates(cls.rr)
        cls.oracle = json.loads((cls.FIXTURE / "jmri_oracle.json").read_text())

    def failed(self, car, destination, track=None, train=None):
        result = self.gates.why_not(car, destination, track, train)
        return {g["gate"] for g in result["gates"] if g["status"] == FAIL}

    def test_counts_match_jmri(self):
        rr, oracle = self.rr, self.oracle
        self.assertEqual((len(rr.cars), len(rr.engines), len(rr.locations), len(rr.routes), len(rr.trains)),
                         (oracle["cars"], oracle["engines"], oracle["locations"], oracle["routes"], oracle["trains"]))

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

    def test_build_blockers_name_exactly_the_trains_jmri_did_not_build(self):
        for train in self.rr.trains.values():
            blockers = self.gates.build_blockers(train)
            with self.subTest(train=train.name, blockers=[g["gate"] for g in blockers]):
                self.assertEqual(not blockers, self.oracle["builds"][train.name]["built"])


class AgainstRealJmri(OracleChecks, unittest.TestCase):
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


def gate_of(result, code):
    return next(g for g in result["gates"] if g["gate"] == code)


class BuildVariant(OracleChecks, unittest.TestCase):
    """tests/variant_fixtures.py build: on-time order, a bad random value, staging checks, a manual line.
    JMRI built only BV1; the build reports name these causes for the others."""
    FIXTURE = DEMO.parent / "build"

    def status(self, car, destination, train, code):
        return gate_of(self.gates.why_not(car, destination, train=train), code)

    def test_a2_on_time_order_refuses_a_train_departing_before_the_last_built(self):
        # TrainManager.checkBuildOrder 1106-1123; T30 is built and departs at 10:00.
        self.assertEqual(self.status("BVR1001", "Tolvern", "T10", "A2")["status"], FAIL)
        self.assertEqual(self.status("BVR1001", "Tolvern", "BV1", "A2")["status"], "pass")
        self.assertFalse(self.oracle["builds"]["T10"]["built"])

    def test_a6_random_that_is_not_a_number_fails_the_build(self):
        # TrainBuilderBase 527-530: buildErrorRandomControl.
        a6 = self.status("BVR2001", "Tolvern", "T30", "A6")
        self.assertEqual(a6["status"], FAIL)
        self.assertIn("abc", a6["reason"])

    def test_a7_terminal_staging_must_take_every_type_the_train_carries(self):
        # TrainBuilderBase 2085-2153 with stagingRestrictionEnabled; West Staging takes no Scalecar.
        a7 = self.status("BVR1103", "West Staging", "BV2", "A7")
        self.assertEqual(a7["status"], FAIL)
        self.assertIn("Scalecar", a7["reason"])
        self.assertEqual(self.status("BVR1001", "East Staging", "BV1", "A7")["status"], "pass")

    def test_a8_departure_locomotive_must_be_the_train_model(self):
        # TrainBuilderBase 1803-1810: buildStagingDepartEngineModel. BV1 asks for an SD40.
        a8 = self.status("BVR1101", "Tolvern", "BV1", "A8")
        self.assertEqual(a8["status"], FAIL)
        self.assertIn("SD40", a8["reason"])

    def test_b19_manual_line_short_of_cars_fails_the_build(self):
        # TrainBuilder 386-390: mbuildFail. One gondola on the route, the line asks for five.
        self.assertEqual(self.status("BVR1001", "Brackwater", "Y20", "B19")["status"], FAIL)


class SpaceVariant(OracleChecks, unittest.TestCase):
    """tests/variant_fixtures.py space: a pool, planned pick ups, a short leg, a division, a caboose."""
    FIXTURE = DEMO.parent / "space"

    def status(self, car, destination, track, train, code):
        return gate_of(self.gates.why_not(car, destination, track, train), code)

    def assigned(self):
        return {line.split(" > ")[0] for build in self.oracle["builds"].values() for line in build["cars"]}

    def test_e9_pool_lends_length_even_to_a_car_longer_than_the_track(self):
        # Track 1633-1645 and Pool.requestTrackLength; JMRI said okay for both (destination oracle).
        for car in ("BVR1001", "BVR4001"):
            e9 = self.status(car, "Brackwater", "Brackwater Team Track", "Y20", "E9")
            self.assertEqual(e9["status"], "pass", car)
            self.assertIn("pool", e9["reason"])
        self.assertEqual(self.oracle["destination"]["BVR4001"]["1s5"], "okay")

    def test_e9_planned_pick_ups_free_an_overfull_yard(self):
        # Track.checkPlannedPickUps and getAvailableTrackSpace: 400 + 400 - 677 leaves 123.
        e9 = self.status("BVR1003", "Brackwater", "Brackwater Yard A", "Y20", "E9")
        self.assertEqual(e9["status"], "pass")
        self.assertIn("planned pick ups", e9["reason"])

    def test_d9_counts_the_locomotive_against_max_length(self):
        # checkTrainLength: the GP9 (60 with couplers) is in the train before any car; Tolvern allows 100.
        self.assertEqual(self.status("BVR3008", "East Staging", "East Stage 2", "BV1", "D9")["status"], FAIL)
        self.assertNotEqual(self.status("BVR2002", "East Staging", "East Stage 2", "BV1", "D9")["status"], FAIL)
        to_east = [line for line in self.oracle["builds"]["BV1"]["cars"] if "East Stage" in line]
        self.assertEqual(to_east, ["BVR2002 > East Stage 2"])

    def test_g10_tests_length_only_for_the_train_being_built(self):
        # Train.isTrainLengthOkay 2120-2134 is true unless the train is building.
        car = replace(self.rr.find_car("BVR3008"), destination_id="5", fd_id="5")
        train = self.rr.find_train("BV1")
        self.assertEqual(gate_of({"gates": self.gates.serviceable(car, train)}, "G10")["status"], "pass")
        self.assertEqual(gate_of({"gates": self.gates.serviceable(car, train, building=True)}, "G10")["status"], FAIL)

    def test_c12_a_home_division_with_no_track_holds_the_car(self):
        # TrainBuilderCars 894-1035: no final destination found, so the car stays.
        self.assertEqual(self.status("BVR3006", "Tolvern", "Tolvern Yard", "BV1", "C12")["status"], FAIL)
        self.assertNotIn("BVR3006", self.assigned())

    def test_b17_a_caboose_no_train_asks_for_is_dropped(self):
        # removeCaboosesAndCarsWithFred, TrainBuilderBase 770-786.
        self.assertEqual(self.status("BVR9001", "Tolvern", "Tolvern Yard", "BV1", "B17")["status"], FAIL)
        self.assertNotIn("BVR9001", self.assigned())

    def test_b19_manual_line_takes_its_car_to_its_destination(self):
        self.assertEqual(self.status("BVR3008", "Brackwater", "Quarry Interchange", "Y20", "B19")["status"], "pass")
        self.assertEqual(self.status("BVR3008", "Brackwater", "Brackwater Yard B", "Y20", "B19")["status"],
                         "not_checked")
        self.assertIn("BVR3008 > Quarry Interchange", self.oracle["builds"]["Y20"]["cars"])

    def test_a6_random_draw_that_always_leaves_moves_passes(self):
        # Random 50 on 5 moves takes at most 2 (TrainBuilderBase 520).
        a6 = self.status("BVR1004", "Tolvern", "Tolvern Yard", "BV1", "A6")
        self.assertEqual(a6["status"], "pass")
        self.assertIn("at least 3 of 5", a6["reason"])


class AggressiveVariant(OracleChecks, unittest.TestCase):
    """tests/variant_fixtures.py aggressive: both East Staging tracks hold cars that are not leaving."""
    FIXTURE = DEMO.parent / "aggressive"

    def test_a7_aggressive_mode_needs_every_car_on_the_track_to_be_leaving(self):
        # TrainBuilderBase 2044-2050: numberRS must equal pickupRS on an occupied track.
        a7 = gate_of(self.gates.why_not("BVR1001", "Tolvern", train="BV1"), "A7")
        self.assertEqual(a7["status"], FAIL)
        self.assertIn("not all of them leaving", a7["reason"])
        rr = ops_data.load(self.FIXTURE / "operations")
        rr.find_car("BVR1103").destination_id = "3"
        self.assertEqual(gate_of(Gates(rr).why_not("BVR1001", "Tolvern", train="BV1"), "A7")["status"], "pass")

    def test_e9_aggressive_pulls_can_open_room_during_the_build(self):
        # Track.addPickupRS gives back a pulled car's length in aggressive mode. JMRI refused the full
        # Team Track before any build, then Y20 set BVR3008 out there after pulling from it.
        self.assertNotEqual(self.oracle["destination"]["BVR3008"]["1s5"], "okay")
        self.assertIn("BVR3008 > Brackwater Team Track", self.oracle["builds"]["Y20"]["cars"])
        e9 = gate_of(self.gates.why_not("BVR3008", "Brackwater", "Brackwater Team Track", "Y20"), "E9")
        self.assertEqual(e9["status"], "not_checked")
        self.assertIn("aggressive", e9["reason"])


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
        # Five moves at Tolvern and five other cars that may be placed first: the build decides.
        result = self.gates.why_not("BVR1001", "Tolvern", "Tolvern Yard", "BV1")
        status = {g["gate"]: g["status"] for g in result["gates"]}
        self.assertEqual(status["D3"], "not_checked")
        self.assertEqual((status["A2"], status["D18"]), ("pass", "pass"))

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

    def test_single_destination_schedule_quiet_when_it_works(self):
        hits = [f for f in self.report["findings"] if f["rule"] == "single-destination-schedule"]
        self.assertEqual(hits, [], "Coal Dock ships to one place that takes and is reached: no finding")

    def test_single_destination_schedule_flags_a_destination_that_cannot_take_the_load(self):
        rr = ops_data.load(OPS)
        dest = next(i.destination_id for sch in rr.schedules.values() if sch.name == "Coal Dock" for i in sch.items)
        for t in rr.tracks.values():
            if t.location_id == dest:
                t.types = [x for x in t.types if x != "Hopper"] if isinstance(t.types, list) else t.types - {"Hopper"}
        found = [f for f in Gates(rr).audit()["findings"]
                 if f["rule"] == "single-destination-schedule" and f["subject"] == "Coal Dock"]
        self.assertTrue(found)

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
        # Old Spur serves North and no road train calls there northbound, but Y20 switches Brackwater and a
        # local switcher ignores track direction (TBB:1479-1482, 1618-1622), so JMRI works the spur.
        # AuditAgainstJava.test_track_direction_* holds the case where the warning still fires.
        self.assertFalse([f for f in self.report["findings"] if f["rule"] == "track-direction-unserved"
                          and f["subject"] == "Brackwater Old Spur"])

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
        engine_rules = {"engine-no-train", "engine-on-refusing-track", "engine-location-refuses-type",
                        "consist-split", "model-type-no-train", "model-type-no-track"}
        self.assertEqual([f for f in self.report["findings"] if f["rule"] in engine_rules], [])


class AuditAgainstJava(Base):
    """Audit rules held to the JMRI 5.16 code paths a second review traced. Each test edits its own copy."""

    def fresh(self):
        rr = ops_data.load(OPS)
        return rr, Gates(rr)

    @staticmethod
    def hits(g, rule, subject=None):
        return [f for f in g.audit()["findings"] if f["rule"] == rule and subject in (None, f["subject"])]

    def test_blank_receive_on_another_spur_receives_a_custom_load(self):
        # Schedule.java:490-494: a blank Receive passes any load; TBC:1070-1096 tries every other spur.
        rr, g = self.fresh()
        self.assertTrue(self.hits(g, "load-no-receiver", "Gondola Scrap"))  # the shed's own blank line never counts
        rr.schedules["4"].items.append(ops_data.ScheduleItem(id="4c3", sequence=3, type="Gondola"))
        self.assertFalse(self.hits(g, "load-no-receiver", "Gondola Scrap"))
        single = self.hits(g, "single-receiver-load", "Gondola Scrap")
        self.assertTrue(single and "Tolvern Coal Dock" in single[0]["message"])

    def test_caboose_must_be_at_the_departure_not_anywhere_on_the_route(self):
        # TBC:113/148/175 look only at the stop given; none there is buildErrorReqDepature (TBC:199-201).
        rr, g = self.fresh()
        train = rr.find_train("T30")
        train.requires, train.caboose_road = 1, "QXR"
        caboose = ops_data.Car(id="QXR9500", road="QXR", number="9500", type="Caboose", length="30",
                               caboose=True, location_id="3", track_id="3s2")
        rr.cars[caboose.id] = caboose
        self.assertTrue(self.hits(g, "caboose-road-mismatch", "T30"))  # Tolvern is on the route, not the start
        caboose.location_id, caboose.track_id = "1", "1s1"
        self.assertFalse(self.hits(g, "caboose-road-mismatch", "T30"))

    def test_track_direction_is_ignored_where_a_switcher_works(self):
        rr, g = self.fresh()
        self.assertFalse(self.hits(g, "track-direction-unserved", "Brackwater Old Spur"))
        del rr.routes["4"]  # no switcher at Brackwater: only the road trains' directions count
        self.assertTrue(self.hits(g, "track-direction-unserved", "Brackwater Old Spur"))

    def test_track_direction_still_warns_where_no_switcher_calls(self):
        rr, g = self.fresh()
        rr.tracks["2s2"].dir = 4  # Ashgrove sees only East and West road trains
        self.assertTrue(self.hits(g, "track-direction-unserved", "Ashgrove Cannery"))

    def test_kernel_without_a_lead_flag_is_led_by_its_first_member(self):
        # RollingStockGroup.java:40-42: the first car added leads; Car.load sets the flag only when stored.
        rr, g = self.fresh()
        first, second = rr.find_car("BVR3013"), rr.find_car("BVR3014")
        second.track_id = first.track_id
        first.lead = second.lead = False
        self.assertFalse(self.hits(g, "kernel-split", "Pair"))
        first.out_of_service = True
        self.assertIn("No lead car", self.hits(g, "kernel-split", "Pair")[0]["message"])

    def test_car_on_a_track_whose_location_refuses_the_type(self):
        # Track.isTypeNameAccepted asks the location first (Track.java:977-982).
        rr, g = self.fresh()
        car = rr.find_car("BVR3017")
        self.assertEqual(car.type, "Gondola")
        car.location_id, car.track_id = "2", "2s2"
        hit = self.hits(g, "car-on-refusing-track", str(car))
        self.assertTrue(hit and "Ashgrove" in hit[0]["message"])

    def test_stale_pick_up_day_does_not_stop_load_generation(self):
        # TBB:2288-2303 tests only the set out day when it picks a line for a custom load.
        rr, g = self.fresh()
        line = rr.schedules["1"].items[0]
        line.pickup_day = "99"
        (pickup,) = self.hits(g, "day-stale-id", "Mill Receiving line 1c1")
        self.assertIn("still used", pickup["message"])
        self.assertNotIn("never", pickup["message"])
        line.pickup_day, line.setout_day = "", "99"
        (setout,) = self.hits(g, "day-stale-id", "Mill Receiving line 1c1")
        self.assertIn("never uses", setout["message"])


class EngineAudit(unittest.TestCase):
    """Locomotives against acceptance. Each test edits a copy of the demo files, since locomotive
    types are read from the files, and checks the finding with its subject and fix."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ops = Path(self.temp.name) / "operations"
        shutil.copytree(OPS, self.ops)

    def edit(self, name, change):
        path = self.ops / name
        tree = ET.parse(path)
        change(tree.getroot())
        tree.write(path, encoding="UTF-8", xml_declaration=True)

    def findings(self, rule):
        report = Gates(ops_data.load(self.ops)).audit()
        hits = [f for f in report["findings"] if f["rule"] == rule]
        for hit in hits:
            self.assertTrue(hit["fix"]["screen"] and hit["fix"]["setting"])
        return {f["subject"]: f for f in hits}

    @staticmethod
    def drop_loco_types(holders):
        for holder in holders:
            types = holder.find("types")
            for entry in list(types.findall("locoType")) if types is not None else []:
                types.remove(entry)

    def engine(self, root, identity):
        return next(e for e in root.iter("engine") if e.get("id") == identity)

    def test_model_type_no_train(self):
        # Train.isTypeNameAccepted: a train with no locomotive types takes no locomotive.
        self.edit("OperationsTrainRoster.xml", lambda r: self.drop_loco_types(r.iter("train")))
        self.assertIn("GP9", self.findings("model-type-no-train"))
        self.assertEqual(self.findings("engine-no-train"), {}, "the model finding covers its engines")

    def test_model_type_no_track_and_location_refuses_type(self):
        # Track.isTypeNameAccepted (Track:977) asks the location first.
        self.edit("OperationsLocationRoster.xml",
                  lambda r: self.drop_loco_types(r.findall("./locations/location")))
        self.assertIn("GP9", self.findings("model-type-no-track"))
        self.assertEqual(set(self.findings("engine-location-refuses-type")), {"BV 101", "BV 102", "BV 103"})
        self.assertEqual(self.findings("engine-on-refusing-track"), {}, "the location finding comes first")

    def test_engine_on_refusing_track(self):
        self.edit("OperationsLocationRoster.xml",
                  lambda r: self.drop_loco_types(t for t in r.iter("track") if t.get("id") == "4s1"))
        found = self.findings("engine-on-refusing-track")
        self.assertEqual(set(found), {"BV 101"})
        self.assertIn("Diesel", found["BV 101"]["message"])
        self.assertEqual(self.findings("model-type-no-track"), {}, "other tracks still take Diesel")

    def test_engine_no_train_applies_the_model_each_train_names(self):
        # getEngines (TrainBuilderEngines:201): a train naming a model skips every other model.
        def every_train_needs_gp9(root):
            for train in root.iter("train"):
                train.set("numberEngines", "1")
                train.set("engineModel", "GP9")
        self.edit("OperationsTrainRoster.xml", every_train_needs_gp9)
        self.edit("OperationsEngineRoster.xml", lambda r: self.engine(r, "BV103").set("model", "SD9"))
        found = self.findings("engine-no-train")
        self.assertEqual(set(found), {"BV 103"})
        self.assertIn("needs GP9", found["BV 103"]["message"])

    def test_engine_no_train_applies_loco_roads_and_owners(self):
        # getAndRemoveEnginesFromList (TrainBuilderEngines:45-58): loco road list and owner list.
        def roads(root):
            for train in root.iter("train"):
                train.set("locoRoadOption", "Exclude")
                ET.SubElement(ET.SubElement(train, "locoRoads"), "locoRoad", {"name": "BV"})
        self.edit("OperationsTrainRoster.xml", roads)
        found = self.findings("engine-no-train")
        self.assertEqual(set(found), {"BV 101", "BV 102", "BV 103"})
        self.assertIn("locomotive road BV", found["BV 101"]["message"])

    def test_out_of_service_engine_is_not_flagged(self):
        def roads(root):
            for train in root.iter("train"):
                train.set("locoRoadOption", "Exclude")
                ET.SubElement(ET.SubElement(train, "locoRoads"), "locoRoad", {"name": "BV"})
        self.edit("OperationsTrainRoster.xml", roads)
        self.edit("OperationsEngineRoster.xml", lambda r: self.engine(r, "BV103").set("outOfService", "true"))
        self.assertNotIn("BV 103", self.findings("engine-no-train"))

    def test_engine_no_train_is_quiet_when_one_train_takes_the_engine(self):
        def roads(root):
            trains = list(root.iter("train"))
            for train in trains[1:]:
                train.set("locoRoadOption", "Exclude")
                ET.SubElement(ET.SubElement(train, "locoRoads"), "locoRoad", {"name": "BV"})
        self.edit("OperationsTrainRoster.xml", roads)
        self.assertEqual(self.findings("engine-no-train"), {})

    def test_consist_split_is_quiet_when_members_share_a_track(self):
        def together(root):
            ET.SubElement(root.find("newConsists"), "consist", {"name": "Pair"})
            first = self.engine(root, "BV101")
            first.attrib.update(consist="Pair", leadConsist="true")
            other = self.engine(root, "BV102")
            other.attrib.update(consist="Pair", locationId=first.get("locationId"),
                                secLocationId=first.get("secLocationId"))
        self.edit("OperationsEngineRoster.xml", together)
        self.assertEqual(self.findings("consist-split"), {})

    def test_consist_split(self):
        def split(root):
            ET.SubElement(root.find("newConsists"), "consist", {"name": "Pair"})
            self.engine(root, "BV101").attrib.update(consist="Pair", leadConsist="true")
            self.engine(root, "BV102").set("consist", "Pair")
        self.edit("OperationsEngineRoster.xml", split)
        found = self.findings("consist-split")
        self.assertIn("Pair", found)
        self.assertEqual(found["Pair"]["fix"]["screen"], "Set Locomotive")


class ReviewFixes(Base):
    """Gate readings checked against JMRI 5.16 source (verification.md, Part 1). Each test names the
    Java it follows. Mutating tests load their own railroad so the shared one stays untouched."""

    def fresh(self):
        rr = ops_data.load(OPS)
        return rr, Gates(rr)

    @staticmethod
    def gate(result, code):
        return next(g for g in result["gates"] if g["gate"] == code)

    def test_staging_restriction_defaults_on_when_the_file_omits_it(self):
        # Setup.java:329 trainIntoStagingCheck = true; read from stagingRestrictionEnabled (Setup 2950).
        rr, g = self.fresh()
        rr.setup.get("buildOptions", {}).pop("stagingRestrictionEnabled", None)
        self.assertTrue(rr.option("buildOptions", "stagingRestrictionEnabled", True))
        a7 = self.gate(g.why_not("BVR1103", "West Staging", train="BV2"), "A7")
        self.assertEqual(a7["status"], FAIL)

    def test_c10_generator_only_covers_a_default_empty_it_can_replace(self):
        # TrainBuilderCars 546-558, 633-637, 658: the ship check runs when both generators fail.
        rr, g = self.rr, self.gates
        empty = self.gate(g.why_not("BVR6001", "Brackwater", train="X99"), "C10")
        self.assertEqual(empty["status"], "not_checked")
        self.assertIn("load generation", empty["reason"])
        custom = self.gate(g.why_not("BVR6002", "Brackwater", train="X99"), "C10")
        self.assertEqual(custom["status"], FAIL)
        routed = replace(rr.find_car("BVR6001"), fd_id="1")
        self.assertEqual(self.gate(g.why_not(routed, "Brackwater", train="X99"), "C10")["status"], FAIL)

    def test_g11_fails_a_train_with_build_off_and_the_router_skips_it(self):
        # TrainManager 556: isOnlyActiveTrainsEnabled && !train.isBuildEnabled.
        rr, g = self.fresh()
        rr.setup["router"]["onlyActiveTrains"] = "true"
        self.assertEqual([p["train"] for p in g.route_path(rr.find_car("QXR3018"), rr.tracks["3s2"])], ["T10", "T30"])
        self.assertEqual(self.gate(g.why_not("QXR3018", "Tolvern", "Tolvern Yard", "T30"), "G11")["status"], "pass")
        rr.find_train("T30").build = False
        self.assertEqual(self.gate(g.why_not("QXR3018", "Tolvern", "Tolvern Yard", "T30"), "G11")["status"], FAIL)
        self.assertIsNone(g.route_path(rr.find_car("QXR3018"), rr.tracks["3s2"]))

    def test_yard_routing_is_off_when_operations_xml_does_not_say(self):
        # Setup 310: carRoutingYards = false.
        rr, g = self.fresh()
        car = rr.find_car("BVR1004")  # Its only route to the feed mill is through Brackwater Yard B.
        self.assertEqual(g.route_path(car, rr.tracks["2s1"])[0]["to"], "Brackwater, Brackwater Yard B")
        del rr.setup["router"]["carRoutingViaYards"]
        self.assertIsNone(g.route_path(car, rr.tracks["2s1"]))

    def test_f5_random_is_skipped_when_the_final_destination_track_is_this_spur(self):
        # Schedule 483-489 compares car.getFinalDestinationTrack() with the spur; ScheduleItem 95-103
        # draws for any non-blank value, so "0" is drawn and a non-number never passes.
        rr, g = self.rr, self.gates
        track = rr.tracks["3s1"]
        item = replace(rr.schedules["4"].items[0], random="50")
        car = replace(rr.find_car("BVR2001"), load="Coal", fd_id="3", fd_track_id="3s1")

        def f5(car, item):
            return next(x for x in g._line(car, item, track) if x["gate"] == "F5")

        self.assertEqual(f5(car, item)["status"], "pass")
        self.assertEqual(f5(replace(car, fd_id="", fd_track_id=""), item)["status"], "not_checked")
        self.assertEqual(f5(replace(car, fd_id="", fd_track_id=""), replace(item, random="0"))["status"], "not_checked")
        self.assertEqual(f5(replace(car, fd_id="", fd_track_id=""), replace(item, random="x"))["status"], FAIL)
        self.assertEqual(f5(replace(car, fd_id="", fd_track_id=""), replace(item, random=""))["status"], "pass")

    def test_g9_allow_return_passes_before_the_local_move_rule(self):
        # Train 1939-1963: the return-to-staging check returns true before isLocalMoveAllowed.
        rr, g = self.fresh()
        stops = rr.routes["5"].stops
        stops.append(ops_data.Stop(id="5r3", name="Quarry Staging", location_id="6", direction=3))
        for stop in stops:
            stop.local = True
        train = rr.find_train("X99")
        train.local_moves = False
        car = replace(rr.find_car("BVR6001"), destination_id="6", dest_track_id="6s1")
        g9 = {x["gate"]: x for x in g.serviceable(car, train)}["G9"]
        self.assertEqual(g9["status"], FAIL)
        self.assertIn("local moves", g9["reason"])
        train.allow_return = True
        g9 = {x["gate"]: x for x in g.serviceable(car, train)}["G9"]
        self.assertEqual(g9["status"], "pass")
        self.assertIn("staging", g9["reason"])

    def test_b5_tests_only_the_assigned_destination(self):
        # TrainBuilderBase 870-890: the car's own destination, caboose exempt when a leg changes the caboose.
        rr, g = self.rr, self.gates
        caboose = replace(rr.find_car("BVR1001"), caboose=True, destination_id="3")
        self.assertEqual(self.gate(g.why_not(caboose, "Tolvern", "Tolvern Yard", "BV1"), "B5")["status"], FAIL)
        what_if = self.gate(g.why_not(replace(caboose, destination_id=""), "Tolvern", "Tolvern Yard", "BV1"), "B5")
        self.assertEqual(what_if["status"], "pass")
        self.assertIn("not one", what_if["reason"])
        changes = replace(rr.find_train("BV1"), leg2_options=ops_data.ADD_CABOOSE)
        self.assertEqual(self.gate(g.why_not(caboose, "Tolvern", "Tolvern Yard", changes), "B5")["status"], "pass")
        fred = replace(caboose, caboose=False, fred=True)
        self.assertEqual(self.gate(g.why_not(fred, "Tolvern", "Tolvern Yard", changes), "B5")["status"], FAIL)

    def test_b18_compares_split_track_names_and_needs_a_lead_in_service(self):
        # TrainBuilderBase 1213-1231: getSplitName on both tracks; a lead that is not out of service.
        rr, g = self.fresh()
        rr.tracks["7s1"].name, rr.tracks["7s2"].name = "North-1", "North-2"
        self.assertEqual(self.gate(g.why_not("BVR3014", "Tolvern"), "B18")["status"], "pass")
        self.assertNotIn("Pair", {f["subject"] for f in g.audit()["findings"] if f["rule"] == "kernel-split"})
        rr.find_car("BVR3013").out_of_service = True
        b18 = self.gate(g.why_not("BVR3014", "Tolvern"), "B18")
        self.assertEqual(b18["status"], FAIL)
        self.assertIn("0 lead", b18["reason"])
        self.assertIn("Pair", {f["subject"] for f in g.audit()["findings"] if f["rule"] == "kernel-split"})

    def test_d12_refuses_exactly_the_staging_tracks_a7_refuses(self):
        # TrainBuilderBase 2577-2612 tryStaging is car.checkDestination on the terminal track; which
        # track that is comes from checkTerminateStagingTrack (2038-2072).
        g = self.gates
        occupied = g.why_not("BVR1001", "East Staging", "East Stage 1", "BV1")
        self.assertEqual(self.gate(occupied, "A7")["status"], "pass")
        self.assertEqual(self.gate(occupied, "D12")["status"], FAIL)
        self.assertIn("occupied", self.gate(occupied, "D12")["reason"])
        empty = g.why_not("BVR1001", "East Staging", "East Stage 2", "BV1")
        self.assertEqual(self.gate(empty, "D12")["status"], "pass")
        self.assertTrue(empty["can_move"])

    def test_a7_counts_cars_already_destined_to_the_staging_track(self):
        # TrainBuilderBase 2067-2072: getDropRS() != 0 fails the track.
        rr, g = self.fresh()
        rr.find_car("BVR1001").destination_id, rr.find_car("BVR1001").dest_track_id = "5", "5s2"
        result = g.why_not("BVR1002", "East Staging", "East Stage 2", "BV1")
        self.assertEqual(self.gate(result, "A7")["status"], FAIL)
        self.assertIn("destined", self.gate(result, "D12")["reason"])

    def test_a7_checks_the_terminal_track_of_a_one_stop_route(self):
        # TrainBuilder 150-194 runs for any route whose terminate location is staging, one stop included.
        rr, g = self.fresh()
        rr.find_car("BVR1001").destination_id, rr.find_car("BVR1001").dest_track_id = "5", "5s2"
        train = rr.find_train("BV1")
        a7 = next(x for x in g._staging_gates(train, [rr.stops(train)[-1]]) if x["gate"] == "A7")
        self.assertEqual(a7["status"], FAIL)

    def test_d17_full_spur_with_an_alternate_is_not_decided(self):
        # TrainBuilderBase 2430-2449: the alternate must take the train and the car at that moment.
        rr, g = self.fresh()
        dock = rr.tracks["3s1"]
        dock.length = 60
        rr.find_car("BVR2001").location_id, rr.find_car("BVR2001").track_id = "3", "3s1"
        car = replace(rr.at(rr.find_car("BVR2002"), "1", "1s1"), load="Coal")
        result = g.why_not(car, "Tolvern", "Tolvern Coal Dock", "BV1")
        self.assertIn("full", self.gate(result, "E9")["reason"])
        d17 = self.gate(result, "D17")
        self.assertEqual(d17["status"], "not_checked")
        self.assertIn("Tolvern Interchange", d17["reason"])
        dock.raw_alternate_id = ""
        self.assertEqual(self.gate(g.why_not(car, "Tolvern", "Tolvern Coal Dock", "BV1"), "D17")["status"], "pass")

    def test_interchange_alternate_warning_names_the_router_and_the_pickup_trap(self):
        # LocationManager 329 skips alternates; TrainBuilderBase 1524-1533 is the same-route pull bar.
        hit = next(f for f in self.gates.audit()["findings"] if f["rule"] == "interchange-as-alternate")
        self.assertIn("every alternate", hit["message"])
        self.assertIn("Any", hit["message"])
        self.assertIn("same route", hit["message"])

    def test_a_day_id_no_schedule_holds_is_flagged_on_lines_and_cars(self):
        # B15/F1 pass an id that is not a train schedule (TrainBuilderBase 965, Schedule.checkScheduleItem).
        rr, g = self.fresh()
        stale = lambda: [f for f in g.audit()["findings"] if f["rule"] == "day-stale-id"]
        before = len(stale())
        line = next(i for s in rr.schedules.values() for i in s.items)
        line.setout_day, line.pickup_day = "99", "98"
        rr.find_car("BVR3012").pickup_day = "97"
        found = stale()
        self.assertEqual(len(found) - before, 3)
        self.assertTrue(all("any day" in f["message"] for f in found))
        rr.find_car("BVR3012").pickup_day = "ANY"
        line.setout_day = line.pickup_day = ""
        self.assertEqual(len(stale()), before)

    def test_foreign_option_words_are_warned_about(self):
        # Track 159-173 compares Bundle values, so a non-English file holds other words.
        self.assertEqual(self.rr.warnings, [])
        with tempfile.TemporaryDirectory() as temp:
            copy = Path(temp) / "operations"
            shutil.copytree(OPS, copy)
            trains = copy / "OperationsTrainRoster.xml"
            trains.write_text(trains.read_text().replace('carRoadOption="Exclude"', 'carRoadOption="Ausschliessen"'))
            warnings = ops_data.load(copy).warnings
        self.assertEqual(len(warnings), 1)
        self.assertIn("train BV1", warnings[0])
        self.assertIn("Ausschliessen", warnings[0])

    def test_g8_without_a_destination_track_ignores_the_schedule(self):
        # Train 1912-1917 uses track.isRollingStockAccepted (Track 1572-1663), which has no schedule test.
        rr, g = self.rr, self.gates
        car = replace(rr.find_car("BVR1003"), destination_id="2", load="Feed")
        for track in rr.locations["2"].tracks:
            self.assertEqual(g.destination_status(car, rr.locations["2"], track), (False, "E10"))
        self.assertEqual({x["gate"]: x["status"] for x in g.serviceable(car, rr.find_train("T10"))}["G8"], "pass")
        with_track = replace(car, dest_track_id="2s1")
        self.assertEqual({x["gate"]: x["status"] for x in g.serviceable(with_track, rr.find_train("T10"))}["G8"], "pass")

    def test_c7_never_refuses_a_car_on_its_own(self):
        # TB 599-612, TBC 465-485: the extra pass only adds a try. The old reading refused this exempt car.
        car = replace(self.rr.find_car("BVR1001"), passenger=True)
        c7 = self.gate(self.gates.why_not(car, "Brackwater", "Brackwater Yard B", "T10"), "C7")
        self.assertEqual(c7["status"], "pass")

    def test_c8_repeats_the_pick_up_rules_at_the_stop(self):
        # TrainBuilderCars 522: checkPickupInterchangeOrSpur again, so it fails with B6.
        result = self.gates.why_not("BVR3006", "Ashgrove", train="T10")
        self.assertEqual((self.gate(result, "B6")["status"], self.gate(result, "C8")["status"]), (FAIL, FAIL))
        self.assertEqual(self.gate(self.gates.why_not("BVR1004", "Tolvern", train="BV1"), "C8")["status"], "pass")

    def test_d3_counts_the_cars_the_build_places_first(self):
        # TBC 1735 against the moves other cars can take first: West Staging and Ashgrove hold 4.
        g = self.gates
        self.assertEqual(self.gate(g.why_not("BVR1004", "Tolvern", "Tolvern Yard", "BV1"), "D3")["status"], "pass")
        rr, g = self.fresh()
        next(s for s in rr.routes["1"].stops if s.id == "1r4").max_moves = 1
        d3 = self.gate(g.why_not("BVR1004", "Tolvern", "Tolvern Yard", "BV1"), "D3")
        self.assertEqual(d3["status"], "not_checked")
        self.assertIn("up to 4 other", d3["reason"])

    def test_d18_timing_matters_only_with_another_trains_car_on_a_tight_track(self):
        # TrainBuilderBase 2487-2536: checkReserved.
        rr, g = self.fresh()
        result = g.why_not("BVR1001", "Brackwater", "Brackwater Team Track", "Y20")
        self.assertEqual(self.gate(result, "D18")["status"], "pass")
        rr.find_car("BVR5001").train_id = "6"
        d18 = self.gate(g.why_not("BVR1001", "Brackwater", "Brackwater Team Track", "Y20"), "D18")
        self.assertEqual(d18["status"], "not_checked")
        self.assertIn("T30", d18["reason"])

    def test_c11_quick_service_waits_only_on_a_clone(self):
        # TrainBuilderBase 3097-3145: no clone on the track means nothing to wait for.
        rr, g = self.fresh()
        rr.tracks["3s2"].load_options |= ops_data.QUICK_SERVICE
        self.assertEqual(self.gate(g.why_not("BVR2002", "Brackwater", train="BV2"), "C11")["status"], "pass")
        rr.cars["clone"] = replace(rr.find_car("BVR2002"), id="clone", number="2002-(Clone)-1",
                                   location_id="2", track_id="2s1", destination_id="3", dest_track_id="3s2",
                                   train_id="3")
        c11 = self.gate(g.why_not("BVR2002", "Brackwater", train="BV2"), "C11")
        self.assertEqual(c11["status"], "not_checked")
        self.assertIn("T10", c11["reason"])

    def test_b17_takes_the_caboose_the_train_requires_to_the_end_of_its_leg(self):
        # TrainBuilderCars 42-192: getCaboose at the departure, set out at the leg's end.
        rr, g = self.fresh()
        rr.find_train("T30").requires = ops_data.REQUIRES_CABOOSE
        caboose = rr.find_car("BVR3016")
        caboose.caboose, caboose.type = True, "Caboose"
        self.assertEqual(self.gate(g.why_not(caboose, "Tolvern", "Tolvern Yard", "T30"), "B17")["status"], "pass")
        self.assertEqual(self.gate(g.why_not(caboose, "Tolvern", "Tolvern Yard", "BV1"), "B17")["status"], FAIL)


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

    def test_lists_tools_with_correct_read_only_flags(self):
        out = call(self.env, INIT, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        tools = out[1]["result"]["tools"]
        writers = {"ops_apply", "ops_session", "ops_deliver_car", "ops_restore", "ops_install_agent", "ops_train",
                   "ops_live_car", "ops_live_save", "ops_live_automation", "ops_backup_now"}
        readers = {"ops_why_not", "ops_audit", "ops_list", "ops_actions", "ops_plan", "ops_build_check",
                   "ops_dry_run", "ops_backups", "ops_live_status", "ops_live_report", "ops_explain_build"}
        self.assertEqual({t["name"] for t in tools}, writers | readers)
        for entry in tools:
            self.assertEqual(entry["annotations"]["readOnlyHint"], entry["name"] in readers, entry["name"])

    def test_explain_build_over_the_wire(self):
        out = call(self.env, INIT, tool("ops_explain_build", {"train": "X99"}))
        self.assertTrue(out[1]["result"].get("isError"), "the demo operations folder holds no buildstatus")
        self.assertIn("buildstatus", self.text(out[1]))
        path = str(DEMO / "buildstatus" / "train (X99).txt")
        out = call(self.env, INIT, tool("ops_explain_build", {"path": path, "train": "X99"}))
        self.assertEqual(json.loads(self.text(out[1]))["outcome"]["failure"][0]["gate"], "A8")

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
        allowed = {"__future__", "collections", "concurrent", "copy", "dataclasses", "datetime", "difflib", "inspect",
                   "contextlib", "hashlib", "json", "os", "pathlib", "re", "shutil", "subprocess", "sys", "tempfile", "time",
                   "typing", "urllib", "uuid", "xml", "mcp_stdio", "ops_actions", "ops_actions_automations",
                   "ops_actions_cars", "ops_actions_engines", "ops_actions_extras", "ops_actions_locations", "ops_actions_more", "ops_actions_names",
                   "ops_actions_schedules", "ops_actions_setup", "ops_actions_trains", "ops_build_state", "ops_data", "ops_gates",
                   "ops_jmri", "ops_live", "ops_paperwork", "ops_report", "ops_report_messages", "ops_router", "ops_store"}
        for path in SERVERS.glob("*.py"):
            if path.name in ("jmri_worker.py", "jmri_agent.py"):  # These run in JMRI's jython, not the server.
                continue
            for line in path.read_text().splitlines():
                words = line.split()
                if len(words) > 1 and words[0] in ("import", "from") and not line.startswith(" "):
                    with self.subTest(file=path.name):
                        self.assertIn(words[1].split(".")[0], allowed)


if __name__ == "__main__":
    unittest.main()
