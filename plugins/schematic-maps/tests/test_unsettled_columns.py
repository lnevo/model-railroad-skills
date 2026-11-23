"""Plans whose columns do not settle on the first try are drawn again with the clearance rules that clash relaxed,
and the sheet lists each relaxation as a fault; plans that settle are never touched."""
import tempfile
import unittest
import unittest.mock
from pathlib import Path

import helpers  # noqa: F401  (puts the plugin on the path)
from schematic import columns, layout, sheet

CASES = Path(__file__).parent / "unsettled"


def build(name):
    return sheet.build([(str(CASES / name), "d")], tempfile.mkdtemp(), preferences=False)


class Relaxed(unittest.TestCase):
    def faults(self, name):
        s = build(name)
        self.assertEqual(len(s.bands), 1)
        return layout.check(s.bands[0][1])

    def test_a_short_unnamed_siding_level_with_its_main_is_a_level_track(self):
        self.assertTrue(any("relaxed" in f and "level" in f for f in self.faults("min11.json")))

    def test_a_short_link_in_a_ring_may_span_more_columns_than_its_rows(self):
        self.assertTrue(any("relaxed" in f and "diagonal" in f for f in self.faults("min24.json")))

    def test_two_turnbacks_at_one_switch_do_not_enclose_each_other(self):
        self.assertTrue(any("relaxed" in f and "enclose" in f for f in self.faults("min38.json")))

    def test_the_example_is_not_relaxed(self):
        for _, band, _ in helpers.build().bands:
            self.assertFalse(any("relaxed" in f for f in layout.check(band)))

    def test_place_without_relaxing_still_raises(self):
        calls = []
        real = columns.place

        def spy(*a, **k):
            calls.append("relaxed" in k and k["relaxed"] is not None)
            try:
                return real(*a, **k)
            except columns.Unsettled:
                calls.append("raised")
                raise

        with unittest.mock.patch.object(layout, "place", spy):
            s = build("min11.json")
        self.assertTrue(s.bands[0][1]["relaxed"])      # the relaxed try drew it: it did not raise
        first_raise = calls.index("raised")
        self.assertNotIn(True, calls[:first_raise])         # not relaxed until a plain try failed
        self.assertIn(True, calls[first_raise:])            # and then the relaxed try is the one that is passed by keyword

    def test_notes_are_fresh_for_each_settling_round(self):
        for name in ("min11.json", "min24.json", "min38.json"):
            notes = self.faults(name)
            relaxed = [f for f in notes if f.startswith("relaxed")]
            self.assertEqual(len(relaxed), len(set(relaxed)), relaxed)
            self.assertFalse(any("turn:" in f for f in relaxed), relaxed)

    def test_no_relaxed_try_when_another_orientation_settles(self):
        from test_solve_limits import triangle
        real, seen = layout.layout_one, []

        def flaky(*a, **kw):
            seen.append(kw.get("relax", False))
            if len(seen) == 1:
                raise layout.Unsettled("columns: constraints do not settle")
            return real(*a, **kw)

        with unittest.mock.patch.object(layout, "layout_one", flaky):
            layout.layout(triangle(), {}, [])
        self.assertNotIn(True, seen)


if __name__ == "__main__":
    unittest.main()
