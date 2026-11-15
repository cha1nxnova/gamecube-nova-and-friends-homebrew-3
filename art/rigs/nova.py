"""NOVA the serval: the reference rig.  Read this one before writing another.

House style: chibi die-cut sticker, front-facing, in the orange smiley tee.  Canon is docs/CHARACTERS.md;
every must-have on that list has a numbered comment here (``# MH3`` = must-have 3) so it is easy to check.

Coordinates: the body is drawn around x = 0 and moved to the canvas centre line at the end; y is canvas y
(feet on ``BASELINE``).  The head is drawn in its own frame (origin at the middle of the skull) so it can
bob and tilt.  "l" / "r" always mean *screen* left / right.
"""
from __future__ import annotations

import math

from lib2d import (BASELINE, CX, anim, band, bezier, blob, capsule, circle, clip, cycle, detail, ellipse,
                   g, lerp, lerp_pts, line, mix, outlined, path, polar, poly, pose, ribbon, rotate, scale,
                   smooth, sparkle, sticker, sym, top_y, translate, tween, zzz)

CHAR_ID = "nova"
HEIGHT = 1.0          # the tallest of the cast: ear tips at top_y(1.0)

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Nova)
NAVY = "#2b2d42"      # fur, main
INK = "#1b1c30"       # fur shadow / ink line
FUR_W = "#f1eff8"     # white markings
FUR_WS = "#d9d6ea"    # white, shaded
EAR_IN = "#e9e7f7"    # inner ear, light
EAR_PERI = "#a9b4e6"  # inner ear, periwinkle patch
IRIS = "#3d8fe0"
IRIS_HI = "#7cc4ff"
IRIS_LO = "#1f6fc4"
NOSE = "#e9cfe2"
PAD = "#f29abf"
TONGUE = "#ee7fa6"
TEE = "#e8894a"
TEE_SH = "#cf7137"
SMILEY = "#f7bd45"
SMILEY_F = "#c98a1e"
PLUM = "#2e2440"      # sleepy tee (wardrobe option)
MAGENTA = "#f52fd2"   # his lettering colour: sparkles
# derived tones (one soft shade per colour area)
NAVY_SH = mix(NAVY, INK, 0.6)
LID = mix(NAVY, EAR_PERI, 0.13)   # eyelids: fur with a breath of periwinkle so the half-lids read
MOUTH_IN = mix(INK, TONGUE, 0.3)
TONGUE_SH = mix(TONGUE, INK, 0.28)
PLUM_SH = mix(PLUM, INK, 0.5)
# the grilled cheese (prop palette: toast and cheese built from the smiley / gold tones)
BREAD = "#dba24f"
CRUST = "#b5772a"
BREAD_HI = "#edc27a"
CHEESE = "#f7bd45"
CHEESE_SH = "#e39a26"
CHEESE_INK = "#8a5a12"   # thin strings get a warm outline instead of the navy ink

W = 3.4               # ink line width (units outside each part)
HEAD_Y = 214.0        # canvas y of the head frame origin
NECK = (0.0, 62.0)    # head-frame pivot for tilt

# ------------------------------------------------------------------ pose parameters
DEFAULTS = {
    "ear_l": 0.0,          # extra ear rotation, degrees; + = droops outward, - = perks upright
    "ear_r": 0.0,
    "eyes": "half",        # "open" | "half" (his resting smug look) | "closed" | "happy"
    "lid": None,           # override how far the upper lids are down, 0 (wide) .. 1 (shut)
    "look": (0.0, 0.0),    # where the pupils point, each -1 .. 1 (x: screen left .. right, y: up .. down)
    "mouth": "w",          # "w" | "open_s" | "open_l" | "smile" | "blep" | "chew"
    "arm_l": (12.0, 4.0),  # (upper arm, forearm) angles from straight down, + = away from the body
    "arm_r": (12.0, 4.0),
    "hand_l": "paw",       # "paw" | "open" (palm + pink pads) | "peace" | "grip"
    "hand_r": "paw",
    "bob": 0.0,            # upper body + head down (+) or up (-), units
    "squash": 0.0,         # whole figure: + squashes onto the feet, - stretches
    "hop": 0.0,            # whole figure off the ground, units
    "tilt": 0.0,           # head tilt, degrees clockwise
    "nod": 0.0,            # head only, down (+)
    "tail": 0.0,           # tail swing, -1 (tucked in) .. 1 (swung out and up)
    "prop": None,          # None | "cheese" (whole sandwich in the left hand) | "cheese_bitten"
    "pull": 0.0,           # cheese pull, 0 (none) .. 1 (stretched thin); needs a cheese prop
    "string": False,       # a snapped cheese string hanging from the mouth
    "zzz": None,           # None, or 0..1 drift of the sleep Zs
    "sparkles": 0,         # 0..3 sparkle arrangement (0 = none)
    "tee": "orange",       # "orange" | "plum"
    "big": False,          # extra fine detail for large stills (third forehead dash, more ear hairs)
}

ARM_DOWN = (12.0, 4.0)


