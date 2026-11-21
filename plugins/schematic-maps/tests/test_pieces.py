"""schematic pieces: every piece of a made-up AnyRail-shaped JMRI export told by its geometry.

The exports here are written by hand, track only, in the shape AnyRail writes: each turnout part is a short JMRI
turnout with one track segment per leg out to the part's end point, and the track beyond joins at those points.
"""
import json
import math
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers
from schematic import pieces
from schematic.plan_reader import PX_PER_CM, PlanError


def _rot(p, deg, about=(0.0, 0.0)):
    a = math.radians(deg)
    x, y = p[0] - about[0], p[1] - about[1]
    return (about[0] + x * math.cos(a) - y * math.sin(a), about[1] + x * math.sin(a) + y * math.cos(a))


def _ahead(p, deg, cm):
    return (p[0] + cm * math.cos(math.radians(deg)), p[1] + cm * math.sin(math.radians(deg)))


class Plan:
    """A made-up export, built in plan centimetres (y down the screen) and written in px at PX_PER_CM."""

    def __init__(self, turn=0.0, shift=(0.0, 0.0)):
        self.turn, self.shift = turn, shift
        self.items, self.n = [], 0

    def px(self, p):
        q = _rot(p, self.turn)
        return ((q[0] + self.shift[0]) * PX_PER_CM, (q[1] + self.shift[1]) * PX_PER_CM)

    def name(self, prefix):
        self.n += 1
        return f"{prefix}{self.n}"

    def point(self, p, kind="ANCHOR"):
        ident = self.name("EB" if kind == "END_BUMPER" else "A")
        x, y = self.px(p)
        self.items.append(f'<positionablepoint ident="{ident}" type="{kind}" x="{x:.4f}" y="{y:.4f}"/>')
        return ident

    def segment(self, one, two, extra="", ctrl=()):
        """A track segment between two (name, type) ends; ctrl are Bezier control points in plan cm."""
        ident = self.name("S")
        kids = "".join(f'<controlpoint index="{i}" x="{self.px(c)[0]:.4f}" y="{self.px(c)[1]:.4f}"/>'
                       for i, c in enumerate(ctrl))
        kids = f"<controlpoints>{kids}</controlpoints>" if ctrl else ""
        self.items.append(f'<tracksegment ident="{ident}" connect1name="{one[0]}" type1="{one[1]}" '
                          f'connect2name="{two[0]}" type2="{two[1]}"{extra}>{kids}</tracksegment>')
        return ident

    def track(self, a, b):
        """A plain track between two point names."""
        return self.segment((a, "POS_POINT"), (b, "POS_POINT"))

    def turnout(self, ty, ends, symbol, ident=None):
        """A turnout part: `ends` its points, B and C end points in plan cm; `symbol` the JMRI turnout's centre, B
        and C points (drawn small inside the part, as AnyRail does). Returns the three end points' names."""
        ident = ident or self.name("TO")
        names = [self.point(p) for p in ends]
        legs = {}
        for leg, end in zip("ABC", names):
            legs[leg] = self.segment((ident, f"TURNOUT_{leg}"), (end, "POS_POINT"))
        (cx, cy), (bx, by), (qx, qy) = (self.px(p) for p in symbol)
        self.items.append(f'<layoutturnout ident="{ident}" type="{ty}" xcen="{cx:.4f}" ycen="{cy:.4f}" xb="{bx:.4f}" '
                          f'yb="{by:.4f}" xc="{qx:.4f}" yc="{qy:.4f}" connectaname="{legs["A"]}" '
                          f'connectbname="{legs["B"]}" connectcname="{legs["C"]}"/>')
        return names

    def beyond(self, end, at, heading, cm=30.0):
        """A plain track leaving end point `end` (at plan point `at`) on `heading`, to a new anchor."""
        return self.track(end, self.point(_ahead(at, heading, cm)))

    def xml(self):
        return ('<?xml version="1.0"?><layout-config><LayoutEditor name="made-up">' + "".join(self.items) +
                "</LayoutEditor></layout-config>")

    def read(self, **kw):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.xml"
            path.write_text(self.xml())
            return pieces.read(str(path), **kw)


