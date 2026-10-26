#!/usr/bin/env python3
"""Clean a talking-head video: keep the good takes, cut the pauses, punch in every other cut, even out the voice.

usage: cut.py RAW.mp4 WORKDIR [--keep 3.2-5.8 ...] [--drop 10.9-21.1 ...] [--protect 72.0-72.6 ...]
              [--min-gap 0.25] [--zoom 1.06] [--lang es] [--model small]
  --keep     only these source ranges survive (one per good take, in order). Get the times from transcribe.py on the raw file.
  --drop     remove these source ranges (a repeated line, a mistake)
  --protect  keep the silence inside these ranges (a deliberate dramatic pause)
-> WORKDIR/talk.mp4 (1080x1920, 30 fps, voice at -16 LUFS), WORKDIR/cuts.json, WORKDIR/words.json (cut timeline)
"""
import argparse
import json
import re
import subprocess
from pathlib import Path

from common import duration, ffmpeg, need, save_json
from transcribe import transcribe

ap = argparse.ArgumentParser()
ap.add_argument("raw"); ap.add_argument("work")
ap.add_argument("--keep", action="append", default=[]); ap.add_argument("--drop", action="append", default=[])
ap.add_argument("--protect", action="append", default=[])
ap.add_argument("--min-gap", type=float, default=0.25); ap.add_argument("--keep-gap", type=float, default=0.09)
ap.add_argument("--noise", default="-38dB"); ap.add_argument("--zoom", type=float, default=1.06)
ap.add_argument("--lang", default="es"); ap.add_argument("--model", default="small")
a = ap.parse_args()
raw, work = Path(a.raw), Path(a.work)
work.mkdir(parents=True, exist_ok=True)
rng = lambda s: tuple(map(float, s.split("-")))

dur = duration(raw)
log = subprocess.run([need("ffmpeg"), "-hide_banner", "-nostats", "-i", str(raw), "-af", f"silencedetect=noise={a.noise}:d=0.15",
                      "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", log)]
ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", log)]
sil = list(zip(starts, ends + [dur] * (len(starts) - len(ends))))
prot = [rng(p) for p in a.protect]
sil = [(s, e) for s, e in sil if not any(s < y and e > x for x, y in prot)]

lead = sil[0][1] if sil and sil[0][0] < 0.05 else 0.0
tail = sil[-1][0] if sil and sil[-1][1] >= dur - 0.05 else dur
keep, cur = [], max(0.0, lead - a.keep_gap)
for s, e in sil:
    if s < 0.05 or e >= dur - 0.05:
        continue
    if e - s >= a.min_gap:
        keep.append([cur, s + a.keep_gap]); cur = e - a.keep_gap
keep.append([cur, min(dur, tail + 0.30)])
if a.keep:
    ks = [rng(k) for k in a.keep]
    keep = sorted([max(s, x), min(e, y)] for s, e in keep for x, y in ks if min(e, y) > max(s, x))
for d in a.drop:
    x, y = rng(d)
    nk = []
    for s, e in keep:
        if e <= x or s >= y:
            nk.append([s, e]); continue
        if s < x: nk.append([s, x])
        if e > y: nk.append([y, e])
    keep = nk
keep = [[round(s, 3), round(e, 3)] for s, e in keep if e - s > 0.12]
save_json(work / "cuts.json", keep)
print(f"{len(keep)} segments, kept {sum(e - s for s, e in keep):.2f}s of {dur:.2f}s")

vf, af = [], []
for i, (s, e) in enumerate(keep):
    z = a.zoom if i % 2 else 1.0
    vf.append(f"[0:v]trim={s}:{e},setpts=PTS-STARTPTS,fps=30,scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,"
              f"scale=iw*{z}:ih*{z},crop=1080:1920:(iw-1080)*0.5:(ih-1920)*0.35,setsar=1[v{i}]")
    af.append(f"[0:a]atrim={s}:{e},asetpts=PTS-STARTPTS,afade=t=in:d=0.01,afade=t=out:st={max(0.0, e - s - 0.012):.3f}:d=0.012[a{i}]")
n = len(keep)
voice = ("highpass=f=75,afftdn=nr=12:nf=-32,equalizer=f=230:t=q:w=1.2:g=-2,equalizer=f=3200:t=q:w=1.1:g=2,"
         "acompressor=threshold=-21dB:ratio=3:attack=6:release=90:makeup=3,alimiter=limit=0.89")
graph = ";".join(vf + af + ["".join(f"[v{i}][a{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]",
                            "[vc]eq=contrast=1.03:saturation=1.05,format=yuv420p[vo]", f"[ac]{voice}[ao]"])
(work / "filter.txt").write_text(graph, encoding="utf-8")
pre = work / "talk_pre.mp4"
ffmpeg("-i", raw, "-filter_complex_script", work / "filter.txt", "-map", "[vo]", "-map", "[ao]", "-c:v", "libx264", "-preset", "medium",
       "-crf", "16", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "256k", "-ar", "48000", pre)

r = subprocess.run([need("ffmpeg"), "-hide_banner", "-nostats", "-i", str(pre), "-af", "loudnorm=I=-16:TP=-1.5:LRA=9:print_format=json",
                    "-vn", "-f", "null", "-"], capture_output=True, text=True).stderr
j = json.loads(re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r, re.S).group(0))
ln = (f"loudnorm=I=-16:TP=-1.5:LRA=9:measured_I={j['input_i']}:measured_TP={j['input_tp']}:measured_LRA={j['input_lra']}"
      f":measured_thresh={j['input_thresh']}:offset={j['target_offset']}:linear=true")
ffmpeg("-i", pre, "-c:v", "copy", "-af", ln, "-c:a", "aac", "-b:a", "256k", "-ar", "48000", work / "talk.mp4")
pre.unlink(); (work / "filter.txt").unlink()

d = transcribe(work / "talk.mp4", work / "words.json", a.lang, a.model)
print(f"talk.mp4 {duration(work / 'talk.mp4'):.2f}s, {len(d['words'])} words")
for t0, t1, txt in d["segments"]:
    print(f"{t0:7.2f}-{t1:7.2f}  {txt}")
