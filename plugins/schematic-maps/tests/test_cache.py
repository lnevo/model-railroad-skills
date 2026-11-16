"""cache.py: SCHEMATIC_CACHE keeps solved sheets, keyed on everything sheet.build reads."""
import os
import shutil
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

import helpers
import test_le
from schematic import cache, le, sheet
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
        (self.data / "other.preferences.json").write_text("{}")
        self.assertEqual(cache.key(self.inputs, self.data, True, False), k)

    def test_every_layer_file_of_a_name_with_a_folder_is_in_the_key(self):
        (self.data / "levels").mkdir()
        inputs = [(helpers.graph(), "levels/example")]
        k = cache.key(inputs, self.data, True, False)
        (self.data / "levels/example.hints.json").write_text("{}")
        k2 = cache.key(inputs, self.data, True, False)
        self.assertNotEqual(k, k2)                              # a new file is a new key
        (self.data / "levels/example.hints.json").write_text("")
        self.assertNotEqual(cache.key(inputs, self.data, True, False), k2)
        (self.data / "sheet.preferences.json").write_text("{}")
        self.assertNotEqual(cache.key(inputs, self.data, True, False), k2)

    def test_a_graph_that_is_not_plain_json_is_solved_without_the_cache(self):
        self.inputs = [(dict(helpers.graph(), odd={1, 2}), "example")]
        with mock.patch("sys.stderr") as err:
            self.assertEqual(self.solves(), 1)
        self.assertIn("not plain JSON", "".join(c.args[0] for c in err.write.call_args_list))
        self.assertFalse(list(self.where.glob("*.pickle")))

    def test_a_cache_that_cannot_be_written_still_returns_the_solved_sheet(self):
        self.where.mkdir()
        with mock.patch("tempfile.mkstemp", side_effect=OSError(28, "No space left on device")), \
                mock.patch("sys.stderr") as err:
            got = self.build()
        self.assertEqual(got.svg(), helpers.build().svg())
        self.assertIn("cannot write", "".join(c.args[0] for c in err.write.call_args_list))

    def test_an_entry_removed_by_another_build_while_pruning_is_skipped(self):
        self.where.mkdir()
        cache.store(self.where, "a", ["sheet"])
        real = cache._mtime
        with mock.patch.object(cache, "_mtime", side_effect=lambda p: None if p.stem == "a" else real(p)):
            cache.prune(self.where)                             # no FileNotFoundError

    def test_old_half_written_files_are_removed(self):
        self.where.mkdir()
        old, new = self.where / "x.tmp", self.where / "y.tmp"
        old.write_bytes(b"half")
        new.write_bytes(b"half")
        os.utime(old, (1000, 1000))
        cache.prune(self.where)
        self.assertEqual([p.name for p in self.where.glob("*.tmp")], ["y.tmp"])

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

    def set_prefs(self, **fields):
        import json
        prefs = self.data / "example.preferences.json"
        d = json.loads(prefs.read_text())
        d.update(fields)
        prefs.write_text(json.dumps(d))

    def test_the_title_block_fields_are_not_in_the_key_and_a_hit_takes_them_from_the_files(self):
        self.set_prefs(date="2026-01-02", revision=3, sheet="1 of 2")
        self.build()
        self.set_prefs(date="2026-03-04", revision=4, sheet="2 of 2")
        self.assertEqual(self.solves(), 0)
        got = self.build()
        self.assertIn("REV 4", got.svg())
        self.assertIn("SHEET 2 OF 2", got.svg())
        self.assertNotIn("REV 3", got.svg())
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            cold = sheet.build(self.inputs, self.data)
        self.assertEqual(got.svg(), cold.svg())                # as a solve of the files as they are now
        self.assertEqual(got.log, cold.log)

    def test_a_title_field_taken_out_of_the_files_leaves_the_page(self):
        self.set_prefs(revision=7)
        self.build()
        import json
        prefs = self.data / "example.preferences.json"
        d = json.loads(prefs.read_text())
        del d["revision"]
        prefs.write_text(json.dumps(d))
        got = self.build()
        self.assertNotIn("REV 7", got.svg())
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            self.assertEqual(got.svg(), sheet.build(self.inputs, self.data).svg())

    def test_any_other_preference_is_still_in_the_key(self):
        k = cache.key(self.inputs, self.data, True, False)
        self.set_prefs(unused_test_key=2)
        self.assertNotEqual(cache.key(self.inputs, self.data, True, False), k)

    def test_the_solve_key_holds_only_the_code_the_solve_runs(self):
        names = {f.name for f in cache.modules("sheet", "cache")}
        self.assertTrue({"sheet.py", "rows.py", "layout.py", "draw.py", "cache.py"} <= names)
        self.assertFalse({"le.py", "le_labels.py", "le_masts.py", "cats.py", "cli.py"} & names)
        k = cache.key(self.inputs, self.data, True, False)
        real = Path.read_bytes
        with mock.patch.object(Path, "read_bytes", lambda f: real(f) + (b"# edited" if f.name == "le.py" else b"")):
            self.assertEqual(cache.key(self.inputs, self.data, True, False), k)
        with mock.patch.object(Path, "read_bytes", lambda f: real(f) + (b"# edited" if f.name == "rows.py" else b"")):
            self.assertNotEqual(cache.key(self.inputs, self.data, True, False), k)

    def test_imports_inside_functions_are_followed(self):
        names = {f.name for f in cache.modules("le")}
        self.assertTrue({"le_masts.py", "le_labels.py", "slots.py", "layout.py"} <= names)   # le_masts: in a function

    def test_an_unknown_module_is_a_clear_error(self):
        with self.assertRaises(SchematicError) as e:
            cache.modules("no_such_module")
        self.assertIn("no module no_such_module", str(e.exception))


