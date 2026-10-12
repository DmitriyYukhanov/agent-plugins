"""Run with python -m unittest discover -s this_folder."""
import contextlib
import asyncio
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
import sys
import time
import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from telethon.tl import types
import tg_export
import tg_transcribe


DATE = dt.datetime(2026, 10, 4, 12, tzinfo=dt.timezone.utc)
CANCEL_TIMEOUT = 5  # Windows taskkill can take over two seconds to stop the process tree.

FAKE_WHISPER = '''
import json, pathlib, time
from types import SimpleNamespace
root = pathlib.Path(__file__).parent
class WhisperModel:
    def __init__(self, *args, **kwargs):
        with (root / "loads").open("a") as f:
            f.write("loaded\\n")
        self.control = json.loads((root / "control.json").read_text())
        if self.control.get("bad_ready"):
            print(self.control["bad_ready"], flush=True)
        if self.control.get("block_setup"):
            (root / "started").touch()
            time.sleep(30)
        if self.control.get("exit_after_ready"):
            import os, threading
            threading.Timer(0.05, lambda: os._exit(17)).start()
        if self.control.get("setup_error"):
            raise OSError("private model download error")
    def transcribe(self, path, **options):
        if self.control.get("crash"):
            import os
            os._exit(17)
        if self.control.get("inference_error"):
            raise RuntimeError("private inference error")
        with open(path, "r", encoding="utf-8") as f:
            docid = f.read()
            if self.control.get("block"):
                (root / "started").touch()
                deadline = time.monotonic() + 5
                while not (root / "release").exists() and time.monotonic() < deadline:
                    time.sleep(0.01)
        text = self.control.get("text", "Transcript\\n" + docid)
        segments = [SimpleNamespace(text=text)] if self.control.get("speech", True) else []
        return iter(segments), SimpleNamespace(language="en")
'''


def message(mid, kind=None, docid=None, caption=""):
    attributes = {
        "voice": types.DocumentAttributeAudio(duration=5, voice=True),
        "video_note": types.DocumentAttributeVideo(duration=5, w=240, h=240, round_message=True),
        "video": types.DocumentAttributeVideo(duration=5, w=640, h=480),
        "audio": types.DocumentAttributeAudio(duration=5, voice=False),
    }
    media = None
    if kind:
        document = types.Document(
            id=docid or mid, access_hash=0, file_reference=b"", date=DATE,
            mime_type="audio/ogg" if kind in ("voice", "audio") else "video/mp4",
            size=10, dc_id=2, attributes=[attributes[kind]],
        )
        media = types.MessageMediaDocument(document=document)
    return types.Message(id=mid, peer_id=types.PeerUser(42), date=DATE, message=caption, media=media)


class Client:
    def __init__(self, messages, download_error=False, missing_media=False, download_delay=0):
        self.messages = sorted(messages, key=lambda m: m.id, reverse=True)
        self.download_error = download_error
        self.missing_media = missing_media
        self.download_delay = download_delay
        self.downloads = []
        self.disconnected = False

    async def get_messages(self, entity, limit, offset_id=0):
        return [m for m in self.messages if not offset_id or m.id < offset_id][:limit]

    async def download_media(self, m, file):
        self.downloads.append(pathlib.Path(file))
        if self.download_delay:
            await asyncio.to_thread(time.sleep, self.download_delay)
        if self.download_error:
            raise OSError("private download error")
        if self.missing_media:
            return None
        pathlib.Path(file).write_text(str(m.document.id), encoding="utf-8")
        return str(file)

    async def disconnect(self):
        self.disconnected = True


