"""Mast icons on the generated Layout Editor panel placed by the CATS rules (le_masts): gantries in one column, icons
clear of turnouts, labels and one another, and every mast still in the slot JMRI resolves to its blocks."""
import math
import unittest

import helpers
from schematic import le, le_masts, slots
from test_le import bands
from test_slots import boundaries

# the double track between switches 2 and 6 and between 6 and 3, each track cut into two blocks: the cut on Main and
# the cut on Passing stand a few pixels apart, so the masts there that govern one switch form a gantry
BLOCKS = {"e3": ["Main A", "Main B"], "e4+e5": ["Passing A", "Passing B"],
          "e7": ["Main C", "Main D"], "e8": ["Passing C", "Passing D"]}
GANTRY_MASTS = [("East 6 main", "Main A", "Main B"), ("East 6 passing", "Passing A", "Passing B"),
                ("West 6 main", "Main D", "Main C"), ("West 6 passing", "Passing D", "Passing C")]


def lower():
    return next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))


def key():
    return le.band_key(bands()[lower()][0])


def built(dense=True):
    """(Panel, the bare panel's slots by blocks, the masts asked for). The gantry masts, and with `dense` a mast in
    every turnout leg and end bumper slot that resolves to blocks of its own (some high, most dwarfs): far more than
    a real panel holds, so not every icon can be clean; without it, the gantry masts and the masts of switch 3."""
    if ("le_masts", dense) not in helpers._cache:
        base = {key(): {"blocks": BLOCKS}}
        found = boundaries(le.panel(bands(), base), lower())
        masts = [dict(mast=m, facing=f, protects=[p], kind="anchor") for m, f, p in GANTRY_MASTS]
        for (f, pr), cs in sorted(found.items()):
            if len(cs) == 1 and cs[0][0] in ("turnout", "end bumper"):
                if dense or (cs[0][0] == "turnout" and f in ("Main D", "Passing D")):
                    masts.append(dict(mast=f"{cs[0][0]} {cs[0][1]} {cs[0][2]}", facing=f, protects=list(pr),
                                      kind=cs[0][0], icon=[12, 40] if len(masts) % 3 == 0 else [12, 17]))
        names = {key(): {"blocks": BLOCKS, "masts": masts}}
        helpers._cache[("le_masts", dense)] = (le.panel(bands(), names), found, masts)
    return helpers._cache[("le_masts", dense)]


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
        turnouts = {t["ident"]: t for t in P.turnouts}
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
                    fars.append(le_masts.end_xy(P, turnouts, end))
                a, b = fars
                u = le.unit(le.sub(b, a))
                self.assertLess(abs(le.cross(u, le.sub(p, a))), 0.01)            # on the line
                self.assertLess(abs(le.cross(u, le.sub(was, a))), 0.01)
                t = le.dot(le.sub(p, a), u)
                self.assertGreaterEqual(t, min(P.cellx[lower()], le.dot(le.sub(was, a), u)) - 0.01)
                self.assertLessEqual(t, math.dist(a, b) - min(P.cellx[lower()],
                                                              math.dist(a, b) - le.dot(le.sub(was, a), u)) + 0.01)


class Icons(unittest.TestCase):
    def test_icons_clear_of_turnouts_tracks_labels_and_each_other(self):
        P, _found, masts = built(dense=False)
        self.assertGreater(len(masts), 4)
        world = le_masts.World(P)
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
        world = le_masts.World(P)
        first = {}
        for m in P.masts:
            p, d = ix.travel(m["kind"], m["ident"], m["slot"])
            first[m["mast"]] = (le_masts.icon_rect(p, d, m["size"], slots.GAP, slots.GAP), p, m)

        def trouble(rects):
            bad = 0
            for name, (r, p, m) in rects.items():
                own = set(le_masts._facing(ix, m, p, ix.travel(m["kind"], m["ident"], m["slot"])[1])[1])
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
        first = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)
        touch = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, le_masts.TOUCH)
        self.assertIn("other", le_masts.spot_cost(first, near, {"own"}, set(), [])[1])
        self.assertEqual(le_masts.spot_cost(touch, near, {"own"}, set(), [])[1], ["graze"])

    def test_a_turnout_body_is_never_a_clean_spot(self):
        near = ({"own": [((-100, 0), (0, 0))]}, {"T": ((10, 0), [((10, 0), (22, 0)), ((10, 0), (-2, 0))])}, [], [])
        at = le_masts.icon_rect((0, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)
        self.assertNotIn("turnout", le_masts.spot_cost(at, near, {"own"}, set(), [])[1])
        over = le_masts.icon_rect((20, 0), (1, 0), slots.ICON, slots.GAP, slots.GAP)
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
