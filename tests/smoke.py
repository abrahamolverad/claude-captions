#!/usr/bin/env python3
"""End-to-end smoke test on a synthetic clip (used by CI on Windows and macOS): every script runs and the final video exists.
usage: python tests/smoke.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
S = ROOT / "scripts"


def run(*args):
    print(">", " ".join(map(str, args)), flush=True)
    subprocess.run([sys.executable, *map(str, args)], check=True)


with tempfile.TemporaryDirectory() as tmp:
    w = Path(tmp)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1080x1920:rate=30", "-f", "lavfi",
                    "-i", "sine=frequency=330:sample_rate=48000", "-t", "4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
                    "-shortest", str(w / "raw.mp4")], check=True)
    run(S / "transcribe.py", w / "raw.mp4", w / "raw_words.json", "--model", "tiny")
    run(S / "cut.py", w / "raw.mp4", w / "work", "--model", "tiny")
    work = w / "work"
    words = [{"w": t, "t0": round(0.3 + i * 0.35, 2), "t1": round(0.6 + i * 0.35, 2)}
             for i, t in enumerate("hola mundo esto es una prueba de captions en windows y mac.".split())]
    (work / "words.json").write_text(json.dumps({"words": words}, ensure_ascii=False), encoding="utf-8")
    run(S / "mask.py", work / "talk.mp4", work / "mask.raw", "--engine", "mediapipe")
    run(S / "maps.py", work / "maps", "Spain=españa", "Mexico=méxico")
    shot = Image.new("RGB", (1290, 2000), "white"); ImageDraw.Draw(shot).rectangle((80, 300, 1100, 420), fill=(30, 30, 30))
    (work / "shots").mkdir(); shot.save(work / "shots" / "page.png")
    (work / "broll.json").write_text(json.dumps({"size": "split", "clips": [
        {"name": "page", "src": "shots/page.png", "dur": 1.2, "focus": {"box": [80, 300, 1100, 420], "zoom": 1.2, "t": 0.5},
         "circles": [{"box": [80, 300, 1100, 420], "t": 0.4}], "notes": [{"text": "~70%", "at": [600, 520], "t": 0.6, "px": 80}]},
        {"name": "todo", "dur": 1.0, "checklist": {"title": "qué hacer hoy", "items": [["uno", 0.1], ["dos", 0.5]]}}]}, ensure_ascii=False),
        encoding="utf-8")
    run(S / "broll.py", work / "broll.json")
    (work / "plan.json").write_text(json.dumps({
        "video": "talk.mp4", "words": "words.json", "mask": "mask.raw", "out": "final.mp4",
        "hook": {"lines": [["así se ve", 80, 380, False], ["prueba", 220, 640, True], ["de captions", 80, 1330, False]], "end": 1.0},
        "no_captions": [[0, 1.0]],
        "broll": [{"file": "broll/page.mp4", "at": 1.4, "dur": 1.2, "layout": "split"}, {"file": "broll/todo.mp4", "at": 2.8, "dur": 1.0, "layout": "full"}],
        "floaters": [{"img": "maps/espana.png", "t0": 0, "t1": 1.2, "behind": True, "keys": [[0, 200, 830, 1.0, -6], [1.2, 900, 760, 1.1, 4]]}]},
        ensure_ascii=False), encoding="utf-8")
    run(S / "render.py", work / "plan.json")
    run(S / "frames.py", work / "final.mp4", work / "check.jpg", "0.5", "1.8", "3.2")
    out = work / "final.mp4"
    assert out.exists() and out.stat().st_size > 50_000, "final.mp4 missing"
    print("SMOKE OK", out.stat().st_size, "bytes")
