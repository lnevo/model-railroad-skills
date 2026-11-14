"""Station detail sheets: the cut is a rule on the solved band, so it must agree with the overall sheet."""
import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
from schematic import capacity, detail, draw, label_check, layout
from schematic.core import SchematicError

STATIONS = {"Throat": ["1"], "Yard": ["11", "12", "13"], "Junction": ["2", "6", "3"]}


def staged():
    """The example sheet with stations named, built once (the example's own files name none)."""
    if "detail" not in helpers._cache:
        s = copy.copy(helpers.build())
        s.bands = [(t, b, dict(o, stations=STATIONS, capacity={})) for t, b, o in s.bands]
        helpers._cache["detail"] = s
    return helpers._cache["detail"]


def sheet_of(name):
    s = staged()
    allo = [o for _, _, o in s.bands]
    picks = dict(detail.selections(allo))
    svg, sub = detail.sheet_svg(s.bands, picks[name], name, detail.owners(allo))
    return svg, sub, s


class Selection(unittest.TestCase):
    def test_every_station_of_the_preference_by_default(self):
        picks = detail.selections([{"stations": STATIONS}])
        self.assertEqual([n for n, _ in picks], ["Throat", "Yard", "Junction"])

    def test_chosen_stations_in_any_case(self):
        self.assertEqual(detail.selections([{"stations": STATIONS}], ["yard"]), [("Yard", ["11", "12", "13"])])

    def test_a_group_of_switches_needs_a_name(self):
        self.assertEqual(detail.selections([{}], None, [2, 3], "Pair"), [("Pair", ["2", "3"])])
        with self.assertRaises(SchematicError):
            detail.selections([{}], None, ["2"], None)

    def test_unknown_station_and_no_stations_stop(self):
        with self.assertRaisesRegex(SchematicError, "no station 'Nowhere'"):
            detail.selections([{"stations": STATIONS}], ["Nowhere"])
        with self.assertRaisesRegex(SchematicError, "no detail_sheets or stations"):
            detail.selections([{}])

    def test_a_switch_that_is_not_drawn_or_a_split_group_stops(self):
        s = staged()
        with self.assertRaisesRegex(SchematicError, "switch 99 is not on any band"):
            detail.find_band(s.bands, ["99"])
        with self.assertRaisesRegex(SchematicError, "more than one band"):
            detail.find_band(s.bands, ["1", "21"])


class DetailSheets(unittest.TestCase):
    SHEETS = {"Whole": ["11", "12", "13", "2", "6", "3"], "Yard": ["11", "12", "13"], "Mixed": ["11", "12"]}

    def test_the_preference_wins_over_stations_and_may_overlap_them(self):
        picks = detail.selections([{"stations": STATIONS, "detail_sheets": self.SHEETS}])
        self.assertEqual([n for n, _ in picks], ["Whole", "Yard", "Mixed"])
        self.assertEqual(detail.selections([{"stations": STATIONS, "detail_sheets": self.SHEETS}], ["whole"])[0][0], "Whole")
        with self.assertRaisesRegex(SchematicError, "detail_sheets entry Whole is defined differently"):
            detail.selections([{"detail_sheets": {"Whole": ["1"]}}, {"detail_sheets": {"Whole": ["2"]}}])

    def test_a_sheet_shows_each_station_inside_it_with_its_total(self):
        s = staged()
        allo = [o for _, _, o in s.bands]
        svg, sub = detail.sheet_svg(s.bands, self.SHEETS["Whole"], "Whole", detail.owners(allo))
        self.assertEqual(sorted(sub["precomputed"]["totals"]), ["Junction", "Yard"])      # Throat is not wholly inside
        for st in ("YARD", "JUNCTION"):
            self.assertIn(st, svg)
        self.assertIn("CARS", svg)
        self.assertEqual(sub["precomputed"]["totals"]["Yard"], detail.sheet_svg(s.bands, STATIONS["Yard"], "Yard",
                                                                                detail.owners(allo))[1]["precomputed"]["totals"]["Yard"])

    def test_a_group_with_no_station_inside_gets_its_own_bar(self):
        s = staged()
        svg, sub = detail.sheet_svg(s.bands, ["11", "12"], "Mixed", detail.owners([o for _, _, o in s.bands]))
        self.assertIn("MIXED", svg)


