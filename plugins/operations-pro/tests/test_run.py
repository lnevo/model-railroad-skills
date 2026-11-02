"""The test runner's progress and estimate of the time left."""
import unittest
from pathlib import Path

from run import DONE, Progress, choose_files, clock, line, parse_timing, split_names


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


if __name__ == "__main__":
    unittest.main()