def _p(pose_in):
    p = dict(DEFAULTS)
    p.update(pose_in or {})
    return p


# ------------------------------------------------------------------ ears  (MH1)

EAR_OUT = [(-28, 16), (-38, -28), (-38, -72), (-27, -108), (-5, -132), (21, -129), (43, -104), (54, -64),
           (52, -22), (33, 16)]
EAR_INNER = [(-17, 12), (-27, -28), (-27, -70), (-18, -101), (-3, -119), (17, -116), (33, -96), (42, -63),
             (41, -22), (24, 12)]
EAR_PATCH = [(5, 14), (-2, -26), (4, -64), (16, -88), (29, -70), (34, -30), (27, 14)]
EAR_FLUFF = [(-22, 12), (-28, -36), (-15, -68, "c"), (-15, -45), (-1, -58, "c"), (-5, -31), (9, -37, "c"),
             (3, -10), (10, 12)]
EAR_AT = (46.0, -44.0)      # where an ear is rooted on the skull (head frame, screen-right ear)
EAR_SPREAD = 21.0           # resting outward lean, degrees


def _ear(side, extra, big):
    """One ear in the head frame.  ``side`` is -1 (screen left) or +1."""
    hairs = [((-25, -20), (-11, -66), (8, -98)), ((-23, -8), (0, -50), (24, -78)),
             ((-20, 4), (8, -28), (32, -48))]
    if big:
        hairs.append(((-26, -36), (-16, -84), (-2, -110)))
    inner = detail(
        path(blob(EAR_INNER), fill=EAR_IN),
        path(blob(EAR_PATCH), fill=EAR_PERI),
        path(smooth(EAR_FLUFF), fill=EAR_IN),
        [path("M%g %g Q%g %g %g %g" % (a + b + c), fill="none", stroke=INK, stroke_width=1.6,
              stroke_linecap="round") for a, b, c in hairs],
    )
    tf = "%s %s" % (translate(side * EAR_AT[0], EAR_AT[1]), rotate(side * (EAR_SPREAD + extra)))
    if side < 0:
        tf += " " + scale(-1, 1)
    return g(outlined(path(blob(EAR_OUT), fill=NAVY), ink=INK, width=W), inner, transform=tf)


# ------------------------------------------------------------------ face

EYE_X, EYE_Y, EYE_RX, EYE_RY = 42.0, 4.0, 21.5, 23.5


def _eye(side, p):
    """One eye in the head frame (MH5).  Returns paint-only nodes."""
    ex, ey, rx, ry = side * EYE_X, EYE_Y, EYE_RX, EYE_RY
    slant = -side * 6.0          # outer corners lifted a little: cat eyes
    state = p["eyes"]
    lx, ly = p["look"]
    if state in ("closed", "happy"):
        if state == "closed":    # relaxed, curved downwards
            d = "M%g %g Q%g %g %g %g" % (ex - 20, ey + 3, ex, ey + 18, ex + 20, ey + 3)
        else:                    # happy arcs
            d = "M%g %g Q%g %g %g %g" % (ex - 20, ey + 10, ex, ey - 13, ex + 20, ey + 10)
        return [path(d, fill="none", stroke=INK, stroke_width=10.0, stroke_linecap="round"),
                path(d, fill="none", stroke=FUR_W, stroke_width=4.6, stroke_linecap="round")]
    f = p["lid"]
    if f is None:
        f = 0.13 if state == "open" else 0.40
    lid_y = ey - ry + 2 * ry * f
    lean = 1.6 if state == "half" else 0.0       # smug: lids a touch lower towards the nose
    y_in, y_out = lid_y + lean, lid_y - lean
    low_y = ey + ry - (3.6 if state == "half" else 0.0)          # lower lid nudged up: pleased with himself
    eye_shape = ellipse(ex, ey, rx, ry, rot=slant)
    # the visible opening: below the upper lid, above the lower lid
    left_y, right_y = (y_out, y_in) if side > 0 else (y_in, y_out)
    opening = path("M%g %g L%g %g L%g %g Q%g %g %g %gZ" % (
        ex - 34, left_y, ex + 34, right_y, ex + 34, low_y, ex, low_y + (5.0 if state == "half" else 0.0),
        ex - 34, low_y))
    ix, iy = ex + lx * 7.0, ey + 4.0 + ly * 4.5
    iris = circle(ix, iy, 18.2)
    inside = [
        ellipse(ex, ey, rx + 3, ry + 3, fill=FUR_W),
        clip(iris,
             circle(ix, iy, 19.0, fill=IRIS),
             circle(ix, iy + 15.5, 18.2, fill=IRIS_LO),
             circle(ix, iy, 12.0, fill="none", stroke=IRIS_HI, stroke_width=3.0)),
        ellipse(ix, iy + 0.5, 7.4, 9.3, fill=INK),
        circle(ix - 6.6, iy - 5.2, 5.0, fill="#ffffff"),
        circle(ix + 6.4, iy + 7.8, 2.3, fill="#ffffff"),
    ]
    x_in, x_out = ex - side * (rx + 1.0), ex + side * (rx + 4.5)
    lash = path("M%g %g Q%g %g %g %g" % (x_in, y_in, ex, lid_y - 1.0, x_out, y_out), fill="none",
                stroke=INK, stroke_width=5.2, stroke_linecap="round")
    return [
        ellipse(ex, ey, rx + 2.6, ry + 2.6, rot=slant, fill=INK),
        ellipse(ex, ey, rx, ry, rot=slant, fill=LID),
        clip(eye_shape, clip(opening, inside)),
        clip(ellipse(ex, ey, rx + 5.5, ry + 5.5, rot=slant), lash),
    ]


