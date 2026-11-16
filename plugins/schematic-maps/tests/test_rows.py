"""The fast row search must choose exactly what the plain search chose: same rows, same cost, bit for bit."""
import collections
import copy
import random
import unittest
from unittest import mock

import helpers
from schematic import rows, rules, sheet
from schematic.core import descend
from schematic.rows import Rows, descend_rows, rows_cost, search_rows


def plain_push(above, below):
    """The push the row search used before it worked out costs from the moved classes only."""
    def push(r, c, step):
        new = dict(r)
        new[c] += step
        todo = [c]
        while todo:
            k = todo.pop()
            if step > 0:
                for d in above[k]:
                    if new[d] < new[k] + 1:
                        new[d] = new[k] + 1
                        todo.append(d)
            else:
                for d in below[k]:
                    if new[d] > new[k] - 1:
                        new[d] = new[k] - 1
                        todo.append(d)
        return new
    return push


def random_case(rng):
    """Classes in a random above/below DAG at their lowest rows, random slope terms and a bias like solve's."""
    n = rng.randint(2, 30)
    classes = [f"c{i:02d}" for i in range(n)]
    order = classes[:]
    rng.shuffle(order)
    above, below = collections.defaultdict(set), collections.defaultdict(set)
    for i, a in enumerate(order):
        for b in order[i + 1:]:
            if rng.random() < 0.12:
                above[a].add(b)
                below[b].add(a)
    row = {c: 0 for c in classes}
    for c in order:
        for d in above[c]:
            row[d] = max(row[d], row[c] + 1)
    terms = [(rng.choice(classes), rng.choice(classes), rng.choice((0.5, 1.0, 5.0, 9.0)))
             for _ in range(rng.randint(0, 3 * n))]
    bias = sum(rng.choice((0.0, 0.2, 0.01, 0.21)) for _ in range(rng.randint(0, 40)))
    return row, classes, above, below, terms, bias


class FastRowSearch(unittest.TestCase):
    def test_same_rows_and_same_cost_as_the_plain_search(self):
        rng = random.Random(11)
        for case in range(400):
            row, classes, above, below, terms, bias = random_case(rng)
            want = descend(dict(row), classes, plain_push(above, below), lambda r: rows_cost(r, terms, bias))
            got = descend_rows(dict(row), classes, above, below, terms, bias)
            self.assertEqual(got[0], want[0], f"case {case}")
            self.assertEqual(repr(got[1]), repr(want[1]), f"case {case}")

    def test_a_weight_that_is_not_a_whole_count_of_half_rows_takes_the_plain_search(self):
        rng = random.Random(5)
        for case in range(100):
            row, classes, above, below, terms, bias = random_case(rng)
            terms = terms + [(classes[0], classes[-1], 0.3)]
            want = descend(dict(row), classes, plain_push(above, below), lambda r: rows_cost(r, terms, bias))
            self.assertEqual(search_rows(dict(row), classes, above, below, terms, bias), want, f"case {case}")
        for w in (0.3, float("nan"), float("inf")):
            with self.subTest(w=w), self.assertRaises(ValueError):
                descend_rows({"a": 0, "b": 1}, ["a", "b"], {"b": {"a"}}, {"a": {"b"}}, [("a", "b", w)], 0.0)

    def test_classes_with_no_rules_need_no_defaultdict(self):
        got = descend_rows({"a": 0, "b": 0}, ["a", "b"], {}, {}, [("a", "b", 1.0)], 0.0)
        none = collections.defaultdict(set)
        self.assertEqual(got, descend({"a": 0, "b": 0}, ["a", "b"], plain_push(none, none),
                                      lambda r: rows_cost(r, [("a", "b", 1.0)], 0.0)))

    def test_whole_sheets_are_the_same_as_with_the_plain_search(self):
        """The example sheet, with and without hints (cycles broken by the tolerant search among them), drawn
        with the fast search and with core.descend throughout: the same page and log."""
        inputs, data = [(helpers.graph(), "example")], helpers.data_with_signals()
        for hints in (False, True):
            with self.subTest(hints=hints):
                fast = sheet.solve(inputs, data, True, hints)
                with mock.patch.object(rows, "half_rows", lambda w: None):
                    plain = sheet.solve(inputs, data, True, hints)
                self.assertEqual(fast.svg(), plain.svg())
                self.assertEqual(fast.log, plain.log)


class RowsMemo(unittest.TestCase):
    def rows(self, memo):
        lower = next(b for t, b, _ in helpers.build(False).bands if t == "Lower level")
        nodes, strands = copy.deepcopy(lower["nodes"]), copy.deepcopy(lower["strands"])   # the tests edit them
        snaps = [sorted(strands)[i:i + 4] for i in range(0, len(strands), 3)]     # overlapping runs of four tracks
        r = Rows(nodes, strands, snaps, rule_pins=rules.level_legs(nodes, strands, {}))
        if not memo:
            r.solve = r.solve_now
        return r

    def test_memo_changes_nothing_across_repeated_optimise_calls(self):
        fast, plain = self.rows(True), self.rows(False)
        a, b = sorted(fast.strands)[:2]
        for extra in (set(), {(a, b)}, {(b, a)}):
            for _ in range(2):          # the second call starts from the first call's legs and reads the memo
                fast.extra = plain.extra = set(extra)
                self.assertEqual(fast.optimise(), plain.optimise())
                self.assertEqual((fast.flat, fast.dropped), (plain.flat, plain.dropped))

    def test_memo_is_dropped_when_what_solve_reads_changes(self):
        fast, plain = self.rows(True), self.rows(False)
        a, b = sorted(fast.strands)[:2]
        changes = [lambda r: setattr(r, "spans", {s: (0, 1) for s in r.strands}),
                   lambda r: setattr(r, "spans", {s: (i, i + 1) for i, s in enumerate(sorted(r.strands))}),
                   lambda r: r.extra.add((a, b)),
                   lambda r: r.strands[a].update(cm=r.strands[a]["cm"] + 50),     # the graph, edited in place
                   lambda r: setattr(r, "free", {b})]
        fast.optimise()
        for change in changes:
            memo = fast.memo_keep[1]
            change(fast)
            change(plain)
            self.assertEqual(fast.optimise(), plain.optimise())
            self.assertEqual((fast.flat, fast.dropped), (plain.flat, plain.dropped))
            self.assertIsNot(fast.memo_keep[1], memo)
        memo = fast.memo_keep[1]
        fast.optimise()
        self.assertIs(fast.memo_keep[1], memo)          # nothing changed: the memo is kept

    def test_optimise_hands_back_a_copy(self):
        fast = self.rows(True)
        first = fast.optimise()
        first["srow"].clear()
        self.assertTrue(fast.optimise()["srow"])


if __name__ == "__main__":
    unittest.main()
