"""Rules R5 to R7, the checks, labels and the golden fingerprints, on the made-up example."""
import json
import os
import math
import unittest

import helpers
from schematic import fingerprint, label_check, labels, metrics, report, rules


class Checks(unittest.TestCase):
    """Specification, "Checks run every time", on the baseline (layers 1 and 2 only) and the full drawing."""

    def test_no_faults_in_either_drawing(self):
        for prefs in (False, True):
            res = report.run(helpers.build(prefs))
            for title, f in res.items():
                self.assertEqual((f["faults"], f["main"], f["ladder"], f["coverage"]), ([], [], [], []), (prefs, title))

    def test_labels_are_clear_of_everything(self):
        for prefs in (False, True):
            faults, n = label_check.check(helpers.build(prefs).svg())
            self.assertGreater(n, 30)
            self.assertEqual(faults, [], faults)

    def test_two_levels_joined_by_one_lettered_connector(self):
        fp = fingerprint.of(helpers.build())
        self.assertEqual(set(fp), {"Lower level", "Upper level"})
        for title, other in (("Lower level", "Upper level"), ("Upper level", "Lower level")):
            self.assertEqual(fp[title]["connectors"]["A"]["to"], other)

    def test_helix_track_has_the_same_name_on_both_levels(self):
        for title, b, _ in helpers.build().bands:
            self.assertTrue(any(s["name"] == "Summit" for s in b["strands"].values()), title)


class Rules(unittest.TestCase):
    def band(self, title):
        return next(b for t, b, _ in helpers.build(False).bands if t == title)

    def legs(self, band, label):
        n = next(n for n, d in band["nodes"].items() if d["label"] == label and d["kind"] == "switch")
        return {p: sloped for p, (sid, sloped) in report.leg_rows(band)[n].items()}

    def test_r5_main_runs_level_through_switches_on_it(self):
        lower = self.band("Lower level")
        for sw, leg in (("1", "B"), ("2", "B"), ("3", "B"), ("8", "B"), ("4", "B")):
            self.assertFalse(self.legs(lower, sw)[leg], f"switch {sw} leg {leg}")
        self.assertFalse(self.legs(self.band("Upper level"), "21")["B"])

    def test_rules_are_weighted_preferences_and_a_hand_pin_wins(self):
        from schematic.rows import Rows
        lower = self.band("Lower level")
        nodes, strands = lower["nodes"], lower["strands"]
        soft = rules.level_legs(nodes, strands, {})
        n, leg = next(iter(soft.items()))
        other = "C" if leg == "B" else "B"
        rows = Rows(nodes, strands, [], rule_pins=soft)
        rows.rule_weight = 2.5
        self.assertEqual(rows.broken(), 2.5 * sum(rows.flat[k] != v for k, v in soft.items()))
        rows.flat.update(soft)
        self.assertEqual(rows.broken(), 0)
        rows.flat[n] = other
        self.assertEqual(rows.broken(), 2.5)
        label = nodes[n].get("alias") or nodes[n]["label"]
        pinned = Rows(nodes, strands, [], pins={label: other}, rule_pins=soft)
        pinned.flat.update(soft)
        pinned.flat[n] = other
        self.assertEqual(pinned.broken(), 0)      # a hand pin is not a broken rule
        self.assertEqual(pinned.optimise()["cost"] is not None and pinned.flat[n], other)

    def test_r5_pins_come_from_the_track_alone(self):
        lower = self.band("Lower level")
        pins = rules.main_pins(lower["nodes"], lower["strands"])
        self.assertEqual({lower["nodes"][n]["label"]: p for n, p in pins.items()}.get("2"), "B")

    def test_r5_loop_entry_has_no_pin(self):
        lower = self.band("Lower level")
        pins = {lower["nodes"][n]["label"] for n in rules.main_pins(lower["nodes"], lower["strands"])}
        self.assertNotIn("5", pins)          # main on both legs of the loop switch

    def test_r6_ladder_yard_tracks_level_and_links_slope(self):
        lower = self.band("Lower level")
        ladder = {lower["nodes"][n]["label"]: leg for n, leg in rules.ladder_switches(lower).items()}
        self.assertEqual(ladder, {"11": "B", "12": "B"})
        for sw in ("11", "12"):
            legs = self.legs(lower, sw)
            self.assertFalse(legs["B"])
            self.assertTrue(legs["C"])

    def test_r6_threshold_is_a_setting_not_a_hint(self):
        lower = self.band("Lower level")
        self.assertEqual(rules.ladder_switches(lower, {"ladder_link_max_cm": 10}), {})

    def test_r7_second_pass_is_never_worse_than_the_first(self):
        """Rows are kept apart only for runs that overlap; the result is kept only if it uses no more room."""
        from schematic import sheet
        sizes = {}
        for flag in (False, True):
            o = sheet.options("example", helpers.data_with_signals(), False)
            o["rule_rows"] = flag
            o["helix_style"] = "box"
            bands = sheet.build_bands([(helpers.graph(), "example")], [o], [])
            sizes[flag] = {t: tuple(fingerprint.band(t, b)["size"][::-1]) for t, b, _ in bands}   # (rows, columns)
        for title in sizes[False]:
            self.assertLessEqual(sizes[True][title], sizes[False][title])

    def test_r10_no_trial_for_a_missing_hand(self):
        from schematic import edits
        from schematic.core import SchematicError
        with self.assertRaises(SchematicError):
            edits.apply_edits(helpers.graph() and json.loads(json.dumps(helpers.graph())),
                              [{"op": "switch", "label": "9", "on": ["3", "4"], "cm_from_first": 10, "points_toward": "4",
                                "c": {"end": "X"}, "source": "owner"}])


