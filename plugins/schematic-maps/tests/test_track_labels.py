"""The `track_labels` preference: the label drawn for a track in place of its name, on the sheet and the station detail
sheets, sheet-wide, checked up front; with none set the drawing is unchanged."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from schematic import detail, sheet
from schematic.core import SchematicError, helix_order, shown_name

STATIONS = {"Throat": ["1"], "Junction": ["2", "6", "3"]}


def built(labels=None, rename=None):
    """The example built with `track_labels` set to `labels` (left out when None), after renaming its tracks by
    `rename` ({old name: new name}) in its plan overrides."""
    src = helpers.data_with_signals()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for f in src.iterdir():
            shutil.copy(f, d / f.name)
        if rename:
            p = d / "example.plan_overrides.json"
            text = p.read_text()
            for old, new in rename.items():
                text = text.replace(json.dumps(old), json.dumps(new))
            p.write_text(text)
        if labels is not None:
            p = d / "example.preferences.json"
            o = json.loads(p.read_text())
            o["track_labels"] = labels
            p.write_text(json.dumps(o))
        return sheet.build([(helpers.graph(), "example")], d, preferences=True)


def detail_svgs(s):
    """{station: its detail sheet SVG} of sheet `s` with the STATIONS named."""
    bands = [(t, b, dict(o, stations=STATIONS, capacity={})) for t, b, o in s.bands]
    allo = [o for _, _, o in bands]
    return {name: detail.sheet_svg(bands, members, name, detail.owners(allo))[0]
            for name, members in detail.selections(allo)}


class TrackLabels(unittest.TestCase):
    def test_unset_and_empty_draw_as_before(self):
        base = helpers.build().svg()
        self.assertEqual(built().svg(), base)
        self.assertEqual(built({}).svg(), base)

    def test_a_label_is_drawn_in_place_of_the_name(self):
        svg = built({"Summit": "Pike Peak"}).svg()
        self.assertIn("PIKE PEAK", svg)
        self.assertNotIn(">SUMMIT<", svg)
        self.assertNotIn("SUMMIT", svg.replace("PIKE PEAK", ""))

    def test_a_renamed_track_labelled_with_its_old_name_draws_the_same_sheets(self):
        """The label is used wherever the drawing measures or prints a name (columns, labels, helix letters, the
        detail sheets' cut room), so a track renamed and labelled with its old name draws byte for byte as before."""
        base, got = helpers.build(), built({"Peak": "Summit"}, rename={"Summit": "Peak"})
        self.assertEqual(got.svg(), base.svg())
        self.assertEqual(detail_svgs(got), detail_svgs(base))

    def test_the_labels_reach_every_input(self):
        s = built({"Summit": "Pike Peak"})
        for _t, _b, o in s.bands:
            self.assertEqual(o["track_labels"], {"Summit": "Pike Peak"})

    def test_bad_values_stop(self):
        for labels, msg in (([], "object of track name to label"),
                            ({"Summit": ""}, "object of track name to label"),
                            ({"Summit": 3}, "object of track name to label"),
                            ({"Nowhere": "X"}, "track_labels names Nowhere, which no track of the sheet has")):
            with self.subTest(labels=labels), self.assertRaisesRegex(SchematicError, msg):
                built(labels)

    def test_two_inputs_giving_one_track_two_labels_stop(self):
        with self.assertRaisesRegex(SchematicError, "gives Summit the label 'A' in one and 'B' in two"):
            sheet.track_labels([{"track_labels": {"Summit": "A"}}, {"track_labels": {"Summit": "B"}}], ["one", "two"])

    def test_one_input_may_give_the_labels_for_the_sheet(self):
        optlist = [{}, {"track_labels": {"Summit": "A"}}]
        self.assertEqual(sheet.track_labels(optlist, ["one", "two"]), {"Summit": "A"})
        self.assertEqual(optlist[0]["track_labels"], {"Summit": "A"})


class HelixOrder(unittest.TestCase):
    """The helix letters (H1, H2, ...) follow the names drawn: a label moves its track to where the label sorts."""

    def test_no_labels_is_the_names_sorted(self):
        self.assertEqual(helix_order({"Outer", "Inner"}, {}), ["Inner", "Outer"])

    def test_labels_order_by_the_label(self):
        opts = {"track_labels": {"Outer": "Alpha", "Inner": "Beta"}}
        self.assertEqual(helix_order(["Inner", "Outer", "Inner"], opts), ["Outer", "Inner"])

    def test_shown_name_maps_each_part_of_a_joined_name(self):
        opts = {"track_labels": {"A": "X"}}
        self.assertEqual(shown_name("A / B", opts), "X / B")
        self.assertEqual(shown_name("", opts), "")
        self.assertEqual(shown_name("A", {}), "A")


if __name__ == "__main__":
    unittest.main()
