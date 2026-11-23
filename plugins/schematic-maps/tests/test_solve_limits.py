"""The solve never stops on a setting or a traceback: the turnback cap rises when nothing is found, and a band whose
columns do not settle moves on to the next orientation."""
import collections
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import layout, orient, sheet
from schematic.core import SchematicError


def triangle():
    """Three switches in a ring whose runs need one turnback; each other leg ends on a bumper."""
    nodes = {n: dict(kind="switch", label=n, xy=[i * 10, 0], hand=1, dirs={}) for i, n in enumerate(("s1", "s2", "s3"))}
    edges, k = [], 0

    def edge(u, up, v, vp):
        nonlocal k
        k += 1
        edges.append(dict(id=f"e{k}", u=u, up=up, v=v, vp=vp, names=[], cm=50.0, link=False, main=False, hidden=False))

    edge("s1", "A", "s2", "A")
    edge("s2", "B", "s3", "B")
    edge("s3", "C", "s1", "B")
    for n, port in (("s1", "C"), ("s2", "C"), ("s3", "A")):
        nodes[f"end{n}"] = dict(kind="end", sub="bumper", label="", xy=[0, 5])
        edge(n, port, f"end{n}", "E")
    return dict(nodes=nodes, edges=edges)


class TurnbackCap(unittest.TestCase):
    def test_the_first_cap_is_kept_when_it_finds_something(self):
        found = orient.orient(triangle(), max_turnbacks=3)
        self.assertTrue(all(len(T) >= 1 for _, T in found))

    def test_a_cap_that_is_too_low_is_raised_not_reported(self):
        notes = []
        found = orient.orient(triangle(), max_turnbacks=0, log=notes.append)
        self.assertTrue(found)
        self.assertTrue(any("turnbacks" in n for n in notes), notes)

    def test_with_nothing_to_find_the_error_does_not_ask_for_a_setting(self):
        with mock.patch.object(orient, "colour", return_value=None):
            with self.assertRaises(SchematicError) as cm:
                orient.orient(triangle(), max_turnbacks=0)
        self.assertNotIn("max_turnbacks", str(cm.exception))
        self.assertIn("no orientation", str(cm.exception))


class Unsettled(unittest.TestCase):
    def test_the_next_orientation_is_tried_when_one_does_not_settle(self):
        g, real, calls = triangle(), layout.layout_one, collections.Counter()

        def flaky(*a, **kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise layout.Unsettled("columns: constraints do not settle")
            return real(*a, **kw)

        warnings = []
        with mock.patch.object(layout, "layout_one", flaky):
            band = layout.layout(g, {}, warnings)
        self.assertGreater(calls["n"], 1)
        self.assertIn("nodes", band)
        self.assertTrue(any("do not settle" in w for w in warnings), warnings)

    def test_when_every_orientation_fails_the_error_is_clean(self):
        with mock.patch.object(layout, "layout_one", side_effect=layout.Unsettled("columns: constraints do not settle")):
            with self.assertRaisesRegex(SchematicError, "did not settle"):
                layout.layout(triangle(), {}, [])


class FaultLog(unittest.TestCase):
    def test_the_log_lists_the_faults_it_counts(self):
        fault = ("crossing", "e1", ((0, 0), (1, 1)), "e2", ((0, 1), (1, 0)))
        with mock.patch.object(layout, "faults", return_value=[fault]):
            s = sheet.build([(helpers.graph(), "example")], helpers.data_with_signals(), preferences=False)
        lines = [ln for ln in s.log if "drawing faults" in ln]
        self.assertTrue(lines)
        self.assertTrue(all("1 drawing faults ['crossing: e1 / e2']" in ln for ln in lines), lines)


if __name__ == "__main__":
    unittest.main()