class Labels(unittest.TestCase):
    def test_bundled_font_table_gives_stable_widths(self):
        self.assertAlmostEqual(metrics.text_width("T196", 8, "bold"), 18.232, places=3)
        self.assertAlmostEqual(metrics.text_width("MAIN WEST", 8.5, "normal", 0.4), 5.537 * 8.5 + 3.2, places=3)
        self.assertGreater(metrics.text_width("é", 10), 0)         # outside ASCII: a fallback width, no error

    def test_check_applies_rotation_and_scale(self):
        svg = ('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0,0 L100,0" stroke-width="2"/>'
               '<g transform="rotate(90 0 0)"><text x="50" y="0" font-size="10">AB</text></g>'
               '<g transform="translate(0,40) scale(2)"><text x="5" y="0" font-size="5">CD</text></g></svg>')
        faults, n = label_check.check(svg)
        self.assertEqual(n, 2)
        # rotated 90 degrees, the first text lies along the y axis from (0,50), well clear of the line at y=0
        # beyond its end: no fault; the scaled one sits at y=40, also clear
        self.assertEqual(faults, [])
        crossing = svg.replace('x="50" y="0"', 'x="-5" y="0"')
        faults, _ = label_check.check(crossing)
        self.assertEqual([f[0] for f in faults], ["track"])

    def test_placer_takes_first_free_position_and_reports_when_none(self):
        p = labels.Placer()
        p.line((0, 0), (100, 0), 2)
        p.ask("t", "AB", 8, [(20, 0, "middle"), (20, -10, "middle")])
        p.ask("t", "CD", 8, [(20, 0, "middle")])
        out = {a["s"]: xy for a, xy in p.solve()}
        self.assertEqual(out["AB"], (20, -10, "middle"))
        self.assertEqual(p.unplaced, ["t CD"])

    def test_placer_places_the_hardest_label_first(self):
        p = labels.Placer()
        p.ask("t", "EASY", 8, [(0, 0, "middle"), (0, 20, "middle")])
        p.ask("t", "HARD", 8, [(0, 0, "middle")])
        out = {a["s"]: xy for a, xy in p.solve()}
        self.assertEqual(out["HARD"], (0, 0, "middle"))
        self.assertEqual(out["EASY"], (0, 20, "middle"))
        self.assertEqual(p.unplaced, [])


class EndRules(unittest.TestCase):
    """Layer 1 facts about a level's ends decide the orientation before the fault count does."""

    def bands(self, **over):
        from schematic import sheet
        o = sheet.options("example", helpers.data_with_signals(), False)
        o.update(over)
        o["helix_style"] = "box"
        return {t: b for t, b, _ in sheet.build_bands([(helpers.graph(), "example")], [o], [])}

    def end_x(self, band, pred):
        xs = [x for n, x in band["x"].items() if band["nodes"][n]["kind"] == "end" and pred(band["nodes"][n], n, band)]
        mid = (min(band["x"].values()) + max(band["x"].values())) / 2
        return [x - mid for x in xs]

    def test_an_east_helix_comes_out_on_the_right_and_a_west_helix_on_the_left(self):
        for side, sign in (("east", 1), ("west", -1)):
            for title, b in self.bands(helix_side=side).items():
                xs = self.end_x(b, lambda d, n, band: d.get("sub") == "helix")
                self.assertTrue(xs and all(sign * x > 0 for x in xs), (side, title, xs))

    def test_a_stub_declared_west_ends_leftmost_and_points_left(self):
        """The two yard stubs Y-3 and Y-4 hang off switch 13 and run east on the plan. Declared west, Y-3 must
        be the leftmost end of its band with its track running leftward from its switch."""
        b = self.bands(left_end="Y-3", helix={}, helix_side=None, main_route=[["21", "22", "direct"]])["Lower level"]
        node = next(n for e in b["strands"].values() for n in (e["src"][0], e["dst"][0])
                    if b["nodes"][n]["kind"] == "end" and e["name"] == "Y-3")
        ends = [b["x"][n] for n, d in b["nodes"].items() if d["kind"] == "end"]
        self.assertEqual(b["x"][node], min(ends))
        self.assertTrue(b["nodes"][node]["outs"], "the stub must run leftward from its switch")

    def test_a_level_leg_preference_pins_the_owners_choice_over_the_rule(self):
        """Layer 3 `level_leg` names the leg a switch keeps level, where the rules chose the other valid one."""
        from schematic import sheet
        o = sheet.options("example", helpers.data_with_signals(), False)
        o["helix_style"] = "box"
        o["level_leg"] = {"11": "C"}                  # R6 would keep the yard track (B) level
        bands = {t: b for t, b, _ in sheet.build_bands([(helpers.graph(), "example")], [o], [])}
        fp = fingerprint.band("Lower level", bands["Lower level"])
        self.assertEqual(fp["switches"]["11"]["level_leg"], "C")

    def test_a_declared_west_end_comes_out_on_the_left(self):
        for name in ("Siding", "Spur"):
            b = self.bands(left_end=name, helix={}, helix_side=None, main_route=[["21", "22", "direct"]])["Upper level"]
            node = next(n for e in b["strands"].values() for n in (e["src"][0], e["dst"][0])
                        if b["nodes"][n]["kind"] == "end" and name in e["name"])
            self.assertLess(b["x"][node], (min(b["x"].values()) + max(b["x"].values())) / 2, name)


