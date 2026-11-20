"""The label layer of the generated Layout Editor panel (le_labels): switch numbers, track names, one block contents
icon per block and station names, each in a clean spot sized as JMRI draws it, checked from scratch."""
import copy
from collections import defaultdict
import math
import unittest
import xml.etree.ElementTree as ET

import helpers
from schematic import jmri_text, le, le_labels
from schematic.core import SchematicError
from unittest import mock
from test_le import bands


def panel(opts=None):
    """The example's panel, with `opts` as every band's le_labels; built once per test run."""
    key = ("le_labels", repr(opts))
    if key not in helpers._cache:
        helpers._cache[key] = le.panel(with_opts(opts))
    return helpers._cache[key]


def with_opts(opts, where="band"):
    out = []
    for t, b, o in bands():
        o = dict(o)
        if opts is not None and where == "band":
            o["le_labels"] = opts
        out.append((t, b, o))
    return out


def boxes(P):
    return [le_labels.box_of(*lb["box"]) for lb in P.labels] + [le_labels.box_of(*b["box"]) for b in P.bcis]


class Placed(unittest.TestCase):
    def test_every_item_is_placed_once(self):
        P = panel()
        numbers = sorted(lb["text"] for lb in P.labels if lb["kind"] == "switch")
        want = sorted(bands()[t["band"]][1]["nodes"][t["nodes"][0]]["label"] for t in P.turnouts
                      if bands()[t["band"]][1]["nodes"][t["nodes"][0]].get("label"))
        self.assertEqual(numbers, want)
        named = [k for k in P.strand_segments if bands()[k[0]][1]["strands"][k[1]]["name"]]
        self.assertEqual(len([lb for lb in P.labels if lb["kind"] == "name"]), len(named))
        self.assertEqual(sorted(b["block"] for b in P.bcis), sorted(P.blocks))       # one icon per block
        kinds = {b["block"]: b["kind"] for b in P.bcis}
        for t in P.turnouts:
            for blk in t["blocks"].values():
                self.assertEqual(kinds[blk], "os", blk)

    def test_boxes_are_what_jmri_draws_and_nothing_overlaps(self):
        P = panel()
        for lb in P.labels:
            x, y, w, h = lb["box"]
            self.assertEqual((x, y), (round(lb["xy"][0]), round(lb["xy"][1])))
            self.assertEqual(w, jmri_text.width(lb["text"], lb["size"], lb["bold"]))
            self.assertEqual(h, jmri_text.height(lb["size"], lb["bold"]))
        for b in P.bcis:
            self.assertEqual(b["box"][2:], (jmri_text.width("OCS-1234", 13), jmri_text.height(13)))
        bx = boxes(P)
        for i, a in enumerate(bx):
            for b in bx[i + 1:]:
                self.assertFalse(le_labels.boxes_overlap(a, b, -le_labels.OVERLAP), (a, b))
        le_labels.verify(P)

    def test_a_switch_number_reads_as_its_own_turnout(self):
        P = panel()
        L = le_labels.Layer(P, bands(), le_labels.options(bands(), None))
        marks = [(p, t["ident"]) for t in P.turnouts for p in L.halves(t).values()]
        for lb in P.labels:
            if lb["kind"] != "switch":
                continue
            box = le_labels.box_of(*lb["box"])
            mine = [t["ident"] for t in P.turnouts
                    if bands()[t["band"]][1]["nodes"][t["nodes"][0]].get("label") == lb["text"]]
            near = min(marks, key=lambda m: le_labels.point_gap(box, m[0]))
            self.assertIn(near[1], mine, lb["text"])

    def test_xml_writes_dialog_labels_and_block_contents_icons(self):
        P = panel()
        el = le.to_xml(P, "Generated")
        for lb in el.iter("positionablelabel"):
            self.assertEqual((lb.get("fontFamily"), lb.get("fontname")), ("Dialog", "Dialog"))
        icons = el.findall("BlockContentsIcon")
        self.assertEqual(len(icons), len(P.blocks))
        self.assertEqual(sorted(i.get("blockcontents") for i in icons), sorted(P.blocks))
        want = dict(level="4", forcecontroloff="false", hidden="no", positionable="true", showtooltip="true",
                    editable="true", size="13", style="0", red="0", green="0", blue="0", hasBackground="no",
                    justification="left", selectable="no", fontFamily="Dialog", fontname="Dialog",
                    **{"class": "jmri.jmrit.display.configurexml.BlockContentsIconXml"})
        for i in icons:
            self.assertEqual({k: i.get(k) for k in want}, want)
            int(i.get("x")), int(i.get("y"))
        self.assertIn("block contents icons", le.summary(P))

    def test_extent_holds_every_icon(self):
        P = panel()
        box = le.extent(P)
        for b in P.bcis:
            x, y, w, h = b["box"]
            self.assertTrue(box[0] <= x and x + w <= box[2] and box[1] <= y and y + h <= box[3])
            self.assertGreaterEqual(min(x, y), le.MARGIN)


class Options(unittest.TestCase):
    def test_switch_style_and_no_block_contents(self):
        P = panel({"switch_prefix": "SW-", "switch_size": 13, "block_contents": False})
        numbers = [lb for lb in P.labels if lb["kind"] == "switch"]
        self.assertTrue(numbers)
        self.assertTrue(all(lb["text"].startswith("SW-") and lb["size"] == 13 and lb["bold"] for lb in numbers))
        self.assertEqual(P.bcis, [])
        self.assertEqual(le.to_xml(P, "G").findall("BlockContentsIcon"), [])

    def test_a_band_overrides_the_page(self):
        b = with_opts({"switch_prefix": "B-"})
        page = dict(b[-1][2], le_labels={"switch_prefix": "P-", "block_contents": False})
        b = [(t, band, {k: v for k, v in o.items() if k != "le_labels"} if i == 0 else o)
             for i, (t, band, o) in enumerate(b)]
        opts = le_labels.options(b, page)
        self.assertEqual((opts[0]["switch_prefix"], opts[1]["switch_prefix"]), ("P-", "B-"))
        self.assertEqual((opts[0]["block_contents"], opts[1]["block_contents"]), (False, False))

    def test_bad_options_stop_before_drawing(self):
        bad = ["x", {"colour": 1}, {"switch_size": "9"}, {"switch_size": 7}, {"switch_size": 29},
               {"block_contents_size": True}, {"block_contents": "yes"}, {"switch_bold": 1},
               {"block_contents_text": " "}, {"switch_prefix": 3}]
        for o in bad:
            with self.subTest(opts=o), self.assertRaisesRegex(SchematicError, "le_labels"):
                le_labels.options(with_opts(o), None)
            with self.subTest(page=o), self.assertRaisesRegex(SchematicError, "page: le_labels"):
                le_labels.options(with_opts(None), {"le_labels": o})
        with self.assertRaisesRegex(SchematicError, "le_labels: unknown key colour"):
            le.panel(with_opts({"colour": 1}))


