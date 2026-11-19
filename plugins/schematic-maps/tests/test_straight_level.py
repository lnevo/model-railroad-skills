"""R8 straight level, the same-leg ladder chain, the level cell before straight-level points and branch_leg."""
import unittest

from schematic import columns, edits, rules
from schematic.core import SchematicError


def band(switches, ends, tracks):
    """nodes and strands from switch ids, end ids and tracks (sid, (node, port), (node, port), cm, main)."""
    nodes = {n: dict(kind="switch", label=n, outs={}, ins={}) for n in switches}
    nodes.update({n: dict(kind="end", label=n, outs={}, ins={}) for n in ends})
    strands = {}
    for sid, src, dst, cm, main in tracks:
        strands[sid] = dict(src=src, dst=dst, cm=cm, main=main)
        nodes[src[0]]["outs"][src[1]] = sid
        nodes[dst[0]]["ins"][dst[1]] = sid
    return nodes, strands


def lone_switch(main_b=False, main_c=False, b_cm=150.0, b_sid="b"):
    """Switch s off the main by A, with tracks to ends on B and C."""
    return band(["s"], ["w", "e1", "e2"],
                [("a", ("w", "E"), ("s", "A"), 120.0, main_b or main_c),
                 (b_sid, ("s", "B"), ("e1", "E"), b_cm, main_b),
                 ("c", ("s", "C"), ("e2", "E"), 150.0, main_c)])


class StraightLevel(unittest.TestCase):
    def test_a_switch_keeps_its_straight_leg_level(self):
        nodes, strands = lone_switch()
        self.assertEqual(rules.straight_pins(nodes, strands), {"s": "B"})
        self.assertEqual(rules.level_legs(nodes, strands, {}), {"s": "B"})

    def test_the_main_rule_wins_over_the_straight_rule(self):
        nodes, strands = lone_switch(main_c=True)
        self.assertEqual(rules.straight_pins(nodes, strands), {"s": "B"})
        self.assertEqual(rules.level_legs(nodes, strands, {}), {"s": "C"})

    def test_a_loop_entry_is_left_to_the_search(self):
        nodes, strands = lone_switch(main_b=True, main_c=True)
        self.assertEqual(rules.straight_pins(nodes, strands), {})

    def test_a_loop_return_on_leg_b_is_left_to_the_search(self):
        nodes, strands = lone_switch(b_cm=300.0, b_sid="r.0")
        self.assertEqual(rules.straight_pins(nodes, strands), {})

    def test_a_wye_with_no_leg_b_has_no_pin(self):
        nodes, strands = band(["s"], ["w", "e2"], [("a", ("w", "E"), ("s", "A"), 120.0, False),
                                                   ("c", ("s", "C"), ("e2", "E"), 150.0, False)])
        self.assertEqual(rules.straight_pins(nodes, strands), {})

    def test_a_crossover_diagonal_on_leg_b_is_left_to_the_search(self):
        # p's diverging leg joins q's straight leg by a short track: one crossover on the ground
        nodes, strands = band(["p", "q"], ["w1", "w2", "e1", "e2"],
                              [("pa", ("w1", "E"), ("p", "A"), 120.0, True),
                               ("pb", ("p", "B"), ("e1", "E"), 120.0, True),
                               ("x", ("p", "C"), ("q", "B"), 10.0, False),
                               ("qa", ("w2", "E"), ("q", "A"), 120.0, False),
                               ("qc", ("q", "C"), ("e2", "E"), 120.0, False)])
        pins = rules.straight_pins(nodes, strands)
        self.assertNotIn("q", pins)
        self.assertEqual(pins["p"], "B")
        self.assertTrue(rules.crossover_leg(nodes, strands, "q", "x"))
        self.assertFalse(rules.crossover_leg(nodes, strands, "q", "x", {"ladder_link_max_cm": 5}))

    def test_two_switches_back_to_back_keep_their_straight_legs_level(self):
        # p and q joined straight leg to straight leg by a short track: one through track, no crossover
        nodes, strands = band(["p", "q"], ["w1", "w2", "e1", "e2"],
                              [("pa", ("w1", "E"), ("p", "A"), 120.0, False),
                               ("x", ("p", "B"), ("q", "B"), 10.0, False),
                               ("pc", ("p", "C"), ("e1", "E"), 120.0, False),
                               ("qa", ("w2", "E"), ("q", "A"), 120.0, False),
                               ("qc", ("q", "C"), ("e2", "E"), 120.0, False)])
        self.assertEqual(rules.straight_pins(nodes, strands), {"p": "B", "q": "B"})


def ladder(leg_links):
    """Switches 1..n joined each by a short link from leg `leg_links[i]` to the next one's A; the other leg of each,
    and both legs of the last, run to yard track ends."""
    n = len(leg_links) + 1
    sw = [f"s{i}" for i in range(1, n + 1)]
    tracks, ends = [("lead", ("w", "E"), ("s1", "A"), 120.0, False)], ["w"]
    for i, leg in enumerate(leg_links):
        other = "C" if leg == "B" else "B"
        tracks.append((f"l{i}", (sw[i], leg), (sw[i + 1], "A"), 25.0, False))
        tracks.append((f"y{i}", (sw[i], other), (f"t{i}", "E"), 150.0, False))
        ends.append(f"t{i}")
    for leg in "BC":
        tracks.append((f"y{leg}", (sw[-1], leg), (f"t{leg}", "E"), 150.0, False))
        ends.append(f"t{leg}")
    return band(sw, ends, tracks)


