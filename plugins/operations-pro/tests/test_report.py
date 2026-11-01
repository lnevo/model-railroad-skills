"""The build report reader, held to reports real JMRI 5.16 wrote for the demo railroad.

tests/fixtures/demo/buildstatus holds one report per train and builds.json with what the
builder itself returned for that run. tests/report_fixtures.py regenerates both.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import ops_report  # noqa: E402
from ops_report import ASSIGNED, HELD, NO_DESTINATION, PICKUP_REFUSED  # noqa: E402

REPORTS = ROOT / "tests" / "fixtures" / "demo" / "buildstatus"
BUILDS = json.loads((REPORTS / "builds.json").read_text())


def text(train):
    return (REPORTS / f"train ({train}).txt").read_text()


def explained(train, **kw):
    return ops_report.explain(text(train), **kw)


class EveryReport(unittest.TestCase):
    """What holds for all six reports."""

    def test_fixtures_are_from_the_version_the_rules_were_checked_on(self):
        self.assertTrue(BUILDS["jmri"].startswith("5.16"))

    def test_every_line_matches_a_template_except_the_railroad_comment_and_lists(self):
        for train in BUILDS["builds"]:
            lines = ops_report.read(text(train))
            unmatched = [line.text for line in lines if line.text and line.key is None]
            for item in unmatched:
                self.assertTrue(item.startswith("Invented railroad") or re.fullmatch(r"[A-Za-z ,&]+", item),
                                f"{train}: {item}")
            self.assertEqual(explained(train)["unparsed"], [], train)
            self.assertNotIn("unhandled", explained(train), train)

    def test_outcome_matches_what_the_builder_returned(self):
        for train, row in BUILDS["builds"].items():
            result = explained(train)
            self.assertEqual((result["outcome"]["built"], result["outcome"]["failed"]), (row["built"], row["failed"]), train)
            if row["built"]:
                self.assertEqual(result["outcome"]["status"], row["status"], train)

    def test_assigned_cars_and_destinations_match_the_builder(self):
        for train, row in BUILDS["builds"].items():
            got = {c["car"].replace(" ", ""): c["destination"] for c in explained(train)["cars"]
                   if c["outcome"] == ASSIGNED}
            want = {}
            for item in row["cars"]:
                car, rest = item.split(" > ")
                location, track = rest.split(" / ")
                want[car] = f"{location}, {track}"
            self.assertEqual(got, want, train)

    def test_header(self):
        result = explained("BV1")
        self.assertEqual(result["train"], "BV1")
        self.assertTrue(result["jmri_version"].startswith("5.16"))
        self.assertEqual(result["active_schedule"], "Monday")
        self.assertEqual(result["mode"], "Normal")
        self.assertTrue(result["levels"]["complete"])
        self.assertFalse(result["levels"]["router_detailed"])

    def test_wrapped_lines_are_joined(self):
        lines = ops_report.read(text("BV1"))
        joined = [line for line in lines if line.key == "buildExcludeCarWrongRoad"]
        self.assertEqual([line.f(0) for line in joined], ["QXR 3009", "QXR 3018"])
        stops = explained("BV1")["route"]["stops"]
        self.assertEqual([s["id"] for s in stops], ["1r1", "1r2", "1r3", "1r4", "1r5"])
        self.assertEqual(stops[0]["max_length"], "1,000 feet")
        self.assertTrue(stops[4]["terminates"])


class FailedBuild(unittest.TestCase):
    def test_cause_and_gate(self):
        result = explained("X99")
        self.assertTrue(result["outcome"]["failed"])
        self.assertEqual([f["key"] for f in result["outcome"]["failure"]], ["buildErrorStagingEmpty"])
        self.assertEqual(result["outcome"]["failure"][0]["gate"], "A8")
        rejected = [r for r in result["staging"]["departure"] if r["kind"] == "rejected"]
        self.assertIn("caboose with the correct road (QXR)", rejected[0]["text"])
        self.assertIn("A8", result["summary"][1])
        self.assertIn("road (QXR)", " ".join(result["summary"]))


class Exclusions(unittest.TestCase):
    def test_each_exclusion_names_its_gate(self):
        rows = {r["car"]: r["gate"] for r in explained("BV1")["excluded_cars"]}
        self.assertEqual(rows, {"BVR 3007": "B8", "QXR 3009": "B9", "BVR 3002": "B2", "BVR 3001": "B3",
                                "BVR 4003": "B13", "BVR 4002": "B10", "BVR 4001": "B10", "QXR 3018": "B9",
                                "BVR 3012": "B15", "BVR 3011": "B16", "BVR 3010": "B14", "BVR 3003": "B1"})

    def test_wait_count_note_attaches_to_the_exclusion(self):
        row = next(r for r in explained("BV1")["excluded_cars"] if r["car"] == "BVR 3011")
        self.assertIn("decrementing wait count to (8)", row["note"])

    def test_fix_text_comes_from_the_gate_table(self):
        row = next(r for r in explained("BV1")["excluded_cars"] if r["car"] == "QXR 3009")
        self.assertIn("Train Road Options", row["fix"])


class CarStories(unittest.TestCase):
    def story(self, train, car):
        return next(c for c in explained(train)["cars"] if c["car"] == car)

    def test_track_type_refusals_and_same_track(self):
        story = self.story("Y20", "BVR 4005")
        self.assertEqual(story["outcome"], NO_DESTINATION)
        self.assertEqual(story["gates"], ["D13", "E3"])
        self.assertTrue(all("(E3)" in r or "same track" in r for r in story["attempts"][0]["refused"]))

    def test_pick_up_direction(self):
        story = self.story("T10", "BVR 4005")
        self.assertEqual(story["outcome"], PICKUP_REFUSED)
        self.assertEqual(story["gates"], ["C9"])
        self.assertEqual(len(story["attempts"]), 2)  # both visits to Brackwater

    def test_location_type_and_same_location(self):
        story = self.story("T10", "BVR 3017")
        self.assertEqual(story["gates"], ["D4", "D7"])

    def test_held_for_another_train(self):
        story = self.story("T10", "BVR 2001")
        self.assertEqual(story["outcome"], HELD)
        self.assertEqual(story["attempts"][0]["search"], "custom load")
        self.assertIn("Train (BV1)", " ".join(story["attempts"][0]["refused"]))

    def test_router_failure_then_default_search(self):
        story = self.story("T10", "BVR 3015")
        self.assertEqual([a["search"] for a in story["attempts"]][:2], ["router", "default"])
        self.assertEqual(story["attempts"][0]["final_destination"], "Quarry Staging")
        self.assertIn("G12", story["attempts"][0]["gates"])
        self.assertIn("E10", story["attempts"][1]["gates"])
        stuck = explained("T10")["not_routable"]
        self.assertEqual(stuck[0]["car"], "BVR 3015")

    def test_custom_load_sent_to_staging(self):
        story = self.story("BV1", "BVR 1004")
        self.assertEqual(story["outcome"], ASSIGNED)
        self.assertEqual(story["destination"], "East Staging, East Stage 2")
        self.assertIn("Try to send car (BVR 1004) custom load (Feed) to staging", story["attempts"][0]["notes"])

    def test_no_staging_accepts_the_load(self):
        story = self.story("BV1", "BVR 4004")
        self.assertEqual(story["outcome"], NO_DESTINATION)
        self.assertIn("G12", story["gates"])
        self.assertTrue(any("Couldn't find staging" in r for r in story["attempts"][0]["refused"]))

    def test_moves_used_up(self):
        story = self.story("BV1", "BVR 2002")
        self.assertEqual(story["gates"], ["D3"])
        ignored = [r["car"] for r in explained("BV1")["ignored_moves_done"]]
        self.assertIn("BVR 1003", ignored)

    def test_generated_load_from_staging(self):
        story = self.story("BV2", "BVR 1103")
        self.assertEqual(story["attempts"][0]["search"], "generate load")
        self.assertEqual(story["destination"], "Ashgrove, Ashgrove Feed Mill")

    def test_stop_notes_carry_gates(self):
        passes = explained("BV2")["route"]["passes"]
        first = next(p for p in passes if p["id"] == "2r1")
        self.assertTrue(any("(C4)" in n for n in first["notes"]))

    def test_room_refusal_is_read_from_the_status(self):
        story = self.story("BV2", "BVR 3016")
        self.assertIn("E9", story["gates"])


class OneCar(unittest.TestCase):
    def test_car_filter_by_id_or_name(self):
        for name in ("BVR 3015", "BVR3015", "bvr 3015"):
            result = explained("T30", car=name)
            self.assertEqual(result["story"]["car"], "BVR 3015", name)
            self.assertEqual(result["not_routable"][0]["car"], "BVR 3015")
        self.assertNotIn("cars", result)

    def test_excluded_car_has_no_story_but_a_reason(self):
        result = explained("BV1", car="QXR 3009")
        self.assertIsNone(result["story"])
        self.assertEqual(result["excluded"][0]["gate"], "B9")

    def test_unknown_car_is_said(self):
        self.assertIn("does not appear", explained("BV1", car="XYZ 1")["note"])


class Detail(unittest.TestCase):
    def test_full_detail_keeps_every_event_with_its_line(self):
        story = next(c for c in explained("Y20", detail="full")["cars"] if c["car"] == "BVR 4005")
        events = story["attempts"][0]["events"]
        self.assertTrue(all("line" in e and "kind" in e for e in events))
        self.assertEqual(events[0]["kind"], "location")

    def test_preview_text_without_level_prefixes_still_reads(self):
        stripped = re.sub(r"^[1357]- ?", "", text("Y20"), flags=re.M)
        result = ops_report.explain(stripped)
        self.assertEqual(result["outcome"]["status"], "Partial 0/5 cars")
        self.assertFalse(result["levels"]["complete"])
        self.assertTrue(any("detail levels" in s for s in result["summary"]))

    def test_file_reader_names_a_missing_report(self):
        with self.assertRaisesRegex(FileNotFoundError, "buildstatus"):
            ops_report.explain_file(REPORTS / "train (none).txt")
        result = ops_report.explain_file(REPORTS / "train (T30).txt")
        self.assertTrue(result["path"].endswith("train (T30).txt"))
        self.assertEqual(ops_report.report_path("/ops", "T30"), Path("/ops/buildstatus/train (T30).txt"))


class Statuses(unittest.TestCase):
    def test_status_text_maps_to_gates(self):
        cases = {"type (Scalecar)": "E3", "road (QXR)": "E4", "load (Acid)": "E8",
                 "rolling stock length 44 feet, track length 400 feet, available track space -277 feet": "E9",
                 "track capacity, rolling stock length 90 feet is greater than track length 60 feet": "E9",
                 "schedule (Coal Dock) doesn't service car type (Boxcar)": "F2",
                 "schedule (Mill Receiving) in match mode, no match": "E10",
                 "schedule (Elevator) requests car type (Hopper)": "F2",
                 "schedule (Elevator) requests car type (Hopper) road (BVR)": "F3",
                 "schedule (Elevator) requests car type (Hopper) load (Grain)": "F4",
                 "schedule (Elevator) requests car type (Hopper) only on (Monday)": "F1",
                 "rolling stock length (abc)": "E5",
                 "car's final destination (Tolvern) is not allowed by track (Quarry Interchange)": "E6",
                 "car doesn't have a final destination": "E7", "could not route car": "G12",
                 "Train (BV1) no moves left for route (Main East) id 1r5 destination (East Staging)": "G6"}
        for status, gate in cases.items():
            self.assertEqual(ops_report.status_gate(status)[0], gate, status)
        self.assertIsNone(ops_report.status_gate("Train (BV1)")[0])


SEARCH = "5- Find destinations for (BVR 1001) type (Boxcar) load (E) at yard (Brackwater, Brackwater Yard A)\n"


def parsed(*lines):
    """Walk a synthetic snippet of report lines, written as JMRI 5.16 prints them."""
    return ops_report.parse("".join(line + "\n" for line in lines))


def only_story(report):
    (car, attempts), = report["cars"].items()
    return car, attempts


class Findings(unittest.TestCase):
    """Emit sites checked against the JMRI 5.16 source; the comment on each names the line."""

    def test_skipped_destination_inside_a_search_does_not_close_the_car(self):  # TBC:1731, gate D2
        report = parsed(SEARCH, "5- Searching location (Ashgrove) route id 1r2 for possible destination",
                        "5- Route location (Ashgrove) id 1r2 is skipped by train (BV1)",
                        "5- Searching location (Tolvern) route id 1r3 for possible destination",
                        "7- Can't send car (BVR 1001) to same track (Brackwater Yard A)",
                        "5- Did not assign a destination for car (BVR 1001)")
        car, attempts = only_story(report)
        self.assertEqual((car, len(attempts)), ("BVR 1001", 1))
        self.assertEqual(attempts[0]["outcome"], NO_DESTINATION)
        gates = [e.get("gate") for e in attempts[0]["events"] if e["kind"] == "refused"]
        self.assertEqual(gates, ["D2", "D13"])
        self.assertEqual(report["route"].get("notes", []), [])

    def test_skipped_pickup_stop_is_a_stop_note(self):  # TBB:3065, gate C1
        report = parsed("1- Route location (Ashgrove) id 1r2 is skipped by train (BV1)")
        self.assertEqual(report["cars"], {})
        self.assertIn("(C1)", report["route"]["notes"][0])

    def test_return_to_staging_and_leave_in_staging_keep_the_story_open(self):  # TBC:1761, 1912
        for note in ("7- Returning car (BVR 1001) to staging (West Staging), no other tracks available",
                     "7- Leave car (BVR 1001) in staging (West Staging, West Stage 1)"):
            report = parsed(SEARCH, "5- Searching location (West Staging) route id 1r5 for possible destination",
                            note, "7- Staging (West Staging, West Stage 1) can accept car's load (E)",
                            "3- Car (BVR 1001) assigned to train, destination (West Staging, West Stage 1)")
            car, attempts = only_story(report)
            self.assertEqual(len(attempts), 1, note)
            self.assertEqual(attempts[0]["outcome"], ASSIGNED)
            kinds = [e["kind"] for e in attempts[0]["events"]]
            self.assertEqual(kinds, ["location", "note", "accepted", "outcome"], note)

    def test_staging_refusals_follow_the_open_side(self):  # TBB:1718 and TB:235 depart; TBB:2040 and 2093 terminate
        report = parsed("1- Train terminates into staging at (East Staging), there are 2 tracks",
                        "5- Staging track (East Stage 1) does not service this train",
                        "7- Staging track (East Stage 2) cannot service train (BV1)",
                        "1- Train will depart staging (West Staging), there are 1 tracks",
                        "3- Staging track (West Stage 1) does not service this train",
                        "7- Staging track (West Stage 1) cannot service train (BV1)")
        terminal = [(r["kind"], r["gate"]) for r in report["staging"]["terminal"] if r["kind"] != "note"]
        departure = [(r["kind"], r["gate"]) for r in report["staging"]["departure"] if r["kind"] != "note"]
        self.assertEqual(terminal, [("rejected", "A7"), ("summary", "A7")])
        self.assertEqual(departure, [("rejected", "A8"), ("summary", "A8")])
        x99 = explained("X99")["staging"]
        # TB:235 prints "cannot service train" after the caboose refusal; it is not a second check
        self.assertEqual([(r["kind"], r["gate"]) for r in x99["departure"] if r["kind"] != "note"],
                         [("rejected", "A8"), ("summary", "A8")])
        self.assertIn("not a separate check", x99["departure"][-1]["text"])
        self.assertEqual(x99["terminal"], [])

    def test_caboose_set_aside_is_b17_not_a_type_refusal(self):  # TBB:777, TBC:117, 279
        report = parsed("7- Exclude car (BVR 9001) type (Caboose)  at location (Brackwater, Brackwater Yard A)")
        self.assertEqual([(r["car"], r["gate"]) for r in report["excluded_cars"]], [("BVR 9001", "B17")])

    def test_train_local_move_option_is_g9(self):  # TBB:2727, isAllowLocalMovesEnabled
        report = parsed(SEARCH, "7- Local move from (Brackwater, Yard A) to track (Brackwater, Mill) disabled for train (BV1)")
        event = only_story(report)[1][0]["events"][0]
        self.assertEqual(event["gate"], "G9")
        self.assertIn("Edit Train > Build Options", event["short"])

    def test_spur_type_before_schedule_is_e3(self):  # TBB:2193, track.isTypeNameAccepted
        report = parsed(SEARCH, "7- Spur (Ashgrove, Feed Mill) schedule (Mill) doesn't service type (Tank)")
        self.assertEqual(only_story(report)[1][0]["events"][0]["gate"], "E3")

    def test_non_numeric_length_status_is_e5(self):  # TR:1591-1593 with Track.LENGTH, TR:191-193
        line = ops_report.read("7- Can't send (BVR 1001) to spur (Ashgrove, Mill) due to rolling stock length (abc)")[0]
        self.assertEqual(line.key, "buildCanNotDropCarBecause")
        report = parsed(SEARCH, line.text)
        self.assertEqual(only_story(report)[1][0]["events"][0]["gate"], "E5")

    def test_train_refusing_a_generated_load_is_b13(self):  # TBB:2275, 2807
        report = parsed(SEARCH, "7- Train (BV1) doesn't service load (Grain) destination (Ashgrove, Mill)")
        self.assertEqual(only_story(report)[1][0]["events"][0]["gate"], "B13")

    def test_second_pass_without_local_moves_is_a_stop_note_c7(self):  # TBC:467
        report = parsed("1- Route location (Ashgrove) id 1r2 requests 4 moves, 2/4 moves are available",
                        "5- Route (Main) id 1r2 no local moves at location (Ashgrove)")
        self.assertNotIn("unhandled", report)
        self.assertIn("(C7)", report["route"]["passes"][0]["notes"][0])

    def test_terminal_type_and_mid_search_staging_lines_are_filed_apart(self):  # TBB:2107 vs 2752, 2758; TBE:838
        report = parsed("1- Train terminates into staging at (East Staging), there are 2 tracks",
                        "5- Destination (East Staging) does not accept type (Tank)",
                        "3- Error, no tracks at destination (Ashgrove)!",
                        "7- Generate load for (BVR 1001) type (Boxcar) load (E) at (West Staging, West Stage 1) "
                        "to staging (East Staging, East Stage 1)",
                        "7- Staging track (East Staging, East Stage 1) does not accept type (Boxcar)",
                        "7- Staging track (East Staging, East Stage 1) does not accept road (BVR)")
        self.assertEqual([(r["kind"], r["gate"]) for r in report["staging"]["terminal"] if r["kind"] == "rejected"],
                         [("rejected", "A7")])
        self.assertIn("no tracks at destination", report["engines"]["notes"][0])
        events = only_story(report)[1][0]["events"]
        self.assertEqual([e["gate"] for e in events], ["E3", "E4"])
        self.assertNotIn("unhandled", report)

    def test_thrown_no_track_warning_is_the_failure(self):  # TBB:1477 thrown; TB:727-730 prints it before buildFailedMsg
        report = parsed("1- WARNING! Exclude (BVR 3003) at location (Brackwater) no track assignment",
                        "1- Build failed for train (BV1)")
        self.assertTrue(report["outcome"]["failed"])
        self.assertEqual([(f["key"], f["gate"]) for f in report["outcome"]["failure"]], [("buildWarningRsNoTrack", "B1")])
        self.assertEqual(report["excluded_cars"], [])
        kept = [r["car"] for r in explained("BV1")["excluded_cars"] if r["gate"] == "B1"]  # TBB:827, not thrown
        self.assertEqual(kept, ["BVR 3003"])

    def test_open_ended_template_does_not_absorb_the_next_line(self):
        lines = ops_report.read("7- Car (BVR 1001) is lead in kernel (K1) with 2 cars, 80 feet \n"
                                "7- Car (BVR 1002) is in kernel (K1) with 2 cars, 80 feet\n")
        self.assertEqual([line.key for line in lines], ["buildCarLeadKernel", "buildCarPartOfKernel"])


if __name__ == "__main__":
    unittest.main()
