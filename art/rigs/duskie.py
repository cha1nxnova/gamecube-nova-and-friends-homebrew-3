"""DUSKIE the golden jackal: the recurring guest.  Same house style and pipeline as ``nova.py`` (read that first).

Chibi die-cut sticker, front-facing, in a sky-blue bandana.  Canon is docs/CHARACTERS.md; every must-have on
that list has a numbered comment here (``# MH2`` = must-have 2).  MH4 (the mottled saddle) is on his upper back
and is "seen from behind or three-quarter views only", so a front-facing sprite cannot show it.

Why a bandana and not a tee: the canon lets the project choose, and a tee would hide three of his must-haves
(cream chest, cream belly, shoulder freckles).  The bandana keeps them all on show.

Coordinates follow nova.py: the body is drawn around x = 0 and moved to the canvas centre line at the end; y
is canvas y (feet on ``BASELINE``).  The head has its own frame (origin at the middle of the skull) so it can
bob and tilt.  "l" / "r" always mean *screen* left / right.
"""
from __future__ import annotations

import math

from lib2d import (BASELINE, CX, along, anim, band, bezier, blob, capsule, circle, clamp, clip, cycle, detail,
                   ellipse, g, lerp, lerp_pts, line, mix, outlined, path, poly, pose, rotate, scale, smooth,
                   sparkle, sticker, sym, translate, zzz)

CHAR_ID = "duskie"
HEIGHT = 0.88         # between Iggy and Nova: ear tips at top_y(0.88)

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Duskie)
GOLD = "#ffd37c"      # coat, main
GOLD_D = "#fec349"    # coat, deep gold: the coat's one shade tone
CREAM = "#fdebc8"     # muzzle, chest, belly, socks, inner ear
BROWN = "#b5832a"     # brown-gold: ear backs / tips, tail brush, brow dots, freckles
IRIS = "#79bff0"
IRIS_LO = "#4a98d6"
BLACK = "#1f1c1a"     # nose, paw pads, pupils
SKY = "#9fd3f5"       # bandana
TONGUE = "#ee7fa6"    # the house tongue pink (Nova's palette row); his own palette lists none
# derived tones (one soft shade per colour area)
INK = mix(BROWN, BLACK, 0.80)         # his ink line: the brown-gold taken down almost to the nose black
CREAM_SH = mix(CREAM, GOLD_D, 0.32)
BROWN_SH = mix(BROWN, BLACK, 0.26)
SKY_SH = mix(SKY, IRIS_LO, 0.45)
IRIS_HI = mix(IRIS, "#ffffff", 0.55)
EYE_W = mix(CREAM, "#ffffff", 0.82)   # eye whites: a warm white
FLUFF = mix(CREAM, "#ffffff", 0.55)   # ear fluff
LID = mix(GOLD_D, BROWN, 0.06)        # eyelids: deep gold with a breath of brown so the lids read
MOUTH_IN = mix(INK, TONGUE, 0.3)
TONGUE_SH = mix(TONGUE, INK, 0.28)

W = 3.4               # ink line width (units outside each part): the same as Nova's
HEAD_Y = 223.0        # canvas y of the head frame origin
NECK = (0.0, 62.0)    # head-frame pivot for tilt

# ------------------------------------------------------------------ pose parameters
DEFAULTS = {
    "ear_l": 0.0,          # extra ear rotation, degrees; + = droops outward, - = perks upright
    "ear_r": 0.0,
    "eyes": "soft",        # "soft" (his relaxed resting look) | "open" | "closed" | "happy"
    "lid": None,           # override how far the upper lids are down, 0 (wide) .. 1 (shut)
    "look": (0.0, 0.0),    # where the pupils point, each -1 .. 1 (x: screen left .. right, y: up .. down)
    "mouth": "smile",      # "smile" (easy closed grin) | "open_s" | "open_l" | "grin" | "pant" (tongue out)
    "arm_l": (13.0, 5.0),  # (upper arm, forearm) angles from straight down, + = away from the body
    "arm_r": (13.0, 5.0),
    "hand_l": "paw",       # "paw" | "open" (palm + black pads)
    "hand_r": "paw",
    "bob": 0.0,            # chest + head down (+) or up (-), units; the hips stay put
    "squash": 0.0,         # whole figure: + squashes onto the feet, - stretches
    "hop": 0.0,            # whole figure off the ground, units
    "sway": 0.0,           # whole figure leaning about the feet, degrees clockwise (the wag wiggle)
    "tilt": 0.0,           # head tilt, degrees clockwise
    "nod": 0.0,            # head only, down (+)
    "tail": 0.0,           # tail swing, -1 (tucked in) .. 1 (swung out and up); the big wag pushes past 1
    "tail_side": 1,        # 1 = screen right (where it rests), -1 = swung across to screen left
    "zzz": None,           # None, or 0..1 drift of the sleep Zs
    "sparkles": 0,         # 0..3 sparkle arrangement (0 = none)
    "big": False,          # extra fine detail for large stills (more freckles, ear hairs, bandana stars)
}