class Golden(unittest.TestCase):
    """Fingerprints compared switch by switch. Set UPDATE_GOLDEN=1 to rewrite them after a change you meant."""

    def compare(self, name, prefs):
        actual = fingerprint.of(helpers.build(prefs))
        path = helpers.GOLDEN / name
        if os.environ.get("UPDATE_GOLDEN"):
            path.write_text(json.dumps(actual, indent=1, sort_keys=True) + "\n")
        golden = json.loads(path.read_text())
        actual = json.loads(json.dumps(actual))
        diff = fingerprint.diff(golden, actual)
        self.assertEqual(diff, [], "\n" + "\n".join(diff))

    def test_baseline_layers_one_and_two(self):
        self.compare("baseline.json", False)

    def test_approved_layers_one_two_and_three(self):
        self.compare("approved.json", True)

    def test_diff_names_the_switch(self):
        a = {"B": dict(title="B", switches={"5": dict(col=3, row=1)}, tracks={}, connectors={}, size=[1, 1])}
        b = {"B": dict(title="B", switches={"5": dict(col=4, row=1), "6": dict(col=1, row=1)}, tracks={}, connectors={}, size=[1, 1])}
        self.assertEqual(fingerprint.diff(a, b), ["B: switch 5: col 3 -> 4", "B: switch 6 is new"])

    def test_every_switch_and_track_is_fingerprinted(self):
        fp = fingerprint.of(helpers.build(False))["Lower level"]
        for key in ("1", "2", "3", "4", "5", "8", "11", "12", "13", "6"):
            self.assertIn(key, fp["switches"], key)
        self.assertIn("1.B-2.A", fp["tracks"])
        self.assertEqual(fp["switches"]["11"]["level_leg"], "B")




class GridRoom(unittest.TestCase):
    """R12, layout part: a label with no free position claims grid room on its track."""

    def test_unplaced_label_names_its_strand(self):
        P = labels.Placer()
        P.line((0, 0), (100, 0), 2)
        P.ask("track", "LONG NAME", 9, [(50, 3, "middle")], room=("e7",))
        P.ask("switch", "4", 9, [(50, -30, "middle")], room=("e8",))
        P.solve()
        self.assertEqual(P.short, {"e7"})

    def test_claimed_room_widens_the_run(self):
        from schematic import columns
        band = next(b for t, b, _ in helpers.build(False).bands if t == "Lower level")
        sid = next(k for k, s in band["strands"].items() if k not in band["R"]["diag"] and s["name"])
        opts = {k: v for k, v in helpers.build(False).bands[0][2].items() if k != "_room"}
        edge = band["strands"][sid]["edge"]
        _, need = columns.place(band["nodes"], band["strands"], band["R"], {}, opts)
        _, wider = columns.place(band["nodes"], band["strands"], band["R"], {}, dict(opts, _room={edge: 2}))
        self.assertEqual(wider[sid][2], need[sid][2] + 2)

    def test_sheet_lays_out_again_until_labels_fit(self):
        """With names reserving no width, labels only fit if the sheet's room rounds lengthen their tracks."""
        from unittest import mock
        from schematic import columns, sheet
        build = lambda: sheet.build([(helpers.graph(), "example")], helpers.data_with_signals(), preferences=False)
        with mock.patch.object(columns, "name_cells", lambda name, opts: 0):
            with mock.patch.object(sheet, "ROOM_ROUNDS", 0):
                before = len(label_check.check(build().svg())[0])
            grown = build()
            after = len(label_check.check(grown.svg())[0])
        self.assertGreater(before, 2)
        self.assertLess(after, before / 2)
        self.assertTrue(any(line.startswith("R12 round 1") for line in grown.log), grown.log)


class TitleBlock(unittest.TestCase):
    def test_fields(self):
        from schematic import draw
        self.assertEqual(draw.title_fields({"date": "2026-11-14", "revision": 1, "sheet": "1 of 1"}),
                         ["NOV 14, 2026", "REV 1", "SHEET 1 OF 1"])
        self.assertEqual(draw.title_fields({"revision": 0}), ["REV 0"])
        self.assertEqual(draw.title_fields({}), [])

    def test_column_only_when_set(self):
        import re
        from schematic import draw
        s = helpers.build()
        opts = dict(s.opts, title=s.opts.get("system_title", s.opts["title"]))     # as sheet.py passes it
        plain = draw.page_svg(s.bands, opts)
        self.assertEqual(len(re.findall(r'<rect x="[\d.]+" y="728" ', plain)), 1)    # title box only: no empty column
        svg = draw.page_svg(s.bands, dict(opts, date="2026-01-05", revision=3))
        self.assertIn(">JAN 5, 2026<", svg)
        self.assertIn(">REV 3<", svg)
        self.assertNotIn("SHEET", svg)
        self.assertEqual(len(re.findall(r'<rect x="[\d.]+" y="728" ', svg)), 2)

    def test_bad_date_is_named(self):
        from schematic import draw
        from schematic.core import SchematicError
        for bad in ("2026-13-01", "2026-00-01", "2026-02-31", "14 Nov 2026"):
            with self.assertRaisesRegex(SchematicError, "YYYY-MM-DD"):
                draw.title_fields({"date": bad})

    def test_long_values_widen_the_box(self):
        from schematic import draw
        import re
        s = helpers.build()
        svg = draw.page_svg(s.bands, dict(s.opts, title=["A very long railroad name for testing overflow of the box"],
                                          sheet="Detail 3 of 12"))
        rects = re.findall(r'<rect x="([\d.]+)" y="[\d.]+" width="([\d.]+)" height="64"', svg)
        (tx, tw), (cx, cw) = [(float(a), float(b)) for a, b in rects]
        self.assertGreater(tw, 330)
        self.assertEqual(cx, tx + tw)
        self.assertGreater(cw, 104)


