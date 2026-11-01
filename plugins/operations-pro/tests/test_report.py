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
                 "schedule (Elevator) requests car type (Hopper) load (Grain)": "F2",
                 "car's final destination (Tolvern) is not allowed by track (Quarry Interchange)": "E6",
                 "car doesn't have a final destination": "E7", "could not route car": "G12",
                 "Train (BV1) no moves left for route (Main East) id 1r5 destination (East Staging)": "G6"}
        for status, gate in cases.items():
            self.assertEqual(ops_report.status_gate(status)[0], gate, status)
        self.assertIsNone(ops_report.status_gate("Train (BV1)")[0])


if __name__ == "__main__":
    unittest.main()
