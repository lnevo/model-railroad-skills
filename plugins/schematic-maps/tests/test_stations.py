"""Stations: object entries, overlap, tracks-limited car totals and bars on either side of the band."""
import copy
import re
import unittest
import xml.etree.ElementTree as ET

import helpers
from schematic import capacity, detail, label_check, stations
from schematic.core import SchematicError

BAR = re.compile(r'd="M(-?[\d.]+),(-?[\d.]+) L\1,(-?[\d.]+) L(-?[\d.]+),\3 L\4,\2"')
YARD = ["11", "12", "13"]


def drawn(stations_, **extra):
    """The example's overall sheet drawn with these stations (capacity on): its SVG text."""
    s = copy.copy(helpers.build())
    s.bands = [(t, b, dict(o, stations=stations_, capacity={}, **extra)) for t, b, o in s.bands]
    s.opts = s.bands[-1][2]
    s._svg = None
    return s.svg(), s


def lower(s):
    return next(b for b in s.bands if b[0] == "Lower level")


def text_y(svg, text):
    root = ET.fromstring(svg)
    ys = [float(e.get("y")) for e in root.iter("{http://www.w3.org/2000/svg}text") if "".join(e.itertext()).split(" (")[0] == text]
    return ys[0] if ys else None


class Entries(unittest.TestCase):
    def test_list_and_object_forms_read_the_same(self):
        a = stations.entries({"stations": {"Y": YARD}})
        b = stations.entries({"stations": {"Y": {"switches": YARD}}})
        self.assertEqual(a, b)
        self.assertEqual(a["Y"]["side"], "bottom")
        self.assertIsNone(a["Y"]["tracks"])

    def test_station_side_wins_over_the_objects_side(self):
        e = stations.entries({"stations": {"Y": {"switches": YARD, "side": "top"}}, "station_side": {"Y": "bottom"}})
        self.assertEqual(e["Y"]["side"], "bottom")
        e = stations.entries({"stations": {"Y": {"switches": YARD, "side": "top"}}})
        self.assertEqual(e["Y"]["side"], "top")

    def test_bad_entries_stop(self):
        for bad, msg in (({"stations": {"Y": {"switches": YARD, "side": "left"}}}, "side must be top or bottom"),
                         ({"stations": {"Y": {"switches": YARD, "colour": 1}}}, "colour"),
                         ({"stations": {"Y": {"tracks": []}}}, "needs `switches`"),
                         ({"stations": {"Y": 5}}, "list of switches or an object"),
                         ({"stations": {"Y": {"switches": "11"}}}, "switches must be a list")):
            with self.assertRaisesRegex(SchematicError, msg):
                stations.entries(bad)

    def test_a_scope_name_that_matches_no_input_stops_but_one_in_another_input_is_ignored(self):
        a, b = {"stations": {"A": ["1"]}, "station_side": {"B": "top"}}, {"stations": {"B": ["2"]}}
        stations.check([a, b])                                         # B is B's, so A just ignores it
        self.assertEqual(stations.entries(a)["A"]["side"], "bottom")
        with self.assertRaisesRegex(SchematicError, "station_side names Z, which is not a station"):
            stations.check([dict(a, station_side={"Z": "top"}), b])
        with self.assertRaisesRegex(SchematicError, "station_tracks names Z"):
            stations.check([dict(a, station_tracks={"Z": []}), b])

    def test_station_tracks_is_its_own_layer_1_key_and_wins_over_the_object(self):
        e = stations.entries({"stations": {"Y": YARD}, "station_tracks": {"Y": ["y-1"]}})
        self.assertEqual(e["Y"]["tracks"], {"Y-1"})
        e = stations.entries({"stations": {"Y": {"switches": YARD, "tracks": ["Y-2"]}}, "station_tracks": {"Y": []}})
        self.assertEqual(e["Y"]["tracks"], set())
        self.assertEqual(stations.entries({"stations": {"Y": {"switches": YARD, "tracks": ["Y-2"]}}})["Y"]["tracks"], {"Y-2"})

    def test_a_station_defined_differently_in_two_inputs_stops(self):
        one, two = {"stations": {"Y": YARD}}, {"stations": {"Y": YARD}, "station_tracks": {"Y": ["Y-1"]}}
        with self.assertRaisesRegex(SchematicError, "defined differently"):
            stations.check([one, two])
        with self.assertRaisesRegex(SchematicError, "defined differently"):
            detail.owners([one, two])
        with self.assertRaisesRegex(SchematicError, "defined differently"):
            detail.selections([one, two])
        stations.check([one, dict(one, station_side={"Y": "top"})])      # the look may differ

    def test_a_joined_track_name_matches_whole_or_in_parts(self):
        names = stations.track_names("Main / Passing")
        self.assertEqual(names, {"MAIN / PASSING", "MAIN", "PASSING"})
        self.assertTrue(stations.track_names("main / passing") & {"MAIN / PASSING"})

    def test_the_object_form_with_nothing_extra_draws_the_same_sheet(self):
        self.assertEqual(drawn({"Yard": YARD})[0], drawn({"Yard": {"switches": YARD}})[0])


class Scope(unittest.TestCase):
    def totals(self, st, **extra):
        _, s = drawn(st, **extra)
        _, band, opts = lower(s)
        return capacity.station_totals(band, opts, band["x"])

    def test_a_track_whose_west_switch_is_in_stations_that_do_not_list_it_counts_for_the_other_end(self):
        gate = {"switches": ["1"], "tracks": ["Nope"]}
        both = self.totals({"Gate": gate, "Plain": ["11"]})
        alone = self.totals({"Plain": ["11"]})
        self.assertTrue(alone["Plain"])
        self.assertEqual(both["Plain"], alone["Plain"])        # Yard Lead runs from switch 1 to 11: 11's station counts it
        self.assertNotIn("Gate", both)

    def test_station_tracks_and_the_object_form_count_alike(self):
        a = self.totals({"Few": {"switches": YARD, "tracks": ["Y-1"]}})
        self.assertEqual(self.totals({"Few": YARD}, station_tracks={"Few": ["Y-1"]}), a)
        self.assertTrue(a["Few"])


