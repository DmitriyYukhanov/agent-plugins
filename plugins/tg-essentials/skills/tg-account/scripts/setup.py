"""Create the venv in ~/.tg-account/venv. Idempotent.

The venv lives outside the plugin so plugin updates do not wipe it.
Run with Python 3.12: python setup.py [--transcribe]
"""
import argparse, pathlib, subprocess, sys, venv

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--transcribe", action="store_true", help="Install local voice/video-note transcription")
args = parser.parse_args()

VENV = pathlib.Path.home() / ".tg-account" / "venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

if not PY.exists():
    venv.create(VENV, with_pip=True)
subprocess.check_call([str(PY), "-m", "pip", "install", "-q", "telethon==1.45.0", "qrcode==8.2"])
if args.transcribe:
    print("Preparing Whisper small for local transcription (first download is about 500 MB)...", flush=True)
    subprocess.check_call([str(PY), str(pathlib.Path(__file__).with_name("tg_transcribe.py")), "--prepare"])
print("ok:", PY)
