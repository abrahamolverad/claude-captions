#!/usr/bin/env python3
"""B-roll clips from screenshots or footage: moving camera, hand-drawn red circles, handwritten notes, privacy blur, checklists.

usage: broll.py SPEC.json   -> <spec dir>/broll/<name>.mp4 for every clip, and prints the entries to paste into plan.json

SPEC = {
  "size": "split" | "full",              split = 1080x960 (top half of a split-screen Reel), full = 1080x1920
  "clips": [{
     "name": "headline", "src": "shots/article.png" | "footage.mp4", "dur": 2.4,
     "cam":   [[t, cx, cy, scale, out_y], ...]   source point (cx, cy) sits at (540, out_y) of the frame; eased between keys
     "focus": {"box": [x0, y0, x1, y1], "zoom": 1.6, "t": 0.9}   (instead of cam) start fitted to the width, push in on the box
     "circles": [{"box": [x0, y0, x1, y1], "t": 0.5}],            red marker ellipse drawn around a box (source px)
     "notes":   [{"text": "~70%", "at": [x, y], "t": 1.2, "px": 100, "rot": -5}],   handwritten red label (source px)
     "blur":    [[x0, y0, x1, y1]],                                 pixelate names, emails, faces of private people
     "video_start": 0, "speed": 1.0, "punch": 0.08, "radius": 0, "shade": [760, 960, 0.7]
  }, {
     "name": "todo", "dur": 7, "checklist": {"title": "qué hacer hoy", "items": [["actualiza tu teléfono", 0.2], ["cambia tus contraseñas", 2.4]]}
  }]
}
Coordinates are pixels of the source image or video. Use grid.py on a screenshot to read them.
"""
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from common import FPS, caption_font, hand_font, load_json, need, video_size

RED = (255, 38, 38)
W, H = 1080, 960


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def cam_at(cam, t):
    if t <= cam[0][0]:
        return cam[0][1:]
    for a, b in zip(cam, cam[1:]):
        if t <= b[0]:
            k = ease((t - a[0]) / max(1e-6, b[0] - a[0]))
            return tuple(av + (bv - av) * k for av, bv in zip(a[1:], b[1:]))
    return cam[-1][1:]


