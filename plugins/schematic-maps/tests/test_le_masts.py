"""Mast icons on the generated Layout Editor panel placed by the CATS rules (le_masts): gantries in one column, icons
clear of turnouts, labels and one another, and every mast still in the slot JMRI resolves to its blocks."""
import math
import unittest

from unittest import mock

import helpers
from schematic import le, le_masts, slots
from schematic.core import SchematicError
import test_le
from test_slots import boundaries

# the double track between switches 2 and 6 and between 6 and 3, each track cut into two blocks: the cut on Main and
# the cut on Passing stand a few pixels apart, so the masts there that govern one switch form a gantry
BLOCKS = {"e3": ["Main A", "Main B"], "e4+e5": ["Passing A", "Passing B"],
          "e7": ["Main C", "Main D"], "e8": ["Passing C", "Passing D"]}
GANTRY_MASTS = [("East 6 main", "Main A", "Main B"), ("East 6 passing", "Passing A", "Passing B"),
                ("West 6 main", "Main D", "Main C"), ("West 6 passing", "Passing D", "Passing C")]


def bands():
    """The example's bands without block contents icons: BLOCKS cuts the double track into eight blocks on a 36 px
    grid, more icons than its rows have room for, and these tests are about the masts."""
    return [(t, b, dict(o, le_labels={"block_contents": False})) for t, b, o in test_le.bands()]


def lower():
    return next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))


def key():
    return le.band_key(bands()[lower()][0])


def names_for(dense):
    """(names, the bare panel's slots by blocks, the masts asked for). The gantry masts, and with `dense` a mast in
    every turnout leg and end bumper slot that resolves to blocks of its own (some high, most dwarfs): far more than
    a real panel holds, so not every icon can be clean; without it, the gantry masts and two masts of switch 3."""
    base = {key(): {"blocks": BLOCKS}}
    found = boundaries(le.panel(bands(), base), lower())
    masts = [dict(mast=m, facing=f, protects=[p], kind="anchor") for m, f, p in GANTRY_MASTS]
    for (f, pr), cs in sorted(found.items()):
        if len(cs) == 1 and cs[0][0] in ("turnout", "end bumper"):
            if dense or (cs[0][0] == "turnout" and f in ("Main D", "Passing D")):
                masts.append(dict(mast=f"{cs[0][0]} {cs[0][1]} {cs[0][2]}", facing=f, protects=list(pr),
                                  kind=cs[0][0], icon=[12, 40] if len(masts) % 3 == 0 else [12, 17]))
    return {key(): {"blocks": BLOCKS, "masts": masts}}, found, masts


def built(dense=True):
    """(Panel, the bare panel's slots by blocks, the masts asked for), built once per test run."""
    if ("le_masts", dense) not in helpers._cache:
        names, found, masts = names_for(dense)
        helpers._cache[("le_masts", dense)] = (le.panel(bands(), names), found, masts)
    return helpers._cache[("le_masts", dense)]


def masts_of(P):
    """le_masts' view of a placed panel (its indexes), to check it with."""
    return le_masts.Masts(P, bands(), slots.Index(le.to_xml(P, "probe", probe=True)))


def M_x(P, m):
    """The x of a mast's boundary."""
    return masts_of(P).boundary(m)[0]


def three_blocks():
    """Main (2 to 6) cut into three blocks, an east bound mast at both cuts, both governing switch 6: two anchors on
    one track in one cluster."""
    blocks = dict(BLOCKS, e3=["Main A", "Main B", "Main C"])
    masts = [dict(mast="East A", facing="Main A", protects=["Main B"], kind="anchor"),
             dict(mast="East B", facing="Main B", protects=["Main C"], kind="anchor"),
             dict(mast="East P", facing="Passing A", protects=["Passing B"], kind="anchor")]
    return {key(): {"blocks": blocks, "masts": masts}}


