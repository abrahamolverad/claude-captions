#!/usr/bin/env python3
"""Country silhouettes (flag-filled when the flag is simple, white otherwise) with a label, for floating maps.

usage: maps.py OUTDIR "Spain=españa" "Japan=japón" "United States of America=estados unidos" "Finland=finlandia" [--width 330] [--plain]
  -> OUTDIR/<slug>.png  (transparent sprite: silhouette + white rim + soft shadow + label below)
Names are the English Natural Earth names (assets/maps/countries-50m.json). Far islands and overseas parts are dropped
automatically (keeps the main landmass and the big parts near it). Use the sprites as "floaters" in plan.json.
"""
import argparse
import json
import math
import re
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from common import ASSETS, caption_font

topo = json.loads((ASSETS / "maps" / "countries-50m.json").read_text(encoding="utf-8"))
(sx, sy), (tx, ty) = topo["transform"]["scale"], topo["transform"]["translate"]
ARCS = []
for arc in topo["arcs"]:
    x = y = 0; pts = []
    for dx, dy in arc:
        x += dx; y += dy; pts.append((x * sx + tx, y * sy + ty))
    ARCS.append(pts)
GEOMS = {g["properties"]["name"]: g for g in topo["objects"]["countries"]["geometries"] if "properties" in g}

# horizontal ("h") or vertical ("v") stripes, top-to-bottom / left-to-right, with relative widths
STRIPES = {
    "Spain": ("h", [("#AA151B", 1), ("#F1BF00", 2), ("#AA151B", 1)]), "Mexico": ("v", [("#006847", 1), ("#FFFFFF", 1), ("#CE1126", 1)]),
    "Argentina": ("h", [("#74ACDF", 1), ("#FFFFFF", 1), ("#74ACDF", 1)]), "Colombia": ("h", [("#FCD116", 2), ("#003893", 1), ("#CE1126", 1)]),
    "Peru": ("v", [("#D91023", 1), ("#FFFFFF", 1), ("#D91023", 1)]), "France": ("v", [("#002654", 1), ("#FFFFFF", 1), ("#CE1126", 1)]),
    "Italy": ("v", [("#008C45", 1), ("#F4F5F0", 1), ("#CD212A", 1)]), "Germany": ("h", [("#000000", 1), ("#DD0000", 1), ("#FFCE00", 1)]),
    "Netherlands": ("h", [("#AE1C28", 1), ("#FFFFFF", 1), ("#21468B", 1)]), "Canada": ("v", [("#D52B1E", 1), ("#FFFFFF", 2), ("#D52B1E", 1)]),
    "Ireland": ("v", [("#169B62", 1), ("#FFFFFF", 1), ("#FF883E", 1)]), "Belgium": ("v", [("#000000", 1), ("#FDDA24", 1), ("#EF3340", 1)]),
    "Austria": ("h", [("#ED2939", 1), ("#FFFFFF", 1), ("#ED2939", 1)]), "Russia": ("h", [("#FFFFFF", 1), ("#0039A6", 1), ("#D52B1E", 1)]),
    "Ukraine": ("h", [("#0057B7", 1), ("#FFD700", 1)]), "Poland": ("h", [("#FFFFFF", 1), ("#DC143C", 1)]),
    "Indonesia": ("h", [("#CE1126", 1), ("#FFFFFF", 1)]), "Nigeria": ("v", [("#008751", 1), ("#FFFFFF", 1), ("#008751", 1)]),
    "Venezuela": ("h", [("#FFCC00", 1), ("#00247D", 1), ("#CF142B", 1)]), "Ecuador": ("h", [("#FFDD00", 2), ("#034EA2", 1), ("#ED1C24", 1)]),
    "Bolivia": ("h", [("#D52B1E", 1), ("#F9E300", 1), ("#007934", 1)]), "Hungary": ("h", [("#CE2939", 1), ("#FFFFFF", 1), ("#477050", 1)]),
}
NORDIC = {"Finland": ("#FFFFFF", "#002F6C", None), "Sweden": ("#006AA7", "#FECC00", None), "Denmark": ("#C8102E", "#FFFFFF", None),
          "Norway": ("#BA0C2F", "#FFFFFF", "#00205B"), "Iceland": ("#02529C", "#FFFFFF", "#DC1E35")}


def ring(ids):
    out = []
    for i in ids:
        pts = ARCS[i] if i >= 0 else ARCS[~i][::-1]
        out += pts if not out else pts[1:]
    return out


def polygons(name):
    if name not in GEOMS:
        close = [n for n in GEOMS if name.lower() in n.lower()]
        raise SystemExit(f"Unknown country {name!r}. Close matches: {close[:8]}")
    g = GEOMS[name]
    polys = g["arcs"] if g["type"] == "MultiPolygon" else [g["arcs"]]
    return [[ring(r) for r in p] for p in polys]


def area_centroid(r):
    k = math.cos(math.radians(sum(p[1] for p in r) / len(r)))
    a = sum((r[i][0] * k) * r[i + 1][1] - (r[i + 1][0] * k) * r[i][1] for i in range(len(r) - 1)) / 2
    return abs(a), (sum(p[0] for p in r) / len(r), sum(p[1] for p in r) / len(r))


