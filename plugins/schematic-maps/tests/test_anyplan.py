"""schematic anyplan: the .any record shapes on made-up bytes, the part types on made-up ends, joins, runs and the
level cut. Every file here is written by the tests, track only; no real plan is read."""
import io
import json
import math
import struct
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import helpers  # noqa: F401  (puts the plugin on the module path)
from schematic import anyplan as A
from schematic import cli


def u64(n):
    return struct.pack("<Q", n)


def text(s):
    return u64(len(s)) + s.encode()


def name(cat, lib):
    return b"\x01\x02" + text(cat) + text(lib) + b"\x00" * 6


def end(x, y, z, deg, system, head=b"X\x00\x01\x00\x00\x00\x02\x00\x00\x00"):
    return head + struct.pack("<4d", x, y, z, math.radians(deg)) + text(system) + b"\x00\x00"


def curve(points, tag=b"6\x00"):
    out = u64(len(points))
    for k, (x, y) in enumerate(points):
        out += tag + struct.pack("<I", 100 + k) + struct.pack("<2d", x, y)
    return out


def plan_bytes():
    """A flex piece (first in the file, so its first end has the longer first-of-its-kind header), a right-hand
    turnout of another maker's library, a placed object and the junk shapes found in real headers."""
    return b"".join([
        b"\x00" * 16, end(0.0, 0.0, 0.0, 0.0, "QRS83"),                     # a header: (0, 0) is no place
        end(1e-320, 5e-318, 0.0, 0.0, "QRS83"),                              # subnormal junk
        name("OBJECT-1", "OBJLIB"), end(50.0, 50.0, 0.0, 0.0, "OBJLIB"),   # a placed object: one end
        name("FLEX-1", "ABC87"),
        end(10.0, 20.0, -30.0, 180.0, "ABC87", head=b"X\x00\x01\x04\x00\x00\x00\x83\x5a\x00\x00\x01\x00\x00\x00\x00"),
        end(40.0, 20.0, -30.0, 0.0, "ABC87"),
        curve([(10.0, 20.0), (20.0, 20.0), (30.0, 20.0), (40.0, 20.0)]),
        name("83999", "XYZ87F19"),                                           # a library longer than its system
        end(40.0, 20.0, -30.0, 180.0, "XYZ87"),
        end(63.4, 20.0, -30.0, 0.0, "XYZ87"),
        end(63.3, 22.5, -30.0, 9.5, "XYZ87"),
    ])