class Gantries(unittest.TestCase):
    def test_the_masts_of_one_switch_and_direction_stand_in_one_column(self):
        P, _found, _masts = built()
        at = {m["mast"]: P.points[m["ident"]]["xy"] for m in P.masts if m["mast"] in dict(
            (g[0], 1) for g in GANTRY_MASTS)}
        self.assertAlmostEqual(at["East 6 main"][0], at["East 6 passing"][0], delta=0.05)
        self.assertAlmostEqual(at["West 6 main"][0], at["West 6 passing"][0], delta=0.05)
        groups = [sorted(m["mast"] for m in g) for g in P.gantries]
        self.assertIn(["East 6 main", "East 6 passing"], groups)
        self.assertIn(["West 6 main", "West 6 passing"], groups)
        self.assertTrue(P.anchors_moved)
        self.assertTrue(any("into the gantry of switch 6 east bound" in line for line in P.log))

    def test_slots_and_blocks_are_unchanged(self):
        P, found, masts = built()
        want = {m["mast"]: m for m in masts}
        got = {m["mast"]: m for m in slots.Index(le.to_xml(P, "Generated")).masts()}
        self.assertEqual(set(got), set(want))
        for name, m in want.items():
            with self.subTest(mast=name):
                g = got[name]
                self.assertEqual((g["kind"], g["facing"], g["protects"]), (m["kind"], m["facing"], m["protects"]))
                # the very slot it had on the panel before any anchor slid
                self.assertIn((g["kind"], g["ident"], g["slot"]), found[(m["facing"], tuple(m["protects"]))])

    def test_a_moved_anchor_stays_on_its_straight_track_between_the_same_points(self):
        P, _found, _masts = built()
        plain = le.panel(bands(), {key(): {"blocks": BLOCKS}})
        segs = {s["ident"]: s for s in P.segments}
        M = masts_of(P)
        for _mast, ident, px in P.anchors_moved:
            with self.subTest(anchor=ident):
                self.assertLessEqual(px, le_masts.GANTRY_SHIFT * P.cellx[lower()])
                p, was = P.points[ident]["xy"], plain.points[ident]["xy"]
                self.assertEqual(P.points[ident]["conn"], plain.points[ident]["conn"])
                fars = []
                for sid in P.points[ident]["conn"]:
                    s = segs[sid]
                    self.assertIsNone(s["arc"])
                    end = s["ends"][1] if s["ends"][0] == (ident, "POS_POINT") else s["ends"][0]
                    fars.append(M.xy(end))
                a, b = fars
                u = le.unit(le.sub(b, a))
                self.assertLess(abs(le.cross(u, le.sub(p, a))), 0.01)            # on the line
                self.assertLess(abs(le.cross(u, le.sub(was, a))), 0.01)
                t = le.dot(le.sub(p, a), u)
                self.assertGreaterEqual(t, min(P.cellx[lower()], le.dot(le.sub(was, a), u)) - 0.01)
                self.assertLessEqual(t, math.dist(a, b) - min(P.cellx[lower()],
                                                              math.dist(a, b) - le.dot(le.sub(was, a), u)) + 0.01)


    def test_anchors_on_one_track_never_meet_or_pass_and_keep_their_minimum(self):
        for span in (le_masts.GANTRY_SPAN, 5):         # wide: both cuts of Main fall in one cluster
            with self.subTest(span=span), mock.patch.object(le_masts, "GANTRY_SPAN", span):
                P = le.panel(bands(), three_blocks())
                M = masts_of(P)
                plain = le.panel(bands(), {key(): {"blocks": three_blocks()[key()]["blocks"]}})
                cell = P.cellx[lower()]
                for s in P.segments:
                    if s["arc"] or s["hidden"]:
                        continue
                    a, b = (M.xy(e) for e in s["ends"])
                    was = math.dist(*(masts_of(plain).xy(e) for e in s["ends"]))
                    self.assertGreaterEqual(math.dist(a, b), min(cell, was) - 0.01, s["ident"])
                cuts = [m for m in P.masts if m["mast"] in ("East A", "East B")]
                xa, xb = (P.points[m["ident"]]["xy"][0] for m in cuts)
                pa, pb = (plain.points[m["ident"]]["xy"][0] for m in cuts)
                self.assertEqual(xa < xb, pa < pb)                       # the same order along the track
                self.assertGreater(abs(xb - xa), cell - 0.01)

    def test_a_gantry_spans_at_most_its_span(self):
        with mock.patch.object(le_masts, "GANTRY_SPAN", 0.001):        # under a pixel: no two cuts are that close
            P = le.panel(bands(), names_for(False)[0])
        self.assertEqual(P.anchors_moved, [])                              # nothing may move into a column
        for g in P.gantries:                                                # only masts already in one stand as one
            self.assertLess(max(M_x(P, m) for m in g) - min(M_x(P, m) for m in g), 0.001 * P.cellx[lower()])

    def test_a_slid_anchor_that_left_its_line_or_track_stops(self):
        P, _found, _masts = built(dense=False)
        M = masts_of(P)
        ident = next(m["ident"] for m in P.masts if m["mast"] == "East 6 main")
        xy = list(P.points[ident]["xy"])
        M.original[ident] = (tuple(xy), {sid: 1.0 for sid in P.points[ident]["conn"]})
        try:
            P.points[ident]["xy"] = [xy[0], xy[1] + 5]                     # off the line
            with self.assertRaisesRegex(SchematicError, "off the line"):
                M.verify()
            far = max(M.xy(M.other_end(sid, (ident, "POS_POINT")))[0] for sid in P.points[ident]["conn"])
            P.points[ident]["xy"] = [far + 20, xy[1]]                       # past the end of its track
            with self.assertRaisesRegex(SchematicError, "past the end|changed its blocks"):
                M.verify()
            M.original[ident] = (tuple(xy), {sid: 1000.0 for sid in P.points[ident]["conn"]})
            P.points[ident]["xy"] = [far - 2, xy[1]]                        # a track left too short
            with self.assertRaisesRegex(SchematicError, "minimum"):
                M.verify()
        finally:
            P.points[ident]["xy"] = xy


