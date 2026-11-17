"""The Layout Editor preferences (schematic/le_prefs.py): le_shift, le_longer_straights, le_crossover_angle,
le_title_clear, le_stretch and a band's le_labels extra_steps and extra_follow."""
import math
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import le, le_labels, le_prefs
from schematic.core import SchematicError
from test_le import bands


def with_prefs(key, **prefs):
    """The example's bands with `prefs` in the options of the band `key` (a copy)."""
    return [(t, b, dict(o, **prefs) if t.startswith(key) else o) for t, b, o in bands()]


def lower(bs):
    return next(b for t, b, _o in bs if t.startswith("Lower"))


def column(band, label):
    return next(band["x"][n] for n, d in band["nodes"].items() if d.get("label") == label and d["kind"] == "switch")


class Shift(unittest.TestCase):
    def test_nodes_between_the_two_switches_move_and_the_rest_stay(self):
        raw = lower(bands())
        got = lower(le.drawn_bands(with_prefs("Lower", le_shift={"Lower": [{"from": "3", "to": "5", "columns": -1}]})))
        lo, hi = column(raw, "3"), column(raw, "5")
        for n, x in raw["x"].items():
            turnback = raw["nodes"][n]["kind"].startswith("turn")
            self.assertEqual(got["x"][n], x - 1 if lo <= x <= hi and not turnback else x, n)
        self.assertTrue(got[le_prefs.DRAWN])
        self.assertNotIn(le_prefs.DRAWN, raw)                   # the bands given are not changed
        self.assertIs(le.drawn_bands(bands())[0][1], bands()[0][1])     # a band with neither is returned as it is

    def test_applied_once_and_only_on_the_layout_editor_panel(self):
        prefs = with_prefs("Lower", le_shift={"Lower": [{"from": "3", "to": "5", "columns": -1}]})
        once = le.drawn_bands(prefs)
        self.assertEqual(lower(le.drawn_bands(once))["x"], lower(once)["x"])
        P, Q = le.panel(prefs), le.panel(once)
        self.assertEqual(le.geometry(P), le.geometry(Q))
        self.assertNotEqual(le.geometry(P), le.geometry(le.panel(bands())))

    def test_a_shift_that_reverses_a_track_or_names_no_switch_stops(self):
        for entry, why in (({"from": "3", "to": "5", "columns": -5}, "track Main would be turned round"),
                           ({"from": "5", "to": "3", "columns": -1}, "not drawn left to right"),
                           ({"from": "3", "to": "99", "columns": -1}, "no switch 99")):
            with self.subTest(entry=entry), self.assertRaisesRegex(SchematicError, why):
                le.drawn_bands(with_prefs("Lower", le_shift={"Lower": [entry]}))

    def test_bad_entries_stop_before_drawing(self):
        for value, why in (([{"from": "3", "to": "5"}], "nothing else"), ([{"from": "3", "to": "5", "columns": 1.5}],
                                                                        "whole number"),
                           ([{"from": "3", "to": "5", "columns": 0}], "other than 0"),
                           ([{"from": "3", "to": "3", "columns": 1}], "both switch 3"),
                           ({"from": "3"}, "must be a list")):
            with self.subTest(value=value), self.assertRaisesRegex(SchematicError, why):
                le.panel(with_prefs("Lower", le_shift={"Lower": value}))
        with self.assertRaisesRegex(SchematicError, "names Nowhere, which is no band"):
            le.panel(with_prefs("Lower", le_shift={"Nowhere": []}))
        with self.assertRaisesRegex(SchematicError, "le_shift for Upper is not in that band's own preferences"):
            le.panel(with_prefs("Lower", le_shift={"Upper": []}))           # the page is Lower's own options here
        page = dict(bands()[-1][2])
        with self.assertRaisesRegex(SchematicError, "le_shift for Upper is in another band's preferences"):
            le.panel(with_prefs("Lower", le_shift={"Upper": []}), page=page)

    def test_a_shift_that_parts_a_diagonal_or_makes_lines_cross_stops(self):
        # e16 runs from switch 12 (column 8, outside 3 to 5) to 13 (column 12, inside): as a diagonal it would tear
        torn = [(t, dict(b, R=dict(b["R"], diag=set(b["R"]["diag"]) | {"e16"})),
                 dict(o, le_shift={"Lower": [{"from": "3", "to": "5", "columns": -1}]}))
                if t.startswith("Lower") else (t, b, o) for t, b, o in bands()]
        with self.assertRaisesRegex(SchematicError, "moves one end of the diagonal track\\(s\\) "):
            le.drawn_bands(torn)
        with mock.patch("schematic.le.let_out_fault", return_value="lines e1 and e2 would cross"), \
                self.assertRaisesRegex(SchematicError, "le_shift of -1 columns from switch 3 to 5: lines e1 and e2"):
            le.drawn_bands(with_prefs("Lower", le_shift={"Lower": [{"from": "3", "to": "5", "columns": -1}]}))

    def test_a_band_preference_on_an_explicit_page_that_no_band_reads_stops(self):
        page = dict(bands()[-1][2], le_crossover_angle={"Lower": 45})
        with self.assertRaisesRegex(SchematicError, "page: le_crossover_angle for Lower is not in that band's own"):
            le.panel(bands(), page=page)
        le.panel(bands(), page=dict(page, le_crossover_angle={"Elsewhere": 45}))     # a band not drawn: not read
        with self.assertRaisesRegex(SchematicError, "must be an object of band"):
            le.panel(with_prefs("Lower", le_shift=[1]))