class Cut(unittest.TestCase):
    def test_keeps_the_stations_switches_and_cuts_the_leaving_track(self):
        svg, sub, s = sheet_of("Yard")
        labels = {d["label"] for d in sub["nodes"].values() if d["kind"] == "switch"}
        self.assertEqual(labels, {"11", "12", "13"})
        cuts = [d for n, d in sub["nodes"].items() if n.startswith("CUT:")]
        self.assertEqual([d["label"] for d in cuts], ["TO THROAT"])      # Yard Lead runs to switch 1, Throat's
        self.assertIn("TO THROAT", svg)
        self.assertIn("YARD LEAD", svg)
        for name in ("Y-1", "Y-2", "Y-3", "Y-4"):
            self.assertIn(name.upper(), svg)

    def test_a_switch_no_station_owns_is_named_by_number(self):
        svg, sub, _ = sheet_of("Junction")
        self.assertIn("TO SW 8", svg)                  # the far end of the track out of switch 3
        self.assertIn("TO THROAT", svg)                # Main West runs to switch 1

    def test_same_grid_as_the_overall_sheet(self):
        _, sub, s = sheet_of("Junction")
        band = next(b for t, b, _ in s.bands if t == "Lower level")
        for n in sub["nodes"]:
            if n in band["x"]:
                self.assertEqual(sub["x"][n], band["x"][n])
        for sid in sub["strands"]:
            if sid not in sub["R"]["diag"] and sid in band["R"]["srow"]:
                self.assertEqual(sub["R"]["srow"][sid], band["R"]["srow"][sid])
        self.assertEqual(layout.faults(sub), [])

    def test_a_cut_track_stays_short(self):
        _, sub, s = sheet_of("Yard")
        band = next(b for t, b, _ in s.bands if t == "Lower level")
        cut_id = next(n for n in sub["nodes"] if n.startswith("CUT:"))
        self.assertLess(sub["x"]["L11"] - sub["x"][cut_id], band["x"]["L11"] - band["x"]["S1"])
        self.assertEqual(sub["strands"]["e2"]["cm"], band["strands"]["e2"]["cm"])   # its real length is kept

    def test_capacity_agrees_with_the_overall_sheet(self):
        _, sub, s = sheet_of("Yard")
        title, band, opts = next(b for b in s.bands if b[0] == "Lower level")
        whole = capacity.counts(band, opts)
        want = {band["strands"][k]["name"]: n for k, n in whole.items() if band["strands"][k]["name"].startswith("Y-")}
        self.assertEqual(len(want), 4)
        got = {sub["strands"][k]["name"]: n for k, n in sub["precomputed"]["cars"].items()}
        self.assertEqual({k: v for k, v in got.items() if k.startswith("Y-")}, want)
        self.assertTrue(sub["precomputed"]["totals"]["Yard"])
        self.assertEqual(sub["precomputed"]["totals"], {"Yard": capacity.station_totals(band, opts, band["x"])["Yard"]})

    def test_drawn_larger_with_a_station_bar_and_its_own_title_block(self):
        svg, _, _ = sheet_of("Yard")
        self.assertGreater(float(re.search(r"scale\(([\d.]+)\)", svg).group(1)), 1.0)    # enlarged, never shrunk to nothing
        self.assertIn("YARD", svg)
        self.assertIn("STATION DETAIL SHEET", svg)
        self.assertIn("CARS", svg)
        self.assertNotIn("BOTH LEVELS", svg)
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "y.svg").write_text(svg)
            faults, _ = label_check.report(str(Path(tmp) / "y.svg"))
        self.assertEqual(faults, [])

    def test_masts_on_the_cut_are_drawn_and_far_ones_dropped(self):
        svg, sub, s = sheet_of("Yard")
        self.assertIn("M12C", svg)
        far = dict(s.bands[1][2]["signals"][0], _edge="e2", _toward_node="S1", cm_from_toward=100.0)
        near = dict(far, _toward_node="L11", cm_from_toward=1.0)
        opts = {"signals": [far, near]}
        self.assertEqual(detail.cut_signals(opts, sub), [near])      # near stands on the part that is drawn
        self.assertEqual(detail.cut_signals({"signals": [dict(far, _edge="e99")]}, sub), [])

    def test_totals_on_a_band_turned_end_for_end_are_the_overall_sheets(self):
        s = staged()
        turned = [(t, b, dict(o, rotate_bands=["Lower"])) for t, b, o in s.bands]
        title, band, opts = next(b for b in turned if b[0] == "Lower level")
        owner = detail.owners([o for _, _, o in turned])
        self.assertNotEqual(capacity.station_totals(band, opts, band["x"], True),
                            capacity.station_totals(band, opts, band["x"], False))
        for name, members in detail.selections([opts]):
            svg, sub = detail.sheet_svg(turned, members, name, owner)
            want = capacity.station_totals(band, opts, band["x"], True).get(name)
            self.assertEqual(f"{want} CARS" in svg, bool(want), name)

    def test_the_overall_sheet_is_untouched(self):
        before = helpers.build().svg()
        sheet_of("Yard")
        self.assertEqual(helpers.build().svg(), before)

    def test_a_crossover_group_and_a_loop_cut_cleanly(self):
        s = staged()
        allo = [o for _, _, o in s.bands]
        for members in (["4", "5"], ["2", "6", "3"]):
            svg, sub = detail.sheet_svg(s.bands, members, "Group", detail.owners(allo))
            self.assertEqual(layout.faults(sub), [])
            self.assertTrue(svg.startswith("<svg"))


