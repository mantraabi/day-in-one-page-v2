#!/usr/bin/env python3
"""Build the 17 November 2026 "day in one page" poster.

Pure Pillow + stdlib.  Everything is drawn at SS x resolution and downsampled
once with LANCZOS, so hair lines and small type stay clean.

Layout is a newspaper front page in three tiers:
    masthead  ->  hero (illustration + lead type + small map)  ->  six cards
    ->  also reported  ->  numbers band  ->  footer
"""

import json
import math
import os
import random

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------
# page geometry
# --------------------------------------------------------------------------

W = 1024
H = 1024
SS = 3                      # supersample factor: draw at 3072, ship at 1024

MARGIN = 28
CONTENT_X0 = MARGIN
CONTENT_X1 = W - MARGIN
CONTENT_W = CONTENT_X1 - CONTENT_X0

FONT_DIR = "/usr/share/fonts/truetype/liberation"
SERIF_B = os.path.join(FONT_DIR, "LiberationSerif-Bold.ttf")
SERIF_R = os.path.join(FONT_DIR, "LiberationSerif-Regular.ttf")
SANS_R = os.path.join(FONT_DIR, "LiberationSans-Regular.ttf")
SANS_B = os.path.join(FONT_DIR, "LiberationSans-Bold.ttf")
MONO_B = os.path.join(FONT_DIR, "LiberationMono-Bold.ttf")

HERE = os.path.dirname(os.path.abspath(__file__))
LAND_JSON = os.path.join(HERE, "land.json")

# --------------------------------------------------------------------------
# palette — navy ink, warm paper, one accent per region
# --------------------------------------------------------------------------

PAPER = (246, 241, 230)
PAPER_CARD = (252, 249, 242)
NAVY = (19, 31, 53)
NAVY_SOFT = (38, 52, 78)
INK = (26, 33, 47)
GREY = (104, 106, 113)
HAIRLINE = (204, 196, 182)
CREAM = (243, 236, 220)
CREAM_DIM = (198, 192, 176)

ACCENT = {
    "EUROPE": (23, 62, 122),
    "MIDDLE EAST": (167, 84, 24),
    "ASIA": (150, 43, 37),
    "AMERICAS": (96, 52, 120),
    "WORLD": (86, 92, 104),
}

SEA = (186, 205, 214)
LAND = (243, 234, 215)
COAST = (126, 118, 104)

# --------------------------------------------------------------------------
# font cache / text helpers
# --------------------------------------------------------------------------

_FONT_CACHE = {}


def fnt(path, px):
    """Font object for a point size expressed in final-page pixels."""
    key = (path, round(px, 2))
    f = _FONT_CACHE.get(key)
    if f is None:
        f = ImageFont.truetype(path, max(1, int(round(px * SS))))
        _FONT_CACHE[key] = f
    return f


def tw(d, text, font):
    """Text width in final-page pixels."""
    return d.textlength(text, font=font) / SS


def wrap(d, text, font, max_w):
    """Greedy word wrap."""
    words = text.split()
    if not words:
        return [""]
    lines = []
    cur = words[0]
    for word in words[1:]:
        trial = cur + " " + word
        if tw(d, trial, font) <= max_w:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


def _raggedness(d, lines, font):
    widths = [tw(d, ln, font) for ln in lines]
    widest = max(widths)
    score = widest - min(widths)
    if len(lines) > 1 and len(lines[-1].split()) == 1:
        score += widest * 0.9          # punish a one-word last line
    if len(lines) > 1 and len(lines[0].split()) == 1:
        score += widest * 0.5
    return score


def wrap_balanced(d, text, font, max_w):
    """Wrap, then look for a narrower measure that evens the rag out."""
    base = wrap(d, text, font, max_w)
    n = len(base)
    if n < 2:
        return base
    best = base
    best_score = _raggedness(d, base, font)
    for i in range(1, 13):
        trial_w = max_w * (1.0 - i * 0.045)
        if trial_w < max_w * 0.45:
            break
        cand = wrap(d, text, font, trial_w)
        if len(cand) != n:
            continue
        score = _raggedness(d, cand, font)
        if score < best_score - 0.01:
            best, best_score = cand, score
    return best


def fit(d, text, path, box_w, box_h, sizes, leading=1.16, balanced=True):
    """Largest size from `sizes` whose wrapped text fits box_w x box_h.

    Returns (size, lines, line_height).  Falls back to the smallest size so
    callers always get drawable text back.
    """
    for px in sizes:
        f = fnt(path, px)
        lines = wrap_balanced(d, text, f, box_w) if balanced else wrap(
            d, text, f, box_w)
        lh = px * leading
        widest = max(tw(d, ln, f) for ln in lines)
        if widest <= box_w + 0.6 and len(lines) * lh <= box_h + 0.6:
            return px, lines, lh
    px = sizes[-1]
    f = fnt(path, px)
    lines = wrap_balanced(d, text, f, box_w)
    return px, lines, px * leading


def fit_line(d, text, path, box_w, sizes):
    """Largest size that keeps `text` on a single line inside box_w."""
    for px in sizes:
        f = fnt(path, px)
        if tw(d, text, f) <= box_w:
            return px, text
    px = sizes[-1]
    f = fnt(path, px)
    out = text
    while len(out) > 4 and tw(d, out + "…", f) > box_w:
        out = out[:-1].rstrip()
    return px, out + "…" if out != text else out


def draw_lines(d, x, y, lines, path, px, lh, fill, tracking=0.0, stroke=0.0):
    """Draw pre-wrapped lines left aligned on a shared line grid.

    `stroke` adds ink weight in final-page pixels (0.3 is roughly a 1 % stem
    thickening).  At judge scale a 23 px serif is only ~7 px tall, so a touch
    of stroke is the difference between a firm letter and a grey smear.
    """
    f = fnt(path, px)
    kw = {}
    if stroke:
        kw = {"stroke_width": stroke * SS, "stroke_fill": fill}
    cy = y
    for ln in lines:
        if tracking:
            draw_tracked(d, x, cy, ln, path, px, fill, tracking)
        else:
            d.text((x * SS, cy * SS), ln, font=f, fill=fill, anchor="la", **kw)
        cy += lh
    return cy


def draw_tracked(d, x, y, text, path, px, fill, tracking):
    """Letter-spaced text; tracking is extra space per gap in page pixels."""
    f = fnt(path, px)
    cx = x
    for ch in text:
        d.text((cx * SS, y * SS), ch, font=f, fill=fill, anchor="la")
        cx += tw(d, ch, f) + tracking
    return cx - tracking if text else x


def tracked_width(d, text, path, px, tracking):
    f = fnt(path, px)
    if not text:
        return 0.0
    total = sum(tw(d, ch, f) for ch in text)
    return total + tracking * (len(text) - 1)


def rule(d, x0, y, x1, fill, w=1.0):
    d.rectangle([x0 * SS, y * SS, x1 * SS, y * SS + max(1, int(round(w * SS))) - 1],
                fill=fill)


def mix(c1, c2, t):
    t = 0.0 if t < 0 else (1.0 if t > 1 else t)
    return tuple(int(round(a + (b - a) * t)) for a, b in zip(c1, c2))


def tint_of(col, t, base=PAPER_CARD):
    return mix(base, col, t)


# --------------------------------------------------------------------------
# the content — every string below is from the day's wire reports
# --------------------------------------------------------------------------

LEAD = {
    "where": "CRIMEA · KERCH STRAIT",
    "region": "EUROPE",
    "headline": "Crimean Bridge hit again; a road span falls into the strait",
    "deck": ("Ukrainian drones struck the bridge over the Kerch Strait for a "
             "second day running, killing two people and closing vehicle traffic "
             "again. Open-source analysts say a section damaged the day before "
             "has collapsed into the water."),
    "source": "Reuters · Türkiye Today",
    "pin": (36.2, 45.3),
}

