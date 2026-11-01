"""The skill's entry file must point at reference files that exist, and name every gate and finding the code has."""
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
        banned = re.compile(r"groups\.io|jmriusers|hart", re.I)
        for path in [SKILL / "SKILL.md", *(SKILL / "references").glob("*.md"), AGENT, ROOT / "README.md"]:
            self.assertIsNone(banned.search(path.read_text()), path.name)


if __name__ == "__main__":
    unittest.main()