class LongerStraights(unittest.TestCase):
    def test_only_the_one_tracks_climb_changes(self):
        raw = lower(bands())
        got = lower(le.drawn_bands(with_prefs("Lower", le_longer_straights={
            "Lower": [{"from": "1", "to": "11", "columns": 0.5}]})))
        changed = [sid for sid in raw["need"] if raw["need"][sid] != got["need"][sid]]
        self.assertTrue(changed)
        self.assertEqual(len(changed), 1)
        self.assertAlmostEqual(raw["need"][changed[0]][0] - got["need"][changed[0]][0], 0.5)
        self.assertEqual(got["x"], raw["x"])                    # both switches stay

    def test_no_such_track_or_too_short_a_climb_stops(self):
        for entry, why in (({"from": "1", "to": "13", "columns": 0.5}, "0 tracks join"),
                           ({"from": "1", "to": "11", "columns": 2}, "climbs 2 columns"),
                           ({"from": "1", "to": "11", "columns": -1}, "above zero")):
            with self.subTest(entry=entry), self.assertRaisesRegex(SchematicError, why):
                le.panel(with_prefs("Lower", le_longer_straights={"Lower": [entry]}))
        bare = [(t, dict(b, need={}), dict(o, le_longer_straights={"Lower": [{"from": "1", "to": "11", "columns": 0.5}]}))
                if t.startswith("Lower") else (t, b, o) for t, b, o in bands()]
        with self.assertRaisesRegex(SchematicError, "has no climbs in the solved band"):
            le.drawn_bands(bare)


class CrossoverAngle(unittest.TestCase):
    def test_the_angle_gives_the_run_of_one_row(self):
        P = le.panel(with_prefs("Lower", le_crossover_angle={"Lower": 45}))
        Q = le.panel(bands(), crossover_run={"Lower": le.ROW / math.tan(math.radians(45))})
        self.assertEqual(le.geometry(P), le.geometry(Q))

    def test_bad_angles_and_both_ways_stop_and_a_fit_logs_it(self):
        for bad in (0, 90, "45", True):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "degrees above 0"):
                le.panel(with_prefs("Lower", le_crossover_angle={"Lower": bad}))
        with self.assertRaisesRegex(SchematicError, "give one of them"):
            le.panel(with_prefs("Lower", le_crossover_angle={"Lower": 45}), crossover_run=20.0)
        P = le.panel(with_prefs("Lower", le_crossover_angle={"Lower": 45}), fit=(1300, 700))
        self.assertTrue(any(line.startswith("le_crossover_angle is for a panel drawn at a given grid")
                            for line in P.log))