class Lone(unittest.TestCase):
    def test_an_anchor_slides_only_when_no_icon_spot_is_clean_where_it_stood(self):
        for P in (built()[0], built(dense=False)[0], le.panel(bands(), three_blocks())):
            in_gantry = {m["mast"] for g in P.gantries for m in g}
            M = masts_of(P)
            for ident, was in P.anchors_from.items():
                ms = M.on_anchor[ident]
                if {m["mast"] for m in ms} & in_gantry:
                    continue
                with self.subTest(anchor=ident):
                    now = list(P.points[ident]["xy"])
                    P.points[ident]["xy"] = list(was)
                    M.world.update(P.points[ident]["conn"])
                    others = [le_masts.icon_rect_of(q) for q in P.masts if q not in ms]
                    self.assertTrue(any(M.best(m, others)[4] for m in ms))
                    P.points[ident]["xy"] = now

    def test_a_lone_anchor_with_no_clean_spot_slides_the_least_it_must(self):
        names = {key(): {"blocks": BLOCKS, "masts": [dict(mast="Lone", facing="Main A", protects=["Main B"],
                                                         kind="anchor")]}}
        P0 = le.panel(bands(), {key(): {"blocks": BLOCKS}})
        ident = masts_of(le.panel(bands(), names)).P.masts[0]["ident"]
        x0 = P0.points[ident]["xy"][0]
        real = le_masts.Masts.best

        def best(self, m, others):          # no clean spot until the boundary is 5 px east of where it was drawn
            got = real(self, m, others)
            return got if self.boundary(m)[0] >= x0 + 5 else (got[0] + 10, got[1], got[2], got[3], ["ink"], *got[5:])
        with mock.patch.object(le_masts.Masts, "best", best):
            P = le.panel(bands(), names)
        self.assertEqual(P.anchors_from, {ident: tuple(P0.points[ident]["xy"])})
        self.assertAlmostEqual(P.points[ident]["xy"][0], x0 + 3 * le_masts.ICON_STEP, delta=0.01)
        self.assertEqual(P.masts[0]["spot"][2], ())
        self.assertTrue(any("no icon spot was clean where it stood" in line for line in P.log))
        self.assertEqual(le.panel(bands(), names).anchors_from, {})           # clean where it stands: stays

    def test_no_slide_when_an_icon_spot_is_clean(self):
        clean = lambda self, m, others: (0, 0, slots.GAP, slots.GAP, [],     # noqa: E731
                                         *le_masts.icon_rect(self.boundary(m), self.d[m["mast"]], m["size"],
                                                             slots.GAP, slots.GAP))
        with mock.patch.object(le_masts.Masts, "best", clean):
            P = le.panel(bands(), names_for(True)[0])
        in_gantry = {m["mast"] for g in P.gantries for m in g}
        self.assertFalse([a for m, a, _px in P.anchors_moved if m not in in_gantry])