ARM_DOWN = (13.0, 5.0)


def _p(pose_in):
    p = dict(DEFAULTS)
    p.update(pose_in or {})
    return p


def _mx(points):
    return [(-pt[0],) + tuple(pt[1:]) for pt in points]


# ------------------------------------------------------------------ ears  (MH1)

EAR_OUT = [(-28, 14), (-31, -16), (-25, -46), (-13, -72), (-1, -92, "c"), (10, -72), (23, -44), (30, -15),
           (28, 14)]
EAR_INNER = [(-17, 12), (-21, -15), (-16, -38), (-7, -57), (0, -68, "c"), (7, -56), (15, -37), (20, -14),
             (18, 12)]
EAR_DEEP = [(1, 12), (-3, -16), (2, -40), (6, -52), (12, -36), (15, -14), (13, 12)]
EAR_FLUFF = [(-16, 12), (-19, -16), (-11, -34, "c"), (-10, -19), (-1, -30, "c"), (-2, -12), (8, -19, "c"),
             (6, -2), (11, 12)]
# brown-gold back showing as the rim's upper half and the whole tip, with a furry lower edge
EAR_TIP = [(-40, -30), (-26, -41), (-17, -31), (-6, -44), (4, -33), (15, -43), (24, -32), (40, -40),
           (40, -110), (-40, -110)]
EAR_AT = (53.0, -38.0)      # where an ear is rooted on the skull (head frame, screen-right ear)
EAR_SPREAD = 15.0           # resting outward lean, degrees


def _ear(side, extra, big):
    """One ear in the head frame.  ``side`` is -1 (screen left) or +1."""
    shape = path(blob(EAR_OUT), fill=GOLD)
    hairs = [((-15, -6), (-5, -34), (5, -50)), ((-12, 4), (3, -20), (13, -32))]
    if big:
        hairs.append(((-17, -18), (-11, -42), (-3, -58)))
    inner = detail(
        clip(shape, path(poly(EAR_TIP), fill=BROWN)),
        path(smooth(EAR_INNER), fill=CREAM),
        path(blob(EAR_DEEP), fill=CREAM_SH),
        path(smooth(EAR_FLUFF), fill=FLUFF),
        [path("M%g %g Q%g %g %g %g" % (a + b + c), fill="none", stroke=INK, stroke_width=1.5,
              stroke_linecap="round") for a, b, c in hairs],
    )
    tf = "%s %s" % (translate(side * EAR_AT[0], EAR_AT[1]), rotate(side * (EAR_SPREAD + extra)))
    if side < 0:
        tf += " " + scale(-1, 1)
    return g(outlined(shape, ink=INK, width=W), inner, transform=tf)


# ------------------------------------------------------------------ face  (MH2)

EYE_X, EYE_Y, EYE_RX, EYE_RY = 41.0, 5.0, 21.0, 22.5


