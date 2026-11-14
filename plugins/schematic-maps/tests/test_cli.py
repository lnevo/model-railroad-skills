"""The command line, end to end on the example: plan, panel, signals, draw, report, fingerprint, check."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import helpers


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-m", "schematic", *map(str, args)], cwd=helpers.PLUGIN,
                          capture_output=True, text=True, timeout=120)


class Cli(unittest.TestCase):
    def test_whole_flow(self):
        f = helpers.folder()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            for name in ("example.plan_overrides.json", "example.preferences.json"):
                (tmp / name).write_text((f / name).read_text())
            r = run("plan", f / "plan.xml", tmp / "graph.json", "--parts", f / "parts.json")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("matched 12 of 12", r.stdout)
            r = run("panel", f / "panel.xml", tmp / "panel.json", "--numbers", f / "numbers.csv", "--lengths", f / "lengths.csv")
            self.assertEqual(r.returncode, 0, r.stderr)
            r = run("signals", f / "panel.xml", tmp / "graph.json", "example", tmp / "example.signals.json", "--data", tmp,
                    "--numbers", f / "numbers.csv", "--lengths", f / "lengths.csv")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("5 masts placed", r.stdout)
            self.assertEqual(json.loads((tmp / "example.signals.json").read_text())["schema"], "schematic.signals/1")
            r = run("draw", tmp / "out.svg", "--data", tmp, f"{tmp / 'graph.json'}:example")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("0 label faults", r.stdout)
            self.assertTrue((tmp / "out.svg").read_text().startswith("<svg"))
            r = run("report", "--data", tmp, f"{tmp / 'graph.json'}:example", "--no-preferences")
            self.assertIn("total: crossings 0, main not level 0, ladder not level 0", r.stdout)
            r = run("fingerprint", tmp / "fp.json", "--data", tmp, f"{tmp / 'graph.json'}:example")
            self.assertIn("Lower level", json.loads((tmp / "fp.json").read_text()))
            r = run("check", tmp / "out.svg", "--list")
            self.assertEqual(r.returncode, 0, r.stdout)

    def test_a_bad_input_exits_with_a_message(self):
        r = run("draw", "x.svg", "--data", ".", "no_layer_name")
        self.assertEqual(r.returncode, 2)
        self.assertIn("GRAPH.json:NAME", r.stderr)


if __name__ == "__main__":
    unittest.main()