class TitleClear(unittest.TestCase):
    def page(self, **prefs):
        return dict(bands()[-1][2], **prefs)

    def test_each_title_stands_clear_px_below_the_band_above(self):
        P = le.panel(bands(), page=self.page(le_title_clear=8))
        self.assertEqual(len(P.gaps), 1)
        title = [lb for lb in P.labels if lb.get("kind") == "title"][1]
        self.assertAlmostEqual(title["box"][1] - le.extent(P, 0)[3], 8, delta=1.0)
        self.assertEqual(P.gaps, [le.title_gap(P, 0, 8)])

    def test_a_callers_items_under_a_band_push_the_next_down(self):
        P = le.panel(bands(), page=self.page(le_title_clear=8))
        below = le.extent(P, 0)[3] - P.band_boxes[0][3] + 30      # px under band 0's box
        Q = le.panel(bands(), page=self.page(le_title_clear=8), band_bottoms={bands()[0][0].split()[0]: below})
        self.assertAlmostEqual(Q.gaps[0] - P.gaps[0], 30, delta=1.0)

    def test_band_bottoms_of_a_band_that_moves_down(self):
        """Three bands: band 1 moves down as the gap above it settles, and its band_bottoms moves with it."""
        third = [(t.replace("Lower", "Third"), b, o) for t, b, o in bands() if t.startswith("Lower")]
        three = list(bands()) + third
        page = dict(self.page(le_title_clear=8), band_order=["Upper", "Lower", "Third"])
        P = le.panel(three, page=page)
        self.assertEqual(len(P.gaps), 2)
        below = le.extent(P, 1)[3] - P.band_boxes[1][3] + 30
        Q = le.panel(three, page=page, band_bottoms={"Lower": below})
        self.assertEqual(Q.gaps[0], P.gaps[0])
        self.assertAlmostEqual(Q.gaps[1] - P.gaps[1], 30, delta=1.0)
        title = [lb for lb in Q.labels if lb.get("kind") == "title"][2]
        self.assertAlmostEqual(title["box"][1] - (Q.band_boxes[1][3] + below), 8, delta=1.0)
        for bad, why in ({"Nowhere": 1}, "no band drawn"), ({"Upper": "1"}, "number of px"), ([1], "object"):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, why):
                le.panel(bands(), page=self.page(le_title_clear=8), band_bottoms=bad)

    def test_bad_values_stop_unsettled_gaps_stop_and_a_fit_logs_it(self):
        for bad in (-1, "8", True, float("nan")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, "le_title_clear must be"):
                le.panel(bands(), page=self.page(le_title_clear=bad))
        counter = iter(range(100, 10 ** 6, 17))     # a gap that never settles
        with mock.patch.object(le, "title_gap", side_effect=lambda *_a, **_k: next(counter)), \
                self.assertRaisesRegex(SchematicError, "do not settle"):
            le.panel(bands(), page=self.page(le_title_clear=8))
        P = le.panel(bands(), page=self.page(le_title_clear=8), fit=(1300, 700))
        self.assertTrue(any(line.startswith("le_title_clear is for a panel drawn at a given grid") for line in P.log))


class Stretch(unittest.TestCase):
    PAGE = {"le_stretch": {"factor": 1.25, "tolerance": 0.03}}

    def test_the_grid_is_widened_and_the_shape_checked(self):
        self.assertEqual(le.stretched((0.8, 1.0), self.PAGE), (0.8 * 1.25, 1.0))
        want = (1900 - le.CHROME[0]) / (1140 - le.CHROME[1])
        le.check_stretch((round(1000 * want), 1000), (1900, 1140), self.PAGE)
        with self.assertRaisesRegex(SchematicError, r"set le_stretch's factor to about 1\.\d+ \(now 1\.25\)"):
            le.check_stretch((1984, 1505), (1900, 1140), self.PAGE)

    def test_bad_stretch_stops(self):
        for bad, why in ((None, "hold no le_stretch"), ({"factor": 1.2}, "nothing else"),
                         ({"factor": 0, "tolerance": 0.1}, "factor must"), ({"factor": 1, "tolerance": 1}, "share")):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, why):
                le.stretched((1, 1), {"le_stretch": bad} if bad is not None else {})
        with self.assertRaisesRegex(SchematicError, "factor must"):
            le.panel(bands(), page=dict(bands()[-1][2], le_stretch={"factor": -1, "tolerance": 0.1}))
        with self.assertRaisesRegex(SchematicError, "no room for a panel"):
            le.check_stretch((10, 10), (10, 10), self.PAGE)


