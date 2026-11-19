"""Single crossovers whose halves join by leg B or C (core.crossover_halves): the pairing by switch number, its
errors, the solver's level leg (R8), and both panels (tests/xover_legs.py is the railroad)."""
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts the plugin on the path)
import xover_legs
from schematic import cats, core, le, rules
from schematic.core import SchematicError
from test_straight_level import band as small_band

THROUGH = {"X3A": "B", "X3B": "B", "X5A": "B", "X5B": "C"}     # each half's normal leg in xover_legs


def two_halves(labels, legs, cm=20.0):
    """Switches p and q (labelled `labels`) joined by one track x from p's leg legs[0] to q's leg legs[1]; every
    other leg runs to an end of its own."""
    tracks = [("x", ("p", legs[0]), ("q", legs[1]), cm, False)]
    ends = []
    for n, link in (("p", legs[0]), ("q", legs[1])):
        for leg in "ABC":
            if leg != link:
                ends.append(f"{n}{leg}")
                tracks.append((f"t{n}{leg}", (n, leg), (f"{n}{leg}", "E"), 150.0, False))
    nodes, strands = small_band(["p", "q"], ends, tracks)
    nodes["p"]["label"], nodes["q"]["label"] = labels
    return nodes, strands


class Pairing(unittest.TestCase):
    def test_switch_numbers(self):
        self.assertEqual(core.switch_number("23A"), "23")
        self.assertEqual(core.switch_number("23B*"), "23")
        self.assertEqual(core.switch_number("23"), "23")
        self.assertEqual(core.switch_number("CLUB"), "CLUB")       # a letter after no digit is part of the name
        self.assertEqual(core.crossover_name("23B"), "23")
        self.assertEqual(core.crossover_name("23"), "23")

    def test_halves_by_leg(self):
        for labels in (("3A", "3B"), ("3B", "3A"), ("3", "3")):
            for legs in (("C", "C"), ("C", "B"), ("B", "C"), ("B", "B")):
                with self.subTest(labels=labels, legs=legs):
                    got = core.crossover_halves(*two_halves(labels, legs))
                    self.assertEqual(got, {"p": (legs[0], "q", "x"), "q": (legs[1], "p", "x")})
                    self.assertEqual({n: core.through_leg(v[0]) for n, v in got.items()},
                                     {"p": "B" if legs[0] == "C" else "C", "q": "B" if legs[1] == "C" else "C"})

    def test_other_numbers_or_no_link_are_two_switches(self):
        self.assertEqual(core.crossover_halves(*two_halves(("3A", "4B"), ("C", "C"))), {})
        # lettered halves of one number with no track between them: two plain switches
        nodes, strands = small_band(["p", "q"], ["e1", "e2"], [("a", ("p", "B"), ("e1", "E"), 100.0, False),
                                                               ("b", ("q", "B"), ("e2", "E"), 100.0, False)])
        nodes["p"]["label"], nodes["q"]["label"] = "3A", "3B"
        self.assertEqual(core.crossover_halves(nodes, strands), {})

    def test_one_number_joined_at_the_points_is_two_switches(self):
        for labels in (("3A", "3B"), ("3", "3"), ("3A", "3A"), ("3", "3B")):
            for legs in (("A", "C"), ("B", "A"), ("A", "A")):
                with self.subTest(labels=labels, legs=legs):
                    self.assertEqual(core.crossover_halves(*two_halves(labels, legs)), {})

    def test_ambiguous_lettered_halves_stop(self):
        for labels in (("3A", "3A"), ("3B", "3B"), ("3", "3B"), ("3A", "3*"), ("3B*", "3B")):
            with self.subTest(labels=labels), \
                    self.assertRaisesRegex(SchematicError, "not lettered one A and one B"):
                core.crossover_halves(*two_halves(labels, ("C", "B")))

    @staticmethod
    def chain(labels):
        """p, q and r: p's leg C joined to q's leg C, q's leg B to r's leg C."""
        nodes, strands = small_band(["p", "q", "r"], ["e1", "e2", "e3", "e4", "e5"], [
            ("pq", ("p", "C"), ("q", "C"), 20.0, False), ("qr", ("q", "B"), ("r", "C"), 20.0, False),
            ("pa", ("e1", "E"), ("p", "A"), 100.0, False), ("pb", ("p", "B"), ("e2", "E"), 100.0, False),
            ("qa", ("q", "A"), ("e3", "E"), 100.0, False), ("ra", ("e4", "E"), ("r", "A"), 100.0, False),
            ("rb", ("r", "B"), ("e5", "E"), 100.0, False)])
        for n, label in zip("pqr", labels):
            nodes[n]["label"] = label
        return nodes, strands

    def test_a_lettered_half_joined_to_two_of_its_number_stops(self):
        with self.assertRaisesRegex(SchematicError, "crossover half 3B: joined to 3A and 3A, more than one"):
            core.crossover_halves(*self.chain(("3A", "3B", "3A")))

    def test_three_alike_keep_the_pair_joined_c_to_c(self):
        # before leg B could join a crossover, p and q (C to C) were the crossover and r a switch: still so
        self.assertEqual(core.crossover_halves(*self.chain(("3", "3", "3"))),
                         {"p": ("C", "q", "pq"), "q": ("C", "p", "pq")})

    def test_the_solver_stops_on_a_bad_pair(self):
        with self.assertRaisesRegex(SchematicError, "not lettered one A and one B"):
            xover_legs.bands({"X5B": "5A"})


