"""Gates only a build can decide are settled by a real JMRI build, and say so. Skipped without JMRI."""
import shutil
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVERS = ROOT / "servers"
FIXTURES = ROOT / "tests" / "fixtures"
sys.path.insert(0, str(SERVERS))

import ops_build_state  # noqa: E402
import ops_data  # noqa: E402
import ops_jmri  # noqa: E402
from ops_gates import Gates  # noqa: E402

REAL = "real JMRI build"
ALONE = "real JMRI build of this train alone"


def gate(result, code):
    return next(g for g in result["gates"] if g["gate"] == code)


def copy_of(name):
    scratch = Path(tempfile.mkdtemp(prefix="opspro-bs-"))
    shutil.copytree(FIXTURES / name / "operations", scratch / "operations")
    return scratch / "operations"


def edit(path, name, old, new):
    text = (path / name).read_text(encoding="utf-8")
    assert old in text, old
    (path / name).write_text(text.replace(old, new, 1), encoding="utf-8")


class Fallback(unittest.TestCase):
    """The port alone, which is also what runs when JMRI is missing."""

    def test_opt_out_leaves_the_gate_not_checked_and_unmarked(self):
        g = Gates(ops_data.load(FIXTURES / "space" / "operations"))
        d3 = gate(g.why_not("BVR3015", "West Staging", "West Stage 1", "BV2", real_build=False), "D3")
        self.assertEqual(d3["status"], "not_checked")
        self.assertNotIn("settle", d3)
        self.assertEqual(d3["source"], "port")

    def test_without_jmri_the_gate_stays_not_checked_and_says_why(self):
        g = Gates(ops_data.load(FIXTURES / "space" / "operations"))
        real = ops_build_state.available
        ops_build_state.available = lambda: False
        try:
            result = g.why_not("BVR3015", "West Staging", "West Stage 1", "BV2")
        finally:
            ops_build_state.available = real
        d3 = gate(result, "D3")
        self.assertEqual((d3["status"], d3["source"]), ("not_checked", "port"))
        self.assertIn("JMRI was not found", result["note"])

    def test_a_railroad_changed_in_memory_is_not_judged_by_the_files(self):
        rr = ops_data.load(FIXTURES / "space" / "operations")
        rr.cars["extra"] = replace(next(iter(rr.cars.values())), id="extra")
        self.assertFalse(ops_build_state.in_sync(rr))
        result = Gates(rr).why_not("BVR3015", "West Staging", "West Stage 1", "BV2")
        self.assertEqual(gate(result, "D3")["status"], "not_checked")
        self.assertIn("differs from the files", result["note"])


class Aggregation(unittest.TestCase):
    """The builder draws at random: pass if any build passes, fail only if every build refuses."""

    def setUp(self):
        self.rr = ops_data.load(FIXTURES / "space" / "operations")
        self.g = Gates(self.rr)
        self.car = self.rr.find_car("BVR3015")
        self.train = self.rr.find_train("BV2")
        self.track = self.rr.find_track("West Stage 1", self.rr.find_location("West Staging"))
        port = self.g.why_not("BVR3015", "West Staging", "West Stage 1", "BV2", real_build=False)
        self.gates = [dict(x, settle=True) if x["gate"] == "D3" else x for x in port["gates"]]
        self.refusal = ops_build_state._refusals
        self.place = self.rr.locations[self.track.location_id].name

    def tearDown(self):
        ops_build_state._refusals = self.refusal

    def run_with(self, builds, refusals):
        it = iter(refusals)
        ops_build_state._refusals = lambda row, car: next(it)
        results = [{"builds": {"BV2": {"built": True, "placed": placed, "engines": ["e"]}}} for placed in builds]
        out = ops_build_state.settle_runs(self.rr, self.g, self.car, self.train, self.track, self.gates,
                                          results, "x")
        return next(x for x in out if x["gate"] == "D3")

    def test_every_build_refusing_the_gate_fails_it(self):
        line = [("D3", f"Used 5/5 moves at {self.place} (D3)")]
        d3 = self.run_with([[], []], [line, line])
        self.assertEqual(d3["status"], "fail")
        self.assertIn("in all 2 builds", d3["reason"])

    def test_one_refusing_build_alone_does_not_fail_it(self):
        line = [("D3", f"Used 5/5 moves at {self.place} (D3)")]
        d3 = self.run_with([[], []], [line, []])
        self.assertEqual(d3["status"], "not_checked")
        self.assertIn("1 of 2 builds refused it", d3["build_note"])

    def test_one_build_that_places_the_car_passes_it(self):
        placed = [{"car": self.car.id, "location": self.place, "track": self.track.name, "track_id": self.track.id}]
        d3 = self.run_with([[], placed], [[], []])
        self.assertEqual(d3["status"], "pass")
        self.assertIn("in 1 of 2 builds", d3["reason"])


