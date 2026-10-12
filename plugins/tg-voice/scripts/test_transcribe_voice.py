"""Offline hook contract tests; Whisper and model downloads are replaced."""

import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "transcribe_voice", PLUGIN_ROOT / "scripts" / "transcribe-voice.py"
)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)


class TranscribeVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.voice = Path(self.temp.name) / "voice.oga"
        self.voice.write_text("Hello from voice", encoding="utf-8")

    def run_hook(self, **responses):
        payload = {
            "session_id": "offline-test",
            "transcript_path": str(Path(self.temp.name) / "session.jsonl"),
            "cwd": self.temp.name,
            "permission_mode": "default",
            "hook_event_name": "PostToolUse",
            "tool_name": "mcp__plugin_telegram_telegram__download_attachment",
            "tool_input": {"attachment_id": "test-voice"},
            "tool_use_id": "test-tool-use",
            "mcp_server": {"name": "telegram"},
        }
        payload.update(responses)
        model = SimpleNamespace(
            transcribe=lambda path, beam_size: (
                [SimpleNamespace(text=Path(path).read_text(encoding="utf-8"))],
                SimpleNamespace(language="en", language_probability=0.95),
            )
        )
        modules = {
            "faster_whisper": SimpleNamespace(WhisperModel=lambda *args, **kwargs: model),
            "huggingface_hub": SimpleNamespace(try_to_load_from_cache=lambda *args: "cached"),
        }
        output = io.StringIO()
        with patch.dict(sys.modules, modules), patch.object(
            sys, "stdin", io.StringIO(json.dumps(payload))
        ), patch.object(sys, "stdout", output):
            hook.main()
        return json.loads(output.getvalue()) if output.getvalue() else None

    def test_manifest_registers_an_existing_post_tool_use_hook(self):
        manifest = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
        hooks_path = PLUGIN_ROOT / manifest.get("hooks", "hooks/hooks.json")
        self.assertTrue(hooks_path.is_file(), f"Registered hook file missing: {hooks_path}")
        config = json.loads(hooks_path.read_text())
        self.assertTrue(config["hooks"]["PostToolUse"])

    def test_tool_response_voice_paths_are_transcribed(self):
        for response in (
            {"path": str(self.voice)},
            {"file_path": str(self.voice)},
            str(self.voice),
        ):
            with self.subTest(response=response):
                result = self.run_hook(tool_response=response)
                self.assertIsNotNone(result)
                self.assertIn("Hello from voice", result["systemMessage"])

    def test_transcription_is_added_to_agent_context(self):
        result = self.run_hook(tool_result={"path": str(self.voice)})
        self.assertEqual(
            result.get("hookSpecificOutput"),
            {
                "hookEventName": "PostToolUse",
                "additionalContext": "Voice message transcription "
                "(language: en, confidence: 95%):\n\nHello from voice",
            },
        )

    def test_tool_response_takes_precedence_over_legacy_result(self):
        result = self.run_hook(
            tool_response={"path": str(self.voice)}, tool_result="missing.oga"
        )
        self.assertIsNotNone(result)
        self.assertIn("Hello from voice", result["systemMessage"])

    def test_legacy_result_remains_supported_when_response_is_absent(self):
        result = self.run_hook(tool_result={"path": str(self.voice)})
        self.assertIsNotNone(result)
        self.assertIn("Hello from voice", result["systemMessage"])

    def test_non_voice_and_missing_paths_remain_silent(self):
        music = Path(self.temp.name) / "music.mp3"
        music.write_text("Music", encoding="utf-8")
        for response in ({"path": str(music)}, {"path": str(self.voice) + ".missing.oga"}, ""):
            with self.subTest(response=response):
                self.assertIsNone(self.run_hook(tool_response=response))


if __name__ == "__main__":
    unittest.main()