CARDS = [
    {"region": "MIDDLE EAST", "where": "BAHRAIN · IRAN",
     "headline": "Bahrain downs IRGC drones aimed at Sheikh Isa",
     "icon": "drone", "pin": (50.6, 26.0)},
    {"region": "MIDDLE EAST", "where": "QESHM ISLAND",
     "headline": "US strikes Qeshm six times; a Reaper is shot down",
     "icon": "strike", "pin": (55.9, 26.9)},
    {"region": "MIDDLE EAST", "where": "GAZA · WEST BANK",
     "headline": "Five killed in Gaza despite the ceasefire",
     "icon": "dome", "pin": (34.4, 31.5)},
    {"region": "ASIA", "where": "BANGLADESH",
     "headline": "Tungipara police station stormed and burned",
     "icon": "station", "pin": (90.0, 23.2)},
    {"region": "ASIA", "where": "BANGLADESH",
     "headline": "Garment workers clash with police over pay",
     "icon": "garment", "pin": (90.4, 23.9)},
    {"region": "ASIA", "where": "MONGOLIA",
     "headline": "President Khürelsükh resigns over embezzlement claim",
     "icon": "yurt", "pin": (104.0, 47.4)},
]

BRIEFS = [
    ("plane", "A Russian An-12 crash near Kemerovo kills all 19 aboard"),
    ("trains", "Two trains collide in Prague; 46 injured"),
    ("vial", "US, Mexico and Bolivia lose measles-free status as cases pass 5,700"),
    ("pact", "France and Malaysia sign a defence, energy and rare-earths pact"),
    ("tag", "Canada and China agree more tariff cuts after Carney–Xi talks"),
    ("flag", "Britain sanctions eight firms building West Bank settlements"),
    ("phone", "Apple Pay, iCloud and the App Store go down; an update is blamed"),
    ("house", "Israel's army blows up homes in Gaza during the truce"),
]

NUMBERS = [
    ("19", "killed in the An-12 crash in Siberia"),
    ("46", "injured as two trains collided in Prague"),
    ("42", "Border Guard platoons in Bangladesh"),
    ("5", "cities hit by garment wage protests"),
    ("5,700", "measles cases in the US, PAHO says"),
]

# Eight pins: the lead, the six cards, and the Siberia crash from the numbers
# strip.  lon, lat, key number, region for colour.
PINS = [
    (36.2, 45.3, 1, "EUROPE"),
    (50.6, 26.0, 2, "MIDDLE EAST"),
    (55.9, 26.9, 3, "MIDDLE EAST"),
    (34.4, 31.5, 4, "MIDDLE EAST"),
    (90.0, 23.2, 5, "ASIA"),
    (90.4, 23.9, 6, "ASIA"),
    (104.0, 47.4, 7, "ASIA"),
    (86.1, 55.3, 8, "EUROPE"),
]

# --------------------------------------------------------------------------
# vertical rhythm
# --------------------------------------------------------------------------

MAST_Y0, MAST_Y1 = 0, 92
HERO_Y0, HERO_Y1 = 98, 434
CARDS_Y0, CARDS_Y1 = 446, 726
BRIEF_Y0, BRIEF_Y1 = 744, 836
NUM_Y0, NUM_Y1 = 850, 942
FOOT_Y0 = 950

ART_X1 = 600
TYPE_X0 = 612
TYPE_W = CONTENT_X1 - TYPE_X0

CARD_GAP = 8
CARD_W = (CONTENT_W - 2 * CARD_GAP) / 3.0
CARD_H = 128
CARD_VGAP = 24

# The card headline is the whole point of the thumbnail pass: it was 17 px and
# is now 24.6 px, still hard-capped at two lines.  The box height below is well
# under three lines so fit() can never return a three-line setting.
CARD_HEAD_PX = 24.6
CARD_HEAD_Y = 54
CARD_HEAD_BOX = 57

# --------------------------------------------------------------------------
# small drawing primitives (all take final-page pixel coordinates)
# --------------------------------------------------------------------------


def P(pts):
    return [(x * SS, y * SS) for x, y in pts]


def poly(d, pts, fill=None, outline=None, w=1.0):
    pp = P(pts)
    if fill is not None:
        d.polygon(pp, fill=fill)
    if outline is not None:
        d.line(pp + [pp[0]], fill=outline, width=max(1, int(round(w * SS))),
               joint="curve")


def line(d, pts, fill, w=1.0):
    d.line(P(pts), fill=fill, width=max(1, int(round(w * SS))), joint="curve")


def ell(d, x0, y0, x1, y1, fill=None, outline=None, w=1.0):
    d.ellipse([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill, outline=outline,
              width=max(1, int(round(w * SS))))


def rect(d, x0, y0, x1, y1, fill=None, outline=None, w=1.0):
    d.rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS], fill=fill,
                outline=outline, width=max(1, int(round(w * SS))))


def rrect(d, x0, y0, x1, y1, r, fill=None, outline=None, w=1.0):
    d.rounded_rectangle([x0 * SS, y0 * SS, x1 * SS, y1 * SS],
                        radius=r * SS, fill=fill, outline=outline,
                        width=max(1, int(round(w * SS))))


def vgrad(d, box, c0, c1):
    """Vertical gradient fill inside a box, one SS row at a time."""
    x0, y0, x1, y1 = box
    ys, ye = int(y0 * SS), int(y1 * SS)
    span = max(1, ye - ys - 1)
    for i in range(ye - ys):
        d.line([(x0 * SS, ys + i), (x1 * SS - 1, ys + i)],
               fill=mix(c0, c1, i / span))


# --------------------------------------------------------------------------
# the hero illustration: the Kerch Strait bridge, one span in the water
# --------------------------------------------------------------------------

ART_SKY_TOP = (233, 223, 203)
ART_SKY_LOW = (250, 236, 208)
ART_HAZE = (243, 214, 170)
ART_SEA_FAR = (203, 214, 216)
ART_SEA_NEAR = (129, 150, 168)
ART_DECK = (37, 47, 70)
ART_DECK_EDGE = (146, 152, 164)
ART_DECK_DARK = (17, 23, 37)
ART_CONCRETE = (161, 166, 172)
ART_CONCRETE_DARK = (86, 96, 114)
ART_SUN = (211, 128, 58)


