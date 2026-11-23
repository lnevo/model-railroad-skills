"""Plan reader: track ends that nearly meet are joined (with a warning), every piece with a switch is kept and drawn,
and a piece with no switch is listed rather than dropped."""
import json
import math
import re
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts the plugin on the path)
from plan_cuts_helpers import bumper, panel, seg
from schematic import edits, plan_reader
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
        self.assertEqual(len(edits.split_pieces(dict(nodes=g["nodes"], edges=g["edges"]))), 2)

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

    def test_bare_track_with_unnamed_ends_is_not_merged_into_one_piece(self):
        bare = [bumper("LB1", 300, 300), bumper("LB2", 400, 300),
                '<tracksegment ident="ls1" type1="POS_POINT" connect2name="LB1" type2="POS_POINT" blockname="B_1_Mainline" dashed="no"/>',
                '<tracksegment ident="ls2" type1="POS_POINT" connect2name="LB2" type2="POS_POINT" blockname="B_1_Mainline" dashed="no"/>']
        g = read(panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *bare))
        self.assertEqual(len(g["left_out"]), 2)

    def test_a_section_filter_does_not_list_the_track_it_removed_as_left_out(self):
        loop = [bumper("LB1", 300, 300), bumper("LB2", 800, 300), seg("ls", "LB1", "POS_POINT", "LB2", "POS_POINT")]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *loop))
            g = plan_reader.read(str(f), "+Mainline")
        self.assertNotIn("left_out", g)

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






def joined(specs, links):
    """Switches (ident, x, y, section) each with a bumper at every leg; `links` are (ident, leg, ident, leg) tracks that
    replace the two bumpers at their ends."""
    gone = {(a, la) for a, la, _, _ in links} | {(b, lb) for _, _, b, lb in links}
    parts = []
    for ident, x, y, name in specs:
        for part in single(ident, x, y, x + 100, y, x + 50, y + 60, x - 40):
            if not any(f'ident="{a}{leg.lower()}"' in part or f'ident="{a}s{leg.lower()}"' in part for a, leg in gone):
                parts.append(part.replace("B_1_Mainline", name))
    parts += [seg(f"link{i}", a, f"TURNOUT_{la}", b, f"TURNOUT_{lb}") for i, (a, la, b, lb) in enumerate(links)]
    return panel(*parts)


