"""Single crossovers whose halves join by leg B or C (core.crossover_halves): the pairing by switch number, what it
leaves as two switches (and logs), the solver's level leg (R8), and both panels (tests/xover_legs.py is the
railroad)."""
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts the plugin on the path)
import xover_legs
from schematic import cats, core, le, rules
from schematic.core import SchematicError
from test_straight_level import band as small_band

THROUGH = {"X3A": "B", "X3B": "B", "X5A": "B", "X5B": "C"}     # each half's normal leg in xover_legs
WIRE = ("switch 5B is laid straight on the crossover's diagonal: wire its machine reversed so Closed lines the "
        "through route")


def two_halves(labels, legs, cm=20.0, extra=()):
    """Switches p and q (labelled `labels`) joined by track x from p's leg legs[0] to q's leg legs[1], and by each
    (sid, p's leg, q's leg) in `extra`; every other leg runs to an end of its own."""
    joins = [("x", legs[0], legs[1])] + list(extra)
    tracks = [(sid, ("p", a), ("q", b), cm, False) for sid, a, b in joins]
    used = {"p": {a for _s, a, _b in joins}, "q": {b for _s, _a, b in joins}}
    ends = []
    for n in ("p", "q"):
        for leg in "ABC":
            if leg not in used[n]:
                ends.append(f"{n}{leg}")
                tracks.append((f"t{n}{leg}", (n, leg), (f"{n}{leg}", "E"), 150.0, False))
    nodes, strands = small_band(["p", "q"], ends, tracks)
    nodes["p"]["label"], nodes["q"]["label"] = labels
    return nodes, strands


def paired(labels, legs, extra=()):
    log = []
    return core.crossover_halves(*two_halves(labels, legs, extra=extra), log), log