class ExportTranscription(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = pathlib.Path(self.temp.name)
        self.model_loads = 0
        self.speech = True
        self.inference_error = False
        self.control = {}
        self.workers = []
        (self.out / "faster_whisper.py").write_text(FAKE_WHISPER, encoding="utf-8")
        for package, value in (("faster_whisper", "1.2.1"), ("av", "18.1.0")):
            metadata = self.out / f"{package}-{value}.dist-info"
            metadata.mkdir()
            (metadata / "METADATA").write_text(f"Name: {package.replace('_', '-')}\nVersion: {value}\n")

    async def export(self, messages, transcribe=True, account=1, peer=None, **client_options):
        client = Client(messages, **client_options)
        self.last_client = client
        output = io.StringIO()
        entity = peer or types.User(id=42, first_name="Example")
        (self.out / "control.json").write_text(json.dumps({"speech": self.speech, "inference_error": self.inference_error, **self.control}))
        loads = self.out / "loads"
        before = len(loads.read_text().splitlines()) if loads.exists() else 0
        start_process = asyncio.create_subprocess_exec

        async def start(*args, **kwargs):
            kwargs["env"] = {**os.environ, "PYTHONPATH": str(self.out)}
            worker = await start_process(*args, **kwargs)
            self.workers.append(worker)
            return worker

        with patch("tgsess.open_chat", AsyncMock(return_value=(client, entity, account))), \
                patch.object(asyncio, "create_subprocess_exec", side_effect=start), \
                patch.object(tg_export.asyncio, "sleep", AsyncMock()), contextlib.redirect_stdout(output):
            options = {} if transcribe is None else {"transcribe": transcribe}
            await tg_export.main("example", "2026-10-04", self.out, **options)
        after = len(loads.read_text().splitlines()) if loads.exists() else 0
        self.model_loads += after - before
        self.assertTrue(all(worker.returncode is not None for worker in self.workers))
        self.assertTrue(client.disconnected)
        files = list(self.out.glob("????-??-??.txt"))
        text = files[0].read_text(encoding="utf-8") if files else ""
        return text, client, output.getvalue()

    async def test_default_export_includes_voice_and_video_in_context(self):
        text, _, _ = await self.export(
            [message(1, caption="Before"), message(2, "voice"), message(3, "video_note"), message(4, caption="After")],
            transcribe=None,
        )
        self.assertIn("[voice] Transcript 2", text)
        self.assertIn("[video note] Transcript 3", text)
        self.assertEqual([int(line.split("#")[1].split()[0]) for line in text.splitlines()], [1, 2, 3, 4])

    async def test_text_only_keeps_media_and_caption_without_whisper(self):
        messages = [message(2, "voice"), message(1, "video_note", caption="Caption\nline")]
        text, client, output = await self.export(messages, transcribe=False)
        self.assertIn("#1 ?: Caption line\n", text)
        self.assertTrue(text.endswith("#2 ?: [media]"))
        self.assertEqual(client.downloads, [])
        self.assertEqual(self.model_loads, 0)
        self.assertNotIn("transcribed=", output)

    async def test_voice_and_video_note_keep_ids_replies_and_captions(self):
        video = message(2, "video_note", caption="Caption")
        video.reply_to = types.MessageReplyHeader(reply_to_msg_id=1)
        text, client, output = await self.export([message(1, "voice"), video])
        self.assertIn("#1 ?: [voice] Transcript 1", text)
        self.assertIn("#2 ->#1 ?: Caption [video note] Transcript 2", text)
        self.assertEqual(self.model_loads, 1)
        self.assertTrue(all(not path.exists() for path in client.downloads))
        self.assertIn("transcribed=2", output)

    async def test_success_cache_avoids_download_and_model_on_rerun(self):
        await self.export([message(1, "voice")])
        self.model_loads = 0
        text, client, _ = await self.export([message(1, "voice")])
        self.assertIn("Transcript 1", text)
        self.assertEqual(client.downloads, [])
        self.assertEqual(self.model_loads, 0)

    async def test_default_text_chat_does_not_start_whisper(self):
        text, client, _ = await self.export([message(1, caption="Only text")], transcribe=None)
        self.assertIn("Only text", text)
        self.assertEqual(client.downloads, [])
        self.assertEqual(self.workers, [])

    async def test_unicode_and_long_speech_survive_worker_pipe(self):
        self.control["text"] = "Привет 🌿 " * 10000
        text, _, _ = await self.export([message(1, "voice")])
        self.assertIn("[voice] " + self.control["text"].strip(), text)

    async def test_setup_failure_is_attempted_once_and_text_survives(self):
        self.control["setup_error"] = True
        text, client, output = await self.export([message(1, "voice"), message(2, "video_note"), message(3, caption="Text survives")])
        self.assertEqual(text.count("transcription failed"), 2)
        self.assertIn("Text survives", text)
        self.assertNotIn("private model download error", text)
        self.assertIn("transcription_failures=2", output)
        self.assertEqual(self.model_loads, 1)
        self.assertEqual(len(self.workers), 1)
        self.assertEqual(client.downloads, [])

    async def test_worker_crash_is_visible_without_restart_loop(self):
        self.control["crash"] = True
        text, client, _ = await self.export([message(1, "voice"), message(2, "video_note"), message(3, caption="Text survives")])
        self.assertEqual(text.count("transcription failed"), 2)
        self.assertIn("Text survives", text)
        self.assertEqual(len(self.workers), 1)
        self.assertTrue(all(not path.exists() for path in client.downloads))

    async def test_worker_exit_after_readiness_stops_later_downloads(self):
        self.control["exit_after_ready"] = True
        text, client, _ = await self.export([message(1, "voice"), message(2, "video_note")], download_delay=0.2)
        self.assertEqual(text.count("transcription failed"), 2)
        self.assertLessEqual(len(client.downloads), 1)
        self.assertEqual(len(self.workers), 1)

    async def test_invalid_readiness_stops_worker_and_all_downloads(self):
        for response in ("not JSON", "[]", '{"text": "unexpected"}'):
            with self.subTest(response=response):
                self.control["bad_ready"] = response
                text, client, _ = await self.export([message(1, "voice"), message(2, "video_note")])
                self.assertEqual(text.count("transcription failed"), 2)
                self.assertEqual(client.downloads, [])

    async def test_cache_separates_account_chat_type_and_replaced_document(self):
        await self.export([message(1, "voice", docid=7)])
        for account, peer, docid in (
            (2, types.User(id=42), 7),
            (1, types.Chat(id=42, title="Group", photo=types.ChatPhotoEmpty(), participants_count=2, date=DATE, version=1), 7),
            (1, types.User(id=42), 8),
        ):
            with self.subTest(account=account, peer=type(peer).__name__, docid=docid):
                text, client, _ = await self.export([message(1, "voice", docid=docid)], account=account, peer=peer)
                self.assertIn(f"Transcript {docid}", text)
                self.assertEqual(len(client.downloads), 1)

    async def test_download_failure_is_visible_and_retried(self):
        text, client, output = await self.export([message(1, "voice")], download_error=True)
        self.assertIn("[voice: transcription failed", text)
        self.assertNotIn("private download error", text)
        self.assertIn("transcription_failures=1", output)
        self.assertTrue(client.disconnected)
        text, client, _ = await self.export([message(1, "voice")])
        self.assertIn("Transcript 1", text)
        self.assertEqual(len(client.downloads), 1)

    async def test_missing_media_is_visible(self):
        text, _, _ = await self.export([message(1, "video_note")], missing_media=True)
        self.assertIn("[video note: transcription failed", text)

    async def test_inference_failure_deletes_media_and_continues(self):
        self.inference_error = True
        text, client, _ = await self.export([message(1, "voice"), message(2, caption="Plain text")])
        self.assertIn("[voice: transcription failed", text)
        self.assertIn("#2 ?: Plain text", text)
        self.assertNotIn("private inference error", text)
        self.assertTrue(all(not path.exists() for path in client.downloads))

    async def test_no_speech_is_visible_and_not_cached(self):
        self.speech = False
        text, _, _ = await self.export([message(1, "voice")])
        self.assertIn("[voice: no speech detected]", text)
        self.speech = True
        text, client, _ = await self.export([message(1, "voice")])
        self.assertIn("Transcript 1", text)
        self.assertEqual(len(client.downloads), 1)

    async def test_regular_audio_video_and_old_notes_are_not_downloaded(self):
        old = message(1, "voice")
        old.date = DATE - dt.timedelta(days=1)
        text, client, _ = await self.export([old, message(2, "audio"), message(3, "video")])
        self.assertNotIn("#1", text)
        self.assertEqual(text.count("[media]"), 2)
        self.assertEqual(client.downloads, [])
        self.assertEqual(self.model_loads, 0)

    async def test_corrupt_cache_is_rebuilt(self):
        await self.export([message(1, "voice")])
        cache = next((self.out / ".transcripts").rglob("1.txt"))
        cache.write_bytes(b"\xff")
        text, client, _ = await self.export([message(1, "voice")])
        self.assertIn("Transcript 1", text)
        self.assertEqual(len(client.downloads), 1)
        self.assertEqual(cache.read_text(encoding="utf-8"), "Transcript 1")

    async def test_cache_write_failure_preserves_recognized_text(self):
        with patch.object(pathlib.Path, "replace", side_effect=OSError("private disk error")), \
                contextlib.redirect_stderr(io.StringIO()) as warnings:
            text, client, output = await self.export([message(1, "voice")])
        self.assertIn("[voice] Transcript 1", text)
        self.assertIn("transcription_failures=0", output)
        self.assertIn("cache", warnings.getvalue().lower())
        self.assertNotIn("private disk error", warnings.getvalue())
        self.assertTrue(all(not path.exists() for path in client.downloads))

    async def test_history_error_disconnects_client(self):
        client = Client([])
        with patch("tgsess.open_chat", AsyncMock(return_value=(client, types.User(id=42), 1))), \
                patch.object(client, "get_messages", AsyncMock(side_effect=OSError("history unavailable"))), \
                contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(OSError):
                await tg_export.main("example", "2026-10-04", self.out)
        self.assertTrue(client.disconnected)

    async def test_cancel_waits_for_decoder_before_deleting_media(self):
        self.control["block"] = True
        task = asyncio.create_task(self.export([message(1, "voice")]))

        def wait_for_decoder():
            deadline = time.monotonic() + 3
            while not (self.out / "started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            return (self.out / "started").exists()

        try:
            self.assertTrue(await asyncio.to_thread(wait_for_decoder))
            task.cancel()
            yielded = asyncio.get_running_loop().create_future()
            asyncio.get_running_loop().call_soon(yielded.set_result, None)
            await yielded
            task.cancel()
            done, _ = await asyncio.wait([task], timeout=CANCEL_TIMEOUT)
            self.assertIn(task, done, "Cancellation must stop a stalled decoder")
            with self.assertRaises(asyncio.CancelledError):
                await task
        finally:
            (self.out / "release").touch()
            await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(all(not path.exists() for path in self.last_client.downloads))
        self.assertTrue(self.last_client.disconnected)
        self.assertTrue(all(worker.returncode is not None for worker in self.workers))

    async def test_cancel_stops_worker_before_removing_partial_download(self):
        started = asyncio.Event()
        cleanup_worker_exits = []

        async def download(client, m, file):
            client.downloads.append(pathlib.Path(file))
            pathlib.Path(file).write_text("partial", encoding="utf-8")
            started.set()
            await asyncio.Future()

        @contextlib.contextmanager
        def temporary_directory(**kwargs):
            with TemporaryDirectory(**kwargs) as path:
                try:
                    yield path
                finally:
                    cleanup_worker_exits.append(all(worker.returncode is not None for worker in self.workers))

        with patch.object(Client, "download_media", download), \
                patch.object(tg_transcribe, "TemporaryDirectory", temporary_directory):
            task = asyncio.create_task(self.export([message(1, "voice")]))
            try:
                await asyncio.wait_for(started.wait(), timeout=3)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await asyncio.wait_for(task, timeout=CANCEL_TIMEOUT)
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        self.assertEqual(cleanup_worker_exits, [True])
        self.assertTrue(all(not path.exists() for path in self.last_client.downloads))
        self.assertTrue(self.last_client.disconnected)

    async def test_cancel_stops_stalled_model_preparation_before_media_download(self):
        self.control["block_setup"] = True
        task = asyncio.create_task(self.export([message(1, "voice")]))

        def wait_for_setup():
            deadline = time.monotonic() + 3
            while not (self.out / "started").exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            return (self.out / "started").exists()

        self.assertTrue(await asyncio.to_thread(wait_for_setup))
        task.cancel()
        done, _ = await asyncio.wait([task], timeout=CANCEL_TIMEOUT)
        self.assertIn(task, done)
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(self.last_client.downloads, [])
        self.assertTrue(self.last_client.disconnected)
        self.assertTrue(all(worker.returncode is not None for worker in self.workers))


class ExportCLI(unittest.TestCase):
    def test_help_exits_successfully_without_connecting(self):
        result = subprocess.run(
            [sys.executable, str(pathlib.Path(__file__).with_name("tg_export.py")), "--help"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class AutomaticSetup(unittest.TestCase):
    def test_ready_dependencies_skip_pip_and_allow_model_download(self):
        model = Mock()
        with patch.object(tg_transcribe, "version", side_effect=["1.2.1", "18.1.0"]), \
                patch.object(tg_transcribe.subprocess, "check_call") as install, \
                patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=model)}):
            tg_transcribe._load_model()
        install.assert_not_called()
        model.assert_called_once_with("small", device="cpu", compute_type="int8")

    def test_missing_or_incompatible_dependencies_install_in_current_interpreter(self):
        for versions in (tg_transcribe.PackageNotFoundError("faster-whisper"), ["1.2.1", "19.0.1"], ["1.1.0"]):
            with self.subTest(versions=versions), \
                    patch.object(tg_transcribe, "version", side_effect=versions), \
                    patch.object(tg_transcribe.subprocess, "check_call") as install, \
                    patch.dict(sys.modules, {"faster_whisper": SimpleNamespace(WhisperModel=Mock())}), \
                    contextlib.redirect_stderr(io.StringIO()):
                tg_transcribe._load_model()
            self.assertEqual(install.call_count, 1)
            self.assertEqual(install.call_args.args[0], [sys.executable, "-m", "pip", "install", "-q", "faster-whisper==1.2.1", "av<19"])


if __name__ == "__main__":
    unittest.main()
