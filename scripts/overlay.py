#!/usr/bin/env python3
"""Post pass over the rendered video: subtitles in other languages, stickers and flags, animated counters with an icon, music.
Runs AFTER render.py so nothing here is zoomed or masked.

usage: overlay.py OVERLAY.json          (paths inside the file are relative to it)

OVERLAY = {
  "video": "final_voz.mp4", "out": "final.mp4",
  "subtitles": [{"t0": 12.1, "t1": 14.0, "y": 1480, "px": 40,
                 "lines": [{"text": "今、僕が言っていること…", "lang": "ja", "from": 12.14},
                           {"text": "अब मैं चाहता हूँ…", "lang": "hi", "from": 13.02},
                           {"text": "Now I want you to…", "lang": "en", "from": 13.60}]}],
        lines stack from y; each one appears at "from" (default t0) and all leave at t1
  "stickers": [{"emoji": "🇲🇽", "t0": 15.74, "t1": 17.26, "x": 210, "y": 240, "w": 300},
               {"img": "mascot.png", "t0": 0, "t1": 1.95, "x": 215, "y": 470, "w": 300, "remove_white": true, "rot": [-3, 3]}],
        x, y = centre; "pop": true (default) = scale-in + fade; "bob": gentle float (default true)
  "counters": [{"t0": 25.24, "t1": 26.18, "value": 1000000, "label": "followers", "icon": "people", "y": 300, "dur": 0.7}],
        counts up to value over dur seconds; icon = "people" (SF Symbol / 👥), any emoji, or an image path
  "music": [{"file": "music/epic.mp3", "at": 19.98, "until": 22.2, "gain": 0.2, "start": 0},
            {"file": "music/pop.mp3", "at": 22.2, "gain": 0.12, "start": 84, "fade_out": 1.2}]
        each track plays from "at" to "until" (default: end of video) under the existing audio
}
"""
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

from common import FPS, H, IS_MAC, IS_WIN, W, caption_font, duration, ffmpeg, filter_script, load_json, need

ov_path = Path(sys.argv[1]).resolve()
O = load_json(ov_path)
base = ov_path.parent
rel = lambda p: (base / p) if not Path(p).is_absolute() else Path(p)
video, out = rel(O["video"]), rel(O.get("out", "final.mp4"))
TMP = base / "_overlay"; TMP.mkdir(exist_ok=True)
END = duration(video)


def ease_out(x):
    x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3


def with_alpha(im, a):
    if a >= 1: return im
    arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3] * max(0.0, a)).astype(np.uint8); return Image.fromarray(arr)


def scaled(im, s):
    return im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.BICUBIC)


def shadowed(im, blur=12, strength=0.65, dy=6):
    """soft black shadow under an RGBA sprite"""
    sh = Image.new("RGBA", (im.width + 2 * blur * 2, im.height + 2 * blur * 2), (0, 0, 0, 0))
    a = Image.new("L", sh.size, 0); a.paste(im.split()[3], (2 * blur, 2 * blur + dy))
    a = a.filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * strength))
    sh.paste(Image.new("RGBA", sh.size, (0, 0, 0, 255)), (0, 0), a)
    sh.alpha_composite(im, (2 * blur, 2 * blur)); return sh


def remove_white(im, thr=225):
    """knock out a flat white background (and its grey anti-aliasing) from a sticker"""
    a = np.asarray(im.convert("RGBA")).astype(int)
    light = (a[..., 0] > thr) & (a[..., 1] > thr) & (a[..., 2] > thr)
    sat = a[..., :3].max(-1) - a[..., :3].min(-1)
    a[..., 3] = np.where(light & (sat < 18), 0, a[..., 3])
    im = Image.fromarray(a.astype(np.uint8)); bb = im.getbbox()
    return im.crop(bb) if bb else im