class Probe(unittest.TestCase):
    def test_an_export_with_a_mast_but_no_icon_stops(self):
        P, _found, _masts = built(dense=False)
        m = P.masts[0]
        icon = m.pop("icon")
        try:
            le.to_xml(P, "Probe", probe=True)                               # slots only: fine
            with self.assertRaisesRegex(SchematicError, "no icon"):
                le.to_xml(P, "Generated")
        finally:
            m["icon"] = icon


class Errors(unittest.TestCase):
    def names(self):
        return names_for(False)[0]

    def test_bad_control_points_stop_before_any_work(self):
        for bad in ("CP", {"CP": ["6"]}, {"CP": {"switches": "6"}}, {"CP": {"switches": [None]}},
                    {"CP": {"switches": [True]}}, {"CP": {}}, {"A": {"switches": ["6"]}, "B": {"switches": ["6"]}}):
            bs = [(t, b, dict(o, control_points=bad) if i == lower() else o) for i, (t, b, o) in enumerate(bands())]
            with self.subTest(bad=bad), self.assertRaises(SchematicError):
                le.panel(bs, self.names())

    def test_control_points_group_masts(self):
        bs = [(t, b, dict(o, control_points={"Junction": {"switches": ["6*"]}}) if i == lower() else o)
              for i, (t, b, o) in enumerate(bands())]
        P = le.panel(bs, self.names())
        self.assertTrue(any("gantry of Junction east bound" in line for line in P.log))

    def test_an_icon_off_the_trains_right_hand_side_stops(self):
        real = le_masts.icon_rect

        def left(p, d, size, back, across):          # mirror every spot to the left of the train
            return real(p, (-d[0], -d[1]), size, back, across)
        with mock.patch.object(le_masts, "icon_rect", left), \
                self.assertRaisesRegex(SchematicError, "right-hand side"):
            le.panel(bands(), self.names())

    def test_a_moved_anchor_whose_track_ends_meet_stops(self):
        P = le.panel(bands(), self.names())
        M = masts_of(P)
        ident = sorted(P.anchors_from)[0]
        M.original[ident] = (tuple(P.points[ident]["xy"]), {})
        with mock.patch.object(M, "xy", lambda end: (0.0, 0.0)), self.assertRaisesRegex(SchematicError, "meet"):
            M.verify()


def drawn_blocks(P, sid):
    """[(block, px)] along a strand of the lower band, from its first end, runs of one block folded."""
    segs = {s["ident"]: s for s in P.segments}
    out = []
    for ident in P.strand_segments[(lower(), sid)]:
        s = segs[ident]
        L = le.piece_len(dict(kind="arc", a=s["arc"]["drawn"][0], b=s["arc"]["drawn"][-1], angle=s["arc"]["angle"])) \
            if s["arc"] else math.dist(*(masts_of(P).xy(e) for e in s["ends"]))
        if out and out[-1][0] == s["block"]:
            out[-1] = (s["block"], out[-1][1] + L)
        else:
            out.append((s["block"], L))
    return out


