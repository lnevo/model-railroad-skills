"""Plan reader on parts it cannot model: a crossing, a turntable and a slip cut the track; a single crossover is read."""
import json
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

    def test_a_single_crossover_is_two_turnouts_and_a_link(self):
        xover = ('<layoutturnout ident="XO1" type="RH_XOVER" blockname="B_1_Mainline" xcen="100" ycen="100" '
                 'xa="80" ya="90" xb="120" yb="95" xc="120" yc="110" xd="80" yd="105"/>')
        text = panel(xover, *(bumper(f"EB{i}", 20 * i, 50) for i in range(1, 5)),
                     seg("s1", "XO1", "TURNOUT_A", "EB1", "POS_POINT"), seg("s2", "XO1", "TURNOUT_B", "EB2", "POS_POINT"),
                     seg("s3", "XO1", "TURNOUT_C", "EB3", "POS_POINT"), seg("s4", "XO1", "TURNOUT_D", "EB4", "POS_POINT"))
        g, _ = self.read(text)
        sw = [n for n, d in g["nodes"].items() if d["kind"] == "switch"]
        self.assertEqual(len(sw), 2)
        self.assertEqual(len(g["edges"]), 5)
        link = next(e for e in g["edges"] if e["u"] in sw and e["v"] in sw)
        self.assertEqual((link["up"], link["vp"]), ("C", "C"))
        self.assertEqual(g.get("cuts"), [])


if __name__ == "__main__":
    unittest.main()