# ---------- text in any script: CoreText on macOS, PIL (+raqm when available) elsewhere ----------
SWIFT = IS_MAC and shutil.which("swift") is not None and not os.environ.get("CAPTIONS_NO_SWIFT")   # env var = test the PIL path
_swift_jobs, _swift_results = [], {}
FONT_MAC = {"ja": "HiraginoSans-W6", "zh": "PingFangSC-Semibold", "ko": "AppleSDGothicNeo-Bold", "hi": "KohinoorDevanagari-Semibold",
            "ar": "GeezaPro-Bold", "th": "Thonburi-Bold", "he": "ArialHebrew-Bold"}
FONT_WIN = {"ja": ["YuGothB.ttc", "meiryob.ttc", "msgothic.ttc"], "zh": ["msyhbd.ttc", "simhei.ttf"], "ko": ["malgunbd.ttf"],
            "hi": ["NirmalaB.ttf", "Nirmala.ttf"], "ar": ["segoeuib.ttf"], "th": ["LeelawUI.ttf"], "he": ["segoeuib.ttf"]}
FONT_LINUX = {"ja": ["NotoSansCJK-Bold.ttc", "NotoSansCJKjp-Bold.otf"], "hi": ["NotoSansDevanagari-Bold.ttf"], "ar": ["NotoSansArabic-Bold.ttf"]}


FONT_MAC_FILES = {"ja": ["Hiragino Sans GB.ttc", "ヒラギノ角ゴシック W6.ttc"], "zh": ["Hiragino Sans GB.ttc", "PingFang.ttc"], "ko": ["AppleSDGothicNeo.ttc"],
                  "hi": ["Kohinoor.ttc", "DevanagariMT.ttc"], "ar": ["GeezaPro.ttc"], "th": ["Thonburi.ttc"], "he": ["ArialHB.ttc"]}


