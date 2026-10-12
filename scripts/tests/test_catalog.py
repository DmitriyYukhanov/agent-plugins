"""Check the files a host needs to discover and install this catalog."""

import json
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[2]
NAME = r"[a-z0-9]+(?:-[a-z0-9]+)*"


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = json.loads(
            (ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8")
        )["plugins"]

    def test_catalog_has_one_entry_for_each_plugin_directory(self):
        names = [entry["name"] for entry in self.catalog]
        self.assertEqual(len(names), len(set(names)), "Duplicate catalog names")
        directories = {path.name for path in (ROOT / "plugins").iterdir() if path.is_dir()}
        self.assertEqual(set(names), directories, "Catalog and plugin directories differ")

    def test_sources_stay_inside_the_matching_plugin_directory(self):
        for entry in self.catalog:
            with self.subTest(plugin=entry["name"]):
                self.assertRegex(entry["name"], rf"^{NAME}$")
                self.assertEqual(entry["source"], f'./plugins/{entry["name"]}')
                path = (ROOT / entry["source"]).resolve()
                self.assertTrue(path.is_relative_to((ROOT / "plugins").resolve()))
                self.assertTrue(path.is_dir(), f"Missing plugin source: {path}")

    def test_catalog_metadata_matches_each_install_manifest(self):
        for entry in self.catalog:
            with self.subTest(plugin=entry["name"]):
                path = ROOT / entry["source"] / ".claude-plugin/plugin.json"
                self.assertTrue(path.is_file(), f"Missing install manifest: {path}")
                manifest = json.loads(path.read_text(encoding="utf-8"))
                for field in ("name", "version", "description"):
                    self.assertIsInstance(manifest[field], str, field)
                    self.assertTrue(manifest[field].strip(), f"Empty {field}")
                    self.assertEqual(entry[field], manifest[field], f"{field} differs")

    def test_each_plugin_has_discoverable_skill_frontmatter(self):
        for entry in self.catalog:
            skills = ROOT / entry["source"] / "skills"
            with self.subTest(plugin=entry["name"]):
                self.assertTrue(skills.is_dir(), "Plugin has no skill directory")
                entries = list(skills.rglob("SKILL.md"))
                self.assertTrue(entries, "Plugin has no skills")
                for path in entries:
                    directory = path.parent
                    with self.subTest(skill=directory.name):
                        self.assertEqual(directory.parent, skills, "Skill is outside its discovery directory")
                        self.assertRegex(directory.name, rf"^{NAME}$")
                        self.assertLessEqual(len(directory.name), 64)
                        self.assertTrue(path.is_file(), f"Missing skill entry: {path}")
                        self.assertTrue(path.resolve().is_relative_to(skills.resolve()))
                        text = path.read_text(encoding="utf-8")
                        frontmatter = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
                        self.assertIsNotNone(frontmatter, f"Missing frontmatter: {path}")
                        names = re.findall(r"^name:\s*([^\r\n]+)$", frontmatter[1], re.M)
                        self.assertEqual(len(names), 1, f"Missing or duplicate skill name: {path}")
                        self.assertEqual(names[0].strip().strip("\"'"), directory.name)
                        self.assertRegex(frontmatter[1], r"(?m)^description:\s*\S")

    def test_native_workflow_entries_are_packaged_as_skills(self):
        for plugin in ("python-dev", "typescript-dev", "unity-dev"):
            with self.subTest(plugin=plugin):
                self.assertTrue(
                    (ROOT / "plugins" / plugin / "skills" / plugin / "SKILL.md").is_file(),
                    "Native skill entry is missing",
                )

    def test_portable_skills_resolve_resources_without_a_vendor_environment(self):
        paths = []
        for plugin in ("learning-guide", "implementation-prd", "claude-md-slim"):
            paths.extend((ROOT / "plugins" / plugin / "skills").rglob("SKILL.md"))
        paths.append(ROOT / "plugins/unity-dev/skills/unity-run/SKILL.md")
        paths.append(ROOT / "plugins/learning-guide/skills/render/references/renderer-cli.md")
        for path in paths:
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", path.read_text(encoding="utf-8"))

    def test_readme_documents_each_catalog_plugin(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        sections = set(re.findall(r"^### ([a-z0-9-]+)\s*$", readme, re.M))
        self.assertTrue({entry["name"] for entry in self.catalog}.issubset(sections))

    def test_readme_local_links_resolve(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        headings = re.findall(r"^#{1,6}\s+(.+?)\s*$", readme, re.M)
        anchors = set()
        for heading in headings:
            slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
            anchors.add(slug)
        links = re.findall(r"\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", readme)
        for link in links:
            target = urlsplit(link.strip("<>"))
            if target.scheme or target.netloc:
                continue
            with self.subTest(link=link):
                if target.path:
                    path = (ROOT / unquote(target.path)).resolve()
                    self.assertTrue(path.is_relative_to(ROOT), "Link escapes the repository")
                    self.assertTrue(path.exists(), f"Broken local link: {link}")
                elif target.fragment:
                    self.assertIn(unquote(target.fragment), anchors, f"Broken anchor: {link}")


if __name__ == "__main__":
    unittest.main()
