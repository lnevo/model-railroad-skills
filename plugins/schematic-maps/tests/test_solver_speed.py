"""The faster solve gives the same drawings: the lean left-to-right graph in orient, the column search that prices a
move from the nodes it moves, the feasibility-only column check, and the row flips that skip a search that cannot
win."""
import random
import unittest
from unittest import mock

import copy

import helpers
from schematic import columns, layout, orient, rows, rules, sheet
from schematic.core import JUNCTION, descend
from test_solve_limits import triangle


def plain_descend_columns(start, items, push, cost, weight):
    """core.descend over full column dicts, as place ran before descend_columns."""
    return descend(start, items, lambda xs, n, step: {**xs, **push(xs, n, step)}, cost)


class LeanGraph(unittest.TestCase):
    def test_the_same_counts_as_building_the_strands(self):
        graphs = [triangle(), helpers.graph()]
        for g in graphs:
            g, _ = orient.split_through_loops(g)
            frame = orient.Frame(g)
            junctions = sorted(n for n, d in g["nodes"].items() if d["kind"] in JUNCTION)
            rng = random.Random(4)
            for case in range(200):
                sig = {n: rng.choice((1, -1)) for n in junctions}
                nodes, strands = orient.build(g, sig, set())
                col = orient.columns(nodes, strands)
                want = (orient.cyclic_nodes(nodes, strands), max(col.values()) if col else None)
                self.assertEqual(frame.dag(sig), want, f"case {case}")


class ParityTest(unittest.TestCase):
    def test_parity_says_what_colour_says(self):
        for g in (triangle(), helpers.graph()):
            g, _ = orient.split_through_loops(g)
            sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in JUNCTION for n in (e["u"], e["v"]))]
            parity = orient.Parity(g, sw)
            rng = random.Random(8)
            for case in range(300):
                ids = {e["id"] for e in sw if rng.random() < rng.choice((0.1, 0.3, 0.6))}
                self.assertEqual(parity.fits(ids), orient.colour(g, sw, ids) is not None, f"case {case}")

    def test_the_search_finds_the_same_with_and_without_the_parity_test(self):
        g, _ = orient.split_through_loops(helpers.graph())
        sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in JUNCTION for n in (e["u"], e["v"]))]
        cand = [e for e in sw if not e["link"]]

        class Everything:           # a parity test that lets every set through to colour
            mask = {e["id"]: 0 for e in sw}
            target = 0

        fast, plain = [], []
        orient.search(g, sw, [], cand, range(4), fast, None)
        orient.search(g, sw, [], cand, range(4), plain, None, parity=Everything())
        self.assertEqual(sorted((c, i) for c, i, _, _ in fast), sorted((c, i) for c, i, _, _ in plain))
        self.assertTrue(fast)


class ColumnSearch(unittest.TestCase):
    def test_whole_sheets_are_the_same_as_with_the_plain_search(self):
        inputs, data = [(helpers.graph(), "example")], helpers.data_with_signals()
        for hints in (False, True):
            with self.subTest(hints=hints):
                fast = sheet.solve(inputs, data, True, hints)
                with mock.patch.object(columns, "descend_columns", plain_descend_columns):
                    plain = sheet.solve(inputs, data, True, hints)
                self.assertEqual(fast.svg(), plain.svg())
                self.assertEqual(fast.log, plain.log)

    def test_the_check_alone_fails_where_the_placement_fails(self):
        calls = []
        real = columns.place

        def both(*a, check=False, **k):
            try:
                real(*a, **k)
                full = None
            except columns.Unsettled as e:
                full = str(e)
            try:
                got = real(*a, check=True, **k)
                quick = None
            except columns.Unsettled as e:
                got, quick = None, str(e)
            calls.append(check)
            self.assertIsNone(got)
            self.assertEqual(quick, full)
            return real(*a, check=check, **k)

        with mock.patch("schematic.layout.place", both):
            sheet.solve([(helpers.graph(), "example")], helpers.data_with_signals(), True, True)
        self.assertTrue(calls)


class BigBand(unittest.TestCase):
    def test_a_big_band_lays_out_fewer_orientations_and_says_so(self):
        g, real, calls, starts = helpers.graph(), layout.layout_one, [], []
        real_opt = rows.Rows.optimise

        def counted(*a, **kw):
            calls.append(kw.get("big"))
            return real(*a, **kw)

        def optimise(self):
            starts.append((self.optimised, self.restart_every_round))
            return real_opt(self)

        warnings = []
        with mock.patch.object(layout, "BIG_BAND", 1), mock.patch.object(layout, "layout_one", counted), \
                mock.patch.object(rows.Rows, "optimise", optimise), \
                mock.patch.object(layout, "faults", return_value=[("cross", "a", ((0, 0), (1, 1)), "b", ((0, 1), (1, 0)))]):
            layout.layout(g, {}, warnings)
        self.assertTrue(calls)
        self.assertLessEqual(len(calls), layout.BIG_ORIENTATIONS)      # no drawing is perfect, yet only three are tried
        self.assertTrue(all(calls))
        self.assertTrue(any(w.startswith("big band") for w in warnings), warnings)
        self.assertTrue(all(not every for _, every in starts))

    def test_the_local_row_search_keeps_every_rule(self):
        lower = next(b for t, b, _ in helpers.build(False).bands if t == "Lower level")
        nodes, strands = copy.deepcopy(lower["nodes"]), copy.deepcopy(lower["strands"])
        snaps = [sorted(strands)[i:i + 4] for i in range(0, len(strands), 3)]
        r = rows.Rows(nodes, strands, snaps, rule_pins=rules.level_legs(nodes, strands, {}))
        r.local, r.restart_every_round = True, False
        for _ in range(2):
            got = r.optimise()
            p = r.prepare()             # the classes and rules of the legs it chose
            find = p["find"]
            row = {find(s): got["srow"][s] for s in got["srow"]}
            for c, ds in p["above"].items():
                for d in ds:
                    self.assertGreater(row[d], row[c])
            self.assertIsNone(r.warm)

    def test_a_small_band_is_not_big(self):
        warnings = []
        layout.layout(helpers.graph(), {}, warnings)
        self.assertFalse(any(w.startswith("big band") for w in warnings))


if __name__ == "__main__":
    unittest.main()
