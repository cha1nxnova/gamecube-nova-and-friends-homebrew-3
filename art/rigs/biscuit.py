"""BISCUIT the dog: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, deliberately simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 floppy ears, MH2 white blaze and chest, MH3 tongue out, MH4 tail mid-wag, MH5 pink collar.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres him.
"""
from __future__ import annotations

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined, path, pose,
                   ribbon, bezier, rotate, scale, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure

CHAR_ID = "biscuit"
HEIGHT = 0.55
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Biscuit)
CARAMEL = "#d79a55"
WHITE = "#fbf5ea"
SHADE = "#b97f40"
NOSE = "#3a2a22"
TONGUE = "#f29abf"
COLLAR = "#e2358d"
# derived
INK = mix(SHADE, "#1f1714", 0.80)
WHITE_SH = mix(WHITE, CARAMEL, 0.28)
EAR = mix(SHADE, CARAMEL, 0.25)
EAR_SH = mix(SHADE, INK, 0.25)
IRIS = mix(CARAMEL, NOSE, 0.55)
IRIS_LO = mix(NOSE, INK, 0.3)
LID = SHADE
COLLAR_SH = mix(COLLAR, INK, 0.28)
TAG = mix(COLLAR, "#ffffff", 0.62)
MOUTH_IN = mix(INK, TONGUE, 0.3)
TONGUE_SH = mix(TONGUE, INK, 0.28)

W = 3.4
HEAD_Y = 300.0

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open", "lid": 0.12, "mouth": "pant",
            "tail": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ head (head frame)

HEAD_HALF = [(0, -60), (36, -57), (60, -40), (70, -14), (70, 14), (60, 38), (38, 52), (0, 57)]
# MH1: a floppy ear hanging from the top of the head down past the cheek (screen-right one)
EAR_PTS = [(40, -54), (62, -50), (80, -30), (88, 2), (86, 30), (76, 44), (64, 38), (58, 10), (50, -24),
           (34, -44)]
EAR_ROOT = (50.0, -50.0)
# MH2: the white blaze runs up between the eyes from the muzzle
BLAZE = [(0, -56), (7, -54), (9, -24), (12, -2), (34, 8), (44, 26), (38, 46), (0, 58), (-38, 46), (-44, 26),
         (-34, 8), (-12, -2), (-9, -24), (-7, -54)]


def _ear(side, extra):
    pts = EAR_PTS if side > 0 else _mx(EAR_PTS)
    shape = path(blob(pts), fill=EAR)
    shade = path(blob([(side * x, y) for x, y in [(60, 6), (88, 0), (90, 50), (60, 50)]]), fill=EAR_SH)
    tf = rotate(side * extra, side * EAR_ROOT[0], EAR_ROOT[1])
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, shade)), transform=tf)


def _mouth(p):
    m = p["mouth"]
    depth = {"pant": 8.0, "open_s": 11.0, "open_l": 15.0}.get(m, 8.0)
    top = 30.0
    cav = "M%g %g Q%g %g %g %g Q%g %g %g %g Q%g %g %g %g Q%g %g %g %gZ" % (
        -16, top - 2, -8, top + 3, 0, top, 8, top + 3, 16, top - 2,
        14, top + depth + 3, 0, top + depth + 3, -14, top + depth + 3, -16, top - 2)
    # MH3: the tongue always lolls out over the lower lip
    tl = 18.0 + (depth - 8.0) * 0.5
    tongue = blob([(-8, top + depth - 2), (-9.5, top + depth + 8), (-6, top + depth + tl - 4),
                   (0, top + depth + tl), (6, top + depth + tl - 4), (9.5, top + depth + 8),
                   (8, top + depth - 2)])
    return g(path(cav, fill=MOUTH_IN, stroke=INK, stroke_width=2.6, stroke_linejoin="round"),
             path(tongue, fill=TONGUE, stroke=INK, stroke_width=2.4, stroke_linejoin="round"),
             line(0, top + depth + 2, 0, top + depth + tl - 6, stroke=TONGUE_SH, stroke_width=1.8),
             path("M-17 %g Q-8 %g 0 %g Q8 %g 17 %g" % (top - 3, top + 3, top - 1, top + 3, top - 3), fill="none",
                  stroke=INK, stroke_width=2.6, stroke_linecap="round"),
             line(0, 20, 0, top - 1, stroke=INK, stroke_width=2.4))


def _head(p):
    skull_d = blob(sym(HEAD_HALF))
    skull = path(skull_d, fill=CARAMEL)
    marks = [
        path(blob([(-90, 40), (0, 54), (90, 40), (90, 90), (-90, 90)]), fill=SHADE),
        path(blob(BLAZE), fill=WHITE),                                              # MH2
        clip(path(blob(BLAZE)), path(blob([(-90, 44), (0, 56), (90, 44), (90, 90), (-90, 90)]),
                                     fill=WHITE_SH)),
    ]
    eyes = [eye(s * 30, -6, 12.5, 13.5, ink=INK, lid_fill=LID, iris=IRIS, iris_lo=IRIS_LO, pupil=INK,
                lid=p["lid"], state=p["eyes"]) for s in (-1, 1)]
    brows = [ellipse(s * 28, -30, 6.5, 4.2, rot=-s * 12, fill=SHADE) for s in (-1, 1)]
    nose = blob([(-11, 10), (0, 8), (11, 10), (8, 17), (0, 21), (-8, 17)])
    face = detail(clip(skull, marks), brows, eyes, _mouth(p),
                  path(nose, fill=NOSE, stroke=INK, stroke_width=2.2, stroke_linejoin="round"),
                  ellipse(-3.5, 11.5, 3.2, 1.6, fill="#ffffff"))
    tf = "%s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 56))
    return g(outlined(skull, ink=INK, width=W), face, _ear(-1, p["ear_l"]), _ear(1, p["ear_r"]), transform=tf)


