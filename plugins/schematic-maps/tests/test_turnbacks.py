"""The `turnbacks` preference pins which tracks a band draws as turnbacks, and a helix end's Layout Editor label moves
above or below its circle when its own spot lies on a track."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path

import helpers
from schematic import le, le_labels, le_masts, sheet
from schematic.core import SchematicError
from unittest import mock


def built(names):
    """The example built with `turnbacks` set to `names`: its bands' turnback nodes, by band title."""
    src = helpers.data_with_signals()
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        for f in src.iterdir():
            shutil.copy(f, d / f.name)
        p = d / "example.preferences.json"
        o = json.loads(p.read_text())
        o["turnbacks"] = names
        p.write_text(json.dumps(o))
        s = sheet.build([(helpers.graph(), "example")], d, preferences=True)
    return {t.split()[0]: sorted(k for k in b["nodes"] if k.startswith("turn:")) for t, b, _ in s.bands}


class Turnbacks(unittest.TestCase):
    def test_the_cheapest_turnback_stays_when_named(self):
        self.assertEqual(built(["Loop"])["Lower"], ["turn:e12"])

    def test_a_named_track_is_drawn_as_a_turnback(self):
        self.assertIn("turn:e1", built(["Main West"])["Lower"])

    def test_a_track_no_orientation_can_turn_back_stops(self):
        with self.assertRaisesRegex(SchematicError, "no orientation draws Engine Spur as turnbacks"):
            built(["Engine Spur"])

    def test_a_name_on_no_track_stops(self):
        with self.assertRaisesRegex(SchematicError, "turnbacks names Nowhere, which no track of the sheet has"):
            built(["Nowhere"])

    def test_a_bad_value_stops(self):
        with self.assertRaisesRegex(SchematicError, "list of track names"):
            built("Loop")


class HelixLabel(unittest.TestCase):
    """settle_end_labels: an end's label on a track takes its first clear spot above or below its circle, inside the
    panel and off tracks, masts and other fixed labels; a clear one stays."""

    @staticmethod
    def setup():
        P = le.panel(helpers.build().bands)
        world = le_masts.World(le_masts.PanelView(P))
        a, b = max((seg for pieces in world.track.values() for seg in pieces if seg[0][1] == seg[1][1]),
                   key=lambda seg: abs(seg[1][0] - seg[0][0]))                 # the longest level track line
        lb = next(lb for lb in P.labels if lb["text"].startswith("HELIX TO"))
        x0, y0, x1, y1 = le_labels.label_box(lb)
        centre = min((sh["centre"] for sh in P.shapes), key=lambda c: abs(c[0] - x0) + abs(c[1] - y0))
        on_track = [min(a[0], b[0]) + 2, a[1] - (y1 - y0) / 2]
        return P, lb, centre, on_track

    def test_labels_clear_at_their_own_spot_do_not_move(self):
        P = le.panel(helpers.build().bands)
        self.assertTrue([lb for lb in P.labels if lb["text"].startswith("HELIX TO")])
        self.assertFalse([lb for lb in P.labels if "around" in lb])        # taken up by the label layer
        self.assertFalse([line for line in P.log if "lay on a track beside its end" in line])

    def test_a_label_on_a_track_moves_beside_its_circle(self):
        P, lb, centre, on_track = self.setup()
        lb["xy"], lb["around"] = list(on_track), [list(centre), le.HELIX_R]
        spots = le_labels.end_label_spots(lb)
        le_labels.settle_end_labels(P)
        self.assertIn(lb["xy"], spots)
        self.assertNotIn("around", lb)
        self.assertIsNone(le_labels.fixed_on_line(le_labels.track_ink(P), le_labels.label_box(lb)))
        x0, _y0, x1, _y1 = le_labels.label_box(lb)
        self.assertAlmostEqual((x0 + x1) / 2, centre[0], delta=1)            # centred as JMRI draws it
        self.assertTrue([line for line in P.log if "lay on a track beside its end" in line])

    def test_a_spot_off_the_panel_or_on_a_track_is_passed_over(self):
        P, lb, centre, on_track = self.setup()
        lb["xy"], lb["around"] = list(on_track), [list(centre), le.HELIX_R]
        with mock.patch.object(le_labels, "end_label_spots", return_value=[[-500.0, -500.0], list(on_track)]):
            le_labels.settle_end_labels(P)
        self.assertEqual(lb["xy"], on_track)                                   # stays where the check finds it
        self.assertEqual(le_labels.fixed_on_line(le_labels.track_ink(P), le_labels.label_box(lb)), "a track")


if __name__ == "__main__":
    unittest.main()
