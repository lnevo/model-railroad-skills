"""The test runner's progress and estimate of the time left, how it splits files, and the shared builds."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from run import (DONE, ONE_FILE, SPLIT_CLASS, TESTS, Progress, Unit, choose_files, clock, line, parse_timing,
                 plan_units, split_names, unit_history)

sys.path.insert(0, str(TESTS.parent / "servers"))
import ops_build_state  # noqa: E402
import ops_jmri  # noqa: E402
import shared_builds  # noqa: E402


class Choosing(unittest.TestCase):
    EVERY = [Path("test_a.py"), Path("test_b.py"), Path("test_c.py")]

    def test_a_mode_can_come_with_files(self):
        self.assertEqual(split_names(["fast", "test_a"]), ("fast", ["test_a"]))

    def test_files_alone_run_with_real_jmri(self):
        self.assertEqual(split_names(["test_a", "test_b"]), ("all", ["test_a", "test_b"]))

    def test_no_names_is_every_test(self):
        self.assertEqual(split_names([]), ("all", []))
        self.assertEqual(choose_files(self.EVERY, []), self.EVERY)

    def test_only_the_named_files_run_with_or_without_py(self):
        self.assertEqual(choose_files(self.EVERY, ["test_c.py", "test_a"]), [self.EVERY[0], self.EVERY[2]])

    def test_a_mistyped_file_is_refused(self):
        with self.assertRaises(ValueError):
            choose_files(self.EVERY, ["test_nope"])


class TimeLeft(unittest.TestCase):
    def progress(self, history=None):
        return Progress({"a": 10, "b": 10}, history or {})

    def test_nothing_done_gives_no_estimate(self):
        self.assertIsNone(self.progress().seconds_left(30))

    def test_the_estimate_follows_this_run_not_the_last_one(self):
        # Half the work took 100 seconds: a machine twice as slow as last time still says 100 more.
        p = self.progress({"a": {"seconds": 25, "tests": 10}, "b": {"seconds": 25, "tests": 10}})
        p.start("a")
        for _ in range(10):
            p.tested("a")
        p.finish("a", True)
        self.assertEqual(p.seconds_left(100), 100)

    def test_a_slow_file_counts_for_what_it_took_last_time(self):
        p = self.progress({"a": {"seconds": 10, "tests": 10}, "b": {"seconds": 90, "tests": 10}})
        p.start("a")
        for _ in range(10):
            p.tested("a")
        p.finish("a", True)
        self.assertEqual(p.seconds_left(10), 90)

    def test_a_running_file_counts_for_the_tests_it_has_finished(self):
        p = self.progress()
        p.start("a")
        for _ in range(5):
            p.tested("a")
        self.assertEqual(p.seconds_left(10), 30)

    def test_a_new_file_is_weighed_at_the_average_rate(self):
        p = Progress({"a": 10, "b": 10}, {"a": {"seconds": 40, "tests": 10}})
        self.assertEqual(p.files["b"]["weight"], 40)


class Reporting(unittest.TestCase):
    def test_the_line_says_counts_time_left_and_what_is_running(self):
        p = Progress({"a": 2, "b": 2}, {})
        p.start("a")
        p.tested("a")
        text = line(p.snapshot())
        self.assertTrue(text.startswith("[1/4 tests, 0/2 files]"), text)
        self.assertIn("left", text)
        self.assertIn("running a", text)

    def test_a_failed_file_is_named(self):
        p = Progress({"a": 1}, {})
        p.start("a")
        p.finish("a", False)
        self.assertIn("FAILED a", line(p.snapshot()))

    def test_the_total_becomes_true_when_a_file_ends(self):
        p = Progress({"a": 5}, {})
        p.start("a")
        p.tested("a")
        p.finish("a", True)
        self.assertEqual(p.snapshot()["tests"], 1)

    def test_a_done_line_gives_the_test_and_its_seconds(self):
        self.assertEqual(parse_timing(f"{DONE} 1.25 test_a.Case.test_b\n"), (1.25, "test_a.Case.test_b"))

    def test_a_tests_own_output_can_share_the_line(self):
        self.assertEqual(parse_timing(f"partial{DONE} 2.0 test_a.Case.test_b\n"), (2.0, "test_a.Case.test_b"))

    def test_other_output_is_not_a_timing(self):
        self.assertIsNone(parse_timing("ordinary output\n"))

    def test_clock(self):
        self.assertEqual((clock(9), clock(125)), ("9s", "2m05s"))


class Splitting(unittest.TestCase):
    def file(self, text="class A(unittest.TestCase):\n    pass\n"):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        path = Path(folder.name) / "test_x.py"
        path.write_text(text)
        return path

    def test_a_file_with_no_class_times_runs_whole(self):
        self.assertEqual(plan_units(self.file(), {}), [Unit("test_x", "test_x")])

    def test_a_slow_class_runs_alone_and_the_rest_runs_together(self):
        past = {"seconds": 90, "tests": 6, "classes": {"Slow": [SPLIT_CLASS + 1, 2], "Quick": [3, 4]}}
        self.assertEqual(plan_units(self.file(), past),
                         [Unit("test_x.Slow", "test_x", ("Slow",)), Unit("test_x (rest)", "test_x", skip=("Slow",))])

    def test_a_file_with_a_module_fixture_is_never_split(self):
        past = {"classes": {"Slow": [SPLIT_CLASS + 1, 2]}}
        self.assertEqual(plan_units(self.file("def setUpModule():\n    pass\n"), past), [Unit("test_x", "test_x")])

    def test_each_unit_is_weighed_by_its_own_classes(self):
        past = {"seconds": 90, "tests": 6, "classes": {"Slow": [60, 2], "Quick": [3, 4]}}
        self.assertEqual(unit_history(Unit("test_x", "test_x"), past), past)
        self.assertEqual(unit_history(Unit("test_x.Slow", "test_x", ("Slow",)), past), {"seconds": 60, "tests": 2})
        self.assertEqual(unit_history(Unit("r", "test_x", skip=("Slow",)), past), {"seconds": 3, "tests": 4})

    def run_child(self, only, skip):
        """The child script on a file of two classes; the test ids it reports done."""
        path = self.file("import unittest\nclass A(unittest.TestCase):\n    def test_a(self):\n        pass\n"
                         "class B(unittest.TestCase):\n    def test_b(self):\n        pass\n"
                         "    def test_c(self):\n        pass\n")
        code = ONE_FILE.format(servers=str(TESTS.parent / "servers"), fast=True, name="test_x", done=DONE,
                               only=only, skip=skip)
        done = subprocess.run([sys.executable, "-c", code], cwd=path.parent, capture_output=True, text=True,
                              env={"PATH": "", "OPS_SHARED_BUILDS": ""})
        self.assertEqual(done.returncode, 0, done.stderr)
        return sorted(parse_timing(text)[1] for text in done.stdout.splitlines() if parse_timing(text))

    def test_the_child_runs_only_the_classes_named(self):
        self.assertEqual(self.run_child({"A"}, set()), ["test_x.A.test_a"])

    def test_the_rest_is_every_class_not_split_off(self):
        self.assertEqual(self.run_child(None, {"A"}), ["test_x.B.test_b", "test_x.B.test_c"])
        self.assertEqual(len(self.run_child(None, set())), 3)


@unittest.skipUnless(shared_builds.SUPPORTED, "no fcntl here")
class SharedBuilds(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.folder, self.ops = Path(temp.name) / "builds", Path(temp.name) / "operations"
        self.folder.mkdir()
        self.ops.mkdir()
        (self.ops / "Operations.xml").write_text("<operations/>")
        self.calls = []
        for patch in (mock.patch.object(ops_build_state, "run_builds", self.fake_build),
                      mock.patch.object(ops_jmri, "jmri_home", return_value=None)):
            patch.start()
            self.addCleanup(patch.stop)

    def fake_build(self, directory, job, runs):
        self.calls.append(job)
        if job.get("fail"):
            raise RuntimeError("JMRI did not finish")
        return [{"run": n, "job": job} for n in range(runs)]

    def test_a_second_process_reads_the_build_the_first_one_kept(self):
        shared_builds.install(self.folder)
        first = ops_build_state.run_builds(self.ops, {"build": True}, 2)
        second = ops_build_state.run_builds(self.ops, {"build": True}, 2)
        self.assertEqual((first, second, len(self.calls)), (second, first, 1))
        kept = [p for p in self.folder.iterdir() if p.suffix == ".json"]
        self.assertEqual([json.loads(p.read_text()) for p in kept], [first])

    def test_a_different_job_run_count_or_folder_builds_again(self):
        shared_builds.install(self.folder)
        ops_build_state.run_builds(self.ops, {"build": True}, 2)
        ops_build_state.run_builds(self.ops, {"build": True, "only": ["T1"]}, 2)
        ops_build_state.run_builds(self.ops, {"build": True}, 1)
        (self.ops / "Operations.xml").write_text("<operations changed='yes'/>")
        ops_build_state.run_builds(self.ops, {"build": True}, 2)
        self.assertEqual(len(self.calls), 4)

    def test_a_failed_build_is_not_kept(self):
        shared_builds.install(self.folder)
        for _ in range(2):
            with self.assertRaisesRegex(RuntimeError, "did not finish"):
                ops_build_state.run_builds(self.ops, {"fail": True}, 1)
        self.assertEqual(len(self.calls), 2)
        self.assertEqual([p for p in self.folder.iterdir() if p.suffix == ".json"], [])

    def test_a_missing_folder_is_refused(self):
        with self.assertRaisesRegex(RuntimeError, "not a folder"):
            shared_builds.install(self.folder / "gone")


if __name__ == "__main__":
    unittest.main()
