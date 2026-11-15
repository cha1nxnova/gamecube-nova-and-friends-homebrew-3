"""VESPER the bat-eared fox: background cast (cameo).  Same house style as ``nova.py``, deliberately simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 enormous rounded dark-backed ears, each wider than her face, set low and wide; MH2 a dark bandit mask
across the eyes; MH3 small pointed muzzle with one tiny fang; MH4 black stockings; MH5 a high-collared cape
with a red lining and a ruby brooch, always.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres her.
"""
from __future__ import annotations

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, line, mix, outlined, path, poly,
                   pose, rotate, scale, smooth, sparkle, sticker, sym, translate)
from lib2d.chibi import eye, figure

CHAR_ID = "vesper"
HEIGHT = 0.50
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Vesper)
FUR = "#9a8f84"
SHADE = "#7c726a"
MASK = "#2e2826"      # mask, ear backs, lower legs
THROAT = "#e3d6c5"    # throat and inner ear
EYES = "#f0b03c"
CAPE = "#1f1b22"
LINING = "#c2183a"
RUBY = "#e2264d"
GOLD = "#d9a441"
# derived
INK = mix(CAPE, "#000000", 0.25)
THROAT_SH = mix(THROAT, SHADE, 0.35)
EYES_LO = mix(EYES, "#c2183a", 0.35)
CAPE_HI = mix(CAPE, FUR, 0.18)
LINING_SH = mix(LINING, CAPE, 0.35)
RUBY_HI = mix(RUBY, "#ffffff", 0.55)
MOUTH_IN = mix(INK, LINING, 0.35)

W = 3.4
HEAD_Y = 350.0

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open", "lid": 0.22, "mouth": "smile",
            "flourish": 0.0, "squash": 0.0, "hop": 0.0, "tilt": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ ears  (MH1)

EAR = [(-30, 6), (-46, -26), (-48, -64), (-34, -98), (-6, -118), (16, -106), (34, -84), (44, -54),
       (40, -20), (26, 6)]
EAR_IN = [(-20, 0), (-34, -28), (-35, -62), (-24, -88), (-6, -102), (10, -92), (24, -72), (30, -44),
          (27, -16), (16, 0)]
EAR_ROOT = (40.0, -24.0)       # head frame
EAR_SPREAD = 50.0              # set low and wide


def _ear(side, extra):
    shape = path(blob(EAR), fill=MASK)
    inner = blob(EAR_IN)
    marks = [path(inner, fill=THROAT),
             clip(path(inner), path(blob([(-40, 8), (-40, -40), (-14, -70), (0, -40), (6, 8)]), fill=THROAT_SH))]
    tf = "%s %s" % (translate(side * EAR_ROOT[0], EAR_ROOT[1]), rotate(side * (EAR_SPREAD + extra)))
    if side < 0:
        tf += " " + scale(-1, 1)
    return g(outlined(shape, ink=INK, width=W), detail(marks), transform=tf)


# ------------------------------------------------------------------ head  (MH2, MH3)

HEAD_HALF = [(0, -40), (28, -38), (46, -22), (52, 0), (48, 22), (30, 36), (12, 42), (0, 44, "c")]
MASK_HALF = [(0, -6), (12, -12), (30, -15), (46, -10), (58, -6, "c"), (48, 4), (40, 14), (24, 16), (10, 10),
             (0, 12)]
MUZZLE_HALF = [(0, 6), (10, 10), (17, 22), (14, 34), (0, 46, "c")]


def _mouth(p):
    m = p["mouth"]
    out = []
    if m == "smile":
        out.append(path("M-9 31 Q-4 35 0 32 Q4 35 9 31", fill="none", stroke=INK, stroke_width=2.4,
                        stroke_linecap="round"))
        fang_y = 33.5
    else:
        depth = 7.0 if m == "open_s" else 10.5
        d = "M-9 31 Q0 33 9 31 Q8 %g 0 %g Q-8 %g -9 31Z" % (31 + depth, 32 + depth, 31 + depth)
        out.append(path(d, fill=MOUTH_IN, stroke=INK, stroke_width=2.3, stroke_linejoin="round"))
        out.append(clip(path(d), ellipse(0, 33 + depth, 6, 3.6, fill=RUBY_HI)))
        fang_y = 32.0
    # MH3: one tiny fang, on her screen-left
    out.append(path(poly([(-6.6, fang_y - 0.6), (-2.6, fang_y - 0.2), (-4.8, fang_y + 5.2)]), fill="#ffffff",
                    stroke=INK, stroke_width=1.5, stroke_linejoin="round"))
    out.append(line(0, 24, 0, 31.5, stroke=INK, stroke_width=2.0))
    return g(out)


