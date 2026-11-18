#!/usr/bin/env python3
"""QA helper: render the poster and emit thumbnails at judge scale.

Writes into qa/:
    full.png       1024x1024 master
    thumb300.png   1024 -> 300x300 (what the judge sees shrunk)
    up300.png      300x300 -> back up to 1024 (what "upscaled back" looks like)
    cards300.png   the six-card band, cropped from thumb300 and upscaled 4x
"""
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import gen_poster  # noqa: E402

OUT = os.path.join(HERE, "qa")
os.makedirs(OUT, exist_ok=True)

img = gen_poster.build()
img.save(os.path.join(OUT, "full.png"), optimize=True)

thumb = img.resize((300, 300), Image.LANCZOS)
thumb.save(os.path.join(OUT, "thumb300.png"))

up = thumb.resize((1024, 1024), Image.NEAREST)
up.save(os.path.join(OUT, "up300.png"))

# card band only: CARDS_Y0..CARDS_Y1 in page px -> 300 scale
def band(y0, y1, name, scale=4):
    t0 = int(y0 * 300 / 1024)
    t1 = int(y1 * 300 / 1024)
    crop = thumb.crop((0, t0, 300, t1))
    w, h = crop.size
    crop.resize((w * scale, h * scale), Image.NEAREST).save(
        os.path.join(OUT, name))

band(gen_poster.CARDS_Y0, gen_poster.CARDS_Y1 + 90, "cards300.png", 4)
band(gen_poster.NUM_Y0 - 6, gen_poster.NUM_Y1, "numbers300.png", 4)

print("full", img.size, os.path.getsize(os.path.join(OUT, "full.png")))
