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
        self.assertEqual(built(["Main West"])["Lower"], ["turn:e1", "turn:e12"])

    def test_a_track_no_orientation_can_turn_back_stops(self):
        with self.assertRaisesRegex(SchematicError, "no orientation draws Main as turnbacks"):
            built(["Main"])

    def test_a_name_on_no_track_stops(self):
        with self.assertRaisesRegex(SchematicError, "turnbacks names Nowhere"):
            built(["Nowhere"])

    def test_a_bad_value_stops(self):
        with self.assertRaisesRegex(SchematicError, "list of track names"):
            built("Loop")


class HelixLabel(unittest.TestCase):
    """settle_end_labels: an end's label on a track takes its first clear other spot; a clear one stays."""

    @staticmethod
    def panel():
        return le.panel(helpers.build().bands)

    def test_labels_clear_at_their_own_spot_do_not_move(self):
        P = self.panel()
        helix = [lb for lb in P.labels if lb["text"].startswith("HELIX TO")]
        self.assertTrue(helix)
        self.assertFalse([lb for lb in P.labels if "alts" in lb])          # taken up by the label layer
        self.assertFalse([line for line in P.log if "lay on a track beside its end" in line])

    def test_a_label_on_a_track_takes_its_first_clear_spot(self):
        P = self.panel()
        world = le_masts.World(le_masts.PanelView(P))
        a, b = max((seg for pieces in world.track.values() for seg in pieces if seg[0][1] == seg[1][1]),
                   key=lambda seg: abs(seg[1][0] - seg[0][0]))                 # the longest level track line
        lb = next(lb for lb in P.labels if lb["text"].startswith("HELIX TO"))
        h = le_labels.label_box(lb)[3] - le_labels.label_box(lb)[1]
        on_track = [min(a[0], b[0]) + 2, a[1] - h / 2]
        clear = [lb["xy"][0], lb["xy"][1]]                                     # where le drew it, clear of track
        lb["xy"], lb["alts"] = list(on_track), [list(on_track), clear]
        le_labels.settle_end_labels(P)
        self.assertEqual(lb["xy"], clear)                                      # the blocked other spot is passed over
        self.assertNotIn("alts", lb)
        self.assertTrue([line for line in P.log if "lay on a track beside its end" in line])

    def test_a_label_with_no_clear_spot_stays_where_the_check_finds_it(self):
        P = self.panel()
        world = le_masts.World(le_masts.PanelView(P))
        a, b = max((seg for pieces in world.track.values() for seg in pieces if seg[0][1] == seg[1][1]),
                   key=lambda seg: abs(seg[1][0] - seg[0][0]))
        lb = next(lb for lb in P.labels if lb["text"].startswith("HELIX TO"))
        h = le_labels.label_box(lb)[3] - le_labels.label_box(lb)[1]
        on_track = [min(a[0], b[0]) + 2, a[1] - h / 2]
        lb["xy"], lb["alts"] = list(on_track), [list(on_track)]
        le_labels.settle_end_labels(P)
        self.assertEqual(lb["xy"], on_track)
        self.assertEqual(le_labels.fixed_on_line(le_labels.track_ink(P), le_labels.label_box(lb)), "a track")


if __name__ == "__main__":
    unittest.main()
