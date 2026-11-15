"""MOCHI the cat: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, deliberately simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 small round cat, MH2 half-closed eyes, MH3 one grey ear (screen left), MH4 one grey eye patch (screen
right), MH5 tail curled round her feet.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres her.
"""
from __future__ import annotations

from lib2d import (anim, band, bezier, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined,
                   path, pose, ribbon, rotate, scale, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure, open_mouth, w_mouth

CHAR_ID = "mochi"
HEIGHT = 0.55
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Mochi)
CREAM = "#f3ead9"
GREY = "#a7a3ad"
SHADE = "#ddd2bf"
NOSE = "#e8a5b5"
EYES = "#5d6b4f"
# derived (one soft shade per colour area)
INK = mix(GREY, "#1d1a22", 0.80)
GREY_SH = mix(GREY, INK, 0.22)
EYES_LO = mix(EYES, INK, 0.35)
EAR_IN = mix(NOSE, CREAM, 0.45)
MOUTH_IN = mix(INK, NOSE, 0.35)

W = 3.4               # ink line width, as on the main cast
HEAD_Y = 323.0        # head frame origin (canvas y)

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "lid": 0.46, "eyes": "open", "mouth": "w",
            "tail": 0.0, "tilt": 0.0, "squash": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ head (head frame: origin at its middle)

EAR = [(18, -36), (30, -58), (44, -76), (52, -79, "c"), (57, -70), (61, -48), (66, -18)]
EAR_INNER = [(30, -38), (39, -55), (49, -68, "c"), (53, -50), (56, -30)]
EAR_ROOT = (42.0, -40.0)


def _ear(side, extra, grey):
    fill = GREY if grey else CREAM
    pts = EAR if side > 0 else _mx(EAR)
    inner = EAR_INNER if side > 0 else _mx(EAR_INNER)
    shape = path(blob(pts), fill=fill)
    tf = rotate(side * extra, side * EAR_ROOT[0], EAR_ROOT[1])
    return g(outlined(shape, ink=INK, width=W),
             detail(path(blob(inner), fill=mix(EAR_IN, GREY, 0.35) if grey else EAR_IN)), transform=tf)


HEAD_HALF = [(0, -50), (34, -47), (56, -35), (68, -14), (71, 8), (66, 30), (48, 46), (22, 53), (0, 54)]
PATCH = [(8, -18), (20, -32), (40, -34), (54, -22), (52, 2), (44, 20), (24, 22), (10, 12)]


