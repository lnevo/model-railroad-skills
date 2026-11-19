"""Plan reader, panel reader, layer merge and the plan overrides, on the made-up example."""
import copy
import json
from pathlib import Path
import unittest

import helpers
from schematic import edits, layers, panel_reader, plan_reader
from schematic.core import SchematicError


class PlanReader(unittest.TestCase):
    def setUp(self):
        self.g = helpers.graph()

    def kinds(self):
        out = {}
        for d in self.g["nodes"].values():
            out[d["kind"]] = out.get(d["kind"], 0) + 1
        return out

    def test_every_switch_and_end_is_read(self):
        self.assertEqual(self.kinds(), {"switch": 11, "dx": 1, "end": 9})
        self.assertEqual(len(self.g["edges"]), 23)

    def test_parts_give_part_numbers_and_heights(self):
        by = {d["label"]: d for d in self.g["nodes"].values() if d["kind"] != "end"}
        self.assertEqual(by["T10"]["z"], 0.0)
        self.assertEqual(by["T30"]["z"], 15.0)
        self.assertEqual(by["T14"]["kind"], "dx")

    def test_hands_come_from_the_geometry(self):
        by = {d["label"]: d for d in self.g["nodes"].values() if d["kind"] != "end"}
        self.assertEqual(by["T10"]["hand"], 1)      # switch 1: right-hand
        self.assertEqual(by["T16"]["hand"], -1)     # switch 3: left-hand, facing west
        self.assertEqual(by["T32"]["hand"], -1)

    def test_two_track_ends_on_one_spot_are_one_loop(self):
        loop = [e for e in self.g["edges"] if e["u"] == e["v"]]
        self.assertEqual(len(loop), 1)
        self.assertGreater(loop[0]["cm"], 500)

    def test_lengths_follow_the_plan(self):
        lead = next(e for e in self.g["edges"] if {e["u"], e["v"]} == {"S1", "L11"})
        self.assertAlmostEqual(lead["cm"], 107, delta=2)

    def test_main_comes_from_the_section_name(self):
        rise = next(e for e in self.g["edges"] if {e["u"], e["v"]} == {"S4", "U1"})
        self.assertTrue(rise["main"])

    def test_section_filter_keeps_one_group(self):
        f = helpers.folder()
        lower = plan_reader.read(str(f / "plan.xml"), "+Lower")
        self.assertFalse(any(d.get("district", "").startswith("Upper") for d in lower["nodes"].values()
                             if d["kind"] != "end"))

    def test_unsupported_type_is_an_error(self):
        f = helpers.folder()
        bad = f / "bad.xml"
        bad.write_text((f / "plan.xml").read_text().replace("RH_TURNOUT", "CROSSING", 1))
        with self.assertRaises(plan_reader.PlanError):
            plan_reader.read(str(bad))


class PlanScale(unittest.TestCase):
    """Lengths come from the export's scale fitted against the parts, so any export size gives plan lengths."""

    def export(self, kx, ky):
        """The example's export with its x and y coordinates multiplied by kx and ky, as a file path."""
        import re
        import tempfile
        f = helpers.folder()

        def times(m):
            k = kx if m.group(1) in ("x", "xcen", "xb", "xc") else ky
            return f'{m.group(1)}="{float(m.group(2)) * k:.2f}"'
        text = re.sub(r'\b(x|y|xcen|ycen|xb|yb|xc|yc)="([-0-9.]+)"', times, (f / "plan.xml").read_text())
        self._tmp = tempfile.TemporaryDirectory()
        path = Path(self._tmp.name) / "plan.xml"
        path.write_text(text)
        return str(path)

    def parts(self):
        return json.loads((helpers.folder() / "parts.json").read_text())

    def test_an_export_at_twice_the_size_gives_the_same_lengths_and_labels(self):
        big = plan_reader.read(self.export(2, 2), None, self.parts())
        usual = helpers.graph()
        self.assertEqual({d["label"] for d in big["nodes"].values()}, {d["label"] for d in usual["nodes"].values()})
        for a, b in zip(usual["edges"], big["edges"]):
            self.assertAlmostEqual(a["cm"], b["cm"], delta=max(0.5, a["cm"] * 0.005), msg=a["id"])
        self.assertTrue(any("fitted to the parts" in n and "2.000 times" in n for n in big["notes"]), big["notes"])

    def test_without_parts_lengths_are_at_the_usual_size_and_say_so(self):
        g = plan_reader.read(str(helpers.folder() / "plan.xml"))
        self.assertTrue(any(f"{plan_reader.PX_PER_CM:.4f} px per cm" in n and "no parts" in n for n in g["notes"]),
                        g["notes"])
        lead = next(e for e in g["edges"] if {e["u"], e["v"]} == {"S1", "L11"})
        self.assertAlmostEqual(lead["cm"], 107, delta=2)

    def test_an_export_stretched_on_one_axis_is_an_error(self):
        with self.assertRaisesRegex(plan_reader.PlanError, "not a uniform copy of the plan"):
            plan_reader.read(self.export(1, 1.05), None, self.parts())

    def test_too_few_matched_switches_cannot_fit_a_scale(self):
        with self.assertRaisesRegex(plan_reader.PlanError, "at least 3"):
            plan_reader.uniform_scale([((0, 0), (0, 0)), ((10, 0), (10, 0))])