def _head(p):
    skull = path(blob(sym(HEAD_HALF)), fill=FUR)
    mask_d = blob(sym(MASK_HALF))
    muzzle_d = blob(sym(MUZZLE_HALF))
    marks = [
        path(blob([(-70, 26), (0, 40), (70, 26), (70, 70), (-70, 70)]), fill=SHADE),
        path(muzzle_d, fill=THROAT),
        clip(path(muzzle_d), path(blob([(-30, 34), (0, 40), (30, 34), (30, 60), (-30, 60)]), fill=THROAT_SH)),
        path(mask_d, fill=MASK),                                                   # MH2: bandit mask
    ]
    eyes = [eye(s * 21, 1, 10.0, 10.5, ink=INK, lid_fill=MASK, iris=EYES, iris_lo=EYES_LO, white="#fff6e8",
                lid=p["lid"], state=p["eyes"], arch=0.6, look=(0.0, 0.0), closed_width=4.6) for s in (-1, 1)]
    if p["eyes"] in ("closed", "happy"):      # closed eyes on a black mask: draw the arc in throat cream
        eyes = [[n.copy(stroke=THROAT) for n in e] for e in eyes]
    nose = blob([(-6, 19), (0, 18), (6, 19), (3, 24), (0, 26), (-3, 24)])
    face = detail(clip(skull, marks), eyes, _mouth(p),
                  path(nose, fill=MASK, stroke=INK, stroke_width=1.8, stroke_linejoin="round"),
                  [path("M%g -24 Q%g -27 %g -22" % (s * 8, s * 15, s * 22), fill="none", stroke=SHADE,
                        stroke_width=2.4, stroke_linecap="round") for s in (-1, 1)])     # a haughty brow
    return g(outlined(skull, ink=INK, width=W), face, transform=_head_tf(p))


def _head_tf(p):
    return "%s %s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 40), scale(1.12))


def _ears(p):
    tf = "%s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 40))
    return g(_ear(-1, p["ear_l"]), _ear(1, p["ear_r"]), transform=tf)


# ------------------------------------------------------------------ body, cape  (MH4, MH5)

COLLAR = [(12, 394), (34, 380), (52, 350), (70, 318, "c"), (76, 352), (68, 384), (46, 402), (22, 406)]


def _collar(p):
    """MH5: the high stand-up collar behind her head: cape-black outside, red inside."""
    out = []
    for s in (-1, 1):
        pts = [(s * x, y + p["bob"]) + tuple(r) for (x, y, *r) in COLLAR]
        shape = path(blob(pts), fill=LINING)
        rim = [(s * x, y + p["bob"]) for (x, y) in [(66, 322), (80, 322), (80, 404), (44, 412), (64, 382)]]
        out.append(g(outlined(shape, ink=INK, width=W),
                     detail(clip(shape, path(blob(rim), fill=CAPE),
                                 path(blob([(s * 20, 390 + p["bob"]), (s * 40, 382 + p["bob"]),
                                            (s * 50, 400 + p["bob"])]), fill=LINING_SH)))))
    return out


def _legs():
    out = []
    for s in (-1, 1):                                            # MH4: black stockings, little dark feet
        leg = path(capsule((s * 13, 436), (s * 14, 460), 8.5, 8.0), fill=MASK)
        foot = path(blob([(s * 4, 471), (s * 5, 462), (s * 15, 458), (s * 25, 462), (s * 27, 471)]), fill=MASK)
        out.append(outlined(leg, foot, ink=INK, width=W))
    return g(out)


