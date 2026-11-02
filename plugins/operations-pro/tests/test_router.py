"""ops_router against real JMRI 5.16's car router.

jmri_router_oracle.json is what Router.setDestination returned in real JMRI for every car
on a track, every track as its final destination, and no train or each train named: in
the demo railroad and in scenarios that change settings in memory first. Only the
answers that differ from the demo are kept for a scenario. tests/jmri_router_oracle.py
regenerates it. The spur search for custom loads is held to the build reports in
tests/fixtures/demo/buildstatus, where the build state still matched the files.
"""
import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "tests" / "fixtures" / "demo"
sys.path.insert(0, str(ROOT / "servers"))

import ops_data  # noqa: E402
import ops_router  # noqa: E402
from ops_gates import Gates  # noqa: E402

ORACLE = json.loads((DEMO / "jmri_router_oracle.json").read_text())
KINDS = (ops_router.OKAY, ops_router.LENGTH, ops_router.CAPACITY, ops_router.TYPE, ops_router.ROAD,
         ops_router.DESTINATION, ops_router.NO_FD, ops_router.LOAD, ops_router.SCHEDULE, "car has a custom",
         ops_router.NOT_ABLE, ops_router.DISABLED)


def kind(status: str) -> str:
    """JMRI's own words after the first are not compared, only how the status starts."""
    if status.startswith(ops_router.NOT_THIS_TRAIN + " ("):
        return status
    return next((k for k in KINDS if status.startswith(k)), status)


def railroad(scenario: dict):
    """The demo with a scenario's changes, made the way jmri_router_oracle.py makes them in JMRI."""
    rr = ops_data.load(DEMO / "operations")
    for name, value in scenario.get("options", {}).items():
        rr.setup.setdefault("buildOptions", {})[name] = "true" if value else "false"
    for name, value in scenario.get("router", {}).items():
        rr.setup.setdefault("router", {})[name] = "true" if value else "false"
    for track_id, change in scenario.get("tracks", {}).items():
        track = rr.tracks[track_id]
        track.length = change.get("length", track.length)
        track.raw_alternate_id = change.get("alternate", track.raw_alternate_id)
        if change.get("quickService"):
            track.load_options |= ops_data.QUICK_SERVICE
        track.pool = change.get("pool", track.pool)
        track.ignore_used = change.get("ignoreUsed", track.ignore_used)
        track.schedule_id = change.get("scheduleId", track.schedule_id)
    for car_id, change in scenario.get("cars", {}).items():
        car, track = rr.cars[car_id], rr.tracks[change["destination"]]
        car.destination_id, car.dest_track_id = track.location_id, track.id
    stops = {s.id: s for r in rr.routes.values() for s in r.stops}
    for stop_id, length in scenario.get("stops", {}).items():
        stops[stop_id].max_length = length
    for train_id, change in scenario.get("trains", {}).items():
        train = rr.trains[train_id]
        train.service_all = change.get("serviceAll", train.service_all)
        train.build = change.get("build", train.build)
        if "terminationTrack" in change:
            train.termination_track_id, train.built = change["terminationTrack"], True
    return rr, Gates(rr)


def ask(gates, scenario: dict, car_id: str, track_id: str, train_id: str):
    """Router.isCarRouteable on a copy, as the oracle asks JMRI: (returned, status, destination, trains)."""
    rr = gates.rr
    train = rr.trains.get(train_id)
    # JMRI keeps the named train's saved termination track while the oracle marks it building; in a
    # real build that is the track the build picked, which is what a Build names.
    building = ops_router.Build(termination_track_id=train.termination_track_id) \
        if scenario.get("building") and train else None
    router = ops_router.Router(gates, building)
    target = rr.tracks[track_id]
    copy = replace(rr.cars[car_id], kernel="", lead=False, train_id="", fd_id=target.location_id,
                   fd_track_id=target.id, destination_id="", dest_track_id="")
    ok = router.set_car_destination(copy, train)
    return ok, kind(router.status), copy.dest_track_id or copy.destination_id, [p["train"] for p in router.shown or []]