def _eye(side, p):
    """One eye in the head frame.  Built exactly like Nova's; only the lids and colours differ."""
    ex, ey, rx, ry = side * EYE_X, EYE_Y, EYE_RX, EYE_RY
    state = p["eyes"]
    lx, ly = p["look"]
    if state in ("closed", "happy"):
        if state == "closed":    # relaxed, curved downwards
            d = "M%g %g Q%g %g %g %g" % (ex - 19, ey + 4, ex, ey + 18, ex + 19, ey + 4)
        else:                    # happy arcs
            d = "M%g %g Q%g %g %g %g" % (ex - 19, ey + 10, ex, ey - 12, ex + 19, ey + 10)
        return [path(d, fill="none", stroke=INK, stroke_width=6.6, stroke_linecap="round")]
    f = p["lid"]
    if f is None:
        f = 0.10 if state == "open" else 0.21
    lid_y = ey - ry + 2 * ry * f
    low_y = ey + ry - (2.0 if state == "soft" else 0.0)          # lower lid lifted a little by the smile
    eye_shape = ellipse(ex, ey, rx, ry)
    # the upper lid is an arch (round, friendly dog eyes; Nova's lids are straight and smug)
    lid_d = "M%g %g Q%g %g %g %g" % (ex - 34, lid_y + 10, ex, lid_y - 16, ex + 34, lid_y + 10)
    opening = path("%s L%g %g Q%g %g %g %gZ" % (
        lid_d, ex + 34, low_y, ex, low_y + (3.0 if state == "soft" else 0.0), ex - 34, low_y))
    ix, iy = ex + lx * 6.8, ey + 3.5 + ly * 4.5
    iris = circle(ix, iy, 17.8)
    inside = [
        ellipse(ex, ey, rx + 3, ry + 3, fill=EYE_W),
        clip(iris,
             circle(ix, iy, 18.6, fill=IRIS),
             circle(ix, iy + 15.5, 17.8, fill=IRIS_LO),
             circle(ix, iy, 11.6, fill="none", stroke=IRIS_HI, stroke_width=3.0),
             circle(ix, iy, 17.2, fill="none", stroke=IRIS_LO, stroke_width=2.4)),   # pale iris needs a rim
        ellipse(ix, iy + 0.5, 7.8, 8.8, fill=BLACK),
        circle(ix - 6.4, iy - 5.2, 4.9, fill="#ffffff"),
        circle(ix + 6.2, iy + 7.6, 2.2, fill="#ffffff"),
    ]
    lash = path(lid_d, fill="none", stroke=INK, stroke_width=5.2, stroke_linecap="round")
    return [
        ellipse(ex, ey, rx + 2.6, ry + 2.6, fill=INK),
        ellipse(ex, ey, rx, ry, fill=LID),
        clip(eye_shape, clip(opening, inside)),
        clip(ellipse(ex + side * 1.6, ey, rx + 3.6, ry + 5.5), lash),       # a small flick at the outer corner
    ]


# the mouth line: a wide soft "w" with the corners turned up (his easy grin); left half as a cubic Bezier
MOUTH_L = [(-29.0, 44.5), (-28.0, 57.5), (-8.0, 61.0), (0.0, 51.0)]
MOUTH_LINE = "M-29 44.5 C-28 57.5 -8 61 0 51 C8 61 28 57.5 29 44.5"
# name -> (how much of the "w" opens: 0 = corner to corner .. 1 = nothing, how deep, tongue (rx, ry), jaw drop)
MOUTHS = {
    "smile": (None, 0.0, None, 0.0),
    "open_s": (0.64, 10.0, (6.0, 4.0), 2.5),
    "open_l": (0.52, 15.5, (8.2, 5.6), 6.0),
    "grin": (0.26, 20.5, (11.0, 7.0), 6.5),
    "pant": (0.26, 20.5, (11.0, 7.0), 6.5),
}


def _cavity(t0, depth):
    """Open-mouth shape hanging under the mouth line from parameter ``t0`` of each half, ``depth`` deep."""
    pts = bezier(*MOUTH_L, n=20)
    left = pts[int(round(t0 * 20)):]
    xl, yl = left[0]
    top = [(xl, yl, "c")] + left[1:-1] + [(0.0, 51.0, "c")] + [(-x, y) for x, y in reversed(left[1:-1])]
    jaw = [(-xl, yl, "c"), (-xl * 0.92, yl + depth * 0.58), (-xl * 0.5, yl + depth * 0.95), (0.0, yl + depth),
           (xl * 0.5, yl + depth * 0.95), (xl * 0.92, yl + depth * 0.58)]
    return smooth(top + jaw), yl + depth


def _mouth(p):
    name = p["mouth"]
    t0, depth, tongue, _ = MOUTHS[name]
    out = []
    if t0 is not None:
        d, bottom = _cavity(t0, depth)
        out.append(path(d, fill=MOUTH_IN, stroke=INK, stroke_width=2.8, stroke_linejoin="round"))
        out.append(clip(path(d), ellipse(0, bottom - 0.5, tongue[0], tongue[1], fill=TONGUE)))
    if name == "pant":           # happy dog: tongue lolling over the lower lip
        t = blob([(-8.2, 63.5), (-9.2, 74), (-5.6, 82.5), (0, 85.5), (5.6, 82.5), (9.2, 74), (8.2, 63.5),
                  (0, 61.5)])
        out.append(path(t, fill=TONGUE, stroke=INK, stroke_width=2.5, stroke_linejoin="round"))
        out.append(line(0, 67.5, 0, 78.5, stroke=TONGUE_SH, stroke_width=1.8))
    out.append(path(MOUTH_LINE, fill="none", stroke=INK, stroke_width=2.8, stroke_linecap="round",
                    stroke_linejoin="round"))
    out.append(line(0, 45, 0, 51, stroke=INK, stroke_width=2.4))
    return g(out)