# ------------------------------------------------------------------ body, collar, tail

BODY_HALF = [(0, 344), (30, 350), (47, 372), (54, 404), (55, 436), (48, 456), (28, 463), (0, 464)]
CHEST_HALF = [(0, 352), (20, 354), (28, 380), (26, 414), (16, 440), (0, 448)]
FOOT = [(6, 464), (10, 451), (24, 446), (39, 451), (45, 463), (38, 471), (22, 472.5), (10, 471)]


def _bp(pts, bob):
    return [(x, y + bob * max(0.0, (430.0 - y) / 70.0)) for x, y in pts]


def _body(p):
    bob = p["bob"]
    d = blob(sym(_bp(BODY_HALF, bob)))
    body = path(d, fill=CARAMEL)
    feet = [path(blob(FOOT), fill=WHITE), path(blob(_mx(FOOT)), fill=WHITE)]
    chest = blob(sym(_bp(CHEST_HALF, bob)))
    marks = [path(blob([(36, 350), (70, 360), (70, 470), (40, 470), (48, 430), (46, 390)]), fill=SHADE),
             path(chest, fill=WHITE),                                                # MH2: white chest
             clip(path(chest), path(blob([(10, 350), (40, 350), (40, 450), (14, 450), (20, 400)]),
                                    fill=WHITE_SH))]
    toes = [line(s * x, 465, s * x, 471, stroke=INK, stroke_width=2.0) for s in (-1, 1) for x in (20.0, 31.0)]
    arms = []
    for s in (-1, 1):
        sh, hand = (s * 44, 382 + bob), (s * 52, 420 + bob * 0.4)
        arm = path(capsule(sh, hand, 11.0, 10.5), fill=CARAMEL)
        paw = circle(hand[0], hand[1] + 3, 10.8, fill=WHITE)
        arms.append(g(outlined(arm, paw, ink=INK, width=W),
                      detail(line(hand[0] - 3.4, hand[1] + 9, hand[0] - 3.4, hand[1] + 5, stroke=INK,
                                  stroke_width=1.8),
                             line(hand[0] + 3.4, hand[1] + 9, hand[0] + 3.4, hand[1] + 5, stroke=INK,
                                  stroke_width=1.8))))
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks), toes), arms)


def _collar(p):
    """MH5: the pink collar, with a little tag."""
    y = 364.0 + p["bob"]
    band_d = "M-46 %g Q0 %g 46 %g L44 %g Q0 %g -44 %gZ" % (y - 9, y + 3, y - 9, y + 2, y + 14, y + 2)
    shape = path(band_d, fill=COLLAR)
    tag = circle(0, y + 17, 6.2, fill=TAG)
    return g(outlined(shape, tag, ink=INK, width=3.0),
             detail(clip(shape, path(band_d, fill=COLLAR_SH, transform=translate(0, 5))),
                    circle(0, y + 17, 2.0, fill=COLLAR)))


def _tail(p):
    """MH4: up and out to screen right, caught mid-wag (``tail`` swings it, -1 .. 1)."""
    ang = 6.0 + 13.0 * p["tail"]
    spine = bezier((36, 436), (64, 436), (86, 420), (92, 384), n=24)
    d = ribbon(spine, [19.0, 17.0, 14.0, 11.0])
    shape = path(d, fill=CARAMEL)
    tip = path(blob([(70, 400), (110, 392), (110, 360), (76, 368)]), fill=WHITE)
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, tip)),
             transform=rotate(ang, 40, 436))


SPARKLES = {1: [(-96, 280, 11, COLLAR), (98, 300, 8, CARAMEL)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_tail(p), _body(p), _collar(p), _head(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # panting breath, the tail wagging side to side, ears flopping a little
    "idle": anim([pose(REST, tail=-1.0, ear_l=2, ear_r=-2), pose(REST, tail=0.0, bob=1.2, squash=0.01),
                  pose(REST, tail=1.0, ear_l=-2, ear_r=2), pose(REST, tail=0.0, bob=1.2, squash=0.01)],
                 fps=6, loop=True),
    "talk": anim([pose(REST, mouth="open_l", bob=1.0, tail=0.6, ear_l=-3, ear_r=-3),
                  pose(REST, mouth="open_s", tail=-0.6)], fps=8, loop=True),
    "blink": anim([pose(REST, lid=0.7), pose(REST, eyes="closed")], fps=10, loop=False),
}
