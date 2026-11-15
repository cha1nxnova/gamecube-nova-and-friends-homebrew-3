"""HAZEL the red squirrel: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 a plume tail taller than her body, curled in an S behind her (figure 0.50 of Nova, tail tip 0.85);
MH2 tufted ears; MH3 cream belly; MH4 buck teeth just visible; MH5 a teal scarf; MH6 holds a memory card
(a plain grey rectangle with a notch, no logo) the way a squirrel holds an acorn.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

import math

from lib2d import (CX, anim, blob, capsule, circle, clip, detail, ellipse, g, heart, line, mix, outlined,
                   path, poly, pose, rect, ribbon, rotate, smooth, sparkle, sticker, sym, top_y, translate)
from lib2d.chibi import eye, figure, open_mouth, w_mouth
from lib2d.geom import bezier

CHAR_ID = "hazel"
HEIGHT = 0.50         # ear tufts at top_y(0.50); the tail plume reaches top_y(0.85)
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Hazel)
FUR = "#c8743c"
SHADE = "#a85c2c"
CREAM = "#f6e3c8"     # belly and tail underside
TUFT = "#8a4a22"      # ear tufts
EYES = "#3a2a22"
SCARF = "#2fa39a"
SCARF_SH = "#23807a"
# derived
INK = mix(TUFT, EYES, 0.55)
CREAM_SH = mix(CREAM, FUR, 0.28)
EAR_IN = mix(CREAM, FUR, 0.35)
IRIS = mix(EYES, FUR, 0.6)
NOSE = mix(EYES, "#c27a6a", 0.45)
MOUTH_IN = mix(INK, "#c25a5a", 0.35)
TONGUE = "#ee7fa6"
TEETH = "#fffaf0"
# the memory card: plain greys, no logo (MH6)
CARD = "#a3a6ae"
CARD_SH = "#83868f"
CARD_LO = "#c4c6cc"

W = 3.4
HEAD_Y = 354.0
TAIL_TOP = top_y(0.85)

DEFAULTS = {"bob": 0.0, "ear_l": 0.0, "ear_r": 0.0, "eyes": "open", "lid": 0.12, "look": (0.0, 0.0),
            "mouth": "w", "tail": 0.0, "tilt": 0.0, "squash": 0.0, "hop": 0.0, "hug": 0.0, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _mx(pts):
    return [(-q[0],) + tuple(q[1:]) for q in pts]


# ------------------------------------------------------------------ tail  (MH1)

TAIL_W = [26.0, 50.0, 60.0, 64.0, 62.0, 56.0, 40.0]


def _tail_spine(sway):
    """An S: out to the right at the hips, up behind her back, curling over at the top with the tip out."""
    k = sway
    lo = bezier((20, 452), (96, 462), (118 + 3 * k, 384), (84 + 4 * k, 330), 14)
    hi = bezier((84 + 4 * k, 330), (54 + 5 * k, 282), (34 + 8 * k, 226), (52 + 10 * k, 176), 14)
    top = bezier((52 + 10 * k, 176), (58 + 10 * k, 128), (116 + 12 * k, 124), (114 + 12 * k, 172), 10)
    return lo + hi[1:] + top[1:]


def _offset(spine, frac, widths):
    """The spine pushed sideways by ``frac`` of the local half-width (+ = left of travel)."""
    n = len(spine)
    out = []
    for i, pt in enumerate(spine):
        a, b = spine[max(i - 1, 0)], spine[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        t = i / float(n - 1)
        x = t * (len(widths) - 1)
        j = min(int(x), len(widths) - 2)
        w = widths[j] + (widths[j + 1] - widths[j]) * (x - j)
        out.append((pt[0] - dy / m * frac * w / 2.0, pt[1] + dx / m * frac * w / 2.0))
    return out


def _tail(p):
    spine = _tail_spine(p["tail"])
    d = ribbon(spine, TAIL_W)
    shape = path(d, fill=FUR)
    # cream underside along the inner (body-facing / lower) edge of the S, plus one shade on the outer edge
    under = path(ribbon(_offset(spine, -0.74, TAIL_W), [8, 18, 22, 22, 20, 16, 6]), fill=CREAM)
    outer = path(ribbon(_offset(spine, 0.84, TAIL_W), [4, 12, 14, 14, 12, 10, 4]), fill=SHADE)
    # a few fur flicks on the plume
    flicks = []
    for t, s in ((0.42, 1), (0.7, -1)):
        i = int(t * (len(spine) - 1))
        x, y = spine[i]
        flicks.append(path("M%g %g q%g %g %g %g" % (x - 6, y + 4, 6 * s, -4, 12, -10), fill="none", stroke=INK,
                           stroke_width=1.8, stroke_linecap="round"))
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, outer, under), flicks))


# ------------------------------------------------------------------ head  (MH2, MH4)

HEAD_HALF = [(0, -44), (24, -42), (42, -31), (51, -12), (52, 6), (58, 16, "c"), (47, 22), (40, 32), (22, 42),
             (0, 45)]
EAR = [(16, -28), (17, -50), (27, -70, "c"), (40, -52), (44, -30)]
EAR_INNER = [(23, -32), (24, -48), (28, -58, "c"), (35, -47), (37, -32)]
EAR_ROOT = (30.0, -32.0)


def _ear(side, extra):
    pts = EAR if side > 0 else _mx(EAR)
    shape = path(blob(pts), fill=FUR)
    tip = (side * 27.0, -70.0)
    lean = side * 6.0
    spine = [(tip[0] - side * 1, tip[1] + 8), (tip[0] + lean * 0.3, tip[1] - 6), (tip[0] + lean * 0.8, tip[1] - 16),
             (tip[0] + lean * 1.6, tip[1] - 22)]
    tuft = path(ribbon(spine, [12.0, 10.5, 6.5, 2.0]), fill=TUFT)      # MH2: a dark tuft off each ear tip
    inner = path(blob(EAR_INNER if side > 0 else _mx(EAR_INNER)), fill=EAR_IN)
    tf = rotate(side * extra, side * EAR_ROOT[0], EAR_ROOT[1])
    return g(outlined(shape, tuft, ink=INK, width=W), detail(clip(shape, inner)), transform=tf)


def _mouth(p):
    m = p["mouth"]
    teeth = [rect(-6.2, 0, 6.0, 8.6, 1.6, fill=TEETH, stroke=INK, stroke_width=1.6),
             rect(0.2, 0, 6.0, 8.6, 1.6, fill=TEETH, stroke=INK, stroke_width=1.6)]
    if m == "w":     # MH4: two buck teeth peeking under the "w"
        return g(g(teeth, transform=translate(0, 19.2)), w_mouth(0, 19, 8.0, 3.6, ink=INK, width=2.3,
                                                                  philtrum=3.0))
    big = m == "open"
    return g(open_mouth(0, 19.5, 8.5 if big else 6.5, 11.0 if big else 7.0, ink=INK, inner=MOUTH_IN,
                        tongue=TONGUE, width=2.2),
             g(teeth, transform=translate(0, 19.0)),
             w_mouth(0, 19, 8.0, 3.0, ink=INK, width=2.3, philtrum=3.0))


def _head(p):
    skull_d = blob(sym(HEAD_HALF))
    skull = path(skull_d, fill=FUR)
    muzzle = blob(sym([(0, 2), (14, 4), (26, 14), (28, 28), (16, 40), (0, 42)]))
    marks = [path(blob([(-90, 26), (0, 40), (90, 26), (90, 90), (-90, 90)]), fill=SHADE),
             path(blob([(36, -40), (70, -20), (70, 40), (44, 30), (48, 0)]), fill=SHADE),
             path(muzzle, fill=CREAM),
             clip(path(muzzle), path(blob([(-90, 34), (0, 46), (90, 34), (90, 90), (-90, 90)]), fill=CREAM_SH))]
    eyes = [eye(s * 22, -6, 12.0, 13.2, ink=INK, lid_fill=SHADE, iris=IRIS, iris_lo=EYES, pupil=INK,
                lid=p["lid"], state=p["eyes"], look=p["look"]) for s in (-1, 1)]
    nose = blob([(-5.5, 10), (0, 9), (5.5, 10), (3, 14.5), (0, 16), (-3, 14.5)])
    face = detail(clip(skull, marks), eyes, _mouth(p),
                  path(nose, fill=NOSE, stroke=INK, stroke_width=1.8, stroke_linejoin="round"),
                  ellipse(-1.8, 10.8, 1.8, 1.0, fill="#ffffff"))
    tf = "%s %s" % (translate(0, HEAD_Y + p["bob"]), rotate(p["tilt"], 0, 44))
    return g(_ear(-1, p["ear_l"]), _ear(1, p["ear_r"]), outlined(skull, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ body  (MH3), scarf (MH5), card (MH6)

BODY_HALF = [(0, 382), (24, 386), (37, 402), (43, 428), (41, 452), (33, 465), (0, 467)]
FOOT = [(6, 465), (9, 455), (22, 451), (36, 456), (40, 465), (33, 471), (20, 472.5), (9, 471)]


def _body(p):
    bob = p["bob"]
    pts = [(x, y + bob * max(0.0, (450.0 - y) / 60.0)) for x, y in BODY_HALF]
    body = path(blob(sym(pts)), fill=FUR)
    feet = [path(blob(FOOT), fill=FUR), path(blob(_mx(FOOT)), fill=FUR)]
    belly_d = blob(sym([(0, 398), (24, 404), (32, 430), (28, 454), (0, 464)]))
    marks = [path(blob([(30, 384), (60, 396), (60, 472), (32, 472), (40, 430)]), fill=SHADE),
             path(belly_d, fill=CREAM),                                                    # MH3
             clip(path(belly_d), path(blob([(16, 400), (40, 410), (40, 470), (14, 470), (24, 436)]),
                                      fill=CREAM_SH))]
    foot_sh = [path(blob([(s * 6, 468), (s * 22, 470), (s * 42, 467), (s * 42, 476), (s * 6, 476)]), fill=SHADE)
               for s in (-1, 1)]
    toes = [line(s * x, 466, s * x, 471.5, stroke=INK, stroke_width=1.7) for s in (-1, 1) for x in (18.0, 27.0)]
    return g(outlined(body, feet, ink=INK, width=W), detail(clip(body, marks), clip(feet, foot_sh), toes))


def _scarf(p):
    """MH5: a teal scarf wrapped once round the neck, one end hanging over her (screen-left) shoulder."""
    bob = p["bob"]
    wrap_d = blob(sym([(0, 392), (30, 389), (44, 395, "c"), (40, 408), (0, 414)]))
    end_d = blob([(-24, 404), (-38, 404), (-46, 430), (-44, 442, "c"), (-38, 436), (-33, 443, "c"), (-29, 432),
                  (-22, 410)])
    wrap, end = path(wrap_d, fill=SCARF), path(end_d, fill=SCARF)
    marks = [path(blob([(-60, 402), (0, 410), (60, 402), (60, 430), (-60, 430)]), fill=SCARF_SH),
             path(blob([(-36, 424), (-50, 424), (-50, 450), (-30, 450)]), fill=SCARF_SH)]
    stripes = [line(x, 395 + abs(x) * 0.05, x - 1, 410, stroke=SCARF_SH, stroke_width=1.6) for x in (-14, 14)]
    return g(outlined(end, ink=INK, width=W), detail(clip(end, marks)),
             outlined(wrap, ink=INK, width=W), detail(clip(wrap, marks), stripes),
             transform=translate(0, bob * 0.8))


def _card(cx, cy, rot_deg):
    """MH6: a plain grey memory card (no logo): a notched corner, the connector ridge and a blank label."""
    w, h = 34.0, 40.0
    x0, y0 = -w / 2, -h / 2
    n = 8.0
    body = path(poly([(x0, y0), (x0 + w - n, y0), (x0 + w, y0 + n), (x0 + w, y0 + h), (x0, y0 + h)]), fill=CARD)
    marks = [rect(x0, y0, w, 7.5, fill=CARD_SH),
             rect(x0 + 5, y0 + 13, w - 10, h - 19, 3, fill=CARD_LO),
             path(poly([(x0 + w - 7, y0), (x0 + w, y0), (x0 + w, y0 + h), (x0 + w - 7, y0 + h)]), fill=CARD_SH)]
    ridge = [line(x0 + 5 + 6 * i, y0 + 2, x0 + 5 + 6 * i, y0 + 5.5, stroke=mix(CARD_SH, INK, 0.4),
                  stroke_width=1.6) for i in range(4)]
    return g(outlined(body, ink=INK, width=W), detail(clip(body, marks), ridge),
             transform="%s %s" % (translate(cx, cy), rotate(rot_deg)))


def _arms_and_card(p):
    bob, hug = p["bob"], p["hug"]
    card_y = 434 - 12 * hug + bob * 0.5
    card = _card(0, card_y, -6 + 6 * hug)
    arms, paws = [], []
    for s in (-1, 1):
        sh = (s * 34, 412 + bob * 0.7)
        hand = (s * (20 - 6 * hug), card_y - 2 - 2 * hug)
        arms.append(outlined(path(capsule(sh, hand, 9.0, 8.0), fill=FUR), ink=INK, width=W))
        paws.append(outlined(ellipse(hand[0] - s * 1.5, hand[1] + 1, 8.6, 9.6, fill=FUR), ink=INK, width=W))
        paws.append(detail(line(hand[0] - s * 7, hand[1] - 2, hand[0] - s * 4, hand[1] + 0.5, stroke=INK,
                                stroke_width=1.5),
                           line(hand[0] - s * 7, hand[1] + 4, hand[0] - s * 4, hand[1] + 5.5, stroke=INK,
                                stroke_width=1.5)))
    return g(arms, card, paws)


SPARKLES = {1: [(-80, 330, 11, CREAM), (86, 404, 8, SCARF)],
            2: [(-86, 352, 8, SCARF), (74, 410, 11, CREAM)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    if p["sparkles"] == 2:
        extras.append(heart(CX - 62, 300, 9, ink=INK))
    fig = figure([_tail(p), _body(p), _scarf(p), _head(p), _arms_and_card(p)], p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()

ANIMS = {
    # a quick little breath, the tail swaying, one ear flicking: she is never quite still
    "idle": anim([pose(REST), pose(REST, bob=1.4, squash=0.01, tail=1.0, ear_r=-6),
                  pose(REST, bob=0.7, tail=0.5)], fps=5, loop=True),
    "talk": anim([pose(REST, mouth="open", tilt=-2.0), pose(REST, mouth="open_s", tilt=-1.0)], fps=8, loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
    # she hugs her memory card
    "special": anim([pose(REST, hug=0.6, eyes="happy", tilt=-3.0, tail=0.6),
                     pose(REST, hug=1.0, eyes="happy", tilt=-4.0, squash=0.03, tail=1.2, sparkles=1),
                     pose(REST, hug=1.0, eyes="happy", tilt=-3.0, squash=0.01, tail=0.8, sparkles=2)],
                    fps=6, loop=False),
}
