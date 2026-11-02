"""What each JMRI start costs: the Jython package cache is built once and then only read."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "servers"))

import mcp_stdio  # noqa: E402
import ops_jmri  # noqa: E402


def value(command, name):
    return next(a.split("=", 1)[1] for a in command if a.startswith(f"-D{name}="))


class JythonCache(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix="opspro-cache-")
        self.addCleanup(scratch.cleanup)
        self.dir = Path(scratch.name)
        self.home = self.dir / "JMRI"
        (self.home / "lib").mkdir(parents=True)
        (self.home / "jmri.jar").write_text("jar")
        self.source = self.dir / "source"
        self.source.mkdir()
        self.shared = self.dir / "shared" / "install"
        self.commands = []
        for patch in (mock.patch.object(ops_jmri, "jmri_home", return_value=self.home),
                      mock.patch.object(ops_jmri, "_shared_jython_cache", return_value=self.shared),
                      mock.patch.object(ops_jmri.subprocess, "run", side_effect=self.fake_java)):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_java(self, command, **_):
        self.commands.append(command)
        if self.write_result:
            Path(value(command, "worker.out")).write_text(json.dumps({}))
        cache = Path(value(command, "python.cachedir"))
        cache.mkdir(parents=True, exist_ok=True)
        (cache / "packages.idx").write_text("index")
        return SimpleNamespace(stdout="", stderr="died")

    write_result = True

    def lock(self):
        self.shared.parent.mkdir(parents=True, exist_ok=True)
        lock = self.shared.with_name(self.shared.name + ".lock")
        lock.touch()
        return lock

    def test_the_first_run_builds_the_shared_cache_in_place(self):
        ops_jmri.run_worker(self.source, {})
        self.assertEqual(Path(value(self.commands[0], "python.cachedir")), self.shared)
        self.assertTrue((self.shared / ops_jmri.CACHE_READY).is_file())
        self.assertFalse(self.shared.with_name(self.shared.name + ".lock").exists())

    def test_a_later_run_reads_the_shared_cache(self):
        ops_jmri.run_worker(self.source, {})
        ops_jmri.run_worker(self.source, {})
        self.assertEqual(Path(value(self.commands[1], "python.cachedir")), self.shared)

    def test_while_another_run_builds_it_a_run_stays_private(self):
        self.lock()
        ops_jmri.run_worker(self.source, {})
        self.assertNotEqual(Path(value(self.commands[0], "python.cachedir")), self.shared)
        self.assertFalse(self.shared.exists())

    def test_an_unfinished_cache_is_not_read(self):
        self.lock()
        self.shared.mkdir()
        ops_jmri.run_worker(self.source, {})
        self.assertNotEqual(Path(value(self.commands[0], "python.cachedir")), self.shared)

    def test_a_lock_left_by_a_killed_run_is_taken_over(self):
        os.utime(self.lock(), (1, 1))
        ops_jmri.run_worker(self.source, {})
        self.assertEqual(Path(value(self.commands[0], "python.cachedir")), self.shared)

    def test_a_run_that_stopped_publishes_nothing_and_frees_the_lock(self):
        self.write_result = False
        with self.assertRaises(ops_jmri.Refused):
            ops_jmri.run_worker(self.source, {})
        self.assertFalse((self.shared / ops_jmri.CACHE_READY).exists())
        self.assertFalse(self.shared.with_name(self.shared.name + ".lock").exists())

    def test_every_run_uses_the_quick_compiler(self):
        ops_jmri.run_worker(self.source, {})
        self.assertEqual(self.commands[0][1], ops_jmri.QUICK_JIT)


class ServerVersion(unittest.TestCase):
    def test_the_server_reports_the_plugin_version(self):
        plugin = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(mcp_stdio.PLUGIN_VERSION, plugin["version"])


class SharedPlace(unittest.TestCase):
    def test_a_new_jmri_gets_a_new_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            (home / "jmri.jar").write_text("5.16")
            before = ops_jmri._shared_jython_cache(home)
            (home / "jmri.jar").write_text("5.18 build")
            self.assertNotEqual(ops_jmri._shared_jython_cache(home), before)


if __name__ == "__main__":
    unittest.main()
