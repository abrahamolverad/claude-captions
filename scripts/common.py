"""Shared helpers: paths, ffmpeg, fonts. Works on macOS, Windows and Linux."""
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):          # Windows consoles/pipes default to cp1252: print accents and arrows safely
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
W, H, FPS = 1080, 1920, 30
IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"


def need(tool):
    path = shutil.which(tool)
    if not path:
        hint = {"Darwin": "brew install ffmpeg", "Windows": "winget install Gyan.FFmpeg"}.get(platform.system(), "sudo apt install ffmpeg")
        sys.exit(f"{tool} not found. Install it first: {hint}")
    return path


def ffmpeg(*args, quiet=True):
    cmd = [need("ffmpeg"), "-y", *(["-loglevel", "error"] if quiet else []), *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.exit("ffmpeg failed:\n" + r.stderr[-2000:])
    return r


def duration(path):
    r = subprocess.run([need("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip())


def video_size(path):
    r = subprocess.run([need("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    w, h = r.stdout.strip().split(",")[:2]
    return int(w), int(h)


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(path, data):
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------- fonts ----------
_fonts = {}
HELVETICA = Path("/System/Library/Fonts/HelveticaNeue.ttc")      # macOS system font (not redistributed)
INTER = ASSETS / "fonts" / "Inter-Variable.ttf"                    # SIL OFL, used where Helvetica is missing
HAND = ASSETS / "fonts" / "ArchitectsDaughter-Regular.ttf"         # SIL OFL, handwritten notes


def caption_font(px):
    """Bold sans for captions: Helvetica Neue Bold on a Mac, Inter Bold elsewhere."""
    from PIL import ImageFont
    px = int(round(px))
    key = ("cap", px)
    if key not in _fonts:
        if HELVETICA.exists():
            _fonts[key] = ImageFont.truetype(str(HELVETICA), px, index=1)
        else:
            f = ImageFont.truetype(str(INTER), px)
            f.set_variation_by_name("Bold")
            _fonts[key] = f
    return _fonts[key]


def hand_font(px):
    from PIL import ImageFont
    px = int(round(px))
    key = ("hand", px)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(str(HAND), px)
    return _fonts[key]
