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
                         ({"stations": {"Y": YARD}, "station_side": {"Z": "top"}}, "Z, which is not a station")):
            with self.assertRaisesRegex(SchematicError, msg):
                stations.entries(bad)

    def test_the_object_form_with_nothing_extra_draws_the_same_sheet(self):
        self.assertEqual(drawn({"Yard": YARD})[0], drawn({"Yard": {"switches": YARD}})[0])


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