class Digest(unittest.TestCase):
    def test_order_of_dicts_and_sets_does_not_matter(self):
        self.assertEqual(cache.digest({"a": 1, "b": {2, 3}}), cache.digest({"b": {3, 2}, "a": 1}))

    def test_types_and_values_are_told_apart(self):
        values = [1, 1.0, True, "1", None, [1], (1,), {1}, {"1": 1}, {1: 1}, [1, 2], [[1], 2], ["a;", "b"], ["a", ";b"]]
        self.assertEqual(len({cache.digest(v) for v in values}), len(values))

    def test_anything_but_plain_data_is_refused(self):
        with self.assertRaises(TypeError):
            cache.digest({"x": object()})


def xml(P):
    return ET.tostring(le.to_xml(P, "p"))


class PanelCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {cache.ENV: str(Path(self._tmp.name) / "cache")})
        self.env.start()
        self.bands = test_le.bands()
        full = le.panel(self.bands, None)
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            self.fit = (int(full.size[0] * 0.8) + le.CHROME[0], full.size[1] + le.CHROME[1])

    def tearDown(self):
        self.env.stop()
        self._tmp.cleanup()

    def draws(self, **kw):
        with mock.patch.object(le, "draw_panel", wraps=le.draw_panel) as spy:
            P = le.panel(self.bands, None, **kw)
        return P, spy.call_count

    def test_a_hit_draws_nothing_and_is_the_same_panel(self):
        first, n = self.draws(fit=self.fit)
        self.assertGreater(n, 1)
        again, n = self.draws(fit=self.fit)
        self.assertEqual(n, 0)
        self.assertEqual(xml(again), xml(first))
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            self.assertEqual(xml(le.panel(self.bands, None, fit=self.fit)), xml(first))
        self.assertEqual(again.scale, first.scale)

    def test_a_label_layer_change_keeps_the_fit_grid(self):
        first, _ = self.draws(fit=self.fit)
        second, n = self.draws(fit=self.fit, labels_by_band=True)
        self.assertEqual(n, 1)                                  # drawn once, at the kept grid: no search
        self.assertEqual(second.scale, first.scale)
        with mock.patch.dict(os.environ, {cache.ENV: ""}):
            cold = le.panel(self.bands, None, fit=self.fit, labels_by_band=True)
        self.assertEqual(xml(second), xml(cold))

    def test_every_call_gets_its_own_copy(self):
        a = le.panel(self.bands, None)
        a.labels.clear()
        self.assertTrue(le.panel(self.bands, None).labels)

    def test_a_changed_argument_is_drawn_again(self):
        self.draws()
        _, n = self.draws(gap=le.BAND_GAP + 8)
        self.assertEqual(n, 1)

    def test_arguments_that_are_not_plain_data_are_drawn_without_the_cache(self):
        odd = [(t, b, dict(o, odd=object())) for t, b, o in self.bands]
        with mock.patch("sys.stderr") as err:
            with mock.patch.object(le, "draw_panel", wraps=le.draw_panel) as spy:
                le.panel(odd, None)
                le.panel(odd, None)
        self.assertEqual(spy.call_count, 2)
        self.assertIn("not plain data", "".join(c.args[0] for c in err.write.call_args_list))


if __name__ == "__main__":
    unittest.main()