class Throats(unittest.TestCase):
    """Short blocks at the ends of a track (throats) are drawn at their own ends, at their real share."""
    BLOCKS = dict(BLOCKS, e3=["Main West throat", "Main", "Main East throat"])
    LENGTHS = {"Main West throat": 1.0, "Main": 30.0, "Main East throat": 1.0}

    def test_split_follows_real_lengths_floor_arcs_and_room(self):
        line = lambda a, b: dict(kind="line", a=a, b=b)     # noqa: E731
        got = le.split([line((0, 0), (320, 0))], 3, "t", [1, 30, 1])
        self.assertEqual([round(le.piece_len(pc), 3) for pc, _ in got], [12, 296, 12])      # 10 px throats raised to the floor
        self.assertEqual([i for _, i in got], [0, 1, 2])
        got = le.split([line((0, 0), (640, 0))], 3, "t", [1, 30, 1])                 # above the floor: shares
        self.assertEqual([round(le.piece_len(pc), 3) for pc, _ in got], [20, 600, 20])
        arc = le.rounded([(0, 0), (100, 0), (100, 100)])                              # a cut in the arc moves out
        got = le.split(arc, 2, "t", [1, 1])
        self.assertTrue(all(pc["kind"] == "line" or i in (0, 1) for pc, i in got))
        self.assertEqual(len({i for pc, i in got if pc["kind"] == "arc"}), 1)
        got = le.split([line((0, 0), (100, 0)), *le.rounded([(100, 0), (200, 0), (200, 100)])[1:]], 2, "t",
                       [1, 1], room=[(30, 0)])                                       # icon room before the cut
        cut = sum(le.piece_len(pc) for pc, i in got if i == 0)
        self.assertGreaterEqual(cut, 30)
        with self.assertRaises(SchematicError):
            le.split([line((0, 0), (0.0000001, 0))], 3, "t")

    def test_throats_sit_at_their_own_ends_in_block_order(self):
        names = {key(): {"blocks": self.BLOCKS, "lengths": self.LENGTHS}}
        P = le.panel(bands(), names)
        got = drawn_blocks(P, "e3")
        self.assertEqual([b for b, _ in got], self.BLOCKS["e3"])
        total = sum(L for _, L in got)
        for (b, L) in (got[0], got[-1]):
            self.assertLessEqual(L, max(le.MIN_BLOCK, total / 32) + 0.01, b)
            self.assertGreaterEqual(L, min(le.MIN_BLOCK, total / 3) - 0.01, b)
        plain = drawn_blocks(le.panel(bands(), {key(): {"blocks": self.BLOCKS}}), "e3")
        self.assertAlmostEqual(plain[0][1], total / 3, delta=1)                      # without lengths: equal

    def test_lengths_for_only_some_blocks_are_logged_and_drawn_equal(self):
        names = {key(): {"blocks": self.BLOCKS, "lengths": {"Main": 30.0}}}
        P = le.panel(bands(), names)
        self.assertTrue(any("lengths given for Main but not for" in line for line in P.log))

    def test_bad_lengths_stop(self):
        for bad in ([1], {"Main": 0}, {"Main": -1}, {"Main": "long"}, {"Main": True}, {"Main": float("inf")},
                    {"Nowhere": 3.0}):
            with self.subTest(bad=bad), self.assertRaises(SchematicError):
                le.panel(bands(), {key(): {"blocks": self.BLOCKS, "lengths": bad}})


def block_lengths(got):
    out = []
    for pc, i in got:
        if out and out[-1][0] == i:
            out[-1] = (i, out[-1][1] + le.piece_len(pc))
        else:
            out.append((i, le.piece_len(pc)))
    return [v for _, v in out]


class Split(unittest.TestCase):
    """Moving a cut off an arc or to a place with room for an icon never breaks the blocks' order or floors."""
    line = staticmethod(lambda a, b: dict(kind="line", a=a, b=b))

    def test_room_that_would_squeeze_a_throat_gives_way_to_its_floor(self):
        log = []
        got = block_lengths(le.split([self.line((0, 0), (100, 0))], 3, "t", [10, 80, 10], room=[(0, 0), (95, 0)],
                                     log=log))
        self.assertTrue(all(v >= le.MIN_BLOCK - 1e-6 for v in got), got)
        self.assertTrue(log)

    def test_room_never_makes_cuts_cross(self):
        got = le.split([self.line((0, 0), (100, 0))], 3, "t", [10, 10, 80], room=[(30, 0), (0, 0)])
        self.assertEqual([i for _, i in got], [0, 1, 2])
        self.assertTrue(all(v >= le.MIN_BLOCK - 1e-6 for v in block_lengths(got)))
        self.assertGreaterEqual(block_lengths(got)[0], 30 - 1e-6)

    def test_a_rounded_corner_never_leaves_a_sliver(self):
        got = le.split(le.rounded([(0, 0), (30, 0), (30, 30)]), 3, "t")
        self.assertTrue(all(v >= le.MIN_BLOCK - 1e-6 for v in block_lengths(got)), block_lengths(got))
        self.assertFalse([pc for pc, _ in got if pc["kind"] == "arc" and le.piece_len(pc) < 1])

    def test_two_cuts_near_one_arc_end_take_both_ends(self):
        got = le.split(le.rounded([(0, 0), (100, 0), (100, 100)]), 3, "t", [60, 10, 100])
        self.assertEqual(len(block_lengths(got)), 3)
        self.assertTrue(all(v >= le.MIN_BLOCK - 1e-6 for v in block_lengths(got)))

    def test_no_place_stops_naming_the_track(self):
        with self.assertRaisesRegex(SchematicError, "Track Q: too short"):
            le.split(le.rounded([(0, 0), (40, 0), (40, 40)]), 3, "Track Q", least=[30, 30, 30])