class Errors(unittest.TestCase):
    def test_no_clean_spot_stops_naming_the_item(self):
        with self.assertRaisesRegex(SchematicError, r"block contents of .*: no clean spot for it among \d+ tried \("):
            le.panel(with_opts({"block_contents_text": "W" * 60, "block_contents_size": 28}))

    def test_an_optional_block_contents_icon_is_left_out(self):
        """optional_block_contents: an icon with no clean spot at either reserve is left out and logged; every other
        icon still stops."""
        big = {"block_contents_text": "W" * 60, "block_contents_short": "W" * 50, "block_contents_size": 28}
        P = le.panel(with_opts(dict(big, optional_block_contents=sorted(panel().blocks))))
        self.assertTrue(P.bcis_skipped)
        self.assertEqual(len(P.bcis) + len(P.bcis_skipped), len(panel().blocks))
        self.assertTrue(all("optional_block_contents: left out" in line for line in P.log
                            if "optional_block_contents" in line))
        for bad in ({"optional_block_contents": "Main"}, {"optional_block_contents": [3]}):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "optional_block_contents"):
                le_labels.options(with_opts(bad), None)
        P = le.panel(with_opts({"optional_block_contents": ["Nowhere"]}))     # not drawn here (--band): logged
        self.assertTrue(any("optional_block_contents: block Nowhere is not drawn on this panel (ignored)" in line
                            for line in P.log))

    def test_optional_icons_are_a_bands_own(self):
        P = le.draw_panel(bands(), None, le.CELL, le.ROW, None, labels=False)
        L = le_labels.Layer(P, bands(), le_labels.options(bands(), None))
        places = le_labels.block_places(P, L)
        of = {b: le_labels.block_band(L, places, b) for b in P.blocks}
        upper = next(b for b, bi in of.items() if bi == 0)
        lower = next(b for b, bi in of.items() if bi == 1)
        b = with_opts(None)
        b[0][2]["le_labels"] = {"optional_block_contents": [upper, lower]}      # Upper lists one of Lower's too
        got = le_labels.optional_icons(P, L, b, le_labels.options(b, None))
        self.assertEqual(got, {("bci", upper)})

    def test_an_optional_icon_is_never_put_first_nor_chooses_the_round(self):
        big = {"block_contents_text": "W" * 60, "block_contents_short": "W" * 50, "block_contents_size": 28}
        firsts = []
        real = le_labels.place_round

        def watch(L, items, first, again=()):
            firsts.append(list(first))
            return real(L, items, first, again)
        with mock.patch.object(le_labels, "place_round", watch):
            P = le.panel(with_opts(dict(big, optional_block_contents=sorted(panel().blocks))))
        self.assertTrue(P.bcis_skipped)
        self.assertFalse([k for f in firsts for k in f if k[0] == "bci"])
        self.assertLessEqual(len(firsts), 4)            # only optional icons failing: no reordering rounds

    def test_not_strict_an_item_with_no_spot_is_listed_not_raised(self):
        b = with_opts({"block_contents_text": "W" * 60, "block_contents_size": 28})
        P = le.draw_panel(b, None, le.CELL, le.ROW, None, labels=False)
        le_labels.place(P, b, le_labels.options(b, None), strict=False)
        self.assertTrue(P.labels_unplaced)
        self.assertTrue(all("no clean spot" in why for _k, why in P.labels_unplaced))
        self.assertLess(len(P.bcis), len(P.blocks))

    def test_unknown_font_size_stops(self):
        for size in (7, 29, 12.5):
            with self.subTest(size=size), self.assertRaisesRegex(SchematicError, "no Dialog font metrics"):
                jmri_text.width("SW-1", size)
        self.assertGreater(jmri_text.width("é", 10), 0)       # outside ASCII: the widest character, no error

    def test_the_check_catches_an_overlap_and_a_label_on_track(self):
        P = copy.deepcopy(panel())
        name = next(lb for lb in P.labels if lb["kind"] == "name")
        P.bcis[0]["box"] = name["box"]
        with self.assertRaisesRegex(SchematicError, "le labels: .* overlaps"):
            le_labels.verify(P)
        P = copy.deepcopy(panel())
        seg = next(s for s in P.segments if not s["hidden"] and not s["arc"])
        a = P.points[seg["ends"][0][0]]["xy"] if seg["ends"][0][1] == "POS_POINT" else None
        a = a or next(t for t in P.turnouts if t["ident"] == seg["ends"][0][0])["pts"][seg["ends"][0][1][-1]]
        lb = next(lb for lb in P.labels if lb["kind"] == "switch")
        lb["box"] = (round(a[0]) - 2, round(a[1]) - 2, lb["box"][2], lb["box"][3])
        P.labels = [lb]                     # alone, so it can only lie on the track
        P.bcis = []
        with self.assertRaisesRegex(SchematicError, "le labels: label .* lies on"):
            le_labels.verify(P)

    def test_a_block_with_nothing_drawn_stops(self):
        P = copy.deepcopy(panel())
        P.labels = [lb for lb in P.labels if lb["kind"] in le_labels.FIXED]
        P.blocks.add("Nowhere")
        with self.assertRaisesRegex(SchematicError, "block Nowhere: nothing of it is drawn"):
            le_labels.place(P, bands(), le_labels.options(bands(), None))


class Geometry(unittest.TestCase):
    def test_the_label_layer_changes_nothing_of_the_drawing(self):
        import test_le_masts
        names, _found, _masts = test_le_masts.names_for(False)
        b = with_opts({"block_contents": False})        # the mast fixture's blocks are too crowded for icons
        bare = le.draw_panel(b, names, le.CELL, le.ROW, None, labels=False)
        full = le.draw_panel(b, names, le.CELL, le.ROW, None)
        self.assertTrue(full.masts)
        self.assertEqual(le.geometry(bare), le.geometry(full))
        self.assertTrue(any(lb["kind"] == "switch" for lb in full.labels))
        plain = le.draw_panel(bands(), None, le.CELL, le.ROW, None, labels=False)
        self.assertEqual(le.geometry(plain), le.geometry(panel()))

    def test_a_layer_that_moves_the_drawing_stops(self):
        real = le_labels.place

        def moving(P, *a, **k):
            real(P, *a, **k)
            pid = next(iter(P.points))
            P.points[pid]["xy"][0] += 1
        with mock.patch.object(le_labels, "place", moving), \
                self.assertRaisesRegex(SchematicError, "the label layer changed the drawing: point "):
            le.panel(bands())


REAL_ALONG = le_labels.along
ICON_W = jmri_text.width("OCS-1234", 13)


def no_room_beside_icons(lines, w, h, first):
    """le_labels.along with no spot beside a long track (over 150 px) for a block contents icon; names and the
    icons of shorter tracks keep theirs."""
    long = sum(math.dist(a, b) for a, b in lines) > 150
    return iter(()) if w == ICON_W and long else REAL_ALONG(lines, w, h, first)


class OnTrack(unittest.TestCase):
    def test_with_no_room_beside_a_track_icon_stands_on_its_own_block(self):
        with mock.patch.object(le_labels, "along", no_room_beside_icons):
            P = le.panel(bands())
        track = [b for b in P.bcis if b["on_track"]]
        self.assertGreaterEqual(len(track), 2)
        self.assertTrue(all(b["kind"] == "track" for b in track))
        self.assertEqual(sum("stands on its own block's track" in line for line in P.log), len(track))
        from schematic import le_masts
        from schematic.label_check import _pt_seg
        world = le_masts.World(le_masts.PanelView(P))
        block_of = {x["ident"]: x["block"] for x in P.segments}
        for b in track:                                     # centred on a rail of its own block
            x, y, w, h = b["box"]
            mid = (x + w / 2, y + h / 2)
            lines = [ab for sid, pcs in world.track.items() if block_of[sid] == b["block"] for ab in pcs]
            self.assertLessEqual(min(_pt_seg(mid, *ab) for ab in lines), 1.0, b)
        le_labels.verify(P)                                 # its own block's line is no fault
        el = le.to_xml(P, "G")
        self.assertTrue(all(i.get("hasBackground") == "no" for i in el.findall("BlockContentsIcon")))

    def test_on_another_blocks_track_is_still_a_fault(self):
        with mock.patch.object(le_labels, "along", no_room_beside_icons):
            P = copy.deepcopy(le.panel(bands()))
        b = next(b for b in P.bcis if b["on_track"])
        b["block"] = next(x["block"] for x in P.bcis if x is not b and x["kind"] == "track")
        with self.assertRaisesRegex(SchematicError, "lies on a track"):
            le_labels.verify(P)


class ShortReserve(unittest.TestCase):
    def test_an_icon_with_no_spot_at_full_size_takes_the_short_reserve(self):
        P = le.panel(with_opts({"block_contents_text": "W" * 30}))        # 330 px: too wide for many spots
        self.assertEqual(sorted(b["block"] for b in P.bcis), sorted(P.blocks))
        short = [b for b in P.bcis if b["short"]]
        self.assertTrue(short)
        full_w, short_w = jmri_text.width("W" * 30, 13), jmri_text.width("OCS-1", 13)
        for b in P.bcis:
            self.assertEqual(b["box"][2], short_w if b["short"] else full_w, b)
        lines = [line for line in P.log if "placed" in line and "short reserve 'OCS-1'" in line]
        self.assertEqual(len(lines), len(short))
        self.assertTrue(all(any(b["block"] in line for line in lines) for b in short))
        le_labels.verify(P)

    def test_with_no_room_at_the_short_reserve_either_it_stops(self):
        with self.assertRaisesRegex(SchematicError, "block contents of .*: no clean spot for it"):
            le.panel(with_opts({"block_contents_text": "W" * 60, "block_contents_short": "W" * 50,
                                "block_contents_size": 28}))

    def test_the_short_reserve_is_checked(self):
        for o in ({"block_contents_short": ""}, {"block_contents_short": 5},
                  {"block_contents_short": "OCS-12345"}, {"block_contents_text": "OCS", "block_contents_short": "OCS"}):
            with self.subTest(opts=o), self.assertRaisesRegex(SchematicError, "le_labels"):
                le_labels.options(with_opts(o), None)


REAL_TRACK_NAME = le_labels._track_name


def no_room_for_names(L, bi, text, mine, cx=None):
    make = REAL_TRACK_NAME(L, bi, text, mine, cx)
    return lambda state, short=False: (lambda got: got and (got[0], iter(()), got[2]))(make(state, short))


class ByBand(unittest.TestCase):
    def test_a_bands_labels_are_the_same_whatever_is_drawn_below_it(self):
        def placed(P, bi):
            return sorted((lb["text"], tuple(lb["box"])) for lb in P.labels if lb["band"] == bi) + \
                sorted((b["block"], tuple(b["box"])) for b in P.bcis if b["band"] == bi)
        b = bands()
        # the lower band's labels made much harder to place: the upper band's stay where they were
        hard = [b[0]] + [(t, band, dict(o, le_labels={"block_contents_text": "OCS-123456"}))
                         for t, band, o in b[1:]]
        both = le.panel(b, labels_by_band=True)
        self.assertEqual(placed(le.panel(hard, labels_by_band=True), 0), placed(both, 0))
        self.assertNotEqual(placed(le.panel(hard, labels_by_band=True), 1), placed(both, 1))
        self.assertEqual(sorted(x["block"] for x in both.bcis), sorted(both.blocks))
        le_labels.verify(both)
        with self.assertRaisesRegex(SchematicError, "labels_by_band must be true or false"):
            le.panel(b, labels_by_band="yes")

    def test_by_band_is_the_same_as_one_round_for_one_band(self):
        b = bands()[:1]
        one, by = le.panel(b), le.panel(b, labels_by_band=True)
        self.assertEqual([(lb["text"], lb["box"]) for lb in one.labels], [(lb["text"], lb["box"]) for lb in by.labels])
        self.assertEqual([(x["block"], x["box"]) for x in one.bcis], [(x["block"], x["box"]) for x in by.bcis])


