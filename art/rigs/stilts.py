"""STILTS the maned wolf: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 very long thin legs in black stockings (half his height is leg); MH2 rust-orange coat; MH3 large upright
ears with white insides; MH4 black upper muzzle and white throat patch; MH5 a short dark mane ridge; MH6 bushy
tail with a white tip; MH7 a slight stoop, as if every ceiling is low.  Height 0.95 of Nova.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined, path, poly,
                   pose, ribbon, rotate, smooth, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure, open_mouth
from lib2d.geom import bezier

CHAR_ID = "stilts"
HEIGHT = 0.95         # ear tips at top_y(0.95): just under Nova ("counting ears", says Nova)
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Stilts)
COAT = "#d9762b"
SHADE = "#b85e1e"
BLACK = "#2a2221"     # stockings, upper muzzle, mane
WHITE = "#fbf3e6"     # throat, inner ears, tail tip
EYES = "#5a3d1e"
NOSE = "#1f1a19"
# derived
INK = mix(BLACK, SHADE, 0.12)
BLACK_SH = mix(BLACK, "#000000", 0.35)
BLACK_HI = mix(BLACK, COAT, 0.22)
WHITE_SH = mix(WHITE, SHADE, 0.22)
IRIS = mix(EYES, COAT, 0.35)
MOUTH_IN = mix(INK, "#c25a5a", 0.4)
TONGUE = "#ee7fa6"

W = 3.4
HEAD_Y = 214.0
STOOP = 6.0           # MH7: resting forward-and-down head droop, degrees of tilt

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open", "lid": 0.22, "look": (0.0, 0.0),
            "mouth": "smile", "tail": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "duck": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ ears  (MH3), head (MH4)

EAR = [(10, -30), (14, -80), (30, -126), (44, -136, "c"), (56, -108), (60, -64), (48, -22)]
EAR_INNER = [(21, -34), (25, -78), (36, -112), (44, -120, "c"), (50, -98), (50, -62), (41, -30)]
EAR_ROOT = (30.0, -30.0)


def _ear(side, extra):
    pts = EAR if side > 0 else _mx(EAR)
    shape = path(blob(pts), fill=COAT)
    inner = path(blob(EAR_INNER if side > 0 else _mx(EAR_INNER)), fill=WHITE)
    fluff = [line(side * x, y, side * (x + 5), y - 10, stroke=WHITE_SH, stroke_width=1.8)
             for (x, y) in ((28, -44), (34, -52), (40, -44))]
    rim = path(blob([(side * 30, -150), (side * 70, -150), (side * 70, -80), (side * 52, -96)]), fill=SHADE)
    tf = rotate(side * extra, side * EAR_ROOT[0], EAR_ROOT[1])
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, rim, inner), fluff), transform=tf)


HEAD_HALF = [(0, -46), (28, -44), (46, -30), (54, -8), (52, 8), (42, 22), (26, 34), (14, 46), (0, 50)]
SNOUT_HALF = [(0, -4), (6, -2), (10, 12), (14, 30), (13, 38), (0, 40)]        # MH4: black upper muzzle
CHIN_HALF = [(0, 34), (16, 32), (22, 38), (14, 50), (0, 53)]


def _mouth(p):
    if p["mouth"] == "smile":
        return path("M-9 44 Q0 50 9 44", fill="none", stroke=INK, stroke_width=2.2, stroke_linecap="round")
    big = p["mouth"] == "open"
    return open_mouth(0, 42.5, 8.0 if big else 6.5, 6.5 if big else 4.0, ink=INK, inner=MOUTH_IN, tongue=TONGUE,
                      width=2.2)


def _head(p):
    skull = path(blob(sym(HEAD_HALF)), fill=COAT)
    chin_d = blob(sym(CHIN_HALF))
    marks = [path(blob([(30, -46), (70, -30), (70, 60), (24, 40), (44, 0)]), fill=SHADE),
             path(chin_d, fill=WHITE),
             path(blob(sym(SNOUT_HALF)), fill=BLACK),
             path(blob([(3, -6), (8, 8), (11, 30), (6, 34), (4, 10)]), fill=BLACK_HI)]
    eyes = [eye(s * 25, -10, 12.5, 13.0, ink=INK, lid_fill=SHADE, iris=IRIS, iris_lo=EYES, pupil=INK,
                lid=p["lid"], state=p["eyes"], look=p["look"]) for s in (-1, 1)]
    brows = [path("M%g -33 Q%g -38 %g -36" % (s * 15, s * 25, s * 34), fill="none", stroke=SHADE, stroke_width=3.0,
                  stroke_linecap="round") for s in (-1, 1)]                     # soft, slightly sheepish brows
    nose = blob([(-8, 31), (0, 29), (8, 31), (6, 37), (0, 40), (-6, 37)])
    face = detail(clip(skull, marks), brows, eyes, _mouth(p),
                  path(nose, fill=NOSE, stroke=INK, stroke_width=1.6, stroke_linejoin="round"),
                  ellipse(-2.5, 32, 2.6, 1.3, fill="#8a7d78"))
    tilt = STOOP + p["tilt"]
    tf = "%s %s %s" % (translate(5, HEAD_Y + 4 + p["bob"] + p["duck"] * 10), rotate(tilt, 0, 50),
                       "scale(1.08)")
    return g(_ear(-1, p["ear_l"] + 6 * p["duck"]), _ear(1, p["ear_r"] + 6 * p["duck"]),
             outlined(skull, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ mane (MH5), torso, arms, legs (MH1)

MANE_HALF = [(0, 236), (20, 236), (34, 226, "c"), (36, 240), (50, 236, "c"), (44, 250), (54, 252, "c"),
             (38, 262), (0, 264)]
TORSO_HALF = [(0, 250), (24, 252), (38, 264), (40, 290), (34, 312), (20, 320), (0, 322)]


def _mane(p):
    shape = path(blob(sym(MANE_HALF)), fill=BLACK)
    return g(outlined(shape, ink=INK, width=W), transform=translate(4, p["bob"] + p["duck"] * 6))


def _torso(p):
    bob = p["bob"] + p["duck"] * 4
    pts = [(x, y + bob * max(0.0, (318.0 - y) / 60.0)) for x, y in TORSO_HALF]
    body = path(blob(sym(pts)), fill=COAT)
    throat = blob(sym([(0, 252 + bob), (17, 254 + bob), (21, 272 + bob), (12, 292), (0, 300)]))   # MH4
    marks = [path(blob([(26, 252), (60, 262), (60, 330), (24, 330), (34, 290)]), fill=SHADE),
             path(throat, fill=WHITE),
             clip(path(throat), path(blob([(10, 256), (40, 262), (40, 310), (8, 306)]), fill=WHITE_SH))]
    return g(outlined(body, ink=INK, width=W), detail(clip(body, marks)))


def _arm(side, p):
    bob = p["bob"] + p["duck"] * 4
    sh = (side * 30, 262 + bob)
    el = (side * 39, 302 + bob * 0.6)
    wr = (side * 41, 336)
    upper = path(capsule(sh, el, 9.5, 8.5), fill=COAT)
    fore = path(capsule(el, wr, 8.5, 8.0), fill=BLACK)          # the stockings run up the forelegs too
    paw = ellipse(wr[0], wr[1] + 5, 9.0, 10.0, fill=BLACK)
    sock_edge = path(poly([(el[0] - 10, el[1] + 6), (el[0] - 5, el[1] - 1), (el[0], el[1] + 5),
                           (el[0] + 5, el[1] - 1), (el[0] + 10, el[1] + 6), (el[0] + 10, el[1] + 30),
                           (el[0] - 10, el[1] + 30)]), fill=BLACK)
    hi = line(wr[0] - side * 3, el[1] + 10, wr[0] - side * 3, wr[1] - 4, stroke=BLACK_HI, stroke_width=2.4)
    return g(outlined(upper, fore, paw, ink=INK, width=W), detail(clip(upper, sock_edge), hi))


LEG_TOP = 300.0


def _legs(p):
    """MH1: two long thin legs in black stockings, rust only at the very top; half his height."""
    shapes, marks = [], []
    for s in (-1, 1):
        hip, ank = (s * 17, LEG_TOP), (s * 19, 456)
        leg = path(capsule(hip, ank, 13.0, 8.5), fill=BLACK)
        foot = path(blob([(s * 8, 466), (s * 11, 457), (s * 22, 454), (s * 33, 458), (s * 35, 466), (s * 28, 471),
                          (s * 19, 472.5), (s * 11, 471)]), fill=BLACK)
        shapes += [leg, foot]
        top = path(poly([(s * 2, 290), (s * 34, 290), (s * 34, 330), (s * 29, 324), (s * 23, 333), (s * 17, 325),
                         (s * 11, 333), (s * 5, 325), (s * 2, 330)]), fill=COAT)
        marks += [top, line(s * 14, 342, s * 16, 448, stroke=BLACK_HI, stroke_width=2.6)]
        marks += [path(poly([(s * 24, 290), (s * 34, 290), (s * 34, 326), (s * 24, 330)]), fill=SHADE)]
    toes = [line(s * x, 465, s * x, 471, stroke=BLACK_HI, stroke_width=1.8) for s in (-1, 1) for x in (17.0, 26.0)]
    return g(outlined(*shapes, ink=INK, width=W), detail(clip(shapes, marks), toes))


def _tail(p):
    """MH6: a bushy tail hanging behind his screen-right leg, white tip."""
    k = p["tail"]
    spine = bezier((18, 304), (66 + 4 * k, 318), (78 + 8 * k, 380), (62 + 12 * k, 432), 16)
    widths = [16.0, 30.0, 38.0, 36.0, 26.0]
    d = ribbon(spine, widths)
    shape = path(d, fill=COAT)
    tip = path(blob([(30 + 12 * k, 404), (100 + 12 * k, 400), (100 + 12 * k, 470), (30 + 12 * k, 470)]), fill=WHITE)
    edge = path(poly([(30 + 12 * k, 404), (40 + 12 * k, 398), (50 + 12 * k, 408), (62 + 12 * k, 396),
                      (72 + 12 * k, 408), (84 + 12 * k, 398), (100 + 12 * k, 404), (100 + 12 * k, 470),
                      (30 + 12 * k, 470)]), fill=WHITE)
    shade = path(ribbon([(x + 9, y) for x, y in spine], [6, 12, 14, 12, 6]), fill=SHADE)
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, shade, tip, edge)))


SPARKLES = {1: [(-84, 150, 10, WHITE), (90, 120, 8, COAT)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_tail(p), _legs(p), _mane(p), _torso(p), _arm(-1, p), _arm(1, p), _head(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # a slow, careful breath; one big ear swivels; the tail sways
    "idle": anim([pose(REST), pose(REST, bob=1.6, ear_l=-5, tail=0.6), pose(REST, bob=0.8, tail=1.0)],
                 fps=4, loop=True),
    "talk": anim([pose(REST, mouth="open", tilt=-1.5), pose(REST, mouth="open_s", tilt=1.0)], fps=7, loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
}