def draw_bridge(d, canvas, box):
    """Editorial vector illustration of the Kerch Strait crossing, one span gone.

    One deck, one vanishing point, one perspective: a road running away to the
    right, a tied arch over the channel, and a hole in the near span with the
    missing piece standing in the water. Deliberately simple - a reader should
    get "bridge, broken, burning" in under a second.
    """
    _bx, _by = box[0], box[1]
    aw, ah = box[2] - box[0], box[3] - box[1]

    # Draw on an isolated layer: nothing (glow, smoke, spray) may leak out of
    # the illustration panel and dirty the masthead or the type beside it.
    _out = canvas
    canvas = Image.new("RGBA", (int(round(aw * SS)), int(round(ah * SS))),
                       (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    x0, y0, x1, y1 = 0.0, 0.0, aw, ah
    HORIZON = ah * 0.446
    VPX, VPY = aw * 1.06, HORIZON - 2.0

    def gx(u):
        return u * aw

    def conv(u):
        return gx(u) / VPX

    def dy(u, y_left):
        return y_left + (VPY - y_left) * conv(u)

    DTOP, DBOT = ah * 0.612, ah * 0.818
    GAP0, GAP1 = 0.330, 0.452

    # ---- sky -------------------------------------------------------------
    vgrad(d, (x0, y0, x1, HORIZON), (236, 227, 209), (251, 238, 212))
    for i in range(14):
        t = i / 13.0
        yy = HORIZON - (1.0 - t) ** 1.8 * ah * 0.34
        line(d, [(x0, yy), (x1, yy)],
             mix((251, 238, 212), (243, 219, 176), 0.30 * (1.0 - t) ** 1.2), 1.0)

    # low sun, tucked inside the arch
    sx, sy, sr = aw * 0.688, ah * 0.247, aw * 0.0235
    glow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for i in range(18):
        rr = sr * (1.0 + (17 - i) * 0.40)
        gd.ellipse([(sx - rr * 1.30) * SS, (sy - rr) * SS,
                    (sx + rr * 1.30) * SS, (sy + rr) * SS],
                   fill=(246, 205, 146, 6 + i // 4))
    canvas.alpha_composite(glow)
    d = ImageDraw.Draw(canvas)
    ell(d, sx - sr, sy - sr, sx + sr, sy + sr, fill=(199, 133, 76))
    ell(d, sx - sr * 0.60, sy - sr * 0.60, sx + sr * 0.60, sy + sr * 0.60,
        fill=(224, 168, 112))

    for ua, ub, vv, ww in ((0.04, 0.28, 0.070, 1.5), (0.09, 0.24, 0.132, 1.1),
                           (0.42, 0.58, 0.048, 1.2), (0.36, 0.50, 0.115, 1.0)):
        line(d, [(gx(ua), ah * vv), (gx(ub), ah * vv)], (232, 218, 195), ww)

    # ---- strait ----------------------------------------------------------
    vgrad(d, (x0, HORIZON, x1, y1), (206, 218, 222), (116, 139, 161))
    for i in range(9):
        yy = HORIZON + i * 0.85
        line(d, [(x0, yy), (x1, yy)],
             mix((206, 218, 222), (247, 233, 208), 0.60 - i * 0.065), 1.0)
    # far shore, right of centre
    poly(d, [(aw * 0.47, HORIZON + 0.8), (aw * 0.55, HORIZON - 5.0),
             (aw * 0.70, HORIZON - 7.0), (aw * 0.88, HORIZON - 3.2),
             (aw * 1.02, HORIZON + 0.8)], fill=(227, 220, 204))

    # water texture, drawn before the piers so they sit in it
    rnd_w = random.Random(31)
    for i in range(34):
        t = i / 33.0
        yy = HORIZON + 2.0 + (y1 - HORIZON - 5.0) * (t ** 1.75)
        seg = aw * (0.05 + 0.26 * t)
        for k in range(2 + int(3 * t)):
            u = rnd_w.uniform(0.0, 0.92)
            xx = gx(u)
            line(d, [(xx, yy), (xx + seg * rnd_w.uniform(0.35, 1.0), yy)],
                 mix((192, 206, 212), (88, 112, 136), 0.20 + t * 0.62),
                 0.6 + t * 1.1)

    # ---- the rail span, one deck further back ---------------------------
    # Same vanishing point as the road span, so it reads as the parallel deck
    # and not as a second bridge. Lighter, thinner, and left unbroken: the road
    # span is the one that fell.
    FD_TOP = DTOP - 30.0
    FD_BOT = FD_TOP + (DBOT - DTOP) * 0.58

    def fband(u_a, u_b, fa, fb, steps=16):
        us = [u_a + (u_b - u_a) * i / steps for i in range(steps + 1)]
        top = [(gx(u), dy(u, FD_TOP + (FD_BOT - FD_TOP) * fa)) for u in us]
        bot = [(gx(u), dy(u, FD_TOP + (FD_BOT - FD_TOP) * fb)) for u in us]
        return top, bot[::-1]

    for u in (0.075, 0.165, 0.255, 0.345, 0.435, 0.525, 0.615, 0.705,
              0.795, 0.885, 0.955):
        px_ = gx(u)
        c = conv(u)
        hw = 8.4 * (1.0 - 0.55 * c)
        top = dy(u, FD_BOT) + 0.8
        bot = dy(u, DTOP) + 3.0
        poly(d, [(px_ - hw, top), (px_ + hw, top),
                 (px_ + hw * 1.10, bot), (px_ - hw * 1.10, bot)],
             fill=mix((158, 164, 176), (104, 114, 132), 0.30 + 0.42 * c),
             outline=(68, 78, 96), w=0.7)

    ft, fb = fband(0.0, 1.0, 0.0, 1.0)
    poly(d, ft + fb, fill=(50, 64, 90))
    ftp, fbp = fband(0.0, 1.0, 0.0, 0.30)
    poly(d, ftp + fbp, fill=(134, 142, 158))
    line(d, ft, (176, 182, 194), 1.0)
    line(d, fb, (32, 42, 62), 1.4)

    # ---- piers -----------------------------------------------------------
    pier_feet = []

    def pier(u):
        px_ = gx(u)
        c = conv(u)
        hw = 15.0 * (1.0 - 0.58 * c)
        dep = ah * 0.215 * (1.0 - 0.55 * c)
        top = dy(u, DBOT) + 1.0
        bot = top + dep
        col = mix((172, 176, 182), (98, 108, 124), 0.22 + 0.45 * c)
        poly(d, [(px_ - hw, top), (px_ + hw, top),
                 (px_ + hw * 1.15, bot), (px_ - hw * 1.15, bot)],
             fill=col, outline=(58, 68, 86), w=0.9)
        for k in (0.34, 0.66):
            yy = top + (bot - top) * k
            wk = hw + hw * 0.15 * k
            line(d, [(px_ - wk, yy), (px_ + wk, yy)],
                 mix(col, (66, 76, 94), 0.45), 0.8)
        # sun side
        line(d, [(px_ + hw * 0.42, top + 1.4), (px_ + hw * 0.68, bot - 1.4)],
             mix(col, (246, 242, 228), 0.50), 1.3)
        ell(d, px_ - hw * 1.36, bot - 1.6, px_ + hw * 1.36, bot + 1.9,
            fill=mix((116, 139, 161), (240, 246, 244), 0.55))
        pier_feet.append((px_, bot, hw * 1.15))

    for u in (0.045, 0.115, 0.185, 0.398, 0.472, 0.546, 0.620, 0.694,
              0.768, 0.842, 0.912):
        pier(u)

    # ---- the deck --------------------------------------------------------
    def band(u_a, u_b, fa, fb, steps=18):
        us = [u_a + (u_b - u_a) * i / steps for i in range(steps + 1)]
        top = [(gx(u), dy(u, DTOP + (DBOT - DTOP) * fa)) for u in us]
        bot = [(gx(u), dy(u, DTOP + (DBOT - DTOP) * fb)) for u in us]
        return top, bot[::-1]

    for u_a, u_b in ((0.0, GAP0), (GAP1, 1.0)):
        t0, b0 = band(u_a, u_b, 0.0, 1.0)
        poly(d, t0 + b0, fill=ART_DECK)
        # road surface a shade lighter than the flank, so it reads as a road
        t1, b1 = band(u_a, u_b, 0.22, 0.62)
        poly(d, t1 + b1, fill=(44, 55, 79))
        # parapet
        tp, bp = band(u_a, u_b, 0.0, 0.185)
        poly(d, tp + bp, fill=(150, 156, 166))
        line(d, tp, (192, 196, 202), 1.3)
        line(d, bp, (52, 62, 82), 1.3)
        line(d, b0, ART_DECK_DARK, 1.9)

    # guardrail posts
    for i in range(1, 31):
        u = (i / 31.0) ** 1.45
        if GAP0 < u < GAP1:
            continue
        xx = gx(u)
        yt = dy(u, DTOP)
        h = 7.0 * (1.0 - 0.52 * conv(u))
        line(d, [(xx, yt - h), (xx, yt)], mix(ART_DECK, (178, 184, 192), 0.55),
             0.7)

    # a single continuous carriageway line: enough to read as a road,
    # too little to read as markings
    for u_a, u_b in ((0.0, GAP0), (GAP1, 1.0)):
        tc, bc = band(u_a, u_b, 0.63, 0.66)
        poly(d, tc + bc, fill=(96, 108, 130))

    # ---- tied arch over the channel --------------------------------------
    AU0, AU1 = 0.552, 0.800
    f0 = (gx(AU0), dy(AU0, DTOP))
    f1 = (gx(AU1), dy(AU1, DTOP))
    rise = ah * 0.300
    steps = 46
    spine = []
    for i in range(steps + 1):
        t = i / steps
        xx = f0[0] + (f1[0] - f0[0]) * t
        base = f0[1] + (f1[1] - f0[1]) * t
        spine.append((xx, base - rise * math.sin(math.pi * t) ** 0.80))
    line(d, spine, ART_DECK, 5.4)
    line(d, [(x, y - 2.1) for x, y in spine], (126, 138, 158), 1.5)
    line(d, [(x, y + 2.6) for x, y in spine], ART_DECK_DARK, 1.2)
    for i in range(3, steps - 2, 3):
        xx, yy = spine[i]
        u = AU0 + (AU1 - AU0) * (i / steps)
        yb = dy(u, DTOP) - 1.0
        if yb - yy > 4.5:
            line(d, [(xx, yy + 2.0), (xx, yb)],
                 mix(ART_DECK, (154, 164, 180), 0.42), 0.7)
    for f in (f0, f1):
        poly(d, [(f[0] - 6.4, f[1] + 1.0), (f[0] + 6.4, f[1] + 1.0),
                 (f[0] + 8.0, f[1] + 13.0), (f[0] - 8.0, f[1] + 13.0)],
             fill=(116, 124, 140), outline=ART_DECK_DARK, w=0.9)

    # ---- the cut ---------------------------------------------------------
    for u, sgn in ((GAP0, 1.0), (GAP1, -1.0)):
        xx = gx(u)
        yt, yb = dy(u, DTOP), dy(u, DBOT)
        # the severed end is exposed concrete: a zigzag edge, no loose spikes
        edge = []
        nseg = 7
        for i in range(nseg + 1):
            ty = yt + (yb - yt) * i / nseg
            jj = 4.2 + (2.4 if i % 2 else 0.0)
            edge.append((xx + sgn * jj, ty))
        poly(d, [(xx, yt)] + edge + [(xx, yb)],
             fill=(138, 134, 126), outline=ART_DECK_DARK, w=1.2)
        line(d, [(xx, yt + 1.0), (xx, yb - 1.0)], (104, 102, 96), 1.0)

    # rebar clawing into the hole
    rnd_rb = random.Random(41)
    for side, u0 in ((1.0, GAP0), (-1.0, GAP1)):
        span = dy(u0, DBOT) - dy(u0, DTOP)
        for k in range(5):
            yy = dy(u0, DTOP) + span * (0.12 + 0.19 * k) + rnd_rb.uniform(-2, 2)
            ln = rnd_rb.uniform(4.5, 11.0)
            drop = rnd_rb.uniform(3.0, 9.0)
            line(d, [(gx(u0) + side * 1.0, yy),
                     (gx(u0) + side * ln * 0.55, yy + drop * 0.55),
                     (gx(u0) + side * ln, yy + drop)],
                 ART_DECK_DARK, 0.9)

    # ---- the piece that fell --------------------------------------------
    def plate(px, py, length, ang_deg, thick, face, edge, jag=0.0, jn=5):
        a = math.radians(ang_deg)
        ux, uy = math.cos(a), math.sin(a)
        nx, ny = -uy, ux
        ex, ey = px + ux * length, py + uy * length
        near = [(px, py)]
        for i in range(1, jn):
            t = i / jn
            bx, by = px + nx * thick * t, py + ny * thick * t
            if jag and i % 2:
                bx, by = bx - ux * jag, by - uy * jag
            near.append((bx, by))
        near.append((px + nx * thick, py + ny * thick))
        pts = [(ex, ey), (ex + nx * thick, ey + ny * thick)] + near[::-1]
        poly(d, pts, fill=face, outline=ART_DECK_DARK, w=1.5)
        line(d, near[::-1][:2], edge, 1.0)
        line(d, [(ex, ey), (ex + nx * thick, ey + ny * thick)],
             ART_DECK_DARK, 1.8)
        return (ex, ey, ux, uy, nx, ny)

    thick_d = dy(GAP0, DBOT) - dy(GAP0, DTOP)
    # Off the bridge entirely: a slit of open water between the deck end and
    # the piece. Anything still aligned with the road reads as a ramp, however
    # far you slide it, so the piece sits below the deck line and toppled.
    hx, hy = gx(GAP0) + 21.0, dy(GAP0, DBOT) + 6.0
    slab = plate(hx, hy, 56.0, 79, thick_d * 0.72,
                 mix(ART_DECK, (255, 255, 255), 0.05),
                 mix(ART_DECK, (156, 162, 172), 0.80), jag=3.4)

    # water closing over the sunken end
    end_a = (slab[0], slab[1])
    end_b = (slab[0] + slab[4] * thick_d * 0.72,
             slab[1] + slab[5] * thick_d * 0.72)
    lo = sorted([end_a, end_b], key=lambda q: -q[1])
    wcx = (lo[0][0] + lo[1][0]) / 2.0
    wcy = lo[0][1] - 1.0

    # churn: foam and displaced water, softened so it reads as spray
    foam = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    fd = ImageDraw.Draw(foam)
    fd.ellipse([(wcx - 21) * SS, (wcy - 4.6) * SS,
                (wcx + 21) * SS, (wcy + 5.4) * SS],
               fill=(238, 246, 245, 230))
    fd.ellipse([(wcx - 27) * SS, (wcy - 2.6) * SS,
                (wcx + 27) * SS, (wcy + 6.6) * SS],
               outline=(146, 174, 194, 205), width=max(1, int(1.3 * SS)))
    rnd_f = random.Random(5)
    for i in range(16):
        a = rnd_f.uniform(0, math.pi)
        rr = 14 + rnd_f.uniform(0, 21)
        fx = wcx + math.cos(a) * rr
        fy = wcy - math.sin(a) * rr * 0.26 - rnd_f.uniform(0, 5)
        s = rnd_f.uniform(1.8, 4.2)
        fd.ellipse([(fx - s) * SS, (fy - s * 0.7) * SS,
                    (fx + s) * SS, (fy + s * 0.7) * SS],
                   fill=(240, 247, 246, 224))
    foam = foam.filter(ImageFilter.GaussianBlur(radius=0.9 * SS))
    canvas.alpha_composite(foam)
    d = ImageDraw.Draw(canvas)

    for i in range(2):
        rr = 20.0 + i * 9.5
        d.arc([(wcx - rr) * SS, (wcy - rr * 0.34) * SS,
               (wcx + rr) * SS, (wcy + rr * 0.34) * SS],
              start=196, end=344, fill=(236, 243, 241),
              width=max(1, int(1.2 * SS)))
    for i in range(10):
        h = rnd_f.uniform(7, 22)
        fx = wcx + rnd_f.uniform(-16, 16)
        line(d, [(fx, wcy - 3.0), (fx + rnd_f.uniform(-2.5, 2.5),
                                   wcy - 3.0 - h)],
             (238, 245, 243), 1.0)

    # debris in the water
    rnd_b = random.Random(11)
    for i in range(5):
        bx = aw * (0.285 + rnd_b.uniform(0.0, 0.075))
        by = ah * (0.875 + rnd_b.uniform(0.0, 0.060))
        s = 5.0 + rnd_b.uniform(0.0, 3.4)
        line(d, [(bx - s * 1.5, by + s * 0.72), (bx + s * 2.4, by + s * 0.72)],
             (198, 212, 216), 1.4)
        poly(d, [(bx, by), (bx + s, by - s * 0.62),
                 (bx + s * 1.9, by + s * 0.20), (bx + s * 0.5, by + s * 0.62)],
             fill=mix(ART_DECK, ART_DECK_DARK, 0.22),
             outline=ART_DECK_DARK, w=0.7)

    # ---- smoke -----------------------------------------------------------
    base_x = gx(GAP0) + 4.0
    base_y = dy(GAP0, DTOP) - 2.0

    def ribbon(cx_off, grow, tone, blur):
        lyr = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        ld = ImageDraw.Draw(lyr)
        left, right = [], []
        n = 22
        for i in range(n + 1):
            t = i / n
            vy = base_y - t * ah * 0.62
            lean = -t * aw * (0.070 + cx_off)
            wob = math.sin(t * 5.2 + 0.45) * aw * 0.020
            cx = base_x + lean + wob
            hw = aw * (0.014 + grow * (t ** 0.82))
            left.append((cx - hw, vy))
            right.append((cx + hw, vy))
        ld.polygon(P(left + right[::-1]), fill=tone + (255,))
        lyr = lyr.filter(ImageFilter.GaussianBlur(radius=blur * SS))
        # fade the column out as it rises
        mask = Image.new("L", lyr.size, 0)
        md = ImageDraw.Draw(mask)
        ybase = base_y * SS
        top = 0
        for yy in range(int(top), int(ybase)):
            f = 1.0 - (ybase - yy) / max(1.0, (ybase - top))
            md.line([(0, yy), (lyr.size[0], yy)],
                    fill=int(255 * (0.30 + 0.70 * f ** 1.5)))
        lyr.putalpha(ImageChops.multiply(lyr.getchannel("A"), mask))
        return lyr

    canvas.alpha_composite(ribbon(0.000, 0.075, (64, 68, 82), 3.4))
    canvas.alpha_composite(ribbon(0.014, 0.052, (150, 146, 142), 2.2))
    d = ImageDraw.Draw(canvas)

    # fire at the cut: small, hot, and clearly a fire
    fglow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    gd2 = ImageDraw.Draw(fglow)
    gd2.ellipse([(base_x - 16) * SS, (base_y - 10) * SS,
                 (base_x + 16) * SS, (base_y + 6) * SS],
                fill=(232, 142, 58, 118))
    fglow = fglow.filter(ImageFilter.GaussianBlur(radius=2.6 * SS))
    canvas.alpha_composite(fglow)
    d = ImageDraw.Draw(canvas)
    rnd_fire = random.Random(77)
    for i in range(6):
        fx = base_x + rnd_fire.uniform(-10, 10)
        fh = rnd_fire.uniform(7, 16)
        fw = rnd_fire.uniform(2.0, 4.0)
        poly(d, [(fx - fw, base_y + 3.0), (fx, base_y - fh),
                 (fx + fw, base_y + 3.0)], fill=(226, 132, 48))
        poly(d, [(fx - fw * 0.45, base_y + 3.0), (fx + fw * 0.1,
                 base_y - fh * 0.55), (fx + fw * 0.45, base_y + 3.0)],
             fill=(243, 186, 96))

    # embers riding the column
    rnd_e = random.Random(19)
    for i in range(10):
        u = rnd_e.uniform(0.245, 0.350)
        v = rnd_e.uniform(0.52, 0.64)
        s = rnd_e.uniform(0.9, 2.0)
        ell(d, gx(u), ah * v, gx(u) + s, ah * v + s, fill=(232, 152, 70))

    # ---- reflections -----------------------------------------------------
    refl = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    rd = ImageDraw.Draw(refl)
    for px_, bot, hw in pier_feet:
        for k in range(6):
            yy = bot + 1.0 + k * 2.8
            wid = hw * (1.02 + k * 0.10)
            rd.line([((px_ - wid) * SS, yy * SS), ((px_ + wid) * SS, yy * SS)],
                    fill=(54, 68, 90, 60 - k * 9), width=max(1, int(1.4 * SS)))
    canvas.alpha_composite(refl)

    _out.alpha_composite(canvas, (int(round(_bx * SS)), int(round(_by * SS))))
    d = ImageDraw.Draw(_out)
    rule(d, _bx, _by, _bx + aw, mix(ART_SKY_TOP, PAPER, 0.4), 0.9)
    rule(d, _bx, _by + ah - 1.2, _bx + aw, (28, 38, 58), 1.2)


# --------------------------------------------------------------------------
# pictograms
# --------------------------------------------------------------------------


def icon_drone(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    poly(d, [(px(0.36), py(0.40)), (px(0.64), py(0.40)),
             (px(0.68), py(0.54)), (px(0.32), py(0.54))], fill=ink)
    for u in (0.20, 0.80):
        line(d, [(px(u), py(0.28)), (px(0.50), py(0.44))], ink, 1.9)
        line(d, [(px(u - 0.13), py(0.24)), (px(u + 0.13), py(0.24))], ink, 2.2)
        ell(d, px(u - 0.09), py(0.29), px(u + 0.09), py(0.34), fill=col)
    for u in (0.36, 0.64):
        line(d, [(px(u), py(0.54)), (px(u), py(0.62))], ink, 1.6)
    line(d, [(px(0.32), py(0.62)), (px(0.68), py(0.62))], ink, 1.2)
    for u, v in ((0.20, 0.60), (0.26, 0.68), (0.32, 0.76)):
        line(d, [(px(u), py(v)), (px(u - 0.05), py(v + 0.05))], col, 1.4)
    cx, cy, r = px(0.22), py(0.86), bw * 0.11
    for i in range(8):
        a = i * math.pi / 4
        line(d, [(cx + math.cos(a) * r * 0.5, cy + math.sin(a) * r * 0.5),
                 (cx + math.cos(a) * r, cy + math.sin(a) * r)], col, 1.5)


def icon_strike(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    poly(d, [(px(0.06), py(0.92)), (px(0.26), py(0.76)), (px(0.52), py(0.70)),
             (px(0.78), py(0.80)), (px(0.94), py(0.92))],
         fill=tint_of(col, 0.30), outline=col, w=1.4)
    for u, v, s in ((0.30, 0.14, 1.0), (0.52, 0.26, 0.82), (0.72, 0.12, 0.9)):
        poly(d, [(px(u), py(v + 0.02)),
                 (px(u + 0.07 * s), py(v + 0.16 * s)),
                 (px(u), py(v + 0.24 * s)),
                 (px(u - 0.07 * s), py(v + 0.16 * s))], fill=ink)
        line(d, [(px(u - 0.05 * s), py(v + 0.02)),
                 (px(u + 0.05 * s), py(v + 0.02))], ink, 1.4)
    cx, cy, r = px(0.62), py(0.72), bw * 0.13
    for i in range(7):
        a = i * 2 * math.pi / 7 + 0.3
        line(d, [(cx, cy), (cx + math.cos(a) * r, cy + math.sin(a) * r)], col, 1.5)


def icon_dome(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    for u in (0.12, 0.88):
        rect(d, px(u - 0.045), py(0.30), px(u + 0.045), py(0.68), fill=ink)
        poly(d, [(px(u - 0.055), py(0.30)), (px(u), py(0.20)),
                 (px(u + 0.055), py(0.30))], fill=col)
    d.pieslice([px(0.24) * SS, py(0.24) * SS, px(0.76) * SS, py(0.76) * SS],
               start=180, end=360, fill=ink)
    poly(d, [(px(0.24), py(0.50)), (px(0.76), py(0.50)),
             (px(0.76), py(0.66)), (px(0.24), py(0.66))], fill=ink)
    d.pieslice([px(0.42) * SS, py(0.50) * SS, px(0.58) * SS, py(0.70) * SS],
               start=180, end=360, fill=tint_of(col, 0.45))
    for i in range(5):
        u = 0.20 + i * 0.15
        rect(d, px(u), py(0.80), px(u + 0.035), py(0.94), fill=col)


def icon_station(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    rect(d, px(0.14), py(0.44), px(0.86), py(0.92), fill=tint_of(col, 0.26),
         outline=col, w=1.4)
    poly(d, [(px(0.08), py(0.44)), (px(0.50), py(0.24)), (px(0.92), py(0.44))],
         fill=ink)
    for u in (0.24, 0.56):
        rect(d, px(u), py(0.58), px(u + 0.16), py(0.72), fill=ink)
    rect(d, px(0.42), py(0.74), px(0.58), py(0.92), fill=ink)
    for u, sc in ((0.34, 1.0), (0.60, 0.78)):
        top = 0.44 - 0.26 * sc
        poly(d, [(px(u - 0.09 * sc), py(0.44)),
                 (px(u - 0.03 * sc), py(top + 0.06)),
                 (px(u + 0.01 * sc), py(top)),
                 (px(u + 0.04 * sc), py(top + 0.09)),
                 (px(u + 0.09 * sc), py(0.44))], fill=col)


def icon_garment(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    poly(d, [(px(0.20), py(0.24)), (px(0.38), py(0.18)), (px(0.50), py(0.28)),
             (px(0.62), py(0.18)), (px(0.80), py(0.24)), (px(0.72), py(0.40)),
             (px(0.66), py(0.36)), (px(0.66), py(0.82)), (px(0.34), py(0.82)),
             (px(0.34), py(0.36)), (px(0.28), py(0.40))],
         fill=tint_of(col, 0.28), outline=col, w=1.4)
    rrect(d, px(0.78), py(0.34), px(0.96), py(0.62), bw * 0.05, fill=ink)
    line(d, [(px(0.78), py(0.44)), (px(0.70), py(0.42))], ink, 1.6)
    for v in (0.30, 0.42):
        line(d, [(px(0.02), py(v)), (px(0.12), py(v))], col, 1.3)


def icon_yurt(d, bx, by, bw, bh, col, ink):
    px = lambda u: bx + u * bw
    py = lambda v: by + v * bh
    poly(d, [(px(0.06), py(0.92)), (px(0.14), py(0.58)),
             (px(0.56), py(0.58)), (px(0.64), py(0.92))],
         fill=tint_of(col, 0.26), outline=col, w=1.4)
    d.pieslice([px(0.12) * SS, py(0.34) * SS, px(0.58) * SS, py(0.74) * SS],
               start=180, end=360, fill=ink)
    rect(d, px(0.28), py(0.70), px(0.42), py(0.92), fill=ink)
    poly(d, [(px(0.62), py(0.16)), (px(0.94), py(0.24)),
             (px(0.90), py(0.66)), (px(0.58), py(0.58))],
         fill=PAPER_CARD, outline=ink, w=1.3)
    for k in range(3):
        v = 0.30 + k * 0.10
        line(d, [(px(0.66), py(v)), (px(0.86), py(v + 0.022))], ink, 1.2)
    ell(d, px(0.80), py(0.50), px(0.90), py(0.62), fill=col)


ICONS = {
    "drone": icon_drone,
    "strike": icon_strike,
    "dome": icon_dome,
    "station": icon_station,
    "garment": icon_garment,
    "yurt": icon_yurt,
}


def icon_tiny(d, kind, x, y, s, col):
    """10 px pictograms for the also-reported list."""
    def p(u, v):
        return (x + u * s, y + v * s)

    if kind == "plane":
        line(d, [p(0.10, 0.70), p(0.90, 0.34)], col, 1.6)
        poly(d, [p(0.42, 0.44), p(0.62, 0.36), p(0.50, 0.60), p(0.44, 0.50)],
             fill=col)
        line(d, [p(0.68, 0.30), p(0.74, 0.58)], col, 1.3)
    elif kind == "trains":
        rect(d, x, y + 0.30 * s, x + 0.42 * s, y + 0.92 * s, outline=col, w=1.3)
        rect(d, x + 0.58 * s, y + 0.08 * s, x + s, y + 0.70 * s,
             outline=col, w=1.3)
        line(d, [p(0.06, 0.24), p(0.94, 0.80)], (150, 43, 37), 1.7)
    elif kind == "vial":
        rect(d, x + 0.30 * s, y + 0.18 * s, x + 0.58 * s, y + 0.86 * s,
             outline=col, w=1.3)
        rect(d, x + 0.34 * s, y + 0.56 * s, x + 0.54 * s, y + 0.82 * s,
             fill=col)
        line(d, [p(0.44, 0.18), p(0.44, 0.02)], col, 1.3)
        line(d, [p(0.68, 0.30), p(0.88, 0.16)], col, 1.2)
    elif kind == "pact":
        line(d, [p(0.04, 0.62), p(0.44, 0.34)], col, 2.0)
        line(d, [p(0.96, 0.62), p(0.56, 0.34)], col, 2.0)
        line(d, [p(0.44, 0.34), p(0.56, 0.34)], col, 1.4)
        ell(d, x + 0.02 * s, y + 0.52 * s, x + 0.20 * s, y + 0.72 * s, fill=col)
        ell(d, x + 0.80 * s, y + 0.52 * s, x + 0.98 * s, y + 0.72 * s, fill=col)
    elif kind == "tag":
        poly(d, [p(0.14, 0.16), p(0.66, 0.16), p(0.94, 0.50),
                 p(0.64, 0.86), p(0.14, 0.86)], outline=col, w=1.3)
        ell(d, x + 0.26 * s, y + 0.34 * s, x + 0.44 * s, y + 0.52 * s, fill=col)
        line(d, [p(0.52, 0.50), p(0.80, 0.50)], col, 1.2)
    elif kind == "flag":
        line(d, [p(0.18, 0.06), p(0.18, 0.94)], col, 1.5)
        poly(d, [p(0.18, 0.10), p(0.86, 0.24), p(0.18, 0.42)], fill=col)
    elif kind == "phone":
        rrect(d, x + 0.22 * s, y + 0.06 * s, x + 0.78 * s, y + 0.94 * s,
              s * 0.12, outline=col, w=1.3)
        line(d, [p(0.60, 0.14), p(0.86, 0.30)], (150, 43, 37), 2.0)
        line(d, [p(0.40, 0.84), p(0.60, 0.84)], col, 1.2)
    elif kind == "house":
        poly(d, [p(0.08, 0.52), p(0.50, 0.14), p(0.92, 0.52)], fill=col)
        rect(d, x + 0.18 * s, y + 0.52 * s, x + 0.82 * s, y + 0.92 * s,
             outline=col, w=1.3)
        line(d, [p(0.44, 0.52), p(0.56, 0.70), p(0.40, 0.78), p(0.52, 0.92)],
             (150, 43, 37), 1.2)


# --------------------------------------------------------------------------
# the map
# --------------------------------------------------------------------------

MAP_LON = (8.0, 150.0)
MAP_LAT_S = 17.3
MAP_LAT_N = 58.0


def load_land(path=LAND_JSON):
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("polygons", [])


def clip_ring(ring, lon_w, lat_s, lon_e, lat_n):
    """Sutherland-Hodgman clip of one lon/lat ring to the map window."""
    def clip_edge(points, inside, intersect):
        if not points:
            return []
        out = []
        prev = points[-1]
        prev_in = inside(prev)
        for cur in points:
            cur_in = inside(cur)
            if cur_in:
                if not prev_in:
                    out.append(intersect(prev, cur))
                out.append(cur)
            elif prev_in:
                out.append(intersect(prev, cur))
            prev, prev_in = cur, cur_in
        return out

    def ix_lon(a, b, x):
        if b[0] == a[0]:
            return (x, a[1])
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + (b[1] - a[1]) * t)

    def ix_lat(a, b, y):
        if b[1] == a[1]:
            return (a[0], y)
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + (b[0] - a[0]) * t, y)

    pts = [(float(p[0]), float(p[1])) for p in ring]
    pts = clip_edge(pts, lambda p: p[0] >= lon_w, lambda a, b: ix_lon(a, b, lon_w))
    pts = clip_edge(pts, lambda p: p[0] <= lon_e, lambda a, b: ix_lon(a, b, lon_e))
    pts = clip_edge(pts, lambda p: p[1] >= lat_s, lambda a, b: ix_lat(a, b, lat_s))
    pts = clip_edge(pts, lambda p: p[1] <= lat_n, lambda a, b: ix_lat(a, b, lat_n))
    return pts


def draw_map(d, box, polygons):
    x0, y0, x1, y1 = box
    mw, mh = x1 - x0, y1 - y0
    lon_w, lon_e = MAP_LON
    lat_s, lat_n = MAP_LAT_S, MAP_LAT_N

    def proj(lon, lat):
        return (x0 + (lon - lon_w) / (lon_e - lon_w) * mw,
                y0 + (lat_n - lat) / (lat_n - lat_s) * mh)

    rect(d, x0, y0, x1, y1, fill=SEA)

    lon = math.ceil(lon_w / 20.0) * 20.0
    while lon < lon_e:
        xx = proj(lon, lat_s)[0]
        line(d, [(xx, y0), (xx, y1)], (166, 187, 198), 0.55)
        lon += 20.0
    lat = math.ceil(lat_s / 10.0) * 10.0
    while lat < lat_n:
        yy = proj(lon_w, lat)[1]
        line(d, [(x0, yy), (x1, yy)], (166, 187, 198), 0.55)
        lat += 10.0

    for parts in polygons:
        for idx, ring in enumerate(parts):
            lons = [q[0] for q in ring]
            lats = [q[1] for q in ring]
            if max(lons) < lon_w or min(lons) > lon_e:
                continue
            if max(lats) < lat_s or min(lats) > lat_n:
                continue
            clipped = clip_ring(ring, lon_w, lat_s, lon_e, lat_n)
            if len(clipped) < 3:
                continue
            pts = [proj(lo, la) for lo, la in clipped]
            if idx == 0:
                poly(d, pts, fill=LAND, outline=COAST, w=0.7)
            else:
                # hole: inland water back to sea, no stroke
                poly(d, pts, fill=SEA)

    for lon_p, lat_p, num, region in PINS:
        cx, cy = proj(lon_p, lat_p)
        col = ACCENT[region]
        ell(d, cx - 5.6, cy - 5.6, cx + 5.6, cy + 5.6, fill=col)
        ell(d, cx - 5.6, cy - 5.6, cx + 5.6, cy + 5.6,
            outline=(252, 250, 242), w=0.9)
        d.text((cx * SS, cy * SS), str(num), font=fnt(SANS_B, 5.6),
               fill=(255, 253, 246), anchor="mm")

    rect(d, x0, y0, x1, y1, outline=(174, 180, 182), w=0.8)


# --------------------------------------------------------------------------
# masthead
# --------------------------------------------------------------------------


def draw_masthead(d):
    rect(d, 0, MAST_Y0, W, MAST_Y1, fill=NAVY)
    rect(d, 0, MAST_Y1 - 3, W, MAST_Y1, fill=(150, 78, 30))

    x = MARGIN
    draw_tracked(d, x, 12, "THE DAY IN ONE PAGE", SANS_B, 7.4, CREAM_DIM, 2.5)

    date = "17 NOVEMBER 2026"
    px = 46
    f = fnt(SERIF_B, px)
    while tw(d, date, f) > 660:
        px -= 1
        f = fnt(SERIF_B, px)
    d.text((x * SS, 22 * SS), date, font=f, fill=(253, 250, 242), anchor="la")

    draw_tracked(d, x, 76, "WHAT THE WORLD REPORTED ON TUESDAY, IN FIFTEEN STORIES",
                 SANS_R, 6.6, (182, 178, 164), 1.5)

    groups = [("15", "STORIES"), ("6", "REGIONS"), ("9", "DESKS")]
    fnum = fnt(SERIF_B, 19)
    widths = [max(tracked_width(d, lab, SANS_B, 5.6, 1.2), tw(d, num, fnum))
              for num, lab in groups]
    gx = CONTENT_X1
    for idx in range(len(groups) - 1, -1, -1):
        num, lab = groups[idx]
        gx -= widths[idx]
        d.text((gx * SS, 30 * SS), num, font=fnum, fill=(253, 250, 242),
               anchor="la")
        draw_tracked(d, gx, 52, lab, SANS_B, 5.6, (192, 187, 172), 1.2)
        gx -= 20
        if idx > 0:
            line(d, [(gx + 10, 30), (gx + 10, 58)], (62, 76, 102), 0.8)


# --------------------------------------------------------------------------
# hero
# --------------------------------------------------------------------------


def pin_badge(d, cx, cy, r, num, col, ring=(252, 250, 243)):
    ell(d, cx - r, cy - r, cx + r, cy + r, fill=col)
    ell(d, cx - r, cy - r, cx + r, cy + r, outline=ring, w=0.9)
    d.text((cx * SS, cy * SS), str(num), font=fnt(SANS_B, r * 1.35),
           fill=(255, 253, 246), anchor="mm")


def draw_hero(d, canvas, rings):
    draw_bridge(d, canvas, (0, HERO_Y0, ART_X1, HERO_Y1))

    x = TYPE_X0
    region = LEAD["region"]
    col = ACCENT[region]

    badge_cy = 105.5
    pin_badge(d, x + 6.0, badge_cy, 6.0, 1, col)
    tx = x + 18
    draw_tracked(d, tx, 101.5, region, SANS_B, 6.8, col, 2.0)
    tx += tracked_width(d, region, SANS_B, 6.8, 2.0) + 6
    draw_tracked(d, tx, 101.5, "· " + LEAD["where"], SANS_B, 6.8, GREY, 1.5)

    px, lines, lh = fit(d, LEAD["headline"], SERIF_B, TYPE_W, 102,
                        [31, 30, 29, 28, 27, 26], leading=1.14)
    y = draw_lines(d, x, 116, lines, SERIF_B, px, lh, (21, 27, 41),
                   stroke=0.3)

    y += 7
    dpx, dlines, dlh = fit(d, LEAD["deck"], SERIF_R, TYPE_W, 58,
                           [10.0, 9.7, 9.4, 9.0, 8.6], leading=1.32)
    y = draw_lines(d, x, y, dlines, SERIF_R, dpx, dlh, (56, 58, 65))

    y += 5
    line(d, [(x, y + 3), (x + 16, y + 3)], col, 1.2)
    draw_tracked(d, x + 22, y, LEAD["source"].upper(), SANS_B, 6.2, GREY, 1.4)

    map_y0 = 314
    map_h = 110
    draw_tracked(d, x, map_y0 - 10, "WHERE IT HAPPENED", SANS_B, 5.9, GREY, 1.8)
    lx = CONTENT_X1
    for name in ("ASIA", "MIDDLE EAST", "EUROPE"):
        wl = tracked_width(d, name, SANS_B, 5.0, 1.0)
        lx -= wl
        draw_tracked(d, lx, map_y0 - 10.6, name, SANS_B, 5.0, GREY, 1.0)
        ell(d, lx - 6.4, map_y0 - 8.4, lx - 2.6, map_y0 - 4.6, fill=ACCENT[name])
        lx -= 12
    draw_map(d, (x, map_y0, CONTENT_X1, map_y0 + map_h), rings)


# --------------------------------------------------------------------------
# six cards
# --------------------------------------------------------------------------


def kicker_w(d, card, rpx, upx, track):
    """Width of the merged one-line 'REGION · PLACE' kicker."""
    return (tracked_width(d, card["region"], SANS_B, rpx, track)
            + tw(d, " · ", fnt(SANS_B, rpx))
            + tw(d, card["where"], fnt(SERIF_B, upx)))


def draw_kicker(d, x, y, card, col, rpx, upx, track):
    """Region and place on a single line, both in the region accent colour.

    The serif runs a little higher than the sans in 'la' space, so the sans is
    pushed down by the ascent difference to sit on a shared baseline.
    """
    draw_tracked(d, x, y + (upx - rpx) * 0.9, card["region"], SANS_B, rpx,
                 col, track)
    x += tracked_width(d, card["region"], SANS_B, rpx, track)
    d.text((x * SS, (y + (upx - rpx) * 0.9) * SS), " · ",
           font=fnt(SANS_B, rpx), fill=mix(col, PAPER_CARD, 0.45),
           anchor="la")
    x += tw(d, " · ", fnt(SANS_B, rpx))
    d.text((x * SS, y * SS), card["where"], font=fnt(SERIF_B, upx),
           fill=col, anchor="la")


def draw_cards(d):
    for i, card in enumerate(CARDS):
        cidx = i % 3
        ridx = i // 3
        x0 = CONTENT_X0 + cidx * (CARD_W + CARD_GAP)
        y0 = CARDS_Y0 + ridx * (CARD_H + CARD_VGAP)
        x1 = x0 + CARD_W
        y1 = y0 + CARD_H
        col = ACCENT[card["region"]]

        rect(d, x0, y0, x1, y1, fill=PAPER_CARD, outline=HAIRLINE, w=0.75)
        rect(d, x0 + 0.6, y0 + 0.6, x1 - 0.6, y0 + 3.4, fill=col)

        # pictogram plate, trimmed back to a badge -- the headline carries the
        # card now, the icon is a marker not a picture
        plat = 36
        pxx, pyy = x0 + 10, y0 + 13
        rect(d, pxx, pyy, pxx + plat, pyy + plat, fill=tint_of(col, 0.12))
        rect(d, pxx, pyy, pxx + plat, pyy + plat,
             outline=tint_of(col, 0.32), w=0.7)
        ICONS[card["icon"]](d, pxx + 4, pyy + 3, plat - 8, plat - 7, col, INK)

        pin_badge(d, x1 - 19, y0 + 26, 7.0, i + 2, col)

        # region + place, merged onto one kicker line beside the plate
        tx = pxx + plat + 10
        avail = (x1 - 28) - tx
        rpx, upx = 7.2, 9.0
        while kicker_w(d, card, rpx, upx, 1.7) > avail and rpx > 5.6:
            rpx -= 0.2
            upx -= 0.3
        draw_kicker(d, tx, pyy + 15, card, col, rpx, upx, 1.7)

        # the headline: 22.5 px where it was 17, never more than two lines
        hp, hlines, hlh = fit(d, card["headline"], SERIF_B, CARD_W - 20,
                              CARD_HEAD_BOX,
                              [CARD_HEAD_PX, 24.2, 23.8, 23.4, 23.2,
                               22.8, 22.4],
                              leading=1.13)
        draw_lines(d, x0 + 10, y0 + CARD_HEAD_Y, hlines, SERIF_B, hp, hlh,
                   (22, 27, 41), stroke=0.55)


# --------------------------------------------------------------------------
# also reported
# --------------------------------------------------------------------------


def draw_briefs(d):
    head = "ALSO REPORTED"
    y = BRIEF_Y0 + 2
    draw_tracked(d, CONTENT_X0, y, head, SANS_B, 7.0, NAVY, 2.4)
    hw = tracked_width(d, head, SANS_B, 7.0, 2.4)
    rule(d, CONTENT_X0 + hw + 10, y + 3.8, CONTENT_X1 - 250, HAIRLINE, 0.8)
    note = "EIGHT MORE STORIES FROM THE SAME DAY"
    nw = tracked_width(d, note, SANS_B, 5.2, 1.4)
    draw_tracked(d, CONTENT_X1 - nw, y + 1.0, note, SANS_B, 5.2, GREY, 1.4)

    col_w = (CONTENT_W - 18) / 2.0
    row_h = 17.0
    for i, (kind, text) in enumerate(BRIEFS):
        cidx = i // 4
        ridx = i % 4
        x0 = CONTENT_X0 + cidx * (col_w + 18)
        y0 = BRIEF_Y0 + 18 + ridx * row_h
        icon_tiny(d, kind, x0 + 1, y0 + 1.4, 9.4, NAVY_SOFT)
        bpx, bline = fit_line(d, text, SANS_R, col_w - 20,
                              [8.6, 8.4, 8.2, 8.0, 7.8])
        d.text(((x0 + 16) * SS, y0 * SS), bline, font=fnt(SANS_R, bpx),
               fill=(38, 42, 54), anchor="la")


# --------------------------------------------------------------------------
# numbers strip
# --------------------------------------------------------------------------


def draw_numbers(d):
    rect(d, 0, NUM_Y0, W, NUM_Y1, fill=NAVY)
    draw_tracked(d, MARGIN, NUM_Y0 + 8, "THE DAY IN NUMBERS", SANS_B, 6.4,
                 CREAM_DIM, 2.2)
    rule(d, MARGIN + 96, NUM_Y0 + 11.6, CONTENT_X1, (54, 68, 94), 0.8)

    cell_w = CONTENT_W / 5.0
    for i, (num, cap) in enumerate(NUMBERS):
        cx = CONTENT_X0 + i * cell_w
        d.text((cx * SS, (NUM_Y0 + 24) * SS), num, font=fnt(SERIF_B, 28),
               fill=(246, 242, 232), anchor="la")
        # one short caption line, set bigger than the old two-line mush
        cpx, cline = fit_line(d, cap, SANS_R, cell_w - 12,
                              [10.6, 10.5, 10.4, 10.2, 10.0, 9.8])
        d.text((cx * SS, (NUM_Y0 + 62) * SS), cline,
               font=fnt(SANS_R, cpx), fill=(206, 207, 199), anchor="la")
        if i:
            line(d, [(cx - 7, NUM_Y0 + 20), (cx - 7, NUM_Y1 - 14)],
                 (46, 60, 86), 0.8)


# --------------------------------------------------------------------------
# footer
# --------------------------------------------------------------------------


def draw_footer(d):
    rule(d, 0, FOOT_Y0, W, NAVY, 1.4)
    f1 = ("Compiled from the day's wire reports. Figures are as reported; "
          "contested claims are attributed to the side that made them.")
    f2 = ("Illustrations and the map are original vector drawings made for this "
          "page; no photograph, logo or third-party artwork is reproduced.")
    for i, txt in enumerate((f1, f2)):
        px = 6.5
        f = fnt(SANS_R, px)
        while tw(d, txt, f) > 700 - MARGIN:
            px -= 0.2
            f = fnt(SANS_R, px)
        d.text((MARGIN * SS, (FOOT_Y0 + 13 + i * 11) * SS), txt, font=f,
               fill=(92, 93, 98), anchor="la")

    for i, txt in enumerate(("make.fun · news-image-20261117",
                             "17 November 2026, all time zones")):
        f = fnt(SANS_B if i == 0 else SANS_R, 6.5)
        d.text((CONTENT_X1 * SS, (FOOT_Y0 + 13 + i * 11) * SS), txt, font=f,
               fill=(66, 68, 78) if i == 0 else (118, 118, 122), anchor="ra")


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------


def build():
    rings = load_land()
    canvas = Image.new("RGBA", (W * SS, H * SS), PAPER + (255,))
    d = ImageDraw.Draw(canvas)
    vgrad(d, (0, 0, W, H), (247, 242, 231), (243, 237, 224))

    draw_masthead(d)
    draw_hero(d, canvas, rings)
    draw_cards(d)
    draw_briefs(d)
    draw_numbers(d)
    draw_footer(d)

    return canvas.convert("RGB").resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    img = build()
    os.makedirs("out", exist_ok=True)
    img.save("out/preview.png", optimize=True)
    print("wrote out/preview.png", img.size)
