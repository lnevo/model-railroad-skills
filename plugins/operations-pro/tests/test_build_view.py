"""ops_dry_run and ops_train answer with the build report reader's output, not a text tail."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "servers"))

import ops_jmri  # noqa: E402
import ops_report  # noqa: E402
from ops_store import Refused  # noqa: E402

BUILDSTATUS = ROOT / "tests" / "fixtures" / "demo" / "buildstatus"


def row(train: str) -> dict:
    text = (BUILDSTATUS / f"train ({train}).txt").read_text(encoding="utf-8")
    return {"built": train != "X99", "cars": [], "report_text": text, "report_tail": text[-1500:]}


class AttachReport(unittest.TestCase):
    def test_default_is_compact_and_replaces_the_tail(self):
        out = ops_jmri.attach_report(row("BV1"))
        self.assertNotIn("report_tail", out)
        self.assertNotIn("report_text", out)
        self.assertEqual(sorted(out["report"]), ["built_on", "outcome", "summary", "train"])
        self.assertEqual(out["report"]["train"], "BV1")
        self.assertTrue(out["report"]["summary"])

    def test_failed_build_names_its_gate(self):
        out = ops_jmri.attach_report(row("X99"))
        self.assertTrue(out["report"]["outcome"]["failed"])
        self.assertEqual(out["report"]["outcome"]["failure"][0]["gate"], "A8")

    def test_normal_and_full_match_ops_explain_build(self):
        for detail in ("normal", "full"):
            out = ops_jmri.attach_report(row("BV1"), detail)["report"]
            expected = ops_report.explain((BUILDSTATUS / "train (BV1).txt").read_text(encoding="utf-8"),
                                          detail=detail)
            self.assertEqual(out, expected)
        self.assertIn("car_list", ops_jmri.attach_report(row("BV1"), "full")["report"])

    def test_tail_is_the_fallback_without_a_report(self):
        out = ops_jmri.attach_report({"built": False, "report_text": "", "report_tail": ""})
        self.assertEqual(out, {"built": False, "report_tail": ""})
        out = ops_jmri.attach_report({"built": True, "report_text": "", "report_tail": "the end"}, "full")
        self.assertEqual(out["report_tail"], "the end")
        self.assertNotIn("report", out)

    def test_unreadable_report_falls_back_with_a_note(self):
        original = ops_report.explain
        ops_report.explain = lambda *a, **k: (_ for _ in ()).throw(ValueError("odd"))
        try:
            out = ops_jmri.attach_report({"report_text": "x", "report_tail": "x"})
        finally:
            ops_report.explain = original
        self.assertEqual(out["report_tail"], "x")
        self.assertIn("odd", out["report_note"])

    def test_unknown_detail_is_refused(self):
        with self.assertRaises(Refused):
            ops_jmri.attach_report(row("BV1"), "everything")


class Wiring(unittest.TestCase):
    def test_tools_offer_detail(self):
        import operations_pro
        tools = {t.name: t for t in operations_pro.tools()}
        for name in ("ops_dry_run", "ops_train"):
            self.assertIn("detail", tools[name].schema["properties"])


if __name__ == "__main__":
    unittest.main()