class ReviewFixes(unittest.TestCase):
    def test_a_gantry_is_never_slid_again_by_a_lone_anchor(self):
        real = le_masts.Masts.best
        gantry = {"East 6 main", "East 6 passing"}

        def best(self, m, others):                       # the gantry's masts are clean only out of their column
            got = real(self, m, others)
            xs = {round(self.boundary(self.by_name[n])[0], 2) for n in gantry}
            return (got[0] + 10, *got[1:4], ["ink"], *got[5:]) if m["mast"] in gantry and len(xs) == 1 else got
        real_options = le_masts.Masts.options

        def options(self, m, run=None):                  # no spot common to the gantry: each icon takes its own
            got = real_options(self, m, run)
            return [o for o in got if (o[1] == slots.GAP) == (m["mast"] == "East 6 main")] or got
        with mock.patch.object(le_masts.Masts, "best", best), mock.patch.object(le_masts.Masts, "options", options):
            P = le.panel(bands(), names_for(False)[0])
        xs = {round(P.points[m["ident"]]["xy"][0], 3) for m in P.masts if m["mast"] in gantry}
        self.assertEqual(len(xs), 1)
        self.assertFalse([line for line in P.log if "no icon spot was clean where it stood" in line
                          and any(n in line for n in gantry)])
        self.assertTrue(any("East 6" in line and "no clean spot for its icon" in line for line in P.log))

    def test_a_turnout_legs_gantry_scores_its_own_turnout_as_its_track(self):
        seen = []
        real = le_masts.Masts.mine

        def mine(m):
            seen.append(m["mast"])
            return real(m)
        with mock.patch.object(le_masts.Masts, "mine", staticmethod(mine)):
            P = le.panel(bands(), names_for(True)[0])
        legs = [g for g in P.gantries if all(m["kind"] == "turnout" for m in g)]
        self.assertTrue(legs)
        for g in legs:
            self.assertTrue(all(m["mast"] in seen for m in g))

    def test_every_icon_is_scored_where_everything_stands_at_the_end(self):
        real = le_masts.Masts.best
        names = names_for(True)[0]
        P0 = le.panel(bands(), {key(): {"blocks": BLOCKS}})
        lone = next(m for m in names[key()]["masts"] if m["mast"] == "East 6 main")
        names[key()]["masts"] = [m for m in names[key()]["masts"] if m["mast"] not in ("East 6 passing",)]
        ident = masts_of(le.panel(bands(), names)).by_name["East 6 main"]["ident"]
        x0 = P0.points[ident]["xy"][0]

        def best(self, m, others):                       # East 6 main is clean only 5 px east of where it was drawn
            got = real(self, m, others)
            if m["mast"] == lone["mast"] and self.boundary(m)[0] < x0 + 5:
                return (got[0] + 10, *got[1:4], ["ink"], *got[5:])
            return got
        with mock.patch.object(le_masts.Masts, "best", best):        # as the icons were scored: the drawing's labels
            P = le.draw_panel(bands(), names, le.CELL, le.ROW, None, labels=False)
        self.assertIn(ident, P.anchors_from)
        self.assertEqual(sum(1 for a in P.anchors_moved if a[1] == ident), 1)       # recorded once
        M = masts_of(P)
        rects = {m["mast"]: le_masts.icon_rect_of(m) for m in P.masts}
        for m in P.masts:
            with self.subTest(mast=m["mast"]):
                _run, own = M.run(m)
                why = le_masts.spot_cost(rects[m["mast"]], M.world.near(M.boundary(m), le_masts.NEAR + m["size"][1]),
                                         own, M.mine(m), [r for n, r in rects.items() if n != m["mast"]])[1]
                self.assertEqual(sorted(why), sorted(m["spot"][2]))

    def test_a_slid_anchor_rescores_the_masts_whose_track_it_ends(self):
        P, _found, _masts = built()
        M = masts_of(P)
        for m in P.masts:
            M.picks[m["mast"]] = (0, 0, [], 0, le_masts.icon_rect_of(m), m["icon"])
        ident = next(m["ident"] for m in P.masts if m["kind"] == "anchor")
        conn = set(P.points[ident]["conn"])
        mine = {m["mast"] for m in M.on_anchor[ident]}
        touched = {m["mast"] for m in P.masts if m["mast"] not in mine and M.run(m)[1] & conn}
        self.assertTrue(touched)
        seen = []
        real = le_masts.Masts.best
        with mock.patch.object(le_masts.Masts, "best", lambda self, m, o: seen.append(m["mast"]) or real(self, m, o)):
            M.rescore(ident, tuple(P.points[ident]["xy"]), mine, set())
        self.assertTrue(touched <= set(seen), touched - set(seen))
        self.assertFalse(mine & set(seen))

    def test_bad_block_names_stop(self):
        for bad in ([["A"]], {"e3": 7}, {"e3": []}, {"e3": [None]}, {"e3": ["A", ""]}, {"e3": {"A": 1}}):
            with self.subTest(bad=bad), self.assertRaises(SchematicError):
                le.panel(bands(), {key(): {"blocks": bad}})
        with self.assertRaises(SchematicError):
            le.panel(bands(), {key(): {"turnouts": ["x"]}})

    def test_a_length_on_two_tracks_is_logged(self):
        blocks = dict(BLOCKS, e3=["Shared", "Main B"], e7=["Shared", "Main D"])
        P = le.panel(bands(), {key(): {"blocks": blocks, "lengths": {"Shared": 1, "Main B": 5, "Main D": 5}}})
        self.assertTrue(any("Shared's length is used on more than one track" in line for line in P.log))


