"""Plan reader: track ends that nearly meet are joined (with a warning), every piece with a switch is kept and drawn,
and a piece with no switch is listed rather than dropped."""
import json
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts the plugin on the path)
from plan_cuts_helpers import bumper, panel, seg
from schematic import plan_reader
from test_cli import run

CM = plan_reader.PX_PER_CM


def switch(ident, x, y, flip=False):
    """A right-hand turnout; `flip` runs it westward (its points face east)."""
    d = -1 if flip else 1
    return (f'<layoutturnout ident="{ident}" type="RH_TURNOUT" blockname="B_1_Mainline" xcen="{x}" ycen="{y}" '
            f'xb="{x + 20 * d}" yb="{y}" xc="{x + 20 * d}" yc="{y + 10 * d}"/>')


def single(ident, x, y, bx, by, cx, cy, ax):
    """A switch at x, y with its three legs ending at bumpers: A west (ax), B at bx, C at cx."""
    return [switch(ident, x, y), bumper(f"{ident}a", ax, y), bumper(f"{ident}b", bx, by), bumper(f"{ident}c", cx, cy),
            seg(f"{ident}sa", ident, "TURNOUT_A", f"{ident}a", "POS_POINT"),
            seg(f"{ident}sb", ident, "TURNOUT_B", f"{ident}b", "POS_POINT"),
            seg(f"{ident}sc", ident, "TURNOUT_C", f"{ident}c", "POS_POINT")]


def read(text):
    with tempfile.TemporaryDirectory() as tmp:
        f = Path(tmp) / "plan.xml"
        f.write_text(text)
        return plan_reader.read(str(f))


class Gaps(unittest.TestCase):
    def two(self, gap_px, dy=0):
        """Two switches whose B legs run toward each other and stop `gap_px` apart (the second `dy` lower)."""
        return panel(*single("T1", 100, 100, 200, 100, 150, 160, 60),
                     switch("T2", 400, 100 + dy, flip=True),
                     bumper("T2a", 460, 100 + dy), bumper("T2b", 200 + gap_px, 100 + dy), bumper("T2c", 350, 160 + dy),
                     seg("T2sa", "T2", "TURNOUT_A", "T2a", "POS_POINT"),
                     seg("T2sb", "T2", "TURNOUT_B", "T2b", "POS_POINT"),
                     seg("T2sc", "T2", "TURNOUT_C", "T2c", "POS_POINT"))

    def test_ends_facing_each_other_within_five_cm_are_joined_and_listed(self):
        g = read(self.two(3 * CM))
        self.assertEqual(sum(d["kind"] == "switch" for d in g["nodes"].values()), 2)
        link = [e for e in g["edges"] if g["nodes"][e["u"]]["kind"] == "switch" and g["nodes"][e["v"]]["kind"] == "switch"]
        self.assertEqual(len(link), 1)
        self.assertEqual([j["gap_cm"] for j in g["joins"]], [3.0])
        self.assertTrue(any("3.0 cm" in n for n in g["notes"]), g["notes"])
        self.assertIn("joined 0 pairs of track ends that met", g["notes"])

    def test_ends_under_one_and_a_half_cm_join_as_before_with_no_warning(self):
        g = read(self.two(1 * CM))
        self.assertNotIn("joins", g)
        self.assertIn("joined 1 pairs of track ends that met", g["notes"])

    def test_ends_past_five_cm_are_not_joined(self):
        g = read(self.two(6 * CM))
        self.assertNotIn("joins", g)
        self.assertEqual(len(g["pieces"]) if "pieces" in g else 2, 2)

    def test_ends_of_tracks_side_by_side_are_not_joined(self):
        # both B legs run east and stop 2.5 cm apart, one above the other
        text = panel(*single("T1", 100, 100, 200, 100, 150, 160, 60),
                     switch("T2", 100, 112), bumper("T2a", 60, 112), bumper("T2b", 200, 112), bumper("T2c", 120, 200),
                     seg("T2sa", "T2", "TURNOUT_A", "T2a", "POS_POINT"),
                     seg("T2sb", "T2", "TURNOUT_B", "T2b", "POS_POINT"),
                     seg("T2sc", "T2", "TURNOUT_C", "T2c", "POS_POINT"))
        g = read(text)
        self.assertNotIn("joins", g)

    def test_ends_that_miss_each_other_sideways_are_not_joined(self):
        g = read(self.two(3 * CM, dy=14))        # 3 cm along, 3 cm across: past the angle
        self.assertNotIn("joins", g)

    def test_the_cli_warns_on_stderr(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(self.two(3 * CM))
            r = run("plan", f, Path(tmp) / "g.json")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("warning: joined track ends 3.0 cm apart", r.stderr)


class Pieces(unittest.TestCase):
    def apart(self):
        return panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *single("T2", 600, 400, 700, 400, 650, 460, 560))

    def test_every_piece_with_a_switch_is_kept(self):
        g = read(self.apart())
        self.assertEqual(sum(d["kind"] == "switch" for d in g["nodes"].values()), 2)
        self.assertEqual(len(g["edges"]), 6)
        self.assertEqual(sorted(d["label"] for d in g["nodes"].values() if d["kind"] == "switch"), ["1", "2"])

    def test_a_one_piece_graph_is_unchanged(self):
        g = read(panel(*single("T1", 100, 100, 200, 100, 150, 160, 60)))
        self.assertNotIn("joins", g)
        self.assertNotIn("left_out", g)

    def test_a_piece_with_no_switch_is_listed_not_dropped(self):
        loop = [bumper("LB1", 300, 300), bumper("LB2", 300 + 100 * CM, 300), seg("ls", "LB1", "POS_POINT", "LB2", "POS_POINT")]
        g = read(panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *loop))
        self.assertEqual(len(g["left_out"]), 1)
        self.assertAlmostEqual(g["left_out"][0]["cm"], 100, delta=1)
        self.assertTrue(any(n.startswith("left out: a piece with no switches, ") for n in g["notes"]), g["notes"])

    def test_the_cli_lists_the_left_out_piece_on_stderr(self):
        loop = [bumper("LB1", 300, 300), bumper("LB2", 800, 300), seg("ls", "LB1", "POS_POINT", "LB2", "POS_POINT")]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *loop))
            r = run("plan", f, Path(tmp) / "g.json")
            self.assertRegex(r.stderr, r"warning: left out: a piece with no switches, \d+(\.\d)? cm of track")

    def test_each_piece_is_drawn_as_its_own_band_largest_first(self):
        text = panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *single("T2", 600, 400, 700, 400, 650, 460, 560),
                     *single("T3", 600, 700, 700, 700, 650, 760, 560),
                     switch("T4", 900, 700), bumper("T4a", 860, 700), bumper("T4b", 960, 700), bumper("T4c", 940, 760),
                     seg("T4sa", "T4", "TURNOUT_A", "T4a", "POS_POINT"), seg("T4sb", "T4", "TURNOUT_B", "T4b", "POS_POINT"),
                     seg("T4sc", "T4", "TURNOUT_C", "T4c", "POS_POINT"))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "plan.xml"
            f.write_text(text)
            self.assertEqual(run("plan", f, tmp / "g.json").returncode, 0)
            r = run("draw", tmp / "out.svg", "--data", tmp, "--no-preferences", f"{tmp / 'g.json'}:sample")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(len(re.findall(r"drawing faults", r.stdout)), 4, r.stdout)
            svg = (tmp / "out.svg").read_text()
            for label in "1234":
                self.assertRegex(svg, rf">{label}<")