MOUTH_W = "M-17.5 45 C-17 53 -4.5 55.5 0 47.5 C4.5 55.5 17 53 17.5 45"
MOUTH_AT = "translate(0 51) scale(1.18) translate(0 -47)"     # where the mouth sits under the nose
# name -> (cavity path or None, tongue (cx, cy, rx, ry) or None, how far the jaw drops)
MOUTHS = {
    "w": (None, None, 0.0),
    "chew": (None, None, 0.0),
    "blep": (None, None, 0.0),
    "open_s": ("M-8.5 52.4 C-5 54 -2 52 0 47.5 C2 52 5 54 8.5 52.4 C9 58 5 62 0 62 C-5 62 -9 58 -8.5 52.4Z",
               (0, 61.5, 5.5, 3.6), 2.0),
    "open_l": ("M-11 51.8 C-6 54.5 -2 52 0 47.5 C2 52 6 54.5 11 51.8 C12 60 7 66.5 0 66.5 "
               "C-7 66.5 -12 60 -11 51.8Z", (0, 65.5, 7.5, 5.0), 6.0),
    "smile": ("M-15.5 49.5 C-10 55 -3 53.5 0 47.5 C3 53.5 10 55 15.5 49.5 C16 60 8 66.5 0 66.5 "
              "C-8 66.5 -16 60 -15.5 49.5Z", (0, 66, 9.0, 5.5), 5.0),
}


def _mouth(p):
    name = p["mouth"]
    cavity, tongue, _ = MOUTHS[name]
    out = []
    if cavity:
        shape = path(cavity)
        out.append(path(cavity, fill=MOUTH_IN, stroke=INK, stroke_width=2.8, stroke_linejoin="round"))
        out.append(clip(shape, ellipse(tongue[0], tongue[1], tongue[2], tongue[3], fill=TONGUE)))
    if name == "blep":           # MH5: tongue out
        t = blob([(-5.8, 50.5), (-6.4, 57.5), (0, 64), (6.4, 57.5), (5.8, 50.5), (0, 49)])
        out.append(path(t, fill=TONGUE, stroke=INK, stroke_width=2.5, stroke_linejoin="round"))
        out.append(line(0, 54, 0, 59.5, stroke=TONGUE_SH, stroke_width=1.7))
    w = MOUTH_W
    if name == "chew":           # cheeks full: the "w" flattens and widens
        w = "M-19 46.5 C-16 52 -5 54 0 48.5 C5 54 16 52 19 46.5"
    out.append(path(w, fill="none", stroke=INK, stroke_width=2.8, stroke_linecap="round",
                    stroke_linejoin="round"))
    out.append(line(0, 41.5, 0, 47.5 if name != "chew" else 48.5, stroke=INK, stroke_width=2.4))
    return g(out, transform=MOUTH_AT)


def _head(p):
    jaw = MOUTHS[p["mouth"]][2]
    half = [(0, -64), (38, -62), (72, -46), (91, -19), (97, 3), (119, 13, "c"), (104, 25), (114, 41, "c"),
            (97, 50), (71, 64 + jaw * 0.5), (36, 73 + jaw), (0, 76 + jaw)]
    skull = path(blob(sym(half)), fill=NAVY)
    # MH2: white lower face; the boundary runs just under the eyes and out into the cheek tufts
    lower = blob(sym([(0, 38), (13, 35.5), (26, 33.5), (44, 33), (64, 27.5), (82, 16), (100, -2), (130, -14),
                      (140, 46), (96, 108), (0, 114)]))
    chin_shade = blob(sym([(0, 72 + jaw), (34, 69.5 + jaw), (68, 61 + jaw * 0.5), (92, 49), (106, 44),
                           (120, 66), (64, 100), (0, 104)]))
    marks = [
        path(lower, fill=FUR_W),
        path(chin_shade, fill=FUR_WS),
        # MH3: forehead dashes above the inner corner of each eye
        line(-23, -47, -19.5, -27, stroke=FUR_W, stroke_width=6.8),
        line(23, -47, 19.5, -27, stroke=FUR_W, stroke_width=6.8),
        p["big"] and line(0, -48, 0, -38, stroke=FUR_W, stroke_width=5.0),
        # MH4: freckles at the outer corner of each eye
        [[circle(s * 69.5, -6, 2.5, fill=FUR_W), circle(s * 75.5, 2.5, 2.9, fill=FUR_W),
          circle(s * 71.5, 11, 2.2, fill=FUR_W)] for s in (-1, 1)],
    ]
    nose = blob([(-10.5, 34.8), (0, 33.4), (10.5, 34.8), (7.2, 41.6), (0, 46.2), (-7.2, 41.6)])
    whiskers = []
    for s in (-1, 1):
        for (x0, y0, x1, y1, bend) in ((27, 48, 112, 30, -5), (28, 52.5, 116, 47, -2), (26, 57, 88, 65, 2)):
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0 + bend
            whiskers.append(path("M%g %g Q%g %g %g %g" % (s * x0, y0, s * mx, my, s * x1, y1), fill="none",
                                 stroke=INK, stroke_width=1.7, stroke_linecap="round"))
    face = detail(
        clip(skull, marks),
        _eye(-1, p), _eye(1, p),
        _mouth(p),
        path(nose, fill=NOSE, stroke=INK, stroke_width=2.5, stroke_linejoin="round"),
        ellipse(-3.4, 37, 3.0, 1.4, fill="#ffffff"),
        whiskers,
    )
    hy = HEAD_Y + p["bob"] + p["nod"]
    tf = "%s %s" % (translate(0, hy), rotate(p["tilt"], NECK[0], NECK[1]))
    return g(_ear(-1, p["ear_l"], p["big"]), _ear(1, p["ear_r"], p["big"]),
             outlined(skull, ink=INK, width=W), face, transform=tf)


