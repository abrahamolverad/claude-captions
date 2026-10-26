#!/usr/bin/env python3
"""First-run setup: checks ffmpeg and builds the skill's own Python environment (.venv inside the skill folder).

usage: python3 scripts/setup.py          (Windows: py -3.12 scripts\\setup.py)
Needs Python 3.10, 3.11 or 3.12 (MediaPipe does not publish wheels for newer versions yet).
"""
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"
PY = VENV / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")

if not ((3, 10) <= sys.version_info[:2] <= (3, 12)):
    sys.exit(f"Python {sys.version.split()[0]} found. Run this with Python 3.10–3.12, e.g. `python3.12 scripts/setup.py` "
             "(Windows: `py -3.12 scripts\\setup.py`).")

missing = [t for t in ("ffmpeg", "ffprobe") if not shutil.which(t)]
if missing:
    hint = {"darwin": "brew install ffmpeg", "win32": "winget install Gyan.FFmpeg  (then open a new terminal)"}.get(sys.platform, "sudo apt install ffmpeg")
    sys.exit(f"Missing {', '.join(missing)}. Install it first: {hint}")

if not PY.exists():
    print("Creating", VENV)
    venv.create(VENV, with_pip=True)
subprocess.run([str(PY), "-m", "pip", "install", "-q", "--upgrade", "pip"], check=True)
subprocess.run([str(PY), "-m", "pip", "install", "-q", "-r", str(ROOT / "requirements.txt")], check=True)
subprocess.run([str(PY), "-c", "import numpy, PIL, mediapipe, faster_whisper; print('ok: numpy, pillow, mediapipe, faster-whisper')"], check=True)
print(f"\nReady. Run the scripts with: {PY}")