def main_parts(polys, min_share=0.03, max_deg=12):
    info = [(area_centroid(p[0]), p) for p in polys]
    (amax, (cx, cy)), _ = max(info, key=lambda x: x[0][0])
    return [p for (a, (x, y)), p in info if a >= amax * min_share and math.hypot(x - cx, y - cy) <= max_deg]


def flag(name, w, h, mask):
    f = Image.new("RGB", (w, h), "white"); d = ImageDraw.Draw(f)
    if name in STRIPES:
        orient, bands = STRIPES[name]; total = sum(b for _, b in bands); pos = 0
        for color, b in bands:
            if orient == "h":
                d.rectangle((0, h * pos / total, w, h * (pos + b) / total), fill=color)
            else:
                d.rectangle((w * pos / total, 0, w * (pos + b) / total, h), fill=color)
            pos += b
    elif name in NORDIC:
        bgc, cross, inner = NORDIC[name]; d.rectangle((0, 0, w, h), fill=bgc); b = min(w, h) * 0.18
        d.rectangle((w * 0.36 - b / 2, 0, w * 0.36 + b / 2, h), fill=cross); d.rectangle((0, h * 0.55 - b / 2, w, h * 0.55 + b / 2), fill=cross)
        if inner:
            b2 = b * 0.5
            d.rectangle((w * 0.36 - b2 / 2, 0, w * 0.36 + b2 / 2, h), fill=inner); d.rectangle((0, h * 0.55 - b2 / 2, w, h * 0.55 + b2 / 2), fill=inner)
    elif name == "Japan":
        ys, xs = np.nonzero(np.asarray(mask) > 128); r = min(w, h) * 0.17
        d.ellipse((xs.mean() - r, ys.mean() - r, xs.mean() + r, ys.mean() + r), fill="#BC002D")
    elif name == "United States of America":
        for i in range(13):
            d.rectangle((0, h * i / 13, w, h * (i + 1) / 13), fill="#B22234" if i % 2 == 0 else "white")
        cw, ch = w * 0.42, h * 7 / 13; d.rectangle((0, 0, cw, ch), fill="#3C3B6E"); r = max(2, int(h / 90))
        for row in range(9):
            for col in range(11 if row % 2 == 0 else 10):
                x = cw * (col + (0.5 if row % 2 == 0 else 1.0)) / 11.5; y = ch * (row + 0.7) / 9.6
                d.ellipse((x - r, y - r, x + r, y + r), fill="white")
    else:
        return None
    return f


def sprite(name, label, width, plain=False):
    pts = main_parts(polygons(name))
    allp = [q for p in pts for q in p[0]]
    k = math.cos(math.radians(sum(q[1] for q in allp) / len(allp)))
    xs = [q[0] * k for q in allp]; ys = [-q[1] for q in allp]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    S = 4; sc = width * S / (x1 - x0)
    m = Image.new("L", (int(width * S), max(1, int((y1 - y0) * sc))), 0); d = ImageDraw.Draw(m)
    for p in pts:
        for j, r in enumerate(p):
            d.polygon([((q[0] * k - x0) * sc, (-q[1] - y0) * sc) for q in r], fill=255 if j == 0 else 0)
    m = m.resize((width, max(1, int(m.height / S))), Image.LANCZOS)
    w, h = m.size
    fill = None if plain else flag(name, w, h, m)
    fill = fill or Image.new("RGB", (w, h), "white")
    pad, font = 40, caption_font(44)
    lw = int(font.getlength(label)) if label else 0
    cw, ch = max(w, lw) + 2 * pad, h + 2 * pad + (70 if label else 0)
    out = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); ox = (cw - w) // 2
    edge = m.filter(ImageFilter.GaussianBlur(3.5)).point(lambda v: 255 if v > 24 else v * 10)
    shm = Image.new("L", (cw, ch), 0); shm.paste(edge, (ox, pad + 8))
    sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0)); sh.putalpha(shm.point(lambda v: int(v * 0.55)).filter(ImageFilter.GaussianBlur(14)))
    out.alpha_composite(sh)
    rim = Image.new("RGBA", (w, h), (255, 255, 255, 255)); rim.putalpha(edge); out.alpha_composite(rim, (ox, pad))
    land = fill.convert("RGBA"); land.putalpha(m); out.alpha_composite(land, (ox, pad))
    if label:
        t = Image.new("RGBA", (cw, 90), (0, 0, 0, 0)); td = ImageDraw.Draw(t)
        td.text((cw / 2, 45), label, font=font, fill=(0, 0, 0, 150), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0, 150))
        t = t.filter(ImageFilter.GaussianBlur(6)); ImageDraw.Draw(t).text((cw / 2, 45), label, font=font, fill="white", anchor="mm")
        out.alpha_composite(t, (0, pad + h - 10))
    return out


def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out"); ap.add_argument("countries", nargs="+", help='"Natural Earth name=label"')
    ap.add_argument("--width", type=int, default=330); ap.add_argument("--plain", action="store_true")
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for item in a.countries:
        name, _, label = item.partition("=")
        im = sprite(name.strip(), label.strip() or None, a.width, a.plain)
        f = out / f"{slug(label or name)}.png"; im.save(f)
        print(f"{f}  {im.size[0]}x{im.size[1]}  {'flag' if (not a.plain and (name in STRIPES or name in NORDIC or name in ('Japan', 'United States of America'))) else 'white'}")
