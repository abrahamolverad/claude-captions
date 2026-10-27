#!/usr/bin/env python3
"""Video effects on the cut talking video, applied BEFORE the captions so the text stays sharp and in place:
punch-in zoom (close in / close out), black and white ranges, cuts to black, colour tints.

usage: fx.py FX.json            (paths inside the file are relative to it)

FX = {
  "video": "talk.mp4", "out": "talk_fx.mp4",
  "zoom": [{"at": 8.08, "back": 9.04, "scale": 1.3, "dur": 0.35, "cy": 0.42}],
        zoom in at "at" over "dur" seconds, hold, zoom back out at "back" (omit "back" to stay in); cy = vertical centre (0.42 ≈ the face)
  "bw": [[18.78, 22.2]],                        black and white between those times
  "black": [[17.98, 18.18]],                    hard cut to black (a few frames)
  "tint": [{"t0": 5.5, "t1": 6.4, "hue": 215, "mix": 0.5}]   flat colour wash (hue 0-360) — strong on purpose
}
Frame count and audio are untouched, so words.json still matches.
"""
import sys
from pathlib import Path

from common import FPS, H, W, duration, ffmpeg, filter_script, load_json

fx_path = Path(sys.argv[1]).resolve()
F = load_json(fx_path)
base = fx_path.parent
rel = lambda p: (base / p) if not Path(p).is_absolute() else Path(p)
video, out = rel(F["video"]), rel(F.get("out", "talk_fx.mp4"))
END = duration(video)

chain = []
zooms = F.get("zoom", [])
if zooms:
    terms = []
    for z in zooms:
        a = int(round(z["at"] * FPS)); n = max(1, int(round(z.get("dur", 0.35) * FPS)))
        s = float(z.get("scale", 1.3)) - 1.0
        t = f"{s}*clip((in-{a})/{n},0,1)"
        if z.get("back") is not None:
            b = int(round(z["back"] * FPS)); m = max(1, int(round(z.get("dur_out", z.get("dur", 0.35)) * FPS)))
            t += f"-{s}*clip((in-{b})/{m},0,1)"
        terms.append(t)
    cy = float(zooms[0].get("cy", 0.42))
    chain.append(f"zoompan=z='1+{'+'.join(terms)}':x='iw/2-(iw/zoom/2)':y='ih*{cy}-(ih/zoom)*{cy}':d=1:s={W}x{H}:fps={FPS}")
for tnt in F.get("tint", []):
    chain.append(f"colorize=hue={float(tnt['hue'])}:saturation={float(tnt.get('saturation', 0.65))}:lightness=0.5:"
                 f"mix={float(tnt.get('mix', 0.5))}:enable='between(t,{tnt['t0']},{tnt['t1']})'")
for a, b in F.get("bw", []):
    chain.append(f"hue=s=0:enable='between(t,{a},{b})'")
for a, b in F.get("black", []):
    chain.append(f"drawbox=c=black:t=fill:enable='between(t,{a},{b})'")
if not chain:
    chain.append("null")

script = base / "_fx.txt"
script.write_text("[0:v]" + ",".join(chain) + "[v]", encoding="utf-8")
ffmpeg("-i", video, *filter_script(script), "-map", "[v]", "-map", "0:a?", "-c:v", "libx264", "-crf", "12", "-preset", "fast",
       "-pix_fmt", "yuv420p", "-c:a", "copy", "-t", f"{END:.3f}", out)
script.unlink()
print("wrote", out, f"({len(zooms)} zoom, {len(F.get('bw', []))} b&w, {len(F.get('black', []))} black, {len(F.get('tint', []))} tint)")