def _head_pt(p, x, y):
    """A head-frame point in body coordinates (for props that touch the face)."""
    hy = HEAD_Y + p["bob"] + p["nod"]
    r = math.radians(p["tilt"])
    dx, dy = x - NECK[0], y - NECK[1]
    return (NECK[0] + dx * math.cos(r) - dy * math.sin(r), hy + NECK[1] + dx * math.sin(r) + dy * math.cos(r))


# ------------------------------------------------------------------ body, legs, tee

BODY_HALF = [(0, 262), (17, 262, "c"), (18, 284), (36, 291), (48, 303), (47, 345), (46, 392), (47, 420),
             (43, 448), (43, 464, "c"), (12, 464, "c"), (11, 440), (7, 421), (0, 409, "c")]
FOOT = [(3, 462), (7, 452.5), (26, 449), (45, 452.5), (53, 462), (49, 470.2), (28, 471.6), (7, 470.2)]


def _mx(points):
    return [(-pt[0],) + tuple(pt[1:]) for pt in points]


def _lower(p):
    """Legs and feet (planted) plus the torso under the tee."""
    body = path(blob(sym(BODY_HALF)), fill=NAVY)
    feet = [path(blob(FOOT), fill=FUR_W), path(blob(_mx(FOOT)), fill=FUR_W)]     # MH8: white toes
    marks = [
        # hem shadow and one soft shade down the screen-right side of each leg
        path(poly([(-60, 386), (60, 386), (60, 401), (0, 404), (-60, 401)]), fill=NAVY_SH),
        # MH6: the bib runs down the belly; its point shows below the tee hem
        path(smooth([(-11, 384), (11, 384), (6, 398), (0, 407, "c"), (-6, 398)]), fill=FUR_W),
        # MH8: oval spots on hips and thighs, short dashes on the shins
        ellipse(37, 411, 5.6, 9.6, rot=-16, fill=FUR_W), ellipse(-37, 411, 5.6, 9.6, rot=16, fill=FUR_W),
        ellipse(23, 425.5, 4.2, 7.0, rot=14, fill=FUR_W), ellipse(-22, 426.5, 4.4, 6.6, rot=-12, fill=FUR_W),
        line(17, 439.5, 27, 437.5, stroke=FUR_W, stroke_width=4.2),
        line(18.5, 447, 27, 445.5, stroke=FUR_W, stroke_width=3.6),
        line(-17, 439.5, -27, 437.5, stroke=FUR_W, stroke_width=4.2),
        line(-18.5, 447, -27, 445.5, stroke=FUR_W, stroke_width=3.6),
    ]
    toes = [line(s * x, 464.5, s * x, 470.5, stroke=INK, stroke_width=2.2)
            for s in (-1, 1) for x in (20.5, 35.5)]
    foot_shade = [path(blob([(s * 8, 468), (s * 28, 469.5), (s * 49, 467), (s * 50, 474), (s * 8, 474)]),
                       fill=FUR_WS) for s in (-1, 1)]
    return g(outlined(body, feet, ink=INK, width=W),
             detail(clip(body, marks), clip(feet, foot_shade), toes))