def straight_turnout(plan, hand="R", origin=(0.0, 0.0), angle=9.5, beyond=("A", "B", "C"), kink=0.0):
    """A straight turnout like a #6: 23.35 cm straight route, diverging end 2.5 cm aside, leaving at `angle`."""
    s = 1 if hand == "R" else -1
    ox, oy = origin
    ends = [(ox, oy), (ox + 23.35, oy), (ox + 23.3, oy + s * 2.5)]
    symbol = [(ox + 11.7, oy), (ox + 15.8, oy), (ox + 15.8, oy + s * 0.6)]
    a, b, c = plan.turnout(f"{'RH' if hand == 'R' else 'LH'}_TURNOUT", ends, symbol)
    if "A" in beyond:
        plan.beyond(a, ends[0], 180 + kink)
    if "B" in beyond:
        plan.beyond(b, ends[1], 0)
    if "C" in beyond:
        plan.beyond(c, ends[2], s * angle)
    return a, b, c


def kinds(result, kind):
    return [p for p in result["pieces"] if p["kind"] == kind]


class Turnouts(unittest.TestCase):
    def test_a_straight_turnout_by_hand_lengths_angle_and_frog(self):
        plan = Plan()
        straight_turnout(plan, "R")
        straight_turnout(plan, "L", origin=(0.0, 50.0))
        right, left = kinds(plan.read(), "turnout")
        self.assertEqual((right["shape"], right["hand"], left["shape"], left["hand"]), ("straight", "R", "straight", "L"))
        self.assertAlmostEqual(right["straight_cm"], 23.35, places=3)
        self.assertAlmostEqual(right["diverging_chord_cm"], math.hypot(23.3, 2.5), places=3)
        self.assertAlmostEqual(right["angle_deg"], 9.5, places=3)
        self.assertAlmostEqual(right["frog_number"], 1 / (2 * math.tan(math.radians(4.75))), places=3)
        self.assertEqual(right["notes"], [])

    def test_the_same_part_turned_and_moved_reads_the_same(self):
        here, there = Plan(), Plan(turn=37.0, shift=(120.0, 40.0))
        straight_turnout(here)
        straight_turnout(there)
        a, b = kinds(here.read(), "turnout")[0], kinds(there.read(), "turnout")[0]
        for key in ("shape", "hand"):
            self.assertEqual(a[key], b[key])
        for key in ("straight_cm", "diverging_chord_cm", "angle_deg"):
            self.assertAlmostEqual(a[key], b[key], places=3)

    def test_a_kinked_join_at_the_points_does_not_change_the_shape(self):
        plan = Plan()
        straight_turnout(plan, kink=2.0)        # the track before the points is 2 degrees off line
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual((t["shape"], t["hand"]), ("straight", "R"))

    def test_with_nothing_beyond_b_the_track_before_the_points_gives_the_line(self):
        plan = Plan()
        straight_turnout(plan, beyond=("A", "C"))
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual(t["shape"], "straight")
        self.assertAlmostEqual(t["angle_deg"], 9.5, places=3)

    def test_a_curved_turnout_has_both_legs_to_one_side_and_no_frog_number(self):
        plan = Plan()
        ends = [(0.0, 0.0), (28.0, 3.0), (27.0, 6.0)]
        a, b, c = plan.turnout("RH_TURNOUT", ends, [(12.0, 0.5), (16.0, 1.0), (16.0, 1.6)])
        plan.beyond(a, ends[0], 180)
        plan.beyond(b, ends[1], 15)
        plan.beyond(c, ends[2], 25)
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual((t["shape"], t["hand"], t["frog_number"]), ("curved", "R", None))
        self.assertAlmostEqual(t["angle_deg"], 10.0, places=3)

    def test_a_wye_has_a_leg_each_side_and_no_hand(self):
        plan = Plan()
        ends = [(0.0, 0.0), (25.0, -2.0), (25.0, 2.0)]
        a, b, c = plan.turnout("WYE_TURNOUT", ends, [(12.0, 0.0), (16.0, -0.4), (16.0, 0.4)])
        plan.beyond(a, ends[0], 180)
        plan.beyond(b, ends[1], -9)
        plan.beyond(c, ends[2], 9)
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual((t["shape"], t["hand"]), ("wye", None))
        self.assertAlmostEqual(t["angle_deg"], 18.0, places=3)
        self.assertAlmostEqual(t["frog_number"], 1 / (2 * math.tan(math.radians(9))), places=3)

    def test_with_nothing_beyond_the_shape_is_unknown_and_says_so(self):
        plan = Plan()
        ends = [(0.0, 0.0), (23.35, 0.0), (23.3, 2.5)]
        names = plan.turnout("RH_TURNOUT", ends, [(11.7, 0.0), (15.8, 0.0), (15.8, 0.6)])
        for n in names:                 # each end a track end: a buffer stop on a short track
            plan.track(n, plan.point((0.0, -9.0), "END_BUMPER"))
        res = plan.read()
        t = next(p for p in kinds(res, "turnout"))
        self.assertEqual((t["shape"], t["hand"], t["angle_deg"]), ("unknown", None, None))
        self.assertIn("shape not read", t["notes"][0])
        self.assertTrue(any("shape not read" in line for line in pieces.report(res)))

    def test_a_curve_beyond_a_leg_is_not_read_as_its_heading(self):
        plan = Plan()
        a, b, c = straight_turnout(plan, beyond=("A", "B"))
        far = plan.point((50.0, 10.0))
        plan.segment((c, "POS_POINT"), (far, "POS_POINT"), ' arc="yes" circle="yes" angle="20"')
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual(t["shape"], "straight")
        self.assertIsNone(t["angle_deg"])

    def test_a_hand_the_export_type_contradicts_is_noted(self):
        plan = Plan()
        ends = [(0.0, 0.0), (23.35, 0.0), (23.3, 2.5)]
        a, b, c = plan.turnout("LH_TURNOUT", ends, [(11.7, 0.0), (15.8, 0.0), (15.8, 0.6)])
        plan.beyond(a, ends[0], 180)
        plan.beyond(b, ends[1], 0)
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual(t["hand"], "R")
        self.assertIn("the export calls it LH_TURNOUT", t["notes"][0])

    def test_turnout_legs_are_not_listed_as_track(self):
        plan = Plan()
        straight_turnout(plan)
        res = plan.read()
        self.assertEqual(len(kinds(res, "straight")), 3)        # the three tracks beyond, not the three legs


