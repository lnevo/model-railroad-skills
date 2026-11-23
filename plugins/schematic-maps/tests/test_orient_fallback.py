"""Plans the first orient pass cannot solve: a balloon loop closed on a switch's through route, and plans that need
turnbacks on straight runs."""
import unittest
import unittest.mock

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import layout, orient, rules
from schematic.draw import DEFAULTS


class Graph:
    def __init__(self):
        self.nodes, self.edges = {}, []

    def switch(self, n, x, y, hand=1):
        self.nodes[n] = dict(kind="switch", label=str(n), xy=[x, y], district="Main", hand=hand,
                             dirs=dict(A=[-1, 0], B=[1, 0], C=[1, 0.4]))

    def end(self, n, x, y):
        self.nodes[n] = dict(kind="end", sub="bumper", label="", xy=[x, y])

    def edge(self, u, up, v, vp):
        self.edges.append(dict(u=u, up=up, v=v, vp=vp, names=[], cm=50.0, link=False, main=False,
                               district="Main", hidden=False, id=f"e{len(self.edges)}"))

    def graph(self):
        return dict(nodes=self.nodes, edges=self.edges, notes=[], cuts=[])


def loop_through():
    g = Graph()
    g.switch("s1", 100, 100)
    g.end("b1", 300, 100)
    g.edge("s1", "A", "s1", "B")
    g.edge("s1", "C", "b1", "E")
    return g.graph()


def straight_digon(n=42):
    """A chain of n switches, each with a stub, closed by two parallel runs between two switches whose legs
    point the same way: both must be turnbacks, and they are straight."""
    g = Graph()
    for i in range(n):
        g.switch(f"c{i}", 100 + 60 * i, 300)
        g.end(f"x{i}", 100 + 60 * i, 330)
        g.edge(f"c{i}", "C", f"x{i}", "E")
    for i in range(n - 1):
        g.edge(f"c{i}", "B", f"c{i + 1}", "A")
    g.switch("u", 100, 100)
    g.switch("v", 900, 100)
    g.nodes["u"]["dirs"] = dict(A=[-1, 0], B=[-1, 0], C=[1, 0.4])
    g.nodes["v"]["dirs"] = dict(A=[1, 0], B=[1, 0], C=[1, 0.4])
    g.edge("u", "C", "c0", "A")
    g.edge(f"c{n - 1}", "B", "v", "C")
    g.edge("u", "A", "v", "A")
    g.edge("u", "B", "v", "B")
    return g.graph()


class BalloonOnThroughRoute(unittest.TestCase):
    def test_orient_finds_a_way_and_leaves_the_loop_out_of_the_turnbacks(self):
        found = orient.orient(loop_through())
        self.assertTrue(found)
        self.assertTrue(all("e0" not in T for _, T in found))

    def test_layout_draws_it_and_says_so(self):
        warnings = []
        band = layout.layout(loop_through(), {}, warnings)
        self.assertTrue(band["strands"])
        self.assertTrue(any("balloon loop on its through route" in w and "s1" in w for w in warnings), warnings)

    def test_the_stubs_are_not_fold_halves_and_share_the_length(self):
        g = loop_through()
        before = next(e for e in g["edges"] if e["id"] == "e0")
        split, _ = orient.split_through_loops(g)
        stubs = [e for e in split["edges"] if e.get("split")]
        self.assertEqual(len(stubs), 2)
        for e in stubs:
            self.assertFalse(rules.is_fold(e["id"]), e["id"])
            self.assertAlmostEqual(e["cm"], before["cm"] / 2, delta=0.1)

    def test_a_turnbacks_preference_naming_the_loop_warns_instead_of_failing(self):
        g = loop_through()
        for e in g["edges"]:
            if e["id"] == "e0":
                e["names"] = ["LOOP"]
        warnings = []
        band = layout.layout(g, dict(DEFAULTS, turnbacks=["LOOP"]), warnings)
        self.assertTrue(band["strands"])
        self.assertTrue(any("LOOP" in w and "balloon loop" in w and "turnbacks" in w for w in warnings), warnings)

    def test_a_loop_on_the_lead_leg_is_not_touched(self):
        g = Graph()
        g.switch("s1", 100, 100)
        g.end("b1", 300, 100)
        g.edge("s1", "B", "s1", "C")
        g.edge("s1", "A", "b1", "E")
        self.assertEqual(orient.split_through_loops(g.graph())[1], [])


class StraightTurnbacks(unittest.TestCase):
    def test_the_second_pass_finds_turnbacks_on_straight_runs(self):
        g = straight_digon()
        notes = []
        found = orient.orient(g, seconds=40, log=notes.append)
        self.assertTrue(found)
        sig, T = found[0]
        self.assertLessEqual(len(T), 3)
        self.assertTrue(any("second pass" in n for n in notes), notes)

    def test_the_second_pass_gives_the_same_answer_twice(self):
        a = orient.orient(straight_digon(), seconds=40)
        b = orient.orient(straight_digon(), seconds=40)
        self.assertEqual([sorted(T) for _, T in a], [sorted(T) for _, T in b])

    def test_the_second_pass_out_of_time_gives_nothing_not_a_shorter_answer(self):
        g = straight_digon()
        sw = [e for e in g["edges"] if all(g["nodes"][n]["kind"] in orient.JUNCTION for n in (e["u"], e["v"]))]
        self.assertEqual(orient.second_pass(g, sw, [], -1.0, 10), [])
        self.assertTrue(orient.second_pass(g, sw, [], 60.0, 10))

    def test_the_second_pass_shares_the_deadline_of_the_raised_steps(self):
        seen = []
        real = orient._second_pass
        t0 = orient.time.monotonic()

        def spy(g, sw, must, deadline, keep):
            seen.append(deadline - t0)
            return real(g, sw, must, deadline, keep)

        with unittest.mock.patch.object(orient, "_second_pass", spy):
            orient.orient(straight_digon(), seconds=40)
        self.assertEqual(len(seen), 1)
        self.assertLessEqual(seen[0], 40.5)

    def test_a_plan_the_first_pass_solves_does_not_run_it(self):
        notes = []
        orient.orient(loop_through(), log=notes.append)
        self.assertFalse(any("second pass" in n for n in notes), notes)


if __name__ == "__main__":
    unittest.main()