class NameColumns(unittest.TestCase):
    def test_a_groups_names_stand_on_one_centre_x(self):
        b = bands()
        lower = next(i for i, (t, _b, _o) in enumerate(b) if t.startswith("Lower"))
        P0 = le.panel(b)
        level = [lb["text"] for lb in P0.labels if lb["kind"] == "name" and lb["band"] == lower]
        groups = []
        for i, t1 in enumerate(level):          # two names whose tracks run level side by side somewhere
            for t2 in level[i + 1:]:
                try:
                    P = le.panel([(t, band, dict(o, le_labels={"name_columns": [[t1, t2]]}) if k == lower else o)
                                  for k, (t, band, o) in enumerate(b)])
                except SchematicError:
                    continue
                groups.append((t1, t2, P))
        self.assertTrue(groups, "no pair of level tracks side by side in the example")
        t1, t2, P = groups[0]
        centres = {lb["text"]: lb["box"][0] + lb["box"][2] / 2 for lb in P.labels if lb["text"] in (t1, t2)}
        self.assertAlmostEqual(centres[t1], centres[t2], delta=1.0)    # whole pixels
        le_labels.verify(P)

    def test_name_columns_are_checked(self):
        for bad in ("S-1", [["S-1"]], [["S-1", ""]], [["A", "B"], ["B", "C"]]):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "name_columns"):
                le_labels.options(with_opts({"name_columns": bad}), None)
        with self.assertRaisesRegex(SchematicError, "name_columns names Nowhere"):
            le.panel(with_opts({"name_columns": [["Nowhere", "Else"]]}))


class NameSteps(unittest.TestCase):
    def level_west_and_run(self, P, bi, name):
        """(x of the west end, px) of a named track's level run, from the drawn segments."""
        from schematic.le_masts import PanelView
        view = PanelView(P)
        segs = {s["ident"]: s for s in P.segments}
        xs = []
        for (b, sid), idents in P.strand_segments.items():
            if b != bi or le_labels.tidy([le.drawn_bands(bands())[bi][1]["strands"][sid].get("name") or ""])[0] != name:
                continue
            for i in idents:
                a, c = (view.xy(e) for e in segs[i]["ends"])
                if not segs[i]["arc"] and abs(a[1] - c[1]) < 1e-6:
                    xs += [a[0], c[0]]
        return min(xs), max(xs) - min(xs)

    def test_a_groups_names_stand_the_same_way_in_from_their_tracks_west_ends(self):
        b = bands()
        lower = next(i for i, (t, _b, _o) in enumerate(b) if t.startswith("Lower"))
        level = [lb["text"] for lb in le.panel(b).labels if lb["kind"] == "name" and lb["band"] == lower]
        P = None
        for i, t1 in enumerate(level):
            for t2 in level[i + 1:]:
                try:
                    P = le.panel([(t, band, dict(o, le_labels={"name_steps": [[t1, t2]]}) if k == lower else o)
                                  for k, (t, band, o) in enumerate(b)])
                except SchematicError:
                    continue
                break
            if P is not None:
                break
        self.assertIsNotNone(P, "no pair of level tracks whose names fit stepped in the example")
        runs = {n: self.level_west_and_run(P, lower, n) for n in (t1, t2)}
        inset = min(r for _w, r in runs.values()) / 2
        for lb in P.labels:
            if lb["kind"] == "name" and lb["band"] == lower and lb["text"] in runs:
                self.assertAlmostEqual(lb["box"][0] + lb["box"][2] / 2, runs[lb["text"]][0] + inset, delta=1.0)
        le_labels.verify(P)

    def test_the_west_level_run_stops_at_a_climb(self):
        lines = [((0, 5), (10, 5)), ((10, 5), (20, 5)), ((20, 5), (30, 0)), ((30, 0), (50, 0))]
        self.assertEqual(le_labels.west_level_run(lines), (0, 20))
        self.assertIsNone(le_labels.west_level_run([((0, 0), (5, 5))]))

    def test_name_steps_are_checked(self):
        for bad in ("S-1", [["S-1"]], [["S-1", ""]], [["A", "B"], ["B", "C"]]):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "name_steps"):
                le_labels.options(with_opts({"name_steps": bad}), None)
        with self.assertRaisesRegex(SchematicError, "A in both name_columns and name_steps"):
            le_labels.options(with_opts({"name_steps": [["A", "B"]], "name_columns": [["A", "C"]]}), None)
        with self.assertRaisesRegex(SchematicError, "A in both name_columns and name_steps \\(from the page's"):
            le_labels.name_step_x(None, [("Lower", {}, {})], [{"name_steps": [["A", "B"]],
                                                               "name_columns": [["A", "C"]]}], [])
        with self.assertRaisesRegex(SchematicError, "name_steps names Nowhere"):
            le.panel(with_opts({"name_steps": [["Nowhere", "Else"]]}))


class LampColumns(unittest.TestCase):
    def test_a_groups_lamps_are_kept_clear_on_one_x_on_their_tracks(self):
        b = bands()
        lower = next(i for i, (t, _b, _o) in enumerate(b) if t.startswith("Lower"))
        P0 = le.panel(b)
        level = [lb["text"] for lb in P0.labels if lb["kind"] == "name" and lb["band"] == lower]
        P = None
        for i, t1 in enumerate(level):
            for t2 in level[i + 1:]:
                try:
                    P = le.panel([(t, band, dict(o, le_labels={"lamp_columns": [[t1, t2]]}) if k == lower else o)
                                  for k, (t, band, o) in enumerate(b)])
                except SchematicError:
                    continue
                break
            if P is not None:
                break
        self.assertIsNotNone(P, "no pair of level tracks side by side in the example")
        self.assertEqual(len(P.lamps), 2)
        self.assertEqual(len({lp["box"][0] for lp in P.lamps}), 1)              # one x
        boxes = [le_labels.box_of(*x["box"]) for x in P.labels + P.bcis]
        for lp in P.lamps:
            self.assertEqual(lp["box"][2:], (10, 10))
            mine = le_labels.box_of(*lp["box"])
            self.assertFalse([x for x in boxes if le_labels.boxes_overlap(mine, x, -le_labels.OVERLAP)])
        le_labels.verify(P)
        for bad in ({"lamp_size": [10]}, {"lamp_size": [0, 4]}, {"lamp_columns": [["A"]]}):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "lamp_"):
                le_labels.options(with_opts(bad), None)


class NumbersBelow(unittest.TestCase):
    def test_a_switch_in_numbers_below_takes_a_spot_below_its_turnout_first(self):
        from test_le import crossover_band
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            for below, side in (([], "above"), (["7"], "below")):
                (t, b, o), = crossover_band()
                P = le.panel([(t, b, dict(o, le_labels={"numbers_below": below}))])
                x = P.turnouts[0]
                number = next(lb for lb in P.labels if lb.get("kind") == "switch")
                ys = [p[1] for p in x["pts"].values()]
                with self.subTest(below=below):
                    if side == "below":
                        self.assertGreaterEqual(number["box"][1], max(ys))
                    else:
                        self.assertLessEqual(number["box"][1] + number["box"][3], min(ys))
        for bad in ({"numbers_below": "7"}, {"numbers_below": [7]}, {"numbers_below": [" "]}):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "numbers_below"):
                le_labels.options(with_opts(bad), None)


class CrossoverRun(unittest.TestCase):
    def test_every_single_crossover_runs_the_same_distance_across(self):
        from test_le import crossover_band
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            base = le.panel(crossover_band())
            P = le.panel(crossover_band(), crossover_run=20.0)
        t0, t = base.turnouts[0], P.turnouts[0]
        mid = lambda q, a, b: ((q[a][0] + q[b][0]) / 2)          # noqa: E731
        self.assertAlmostEqual(mid(t["pts"], "D", "C") - mid(t["pts"], "A", "B"), 20.0)
        self.assertAlmostEqual(t["cen"][0], t0["cen"][0])          # about its middle
        with mock.patch.object(le, "paths", lambda band: band["_drawn"]):
            wide = le.panel(crossover_band(), crossover_run=10000.0)          # no room for it: as much as there is
        t = wide.turnouts[0]
        self.assertLess(mid(t["pts"], "D", "C") - mid(t["pts"], "A", "B"), 10000.0)
        self.assertTrue(any("crossover drawn" in line and "degrees: no room for" in line for line in wide.log))
        for bad in (0, -1, "9", True):
            with self.subTest(run=bad), self.assertRaisesRegex(SchematicError, "crossover_run"):
                le.panel(bands(), crossover_run=bad)
        with self.assertRaisesRegex(SchematicError, "not one fitted"):
            le.panel(bands(), crossover_run=10.0, fit=(1300, 700))