class ExtraSteps(unittest.TestCase):
    def fake(self, boxes, band=0):
        return mock.Mock(extras=[{"id": i, "box": b, "band": band} for i, b in boxes.items()])

    def opts(self, **o):
        return [dict({"extra_steps": [], "extra_follow": []}, **o)]

    def test_steps_and_follow(self):
        P = self.fake({"A": (100, 0, 10, 10), "B": (90, 48, 10, 10), "C": (300, 96, 10, 10),
                       "W": (50, 0, 10, 10), "V": (70, 48, 10, 10)})
        extras = [{"id": i} for i in "ABCWV"]
        got = le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "B", "C"]], extra_follow=[["W", "V"]]), extras)
        self.assertEqual(got, {"C": 80, "V": 40})
        given = [dict(e, x=5) if e["id"] == "C" else e for e in extras]       # an item given its x keeps it
        self.assertEqual(le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "B", "C"]]), given), {})
        self.assertEqual(le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "B", "C"]]), []), {})

    def test_what_gives_no_slope_or_is_not_placed_stops(self):
        P = self.fake({"A": (100, 0, 10, 10), "B": (90, 0, 10, 10), "W": (50, 0, 10, 10), "V": (70, 48, 10, 10)})
        extras = [{"id": i} for i in "ABWV"]
        with self.assertRaisesRegex(SchematicError, "stand on one row"):
            le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "B"]]), extras)
        with self.assertRaisesRegex(SchematicError, "no extra_steps group gives the slope"):
            le_prefs.extra_steps(P, self.opts(extra_follow=[["W", "V"]]), extras)
        with self.assertRaisesRegex(SchematicError, "Z is not one of the caller's extras"):
            le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "Z"]]), extras)
        with self.assertRaisesRegex(SchematicError, "not placed on the band"):
            le_prefs.extra_steps(self.fake({"A": (0, 0, 1, 1), "B": (0, 9, 1, 1)}, band=1),
                                 self.opts(extra_steps=[["A", "B"]]), [{"id": "A"}, {"id": "B"}])

    def test_a_second_drawing_that_moves_a_leader_stops(self):
        before = self.fake({"A": (100, 0, 10, 10), "B": (90, 48, 10, 10), "C": (80, 96, 10, 10)})
        extras = [{"id": i} for i in "ABC"]
        opts = self.opts(extra_steps=[["A", "B", "C"]])
        xs = le_prefs.extra_steps(before, opts, extras)
        self.assertEqual(xs, {"C": 80})
        le_prefs.check_steps(before, opts, extras, xs)
        after = self.fake({"A": (104, 0, 10, 10), "B": (90, 48, 10, 10), "C": (80, 96, 10, 10)})
        with self.assertRaisesRegex(SchematicError, "C at 80, its leaders now give 76"):
            le_prefs.check_steps(after, opts, extras, xs)

    def test_no_extras_is_logged(self):
        P = mock.Mock(log=[], extras=[])
        self.assertEqual(le_prefs.extra_steps(P, self.opts(extra_steps=[["A", "B", "C"]]) + self.opts(), []), {})
        self.assertEqual(len(P.log), 1)
        self.assertIn("band 1: the panel has no caller's items", P.log[0])

    def test_options_are_checked_and_are_a_bands_own(self):
        for bad, why in ({"extra_steps": [["A"]]}, "two or more"), ({"extra_steps": [["A", "B"], ["B", "C"]]}, "twice"), \
                        ({"extra_follow": [["A", "A"]]}, "leader, follower"), \
                        ({"extra_steps": [["A", "B", "C"]], "extra_follow": [["A", "C"]]}, "places too"), \
                        ({"extra_steps": [["A", "B", "C"]], "extra_follow": [["C", "D"]]}, "leader C is itself"), \
                        ({"extra_steps": [["A", "B"]], "extra_follow": [["A", "D"], ["D", "E"]]}, "leader D is itself"):
            with self.subTest(bad=bad), self.assertRaisesRegex(SchematicError, why):
                le.panel(with_prefs("Lower", le_labels=bad))
        page = dict(bands()[-1][2], le_labels={"extra_steps": [["A", "B"]]})
        with self.assertRaisesRegex(SchematicError, "extra_steps is a band's own option"):
            le.panel([(t, b, {}) for t, b, _o in bands()], page=page)

    def test_the_panel_is_drawn_again_with_the_stepped_items_at_their_x(self):
        extras = [{"id": "Passing cluster", "block": "Passing", "size": [82, 20]}]
        first = le.panel(bands(), extras=extras)
        x = first.extras[0]["box"][0] - 16
        with mock.patch.object(le_prefs, "extra_steps", return_value={"Passing cluster": x}) as steps, \
                mock.patch.object(le_prefs, "check_steps") as check:
            P = le.panel(bands(), extras=extras)
        self.assertEqual(check.call_args.args[3], {"Passing cluster": x})
        self.assertEqual(steps.call_count, 1)
        self.assertEqual(P.extra_x, {"Passing cluster": x})
        self.assertEqual(P.extras[0]["box"][0], x)
        self.assertEqual(le.panel(bands(), extras=extras).extra_x, {})
        le_labels.verify(P)


if __name__ == "__main__":
    unittest.main()