def _head(p):
    skull = path(blob(sym(HEAD_HALF)), fill=CREAM)
    skull_d = blob(sym(HEAD_HALF))
    marks = [
        # one soft shade along the jaw, a little more on the screen-right side
        path(blob([(-80, 34), (-40, 44), (0, 48), (44, 38), (80, 20), (80, 80), (-80, 80)]), fill=SHADE),
        path(blob(PATCH), fill=GREY),                                              # MH4: grey eye patch
        clip(path(blob(PATCH)), path(blob([(-80, 34), (-40, 44), (0, 48), (44, 38), (80, 20), (80, 80),
                                           (-80, 80)]), fill=GREY_SH)),
    ]
    blink = p["eyes"]
    eyes = [eye(s * 28, 4, 13.5, 13.0, ink=INK, lid_fill=(GREY_SH if s > 0 else SHADE), iris=EYES,
                iris_lo=EYES_LO, lid=p["lid"], state=blink, arch=0.2, look=(0.0, 0.1)) for s in (-1, 1)]
    nose = blob([(-6, 18), (0, 17), (6, 18), (3, 23), (0, 25), (-3, 23)])
    if p["mouth"] == "w":
        mouth = w_mouth(0, 27, 9.0, 5.0, ink=INK, width=2.5, philtrum=2.5)
    else:
        mouth = g(open_mouth(0, 28, 6.5 if p["mouth"] == "open_s" else 8.0,
                             5.5 if p["mouth"] == "open_s" else 8.5, ink=INK, inner=MOUTH_IN, tongue=NOSE),
                  w_mouth(0, 27, 9.0, 4.0, ink=INK, width=2.5, philtrum=2.5))
    whiskers = [line(s * 46, 22 + k * 7, s * 62, 18 + k * 9, stroke=INK, stroke_width=1.6) for s in (-1, 1)
                for k in (0, 1)]
    face = detail(clip(skull, marks), eyes, mouth, whiskers,
                  path(nose, fill=NOSE, stroke=INK, stroke_width=2.0, stroke_linejoin="round"))
    tf = "%s %s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 50), scale(1.07))
    return g(_ear(-1, p["ear_l"], True), _ear(1, p["ear_r"], False),            # MH3: one grey ear
             outlined(skull_d and skull, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ body  (MH1)

BODY_HALF = [(0, 364), (30, 368), (48, 386), (56, 412), (57, 438), (49, 457), (28, 465), (0, 466)]
FOOT = [(6, 466), (9, 452), (21, 446), (34, 450), (40, 462), (34, 471), (20, 472.5), (10, 471)]


def _body(p):
    bob = p["bob"]
    pts = [(x, y + bob * max(0.0, (430.0 - y) / 70.0)) for x, y in BODY_HALF]
    d = blob(sym(pts))
    body = path(d, fill=CREAM)
    feet = [path(blob(FOOT), fill=CREAM), path(blob(_mx(FOOT)), fill=CREAM)]
    marks = [
        path(blob([(30, 360), (60, 370), (60, 470), (34, 470), (42, 430), (40, 392)]), fill=SHADE),
        path(blob([(-50, 350), (0, 350), (50, 350), (50, 374), (0, 382), (-50, 374)]), fill=SHADE),
    ]
    arms = []
    for s in (-1, 1):
        sh, hand = (s * 42, 394 + bob), (s * 50, 426 + bob * 0.4)
        arm = path(capsule(sh, hand, 10.5, 10.0), fill=CREAM)
        arms.append(g(outlined(arm, ink=INK, width=W),
                      detail(line(hand[0] - 3, hand[1] + 6, hand[0] - 3, hand[1] + 1, stroke=INK,
                                  stroke_width=1.8),
                             line(hand[0] + 3, hand[1] + 6, hand[0] + 3, hand[1] + 1, stroke=INK,
                                  stroke_width=1.8))))
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks)), arms)


# ------------------------------------------------------------------ tail  (MH5: curled round her feet)

def _tail_spine(t):
    a = bezier((46, 440), (84, 446), (78, 470), (34, 468), n=18)
    b = bezier((30, 468), (-16, 467), (-52, 474), (-62 - 3 * t, 452 - 7 * t), n=18)
    return a + b[1:]


def _tail_w(u):
    return 15.0 - 3.0 * u


def _tail(p):
    spine = _tail_spine(p["tail"])
    d = ribbon(spine, _tail_w)
    shape = path(d, fill=CREAM)
    marks = [path(d, fill=SHADE, transform=translate(0, 4.5)),
             clip(path(d, transform=translate(0, -1.5)), path(d, fill=CREAM)),
             path(band(spine, _tail_w, 0.84, 1.3, zig=3.0, teeth=2, over=10.0), fill=GREY)]
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, marks)))


SPARKLES = {1: [(-84, 290, 11, GREY), (86, 330, 8, NOSE)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX_ + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_body(p), _head(p), _tail(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


CX_ = 256.0

# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # a slow breath; the tail tip lifts and settles, the grey ear flicks once
    "idle": anim([pose(REST), pose(REST, bob=1.2, squash=0.008, tail=0.6),
                  pose(REST, bob=1.8, squash=0.012, tail=1.0, ear_l=-7.0), pose(REST, bob=0.8, tail=0.5)],
                 fps=4, loop=True),
    "talk": anim([pose(REST, mouth="open_s", bob=0.6), pose(REST, mouth="open_l", bob=1.2, lid=0.42)],
                 fps=6, loop=True),
    "blink": anim([pose(REST, lid=0.78), pose(REST, eyes="closed")], fps=10, loop=False),
}
