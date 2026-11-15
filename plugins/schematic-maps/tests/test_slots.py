"""Mast slots resolved as JMRI resolves them, masts placed on the generated panel, and the panel fitted to a size."""
import json
import math
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

import helpers
from schematic import le, slots
from schematic.core import SchematicError
from test_le import bands, panel

SEG = '<tracksegment ident="{i}" blockname="{b}" connect1name="{c1}" type1="{t1}" connect2name="{c2}" type2="{t2}"/>'


def point(ident, kind, x, y, c1, c2=None, **masts):
    at = f'ident="{ident}" type="{kind}" x="{x}" y="{y}" connect1name="{c1}"'
    if c2:
        at += f' connect2name="{c2}"'
    for k, v in masts.items():
        at += f' {k}="{v}"'
    return f"<positionablepoint {at}/>"


def seg(i, b, c1, c2, t1="POS_POINT", t2="POS_POINT"):
    return SEG.format(i=i, b=b, c1=c1, c2=c2, t1=t1, t2=t2)


def index(*parts):
    return slots.Index(ET.fromstring("<LayoutEditor>" + "".join(parts) + "</LayoutEditor>"))


def two_blocks(a, m, b, **masts):
    """A bumper at a, an anchor at m, a bumper at b: block W from a to m, block E from m to b."""
    return index(point("EB1", "END_BUMPER", *a, "T1"), point("A1", "ANCHOR", *m, "T1", "T2", **masts),
                 point("EB2", "END_BUMPER", *b, "T2"), seg("T1", "W", "EB1", "A1"), seg("T2", "E", "A1", "EB2"))


class Anchors(unittest.TestCase):
    def test_horizontal_east_faces_west_and_protects_east(self):
        ix = two_blocks((0, 0), (100, 0), (200, 0), eastboundsignalmast="M1", westboundsignalmast="M2")
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("W", ["E"]))
        self.assertEqual(ix.blocks("anchor", "A1", "west"), ("E", ["W"]))
        got = {m["mast"]: (m["kind"], m["slot"], m["facing"], m["protects"]) for m in ix.masts()}
        self.assertEqual(got, {"M1": ("anchor", "east", "W", ["E"]), "M2": ("anchor", "west", "E", ["W"])})

    def test_connect_order_does_not_matter(self):
        ix = index(point("EB1", "END_BUMPER", 0, 0, "T1"), point("A1", "ANCHOR", 100, 0, "T2", "T1"),
                   point("EB2", "END_BUMPER", 200, 0, "T2"), seg("T1", "W", "A1", "EB1"), seg("T2", "E", "EB2", "A1"))
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("W", ["E"]))

    def test_vertical_west_is_up(self):
        ix = two_blocks((0, 0), (0, 100), (0, 200))         # W at the top
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("W", ["E"]))       # east bound runs down the panel
        ix = two_blocks((0, 200), (0, 100), (0, 0))         # W at the bottom
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("E", ["W"]))

    def test_far_ends_decide_and_a_diagonal_counts_as_horizontal(self):
        ix = two_blocks((0, 0), (100, 100), (200, 200))
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("W", ["E"]))
        ix = two_blocks((0, 0), (300, 50), (40, 400))       # x gap 40, y gap 400: vertical, though it bends
        self.assertEqual(ix.blocks("anchor", "A1", "east"), ("W", ["E"]))


class Bumpers(unittest.TestCase):
    def test_slot_by_the_side_the_track_runs_from(self):
        # the skill's table: track runs right from a bumper at its left end -> west bound; left -> east bound
        for bumper, far, good in (((0, 0), (100, 0), "west"), ((100, 0), (0, 0), "east"),
                                  ((0, 0), (0, 100), "west"), ((0, 100), (0, 0), "east")):
            ix = index(point("EB1", "END_BUMPER", *bumper, "T1"), point("EB2", "END_BUMPER", *far, "T1"),
                       seg("T1", "X", "EB1", "EB2"))
            with self.subTest(bumper=bumper, far=far):
                self.assertEqual(ix.blocks("end bumper", "EB1", good), ("X", []))
                bad = "east" if good == "west" else "west"
                self.assertEqual(ix.blocks("end bumper", "EB1", bad), (None, ["X"]))   # no facing block: unusable


