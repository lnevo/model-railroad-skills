"""The Layout Editor panel drawn from the example's solved bands: turnouts, track, arcs, ends, names, XML."""
import json
import math
import re
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from unittest import mock

import helpers
from schematic import le, le_labels
from schematic.core import SchematicError


def bands():
    return helpers.build().bands


def panel(names=None):
    key = ("le", repr(names))
    if key not in helpers._cache:
        helpers._cache[key] = le.panel(bands(), names)
    return helpers._cache[key]


def element(P=None):
    return le.to_xml(P or panel(), "Generated")


def items(el):
    return {c.get("ident"): c for c in el if c.get("ident")}


def strand_at(band, n, port):
    d = band["nodes"][n]
    return d["ins"].get(port) or d["outs"].get(port)


class Track(unittest.TestCase):
    def test_every_strand_is_drawn_and_the_panel_is_one_railroad(self):
        P = panel()
        for bi, (_, band, _) in enumerate(bands()):
            for sid in band["strands"]:
                self.assertTrue(P.strand_segments[(bi, sid)], sid)
        # every piece of track reaches every other through the segments (the levels by their hidden joins)
        graph = defaultdict(set)
        for s in P.segments:
            a, b = s["ends"][0][0], s["ends"][1][0]
            graph[a].add(b)
            graph[b].add(a)
        start = next(iter(graph))
        seen, todo = {start}, [start]
        while todo:
            for nxt in graph[todo.pop()]:
                if nxt not in seen:
                    seen.add(nxt)
                    todo.append(nxt)
        self.assertEqual(seen, set(P.points) | {t["ident"] for t in P.turnouts})

    def test_no_dangling_connection_names(self):
        el = element()
        it = items(el)
        for s in el.findall("tracksegment"):
            for i in (1, 2):
                name, typ = s.get(f"connect{i}name"), s.get(f"type{i}")
                far = it[name]
                if typ == "POS_POINT":
                    self.assertEqual(far.tag, "positionablepoint")
                    self.assertIn(s.get("ident"), (far.get("connect1name"), far.get("connect2name")))
                else:
                    self.assertEqual(far.tag, "layoutturnout")
                    self.assertEqual(far.get(f"connect{typ[-1].lower()}name"), s.get("ident"))
        for p in el.findall("positionablepoint"):
            if p.get("type") == "ANCHOR":
                self.assertTrue(p.get("connect1name") and p.get("connect2name"), p.get("ident"))
            else:
                self.assertEqual(p.get("type"), "END_BUMPER")
                self.assertIsNone(p.get("connect2name"))
        for t in el.findall("layoutturnout"):
            for leg in ("abcd" if "XOVER" in t.get("type") else "abc"):
                self.assertEqual(it[t.get(f"connect{leg}name")].tag, "tracksegment")

    def test_track_attributes_and_idents(self):
        el = element()
        idents = [c.get("ident") for c in el if c.get("ident")]
        self.assertEqual(len(idents), len(set(idents)))
        for c in el:
            self.assertTrue(c.get("class"), c.tag)
        for s in el.findall("tracksegment"):
            self.assertFalse(s.get("ident").startswith(("TO", "TUR", "TRV")))
            for a in ("dashed", "mainline", "hidden"):
                self.assertIn(s.get(a), ("yes", "no"))
        for t in el.findall("layoutturnout"):
            self.assertTrue(t.get("ident").startswith("TO"))
        for p in el.findall("positionablepoint"):
            self.assertTrue(p.get("ident").startswith("EB" if p.get("type") == "END_BUMPER" else "A"))

    def test_main_track_is_mainline(self):
        P = panel()
        by = {s["ident"]: s for s in P.segments}
        for bi, (_, band, _) in enumerate(bands()):
            for sid, s in band["strands"].items():
                for seg in P.strand_segments[(bi, sid)]:
                    self.assertEqual(by[seg]["main"], s["main"], sid)
        el = element()
        self.assertEqual(el.get("mainlinetrackwidth"), "4")
        self.assertEqual(el.get("sidetrackwidth"), "2")
        opts = el.find("layoutTrackDrawingOptions")
        self.assertEqual(opts.findtext("mainBlockLineWidth"), "4")
        self.assertEqual(opts.findtext("sideBlockLineWidth"), "2")

    def test_corners_are_arcs_that_meet_their_ends(self):
        P = panel()
        el = element()
        it = items(el)

        def where(name, typ):
            e = it[name]
            if typ == "POS_POINT":
                return (float(e.get("x")), float(e.get("y")))
            leg = typ[-1].lower()
            return (float(e.get(f"x{leg}")), float(e.get(f"y{leg}")))

        arcs = 0
        for s in el.findall("tracksegment"):
            if s.get("arc") != "yes":
                continue
            arcs += 1
            self.assertEqual(s.get("circle"), "yes")
            a, b = where(s.get("connect1name"), s.get("type1")), where(s.get("connect2name"), s.get("type2"))
            pts = le.arc_points(a, b, float(s.get("angle")), s.get("flip") == "yes")
            self.assertLess(math.dist(pts[0], a), 0.2)
            self.assertLess(math.dist(pts[-1], b), 0.2)
        self.assertGreater(arcs, 10)
        # Yard Lead (e2) slopes down from switch 1 and runs level to 11: its corner is one 45 degree arc
        segs = {s["ident"]: s for s in P.segments}
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        corner = [segs[k] for k in P.strand_segments[(lower, "e2")] if segs[k]["arc"]]
        self.assertEqual(len(corner), 1)
        self.assertAlmostEqual(corner[0]["arc"]["angle"], 45.0, places=3)

    def test_turnback_is_a_half_circle_bowing_out(self):
        P = panel()
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        segs = {s["ident"]: s for s in P.segments}
        pair = [segs[k] for k in P.turnbacks[(lower, "turn:e12")]]
        self.assertEqual([s["arc"]["angle"] for s in pair], [90.0, 90.0])
        ends = [P.points[s["ends"][0][0]]["xy"] for s in pair] + [P.points[pair[1]["ends"][1][0]]["xy"]]
        top, apex, bottom = ends
        self.assertAlmostEqual(top[0], bottom[0], places=3)
        self.assertGreater(apex[0], top[0])           # turnR: the loop bows to the right
        r = (bottom[1] - top[1]) / 2
        self.assertAlmostEqual(apex[0] - top[0], r, places=3)
        for s in pair:
            for q in s["arc"]["drawn"]:
                self.assertGreaterEqual(q[0], top[0] - 0.01)
                self.assertAlmostEqual(math.dist(q, (top[0], top[1] + r)), r, places=2)

    def test_jmri_arc_direction(self):
        pts = le.arc_points((0, 0), (0, 100), 180, False)
        self.assertLess(math.dist(pts[0], (0, 0)), 1e-6)
        self.assertLess(math.dist(pts[-1], (0, 100)), 1e-6)
        self.assertAlmostEqual(pts[len(pts) // 2][0], 50.0)     # not flipped: bows right of 1 -> 2 going down
        self.assertAlmostEqual(le.arc_points((0, 0), (0, 100), 180, True)[6][0], -50.0)


class Switches(unittest.TestCase):
    def test_turnout_legs_match_band_legs(self):
        P = panel()
        segs = {s["ident"]: s for s in P.segments}
        turnouts = {t["ident"]: t for t in P.turnouts}
        count = 0
        for bi, (_, band, _) in enumerate(bands()):
            for n, d in band["nodes"].items():
                if d["kind"] not in ("switch", "dx"):
                    continue
                count += 1
                ident, legs = P.turnout_of[(bi, n)]
                t = turnouts[ident]
                self.assertEqual(sorted(legs), sorted(set(d["ins"]) | set(d["outs"])))
                for port, leg in legs.items():
                    seg = t["conn"][leg]
                    sid = strand_at(band, n, port)
                    self.assertIn(seg, P.strand_segments[(bi, sid)], (d.get("label"), port))
                    self.assertIn((ident, f"TURNOUT_{leg}"), segs[seg]["ends"])
                if d["kind"] == "switch":
                    self.assertEqual(legs["A"], "A")
                    self.assertEqual(t["continuing"], "2" if legs["B"] == "B" else "4", d.get("label"))
        self.assertEqual(count, len(P.turnouts))

    def test_drawn_straight_leg_is_layout_editor_leg_b(self):
        P = panel()
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        by = {t["ident"]: t for t in P.turnouts}
        # 13: the drawing slopes B (Y-3) up and runs C (Y-4) level, so the legs swap and closed stays on Y-3
        ident, legs = P.turnout_of[(lower, "L13")]
        self.assertEqual(legs, {"A": "A", "B": "C", "C": "B"})
        self.assertEqual(by[ident]["continuing"], "4")
        # 4: B (the rise) level, C slopes down
        ident, legs = P.turnout_of[(lower, "S4")]
        self.assertEqual(legs, {"A": "A", "B": "B", "C": "C"})
        self.assertEqual(by[ident]["continuing"], "2")
        self.assertEqual(by[ident]["type"], "RH_TURNOUT")          # C drawn below, to the right of A to B

    def test_turnout_geometry_is_what_layout_editor_computes(self):
        for t in panel().turnouts:
            c, p = t["cen"], t["pts"]
            if t["type"] in ("RH_TURNOUT", "LH_TURNOUT"):           # A = centre - (B - centre)
                self.assertLess(math.dist(p["A"], (2 * c[0] - p["B"][0], 2 * c[1] - p["B"][1])), 0.01)
            elif t["type"] == "WYE_TURNOUT":
                m = ((p["B"][0] + p["C"][0]) / 2 - c[0], (p["B"][1] + p["C"][1]) / 2 - c[1])
                self.assertLess(math.dist(p["A"], (c[0] - m[0], c[1] - m[1])), 0.01)
            else:       # JMRI 5.16 keeps a crossover's view at version 1, whatever the XML says (JmriCrossovers)
                self.assertEqual(t["ver"], "1")

    def test_double_crossover(self):
        P = panel()
        dx = [t for t in P.turnouts if t["type"] == "DOUBLE_XOVER"]
        self.assertEqual(len(dx), 1)
        p = dx[0]["pts"]
        self.assertAlmostEqual(p["A"][1], p["B"][1])           # A-B one through track, D-C the other
        self.assertAlmostEqual(p["C"][1], p["D"][1])
        self.assertLess(p["A"][0], p["B"][0])
        self.assertLess(p["A"][1], p["D"][1])
        self.assertEqual(set(dx[0]["blocks"].values()), {"OS 6"})


def crossover_band():
    """Two switches numbered 7, joined C to C: a single crossover between two level tracks."""
    end = lambda s, io: dict(kind="end", sub="bumper", label="", ins={"E": s} if io else {}, outs={} if io else {"E": s})  # noqa: E731
    nodes = {
        "W1": end("s1", False), "W2": end("s3", False), "E1": end("s2", True), "E2": end("s4", True),
        "P": dict(kind="switch", label="7", hand=1, ins={"A": "s1"}, outs={"B": "s2", "C": "x"}),
        "Q": dict(kind="switch", label="7", hand=1, ins={"B": "s3", "C": "x"}, outs={"A": "s4"}),
    }
    st = lambda a, b, name, main: dict(src=a, dst=b, name=name, main=main, hidden=False, link=False, edge="", cm=1.0)  # noqa: E731
    strands = {"s1": st(("W1", "E"), ("P", "A"), "North", True), "s2": st(("P", "B"), ("E1", "E"), "North", True),
               "s3": st(("W2", "E"), ("Q", "B"), "South", False), "s4": st(("Q", "A"), ("E2", "E"), "South", False),
               "x": st(("P", "C"), ("Q", "C"), "", False)}
    drawn = {"s1": [(0, 0), (2, 0)], "s2": [(2, 0), (6, 0)], "x": [(2, 0), (3, 1)], "s3": [(0, 1), (3, 1)],
             "s4": [(3, 1), (6, 1)]}
    return [("Test level", dict(nodes=nodes, strands=strands, _drawn=drawn), {})]


def mirrored(bands_):
    """The crossover band drawn end for end (x negated): its crossover leans the other way."""
    (title, band, opts), = bands_
    band = dict(band, _drawn={k: [(-x, y) for x, y in v] for k, v in band["_drawn"].items()})
    return [(title, band, opts)]


class JmriCrossovers(unittest.TestCase):
    """What JMRI 5.16 draws from the crossovers the panel writes (tests/jmri_xover.py ports its loader): the same four
    points, leaning the way the sheet draws them."""

    def check(self, P, drawn_slant):
        import jmri_xover
        el = le.to_xml(P, "G")
        seen = 0
        for t in el.findall("layoutturnout"):
            if "XOVER" not in t.get("type"):
                continue
            seen += 1
            got = jmri_xover.load(t)
            for leg in "ABCD":
                want = (float(t.get("x" + leg.lower())), float(t.get("y" + leg.lower())))
                self.assertAlmostEqual(got[leg][0], want[0], places=3, msg=(t.get("ident"), leg))
                self.assertAlmostEqual(got[leg][1], want[1], places=3, msg=(t.get("ident"), leg))
            if t.get("type") != "DOUBLE_XOVER":
                self.assertEqual(jmri_xover.slant(got), drawn_slant, t.get("ident"))
                self.assertEqual(t.get("type"), "RH_XOVER" if drawn_slant == "\\" else "LH_XOVER")
        self.assertTrue(seen)

    def test_single_crossovers_load_as_written_and_lean_as_drawn(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            for run in (None, 20.0, 40.0):
                with self.subTest(run=run):
                    self.check(le.panel(crossover_band(), crossover_run=run), "\\")      # 7 at (2,0) and (3,1)
                    self.check(le.panel(mirrored(crossover_band()), crossover_run=run), "/")

    def test_a_crossover_with_no_room_is_two_turnouts_on_its_one_name(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]), \
                mock.patch.object(le.Band, "room_toward", lambda self, n, port: 0.0):
            P = le.panel(crossover_band(), {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 7"}}})
        self.assertEqual(sorted(t["type"] for t in P.turnouts), ["RH_TURNOUT", "RH_TURNOUT"])
        self.assertEqual({t["name"] for t in P.turnouts}, {"Switch 7"})
        self.assertTrue(any("no room for a crossover JMRI can draw" in line and "two turnouts" in line
                            for line in P.log))

    def test_a_double_crossover_loads_as_written(self):
        self.check(panel(), None)

    def test_every_crossover_is_drawn_at_the_run_asked(self):
        """The diagonals JMRI draws (jmri_xover.diagonals, a port of draw1), not the corners, are at the angle the
        run gives: a double crossover drawn with A-B twice the run had diagonals at 69 degrees for 45 asked."""
        import jmri_xover
        dy = None
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            single = le.panel(crossover_band(), crossover_run=24.0)
        for P in (le.panel(bands(), crossover_run=24.0), single):
            for t in le.to_xml(P, "G").findall("layoutturnout"):
                if "XOVER" not in t.get("type"):
                    continue
                pts = jmri_xover.load(t)
                ys = sorted({p[1] for p in pts.values()})
                dy = ys[-1] - ys[0]
                want = math.degrees(math.atan2(dy, 24.0))
                for seg in jmri_xover.diagonals(t.get("type"), pts, (float(t.get("xcen")), float(t.get("ycen")))):
                    with self.subTest(turnout=t.get("ident"), type=t.get("type")):
                        self.assertAlmostEqual(jmri_xover.angle(seg), want, delta=0.8)
        self.assertIsNotNone(dy)
        # the 2026-11-16 candidate's 225: A-B twice the 48 px run asked for 45 degrees, drawn at 69
        old = {"A": (-24.0, 0.0), "B": (24.0, 0.0), "C": (24.0, 48.0), "D": (-24.0, 48.0)}
        self.assertAlmostEqual(jmri_xover.angle(jmri_xover.diagonals("DOUBLE_XOVER", old, (0.0, 24.0))[0]), 69.4,
                               delta=0.1)

    def test_the_old_shape_is_what_jmri_mirrored(self):
        import jmri_xover
        import xml.etree.ElementTree as ET
        # the 2026-11-16 candidate's Switch 23: legs 18 px either side, ver 2; JMRI draws it leaning the other way
        el = ET.fromstring('<layoutturnout type="RH_XOVER" xcen="1412.5" ycen="210.0" xa="1370.5" ya="186.0" '
                           'xb="1406.5" yb="186.0" xc="1454.5" yc="234.0" xd="1418.5" yd="234.0" ver="2"/>')
        self.assertEqual(jmri_xover.slant(jmri_xover.load(el)), "/")
        self.assertNotAlmostEqual(jmri_xover.load(el)["A"][0], 1370.5)


def three_way_band():
    """Two single crossovers sharing the middle track: 7 (top half P on it) down to the bottom track, 8 (bottom half
    S on it) up to the top track, like the two crossovers of one three-way switch."""
    end = lambda s, io: dict(kind="end", sub="bumper", label="", ins={"E": s} if io else {}, outs={} if io else {"E": s})  # noqa: E731
    nodes = {
        "W0": end("a0", False), "E0": end("b0", True), "W1": end("a1", False), "E1": end("c1", True),
        "W2": end("a2", False), "E2": end("b2", True),
        "R": dict(kind="switch", label="8", hand=-1, ins={"A": "a0"}, outs={"B": "b0", "C": "y"}),
        "S": dict(kind="switch", label="8", hand=-1, ins={"B": "mid", "C": "y"}, outs={"A": "c1"}),
        "P": dict(kind="switch", label="7", hand=1, ins={"A": "a1"}, outs={"B": "mid", "C": "x"}),
        "Q": dict(kind="switch", label="7", hand=1, ins={"B": "a2", "C": "x"}, outs={"A": "b2"}),
    }
    st = lambda a, b, name: dict(src=a, dst=b, name=name, main=False, hidden=False, link=False, edge="", cm=1.0)  # noqa: E731
    strands = {"a0": st(("W0", "E"), ("R", "A"), "Top"), "b0": st(("R", "B"), ("E0", "E"), "Top"),
               "y": st(("R", "C"), ("S", "C"), ""), "a1": st(("W1", "E"), ("P", "A"), "Middle"),
               "mid": st(("P", "B"), ("S", "B"), "Shared"), "c1": st(("S", "A"), ("E1", "E"), "Middle"),
               "x": st(("P", "C"), ("Q", "C"), ""), "a2": st(("W2", "E"), ("Q", "B"), "Bottom"),
               "b2": st(("Q", "A"), ("E2", "E"), "Bottom")}
    drawn = {"a0": [(0, 0), (5, 0)], "b0": [(5, 0), (10, 0)], "y": [(5, 0), (4, 1)], "a1": [(0, 1), (2, 1)],
             "mid": [(2, 1), (4, 1)], "c1": [(4, 1), (10, 1)], "x": [(2, 1), (3, 2)], "a2": [(0, 2), (3, 2)],
             "b2": [(3, 2), (10, 2)]}
    return [("Test level", dict(nodes=nodes, strands=strands, _drawn=drawn), {})]


class TightCrossovers(unittest.TestCase):
    """tight_crossovers: two crossovers on one shared track drawn as close as their shapes allow."""

    def draw(self, **kw):
        names = {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 7", "R": "Switch 8", "S": "Switch 8"}}}
        (t, b, o), = three_way_band()
        bands_ = [(t, b, dict(o, le_labels={"block_contents": False}))]       # the small band has no room for them
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            return le.panel(bands_, names, crossover_run=48.0, **kw)

    def gap(self, P):
        t = {x["name"]: x for x in P.turnouts}
        seven, eight = t["Switch 7"], t["Switch 8"]
        self.assertEqual((seven["type"], eight["type"]), ("RH_XOVER", "LH_XOVER"))
        for x in (seven, eight):        # both at the run asked: pieces twice the run, diagonals 48 across
            self.assertAlmostEqual(x["pts"]["B"][0] - x["pts"]["A"][0], 96.0)
        self.assertEqual(seven["pts"]["B"][1], eight["pts"]["D"][1])      # on the one shared track
        return eight["pts"]["D"][0] - seven["pts"]["B"][0]

    def test_the_shared_track_keeps_only_its_least_length(self):
        P = self.draw(tight_crossovers={"Test": [["7", "8"]]})
        self.assertFalse([line for line in P.log if "no room for" in line])
        self.assertGreaterEqual(self.gap(P), le.MIN_BLOCK)
        self.assertLessEqual(self.gap(P), le.MIN_BLOCK + 1)              # whole-pixel points
        import jmri_xover
        for t in le.to_xml(P, "G").findall("layoutturnout"):           # JMRI holds them as written
            got = jmri_xover.load(t)
            for leg in "ABCD":
                self.assertAlmostEqual(got[leg][0], float(t.get("x" + leg.lower())), places=3)
        # as usual the shared track is split half and half, and neither has room for its run
        self.assertTrue([line for line in self.draw().log if "no room for 48.0 px" in line])

    def test_split_crossovers_bring_the_throats_together(self):
        P = self.draw(tight_crossovers={"Test": [["7", "8"]]}, split_crossovers={"Test": ["7", "8"]})
        by = defaultdict(list)
        for t in P.turnouts:
            by[t["name"]].append(t)
        self.assertEqual({k: len(v) for k, v in by.items()}, {"Switch 7": 2, "Switch 8": 2})
        self.assertTrue(all(t["type"].endswith("H_TURNOUT") for t in P.turnouts))     # plain turnouts
        self.assertEqual(P.split_names, {"Switch 7", "Switch 8"})
        row = min(t["at"][1] for t in by["Switch 7"])                     # the shared track
        throats = sorted(t["at"][0] for v in by.values() for t in v if abs(t["at"][1] - row) < 1e-6)
        self.assertEqual(len(throats), 2)
        self.assertAlmostEqual(throats[1] - throats[0], 2 * le.LEG + le.MIN_BLOCK)
        for v in by.values():           # each diagonal runs the run asked across
            self.assertAlmostEqual(abs(v[0]["at"][0] - v[1]["at"][0]), 48.0)
        numbers = [lb["text"] for lb in P.labels if lb.get("kind") == "switch"]
        self.assertEqual(sorted(numbers), ["7", "8"])                    # one number each
        with self.assertRaisesRegex(SchematicError, "both or neither"):
            self.draw(tight_crossovers={"Test": [["7", "8"]]}, split_crossovers={"Test": ["7"]})
        with self.assertRaisesRegex(SchematicError, "switch 9 is no single crossover"):
            self.draw(split_crossovers={"Test": ["9"]})

    def test_bad_tight_crossovers_stop(self):
        for bad, why in (({"Test": [["7", "9"]]}, "switch 9 is no single crossover"),
                         ({"Other": [["7", "8"]]}, "Other, which is no band"),
                         ({"Test": [["7"]]}, "is not two switch numbers"),
                         ([["7", "8"]], "must be")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, why):
                self.draw(tight_crossovers=bad)
        with self.assertRaisesRegex(SchematicError, "needs crossover_run"):
            le.panel(three_way_band(), tight_crossovers={"Test": [["7", "8"]]})


class BandRoundsReview(unittest.TestCase):
    """The 0.1.25 review fixes: rooms, rounding, split crossovers, double crossovers and lamp columns."""

    def three_way(self, **kw):
        names = {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 7", "R": "Switch 8", "S": "Switch 8"}}}
        (t, b, o), = three_way_band()
        bands_ = [(t, b, dict(o, le_labels={"block_contents": False}))]
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            return le.panel(bands_, names, **kw)

    def test_a_tight_partner_drawn_as_turnouts_bounds_the_room(self):
        real = le.Band.crossover_points

        def no_room_for_8(self, label, *a, **k):
            if label == "8":
                raise le.NoRoom(f"{self.title}: switch 8: no room for a crossover JMRI can draw")
            return real(self, label, *a, **k)
        with mock.patch.object(le.Band, "crossover_points", no_room_for_8):
            P = self.three_way(crossover_run=70.0, tight_crossovers={"Test": [["7", "8"]]})     # more than fits
        seven = next(t for t in P.turnouts if t["name"] == "Switch 7")
        eights = [t for t in P.turnouts if t["name"] == "Switch 8"]
        self.assertEqual(len(eights), 2)                    # drawn as two turnouts
        row = seven["pts"]["B"][1]
        shared = next(t for t in eights if abs(t["at"][1] - row) < 1e-6)
        legs = [p[0] for p in shared["pts"].values() if abs(p[1] - row) < 1e-6]
        self.assertGreaterEqual(min(legs) - seven["pts"]["B"][0], le.MIN_BLOCK - 0.5)

    def test_a_split_half_slid_past_its_track_stops(self):
        with self.assertRaisesRegex(SchematicError, "switch 7: drawn as two turnouts, its track toward leg .* "
                                                    "\\(it slid past that track's far end\\)"):
            self.three_way(crossover_run=400.0, split_crossovers={"Test": ["7"]})

    def test_split_crossovers_go_through_the_fit(self):
        P = self.three_way(split_crossovers={"Test": ["7"]}, fit=(1300, 700))
        self.assertIn("Switch 7", P.split_names)
        self.assertEqual(sum(t["name"] == "Switch 7" for t in P.turnouts), 2)

    def test_a_double_crossover_takes_the_run_asked_or_logs_why_not(self):
        def dx(P):
            t = next(t for t in P.turnouts if t["type"] == "DOUBLE_XOVER")
            return t["pts"]["B"][0] - t["pts"]["A"][0]
        default = dx(panel())
        small = le.panel(bands(), crossover_run=6.0)
        self.assertEqual(dx(small), 2 * round(4 * 6.0 / 3))      # below its default: honoured
        self.assertLess(dx(small), default)
        big = le.panel(bands(), crossover_run=200.0)
        self.assertTrue(any("double crossover" in line and "no room for 200.0 px" in line for line in big.log))
        t = next(t for t in big.turnouts if t["type"] == "DOUBLE_XOVER")
        self.assertLess(dx(big), 2 * 4 * 200.0 / 3)

    def test_rounding_past_the_room_is_logged_or_stops(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            with mock.patch.object(le.Band, "over_room", lambda self, n, x, h: 0.3):
                P = le.panel(crossover_band(), crossover_run=24.0)
            self.assertTrue(any("rounded to whole pixels, its crossover reaches 0.30 px past" in line
                                for line in P.log))
            with mock.patch.object(le.Band, "over_room", lambda self, n, x, h: 2.0), \
                    self.assertRaisesRegex(SchematicError, "switch 7: rounded to whole pixels, .* 2.00 px past"):
                le.panel(crossover_band(), crossover_run=24.0)

    def test_a_lamp_column_with_no_level_piece_stops(self):
        from types import SimpleNamespace
        from schematic import le_labels
        L = SimpleNamespace(pieces={("seg", "T1"): [((0, 0), (40, 40))]}, bands=[("Test level", None, {})])
        with self.assertRaisesRegex(SchematicError, "Test level: lamp_columns: track Siding has no level piece"):
            le_labels.lamp_boxes(L, [{"lamp_size": (8, 8)}], [(0, "s", "Siding", ["T1"])], {(0, "Siding"): 20})


class Crossover(unittest.TestCase):
    def test_two_switches_of_one_number_are_one_single_crossover(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            P = le.panel(crossover_band(), {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 7"},
                                                     "os": {"P": "OS 7a", "Q": "OS 7b"}}})
        self.assertEqual(len(P.turnouts), 1)
        t = P.turnouts[0]
        self.assertEqual(t["type"], "RH_XOVER")           # the joining track slopes down to the right
        self.assertEqual(t["name"], "Switch 7")
        self.assertEqual(t["blocks"], {"A": "OS 7a", "B": "OS 7a", "C": "OS 7b", "D": "OS 7b"})
        self.assertEqual(P.turnout_of[(0, "P")][1], {"A": "A", "B": "B"})
        self.assertEqual(P.turnout_of[(0, "Q")][1], {"B": "D", "A": "C"})
        self.assertFalse(P.strand_segments[(0, "x")])      # the joining track is inside the crossover
        mid_ab = ((t["pts"]["A"][0] + t["pts"]["B"][0]) / 2, t["pts"]["A"][1])
        west = min(p["xy"][0] for p in P.points.values())
        self.assertAlmostEqual(mid_ab[0] - west, 2 * le.CELL)     # the diagonal leaves where switch P stands

    def test_two_names_for_one_crossover_stop(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            with self.assertRaises(SchematicError):
                le.panel(crossover_band(), {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 8"}}})


class BandPlaces(unittest.TestCase):
    def test_band_align_puts_a_band_against_an_edge_of_the_widest(self):
        page = dict(bands()[-1][2])
        base = panel()
        widths = [le.extent(base, bi)[2] - le.extent(base, bi)[0] for bi in range(len(bands()))]
        narrow = widths.index(min(widths))
        key = bands()[narrow][0].split()[0]
        x = lambda P: min(t["cen"][0] for t in P.turnouts if t["band"] == narrow)     # noqa: E731
        moved = {side: x(le.panel(bands(), page=dict(page, band_align={key: side}))) - x(base)
                 for side in ("left", "centre", "right")}
        self.assertEqual(moved["centre"], 0)
        self.assertLess(moved["left"], 0)                       # the narrower band to the left edge ...
        self.assertAlmostEqual(moved["right"], -moved["left"])  # ... or as far to the right
        other = 1 - narrow
        self.assertEqual([t["cen"] for t in le.panel(bands(), page=dict(page, band_align={key: "left"})).turnouts
                          if t["band"] == other], [t["cen"] for t in base.turnouts if t["band"] == other])
        for bad, shown in (({"Nowhere": "left"}, "Nowhere \\(no band"), ({key: "middle"}, "'middle'"),
                           (["left"], "not \\['left'\\]")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "band_align.*" + shown):
                le.panel(bands(), page=dict(page, band_align=bad))

    def test_band_align_may_name_a_band_the_page_knows_but_not_drawn(self):
        page = dict(bands()[-1][2])                         # band_order: Upper, Lower
        lower = [b for b in bands() if b[0].startswith("Lower")]
        P = le.panel(lower, page=dict(page, band_align={"Upper": "right"}))      # `schematic le --band Lower`
        self.assertTrue(P.turnouts)
        with self.assertRaisesRegex(SchematicError, "Nowhere"):
            le.panel(lower, page=dict(page, band_align={"Nowhere": "right"}))

    def test_gap_is_checked_on_every_path(self):
        for gap in (-1, "9", True, float("nan")):
            for draw in (lambda g: le.panel(bands(), gap=g), lambda g: le.panel(bands(), gap=g, fit=(1300, 700)),
                         lambda g: le.draw_panel(bands(), None, le.CELL, le.ROW, None, gap=g)):
                with self.subTest(gap=gap), self.assertRaisesRegex(SchematicError, "gap between bands"):
                    draw(gap)

    def test_a_gap_per_pair_of_bands(self):
        base = panel()
        P = le.panel(bands(), gap=[le.BAND_GAP + 30])          # two bands: one gap
        self.assertAlmostEqual(le.extent(P, 1)[1], le.extent(base, 1)[1] + 30)
        (_a, _b, _c, low), (_d, top, _e, _f) = P.band_boxes      # the boxes the bands were placed by, that far apart
        self.assertAlmostEqual(top - low, le.BAND_GAP + 30)
        for bad in ([], [1, 2], [-1], ["9"], (True,)):
            with self.subTest(gap=bad), self.assertRaisesRegex(SchematicError, "gaps between bands must be 1"):
                le.panel(bands(), gap=bad)

    def test_gap_moves_the_bands_below_down(self):
        base, wide = panel(), le.panel(bands(), gap=le.BAND_GAP + 50)
        self.assertAlmostEqual(le.extent(wide, 0)[1], le.extent(base, 0)[1])
        self.assertAlmostEqual(le.extent(wide, 1)[1], le.extent(base, 1)[1] + 50)
        for bad in (-1, "96", True, float("nan")):
            with self.subTest(gap=bad), self.assertRaisesRegex(SchematicError, "gap between bands"):
                le.panel(bands(), gap=bad)

    def test_a_joined_end_is_numbered_among_the_ends(self):
        P = panel()
        joined = {i for (_b, i) in P.join_ends}
        self.assertTrue(joined)
        self.assertTrue(all(re.fullmatch(r"AGE\d+", i) for i in joined), joined)
        self.assertEqual(le.jmri_kind(next(iter(joined))), "point")
        self.assertTrue(le.GENERATED.fullmatch("AGE3"))
        ends = sorted(int(re.sub(r"\D", "", k)) for k, p in P.points.items()
                      if p["type"] == "END_BUMPER" or k in joined)
        self.assertEqual(ends, list(range(1, len(ends) + 1)))        # one count for bumpers and joined ends


class Names(unittest.TestCase):
    NAMES = {"Lower": {"turnouts": {"S1": "Turnout One"}, "os": {"S1": "OS One"}, "normal": {"S4": "C"},
                       "blocks": {"e1": ["Main West 1", "Main West 2"]}}}

    def test_names_reach_the_panel(self):
        P = panel(self.NAMES)
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        by = {t["ident"]: t for t in P.turnouts}
        t = by[P.turnout_of[(lower, "S1")][0]]
        self.assertEqual(t["name"], "Turnout One")
        self.assertEqual(t["blocks"]["A"], "OS One")
        self.assertEqual(by[P.turnout_of[(lower, "S4")][0]]["continuing"], "4")      # normal on leg C
        segs = {s["ident"]: s for s in P.segments}
        blocks = [segs[k]["block"] for k in P.strand_segments[(lower, "e1")]]
        self.assertEqual(blocks[0], "Main West 1")                  # from switch 1 (src) to switch 2
        self.assertEqual(blocks[-1], "Main West 2")
        self.assertEqual(blocks, sorted(blocks))
        el = element(P)
        self.assertIn("Turnout One", {x.get("turnoutname") for x in el.findall("layoutturnout")})

    def test_default_names(self):
        P = panel()
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        segs = {s["ident"]: s for s in P.segments}
        block = lambda bi, sid: {segs[k]["block"] for k in P.strand_segments[(bi, sid)]}      # noqa: E731
        self.assertEqual(block(lower, "e1"), {"Main West"})
        self.assertEqual(block(lower, "e3"), {"Main"})
        self.assertEqual(block(lower, "e7"), {"Main 2"})             # Main on both sides of the crossover: unique
        self.assertEqual(block(lower, "e12.1"), {"Loop"})            # a turnback shares its track's block
        upper = 1 - lower
        self.assertEqual(block(upper, "e10y"), block(lower, "e10x"))  # one track across connector A
        self.assertFalse(any(t["name"] for t in P.turnouts))

    def test_names_for_a_band_that_is_not_there_stop(self):
        with self.assertRaises(SchematicError):
            le.panel(bands(), {"Nowhere": {}})

    def test_bad_normal_leg_stops(self):
        with self.assertRaises(SchematicError):
            le.panel(bands(), {"Lower": {"normal": {"S4": "D"}}})


class Idents(unittest.TestCase):
    """`idents` gives drawn objects an older panel's names; `leg_b` keeps a turnout's leg letters."""
    BASE = {"blocks": {"e1": ["Main West 1", "Main West 2"], "e13": ["Y-1"], "e15": ["Y-2"], "e2": ["Yard Lead"]}}

    def lower(self):
        return next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))

    def names(self, **idents):
        return {"Lower": {**self.BASE, "idents": idents}}

    def test_given_idents_reach_the_panel_and_its_xml(self):
        base = panel(self.names())
        drawn = defaultdict(list)
        for sg in base.segments:
            if sg["band"] == self.lower():
                drawn[sg["block"]].append(sg["ident"])
        self.assertEqual(len(drawn["Y-1"]), 1)              # Y-1 is one straight segment: its ident is used
        self.assertEqual(len(drawn["Yard Lead"]), 3)        # Yard Lead is three (line, arc, line): logged, not used
        P = panel(self.names(turnouts={"S1": "TO100"}, boundaries=[{"blocks": ["Main West 2", "Main West 1"],
                                                                     "ident": "F3-A-1"}],
                             ends={"Y-1": "EB100"}, segments={"Y-1": "T-Y1", "Yard Lead": "F2-S-7"}))
        lower = self.lower()
        self.assertEqual(P.name(P.turnout_of[(lower, "S1")][0]), "TO100")
        self.assertTrue(le.GENERATED.fullmatch(P.turnout_of[(lower, "S1")][0]))   # the Panel keeps generated idents
        by = items(element(P))
        self.assertEqual(by["F3-A-1"].get("type"), "ANCHOR")
        self.assertEqual(by["EB100"].get("type"), "END_BUMPER")
        self.assertEqual({by[by["F3-A-1"].get(f"connect{i}name")].get("blockname") for i in (1, 2)},
                         {"Main West 1", "Main West 2"})
        self.assertEqual(by["T-Y1"].get("blockname"), "Y-1")
        self.assertNotIn("F2-S-7", by)
        self.assertIn("Lower level: idents: block Yard Lead is drawn as 3 track segments, so segment ident F2-S-7 is not used (they keep "
                      "generated idents)", P.log)
        self.assertEqual(set(P.idents_given.values()), {"TO100", "F3-A-1", "EB100", "T-Y1"})
        el = element(P)
        names = {c.get("ident") for c in el if c.get("ident")}
        self.assertTrue({"TO100", "F3-A-1", "EB100", "T-Y1"} <= names)
        for c in el:                                    # every connection names an object of the panel
            for attr in ("connect1name", "connect2name", "connectaname", "connectbname", "connectcname"):
                if c.get(attr):
                    self.assertIn(c.get(attr), names, (c.get("ident"), attr))

    def test_jmri_kind_follows_find_object_by_name(self):
        for name, kind in (("TO1", "turnout"), ("TOL3", "turnout"), ("A12", "point"), ("EB7", "point"),
                           ("EC2", "point"), ("F3-A-1", "point"), ("X1", "xing"), ("SL1", "slip"),
                           ("TUR1", "turntable"), ("TRV1", "traverser"), ("T5", "segment"), ("T-EL-TOL3", "segment"),
                           ("F30-S-0", "segment"), ("Q-EB", "point"), ("T5-EB", "segment"), ("Y1", None),
                           ("F3-B-1", None)):
            with self.subTest(name=name):
                self.assertEqual(le.jmri_kind(name), kind)

    def test_bad_idents_stop_before_drawing(self):
        bad = [dict(turnouts={"S1": "X1"}),                                  # JMRI reads a level crossing
               dict(turnouts={"S1": "TOG1"}),                                # the generated form
               dict(turnouts={"S1": "TO100"}, ends={"Y-1": "TO100"}),        # a turnout's name for an end
               dict(turnouts={"S1": "TO100", "S2": "TO100"}),                # two switches, no crossover
               dict(segments={"Y-1": "TO5"}), dict(segments={"Y-1": "A77"}), dict(segments={"Y-1": "EB77"}),
               dict(segments={"Y-1": "SL1"}), dict(segments={"Y-1": "Y1"}),   # not found as a segment
               dict(boundaries=[{"blocks": ["Y-1", "Y-1"], "ident": "A1"}]),
               dict(boundaries=[{"blocks": ["Y-1", "Nowhere"], "ident": "A1"}]),     # a block not named
               dict(boundaries=[{"blocks": ["Y-1", "Y-2"], "ident": "T1"}]),         # not a point's name
               dict(ends={"Nowhere": "EB1"}), dict(ends={"Y-1": "T9"}),
               dict(turnouts={"NOPE": "TO1"}),
               dict(nope={})]
        with mock.patch.object(le, "Band", side_effect=AssertionError("drawn")) as band:
            for idents in bad:
                with self.subTest(idents=idents), self.assertRaises(SchematicError):
                    le.panel(bands(), self.names(**idents))
        band.assert_not_called()

    def test_what_only_the_drawing_shows_stops_after_drawing(self):
        for idents in (dict(boundaries=[{"blocks": ["Y-1", "Y-2"], "ident": "A1"}]),   # not drawn as one anchor
                       dict(ends={"Main West 1": "EB1"})):                            # ends at no bumper
            with self.subTest(idents=idents), self.assertRaisesRegex(SchematicError, "exactly one|an end ident"):
                le.panel(bands(), self.names(**idents))

    def test_a_crossover_shares_one_ident(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            P = le.panel(crossover_band(), {"Test": {"idents": {"turnouts": {"P": "TO117", "Q": "TO117"}}}})
            self.assertEqual([P.name(t["ident"]) for t in P.turnouts], ["TO117"])
            with self.assertRaisesRegex(SchematicError, "already named"):      # one turnout, two idents
                le.panel(crossover_band(), {"Test": {"idents": {"turnouts": {"P": "TO1", "Q": "TO2"}}}})
            with self.assertRaisesRegex(SchematicError, "half of a single crossover"):
                le.panel(crossover_band(), {"Test": {"leg_b": {"P": "C"}}})

    def test_every_written_ident_resolves_through_the_one_mapping(self):
        P = panel(self.names(turnouts={"S1": "TO100"}))
        el = element(P)
        written = [c.get("ident") for c in el if c.get("ident")]
        self.assertEqual(len(written), len(set(written)))
        self.assertIn("TO100", written)
        self.assertNotIn(next(k for k, v in P.idents_given.items() if v == "TO100"), written)
        for bad, why in ((lambda Q: {"TG999999": "T-NONE"}, "given to nothing drawn: T-NONE"),    # an alias of nothing
                         (lambda Q: {Q.segments[0]["ident"]: "TO100"},                          # two objects, one
                          r"TO100 would name 2 objects \(turnout, track segment\)")):           # ident
            Q = le.panel(bands(), self.names(turnouts={"S1": "TO100"}))          # its own, not the cached panel
            Q.idents_given.update(bad(Q))
            with self.subTest(why=why), self.assertRaisesRegex(SchematicError, why):
                le.to_xml(Q, "Generated")

    def generated_in(self, P, text):
        """The generated idents that have a given one and still appear in text, as whole idents."""
        return [g for g in P.idents_given if re.search(rf"(?<![A-Za-z0-9_-]){re.escape(g)}(?![A-Za-z0-9_-])", text)]

    def test_errors_name_objects_by_their_written_idents(self):
        names = self.names(turnouts={"S1": "TO100"},
                           boundaries=[{"blocks": ["Main West 2", "Main West 1"], "ident": "F3-A-1"}])
        names["Lower"]["masts"] = [{"mast": "M", "facing": "Y-1"}]
        P = le.panel(bands(), names)
        anchor = next(k for k, v in P.idents_given.items() if v == "F3-A-1")
        turnout = next(k for k, v in P.idents_given.items() if v == "TO100")

        def slot_error(P_, bands_, ix):             # a placing error that names the anchor, as le_masts.verify does
            raise SchematicError(f"anchor {anchor}: slid past the end of its track (turnout {turnout} beside it)")
        with mock.patch("schematic.le_masts.place", slot_error), \
                self.assertRaises(SchematicError) as got:
            le.panel(bands(), names)
        self.assertIn("anchor F3-A-1: slid past", str(got.exception))
        self.assertIn("turnout TO100 beside", str(got.exception))
        self.assertFalse(self.generated_in(P, str(got.exception)))
        Q = le.panel(bands(), names)                # a connection error while writing: a turnout leg to nothing
        t = next(t for t in Q.turnouts if t["ident"] == turnout)
        leg = sorted(t["conn"])[0]
        t["conn"][leg] = "TGNONE"
        with self.assertRaises(SchematicError) as got:
            le.to_xml(Q, "Generated")
        self.assertIn(f"turnout TO100 leg {leg}: TGNONE", str(got.exception))
        self.assertFalse(self.generated_in(Q, str(got.exception)))
        self.assertFalse([line for line in Q.log if self.generated_in(Q, line)])

    def test_a_joins_hidden_segment_does_not_count_against_its_block(self):
        upper = 1 - self.lower()
        names = {"Upper": {"blocks": {"e10y": ["Rise"]}, "idents": {"segments": {"Rise": "T-RISE"}}},
                 "Lower": {"blocks": {"e10x": ["Rise"]}}}
        P = panel(names)
        mine = [sg for sg in P.segments if sg["block"] == "Rise" and sg["band"] == upper]
        self.assertTrue(any(sg["hidden"] for sg in P.segments if sg["block"] == "Rise"))   # the join carries it
        self.assertEqual([P.name(sg["ident"]) for sg in mine], ["T-RISE"])    # its one drawn segment, not the join

    def test_leg_b_keeps_the_letters_and_layout_editors_point_a(self):
        P = panel({"Lower": {"leg_b": {"S4": "C"}}})
        plain = panel()
        lower = self.lower()
        ident, legs = P.turnout_of[(lower, "S4")]
        t = next(t for t in P.turnouts if t["ident"] == ident)
        t0 = next(t for t in plain.turnouts if t["ident"] == plain.turnout_of[(lower, "S4")][0])
        self.assertEqual(legs, {"A": "A", "B": "C", "C": "B"})            # the drawn diverging leg is leg B
        self.assertEqual(t["continuing"], "4")                              # normal stays on the band's leg B
        c, p = t["cen"], t["pts"]
        self.assertLess(math.dist(p["A"], (2 * c[0] - p["B"][0], 2 * c[1] - p["B"][1])), 0.01)
        for leg in "ABC":                                                   # every leg still ends where it did
            other = {"A": "A", "B": "C", "C": "B"}[leg]
            self.assertLess(math.dist(p[leg], t0["pts"][other]), 0.01)
        self.assertGreater(math.dist(t["cen"], t0["cen"]), 1)              # the centre moved...
        self.assertEqual(t["at"], t0["cen"])                                # ...not where the legs meet
        box = le_labels.box_of(*next(lb for lb in P.labels if lb["text"] == "4")["box"])   # its number goes by
        gaps = sorted((le_labels.point_gap(box, o["at"]), o["ident"]) for o in P.turnouts)  # where the legs meet
        self.assertEqual(gaps[0][1], ident, gaps[:2])
        self.assertTrue(any(lb["text"] == "4" for lb in plain.labels))
        self.assertTrue(any("leg_b" in line for line in P.log))
        for bad in ({"S4": "D"}, {"DX": "B"}, {"nope": "B"}):
            with self.subTest(bad=bad), self.assertRaises(SchematicError):
                le.panel(bands(), {"Lower": {"leg_b": bad}})


class Ends(unittest.TestCase):
    def test_connector_and_helix_are_joined_hidden(self):
        P = panel()
        self.assertEqual(len(P.joins), 2)                 # connector A and the helix track Summit
        by = {s["ident"]: s for s in P.segments}
        for j in P.joins:
            self.assertTrue(by[j]["hidden"])
            for name, typ in by[j]["ends"]:
                self.assertEqual(P.points[name]["type"], "ANCHOR")
        bumpers = sum(1 for p in P.points.values() if p["type"] == "END_BUMPER")
        ends = sum(1 for _, b, _ in bands() for d in b["nodes"].values() if d["kind"] == "end")
        self.assertEqual(bumpers, ends - 4)
        self.assertEqual(len(P.shapes), 4)                # two helix circles and two connector circles
        texts = {lb["text"] for lb in P.labels}
        self.assertIn("A", texts)
        self.assertIn("HELIX TO THE OTHER LEVEL", texts)
        self.assertIn("UPPER LEVEL", texts)

    def test_bands_stack_top_to_bottom(self):
        P = panel()
        ys = defaultdict(list)
        for (bi, sid), segs in P.strand_segments.items():
            for k in segs:
                for name, typ in next(s for s in P.segments if s["ident"] == k)["ends"]:
                    if name in P.points:
                        ys[bi].append(P.points[name]["xy"][1])
        self.assertLess(max(ys[0]), min(ys[1]))


class Xml(unittest.TestCase):
    def test_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.xml", Path(tmp) / "b.xml"
            le.write(panel(), a, "Generated")
            le.write(le.panel(bands()), b, "Generated")
            self.assertEqual(a.read_text(), b.read_text())
            root = ET.parse(a).getroot()
        self.assertEqual(root.tag, "LayoutEditor")
        self.assertEqual(root.get("name"), "Generated")
        self.assertEqual(root.find("layoutTrackDrawingOptions").get("name"), "Generated")
        shape = root.find("layoutShape")
        self.assertEqual(len(shape.findall("points/point")), 8)

    def test_cli(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(helpers.graph()))
            out = Path(tmp) / "le.xml"
            run = subprocess.run([sys.executable, "-m", "schematic", "le", str(out), "--data", str(f),
                                  f"{graph}:example", "--panel", "Example", "--band", "Lower"],
                                 capture_output=True, text=True, cwd=helpers.PLUGIN, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("Lower level", run.stdout)
            self.assertNotIn("Upper level", run.stdout)
            self.assertEqual(ET.parse(out).getroot().get("name"), "Example")

def turnback_band():
    """Two tracks into one turnback, their ends a column apart: the shorter is run on before the loop."""
    nodes = {"E1": dict(kind="end", sub="bumper", label="", ins={}, outs={"E": "a"}),
             "E2": dict(kind="end", sub="bumper", label="", ins={}, outs={"E": "b"}),
             "T": dict(kind="turnR", label="", ins={0: "a", 1: "b"}, outs={})}
    st = lambda a, b: dict(src=a, dst=b, name="Loop", main=True, hidden=False, link=False, edge="", cm=1.0)  # noqa: E731
    strands = {"a": st(("E1", "E"), ("T", 0)), "b": st(("E2", "E"), ("T", 1))}
    drawn = {"a": [(0, 0), (4, 0)], "b": [(0, 2), (3, 2)], "T": [(4, 0), (4.5, 0.5), (4.5, 1.5), (4, 2)]}
    return [("Test level", dict(nodes=nodes, strands=strands, _drawn=drawn), {})]


def wye_band():
    """A switch whose legs B and C leave straight up and straight down: no Layout Editor turnout has that shape."""
    end = lambda s, io: dict(kind="end", sub="bumper", label="", ins={"E": s} if io else {}, outs={} if io else {"E": s})  # noqa: E731
    nodes = {"W": end("a", False), "N": end("b", True), "S": end("c", True),
             "X": dict(kind="switch", label="9", hand=1, ins={"A": "a"}, outs={"B": "b", "C": "c"})}
    st = lambda a, b: dict(src=a, dst=b, name="", main=False, hidden=False, link=False, edge="", cm=1.0)  # noqa: E731
    strands = {"a": st(("W", "E"), ("X", "A")), "b": st(("X", "B"), ("N", "E")), "c": st(("X", "C"), ("S", "E"))}
    drawn = {"a": [(0, 1), (2, 1)], "b": [(2, 1), (2, 0), (4, 0)], "c": [(2, 1), (2, 2), (4, 2)]}
    return [("Test level", dict(nodes=nodes, strands=strands, _drawn=drawn), {})]


class ReviewFixes(unittest.TestCase):
    def test_turnback_with_ends_at_two_columns_stays_tangent(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            P = le.panel(turnback_band())
        segs = {s["ident"]: s for s in P.segments}
        loop = [segs[k] for k in P.turnbacks[(0, "T")]]
        self.assertEqual([bool(s["arc"]) for s in loop], [True, False, True])     # arc, run-on straight, arc
        arcs = [s for s in loop if s["arc"]]
        starts = [P.points[arcs[0]["ends"][0][0]]["xy"], P.points[arcs[1]["ends"][1][0]]["xy"]]
        self.assertAlmostEqual(starts[0][0], starts[1][0])          # both quarter arcs start at one column
        apex = P.points[arcs[0]["ends"][1][0]]["xy"]
        r = (starts[1][1] - starts[0][1]) / 2
        self.assertAlmostEqual(apex[0] - starts[0][0], r)
        for s in arcs:                                              # every point on the circle about the centre
            for q in s["arc"]["drawn"]:
                self.assertAlmostEqual(math.dist(q, (starts[0][0], starts[0][1] + r)), r, places=2)

    def test_everything_lies_inside_the_margin(self):
        for P in (panel(), panel(Names.NAMES)):
            box = le.extent(P)
            self.assertGreaterEqual(box[0], le.MARGIN - 0.01)
            self.assertGreaterEqual(box[1], le.MARGIN - 0.01)
            self.assertLessEqual(box[2], P.size[0])
            self.assertLessEqual(box[3], P.size[1])

    def test_one_turnout_name_on_two_switches_stops(self):
        with self.assertRaisesRegex(SchematicError, "given to 2 turnouts, but this band does not list it"):
            le.panel(bands(), {"Lower": {"turnouts": {"S1": "Switch X", "S2": "Switch X"}}})

    def test_a_shared_turnout_name_is_one_turnout_drawn_twice(self):
        # one band: two switches drawn as two turnouts, one JMRI turnout
        P = le.panel(bands(), {"Lower": {"turnouts": {"S1": "Switch X", "S2": "Switch X"},
                                         "shared_turnouts": ["Switch X"]}})
        self.assertEqual(sum(t["name"] == "Switch X" for t in P.turnouts), 2)
        self.assertEqual(sum(x.get("turnoutname") == "Switch X" for x in element(P).findall("layoutturnout")), 2)
        # two bands: each lists it
        P = le.panel(bands(), {"Lower": {"turnouts": {"S1": "Switch Y"}, "shared_turnouts": ["Switch Y"]},
                               "Upper": {"turnouts": {"U1": "Switch Y"}, "shared_turnouts": ["Switch Y"]}})
        self.assertEqual(sorted(t["band"] for t in P.turnouts if t["name"] == "Switch Y"), [0, 1])

    def test_shared_turnout_names_are_checked(self):
        cases = (
            ({"Lower": {"turnouts": {"S1": "Switch Y"}, "shared_turnouts": ["Switch Y"]},
              "Upper": {"turnouts": {"U1": "Switch Y"}}}, "does not list it in shared_turnouts"),
            ({"Lower": {"turnouts": {"S1": "Switch Y"}}, "Upper": {"turnouts": {"U1": "Switch Y"},
                                                                    "shared_turnouts": ["Switch Y"]}},
             "Lower level: turnout name 'Switch Y' is given to 2 turnouts, but this band does not list it"),
            ({"Lower": {"turnouts": {"S1": "Switch X"}, "shared_turnouts": ["Switch X"]}}, "it shares nothing"),
            ({"Lower": {"turnouts": {"S1": "Switch X"}, "shared_turnouts": ["Switch Z"]}},
             "no switch of the band is given"),
            ({"Lower": {"turnouts": {"S1": "Switch X"}, "shared_turnouts": "Switch X"}}, "must be a list"),
            ({"Lower": {"turnouts": {"S1": "Switch X"}, "shared_turnouts": ["Switch X", "Switch X"]}},
             "must be a list of different"),
        )
        for names, why in cases:
            with self.assertRaisesRegex(SchematicError, why, msg=names):
                le.panel(bands(), names)

    def test_shared_turnouts_are_checked_once_before_drawing(self):
        lower = [b for b in bands() if b[0].startswith("Lower")]
        page = dict(bands()[-1][2])                         # its band_order names Upper too
        one = {"Lower": {"turnouts": {"S1": "Switch Y"}, "shared_turnouts": ["Switch Y"]}}
        P = le.panel(lower, one, page=page)                 # the other half on Upper, not drawn: fine, and said
        self.assertTrue(any("shared turnout 'Switch Y' is drawn once here" in line for line in P.log), P.log)
        with self.assertRaisesRegex(SchematicError, "drawn as 1 turnout; it shares nothing"):
            le.panel(bands(), one, page=page)                # both bands drawn, given once
        three = {"Lower": {"turnouts": {"S1": "Switch Y", "S2": "Switch Y"}, "shared_turnouts": ["Switch Y"]},
                 "Upper": {"turnouts": {"U1": "Switch Y"}, "shared_turnouts": ["Switch Y"]}}
        with self.assertRaisesRegex(SchematicError, "given to 3 turnouts; one turnout is drawn at most twice"):
            le.panel(bands(), three)
        with mock.patch.object(le.Band, "build") as build, self.assertRaisesRegex(SchematicError, "shares nothing"):
            le.panel(bands(), one, page=page)
        build.assert_not_called()                           # stopped before anything was drawn

    def test_the_drawn_turnouts_must_match_the_names_count(self):
        P = le.Panel()
        P.turnouts = [dict(name="Switch Y"), dict(name="Switch Y")]
        with self.assertRaisesRegex(SchematicError, "Switch Y \\(2 drawn, 1 given\\)"):
            le.check_shared(P, {"Switch Y": 1})

    def test_names_for_switches_or_tracks_that_are_not_there_stop(self):
        for bad in ({"blocks": {"nope": ["X"]}}, {"turnouts": {"e1": "X"}}, {"os": {"nope": "X"}},
                    {"normal": {"nope": "C"}}, {"tracks": {}}):
            with self.assertRaises(SchematicError, msg=bad):
                le.panel(bands(), {"Lower": bad})

    def test_default_names_never_meet_given_names(self):
        P = panel({"Lower": {"blocks": {"e1": ["Main"]}}})
        lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        segs = {s["ident"]: s for s in P.segments}
        owner = defaultdict(set)
        for (bi, sid), ks in P.strand_segments.items():
            for k in ks:
                owner[segs[k]["block"]].add((bi, sid))
        self.assertEqual(owner["Main"], {(lower, "e1")})            # e3, whose default would be Main, is not in it
        for block, strands in owner.items():                        # no two unrelated tracks share a block
            self.assertTrue(len(strands) == 1 or block in ("Loop", "Summit", "Rise"), (block, strands))

    def test_double_crossover_leg_straight_up_stops(self):
        band = bands()[[t for t, _, _ in bands()].index(next(t for t, _, _ in bands() if t.startswith("Lower")))][1]
        from schematic.layout import paths
        drawn = paths(band)
        drawn["e7"] = [(6, 1), (6, 0.5), (10, 1)]
        with mock.patch.object(le, "paths", lambda b: drawn if b is band else paths(b)):
            with self.assertRaisesRegex(SchematicError, "double crossover 6: leg B leaves straight up or down"):
                le.panel([b for b in bands() if b[1] is band])

    def test_switch_with_legs_b_and_c_opposite_stops_clearly(self):
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            with self.assertRaisesRegex(SchematicError, "switch 9: legs B and C leave in opposite directions"):
                le.panel(wye_band())

    def test_cli_names_checked_against_every_band_and_read_safely(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(helpers.graph()))
            names = Path(tmp) / "names.json"
            run = lambda *extra: subprocess.run(  # noqa: E731
                [sys.executable, "-m", "schematic", "le", str(Path(tmp) / "le.xml"), "--data", str(f),
                 f"{graph}:example", "--band", "Lower", *extra], capture_output=True, text=True,
                cwd=helpers.PLUGIN, timeout=120)
            names.write_text(json.dumps({"Upper": {"turnouts": {"U1": "Turnout 21"}},
                                         "Lower": {"turnouts": {"S1": "Turnout 1"}}}))
            r = run("--names", str(names))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Turnout 1", (Path(tmp) / "le.xml").read_text())
            names.write_text(json.dumps({"Nowhere": {}}))
            r = run("--names", str(names))
            self.assertEqual(r.returncode, 2)
            self.assertIn("not a band", r.stderr)
            r = run("--names", str(Path(tmp) / "missing.json"))
            self.assertEqual(r.returncode, 2)
            self.assertIn("cannot read the names", r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            names.write_text("{not json")
            r = run("--names", str(names))
            self.assertEqual(r.returncode, 2)
            self.assertNotIn("Traceback", r.stderr)


if __name__ == "__main__":
    unittest.main()


def balloon_band():
    """A balloon loop: switch 7's legs B and C both lead into the one Loop track, so two masts face it and protect
    OS 7, one on each leg."""
    nodes = {"W": dict(kind="end", sub="bumper", label="", ins={}, outs={"E": "a"}),
             "S": dict(kind="switch", label="7", hand=1, ins={"A": "a", "C": "loop"}, outs={"B": "loop"})}
    st = lambda a, b, n: dict(src=a, dst=b, name=n, main=True, hidden=False, link=False, edge="", cm=1.0)  # noqa: E731
    strands = {"a": st(("W", "E"), ("S", "A"), "Lead"), "loop": st(("S", "B"), ("S", "C"), "Loop")}
    drawn = {"a": [(0, 0), (3, 0)], "loop": [(3, 0), (8, 0), (9, 1), (8, 2), (5, 2), (4, 1), (3, 0)]}
    return [("Test level", dict(nodes=nodes, strands=strands, _drawn=drawn),
             {"le_labels": {"block_contents": False}})]


class MastLeg(unittest.TestCase):
    """A turnout mast's `leg`: which of two slots with one facing and protected block it takes."""

    def draw(self, masts):
        names = {"Test": {"os": {"S": "OS 7"}, "masts": masts}}
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            return le.panel(balloon_band(), names)

    def test_each_mast_on_its_leg(self):
        for first, second in (("normal", "diverging"), ("diverging", "normal")):
            P = self.draw([{"mast": "M A", "facing": "Loop", "protects": ["OS 7"], "leg": first},
                           {"mast": "M B", "facing": "Loop", "protects": ["OS 7"], "leg": second}])
            normal = "B" if P.turnouts[0]["continuing"] == "2" else "C"
            got = {m["mast"]: m["slot"] for m in P.masts}
            with self.subTest(first=first):
                self.assertEqual(got["M A"], normal if first == "normal" else "BC".replace(normal, ""))
                self.assertEqual(sorted(got.values()), ["B", "C"])
                self.assertFalse(P.unplaced)
        # without it the first takes the first slot that fits, and the log says so
        P = self.draw([{"mast": "M A", "facing": "Loop", "protects": ["OS 7"]}])
        self.assertTrue(any("2 slots fit" in line for line in P.log))

    def test_a_leg_with_no_slot_is_left_unplaced(self):
        P = self.draw([{"mast": "M A", "facing": "Loop", "protects": ["OS 7"], "leg": "normal"},
                       {"mast": "M B", "facing": "Loop", "protects": ["OS 7"], "leg": "normal"}])
        self.assertEqual([u[1] for u in P.unplaced], ["M B"])
        self.assertIn("no normal turnout leg faces Loop", P.unplaced[0][2])

    def test_bad_legs_stop(self):
        for bad in ({"leg": "left"}, {"leg": "normal", "kind": "anchor"}):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "leg must be one of normal, diverging"):
                self.draw([dict({"mast": "M", "facing": "Loop", "protects": ["OS 7"]}, **bad)])


class Unjoined(unittest.TestCase):
    def test_joins_none_leaves_a_bands_ends_unjoined(self):
        joined = le.panel(bands())
        self.assertTrue(joined.joins)
        key = le.band_key(bands()[0][0])
        P = le.panel(bands(), {key: {"joins": "none"}})
        touching = {b for (b, _i) in joined.join_ends}
        self.assertIn(0, touching)
        self.assertFalse([1 for (b, _i) in P.join_ends if b == 0])          # nothing reaches that band
        self.assertLess(len(P.joins), len(joined.joins))
        bumpers = lambda Q: sum(1 for p in Q.points.values() if p["type"] == "END_BUMPER")     # noqa: E731
        self.assertGreater(bumpers(P), bumpers(joined))                       # its ends are ends again
        with self.assertRaisesRegex(SchematicError, 'joins must be "own", "other" or "none"'):
            le.panel(bands(), {key: {"joins": "neither"}})