def _torso(p):
    bob = p["bob"]
    d = blob(sym([(0, 386 + bob), (20, 390 + bob), (30, 412), (30, 438), (18, 448), (0, 449)]))
    shape = path(d, fill=FUR)
    marks = [path(blob(sym([(0, 386 + bob), (12, 390 + bob), (14, 410), (0, 424)])), fill=THROAT)]
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, marks)))


def _panel(side, p):
    """One front panel of the cape (screen side ``side``).  ``flourish`` sweeps the screen-left one out."""
    bob = p["bob"]
    f = p["flourish"] if side < 0 else 0.0
    top = (side * 6, 394 + bob)
    sh = (side * 40, 382 + bob)
    out_bot = (side * (64 + 52 * f), 456 - 64 * f)
    in_bot = (side * (24 + 40 * f), 456 - 22 * f)
    pts = [top, sh + ("c",), (side * (60 + 30 * f), 420 - 30 * f), out_bot + ("c",),
           ((out_bot[0] + in_bot[0]) / 2.0, max(out_bot[1], in_bot[1]) + 4 - 6 * f), in_bot + ("c",),
           (side * (14 + 18 * f), 420 - 6 * f)]
    shape = path(smooth(pts), fill=CAPE)
    # the red lining turned back along the inner edge; in the flourish the whole inside swings into view
    lining_pts = [top, (side * (14 + 18 * f), 420 - 6 * f), in_bot, (side * (24 + 40 * f + 12), in_bot[1] - 2),
                  (side * (24 + 12 * (1 - f) + 30 * f), 420 - 20 * f), (side * 14, 396 + bob)]
    if f > 0.5:
        lining_pts = [(side * 20, 400 + bob), (side * 56 * (0.6 + 0.4 * f), 410 - 26 * f), out_bot, in_bot,
                      (side * (14 + 18 * f), 420 - 6 * f)]
    marks = [path(smooth([(side * 44, 386), (side * 70, 420), (side * 70, 470), (side * 48, 470)]),
                  fill=CAPE_HI) if f < 0.5 else None,
             path(poly(lining_pts), fill=LINING)]
    paw = circle(out_bot[0] - side * 4, out_bot[1] - 4, 8.5, fill=FUR) if f > 0.3 else None
    return g(outlined(shape, paw, ink=INK, width=W), detail(clip(shape, marks)))


def _brooch(p):
    """MH5: a ruby brooch in a gold setting, fastening the cape at the throat."""
    y = 404.0 + p["bob"]
    return g(outlined(circle(0, y, 8.6, fill=GOLD), ink=INK, width=2.6),
             detail(circle(0, y, 5.4, fill=RUBY), circle(-1.8, y - 2.0, 1.8, fill=RUBY_HI)))


SPARKLES = {1: [(-112, 300, 10, LINING), (96, 410, 8, GOLD)],
            2: [(-120, 330, 12, GOLD), (100, 300, 9, LINING), (-60, 270, 7, LINING)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    fig = figure([_ears(p), _collar(p), _legs(), _torso(p), _panel(1, p), _panel(-1, p), _head(p), _brooch(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    "idle": anim([pose(REST), pose(REST, bob=1.4, squash=0.01, ear_l=-3, ear_r=-3),
                  pose(REST, bob=0.8, ear_r=5)], fps=4, loop=True),
    "talk": anim([pose(REST, mouth="open_l", tilt=-2.0), pose(REST, mouth="open_s", tilt=-1.0)], fps=7, loop=True),
    "blink": anim([pose(REST, lid=0.7), pose(REST, eyes="closed")], fps=10, loop=False),
    # "Good EVENING.": the cape swept out to show its lining
    "special": anim([pose(REST, flourish=0.45, tilt=-3.0, mouth="open_s"),
                     pose(REST, flourish=1.0, tilt=-5.0, mouth="open_l", sparkles=1, ear_l=-4, ear_r=-4),
                     pose(REST, flourish=1.0, tilt=-5.0, mouth="smile", lid=0.4, sparkles=2, ear_l=-4, ear_r=-4)],
                    fps=6, loop=False),
}