class Spots:
    """A stand-in for le_labels.Layer in place_items: each item takes the first of its spots no one holds (a spot is
    a name, so two items clash only on the same one)."""

    def __init__(self):
        self.held, self.notes, self.boxes = {}, [], None

    def reset(self):
        self.held, self.notes = {}, []

    def take(self, item, spots):
        for s in spots:
            if s not in self.held:
                self.held[s] = (item["what"], item["kind"], item.get("key"))
                return s, None
        return None, f"{item['what']}: no clean spot"

    def in_way(self, item, spot, kinds):
        thing = self.held.get(spot)
        return [] if thing is None else [(thing, spot)] if thing[1] in kinds else None

    @staticmethod
    def as_placed(box):
        return box

    def lift(self, things):
        saved = dict(self.held)
        self.held = {s: t for s, t in self.held.items() if t not in things}
        return saved

    def restore(self, saved):
        self.held = saved


def spot_items(want, short=None):
    """[(key, make)]: one item per (key, spots), each placing at the first free spot of its list; a block contents
    icon (key ("bci", block)) at its short reserve at the first free spot of short[key] (default: the same spots)."""
    short = short or {}

    def maker(key, spots):
        icon = key[0] == "bci"

        def make(state, short_reserve=False):
            item = dict(what=str(key), kind=le_labels.ICON_KIND if icon else "a track name", key=key)
            if icon:
                return (item, list(short.get(key, spots) if short_reserve else spots),
                        lambda box: ("bci", dict(block=key[1], key=key, box=box)))
            return item, list(spots), lambda box: ("label", dict(key=key, box=box))
        return lambda state, short=False: make(state, short)
    return [(key, maker(key, spots)) for key, spots in want]


