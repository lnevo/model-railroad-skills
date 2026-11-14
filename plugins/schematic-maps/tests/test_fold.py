"""Page folding (style rule 24) on the made-up example, stretched until it is too long for the page."""
import re
import unittest
from xml.dom import minidom

import helpers
from schematic import draw, fold


def long_bands(cell=110):
    """The example's bands drawn `cell` units per column, far wider than a Letter page."""
    return [(t, b, dict(o, band_cell={"Lower": cell, "Upper": cell})) for t, b, o in helpers.build(True).bands]


def page(bands, **prefs):
    opts = dict(helpers.build(True).opts, equal_width=False, _folds=[], **prefs)
    return draw.page_svg(bands, opts), opts["_folds"]


def scale_of(svg):
    return float(re.search(r"scale\(([\d.]+)\)", svg).group(1))


class Folding(unittest.TestCase):
    def test_off_by_default_and_when_the_sheet_is_not_too_small(self):
        sheet = helpers.build(True)
        o0 = dict(sheet.opts, title=sheet.opts.get("system_title", sheet.opts["title"]))
        plain = draw.page_svg(sheet.bands, dict(o0))
        self.assertEqual(plain, sheet.svg())
        for prefs in ({"fold": False}, {"fold": True}, {"fold_min_scale": 0.05}):     # a short sheet needs no fold
            self.assertEqual(draw.page_svg(sheet.bands, dict(o0, **prefs)), plain, prefs)
        svg, notes = page(long_bands())          # long, but folding is not asked for
        self.assertNotIn("CONTINUED", svg)
        self.assertEqual(notes, [])

    def test_setting(self):
        self.assertIsNone(fold.setting({}))
        self.assertIsNone(fold.setting({"fold": False}))
        self.assertEqual(fold.setting({"fold": True}), fold.DEFAULT_MIN)
        self.assertEqual(fold.setting({"fold_min_scale": 0.5}), 0.5)

    def test_a_long_band_folds_into_rows_and_is_drawn_larger(self):
        bands = long_bands()
        flat, _ = page(bands)
        svg, notes = page(bands, fold=True)
        self.assertGreater(scale_of(svg), 1.5 * scale_of(flat))
        self.assertGreaterEqual(scale_of(svg), fold.DEFAULT_MIN * 0.9)
        self.assertEqual(len(notes), 1)
        self.assertIn("Lower level cut at", notes[0])
        self.assertNotIn("through something", notes[0])
        self.assertEqual(svg.count("(CONTINUED)"), svg.count("<clipPath") - 1)       # every row but the first says so
        minidom.parseString(svg)                 # still well-formed

    def test_a_min_scale_of_its_own(self):
        svg, notes = page(long_bands(), fold_min_scale=0.5)
        self.assertEqual(len(notes), 1)
        self.assertIn("CONTINUED", svg)

    def test_the_cut_is_between_switches(self):
        """Never through a ladder, crossover, loop or label: every cut costs less than a cut through any of them."""
        bands = long_bands()
        flat, _ = page(bands)           # measures each band at the origin, as the fold does
        for title, band, o in bands:
            info = band["fold"]
            width = max(x1 for *_, x1, _ in info["boxes"])
            cut_list, clean = fold.cuts(info, width, width / 3 + 10)
            self.assertTrue(clean, title)
            for u in cut_list:
                self.assertLess(fold.cost(info, u), fold.BAD, (title, u))

    def test_each_cut_track_gets_an_arrow_and_the_main_a_large_one(self):
        svg, _ = page(long_bands(), fold=True)
        out, into = svg.count(">CONTINUES<"), svg.count(">CONTINUED<")
        self.assertGreaterEqual(out, 1)           # the main line leaves the first row with a large arrow
        self.assertEqual(out, into)               # and arrives in the next with one

    def test_a_cut_through_nothing_clean_is_reported(self):
        """A band that is all slope has no clean cut: it is cut anyway and the note says so."""
        info = dict(boxes=[], lines=[((0, 0), (1000, 40), 1.4)], track_y=(0, 40), zones=[])
        cut_list, clean = fold.cuts(info, 1000, 400)
        self.assertEqual(len(cut_list), 2)
        self.assertFalse(clean)

    def test_not_folded_when_it_does_not_help(self):
        bands = long_bands()
        flat, _ = page(bands)
        svg, notes = page(bands, fold_min_scale=0.2)      # already above the floor
        self.assertEqual((svg, notes), (flat, []))


if __name__ == "__main__":
    unittest.main()