class LevelLeg(unittest.TestCase):
    """R8: a crossover half keeps its normal (through) leg level, not its straight leg."""

    def test_a_half_joined_by_leg_b_keeps_leg_c_level(self):
        nodes, strands = two_halves(("5A", "5B"), ("C", "B"))
        self.assertEqual(rules.straight_pins(nodes, strands), {"p": "B", "q": "C"})
        self.assertTrue(rules.crossover_leg(nodes, strands, "q", "x"))
        self.assertTrue(rules.crossover_leg(nodes, strands, "p", "x"))

    def test_c_to_c_keeps_leg_b_level_as_before(self):
        nodes, strands = two_halves(("3A", "3B"), ("C", "C"))
        self.assertEqual(rules.straight_pins(nodes, strands), {"p": "B", "q": "B"})

    def test_a_straight_leg_that_meets_a_halfs_through_leg_is_no_diagonal(self):
        # s's leg B runs a short way to half q's leg C, its through leg: no diagonal, so s keeps B level (a short
        # track to a plain switch's leg C is still taken for a crossover's diagonal)
        nodes, strands = small_band(["p", "q", "s"], ["pa", "pb", "qa", "sa", "sc"], [
            ("x", ("p", "C"), ("q", "B"), 20.0, False), ("tpa", ("pa", "E"), ("p", "A"), 150.0, False),
            ("tpb", ("p", "B"), ("pb", "E"), 150.0, False), ("tqa", ("q", "A"), ("qa", "E"), 150.0, False),
            ("sq", ("s", "B"), ("q", "C"), 20.0, False), ("tsa", ("sa", "E"), ("s", "A"), 150.0, False),
            ("tsc", ("s", "C"), ("sc", "E"), 150.0, False)])
        nodes["p"]["label"], nodes["q"]["label"], nodes["s"]["label"] = "5A", "5B", "7"
        pins = rules.straight_pins(nodes, strands)
        self.assertEqual((pins["p"], pins["q"], pins["s"]), ("B", "C", "B"))
        self.assertFalse(rules.crossover_leg(nodes, strands, "s", "sq"))
        nodes["q"]["label"] = "9"         # no longer a half: the short track to its leg C reads as a diagonal
        self.assertTrue(rules.crossover_leg(nodes, strands, "s", "sq"))

    def test_the_solved_railroad_draws_each_halfs_through_track_level(self):
        (_title, band, _opts), = xover_legs.bands()
        nrow, srow = band["R"]["nrow"], band["R"]["srow"]
        for n, leg in THROUGH.items():
            d = band["nodes"][n]
            for port in ("A", leg):
                sid = d["ins"].get(port) or d["outs"].get(port)
                self.assertEqual(srow[sid], nrow[n], (n, port))
        self.assertEqual(nrow["X5A"], nrow["X3A"])
        self.assertEqual(nrow["X5B"], nrow["X3B"])
        self.assertNotEqual(nrow["X5A"], nrow["X5B"])