def jmri(scenario: str, key: str):
    answer = ORACLE["answers"][scenario].get(key) or ORACLE["answers"]["demo"][key]
    ok, status, dest, trains = answer
    return ok, kind(status), dest, trains


class EveryAnswer(unittest.TestCase):
    def test_every_car_track_and_train_matches_jmri_in_every_scenario(self):
        for scenario in ORACLE["scenarios"]:
            _, gates = railroad(scenario)
            wrong = []
            for key in ORACLE["answers"]["demo"]:
                car, track, train = key.split("|")
                got, want = ask(gates, scenario, car, track, train), jmri(scenario["name"], key)
                if got != want:
                    wrong.append((key, want, got))
            with self.subTest(scenario=scenario["name"]):
                self.assertEqual(wrong[:10], [], f"{len(wrong)} answers differ from JMRI")

    def test_the_oracle_covers_every_car_on_a_track_every_track_and_every_train(self):
        rr = ops_data.load(DEMO / "operations")
        placed = [c for c in rr.cars.values() if c.track_id]
        self.assertEqual(len(ORACLE["answers"]["demo"]), len(placed) * len(rr.tracks) * (len(rr.trains) + 1))


class WhereTheOldSearchWasWrong(unittest.TestCase):
    """Each case is one the breadth-first search answered differently from real JMRI."""

    def check(self, scenario_name: str, key: str, expected: tuple):
        scenario = next(s for s in ORACLE["scenarios"] if s["name"] == scenario_name)
        _, gates = railroad(scenario)
        self.assertEqual(jmri(scenario_name, key), expected, "the recorded JMRI answer")
        self.assertEqual(ask(gates, scenario, *key.split("|")), expected)

    def test_the_target_spur_schedule_is_not_asked_when_routing(self):
        # R:146: the clone is already destined to the spur, so Track.checkSchedule passes (TR:2062).
        self.check("demo", "BVR1001|2s1|", (True, "okay", "", ["BV2"]))

    def test_the_target_track_filter_is_asked_for_the_final_destination(self):
        # Quarry Interchange accepts only cars for Quarry Staging; the old search ignored the target's filter.
        self.check("demo", "BVR1004|1s3|", (False, ops_router.DESTINATION, "", []))

    def test_a_full_final_track_forwards_the_car_to_a_yard_at_the_destination(self):
        # R:390: forward to yard, Location.getTracksByMoves(YARD).
        self.check("demo", "BVR1004|1s1|3", (True, ops_router.LENGTH, "1s2", ["T10"]))
        self.check("scrap shed full", "BVR1001|3s3|6", (True, ops_router.LENGTH, "3s2", ["T30"]))

    def test_without_forward_to_yard_a_full_track_leaves_the_car_without_a_destination(self):
        self.check("scrap shed full, no forward", "BVR1001|3s3|6", (True, ops_router.LENGTH, "", ["T30"]))

    def test_a_schedule_refusal_at_set_out_sends_the_car_to_the_spur_alternate(self):
        # R:358: Coal Dock's schedule refuses the car when the destination is set; its alternate takes it.
        self.check("demo", "BVR3010|3s1|1", (True, ops_router.SCHEDULE, "3s4", []))

    def test_the_train_being_built_too_long_on_its_own_legs_holds_the_car_for_it(self):
        # T:2121 counts only while building; R:282 then answers "Train (T10)" and the car waits.
        self.check("demo", "QXR3018|3s2|3", (True, ops_router.OKAY, "1s4", ["T10", "T30"]))
        self.check("building, short turn", "QXR3018|3s2|3", (True, "Train (T10)", "", ["T10", "T30"]))

    def test_service_all_refuses_routes_that_start_on_another_train(self):
        self.check("service all", "BVR1001|3s1|3", (False, ops_router.NOT_ABLE, "", []))

    def test_only_active_trains_drops_a_train_with_build_off(self):
        self.check("only active", "QXR3018|3s2|", (False, ops_router.NOT_ABLE, "", []))

    def test_routing_through_staging_picks_staging_by_location_order(self):
        # LocationManager enumerates a Hashtable: East Staging comes before West Staging here.
        self.check("staging on", "BVR1001|1s1|", (True, ops_router.OKAY, "5s2", ["BV1", "BV2"]))

    def test_router_calls_bump_track_moves_as_jmri_does(self):
        # Track.addDropRS bumps moves on every new destination, which reorders later track lists.
        rr = ops_data.load(DEMO / "operations")
        router = ops_router.Router(Gates(rr))
        car = replace(rr.find_car("BVR1001"), fd_id="", fd_track_id="")
        self.assertEqual(router.set_destination(car, rr.locations["1"], rr.tracks["1s2"]), ops_router.OKAY)
        self.assertEqual(router._moves(rr.tracks["1s2"]), rr.tracks["1s2"].moves + 1)


