"""Hold the portable plugin files to the Agent Plugins and Agent Skills rules, with the standard library only."""
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_portable  # noqa: E402

PLUGINS = build_portable.PLUGINS
SCHEMAS = "https://agent-plugins.org/schemas/1.0.0"
NAME = re.compile(r"^(?!.*--)[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}


def skills() -> list[Path]:
    return [p for plugin in PLUGINS for p in sorted((plugin / "skills").glob("*/SKILL.md"))]


class PortableFiles(unittest.TestCase):
    def test_generated_files_are_up_to_date(self):
        self.assertEqual(build_portable.stale(), [])

    def test_manifests_name_the_schema_and_match_claude(self):
        for plugin in PLUGINS:
            portable = json.loads((plugin / "plugin.json").read_text())
            claude = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text())
            self.assertEqual(portable["$schema"], f"{SCHEMAS}/plugin.schema.json")
            self.assertEqual((portable["name"], portable["version"]), (claude["name"], claude["version"]))

    def test_servers_start_from_the_plugin_root(self):
        for plugin in PLUGINS:
            if not (plugin / ".mcp.json").is_file():
                self.assertFalse((plugin / "mcp.json").exists(), plugin)
                continue
            config = json.loads((plugin / "mcp.json").read_text())
            self.assertEqual(config["$schema"], f"{SCHEMAS}/mcp.schema.json")
            for name, entry in config["mcpServers"].items():
                self.assertEqual(entry["type"], "stdio")
                self.assertNotIn("CLAUDE", json.dumps(entry))
                done = subprocess.run([sys.executable, *entry["args"]], cwd=plugin, input=json.dumps(INIT) + "\n",
                                      capture_output=True, text=True, timeout=30)
                self.assertEqual(json.loads(done.stdout)["result"]["serverInfo"]["name"], name, done.stderr)


class Skills(unittest.TestCase):
    def test_skills_meet_the_standard(self):
        self.assertEqual(len(skills()), 8)
        for path in skills():
            head = re.match(r"---\n(.*?)\n---\n", path.read_text(), re.S).group(1)
            fields = dict(line.split(": ", 1) for line in head.splitlines())
            self.assertEqual(set(fields), {"name", "description"}, path)
            self.assertEqual(fields["name"], path.parent.name)
            self.assertRegex(fields["name"], NAME)
            self.assertLessEqual(len(fields["description"]), 1024, path)

    def test_skills_need_no_one_platform(self):
        for path in skills():
            self.assertNotRegex(path.read_text(), r"CLAUDE_|mcp__|Claude", path)


class InstallSteps(unittest.TestCase):
    def test_the_readme_paths_exist(self):
        text = (ROOT / "plugins" / "operations-pro" / "README.md").read_text()
        for path in set(re.findall(r"model-railroad-skills/(plugins/operations-pro/\S+?)(?:[\s\"]|$)", text, re.M)):
            self.assertTrue((ROOT / path).exists(), path)

    def test_the_server_starts_by_full_path_from_anywhere(self):
        server = ROOT / "plugins" / "operations-pro" / "servers" / "operations_pro.py"
        done = subprocess.run([sys.executable, str(server)], cwd="/", input=json.dumps(INIT) + "\n",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(json.loads(done.stdout)["result"]["serverInfo"]["name"], "operations-pro", done.stderr)


if __name__ == "__main__":
    unittest.main()