def renamed(band, old, new):
    """A copy of the band with strand `old` called `new` (and its edge, so it reads as a level-joining or fold piece)."""
    b = copy.deepcopy(band)
    b["strands"][new] = b["strands"].pop(old)
    b["strands"][new]["edge"] = new
    b["need"][new] = b["need"].pop(old)
    b["R"]["srow"][new] = b["R"]["srow"].pop(old)
    for d in b["nodes"].values():
        for side in ("ins", "outs"):
            d[side] = {p: (new if sid == old else sid) for p, sid in d[side].items()}
    return b


class CutDetails(unittest.TestCase):
    def band(self):
        return next(b for t, b, _ in staged().bands if t == "Lower level"), staged().bands[1][2]

    def cut(self, band, members, reach=detail.DETAIL_REACH):
        _, _, opts = staged().bands[1]
        return detail.cut(band, members, opts, "G", detail.owners([opts]), reach)

    def test_a_fold_half_counts_half_its_runs_length(self):
        band, _ = self.band()
        whole = self.cut(band, ["4"])["strands"]["e11"]
        half = self.cut(renamed(band, "e11", "e11.0"), ["4"])["strands"]["e11.0"]
        self.assertAlmostEqual(half["cut_cm"], whole["cut_cm"] / 2)

    def test_masts_on_a_level_joining_piece_follow_the_cut(self):
        band, _ = self.band()
        short = renamed(band, "e2", "e2x")
        short["strands"]["e2x"]["name"] = ""            # no name to leave room for: only the reach counts
        sub = self.cut(short, ["11", "12", "13"], reach=0.5)
        mast = dict(staged().bands[1][2]["signals"][0], _edge="e2", cm_from_toward=1.0)
        facing = dict(mast, _toward_node="L11")
        away = dict(mast, _toward_node="S1")                     # S1 is off the cut
        self.assertEqual(detail.cut_signals({"signals": [facing, away]}, sub), [facing])
        far = dict(facing, cm_from_toward=band["strands"]["e2"]["cm"] - 1)
        self.assertIsNone(draw.mast_piece(far, sub["strands"]))    # beyond the part that is drawn
        self.assertIsNotNone(draw.mast_piece(facing, sub["strands"]))

    def test_a_slope_is_cut_like_a_level_track(self):
        band, _ = self.band()
        sloped = copy.deepcopy(band)
        sloped["R"]["diag"].add("e2")
        sub = self.cut(sloped, ["11", "12", "13"])
        cid = "CUT:e2"
        self.assertTrue(sloped["x"]["S1"] < sub["x"][cid] < sloped["x"]["L11"])
        self.assertTrue(sloped["R"]["nrow"]["S1"] < sub["R"]["nrow"][cid] < sloped["R"]["nrow"]["L11"])
        self.assertLess(sub["strands"]["e2"]["cut_cm"], band["strands"]["e2"]["cm"])
        self.assertIn("e2", sub["R"]["diag"])

    def test_a_switch_in_two_stations_stops(self):
        with self.assertRaisesRegex(SchematicError, "switch 2 is in both A and B"):
            detail.owners([{"stations": {"A": ["1", "2"], "B": ["2"]}}])

    def test_stations_and_switches_together_or_defined_twice_stop(self):
        with self.assertRaisesRegex(SchematicError, "use one"):
            detail.selections([{"stations": STATIONS}], ["Yard"], ["2"], "X")
        with self.assertRaisesRegex(SchematicError, "defined differently"):
            detail.selections([{"stations": {"Yard": ["1"]}}, {"stations": {"Yard": ["2"]}}])
        self.assertEqual(len(detail.selections([{"stations": {"Yard": ["1"]}}, {"stations": {"Yard": [1]}}])), 1)


