#!/usr/bin/env python3
"""PostToolUse hook: transcribe Telegram voice messages using faster-whisper."""

import json
import os
import sys

# Telegram voice messages are always Opus-in-Ogg (.oga).
# This deliberately excludes other audio formats (.mp3, .wav, etc.)
# so the hook only fires for voice messages, not for music or audio documents.
VOICE_EXTENSIONS = {".oga"}
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")


def main():
    try:
        hook_input = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        return

    tool_response = hook_input.get("tool_response", hook_input.get("tool_result", ""))
    if isinstance(tool_response, dict):
        file_path = tool_response.get("path", tool_response.get("file_path", ""))
    else:
        file_path = str(tool_response).strip()

    if not file_path:
        return

    ext = os.path.splitext(file_path)[1].lower()
    if ext not in VOICE_EXTENSIONS:
        return  # not a voice message, skip silently

    if not os.path.isfile(file_path):
        return

    # Check if faster-whisper is installed
    try:
        from faster_whisper import WhisperModel  # noqa: F811
    except ImportError:
        json.dump(
            {
                "systemMessage": (
                    "Voice message received but faster-whisper is not installed.\n"
                    "Ask the user to run /voice-to-text-config (tg-voice skill) to set it up,\n"
                    "or install manually: pip install faster-whisper"
                )
            },
            sys.stdout,
        )
        return

    # Check if model is cached to avoid slow first-run downloads inside the hook timeout
    try:
        from huggingface_hub import try_to_load_from_cache

        repo = f"Systran/faster-whisper-{MODEL_SIZE}"
        cached = try_to_load_from_cache(repo, "model.bin")
        if cached is None:
            json.dump(
                {
                    "systemMessage": (
                        f"Voice message received but the whisper '{MODEL_SIZE}' model is not downloaded yet.\n"
                        "Ask the user to run /voice-to-text-config (tg-voice skill) to download it,\n"
                        f"or download manually:\n"
                        f"  python -c \"from faster_whisper import WhisperModel; WhisperModel('{MODEL_SIZE}')\""
                    )
                },
                sys.stdout,
            )
            return
    except ImportError:
        pass  # huggingface_hub not available, proceed and let whisper handle it

    try:
        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
        segments, info = model.transcribe(file_path, beam_size=5)
        text = " ".join(seg.text.strip() for seg in segments)
    except Exception as exc:
        json.dump(
            {"systemMessage": f"Voice transcription failed: {exc}"},
            sys.stdout,
        )
        return

    if not text.strip():
        json.dump(
            {"systemMessage": "Voice message was empty or could not be transcribed."},
            sys.stdout,
        )
        return

    lang = getattr(info, "language", "unknown")
    prob = getattr(info, "language_probability", 0)
    transcription = (
        f"Voice message transcription "
        f"(language: {lang}, confidence: {prob:.0%}):\n\n{text}"
    )
    json.dump(
        {
            "systemMessage": transcription,
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": transcription,
            },
        },
        sys.stdout,
    )


if __name__ == "__main__":
    main()
