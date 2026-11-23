"""Plan reader on parts it cannot model: a crossing, a turntable and a slip cut the track; a single crossover is read."""
import json
import math
import tempfile
import unittest
from pathlib import Path

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import plan_reader
from test_cli import run


def seg(ident, a, ta, b, tb):
    return (f'<tracksegment ident="{ident}" connect1name="{a}" type1="{ta}" connect2name="{b}" type2="{tb}" '
            'blockname="B_1_Mainline" dashed="no" mainline="yes" hidden="no"/>')


def bumper(ident, x, y):
    return f'<positionablepoint ident="{ident}" type="END_BUMPER" x="{x}" y="{y}" connect1name="s"/>'


def panel(*parts):
    return '<layout-config><LayoutEditor name="t">' + "".join(parts) + "</LayoutEditor></layout-config>"


SWITCH = ('<layoutturnout ident="TO1" type="RH_TURNOUT" blockname="B_1_Mainline" xcen="100" ycen="100" xb="120" yb="100" '
          'xc="120" yc="110"/>')
XING = '<levelxing ident="X1" xcen="160" ycen="100" xa="150" ya="100" xb="160" yb="90"/>'
SLIP = '<layoutSlip ident="SL1" slipType="DOUBLE_SLIP" xcen="160" ycen="130" xa="150" ya="130" xb="160" yb="120"/>'
TABLE = ('<layoutturntable ident="TUR1" radius="20" xcen="160" ycen="110">'
         '<raytrack angle="90" connectname="TUR1-S-0" index="0"/></layoutturntable>')


