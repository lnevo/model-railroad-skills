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
from schematic import capacity, detail, label_check, layout
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
    svg, sub = detail.sheet_svg(s.bands, picks[name], name, allo)
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
        with self.assertRaisesRegex(SchematicError, "no stations in the preferences"):
            detail.selections([{}])

    def test_a_switch_that_is_not_drawn_or_a_split_group_stops(self):
        s = staged()
        with self.assertRaisesRegex(SchematicError, "switch 99 is not on any band"):
            detail.find_band(s.bands, ["99"])
        with self.assertRaisesRegex(SchematicError, "more than one band"):
            detail.find_band(s.bands, ["1", "21"])


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
        got = {sub["strands"][k]["name"]: n for k, n in capacity.counts(sub, opts).items()}
        self.assertEqual({k: v for k, v in got.items() if k.startswith("Y-")}, want)
        self.assertTrue(sub["station_totals"]["Yard"])
        self.assertEqual(sub["station_totals"], {"Yard": capacity.station_totals(band, opts, band["x"])["Yard"]})

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

    def test_the_overall_sheet_is_untouched(self):
        before = helpers.build().svg()
        sheet_of("Yard")
        self.assertEqual(helpers.build().svg(), before)

    def test_a_crossover_group_and_a_loop_cut_cleanly(self):
        s = staged()
        allo = [o for _, _, o in s.bands]
        for members in (["4", "5"], ["2", "6", "3"]):
            svg, sub = detail.sheet_svg(s.bands, members, "Group", allo)
            self.assertEqual(layout.faults(sub), [])
            self.assertTrue(svg.startswith("<svg"))


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