class Pairing(unittest.TestCase):
    def test_switch_numbers(self):
        self.assertEqual(core.switch_number("23A"), "23")
        self.assertEqual(core.switch_number("23B*"), "23")
        self.assertEqual(core.switch_number("23"), "23")
        self.assertEqual(core.switch_number("CLUB"), "CLUB")       # a letter after no digit is part of the name
        self.assertEqual(core.crossover_name("23B"), "23")
        self.assertEqual(core.crossover_name("23"), "23")

    def test_which_joins_pair(self):
        both = lambda a, b: {"p": (a, "q", "x"), "q": (b, "p", "x")}     # noqa: E731
        want = {("3A", "3B"): {("C", "C"): both("C", "C"), ("C", "B"): both("C", "B"), ("B", "C"): both("B", "C"),
                               ("B", "B"): {}},
                ("3", "3"): {("C", "C"): both("C", "C"), ("C", "B"): {}, ("B", "C"): {}, ("B", "B"): {}}}
        for labels, by_legs in want.items():
            for legs, expect in by_legs.items():
                with self.subTest(labels=labels, legs=legs):
                    got, log = paired(labels, legs)
                    self.assertEqual(got, expect)
                    self.assertEqual(log, [])
        got, _ = paired(("3B", "3A"), ("B", "C"))
        self.assertEqual({n: core.through_leg(v[0]) for n, v in got.items()}, {"p": "C", "q": "B"})

    def test_one_number_joined_at_the_points_is_two_switches(self):
        for labels in (("3A", "3B"), ("3", "3"), ("3A", "3A"), ("3", "3B")):
            for legs in (("A", "C"), ("B", "A"), ("A", "A")):
                with self.subTest(labels=labels, legs=legs):
                    self.assertEqual(paired(labels, legs), ({}, []))

    def test_alike_labels_pair_c_to_c_but_not_lettered_alike(self):
        self.assertEqual(paired(("3", "3"), ("C", "C"))[0], {"p": ("C", "q", "x"), "q": ("C", "p", "x")})
        for labels in (("3A", "3A"), ("3B", "3B*")):        # lettered alike: ambiguous, whichever legs
            for legs in (("C", "C"), ("B", "C"), ("C", "B")):
                with self.subTest(labels=labels, legs=legs):
                    got, log = paired(labels, legs)
                    self.assertEqual(got, {})
                    self.assertEqual(len(log), 1, log)
                    self.assertIn(f"both lettered {labels[0][-1]}", log[0])
        self.assertEqual(paired(("3A", "3A"), ("B", "B")), ({}, []))      # back to back: two switches, as before

    def test_lettered_alike_among_more_letters_of_the_number(self):
        log = []
        self.assertEqual(core.crossover_halves(*self.chain(("3A", "3A", "3B")), log), {})
        self.assertTrue(log and all("3 switches carry letters of number 3" in m for m in log), log)

    def test_ambiguous_lettering_is_logged_not_paired(self):
        for labels, why in ((("3A", "3A"), "both lettered A"), (("3B*", "3B"), "both lettered B"),
                            (("3", "3B"), "not lettered one A and one B"),
                            (("3A", "3*"), "not lettered one A and one B")):
            with self.subTest(labels=labels):
                got, log = paired(labels, ("C", "B"))
                self.assertEqual(got, {})
                self.assertEqual(len(log), 1, log)
                self.assertIn(why, log[0])

    def test_a_run_around_is_two_switches(self):
        # 3A and 3B joined B to B (the main) and C to C (the siding): a passing track, not a crossover
        got, log = paired(("3A", "3B"), ("B", "B"), extra=[("y", "C", "C")])
        self.assertEqual(got, {})
        self.assertIn("joined by 2 tracks (a run-around or passing track)", log[0])

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

    def test_three_lettered_halves_of_one_number_are_logged_not_paired(self):
        log = []
        self.assertEqual(core.crossover_halves(*self.chain(("3A", "3B", "3A")), log), {})
        self.assertTrue(log and all("3 switches carry letters of number 3" in m for m in log), log)

    def test_three_alike_keep_the_pair_joined_c_to_c(self):
        # p and q (C to C) are the crossover and r a switch, as before
        self.assertEqual(core.crossover_halves(*self.chain(("3", "3", "3"))),
                         {"p": ("C", "q", "pq"), "q": ("C", "p", "pq")})

    def test_the_solver_never_stops_on_lettering(self):
        bands = xover_legs.bands({"X5B": "5A"})         # two 5A's joined B to C: two switches, drawn
        self.assertEqual([(u, v) for _s, u, v in le.crossover_pairs(bands[0][1])], [("X3A", "X3B")])


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
        self.assertIn("Xo level: " + WIRE, P.log)
        self.assertEqual(sum("wire its machine reversed" in m for m in P.log), 1, P.log)     # 5B only

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

    def test_halves_not_on_two_level_tracks_share_their_one_turnout_name(self):
        # the halves drawn as two plain turnouts (not on two level tracks) on the one turnout name the names give
        real = le.Band.direction

        def sloped(self, n, p):
            d = real(self, n, p)
            return (d[0], d[1] + 0.5) if n in ("X5A", "X5B") else d

        with mock.patch.object(le.Band, "direction", sloped):
            P = le.panel(self.bands, {"Xo": {"turnouts": {"X5A": "NT5", "X5B": "NT5"}}})
        self.assertEqual(sorted(t["nodes"] for t in P.turnouts if t["name"] == "NT5"), [["X5A"], ["X5B"]], P.log)
        self.assertIn("NT5", P.split_names)
        # numbered once, by the crossover's number, not a half's letter
        numbers = [lb["text"] for lb in P.labels if lb["kind"] == "switch"]
        self.assertEqual([n for n in numbers if n.startswith("5")], ["5"], numbers)

    def test_a_normal_for_a_half_stops_however_it_is_drawn(self):
        # one answer for one names file: as one crossover, or as two turnouts for no room
        why = ("normal names X5B \\(switch 5B\\), half of a single crossover, whose closed route is both through "
               "tracks.*remove that normal entry")
        with mock.patch.object(le.Band, "room_toward", lambda self, n, port: 0.0), \
                self.assertRaisesRegex(SchematicError, why):
            le.panel(self.bands, {"Xo": {"normal": {"X5B": "B"}}})
        with self.assertRaisesRegex(SchematicError, why):
            le.panel(self.bands, {"Xo": {"normal": {"X5B": "B"}}})

    def test_a_normal_or_leg_b_for_a_half_drawn_as_a_crossover_stops(self):
        with self.assertRaisesRegex(SchematicError, "normal names X5B \\(switch 5B\\), half of a single crossover, "
                                                    "whose closed route is both through tracks"):
            le.panel(self.bands, {"Xo": {"normal": {"X5B": "C"}}})
        with self.assertRaisesRegex(SchematicError, "leg_b names X5B, half of a single crossover.*remove that leg_b"):
            le.panel(self.bands, {"Xo": {"leg_b": {"X5B": "C"}}})

    def test_halves_labelled_alike_pair_c_to_c_only(self):
        P = le.panel(xover_legs.bands({"X3A": "3", "X3B": "3"}))
        self.assertEqual(sorted(t["type"] for t in P.turnouts), ["RH_XOVER", "RH_XOVER"], P.log)
        P = le.panel(xover_legs.bands({"X5A": "5", "X5B": "5"}))        # alike, B to C: two switches
        self.assertEqual(sorted(t["nodes"] for t in P.turnouts), [["X3A", "X3B"], ["X5A"], ["X5B"]], P.log)

    def test_two_crossovers_of_one_number(self):
        bands = xover_legs.bands({"X3A": "5", "X3B": "5"})      # 5/5 and 5A/5B
        P = le.panel(bands)
        self.assertIn("Xo level: crossovers 5/5 and 5A/5B both take number 5", P.log)
        with self.assertRaisesRegex(SchematicError, "split_crossovers for Xo: switch 5 names crossover 5/5 and "
                                                    "crossover 5A/5B; relabel one"):
            le.panel(bands, split_crossovers={"Xo": ["5"]})
        with self.assertRaisesRegex(SchematicError, "tight_crossovers for Xo: switch 5 names crossover 5/5"):
            le.one_crossover(bands[0][1], "Xo", "tight_crossovers", "5")    # as check_tight and check_pairs call it


class Cats(unittest.TestCase):
    def normals(self, P):
        return {p["node"][1]: next(p["ports"][far] for far, normal in p["routes"] if normal)
                for p in P.points.values()}

    def test_each_half_is_normal_on_its_through_leg(self):
        P = cats.panel(xover_legs.bands())
        self.assertEqual(self.normals(P), THROUGH)
        self.assertIn("Xo level: " + WIRE, P.log)

    def test_a_compact_panel_too(self):
        # at one cell per unit every labelled switch is placed with its number first; 3A, 3B and 5A sort before 5B
        self.assertEqual(self.normals(cats.panel(xover_legs.bands(), scale=1)), THROUGH)

    def test_a_normal_binding_still_wins(self):
        P = cats.panel(xover_legs.bands(), bindings={"switches": {"5B": {"normal": "B"}}})
        self.assertEqual(self.normals(P)["X5B"], "B")

    def test_lettered_halves_keep_an_os_block_each(self):
        names = set(cats.panel(xover_legs.bands()).names.values())
        self.assertTrue({"OS 5A", "OS 5B", "OS 3A", "OS 3B"} <= names, names)


if __name__ == "__main__":
    unittest.main()