class NamesLast(unittest.TestCase):
    def test_a_name_left_out_is_tried_first_and_kept_when_everything_still_stands(self):
        """The icon takes the name's only spot when the name goes last; tried first, the name has it and the icon
        its second choice, so the name leads. A name whose lead would leave a needed item without a spot does not."""
        name, icon, other = ("name", 1, "s1"), ("bci", "Block A"), ("name", 1, "s2")
        items = spot_items([(icon, ["S", "T"]), (name, ["S"])])
        done, failed, skipped = le_labels.place_items(Spots(), items, {name}, set())
        self.assertEqual((failed, skipped), ([], []))
        self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), [(icon, "T"), (name, "S")])
        items = spot_items([(icon, ["S"]), (other, ["S"])])         # the icon has no other spot: the name stays out
        done, failed, skipped = le_labels.place_items(Spots(), items, {other}, set())
        self.assertEqual(failed, [])
        self.assertEqual([k for k, _w in skipped], [other])
        self.assertEqual([(d["key"], d["box"]) for _k, d in done], [(icon, "S")])

    def room(self, L, items, done, skipped):
        return le_labels.make_room(L, items, done, [], [(k, f"{k}: no clean spot") for k in skipped],
                                   dict(number_side={}, name_side={}))

    def test_a_name_left_out_takes_an_icons_spot_when_the_icon_has_another(self):
        """make_room: the name's first spot held only by an icon; the icon moves to its next clean spot and both
        stand, logged. Where the icon has no other spot at full size, it takes its short reserve."""
        name, icon = ("name", 1, "s1"), ("bci", "Block A")
        for short, where in ({}, "T"), ({icon: ["U"]}, "U"):
            with self.subTest(short=short):
                items = spot_items([(icon, ["S", "T"] if not short else ["S"]), (name, ["S"])], short)
                L = Spots()
                L.held = {"S": (str(icon), le_labels.ICON_KIND, icon)}
                done, failed, skipped = self.room(L, items, [("bci", dict(block="Block A", key=icon, box="S"))],
                                                  [name])
                self.assertEqual((failed, skipped), ([], []))
                self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), [(icon, where), (name, "S")])
                self.assertEqual(L.held, {"S": (str(name), "a track name", name), where: (str(icon), le_labels.ICON_KIND, icon)})
                self.assertTrue(any("room made" in n for n in L.notes))

    def test_a_name_stays_out_when_the_icon_has_no_other_spot_and_everything_is_put_back(self):
        name, icon = ("name", 1, "s1"), ("bci", "Block A")
        items = spot_items([(icon, ["S"]), (name, ["S"])], {icon: []})
        L = Spots()
        L.held = {"S": (str(icon), le_labels.ICON_KIND, icon)}
        before = [("bci", dict(block="Block A", key=icon, box="S"))]
        done, failed, skipped = self.room(L, items, list(before), [name])
        self.assertEqual((done, failed, [k for k, _w in skipped]), (before, [], [name]))
        self.assertEqual((L.held, L.notes), ({"S": (str(icon), le_labels.ICON_KIND, icon)}, []))

    def test_icons_move_first_then_a_name_with_another_spot(self):
        """The first pass moves only icons: a spot another name holds is passed over for the next, held by an icon
        that has another. When no icon can move, a name in the way that has another spot of its own moves."""
        name, other, icon = ("name", 1, "s1"), ("name", 1, "s2"), ("bci", "Block A")
        for other_spots, icon_spots, want in ((["R", "Q"], ["S", "T"], [(other, "R"), (icon, "T"), (name, "S")]),
                                              (["R", "Q"], ["S"], [(other, "Q"), (icon, "S"), (name, "R")]),
                                              (["R"], ["S"], None)):
            with self.subTest(other=other_spots, icon=icon_spots):
                items = spot_items([(other, other_spots), (icon, icon_spots), (name, ["R", "S"])], {icon: []})
                L = Spots()
                L.held = {"R": (str(other), "a track name", other), "S": (str(icon), le_labels.ICON_KIND, icon)}
                before = [("label", dict(key=other, box="R")), ("bci", dict(block="Block A", key=icon, box="S"))]
                done, _failed, skipped = self.room(L, items, list(before), [name])
                if want is None:
                    self.assertEqual(([k for k, _w in skipped], done), ([name], before))
                    continue
                self.assertEqual(skipped, [])
                self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), sorted(want))

    def test_a_moved_icon_may_move_another_one_step_deeper_and_no_further(self):
        """The name's spot S is held by icon A, whose other spot T is held by icon B, which has U free: all three
        stand (ROOM_DEPTH 2). One more step (B's U held by C, free V) is past the depth: nothing moves."""
        name, a, b, c = ("name", 1, "s1"), ("bci", "A"), ("bci", "B"), ("bci", "C")
        none = {a: [], b: [], c: []}
        items = spot_items([(a, ["S", "T"]), (b, ["T", "U"]), (name, ["S"])], none)
        L = Spots()
        L.held = {"S": (str(a), le_labels.ICON_KIND, a), "T": (str(b), le_labels.ICON_KIND, b)}
        done, _f, skipped = self.room(L, items, [("bci", dict(block="A", key=a, box="S")),
                                                 ("bci", dict(block="B", key=b, box="T"))], [name])
        self.assertEqual(skipped, [])
        self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), sorted([(name, "S"), (a, "T"), (b, "U")]))
        items = spot_items([(a, ["S", "T"]), (b, ["T", "U"]), (c, ["U", "V"]), (name, ["S"])], none)
        L = Spots()
        L.held = {"S": (str(a), le_labels.ICON_KIND, a), "T": (str(b), le_labels.ICON_KIND, b),
                  "U": (str(c), le_labels.ICON_KIND, c)}
        held = dict(L.held)
        before = [("bci", dict(block=k[1], key=k, box=s)) for k, s in ((a, "S"), (b, "T"), (c, "U"))]
        done, _f, skipped = self.room(L, items, list(before), [name])
        self.assertEqual(([k for k, _w in skipped], done, L.held, L.notes), ([name], before, held, []))

    def test_an_item_that_failed_gets_room_and_names_only_when_asked(self):
        """make_room(names=False) (a lead trial): an icon that found no spot moves another icon; a name left out
        is not tried. A left-out name whose spot has come free just takes it."""
        need, icon, name = ("bci", "Need"), ("bci", "Other"), ("name", 1, "s1")
        items = spot_items([(icon, ["S", "T"]), (need, ["S"]), (name, ["W"])], {need: [], icon: []})
        L = Spots()
        L.held = {"S": (str(icon), le_labels.ICON_KIND, icon)}
        done, failed, skipped = le_labels.make_room(
            L, items, [("bci", dict(block="Other", key=icon, box="S"))], [(need, "no spot")], [(name, "no spot")],
            dict(number_side={}, name_side={}), names=False)
        self.assertEqual((failed, [k for k, _w in skipped]), ([], [name]))
        self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), [(need, "S"), (icon, "T")])
        done, failed, skipped = self.room(L, items, done, [name])
        self.assertEqual((failed, skipped), ([], []))
        self.assertIn((name, "W"), [(d["key"], d["box"]) for _k, d in done])

    def test_an_item_placed_by_an_earlier_band_stands_where_it_is(self):
        """Placing by band, what an earlier band placed is in L's boxes but not among this band's items: make_room
        treats it as fixed. A spot only it holds is passed over (no error), and room is made at the next spot."""
        name, mine, earlier = ("name", 1, "s1"), ("bci", "Mine"), ("bci", "Earlier")
        for mine_spots, want in ((["T", "U"], [(mine, "U"), (name, "T")]), (["T"], None)):
            with self.subTest(mine=mine_spots):
                items = spot_items([(mine, mine_spots), (name, ["S", "T"])], {mine: []})
                L = Spots()
                L.held = {"S": (str(earlier), le_labels.ICON_KIND, earlier), "T": (str(mine), le_labels.ICON_KIND, mine)}
                before = [("bci", dict(block="Mine", key=mine, box="T"))]
                done, failed, skipped = self.room(L, items, list(before), [name])
                self.assertEqual(failed, [])
                self.assertEqual(L.held["S"], (str(earlier), le_labels.ICON_KIND, earlier))
                if want is None:
                    self.assertEqual(([k for k, _w in skipped], done), ([name], before))
                else:
                    self.assertEqual(skipped, [])
                    self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), sorted(want))

    def test_items_sharing_one_text_move_apart(self):
        """Two track names on a band with one text share (what, kind); each box still names its own item (key), so
        making room moves only the one in the way and the other stays placed, once."""
        a, b, icon = ("name", 1, "s1"), ("name", 1, "s2"), ("bci", "Need")
        items = spot_items([(a, ["R"]), (b, ["S", "Q"]), (icon, ["S"])], {icon: []})

        def same_text(make):
            def made(state, short=False):
                got = make(state, short)
                if got and got[0]["kind"] == "a track name":
                    got[0]["what"] = "Band: track name X"
                return got
            return made
        items = [(k, same_text(m)) for k, m in items]
        L = Spots()
        what = "Band: track name X"
        L.held = {"R": (what, "a track name", a), "S": (what, "a track name", b)}
        done = [("label", dict(key=a, box="R")), ("label", dict(key=b, box="S"))]
        done, failed, skipped = le_labels.make_room(L, items, done, [(icon, "no spot")], [],
                                                    dict(number_side={}, name_side={}))
        self.assertEqual((failed, skipped), ([], []))
        self.assertEqual(sorted((d["key"], d["box"]) for _k, d in done), sorted([(a, "R"), (b, "Q"), (icon, "S")]))
        self.assertEqual(L.held, {"R": (what, "a track name", a), "Q": (what, "a track name", b),
                                  "S": (str(icon), le_labels.ICON_KIND, icon)})

    def test_keyed_items_carry_their_key(self):
        name = ("name", 1, "s1")
        (key, make), = le_labels.keyed(spot_items([(name, ["S"])]))
        self.assertEqual((key, make({})[0]["key"]), (name, name))
        (key, make), = le_labels.keyed([(name, lambda state, short=False: None)])
        self.assertIsNone(make({}))

    def test_nothing_left_out_is_returned_as_it_is(self):
        name = ("name", 1, "s1")
        got = le_labels.make_room(Spots(), spot_items([(name, ["S"])]), [], [], [(name, "x")], {}, names=False)
        self.assertEqual(got, ([], [], [(name, "x")]))
        self.assertEqual(le_labels.make_room(Spots(), [], [("label", {})], [], [], {}), ([("label", {})], [], []))

    def test_in_way_on_a_drawn_panel(self):
        """Layer.in_way: [] on a clean spot, what of the kinds asked is in the way when only that is, None when
        anything else is; lift and restore take those away and put them back."""
        b = bands()
        P = le.panel(b)
        L = le_labels.Layer(P, b, le_labels.options(b, None))
        it = L.item("a track name", "test name", "Test", L.name_size, False)
        spot = next((x, y) for y in range(20, P.size[1], 4) for x in range(20, P.size[0], 4)
                    if L.fault(le_labels.box_of(x, y, it["w"], it["h"]), it) is None)
        kinds = (le_labels.ICON_KIND,)
        self.assertEqual(L.in_way(it, spot, kinds), [])
        box = le_labels.box_of(spot[0], spot[1], it["w"], it["h"])
        icon = ("block contents of X", le_labels.ICON_KIND)
        L.boxes.add(box, icon)
        self.assertEqual(L.in_way(it, spot, kinds), [(icon, box)])
        self.assertEqual(L.as_placed(box), (box[0], box[1], box[2] - box[0], box[3] - box[1]))
        saved = L.lift([icon])
        self.assertEqual(L.in_way(it, spot, kinds), [])
        L.restore(saved)
        self.assertEqual(L.in_way(it, spot, kinds), [(icon, box)])
        name = ("a name", "a track name")
        L.boxes.add(box, name)
        self.assertIsNone(L.in_way(it, spot, kinds))
        self.assertEqual(L.in_way(it, spot, le_labels.MOVABLE), sorted([(icon, box), (name, box)]))

    def test_an_optional_icon_left_out_is_tried_first_too(self):
        opt, icon = ("bci", "Track 2"), ("bci", "Track 1")
        items = spot_items([(icon, ["S", "T"]), (opt, ["S"])])
        done, failed, skipped = le_labels.place_items(Spots(), items, set(), {opt})
        self.assertEqual((failed, skipped), ([], []))
        self.assertEqual(sorted(d["key"] for _k, d in done), sorted([icon, opt]))

    def test_a_names_last_band_leaves_out_a_name_with_no_room_and_logs_it(self):
        with mock.patch.object(le_labels, "_track_name", no_room_for_names):
            with self.assertRaisesRegex(SchematicError, "track name .*: no clean spot"):
                le.panel(bands())
            P = le.panel(with_opts({"names_last": True}))
        self.assertFalse([lb for lb in P.labels if lb["kind"] == "name"])
        self.assertTrue(P.names_skipped)
        self.assertEqual(len([line for line in P.log if "(names_last: left out)" in line]), len(P.names_skipped))
        self.assertEqual(sorted(b["block"] for b in P.bcis), sorted(P.blocks))
        le_labels.verify(P)

    def test_names_last_is_a_bands_own_option(self):
        b = with_opts(None)
        with self.assertRaisesRegex(SchematicError, "names_last is a band's own option"):
            le_labels.options(b, {"le_labels": {"names_last": True}})
        b[0][2]["le_labels"] = {"names_last": True}
        opts = le_labels.options(b, {"le_labels": {"switch_prefix": "P-"}})
        self.assertEqual([o["names_last"] for o in opts], [True, False])         # never spread to another band
        self.assertEqual(le_labels.options(b, b[0][2])[1]["names_last"], False)   # the band's own dict as the page

    def test_names_skipped_name_objects_by_their_written_idents(self):
        P = le.Panel()
        P.idents_given = {"TOG3": "TO117"}
        P.names_skipped = ["Lower level: track name Y-1: no clean spot near TOG3"]
        P.labels_unplaced = [(("name", 1, "e1"), "near TOG3")]
        P.final_text()
        self.assertEqual(P.names_skipped, ["Lower level: track name Y-1: no clean spot near TO117"])
        self.assertEqual(P.labels_unplaced[0][1], "near TO117")

    def test_names_last_places_the_icons_before_the_names(self):
        P = le.panel(with_opts({"names_last": True}))
        self.assertEqual(P.names_skipped, [])
        named = [k for k in P.strand_segments if bands()[k[0]][1]["strands"][k[1]]["name"]]
        self.assertEqual(len([lb for lb in P.labels if lb["kind"] == "name"]), len(named))
        for v in (1, "yes"):
            with self.subTest(v=v), self.assertRaisesRegex(SchematicError, "names_last must be true or false"):
                le_labels.options(with_opts({"names_last": v}), None)