class Records(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = tempfile.TemporaryDirectory()
        cls.addClassCleanup(folder.cleanup)
        cls.tmp = Path(folder.name) / "plan.any"
        cls.tmp.write_bytes(plan_bytes())
        cls.parts = A.read(cls.tmp)

    def test_track_parts_only_in_file_order(self):
        self.assertEqual([(p["index"], p["name"]) for p in self.parts], [(0, "FLEX-1"), (1, "83999")])

    def test_the_first_end_point_with_its_longer_header_is_read(self):
        self.assertEqual([(e["x"], e["y"]) for e in self.parts[0]["ends"]], [(10.0, 20.0), (40.0, 20.0)])

    def test_a_library_is_track_when_its_name_starts_with_a_track_system(self):
        self.assertEqual((self.parts[1]["library"], self.parts[1]["system"]), ("XYZ87F19", "XYZ87"))

    def test_the_flex_curve_with_this_files_tag_gives_its_length(self):
        self.assertAlmostEqual(self.parts[0]["cm"], 30.0, places=3)
        self.assertIsNone(self.parts[1]["cm"])

    def test_the_parts_list_holds_name_and_x_y_z_only(self):
        self.assertEqual(A.parts_list(self.parts)[0],
                         {"name": "FLEX-1", "eps": [{"x": 10.0, "y": 20.0, "z": -30.0},
                                                    {"x": 40.0, "y": 20.0, "z": -30.0}]})

    def test_the_two_parts_join_and_runs_end_at_free_ends(self):
        links, free = A.joins(self.parts)
        self.assertEqual(links, [(0, 1, 1, 0)])
        self.assertEqual(sorted(free), [(0, 0), (1, 1), (1, 2)])
        self.assertEqual(sorted((r[1], r[2], round(r[4], 3)) for r in A.runs(self.parts, links)),
                         [(0, None, 30.0), (1, None, 0.0), (2, None, 0.0)])

    def test_a_one_ended_part_is_a_track_end_that_ends_a_run(self):
        stop = self.tmp.with_name("stop.any")
        stop.write_bytes(plan_bytes() + name("STOP-1", "ABC87") + end(63.4, 20.0, -30.0, 180.0, "ABC87"))
        parts = A.read(stop)
        self.assertEqual(parts[2]["kind"], "end")
        links, free = A.joins(parts)
        self.assertIn((1, 1, 2, 0), links)
        self.assertIn((1, 1, None, None, 0.0), A.runs(parts, links))

    def test_a_part_with_five_ends_stops_the_read(self):
        bad = self.tmp.with_name("bad.any")
        bad.write_bytes(plan_bytes() + name("ODD-1", "ABC87") +
                        b"".join(end(90.0 + i, 90.0, 0.0, 0.0, "ABC87") for i in range(5)))
        with self.assertRaisesRegex(A.PlanError, "more than four ends"):
            A.read(bad)

    def test_a_string_followed_by_a_printable_byte_is_still_read(self):
        """The string's length prefix decides where it ends, whatever comes after it."""
        self.assertEqual(A._names(b"\x01" + text("XY-E83") + text("QRS83") + b"A\x00\x00"), [(1, "XY-E83", "QRS83")])
        rec = struct.pack("<4d", 5.0, 6.0, 0.0, 0.0) + text("QRS83") + b"Z"
        self.assertEqual(A._end_records(rec), [(0, 5.0, 6.0, 0.0, 0.0, "QRS83")])

    def test_the_command_line_says_what_is_wrong(self):
        empty = self.tmp.with_name("empty2.any")
        empty.write_bytes(b"\x00" * 64)
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(cli.run(["anyplan", str(empty), "--report"]), 2)
        self.assertIn("no track end points", err.getvalue())

    def test_a_file_with_no_track_says_so(self):
        empty = self.tmp.with_name("empty.any")
        empty.write_bytes(b"\x00" * 64)
        with self.assertRaisesRegex(A.PlanError, "no track end points"):
            A.read(empty)


def ends(*spec):
    return [dict(x=x, y=y, z=z, a=math.radians(deg)) for x, y, z, deg in spec]


class Kinds(unittest.TestCase):
    """Ends as AnyRail stores them: y grows down the screen, a turnout's straight leg faces opposite its points."""

    def test_straight_turnouts_by_hand(self):
        right = A.classify(ends((0, 0, 0, 180), (23.4, 0, 0, 0), (23.3, 2.5, 0, 9.5)))
        left = A.classify(ends((0, 0, 0, 180), (23.4, 0, 0, 0), (23.3, -2.5, 0, -9.5)))
        self.assertEqual((right["kind"], right["hand"], right["curved"], right["points"]), ("turnout", "R", False, 0))
        self.assertEqual((left["hand"], left["straight"], left["diverging"]), ("L", 1, 2))

    def test_a_curved_turnout(self):
        k = A.classify(ends((0, 0, 0, 180), (28.0, -2.4, 0, -10.4), (27.5, -4.9, 0, -20.0)))
        self.assertEqual((k["kind"], k["hand"], k["curved"], k["straight"]), ("turnout", "L", True, 1))

    def test_four_ended_parts(self):
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (20, 0, 0, 0), (20, 3, 0, 9), (20, -3, 0, -9)))["kind"],
                         "threeway")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (0, 5, 0, 180), (48, 0, 0, 0), (48, 5, 0, 0)))["kind"],
                         "double_crossover")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (0, 5, 0, 166), (48, 0, 0, 0), (48, 5, 0, -14)))["kind"],
                         "crossing")
        self.assertEqual(A.classify(ends((0, 0, 0, 180), (10, 0, 0, 0), (5, -5, 0, -90), (5, 5, 0, 90)))["kind"],
                         "crossing")                                         # a square diamond is no three-way

    def test_a_part_with_no_curve_is_measured_from_its_ends(self):
        self.assertAlmostEqual(A.fixed_length(ends((0, 0, 0, 180), (20, 0, 0, 0))), 20.0)
        r = 50.0                                                              # a quarter circle of radius 50
        self.assertAlmostEqual(A.fixed_length(ends((0, 0, 0, 180), (r, r, 0, 90))), math.pi * r / 2, places=6)


