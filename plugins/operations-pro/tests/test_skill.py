"""The skill's entry file must point at reference files that exist, and name every gate and finding the code has."""
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "operations-pro"
sys.path.insert(0, str(ROOT / "servers"))

import operations_pro  # noqa: E402
import ops_gates  # noqa: E402

AGENT = ROOT / "agents" / "ops-diagnoser.md"
TOOL_PREFIX = "mcp__plugin_operations-pro_operations-pro__"


class AgentTest(unittest.TestCase):
    """The diagnosis agent may only hold reading tools, and the names must be real."""

    def setUp(self):
        self.head, self.body = AGENT.read_text().split("---")[1:3]
        self.tools = [t.strip() for t in re.search(r"^tools: (.*)$", self.head, re.M).group(1).split(",")]

    def test_frontmatter(self):
        self.assertIn("name: ops-diagnoser", self.head)
        self.assertIn("description:", self.head)

    def test_only_reading_tools(self):
        by_name = {t.name: t for t in operations_pro.tools()}
        for name in self.tools:
            if name in ("Read", "Grep", "Glob"):
                continue
            self.assertTrue(name.startswith(TOOL_PREFIX), name)
            tool = by_name[name[len(TOOL_PREFIX):]]
            self.assertTrue(tool.read_only, name)
        self.assertIn(TOOL_PREFIX + "ops_explain_build", self.tools)
        for word in ("Edit", "Write", "Bash", "ops_apply", "ops_session", "ops_live_save"):
            self.assertNotIn(word, self.tools)

    def test_points_at_the_skill(self):
        self.assertIn("references/diagnosis.md", self.body)
        self.assertIn("references/build-order.md", self.body)


class SkillTest(unittest.TestCase):
    def setUp(self):
        self.entry = (SKILL / "SKILL.md").read_text()

    def test_frontmatter(self):
        head = self.entry.split("---")[1]
        self.assertIn("name: operations-pro", head)
        self.assertIn("description:", head)

    def test_references_exist(self):
        named = set(re.findall(r"`references/([a-z-]+\.md)`", self.entry))
        self.assertTrue(named)
        on_disk = {p.name for p in (SKILL / "references").glob("*.md")}
        self.assertEqual(named, on_disk)

    def test_gates_all_described(self):
        text = (SKILL / "references" / "build-order.md").read_text()
        missing = [g for g in ops_gates.GATES if not re.search(rf"\| {g} \|", text)]
        self.assertEqual(missing, [])

    def test_findings_all_described(self):
        text = (SKILL / "references" / "diagnosis.md").read_text()
        source = (ROOT / "servers" / "ops_gates.py").read_text()
        rules = set(re.findall(r'_finding\("([a-z-]+)"', source))
        missing = [r for r in sorted(rules) if f"`{r}`" not in text]
        self.assertEqual(missing, [])

    def test_every_tool_is_named_in_the_entry_file(self):
        for tool in operations_pro.tools():
            self.assertIn(f"`{tool.name}`", self.entry, tool.name)

    def test_no_private_content(self):
        # Extra private terms come from the environment, so none are listed in the public tree.
        extra = [t for t in os.environ.get("OPS_BANNED_TERMS", "").split(",") if t.strip()]
        banned = re.compile("|".join([r"groups\.io", "jmriusers", *map(re.escape, extra)]), re.I)
        for path in [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md"), AGENT, ROOT / "README.md"]:
            self.assertIsNone(banned.search(path.read_text()), path.name)

    def test_engine_and_division_actions_are_in_the_references(self):
        import ops_actions
        source = (ROOT / "servers" / "ops_actions_engines.py").read_text()
        block = source[source.index("# ---- Engines"):source.index("# ---- End of engines and divisions")]
        names = re.findall(r"@action\([^)]*\)\ndef ([a-z_]+)", block)
        self.assertEqual(len(names), 18)
        self.assertTrue(all(n in ops_actions.ACTIONS for n in names))
        text = "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))
        self.assertEqual([n for n in names if f"`{n}`" not in text], [])
        self.assertNotIn("does not write engines", text)

    # ---- Manual builds and automations (start)
    def test_manual_build_and_automation_actions_are_in_the_references(self):
        import ops_actions
        source = (ROOT / "servers" / "ops_actions_automations.py").read_text()
        block = source[source.index("# ---- Manual builds and automations (start)"):
                       source.index("# ---- Manual builds and automations (end)")]
        names = re.findall(r"@action\([^)]*\)\ndef ([a-z_]+)", block)
        self.assertEqual(len(names), 6)
        self.assertTrue(all(n in ops_actions.ACTIONS for n in names))
        text = "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))
        self.assertEqual([n for n in names if f"`{n}`" not in text], [])
        self.assertNotIn("can run automations but not create them", text)
        readme = (ROOT / "README.md").read_text()
        self.assertNotIn("manual builds, automations", readme)
    # ---- Manual builds and automations (end)

    def test_day_and_manifest_actions_are_in_the_references(self):
        import ops_actions
        source = (ROOT / "servers" / "ops_actions_setup.py").read_text()
        block = source[source.index("# ---- Train schedule days and manifest formats"):
                       source.index("# ---- End of train schedule days and manifest formats")]
        names = re.findall(r"@action\([^)]*\)\ndef ([a-z_]+)", block)
        self.assertEqual(len(names), 11)
        self.assertTrue(all(n in ops_actions.ACTIONS for n in names))
        text = "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))
        self.assertEqual([n for n in names + ["set_active_day"] if f"`{n}`" not in text], [])
        self.assertNotIn("Days themselves are not written yet", text)
        self.assertNotIn("Format options are outside", text)
        readme = (ROOT / "README.md").read_text()
        self.assertNotIn("train schedule days, manual", readme)

    def test_engine_division_control_creator_and_train_option_actions_are_in_the_references(self):
        import ops_actions
        source = (ROOT / "servers" / "ops_actions_more.py").read_text()
        names = re.findall(r"@action\([^)]*\)\ndef ([a-z_]+)", source)
        self.assertEqual(len(names), 4)
        self.assertTrue(all(n in ops_actions.ACTIONS for n in names))
        text = "".join(p.read_text() for p in (SKILL / "references").glob("*.md"))
        self.assertEqual([n for n in names if f"`{n}`" not in text], [])
        self.assertNotIn("The control limits (field lengths) and the day name mapping are not written", text)

    def test_readme_counts_match_code(self):
        import ops_actions
        text = (ROOT / "README.md").read_text()
        self.assertIn(f"{len(ops_actions.ACTIONS)} actions", text)


if __name__ == "__main__":
    unittest.main()