HEAD_TUFT = [(-13, -54), (-10, -70, "c"), (-3, -62), (4, -75, "c"), (9, -62), (17, -66, "c"), (19, -54),
             (2, -48)]


def _head(p):
    jaw = MOUTHS[p["mouth"]][3]
    half = [(0, -62), (38, -60), (70, -45), (89, -20), (95, 3), (113, 13, "c"), (101, 25), (116, 38, "c"),
            (100, 46), (107, 60, "c"), (87, 59 + jaw * 0.3), (62, 67 + jaw * 0.6), (34, 74 + jaw),
            (0, 76 + jaw)]
    skull = path(blob(sym(half)), fill=GOLD)
    tuft = path(smooth(HEAD_TUFT), fill=GOLD)                  # a scruffy little cowlick between the ears
    # one soft shade along the bottom of the cheek ruffs and jaw
    low = blob(sym([(0, 67 + jaw), (34, 65 + jaw), (62, 58 + jaw * 0.6), (84, 49), (100, 38), (118, 28),
                    (132, 62), (70, 102), (0, 108 + jaw)]))
    # MH2: cream muzzle and throat: a rounded snout shape that starts between the eyes
    muzzle = blob(sym([(0, 17), (17, 19.5), (33, 29), (46, 43), (53, 58), (52, 76), (40, 98),
                       (0, 106 + jaw)]))
    freckles = [(63.5, 33.5, 3.0), (73.5, 29.5, 2.7), (70.5, 40.5, 2.6)]
    if p["big"]:
        freckles += [(81, 37.5, 2.0), (61, 43, 1.9)]
    marks = [
        path(low, fill=GOLD_D),
        path(muzzle, fill=CREAM),
        clip(path(muzzle), path(low, fill=CREAM_SH)),
        # MH2: a brown-gold brow dot above each eye
        [ellipse(s * 37.5, -32.5, 7.6, 5.8, rot=-s * 14, fill=BROWN) for s in (-1, 1)],
        # MH2: freckles across the cheeks
        [[circle(s * x, y, r, fill=BROWN) for (x, y, r) in freckles] for s in (-1, 1)],
    ]
    nose = blob([(-13.5, 31.5), (0, 29), (13.5, 31.5), (10, 40.5), (0, 46), (-10, 40.5)])
    face = detail(
        clip(skull, marks),
        _eye(-1, p), _eye(1, p),
        _mouth(p),
        path(nose, fill=BLACK, stroke=INK, stroke_width=2.5, stroke_linejoin="round"),      # MH2: black nose
        ellipse(-4.4, 34.2, 4.0, 1.9, fill="#ffffff"),
    )
    hy = HEAD_Y + p["bob"] + p["nod"]
    tf = "%s %s" % (translate(0, hy), rotate(p["tilt"], NECK[0], NECK[1]))
    return g(_ear(-1, p["ear_l"], p["big"]), _ear(1, p["ear_r"], p["big"]),
             outlined(skull, tuft, ink=INK, width=W), face, transform=tf)


# ------------------------------------------------------------------ body, legs, feet  (MH3, MH6)

BODY_HALF = [(0, 270), (22, 270, "c"), (24, 290), (44, 297), (57, 309), (58, 350), (58, 396), (60, 424),
             (56, 450), (56, 465, "c"), (15, 465, "c"), (14, 443), (9, 427), (0, 418, "c")]
BELLY_HALF = [(0, 290), (25, 292), (31, 316), (26, 331), (34, 344, "c"), (28, 353), (32, 373), (29, 395),
              (19, 411), (0, 421)]
FOOT = [(4, 462), (9, 451.5), (32, 447.5), (56, 451.5), (65, 462), (60, 470.4), (34, 471.8), (9, 470.4)]
SOCK = [(8, 449), (16, 441), (24, 448.5), (33, 440), (42, 448.5), (51, 441), (63, 449), (63, 474), (8, 474)]


def _by(y, bob):
    """Canvas y of a torso point: the chest rides the breath fully, the hips not at all."""
    return y + bob * clamp((404.0 - y) / 70.0)


def _breathe(points, bob):
    return [(pt[0], _by(pt[1], bob)) + tuple(pt[2:]) for pt in points]