class LayoutEditor(unittest.TestCase):
    def setUp(self):
        self.bands = xover_legs.bands()
        self.band = self.bands[0][1]

    def through_strands(self, n):
        d = self.band["nodes"][n]
        return {d["ins"].get(p) or d["outs"].get(p) for p in ("A", THROUGH[n])}

    def test_both_crossovers_are_single_crossovers_closed_on_their_through_tracks(self):
        P = le.panel(self.bands)
        self.assertEqual(sorted(t["type"] for t in P.turnouts), ["RH_XOVER", "RH_XOVER"], P.log)
        seg_of = {ident: sid for (_bi, sid), idents in P.strand_segments.items() for ident in idents}
        for t in P.turnouts:
            top, bot = t["nodes"]
            # JMRI's closed routes are A-B (the top half's track) and D-C (the bottom one's)
            self.assertEqual({seg_of[t["conn"][k]] for k in "AB"}, self.through_strands(top))
            self.assertEqual({seg_of[t["conn"][k]] for k in "DC"}, self.through_strands(bot))
        numbers = sorted(lab["text"] for lab in P.labels if lab["kind"] == "switch")
        self.assertEqual(numbers, ["3", "5"])          # the crossover's number, not a half's letter

    def test_it_loads_in_jmri_as_written(self):
        from test_le import JmriCrossovers
        JmriCrossovers().check(le.panel(self.bands), "\\")

    def test_a_half_drawn_as_a_plain_turnout_is_normal_on_its_through_leg(self):
        with mock.patch.object(le.Band, "room_toward", lambda self, n, port: 0.0):
            P = le.panel(self.bands)
        self.assertEqual(len(P.turnouts), 4, P.log)
        for n, leg in THROUGH.items():
            t = next(t for t in P.turnouts if t["nodes"] == [n])
            # continuing "2": normal on Layout Editor leg B, else C; the band leg written there is the through leg
            normal_le = "B" if t["continuing"] == "2" else "C"
            self.assertEqual(P.turnout_of[(0, n)][1][leg], normal_le, (n, t["continuing"]))

    def test_an_explicit_normal_still_wins_on_plain_turnouts(self):
        with mock.patch.object(le.Band, "room_toward", lambda self, n, port: 0.0):
            P = le.panel(self.bands, {"Xo": {"normal": {"X5B": "B"}}})
        t = next(t for t in P.turnouts if t["nodes"] == ["X5B"])
        self.assertEqual(P.turnout_of[(0, "X5B")][1]["B"], "B" if t["continuing"] == "2" else "C")

    def test_halves_labelled_alike_pair_too(self):
        P = le.panel(xover_legs.bands({"X5A": "5", "X5B": "5"}))
        self.assertEqual(sorted(t["type"] for t in P.turnouts), ["RH_XOVER", "RH_XOVER"], P.log)


class Cats(unittest.TestCase):
    def normals(self, P):
        return {p["node"][1]: next(p["ports"][far] for far, normal in p["routes"] if normal)
                for p in P.points.values()}

    def test_each_half_is_normal_on_its_through_leg(self):
        self.assertEqual(self.normals(cats.panel(xover_legs.bands())), THROUGH)

    def test_a_normal_binding_still_wins(self):
        P = cats.panel(xover_legs.bands(), bindings={"switches": {"5B": {"normal": "B"}}})
        self.assertEqual(self.normals(P)["X5B"], "B")

    def test_lettered_halves_keep_an_os_block_each(self):
        names = set(cats.panel(xover_legs.bands()).names.values())
        self.assertTrue({"OS 5A", "OS 5B", "OS 3A", "OS 3B"} <= names, names)


if __name__ == "__main__":
    unittest.main()