class Direction(unittest.TestCase):
    """East along the main route, and R or L for each switch by which way its points face."""

    def graph(self):
        # west end - s1 (points west) - s2 (points east, a trailing switch for eastward trains) - east end;
        # s1's diverging leg is a siding that rejoins at s2; crossover halves x1/x2 share one number
        sw = lambda label: dict(kind="switch", label=label)
        N = {"w": dict(kind="end"), "e": dict(kind="end"), "s1": sw("1"), "s2": sw("2"),
             "x1": sw("9"), "x2": sw("9"), "t": dict(kind="end"), "u": dict(kind="end")}
        E = [("w", "E", "s1", "A", True), ("s1", "B", "s2", "B", True), ("s1", "C", "s2", "C", False),
             ("s2", "A", "x1", "A", True), ("x1", "B", "e", "E", True), ("x1", "C", "x2", "C", False),
             ("x2", "A", "t", "E", False), ("x2", "B", "u", "E", False)]
        edges = [dict(u=u, up=up, v=v, vp=vp, cm=50.0, main=m, id=f"e{i}") for i, (u, up, v, vp, m) in enumerate(E)]
        return dict(nodes=N, edges=edges)

    def test_letters_follow_the_route(self):
        from schematic import direction
        g = self.graph()
        rail, conflicts = direction.east(g, [["1", "2"]], lambda r: {"1": "s1", "2": "s2"}[r])
        self.assertEqual(conflicts, [])
        self.assertEqual(direction.letters(g["nodes"], rail), {"s1": "R", "s2": "L"})   # crossover 9: no letter

    def test_route_order_sets_east(self):
        from schematic import direction
        g = self.graph()
        rail, _ = direction.east(g, [["2", "1"]], lambda r: {"1": "s1", "2": "s2"}[r])    # listed the other way
        self.assertEqual(direction.letters(g["nodes"], rail), {"s1": "L", "s2": "R"})

    def test_direct_pair_follows_its_own_track(self):
        """A loop listed as a direct pair seeds along the loop, not the shorter way back round."""
        from schematic import direction
        sw = lambda label: dict(kind="switch", label=label)
        N = {"p": sw("1"), "q": sw("2"), "x": sw("3"), "e": dict(kind="end")}
        E = [("p", "B", "q", "C", 500.0), ("p", "A", "x", "B", 10.0), ("x", "A", "q", "A", 10.0), ("x", "C", "e", "E", 5.0)]
        g = dict(nodes=N, edges=[dict(u=u, up=up, v=v, vp=vp, cm=cm, main=True, id=f"e{i}")
                                 for i, (u, up, v, vp, cm) in enumerate(E)])
        ref = {"1": "p", "2": "q"}.get
        loop, _ = direction.east(g, [["1", "2", "direct"]], ref)
        self.assertEqual((loop["p"], loop["q"]), (1, -1))       # leaves p by B, arrives at q by C
        short, _ = direction.east(g, [["1", "2"]], ref)
        self.assertEqual((short["p"], short["q"]), (-1, 1))     # the short way: out of p by A, into q by A

    def test_arrows_only_where_east_runs_left(self):
        from schematic import direction
        from schematic.layout import paths
        for title, band, _ in helpers.build().bands:
            right = direction.drawn(band, False)
            self.assertEqual(direction.main_runs(dict(band, rail=right), paths(band)), [], title)
            left = {n: -v for n, v in right.items()}
            runs = direction.main_runs(dict(band, rail=left), paths(band))
            self.assertTrue(runs and not any(r[3] for r in runs), title)

    def test_sheet_letters_every_single_switch(self):
        import json
        import tempfile
        from pathlib import Path
        from schematic import sheet
        f = helpers.folder()
        with tempfile.TemporaryDirectory() as tmp:
            for p in f.iterdir():
                if p.name.startswith("example."):
                    (Path(tmp) / p.name).write_text(p.read_text())
            prefs = Path(tmp) / "example.preferences.json"
            o = json.loads(prefs.read_text())
            o["facing_letters"] = o["direction_arrows"] = True
            prefs.write_text(json.dumps(o))
            built = sheet.build([(helpers.graph(), "example")], tmp)
        for title, band, _ in built.bands:
            counts = {}
            for d in band["nodes"].values():
                if d.get("kind") == "switch":
                    counts[d["label"]] = counts.get(d["label"], 0) + 1
            for d in band["nodes"].values():
                if d.get("kind") == "switch":
                    self.assertEqual("facing" in d, counts[d["label"]] == 1, (title, d["label"]))
                    self.assertIn(d.get("facing", "R"), ("R", "L"))


def build_with(prefs=(), overrides=()):
    """The example drawn with extra preference and override keys, from a copy of its layer files."""
    import json
    import tempfile
    from pathlib import Path
    from schematic import sheet
    f = helpers.data_with_signals()
    with tempfile.TemporaryDirectory() as tmp:
        for p in f.iterdir():
            if p.name.startswith("example."):
                (Path(tmp) / p.name).write_text(p.read_text())
        for name, extra in (("preferences", dict(prefs)), ("plan_overrides", dict(overrides))):
            path = Path(tmp) / f"example.{name}.json"
            path.write_text(json.dumps(dict(json.loads(path.read_text()), **extra)))
        return sheet.build([(helpers.graph(), "example")], tmp)