class Order(unittest.TestCase):
    def test_pieces_come_largest_first_and_one_piece_is_returned_whole(self):
        from schematic import edits
        node = lambda k: dict(kind=k, label="", xy=[0, 0])
        edge = lambda i, u, v: dict(id=f"e{i}", u=u, up="A", v=v, vp="B", names=[], cm=1, main=False, district="", hidden=False)
        g = dict(nodes={"a": node("switch"), "ea": node("end"), "b": node("switch"), "c": node("switch"), "eb": node("end")},
                 edges=[edge(1, "a", "ea"), edge(2, "b", "c"), edge(3, "c", "eb")])
        first, second = edits.split_pieces(g)
        self.assertEqual(sorted(first["nodes"]), ["b", "c", "eb"])
        self.assertEqual(sorted(second["nodes"]), ["a", "ea"])
        self.assertIs(edits.split_pieces(first)[0], first)


class Undrawable(unittest.TestCase):
    def test_a_small_piece_that_cannot_be_laid_out_is_logged_and_the_rest_still_draws(self):
        from unittest import mock

        from schematic import layout, sheet
        from schematic.core import SchematicError
        real = layout.layout

        def fussy(sub, opts, w):
            if sub.get("piece"):
                raise SchematicError("no orientation found: made up")
            return real(sub, opts, w)

        text = panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *single("T2", 600, 400, 700, 400, 650, 460, 560))
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            f = tmp / "plan.xml"
            f.write_text(text)
            (tmp / "g.json").write_text(json.dumps(plan_reader.read(str(f))))
            with mock.patch.object(layout, "layout", fussy):
                s = sheet.build([(str(tmp / "g.json"), "sample")], str(tmp), preferences=False)
        self.assertEqual(len(s.bands), 1)
        self.assertTrue(any("piece 2: not drawn, no orientation found" in line for line in s.log), s.log)


if __name__ == "__main__":
    unittest.main()
