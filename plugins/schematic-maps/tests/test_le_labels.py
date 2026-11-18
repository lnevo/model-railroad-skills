"""The label layer of the generated Layout Editor panel (le_labels): switch numbers, track names, one block contents
icon per block and station names, each in a clean spot sized as JMRI draws it, checked from scratch."""
import copy
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
    """A stand-in for le_labels.Layer in place_items: each item takes the first of its spots no one holds."""

    def __init__(self):
        self.held, self.notes, self.boxes = set(), [], None

    def reset(self):
        self.held, self.notes = set(), []

    def take(self, item, spots):
        for s in spots:
            if s not in self.held:
                self.held.add(s)
                return s, None
        return None, f"{item['what']}: no clean spot"


def spot_items(want):
    """[(key, make)]: one item per (key, spots), each placing at the first free spot of its list."""
    def maker(key, spots):
        def make(state, short=False):
            return dict(what=str(key)), list(spots), lambda box: ("label", dict(key=key, box=box))
        return make
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
        P = le.panel(bands(), extras=self.EXTRAS)
        first = next(e for e in P.extras if e["id"] == "Passing cluster")
        want = dict(self.EXTRAS[0], x=first["box"][0] - 16)
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

    def test_draw_panel_marks_them_too(self):
        b, page = shared(le_band_labels={"Lower": {"hidden_names": ["Yard Lead"]}})
        P = le.draw_panel(b, None, le.CELL, le.ROW, page)
        self.assertNotIn("Yard Lead", [lb["text"] for lb in P.labels])


if __name__ == "__main__":
    unittest.main()