class ReviewFixes(unittest.TestCase):
    """Cases a review found, one test each."""

    def test_a_kinked_join_with_nothing_beyond_b_is_unknown_not_a_wye(self):
        plan = Plan()
        straight_turnout(plan, beyond=("A", "C"), kink=2.0)
        t = kinds(plan.read(), "turnout")[0]
        self.assertEqual(t["shape"], "unknown")
        self.assertIn("kinked join", t["notes"][0])

    def test_a_zero_diverging_angle_reports_without_a_frog_number(self):
        plan = Plan()
        straight_turnout(plan, angle=0.0)
        res = plan.read()
        self.assertEqual(kinds(res, "turnout")[0]["angle_deg"], 0.0)
        line = next(x for x in pieces.report(res) if "turnout" in x)
        self.assertNotIn("frog number", line)
        with self.assertRaisesRegex(PlanError, "no frog number"):
            pieces.frog_number(0.0)

    def test_straight_flex_drawn_at_an_angle_has_no_radius(self):
        plan = Plan(turn=37.0)
        a, b = plan.point((0.0, 0.0)), plan.point((30.0, 0.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' bezier="yes"', ctrl=[(10.0, 0.0), (20.0, 0.0)])
        self.assertIsNone(kinds(plan.read(), "flex")[0]["tightest_radius_cm"])

    def test_the_legs_of_a_turnout_type_not_read_are_not_track(self):
        plan = Plan()
        a = plan.point((10.0, 0.0))
        leg = plan.segment(("TX", "TURNOUT_A"), (a, "POS_POINT"))
        plan.items.append(f'<layoutturnout ident="TX" type="LH_XOVER" xcen="0" ycen="0" xb="1" yb="0" xc="1" yc="1" '
                          f'connectaname="{leg}"/>')
        res = plan.read()
        self.assertEqual(res["pieces"], [])
        self.assertIn("nor its legs", dict(res["skipped"])["TX"])

    def test_a_half_circle_of_flex_turns_180_clockwise(self):
        plan = Plan()
        a, b = plan.point((0.0, 0.0)), plan.point((0.0, 100.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' bezier="yes"', ctrl=[(66.5, 0.0), (66.5, 100.0)])
        self.assertAlmostEqual(kinds(plan.read(), "flex")[0]["turn_deg"], 180.0, delta=0.5)

    def test_a_turnout_leg_on_a_crossing_skips_the_turnout_not_the_run(self):
        plan = Plan()
        straight_turnout(plan, origin=(0.0, 50.0))
        ends = [(0.0, 0.0), (23.35, 0.0), (23.3, 2.5)]
        a, b, _ = (plan.point(p) for p in ends)
        legs = [plan.segment(("T9", "TURNOUT_A"), (a, "POS_POINT")), plan.segment(("T9", "TURNOUT_B"), (b, "POS_POINT")),
                plan.segment(("T9", "TURNOUT_C"), ("LX1", "LEVEL_XING_A"))]
        (cx, cy), (bx, by), (qx, qy) = (plan.px(p) for p in ((11.7, 0.0), (15.8, 0.0), (15.8, 0.6)))
        plan.items.append(f'<layoutturnout ident="T9" type="RH_TURNOUT" xcen="{cx}" ycen="{cy}" xb="{bx}" yb="{by}" '
                          f'xc="{qx}" yc="{qy}" connectaname="{legs[0]}" connectbname="{legs[1]}" '
                          f'connectcname="{legs[2]}"/>')
        plan.items.append('<levelxing ident="LX1" xcen="0" ycen="0"/>')
        res = plan.read()
        self.assertIn("a crossing, slip or turntable", dict(res["skipped"])["T9"])
        self.assertEqual(len(kinds(res, "turnout")), 1)

    def test_two_panels_in_one_file_stop(self):
        plan = Plan()
        plan.track(plan.point((0.0, 0.0)), plan.point((1.0, 0.0)))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "two.xml"
            path.write_text(plan.xml().replace("</layout-config>", '<LayoutEditor name="second"/></layout-config>'))
            with self.assertRaisesRegex(PlanError, "2 <LayoutEditor> panels"):
                pieces.read(str(path))


class DoubleCrossover(unittest.TestCase):
    def test_length_and_spacing(self):
        plan = Plan()
        names = [plan.point(p) for p in ((-24.0, -2.5), (24.0, -2.5), (24.0, 2.5), (-24.0, 2.5))]
        legs = {leg: plan.segment(("X", f"TURNOUT_{leg}"), (n, "POS_POINT")) for leg, n in zip("ABCD", names)}
        (cx, cy), (bx, by), (qx, qy) = (plan.px(p) for p in ((0.0, 0.0), (10.0, -2.5), (10.0, 2.5)))
        plan.items.append(f'<layoutturnout ident="X" type="DOUBLE_XOVER" xcen="{cx}" ycen="{cy}" xb="{bx}" yb="{by}" '
                          f'xc="{qx}" yc="{qy}" ' + " ".join(f'connect{k.lower()}name="{v}"' for k, v in legs.items()) +
                          "/>")
        x = kinds(plan.read(), "double_crossover")[0]
        self.assertAlmostEqual(x["length_cm"], 48.0, places=3)
        self.assertAlmostEqual(x["spacing_cm"], 5.0, places=3)


class Track(unittest.TestCase):
    def test_a_curve_gives_its_radius_angle_and_length(self):
        plan = Plan()
        r, angle = 60.96, 30.0
        a = plan.point((0.0, 0.0))
        b = plan.point((2 * r * math.sin(math.radians(angle / 2)), 0.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), f' arc="yes" circle="yes" angle="{angle}"')
        c = kinds(plan.read(), "curve")[0]
        self.assertAlmostEqual(c["radius_cm"], r, places=3)
        self.assertAlmostEqual(c["angle_deg"], angle)
        self.assertAlmostEqual(c["length_cm"], r * math.radians(angle), places=3)

    def test_flex_gives_its_length_turn_and_tightest_radius(self):
        plan = Plan()
        r, k = 50.0, 0.5523 * 50.0                  # a quarter circle drawn as one cubic Bezier
        a, b = plan.point((0.0, 0.0)), plan.point((r, r))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' bezier="yes"', ctrl=[(k, 0.0), (r, r - k)])
        f = kinds(plan.read(), "flex")[0]
        self.assertAlmostEqual(f["length_cm"], math.pi * r / 2, delta=0.05)
        self.assertAlmostEqual(f["turn_deg"], 90.0, places=3)
        self.assertAlmostEqual(f["tightest_radius_cm"], r, delta=0.5)

    def test_straight_flex_has_no_radius(self):
        plan = Plan()
        a, b = plan.point((0.0, 0.0)), plan.point((30.0, 0.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' bezier="yes"', ctrl=[(10.0, 0.0), (20.0, 0.0)])
        f = kinds(plan.read(), "flex")[0]
        self.assertAlmostEqual(f["length_cm"], 30.0, places=3)
        self.assertIsNone(f["tightest_radius_cm"])

    def test_straight_track_and_track_ends(self):
        plan = Plan()
        plan.track(plan.point((0.0, 0.0), "END_BUMPER"), plan.point((40.0, 30.0)))
        res = plan.read()
        self.assertAlmostEqual(kinds(res, "straight")[0]["length_cm"], 50.0, places=3)
        self.assertEqual(res["track_ends"], 1)

    def test_a_scale_given_is_used(self):
        plan = Plan()
        plan.track(plan.point((0.0, 0.0)), plan.point((40.0, 0.0)))
        self.assertAlmostEqual(kinds(plan.read(px_per_cm=PX_PER_CM * 2), "straight")[0]["length_cm"], 20.0, places=3)


class Skipped(unittest.TestCase):
    def test_what_is_not_read_is_listed_with_why(self):
        plan = Plan()
        a, b = plan.point((0.0, 0.0)), plan.point((10.0, 5.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' arc="yes" circle="no" angle="40"')
        plan.items.append('<levelxing ident="LX1" xcen="0" ycen="0"/>')
        plan.items.append('<layoutturnout ident="TX" type="LH_XOVER" xcen="0" ycen="0" xb="1" yb="0" xc="1" yc="1"/>')
        res = plan.read()
        why = dict(res["skipped"])
        self.assertIn("elliptical", why["S3"])
        self.assertIn("levelxing", why["LX1"])
        self.assertIn("LH_XOVER", why["TX"])
        self.assertEqual(res["pieces"], [])


class Report(unittest.TestCase):
    def test_one_part_placed_twice_is_one_line(self):
        plan = Plan()
        straight_turnout(plan)
        straight_turnout(plan, origin=(100.0, 0.0))
        lines = pieces.report(plan.read())
        line = next(x for x in lines if "turnout" in x)
        self.assertTrue(line.lstrip().startswith("2 x straight turnout R, straight route 23.4 cm (9.19 in)"), line)
        self.assertIn("diverging angle 9.5 deg (frog number 6.0;", line)

    def test_curves_of_one_radius_and_two_angles_are_two_lines(self):
        plan = Plan()
        for i, angle in enumerate((30.0, 30.0, 45.0)):
            a = plan.point((0.0, 100.0 * i))
            b = plan.point((2 * 60.0 * math.sin(math.radians(angle / 2)), 100.0 * i))
            plan.segment((a, "POS_POINT"), (b, "POS_POINT"), f' arc="yes" circle="yes" angle="{angle}"')
        lines = [x for x in pieces.report(plan.read()) if "curve radius" in x]
        self.assertEqual([x.split(":")[0].strip() for x in lines],
                         ["2 x curve radius 60.0 cm (23.62 in), 30.0 deg", "1 x curve radius 60.0 cm (23.62 in), 45.0 deg"])

    def test_the_tightest_flex_is_named(self):
        plan = Plan()
        a, b = plan.point((0.0, 0.0)), plan.point((10.0, 10.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' bezier="yes"', ctrl=[(5.0, 0.0), (10.0, 5.0)])
        line = next(x for x in pieces.report(plan.read()) if "flex" in x)
        self.assertIn("on S3", line)


class BadInput(unittest.TestCase):
    def write(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "x.xml"
        path.write_text(text)
        return str(path)

    def test_not_xml(self):
        with self.assertRaisesRegex(PlanError, "not readable XML"):
            pieces.read(self.write("not xml <"))

    def test_no_panel(self):
        with self.assertRaisesRegex(PlanError, "no <LayoutEditor> panel"):
            pieces.read(self.write("<layout-config/>"))

    def test_no_track(self):
        with self.assertRaisesRegex(PlanError, "holds no track"):
            pieces.read(self.write("<layout-config><LayoutEditor/></layout-config>"))

    def test_a_missing_point(self):
        plan = Plan()
        plan.track("A1", "NOPE")
        with self.assertRaisesRegex(PlanError, "'A1', which the export does not have"):
            plan.read()

    def test_a_coordinate_that_is_not_a_number(self):
        plan = Plan()
        plan.items.append('<positionablepoint ident="P" type="ANCHOR" x="abc" y="0"/>')
        plan.items.append('<positionablepoint ident="Q" type="ANCHOR" x="1" y="0"/>')
        plan.track("P", "Q")
        with self.assertRaisesRegex(PlanError, "positionablepoint 'P': x='abc' is not a number"):
            plan.read()

    def test_two_elements_with_one_ident(self):
        plan = Plan()
        plan.track(plan.point((0.0, 0.0)), plan.point((1.0, 0.0)))
        plan.items.append(plan.items[-1])
        with self.assertRaisesRegex(PlanError, "share the ident"):
            plan.read()

    def test_a_scale_that_is_not_above_zero(self):
        plan = Plan()
        plan.track(plan.point((0.0, 0.0)), plan.point((1.0, 0.0)))
        for bad in (0, -1.0, float("nan"), "4"):
            with self.assertRaisesRegex(PlanError, "the scale must be"):
                plan.read(px_per_cm=bad)

    def test_a_turnout_point_that_is_missing_names_the_turnout(self):
        import xml.etree.ElementTree as ET
        from schematic import plan_reader
        t = ET.fromstring('<layoutturnout ident="T9" type="RH_TURNOUT" xcen="1" ycen="1" xc="2" yc="2"/>')
        with self.assertRaisesRegex(PlanError, "layoutturnout 'T9': xb=None is not a number"):
            plan_reader.turnout_point(t, "A")

    def test_an_arc_with_no_angle(self):
        plan = Plan()
        a, b = plan.point((0.0, 0.0)), plan.point((10.0, 0.0))
        plan.segment((a, "POS_POINT"), (b, "POS_POINT"), ' arc="yes" circle="yes" angle="0"')
        with self.assertRaisesRegex(PlanError, "arc angle 0.0 is outside"):
            plan.read()


class Command(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "schematic", "pieces", *map(str, args)], cwd=helpers.PLUGIN,
                              capture_output=True, text=True, timeout=60)

    def test_report_and_json(self):
        plan = Plan()
        straight_turnout(plan)
        with tempfile.TemporaryDirectory() as tmp:
            export, out = Path(tmp) / "export.xml", Path(tmp) / "pieces.json"
            export.write_text(plan.xml())
            r = self.run_cli(export, "--json", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("scale: 4.7244 px per cm (12.00 px per inch)", r.stdout)
            self.assertIn("1 x straight turnout R", r.stdout)
            saved = json.loads(out.read_text())
            self.assertEqual([p["kind"] for p in saved["pieces"]].count("turnout"), 1)

    def test_an_error_is_one_line_and_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.run_cli(Path(tmp) / "missing.xml")
        self.assertEqual(r.returncode, 2)
        self.assertRegex(r.stderr, r"^error: .*missing\.xml: cannot be read")
        self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()
