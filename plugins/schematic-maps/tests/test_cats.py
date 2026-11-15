"""The CATS panel seeded from the example's solved bands: track on whole cells, switch points, blocks, joins, XML."""
import copy
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path
from unittest import mock

import helpers
from schematic import cats
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
                if blk is not None and blk.get("NAME"):
                    self.assertNotIn(blk.get("NAME"), names)
                    names.add(blk.get("NAME"))
            self.assertEqual(len(sec.findall("SEC_NAME")), len(set(x.get("NAME") for x in sec.findall("SEC_NAME"))))
        self.assertEqual(names, set(P.names.values()))
        self.assertEqual(len(list(root.iter("IOSPEC"))), 0)           # no bindings in a generic panel
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


if __name__ == "__main__":
    unittest.main()