class BandDirections(unittest.TestCase):
    """A legend per band (normal, reversed, one way or none), arrows per track, and bands spaced by their labels."""

    def test_page_legend_stays_when_no_band_declares_one(self):
        svg = helpers.build().svg()
        self.assertIn('y="62" font-size="15"', svg)
        self.assertNotIn("\u2190 EAST", svg)

    def test_band_legends_replace_the_page_legend(self):
        svg = build_with({"band_legend": {"Upper": "reversed", "Lower": {"west": "left", "show": "west"}}}).svg()
        self.assertNotIn('y="62" font-size="15"', svg)
        self.assertIn(">\u2190 EAST<", svg)          # reversed: east to the left, west to the right
        self.assertIn(">WEST \u2192<", svg)
        self.assertIn(">\u2190 WEST<", svg)          # the lower band's one arrow, pointing west
        self.assertNotIn(">EAST \u2192<", svg)
        faults, _ = label_check.check(svg)
        self.assertEqual(faults, [])

    def test_undeclared_band_is_normal_and_none_draws_nothing(self):
        from schematic import draw
        self.assertEqual(draw.band_legend({"band_legend": {}, "_band_legends": True}, "Lower level"), ("left", "both"))
        self.assertIsNone(draw.band_legend({"band_legend": {"Lower": "none"}, "_band_legends": True}, "Lower level"))
        self.assertIsNone(draw.band_legend({}, "Lower level"))
        texts = [t for t, _ in draw.legend_texts({"left": "West", "right": "East"}, "right", "both")]
        self.assertEqual(texts, ["\u2190 EAST", "WEST \u2192"])

    def test_bad_legend_is_named(self):
        from schematic import draw
        from schematic.core import SchematicError
        for bad in ("sideways", {"west": "up"}, {"show": "north"}, ["left"]):
            with self.assertRaisesRegex(SchematicError, "band_legend for Lower"):
                draw.band_legend({"band_legend": {"Lower": bad}}, "Lower level")

    def test_track_way_on_whole_fold_and_cut_strands(self):
        from schematic import draw
        s = lambda src, dst, way: dict(src=(src, "A"), dst=(dst, "B"), way=way)
        self.assertTrue(draw.track_way(s("a", "b", ("a", "b"))))
        self.assertFalse(draw.track_way(s("a", "b", ("b", "a"))))
        self.assertTrue(draw.track_way(s("a", "turn:e", ("a", "b"))))       # fold half holding the from end
        self.assertFalse(draw.track_way(s("b", "turn:e", ("a", "b"))))      # the half holding the to end
        self.assertFalse(draw.track_way(s("LINK:A1", "b", ("b", "a"))))     # cut at a level: leaves b leftward
        self.assertIsNone(draw.track_way(s("a", "b", "both")))
        self.assertIsNone(draw.track_way(s("a", "b", None)))

    def test_declared_ways_draw_arrows_that_point_the_way(self):
        import re
        from schematic import draw
        built = build_with(overrides={"track_directions": [["11", "1"], ["21", "22", "both"]]})
        lower = next(b for t, b, _ in built.bands if t == "Lower level")
        lead = next(s for s in lower["strands"].values() if s["name"] == "Yard Lead")
        frm, to = lead["way"]                           # from 11 toward 1: the arrow points at 1 as drawn
        self.assertEqual(draw.track_way(lead), lower["x"][to] > lower["x"][frm])
        svg = built.svg()
        arrows = re.findall(r'<path d="M([\d.]+),([\d.]+) L([\d.]+),[\d.]+((?: M[^"]*)?)" stroke-width="1.3"/>', svg)
        self.assertEqual(len(arrows), 2)
        heads = sorted(len(a[3].split("M")) - 1 for a in arrows)
        self.assertEqual(heads, [1, 2])                 # one way: one head; both ways: two
        self.assertEqual(label_check.check(svg)[0], [])
        from schematic.core import SchematicError
        with self.assertRaisesRegex(SchematicError, "track_directions"):
            build_with(overrides={"track_directions": [["11", "1", "sideways"]]})

    def test_main_arrows_cover_every_main_track_once_per_straight_run(self):
        import re
        from schematic import draw
        from schematic.layout import paths
        built = build_with({"track_arrows": {"Lower": "main"}})
        lower = next(b for t, b, _ in built.bands if t == "Lower level")
        runs = draw.track_runs(lower, paths(lower), "main")
        self.assertTrue(runs and all(r[3] is None for r in runs))      # no declared way: both ways
        mains = {k for k, s in lower["strands"].items() if s["main"]}
        self.assertTrue(set(k for r in runs for k in r[4]) <= mains)
        self.assertTrue(any(len(r[4]) > 1 for r in runs))             # a straight line through switches: one arrow
        self.assertEqual(len(re.findall('stroke-width="1.3"', built.svg())), len(runs))

    def test_band_gap_measures_to_the_lowest_label(self):
        import re
        from schematic import draw
        s = helpers.build()
        title, band, o = s.bands[0]
        _, _, plain = draw.draw_band(band, title, o, 0, 0)
        part, _, measured = draw.draw_band(band, title, dict(o, band_gap=20), 0, 0)
        lowest = max(float(y) for y in re.findall(r'<text x="[\d.]+" y="([\d.]+)"', "".join(part)))
        self.assertGreaterEqual(measured, lowest)
        self.assertGreaterEqual(measured, plain)
        svg = draw.page_svg(s.bands, dict(s.opts, title=s.opts["system_title"], band_gap=20))
        self.assertEqual(label_check.check(svg)[0], [])


class RunHints(unittest.TestCase):
    def bands(self):
        sw = lambda label: dict(kind="switch", label=label)
        nodes = {"p": sw("1"), "q": sw("2"), "r": sw("7*")}
        st = lambda ends, edge, name, cm: dict(ends=ends, src=(ends[0], "B"), dst=(ends[1], "A"), edge=edge, name=name, cm=cm)
        one = dict(nodes=nodes, strands={"e0": st(("p", "q"), "e0", "Main", 100.0), "e1": st(("q", "p"), "e1", "Siding", 90.0),
                                         "e2": st(("p", "q"), "e2", "", 40.0), "e3": st(("q", "r"), "e3", "S-3 / Lead", 60.0)})
        other = dict(nodes={"z": sw("9")}, strands={})          # a second band that holds none of these switches
        return [one, other]

    def check(self, **opts):
        from schematic.columns import check_run_hints
        check_run_hints(self.bands(), opts)

    def test_hints(self):
        from schematic.core import SchematicError
        with self.assertRaisesRegex(SchematicError, "reaches 3 tracks"):
            self.check(min_cells=[["1", "2", 3]])
        self.check(min_cells=[["1", "2", 3, "Main", "siding"]])          # the tracks it is for, in any band
        self.check(shorten=[["2", "7", "S-3"]])                           # a moved switch, one part of a joined name
        with self.assertRaisesRegex(SchematicError, "lists YARD"):
            self.check(shorten=[["1", "2", "Yard"]])
        with self.assertRaisesRegex(SchematicError, "reaches no track"):
            self.check(min_cells=[["1", "50", 4]])
        with self.assertRaisesRegex(SchematicError, "lists 5"):                # a number in the list: an error, not a crash
            self.check(min_cells=[["1", "2", 4, 5]])