def pixelate(im, boxes):
    for x0, y0, x1, y1 in boxes:
        x0, y0, x1, y1 = map(int, (x0, y0, x1, y1))
        reg = im.crop((x0, y0, x1, y1))
        small = reg.resize((max(1, (x1 - x0) // 18), max(1, (y1 - y0) // 18)), Image.BILINEAR)
        im.paste(small.resize(reg.size, Image.NEAREST).filter(ImageFilter.GaussianBlur(4)), (x0, y0))
    return im


def background(src):
    sw, sh = src.size
    k = max(W / sw, H / sh)
    bg = src.resize((max(1, int(sw * k / 12)), max(1, int(sh * k / 12))), Image.BILINEAR)
    bg = bg.filter(ImageFilter.GaussianBlur(3)).resize((int(sw * k) + 2, int(sh * k) + 2), Image.BILINEAR)
    bg = bg.crop(((bg.width - W) // 2, (bg.height - H) // 2, (bg.width - W) // 2 + W, (bg.height - H) // 2 + H))
    return Image.blend(bg, Image.new("RGB", (W, H), (8, 8, 12)), 0.55)


def frame(src, bg, cx, cy, s, oy, radius=0):
    sw, sh = src.size
    l, t = cx - W / 2 / s, cy - oy / s
    r, b = l + W / s, t + H / s
    il, it, ir, ib = max(0, l), max(0, t), min(sw, r), min(sh, b)
    out = bg.copy()
    if ir <= il or ib <= it:
        return out
    piece = src.crop((int(il), int(it), int(math.ceil(ir)), int(math.ceil(ib))))
    pw, ph = max(1, round(piece.width * s)), max(1, round(piece.height * s))
    piece = piece.resize((pw, ph), Image.LANCZOS)
    px, py = round((int(il) - l) * s), round((int(it) - t) * s)
    if (px <= 0 and py <= 0 and px + pw >= W and py + ph >= H) or not radius:
        out.paste(piece, (px, py)); return out
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((px, py + 14, px + pw, py + ph + 14), radius=radius, fill=(0, 0, 0, 150))
    out = out.convert("RGBA"); out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(22)))
    mask = Image.new("L", piece.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw - 1, ph - 1), radius=radius, fill=255)
    out.paste(piece, (px, py), mask)
    return out.convert("RGB")


def circle(img, box, prog, seed=0.0):
    if prog <= 0:
        return img
    x0, y0, x1, y1 = box
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    rx, ry = (x1 - x0) / 2 * 1.16 + 26, (y1 - y0) / 2 * 1.32 + 24
    a0, span = math.radians(-115 + seed * 20), math.radians(385) * min(1.0, prog)
    n = max(2, int(90 * min(1.0, prog)))
    pts = []
    for i in range(n + 1):
        a = a0 + span * i / n
        wob = 1 + 0.035 * math.sin(3 * a + seed) + 0.05 * (a - a0) / math.radians(385)
        pts.append((cx + rx * wob * math.cos(a), cy + ry * wob * math.sin(a) - 4 * math.sin(a / 2)))
    lay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(lay).line([(x + 2, y + 4) for x, y in pts], fill=(0, 0, 0, 110), width=14, joint="curve")
    lay = lay.filter(ImageFilter.GaussianBlur(4))
    d = ImageDraw.Draw(lay)
    d.line(pts, fill=RED + (255,), width=12, joint="curve")
    for p in (pts[0], pts[-1]):
        d.ellipse((p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6), fill=RED + (255,))
    out = img.convert("RGBA"); out.alpha_composite(lay)
    return out.convert("RGB")


def note(img, text, xy, px, prog, rot=-4):
    if prog <= 0:
        return img
    k = 1 - (1 - min(1.0, prog)) ** 3
    f = hand_font(max(8, px * (1.25 - 0.25 * k)))
    w, h = int(f.getlength(text)) + 40, int(px * 1.6) + 40
    lay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    sw = max(2, px // 28)
    d.text((22, 23), text, font=f, fill=(0, 0, 0, int(120 * k)), stroke_width=sw + 1, stroke_fill=(0, 0, 0, int(120 * k)))
    d.text((20, 20), text, font=f, fill=RED + (int(255 * k),), stroke_width=sw, stroke_fill=RED + (int(255 * k),))
    lay = lay.rotate(rot, resample=Image.BICUBIC, expand=True)
    out = img.convert("RGBA")
    x, y = int(xy[0] - lay.width / 2), int(xy[1] - lay.height / 2)
    l, t = max(0, -x), max(0, -y)
    if lay.width - l > 0 and lay.height - t > 0:
        out.alpha_composite(lay.crop((l, t, min(lay.width, W - x), min(lay.height, H - y))), (x + l, y + t))
    return out.convert("RGB")


def shade_layer(y0, y1, a):
    g = np.zeros((H, 1), dtype=np.float32)
    y0, y1 = min(y0, H), min(y1, H)
    g[y0:y1, 0] = np.linspace(0, a, max(0, y1 - y0))
    g[y1:, 0] = a
    return Image.fromarray((np.repeat(g, W, axis=1) * 255).astype(np.uint8))


def checklist_draw(spec):
    title, items = spec["title"], spec["items"]
    def draw(img, t):
        img = img.convert("RGBA"); d = ImageDraw.Draw(img)
        ft, fi = hand_font(74 * W / 1080), hand_font(56 * W / 1080)
        d.text((90, 70), title, font=ft, fill=(20, 20, 20))
        d.line([(90, 168), (90 + ft.getlength(title), 160)], fill=RED, width=6)
        step = min(150, (H - 300) / max(1, len(items)))
        for i, (txt, t0) in enumerate(items):
            y = 250 + i * step
            d.rounded_rectangle((90, y, 160, y + 70), radius=10, outline=(20, 20, 20), width=6)
            d.text((200, y - 2), txt, font=fi, fill=(20, 20, 20))
            p = (t - t0) / 0.22
            if p > 0:
                a_, b_, c_ = (100, y + 30), (128, y + 62), (190, y - 20)
                seg = min(1.0, p)
                if seg < 0.4:
                    k = seg / 0.4
                    d.line([a_, (a_[0] + (b_[0] - a_[0]) * k, a_[1] + (b_[1] - a_[1]) * k)], fill=RED, width=12)
                else:
                    k = (seg - 0.4) / 0.6
                    d.line([a_, b_, (b_[0] + (c_[0] - b_[0]) * k, b_[1] + (c_[1] - b_[1]) * k)], fill=RED, width=12, joint="curve")
        return img.convert("RGB")
    return draw


class VideoSource:
    def __init__(self, path, start=0.0, speed=1.0):
        self.size = video_size(path)
        vf = f"setpts=PTS/{speed},fps={FPS}" if speed != 1 else f"fps={FPS}"
        self.p = subprocess.Popen([need("ffmpeg"), "-loglevel", "error", "-ss", str(start), "-i", str(path), "-vf", vf, "-f", "rawvideo",
                                   "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
        self.last = None

    def next(self):
        n = self.size[0] * self.size[1] * 3
        buf = self.p.stdout.read(n)
        if len(buf) == n:
            self.last = Image.frombytes("RGB", self.size, buf)
        return self.last


def render(out, c, base_dir):
    dur = float(c["dur"])
    src = c.get("src")
    is_video = bool(src) and str(src).lower().endswith((".mp4", ".mov", ".m4v", ".webm"))
    if c.get("checklist"):
        still = Image.new("RGB", (W, H), (244, 241, 234)); draw = checklist_draw(c["checklist"]); cam = [[0, W / 2, H / 2, 1.0, H / 2]]
    else:
        draw = None
        path = (base_dir / src) if not Path(src).is_absolute() else Path(src)
        still = None if is_video else pixelate(Image.open(path).convert("RGB"), c.get("blur", []))
        sw, sh = video_size(path) if is_video else still.size
        cam = c.get("cam")
        if not cam:
            fit = W / sw if not is_video else max(W / sw, H / sh)
            f = c.get("focus")
            if f:
                bx0, by0, bx1, by1 = f["box"]; bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2
                z = f.get("zoom", 1.6) * fit
                cx_z = min(max(bcx, W / 2 / z), sw - W / 2 / z)
                cam = [[0, sw / 2, bcy, fit, H * 0.45], [f.get("t", 0.9) * 0.5, sw / 2, bcy, fit, H * 0.45],
                       [f.get("t", 0.9), cx_z, bcy, z, H * 0.45], [dur, cx_z, bcy, z * 1.04, H * 0.45]]
            else:
                cam = [[0, sw / 2, sh / 2, fit, H / 2], [dur, sw / 2, sh / 2, fit * 1.06, H / 2]]
    vs = VideoSource(base_dir / src if not Path(src).is_absolute() else src, c.get("video_start", 0), c.get("speed", 1.0)) if is_video else None
    bg_still = None if is_video else background(still)
    shade = c.get("shade", [int(H * 0.79), H, 0.7] if H == 960 else [int(H * 0.58), int(H * 0.72), 0.8])
    shade_m = shade_layer(*shade) if shade else None
    enc = subprocess.Popen([need("ffmpeg"), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
                            "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", str(out)], stdin=subprocess.PIPE)
    punch = c.get("punch", 0.08 if not c.get("checklist") else 0.0)
    bg = None
    for i in range(round(dur * FPS)):
        t = i / FPS
        if vs:
            fr = pixelate(vs.next().copy(), c.get("blur", []))
            if i % 3 == 0:
                bg = background(fr)
        else:
            fr, bg = still, bg_still
        cx, cy, s, oy = cam_at(cam, t)
        if punch and t < 0.18:
            s *= 1 + punch * (1 - ease(t / 0.18))
        img = frame(fr, bg, cx, cy, s, oy, c.get("radius", 0))
        for j, ci in enumerate(c.get("circles", [])):
            x0, y0, x1, y1 = ci["box"]
            img = circle(img, (W / 2 + (x0 - cx) * s, oy + (y0 - cy) * s, W / 2 + (x1 - cx) * s, oy + (y1 - cy) * s),
                         (t - ci["t"]) / ci.get("dur", 0.34), seed=j * 1.7)
        for nt in c.get("notes", []):
            sx, sy = nt["at"]
            img = note(img, nt["text"], (W / 2 + (sx - cx) * s, oy + (sy - cy) * s), nt.get("px", 90), (t - nt["t"]) / 0.2, nt.get("rot", -4))
        if shade_m is not None:
            img = Image.composite(Image.new("RGB", (W, H), (0, 0, 0)), img, shade_m)
        if draw:
            img = draw(img, t)
        enc.stdin.write(img.tobytes())
    enc.stdin.close(); enc.wait()
    if vs:
        vs.p.kill()


if __name__ == "__main__":
    spec_path = Path(sys.argv[1]).resolve()
    spec = load_json(spec_path)
    if spec.get("size", "split") == "full":
        W, H = 1080, 1920
    out_dir = spec_path.parent / "broll"; out_dir.mkdir(exist_ok=True)
    only = set(sys.argv[2:])
    for c in spec["clips"]:
        if only and c["name"] not in only:
            continue
        out = out_dir / f"{c['name']}.mp4"
        render(out, c, spec_path.parent)
        print(f'{{"file": "{out.relative_to(spec_path.parent).as_posix()}", "at": 0.0, "dur": {c["dur"]}, '
              f'"layout": "{spec.get("size", "split")}"}}   <- set "at" to the word where it starts')
