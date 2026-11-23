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
            try:
                return real(*a, **k)
            except columns.Unsettled:
                calls.append(k.get("relaxed"))
                raise

        with unittest.mock.patch.object(layout, "place", spy):
            build("min11.json")
        self.assertIn(None, calls)

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