class Capacity(unittest.TestCase):
    def band(self):
        sw = lambda label: dict(kind="switch", label=label)
        nodes = {"p": sw("1"), "q": sw("2"), "r": sw("3"), "a": dict(kind="end"), "b": dict(kind="end"), "c": dict(kind="end"),
                 "t": dict(kind="turnR")}
        st = lambda src, dst, edge, name, cm, main=False: dict(src=(src, "B"), dst=(dst, "A"), edge=edge, name=name, cm=cm,
                                                              main=main, link=False)
        strands = {"m": st("p", "q", "m", "Main", 500.0, True),
                   "y1": st("a", "q", "y1", "", 100.0), "y2": st("q", "r", "y2", "", 60.0),    # one unnamed track, two pieces
                   "s": st("p", "b", "s", "S-1", 300.0),                                        # named, measured
                   "l": st("r", "c", "l", "", 30.0),                                             # a short link
                   "k.0": st("p", "t", "k", "K-1", 600.0), "k.1": st("t", "r", "k", "K-2", 600.0)}   # a loop drawn as two
        srow = {"m": 0, "y1": 1, "y2": 1, "s": 2, "l": 3, "k.0": 4, "k.1": 5}
        return dict(nodes=nodes, strands=strands, R=dict(srow=srow, diag=set()))

    def test_counts(self):
        from schematic import capacity
        opts = {"capacity": {"car_in": 7.4}, "track_lengths_in": {"S-1": 74.0}}
        c = capacity.counts(self.band(), opts)
        self.assertEqual(c, {"y1": math.floor(160 / 2.54 / 7.4), "s": 10,
                             "k.0": math.floor(300 / 2.54 / 7.4), "k.1": math.floor(300 / 2.54 / 7.4)})
        self.assertEqual(capacity.counts(self.band(), {}), {})

    def test_station_totals_go_to_the_west_end(self):
        from schematic import capacity
        band = self.band()
        x = {"p": 0, "q": 5, "r": 9, "a": 1, "b": 12}
        opts = {"capacity": {}, "track_lengths_in": {"S-1": 74.0}, "stations": {"West": ["1", "2"], "East": ["3"]}}
        loop, yard = math.floor(300 / 2.54 / 7.4), math.floor(160 / 2.54 / 7.4)
        # S-1 and K-1 end at switch 1; the unnamed track spans switches 2 and 3; K-2 ends at switch 3
        self.assertEqual(capacity.station_totals(band, opts, x), {"West": 10 + loop + yard, "East": loop})
        turned = capacity.station_totals(band, opts, x, turned=True)          # turned end for end: west is right
        self.assertEqual(turned, {"West": 10 + loop, "East": loop + yard})

    def test_pieces_of_a_named_track_count_once(self):
        from schematic import capacity
        band = self.band()
        band["strands"]["s2"] = dict(band["strands"]["s"], src=("b", "B"), dst=("r", "A"), edge="s2")
        band["R"]["srow"]["s2"] = 2
        c = capacity.counts(band, {"capacity": True, "track_lengths_in": {"S-1": 74.0}})
        self.assertEqual(sorted(v for k, v in c.items() if k in ("s", "s2")), [10])

    def test_bad_car_length_is_named(self):
        from schematic import capacity
        from schematic.core import SchematicError
        for bad in (0, -3, "7", True):
            with self.assertRaisesRegex(SchematicError, "car_in"):
                capacity.counts(self.band(), {"capacity": {"car_in": bad}})
        self.assertEqual(capacity.measured_length({"S-4": 120.0}, "S-4 / S-5"), 120.0)


