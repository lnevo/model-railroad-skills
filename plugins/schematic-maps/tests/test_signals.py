"""Signal reader: masts on a turnout leg, an anchor and a ladder link; virtual and head masts; JMRI's east rule."""
import unittest
import xml.etree.ElementTree as ET

import helpers
from schematic import signal_reader


class Signals(unittest.TestCase):
    def setUp(self):
        res = helpers.signals()
        self.by = {r["mast"]: r for r in res["signals"]}
        self.res = res

    def test_every_mast_is_placed(self):
        self.assertEqual(set(self.by), {"M1A", "M2E", "M12C", "M13B", "V2"})
        self.assertEqual(self.res["unplaced"], [])

    def test_turnout_leg_mast_stands_on_the_run_toward_its_switch(self):
        m = self.by["M1A"]
        self.assertEqual((m["toward"], m["cm_from_toward"], m["dir"]), ("1", 0.0, "east"))

    def test_anchor_mast_sits_part_way_along_its_run_and_follows_its_slot(self):
        m = self.by["M2E"]
        self.assertEqual(m["dir"], "east")
        self.assertEqual(m["toward"], "2")                  # east-bound on Main West heads for switch 2
        self.assertEqual(m["run"], ["2", "1"])
        self.assertAlmostEqual(m["cm_from_toward"] / m["edge_cm"], 0.5, delta=0.02)

    def test_ladder_link_mast(self):
        m = self.by["M12C"]
        self.assertEqual((m["toward"], m["run"], m["dir"]), ("12", ["12", "13"], "west"))

    def test_heads_come_from_the_mast_system_name_and_virtual_masts_are_marked(self):
        self.assertEqual((self.by["M2E"]["heads"], self.by["M1A"]["heads"]), (2, 1))
        self.assertEqual(self.by["V2"]["kind"], "virtual")
        self.assertEqual(self.by["M1A"]["kind"], "field")

    def test_planned_masts_come_from_the_overrides(self):
        f = helpers.folder()
        from schematic import layers, panel_reader
        ov = dict(layers.load("example", f, False), signals_planned=["M1A"])
        res = signal_reader.read(str(f / "panel.xml"), helpers.graph(), ov, panel_reader.load_numbers(f / "numbers.csv"),
                                 panel_reader.load_lengths(f / "lengths.csv"))
        self.assertEqual({r["mast"]: r["kind"] for r in res["signals"]}["M1A"], "planned")

    def test_east_side_follows_jmri_for_horizontal_and_vertical_track(self):
        def segs(far1, far2):
            tos = {}
            xml = {"S1": dict(connect1name="P", connect2name="X1", type2="POSITIONABLE_POINT"),
                   "S2": dict(connect1name="P", connect2name="X2", type2="POSITIONABLE_POINT")}
            return {k: ET.Element("s", dict(ident=k, type1="POSITIONABLE_POINT", **v)) for k, v in xml.items()}, {"X1": far1, "X2": far2}
        pp = ET.Element("pp", dict(ident="P", connect1name="S1", connect2name="S2"))
        for far1, far2, expect in (((0, 0), (10, 0), "S2"), ((10, 0), (0, 0), "S1"),      # horizontal: larger x
                                   ((0, 0), (0, 10), "S2"), ((0, 10), (0, 0), "S1")):     # vertical: larger y
            s, pos = segs(far1, far2)
            self.assertEqual(signal_reader.east_side(pp, s, lambda n, t: pos[n]), expect)

    def test_two_stubs_off_one_switch_are_told_apart_by_their_legs(self):
        """Y-3 and Y-4 both run from switch 13 to a track end. Even with no track names, the leg a mast stands on
        picks the right one."""
        f = helpers.folder()
        from schematic import layers, panel_reader
        ov = layers.load("example", f, False)
        ov = dict(ov, edits=[e for e in ov["edits"] if e["op"] != "end"])         # no names on the ends
        res = signal_reader.read(str(f / "panel.xml"), helpers.graph(), ov, panel_reader.load_numbers(f / "numbers.csv"),
                                 panel_reader.load_lengths(f / "lengths.csv"))
        m = {r["mast"]: r for r in res["signals"]}["M13B"]
        self.assertEqual(self.by["M13B"]["names"], ["Y-3"])
        self.assertEqual(m["_edge"], self.by["M13B"]["_edge"])      # the same run as when the ends carry names
        self.assertAlmostEqual(m["edge_cm"], 218, delta=3)          # Y-3, not Y-4 (238)
        self.assertFalse([p for p in res["unplaced"] if "more than one" in p])


if __name__ == "__main__":
    unittest.main()


class MastPiece(unittest.TestCase):
    """A mast's run may be drawn as fold halves or cut between two bands; its spot is walked along the pieces."""

    def strands(self, pieces):
        return {k: dict(edge=e, cm=cm, src=(a, "A"), dst=(b, "A")) for k, e, cm, a, b in pieces}

    def test_fold_keeps_to_the_toward_half(self):
        from schematic.draw import mast_piece
        st = self.strands([("e5.0", "e5", 600, "S1", "turn:e5"), ("e5.1", "e5", 600, "S2", "turn:e5")])
        sg = dict(_edge="e5", _toward_node="S1", cm_from_toward=450, edge_cm=600)
        self.assertEqual(mast_piece(sg, st), ("e5.0", 300, 300, "S1"))     # at the turnback end of its own half
        self.assertEqual(mast_piece(dict(sg, cm_from_toward=100), st), ("e5.0", 100, 300, "S1"))

    def test_run_cut_between_levels(self):
        from schematic.draw import mast_piece
        here = self.strands([("e7x", "e7x", 200, "S4", "LINK:A0")])
        far = self.strands([("e7y", "e7y", 200, "LINK:A1", "S21")])
        sg = dict(_edge="e7", _toward_node="S4", cm_from_toward=50, edge_cm=400)
        self.assertEqual(mast_piece(sg, here), ("e7x", 50, 200, "S4"))
        self.assertIsNone(mast_piece(sg, far))                 # it stands on the other band's half
        self.assertEqual(mast_piece(dict(sg, cm_from_toward=300), far), ("e7y", 100, 200, "LINK:A1"))