def _body(p):
    """Torso, legs and feet.  The feet stay planted; the chest moves with ``bob``."""
    bob = p["bob"]
    body = path(blob(sym(_breathe(BODY_HALF, bob))), fill=GOLD)
    feet = [path(blob(FOOT), fill=CREAM), path(blob(_mx(FOOT)), fill=CREAM)]         # MH3: cream socks
    belly_d = blob(sym(_breathe(BELLY_HALF, bob)))
    belly = path(belly_d)
    marks = [
        # one soft shade down the screen-right side, and the shadow the head throws on the chest
        path(blob([(47, 296), (68, 302), (70, 472), (50, 472), (52, 400), (51, 350)]), fill=GOLD_D),
        path(blob([(-12, 440), (-21, 452), (-22, 472), (-10, 472)]), fill=GOLD_D),
        path(poly([(-70, 262), (70, 262), (70, 303), (0, 310), (-70, 303)]), fill=GOLD_D),
        # MH3: cream chest and belly (shaded on the same side as the coat)
        path(belly_d, fill=CREAM_SH),
        clip(belly, path(belly_d, fill=CREAM, transform=translate(-5.5, -1.5))),
        clip(belly, path(poly([(-70, 262), (70, 262), (70, 303), (0, 310), (-70, 303)]), fill=CREAM_SH)),
        # MH3: socks: the cream runs up over the ankles with a furry edge
        path(poly(SOCK), fill=CREAM), path(poly(_mx(SOCK)), fill=CREAM),
    ]
    toes = [line(s * x, 464.5, s * x, 470.8, stroke=INK, stroke_width=2.2)
            for s in (-1, 1) for x in (24.0, 44.5)]
    foot_shade = [path(blob([(s * 8, 468.2), (s * 34, 469.8), (s * 61, 467.2), (s * 63, 476), (s * 8, 476)]),
                       fill=CREAM_SH) for s in (-1, 1)]
    return g(outlined(body, feet, ink=INK, width=W),
             detail(clip(body, marks), clip(feet, foot_shade), toes))


# ------------------------------------------------------------------ the bandana

BANDANA_HALF = [(0, 277), (32, 279), (54, 287, "c"), (40, 314), (17, 344), (0, 358, "c")]
STAR = [(0, -1), (0.24, -0.24), (1, 0), (0.24, 0.24), (0, 1), (-0.24, 0.24), (-1, 0), (-0.24, -0.24)]


def _bandana(p):
    """A sky-blue neckerchief: knotted behind the neck, the point hanging over the chest."""
    d = smooth(sym(BANDANA_HALF))
    shape = path(d, fill=SKY)
    stars = [(0.0, 328.0, 8.0)]
    if p["big"]:
        stars += [(-21.0, 311.0, 5.0), (20.0, 309.0, 4.4)]
    marks = [
        path(d, fill=SKY_SH),                                                    # shade down the right edge
        clip(shape, path(d, fill=SKY, transform=translate(-6.5, -3.0))),
        path("M-70 262 L70 262 L70 300 Q0 316 -70 300Z", fill=SKY_SH),            # the head's shadow
        [path(poly([(x + sx * r, y + sy * r) for sx, sy in STAR]), fill=FLUFF) for (x, y, r) in stars],
    ]
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, marks)), transform=translate(0, p["bob"]))


# ------------------------------------------------------------------ arms and hands  (MH3)

L1, L2 = 42.0, 30.0     # upper arm, forearm lengths: shorter and thicker than Nova's
SHOULDER = (58.0, 312.0)


def _arm_points(side, angles, bob):
    a1, a2 = math.radians(angles[0]), math.radians(angles[1])
    s = (side * SHOULDER[0], SHOULDER[1] + bob)
    e = (s[0] + side * math.sin(a1) * L1, s[1] + math.cos(a1) * L1)
    w = (e[0] + side * math.sin(a2) * L2, e[1] + math.cos(a2) * L2)
    return s, e, w


