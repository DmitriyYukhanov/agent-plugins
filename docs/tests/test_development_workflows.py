"""Check development skill entry points and their bundled references."""

from pathlib import Path
import re
import unittest


REPO_ROOT = Path(__file__).resolve().parents[2]


class DevelopmentWorkflowTests(unittest.TestCase):
    def test_shared_entry_points(self):
        for language in ("python", "typescript", "unity"):
            with self.subTest(language=language):
                plugin = REPO_ROOT / "plugins" / f"{language}-dev"
                skill = plugin / "skills" / f"{language}-dev" / "SKILL.md"
                text = skill.read_text(encoding="utf-8")
                self.assertIn("`AGENTS.md`", text)
                self.assertIn("sequential", text)
                self.assertNotIn("AskUserQuestion", text)
                self.assertNotIn("arguments:", text)
                self.assertFalse((plugin / "commands" / f"{language}-dev.md").exists())
                self.assert_local_links(skill, text)

    def test_unity_test_entry_does_not_need_host_arguments(self):
        skill = REPO_ROOT / "plugins/unity-dev/skills/unity-tests-run/SKILL.md"
        text = skill.read_text(encoding="utf-8")
        self.assertNotIn("$ARGUMENTS", text)
        self.assertNotIn("CLAUDE_PLUGIN_ROOT", text)
        self.assertIn("EditMode", text)
        self.assertIn("NOT CHECKED", text)
        self.assert_local_links(skill, text)
        self.assertTrue((skill.parent / "../../scripts/run-unity-tests.sh").is_file())

    def assert_local_links(self, skill, text):
        for target in re.findall(r"\]\(([^)]+)\)", text):
            self.assertTrue((skill.parent / target).is_file(), f"{skill}: {target}")


if __name__ == "__main__":
    unittest.main()