def turnout(ttype, blocks, legs, **extra):
    at = (f'ident="TO1" type="{ttype}" xcen="100" ycen="100" xa="80" ya="100" xb="120" yb="100" xc="120" yc="110" '
          f'xd="80" yd="110" ver="2" turnoutname="Switch 1" blockname="{blocks[0]}"')
    for leg, b in zip("bcd", blocks[1:]):
        at += f' block{leg}name="{b}"'
    for leg in legs:
        at += f' connect{leg.lower()}name="T{leg}"'
    kids = "".join(f"<signal{k}Mast>{v}</signal{k}Mast>" for k, v in extra.items())
    return f"<layoutturnout {at}>{kids}</layoutturnout>"


def leg_tracks(blocks, legs="ABCD"):
    out = []
    for leg, b in zip(legs, blocks):
        out.append(point(f"EB{leg}", "END_BUMPER", 0, 0, f"T{leg}"))
        out.append(seg(f"T{leg}", b, "TO1", f"EB{leg}", t1=f"TURNOUT_{leg}"))
    return out


class Turnouts(unittest.TestCase):
    def test_a_leg_mast_faces_its_track_and_protects_the_turnout(self):
        ix = index(turnout("RH_TURNOUT", ["OS 1"], "ABC", A="M1"), *leg_tracks(["X", "Y", "Z"], "ABC"))
        self.assertEqual(ix.blocks("turnout", "TO1", "A"), ("X", ["OS 1"]))
        self.assertEqual(ix.blocks("turnout", "TO1", "C"), ("Z", ["OS 1"]))
        self.assertEqual(ix.masts()[0]["turnout"], "Switch 1")

    def test_track_in_the_turnouts_own_block(self):
        ix = index(turnout("LH_TURNOUT", ["OS 1"], "ABC"), *leg_tracks(["OS 1", "Y", "Z"], "ABC"))
        self.assertEqual(ix.blocks("turnout", "TO1", "A"), ("OS 1", ["Y", "Z"]))
        ix = index(turnout("LH_TURNOUT", ["OS 1"], "ABC"), *leg_tracks(["X", "OS 1", "Z"], "ABC"))
        self.assertEqual(ix.blocks("turnout", "TO1", "B"), ("OS 1", ["X"]))

    def test_crossovers_pair_their_leg_blocks(self):
        ix = index(turnout("LH_XOVER", ["OS a", "OS a", "OS b", "OS b"], "ABCD"), *leg_tracks("WXYZ"))
        self.assertEqual([ix.blocks("turnout", "TO1", L) for L in "ABCD"],
                         [("W", ["OS a"]), ("X", ["OS a"]), ("Y", ["OS b"]), ("Z", ["OS b"])])
        ix = index(turnout("DOUBLE_XOVER", ["OS"], "ABCD"), *leg_tracks("WXYZ"))
        self.assertEqual({ix.blocks("turnout", "TO1", L)[1][0] for L in "ABCD"}, {"OS"})

    def test_a_mast_on_a_level_crossing_stops(self):
        with self.assertRaises(SchematicError):
            index('<levelxing ident="X1"><signalAMast>M</signalAMast></levelxing>')


class Icons(unittest.TestCase):
    def test_right_hand_side_before_the_boundary(self):
        x, y, deg = slots.icon_place((100, 100), (1, 0))      # east bound: left of the point, below the rail
        self.assertEqual(deg, 90)
        self.assertLess(x + 17, 100)
        self.assertGreater(y, 100)
        x, y, deg = slots.icon_place((100, 100), (-1, 0))     # west bound: right of it, above
        self.assertEqual(deg, 270)
        self.assertGreater(x, 100)
        self.assertLess(y + 12, 100)
        self.assertEqual(slots.icon_place((0, 0), (0, 1))[2], 180)
        self.assertEqual(slots.icon_place((0, 0), (math.sin(0.02), -math.cos(0.02)))[2], 0)   # just off: level