def _hand(kind, side):
    """Hand shapes in the hand frame: wrist at the origin, fingers towards -y.  Returns (shapes, paint)."""
    if kind == "open":       # palm towards us: MH3, black pads
        shapes = [circle(0, -13.5, 15.2, fill=CREAM)]
        fingers = [(-13.0, -25.0), (-4.8, -31.8), (4.9, -31.8), (13.0, -25.0)]
        shapes += [circle(x, y, 6.6, fill=CREAM) for x, y in fingers]
        shapes.append(circle(-side * 17.2, -10.5, 6.0, fill=CREAM))            # thumb, body side
        paint = [path(blob([(-8.6, -9.5), (-6.5, -17.5), (0, -20.0), (6.5, -17.5), (8.6, -9.5), (0, -5.8)]),
                      fill=BLACK)]
        paint += [circle(x, y - 0.6, 3.3, fill=BLACK) for x, y in fingers]
        return shapes, paint
    # "paw": the back of a mitten paw
    shapes = [path(blob([(-12, 2), (-16.5, -11), (-12.5, -24), (0, -28.5), (12.5, -24), (16.5, -11),
                         (12, 2)]), fill=CREAM)]
    paint = [line(-5.2, -27.2, -5.2, -19.6, stroke=INK, stroke_width=2.1),
             line(5.2, -27.2, 5.2, -19.6, stroke=INK, stroke_width=2.1)]
    return shapes, paint


def _arm(side, p):
    angles = p["arm_l"] if side < 0 else p["arm_r"]
    kind = p["hand_l"] if side < 0 else p["hand_r"]
    s, e, w = _arm_points(side, angles, p["bob"])
    d1 = ((e[0] - s[0]) / L1, (e[1] - s[1]) / L1)
    d2 = ((w[0] - e[0]) / L2, (w[1] - e[1]) / L2)
    n1 = (-d1[1], d1[0])
    n2 = (-d2[1], d2[0])
    upper_d = capsule(s, e, 14.6, 14.0)
    fore_d = capsule(e, w, 14.0, 13.2)
    shapes, paint = _hand(kind, side)
    htf = "%s %s" % (translate(w[0], w[1]), rotate(math.degrees(math.atan2(d2[0], -d2[1]))))
    # MH3: cream sock over the wrist with a furry upper edge, halfway up the forearm
    c = (lerp(e[0], w[0], 0.48), lerp(e[1], w[1], 0.48))
    zig = []
    for i in range(7):
        u = -1.0 + i / 3.0
        off = 3.8 if i % 2 else -2.8
        zig.append((c[0] + n2[0] * 18 * u + d2[0] * off, c[1] + n2[1] * 18 * u + d2[1] * off))
    far = [(w[0] + n2[0] * 20 + d2[0] * 10, w[1] + n2[1] * 20 + d2[1] * 10),
           (w[0] - n2[0] * 20 + d2[0] * 10, w[1] - n2[1] * 20 + d2[1] * 10)]
    sock = path(poly(zig + far), fill=CREAM)
    # MH3: freckles on the shoulders (they ride on the upper arm)
    out = -side
    spots = [(5.0, 6.0, 2.6), (12.5, 8.5, 2.3), (15.0, 1.0, 2.5)]
    if p["big"]:
        spots += [(21.0, 6.5, 1.9), (7.5, -1.5, 1.8)]
    freckles = [circle(s[0] + d1[0] * a + n1[0] * b * out, s[1] + d1[1] * a + n1[1] * b * out, r, fill=BROWN)
                for (a, b, r) in spots]
    return g(
        outlined(path(upper_d, fill=GOLD), path(fore_d, fill=GOLD), g(shapes, transform=htf),
                 ink=INK, width=W),
        detail(clip(path(fore_d), sock), clip(path(upper_d), freckles), g(paint, transform=htf)),
    )


# ------------------------------------------------------------------ tail  (MH5)

TAIL_IN = [(20, 404), (60, 446), (116, 452), (112, 368)]
TAIL_OUT = [(20, 404), (82, 444), (182, 440), (176, 312)]
TAIL_W = [20.0, 40.0, 54.0, 50.0, 24.0]         # full width from root to tip: a bushy brush


def _tail_w(t):
    x = clamp(t) * (len(TAIL_W) - 1)
    i = min(int(x), len(TAIL_W) - 2)
    return lerp(TAIL_W[i], TAIL_W[i + 1], x - i)