class ReviewFixes(unittest.TestCase):
    def test_a_bands_options_reach_only_that_band_with_or_without_fit(self):
        b = [(t, band, dict(o, le_labels={"switch_prefix": "L-"}) if t.startswith("Lower") else
              {k: v for k, v in o.items() if k != "le_labels"}) for t, band, o in bands()]
        for P in (le.panel(b), le.panel(b, fit=(1300, 700))):
            numbers = {lb["band"]: [] for lb in P.labels}
            for lb in P.labels:
                if lb["kind"] == "switch":
                    numbers[lb["band"]].append(lb["text"])
            lower = next(i for i, x in enumerate(b) if x[0].startswith("Lower"))
            self.assertTrue(numbers[lower] and all(t.startswith("L-") for t in numbers[lower]))
            self.assertTrue(all(not t.startswith("L-") for bi, ts in numbers.items() if bi != lower for t in ts))
        self.assertEqual(le_labels.options(b, None)[0]["switch_prefix"], "")

    def test_a_track_the_drawing_keeps_no_room_for_gets_no_name_and_says_so(self):
        import test_le
        band = test_le.turnback_band()
        band[0][1]["strands"]["b"]["name"] = "A NAME FAR TOO LONG FOR ITS SHORT LEVEL RUN"
        with mock.patch.object(le, "paths", lambda bd: bd["_drawn"]):
            P = le.panel(band)
        self.assertTrue(any("no name placed (its longest level run is too short for its name)" in line
                            for line in P.log), P.log)
        self.assertFalse(any(lb["text"].startswith("A NAME FAR") for lb in P.labels))

    def test_the_check_covers_circles_and_keeps_every_label_inside_the_panel(self):
        P = copy.deepcopy(panel())
        sh = P.shapes[0]
        b = P.bcis[0]
        b["box"] = (round(sh["centre"][0]) - 3, round(sh["centre"][1]) - 3, 6, 6)
        P.bcis = [b]
        P.labels = [lb for lb in P.labels if lb["kind"] in le_labels.FIXED]
        P.masts = []
        with self.assertRaisesRegex(SchematicError, "over a circle"):
            le_labels.verify(P)
        P = copy.deepcopy(panel())
        title = next(lb for lb in P.labels if lb["kind"] == "title")
        title["box"] = (P.size[0] - 5, title["box"][1], *title["box"][2:])
        with self.assertRaisesRegex(SchematicError, "outside the"):
            le_labels.verify(P)

    def test_the_panel_counts_every_label_as_jmri_draws_it(self):
        P = panel()
        box = le.extent(P)
        for lb in P.labels:
            x0, y0, x1, y1 = le_labels.label_box(lb)
            self.assertTrue(box[0] <= x0 and x1 <= box[2] and box[1] <= y0 and y1 <= box[3], lb)
        self.assertGreaterEqual(P.size[0], box[2])


def a_turnout(c=(10.0, 8.0), kind="RH_TURNOUT"):
    """A turnout whose legs meet at 0, 0: A to the west, B level to the east, C at `c`."""
    return {"ident": "T1", "type": kind, "at": (0.0, 0.0), "pts": {"A": (-10.0, 0.0), "B": (10.0, 0.0), "C": c}}


class FrogSpots(unittest.TestCase):
    """A plain turnout's switch number may stand in its frog: the wedge between its two legs, past where they meet."""

    def test_the_frog_is_the_wedge_between_legs_b_and_c(self):
        at, u, v = le_labels.frog_of(a_turnout())
        self.assertEqual(at, (0.0, 0.0))
        self.assertEqual(u, (1.0, 0.0))
        self.assertAlmostEqual(math.hypot(*v), 1.0)
        for kind in ("RH_XOVER", "LH_XOVER", "DOUBLE_XOVER"):
            self.assertIsNone(le_labels.frog_of(a_turnout(kind=kind)))
        self.assertIsNone(le_labels.frog_of(a_turnout(c=(20.0, 0.0))))     # legs on one line: no wedge

    def test_a_missing_or_empty_leg_stops(self):
        t = a_turnout()
        del t["pts"]["C"]
        with self.assertRaisesRegex(SchematicError, "no leg C"):
            le_labels.frog_of(t)
        with self.assertRaisesRegex(SchematicError, "leg C ends where its legs meet"):
            le_labels.frog_of(a_turnout(c=(0.0, 0.0)))

    def test_every_frog_spot_stands_past_the_points_on_the_wedges_side_of_its_leg(self):
        w, h = 30, 12
        frog = le_labels.frog_of(a_turnout())          # B east, C down and east: the wedge is below B, above C
        spots = le_labels.frog_spots(frog, w, h)
        self.assertEqual(len(spots), 2 * len(le_labels.FROG_GAPS) * len(le_labels.FROG_ALONG))
        bands = [band for band, _xy in spots]
        self.assertEqual(bands, sorted(bands))                  # nearest first
        self.assertTrue(set(bands) <= set(le_labels.AROUND))
        self.assertEqual(spots[0], (le_labels.FROG_GAPS[0], (0.0, le_labels.FROG_GAPS[0])))  # against B, at the points
        c = frog[2]
        for _band, (x, y) in spots:
            corners = [(x, y), (x + w, y), (x, y + h), (x + w, y + h)]
            beside_b = all(cy >= le_labels.FROG_GAPS[0] - 1e-9 for _cx, cy in corners)   # below leg B's line
            beside_c = all(cx * -c[1] + cy * c[0] <= -le_labels.FROG_GAPS[0] + 1e-9 for cx, cy in corners)  # above C's
            self.assertTrue(beside_b or beside_c, (x, y))
            self.assertTrue(all(cx >= -1e-9 for cx, _cy in corners), (x, y))     # past the points, not behind them

    def test_a_plain_turnouts_number_tries_its_frog_after_arounds_spots_of_each_distance(self):
        L = mock.Mock()
        L.boxes.near.return_value = []
        t = dict(a_turnout(), band=0)
        L.bands = [("Band", {}, {})]
        L.halves.return_value = {None: (0.0, 0.0)}
        L.item.return_value = dict(w=30, h=12)
        _it, spots, _commit = le_labels._switch_number(L, t, "8", dict(le_labels.DEFAULTS))(
            dict(number_side={}, name_side={}))
        spots = list(spots)
        frog = le_labels.frog_of(t)
        self.assertEqual(spots, list(le_labels.switch_spots((0.0, 0.0), 30, 12, True, frog, [])))   # C runs down
        ranked = list(le_labels.around((0.0, 0.0, 0.0, 0.0), 30, 12, True, dists=le_labels.AROUND[:1]))
        self.assertEqual(spots[:len(ranked)], ranked)               # around's own first, as ranked before
        frog_first = [xy for band, xy in le_labels.frog_spots(frog, 30, 12) if band == le_labels.AROUND[0]]
        self.assertEqual(spots[len(ranked):len(ranked) + len(frog_first)], frog_first)

    def test_a_crossovers_number_keeps_around_its_crossover(self):
        L = mock.Mock()
        pts = {"A": (0.0, 0.0), "B": (40.0, 0.0), "C": (40.0, 20.0), "D": (0.0, 20.0)}
        t = {"ident": "X", "type": "RH_XOVER", "at": (20.0, 10.0), "pts": pts, "band": 0}
        L.bands = [("Band", {}, {})]
        L.halves.return_value = {"AB": (20.0, 0.0), "DC": (20.0, 20.0)}
        L.item.return_value = dict(w=30, h=12)
        _it, spots, _commit = le_labels._switch_number(L, t, "7", dict(le_labels.DEFAULTS))(
            dict(number_side={}, name_side={}))
        self.assertEqual(list(spots), list(le_labels.around((0.0, 0.0, 40.0, 20.0), 30, 12, True)))
        L.boxes.near.assert_not_called()