def _torso(p):
    """Neck, chest marks and the tee; moves with ``bob``."""
    tee_col, tee_sh = (TEE, TEE_SH) if p["tee"] != "plum" else (PLUM, PLUM_SH)
    chest = path(blob(sym([(0, 262), (17, 262, "c"), (18, 284), (36, 291), (48, 303), (47, 345), (40, 380),
                           (0, 384)])), fill=NAVY)
    marks = [
        path(poly([(-30, 262), (30, 262), (30, 286), (0, 291), (-30, 286)]), fill=NAVY_SH),  # under the chin
        line(-9, 294.5, 9, 294.5, stroke=FUR_W, stroke_width=5.2),                         # MH6: neck dash
        # MH6: heart-shaped bib, its two lobes peeking over the collar
        path("M0 317 C-4 305 -23 302 -26 315 L-26 345 L26 345 L26 315 C23 302 4 305 0 317Z", fill=FUR_W),
    ]
    tee_half = [(0, 327), (15, 321), (28, 307), (36, 288.5, "c"), (54, 299, "c"), (54, 340),
                (57, 393, "c"), (29, 397.5), (0, 398.5)]
    tee = path(smooth(sym(tee_half)), fill=tee_col)
    collar = "M-36 288.5 C-29 306 -15 321 0 327 C15 321 29 306 36 288.5"
    smiley = [
        circle(0, 362, 23.5, fill=SMILEY),
        ellipse(-8.4, 355.5, 2.9, 5.0, fill=SMILEY_F), ellipse(8.4, 355.5, 2.9, 5.0, fill=SMILEY_F),
        path("M-13 365 Q0 380 13 365", fill="none", stroke=SMILEY_F, stroke_width=3.6,
             stroke_linecap="round"),
    ]
    tee_marks = [
        path(blob([(40, 296), (60, 300), (62, 400), (44, 400), (47, 345)]), fill=tee_sh),      # side shade
        path(collar, fill="none", stroke=tee_sh, stroke_width=7.0, transform=translate(0, 3.6)),
        smiley,
    ]
    return g(outlined(chest, ink=INK, width=W), detail(clip(chest, marks)),
             outlined(tee, ink=INK, width=W), detail(clip(tee, tee_marks)),
             transform=translate(0, p["bob"]))


# ------------------------------------------------------------------ arms and hands  (MH7)

L1, L2 = 45.0, 31.0     # upper arm, forearm lengths


def _arm_points(side, angles, bob):
    a1, a2 = math.radians(angles[0]), math.radians(angles[1])
    s = (side * 50.0, 303.0 + bob)
    e = (s[0] + side * math.sin(a1) * L1, s[1] + math.cos(a1) * L1)
    w = (e[0] + side * math.sin(a2) * L2, e[1] + math.cos(a2) * L2)
    return s, e, w


def _hand(kind, side):
    """Hand shapes in the hand frame: wrist at the origin, fingers towards -y.  Returns (shapes, paint)."""
    if kind == "open":       # palm towards us, pink pads
        shapes = [circle(0, -12, 13.6, fill=FUR_W)]
        fingers = [(-11.5, -22.5), (-4.2, -28.5), (4.4, -28.5), (11.6, -22.5)]
        shapes += [circle(x, y, 5.9, fill=FUR_W) for x, y in fingers]
        shapes.append(circle(-side * 15.5, -9.5, 5.4, fill=FUR_W))            # thumb, body side
        paint = [ellipse(0, -11.5, 7.6, 6.0, fill=PAD)] + [circle(x, y - 0.6, 2.9, fill=PAD)
                                                           for x, y in fingers]
        return shapes, paint
    if kind == "peace":      # two fingers up
        shapes = [circle(0, -11, 13.2, fill=FUR_W),
                  path(capsule((-4.5, -17), (-10.5, -37), 5.4, 5.0), fill=FUR_W),
                  path(capsule((4.5, -17), (10.5, -37), 5.4, 5.0), fill=FUR_W)]
        paint = [circle(-10.3, -36.5, 2.7, fill=PAD), circle(10.3, -36.5, 2.7, fill=PAD),
                 path("M-9 -9 Q0 -3 9 -9", fill="none", stroke=INK, stroke_width=2.2, stroke_linecap="round"),
                 line(0, -19, 0, -14, stroke=INK, stroke_width=2.0)]
        return shapes, paint
    # "paw" and "grip": the back of a mitten paw
    shapes = [path(blob([(-10.5, 2), (-14.5, -10), (-11, -21.5), (0, -25.5), (11, -21.5), (14.5, -10),
                         (10.5, 2)]), fill=FUR_W)]
    paint = [line(-4.6, -24.5, -4.6, -17.5, stroke=INK, stroke_width=2.1),
             line(4.6, -24.5, 4.6, -17.5, stroke=INK, stroke_width=2.1)]
    return shapes, paint