class Filters(unittest.TestCase):
    def text(self):
        """Mainline holds a piece of three switches and a piece of one; another section holds a fourth piece."""
        return joined([("T1", 100, 100, "B_1_Mainline"), ("T2", 300, 130, "B_1_Mainline"), ("T5", 500, 160, "B_1_Mainline"),
                       ("T3", 700, 500, "B_1_Mainline"), ("T4", 100, 700, "B_1_Yard")],
                      [("T1", "B", "T2", "A"), ("T2", "B", "T5", "A")])

    def test_a_plain_read_keeps_every_piece(self):
        g = read(self.text())
        self.assertEqual(sum(d["kind"] == "switch" for d in g["nodes"].values()), 5)
        self.assertNotIn("dropped", g)

    def test_a_section_filter_keeps_the_largest_piece_and_lists_the_rest(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(self.text())
            g = plan_reader.read(str(f), "+Mainline")
            self.assertEqual(sum(d["kind"] == "switch" for d in g["nodes"].values()), 3)
            self.assertEqual(g["dropped"], [dict(switches=1)])
            self.assertIn("left out: piece of 1 switches, cut off by the section filter", g["notes"])
            self.assertNotIn("left_out", g)       # the filter's own cut is not a piece with no switches
            r = run("plan", f, Path(tmp) / "g.json", "--section", "+Mainline")
            self.assertIn("warning: left out: piece of 1 switches, cut off by the section filter", r.stderr)

    def test_a_height_filter_keeps_the_largest_piece_and_lists_the_rest(self):
        k = CM
        g0 = read(self.text())
        sw = [d for d in g0["nodes"].values() if d["kind"] == "switch"]
        # one plan part per switch of the large piece, three end points each, all at height 0
        parts = []
        for d in (d for d in sw if d["xy"][1] < 300):
            x, y = d["xy"][0] / k, d["xy"][1] / k
            parts.append(dict(eps=[dict(x=x - 2, y=y, z=0), dict(x=x + 2, y=y, z=0), dict(x=x + 2, y=y + 2, z=0)]))
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(self.text())
            g = plan_reader.read(str(f), None, parts, (-1, 1))
        self.assertEqual(g["dropped"], [dict(switches=1), dict(switches=1)])
        self.assertTrue(any(n.startswith("left out: piece of ") and n.endswith("outside the heights") for n in g["notes"]),
                        g["notes"])


class Arcs(unittest.TestCase):
    def test_an_arc_end_faces_along_its_tangent_not_its_chord(self):
        t = math.radians(40)
        eb2 = (220, 100)
        eb4 = (eb2[0] + 14 * math.cos(t), eb2[1] + 14 * math.sin(t))        # 3 cm out along the arc's end tangent
        b2 = (eb4[0] + 60 * math.cos(t), eb4[1] + 60 * math.sin(t))
        c2 = (b2[0], b2[1] + 10)
        cen = (b2[0] + 20 * math.cos(t), b2[1] + 20 * math.sin(t))
        t2 = (f'<layoutturnout ident="T2" type="RH_TURNOUT" blockname="B_1_Mainline" xcen="{cen[0]}" ycen="{cen[1]}" '
              f'xb="{b2[0]}" yb="{b2[1]}" xc="{c2[0]}" yc="{c2[1]}"/>')
        arc = seg("arc", "T1", "TURNOUT_B", "EB2", "POS_POINT").replace(
            'dashed="no"', 'dashed="no" arc="yes" circle="yes" angle="80" flip="no"')
        text = panel(switch("T1", 100, 100), bumper("T1a", 60, 100), bumper("T1c", 150, 160), bumper("EB2", *eb2),
                     seg("t1a", "T1", "TURNOUT_A", "T1a", "POS_POINT"), seg("t1c", "T1", "TURNOUT_C", "T1c", "POS_POINT"),
                     arc, t2, bumper("EB4", *eb4), bumper("T2a", cen[0] + 40, cen[1]), bumper("T2c", c2[0] + 30, c2[1] + 50),
                     seg("t2b", "T2", "TURNOUT_B", "EB4", "POS_POINT"), seg("t2a", "T2", "TURNOUT_A", "T2a", "POS_POINT"),
                     seg("t2c", "T2", "TURNOUT_C", "T2c", "POS_POINT"))
        g = read(text)
        self.assertEqual([j["gap_cm"] for j in g.get("joins", [])], [3.0])


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

    def test_checks_do_not_misfire_on_names_in_a_skipped_piece_and_draw_warns_on_stderr(self):
        from unittest import mock

        from schematic import cli, layout, sheet
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
            g = plan_reader.read(str(f))
            (tmp / "g.json").write_text(json.dumps(g))
            labels = {n: d["label"] for n, d in g["nodes"].items() if d["kind"] == "switch"}
            mine, other = labels["T1"], labels["T2"]
            (tmp / "sample.plan_overrides.json").write_text(json.dumps(dict(
                control_points={"CP": {"switches": [mine, other]}}, shorten=[[mine, other]], min_cells=[[other, mine, 3]])))
            with mock.patch.object(layout, "layout", fussy):
                s = sheet.build([(str(tmp / "g.json"), "sample")], str(tmp), preferences=False)
                self.assertTrue(any("control point CP: not checked" in line for line in s.log), s.log)
                import contextlib
                import io
                err = io.StringIO()
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    cli.run(["draw", str(tmp / "o.svg"), "--data", str(tmp), "--no-preferences", f"{tmp / 'g.json'}:sample"])
            self.assertIn("warning: ", err.getvalue())
            self.assertIn("piece 2: not drawn, no orientation found", err.getvalue())

    def test_two_pieces_on_one_level_get_distinct_titles(self):
        from schematic import sheet
        g = dict(nodes={}, edges=[])
        text = panel(*single("T1", 100, 100, 200, 100, 150, 160, 60), *single("T2", 600, 400, 700, 400, 650, 460, 560))
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(text)
            g = plan_reader.read(str(f))
        z = {n: 0 for n in g["nodes"]}
        for n, d in g["nodes"].items():
            d["z"] = 0
        opts = dict(levels=dict(bands=[dict(name="Main level, x", below=100)]))
        titles = [t for t, _ in sheet.level_bands(g, opts, "sample")]
        self.assertEqual(len(titles), 2)
        self.assertEqual(len(set(titles)), 2)
        self.assertTrue(titles[1].endswith(", piece 2"))


if __name__ == "__main__":
    unittest.main()
