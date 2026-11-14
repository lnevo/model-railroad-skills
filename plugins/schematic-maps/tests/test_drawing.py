"""Rules R5 to R7, the checks, labels and the golden fingerprints, on the made-up example."""
import json
import os
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


if __name__ == "__main__":
    unittest.main()