class PanelReader(unittest.TestCase):
    def test_panel_graph(self):
        f = helpers.folder()
        g = panel_reader.read(str(f / "panel.xml"), panel_reader.load_numbers(f / "numbers.csv"),
                              panel_reader.load_lengths(f / "lengths.csv"))
        labels = {d["label"] for d in g["nodes"].values() if d["kind"] != "end"}
        self.assertEqual(labels, {"1", "2", "3", "4", "5", "6", "11", "12", "13"})
        self.assertNotIn("7", labels)          # never built
        anchors = [a for e in g["edges"] for a in e.get("anchors", [])]
        self.assertEqual({a[0] for a in anchors}, {"PPmid", "PPloop"})
        loop = [e for e in g["edges"] if e["u"] == e["v"]]
        self.assertEqual(len(loop), 1)

    def test_missing_panel_is_an_error(self):
        f = helpers.folder()
        with self.assertRaises(plan_reader.PlanError):
            panel_reader.read(str(f / "panel.xml"), panel_name="Nope")


class Layers(unittest.TestCase):
    def test_append_lists_collect_and_others_replace(self):
        a = {"edits": [1], "title": ["a"], "main_route": [["x", "y"]], "d": {"k": 1, "j": 1}}
        b = {"edits": [2], "title": ["b"], "main_route": [["y", "z"]], "d": {"k": 2}, "_note": "dropped"}
        m = layers.merge(a, b)
        self.assertEqual(m["edits"], [1, 2])
        self.assertEqual(m["main_route"], [["x", "y"], ["y", "z"]])
        self.assertEqual(m["title"], ["b"])
        self.assertEqual(m["d"], {"k": 2, "j": 1})
        self.assertNotIn("_note", m)

    def test_signals_planned_appends_and_min_cells_and_shorten(self):
        m = layers.merge({"signals_planned": ["a"], "min_cells": [[1, 2, 3]], "shorten": [["a", "b"]], "keep_close": [[1, 2]]},
                         {"signals_planned": ["b"], "min_cells": [[4, 5, 6]], "shorten": [["c", "d"]], "keep_close": [[3, 4]]})
        self.assertEqual(m["signals_planned"], ["a", "b"])
        self.assertEqual(len(m["min_cells"]), 2)
        self.assertEqual(len(m["shorten"]), 2)
        self.assertEqual(len(m["keep_close"]), 2)

    def test_load_reads_layer_one_always_and_preferences_on_request(self):
        f = helpers.folder()
        with_prefs = layers.load("example", f)
        without = layers.load("example", f, preferences=False)
        self.assertIn("title", with_prefs)
        self.assertNotIn("title", without)
        self.assertIn("edits", without)


class Edits(unittest.TestCase):
    def graph_and_edits(self):
        return copy.deepcopy(helpers.graph()), copy.deepcopy(layers.load("example", helpers.folder(), False)["edits"])

    def test_example_edits_apply(self):
        g, ed = self.graph_and_edits()
        edits.apply_edits(g, ed)
        labels = {d["label"] for d in g["nodes"].values() if d["kind"] != "end"}
        self.assertIn("8", labels)             # added by the overrides
        self.assertNotIn("7", labels)          # not built: removed, the track runs straight through
        passing = [e for e in g["edges"] if e["names"] == ["Passing"] and {g["nodes"][e["u"]]["label"], g["nodes"][e["v"]]["label"]} == {"2", "6"}]
        self.assertTrue(passing)
        self.assertAlmostEqual(passing[0]["cm"], 122, delta=3)

    def test_a_switch_without_a_hand_stops_the_run(self):
        g, ed = self.graph_and_edits()
        for e in ed:
            if e["op"] == "switch":
                del e["hand"]
        with self.assertRaisesRegex(SchematicError, r"switch 8: no hand"):
            edits.apply_edits(g, ed)

    def test_a_switch_without_a_source_stops_the_run(self):
        g, ed = self.graph_and_edits()
        for e in ed:
            if e["op"] == "switch":
                del e["source"]
        with self.assertRaisesRegex(SchematicError, r"switch 8: no source"):
            edits.apply_edits(g, ed)

    def test_unknown_edit_and_unknown_switch_are_errors(self):
        g, ed = self.graph_and_edits()
        with self.assertRaises(SchematicError):
            edits.apply_edits(g, [{"op": "bend"}])
        with self.assertRaises(SchematicError):
            edits.apply_edits(copy.deepcopy(g), [{"op": "remove", "switches": ["T999"]}])


if __name__ == "__main__":
    unittest.main()


class EditLookups(unittest.TestCase):
    def test_moved_switch_found_by_plain_number_and_end_keeps_main(self):
        from schematic import edits
        g = dict(nodes={"a": dict(kind="switch", label="7*"), "b": dict(kind="end", label="")},
                 edges=[dict(id="e1", u="a", up="B", v="b", vp="E", names=[], cm=50.0, main=True, link=False)])
        self.assertEqual(edits.by_label(g, "7"), "a")
        edits.apply_edits(g, [dict(op="end", ends=[["7", "B", "Bumper", "stub", ""]])])
        self.assertTrue(g["edges"][0]["main"])

    def test_section_filter_that_keeps_nothing_is_a_plan_error(self):
        from schematic import plan_reader
        import helpers, tempfile, os
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "plan.xml")
            import example
            open(path, "w").write(example.plan_xml())
            with self.assertRaises(plan_reader.PlanError):
                plan_reader.read(path, skip="+NoSuchSection")