class BandFixes(unittest.TestCase):
    def test_band_key_of_an_untitled_band(self):
        from schematic.draw import band_key
        self.assertEqual((band_key(None), band_key(""), band_key("  "), band_key("Upper level")), ("", "", "", "Upper"))

    def test_turned_band_defaults_to_reversed(self):
        from schematic.draw import band_legend
        o = {"_band_legends": True, "rotate_bands": ["Upper"]}
        self.assertEqual(band_legend(o, "Upper level"), band_legend({"band_legend": {"Upper": "reversed"}}, "Upper level"))
        self.assertEqual(band_legend(o, "Lower level"), band_legend({"band_legend": {"Lower": "normal"}}, "Lower level"))

    def test_unknown_band_in_settings_stops(self):
        from schematic import draw
        from schematic.core import SchematicError
        s = helpers.build()
        with self.assertRaisesRegex(SchematicError, "not a band"):
            draw.page_svg(s.bands, dict(s.opts, title=["x"], band_legend={"upper": "reversed"}))
        with self.assertRaisesRegex(SchematicError, "rotate_bands names Uper"):
            draw.page_svg(s.bands, dict(s.opts, title=["x"], rotate_bands=["Uper"]))

    def test_parallel_tracks_in_track_directions_stop(self):
        from schematic import sheet
        from schematic.core import SchematicError
        sw = lambda label: dict(kind="switch", label=label)
        g = dict(nodes={"p": sw("1"), "q": sw("2")},
                 edges=[dict(u="p", up="B", v="q", vp="A", cm=50.0, id="e0"), dict(u="p", up="C", v="q", vp="B", cm=60.0, id="e1")])
        with self.assertRaisesRegex(SchematicError, "2 tracks join"):
            sheet.mark_ways(g, [["1", "2"]])
        sheet.mark_ways(g, [["1", "2", "C"]])                  # the leg picks the track
        self.assertEqual([e.get("way") for e in g["edges"]], [None, ("p", "q")])
        sheet.mark_ways(g, [["1", "2", "both", "B"]])
        self.assertEqual(g["edges"][0]["way"], "both")

    def test_parallel_tracks_in_edits_stop(self):
        from schematic import edits
        from schematic.core import SchematicError

        def graph():
            sw = lambda label: dict(kind="switch", label=label, alias=label, hand=1, dirs={})
            return dict(nodes={"p": sw("1"), "q": sw("2")},
                        edges=[dict(u="p", up="B", v="q", vp="A", cm=50.0, id="e0", names=[], main=False),
                               dict(u="p", up="C", v="q", vp="B", cm=60.0, id="e1", names=[], main=False)])
        new = dict(op="switch", label="9", hand="R", source="owner", cm_from_first=20, points_toward="1",
                   c={"end": "Spur"})
        with self.assertRaisesRegex(SchematicError, "2 tracks join 1 and 2"):
            edits.apply_edits(graph(), [dict(new, on=["1", "2"])])
        g = graph()
        edits.apply_edits(g, [dict(new, on=["1", "2"], port="C")])      # the leg picks the longer one
        self.assertIn("e1a", {e["id"] for e in g["edges"]})
        g = graph()
        edits.apply_edits(g, [dict(new, on=["1", "2"], port="B")])      # or the shorter one
        self.assertIn("e0a", {e["id"] for e in g["edges"]})
        with self.assertRaisesRegex(SchematicError, "2 tracks join 1 and 2"):
            edits.apply_edits(graph(), [dict(op="crossover", label="9", hand="R", source="owner",
                                             sides=[dict(on=["1", "2"], cm_from_first=20, points_toward="1"),
                                                    dict(on=["1", "2"], port="C", cm_from_first=20, points_toward="1")])])
        g = graph()                                                     # switch 3 is moved onto the parallel pair
        g["nodes"].update(r=dict(kind="switch", label="3", alias="3", hand=1, dirs={}),
                          **{k: dict(kind="end", label="") for k in ("t1", "t2", "t3")})
        g["edges"] += [dict(u="r", up=leg, v=t, vp="E", cm=30.0, id=f"x{t}", names=[], main=False)
                       for leg, t in zip("ABC", ("t1", "t2", "t3"))]
        with self.assertRaisesRegex(SchematicError, "2 tracks join 1 and 2"):
            edits.apply_edits(g, [dict(op="move", switch="3", through=["A", "B"], onto=["1", "2"],
                                       cm_from_first=20, hand="R", source="owner")])

    def test_a_track_drawn_only_on_a_slope_gets_an_arrow(self):
        from schematic import draw
        strands = {"s": dict(src=("a", "A"), dst=("b", "B"), main=False, way=("a", "b")),
                   "t": dict(src=("c", "A"), dst=("d", "B"), main=False, way=("d", "c"))}
        drawn = {"s": [(0, 0), (4, 2)], "u": [(3, 3), (5, 4)], "t": [(2, 0), (6, 3)]}
        runs = draw.track_runs({"strands": strands}, drawn, None)
        self.assertEqual(sorted((r[3], r[4][0]) for r in runs), [(False, "t"), (True, "s")])
        self.assertEqual(next(r for r in runs if r[4] == ["s"])[:3], (1.0, 1.0, 3.0))   # middle half of the slope
        level = draw.track_runs({"strands": strands}, {"s": [(0, 0), (1, 1), (3, 1)]}, None)
        self.assertEqual([(r[0], r[1], r[2]) for r in level], [(1, 1, 3)])               # a level piece wins

    def test_a_band_split_by_a_stub_gets_one_arrow_per_run(self):
        from schematic import direction, draw
        strands = {k: dict(src=(k, "A"), dst=(k + "x", "B"), main=True, way=("a", "b")) for k in "pqs"}
        drawn = {"p": [(0, 1), (3, 1)], "s": [(1, 1), (2, 1)], "q": [(3, 1), (6, 1)]}   # a stub drawn under the cells of p
        runs = draw.track_runs({"strands": strands}, drawn, None)
        self.assertEqual([(r[0], r[1], r[2]) for r in runs], [(1, 0, 6)])
        self.assertEqual(sorted(runs[0][4]), ["p", "q", "s"])
        nodes = {n: dict(sig=1, kind="switch") for n in ("p", "q", "s", "px", "qx", "sx")}
        band = dict(nodes=nodes, strands={k: dict(strands[k], src=(k, "A"), dst=(k + "x", "A")) for k in "pqs"},
                    rail={n: 1 for n in nodes})
        west = direction.main_runs(band, drawn)
        east = direction.main_runs(dict(band, rail={n: -1 for n in nodes}), drawn)
        self.assertEqual(east, [])                                       # east to the right all along: no arrows
        self.assertEqual([(r[0], r[1], r[2]) for r in west], [(1, 0, 6)])

    def test_review_fixes_for_runs_and_slopes(self):
        from schematic import direction, draw
        way = lambda: dict(src=("a", "A"), dst=("b", "B"), main=False, way=("a", "b"))
        back = dict(way(), way=("b", "a"))
        # a stub of the other way between two pieces of one run does not split the run
        runs = direction.merge_runs([(1, 0, 3, True, "p"), (1, 1, 2, False, "s"), (1, 3, 6, True, "q")])
        self.assertEqual([(r[1], r[2], r[3]) for r in runs], [(0, 6, True), (1, 2, False)])
        # a nearly upright slope gets no arrow; two strands on one slope share one
        strands = {"v": way(), "s": way(), "t": way(), "r": back}
        drawn = {"v": [(0, 0), (0.0000001, 2)], "s": [(0, 0), (4, 2)], "t": [(0, 0), (4, 2)], "r": [(0, 0), (4, 2)]}
        runs = draw.track_runs({"strands": strands}, drawn, None)
        self.assertEqual(sorted((r[3], sorted(r[4])) for r in runs), [(False, ["r"]), (True, ["s", "t"])])
        # the arrow's spots follow the slope: the rows at its two ends ride on the run
        self.assertEqual(next(r for r in runs if r[3])[5], (0.5, 1.5))

    def test_name_and_move_ask_for_the_leg_only_when_the_owner_left_it_out(self):
        from schematic import edits
        from schematic.core import SchematicError
        sw = lambda label: dict(kind="switch", label=label, alias=label, hand=1, dirs={})
        g = dict(nodes={"p": sw("1"), "q": sw("2")},
                 edges=[dict(u="p", up="B", v="q", vp="A", cm=50.0, id="e0", names=[], main=False),
                        dict(u="p", up="C", v="q", vp="B", cm=60.0, id="e1", names=[], main=False)])
        with self.assertRaisesRegex(SchematicError, "2 tracks join 1 and 2"):
            edits.apply_edits(g, [dict(op="name", tracks=[["1", "2", "Main"]])])
        edits.apply_edits(g, [dict(op="name", tracks=[["1", "2", "Main", "B"]])])
        self.assertEqual([e["names"] for e in g["edges"]], [["Main"], []])
        # a move whose own lift makes a second track between the pair names the track already there
        h = dict(nodes={"a": sw("1"), "b": sw("2"), "x": sw("3"), "t": dict(kind="end", label="")},
                 edges=[dict(u="a", up="B", v="x", vp="A", cm=30.0, id="m1", names=[], main=False),
                        dict(u="x", up="B", v="b", vp="A", cm=30.0, id="m2", names=[], main=False),
                        dict(u="x", up="C", v="t", vp="E", cm=30.0, id="m3", names=[], main=False),
                        dict(u="a", up="C", v="b", vp="B", cm=90.0, id="e0", names=[], main=False)])
        edits.apply_edits(h, [dict(op="move", switch="3", through=["A", "B"], onto=["1", "2"], cm_from_first=20,
                                   hand="R", source="owner")])
        self.assertIn("e0a", {e["id"] for e in h["edges"]})