def boundaries(P, bi):
    """{(facing, protects): (kind, ident, slot)} for every slot of band bi on the drawn panel."""
    ix = slots.Index(le.to_xml(P, "probe"))
    mine = {t["ident"] for t in P.turnouts if t["band"] == bi} | {k for k, p in P.points.items() if p["band"] == bi}
    out = {}
    for c in ix.candidates():
        if c[1] in mine:
            f, pr = ix.blocks(*c)
            if f:
                out.setdefault((f, tuple(pr)), []).append(c)
    return out


class Masts(unittest.TestCase):
    def setUp(self):
        self.lower = next(i for i, (t, _, _) in enumerate(bands()) if t.startswith("Lower"))
        self.key = le.band_key(bands()[self.lower][0])
        base = {self.key: {"blocks": {"e1": ["Main West 1", "Main West 2"]}}}
        self.base = base
        self.found = boundaries(panel(base), self.lower)

    def pick(self, kind):
        return next(((f, list(pr)), cs[0]) for (f, pr), cs in sorted(self.found.items())
                    if len(cs) == 1 and cs[0][0] == kind and (kind == "end bumper") == (not pr))

    def test_masts_go_where_jmri_resolves_their_blocks(self):
        want = []
        for i, kind in enumerate(("anchor", "turnout", "end bumper")):
            (f, pr), _slot = self.pick(kind)
            want.append(dict(mast=f"Mast {i}", facing=f, protects=pr, kind=kind, hidden=i == 2))
        names = {self.key: {**self.base[self.key], "masts": want}}
        P = le.panel(bands(), names)
        self.assertEqual(P.unplaced, [])
        el = le.to_xml(P, "Generated")
        got = {m["mast"]: m for m in slots.Index(el).masts()}
        for w in want:
            self.assertEqual((got[w["mast"]]["kind"], got[w["mast"]]["facing"], got[w["mast"]]["protects"]),
                             (w["kind"], w["facing"], w["protects"]))
        icons = {i.get("signalmast"): i for i in el.findall("signalmasticon")}
        self.assertEqual(set(icons), {w["mast"] for w in want})
        self.assertEqual(icons["Mast 2"].get("hidden"), "yes")
        self.assertEqual(icons["Mast 0"].get("class"), "jmri.jmrit.display.configurexml.SignalMastIconXml")
        ix = slots.Index(el)
        for m in P.masts:
            p, d = ix.travel(m["kind"], m["ident"], m["slot"])
            x, y, bw, bh = m["box"]
            v = (x + bw / 2 - p[0], y + bh / 2 - p[1])
            self.assertGreater(v[0] * -d[1] + v[1] * d[0], 0, m["mast"])          # right of the train
            self.assertLess(v[0] * d[0] + v[1] * d[1], 0, m["mast"])              # before the boundary
        box = le.extent(P)
        self.assertLessEqual(box[2], P.size[0])

    def test_a_mast_with_no_matching_slot_is_listed_not_placed(self):
        (f, _pr), _slot = self.pick("turnout")
        names = {self.key: {**self.base[self.key], "masts": [
            dict(mast="Nowhere", facing=f, protects=["No such block"]),
            dict(mast="Wrong kind", facing=f, protects=list(_pr), kind="anchor")]}}
        P = le.panel(bands(), names)
        self.assertEqual([m for _t, m, _w in P.unplaced], ["Nowhere", "Wrong kind"])
        self.assertIn("only turnout slots", P.unplaced[1][2])
        self.assertFalse(P.masts)
        self.assertIn("2 not placed", le.summary(P))

    def test_a_buffer_stop_mast_on_a_joined_track_stands_at_the_join(self):
        names = {self.key: {**self.base[self.key], "joins": "other"}}
        for (bi, n), (bj, m) in le.partners(bands()).items():     # the far side of each join: a block of its own
            if bi == self.lower:
                title, band, _ = bands()[bj]
                d = band["nodes"][m]
                sid = next(iter(list(d["ins"].values()) + list(d["outs"].values())))
                names.setdefault(le.band_key(title), {"blocks": {}})["blocks"][sid] = [f"Beyond {n}"]
        P = le.panel(bands(), names)
        (bi, anchor), block = next((k, v) for k, v in sorted(P.join_ends.items()) if k[0] == self.lower)
        names[self.key]["masts"] = [dict(mast="Stop", facing=block, protects=[], kind="end bumper")]
        P = le.panel(bands(), names)
        self.assertEqual(P.unplaced, [])
        self.assertEqual([m for _t, m, _w in P.moved], ["Stop"])
        (m,) = P.masts
        self.assertEqual((m["kind"], m["ident"]), ("anchor", anchor))
        el = le.to_xml(P, "Generated")
        hidden = {s.get("blockname") for s in el.findall("tracksegment") if s.get("hidden") == "yes"}
        got = slots.Index(el).masts()[0]
        self.assertEqual(got["facing"], block)
        self.assertEqual(len(got["protects"]), 1)
        self.assertIn(got["protects"][0], hidden)            # the join carries the other band's block
        self.assertNotEqual(got["protects"][0], block)
        # the other band asking for the other block instead: the join keeps this band's block, no boundary there,
        # so the mast has nowhere to go
        del names[self.key]["joins"]
        for key in names:
            if key != self.key:
                names[key]["joins"] = "other"
        self.assertEqual([m for _t, m, _w in le.panel(bands(), names).unplaced], ["Stop"])

    def test_bad_joins_value_stops(self):
        with self.assertRaises(SchematicError):
            le.panel(bands(), {self.key: {"joins": "mine"}})

    def test_bad_mast_entries_stop(self):
        for bad in ([{"facing": "X"}], [{"mast": "M"}], [{"mast": "M", "facing": "X", "kind": "slip"}],
                    [{"mast": "M", "facing": "X"}, {"mast": "M", "facing": "Y"}],
                    [{"mast": "M", "facing": "X", "protects": "Y"}]):
            with self.subTest(bad=bad), self.assertRaises(SchematicError):
                le.panel(bands(), {self.key: {"masts": bad}})


