"""TUFT the lynx: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, deliberately simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 tall triangular ears, each topped by a long black tuft (striped with the fur colour); MH2 very wide fluffy
cheek ruffs (the face is wider than it is tall); MH3 short bobbed tail with a black tip; MH4 small dot eyes, a
permanent blush and the tip of the tongue showing; MH5 round soft body.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined, path, poly,
                   pose, ribbon, rotate, smooth, sparkle, sticker, sym, translate)
from lib2d.chibi import figure, open_mouth, w_mouth

CHAR_ID = "tuft"
HEIGHT = 0.60
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Tuft)
FUR = "#f7dcc3"
SHADE = "#e9c3a4"
DARK = "#3a2b2b"      # ear tufts and tail tip
BLUSH = "#f4a6a0"
NOSE = "#d98a8a"
EYES = "#4a3b3b"
# derived
INK = mix(DARK, "#5a3f3a", 0.25)
EAR_IN = mix(BLUSH, FUR, 0.45)
BLUSH_DEEP = mix(BLUSH, NOSE, 0.55)
TONGUE = mix(NOSE, BLUSH, 0.4)
MOUTH_IN = mix(INK, NOSE, 0.35)
BELLY = mix(FUR, "#ffffff", 0.45)

W = 3.4
HEAD_Y = 336.0

DEFAULTS = {"bob": 0.0, "tuft_l": 0.0, "tuft_r": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open",
            "mouth": "w", "blush": 0.0, "tail": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ ears + tufts  (MH1), head frame

EAR = [(12, -30), (28, -66), (42, -96, "c"), (54, -62), (66, -24)]
EAR_INNER = [(26, -32), (35, -60), (42, -80, "c"), (49, -58), (54, -30)]
EAR_TIP = [(20, -80), (64, -80), (64, -120), (20, -120)]
EAR_ROOT = (40.0, -32.0)


def _ear(side, extra, twitch):
    pts = EAR if side > 0 else _mx(EAR)
    shape = path(smooth(pts), fill=FUR)
    tip = (side * 42.0, -96.0)
    # the tuft: a long tapering dark wisp off the ear tip, leaning outward, with one fur-colour stripe
    lean = side * (10.0 + twitch)
    spine = [(tip[0], tip[1] + 6), (tip[0] + lean * 0.2, tip[1] - 8), (tip[0] + lean * 0.55, tip[1] - 18),
             (tip[0] + lean * 1.0, tip[1] - 26)]
    tuft = path(ribbon(spine, [9.0, 7.5, 5.0, 1.8]), fill=DARK)
    marks = [path(smooth(EAR_INNER if side > 0 else _mx(EAR_INNER)), fill=EAR_IN),
             path(poly(EAR_TIP if side > 0 else _mx(EAR_TIP)), fill=DARK)]
    stripe = line(spine[1][0] - side * 0.4, spine[1][1] + 3, spine[2][0], spine[2][1] + 1, stroke=FUR,
                  stroke_width=2.2)
    tf = rotate(side * extra, side * EAR_ROOT[0], EAR_ROOT[1])
    return g(outlined(shape, tuft, ink=INK, width=W), detail(clip(shape, marks), stripe), transform=tf)


# ------------------------------------------------------------------ head  (MH2, MH4)

# MH2: a face far wider than it is tall: fluffy cheek ruffs with three points each side
HEAD_HALF = [(0, -44), (30, -42), (52, -32), (64, -16), (88, -6, "c"), (72, 4), (94, 16, "c"), (74, 22),
             (86, 36, "c"), (60, 38), (34, 44), (0, 46)]


def _head(p):
    skull_d = blob(sym(HEAD_HALF))
    skull = path(skull_d, fill=FUR)
    marks = [path(blob([(-110, 22), (0, 38), (110, 22), (110, 80), (-110, 80)]), fill=SHADE),
             path(blob(sym([(0, 8), (16, 10), (26, 22), (20, 36), (0, 44)])), fill=BELLY)]
    deep = p["blush"]
    blush = [ellipse(s * 50, 16, 13 + 3 * deep, 7.5 + 1.5 * deep, fill=mix(BLUSH, BLUSH_DEEP, deep))
             for s in (-1, 1)]
    if p["eyes"] == "open":     # MH4: small dot eyes with one glint
        eyes = [[ellipse(s * 28, 2, 6.4, 7.6, fill=EYES), circle(s * 28 - 2, -0.8, 2.2, fill="#ffffff")]
                for s in (-1, 1)]
    else:
        eyes = [path("M%g 1 Q%g %g %g 1" % (s * 28 - 8, s * 28, 9 if p["eyes"] == "closed" else -7, s * 28 + 8),
                     fill="none", stroke=EYES, stroke_width=3.6, stroke_linecap="round") for s in (-1, 1)]
    nose = blob([(-6, 13), (0, 12), (6, 13), (3, 18), (0, 20), (-3, 18)])
    if p["mouth"] == "w":
        mouth = g(clip(path("M-6 24 L6 24 L6 34 L-6 34Z"), ellipse(0, 25.5, 4.6, 5.2, fill=TONGUE,
                                                                   stroke=INK, stroke_width=1.6)),   # MH4: tongue tip
                  w_mouth(0, 22, 9.0, 4.4, ink=INK, width=2.4, philtrum=2.5))
    else:
        mouth = g(open_mouth(0, 23, 6.0 if p["mouth"] == "open_s" else 7.5,
                             5.0 if p["mouth"] == "open_s" else 8.0, ink=INK, inner=MOUTH_IN, tongue=TONGUE),
                  w_mouth(0, 22, 9.0, 3.5, ink=INK, width=2.4, philtrum=2.5))
    whisk = [line(s * 62, 20 + 6 * k, s * 78, 18 + 9 * k, stroke=INK, stroke_width=1.4) for s in (-1, 1)
             for k in (0, 1)]
    face = detail(clip(skull, marks), blush, eyes, mouth, whisk,
                  path(nose, fill=NOSE, stroke=INK, stroke_width=1.8, stroke_linejoin="round"))
    tf = "%s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 46))
    return g(_ear(-1, p["ear_l"], p["tuft_l"]), _ear(1, p["ear_r"], p["tuft_r"]),
             outlined(skull, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ body  (MH5, MH3)

BODY_HALF = [(0, 362), (32, 366), (52, 386), (60, 414), (58, 444), (44, 462), (22, 467), (0, 468)]
FOOT = [(6, 465), (10, 452), (24, 447), (38, 452), (44, 463), (37, 471), (22, 472.5), (10, 471)]


def _body(p):
    bob = p["bob"]
    pts = [(x, y + bob * max(0.0, (440.0 - y) / 70.0)) for x, y in BODY_HALF]
    body = path(blob(sym(pts)), fill=FUR)
    feet = [path(blob(FOOT), fill=FUR), path(blob(_mx(FOOT)), fill=FUR)]
    marks = [path(blob([(38, 364), (70, 380), (70, 470), (40, 470), (50, 420)]), fill=SHADE),
             path(blob(sym([(0, 386), (24, 392), (30, 420), (22, 448), (0, 456)])), fill=BELLY),
             path(blob([(-70, 356), (0, 362), (70, 356), (70, 382), (0, 390), (-70, 382)]), fill=SHADE)]
    toes = [line(s * x, 465, s * x, 471, stroke=INK, stroke_width=1.8) for s in (-1, 1) for x in (19.0, 29.0)]
    arms = []
    for s in (-1, 1):
        sh, hand = (s * 44, 392 + bob), (s * 50, 426 + bob * 0.4)
        arms.append(outlined(path(capsule(sh, hand, 11.0, 10.5), fill=FUR), ink=INK, width=W))
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks), toes), arms)


def _tail(p):
    """MH3: a short bobbed tail peeking out at screen right, black tip."""
    a = 8.0 * p["tail"]
    shape = path(blob([(40, 436), (66, 418), (90, 414), (100, 428), (92, 446), (60, 454)]), fill=FUR)
    tip = path(blob([(80, 404), (110, 410), (110, 456), (82, 452), (88, 430)]), fill=DARK)
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, tip)), transform=rotate(-a, 48, 444))


SPARKLES = {1: [(-104, 270, 10, BLUSH), (104, 300, 8, SHADE)],
            2: [(-110, 300, 8, SHADE), (100, 262, 11, BLUSH)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_tail(p), _body(p), _head(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    "idle": anim([pose(REST), pose(REST, bob=1.4, squash=0.01, tail=1.0, tuft_l=-4, tuft_r=-4),
                  pose(REST, bob=0.7, tail=0.4)], fps=4, loop=True),
    "talk": anim([pose(REST, mouth="open_s", tilt=2.0), pose(REST, mouth="w", tilt=3.0)], fps=6, loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
    # shy delight: the ear tufts twitch and the blush deepens
    "special": anim([pose(REST, tuft_l=-12, tuft_r=8, blush=0.5, tilt=3.0),
                     pose(REST, tuft_l=8, tuft_r=-12, ear_l=-3, ear_r=-3, blush=1.0, eyes="happy", tilt=4.0,
                          sparkles=1),
                     pose(REST, tuft_l=-6, tuft_r=6, blush=1.0, eyes="happy", tilt=4.0, sparkles=2)],
                    fps=6, loop=False),
}