class Cuts(unittest.TestCase):
    def read(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(text)
            return plan_reader.read(str(f)), f

    def test_parts_that_cannot_be_modelled_cut_the_track(self):
        text = panel(SWITCH, XING, SLIP, TABLE, bumper("EB1", 40, 100),
                     seg("s1", "TO1", "TURNOUT_A", "EB1", "POS_POINT"),
                     seg("s2", "TO1", "TURNOUT_B", "X1", "LEVEL_XING_A"),
                     seg("s3", "TO1", "TURNOUT_C", "TUR1", "TURNTABLE_RAY_0"))
        g, _ = self.read(text)
        self.assertEqual([c["part"] for c in g["cuts"]], ["TUR1", "X1"])
        reasons = {c["part"]: c["reason"] for c in g["cuts"]}
        self.assertIn("level crossing", reasons["X1"])
        self.assertIn("turntable", reasons["TUR1"])
        self.assertEqual(sum(d["kind"] == "end" for d in g["nodes"].values()), 3)
        self.assertEqual(sum(d.get("sub") == "cut" for d in g["nodes"].values()), 2)
        self.assertTrue(any("track cut at X1" in n for n in g["notes"]))

    def test_a_slip_is_cut_too_and_the_cli_lists_it_on_stderr(self):
        text = panel(SWITCH, SLIP, bumper("EB1", 40, 100), bumper("EB2", 200, 100),
                     seg("s1", "TO1", "TURNOUT_A", "EB1", "POS_POINT"),
                     seg("s2", "TO1", "TURNOUT_B", "SL1", "SLIP_A"),
                     seg("s3", "TO1", "TURNOUT_C", "EB2", "POS_POINT"))
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(text)
            r = run("plan", f, Path(tmp) / "g.json")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            self.assertIn("track cut at SL1: double slip not read", r.stderr)
            self.assertIn("track cut at SL1", r.stdout)
            self.assertEqual(json.loads((Path(tmp) / "g.json").read_text())["cuts"][0]["part"], "SL1")

    def test_a_track_point_naming_a_missing_piece_ends_the_track(self):
        anchor = ('<positionablepoint ident="A1" type="ANCHOR" x="70" y="100" connect1name="s1" '
                  'connect2name="NOPE"/>')
        text = panel(SWITCH, anchor, bumper("EB2", 200, 100), bumper("EB3", 200, 110),
                     seg("s1", "TO1", "TURNOUT_A", "A1", "POS_POINT"),
                     seg("s2", "TO1", "TURNOUT_B", "EB2", "POS_POINT"), seg("s3", "TO1", "TURNOUT_C", "EB3", "POS_POINT"))
        g, _ = self.read(text)
        self.assertEqual(sum(d["kind"] == "end" for d in g["nodes"].values()), 3)
        self.assertTrue(any("does not hold" in n for n in g["notes"]), g["notes"])

    def xover(self, ty):
        """A single crossover of hand `ty` on its default shape, with a bumper at each leg."""
        shape = {"RH_XOVER": dict(xa=70, ya=90, xb=110, yb=90, xc=130, yc=110, xd=90, yd=110),
                 "LH_XOVER": dict(xa=90, ya=90, xb=130, yb=90, xc=110, yc=110, xd=70, yd=110)}[ty]
        el = (f'<layoutturnout ident="XO1" type="{ty}" blockname="B_1_Mainline" xcen="100" ycen="100" '
              + " ".join(f'{k}="{v}"' for k, v in shape.items()) + "/>")
        legs = {k: (shape["x" + k.lower()], shape["y" + k.lower()]) for k in "ABCD"}
        text = panel(el, *(bumper(f"EB{k}", *legs[k]) for k in "ABCD"),
                     *(seg(f"s{k}", "XO1", f"TURNOUT_{k}", f"EB{k}", "POS_POINT") for k in "ABCD"))
        return self.read(text)[0], legs

    def test_a_single_crossover_is_two_turnouts_and_a_link(self):
        g, _ = self.xover("RH_XOVER")
        sw = [n for n, d in g["nodes"].items() if d["kind"] == "switch"]
        self.assertEqual(len(sw), 2)
        self.assertEqual(len(g["edges"]), 5)
        link = next(e for e in g["edges"] if e["u"] in sw and e["v"] in sw)
        self.assertEqual((link["up"], link["vp"]), ("C", "C"))
        self.assertEqual(g.get("cuts"), [])

    def test_the_crossing_route_is_a_to_c_on_a_right_hand_and_b_to_d_on_a_left_hand(self):
        for ty, route in (("RH_XOVER", "AC"), ("LH_XOVER", "BD")):
            g, legs = self.xover(ty)
            ends = {}
            for e in g["edges"]:
                for n, p, other in ((e["u"], e["up"], e["v"]), (e["v"], e["vp"], e["u"])):
                    if g["nodes"][other]["kind"] == "end":
                        leg = next(k for k, xy in legs.items() if math.dist(xy, g["nodes"][other]["xy"]) < 1e-6)
                        ends[leg] = (n, p)
            points = {k: v for k, v in ends.items() if v[1] == "A"}      # the legs a turnout's points face
            self.assertEqual(sorted(points), sorted(route), ty)
            self.assertNotEqual(points[route[0]][0], points[route[1]][0], ty)

    def test_a_far_end_the_export_does_not_place_keeps_a_sane_length(self):
        text = panel(SWITCH, bumper("EB1", 40, 100), bumper("EB3", 200, 110),
                     seg("s1", "TO1", "TURNOUT_A", "EB1", "POS_POINT"), seg("s3", "TO1", "TURNOUT_C", "EB3", "POS_POINT"),
                     seg("s2", "TO1", "TURNOUT_B", "SL9", "SLIP_A"))
        g, _ = self.read(text)
        cut = next(d for d in g["nodes"].values() if d.get("sub") == "cut")
        self.assertEqual(cut["xy"], [120.0, 100.0])
        e = next(e for e in g["edges"] if g["nodes"][e["v"]].get("sub") == "cut" or g["nodes"][e["u"]].get("sub") == "cut")
        self.assertTrue(0 < e["cm"] < 5, e)
        self.assertTrue(any("position unknown" in n for n in g["notes"]), g["notes"])

    def test_a_part_with_missing_numbers_is_cut_without_a_traceback(self):
        bad = '<levelxing ident="X1" xa="x"/><layoutturntable ident="TUR1"><raytrack index="0"/></layoutturntable>'
        text = panel(SWITCH, bad, bumper("EB1", 40, 100),
                     seg("s1", "TO1", "TURNOUT_A", "EB1", "POS_POINT"),
                     seg("s2", "TO1", "TURNOUT_B", "X1", "LEVEL_XING_A"),
                     seg("s3", "TO1", "TURNOUT_C", "TUR1", "TURNTABLE_RAY_0"))
        g, _ = self.read(text)
        self.assertEqual([c["part"] for c in g["cuts"]], ["TUR1", "X1"])

    def test_a_single_crossover_is_not_matched_to_parts(self):
        k = plan_reader.PX_PER_CM
        spots = [(100, 100), (400, 150), (200, 400)]
        tos = "".join(f'<layoutturnout ident="TO{i}" type="RH_TURNOUT" blockname="B_1_Mainline" xcen="{x}" ycen="{y}" '
                      f'xb="{x + 20}" yb="{y}" xc="{x + 20}" yc="{y + 10}"/>' for i, (x, y) in enumerate(spots, 1))
        xo = ('<layoutturnout ident="XO1" type="RH_XOVER" blockname="B_1_Mainline" xcen="230" ycen="220" xa="200" ya="210" '
              'xb="240" yb="210" xc="260" yc="230" xd="220" yd="230"/>')
        text = panel(tos, xo, *(bumper(f"EB{i}", 0, i) for i in range(1, 9)),
                     seg("a", "TO1", "TURNOUT_B", "TO2", "TURNOUT_A"), seg("b", "TO2", "TURNOUT_B", "TO3", "TURNOUT_A"),
                     seg("c", "TO3", "TURNOUT_B", "XO1", "TURNOUT_A"), seg("d", "TO1", "TURNOUT_A", "EB1", "POS_POINT"),
                     seg("e", "TO1", "TURNOUT_C", "EB2", "POS_POINT"), seg("f", "TO2", "TURNOUT_C", "EB3", "POS_POINT"),
                     seg("g", "TO3", "TURNOUT_C", "EB4", "POS_POINT"), seg("h", "XO1", "TURNOUT_B", "EB5", "POS_POINT"),
                     seg("i", "XO1", "TURNOUT_C", "EB6", "POS_POINT"), seg("j", "XO1", "TURNOUT_D", "EB7", "POS_POINT"))
        parts = [dict(eps=[dict(x=x / k, y=y / k, z=0)] * 3) for x, y in spots]
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "plan.xml"
            f.write_text(text)
            g = plan_reader.read(str(f), None, parts)
        self.assertTrue(any("matched 3 of 3 junctions" in n for n in g["notes"]), g["notes"])
        self.assertFalse(any(d.get("z") is not None for d in g["nodes"].values() if "xover" in d))


class Drawn(unittest.TestCase):
    def test_a_cut_end_is_drawn_like_an_open_end_not_a_bumper(self):
        from schematic import sheet
        s = sheet.build([(helpers.graph(), "example")], helpers.data_with_signals(), preferences=False)
        texts = []
        for sub in ("bumper", "cut"):
            for _, band, _ in s.bands:
                for d in band["nodes"].values():
                    if d["kind"] == "end" and d.get("sub") == "bumper" or d.get("sub") == "cut":
                        d["sub"] = sub
            s._svg = None           # draw again with the changed ends
            texts.append(s.svg())
        self.assertNotEqual(texts[0], texts[1])


if __name__ == "__main__":
    unittest.main()