class Totals(unittest.TestCase):
    def totals(self, st, **extra):
        _, s = drawn(st, **extra)
        _, band, opts = lower(s)
        return capacity.station_totals(band, opts, band["x"])

    def test_tracks_limit_what_a_station_counts_and_a_track_counts_once(self):
        whole = self.totals({"Yard": YARD})["Yard"]
        part = self.totals({"Few": {"switches": YARD, "tracks": ["y-1", "Y-2", "Y-1"]}})
        _, band, opts = lower(drawn({"Yard": YARD})[1])
        by_name = {band["strands"][k]["name"]: n for k, n in capacity.counts(band, opts).items()}
        self.assertEqual(part["Few"], by_name["Y-1"] + by_name["Y-2"])
        self.assertLess(part["Few"], whole)

    def test_empty_tracks_count_nothing(self):
        t = self.totals({"Gate": {"switches": ["11"], "tracks": []}, "Yard": YARD})
        self.assertNotIn("Gate", t)
        self.assertTrue(t["Yard"])

    def test_overlapping_stations_each_count_their_own(self):
        t = self.totals({"A": YARD, "B": {"switches": ["13"], "tracks": ["Y-3", "Y-4"]}})
        _, band, opts = lower(drawn({"A": YARD})[1])
        by_name = {band["strands"][k]["name"]: n for k, n in capacity.counts(band, opts).items()}
        self.assertEqual(t["B"], by_name["Y-3"] + by_name["Y-4"])
        self.assertEqual(t["A"], self.totals({"A": YARD})["A"])        # B being there changes nothing for A


class Bars(unittest.TestCase):
    def test_side_means_the_drawn_side_on_a_band_turned_end_for_end(self):
        for side, above in (("top", True), ("bottom", False)):
            svg, _ = drawn({"Yard": YARD}, station_side={"Yard": side}, rotate_bands=["Lower"])
            self.assertEqual(text_y(svg, "YARD") < text_y(svg, "Y-1"), above, side)
            self.assertEqual(label_check.check(svg)[0], [], side)
            self.assertEqual(label_check.outside_frame(svg), [], side)

    def test_a_detail_sheet_of_a_turned_band_keeps_the_side(self):
        _, s = drawn({"Yard": YARD}, station_side={"Yard": "top"}, rotate_bands=["Lower"])
        svg, _ = detail.sheet_svg(s.bands, YARD, "Yard", detail.owners([o for _, _, o in s.bands]))
        self.assertLess(text_y(svg, "YARD"), text_y(svg, "Y-1"))
        self.assertEqual(label_check.check(svg)[0], [])

    def test_a_listed_track_that_does_not_touch_the_station_does_not_widen_the_bar(self):
        plain, _ = drawn({"W": ["13"]})
        far, _ = drawn({"W": {"switches": ["13"], "tracks": ["Y-1"]}})          # Y-1 runs off switch 11, not 13
        self.assertEqual(BAR.findall(plain), BAR.findall(far))

    def test_a_bar_on_top_stands_above_the_band_and_nothing_collides(self):
        bottom, _ = drawn({"Yard": YARD})
        top, s = drawn({"Yard": YARD}, station_side={"Yard": "top"})
        self.assertGreater(text_y(bottom, "YARD"), text_y(bottom, "Y-1"))
        self.assertLess(text_y(top, "YARD"), text_y(top, "Y-1"))
        faults, _ = label_check.check(top)
        self.assertEqual(faults, [])
        self.assertEqual(label_check.outside_frame(top), [])

    def test_top_and_bottom_lanes_stack_separately(self):
        st = {"A": {"switches": ["11", "12"], "side": "top"}, "B": {"switches": ["12", "13"], "side": "top"},
              "C": {"switches": ["11", "13"]}}
        svg, s = drawn(st)
        faults, _ = label_check.check(svg)
        self.assertEqual(faults, [])
        ya, yb = text_y(svg, "A"), text_y(svg, "B")
        self.assertNotEqual(ya, yb)                                  # overlapping bars on one side take two lanes
        self.assertLess(max(ya, yb), text_y(svg, "Y-1"))
        self.assertGreater(text_y(svg, "C"), text_y(svg, "Y-1"))

    def test_a_bar_spans_the_tracks_it_lists(self):
        plain, _ = drawn({"W": ["13"]})
        wide, _ = drawn({"W": {"switches": ["13"], "tracks": ["Y-3", "Y-4"]}})
        width = lambda svg: [float(m[3]) - float(m[0]) for m in BAR.findall(svg)]
        self.assertEqual(len(width(plain)), 1)
        self.assertGreater(width(wide)[0], width(plain)[0] + 20)

    def test_a_detail_sheet_keeps_a_top_bar_and_its_total(self):
        _, s = drawn({"Yard": {"switches": YARD, "side": "top"}})
        allo = [o for _, _, o in s.bands]
        svg, sub = detail.sheet_svg(s.bands, YARD, "Yard", detail.owners(allo))
        self.assertIsNotNone(text_y(svg, "YARD"))
        self.assertTrue(sub["precomputed"]["totals"]["Yard"])
        self.assertEqual(label_check.check(svg)[0], [])
        self.assertEqual(label_check.outside_frame(svg), [])


if __name__ == "__main__":
    unittest.main()
