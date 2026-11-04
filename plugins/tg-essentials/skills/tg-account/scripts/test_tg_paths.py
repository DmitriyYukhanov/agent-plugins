"""Offline path selection tests. Fixtures contain empty marker files only."""
import os
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import tg_paths


class TdataPaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="tg-paths-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.standard = self.root / "standard" / "tdata"
        self.addCleanup(patch.stopall)
        patch.dict(os.environ, {"TG_TDATA": ""}).start()
        patch.object(tg_paths, "default_tdata", return_value=self.standard).start()
        patch.object(tg_paths.sys, "platform", "win32").start()
        self.adapter = tg_paths.windows_commands
        self.commands = patch.object(tg_paths, "windows_commands", return_value=[]).start()

    def profile(self, folder):
        path = self.root / folder / "tdata"
        path.mkdir(parents=True)
        (path / "key_datas").touch()
        return path

    def command(self, path):
        exe = path.parent / "Telegram.exe"
        exe.touch()
        return f'"{exe}" -- "%1"'

    def test_explicit_path_with_spaces_wins_without_discovery(self):
        path = self.profile("Portable Telegram")
        os.environ["TG_TDATA"] = str(path)
        self.assertEqual(tg_paths.resolve_tdata(), path.resolve())
        self.commands.assert_not_called()

    def test_invalid_explicit_path_never_falls_back(self):
        self.profile("standard")
        os.environ["TG_TDATA"] = str(self.root / "missing")
        with self.assertRaisesRegex(SystemExit, "TG_TDATA"):
            tg_paths.resolve_tdata()
        self.commands.assert_not_called()

    def test_standard_path_wins_without_discovery(self):
        self.profile("standard")
        self.assertEqual(tg_paths.resolve_tdata(), self.standard.resolve())
        self.commands.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_portable_path_and_duplicate_sources(self):
        path = self.profile("Portable Telegram с пробелами")
        command = self.command(path)
        self.commands.return_value = [("process", command), ("tg handler", command)]
        self.assertEqual(tg_paths.resolve_tdata(), path.resolve())

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_different_profiles_require_override(self):
        self.commands.return_value = [
            ("process", self.command(self.profile("one"))),
            ("tg handler", self.command(self.profile("two"))),
        ]
        with self.assertRaisesRegex(SystemExit, "Multiple.*TG_TDATA"):
            tg_paths.resolve_tdata()

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_custom_profile_arguments_require_override(self):
        path = self.profile("portable")
        for flag in ('-workdir "D:/other"', '"-key" secret-profile', '-wo"rkdir" "D:/other"', '-ke"y" secret-profile'):
            with self.subTest(flag=flag):
                self.commands.return_value = [("process", self.command(path) + " " + flag)]
                with self.assertRaisesRegex(SystemExit, "custom profile.*TG_TDATA") as error:
                    tg_paths.resolve_tdata()
                self.assertNotIn("secret-profile", str(error.exception))

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_link_arguments_do_not_look_like_profile_options(self):
        path = self.profile("portable")
        for argument in ('"tg://resolve?domain=foo-keybar"', '"tg://msg_url?url=https://example.com/some-keyboard"'):
            with self.subTest(argument=argument):
                self.commands.return_value = [("process", self.command(path) + " " + argument)]
                self.assertEqual(tg_paths.resolve_tdata(), path.resolve())

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_unquoted_executable_with_spaces_is_rejected(self):
        path = self.profile("Portable Telegram")
        self.commands.return_value = [("tg handler", self.command(path).replace('"', ''))]
        with self.assertRaisesRegex(SystemExit, "Set TG_TDATA"):
            tg_paths.resolve_tdata()

    @unittest.skipUnless(os.name == "nt", "Windows command-line parsing")
    def test_wrong_handler_and_missing_markers_are_rejected(self):
        path = self.profile("portable")
        command = self.command(path)
        (path / "key_datas").unlink()
        for value in (command, command.replace("Telegram.exe", "Other.exe")):
            self.commands.return_value = [("tg handler", value)]
            with self.assertRaisesRegex(SystemExit, "Set TG_TDATA"):
                tg_paths.resolve_tdata()

    def test_non_windows_does_not_probe_windows(self):
        with patch.object(tg_paths.sys, "platform", "linux"):
            with self.assertRaisesRegex(SystemExit, "standard"):
                tg_paths.resolve_tdata()
        self.commands.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows registry adapter")
    def test_registry_survives_process_timeout(self):
        import winreg
        command = self.command(self.profile("portable"))
        notes = []
        with patch.object(winreg, "OpenKey", return_value=MagicMock()), \
             patch.object(winreg, "QueryValueEx", return_value=(command, winreg.REG_SZ)), \
             patch.object(subprocess, "run", side_effect=subprocess.TimeoutExpired("powershell", 3)) as run:
            self.assertEqual(self.adapter(notes), [("HKCU tg handler", command)])
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertIn("timed out", notes[0])

    @unittest.skipUnless(os.name == "nt", "Windows process adapter")
    def test_process_results_accept_one_or_multiple_commands(self):
        import winreg
        command = self.command(self.profile("running Telegram"))
        for value in (command, [command], None):
            with self.subTest(value=value), \
                 patch.object(winreg, "OpenKey", side_effect=FileNotFoundError), \
                 patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 0, json.dumps(value))):
                expected = [("running Telegram", command)] if value else []
                self.assertEqual(self.adapter([]), expected)

    def test_session_resolves_once_and_passes_path_to_desktop_loader(self):
        import tgsess
        path = self.profile("session source")
        with patch.object(tgsess, "TDATA", None), \
             patch.object(tgsess, "resolve_tdata", return_value=path) as resolve, \
             patch.object(tgsess, "TDesktop") as desktop:
            self.assertIs(tgsess.accounts(), desktop.return_value.accounts)
            tgsess.accounts()
            resolve.assert_called_once_with()
            desktop.assert_called_with(str(path))

    def test_diagnostic_runs_without_telegram_dependencies(self):
        path = self.profile("offline diagnostic")
        result = subprocess.run(
            [sys.executable, "-S", tg_paths.__file__],
            env={**os.environ, "TG_TDATA": str(path)}, capture_output=True,
            text=True, encoding="utf-8", timeout=5,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("TG_TDATA", result.stdout)
        self.assertIn(str(path), result.stdout)


if __name__ == "__main__":
    unittest.main()