class StackedSpots(unittest.TestCase):
    """A plain turnout's switch number may stack further out on a side, past a mast icon or label standing there."""

    def test_a_spot_stacks_past_an_obstacle_above_or_below_in_its_column(self):
        w, h = 30, 12
        above = (-10, -20, 30, -8)              # a mast icon above the points
        below = (5, 6, 25, 14)
        aside = (100, -20, 120, -8)             # out of the column a number near the points takes
        across = (-5, -4, 5, 4)                 # on the points' own line
        spots = le_labels.beyond_spots((0.0, 0.0), w, h, [above, below, aside, across])
        ups = {xy for _b, up, xy in spots if up}
        downs = {xy for _b, up, xy in spots if not up}
        top = above[1] - le_labels.PAD - 1 - h
        self.assertIn((-w / 2, top), ups)                       # centred on the points
        self.assertIn(((above[0] + above[2] - w) / 2, top), ups)   # centred over the obstacle
        self.assertIn((above[0], top), ups)
        self.assertIn((-w / 2, below[3] + le_labels.PAD + 1), downs)
        self.assertEqual(len(spots), 16)                        # eight each: nothing for aside or across
        for band, up, (x, y) in spots:
            gap = -(y + h) if up else y
            self.assertEqual(band, next(d for d in le_labels.AROUND if d >= gap))
        self.assertEqual([b for b, _u, _xy in spots], sorted(b for b, _u, _xy in spots))

    def test_an_obstacle_too_far_out_gives_no_spot_and_a_bad_box_stops(self):
        far = (-10, -200, 10, -190)
        self.assertEqual(le_labels.beyond_spots((0.0, 0.0), 30, 12, [far]), [])
        with self.assertRaisesRegex(SchematicError, "no width or height"):
            le_labels.beyond_spots((0.0, 0.0), 30, 12, [(0, 0, 0, 5)])

    def test_a_stacked_spot_ranks_with_its_distance_side_tried_first_first(self):
        w, h = 30, 12
        obstacles = [(-10, -20, 30, -8), (-10, 8, 30, 20)]       # one above, one below: both 21 px out
        spots = list(le_labels.switch_spots((0.0, 0.0), w, h, False, None, obstacles))
        stacked = le_labels.beyond_spots((0.0, 0.0), w, h, obstacles)
        first_down = next(xy for _b, up, xy in stacked if not up)
        first_up = next(xy for _b, up, xy in stacked if up)
        self.assertLess(spots.index(first_down), spots.index(first_up))
        d = stacked[0][0]
        self.assertEqual(spots.index(first_down), len(list(le_labels.around((0, 0, 0, 0), w, h, False,
                                                                             dists=le_labels.AROUND[:le_labels.AROUND.index(d) + 1]))))

    def test_numbers_below_keeps_the_new_spot_kinds_below_its_turnout(self):
        """A switch in numbers_below: its frog spots (here the frog opens upward) and stacked spots above are not
        offered, so nothing takes the number above its turnout ahead of around's spots below it further out;
        around's own spots are as before. Without the preference the frog spots above are offered as before."""
        w, h = 30, 12
        t = dict(a_turnout(), band=0)
        t["pts"] = {k: (p[0], -p[1]) for k, p in t["pts"].items()}          # mirrored: its legs open upward
        frog = le_labels.frog_of(t)
        obstacles = [(-10, -20, 30, -8), (-10, 8, 30, 20)]       # one above, one below
        asked = list(le_labels.switch_spots((0.0, 0.0), w, h, False, frog, obstacles, side_only=True))
        free = list(le_labels.switch_spots((0.0, 0.0), w, h, False, frog, obstacles))
        around = set(le_labels.around((0, 0, 0, 0), w, h, False))
        extra = [xy for xy in asked if xy not in around]
        self.assertTrue(extra)                                   # the stacked spots below stay
        self.assertTrue(all(y + h / 2 > 0 for _x, y in extra), extra)
        self.assertTrue(any(y + h / 2 < 0 for x, y in free if (x, y) not in around))    # frog above, unasked
        firsts = lambda spots: list(dict.fromkeys(xy for xy in spots if xy in around))    # noqa: E731
        self.assertEqual(firsts(asked), list(dict.fromkeys(le_labels.around((0, 0, 0, 0), w, h, False))))
        L = mock.Mock()
        L.boxes.near.return_value = []
        L.bands = [("Band", {}, {})]
        L.halves.return_value = {None: (0.0, 0.0)}
        L.item.return_value = dict(w=w, h=h)
        o = dict(le_labels.DEFAULTS)
        _it, spots, _c = le_labels._switch_number(L, t, "8", o, below=True)(dict(number_side={}, name_side={}))
        self.assertEqual(list(spots), list(le_labels.switch_spots((0.0, 0.0), w, h, False, frog, [], side_only=True)))

    def test_on_the_example_every_plain_turnouts_number_reads_as_its_own_and_the_check_passes(self):
        # with around's own spots all held, every plain turnout's number stands in its frog or stacked past
        # something, on the drawn panel, and the check passes
        real = le_labels.around

        def only_new(region, w, h, up_first, dists=le_labels.AROUND, more=None):
            if more is None:
                yield from real(region, w, h, up_first, dists)
                return
            for d in dists:
                yield from more(d)
        with mock.patch.object(le_labels, "around", only_new):
            P = le.panel(bands())
        frogs = {t["ident"]: le_labels.frog_of(t) for t in P.turnouts}
        L = le_labels.Layer(P, bands(), le_labels.options(bands(), None))
        marks = [(p, t["ident"]) for t in P.turnouts for p in L.halves(t).values()]
        framed = 0
        for lb in P.labels:
            if lb["kind"] != "switch":
                continue
            box = le_labels.box_of(*lb["box"])
            mine = [t for t in P.turnouts if bands()[t["band"]][1]["nodes"][t["nodes"][0]].get("label") == lb["text"]]
            near = min(marks, key=lambda m: le_labels.point_gap(box, m[0]))
            self.assertIn(near[1], [t["ident"] for t in mine], lb["text"])
            frog = frogs[mine[0]["ident"]]
            if frog:
                (cx, cy), (at, u, v) = le_labels.centre(box), frog
                q = (cx - at[0], cy - at[1])
                framed += (u[0] * q[1] - u[1] * q[0]) * (u[0] * v[1] - u[1] * v[0]) > 0 and \
                    (v[0] * q[1] - v[1] * q[0]) * (v[0] * u[1] - v[1] * u[0]) > 0
        self.assertGreater(framed, 0)
        le_labels.verify(P)


def passing_x(P, w):
    """A left edge for a w px item of block Passing: its middle 16 px west of the middle of the block's longest
    level piece, where a given x has its own track under it."""
    L = le_labels.Layer(P, bands(), le_labels.options(bands(), None))
    pieces = [pc for s in P.segments if s["block"] == "Passing" for pc in L.pieces.get(("seg", s["ident"]), [])
              if abs(pc[0][1] - pc[1][1]) < 1e-6]
    a, b = max(pieces, key=lambda pc: abs(pc[1][0] - pc[0][0]))
    return round((a[0] + b[0]) / 2 - 16 - w / 2)


class Extras(unittest.TestCase):
    EXTRAS = [{"id": "Passing cluster", "block": "Passing", "size": [82, 20]},
              {"id": "OS 4 cluster", "block": "OS 4", "size": [40, 20]}]

    def test_a_callers_items_stand_by_their_blocks_and_count_as_obstacles(self):
        P = le.panel(bands(), extras=self.EXTRAS)
        self.assertEqual([e["id"] for e in P.extras], ["Passing cluster", "OS 4 cluster"])
        for e, want in zip(P.extras, self.EXTRAS):
            self.assertEqual(e["box"][2:], tuple(want["size"]))
            self.assertEqual(e["block"], want["block"])
        self.assertEqual(sorted(b["block"] for b in P.bcis), sorted(P.blocks))
        le_labels.verify(P)
        boxes_ = [le_labels.box_of(*x["box"]) for x in P.labels + P.bcis]
        for e in P.extras:
            mine = le_labels.box_of(*e["box"])
            self.assertFalse([b for b in boxes_ if le_labels.boxes_overlap(mine, b, -le_labels.OVERLAP)])
        self.assertEqual(le.geometry(P), le.geometry(le.panel(bands())))      # no track moved
        self.assertNotIn("extra", ET_tags(le.to_xml(P, "G")))                 # the caller writes them

    def test_an_item_with_no_clean_spot_stops_naming_it(self):
        with self.assertRaisesRegex(SchematicError, "item Huge \\(block Passing\\): no clean spot"):
            le.panel(bands(), extras=[{"id": "Huge", "block": "Passing", "size": [5000, 400]}])

    def test_a_callers_item_at_a_given_x(self):
        want = dict(self.EXTRAS[0], x=passing_x(le.panel(bands(), extras=self.EXTRAS), 82))
        Q = le.panel(bands(), extras=[want] + list(self.EXTRAS[1:]))
        got = next(e for e in Q.extras if e["id"] == "Passing cluster")
        self.assertEqual(got["box"][0], round(want["x"]))
        le_labels.verify(Q)
        with self.assertRaisesRegex(SchematicError, "Passing cluster.*no clean spot"):
            le.panel(bands(), extras=[dict(self.EXTRAS[0], x=-5000)])        # no track of its block there

    def test_bad_extras_stop_before_drawing(self):
        good = {"id": "A", "block": "Passing", "size": [10, 10]}
        for bad, msg in (("x", "must be a list"), (["x"], "must be an object"),
                         ([dict(good, colour=1)], "needs id, block and size"), ([dict(good, id="")], "id must"),
                         ([dict(good, x="9")], "x must be a number"), ([dict(good, x=float("inf"))], "x must"),
                         ([good, good], "given twice"), ([dict(good, block=3)], "block must"),
                         ([dict(good, size=[10])], "size must"), ([dict(good, size=[10, 0])], "size must"),
                         ([dict(good, size=[True, 4])], "size must"),
                         ([dict(good, block="Nowhere")], "block 'Nowhere' is not on the panel")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, msg):
                le.panel(bands(), extras=bad)


def ET_tags(el):
    return {e.tag.lower() for e in el.iter()}


def shared(**prefs):
    """The example's bands with `prefs` set in the one preferences dict both bands share (as one file that sets the
    page and both bands), and that dict as the page."""
    b = bands()
    o = dict(b[0][2], **prefs)
    return [(t, band, o) for t, band, _o in b], o