class Joins(unittest.TestCase):
    def part(self, i, *spec):
        return dict(index=i, ends=ends(*spec), cm=None, curve=None, kind="track")

    def test_a_gap_between_facing_ends_is_reported_once_and_side_by_side_ends_not_at_all(self):
        gap = [self.part(0, (0, 0, 0, 180), (10, 0, 0, 0)), self.part(1, (11, 0, 0, 180), (20, 0, 0, 0))]
        self.assertEqual(A.report(gap)[-1].split(": ", 1)[1], "[(0, 1, 1.0, 0)]")
        side = [self.part(0, (0, 0, 0, 180), (10, 0, 0, 0)), self.part(1, (0, 4, 0, 180), (10, 4, 0, 0))]
        self.assertTrue(A.report(side)[-1].endswith("none"))

    def test_ends_at_different_heights_do_not_join(self):
        links, free = A.joins([self.part(0, (0, 0, 0, 0), (10, 0, 0, 0)), self.part(1, (10, 0, 10.8, 0), (20, 0, 10.8, 0))])
        self.assertEqual((links, len(free)), ([], 4))

    def test_three_ends_on_one_spot_stop(self):
        with self.assertRaisesRegex(A.PlanError, "more than two"):
            A.joins([self.part(i, (0, 0, 0, 0), (10 + i, 5, 0, 0)) for i in range(3)])


class Cuts(unittest.TestCase):
    """A run that climbs between two levels is parted at the cut height, each side's share from its pieces' grades."""

    @staticmethod
    def rise():
        """Turnout 0 at -30 cm, two 100 cm flex pieces climbing to 0, turnout 3 at 0 cm; turnout 0's other legs free."""
        def part(i, *spec, cm=None):
            return dict(index=i, ends=ends(*spec), cm=cm, curve=None)
        return [part(0, (0, 0, -30, 180), (-10, 0, -30, 0), (-10, 2, -30, 0)),
                part(1, (0, 0, -30, 0), (100, 0, -15, 0), cm=100.0),
                part(2, (100, 0, -15, 0), (200, 0, 0, 0), cm=100.0),
                part(3, (200, 0, 0, 180), (210, 0, 0, 0), (210, 2, 0, 0))]

    def test_the_cut_parts_the_run_by_height(self):
        parts = self.rise()
        links, _ = A.joins(parts)
        (c,) = A.level_cuts(parts, links, -5.0)
        self.assertEqual((c["low"], c["high"]), ((0, 0), (3, 0)))
        self.assertAlmostEqual(c["low_cm"], 100 + 100 * 10 / 15)            # -15 to -5 of the second piece's 15 cm
        self.assertAlmostEqual(c["low_cm"] + c["high_cm"], 200.0)
        self.assertEqual(A.level_cuts(parts, links, 5.0), [])                # nothing climbs through 5 cm

    def test_each_graph_gets_a_stub_on_the_leg_it_lacks(self):
        cut = dict(low=(0, 0), high=(3, 0), low_cm=173.7, high_cm=26.3)
        g = dict(nodes={"S": dict(kind="switch", label="T0", xy=[0.0, 0.0], dirs={"B": [1.0, 0.0]}),
                        "E": dict(kind="end", label="", xy=[-50.0, 0.0])},
                 edges=[dict(id="e0", u="S", up="A", v="E", vp="E", cm=10.0),
                        dict(id="e1", u="S", up="C", v="E", vp="E", cm=10.0)])
        self.assertEqual(A.add_cut_stubs(g, [cut], -5.0), ["T0"])
        stub = g["edges"][-1]
        self.assertEqual((stub["id"], stub["u"], stub["up"], stub["v"], stub["cm"]), ("e2", "S", "B", "CUT:T0", 173.7))
        self.assertEqual((g["nodes"]["CUT:T0"]["cut"], g["nodes"]["CUT:T0"]["xy"]), (-5.0, [A.STUB_PX, 0.0]))
        with self.assertRaisesRegex(A.PlanError, "lacks none"):               # read twice: no leg left to give
            A.add_cut_stubs(g, [cut], -5.0)

    def test_a_side_no_graph_holds_stops(self):
        parts = self.rise()

        def level(label, port):
            return dict(nodes={"S": dict(kind="switch", label=label, xy=[0.0, 0.0], dirs={port: [1.0, 0.0]}),
                               "E": dict(kind="end", label="", xy=[-50.0, 0.0])},
                        edges=[dict(id="e0", u="S", up=p, v="E", vp="E", cm=10.0) for p in "ABC" if p != port])
        low = level("T0", "A")
        self.assertEqual(A.stub_graphs(parts, -5.0, [low, level("T3", "A")]), ["T0", "T3"])
        with self.assertRaisesRegex(A.PlanError, "gave stubs at T0"):      # turnout 3's level is not given
            A.stub_graphs(parts, -5.0, [level("T0", "A")])