class AsLoaded(unittest.TestCase):
    """State JMRI derives while it loads the files, which the files do not spell out."""

    def test_a_kernel_with_no_lead_flag_is_led_by_its_first_member(self):
        # RollingStockGroup.add makes the first member the lead (:40-42); a later leadKernel wins (Car:1179).
        rr = ops_data.load(DEMO / "operations")
        first, second = rr.cars["BVR3013"], rr.cars["BVR3014"]
        first.lead = False
        self.assertTrue(rr.is_kernel_lead(first))
        self.assertFalse(rr.is_kernel_lead(second))
        self.assertEqual(rr.kernel_length(first), (rr.car_length(first) or 0) + (rr.car_length(second) or 0))
        # R:139: only the lead is routed; another member returns before any search.
        for car, searched in ((second, False), (first, True)):
            router = ops_router.Router(Gates(rr))
            router.set_car_destination(replace(car, fd_id="1", fd_track_id="1s1"), None)
            self.assertEqual(bool(router.steps), searched, car.id)
        first.lead = second.lead = True
        self.assertEqual([rr.is_kernel_lead(first), rr.is_kernel_lead(second)], [False, True])

    def test_why_not_orders_tracks_by_moves_as_loaded_and_schedules_only_on_spurs(self):
        # A destined car bumps its track's moves on load (RS:1490, TR:818); Store left them out (TR:2840).
        # Track.getScheduleId is empty off a spur (TR:1906), so a yard's stale scheduleId does not lead.
        rr = ops_data.load(DEMO / "operations")
        tolvern = rr.locations[rr.tracks["3s2"].location_id]
        self.assertTrue(rr.tracks["3s2"].schedule_id and rr.tracks["3s2"].is_yard)
        before = [t.id for t in Gates(rr).track_order(tolvern)]
        self.assertNotEqual(before[0], "3s2")
        lowest = before[0]
        car = rr.cars["BVR4003"]
        car.destination_id, car.dest_track_id = tolvern.id, lowest
        after = [t.id for t in Gates(rr).track_order(tolvern)]
        self.assertNotEqual(after[0], lowest)
        self.assertEqual(Gates(rr).loaded_moves()[lowest], rr.tracks[lowest].moves + 1)


class Orders(unittest.TestCase):
    def test_hashtable_order_matches_java(self):
        # Printed by java.util.Hashtable in JMRI's own jython for the same keys.
        order = ops_router.java_hashtable_order
        self.assertEqual(order([str(i) for i in range(1, 31)]),
                         ["30", "19", "18", "17", "16", "15", "14", "13", "12", "11", "10", "9", "29", "8", "28",
                          "7", "27", "6", "26", "5", "25", "4", "24", "3", "23", "2", "22", "1", "21", "20"])
        self.assertEqual(order([f"{loc}s{t}" for loc in range(1, 4) for t in range(1, 8)]),
                         ["1s7", "1s6", "1s5", "1s4", "1s3", "3s7", "1s2", "3s6", "1s1", "3s5", "3s4", "3s3", "3s2",
                          "3s1", "2s7", "2s6", "2s5", "2s4", "2s3", "2s2", "2s1"])
        self.assertEqual(order(["Yard", "East", "Main", "Spur 12", "x"]), ["x", "Yard", "East", "Spur 12", "Main"])

    def test_location_order_is_the_one_jmri_listed(self):
        rr = ops_data.load(DEMO / "operations")
        names = [loc.name for loc in ops_router.Router(Gates(rr))._location_order]
        self.assertEqual(names, ["Quarry Staging", "East Staging", "West Staging", "Tolvern", "Ashgrove",
                                 "Brackwater", "Ashgrove-North"])

    def test_spurs_come_in_the_order_the_build_report_tried_them(self):
        # train (T10).txt tries Coal Dock, Scrap Shed, Cannery, Old Spur, Team Track, North Elevator, then
        # Feed Mill, whose moves earlier cars in that build had bumped. In the files every count is 0.
        rr = ops_data.load(DEMO / "operations")
        spurs = [t.id for t in ops_router.Router(Gates(rr)).tracks_by_moves(ops_data.SPUR)]
        self.assertEqual(spurs, ["3s1", "3s3", "2s2", "2s1", "1s6", "1s5", "7s1"])


