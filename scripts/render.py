#!/usr/bin/env python3
"""Render the final video: captions (word by word, one big key word per block), hook text behind the speaker's head,
floating sprites (maps), full-screen or split-screen B-roll and optional sound effects.

usage: render.py PLAN.json            (paths inside the plan are relative to the plan file)

PLAN = {
  "video": "talk.mp4", "words": "words.json", "mask": "mask.raw", "out": "final.mp4",
  "hook": {"lines": [["black october:", 80, 380, false], ["alerta", 260, 650, true], ["en +10 países", 80, 1330, false]], "end": 3.5},
        each line = [text, size px, baseline y, behind the person?]; shown from frame 0 until "end"
  "no_captions": [[0, 3.5]],                       time ranges without word captions (the hook already says it)
  "emphasis": ["alerta", "millones"],              preferred big words (otherwise the longest content word of each block)
  "keep_caps": ["PHP", "IA"], "replace": {"Redway": "Railway"}, "keep_together": [["black", "october"]], "retime": {"funciona.": 22.75},
  "style": {"small": 72, "big": 150, "max_w": 860, "max_words": 4, "body_y": 1340, "broll_y": 1420,
            "seam_y": 960, "split_y0": 400, "seam_small": 62, "seam_big": 124},
  "broll": [{"file": "broll/headline.mp4", "at": 4.45, "dur": 2.4, "layout": "split" | "full"}],
  "floaters": [{"img": "maps/espana.png", "t0": 0, "t1": 2.6, "behind": true, "keys": [[0, 200, 830, 1.15, -6], [2.6, 1260, 760, 1.3, 4]]}],
        keys = [t, x, y, scale, rotation]: the sprite's centre drifts between keys
  "sfx": [{"file": "sfx/whoosh.mp3", "at": 0.0, "vol": 0.4}]
}
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from common import FPS, H, W, caption_font, duration, ffmpeg, filter_script, load_json, need

plan_path = Path(sys.argv[1]).resolve()
P = load_json(plan_path)
base = plan_path.parent
rel = lambda p: (base / p) if not Path(p).is_absolute() else Path(p)
ST = {"small": 72, "big": 150, "max_w": 860, "max_words": 4, "body_y": 1340, "broll_y": 1420,
      "seam_y": 960, "split_y0": 400, "seam_small": 62, "seam_big": 124, **P.get("style", {})}
TRACK, GAP = -0.025, 0.35

video = rel(P["video"])
END = duration(video)
OUT = rel(P.get("out", "final.mp4"))


def text_w(t, px):
    f = caption_font(px)
    return sum(f.getlength(c) for c in t) + TRACK * px * (len(t) - 1)


def sprite(t, px, shadow=150, blur=10):
    f = caption_font(px)
    asc, desc = f.getmetrics()
    w, h = int(text_w(t, px)) + 2 * blur + 8, asc + desc + 2 * blur + 8
    txt = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(txt); x = blur + 4
    for c in t:
        d.text((x, blur + 4), c, font=f, fill="white"); x += f.getlength(c) + TRACK * px
    a = Image.fromarray(np.asarray(txt)[..., 3]).filter(ImageFilter.GaussianBlur(blur))
    a = Image.fromarray((np.asarray(a).astype(float) * shadow / 255).astype(np.uint8))
    out = Image.new("RGBA", (w, h + 4), (0, 0, 0, 0))
    out.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 4), a)
    out.alpha_composite(txt, (0, 0))
    return out, blur + 4 + asc


# ---------- words ----------
words = load_json(rel(P["words"]))["words"]
merged = []
for w in words:                                   # «70» + «%» -> «70%»
    if merged and w["w"].strip() in ("%", "%.", "%,"):
        merged[-1] = {**merged[-1], "w": merged[-1]["w"] + w["w"].strip(), "t1": w["t1"]}
    else:
        merged.append(dict(w))
words = merged
for w in words:
    core = w["w"].strip("¿¡.,?!…")
    if core in P.get("replace", {}):
        w["w"] = w["w"].replace(core, P["replace"][core])
    if w["w"] in P.get("retime", {}):
        w["t0"] = P["retime"][w["w"]]
KEEP_CAPS = set(P.get("keep_caps", []))
EMPH = set(P.get("emphasis", []))
FUNC = set(P.get("function_words", [])) or {
    "a", "al", "el", "la", "los", "las", "un", "una", "de", "del", "y", "o", "que", "en", "mi", "tu", "su", "ese", "esa", "este", "esta",
    "le", "lo", "con", "por", "para", "te", "me", "ni", "se", "es", "cómo", "quién", "cuántos", "muy", "va", "vas", "sí",
    "the", "an", "of", "to", "and", "or", "in", "on", "for", "with", "is", "it", "you", "your", "my", "that", "this", "at", "by", "be", "are"}


def clean(s):
    s = s.strip().strip("¿¡").rstrip(".,?!…")
    return s if s in KEEP_CAPS else s.lower()


nocap = [tuple(r) for r in P.get("no_captions", [])]
ws = [w for w in words if not any(a <= w["t0"] < b for a, b in nocap) and clean(w["w"])]
KEEP = {tuple(p) for p in P.get("keep_together", [])}
chunks, cur = [], []
for w in ws:
    full = len(cur) >= ST["max_words"] and any(clean(x["w"]) not in FUNC for x in cur) and (clean(cur[-1]["w"]), clean(w["w"])) not in KEEP
    if cur and (w["t0"] - cur[-1]["t1"] > GAP or full):
        carry = []
        if w["t0"] - cur[-1]["t1"] <= GAP:
            while len(cur) > 1 and clean(cur[-1]["w"]) in FUNC:
                carry.insert(0, cur.pop())
        chunks.append(cur); cur = carry
    cur.append(w)
    if w["w"].endswith((".", ",", "?", "!")):
        chunks.append(cur); cur = []
if cur:
    chunks.append(cur)

BROLL = [(o["at"], o["at"] + o["dur"]) for o in P.get("broll", [])]
SPLIT = [(o["at"], o["at"] + o["dur"]) for o in P.get("broll", []) if o.get("layout") == "split"]
inside = lambda t, rs: any(a <= t < b for a, b in rs)

blocks, starts, prev_end = [], [c[0]["t0"] for c in chunks] + [END + 1], 0.0
for ci, c in enumerate(chunks):
    texts = [clean(x["w"]) for x in c]
    content = [i for i, t in enumerate(texts) if t not in FUNC]
    pick = [i for i in content if texts[i] in EMPH] or content or [len(texts) - 1]
    big = max(pick, key=lambda i: len(texts[i]))
    c0 = max(prev_end, c[0]["t0"] - 0.03)
    nxt = starts[ci + 1] - 0.03
    c1 = min(END, nxt if nxt - c[-1]["t1"] <= GAP else c[-1]["t1"] + 0.18)
    prev_end = c1
    split, broll = inside(c0 + 0.07, SPLIT), inside(c0 + 0.07, BROLL)
    sm, bg_ = (ST["seam_small"], ST["seam_big"]) if split else (ST["small"], ST["big"])
    lines = []
    for grp, px in ((list(range(0, big)), sm), ([big], bg_), (list(range(big + 1, len(texts))), sm)):
        if not grp:
            continue
        if px == bg_:
            px = min(bg_, bg_ * ST["max_w"] / max(1, text_w(texts[big], bg_)))
        line = []
        for i in grp:
            if line and text_w(" ".join(texts[j] for j in line + [i]), px) > ST["max_w"]:
                lines.append((line, px)); line = []
            line.append(i)
        lines.append((line, px))
    space = lambda px: caption_font(px).getlength(" ") * 0.9
    heights = [px * 0.86 for _, px in lines]
    y = -(sum(heights) + 0.10 * sm * (len(lines) - 1)) / 2
    items = []
    for (line, px), lh in zip(lines, heights):
        x = -(sum(text_w(texts[i], px) for i in line) + space(px) * (len(line) - 1)) / 2
        for i in line:
            blur = 14 if broll else 10
            spr, b0 = sprite(texts[i], px, shadow=210 if broll else 150, blur=blur)
            items.append({"spr": spr, "x": x - (blur + 4), "base": b0, "baseline": y + lh, "t_in": c0 if i == 0 else c[i]["t0"] - 0.03})
            x += text_w(texts[i], px) + space(px)
        y += lh + 0.10 * sm
    cy = ST["seam_y"] if split else (ST["broll_y"] if broll else ST["body_y"])
    blocks.append({"t0": c0, "t1": c1, "cy": cy, "items": items, "text": " ".join(texts)})

# ---------- hook, floaters ----------
HOOK = P.get("hook", {"lines": [], "end": 0})
hook_items = []
for text, px, base_y, behind in HOOK["lines"]:
    spr, b0 = sprite(text, px, shadow=120 if behind else 170, blur=12)
    hook_items.append((spr, int(base_y - b0), behind))
    if W / 2 + spr.width / 2 - 14 > 990:
        print(f"warning: hook line {text!r} is {spr.width - 28}px wide, it may be cut by the screen edge or Instagram's buttons")
FLOATERS = [{**f, "im": Image.open(rel(f["img"])).convert("RGBA")} for f in P.get("floaters", [])]
LAYER_END = max([HOOK.get("end", 0)] + [f["t1"] for f in FLOATERS])
mask_path = rel(P["mask"]) if P.get("mask") else None
masks = np.memmap(mask_path, dtype=np.uint8, mode="r").reshape(-1, 960, 540) if mask_path and mask_path.exists() else None
if masks is None and (any(b for *_, b in HOOK["lines"]) or any(f.get("behind") for f in FLOATERS)):
    print("warning: no mask file, 'behind' text and sprites are drawn in front of the person (run mask.py)")


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def paste(layer, im, x, y):
    l, t = max(0, -x), max(0, -y)
    r, b = min(im.width, W - x), min(im.height, H - y)
    if r > l and b > t:
        layer.alpha_composite(im.crop((l, t, r, b)), (x + l, y + t))


def float_at(f, t):
    ks = f["keys"]; v = ks[-1][1:]
    if t <= ks[0][0]:
        v = ks[0][1:]
    else:
        for a, b in zip(ks, ks[1:]):
            if t <= b[0]:
                u = (t - a[0]) / max(1e-6, b[0] - a[0]); u = u * u * (3 - 2 * u) * 0.35 + u * 0.65
                v = tuple(p + (q - p) * u for p, q in zip(a[1:], b[1:])); break
    x, y, sc, rot = v
    y += 9 * math.sin(2 * math.pi * t / 1.7 + f["t0"] * 3)
    al = min(1.0, (t - f["t0"]) / 0.2, (f["t1"] - t) / 0.28)
    im = f["im"].resize((max(1, int(f["im"].width * sc)), max(1, int(f["im"].height * sc))), Image.BICUBIC).rotate(rot, resample=Image.BICUBIC, expand=True)
    if al < 1:
        arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3] * max(0.0, al)).astype(np.uint8); im = Image.fromarray(arr)
    return im, int(x - im.width / 2), int(y - im.height / 2)


g = np.zeros((H, 1), dtype=np.float32); g[ST["seam_y"]:ST["seam_y"] + 150, 0] = np.linspace(0.62, 0, 150)
SEAM_SHADE = Image.fromarray((np.repeat(g, W, axis=1) * 255).astype(np.uint8)); BLACK = Image.new("RGB", (W, H), (0, 0, 0))


def draw_frame(base_img, t, mask):
    if inside(t, SPLIT):
        base_img = Image.composite(BLACK, base_img, SEAM_SHADE)
    img = base_img.convert("RGBA")
    if t < LAYER_END:
        behind, front = Image.new("RGBA", (W, H), (0, 0, 0, 0)), Image.new("RGBA", (W, H), (0, 0, 0, 0))
        for f in FLOATERS:
            if f["t0"] <= t < f["t1"]:
                im, x, y = float_at(f, t); paste(behind if f.get("behind") else front, im, x, y)
        if t < HOOK.get("end", 0):
            drift = 1 + 0.03 * t / max(0.1, HOOK["end"])
            for spr, y, b in hook_items:
                s = spr.resize((int(spr.width * drift), int(spr.height * drift)), Image.BILINEAR)
                paste(behind if b else front, s, int(W / 2 - s.width / 2), int(y - (drift - 1) * 60))
        if mask is not None:
            m = Image.fromarray(mask).resize((W, H), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2))
            behind.putalpha(Image.fromarray((np.asarray(behind)[..., 3].astype(float) * (1 - np.asarray(m) / 255)).astype(np.uint8)))
        img.alpha_composite(behind); img.alpha_composite(front)
    for b in blocks:
        if not (b["t0"] <= t < b["t1"]):
            continue
        drift = 1 + 0.03 * (t - b["t0"]) / max(0.01, b["t1"] - b["t0"])
        fade = min(1.0, (b["t1"] - t) / 0.1)
        for it in b["items"]:
            if t < it["t_in"]:
                continue
            k = ease_out((t - it["t_in"]) / 0.14); sc = drift * (1.14 - 0.14 * k); spr = it["spr"]
            s = spr.resize((max(1, int(spr.width * sc)), max(1, int(spr.height * sc))), Image.BILINEAR)
            if k * fade < 1:
                arr = np.asarray(s).copy(); arr[..., 3] = (arr[..., 3] * k * fade).astype(np.uint8); s = Image.fromarray(arr)
            bx, by = W / 2 + it["x"] * drift, b["cy"] + it["baseline"] * drift
            paste(img, s, int(bx - (s.width - spr.width * drift) / 2), int(by - it["base"] * sc))
    return img.convert("RGB")


# ---------- base: talk + B-roll ----------
tmp = OUT.with_name(OUT.stem + "_base.mp4")
inputs, fc, last = ["-i", str(video)], [], "[0:v]"
fc.append("[0:v]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[t]"); last = "[t]"
if SPLIT:
    en = "+".join(f"between(t,{a},{b})" for a, b in SPLIT)
    fc += [f"{last}split[t0][t1]", f"[t1]crop=1080:960:0:{ST['split_y0']}[tc]", f"[t0][tc]overlay=0:960:enable='{en}'[vs]"]; last = "[vs]"
for i, o in enumerate(P.get("broll", []), start=1):
    inputs += ["-i", str(rel(o["file"]))]
    sz = "1080:960" if o.get("layout") == "split" else "1080:1920"
    fc.append(f"[{i}:v]setpts=PTS-STARTPTS+{o['at']}/TB,scale={sz}[b{i}]")
    fc.append(f"{last}[b{i}]overlay=0:0:eof_action=pass:enable='between(t,{o['at']},{o['at'] + o['dur']})'[v{i}]"); last = f"[v{i}]"
fc.append(f"{last}null[vo]")
graph = tmp.with_suffix(".txt"); graph.write_text(";".join(fc), encoding="utf-8")
ffmpeg(*inputs, *filter_script(graph), "-map", "[vo]", "-an", "-c:v", "libx264", "-crf", "14", "-preset", "fast", "-t", f"{END:.3f}", tmp)

dec = subprocess.Popen([need("ffmpeg"), "-loglevel", "error", "-i", str(tmp), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
vid = OUT.with_name(OUT.stem + "_video.mp4")
enc = subprocess.Popen([need("ffmpeg"), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(vid)], stdin=subprocess.PIPE)
n = 0
while True:
    buf = dec.stdout.read(W * H * 3)
    if len(buf) < W * H * 3:
        break
    t = n / FPS
    m = masks[min(n, len(masks) - 1)] if masks is not None and t < LAYER_END else None
    enc.stdin.write(draw_frame(Image.frombytes("RGB", (W, H), buf), t, m).tobytes()); n += 1
enc.stdin.close(); enc.wait()

# ---------- audio: voice + optional SFX ----------
sfx = P.get("sfx", [])
ins, fca, mix = ["-i", str(vid), "-i", str(video)], [], ["[1:a]"]
for j, s in enumerate(sfx):
    ins += ["-i", str(rel(s["file"]))]
    fca.append(f"[{j + 2}:a]atrim=start={s.get('start', 0)},asetpts=PTS-STARTPTS,volume={s.get('vol', 0.4)},adelay={int(s['at'] * 1000)}:all=1[s{j}]")
    mix.append(f"[s{j}]")
fca.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.85[ao]")
ffmpeg(*ins, "-filter_complex", ";".join(fca), "-map", "0:v", "-map", "[ao]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", OUT)
for f in (tmp, vid, graph):
    f.unlink(missing_ok=True)
print(f"{OUT}  {n} frames, {len(blocks)} caption blocks")
print(" | ".join(f"{b['t0']:.1f} {b['text']}" for b in blocks))