def level_graph(label, port):
    """A plan graph holding one switch, labelled `label`, whose leg `port` is the one it lacks."""
    return dict(nodes={"S": dict(kind="switch", label=label, xy=[0.0, 0.0], dirs={port: [1.0, 0.0]}),
                       "E": dict(kind="end", label="", xy=[-50.0, 0.0])},
                edges=[dict(id=f"e{i}", u="S", up=p, v="E", vp="E", cm=10.0)
                       for i, p in enumerate(p for p in "ABC" if p != port)])


def rise_bytes():
    """Two turnouts 200 cm apart joined by two flex pieces that climb from -30 cm to 0 cm (away from (0, 0), which
    the reader takes for no place)."""
    def e(x, y, z, deg):
        return end(50.0 + x, 50.0 + y, z, deg, "ABC87")

    def flex(x0, x1):
        return curve([(50.0 + x0 + k * (x1 - x0) / 3, 50.0) for k in range(4)])
    return b"".join([
        name("TURN-1", "ABC87"), e(0.0, 0.0, -30.0, 180.0), e(-10.0, 0.0, -30.0, 0.0), e(-10.0, 2.0, -30.0, 0.0),
        name("FLEX-1", "ABC87"), e(0.0, 0.0, -30.0, 180.0), e(100.0, 0.0, -15.0, 0.0), flex(0.0, 100.0),
        name("FLEX-1", "ABC87"), e(100.0, 0.0, -15.0, 180.0), e(200.0, 0.0, 0.0, 0.0), flex(100.0, 200.0),
        name("TURN-1", "ABC87"), e(200.0, 0.0, 0.0, 180.0), e(210.0, 0.0, 0.0, 0.0), e(210.0, 2.0, 0.0, 0.0),
    ])


