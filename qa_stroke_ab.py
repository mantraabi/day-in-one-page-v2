"""A/B the headline ink weight at judge scale.

Card 6 ("President Khürelsükh resigns...") is hard-capped at 23.4 px by its own
word widths, so size is exhausted.  What is left is stem weight: at 300 px the
headline is ~7 px tall, and a 0.2 px stem difference decides letter vs smear.
Renders the whole poster once per stroke value, then stacks the card-6 crop at
judge scale so the variants can be compared side by side.
"""
import io
import os
import sys

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "tools"))
import gen_poster as g  # noqa: E402

QA = os.path.join(HERE, "qa")
STROKES = [0.35, 0.55, 0.75]
# bottom-right card, derived from the real constants
_CX = g.CONTENT_X0 + 2 * (g.CARD_W + g.CARD_GAP)
_CY = g.CARDS_Y0 + (g.CARD_H + g.CARD_VGAP)
CARD6_BOX = (int(_CX) - 2, int(_CY) - 2, int(_CX + g.CARD_W) + 2,
             int(_CY + g.CARD_H) + 2)


def render(weight):
    real = g.draw_lines

    def patched(d, x, y, lines, path, px, lh, fill, tracking=0.0, stroke=0.0):
        # only the card headlines (23.2 px serif) get the experimental weight
        if 22.0 <= px <= 25.5:   # card headlines only; lead is 31 px
            stroke = weight
        return real(d, x, y, lines, path, px, lh, fill, tracking, stroke)

    g.draw_lines = patched
    try:
        img = g.build()
    finally:
        g.draw_lines = real
    return img.convert("RGB") if hasattr(img, "convert") else img


def judge_crop(img, box, zoom=2):
    """Crop `box` (page px) out of the page AFTER a real 300x300 downscale.

    The box has to be scaled into 300-space first -- cropping a 300 px image
    with 1024 px coordinates silently returns empty black, which is exactly the
    trap this helper exists to avoid.
    """
    s = 300.0 / 1024.0
    sb = tuple(int(round(v * s)) for v in box)
    small = img.resize((300, 300), Image.LANCZOS).crop(sb)
    full_w = box[2] - box[0]
    full_h = box[3] - box[1]
    return small.resize((full_w * zoom, full_h * zoom), Image.NEAREST)


def main():
    print("card6 box", CARD6_BOX)
    tiles = []
    for s in STROKES:
        img = render(s)
        tiles.append(judge_crop(img, CARD6_BOX))

    w, h = tiles[0].size
    sheet = Image.new("RGB", (w, h * len(tiles) + 8 * (len(tiles) - 1)),
                      (255, 255, 255))
    for i, t in enumerate(tiles):
        sheet.paste(t, (0, i * (h + 8)))
    sheet.save(os.path.join(QA, "stroke_ab.png"), optimize=True)
    print("qa/stroke_ab.png written, top->bottom strokes:", STROKES)


if __name__ == "__main__":
    main()