def _tail(p):
    t = (p["tail"] + 1.0) / 2.0
    spine = bezier(*lerp_pts(TAIL_IN, TAIL_OUT, t), n=40)

    def edge(u, sign, extra=0.0, corner=False):
        pt, tan = along(spine, u)
        h = (_tail_w(u) / 2.0 + extra) * sign
        xy = (pt[0] - tan[1] * h, pt[1] + tan[0] * h)
        return xy + ("c",) if corner else xy

    root, rtan = along(spine, 0.0)
    tip, ttan = along(spine, 1.0)
    outline = [(root[0] - rtan[0] * 9, root[1] - rtan[1] * 9)]
    # outer edge, root to tip, with two fur points leaning towards the tip
    outline += [edge(u, 1) for u in (0.0, 0.12, 0.26, 0.42, 0.56)]
    outline += [edge(0.70, 1, 6.0, True), edge(0.69, 1, -2.0, True), edge(0.79, 1)]
    outline += [edge(0.905, 1, 5.5, True), edge(0.895, 1, -2.5, True), edge(0.96, 1)]
    outline.append((tip[0] + ttan[0] * 17, tip[1] + ttan[1] * 17, "c"))
    # inner edge, tip back to root, one fur point
    outline += [edge(0.95, -1), edge(0.84, -1, -2.5, True), edge(0.85, -1, 5.0, True), edge(0.72, -1)]
    outline += [edge(u, -1) for u in (0.58, 0.42, 0.26, 0.12, 0.0)]
    d = smooth(outline)
    shape = path(d, fill=GOLD_D)
    lit = path(d, transform=translate(-4.5, -6.0))               # everything but a crescent on the underside
    brush = band(spine, _tail_w, 0.55, 1.35, zig=7.0, teeth=4, over=16.0)
    marks = [
        clip(lit, path(d, fill=GOLD)),
        path(brush, fill=BROWN_SH),                              # MH5: dark brown-gold brush end
        clip(lit, path(brush, fill=BROWN)),
    ]
    tf = scale(-1, 1) if p["tail_side"] < 0 else None
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, marks)), transform=tf)


# ------------------------------------------------------------------ extras

SPARKLES = {      # kept clear of the raised paws and of the tail tip
    1: [(-134, 168, 14, SKY), (140, 204, 10, GOLD_D)],
    2: [(-142, 204, 10, GOLD_D), (136, 162, 15, SKY), (-112, 128, 8, SKY)],
    3: [(-128, 150, 11, SKY), (142, 168, 11, GOLD_D), (-146, 212, 12, GOLD_D), (118, 122, 8, SKY)],
}


def _extras(p):
    out = []
    for (x, y, r, col) in SPARKLES.get(int(p["sparkles"] or 0), []):
        out.append(sparkle(x, y, r, fill=col, ink=INK))
    if p["zzz"] is not None:
        out.append(zzz(6, 150, size=19, fill=SKY, ink=INK, drift=float(p["zzz"])))
    return out


# ------------------------------------------------------------------ draw

def draw(pose_in=None, guide=False):
    """One frame of Duskie as a complete SVG document (512 x 512 viewBox, feet at 92 %)."""
    p = _p(pose_in)
    front, behind = [], []
    for side in (-1, 1):
        s_, e_, w_ = _arm_points(side, p["arm_l"] if side < 0 else p["arm_r"], p["bob"])
        top = w_[1] + (w_[1] - e_[1]) / L2 * 28.0          # how high the paw reaches
        (front if min(top, w_[1]) < 294 else behind).append(_arm(side, p))
    parts = [_tail(p), _body(p), _bandana(p), behind, _head(p), front]
    sq = p["squash"]
    figure = g(parts, transform="%s %s %s %s %s" % (
        translate(CX, -p["hop"]), translate(0, BASELINE), rotate(p["sway"]),
        scale(1 + sq * 0.55, 1 - sq), translate(0, -BASELINE)))
    extras = g(_extras(p), transform=translate(CX, 0))
    return sticker(figure, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 5)

REST = pose()                       # the neutral stand: relaxed eyes, easy closed grin, every default


def _idle():
    frames = []
    n = 8
    for i in range(n):
        breath = cycle(i, n)
        frames.append(pose(REST,
                           squash=0.010 * breath, bob=1.2 * breath,
                           tail=0.15 + 0.55 * cycle(i, n, phase=0.35),
                           ear_l=-6.0 if i == 2 else (-2.5 if i == 3 else 0.0)))   # Nova flicks on 5 and 6
    return frames


def _blink():
    return [pose(REST, lid=0.72), pose(REST, eyes="closed"), pose(REST, lid=0.62)]


def _talk():
    return [pose(REST, mouth="open_s", nod=0.5), pose(REST, mouth="open_l", nod=1.5, ear_l=-2, ear_r=-2),
            pose(REST, mouth="open_s", nod=0.5, tail=0.35), pose(REST, mouth="smile", tail=0.35)]