class Command(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.tmp = Path(folder.name)
        self.plan = self.tmp / "rise.any"
        self.plan.write_bytes(rise_bytes())

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.run(["anyplan", str(self.plan), *map(str, args)])
        return code, out.getvalue(), err.getvalue()

    def test_the_parts_list_is_written(self):
        code, out, _ = self.run_cli("--parts", self.tmp / "parts.json")
        self.assertEqual(code, 0)
        self.assertIn("4 parts", out)
        self.assertEqual(len(json.loads((self.tmp / "parts.json").read_text())), 4)

    def test_the_report_is_printed_without_options(self):
        code, out, _ = self.run_cli()
        self.assertEqual(code, 0)
        self.assertIn("4 track parts", out)
        self.assertIn("sloped two-ended pieces: 2", out)

    def test_cut_and_stubs_go_together(self):
        code, _, err = self.run_cli("--cut", "-5")
        self.assertEqual(code, 2)
        self.assertIn("--cut and --stubs go together", err)

    def test_each_level_gets_its_stub_and_the_graphs_are_written(self):
        low, high = self.tmp / "low.json", self.tmp / "high.json"
        low.write_text(json.dumps(level_graph("T0", "A")))
        high.write_text(json.dumps(level_graph("T3", "A")))
        code, out, err = self.run_cli("--cut", "-5", "--stubs", low, high)
        self.assertEqual(code, 0, err)
        stub = json.loads(low.read_text())["edges"][-1]
        self.assertEqual((stub["v"], stub["cm"]), ("CUT:T0", round(100 + 100 * 10 / 15, 1)))
        self.assertEqual(json.loads(high.read_text())["edges"][-1]["v"], "CUT:T3")

    def test_a_graph_that_is_not_json_stops_before_anything_is_written(self):
        low, bad, parts = self.tmp / "low.json", self.tmp / "bad.json", self.tmp / "parts.json"
        low.write_text(json.dumps(level_graph("T0", "A")))
        bad.write_text("{not json")
        before = low.read_text()
        code, _, err = self.run_cli("--parts", parts, "--cut", "-5", "--stubs", low, bad)
        self.assertEqual(code, 2)
        self.assertIn("bad.json: cannot read the graph", err)
        self.assertEqual(low.read_text(), before)
        self.assertFalse(parts.exists())


class PortReviewFixes(unittest.TestCase):
    """Cases a review of the port found, one test each."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.tmp = Path(folder.name)

    def test_a_long_catalogue_name_is_still_a_part(self):
        long = "A-VERY-LONG-CATALOGUE-NAME-FOR-ONE-FLEX-PIECE-OF-TRACK-IN-SOME-LIBRARY"     # 70 bytes
        plan = self.tmp / "long.any"
        plan.write_bytes(name("FLEX-1", "ABC87") + end(10.0, 20.0, 0.0, 180.0, "ABC87") + end(40.0, 20.0, 0.0, 0.0, "ABC87")
                         + name(long, "ABC87") + end(40.0, 20.0, 0.0, 180.0, "ABC87") + end(70.0, 20.0, 0.0, 0.0, "ABC87"))
        parts = A.read(plan)
        self.assertEqual([(p["name"], len(p["ends"])) for p in parts], [("FLEX-1", 2), (long, 2)])

    def test_a_run_that_crosses_the_cut_three_times_stops(self):
        def part(i, *spec, cm=None):
            return dict(index=i, ends=ends(*spec), cm=cm, curve=None)
        parts = [part(0, (0, 0, -30, 180), (-10, 0, -30, 0), (-10, 2, -30, 0)),
                 part(1, (0, 0, -30, 0), (100, 0, -4, 0), cm=100.0),
                 part(2, (100, 0, -4, 0), (150, 0, -6, 0), cm=50.0),          # dips back through -5
                 part(3, (150, 0, -6, 0), (250, 0, 0, 0), cm=100.0),
                 part(4, (250, 0, 0, 180), (260, 0, 0, 0), (260, 2, 0, 0))]
        links, _ = A.joins(parts)
        with self.assertRaisesRegex(A.PlanError, "crosses -5.0 cm 3 times"):
            A.level_cuts(parts, links, -5.0)

    def test_a_curve_must_start_on_one_end_and_finish_on_the_other(self):
        short = ends((10.0, 20.0, 0, 180), (10.4, 20.0, 0, 0))     # both ends near one tip of the list below
        data = curve([(10.2, 20.0), (20.0, 20.0), (30.0, 20.0), (40.0, 20.0)])
        self.assertIsNone(A._curve(data, 0, short))
        right = ends((10.2, 20.0, 0, 180), (40.0, 20.0, 0, 0))
        self.assertIsNotNone(A._curve(data, 0, right))

    def test_a_stubs_file_that_is_not_a_plan_graph_says_so(self):
        plan = self.tmp / "rise.any"
        plan.write_bytes(rise_bytes())
        low, other = self.tmp / "low.json", self.tmp / "other.json"
        low.write_text(json.dumps(level_graph("T0", "A")))
        other.write_text(json.dumps([{"name": "x", "eps": []}]))
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cli.run(["anyplan", str(plan), "--cut", "-5", "--stubs", str(low), str(other)])
        self.assertEqual(code, 2)
        self.assertIn("other.json is not a plan graph", err.getvalue())

    def test_a_parts_file_in_a_missing_folder_writes_nothing(self):
        plan = self.tmp / "rise.any"
        plan.write_bytes(rise_bytes())
        low, high = self.tmp / "low.json", self.tmp / "high.json"
        low.write_text(json.dumps(level_graph("T0", "A")))
        high.write_text(json.dumps(level_graph("T3", "A")))
        before = low.read_text()
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = cli.run(["anyplan", str(plan), "--parts", str(self.tmp / "nope" / "parts.json"),
                            "--cut", "-5", "--stubs", str(low), str(high)])
        self.assertEqual(code, 2)
        self.assertIn("no such folder; nothing written", err.getvalue())
        self.assertEqual(low.read_text(), before)


class SharedBezier(unittest.TestCase):
    def test_a_chain_of_cubics_is_measured_along_each(self):
        line = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (3.0, 0.0), (4.0, 0.0), (5.0, 0.0), (6.0, 0.0)]
        self.assertAlmostEqual(A.bezier_length(line), 6.0, places=6)

    def test_a_chain_of_the_wrong_length_says_so(self):
        with self.assertRaisesRegex(A.PlanError, "1 \\+ 3n points"):
            A.bezier_length([(0.0, 0.0), (1.0, 0.0), (2.0, 0.0)])


if __name__ == "__main__":
    unittest.main()
