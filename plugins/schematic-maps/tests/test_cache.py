"""cache.py: SCHEMATIC_CACHE keeps solved sheets, keyed on everything sheet.build reads."""
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import helpers
from schematic import cache, sheet
from schematic.core import SchematicError


class SheetCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.data = self.tmp / "data"
        shutil.copytree(helpers.data_with_signals(), self.data)
        self.where = self.tmp / "cache"
        self.inputs = [(helpers.graph(), "example")]

    def tearDown(self):
        self._tmp.cleanup()

    def build(self, **env):
        with mock.patch.dict(os.environ, {cache.ENV: str(self.where), **env}):
            return sheet.build(self.inputs, self.data)

    def solves(self, **env):
        """How many times sheet.build really solved during one call."""
        with mock.patch.object(sheet, "solve", wraps=sheet.solve) as spy:
            self.build(**env)
        return spy.call_count

    def test_a_hit_is_the_same_drawing_and_does_not_solve(self):
        first = self.build()
        self.assertEqual(self.solves(), 0)
        self.assertEqual(self.build().svg(), first.svg())
        self.assertEqual(first.svg(), helpers.build().svg())   # the same as a build without the cache

    def test_every_call_gets_its_own_copy(self):
        a = self.build()
        a.bands[0][1]["nodes"].clear()
        a.log.append("changed by a caller")
        b = self.build()
        self.assertTrue(b.bands[0][1]["nodes"])
        self.assertNotIn("changed by a caller", b.log)

    def test_a_changed_layer_file_or_graph_is_a_new_key(self):
        self.build()
        prefs = self.data / "example.preferences.json"
        prefs.write_text(prefs.read_text().rstrip()[:-1] + ', "unused_test_key": 1}')
        self.assertEqual(self.solves(), 1)
        self.inputs = [(dict(helpers.graph(), extra=1), "example")]
        self.assertEqual(self.solves(), 1)
        self.assertNotEqual(cache.key(self.inputs, self.data, True, False), cache.key(self.inputs, self.data, False, False))

    def test_a_file_outside_the_layer_files_does_not_change_the_key(self):
        k = cache.key(self.inputs, self.data, True, False)
        (self.data / "notes.csv").write_text("not read by a build\n")
        self.assertEqual(cache.key(self.inputs, self.data, True, False), k)

    def test_off_without_the_variable(self):
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            sheet.build(self.inputs, self.data)
        self.assertFalse(self.where.exists())

    def test_an_unreadable_entry_is_dropped_and_solved_again(self):
        self.build()
        (entry,) = self.where.glob("*.pickle")
        entry.write_bytes(b"not a pickle")
        with mock.patch("sys.stderr") as err:
            self.assertEqual(self.solves(), 1)
        self.assertIn("dropping unreadable", "".join(c.args[0] for c in err.write.call_args_list))
        self.assertEqual(len(list(self.where.glob("*.pickle"))), 1)

    def test_only_the_newest_entries_are_kept(self):
        self.where.mkdir()
        with mock.patch.object(cache, "KEEP", 2):
            for i in range(3):
                cache.store(self.where, f"k{i}", ["sheet", i])
                os.utime(self.where / f"k{i}.pickle", (1000 + i, 1000 + i))
            cache.store(self.where, "k3", ["sheet", 3])
        self.assertEqual(sorted(p.stem for p in self.where.glob("*.pickle")), ["k2", "k3"])
        self.assertEqual(list(self.where.glob("*.tmp")), [])

    def test_a_cache_folder_that_cannot_be_made_is_a_clear_error(self):
        blocker = self.tmp / "file"
        blocker.write_text("x")
        with mock.patch.dict(os.environ, {cache.ENV: str(blocker / "sub")}):
            with self.assertRaises(SchematicError) as e:
                sheet.build(self.inputs, self.data)
        self.assertIn("cannot make the cache folder", str(e.exception))


if __name__ == "__main__":
    unittest.main()