def _find_font(lang):
    names = (FONT_WIN if IS_WIN else FONT_MAC_FILES if IS_MAC else FONT_LINUX).get(lang, [])
    dirs = [Path("C:/Windows/Fonts")] if IS_WIN else [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"), Path("/Library/Fonts")] if IS_MAC \
        else [Path("/usr/share/fonts"), Path.home() / ".fonts", Path.home() / ".local/share/fonts"]
    for n in names:
        for d in dirs:
            for p in d.rglob(n):
                return p
    return None


def pil_text(text, px, lang, maxw):
    """wrapped white text with a shadow, PIL only (Latin/CJK fine; complex scripts need libraqm, otherwise a warning)"""
    path = _find_font(lang) if lang not in ("en", "es", "pt", "fr", "de", "it") else None
    layout = ImageFont.Layout.RAQM if features.check("raqm") else ImageFont.Layout.BASIC
    if lang in ("hi", "ar", "th", "he") and layout == ImageFont.Layout.BASIC:
        print(f"warning: {lang} text needs libraqm for correct shaping (pip install pillow with raqm, or brew/apt fribidi); rendering anyway")
    f = ImageFont.truetype(str(path), px, layout_engine=layout) if path else caption_font(px)
    words = text.split(" ") if " " in text else list(text)
    lines, cur = [], ""
    sep = " " if " " in text else ""
    for wd in words:
        t = (cur + sep + wd) if cur else wd
        if f.getlength(t) > maxw and cur:
            lines.append(cur); cur = wd
        else:
            cur = t
    lines.append(cur)
    lh = int(px * 1.35)
    txt = Image.new("RGBA", (maxw + 80, lh * len(lines) + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(txt)
    for i, ln in enumerate(lines):
        d.text(((txt.width - f.getlength(ln)) / 2, 20 + i * lh), ln, font=f, fill="white")
    return shadowed(txt, blur=10, strength=0.75, dy=4)


def swift_text(key, text, px, lang, maxw, kind="text"):
    """queue a CoreText job; resolved once by flush_swift()"""
    outp = TMP / f"{key}.png"
    _swift_jobs.append({"kind": kind, "text": text, "font": FONT_MAC.get(lang, "HelveticaNeue-Bold"), "size": px, "maxw": maxw, "out": str(outp)})
    return outp


def flush_swift():
    if not _swift_jobs: return True
    spec = TMP / "_text_spec.json"; spec.write_text(json.dumps(_swift_jobs, ensure_ascii=False), encoding="utf-8")
    r = subprocess.run(["swift", str(Path(__file__).resolve().parent / "text_macos.swift"), str(spec)], capture_output=True, text=True)
    if r.returncode:
        print("warning: swift text renderer failed, falling back to PIL:\n" + r.stderr[-800:]); return False
    return True


# ---------- sprites: emoji, icons, counters ----------
def emoji_sprite(ch, w):
    if SWIFT:
        p = swift_text(f"emoji_{abs(hash(ch))}", ch, 320, "emoji", 700); return ("swift", p, w)
    path = _find_font("emoji") if IS_WIN else None
    cand = [Path("C:/Windows/Fonts/seguiemj.ttf")] if IS_WIN else [Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")]
    for c in cand:
        if c.exists():
            size = 109 if "Noto" in c.name else 128
            f = ImageFont.truetype(str(c), size)
            im = Image.new("RGBA", (size * 2, int(size * 1.4)), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            try:
                d.text((size * 0.2, 0), ch, font=f, embedded_color=True)
            except TypeError:
                d.text((size * 0.2, 0), ch, font=f, fill="white")
            bb = im.getbbox(); im = im.crop(bb) if bb else im
            return ("pil", im, w)
    print(f"warning: no colour-emoji font found for {ch!r}; skipped"); return None


def finish_sprite(spec, pad_shadow=True):
    """turn a queued ("swift", path, w) or ("pil", im, w) into a ready RGBA sprite of width w"""
    if spec is None: return None
    kind, src, w = spec
    im = Image.open(src).convert("RGBA") if kind == "swift" else src
    bb = im.getbbox(); im = im.crop(bb) if bb else im
    im = im.resize((w, max(1, int(im.height * w / im.width))), Image.LANCZOS)
    return shadowed(im) if pad_shadow else im


_fonts = {}
TRACK = -0.025


def word_sprite(t, px, shadow=170, blur=12, track=TRACK):
    """same look as the captions: Helvetica/Inter bold, tight tracking, soft shadow"""
    f = caption_font(px); asc, desc = f.getmetrics()
    w = int(sum(f.getlength(c) for c in t) + track * px * (len(t) - 1)) + 2 * blur + 8; h = asc + desc + 2 * blur + 8
    txt = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(txt); x = blur + 4
    for c in t:
        d.text((x, blur + 4), c, font=f, fill="white"); x += f.getlength(c) + track * px
    a = np.asarray(txt)[..., 3]
    sh = Image.fromarray(a).filter(ImageFilter.GaussianBlur(blur))
    sh = Image.fromarray((np.asarray(sh).astype(float) * shadow / 255).astype(np.uint8))
    o = Image.new("RGBA", (w, h + 4), (0, 0, 0, 0)); o.paste(Image.new("RGBA", (w, h), (0, 0, 0, 255)), (0, 4), sh)
    o.alpha_composite(txt, (0, 0)); return o


# ---------- build everything (queue swift jobs first, then resolve) ----------
subs = []
for i, s in enumerate(O.get("subtitles", [])):
    px, maxw = int(s.get("px", 40)), int(s.get("maxw", 940))
    lines = []
    for j, ln in enumerate(s["lines"]):
        lang = ln.get("lang", "en")
        if SWIFT:
            lines.append({"from": ln.get("from", s["t0"]), "src": ("swift", swift_text(f"sub{i}_{j}", ln["text"], px, lang, maxw))})
        else:
            lines.append({"from": ln.get("from", s["t0"]), "src": ("pil", pil_text(ln["text"], px, lang, maxw))})
    subs.append({"t0": s["t0"], "t1": s["t1"], "y": int(s.get("y", 1480)), "lines": lines})

stickers = []
for i, st in enumerate(O.get("stickers", [])):
    w = int(st.get("w", 300))
    if st.get("emoji"):
        src = emoji_sprite(st["emoji"], w)
    else:
        im = Image.open(rel(st["img"])).convert("RGBA")
        if st.get("remove_white", False): im = remove_white(im)
        if im.width < w: im = im.resize((w, int(im.height * w / im.width)), Image.NEAREST if im.width < 200 else Image.LANCZOS)
        src = ("pil", im, w)
    stickers.append({**st, "src": src})

counters = []
for i, c in enumerate(O.get("counters", [])):
    icon = c.get("icon")
    src = None
    if icon:
        ip = rel(icon)
        if ip.exists():
            src = ("pil", Image.open(ip).convert("RGBA"), int(c.get("icon_w", 150)))
        elif icon == "people":
            src = ("swift", swift_text(f"icon{i}", "person.3.fill", 120, "", 0, kind="symbol"), int(c.get("icon_w", 150))) if SWIFT \
                else emoji_sprite("👥", int(c.get("icon_w", 150)))
        else:
            src = emoji_sprite(icon, int(c.get("icon_w", 150)))
    counters.append({**c, "src": src})

ok = flush_swift()
if not ok:                                                     # swift failed: redo text with PIL
    SWIFT = False
    for s, raw in zip(subs, O.get("subtitles", [])):
        for ln, r in zip(s["lines"], raw["lines"]):
            ln["src"] = ("pil", pil_text(r["text"], int(raw.get("px", 40)), r.get("lang", "en"), int(raw.get("maxw", 940))))
    for st in stickers:
        if st.get("emoji"): st["src"] = emoji_sprite(st["emoji"], int(st.get("w", 300)))
    for c in counters:
        if c.get("icon") == "people": c["src"] = emoji_sprite("👥", int(c.get("icon_w", 150)))
        elif c.get("icon") and not rel(c["icon"]).exists(): c["src"] = emoji_sprite(c["icon"], int(c.get("icon_w", 150)))

for s in subs:
    for ln in s["lines"]:
        kind, src = ln["src"]
        im = Image.open(src).convert("RGBA") if kind == "swift" else src
        ln["im"] = im
for st in stickers:
    st["im"] = finish_sprite(st["src"], pad_shadow=not st.get("emoji")) if st["src"] else None
    if st["im"] is not None and st.get("emoji"): st["im"] = shadowed(st["im"], blur=12, strength=0.6)
for c in counters:
    c["im"] = finish_sprite(c["src"], pad_shadow=c["src"] is not None and c["src"][0] != "swift") if c["src"] else None
    c["lbl"] = word_sprite(str(c.get("label", "")), int(c.get("label_px", 64))) if c.get("label") else None
    c["cache"] = {}

ACTIVE = [(s["t0"] - 0.05, s["t1"]) for s in subs] + [(st["t0"] - 0.05, st["t1"]) for st in stickers] + [(c["t0"] - 0.05, c["t1"]) for c in counters]


def num_sprite(c, n):
    s = f"{n:,}"
    if s not in c["cache"]: c["cache"][s] = word_sprite(s, int(c.get("px", 170)), track=-0.04)
    return c["cache"][s]


def draw(img, t):
    for s in subs:
        if not (s["t0"] <= t < s["t1"]): continue
        y = s["y"]
        for ln in s["lines"]:
            if t < ln["from"]: continue
            a = min(1.0, (t - ln["from"]) / 0.18, (s["t1"] - t) / 0.12)
            im = ln["im"]; img.alpha_composite(with_alpha(im, a), (W // 2 - im.width // 2, y - 40)); y += im.height - 60
    for st in stickers:
        if st["im"] is None or not (st["t0"] <= t < st["t1"]): continue
        k = ease_out((t - st["t0"]) / 0.22) if st.get("pop", True) else 1.0
        sc = (1.25 - 0.25 * k) if st.get("pop", True) else 1.0
        if st.get("grow"): sc *= 1 + 0.06 * (t - st["t0"]) / max(0.1, st["t1"] - st["t0"])
        rot = 0.0
        if st.get("rot"):
            r0, r1 = st["rot"]; rot = r0 + (r1 - r0) * (t - st["t0"]) / max(0.1, st["t1"] - st["t0"])
        bob = 6 * math.sin(2 * math.pi * t / 1.6) if st.get("bob", True) else 0
        im = scaled(with_alpha(st["im"], min(1.0, k * 1.5, (st["t1"] - t) / 0.1)), sc)
        if rot: im = im.rotate(rot, resample=Image.BICUBIC, expand=True)
        img.alpha_composite(im, (int(st["x"] - im.width / 2), int(st["y"] + bob - im.height / 2)))
    for c in counters:
        if not (c["t0"] <= t < c["t1"]): continue
        u = ease_out((t - c["t0"]) / float(c.get("dur", 0.7))); val = int(c["value"] * u) if u < 1 else int(c["value"])
        k = ease_out((t - c["t0"]) / 0.14); a = min(1.0, k, (c["t1"] - t) / 0.1); sc = 1.12 - 0.12 * k
        ns = num_sprite(c, val); ic = c["im"]; gap = 24; cy = int(c.get("y", 300))
        row_w = ns.width + ((ic.width + gap) if ic is not None else 0); x0 = int(c.get("x", W // 2)) - row_w // 2
        if ic is not None:
            si = scaled(with_alpha(ic, a), sc); img.alpha_composite(si, (int(x0 + ic.width / 2 - si.width / 2), int(cy - si.height / 2))); x0 += ic.width + gap
        s = scaled(with_alpha(ns, a), sc); img.alpha_composite(s, (int(x0 + ns.width / 2 - s.width / 2), int(cy - s.height / 2)))
        if c["lbl"] is not None:
            ls = with_alpha(c["lbl"], a); img.alpha_composite(ls, (int(c.get("x", W // 2)) - ls.width // 2, cy + 70))
    return img


# ---------- frames ----------
vid = TMP / "_video.mp4"
dec = subprocess.Popen([need("ffmpeg"), "-loglevel", "error", "-i", str(video), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
enc = subprocess.Popen([need("ffmpeg"), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                        "-c:v", "libx264", "-preset", "medium", "-crf", "16", "-pix_fmt", "yuv420p", "-color_primaries", "bt709", "-color_trc", "bt709",
                        "-colorspace", "bt709", str(vid)], stdin=subprocess.PIPE)
n = 0
while True:
    buf = dec.stdout.read(W * H * 3)
    if len(buf) < W * H * 3: break
    t = n / FPS
    if any(a <= t < b for a, b in ACTIVE):
        buf = draw(Image.frombytes("RGB", (W, H), buf).convert("RGBA"), t).convert("RGB").tobytes()
    enc.stdin.write(buf); n += 1
enc.stdin.close(); enc.wait(); dec.wait()
print(f"{n} frames; {len(subs)} subtitle blocks, {len(stickers)} stickers, {len(counters)} counters")

# ---------- audio: the video's own track + music under it ----------
music = [m for m in O.get("music", []) if rel(m["file"]).exists()] if O.get("music") else []
for m in O.get("music", []):
    if not rel(m["file"]).exists(): print(f"warning: music file missing, skipped: {m['file']}")
ins = ["-i", str(vid), "-i", str(video)]
if music:
    fc, mix = [], ["[1:a]"]
    for j, m in enumerate(music):
        ins += ["-i", str(rel(m["file"]))]
        at, until = float(m["at"]), float(m.get("until", END))
        seg = max(0.3, until - at); fo = float(m.get("fade_out", 0.25 if m.get("until") else 1.2)); fi = float(m.get("fade_in", 0.08))
        fc.append(f"[{j + 2}:a]atrim=start={float(m.get('start', 0))}:end={float(m.get('start', 0)) + seg + 0.3:.3f},asetpts=PTS-STARTPTS,"
                  f"afade=t=in:d={fi},afade=t=out:st={max(0.0, seg - fo):.3f}:d={fo},volume={float(m.get('gain', 0.12))},adelay={int(at * 1000)}:all=1[m{j}]")
        mix.append(f"[m{j}]")
    fc.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first,alimiter=limit=0.9[ao]")
    script = TMP / "_audio.txt"; script.write_text(";".join(fc), encoding="utf-8")
    ffmpeg(*ins, *filter_script(script), "-map", "0:v", "-map", "[ao]", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", out)
else:
    ffmpeg(*ins, "-map", "0:v", "-map", "1:a?", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k", "-shortest", out)
vid.unlink()
print("wrote", out, f"({len(music)} music tracks)")
