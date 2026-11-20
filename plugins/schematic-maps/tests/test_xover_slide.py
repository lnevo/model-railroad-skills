"""A single crossover drawn short of room for its band's crossover run slides the track east of it, as a crossover
pair does (le.let_in_mast_room, le.crossover_shortfall), and one more than a row deep is two turnouts set to the run
leg to leg (le_band.Band.too_deep)."""
import math
import unittest
from unittest import mock

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import le
from schematic.core import SchematicError
from test_le import JmriCrossovers

RUN = 48.0
NAMES = {"Test": {"turnouts": {"P": "Switch 7", "Q": "Switch 7"}}}


def end(s, into):
    return dict(kind="end", sub="bumper", label="", ins={"E": s} if into else {}, outs={} if into else {"E": s})


def track(a, b, name):
    return dict(src=a, dst=b, name=name, main=False, hidden=False, link=False, edge="", cm=1.0)


def xover_band(q=3, r=4, deep=1, p=2):
    """Crossover 7: half P on the top row at column p, half Q `deep` rows below at column q, joined C to C; switch 5
    (R) east of Q on the bottom row at column r, its spur below. A solved band the plugin's own paths draws, so a
    slide moves the drawing. At q=3, r=4 switch 5 leaves Q too little track for the run."""
    nodes = {"WT": end("wt", False), "ET": end("et", True), "WB": end("wb", False), "EB": end("eb", True),
             "ES": end("s", True),
             "P": dict(kind="switch", label="7", hand=1, ins={"A": "wt"}, outs={"B": "et", "C": "d"}),
             "Q": dict(kind="switch", label="7", hand=1, ins={"B": "wb", "C": "d"}, outs={"A": "m"}),
             "R": dict(kind="switch", label="5", hand=-1, ins={"A": "m"}, outs={"B": "eb", "C": "s"})}
    strands = {"wt": track(("WT", "E"), ("P", "A"), "Top"), "et": track(("P", "B"), ("ET", "E"), "Top east"),
               "d": track(("P", "C"), ("Q", "C"), ""), "wb": track(("WB", "E"), ("Q", "B"), "Bottom"),
               "m": track(("Q", "A"), ("R", "A"), "Middle"), "eb": track(("R", "B"), ("EB", "E"), "Bottom east"),
               "s": track(("R", "C"), ("ES", "E"), "Spur")}
    x = {"WT": 0, "P": p, "ET": 14, "WB": 0, "Q": q, "R": r, "EB": 14, "ES": r + 3}
    nrow = {"WT": 0, "P": 0, "ET": 0, "WB": deep, "Q": deep, "R": deep, "EB": deep, "ES": deep + 1}
    srow = {"wt": 0, "et": 0, "wb": deep, "m": deep, "eb": deep}
    band = dict(nodes=nodes, strands=strands, x=x, need={k: (0, 0, 0) for k in srow},
                R=dict(srow=srow, nrow=nrow, diag={"d", "s"}))
    return [("Test level", band, {"le_labels": {"block_contents": False}})]


def boxed_band():
    """Crossover 7 with switch 9 (S) on the top row right east of half P, west of half Q's column: no slide east of
    Q gives P's track more room, so the run cannot be reached."""
    (t, band, o), = xover_band(q=4, r=5)
    nodes, strands = band["nodes"], band["strands"]
    nodes["P"]["outs"]["B"] = "pt"
    nodes["S"] = dict(kind="switch", label="9", hand=-1, ins={"A": "pt"}, outs={"B": "et", "C": "u"})
    nodes["EU"] = end("u", True)
    strands["pt"] = track(("P", "B"), ("S", "A"), "Top middle")
    strands["et"] = track(("S", "B"), ("ET", "E"), "Top east")
    strands["u"] = track(("S", "C"), ("EU", "E"), "Up")
    band["x"].update(S=3, EU=5)
    nrow = band["R"]["nrow"]
    for n in list(nrow):            # top track on row 1, switch 9's leg up to row 0
        nrow[n] += 1
    nrow["S"], nrow["EU"] = 1, 0
    band["R"]["srow"] = {k: v + 1 for k, v in band["R"]["srow"].items()}
    band["R"]["srow"]["pt"] = 1
    band["R"]["diag"].add("u")
    band["need"]["pt"] = (0, 0, 0)
    return [(t, band, o)]


def unslid(bands, **kw):
    """The panel as before 0.1.42's slide: no single crossover is slid."""
    with mock.patch.object(le, "single_crossovers", lambda *a: []):
        return le.panel(bands, NAMES, **kw)


def rounded(v):
    """v with its floats to 6 places: a run from an angle is the run asked to a float's last digit."""
    if isinstance(v, float):
        return round(v, 6)
    if isinstance(v, (list, tuple)):
        return type(v)(rounded(x) for x in v)
    if isinstance(v, dict):
        return {k: rounded(x) for k, x in v.items()}
    return v


def by_node(P):
    return {t["nodes"][0]: t for t in P.turnouts}