class Command(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "schematic", "detail", *map(str, args)], cwd=helpers.PLUGIN,
                              capture_output=True, text=True, timeout=120)

    def files(self, tmp):
        f = helpers.folder()
        tmp = Path(tmp)
        for name in ("example.plan_overrides.json", "example.preferences.json"):
            (tmp / name).write_text((f / name).read_text())
        prefs = tmp / "example.preferences.json"
        d = json.loads(prefs.read_text())
        d["stations"] = STATIONS
        d["capacity"] = {}
        prefs.write_text(json.dumps(d))
        (tmp / "graph.json").write_text(json.dumps(helpers.graph()))
        return f"{tmp / 'graph.json'}:example"

    def test_one_station_to_a_file_and_all_to_a_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = self.files(tmp)
            r = self.run_cli(Path(tmp) / "yard.svg", "--data", tmp, inp, "--station", "Yard")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 label faults", r.stdout)
            self.assertIn("YARD", (Path(tmp) / "yard.svg").read_text())
            r = self.run_cli(Path(tmp) / "all", "--data", tmp, inp)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(sorted(p.name for p in (Path(tmp) / "all").iterdir()), ["junction.svg", "throat.svg", "yard.svg"])

    def test_folder_or_file_is_decided_by_the_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = self.files(tmp)
            tmp = Path(tmp)
            r = self.run_cli(tmp / "one/", "--data", tmp, inp, "--station", "Yard")       # trailing slash: a folder
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue((tmp / "one" / "yard.svg").is_file())
            r = self.run_cli(tmp / "two", "--data", tmp, inp, "--station", "Yard")        # no .svg: a folder
            self.assertTrue((tmp / "two" / "yard.svg").is_file())
            r = self.run_cli(tmp / "both.svg", "--data", tmp, inp, "--station", "Yard", "--station", "Throat")
            self.assertEqual(r.returncode, 2)
            self.assertIn("cannot go in one file", r.stderr)
            self.assertFalse((tmp / "both.svg").exists())

    def test_names_that_make_the_same_file_name_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = self.files(tmp)
            tmp = Path(tmp)
            prefs = tmp / "example.preferences.json"
            d = json.loads(prefs.read_text())
            d["stations"] = {"A B": ["11"], "A-B": ["12"]}
            prefs.write_text(json.dumps(d))
            r = self.run_cli(tmp / "out", "--data", tmp, inp)
            self.assertEqual(r.returncode, 2)
            self.assertIn("distinct file names", r.stderr)
            self.assertFalse((tmp / "out").exists())

    def test_a_group_with_a_name_and_a_bad_station_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            inp = self.files(tmp)
            r = self.run_cli(Path(tmp) / "pair.svg", "--data", tmp, inp, "--switches", "11", "12", "--name", "Pair")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("PAIR", (Path(tmp) / "pair.svg").read_text())
            r = self.run_cli(Path(tmp) / "x.svg", "--data", tmp, inp, "--station", "Nowhere")
            self.assertEqual(r.returncode, 2)
            self.assertIn("no station", r.stderr)


if __name__ == "__main__":
    unittest.main()