class BandKeyedLabels(unittest.TestCase):
    """le_band_labels: {band: {le_labels key: value}} in a file that sets the page and several bands at once."""

    def test_each_band_takes_its_own_entry_over_the_page_and_the_flat_keys(self):
        b, page = shared(le_labels={"switch_prefix": "P-", "switch_size": 11},
                         le_band_labels={"Lower": {"names_last": True, "block_contents_size": 12,
                                                   "numbers_below": ["7"]},
                                         "Upper": {"optional_block_contents": ["Rise"]}})
        lower, upper = (le_labels.options(b, page)[[t for t, _b, _o in b].index(n)]
                        for n in ("Lower level", "Upper level"))
        for o in (lower, upper):                                # the flat keys reach both bands and the page
            self.assertEqual((o["switch_prefix"], o["switch_size"]), ("P-", 11))
        self.assertEqual((lower["names_last"], lower["block_contents_size"], lower["numbers_below"]),
                         (True, 12, ["7"]))
        self.assertEqual((upper["names_last"], upper["block_contents_size"], upper["numbers_below"]),
                         (False, le_labels.DEFAULTS["block_contents_size"], []))
        self.assertEqual((lower["optional_block_contents"], upper["optional_block_contents"]), ([], ["Rise"]))

    def test_another_band_takes_the_page_and_its_own_flat_keys_only(self):
        b, page = shared(le_labels={"switch_prefix": "P-"}, le_band_labels={"Lower": {"names_last": True}})
        b = [(t, band, {"le_labels": {"switch_size": 10}}) if t.startswith("Upper") else (t, band, o)
             for t, band, o in b]
        upper = le_labels.options(b, page)[0]
        self.assertEqual((upper["switch_prefix"], upper["switch_size"], upper["names_last"]), ("P-", 10, False))

    def test_a_band_key_set_flat_and_band_keyed_stops(self):
        b, page = shared(le_labels={"switch_size": 11}, le_band_labels={"Lower": {"switch_size": 12}})
        with self.assertRaisesRegex(SchematicError, "Lower level: switch_size set in both its le_labels and its "
                                                    "le_band_labels for Lower"):
            le_labels.options(b, page)
        b, page = shared(le_labels={"switch_size": 11}, le_band_labels={"Lower": {"switch_size": 11}})
        with self.assertRaisesRegex(SchematicError, "set in both"):        # even with one value: set it once
            le_labels.options(b, page)

    def test_bad_entries_stop_before_drawing(self):
        cases = [([], "le_band_labels must be an object of band"),
                 ({"Middle": {}}, "le_band_labels names Middle, which is no band"),
                 ({"Lower": ["x"]}, "le_band_labels for Lower: le_labels must be an object"),
                 ({"Lower": {"colour": 1}}, "le_band_labels for Lower: le_labels: unknown key colour"),
                 ({"Lower": {"switch_size": 7}}, "le_band_labels for Lower: le_labels: switch_size must be"),
                 ({"Upper": {"names_last": "yes"}}, "names_last must be true or false")]
        for value, msg in cases:
            b, page = shared(le_band_labels=value)
            with self.subTest(value=value), self.assertRaisesRegex(SchematicError, msg):
                le.panel(b, page=page)

    def test_an_entry_in_another_bands_preferences_or_only_on_the_page_stops(self):
        b = with_opts(None)
        b = [(t, band, dict(o, le_band_labels={"Lower": {"names_last": True}}) if t.startswith("Upper") else
              dict(o)) for t, band, o in b]
        with self.assertRaisesRegex(SchematicError, "le_band_labels for Lower is in another band's preferences"):
            le_labels.options(b, None)
        page = dict(bands()[-1][2], le_band_labels={"Lower": {"names_last": True}})
        with self.assertRaisesRegex(SchematicError, "page: le_band_labels for Lower is not in that band's own"):
            le.panel(bands(), page=page)

    def test_the_band_keyed_entry_draws_as_the_bands_own_flat_keys(self):
        b, page = shared(le_band_labels={"Lower": {"switch_prefix": "L-"}})
        rest = {k: v for k, v in page.items() if k != "le_band_labels"}
        flat = [(t, band, dict(rest, le_labels={"switch_prefix": "L-"}) if t.startswith("Lower") else rest)
                for t, band, _o in b]
        self.assertEqual(ET.tostring(le.to_xml(le.panel(b, page=page), "G")),
                         ET.tostring(le.to_xml(le.panel(flat, page=rest), "G")))


class HiddenNames(unittest.TestCase):
    """hidden_names: a band's track names the Layout Editor panel leaves off."""

    def test_a_hidden_name_is_drawn_as_no_name_but_still_names_its_block(self):
        b, page = shared(le_band_labels={"Lower": {"hidden_names": ["Yard Lead"]}})
        rest = {k: v for k, v in page.items() if k != "le_band_labels"}
        unnamed = [(t, dict(band, strands={sid: dict(s, name="") if s["name"] == "Yard Lead" else s
                                           for sid, s in band["strands"].items()}) if t.startswith("Lower")
                    else band, rest) for t, band, _o in b]
        P, U = le.panel(b, page=page), le.panel(unnamed, page=rest)
        self.assertNotIn("Yard Lead", [lb["text"] for lb in P.labels])
        # drawn as a track with no name: the same labels and track, so no room kept for it either (the block
        # contents icons may stand elsewhere: with no names given, the unnamed track's block takes another name)
        self.assertEqual([(lb["text"], lb["box"]) for lb in P.labels], [(lb["text"], lb["box"]) for lb in U.labels])
        self.assertEqual(P.strand_segments, U.strand_segments)
        self.assertIn("Yard Lead", P.blocks)                    # the name stays: its block is still named by it
        self.assertNotIn("Yard Lead", U.blocks)
        self.assertFalse(any("Yard Lead" in line for line in P.log if "no name placed" in line))
        self.assertTrue(any(s["name"] == "Yard Lead" for s in b[1][1]["strands"].values()))   # not changed

    def test_every_track_of_a_hidden_name_loses_it_on_that_band_only(self):
        b, page = shared(le_band_labels={"Lower": {"hidden_names": ["Main"]}})
        hidden = le_labels.hide_names(b, page)
        mains = [s for s in hidden[1][1]["strands"].values() if s["name"] == "Main"]
        self.assertGreater(len(mains), 1)
        self.assertTrue(all(s[le_labels.HIDDEN] for s in mains))
        self.assertFalse(any(s.get(le_labels.HIDDEN) for s in hidden[1][1]["strands"].values() if s["name"] != "Main"))
        self.assertIs(hidden[0][1], b[0][1])                    # a band with nothing hidden: as it is
        again = le_labels.hide_names(hidden, page)              # marking twice changes nothing
        self.assertIs(again[1][1], hidden[1][1])
        b2, page2 = shared(le_band_labels={"Lower": {"hidden_names": ["Y-9"]}})     # as the panel writes it
        t2, band2, o2 = b2[1]
        b2[1] = (t2, dict(band2, strands={sid: dict(st, name="Track Y-9") if st["name"] == "Y-1" else st
                                          for sid, st in band2["strands"].items()}), o2)     # a copy
        self.assertTrue(all(st[le_labels.HIDDEN] for st in le_labels.hide_names(b2, page2)[1][1]["strands"].values()
                            if st["name"] == "Track Y-9"))

    def test_a_name_on_no_track_or_a_bad_list_stops(self):
        cases = [({"Lower": {"hidden_names": ["Nowhere"]}}, "Lower level: le_labels: hidden_names Nowhere: no "
                                                            "track of the band has that name"),
                 ({"Lower": {"hidden_names": ["Spur"]}}, "hidden_names Spur: no track of the band"),   # Upper's
                 ({"Lower": {"hidden_names": "Main"}}, "hidden_names must be a list of track names"),
                 ({"Lower": {"hidden_names": ["Main", "Main"]}}, "hidden_names names a track twice")]
        for value, msg in cases:
            b, page = shared(le_band_labels=value)
            with self.subTest(value=value), self.assertRaisesRegex(SchematicError, msg):
                le.panel(b, page=page)
        with self.assertRaisesRegex(SchematicError, "hidden_names is a band's own option"):
            le_labels.options(with_opts(None), {"le_labels": {"hidden_names": ["Main"]}})

    def test_a_helix_tracks_hidden_name_still_joins_the_bands(self):
        b, page = shared(le_band_labels={"Upper": {"hidden_names": ["Summit"]}})
        rest = {k: v for k, v in page.items() if k != "le_band_labels"}
        P, full = le.panel(b, page=page), le.panel([(t, band, rest) for t, band, _o in b], page=rest)
        hidden_join = [s for s in P.segments if s.get("hidden")]
        self.assertEqual(len(hidden_join), len([s for s in full.segments if s.get("hidden")]))
        self.assertEqual(sum(lb["text"] == "Summit" for lb in P.labels) + 1,
                         sum(lb["text"] == "Summit" for lb in full.labels))      # Upper's label only

    def test_a_block_on_two_bands_gets_its_icon_on_its_own_band(self):
        """A joined helix track is one block drawn on two bands (the default names share it through the join): its
        block contents icon stands on the band block_band gives it, so the band's extent, and with it
        le_title_clear, never reaches into the other band."""
        b, page = shared()
        P = le.panel(b, page=page)
        segs = defaultdict(set)
        for s in P.segments:
            if not s.get("hidden"):
                segs[s["block"]].add(s["band"])
        two = [blk for blk, on in segs.items() if len(on) > 1]
        self.assertTrue(two)                                    # the example joins its helix as one block
        for blk in two:
            with self.subTest(block=blk):
                icon = next(m for m in P.bcis if m["block"] == blk)
                top, bottom = P.band_boxes[icon["band"]][1], P.band_boxes[icon["band"]][3]
                x, y, w, h = icon["box"]
                self.assertTrue(top - 2 * h <= y <= bottom + h, (blk, icon["band"], y, top, bottom))
                self.assertLessEqual(le.extent(P, icon["band"])[3], bottom + 2 * h)

    def test_draw_panel_marks_them_too(self):
        b, page = shared(le_band_labels={"Lower": {"hidden_names": ["Yard Lead"]}})
        P = le.draw_panel(b, None, le.CELL, le.ROW, page)
        self.assertNotIn("Yard Lead", [lb["text"] for lb in P.labels])


if __name__ == "__main__":
    unittest.main()