class LadderChain(unittest.TestCase):
    def test_links_on_one_leg_make_a_ladder(self):
        nodes, strands = ladder(["B", "B"])
        self.assertEqual(rules.ladder_switches(nodes, None, strands), {"s1": "C", "s2": "C"})

    def test_the_next_switch_of_a_ladder_is_left_to_the_search(self):
        nodes, strands = ladder(["B", "B"])
        self.assertNotIn("s3", rules.straight_pins(nodes, strands))
        self.assertEqual(rules.level_legs(nodes, strands, {}), {"s1": "C", "s2": "C"})

    def test_links_on_mixed_legs_are_no_ladder(self):
        nodes, strands = ladder(["B", "C"])
        self.assertEqual(rules.ladder_switches(nodes, None, strands), {})
        self.assertEqual(rules.straight_pins(nodes, strands), {"s1": "B", "s2": "B", "s3": "B"})

    def test_one_link_is_no_ladder(self):
        nodes, strands = ladder(["C"])
        self.assertEqual(rules.ladder_switches(nodes, None, strands), {})


class LevelCellBeforePoints(unittest.TestCase):
    def test_points_on_a_level_straight_leg(self):
        nodes, strands = lone_switch()
        nrow = {"s": 2}
        self.assertTrue(columns.points_on_straight(nodes, {"b": 2, "c": 3}, nrow, ("s", "A")))
        self.assertFalse(columns.points_on_straight(nodes, {"b": 3, "c": 2}, nrow, ("s", "A")))
        self.assertFalse(columns.points_on_straight(nodes, {"b": 2, "c": 3}, nrow, ("s", "B")))
        self.assertFalse(columns.points_on_straight(nodes, {"b": 2}, nrow, ("w", "E")))


class LadderLinksKeepTheirStep(unittest.TestCase):
    """The level cell before straight-level points is not added on a ladder's links: each rung steps one cell (R6)."""

    @staticmethod
    def link_width(leg_links):
        nodes, strands = ladder(leg_links)
        for sid, s in strands.items():
            s.update(name="", edge=sid)
        sw = sorted(n for n, d in nodes.items() if d["kind"] == "switch")
        nrow = {n: i for i, n in enumerate(sw)}                 # each switch a row below the one before
        nrow.update({n: 0 for n, d in nodes.items() if d["kind"] == "end"})
        srow = {}
        for sid, s in strands.items():
            (u, up), (v, _vp) = s["src"], s["dst"]
            if sid.startswith("l"):
                srow[sid] = nrow[v]                             # the link slopes at its start, level into the points
            elif nodes[u]["kind"] == "switch":
                srow[sid] = nrow[u] if up == "B" else nrow[u] + 1   # leg B level (the yard track), C sloped
            else:
                srow[sid] = nrow[v]
        for n in sw:
            nrow.setdefault(n, 0)
        _x, need = columns.place(nodes, strands, dict(srow=srow, nrow=nrow, diag=set()), {}, {})
        return need["l0"][2]

    def test_a_ladder_link_gets_no_extra_cell(self):
        self.assertEqual(self.link_width(["C", "C"]), 1)

    def test_a_lone_link_into_straight_level_points_gets_one(self):
        self.assertEqual(self.link_width(["C"]), 2)


class BranchLeg(unittest.TestCase):
    @staticmethod
    def graph():
        sw = lambda label: dict(kind="switch", label=label, alias=label, hand=1, dirs={})    # noqa: E731
        return dict(nodes={"p": sw("1"), "q": sw("2")},
                    edges=[dict(u="p", up="B", v="q", vp="A", cm=100.0, id="e0", names=[], main=False)])

    NEW = dict(op="switch", label="9", hand="L", source="owner", on=["1", "2"], cm_from_first=40, points_toward="2",
               c={"end": "Spur"})

    def legs_of_new(self, g):
        x = next(n for n, d in g["nodes"].items() if d.get("label") == "9")
        out = {}
        for e in g["edges"]:
            for n, p, other in ((e["u"], e["up"], e["v"]), (e["v"], e["vp"], e["u"])):
                if n == x:
                    out[p] = g["nodes"][other].get("label") or g["nodes"][other].get("kind")
        return out

    def test_the_branch_hangs_off_c_by_default(self):
        g = self.graph()
        edits.apply_edits(g, [dict(self.NEW)])
        self.assertEqual(self.legs_of_new(g), {"A": "2", "B": "1", "C": "end"})     # points toward 2

    def test_branch_leg_b_puts_the_through_track_on_c(self):
        g = self.graph()
        edits.apply_edits(g, [dict(self.NEW, branch_leg="B")])
        self.assertEqual(self.legs_of_new(g), {"A": "2", "B": "end", "C": "1"})

    def test_a_bad_branch_leg_stops_before_the_switch_is_added(self):
        g = self.graph()
        with self.assertRaisesRegex(SchematicError, "branch_leg must be 'B' or 'C', not 'A'"):
            edits.apply_edits(g, [dict(self.NEW, branch_leg="A")])
        self.assertEqual(set(g["nodes"]), {"p", "q"})


if __name__ == "__main__":
    unittest.main()