class Icons(unittest.TestCase):
    def test_icons_clear_of_turnouts_tracks_labels_and_each_other(self):
        P, _found, masts = built(dense=False)
        self.assertGreater(len(masts), 4)
        world = masts_of(P).world
        rects = {m["mast"]: le_masts.icon_rect_of(m) for m in P.masts}
        names = [le_masts.label_rect(lb) for lb in P.labels]
        for m in P.masts:
            with self.subTest(mast=m["mast"]):
                r = rects[m["mast"]]
                self.assertEqual(m["spot"][2], (), f"{m['mast']}: {m['spot']}")
                for cen, lines in world.bodies.values():
                    self.assertGreaterEqual(r.gap_point(cen), le_masts.TURNOUT_R)
                    for a, b in lines:
                        self.assertGreaterEqual(r.gap_seg(a, b), le_masts.CLEAR[1])
                for pieces in world.track.values():
                    self.assertGreaterEqual(min(r.gap_seg(a, b) for a, b in pieces), le_masts.CLEAR[0])
                self.assertFalse([n for n, o in rects.items() if n != m["mast"] and r.overlaps(o)])
                self.assertFalse([lb for lb in names if r.overlaps(lb)])

    def test_a_crowded_panel_has_fewer_icons_in_trouble_than_with_every_icon_in_its_first_spot(self):
        P, _found, _masts = built()
        ix = slots.Index(le.to_xml(P, "Generated"))
        M = masts_of(P)
        world = M.world
        first = {}
        for m in P.masts:
            p, d = ix.travel(m["kind"], m["ident"], m["slot"])
            first[m["mast"]] = (le_masts.icon_rect(p, d, m["size"], slots.GAP, slots.GAP)[0], p, m)

        def trouble(rects):
            bad = 0
            for name, (r, p, m) in rects.items():
                own = M.run(m)[1]
                why = le_masts.spot_cost(r, world.near(p, 150), own, {m["ident"]} if m["kind"] == "turnout" else
                                         set(), [o for k, (o, _p, _m) in rects.items() if k != name])[1]
                bad += bool(le_masts.HARD & set(why))
            return bad
        now = {m["mast"]: (le_masts.icon_rect_of(m), first[m["mast"]][1], m) for m in P.masts}
        self.assertLess(trouble(now), trouble(first) * 0.7)

    def test_right_hand_side_close_to_the_rail_turned_to_travel(self):
        P, _found, _masts = built()
        ix = slots.Index(le.to_xml(P, "Generated"))
        for m in P.masts:
            with self.subTest(mast=m["mast"]):
                p, d = ix.travel(m["kind"], m["ident"], m["slot"])
                c = le_masts.icon_rect_of(m).c
                v = le.sub(c, p)
                across = v[0] * -d[1] + v[1] * d[0]
                self.assertGreater(across, slots.GAP)
                self.assertLessEqual(across, le_masts.WIDE + m["size"][0] / 2 + 0.75)
                self.assertLess(le.dot(v, d), 0)
                self.assertEqual(m["icon"][2], slots.icon_degrees(d))

    def test_a_gantrys_icons_line_up(self):
        P, _found, _masts = built()
        for g in P.gantries:
            with self.subTest(gantry=[m["mast"] for m in g]):
                self.assertEqual(len({m["spot"][:2] for m in g}), 1)