def _arm(side, p):
    angles = p["arm_l"] if side < 0 else p["arm_r"]
    kind = p["hand_l"] if side < 0 else p["hand_r"]
    tee_col = TEE if p["tee"] != "plum" else PLUM
    s, e, w = _arm_points(side, angles, p["bob"])
    d1 = ((e[0] - s[0]) / L1, (e[1] - s[1]) / L1)
    d2 = ((w[0] - e[0]) / L2, (w[1] - e[1]) / L2)
    n2 = (-d2[1], d2[0])
    upper_d = capsule(s, e, 12.6, 12.0)
    fore_d = capsule(e, w, 12.0, 11.4)
    shapes, paint = _hand(kind, side)
    htf = "%s %s" % (translate(w[0], w[1]), rotate(math.degrees(math.atan2(d2[0], -d2[1]))))
    # white "long glove": forearm and hand, with a jagged upper edge at the elbow
    zig = []
    for i in range(7):
        u = -1.0 + i / 3.0
        off = 3.0 + (4.2 if i % 2 else -2.2)
        zig.append((e[0] + n2[0] * 16 * u + d2[0] * off, e[1] + n2[1] * 16 * u + d2[1] * off))
    far = [(w[0] + n2[0] * 18 + d2[0] * 8, w[1] + n2[1] * 18 + d2[1] * 8),
           (w[0] - n2[0] * 18 + d2[0] * 8, w[1] - n2[1] * 18 + d2[1] * 8)]
    glove = path(poly(zig + far), fill=FUR_W)
    # one white oval band across the navy upper arm
    b = (lerp(s[0], e[0], 0.66), lerp(s[1], e[1], 0.66))
    band_rot = math.degrees(math.atan2(d1[1], d1[0])) - 90.0
    arm = g(
        outlined(path(upper_d, fill=NAVY), path(fore_d, fill=NAVY), g(shapes, transform=htf),
                 ink=INK, width=W),
        detail(clip(path(fore_d), glove),
               clip(path(upper_d), ellipse(b[0], b[1], 15.0, 5.0, rot=band_rot, fill=FUR_W)),
               g(paint, transform=htf)),
    )
    # short sleeve
    n1 = (-d1[1], d1[0])
    def sp(along_d, across):
        return (s[0] + d1[0] * along_d + n1[0] * across, s[1] + d1[1] * along_d + n1[1] * across)
    sleeve = path(smooth([sp(-10, -13), sp(-10, 13), sp(8, 16.5), sp(21, 17.5, ) + ("c",),
                          sp(21, -17.5) + ("c",), sp(8, -16.5)]), fill=tee_col)
    return g(arm, outlined(sleeve, ink=INK, width=W))


# ------------------------------------------------------------------ tail  (MH9)

TAIL_IN = [(24, 420), (78, 474), (138, 462), (128, 372)]
TAIL_OUT = [(24, 420), (92, 468), (176, 436), (158, 338)]


def _tail(p):
    t = (p["tail"] + 1.0) / 2.0
    spine = bezier(*lerp_pts(TAIL_IN, TAIL_OUT, t), n=40)
    width = [20, 18, 17, 16, 15]
    shape = path(ribbon(spine, width), fill=NAVY)
    bands = [path(band(spine, width, a, b, zig=4.0, teeth=2), fill=FUR_W)
             for a, b in ((0.3, 0.4), (0.53, 0.62), (0.74, 0.81), (0.915, 1.2))]
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, bands)))


# ------------------------------------------------------------------ the grilled cheese

def _cheese_frame(p):
    """Where the sandwich is: (origin, rotation in degrees) from the screen-left hand."""
    s, e, w = _arm_points(-1, p["arm_l"], p["bob"])
    d2 = ((w[0] - e[0]) / L2, (w[1] - e[1]) / L2)
    return w, math.degrees(math.atan2(d2[0], -d2[1]))


SANDWICH = [(-27, -6), (29, -13), (5, -67)]          # hand frame: crust corners, then the tip he bites


def _cheese(p):
    """Grilled cheese half in the left hand.  Drawn in the hand frame, then placed."""
    bitten = p["prop"] == "cheese_bitten"
    (ox, oy), deg = _cheese_frame(p)
    a, b, c = SANDWICH
    if bitten:
        # the tip is gone: a scalloped bite edge
        top = [(-11.5, -38, "c"), (-6, -41), (-1.5, -36.5, "c"), (4.5, -40.5), (9.5, -35.5, "c"),
               (15, -39.5), (19.5, -33.5, "c")]
    else:
        top = [(1, -62), (5, -67), (9.5, -62)]
    front = [(-27, -6, "c")] + top + [(29, -13, "c")]
    back_shift = (6.5, 5.0)
    back = [(x + back_shift[0], y + back_shift[1]) + tuple(r) for (x, y, *r) in front]
    cheese_edge = [(x + 3.2, y + 2.6) + tuple(r) for (x, y, *r) in front]
    drips = [
        blob([(14, -9), (20, -10), (21, 2), (17.5, 7), (14, 2)]),
        blob([(-12, -5), (-5, -6), (-5.5, 3), (-9, 6), (-12.5, 2)]),
    ]
    shapes = [path(smooth(back, tension=0.6), fill=CRUST),
              path(smooth(cheese_edge, tension=0.6), fill=CHEESE),
              [path(d, fill=CHEESE) for d in drips],
              path(smooth(front, tension=0.6), fill=BREAD)]
    front_shape = path(smooth(front, tension=0.6))
    paint = [
        clip(front_shape,
             path(poly([(-40, 0), (40, -10), (40, -19), (-40, -11)]), fill=CRUST),          # bottom crust
             line(-13, -24, 17, -29, stroke=BREAD_HI, stroke_width=3.2),
             line(-7, -36, 11, -39, stroke=BREAD_HI, stroke_width=3.2),
             (not bitten) and line(-1, -49, 7, -50.5, stroke=BREAD_HI, stroke_width=3.0)),
    ]
    if bitten:
        paint.append(path(smooth([(-11.5, -38), (-6, -41), (-1.5, -36.5), (4.5, -40.5), (9.5, -35.5),
                                  (15, -39.5), (19.5, -33.5)], closed=False), fill="none", stroke=CHEESE,
                          stroke_width=4.6, stroke_linecap="round", transform=translate(1.5, 1.5)))
    tf = "%s %s" % (translate(ox, oy), rotate(deg))
    return g(outlined(shapes, ink=INK, width=2.8), detail(paint), transform=tf)