class ControlPoints(unittest.TestCase):
    """Interlocking limits: layer 1 `control_points`; detail sheets draw brackets and a quoted name, the overall
    sheet never does."""

    CP = {"control_points": {"Hollow": {"code": "HL", "switches": ["2", "6", "3"]},
                             "Yard": {"switches": ["11", "12", "13"]}}}
    STATIONS = {"Hollow": ["2", "6", "3"], "Summit": ["21", "22"], "Yard": ["11", "12", "13"]}

    def details(self, cps):
        from schematic import detail
        sheet = build_with(overrides=cps)
        bands = [(t, b, dict(o, stations=self.STATIONS)) for t, b, o in sheet.bands]
        owner = detail.owners([o for _, _, o in bands])
        return sheet, {n: detail.sheet_svg(bands, m, n, owner)[0] for n, m in self.STATIONS.items()}

    def test_the_overall_sheet_ignores_control_points(self):
        sheet = build_with(overrides=self.CP)
        self.assertEqual(sheet.svg(), helpers.build().svg())

    def test_detail_sheets_draw_names_codes_and_brackets_without_faults(self):
        _, plain = self.details({})
        _, svgs = self.details(self.CP)
        self.assertIn('"HOLLOW" [HL]', svgs["Hollow"])
        self.assertIn('>"YARD"<', svgs["Yard"])
        for name, svg in svgs.items():
            self.assertEqual(label_check.check(svg)[0], [], name)
            self.assertEqual(label_check.outside_frame(svg), [], name)
        self.assertEqual(svgs["Hollow"].count("<path") - plain["Hollow"].count("<path"), 2)   # a bracket at each end
        self.assertEqual(svgs["Summit"], plain["Summit"])    # no control point there: nothing changes

    def test_a_limit_is_drawn_only_where_the_whole_interlocking_is_on_the_sheet(self):
        from schematic import detail
        sheet = build_with(overrides={"control_points": {"Wide": {"switches": ["2", "6", "3", "1"]}}})
        bands = [(t, b, dict(o, stations=self.STATIONS)) for t, b, o in sheet.bands]
        svg = detail.sheet_svg(bands, self.STATIONS["Hollow"], "Hollow", detail.owners([o for _, _, o in bands]))[0]
        self.assertNotIn("WIDE", svg)

    def test_crossovers_integers_and_stars_match(self):
        for sw in (["6"], [6], ["6*"], [2, "6", 3]):
            _, svgs = self.details({"control_points": {"X": {"switches": sw}}})
            self.assertIn('>"X"<', svgs["Hollow"], sw)

    def test_a_switch_not_on_the_plan_is_an_error(self):
        from schematic.core import SchematicError
        with self.assertRaisesRegex(SchematicError, "control point Ghost.*switch 99"):
            build_with(overrides={"control_points": {"Ghost": {"switches": ["2", "99"]}}})

    def test_a_control_point_across_two_bands_is_refused(self):
        from schematic.core import SchematicError
        with self.assertRaisesRegex(SchematicError, "more than one band"):
            build_with(overrides={"control_points": {"Both": {"switches": ["2", "21"]}}})

    def test_brackets_stop_at_a_neighbouring_switch(self):
        _, svgs = self.details({"control_points": {"A": {"switches": ["2"]}, "B": {"switches": ["6"]}}})
        self.assertIn('>"A"<', svgs["Hollow"])
        self.assertIn('>"B"<', svgs["Hollow"])
        self.assertEqual(label_check.check(svgs["Hollow"])[0], [])


if __name__ == "__main__":
    unittest.main()

