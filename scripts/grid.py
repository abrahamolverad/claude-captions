#!/usr/bin/env python3
"""Draw a labelled pixel grid over a screenshot so you can read box coordinates for circles and notes (broll.py).

usage: grid.py IMAGE OUT.jpg [--step 100] [--crop x0 y0 x1 y1]
"""
import argparse

from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("image"); ap.add_argument("out"); ap.add_argument("--step", type=int, default=100)
ap.add_argument("--crop", type=int, nargs=4)
a = ap.parse_args()
im = Image.open(a.image).convert("RGB")
ox, oy = 0, 0
if a.crop:
    ox, oy = a.crop[0], a.crop[1]; im = im.crop(a.crop)
d = ImageDraw.Draw(im)
for x in range((ox // a.step + 1) * a.step, ox + im.width, a.step):
    d.line([(x - ox, 0), (x - ox, im.height)], fill=(255, 0, 0), width=1); d.text((x - ox + 3, 3), str(x), fill=(255, 0, 0))
for y in range((oy // a.step + 1) * a.step, oy + im.height, a.step):
    d.line([(0, y - oy), (im.width, y - oy)], fill=(0, 120, 255), width=1); d.text((3, y - oy + 3), str(y), fill=(0, 120, 255))
im.save(a.out, quality=90)
print(a.out, im.size, "(coordinates are in the original image's pixels)")
