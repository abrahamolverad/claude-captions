#!/usr/bin/env python3
"""Contact sheet of a video at chosen times, to check the render (hook, every B-roll, close-ups).

usage: frames.py VIDEO OUT.jpg 0.5 3 7.2 ...   [--width 270]
"""
import argparse
import subprocess

from PIL import Image, ImageDraw

from common import need, video_size

ap = argparse.ArgumentParser()
ap.add_argument("video"); ap.add_argument("out"); ap.add_argument("times", nargs="+", type=float); ap.add_argument("--width", type=int, default=270)
a = ap.parse_args()
vw, vh = video_size(a.video)
w = a.width; h = int(vh * w / vw)
tiles = []
for t in a.times:
    r = subprocess.run([need("ffmpeg"), "-loglevel", "error", "-ss", str(t), "-i", a.video, "-frames:v", "1", "-vf", f"scale={w}:{h}",
                        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
    im = Image.frombytes("RGB", (w, h), r.stdout[: w * h * 3]) if len(r.stdout) >= w * h * 3 else Image.new("RGB", (w, h))
    ImageDraw.Draw(im).text((5, 4), f"{t:.2f}s", fill=(255, 255, 0)); tiles.append(im)
cols = min(6, len(tiles)); rows = (len(tiles) + cols - 1) // cols
sheet = Image.new("RGB", (w * cols, h * rows))
for i, im in enumerate(tiles):
    sheet.paste(im, ((i % cols) * w, (i // cols) * h))
sheet.save(a.out, quality=88)
print(a.out, sheet.size)