class Slide(unittest.TestCase):
    def test_a_squeezed_crossover_slides_the_track_east_of_it_to_its_run(self):
        was = unslid(xover_band(), crossover_run=RUN)
        self.assertTrue(any("switch 7: crossover drawn" in line and "no room for 48.0 px" in line
                            for line in was.log))
        P = le.panel(xover_band(), NAMES, crossover_run=RUN)
        x7 = by_node(P)["P"]
        self.assertEqual(x7["type"], "RH_XOVER")
        across = (x7["pts"]["B"][0] - x7["pts"]["A"][0]) / 2
        deep = x7["pts"]["C"][1] - x7["pts"]["B"][1]
        self.assertAlmostEqual(across, RUN, delta=le.PAIR_TOLERANCE)
        px, degrees = P.crossover_slides[("Test", "7")]
        self.assertGreater(px, 0)
        self.assertAlmostEqual(degrees, math.degrees(math.atan2(deep, RUN)), places=1)
        # switch 5, east of half Q, slides by just that; the track west of half P stays
        self.assertAlmostEqual(by_node(P)["R"]["at"][0] - by_node(was)["R"]["at"][0], px, delta=0.06)
        west = lambda Q: sorted(p["xy"] for p in Q.points.values() if p["xy"][0] < 100)   # noqa: E731  west ends
        self.assertTrue(west(P))
        self.assertEqual(west(P), west(was))
        east = lambda Q: sorted(p["xy"] for p in Q.points.values() if p["xy"][0] > 500)   # noqa: E731  band's edge
        self.assertTrue(east(P))
        self.assertEqual(east(P), east(was))        # the band keeps its width
        self.assertTrue(any(f"switch 7: crossover's east half and everything east of it slid +{px:.1f} px" in line
                            for line in P.log))
        self.assertFalse([line for line in P.log if "no room for" in line])

    def test_it_loads_in_jmri_as_written(self):
        JmriCrossovers().check(le.panel(xover_band(), NAMES, crossover_run=RUN), "\\")

    def test_the_preference_slides_as_the_argument(self):
        (t, b, o), = xover_band()
        angle = math.degrees(math.atan(le.ROW / RUN))
        by_pref = le.panel([(t, b, dict(o, le_crossover_angle={"Test": angle}))], NAMES)
        self.assertEqual(rounded(le.geometry(by_pref)),
                         rounded(le.geometry(le.panel(xover_band(), NAMES, crossover_run=RUN))))

    def test_a_crossover_at_its_run_is_left(self):
        P = le.panel(xover_band(r=5), NAMES, crossover_run=RUN)
        self.assertEqual(P.crossover_slides, {})
        self.assertEqual(le.geometry(P), le.geometry(unslid(xover_band(r=5), crossover_run=RUN)))

    def test_with_no_run_nothing_slides(self):
        with mock.patch.object(le, "let_in_mast_room", side_effect=AssertionError("no rounds without a run")):
            P = le.panel(xover_band(q=4, r=5), NAMES)
        self.assertEqual(P.crossover_slides, {})
        self.assertTrue(any("no room for" in line for line in P.log))        # as drawn: logged, as before
        self.assertEqual(le.single_crossovers(xover_band(), None, {}), [])
        self.assertEqual(le.single_crossovers(xover_band(), {"Other": RUN}, {}), [])

    def test_a_split_crossover_is_not_slid_again(self):
        self.assertEqual(le.single_crossovers(xover_band(), RUN, {"Test": {"7"}}), [])
        self.assertEqual([c[4] for c in le.single_crossovers(xover_band(), RUN, {})], ["7"])

    def test_one_that_cannot_reach_its_run_stops(self):
        with self.assertRaisesRegex(SchematicError, "do not settle; crossover 7 runs [0-9.]+ px short of its "
                                                    "crossover run"):
            le.panel(boxed_band(), crossover_run=RUN)
        P = le.panel(boxed_band())          # with no run it is drawn as before, as steep as it must be
        self.assertTrue(any("switch 7: crossover drawn" in line for line in P.log))


class TwoRowsDeep(unittest.TestCase):
    def test_two_turnouts_on_its_one_name_set_to_the_run_leg_to_leg(self):
        P = le.panel(xover_band(q=3, r=6, deep=2), NAMES, crossover_run=RUN)
        t = by_node(P)
        self.assertEqual((t["P"]["type"], t["Q"]["type"]), ("RH_TURNOUT", "RH_TURNOUT"))
        self.assertEqual({t["P"]["name"], t["Q"]["name"]}, {"Switch 7"})
        self.assertIn("Switch 7", P.split_names)
        (ax, ay), (bx, by) = t["P"]["pts"]["C"], t["Q"]["pts"]["C"]
        self.assertAlmostEqual(abs(bx - ax) / abs(by - ay), RUN / le.ROW, delta=le.PAIR_TOLERANCE / abs(by - ay))
        self.assertIn(("Test", "7"), P.crossover_slides)
        self.assertTrue(any("switch 7: drawn 2 rows deep" in line and "two turnouts" in line for line in P.log))

    def test_with_no_run_it_stays_one_crossover(self):
        P = le.panel(xover_band(q=3, r=6, deep=2), NAMES)
        self.assertEqual(by_node(P)["P"]["type"], "RH_XOVER")
        self.assertEqual(P.crossover_slides, {})


class Shortfall(unittest.TestCase):
    def test_halves_in_one_column_stop(self):
        P = le.panel(xover_band(), NAMES, crossover_run=RUN)
        (_t, b, _o), = xover_band()
        b["x"]["Q"] = b["x"]["P"]
        with self.assertRaisesRegex(SchematicError, "crossover 7: its halves stand in one column"):
            le.crossover_shortfall(P, [("Test level", b, {})], 0, "P", "Q", "d", 2 * RUN / le.ROW, "7")

    def test_a_crossover_drawn_as_another_turnout_stops(self):
        P = le.panel(xover_band(), NAMES, crossover_run=RUN)
        for t in P.turnouts:
            if t["type"] == "RH_XOVER":
                t["type"] = "DOUBLE_XOVER"
        with self.assertRaisesRegex(SchematicError, "drawn as one DOUBLE_XOVER, not a single crossover"):
            le.crossover_shortfall(P, xover_band(), 0, "P", "Q", "d", RUN / le.ROW, "7")


if __name__ == "__main__":
    unittest.main()