def _pull(p):
    """Cheese strings from the bite edge to his mouth (``pull`` 0..1) and/or a snapped string."""
    out = []
    (ox, oy), deg = _cheese_frame(p)
    r = math.radians(deg)
    mouth = _head_pt(p, -3, 52)
    k = p["pull"]
    if k > 0 and p["prop"]:
        for (bx, by, mx_, sag, wide) in ((-6, -40, -5.0, 0.9, 1.0), (9, -37, 1.5, 1.4, 0.8)):
            end = (ox + bx * math.cos(r) - by * math.sin(r), oy + bx * math.sin(r) + by * math.cos(r))
            start = (mouth[0] + mx_, mouth[1])
            mid = ((start[0] + end[0]) / 2.0, (start[1] + end[1]) / 2.0 + (6 + 16 * k) * sag)
            spine = bezier(start, mid, mid, end, n=18)
            thick = lerp(9.0, 7.0, k) * wide
            thin = lerp(7.0, 3.4, k) * wide
            out.append(outlined(path(ribbon(spine, [thick, thin, thin, thick * 1.1]), fill=CHEESE),
                                ink=CHEESE_INK, width=1.5))
    if p["string"]:
        start = (mouth[0] - 6.5, mouth[1] + 0.5)
        spine = bezier(start, (start[0] - 3, start[1] + 9), (start[0] + 1, start[1] + 15),
                       (start[0] - 2, start[1] + 23), n=12)
        out.append(outlined(path(ribbon(spine, [5.6, 3.6, 5.4]), fill=CHEESE), ink=CHEESE_INK, width=1.5))
    return out


# ------------------------------------------------------------------ extras

SPARKLES = {
    1: [(-128, 150, 15, MAGENTA), (136, 232, 10, SMILEY)],
    2: [(-136, 176, 11, SMILEY), (134, 196, 16, MAGENTA), (-118, 268, 8, MAGENTA)],
    3: [(-122, 132, 12, MAGENTA), (140, 160, 12, SMILEY), (-140, 236, 14, SMILEY), (128, 262, 9, MAGENTA)],
}


def _extras(p):
    out = []
    for (x, y, r, col) in SPARKLES.get(int(p["sparkles"] or 0), []):
        out.append(sparkle(x, y, r, fill=col, ink=INK))
    if p["zzz"] is not None:
        out.append(zzz(-6, 126, size=19, fill=EAR_PERI, ink=INK, drift=float(p["zzz"])))
    return out


# ------------------------------------------------------------------ draw

def draw(pose_in=None, guide=False):
    """One frame of Nova as a complete SVG document (512 x 512 viewBox, feet at 92 %)."""
    p = _p(pose_in)
    front, behind = [], []
    for side in (-1, 1):
        s_, e_, w_ = _arm_points(side, p["arm_l"] if side < 0 else p["arm_r"], p["bob"])
        has_prop = side < 0 and bool(p["prop"])
        reach = 67.0 if has_prop else 25.0                 # how far past the wrist the hand / sandwich goes
        top = w_[1] + (w_[1] - e_[1]) / L2 * reach
        nodes = [_cheese(p)] if has_prop else []           # the sandwich sits behind its hand
        nodes.append(_arm(side, p))
        (front if min(top, w_[1]) < 286 else behind).append(nodes)
    parts = [_tail(p), _lower(p), _torso(p), behind, _head(p), front, _pull(p)]
    sq = p["squash"]
    figure = g(parts, transform="%s %s %s" % (translate(CX, -p["hop"]),
                                              translate(0, BASELINE),
                                              scale(1 + sq * 0.55, 1 - sq)) + " " + translate(0, -BASELINE))
    extras = g(_extras(p), transform=translate(CX, 0))
    return sticker(figure, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 5)

REST = pose()                       # the neutral, smug stand: every default


def _idle():
    frames = []
    n = 8
    for i in range(n):
        breath = cycle(i, n)
        frames.append(pose(REST,
                           squash=0.010 * breath, bob=1.2 * breath,
                           tail=0.55 * cycle(i, n, phase=0.1),
                           ear_r=-5.0 if i == 5 else (-2.0 if i == 6 else 0.0)))
    return frames