class Fit(unittest.TestCase):
    def test_fit_shrinks_the_grid_not_the_fonts(self):
        full = panel()
        W, H = int(full.size[0] * 0.8), int(full.size[1] * 0.95)
        P = le.panel(bands(), None, fit=(W, H))
        self.assertLessEqual(P.size[0], W)
        self.assertLessEqual(P.size[1], H)
        self.assertGreater(P.size[0], W - 0.02 * W)                  # the largest that fits
        kx, ky = P.scale
        self.assertLess(kx, 1.0)
        self.assertGreaterEqual(ky, kx)
        self.assertEqual(sorted(lb["size"] for lb in P.labels), sorted(lb["size"] for lb in full.labels))
        el = le.to_xml(P, "Fitted")
        self.assertEqual((int(el.get("windowwidth")), int(el.get("windowheight"))),
                         (P.size[0] + le.CHROME[0], P.size[1] + le.CHROME[1]))

    def test_a_panel_that_already_fits_is_unchanged(self):
        full = panel()
        P = le.panel(bands(), None, fit=(full.size[0] + 10, full.size[1] + 10))
        self.assertEqual(P.scale, (1.0, 1.0))
        self.assertEqual(P.size, full.size)

    def test_too_small_stops(self):
        with self.assertRaises(SchematicError):
            le.panel(bands(), None, fit=(100, 100))

    def test_fit_size_option(self):
        self.assertEqual(le.fit_size("1880x1080"), (1880, 1080))
        for bad in ("1880", "ax1", "0x10"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                le.fit_size(bad)

    def test_cli_fit(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(helpers.graph()))
            out = Path(tmp) / "le.xml"
            run = subprocess.run([sys.executable, "-m", "schematic", "le", str(out), "--data", str(f),
                                  f"{graph}:example", "--fit", "900x500"],
                                 capture_output=True, text=True, cwd=helpers.PLUGIN, timeout=120)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("to fit", run.stdout)
            root = ET.parse(out).getroot()
            self.assertLessEqual(int(root.get("panelwidth")), 900)
            self.assertLessEqual(int(root.get("panelheight")), 500)


if __name__ == "__main__":
    unittest.main()
