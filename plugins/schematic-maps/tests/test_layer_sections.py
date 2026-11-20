"""layers.read_layer: a kind kept as one file for every input (<kind>.json, a section per input name) reads the same
as the input's own <name>.<kind>.json, and both at once is an error."""
import json
import tempfile
import unittest
from pathlib import Path

from schematic import cache, layers


class Sections(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data = Path(self._tmp.name)

    def write(self, name, obj):
        (self.data / name).write_text(json.dumps(obj))

    def test_a_section_reads_as_the_own_file_would(self):
        over = {"edits": [{"op": "relabel", "map": {"T1": "1"}}], "title": "A"}
        prefs = {"turnbacks": ["x"], "date": "NOV 1"}
        self.write("a.plan_overrides.json", over)
        self.write("a.preferences.json", prefs)
        self.write("a.signals.json", {"signals": [{"mast": "2L"}]})
        own = layers.load("a", self.data)
        for f in ("a.plan_overrides.json", "a.preferences.json", "a.signals.json"):
            (self.data / f).unlink()
        self.write("plan_overrides.json", {"_note": "one file", "a": over, "b": {"title": "B"}})
        self.write("preferences.json", {"a": prefs})
        self.write("signals.json", {"a": {"signals": [{"mast": "2L"}]}})
        self.assertEqual(layers.load("a", self.data), own)
        self.assertEqual(layers.load("b", self.data), {"title": "B"})
        self.assertEqual(layers.load("c", self.data), {})          # no section: as a missing file

    def test_one_input_may_keep_its_own_file_beside_the_others_sections(self):
        self.write("plan_overrides.json", {"a": {"title": "A"}})
        self.write("b.plan_overrides.json", {"title": "B"})
        self.assertEqual((layers.load("a", self.data)["title"], layers.load("b", self.data)["title"]), ("A", "B"))

    def test_both_for_one_input_stops(self):
        self.write("plan_overrides.json", {"a": {"title": "A"}})
        self.write("a.plan_overrides.json", {"title": "A2"})
        with self.assertRaisesRegex(layers.LayerError, "a has both a.plan_overrides.json and a section in "
                                                        "plan_overrides.json: keep one"):
            layers.load("a", self.data)

    def test_a_bad_combined_file_names_itself(self):
        self.write("preferences.json", ["a"])
        with self.assertRaisesRegex(layers.LayerError, "preferences.json: must be an object"):
            layers.load("a", self.data)
        self.write("preferences.json", {"a": [1]})
        with self.assertRaisesRegex(layers.LayerError, r"section\(s\) a are not objects"):
            layers.load("a", self.data)
        (self.data / "preferences.json").write_text("{")
        with self.assertRaisesRegex(layers.LayerError, "preferences.json: not JSON"):
            layers.load("a", self.data)
        (self.data / "preferences.json").unlink()
        self.assertEqual(layers.load("a", self.data, preferences=False), {})

    def test_the_cache_key_reads_the_combined_files_and_leaves_out_title_fields(self):
        inputs = [({"nodes": [], "edges": []}, "a")]
        self.write("plan_overrides.json", {"a": {"title": "A"}})
        self.assertIn(self.data / "plan_overrides.json", cache.read_files(inputs, self.data))
        self.write("preferences.json", {"a": {"turnbacks": [], "date": "NOV 1", "revision": 3}})
        k1 = cache.key(inputs, self.data, True, False)
        self.write("preferences.json", {"a": {"turnbacks": [], "date": "NOV 2", "revision": 4}})
        self.assertEqual(cache.key(inputs, self.data, True, False), k1)
        self.write("preferences.json", {"a": {"turnbacks": ["x"], "date": "NOV 2"}})
        self.assertNotEqual(cache.key(inputs, self.data, True, False), k1)
        self.write("plan_overrides.json", {"a": {"title": "A2"}})
        self.assertNotEqual(cache.key(inputs, self.data, True, False), k1)


if __name__ == "__main__":
    unittest.main()