@unittest.skipUnless(ops_jmri.jmri_home(), "JMRI is not installed")
class RealBuild(unittest.TestCase):
    """Tests on the same files share their builds: four JVMs for each would be most of this suite's time."""

    @classmethod
    def setUpClass(cls):
        ops_build_state.forget()

    def test_d3_passes_when_the_build_sets_the_car_out(self):
        g = Gates(ops_data.load(FIXTURES / "aggressive" / "operations"))
        self.assertEqual(gate(g.why_not("BVR1001", "Tolvern", "Tolvern Yard", "T30", real_build=False),
                              "D3")["status"], "not_checked")
        d3 = gate(g.why_not("BVR1001", "Tolvern", "Tolvern Yard", "T30"), "D3")
        self.assertEqual((d3["status"], d3["source"]), ("pass", REAL))

    def test_d3_fails_when_the_build_report_names_it(self):
        g = Gates(ops_data.load(FIXTURES / "space" / "operations"))
        d3 = gate(g.why_not("BVR3015", "West Staging", "West Stage 1", "BV2"), "D3")
        self.assertEqual((d3["status"], d3["source"]), ("fail", REAL))
        self.assertIn("(D3)", d3["reason"])
        self.assertIn("fix", d3)

    def test_d9_is_settled_by_the_build(self):
        g = Gates(ops_data.load(FIXTURES / "space" / "operations"))
        d9 = gate(g.why_not("BVR2002", "East Staging", "East Stage 2", "BV1"), "D9")
        self.assertEqual((d9["status"], d9["source"]), ("pass", REAL))

    def test_e9_aggressive_pulls_are_settled_by_the_build(self):
        g = Gates(ops_data.load(FIXTURES / "aggressive" / "operations"))
        self.assertEqual(gate(g.why_not("BVR3006", "Brackwater", "Brackwater Team Track", "Y20",
                                        real_build=False), "E9")["status"], "not_checked")
        e9 = gate(g.why_not("BVR3006", "Brackwater", "Brackwater Team Track", "Y20"), "E9")
        self.assertEqual((e9["status"], e9["source"]), ("pass", ALONE))

    def test_e9_quick_service_timing_is_settled_by_the_build_report(self):
        path = copy_of("aggressive")
        edit(path, "Operations.xml", 'aggressive="true"', 'aggressive="false" onTime="true"')
        edit(path, "OperationsLocationRoster.xml", '<track id="1s5" name="Brackwater Team Track"',
             '<track id="1s5" loadOptions="128" name="Brackwater Team Track"')
        g = Gates(ops_data.load(path))
        port = gate(g.why_not("BVR3006", "Brackwater", "Brackwater Team Track", "Y20", real_build=False), "E9")
        self.assertEqual(port["status"], "not_checked")
        self.assertIn("quick service", port["reason"])
        e9 = gate(g.why_not("BVR3006", "Brackwater", "Brackwater Team Track", "Y20"), "E9")
        self.assertEqual((e9["status"], e9["source"]), ("fail", ALONE))
        self.assertIn("(E9)", e9["reason"])

    def test_auto_locomotive_count_at_a8_is_settled_by_the_build(self):
        path = copy_of("demo")
        edit(path, "OperationsTrainRoster.xml", 'numberEngines="1"', 'numberEngines="Auto"')
        g = Gates(ops_data.load(path))
        port = gate(g.why_not("BVR1001", "Tolvern", "Tolvern Yard", "BV1", real_build=False), "A8")
        self.assertEqual(port["status"], "not_checked")
        a8 = gate(g.why_not("BVR1001", "Tolvern", "Tolvern Yard", "BV1"), "A8")
        self.assertTrue(a8["source"].startswith(REAL))
        self.assertIn(a8["status"], ("pass", "not_checked"))
        if a8["status"] == "pass":
            self.assertIn("departed from", a8["reason"])
        else:
            self.assertIn("build_note", a8)

    def test_the_run_is_cached_per_file_content(self):
        folder = FIXTURES / "space" / "operations"
        ops_build_state.forget()
        first = ops_build_state.real_build(folder, runs=2)
        self.assertEqual(len(first), 2)
        self.assertIs(ops_build_state.real_build(folder, runs=2), first)
        self.assertIsNot(ops_build_state.real_build(folder, only="BV1", runs=2), first)


if __name__ == "__main__":
    unittest.main()