def _blink():
    return [pose(REST, lid=0.72), pose(REST, eyes="closed"), pose(REST, lid=0.62)]


def _talk():
    return [pose(REST, mouth="open_s", nod=0.5), pose(REST, mouth="open_l", nod=1.5, ear_l=-2, ear_r=-2),
            pose(REST, mouth="open_s", nod=0.5, tail=0.3), pose(REST, mouth="w", tail=0.3)]


def _happy():
    up = (104.0, 146.0)
    mid = (70.0, 118.0)
    base = dict(eyes="happy", mouth="smile", hand_l="open", hand_r="open")
    return [
        pose(REST, squash=0.05, bob=2, arm_l=mid, arm_r=mid, ear_l=4, ear_r=4, tail=0.2, **base),
        pose(REST, squash=-0.02, hop=7, arm_l=up, arm_r=up, ear_l=-4, ear_r=-4, tail=0.8, sparkles=1, **base),
        pose(REST, squash=-0.012, hop=12, arm_l=up, arm_r=up, ear_l=-5, ear_r=-5, tail=1.0, sparkles=2, **base),
        pose(REST, squash=0.0, hop=7, arm_l=up, arm_r=up, ear_l=-2, ear_r=-2, tail=0.7, sparkles=3, **base),
        pose(REST, squash=0.055, bob=2, arm_l=mid, arm_r=mid, ear_l=6, ear_r=6, tail=0.1, sparkles=2, **base),
        pose(REST, squash=0.0, arm_l=mid, arm_r=mid, ear_l=0, ear_r=0, tail=0.4, sparkles=1, **base),
    ]


def _sleep():
    base = pose(REST, eyes="closed", mouth="w", tilt=7.0, nod=7.0, ear_l=24.0, ear_r=30.0, tail=-1.0,
                arm_l=(7.0, 2.0), arm_r=(7.0, 2.0))
    return [pose(base, squash=0.012, zzz=0.0), pose(base, squash=0.028, bob=1.5, zzz=0.3, nod=8.5),
            pose(base, squash=0.012, zzz=0.6, mouth="open_s"),
            pose(base, squash=-0.004, bob=-1.0, zzz=0.9, nod=6.0, mouth="open_s")]


def _wave():
    base = dict(eyes="open", mouth="smile", hand_l="open", tail=0.6)
    lo, hi = (100.0, 112.0), (100.0, 152.0)
    return [
        pose(REST, arm_l=(62.0, 96.0), eyes="open", mouth="open_s", hand_l="open", tail=0.3),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-3, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-5, **base),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-3, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-5, **base),
        pose(REST, arm_l=(62.0, 96.0), mouth="w", hand_l="open", tail=0.3),
    ]


def _special():
    low = (26.0, 118.0)       # sandwich held out at chest height
    bite = (68.0, 241.0)      # tip of the sandwich at his mouth

    def between(t):
        return (lerp(bite[0], low[0], t), lerp(bite[1], low[1], t))
    return [
        pose(REST, arm_l=low, prop="cheese", hand_l="grip", look=(-0.9, 0.5), mouth="blep", ear_l=-4,
             ear_r=-4, tail=0.5),
        pose(REST, arm_l=between(0.45), prop="cheese", hand_l="grip", look=(-0.7, 0.7), mouth="open_l",
             eyes="open", tail=0.8),
        pose(REST, arm_l=bite, prop="cheese", hand_l="grip", eyes="happy", mouth="open_l", nod=1.5, ear_l=5,
             ear_r=5, tail=1.0),
        pose(REST, arm_l=bite, prop="cheese", hand_l="grip", eyes="happy", mouth="open_s", nod=3.0,
             squash=0.02, ear_l=9, ear_r=9, tail=0.8),
        pose(REST, arm_l=between(0.3), prop="cheese_bitten", hand_l="grip", pull=0.2, mouth="chew",
             look=(-0.6, 0.8), tail=0.4),
        pose(REST, arm_l=between(0.65), prop="cheese_bitten", hand_l="grip", pull=0.6, mouth="chew",
             eyes="open", look=(-0.8, 0.6), ear_l=-6, ear_r=-6, tail=0.0),
        pose(REST, arm_l=between(1.0), prop="cheese_bitten", hand_l="grip", pull=1.0, mouth="chew",
             eyes="open", look=(-0.9, 0.5), ear_l=-8, ear_r=-8, tail=-0.3),
        pose(REST, arm_l=between(1.05), prop="cheese_bitten", hand_l="grip", string=True, eyes="happy",
             mouth="chew", sparkles=1, ear_l=3, ear_r=3, tail=0.7),
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
    "special": anim(_special(), fps=6, loop=False),
}

#: the 512 px still: peace sign, blep, a sparkle
PORTRAIT = pose(REST, big=True, mouth="blep", arm_l=(100.0, 142.0), hand_l="peace", tilt=-3.0, tail=0.8,
                sparkles=1, ear_l=-3.0)
