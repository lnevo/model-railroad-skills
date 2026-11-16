"""The label layer of the generated Layout Editor panel (le_labels): switch numbers, track names, one block contents
icon per block and station names, each in a clean spot sized as JMRI draws it, checked from scratch."""
import copy
import math
import unittest

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


def no_room_for_names(L, bi, text, mine):
    make = REAL_TRACK_NAME(L, bi, text, mine)
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


class NamesLast(unittest.TestCase):
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

    def test_bad_extras_stop_before_drawing(self):
        good = {"id": "A", "block": "Passing", "size": [10, 10]}
        for bad, msg in (("x", "must be a list"), (["x"], "must be an object"),
                         ([dict(good, colour=1)], "exactly id, block and size"), ([dict(good, id="")], "id must"),
                         ([good, good], "given twice"), ([dict(good, block=3)], "block must"),
                         ([dict(good, size=[10])], "size must"), ([dict(good, size=[10, 0])], "size must"),
                         ([dict(good, size=[True, 4])], "size must"),
                         ([dict(good, block="Nowhere")], "block 'Nowhere' is not on the panel")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, msg):
                le.panel(bands(), extras=bad)


def ET_tags(el):
    return {e.tag.lower() for e in el.iter()}


if __name__ == "__main__":
    unittest.main()
