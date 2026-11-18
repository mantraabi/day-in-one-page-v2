"""Judge-scale proof sheet: the six card headlines after a 300x300 round trip.

Produces
  qa/cards_judge.png  -- the card band at true judge scale (300/1024), upscaled
                         4x with NEAREST so nothing is smoothed by the upscaler
  qa/cards_1024.png   -- the same band at full page scale, for comparison
Both are stacked, so a single look answers "did this survive the thumbnail?"
"""
import os
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
QA = os.path.join(HERE, "qa")
THUMB = 300
FULL = 1024


def main():
    full = Image.open(os.path.join(QA, "full.png")).convert("RGB")

    # exact judge pipeline: downscale the whole page to 300x300, then read back
    judge = full.resize((THUMB, THUMB), Image.LANCZOS).resize(
        (FULL, FULL), Image.LANCZOS)
    judge.save(os.path.join(QA, "thumb300.png"))
    judge.resize((FULL * 2, FULL * 2), Image.NEAREST).save(
        os.path.join(QA, "up300.png"))

    # card band, full scale and judge scale, side by side
    y0, y1 = 440, 732
    band_full = full.crop((0, y0, FULL, y1))
    band_judge = judge.crop((0, y0, FULL, y1))
    up = 2
    w, h = band_full.size
    sheet = Image.new("RGB", (w * up, h * up * 2 + 12), (255, 255, 255))
    sheet.paste(band_judge.resize((w * up, h * up), Image.NEAREST), (0, 0))
    sheet.paste(band_full.resize((w * up, h * up), Image.NEAREST),
                (0, h * up + 12))
    sheet.save(os.path.join(QA, "cards_judge.png"), optimize=True)

    # numbers strip the same way
    n0, n1 = 844, 948
    nb = full.crop((0, n0, FULL, n1))
    nj = judge.crop((0, n0, FULL, n1))
    w, h = nb.size
    ns = Image.new("RGB", (w * up, h * up * 2 + 12), (255, 255, 255))
    ns.paste(nj.resize((w * up, h * up), Image.NEAREST), (0, 0))
    ns.paste(nb.resize((w * up, h * up), Image.NEAREST), (0, h * up + 12))
    ns.save(os.path.join(QA, "numbers_judge.png"), optimize=True)

    print("thumb300.png, up300.png, cards_judge.png, numbers_judge.png written")


if __name__ == "__main__":
    main()
