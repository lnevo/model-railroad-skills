"""The CATS panel seeded from the example's solved bands: track on whole cells, switch points, blocks, joins, XML."""
import copy
import math
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from unittest import mock

import helpers
from schematic import cats, cats_masts
from schematic.layout import paths


def panel():
    if "cats" not in helpers._cache:
        helpers._cache["cats"] = cats.panel(helpers.build().bands)
    return helpers._cache["cats"]


def links(P):
    """{(cell, track): set of (cell, track)} joined across a shared cell edge or a logical join."""
    out = defaultdict(set)
    for cell, tracks in P.cells.items():
        for t in tracks:
            for edge in cats.ENDS[t]:
                far, fedge = P.shared.get((cell, edge)) or cats.neighbour(cell, edge)
                for t2 in P.cells.get(far, {}):
                    if fedge in cats.ENDS[t2]:
                        out[(cell, t)].add((far, t2))
    return out


def component(graph, start):
    seen, todo = {start}, [start]
    while todo:
        for nxt in graph[todo.pop()]:
            if nxt not in seen:
                seen.add(nxt)
                todo.append(nxt)
    return seen


class Cats(unittest.TestCase):
    def test_every_strand_is_drawn_on_cells_and_connected(self):
        P, bands = panel(), helpers.build().bands
        pieces = set((c, t) for c, ts in P.cells.items() for t in ts)
        self.assertTrue(pieces)
        # the two levels are joined by connector A and the helix track, so the whole panel is one piece of track
        self.assertEqual(component(links(P), next(iter(sorted(pieces)))), pieces)
        # and every strand of the drawing is there: as many level and sloped steps as the schematic draws
        want = 0
        for _, band, _ in bands:
            for sid, pts in paths(band).items():
                if sid in band["strands"]:
                    want += sum(int(abs(b[0] - a[0])) * cats.SCALE for a, b in zip(pts, pts[1:]))
        steps = sum(1 for c, ts in P.cells.items() for t in ts if t in ("HORIZONTAL", "UPPERSLASH", "LOWERBACKSLASH"))
        self.assertGreaterEqual(steps, want)

    def test_diagonals_are_whole_45_degree_steps(self):
        P = panel()
        partner = {"UPPERSLASH": ((0, -1), "LOWERSLASH"), "LOWERBACKSLASH": ((0, 1), "UPPERBACKSLASH")}
        for cell, tracks in P.cells.items():
            for t, ((dx, dy), other) in partner.items():
                if t in tracks:
                    near = P.cells.get((cell[0] + dx, cell[1] + dy), {})
                    # the other half of the step, or a turnback's vertical run
                    self.assertTrue(other in near or "VERTICAL" in near, (cell, t))

    def test_only_track_ends_dangle(self):
        P, bands = panel(), helpers.build().bands
        loose = 0
        for cell, tracks in P.cells.items():
            for t in tracks:
                for edge in cats.ENDS[t]:
                    if (cell, edge) in P.shared:
                        continue
                    far, fedge = cats.neighbour(cell, edge)
                    if not any(fedge in cats.ENDS[t2] for t2 in P.cells.get(far, {})):
                        loose += 1
        ends = sum(1 for _, b, _ in bands for d in b["nodes"].values() if d["kind"] == "end")
        self.assertEqual(loose, ends - 2 * (len(P.shared) // 2))
        self.assertEqual(len(P.shared), 4)          # connector A and the helix track Summit

    def test_each_switch_has_points_with_two_routes(self):
        P, bands = panel(), helpers.build().bands
        switches = sum(1 for _, b, _ in bands for d in b["nodes"].values() if d["kind"] == "switch")
        crossovers = sum(1 for _, b, _ in bands for d in b["nodes"].values() if d["kind"] == "dx")
        self.assertEqual(len(P.points), switches + 4 * crossovers)
        for (cell, edge), pt in P.points.items():
            routes = pt["routes"]
            self.assertEqual(len(routes), 2, pt)
            self.assertEqual(sum(normal for _, normal in routes), 1, pt)
            here = [t for t in P.cells[cell] if edge in cats.ENDS[t]]
            self.assertEqual(len(here), 2, (cell, edge))
        self.assertEqual(len(P.crossings), 2 * crossovers)

    def test_normal_route_is_leg_b(self):
        P = panel()
        normal = defaultdict(set)
        for (cell, edge), pt in P.points.items():
            normal[pt["switch"]].add((edge, next(r for r, n in pt["routes"] if n)))
        self.assertEqual(normal["1"], {("LEFT", "RIGHT")})         # B runs on level; C slopes down to the yard
        self.assertEqual(normal["13"], {("LEFT", "TOP")})          # the drawing slopes B (Y-3) up, C (Y-4) level
        self.assertEqual(normal["6"], {("LEFT", "RIGHT"), ("RIGHT", "LEFT")})     # crossover: the through tracks

    def test_xml(self):
        P = panel()
        with tempfile.TemporaryDirectory() as tmp:
            a, b = Path(tmp) / "a.xml", Path(tmp) / "b.xml"
            cats.write(P, a)
            cats.write(cats.panel(helpers.build().bands), b)
            self.assertEqual(a.read_text(), b.read_text())          # deterministic
            root = ET.parse(a).getroot()
        self.assertEqual(root.tag, "DOCUMENT")
        self.assertIsNotNone(root.find("COMPRESSIONTAG"))
        self.assertIsNotNone(root.find("ROWWRAPTAG"))
        plan = root.find("TRACKPLAN")
        cols, rows = int(plan.get("COLUMNS")), int(plan.get("ROWS"))
        names = set()
        for sec in plan.iter("SECTION"):
            self.assertTrue(1 <= int(sec.get("X")) <= cols and 1 <= int(sec.get("Y")) <= rows)
            for se in sec.findall("SEC_EDGE"):
                kinds = {c.tag for c in se} - {"SHARED"}
                self.assertLessEqual(len(kinds), 1, ET.tostring(se))   # never a block on points or a crossing
                blk = se.find("BLOCK")
                if blk is not None:
                    self.assertTrue(blk.get("NAME"), "every boundary edge names its block")
                    names.add(blk.get("NAME"))
            self.assertEqual(len(sec.findall("SEC_NAME")), len(set(x.get("NAME") for x in sec.findall("SEC_NAME"))))
        self.assertEqual(names, set(P.names.values()))
        self.assertEqual(len(list(root.iter("IOSPEC"))), 0)           # no bindings without a bindings file
        self.assertEqual(len(list(root.iter("SECSIGNAL"))), 0)
        self.assertIn("OS 6", names)
        self.assertIn("Y-1", names)
        labels = {s.get("NAME") for s in root.iter("SEC_NAME")}
        self.assertTrue({"1", "11", "Y-1", "PASSING"} <= labels, labels)

    def test_command(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            graph = Path(tmp) / "graph.json"
            import json
            graph.write_text(json.dumps(helpers.graph()))
            out = Path(tmp) / "panel.xml"
            r = subprocess.run([sys.executable, "-m", "schematic", "cats", str(out), "--data", str(f),
                                f"{graph}:example", "--band", "Lower"], cwd=helpers.PLUGIN,
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("Lower level", r.stdout)
            self.assertNotIn("Upper level", r.stdout)
            self.assertEqual(ET.parse(out).getroot().tag, "DOCUMENT")


def bands_copy():
    return copy.deepcopy(helpers.build().bands)


def drawn_with(changes):
    """paths() of the example, with some lines replaced: {line id: points}, or {None: ...} to draw nothing."""
    real = paths

    def fake(band):
        out = real(band)
        if None in changes:
            return {}
        return {k: changes.get(k, v) for k, v in out.items()}
    return mock.patch.object(cats, "paths", fake)


def tiny_panel():
    """Two cells of one block, a track on its own: (1, 1) and (2, 1), level."""
    P = cats.Panel()
    P.cells[(1, 1)]["HORIZONTAL"] = ("track", "t")
    P.cells[(2, 1)]["HORIZONTAL"] = ("track", "t")
    P.blocks[("track", "t")] = "Lone"
    P.names[("track", "t")] = "Lone"
    return P


class Review(unittest.TestCase):
    def test_a_track_on_two_bands_is_one_block(self):
        P = panel()
        names = set(P.names.values())
        self.assertTrue({"Summit", "Rise"} <= names, names)
        self.assertFalse({"Summit 2", "Rise 2"} & names, names)
        root = cats.to_xml(P)
        for se in root.iter("SEC_EDGE"):
            if se.find("SHARED") is not None:
                self.assertIsNone(se.find("BLOCK"), "a joined end inside one block is no boundary")

    def test_a_strand_drawn_as_a_point_is_an_error(self):
        with drawn_with({"e13": [(4, 3), (4, 3)]}):
            with self.assertRaisesRegex(cats.SchematicError, "single point"):
                cats.panel(helpers.build().bands)

    def test_a_band_with_nothing_drawn_is_an_error(self):
        with drawn_with({None: None}):
            with self.assertRaisesRegex(cats.SchematicError, "draws no track"):
                cats.panel(helpers.build().bands)

    def test_a_crossover_without_level_track_beside_it_is_an_error(self):
        with drawn_with({"e3": [(2, 1), (3, 0), (5, 0), (6, 1)]}):    # Main slopes straight into crossover 6
            with self.assertRaisesRegex(cats.SchematicError, "double crossover 6: its through tracks must run level"):
                cats.panel(helpers.build().bands)

    def test_switches_sharing_an_os_block_name_it_together(self):
        with mock.patch.object(cats, "OS_REACH", 3):           # 3-8 is 2 steps, 8-4 is 4: too short for 3 each
            P = cats.panel(helpers.build().bands)
        self.assertIn("OS 3-4-8", P.names.values())
        self.assertTrue(any("switches 3, 4, 8 share one OS block" in line for line in P.log), P.log)

    def test_a_block_without_boundary_is_named_on_its_track_end(self):
        root = cats.to_xml(tiny_panel())
        named = [(sec.get("X"), se.get("EDGE")) for sec in root.iter("SECTION") for se in sec.findall("SEC_EDGE")
                 if se.find("BLOCK") is not None]
        self.assertEqual(named, [("1", "LEFT")])

    def test_a_block_on_points_is_an_error(self):
        P = tiny_panel()
        P.cells[(2, 1)]["UPPERSLASH"] = ("track", "t")
        P.cells[(0, 1)]["HORIZONTAL"] = ("track", "u")
        P.blocks[("track", "u")] = P.names[("track", "u")] = "Other"
        P.points[((1, 1), "LEFT")] = dict(switch="9", routes=[("RIGHT", True), ("TOP", False)])
        P.cells[(1, 1)]["UPPERSLASH"] = ("track", "t")
        with self.assertRaisesRegex(cats.SchematicError, "switch points"):
            cats.to_xml(P)

    def test_no_empty_labels(self):
        bands = bands_copy()
        for _, band, _ in bands:
            for d in band["nodes"].values():
                if d["kind"] == "dx":
                    d["label"] = ""
        root = cats.to_xml(cats.panel(bands))
        texts = [s.get("NAME") for s in root.iter("SEC_NAME")]
        self.assertNotIn("", texts)
        self.assertEqual(sum(t.startswith(("UPPER LEVEL", "LOWER LEVEL")) for t in texts), 2)   # band titles

    def test_discipline_is_one_cats_reads(self):
        P = panel()
        self.assertEqual({b.get("DISCIPLINE") for b in cats.to_xml(P, "APB-2").iter("BLOCK") if b.get("NAME")},
                         {"APB-2"})
        with self.assertRaisesRegex(cats.SchematicError, "not one CATS reads"):
            cats.to_xml(P, "UNDEFINED")
        r = subprocess.run([sys.executable, "-m", "schematic", "cats", "x.xml", "--data", ".", "g.json:x",
                            "--discipline", "APB"], cwd=helpers.PLUGIN, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        self.assertIn("invalid choice", r.stderr)


IO = {"DECADDR": "7", "JMRIPREFIX": "IT", "USER_NAME": "Turnout 1"}


def io(cmd, **kw):
    return dict(IO, command=cmd, **kw)


def relabelled(changes):
    """The example's bands with some switch labels or track names changed: {node or strand: (field, value)}."""
    bands = bands_copy()
    for _, band, _ in bands:
        for key, (field, value) in changes.items():
            for part in (band["nodes"], band["strands"]):
                if key in part:
                    part[key][field] = value
    return bands


def edges_of(root, name):
    """(x, y, edge) of every SEC_EDGE whose BLOCK has this name."""
    return [(int(sec.get("X")), int(sec.get("Y")), se.get("EDGE")) for sec in root.iter("SECTION")
            for se in sec.findall("SEC_EDGE") for b in se.findall("BLOCK") if b.get("NAME") == name]


class Bindings(unittest.TestCase):
    def test_one_bound_block_name_is_one_block_and_never_suffixed(self):
        P = cats.panel(helpers.build().bands, bindings={"switches": {"1": {"block": "OS West"}, "4": {"block": "OS West"}}})
        self.assertEqual(list(P.names.values()).count("OS West"), 1)
        self.assertFalse([n for n in P.names.values() if n.startswith("OS West ")])
        with self.assertRaisesRegex(cats.SchematicError, "also the name of another block"):
            cats.panel(helpers.build().bands, bindings={"switches": {"1": {"block": "Main West"}}})

    def test_a_decoder_address_of_zero_is_an_address(self):
        P = cats.panel(helpers.build().bands, bindings={"blocks": {"Main": {"occupied": io("close", DECADDR=0)}}})
        root = cats.to_xml(P)
        self.assertEqual(next(b.find("OCCUPIEDSPEC/IOSPEC").get("DECADDR") for b in root.iter("BLOCK")
                              if b.get("NAME") == "Main"), "0")

    def test_a_whole_label_with_a_slash_is_a_label(self):
        bands = relabelled({"S1": ("label", "1/2")})
        P = cats.panel(bands, bindings={"switches": {"1/2": {"block": "OS Slash"}}})
        self.assertIn("OS Slash", P.names.values())
        P = cats.panel(bands, bindings={"switches": {"1/2/T10": {"block": "OS Slash"}}})    # alias after the last /
        self.assertIn("OS Slash", P.names.values())

    def test_a_switch_label_binding_replaces_the_number_shown(self):
        P = cats.panel(helpers.build().bands, bindings={"switches": {"1": {"label": "1X"}, "6": {"label": "6Y"}}})
        texts = {t for t, _, _ in P.labels.values()}
        self.assertTrue({"1X", "6Y"} <= texts, texts)
        self.assertFalse({"1", "6"} & texts)
        P = cats.panel(helpers.build().bands, scale=1, bindings={"switches": {"1": {"label": "1X"}}})
        self.assertIn("1X", {t for t, _, _ in P.labels.values()})
        for bad in ("", 7):
            with self.assertRaisesRegex(cats.SchematicError, "label is the text shown"):
                cats.panel(helpers.build().bands, bindings={"switches": {"1": {"label": bad}}})

    def test_switch_routes_are_bound_by_leg(self):
        b = {"switches": {"1": {"routes": {"B": {"ROUTECOMMAND": io("close"), "SELECTEDREPORT": io("close")},
                                           "C": {"ROUTECOMMAND": io("throw")}}}}}
        P = cats.panel(helpers.build().bands, bindings=b)
        (at, pt), = [(k, v) for k, v in P.points.items() if v["switch"] == "1"]
        root = cats.to_xml(P)
        x, y, edge = at[0][0], at[0][1], at[1]
        sp = root.find(f"TRACKPLAN/SECTION[@X='{x}'][@Y='{y}']/SEC_EDGE[@EDGE='{edge}']/SWITCHPOINTS")
        got = {ri.get("ROUTEID"): (ri.get("NORMAL"), [(c.tag, c.find("IOSPEC").text, c.find("IOSPEC").get("DECADDR"))
                                                       for c in ri])
               for ri in sp.findall("ROUTEINFO")}
        leg = {p: e for e, p in pt["ports"].items()}
        self.assertEqual(got[leg["B"]], ("true", [("ROUTECOMMAND", "close", "7"), ("SELECTEDREPORT", "close", "7")]))
        self.assertEqual(got[leg["C"]], (None, [("ROUTECOMMAND", "throw", "7")]))
        # normal C: the other route is NORMAL, the IOSPECs stay on their legs
        b["switches"]["1"]["normal"] = "C"
        P = cats.panel(helpers.build().bands, bindings=b)
        pt = next(v for v in P.points.values() if v["switch"] == "1")
        normal = next(e for e, n in pt["routes"] if n)
        self.assertEqual(pt["ports"][normal], "C")

    def test_a_double_crossover_takes_routes_on_all_four_points(self):
        """One turnout moves all four points of a double crossover: route B along each through track, C into the X."""
        b = {"switches": {"6": {"routes": {"B": {"ROUTECOMMAND": io("close"), "SELECTEDREPORT": io("close")},
                                           "C": {"ROUTECOMMAND": io("throw"), "SELECTEDREPORT": io("throw")}}}}}
        P = cats.panel(helpers.build().bands, bindings=b)
        pts = {k: v for k, v in P.points.items() if v["switch"] == "6"}
        self.assertEqual(len(pts), 4)
        root = cats.to_xml(P)
        for (cell, edge), pt in pts.items():
            sp = root.find(f"TRACKPLAN/SECTION[@X='{cell[0]}'][@Y='{cell[1]}']/SEC_EDGE[@EDGE='{edge}']/SWITCHPOINTS")
            got = {ri.get("ROUTEID"): (ri.get("NORMAL"), sorted((c.tag, c.find("IOSPEC").text) for c in ri))
                   for ri in sp.findall("ROUTEINFO")}
            leg = {p: e for e, p in pt["ports"].items()}
            self.assertEqual(sorted(pt["ports"].values()), ["B", "C"])
            self.assertIn(leg["B"], ("LEFT", "RIGHT"))             # B is the level through track
            self.assertEqual(got[leg["B"]], ("true", [("ROUTECOMMAND", "close"), ("SELECTEDREPORT", "close")]))
            self.assertEqual(got[leg["C"]], (None, [("ROUTECOMMAND", "throw"), ("SELECTEDREPORT", "throw")]))
        b["switches"]["6"]["normal"] = "C"                         # normal C: the crossing routes are NORMAL
        P = cats.panel(helpers.build().bands, bindings=b)
        for pt in (v for v in P.points.values() if v["switch"] == "6"):
            self.assertEqual(pt["ports"][next(e for e, n in pt["routes"] if n)], "C")

    def test_a_helix_track_can_be_a_block_on_each_band(self):
        P = cats.panel(helpers.build().bands, helix_blocks="apart")
        names = set(P.names.values())
        self.assertTrue({"Summit", "Summit 2"} <= names, names)
        self.assertEqual(len(P.shared), 4)                         # still joined: the train runs on
        root = cats.to_xml(P)
        joined = {se.find("BLOCK").get("NAME") for se in root.iter("SEC_EDGE")
                  if se.find("SHARED") is not None and se.find("BLOCK") is not None}
        self.assertEqual(joined, {"Summit", "Summit 2"})           # the helix join is the boundary; connector A is not
        # one block (the default) is unchanged
        self.assertNotIn("Summit 2", set(cats.panel(helpers.build().bands).names.values()))
        with self.assertRaisesRegex(cats.SchematicError, "helix_blocks is one of one, apart"):
            cats.panel(helpers.build().bands, helix_blocks="split")

    def test_blocks_are_renamed_and_bound_on_every_edge(self):
        b = {"blocks": {"Main West": {"name": "Track Main West", "station": "Main", "discipline": "ABS",
                                      "occupied": io("close"), "unoccupied": {"DECADDR": "7", "command": "throw"}}}}
        root = cats.to_xml(cats.panel(helpers.build().bands, bindings=b))
        self.assertFalse(edges_of(root, "Main West"))
        edges = edges_of(root, "Track Main West")
        self.assertGreaterEqual(len(edges), 2)
        for blk in (b_ for b_ in root.iter("BLOCK") if b_.get("NAME") == "Track Main West"):
            self.assertEqual((blk.get("STATION"), blk.get("DISCIPLINE")), ("Main", "ABS"))
            occ = blk.find("OCCUPIEDSPEC/IOSPEC")
            self.assertEqual((occ.get("DECADDR"), occ.get("JMRIPREFIX"), occ.get("USER_NAME"), occ.text),
                             ("7", "IT", "Turnout 1", "close"))
            self.assertEqual(blk.find("UNOCCUPIEDSPEC/IOSPEC").text, "throw")
        other = next(b_ for b_ in root.iter("BLOCK") if b_.get("NAME") == "Main")
        self.assertEqual(other.get("DISCIPLINE"), "CTC")
        self.assertIsNone(other.find("OCCUPIEDSPEC"))

    def test_two_blocks_given_one_name_are_one_block(self):
        bands = helpers.build().bands
        with self.assertRaisesRegex(cats.SchematicError, "the name of block OS 11, which the bindings do not name"):
            cats.panel(bands, bindings={"blocks": {"Link 11-12": {"name": "OS 11"}}})
        P = cats.panel(bands, bindings={"blocks": {"Link 11-12": {"name": "OS 11"}, "OS 11": {}}})
        self.assertIn("blocks Link 11-12, OS 11 are one block, OS 11", P.log)
        self.assertNotIn("Link 11-12", P.names.values())
        self.assertEqual(list(P.names.values()).count("OS 11"), 1)
        root = cats.to_xml(P)
        for x, y, edge in edges_of(root, "OS 11"):          # no boundary left between the two
            far, fedge = cats.neighbour((x, y), edge)
            self.assertNotIn((far[0], far[1], fedge), edges_of(root, "OS 11"))

    def test_switches_of_one_number_bound_to_two_blocks_keep_apart(self):
        bands = relabelled({"L12": ("label", "11")})        # 11 and 12 joined by Link 11-12 now share a number
        self.assertIn("OS 11", cats.panel(bands).names.values())
        self.assertNotIn("OS 12", cats.panel(bands).names.values())
        P = cats.panel(bands, bindings={"switches": {"11/T40": {"block": "OS 11a"}, "11/T42": {"block": "OS 11b"}}})
        self.assertTrue({"OS 11a", "OS 11b"} <= set(P.names.values()), P.names.values())
        self.assertNotIn("OS 11", P.names.values())
        with self.assertRaisesRegex(cats.SchematicError, "bound by both"):
            cats.panel(bands, bindings={"switches": {"11": {}, "11/T40": {}}})

    def test_a_turnback_between_two_named_tracks_is_two_blocks(self):
        P = cats.panel(relabelled({"e12.1": ("name", "Loop East")}))
        self.assertTrue({"Loop", "Loop East"} <= set(P.names.values()))
        root = cats.to_xml(P)
        cut = [e for e in edges_of(root, "Loop") if e[2] in ("TOP", "BOTTOM")]
        self.assertEqual(len(cut), 1)
        x, y, edge = cut[0]
        far, fedge = cats.neighbour((x, y), edge)
        self.assertIn((far[0], far[1], fedge), edges_of(root, "Loop East"))
        self.assertNotIn("Loop East", cats.panel(helpers.build().bands).names.values())    # one name: one block

    def test_masts_stand_on_the_boundary_of_the_block_they_protect(self):
        b = {"masts": {"M12C": {"name": "Mast 12C", "template": "single"}, "M1A": {}, "M2E": {"pantype": "SEM2"}}}
        P = cats.panel(helpers.build().bands, bindings=b)
        header = [ET.fromstring('<SIGNALTEMPLATE TEMPLATENAME="single" TEMPLATEHEADS="1" />')]
        root = cats.to_xml(P, header=header)
        bounds = cats.boundaries(P)
        seen = {}
        for sec in root.iter("SECTION"):
            for se in sec.findall("SEC_EDGE"):
                sig = se.find("SECSIGNAL")
                if sig is None:
                    continue
                edge = se.get("EDGE")
                cell = (int(sec.get("X")), int(sec.get("Y")))
                self.assertIn((cell, edge), bounds)
                pan = sig.find("PANELSIGNAL")
                self.assertEqual(pan.get("SIGORIENT"), cats.OPPOSITE[edge])        # facing out of its block
                self.assertEqual(pan.get("SIGLOCATION"), cats.SIG_LOCATION[edge])  # right-hand side of the move
                seen[sig.text] = (se.find("BLOCK").get("NAME"), pan.get("SIGPANTYPE"), sig.findtext("PHYSIGNAL"))
        self.assertEqual(seen["Mast 12C"], ("OS 12", "LAMP1", "single"))        # toward 12, guards its OS
        self.assertEqual(seen["M1A"], ("OS 1", "LAMP1", None))
        self.assertEqual(seen["M2E"][1:], ("SEM2", None))
        self.assertIn(seen["M2E"][0], ("OS 2", "Main West"))
        self.assertEqual(cats.SIG_LOCATION, {"RIGHT": "UPRIGHT", "LEFT": "LOWLEFT", "TOP": "LEFTUP",
                                             "BOTTOM": "RIGHTLOW"})
        with self.assertRaisesRegex(cats.SchematicError, "no SIGNALTEMPLATE for"):
            cats.to_xml(P)

    def test_a_mast_on_a_fold_guards_its_half_of_the_turnback(self):
        bands = relabelled({"e12.1": ("name", "Loop East")})
        for _, _, o in bands:
            o["signals"] = [dict(mast="X5", toward="5", run=["5", "5"], names=["Loop"], edge_cm=523.6,
                                 cm_from_toward=255.0, dir="east", kind="planned", heads=1, _edge="e12",
                                 _toward_node="S5")]
        P = cats.panel(bands, bindings={"masts": {"X5": {}}})
        (cell, edge), = P.signals
        self.assertIn(edge, ("TOP", "BOTTOM"))
        root = cats.to_xml(P)
        self.assertIn((cell[0], cell[1], edge), edges_of(root, "Loop"))

    def fold_mast(self, bands, start=None):
        for _, _, o in bands:
            o["signals"] = [dict(mast="X5", toward="5", run=["5", "5"], names=["Loop"], edge_cm=523.6,
                                 cm_from_toward=255.0, dir="east", kind="planned", heads=1, _edge="e12",
                                 _toward_node="S5")]
        if start is None:
            return cats.panel(bands, bindings={"masts": {"X5": {}}})
        piece = lambda sg, strands: ("e12.0", 5.0, 261.8, start) if "e12.0" in strands else None
        with mock.patch.object(cats_masts, "mast_piece", piece):
            return cats.panel(bands, bindings={"masts": {"X5": {}}})

    def test_a_turnback_merged_by_the_bindings_is_no_boundary_for_a_mast(self):
        bands = relabelled({"e12.1": ("name", "Loop East")})
        P = self.fold_mast(bands)                         # split: the mast is on the cut
        self.assertIn(next(iter(P.signals))[1], ("TOP", "BOTTOM"))
        P = cats.panel(bands, bindings={"blocks": {"Loop East": {"name": "Loop"}, "Loop": {}}, "masts": {"X5": {}}})
        (cell, edge), = P.signals                         # merged: the cut is gone, the mast takes another boundary
        self.assertNotIn(edge, ("TOP", "BOTTOM"))
        self.assertIn((cell, edge), cats.boundaries(P))

    def test_a_turnback_behind_the_mast_is_a_boundary_too(self):
        P = self.fold_mast(relabelled({"e12.1": ("name", "Loop East")}), start="turn:e12")
        (cell, edge), = P.signals
        self.assertIn(edge, ("TOP", "BOTTOM"))
        root = cats.to_xml(P)
        self.assertIn((cell[0], cell[1], edge), edges_of(root, "Loop East"))    # the block it enters

    def test_a_mast_whose_run_has_no_such_end_is_an_error(self):
        with self.assertRaisesRegex(cats.SchematicError, "cannot tell which end"):
            self.fold_mast(relabelled({"e12.1": ("name", "Loop East")}), start="LINK:A0")

    def test_unknown_names_and_bad_fields_are_errors(self):
        bands = helpers.build().bands
        for bad, msg in (({"switches": {"99": {}}}, "switch 99, which no drawn band has"),
                         ({"switches": {"1/T99": {}}}, "switch 1/T99"),
                         ({"switches": {"1": {"normal": "A"}}}, "normal is leg B or C"),
                         ({"switches": {"1": {"routes": {"B": {"COMMAND": io("close")}}}}}, "unknown field COMMAND"),
                         ({"switches": {"1": {"routes": {"B": {"ROUTECOMMAND": io("open")}}}}}, "close or throw"),
                         ({"switches": {"1": {"routes": {"B": {"ROUTECOMMAND": {"command": "close"}}}}}}, "DECADDR"),
                         ({"switches": {"1": {"routes": {"B": {"ROUTECOMMAND": io("close", PORT="1")}}}}}, "PORT"),
                         ({"blocks": {"Nowhere": {"name": "X"}}}, "block Nowhere, which the panel does not have"),
                         ({"blocks": {"Main": {"discipline": "APB"}}}, "not one CATS reads"),
                         ({"masts": {"M99": {}}}, "mast M99, which no band"),
                         ({"masts": {"V2": {}}}, "V2 is virtual"),
                         ({"masts": {"M1A": {"pantype": "LAMP9"}}}, "pantype"),
                         ({"signals": {}}, "unknown field signals")):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(cats.SchematicError, msg):
                    cats.panel(bands, bindings=bad)

    def test_command_with_bindings_and_templates(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            import json
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(helpers.graph()))
            src = Path(tmp) / "desk.xml"
            src.write_text('<DOCUMENT><SIGNALTEMPLATE TEMPLATENAME="single" TEMPLATEHEADS="1"><ASPECTMAP R292="red"/>'
                           '</SIGNALTEMPLATE><JMRINAME JMRIPREFIX="IT" XMLTYPE="Turnout">x</JMRINAME></DOCUMENT>')
            good = Path(tmp) / "good.json"
            good.write_text(json.dumps({"_note": "a note", "masts": {"M1A": {"template": "single"}},
                                        "blocks": {"Summit": {"occupied": io("close")}}}))
            bad = Path(tmp) / "bad.json"
            bad.write_text(json.dumps({"blocks": {"Nowhere": {}}}))
            out = Path(tmp) / "panel.xml"
            run = lambda *extra: subprocess.run([sys.executable, "-m", "schematic", "cats", str(out), "--data", str(f),
                                                 f"{graph}:example", *extra], cwd=helpers.PLUGIN,
                                                capture_output=True, text=True, timeout=120)
            r = run("--bindings", str(good), "--templates-from", str(src))
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("bound: 1 block sensors, 0 switch points, 1 masts", r.stdout)
            root = ET.parse(out).getroot()
            self.assertEqual([e.tag for e in root if e.tag in ("SIGNALTEMPLATE", "JMRINAME", "TRACKPLAN")],
                             ["SIGNALTEMPLATE", "JMRINAME", "TRACKPLAN"])
            self.assertEqual(root.find("SIGNALTEMPLATE/ASPECTMAP").get("R292"), "red")
            self.assertEqual(next(s.findtext("PHYSIGNAL") for s in root.iter("SECSIGNAL")), "single")
            r = run("--bindings", str(bad))
            self.assertEqual(r.returncode, 2)
            self.assertIn("block Nowhere", r.stderr)
            r = run("--bindings", str(bad), "--templates-from", str(Path(tmp) / "missing.xml"))   # read first
            self.assertEqual(r.returncode, 2)
            self.assertIn("cannot read it as a CATS panel", r.stderr)


MASTS = {"masts": {"M12C": {}, "M1A": {}, "M2E": {}}}


def compact():
    if "cats1" not in helpers._cache:
        helpers._cache["cats1"] = cats.panel(helpers.build().bands, scale=1, bindings=MASTS)
    return helpers._cache["cats1"]


class Compact(unittest.TestCase):
    """One cell per grid unit (--cells-per-unit 1), to fit a screen at CATS's fixed 30 pixel grid."""

    def test_half_the_size_and_the_same_track_switches_and_blocks(self):
        P, wide = compact(), cats.panel(helpers.build().bands, bindings=MASTS)
        cols, rows = cats.shown(P)
        self.assertLessEqual(cols, cats.shown(wide)[0] * 0.6)
        self.assertLessEqual(rows, cats.shown(wide)[1] * 0.7)
        pieces = set((c, t) for c, ts in P.cells.items() for t in ts)
        self.assertEqual(component(links(P), next(iter(sorted(pieces)))), pieces)     # still one piece of track
        self.assertEqual(len(P.points), len(wide.points))
        for (cell, edge), pt in P.points.items():
            self.assertEqual(len(pt["routes"]), 2, pt)
            self.assertEqual(len([t for t in P.cells[cell] if edge in cats.ENDS[t]]), 2, (cell, edge))
        self.assertEqual(len(P.shared), len(wide.shared))
        # every switch keeps its own OS block: 3 and 8 (one unit of level track apart) get a widened column
        self.assertEqual(sorted(n for n in P.names.values() if n.startswith("OS")),
                         sorted(n for n in wide.names.values() if n.startswith("OS")))
        self.assertEqual(P.log, ["label 'RISE' at (20, 12) UPCENT crosses 1 track lines, signals or labels"])

    def test_a_crossover_one_row_deep_crosses_between_the_rows(self):
        P = compact()
        (a, ea), (b, eb) = sorted(P.crossings)
        self.assertEqual((ea, eb), ("BOTTOM", "TOP"))
        self.assertEqual((b[0], b[1] - 1), a)
        self.assertEqual(sorted(P.cells[a]), ["HORIZONTAL", "LOWERBACKSLASH", "LOWERSLASH"])
        self.assertEqual(sum(1 for pt in P.points.values() if pt["switch"] == "6"), 4)
        root = cats.to_xml(P)
        x = [se for sec in root.iter("SECTION") for se in sec.findall("SEC_EDGE") if se.find("CROSSINGEDGE") is not None]
        self.assertEqual([se.find("CROSSINGEDGE").attrib for se in x], [{"LEFT": "NO_BLOCK", "RIGHT": "NO_BLOCK"}] * 2)

    def test_a_double_crossover_with_corners_is_a_block_per_corner(self):
        """corners: the X opens to two rows deep, each corner holds its points, half of each through track and the
        first piece of its diagonal, the middle of the X is a block of its own, and no block parts on points or a
        crossing; the track stays one piece."""
        names = {"A": "C-A", "B": "C-B", "C": "C-C", "D": "C-D", "X": "C-X"}
        P = cats.panel(helpers.build().bands, scale=1, bindings={"switches": {"6": {"corners": names}}})
        self.assertLessEqual(set(names.values()), set(P.names.values()))
        (a, ea), (b, eb) = sorted(P.crossings)
        self.assertEqual((ea, eb), ("RIGHT", "LEFT"))          # two rows deep: the crossing is on a column edge
        bounds = cats.boundaries(P)                             # raises on a boundary at points or a crossing
        name_at = lambda cell, t: P.names[P.find(P.cells[cell][t])]
        self.assertEqual({name_at(a, t) for t in P.cells[a]} | {name_at(b, t) for t in P.cells[b]}, {"C-X"})
        corner_points = defaultdict(set)
        for (cell, edge), pt in P.points.items():
            if pt["switch"] == "6":
                corner_points[{name_at(cell, t) for t in P.cells[cell] if edge in cats.ENDS[t]}.pop()].add(cell)
        self.assertEqual(sorted(corner_points), ["C-A", "C-B", "C-C", "C-D"])
        self.assertTrue(all(len(v) == 1 for v in corner_points.values()))
        self.assertTrue(any(P.names[r] == "C-X" for r in bounds.values()))
        pieces = set((c, t) for c, ts in P.cells.items() for t in ts)
        self.assertEqual(component(links(P), next(iter(sorted(pieces)))), pieces)
        self.assertTrue(any("row(s) opened" in m for m in P.log), P.log)
        cats.to_xml(P)

    def test_corners_must_name_four_different_blocks(self):
        for bad in ({"A": "a", "B": "b", "C": "c"}, {"A": "a", "B": "a", "C": "c", "D": "d"}):
            with self.subTest(corners=bad), self.assertRaises(cats.SchematicError):
                cats.panel(helpers.build().bands, scale=1, bindings={"switches": {"6": {"corners": bad}}})
        with self.assertRaises(cats.SchematicError):
            cats.panel(helpers.build().bands, scale=1, bindings={"switches": {"6": {
                "corners": {"A": "a", "B": "b", "C": "c", "D": "d"}, "block": "OS 6"}}})

    def test_a_slope_across_an_opened_row_jogs_there(self):
        self.assertEqual(cats.unit_steps([(0, 0), (2, 3)], opened={2}), [((0, 0), (1, 1)), ((1, 1), (2, 3))])
        self.assertEqual(cats.step_pieces((1, 1), (2, 3)),
                         [((1, 1), "LOWERBACKSLASH"), ((1, 2), "VERTICAL"), ((1, 3), "UPPERBACKSLASH")])
        self.assertEqual(cats.step_pieces((0, 3), (1, 1)),
                         [((0, 3), "UPPERSLASH"), ((0, 2), "VERTICAL"), ((0, 1), "LOWERSLASH")])
        with self.assertRaises(cats.SchematicError):            # steeper, with no opened row to take it
            cats.unit_steps([(0, 0), (2, 3)])

    def test_masts_keep_their_blocks_and_stand_on_level_edges(self):
        P, wide = compact(), cats.panel(helpers.build().bands, bindings=MASTS)
        protects = lambda Q: {s["mast"]: Q.names[cats.boundaries(Q)[k]] for k, s in Q.signals.items()}
        self.assertEqual(protects(P), protects(wide))
        self.assertEqual(len(P.signals), 3)
        lines = cats.track_lines(P)
        for (cell, edge), s in P.signals.items():
            self.assertIn(edge, ("LEFT", "RIGHT"))      # whole steps fit, so the boundaries are on level edges
            self.assertEqual(s["orient"], cats.OPPOSITE[edge])
            box = cats.frill_box(cell, s["loc"], 2 * cats.SIG_PX, cats.SIG_PX)
            self.assertFalse([ln for ln in lines if cats.crosses(box, ln, rim=1)], s)

    def test_a_mast_on_level_track_points_its_way_on_its_right_near_its_gap_and_clear(self):
        P = cats.Panel()                                # a level track, gaps on both ends of cell (5, 5)
        for x in range(2, 9):
            P.cells[(x, 5)]["HORIZONTAL"] = ("track", "a")
        lines = cats.track_lines(P)
        for edge, heads, want in (("LEFT", 2, ("LOWCENT", "RIGHT")), ("RIGHT", 2, ("UPCENT", "LEFT")),
                                  ("LEFT", 1, ("LOWRIGHT", "RIGHT")), ("RIGHT", 3, ("UPCENT", "LEFT"))):
            cost, loc, orient = cats.place_mast(P, (5, 5), edge, heads)
            self.assertEqual((loc, orient), want, (edge, heads))
            self.assertEqual(cats.spot_costs(P, (5, 5), edge, heads)[(loc, orient)][1], [])     # nothing against it
            box = cats.frill_box((5, 5), loc, *cats.mast_size(heads, orient))
            self.assertTrue(all(cats.box_gap(box, ln) >= 5 for ln in lines))
            self.assertEqual(box[1] > 15 + 5 * 30, edge == "LEFT")     # below the track going right, above going left

    def test_a_mast_takes_a_spot_clear_of_the_points_and_another_mast(self):
        P = cats.Panel()                                # points at the LEFT edge of (5, 5), diverging down
        for x in range(2, 9):
            P.cells[(x, 5)]["HORIZONTAL"] = ("track", "a")
        P.cells[(5, 5)]["LOWERBACKSLASH"] = ("track", "a")
        P.cells[(5, 6)]["UPPERBACKSLASH"] = ("track", "c")
        P.points[((5, 5), "LEFT")] = dict(switch="1", routes=[("BOTTOM", False), ("RIGHT", True)])
        costs = cats.spot_costs(P, (5, 5), "RIGHT", 2)
        self.assertIn("points", costs[("LEFTCENT", "LEFT")][1])     # over the points' gap
        self.assertIn("ink", costs[("LOWRIGHT", "LEFT")][1])        # on the diverging leg
        box = cats.frill_box((5, 5), "UPCENT", *cats.mast_size(2, "LEFT"))
        self.assertEqual(cats.place_mast(P, (5, 5), "RIGHT", 2)[1:], ("UPCENT", "LEFT"))
        self.assertIn("mast", cats.spot_costs(P, (5, 5), "RIGHT", 2, [box])[("UPCENT", "LEFT")][1])  # if taken

    def test_a_mast_mid_slope_in_a_switch_cell_points_up_beside_the_slope(self):
        P = cats.Panel()            # a switch's cell: level track and a slope leaving by the bottom edge, points RIGHT
        P.cells[(5, 5)].update(HORIZONTAL=("track", "a"), LOWERSLASH=("track", "b"))
        P.cells[(5, 6)]["UPPERSLASH"] = ("track", "c")
        P.cells[(4, 5)]["HORIZONTAL"] = ("track", "a")
        P.cells[(6, 5)]["HORIZONTAL"] = ("track", "a")
        P.points[((5, 5), "RIGHT")] = dict(switch="1", routes=[("BOTTOM", False), ("LEFT", True)])
        # nowhere is clean; above the level track would read as that track's mast, so the lamps point up the slope
        costs = cats.spot_costs(P, (5, 5), "BOTTOM", 1)
        self.assertIn("other", costs[("UPCENT", "RIGHT")][1])
        self.assertEqual(cats.place_mast(P, (5, 5), "BOTTOM", 1)[1:], ("LOWLEFT", "TOP"))
        P.cells[(9, 9)]["VERTICAL"] = ("track", "d")         # a turnback's vertical run: lamps up or down, beside it
        self.assertEqual(cats.place_mast(P, (9, 9), "TOP", 1)[1:], ("LEFTCENT", "BOTTOM"))

    def gantry_rows(self, toward="9"):
        P = cats.Panel()
        chains, plans = {}, []
        for row, gap, name in ((5, 5, "A"), (6, 6, "B")):
            pieces, owner = [], []
            for i, x in enumerate(range(2, 10)):
                key = ("track", name) if x < gap else ("os", name)
                P.cells[(x, row)]["HORIZONTAL"] = key
                P.blocks[key] = P.names[key] = name + key[0]
                pieces.append(((x, row), "HORIZONTAL", i, i + 1))
                owner.append(key)
            chains[(0, name)] = dict(pieces=pieces, owner=owner, steps=[None] * len(pieces))
            plans.append(dict(name="M" + name, bi=0, k=name, rev=True, label=name, far="x", near="y", pos=0.0,
                              gap={"b": gap - 2, "pair": (("os", name), ("track", name))},
                              sg={"toward": toward, "dir": "east"}))
        return P, chains, plans

    def test_only_masts_of_one_switch_or_control_point_form_a_gantry(self):
        P, chains, plans = self.gantry_rows(toward="")
        self.assertEqual(cats.shift_gaps(P, [("t", {}, {})], chains, plans), [])
        self.assertEqual([p["gap"]["b"] for p in plans], [3, 4])                    # nothing moved
        P, chains, plans = self.gantry_rows()
        self.assertEqual(len(cats.shift_gaps(P, [("t", {}, {})], chains, plans)), 1)

    def test_a_gap_that_cannot_move_stays_where_it_is(self):
        P, chains, plans = self.gantry_rows()
        P.crossings.add(((6, 6), "LEFT"))               # its own gap fails the checks
        self.assertEqual(cats.shift_gaps(P, [("t", {}, {})], chains, plans), [])
        self.assertEqual(plans[1]["gap"]["b"], 4)
        self.assertIn("mast MB: its gap stays where it is (no room to move it)", P.log)

    def test_a_gap_between_other_blocks_is_an_error(self):
        P, chains, plans = self.gantry_rows()
        self.assertEqual(cats.mast_gap(P, chains, {}, plans[0], plans[0]["gap"]["pair"])["at"], ((5, 5), "LEFT"))
        with self.assertRaisesRegex(cats.SchematicError, "no longer on its track"):
            cats.mast_gap(P, chains, {}, plans[0], (("os", "B"), ("track", "B")))

    def test_a_gantry_look_keeps_clear_of_masts_already_placed(self):
        P, chains, plans = self.gantry_rows()
        spots = {"MA": ((5, 5), "LEFT"), "MB": ((5, 6), "LEFT")}
        for p in plans:
            p["heads"] = 2
        lines = cats.track_lines(P)
        free = cats.gantry_look(P, plans, spots, [], lines)
        box = cats.frill_box((5, 6), free[0], *cats.mast_size(2, free[1]))
        taken = cats.gantry_look(P, plans, spots, [box], lines)
        self.assertNotEqual(taken, free)
        for p in plans:
            if taken:
                b = cats.frill_box(spots[p["name"]][0], taken[0], *cats.mast_size(2, taken[1]))
                self.assertFalse(cats.overlaps(b, box, 1))

    def test_gaps_slide_along_their_tracks_into_one_column_and_out_of_switch_cells(self):
        P = cats.Panel()
        chains, plans = {}, []
        # three parallel tracks heading east into a control point's OS blocks; their gaps in columns 5, 6 and 5,
        # and the middle one's first OS cell is a switch's cell
        for row, gap, name in ((5, 5, "A"), (6, 6, "B"), (7, 5, "C")):
            pieces, owner = [], []
            for i, x in enumerate(range(2, 10)):
                key = ("track", name) if x < gap else ("os", name)
                P.cells[(x, row)]["HORIZONTAL"] = key
                P.blocks[key] = name
                pieces.append(((x, row), "HORIZONTAL", i, i + 1))
                owner.append(key)
            chains[(0, name)] = dict(pieces=pieces, owner=owner)
            plans.append(dict(name="M" + name, bi=0, k=name, rev=True, label=name, gap={"b": gap - 2, "pair": None},
                              sg={"toward": "9", "dir": "east"}))
        P.cells[(6, 6)]["LOWERSLASH"] = ("os", "B")
        bands = [("t", {}, {"control_points": {"Nine": {"switches": ["9"]}}})]
        gantries = cats.shift_gaps(P, bands, chains, plans)
        self.assertEqual([sorted(p["name"] for p in g) for g in gantries], [["MA", "MB", "MC"]])
        cols = {p["name"]: chains[(0, p["k"])]["pieces"][p["gap"]["b"]][0] for p in plans}
        self.assertEqual(cols, {"MA": (5, 5), "MB": (5, 6), "MC": (5, 7)})     # one column, a plain cell each
        for name in "ABC":                              # the same two blocks each side of each gap
            owners = [P.cells[(x, {"A": 5, "B": 6, "C": 7}[name])]["HORIZONTAL"] for x in range(2, 10)]
            self.assertEqual(owners, [("track", name)] * 3 + [("os", name)] * 5)
        self.assertEqual([m for m in P.log if "gap moved" in m], ["mast MB: its gap moved 1 cell(s) along track B"])

    def test_columns_of_plain_level_track_come_out_to_keep_a_margin(self):
        P = cats.Panel()
        P.pending = []
        for x in range(2, 11):
            P.cells[(x, 5)]["HORIZONTAL"] = ("track", "a")
            P.cells[(x, 6)]["HORIZONTAL"] = ("track", "b" if x < 7 else "c")
        P.cells[(11, 5)]["LOWERBACKSLASH"] = ("track", "a")     # a turnback's corner in the last column
        P.signals[((7, 6), "LEFT")] = dict(mast="M", name="M", loc="LOWCENT", orient="RIGHT", pantype="LAMP1",
                                           template=None)
        P.pending.append((3, 0, [((9, 5), "UPCENT"), ((10, 5), "UPCENT")], "A", "FONT_LABEL"))
        cats.trim_columns(P, 9)
        self.assertEqual(max(c[0] for c in P.cells), 9)
        self.assertEqual(P.cells[(9, 5)], {"LOWERBACKSLASH": ("track", "a")})      # the corner moved in
        self.assertIn(((7, 6), "LEFT"), P.signals)                                  # the gap and mast stay
        self.assertEqual([P.cells[(x, 6)]["HORIZONTAL"][1] for x in range(6, 9)], ["b", "c", "c"])
        self.assertEqual(P.pending[0][2], [((8, 5), "UPCENT")])                     # a label's spot follows
        self.assertEqual(len(P.log), 2)
        P.points[((8, 5), "RIGHT")] = dict(switch="1", routes=[])                   # no plain column is left
        with self.assertRaises(cats.SchematicError):
            cats.trim_columns(P, 4)

    def test_an_empty_cell_between_two_track_ends_is_never_taken_out(self):
        P = cats.Panel()
        for x in range(2, 9):
            P.cells[(x, 5)]["HORIZONTAL"] = ("track", "a")
        for x in (2, 3, 5, 6, 7, 8):                    # row 6: two tracks ending either side of the empty (4, 6)
            P.cells[(x, 6)]["HORIZONTAL"] = ("track", "b" if x < 4 else "c")
        self.assertFalse(cats.column_plain(P, 4))
        self.assertTrue(cats.column_plain(P, 6))
        spots = {"M": ((7, 6), "LEFT")}
        cats.trim_columns(P, 7, spots)
        self.assertEqual(spots, {"M": ((6, 6), "LEFT")})                           # a mast's spot follows
        self.assertNotIn((4, 6), P.cells)
        self.assertEqual(P.cells[(3, 6)]["HORIZONTAL"], ("track", "b"))

    def test_ends_of_parallel_tracks_are_named_alike(self):
        P = cats.Panel()
        P.pending = []
        for y in (5, 6):
            for x in range(2, 8):
                P.cells[(x, y)]["HORIZONTAL"] = ("track", str(y))
        P.cells[(11, 5)]["VERTICAL"] = ("track", "v")        # a turnback past the ends: no room beside them
        P.cells[(11, 6)]["VERTICAL"] = ("track", "v")
        P.pending.append((2, 0, [(8, ("LEFTCENT",)), (7, ("LOWLEFT",)), (6, ("LOWLEFT",))],
                          [(5, "HELIX TO MAIN", []), (6, "HELIX TO UPPER", [])], "FONT_LABEL"))
        P.pending.append((3, 1, [5, 4], [(5, "SHORT", []), (6, "LONGER NAME", [])], "FONT_LABEL"))
        cats.place_labels(P)
        self.assertEqual(P.labels[(7, 5)], ("HELIX TO MAIN", "LOWLEFT", "FONT_LABEL"))   # one column and spot
        self.assertEqual(P.labels[(7, 6)], ("HELIX TO UPPER", "LOWLEFT", "FONT_LABEL"))
        names = {t: (c, loc) for c, (t, loc, _) in P.labels.items() if t in ("SHORT", "LONGER NAME")}
        self.assertEqual({loc for _, loc in names.values()}, {"UPLEFT"})   # unequal names start in one line
        self.assertEqual(len({c[0] for c, _ in names.values()}), 1)

    def test_labels_share_cells_with_track_without_covering_it(self):
        P = compact()
        root = cats.to_xml(P)
        labels = {s.get("NAME") for s in root.iter("SEC_NAME")}
        switches = {d["label"] for _, b, _ in helpers.build().bands for d in b["nodes"].values()
                    if d["kind"] in ("switch", "dx") and d.get("label")}
        self.assertTrue(switches <= labels, switches - labels)
        self.assertTrue({"Y-1", "PASSING", "LOOP LEAD"} <= labels)
        self.assertTrue(any(cell in P.cells for cell in P.labels))       # names on their track
        lines, boxes = cats.track_lines(P), []
        for cell, (text, loc, font) in sorted(P.labels.items()):
            box = cats.text_box(cell, loc, text, font)
            if text == "RISE":                                           # the one logged clash
                continue
            self.assertFalse([ln for ln in lines if cats.crosses(box, ln)], text)
            boxes.append((text, box))
        for i, (t1, b1) in enumerate(boxes):
            for t2, b2 in boxes[i + 1:]:
                self.assertFalse(cats.overlaps(b1, b2), (t1, t2))

    def test_one_empty_column_on_the_left(self):
        P = compact()
        self.assertEqual(min(c[0] for c in P.cells), 2)
        self.assertEqual(min(c[0] for c in P.labels), 2)

    def test_a_yards_parallel_tracks_are_named_in_one_column(self):
        runs = [(10, 20, 3, "S-1"), (11, 20, 4, "S-2"), (12, 19, 5, "S-3"), (0, 40, 2, "MAIN"), (30, 34, 4, "SPUR")]
        groups = [[r[3] for r in g] for g in cats.parallel_runs(runs)]
        self.assertEqual(groups, [["MAIN"], ["S-1", "S-2", "S-3"], ["SPUR"]])
        P = cats.Panel()
        P.pending = []
        for xa, xb, y, _ in runs[:3]:
            for x in range(xa, xb):
                P.cells[(x, y)]["HORIZONTAL"] = ("track", y)
        P.cells[(15, 3)]["UPPERSLASH"] = ("track", 9)        # in the way at the middle column of the first track
        P.label(list(range(12, 19)), [(y, t, []) for _, _, y, t in runs[:3]], rank=3)
        cats.place_labels(P)
        cols = {c[0] for c in P.labels}
        self.assertEqual(len(cols), 1, P.labels)
        self.assertNotIn(15, cols)

    def test_connector_labels_sit_at_their_stub_end_without_joined(self):
        P = compact()
        texts = {t: (cell, loc) for cell, (t, loc, _) in P.labels.items()}
        links = [t for t in texts if t.startswith(("A:", "HELIX"))]
        self.assertTrue(links)
        self.assertFalse([t for t in texts if "(JOINED)" in t])
        self.assertTrue(any("(JOINED)" in t for _, (t, _, _) in cats.panel(helpers.build().bands).labels.items()))

    def test_the_template_panels_colours_are_copied(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "desk.xml"
            src.write_text('<DOCUMENT><COLORDEFINITION COLORKEY="DARK" COLORNAME="Dark" COLORTAG="-1"/></DOCUMENT>')
            root = cats.to_xml(compact(), header=cats.header_from(str(src)))
        dark = [c.attrib for c in root.findall("COLORDEFINITION")]
        self.assertEqual(dark, [{"COLORKEY": "DARK", "COLORNAME": "Dark", "COLORTAG": "-1"}])

    def test_lone_tracks_above_one_another_are_named_in_one_column(self):
        runs = [(10, 40, 2, "MAIN WEST"), (18, 40, 8, "MAIN EAST"), (0, 9, 8, "SPUR"), (35, 60, 5, "SIDING")]
        groups = [[r[3] for r in g] for g in cats.stacked_runs(runs)]
        self.assertEqual(groups, [["MAIN WEST", "MAIN EAST"], ["SIDING"], ["SPUR"]])

    def test_one_slope_takes_a_widened_columns_extra_cell_at_a_bend_or_a_free_end(self):
        self.assertEqual(cats.stretched([(0, 0), (3, 0), (6, 2)]), [(0, 0), (3, 0), (4, 0), (6, 2)])
        self.assertEqual(cats.stretched([(0, 2), (3, 0), (6, 0)]), [(0, 2), (2, 0), (3, 0), (6, 0)])
        self.assertEqual(cats.stretched([(0, 0), (4, 2)]), [(0, 0), (1, 1), (3, 1), (4, 2)])
        self.assertIsNone(cats.stretched([(0, 0), (2, 1)]))                  # points to points, one row deep
        self.assertEqual(cats.stretched([(0, 0), (2, 1)], (True, False)), [(0, 0), (1, 0), (2, 1)])
        self.assertEqual(cats.stretched([(0, 0), (2, 1)], (False, True)), [(0, 0), (1, 1), (2, 1)])

    def test_an_orient_binding_on_a_wide_panel_keeps_the_usual_spot(self):
        P = cats.panel(helpers.build().bands, bindings={"masts": {"M12C": {"orient": "TOP"}}})
        (sg,) = P.signals.values()
        self.assertEqual((sg["orient"], sg["loc"]), ("TOP", cats.SIG_LOCATION["BOTTOM"]))

    def test_window_sizes_are_read_like_fits(self):
        self.assertEqual(cats.parse_window("1900x1100"), (1900, 1100))
        for bad in ("1900", "0x5", "1900x1100x3"):
            with self.assertRaisesRegex(cats.SchematicError, "--window is WIDTHxHEIGHT"):
                cats.parse_window(bad)

    def test_fit(self):
        P = compact()
        cols, rows = cats.shown(P)
        self.assertEqual(cats.check_fit(P, cols, rows), (cols, rows))
        with self.assertRaisesRegex(cats.SchematicError, rf"shows {cols} x {rows} cells.*1 columns and 0 rows over"):
            cats.check_fit(P, cols - 1, rows)
        self.assertEqual(cats.parse_fit("63x36"), (63, 36))
        for bad in ("63", "0x5", "axb"):
            with self.assertRaisesRegex(cats.SchematicError, "COLSxROWS"):
                cats.parse_fit(bad)
        for bad in (0, 3, True, 1.0):
            with self.assertRaisesRegex(cats.SchematicError, "1 or an even number of cells"):
                cats.panel(helpers.build().bands, scale=bad)

    def test_a_half_unit_point_is_an_error_at_one_cell_per_unit(self):
        with drawn_with({"e13": [(4, 3), (5.5, 3)]}):
            with self.assertRaisesRegex(cats.SchematicError, "point between cells at 1 cell"):
                cats.panel(helpers.build().bands, scale=1)
            cats.panel(helpers.build().bands)                   # whole cells at 2

    def test_a_slope_with_no_place_for_a_widened_cell_is_an_error_not_a_crash(self):
        bands = helpers.build().bands
        real = cats.widened_columns
        with mock.patch.object(cats, "stretched", lambda pts, free=(False, False): None), \
                mock.patch.object(cats, "widened_columns", lambda *a: real(*a) or {0: 1}):
            with self.assertRaisesRegex(cats.SchematicError, "no place for its extra cell"):
                cats.panel(bands, scale=1)

    def test_titles_and_end_labels_may_run_past_the_last_track_column(self):
        bands = [b for b in bands_copy() if b[0].startswith("Upper")]
        title, band, opts = bands[0]
        bands = [(title, band, dict(opts, left="Far away to the west", right="Far away to the east"))]
        P = cats.panel(bands, scale=1)
        last = max(c[0] for c in P.cells)
        texts = {t: (cell, cats.text_box(cell, loc, t, f)) for cell, (t, loc, f) in P.labels.items()}
        heading = next(t for t in texts if t.startswith("UPPER LEVEL"))
        end = next(t for t in texts if t.startswith("A: TO"))
        self.assertGreater(texts[heading][1][2], (last + 1) * cats.GRID_PX)     # the title is kept, spilling
        self.assertEqual(texts[end][0][0], last + 1)                            # beside the east end
        self.assertGreaterEqual(cats.shown(P)[0], math.ceil(max(b[2] for _, b in texts.values()) / cats.GRID_PX) - 1)
        self.assertFalse([line for line in P.log if "no room" in line], P.log)
        self.assertIn("label 'RISE' at", " ".join(P.log))          # placed past the end, logged, not dropped

    def test_command(self):
        f = helpers.data_with_signals()
        with tempfile.TemporaryDirectory() as tmp:
            import json
            graph = Path(tmp) / "graph.json"
            graph.write_text(json.dumps(helpers.graph()))
            out = Path(tmp) / "panel.xml"
            run = lambda *extra: subprocess.run([sys.executable, "-m", "schematic", "cats", str(out), "--data", str(f),
                                                 f"{graph}:example", "--cells-per-unit", "1", *extra],
                                                cwd=helpers.PLUGIN, capture_output=True, text=True, timeout=120)
            r = run("--fit", "63x36")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r"shows \d+ x \d+ cells \(fit 63 x 36\)")
            r = run("--fit", "10x10")
            self.assertEqual(r.returncode, 2)
            self.assertIn("more than the 10 x 10", r.stderr)


if __name__ == "__main__":
    unittest.main()