def _happy():
    up = (104.0, 146.0)
    mid = (70.0, 118.0)
    base = dict(eyes="happy", mouth="grin", hand_l="open", hand_r="open")
    return [
        pose(REST, squash=0.05, bob=2, arm_l=mid, arm_r=mid, ear_l=4, ear_r=4, tail=0.2, **base),
        pose(REST, squash=-0.02, hop=7, arm_l=up, arm_r=up, ear_l=-4, ear_r=-4, tail=0.9, sparkles=1, **base),
        pose(REST, squash=-0.012, hop=12, arm_l=up, arm_r=up, ear_l=-5, ear_r=-5, tail=0.3, sparkles=2, **base),
        pose(REST, squash=0.0, hop=7, arm_l=up, arm_r=up, ear_l=-2, ear_r=-2, tail=1.0, sparkles=3, **base),
        pose(REST, squash=0.055, bob=2, arm_l=mid, arm_r=mid, ear_l=6, ear_r=6, tail=0.3, sparkles=2, **base),
        pose(REST, squash=0.0, arm_l=mid, arm_r=mid, ear_l=0, ear_r=0, tail=0.8, sparkles=1, **base),
    ]


def _sleep():
    base = pose(REST, eyes="closed", mouth="smile", tilt=7.0, nod=7.0, ear_l=22.0, ear_r=28.0, tail=-1.0,
                arm_l=(8.0, 3.0), arm_r=(8.0, 3.0))
    return [pose(base, squash=0.012, zzz=0.0), pose(base, squash=0.028, bob=1.5, zzz=0.3, nod=8.5),
            pose(base, squash=0.012, zzz=0.6, mouth="open_s"),
            pose(base, squash=-0.004, bob=-1.0, zzz=0.9, nod=6.0, mouth="open_s")]


def _wave():
    base = dict(eyes="open", mouth="grin", hand_l="open", tail=0.7)
    lo, hi = (100.0, 112.0), (100.0, 152.0)
    return [
        pose(REST, arm_l=(62.0, 96.0), eyes="open", mouth="open_s", hand_l="open", tail=0.3),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-3, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-5, **base),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-3, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-5, **base),
        pose(REST, arm_l=(62.0, 96.0), mouth="smile", hand_l="open", tail=0.3),
    ]


def _special():
    """The big happy tail wag: the brush swings right across behind him and back, with a little bounce."""
    paws = (38.0, -146.0)           # excited paws tucked up under his chin
    base = dict(arm_l=paws, arm_r=paws, mouth="pant", eyes="happy")
    return [
        pose(REST, squash=0.045, bob=2, tail=1.0, eyes="open", mouth="grin", arm_l=(24.0, 60.0),
             arm_r=(24.0, 60.0), ear_l=-4, ear_r=-4),
        pose(REST, hop=5, squash=-0.015, tail=-1.0, sway=-1.0, ear_l=-5, ear_r=-5, **base),
        pose(REST, hop=9, squash=-0.01, tail=-1.0, tail_side=-1, sway=1.0, ear_l=-3, ear_r=-3, sparkles=1,
             **base),
        pose(REST, hop=5, tail=1.25, tail_side=-1, sway=2.5, ear_l=2, ear_r=2, sparkles=1, **base),
        pose(REST, squash=0.035, bob=1.5, tail=-1.0, tail_side=-1, sway=1.0, ear_l=5, ear_r=5, sparkles=2,
             **base),
        pose(REST, hop=5, squash=-0.015, tail=-1.0, sway=-1.0, ear_l=-4, ear_r=-4, sparkles=2, **base),
        pose(REST, hop=8, squash=-0.01, tail=1.25, sway=-2.5, ear_l=-5, ear_r=-5, sparkles=3, **base),
        pose(REST, squash=0.03, bob=1.5, tail=1.1, ear_l=3, ear_r=3, sparkles=1, **base),
    ]


ANIMS = {
    "idle": anim(_idle(), fps=6, loop=True),
    "blink": anim(_blink(), fps=12, loop=False),
    "talk": anim(_talk(), fps=8, loop=True),
    "happy": anim(_happy(), fps=10, loop=False),
    "sleep": anim(_sleep(), fps=2, loop=True),
    "wave": anim(_wave(), fps=8, loop=False),
    "look_left": anim([pose(REST, look=(-1.0, 0.0), tilt=-2.0, ear_l=-3.0)], fps=1, loop=False),
    "look_right": anim([pose(REST, look=(1.0, 0.0), tilt=2.0, ear_r=-3.0)], fps=1, loop=False),
    "special": anim(_special(), fps=10, loop=False),
}

#: the 512 px still: "hey, you two" - a raised paw (black pads), the easy grin, a sparkle
PORTRAIT = pose(REST, big=True, mouth="grin", arm_l=(100.0, 144.0), hand_l="open", tilt=-3.0, tail=0.9,
                sparkles=1, ear_l=-3.0)
