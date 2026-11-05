"""Local voice/video-note transcription with an export-scoped success cache."""
import asyncio
import json
import os
import signal
import subprocess
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from tempfile import TemporaryDirectory


class Transcriber:
    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir) / "small"
        self.worker = None
        self.launch = None
        self.ready = False
        self.error = None

    async def _start(self):
        if self.error:
            raise RuntimeError(self.error)
        if self.launch is None:
            # Isolate native speech libraries from the Telegram client process.
            self.launch = asyncio.create_task(asyncio.create_subprocess_exec(
                sys.executable, "-u", str(Path(__file__).resolve()), "--worker",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, limit=8 * 1024 * 1024,
                start_new_session=sys.platform != "win32",
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            ))
        self.worker = await asyncio.shield(self.launch)
        if not self.ready:
            response = await self.worker.stdout.readline()
            try:
                result = json.loads(response) if response else {"error": "WorkerExit"}
                self.error = result.get("error") or (None if result.get("ready") is True else "WorkerProtocolError")
            except (ValueError, AttributeError):
                self.error = "WorkerProtocolError"
            self.ready = True
            if self.error == "WorkerProtocolError":
                await self.close(force=True)
        if self.worker.returncode is not None:
            self.error = self.error or "WorkerExit"
        if self.error:
            raise RuntimeError(self.error)

    async def _recognize(self, path):
        try:
            self.worker.stdin.write((json.dumps(str(path)) + "\n").encode("utf-8"))
            await self.worker.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self.error = "WorkerExit"
            raise
        response = await self.worker.stdout.readline()
        if not response:
            self.error = "WorkerExit"
            raise RuntimeError("Transcription worker stopped without a result")
        result = json.loads(response)
        if "error" in result:
            raise RuntimeError(result["error"])
        return result["text"]

    async def _close(self, force):
        if self.launch is not None:
            try:
                self.worker = await self.launch
            except Exception:
                return  # A failed spawn has no child to clean up.
            if force and self.worker.returncode is None:
                if sys.platform == "win32":
                    killer = await asyncio.create_subprocess_exec(
                        "taskkill", "/PID", str(self.worker.pid), "/T", "/F",
                        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                    await killer.wait()
                else:
                    try:
                        os.killpg(self.worker.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if self.worker.returncode is None:
                    try:
                        self.worker.kill()
                    except ProcessLookupError:
                        pass
            self.worker.stdin.close()
            await self.worker.wait()

    async def close(self, force=False):
        if self.launch is not None:
            completion = asyncio.create_task(self._close(force))
            cancelled = False
            while not completion.done():
                try:
                    await asyncio.shield(completion)
                except asyncio.CancelledError:
                    cancelled = True
            completion.result()
            if cancelled:
                raise asyncio.CancelledError

    async def transcribe(self, client, message):
        cache = self.cache_dir / f"{message.document.id}.txt"
        try:
            text = cache.read_text(encoding="utf-8").strip()
            if text:
                return " ".join(text.split())
        except (OSError, UnicodeError):
            pass
        try:
            await self._start()
        except asyncio.CancelledError:
            await self.close(force=True)
            raise
        with TemporaryDirectory(prefix="tg-transcribe-") as tmp:
            recognition = None
            try:
                suffix = ".ogg" if message.voice else ".mp4"
                path = await client.download_media(message, file=str(Path(tmp) / ("media" + suffix)))
                if not path:
                    raise FileNotFoundError("Telegram did not return a media file")
                recognition = asyncio.create_task(self._recognize(path))
                text = await asyncio.shield(recognition)
            except asyncio.CancelledError:
                # Stop the decoder before removing a file it may still hold open.
                try:
                    await self.close(force=True)
                finally:
                    if recognition is not None:
                        await asyncio.gather(recognition, return_exceptions=True)
                raise
        if text:
            try:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                with TemporaryDirectory(dir=self.cache_dir, prefix=".write-") as tmp:
                    pending = Path(tmp) / "transcript.txt"
                    pending.write_text(text, encoding="utf-8")
                    pending.replace(cache)
            except OSError as ex:
                print(f"Transcript cache write failed ({type(ex).__name__}); keeping text in the export.", file=sys.stderr)
        return text


def _load_model():
    # PyAV 19 removed metadata_errors, still used by faster-whisper 1.2.1.
    try:
        ready = version("faster-whisper") == "1.2.1" and int(version("av").split(".")[0]) < 19
    except PackageNotFoundError:
        ready = False
    if not ready:
        print("Preparing local voice transcription dependencies...", file=sys.stderr, flush=True)
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "-q", "faster-whisper==1.2.1", "av<19"],
            stdout=sys.stderr,
        )
    from faster_whisper import WhisperModel
    return WhisperModel("small", device="cpu", compute_type="int8")


def _worker():
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        model = _load_model()
    except Exception as ex:
        error = type(ex).__name__
        print(f"Local transcription setup failed ({error}).", file=sys.stderr, flush=True)
        print(json.dumps({"error": error}), flush=True)
        return
    print(json.dumps({"ready": True}), flush=True)
    for line in sys.stdin:
        try:
            segments, _ = model.transcribe(json.loads(line), beam_size=5, vad_filter=True)
            result = {"text": " ".join(" ".join(segment.text.split()) for segment in segments).strip()}
        except Exception as ex:
            result = {"error": type(ex).__name__}
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        _worker()
    elif sys.argv[1:] == ["--prepare"]:
        _load_model()