class Spots(unittest.TestCase):
    def test_touching_the_rail_beats_reading_as_another_tracks_mast(self):
        self.assertLess(le_masts.ICON_COST["graze"], le_masts.ICON_COST["other"])
        # an east bound dwarf on a level track at y 0 with another track 18 px below: in the first spot its middle is
        # 10 px from its own rail and 8 from the other, so it reads as the other track's mast; touching, it does not
        near = ({"own": [((-100, 0), (100, 0))], "other": [((-100, 18), (100, 18))]}, {}, [], [])
        first = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)[0]
        touch = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, le_masts.TOUCH)[0]
        self.assertIn("other", le_masts.spot_cost(first, near, {"own"}, set(), [])[1])
        self.assertEqual(le_masts.spot_cost(touch, near, {"own"}, set(), [])[1], ["graze"])

    def test_a_turnout_body_is_never_a_clean_spot(self):
        near = ({"own": [((-100, 0), (0, 0))]}, {"T": ((10, 0), [((10, 0), (22, 0)), ((10, 0), (-2, 0))])}, [], [])
        at = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)[0]
        self.assertNotIn("turnout", le_masts.spot_cost(at, near, {"own"}, set(), [])[1])
        over = le_masts.icon_rect((20, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)[0]
        self.assertIn("turnout", le_masts.spot_cost(over, near, {"own"}, set(), [])[1])

    def test_rect_geometry(self):
        r = le_masts.Rect((0, 0), (1, 0), 5, 2)
        self.assertEqual(r.gap_seg((-10, 0), (10, 0)), 0)
        self.assertAlmostEqual(r.gap_seg((-10, 5), (10, 5)), 3)
        self.assertAlmostEqual(r.gap_point((8, 6)), 5)
        self.assertTrue(r.overlaps(le_masts.Rect((9, 0), (0, 1), 2, 4)))
        self.assertFalse(r.overlaps(le_masts.Rect((12, 0), (0, 1), 2, 4)))
        turned = le_masts.Rect((0, 0), (math.sqrt(0.5), math.sqrt(0.5)), 5, 1)
        self.assertFalse(turned.overlaps(le_masts.Rect((4, -4), (1, 0), 1, 1)))      # beside the diagonal


if __name__ == "__main__":
    unittest.main()


class SegWithin(unittest.TestCase):
    """Rect.seg_within(a, b, t) is gap_seg(a, b) < t, with a shortcut that never changes the answer."""

    def test_agrees_with_the_exact_gap_on_turned_rectangles(self):
        import random
        rng = random.Random(5)
        for _ in range(4000):
            ang = rng.uniform(0, 2 * math.pi)
            rect = le_masts.Rect((rng.uniform(-5, 5), rng.uniform(-5, 5)), (math.cos(ang), math.sin(ang)),
                                 rng.uniform(1, 9), rng.uniform(1, 5))
            for _ in range(5):
                a = (rng.uniform(-30, 30), rng.uniform(-30, 30))
                b = a if rng.random() < 0.1 else (rng.uniform(-30, 30), rng.uniform(-30, 30))
                t = rng.choice((0.0, le_masts.CLEAR[0], le_masts.CLEAR[1], 7.5))
                self.assertEqual(rect.seg_within(a, b, t), rect.gap_seg(a, b) < t, (rect.c, rect.u, a, b, t))

    def test_the_shortcut_boundary(self):
        rect = le_masts.Rect((0, 0), (1, 0), 3, 4)            # circle radius 5
        self.assertFalse(rect.seg_within((8, -20), (8, 20), 3))    # bounding box exactly r + t away: gap 5 >= 3
        self.assertTrue(rect.seg_within((5.9, -20), (5.9, 20), 3))  # gap 2.9 to the long side