class SpurSearch(unittest.TestCase):
    """findFinalDestinationForCarLoad, held to the first custom load car each report shows."""

    @classmethod
    def setUpClass(cls):
        cls.rr = ops_data.load(DEMO / "operations")
        cls.gates = Gates(cls.rr)

    def search(self, car, train, terminal=""):
        return ops_router.find_spur_for_load(self.gates, self.rr.find_car(car), self.rr.find_train(train),
                                             ops_router.Build(termination_track_id=terminal))

    def test_another_train_able_to_reach_the_spur_holds_the_car(self):
        # train (T10).txt: "Could not set destination for car (BVR 2001) due to Train (BV1)", then "Hold car".
        result = self.search("BVR2001", "T10")
        self.assertTrue(result["hold"])
        self.assertIsNone(result["spur"])
        self.assertEqual(result["spurs"][0], {**result["spurs"][0], "spur": "Tolvern, Tolvern Coal Dock",
                                              "result": "router: Train (BV1)"})
        self.assertEqual(result["staging"], [])

    def test_the_train_that_reaches_the_spur_takes_the_car_there(self):
        # train (T30).txt: "Car (BVR 2001) assigned to train, destination (Tolvern, Tolvern Coal Dock)".
        result = self.search("BVR2001", "T30")
        self.assertEqual(result["spur"], "Tolvern, Tolvern Coal Dock")
        self.assertFalse(result["hold"])

    def test_no_spur_then_staging_skipping_the_other_tracks_at_the_terminus(self):
        # train (BV1).txt: West Stage 1 routes only by BV2, then "assigned to staging track (East Stage 2)".
        result = self.search("BVR1004", "BV1", terminal="5s2")
        reachable = [s["staging"] for s in result["staging"] if s["destination"]]
        self.assertEqual(reachable, ["East Staging, East Stage 2"])
        names = [s["staging"] for s in result["staging"]]
        self.assertNotIn("East Staging, East Stage 1", names)
        west = next(s for s in result["staging"] if s["staging"] == "West Staging, West Stage 1")
        self.assertEqual(west["status"], "Train (BV2)")

    def test_staging_reached_through_the_yard_with_room(self):
        # train (BV1).txt: Yard A has -277 feet free, so BVR 3019 goes by Brackwater Yard B to West Stage 2.
        result = self.search("BVR3019", "BV1", terminal="5s2")
        west = next(s for s in result["staging"] if s["staging"] == "West Staging, West Stage 2")
        self.assertEqual(west["destination"], "Brackwater Yard B")

    def test_default_load_is_not_searched(self):
        self.assertFalse(self.search("BVR1001", "BV1")["searched"])

    def test_why_not_shows_the_router_and_the_spur_search(self):
        result = self.gates.why_not("BVR2001", "Tolvern", "Tolvern Coal Dock", "T10")
        self.assertEqual(result["router"]["route"]["status"], "Train (BV1)")
        self.assertTrue(result["router"]["spur_search"]["hold"])
        default = self.gates.why_not("BVR1001", "Tolvern", "Tolvern Yard", "BV1")
        self.assertFalse(default["router"]["used"])


if __name__ == "__main__":
    unittest.main()
