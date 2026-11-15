"""SPROUT the garden kobold: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 a small lizard-like kobold with a blunt snout; MH2 two bark-brown horn nubs; MH3 one two-leaf seedling
growing from the top of the head; MH4 cream belly plates; MH5 a long tail ending in a pink flower bud;
MH6 carries a little watering can.  Height 0.50 of Nova (seedling included).

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

import math

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined, path, poly,
                   pose, ribbon, rotate, smooth, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure, open_mouth
from lib2d.geom import bezier

CHAR_ID = "sprout"
HEIGHT = 0.50
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Sprout)
SCALES = "#7fa065"
SHADE = "#668750"
BELLY = "#e8dcae"
BARK = "#6b4a2f"      # bark patches and horn nubs
LEAF = "#9bd067"
EYES = "#2f2a22"
BUD = "#f29abf"
CAN = "#8fb7c9"
# derived
INK = mix(EYES, SHADE, 0.3)
BELLY_SH = mix(BELLY, SHADE, 0.3)
LEAF_SH = mix(LEAF, SHADE, 0.45)
BARK_HI = mix(BARK, BELLY, 0.3)
BUD_SH = mix(BUD, "#c2577f", 0.5)
CAN_SH = mix(CAN, "#4f7a8e", 0.45)
IRIS = mix(EYES, SCALES, 0.35)
MOUTH_IN = mix(INK, "#c25a5a", 0.4)
TONGUE = "#ee7fa6"
WATER = "#bfe6f5"

W = 3.4
HEAD_Y = 344.0

DEFAULTS = {"bob": 0.0, "leaf": 0.0, "eyes": "open", "lid": 0.08, "look": (0.0, 0.0), "mouth": "smile",
            "tail": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "pour": 0.0, "drops": 0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ head  (MH1, MH2, MH3)

HEAD_HALF = [(0, -44), (28, -42), (48, -28), (56, -6), (56, 14), (48, 32), (28, 42), (0, 45)]
HORN = [(-8, 4), (-8, -5), (-3, -11), (3, -11), (8, -5), (8, 4)]


def _seedling(p):
    """MH3: a short stem with two round-tipped leaves, swaying with ``leaf``."""
    a = p["leaf"]
    stem = path("M0 -40 Q%g -56 %g -66" % (-2 + a, a * 2.5), fill="none", stroke=LEAF_SH, stroke_width=5.0,
                stroke_linecap="round")
    top = (a * 2.5, -66.0)
    leaves = []
    for s in (-1, 1):
        tip = (top[0] + s * 26, top[1] - 12 + (3 * a * s))
        d = smooth([top, (top[0] + s * 10, top[1] - 16), (tip[0], tip[1], "c"), (top[0] + s * 16, top[1] + 4)])
        leaf = path(d, fill=LEAF)
        vein = path("M%g %g Q%g %g %g %g" % (top[0], top[1], top[0] + s * 12, top[1] - 6, tip[0] - s * 6,
                                            tip[1] + 2), fill="none", stroke=LEAF_SH, stroke_width=1.8)
        leaves.append(g(outlined(leaf, ink=INK, width=W),
                        detail(clip(leaf, path(d, fill=LEAF_SH, transform=translate(0, 6))), vein)))
    return g(outlined(stem, ink=INK, width=W), leaves)


def _mouth(p):
    m = p["mouth"]
    if m == "smile":   # MH1: a wide, blunt lizard smile
        return path("M-20 20 Q0 32 20 20", fill="none", stroke=INK, stroke_width=2.6, stroke_linecap="round")
    big = m == "open"
    return g(open_mouth(0, 21, 14 if big else 11, 9 if big else 5.5, ink=INK, inner=MOUTH_IN, tongue=TONGUE,
                        width=2.4),
             path("M-22 19 Q-18 22 -14 21", fill="none", stroke=INK, stroke_width=2.4, stroke_linecap="round"),
             path("M22 19 Q18 22 14 21", fill="none", stroke=INK, stroke_width=2.4, stroke_linecap="round"))


def _head(p):
    skull = path(blob(sym(HEAD_HALF)), fill=SCALES)
    snout = blob(sym([(0, 2), (22, 4), (34, 16), (28, 34), (0, 40)]))
    marks = [path(blob([(-90, 26), (0, 42), (90, 26), (90, 90), (-90, 90)]), fill=SHADE),
             path(blob([(36, -40), (72, -20), (72, 40), (44, 30), (50, 0)]), fill=SHADE),
             path(snout, fill=mix(SCALES, BELLY, 0.3)),
             [circle(x, y, r, fill=SHADE) for (x, y, r) in ((-40, -18, 3.2), (-46, -8, 2.4), (40, -18, 3.2),
                                                           (46, -8, 2.4), (0, -30, 3.0))]]
    eyes = [eye(s * 24, -8, 13.0, 14.0, ink=INK, lid_fill=SHADE, iris=IRIS, iris_lo=EYES, pupil=INK,
                lid=p["lid"], state=p["eyes"], look=p["look"]) for s in (-1, 1)]
    nostrils = [ellipse(s * 7, 10, 2.2, 1.6, fill=INK) for s in (-1, 1)]
    blush = [ellipse(s * 40, 16, 7, 4, fill=mix(BUD, SCALES, 0.35)) for s in (-1, 1)]
    face = detail(clip(skull, marks), blush, eyes, nostrils, _mouth(p))
    horns = [g(outlined(path(blob(HORN), fill=BARK), ink=INK, width=W),
               detail(line(-3, -5, 3, -5, stroke=BARK_HI, stroke_width=1.8)),
               transform="%s %s" % (translate(s * 22, -40), rotate(s * 18)))
             for s in (-1, 1)]                                                          # MH2
    tf = "%s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 44))
    return g(_seedling(p), horns, outlined(skull, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ body (MH4), tail (MH5), can (MH6)

BODY_HALF = [(0, 378), (26, 382), (40, 400), (46, 428), (44, 452), (34, 466), (0, 468)]
FOOT = [(6, 465), (9, 455), (22, 451), (36, 455), (42, 465), (34, 471), (20, 472.5), (9, 471)]


def _body(p):
    bob = p["bob"]
    pts = [(x, y + bob * max(0.0, (450.0 - y) / 60.0)) for x, y in BODY_HALF]
    body = path(blob(sym(pts)), fill=SCALES)
    feet = [path(blob(FOOT), fill=SCALES), path(blob(_mx(FOOT)), fill=SCALES)]
    plates_d = blob(sym([(0, 392), (20, 396), (26, 424), (22, 450), (0, 460)]))
    marks = [path(blob([(30, 380), (60, 392), (60, 472), (32, 472), (40, 430)]), fill=SHADE),
             path(plates_d, fill=BELLY),                                                       # MH4
             clip(path(plates_d), path(blob([(12, 396), (40, 404), (40, 470), (10, 470), (20, 430)]),
                                       fill=BELLY_SH),
                  [path("M-30 %g Q0 %g 30 %g" % (y, y + 5, y), fill="none", stroke=BELLY_SH, stroke_width=2.2)
                   for y in (408, 424, 440)]),
             path(blob([(30, 404), (44, 402), (46, 416), (34, 418)]), fill=BARK)]
    claws = [line(s * x, 466, s * x, 471.5, stroke=INK, stroke_width=1.8) for s in (-1, 1) for x in (16.0, 26.0)]
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks), claws))


def _tail(p):
    """MH5: a long tail out to the right along the floor, curling up into a pink flower bud."""
    k = p["tail"]
    spine = (bezier((24, 450), (70, 470), (110, 468), (130, 446 - 3 * k), 12)
             + bezier((130, 446 - 3 * k), (142, 430 - 5 * k), (136, 408 - 6 * k), (124 + 2 * k, 404 - 8 * k), 8)[1:])
    shape = path(ribbon(spine, [26, 20, 15, 11, 8]), fill=SCALES)
    shade = path(ribbon([(x, y + 6) for x, y in spine], [10, 8, 6, 4, 3]), fill=SHADE)
    end = spine[-1]
    prev = spine[-3]
    ang = math.degrees(math.atan2(end[1] - prev[1], end[0] - prev[0])) + 90
    bud_d = smooth([(0, 6), (-11, -6), (-8, -18), (0, -30, "c"), (8, -18), (11, -6)])
    bud = path(bud_d, fill=BUD)
    sepals = path(poly([(-10, 2), (-4, -6), (0, 2), (4, -6), (10, 2), (6, 8), (-6, 8)]), fill=LEAF)
    tf = "%s %s" % (translate(end[0], end[1]), rotate(ang - 180 + 180))
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, shade)),
             g(outlined(bud, sepals, ink=INK, width=W),
               detail(clip(bud, path(bud_d, fill=BUD_SH, transform=translate(4, 2)),
                           path(bud_d, fill=BUD, transform=translate(-1, -1))),
                      line(-2, -4, 0, -20, stroke=mix(BUD, "#ffffff", 0.5), stroke_width=2.0)),
               transform=tf))


def _can(p, hand):
    """MH6: a little watering can held by its top handle; ``pour`` tips it forward (spout to screen left)."""
    body_d = blob([(-17, -14), (17, -14), (19, 6), (15, 18), (-15, 18), (-19, 6)])
    can = path(body_d, fill=CAN)
    spout = path(poly([(-15, -2), (-40, -24), (-44, -21), (-21, 10)]), fill=CAN)
    rose = path(blob([(-48, -28), (-38, -30), (-36, -20), (-46, -18)]), fill=CAN_SH)
    handle = path("M-10 -14 Q0 -32 10 -14", fill="none", stroke=CAN, stroke_width=6.0, stroke_linecap="round")
    marks = [path(blob([(4, -14), (24, -14), (24, 22), (2, 22)]), fill=CAN_SH),
             path(blob([(-8, -2), (4, -2), (4, 6), (-8, 6)]), fill=LEAF)]       # a little leaf label
    drops = []
    for i in range(p["drops"]):
        x, y = -56 - 3 * i, -22 + 11 * i
        drops.append(outlined(path(smooth([(x, y - 7, "c"), (x + 4.5, y + 1), (x, y + 5), (x - 4.5, y + 1)]),
                                   fill=WATER), ink=INK, width=1.8))
    tf = "%s %s" % (translate(hand[0] - 2, hand[1] + 26), rotate(-34 * p["pour"], 0, -24))
    return g(outlined(handle, spout, rose, can, ink=INK, width=W), detail(clip(can, marks)), drops,
             transform=tf)


def _arms(p):
    bob = p["bob"]
    out = []
    # screen-left arm holds the can down at her side; screen-right arm rests on the belly
    sh_l, hand_l = (-36, 402 + bob), (-50, 420 + bob * 0.4)
    sh_r, hand_r = (36, 402 + bob), (38, 432 + bob * 0.4)
    out.append(_can(p, hand_l))
    for sh, hand in ((sh_l, hand_l), (sh_r, hand_r)):
        out.append(outlined(path(capsule(sh, hand, 9.0, 8.5), fill=SCALES), circle(hand[0], hand[1] + 3, 9.0,
                                                                                  fill=SCALES),
                            ink=INK, width=W))
    return out


SPARKLES = {1: [(-80, 300, 10, LEAF), (84, 330, 8, BUD)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_tail(p), _body(p), _arms(p), _head(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # breathing; the seedling sways and the tail bud bobs
    "idle": anim([pose(REST), pose(REST, bob=1.4, leaf=2.0, tail=1.0, squash=0.01), pose(REST, bob=0.7, leaf=-1.5,
                                                                                         tail=0.5)],
                 fps=4, loop=True),
    "talk": anim([pose(REST, mouth="open", tilt=2.0, leaf=1.0), pose(REST, mouth="open_s", tilt=1.0)], fps=8,
                 loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
    # special: a bit of watering
    "special": anim([pose(REST, pour=0.6, eyes="happy", leaf=1.0),
                     pose(REST, pour=1.0, drops=2, eyes="happy", leaf=-1.0, sparkles=1),
                     pose(REST, pour=1.0, drops=3, eyes="happy", leaf=2.0)], fps=6, loop=False),
}
