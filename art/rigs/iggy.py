"""IGGY the fennec fox: mascot #2, drawn to stand next to ``nova.py`` (read that rig first).

House style: chibi die-cut sticker, front-facing, in the default "emo-casual" outfit (black tee with one
periwinkle zigzag band, striped wristband, grey feather pendant over the shirt).  Canon is
docs/CHARACTERS.md; every must-have on Iggy's list has a numbered comment here (``# MH3`` = must-have 3).
``outfit="apron"`` puts the "KISS THE COOK" apron over the tee.

Coordinates follow Nova's rig: the body is drawn around x = 0 and moved to the canvas centre line at the
end; y is canvas y (feet on ``BASELINE``).  The head is drawn in its own frame (origin at the middle of the
skull) so it can bob and tilt.  "l" / "r" always mean *screen* left / right.

Iggy is 0.75 of Nova's height (MH10): the ear tips reach ``top_y(0.75)``.  The ears go *wide* instead of
tall, which is also what separates the two silhouettes at 96 px.
"""
from __future__ import annotations

import math

from lib2d import (BASELINE, CX, along, anim, band, bezier, blob, capsule, circle, clamp, clip, cycle, detail,
                   ellipse, g, lerp, lerp_pts, line, mix, outlined, path, poly, polyline, pose, rect, ribbon,
                   rotate, scale, smooth, sparkle, sticker, sym, top_y, translate, tween, zzz)

CHAR_ID = "iggy"
HEIGHT = 0.75         # about three-quarters of Nova (MH10): ear tips at top_y(0.75)

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Iggy)
FUR = "#d2b48c"       # fur, main (sand tan)
FUR_L = "#e6d3b3"     # fur, light (inner ear, muzzle)
FUR_SH = "#b89a70"    # fur, shadow
PERI = "#7582b5"      # markings (periwinkle)
PERI_D = "#5a6699"    # markings, dark
EYE = "#5aa04c"
EYE_HI = "#8ed07a"
NOSE = "#4a4648"
PAD = "#f7a8c4"       # paw pads, tongue
GLASS = "#1c1b22"     # glasses frames
TEE = "#24222b"
TEE_SH = "#15141b"
APRON = "#fbf7f0"
APRON_SH = "#e4dccd"
LETTER = "#d6457a"    # apron lettering
FEATHER = "#9aa0a8"
CORD = "#6f747c"
# derived tones (one soft shade per colour area)
INK = mix(FUR_SH, GLASS, 0.9)         # the ink line: the fur shadow taken almost all the way to the frames
EYE_LO = mix(EYE, INK, 0.36)
EYE_W = "#ffffff"
LID = mix(FUR, FUR_SH, 0.55)          # eyelids: a touch darker than the fur so the level lids read
EAR_DEEP = mix(FUR_L, FUR_SH, 0.55)   # the shade tone inside the ear
MOUTH_IN = mix(INK, PAD, 0.3)
TONGUE_SH = mix(PAD, INK, 0.28)
NOSE_HI = mix(NOSE, "#ffffff", 0.5)
FEATHER_SH = mix(FEATHER, CORD, 0.6)
GLINT = mix("#ffffff", PERI, 0.3)     # the pale-blue lens glint
# prop palette: the camcorder (greys from the nose / tee, a lens in the dark periwinkle, one red light)
CAM = "#4a4648"
CAM_D = "#24222b"
CAM_HI = mix(CAM, "#ffffff", 0.3)
REC = "#e8334a"
STEEL = "#9aa0a8"     # ladle (the feather grey)
STEEL_SH = "#6f747c"

W = 3.4               # ink line width (units outside each part): the same as Nova
HEAD_Y = 276.0        # canvas y of the head frame origin
HS = 0.94             # the head frame is drawn at Nova's scale, then shrunk a little: Iggy is the small one
NECK = (0.0, 54.0)    # head-frame pivot for tilt (in head-frame units)
WH = W / HS           # ink width inside the head frame, so the line weight on screen stays W

ARM_DOWN = (12.0, 4.0)

# ------------------------------------------------------------------ pose parameters
DEFAULTS = {
    "ear_l": 0.0,          # extra ear rotation, degrees; + = droops outward, - = perks upright
    "ear_r": 0.0,
    "eyes": "half",        # "open" | "half" (the deadpan resting look: level lids) | "closed" | "happy"
    "lid": None,           # override how far the upper lids are down, 0 (wide) .. 1 (shut)
    "look": (0.0, 0.0),    # where the pupils point, each -1 .. 1 (x: screen left .. right, y: up .. down)
    "mouth": "w",          # "w" (tiny smile + fang) | "open_s" | "open_l" | "smile" | "blep"
    "arm_l": ARM_DOWN,     # (upper arm, forearm) angles from straight down, + = away from the body
    "arm_r": ARM_DOWN,
    "hand_l": "paw",       # "paw" | "open" (palm + pink pads) | "point" (one finger up) | "grip"
    "hand_r": "paw",
    "bob": 0.0,            # upper body + head down (+) or up (-), units
    "squash": 0.0,         # whole figure: + squashes onto the feet, - stretches
    "hop": 0.0,            # whole figure off the ground, units
    "tilt": 0.0,           # head tilt, degrees clockwise
    "nod": 0.0,            # head only, down (+)
    "tail": 0.0,           # tail swing, -1 (tucked in) .. 1 (swung out and up)
    "glasses": 0.0,        # how far the glasses have slipped down the nose, units (they never come off)
    "glint": 0.0,          # lens glint, 0 (normal) .. 1 (both lenses flash white, with a sparkle)
    "prop": None,          # None | "camcorder" (screen-left hand) | "ladle" (screen-left hand)
    "rec": True,           # camcorder: is the red REC light lit
    "stir": 0.0,           # ladle: where it is in its stirring circle, turns (0 .. 1)
    "zzz": None,           # None, or 0..1 drift of the sleep Zs
    "sparkles": 0,         # 0..3 sparkle arrangement (0 = none)
    "outfit": "tee",       # "tee" (emo-casual default) | "apron" (KISS THE COOK over the tee)
    "big": False,          # extra fine detail for large stills (braided cord, feather barbs, more strands)
}


def _p(pose_in):
    p = dict(DEFAULTS)
    p.update(pose_in or {})
    return p


# ------------------------------------------------------------------ ears  (MH1)
# Screen-right ear in its own frame: root at the origin, tip towards -y, the side nearest the middle of the
# head is -x.  Wide at the base, straight-sided and pointed (Nova's are tall and round-tipped).

EAR_OUT = [(-32, 16), (-35, -18), (-28, -58), (-12, -100), (4, -127, "c"), (18, -100), (33, -60), (42, -24),
           (39, 16)]
EAR_INNER = [(-21, 16), (-24, -18), (-18, -54), (-6, -85), (4, -102, "c"), (13, -85), (24, -56), (32, -24),
             (29, 16)]
EAR_SHADE = [(-21, 16), (-24, -18), (-18, -54), (-6, -85), (4, -102, "c"), (4, -64), (-1, -26), (-3, 16)]
# tan fluff at the base: it also covers the periwinkle rim low on the outer side, as on the reference
EAR_FLUFF = [(-34, 22), (-27, 0), (-17, -24, "c"), (-11, -4), (2, -37, "c"), (8, -10), (22, -47, "c"),
             (27, -22), (38, -63, "c"), (50, -34), (50, 22)]
EAR_AT = (46.0, -33.0)      # where an ear is rooted on the skull (head frame, screen-right ear)
EAR_SPREAD = 38.0           # resting outward lean, degrees: fennec ears point out as much as up


def _ear(side, extra):
    """One ear in the head frame.  ``side`` is -1 (screen left) or +1."""
    outer = path(blob(EAR_OUT), fill=PERI)          # periwinkle back, seen as the rim and the tip
    inner = detail(clip(
        outer,
        path(blob(EAR_INNER), fill=FUR_L),
        path(blob(EAR_SHADE), fill=EAR_DEEP),
        path(smooth(EAR_FLUFF), fill=FUR),
    ))
    tf = "%s %s" % (translate(side * EAR_AT[0], EAR_AT[1]), rotate(side * (EAR_SPREAD + extra)))
    if side < 0:
        tf += " " + scale(-1, 1)
    return g(outlined(outer, ink=INK, width=WH), inner, transform=tf)


# ------------------------------------------------------------------ face

EYE_X, EYE_Y, EYE_RX, EYE_RY = 39.0, 8.0, 18.5, 20.5
GL_R = 30.5            # lens radius
GL_W = 5.0             # frame thickness: thin, but it has to survive 96 px


def _eye(side, p):
    """One eye in the head frame (MH4): the same construction as Nova's, green, with level lids."""
    ex, ey, rx, ry = side * EYE_X, EYE_Y, EYE_RX, EYE_RY
    slant = -side * 3.0
    state = p["eyes"]
    lx, ly = p["look"]
    if state in ("closed", "happy"):
        if state == "closed":    # relaxed, curved downwards
            d = "M%g %g Q%g %g %g %g" % (ex - 17, ey + 3, ex, ey + 16, ex + 17, ey + 3)
        else:                    # happy arcs
            d = "M%g %g Q%g %g %g %g" % (ex - 17, ey + 9, ex, ey - 11, ex + 17, ey + 9)
        return [path(d, fill="none", stroke=INK, stroke_width=5.4, stroke_linecap="round")]
    f = p["lid"]
    if f is None:
        f = 0.12 if state == "open" else 0.36
    lid_y = ey - ry + 2 * ry * f
    low_y = ey + ry
    eye_shape = ellipse(ex, ey, rx, ry, rot=slant)
    opening = rect(ex - 32, lid_y, 64, low_y + 8 - lid_y)
    ix, iy = ex + lx * 6.0, ey + 3.5 + ly * 4.0
    iris = circle(ix, iy, 15.6)
    inside = [
        ellipse(ex, ey, rx + 3, ry + 3, fill=EYE_W),
        clip(iris,
             circle(ix, iy, 16.4, fill=EYE),
             circle(ix, iy + 13.4, 15.6, fill=EYE_LO),
             circle(ix, iy, 10.3, fill="none", stroke=EYE_HI, stroke_width=2.6)),
        ellipse(ix, iy + 0.5, 6.3, 8.0, fill=INK),
        circle(ix - 5.6, iy - 4.5, 4.3, fill="#ffffff"),
        circle(ix + 5.5, iy + 6.7, 2.0, fill="#ffffff"),
    ]
    lash = line(ex - rx - 2.5, lid_y, ex + rx + 2.5, lid_y, stroke=INK, stroke_width=4.6)
    return [
        ellipse(ex, ey, rx + 2.4, ry + 2.4, rot=slant, fill=INK),
        ellipse(ex, ey, rx, ry, rot=slant, fill=LID),
        clip(eye_shape, clip(opening, inside)),
        clip(ellipse(ex, ey, rx + 4.6, ry + 4.6, rot=slant), lash),
    ]


def _glasses(p):
    """MH3: round, thin black frames.  Always drawn; ``glasses`` only slides them along the nose."""
    cy = EYE_Y + 0.5 + p["glasses"]
    k = clamp(float(p["glint"]))
    out = []
    for s in (-1, 1):
        cx = s * (EYE_X + 0.5)
        lens = circle(cx, cy, GL_R)
        out.append(circle(cx, cy, GL_R, fill="#ffffff", fill_opacity=lerp(0.25, 0.96, k)))
        streaks = [line(cx - 25, cy - 3, cx - 5, cy - 27, stroke=GLINT, stroke_width=4.4, stroke_linecap="butt"),
                   line(cx - 19, cy + 6, cx - 13, cy - 1.5, stroke=GLINT, stroke_width=3.0,
                        stroke_linecap="butt")]
        if k > 0:                # the flash: two broad bars right across the lens
            streaks = [line(cx - 34, cy + 10, cx + 6, cy - 36, stroke=GLINT, stroke_width=9.0 + 3.0 * k,
                            stroke_linecap="butt"),
                       line(cx - 20, cy + 26, cx + 30, cy - 30, stroke=GLINT, stroke_width=4.0 + 2.0 * k,
                            stroke_linecap="butt")]
        out.append(clip(lens, g(streaks, opacity=lerp(0.85, 1.0, k))))
        out.append(circle(cx, cy, GL_R, fill="none", stroke=GLASS, stroke_width=GL_W))
        # temple arm, running back to the ear
        out.append(line(s * (EYE_X + GL_R + 1.5), cy - 3.5, s * 80.5, cy - 9, stroke=GLASS,
                        stroke_width=GL_W - 0.8, stroke_linecap="butt"))
    bx = EYE_X + 0.5 - GL_R
    out.append(path("M%g %g Q0 %g %g %g" % (-bx - 0.5, cy - 4.5, cy - 12.5, bx + 0.5, cy - 4.5), fill="none",
                    stroke=GLASS, stroke_width=GL_W - 0.6, stroke_linecap="round"))
    if k >= 0.99:
        out.append(sparkle(EYE_X + 21, cy - 21, 12.5, fill="#ffffff", ink=INK, width=2.2))
    return detail(out)


MOUTH_W = "M-16 44.5 C-15 52.5 -4.5 54.5 0 47.5 C4.5 54.5 15 52.5 16 44.5"      # a small upturned fox "w"
MOUTH_AT = "translate(0 46.5) scale(0.95) translate(0 -47.5)"                   # where it sits under the nose
# name -> (cavity path or None, tongue (cx, cy, rx, ry) or None, how far the jaw drops)
MOUTHS = {
    "w": (None, None, 0.0),
    "blep": (None, None, 0.0),
    "open_s": ("M-8.5 52.4 C-5 54 -2 52 0 47.5 C2 52 5 54 8.5 52.4 C9 58 5 62 0 62 C-5 62 -9 58 -8.5 52.4Z",
               (0, 61.5, 5.5, 3.6), 2.0),
    "open_l": ("M-11 51.8 C-6 54.5 -2 52 0 47.5 C2 52 6 54.5 11 51.8 C12 60 7 66.5 0 66.5 "
               "C-7 66.5 -12 60 -11 51.8Z", (0, 65.5, 7.5, 5.0), 5.0),
    "smile": ("M-15.5 49.5 C-10 55 -3 53.5 0 47.5 C3 53.5 10 55 15.5 49.5 C16 60 8 66.5 0 66.5 "
              "C-8 66.5 -16 60 -15.5 49.5Z", (0, 66, 9.0, 5.5), 4.0),
}
FANG_STYLE = dict(fill="#ffffff", stroke=INK, stroke_width=1.9, stroke_linejoin="round")


def _mouth(p):
    name = p["mouth"]
    cavity, tongue, _ = MOUTHS[name]
    out = []
    if cavity:
        shape = path(cavity)
        out.append(path(cavity, fill=MOUTH_IN, stroke=INK, stroke_width=2.8, stroke_linejoin="round"))
        out.append(clip(shape, ellipse(tongue[0], tongue[1], tongue[2], tongue[3], fill=PAD)))
        fx = -6.8 if name != "smile" else -10.4                       # MH4: the fang, upper left of the mouth
        out.append(path(poly([(fx - 2.6, 51.6), (fx + 2.8, 52.4), (fx + 0.6, 58.6)]), **FANG_STYLE))
    else:
        out.append(path(poly([(-13.6, 50.2), (-7.0, 52.6), (-10.4, 60.4)]), **FANG_STYLE))   # MH4: small fang
    if name == "blep":           # MH4: a tiny tongue-out
        t = blob([(-5.2, 50.5), (-5.8, 56.5), (0, 62), (5.8, 56.5), (5.2, 50.5), (0, 49)])
        out.append(path(t, fill=PAD, stroke=INK, stroke_width=2.4, stroke_linejoin="round"))
        out.append(line(0, 53.5, 0, 58, stroke=TONGUE_SH, stroke_width=1.6))
    out.append(path(MOUTH_W, fill="none", stroke=INK, stroke_width=2.8, stroke_linecap="round",
                    stroke_linejoin="round"))
    out.append(line(0, 42, 0, 47.5, stroke=INK, stroke_width=2.4))
    return g(out, transform=MOUTH_AT)


# MH2: the messy fringe.  Clockwise from the screen-left temple: tufts sticking up along the top, then the
# locks that flop over the forehead (they stop short of the dots and the diamond in the middle).
HAIR = [(-60, -26), (-70, -40), (-77, -57, "c"), (-61, -55), (-55, -69), (-46, -83, "c"), (-36, -69),
        (-24, -83), (-8, -97, "c"), (-2, -77), (12, -83), (30, -89, "c"), (30, -71), (46, -71), (63, -69, "c"),
        (56, -55), (66, -47), (75, -32, "c"), (60, -30),
        (56, -15, "c"), (48, -32), (36, -23, "c"), (28, -38), (16, -43), (8, -36, "c"), (-2, -45), (-12, -40),
        (-20, -28, "c"), (-28, -42), (-36, -34), (-42, -19, "c"), (-50, -36), (-56, -28), (-60, -13, "c"),
        (-62, -28)]
# periwinkle streaks (MH2), drawn clipped to the hair: (spine control points, widths) of dyed strands
HAIR_STREAKS = [
    (((-8, -96), (-20, -72), (-36, -50), (-42, -19)), [3, 8, 9, 5]),
    (((30, -88), (29, -66), (38, -46), (36, -23)), [3, 7, 8, 5]),
    (((-76, -56), (-66, -46), (-60, -32), (-60, -13)), [3, 6, 7, 4]),
    (((62, -68), (58, -52), (57, -34), (56, -15)), [3, 5, 6, 4]),
]
HAIR_STRANDS = [((-28, -42), (-22, -54), (-10, -64)), ((-50, -36), (-47, -48), (-40, -58)),
                ((16, -43), (13, -55), (4, -64)), ((48, -32), (47, -45), (40, -55))]
HAIR_STRANDS_BIG = [((-2, -45), (-3, -52), (-8, -57)), ((28, -38), (28, -49), (22, -57)),
                    ((-36, -69), (-33, -62), (-27, -58))]


def _hair(p):
    shape = path(blob(HAIR), fill=FUR)
    strands = HAIR_STRANDS + (HAIR_STRANDS_BIG if p["big"] else [])
    paint = detail(
        clip(shape, [path(ribbon(bezier(*pts, n=16), widths), fill=PERI) for pts, widths in HAIR_STREAKS]),
        [path("M%g %g Q%g %g %g %g" % (a + b + c), fill="none", stroke=INK, stroke_width=2.0,
              stroke_linecap="round") for a, b, c in strands],
    )
    return [outlined(shape, ink=INK, width=WH), paint]


def _head(p):
    jaw = MOUTHS[p["mouth"]][2]
    # MH2: big cheek ruffs, three points a side
    half = [(0, -54), (32, -52), (60, -40), (76, -20), (84, -5), (99, -5), (113, 4, "c"), (102, 14), (115, 21),
            (125, 35, "c"), (108, 39), (114, 49), (112, 63, "c"), (96, 58), (84, 55), (62, 61 + jaw * 0.5),
            (32, 66 + jaw), (0, 67.5 + jaw)]
    skull = path(blob(sym(half)), fill=FUR)
    muzzle = blob(sym([(0, 22), (13, 24), (25, 33), (29, 47), (23, 60 + jaw * 0.6), (0, 72 + jaw)]))
    chin_shade = blob(sym([(0, 63.5 + jaw), (30, 62 + jaw), (60, 57.5 + jaw * 0.5), (84, 49.5), (102, 45),
                           (118, 64), (60, 96), (0, 100)]))
    marks = [
        path(muzzle, fill=FUR_L),
        path(chin_shade, fill=FUR_SH),
        # MH5: a short periwinkle mark under each eye
        [path(smooth([(s * 28, 29), (s * 51, 27), (s * 49, 43), (s * 43, 57, "c"), (s * 35, 43)]), fill=PERI)
         for s in (-1, 1)],
        # MH5: three dots and a small diamond on the forehead
        circle(-8.2, -26.5, 3.3, fill=PERI), circle(0, -30.5, 3.3, fill=PERI), circle(8.2, -26.5, 3.3, fill=PERI),
        path(poly([(0, -21), (5.2, -13), (0, -5), (-5.2, -13)]), fill=PERI),
    ]
    nose = blob([(-9.5, 30.8), (0, 29.6), (9.5, 30.8), (6.6, 37.2), (0, 41.4), (-6.6, 37.2)])
    face = detail(
        clip(skull, marks),
        _eye(-1, p), _eye(1, p),
        _mouth(p),
        path(nose, fill=NOSE, stroke=INK, stroke_width=2.4, stroke_linejoin="round"),
        ellipse(-3.0, 33.0, 2.8, 1.3, fill=NOSE_HI),
    )
    hy = HEAD_Y + p["bob"] + p["nod"]
    tf = "%s %s %s" % (translate(0, hy), rotate(p["tilt"], NECK[0] * HS, NECK[1] * HS), scale(HS))
    return g(_ear(-1, p["ear_l"]), _ear(1, p["ear_r"]),
             outlined(skull, ink=INK, width=WH), face, _hair(p), _glasses(p), transform=tf)


def _head_pt(p, x, y):
    """A head-frame point in body coordinates (for hands that touch the face)."""
    hy = HEAD_Y + p.get("bob", 0.0) + p.get("nod", 0.0)
    r = math.radians(p.get("tilt", 0.0))
    dx, dy = (x - NECK[0]) * HS, (y - NECK[1]) * HS
    return (NECK[0] * HS + dx * math.cos(r) - dy * math.sin(r),
            hy + NECK[1] * HS + dx * math.sin(r) + dy * math.cos(r))


# ------------------------------------------------------------------ body, legs, tee

BODY_HALF = [(0, 330), (15, 330, "c"), (16, 342), (32, 348), (42, 358), (41, 392), (40, 424), (41, 444),
             (38, 456), (38, 465, "c"), (11, 465, "c"), (10, 448), (6, 438), (0, 430, "c")]
FOOT = [(3, 463), (7, 454.5), (24, 451.5), (41, 454.5), (48, 463), (44.5, 470.3), (25.5, 471.6), (7, 470.3)]
HEM_Y = 419.0


def _mx(points):
    return [(-pt[0],) + tuple(pt[1:]) for pt in points]


def _lower(p):
    """Legs and feet (planted) plus the torso under the tee."""
    body = path(blob(sym(BODY_HALF)), fill=FUR)
    feet = [path(blob(FOOT), fill=FUR), path(blob(_mx(FOOT)), fill=FUR)]
    hem = HEM_Y + (7.0 if p["outfit"] == "apron" else 0.0)
    chev = dict(fill="none", stroke=PERI, stroke_width=3.8, stroke_linejoin="miter", stroke_linecap="butt")
    marks = [
        path(poly([(-60, hem - 12), (60, hem - 12), (60, hem + 4.5), (0, hem + 7.5), (-60, hem + 4.5)]),
             fill=FUR_SH),                                             # shadow under the hem
        # MH6: chevrons on the shins
        [[polyline([(s * 3, 446.0 + dy), (s * 23.5, 433.5 + dy), (s * 44, 446.0 + dy)], **chev)
          for dy in (0.0, 9.5)] for s in (-1, 1)],
    ]
    toes = [line(s * x, 465.0, s * x, 470.6, stroke=INK, stroke_width=2.2)
            for s in (-1, 1) for x in (18.5, 32.0)]
    foot_shade = [path(blob([(s * 7, 468.2), (s * 26, 469.6), (s * 45, 467.2), (s * 46, 474), (s * 7, 474)]),
                       fill=FUR_SH) for s in (-1, 1)]
    return g(outlined(body, feet, ink=INK, width=W),
             detail(clip(body, marks), clip(feet, foot_shade), toes))


# "KISS THE COOK", drawn as strokes on a 4 x 6 cell per letter (no fonts anywhere in the pipeline)
LETTERS = {
    "K": [[(0, 0), (0, 6)], [(4, 0), (0, 3.2), (4, 6)]],
    "I": [[(2, 0), (2, 6)]],
    "S": [[(4, 0.6), (2.8, 0), (1, 0), (0, 1), (0, 2), (1, 3), (3, 3), (4, 4), (4, 5), (3, 6), (1.2, 6), (0, 5.4)]],
    "T": [[(0, 0), (4, 0)], [(2, 0), (2, 6)]],
    "H": [[(0, 0), (0, 6)], [(4, 0), (4, 6)], [(0, 3), (4, 3)]],
    "E": [[(4, 0), (0, 0), (0, 6), (4, 6)], [(0, 3), (3, 3)]],
    "C": [[(4, 1), (3, 0), (1, 0), (0, 1), (0, 5), (1, 6), (3, 6), (4, 5)]],
    "O": [[(1, 0), (3, 0), (4, 1), (4, 5), (3, 6), (1, 6), (0, 5), (0, 1), (1, 0)]],
}


def _lettering(text, cx, y, k, stroke_w):
    """One centred line of stroke lettering; ``k`` scales the 4 x 6 letter cell."""
    adv = 5.6 * k
    x0 = cx - (len(text) * adv - 1.6 * k) / 2.0
    out = []
    for i, ch in enumerate(text):
        for stroke in LETTERS.get(ch, []):
            out.append(polyline([(x0 + i * adv + px * k, y + py * k) for px, py in stroke], stroke=LETTER,
                                stroke_width=stroke_w))
    return out


def _pendant(p, drop=0.0):
    """MH8: the grey feather on its cord, over the shirt.  Paint only: it never leaves the torso."""
    top = 368.0 + drop
    cord = [(-18, 344), (-10, 357 + drop * 0.5), (0, top), (10, 357 + drop * 0.5), (18, 344)]
    out = [path(smooth(cord, closed=False, tension=0.7), fill="none", stroke=CORD, stroke_width=2.6,
                stroke_linecap="round", stroke_linejoin="round")]
    if p["big"]:                 # the braid
        out.append(path(smooth(cord, closed=False, tension=0.7), fill="none", stroke=FEATHER, stroke_width=1.2,
                        stroke_dasharray="2.2 2.6"))
    vane = blob([(0.5, top + 1), (6.6, top + 8), (7.4, top + 17), (2.4, top + 27.5, "c"), (-4.6, top + 19),
                 (-5.6, top + 9)])
    out += [
        path(vane, fill=FEATHER, stroke=INK, stroke_width=1.9, stroke_linejoin="round"),
        clip(path(vane), path(blob([(1.4, top), (9, top + 6), (9, top + 20), (2.4, top + 28)]), fill=FEATHER_SH)),
        line(0.6, top + 2, 2.2, top + 25.5, stroke=CORD, stroke_width=1.5),
        circle(0.3, top + 0.6, 3.0, fill=CORD, stroke=INK, stroke_width=1.4),
    ]
    if p["big"]:
        out += [line(1.2, top + 10, -3.4, top + 13.5, stroke=CORD, stroke_width=1.0),
                line(1.6, top + 16, -2.6, top + 19.5, stroke=CORD, stroke_width=1.0),
                line(1.3, top + 10, 5.6, top + 12.5, stroke=CORD, stroke_width=1.0)]
    return detail(out)


def _torso(p):
    """Chest marks, the tee (or tee + apron) and the pendant; moves with ``bob``."""
    apron_on = p["outfit"] == "apron"
    chest = path(blob(sym([(0, 330), (15, 330, "c"), (16, 342), (32, 348), (42, 358), (41, 392), (35, 412),
                           (0, 415)])), fill=FUR)
    marks = [
        path(poly([(-30, 330), (30, 330), (30, 349), (0, 354), (-30, 349)]), fill=FUR_SH),    # under the chin
        # MH6: V-shaped lines at the collar (the heart and the navel diamond are under the shirt)
        polyline([(-13, 337), (0, 357), (13, 337)], stroke=PERI, stroke_width=3.4, stroke_linejoin="miter"),
    ]
    tee_half = [(0, 363), (12, 358), (22, 350), (27, 343.5, "c"), (47, 352.5, "c"), (47, 388),
                (49, HEM_Y - 4, "c"), (25, HEM_Y), (0, HEM_Y + 1)]
    tee = path(smooth(sym(tee_half)), fill=TEE)
    collar = "M-27 343.5 C-22 350 -12 358 0 363 C12 358 22 350 27 343.5"
    zig = [(-58 + 9.0 * i, 399.0 if i % 2 else 409.0) for i in range(14)]
    tee_marks = [
        path(blob([(35, 350), (54, 354), (56, 424), (38, 424), (41, 388)]), fill=TEE_SH),      # side shade
        path(collar, fill="none", stroke=TEE_SH, stroke_width=6.0, transform=translate(0, 3.2)),
        # the one periwinkle zigzag band across the chest
        polyline(zig, stroke=PERI, stroke_width=4.8, stroke_linejoin="miter", stroke_linecap="butt"),
    ]
    out = [outlined(chest, ink=INK, width=W), detail(clip(chest, marks)),
           outlined(tee, ink=INK, width=W), detail(clip(tee, tee_marks))]
    if apron_on:
        bib_half = [(0, 356), (21, 356, "c"), (24, 386), (44, 392, "c"), (46, HEM_Y + 3, "c"), (24, HEM_Y + 7),
                    (0, HEM_Y + 8)]
        bib = path(smooth(sym(bib_half)), fill=APRON)
        strap = dict(fill="none", stroke=APRON, stroke_width=5.4, stroke_linecap="butt")
        straps = [line(-19, 358, -25, 343, **strap), line(19, 358, 25, 343, **strap)]
        k = 1.28
        bib_marks = [
            path(blob([(30, 384), (50, 388), (52, 432), (33, 432), (35, 404)]), fill=APRON_SH),
            line(-21, 361.5, 21, 361.5, stroke=APRON_SH, stroke_width=2.4),
            _lettering("KISS", 0, 392.5, k, 1.7), _lettering("THE", 0, 403.0, k, 1.7),
            _lettering("COOK", 0, 413.5, k, 1.7),
        ]
        out += [outlined(straps, bib, ink=INK, width=2.8), detail(clip(bib, bib_marks)),
                _pendant(p, drop=-3.0)]
    else:
        out.append(_pendant(p))
    return g(out, transform=translate(0, p["bob"]))


# ------------------------------------------------------------------ arms and hands

L1, L2 = 26.0, 30.0     # upper arm, forearm lengths
SHOULDER = (42.0, 357.0)
FINGER = 37.0           # how far past the wrist the tip of the pointing finger is


def _arm_points(side, angles, bob):
    a1, a2 = math.radians(angles[0]), math.radians(angles[1])
    s = (side * SHOULDER[0], SHOULDER[1] + bob)
    e = (s[0] + side * math.sin(a1) * L1, s[1] + math.cos(a1) * L1)
    w = (e[0] + side * math.sin(a2) * L2, e[1] + math.cos(a2) * L2)
    return s, e, w


def aim(side, target, reach=0.0, bob=0.0):
    """Arm angles that put the point ``reach`` units past the wrist on ``target`` (elbow out)."""
    s = (side * SHOULDER[0], SHOULDER[1] + bob)
    dx, dy = target[0] - s[0], target[1] - s[1]
    dist = math.hypot(dx, dy) or 1.0
    r1, r2 = L1, L2 + reach
    d = clamp(dist, abs(r2 - r1) + 0.5, r1 + r2 - 0.5)
    a = (r1 * r1 - r2 * r2 + d * d) / (2.0 * d)
    h = math.sqrt(max(r1 * r1 - a * a, 0.0))
    ux, uy = dx / dist, dy / dist
    mx, my = s[0] + ux * a, s[1] + uy * a
    e = max([(mx - uy * h, my + ux * h), (mx + uy * h, my - ux * h)], key=lambda c: side * c[0])
    a1 = math.degrees(math.atan2(side * (e[0] - s[0]), e[1] - s[1]))
    a2 = math.degrees(math.atan2(side * (target[0] - e[0]), target[1] - e[1]))
    return (a1, a2)


def _hand(kind, side):
    """Hand shapes in the hand frame: wrist at the origin, fingers towards -y.  Returns (shapes, paint)."""
    if kind == "open":       # palm towards us: MH9, pink pads
        shapes = [circle(0, -11, 12.6, fill=FUR)]
        fingers = [(-10.6, -20.6), (-3.9, -26.2), (4.1, -26.2), (10.7, -20.6)]
        shapes += [circle(x, y, 5.5, fill=FUR) for x, y in fingers]
        shapes.append(circle(-side * 14.2, -8.6, 5.0, fill=FUR))             # thumb, body side
        paint = [ellipse(0, -10.4, 7.2, 5.7, fill=PAD)] + [circle(x, y - 0.5, 2.8, fill=PAD)
                                                           for x, y in fingers]
        return shapes, paint
    if kind == "point":      # one finger up (it pushes the glasses), the rest curled
        shapes = [circle(0, -10.5, 12.2, fill=FUR),
                  path(capsule((0.5, -17), (0.5, -32), 5.3, 4.9), fill=FUR)]
        paint = [path("M-8.5 -8.5 Q0 -3 8.5 -8.5", fill="none", stroke=INK, stroke_width=2.1,
                      stroke_linecap="round"),
                 line(-6.0, -19.5, -6.0, -14.5, stroke=INK, stroke_width=2.0),
                 line(6.6, -19.0, 6.6, -14.5, stroke=INK, stroke_width=2.0)]
        return shapes, paint
    # "paw" and "grip": the back of a mitten paw
    shapes = [path(blob([(-9.6, 2), (-13.4, -9.4), (-10.2, -20), (0, -23.6), (10.2, -20), (13.4, -9.4),
                         (9.6, 2)]), fill=FUR)]
    paint = [line(-4.3, -22.6, -4.3, -16.2, stroke=INK, stroke_width=2.1),
             line(4.3, -22.6, 4.3, -16.2, stroke=INK, stroke_width=2.1)]
    return shapes, paint


def _arm(side, p):
    angles = p["arm_l"] if side < 0 else p["arm_r"]
    kind = p["hand_l"] if side < 0 else p["hand_r"]
    s, e, w = _arm_points(side, angles, p["bob"])
    d1 = ((e[0] - s[0]) / L1, (e[1] - s[1]) / L1)
    d2 = ((w[0] - e[0]) / L2, (w[1] - e[1]) / L2)
    n2 = (-d2[1], d2[0])
    upper_d = capsule(s, e, 11.4, 10.8)
    fore_d = capsule(e, w, 10.8, 10.2)
    shapes, paint = _hand(kind, side)
    htf = "%s %s" % (translate(w[0], w[1]), rotate(math.degrees(math.atan2(d2[0], -d2[1]))))

    def across(t, width, colour):
        """A band across the forearm, ``t`` units from the elbow."""
        c = (e[0] + d2[0] * t, e[1] + d2[1] * t)
        return line(c[0] - n2[0] * 15, c[1] - n2[1] * 15, c[0] + n2[0] * 15, c[1] + n2[1] * 15, stroke=colour,
                    stroke_width=width, stroke_linecap="butt")
    if side > 0:
        # MH6: three periwinkle bands, then the striped wristband (emo-casual) on the screen-right wrist
        bands = [across(t, 3.5, PERI) for t in (3.6, 10.2, 16.8)]
        bands += [across(26.2, 9.4, TEE), across(24.2, 1.7, PAD), across(28.0, 1.7, PAD)]
    else:
        bands = [across(t, 3.7, PERI) for t in (7.0, 14.6, 22.2)]
    arm = g(
        outlined(path(upper_d, fill=FUR), path(fore_d, fill=FUR), g(shapes, transform=htf), ink=INK, width=W),
        detail(clip(path(fore_d), bands), g(paint, transform=htf)),
    )
    # short black sleeve
    n1 = (-d1[1], d1[0])

    def sp(along_d, across_d):
        return (s[0] + d1[0] * along_d + n1[0] * across_d, s[1] + d1[1] * along_d + n1[1] * across_d)
    sleeve = path(smooth([sp(-9, -12), sp(-9, 12), sp(6, 15), sp(15.5, 15.8) + ("c",),
                          sp(15.5, -15.8) + ("c",), sp(6, -15)]), fill=TEE)
    return g(arm, outlined(sleeve, ink=INK, width=W))


# ------------------------------------------------------------------ tail  (MH7)

TAIL_IN = [(14, 432), (70, 450), (130, 450), (146, 400)]
TAIL_OUT = [(14, 432), (86, 440), (168, 440), (184, 370)]
TAIL_W = [16, 36, 50, 54, 50, 36, 14]


def _tail_half(t):
    i = clamp(t) * (len(TAIL_W) - 1)
    j = min(int(i), len(TAIL_W) - 2)
    return lerp(TAIL_W[j], TAIL_W[j + 1], i - j) / 2.0


def _tail_outline(spine):
    """The bushy outline: a fat plume with pointed tufts of fur along both edges and a pointed tip."""
    def pt(t, sign, out=0.0, fwd=0.0, corner=False):
        c, tan = along(spine, t)
        nx, ny = -tan[1] * sign, tan[0] * sign
        h = _tail_half(t) + out
        q = (c[0] + nx * h + tan[0] * fwd, c[1] + ny * h + tan[1] * fwd)
        return q + ("c",) if corner else q
    pts = [pt(0.0, 1), pt(0.12, 1), pt(0.24, 1)]
    for t0 in (0.32, 0.51, 0.70):                      # outer edge, root to tip: three tufts
        pts += [pt(t0, 1, 1.5), pt(t0 + 0.075, 1, 8.5, 5.0, True), pt(t0 + 0.09, 1, -2.5, 0.0, True)]
    pts.append(pt(0.9, 1))
    end, tan = along(spine, 1.0)
    pts.append((end[0] + tan[0] * 15, end[1] + tan[1] * 15, "c"))
    pts.append(pt(0.92, -1))
    for t0 in (0.74, 0.52):                            # inner edge, tip to root: two tufts
        pts += [pt(t0 + 0.09, -1, -2.5, 0.0, True), pt(t0 + 0.075, -1, 7.5, 5.0, True), pt(t0, -1, 1.5)]
    pts += [pt(0.4, -1), pt(0.27, -1), pt(0.13, -1), pt(0.0, -1)]
    return blob(pts)


def _tail(p):
    t = (p["tail"] + 1.0) / 2.0
    spine = bezier(*lerp_pts(TAIL_IN, TAIL_OUT, t), n=40)
    shape = path(_tail_outline(spine), fill=FUR)
    marks = [
        # the last third is periwinkle with a soft jagged edge
        path(band(spine, TAIL_W, 0.64, 1.3, zig=7.0, teeth=4, over=16.0), fill=PERI),
        # fine stripes near the base
        [path(band(spine, TAIL_W, a, a + 0.022, over=4.0), fill=PERI) for a in (0.27, 0.33, 0.39)],
    ]
    return g(outlined(shape, ink=INK, width=W), detail(clip(shape, marks)))


# ------------------------------------------------------------------ props

def _hand_frame(p):
    """Where the screen-left hand is: (wrist, rotation in degrees)."""
    s, e, w = _arm_points(-1, p["arm_l"], p["bob"])
    d2 = ((w[0] - e[0]) / L2, (w[1] - e[1]) / L2)
    return w, math.degrees(math.atan2(d2[0], -d2[1]))


def _camcorder(p):
    """A small handheld camcorder in the screen-left hand, lens towards us, REC light on its corner."""
    (ox, oy), deg = _hand_frame(p)
    body = rect(-25, -55, 46, 38, r=7, fill=CAM)
    shapes = [rect(-6, -63, 20, 12, r=4, fill=CAM_D),                  # top handle / microphone
              rect(18, -47, 9, 22, r=3, fill=CAM_D),                   # the folded screen, edge on
              body]
    paint = [
        clip(body, rect(-25, -27, 46, 12, fill=CAM_D)),
        circle(-6, -36, 14.6, fill=CAM_D),
        circle(-6, -36, 11.4, fill=CAM_HI),
        circle(-6, -36, 9.2, fill=PERI_D),
        circle(-6, -36, 4.6, fill=GLASS),
        circle(-9.6, -39.8, 2.8, fill="#ffffff"),
        circle(13.2, -47.4, 5.4, fill=CAM_D),
        circle(13.2, -47.4, 3.9, fill=REC if p["rec"] else mix(REC, CAM_D, 0.78)),
    ]
    if p["rec"]:
        paint.append(circle(12.0, -48.6, 1.2, fill="#ffffff"))
    tf = "%s %s" % (translate(ox, oy), rotate(deg))
    return g(outlined(shapes, ink=INK, width=2.8), detail(paint), transform=tf)


def _ladle(p):
    """A ladle in the screen-left hand, bowl down; ``stir`` swings it round a small circle."""
    (ox, oy), deg = _hand_frame(p)
    a = 2.0 * math.pi * float(p["stir"])
    sway = 9.0 * math.sin(a)
    dip = 2.5 * math.cos(a)
    handle = polyline([(0, -30), (0, -12), (sway * 0.25, 16), (sway, 44 + dip)], stroke=STEEL, stroke_width=5.0)
    bowl = path(blob([(sway - 13, 42 + dip), (sway - 10, 54 + dip), (sway, 59 + dip), (sway + 10, 54 + dip),
                      (sway + 13, 42 + dip)]), fill=STEEL)
    paint = [clip(bowl, path(blob([(sway + 2, 40 + dip), (sway + 16, 40 + dip), (sway + 14, 60 + dip),
                                   (sway + 3, 62 + dip)]), fill=STEEL_SH)),
             circle(0, -29, 1.9, fill=STEEL_SH)]
    tf = "%s %s" % (translate(ox, oy), rotate(deg + 180.0))
    return g(outlined(handle, bowl, ink=INK, width=2.6), detail(paint), transform=tf)


# ------------------------------------------------------------------ extras

SPARKLES = {
    1: [(-152, 236, 14, PERI), (154, 296, 10, PAD)],
    2: [(-160, 266, 11, PAD), (156, 236, 15, PERI), (-144, 338, 8, PERI)],
    3: [(-150, 218, 12, PERI), (164, 268, 12, PAD), (-164, 306, 13, PAD), (-138, 352, 8, PERI)],
}


def _extras(p):
    out = []
    for (x, y, r, col) in SPARKLES.get(int(p["sparkles"] or 0), []):
        out.append(sparkle(x, y, r, fill=col, ink=INK))
    if p["zzz"] is not None:
        out.append(zzz(2, 172, size=18, fill=PERI, ink=INK, drift=float(p["zzz"])))
    return out


# ------------------------------------------------------------------ draw

def draw(pose_in=None, guide=False):
    """One frame of Iggy as a complete SVG document (512 x 512 viewBox, feet at 92 %)."""
    p = _p(pose_in)
    front, behind = [], []
    for side in (-1, 1):
        s_, e_, w_ = _arm_points(side, p["arm_l"] if side < 0 else p["arm_r"], p["bob"])
        prop = p["prop"] if side < 0 else None
        reach = 60.0 if prop == "camcorder" else 24.0
        top = w_[1] + (w_[1] - e_[1]) / L2 * reach
        nodes = []
        if prop == "camcorder":
            nodes.append(_camcorder(p))                    # the camcorder sits behind its hand
        elif prop == "ladle":
            nodes.append(_ladle(p))
        nodes.append(_arm(side, p))
        (front if min(top, w_[1]) < 346 else behind).append(nodes)
    parts = [_tail(p), _lower(p), _torso(p), behind, _head(p), front]
    sq = p["squash"]
    figure = g(parts, transform="%s %s %s" % (translate(CX, -p["hop"]),
                                              translate(0, BASELINE),
                                              scale(1 + sq * 0.55, 1 - sq)) + " " + translate(0, -BASELINE))
    extras = g(_extras(p), transform=translate(CX, 0))
    return sticker(figure, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 5)

REST = pose()                       # the neutral stand: deadpan-fond, every default


def _idle():
    frames = []
    n = 8
    for i in range(n):
        breath = cycle(i, n)
        frames.append(pose(REST,
                           squash=0.010 * breath, bob=1.1 * breath,
                           tail=0.6 * cycle(i, n, phase=0.1),
                           ear_l=-6.0 if i == 2 else (-2.5 if i == 3 else 0.0)))
    return frames


def _blink():
    return [pose(REST, lid=0.72), pose(REST, eyes="closed"), pose(REST, lid=0.62)]


def _talk():
    return [pose(REST, mouth="open_s", nod=0.5), pose(REST, mouth="open_l", nod=1.4, ear_l=-2, ear_r=-2),
            pose(REST, mouth="open_s", nod=0.5, tail=0.3), pose(REST, mouth="w", tail=0.3)]


def _happy():
    up = (106.0, 150.0)
    mid = (72.0, 120.0)
    base = dict(eyes="happy", mouth="smile", hand_l="open", hand_r="open")
    return [
        pose(REST, squash=0.05, bob=2, arm_l=mid, arm_r=mid, ear_l=5, ear_r=5, tail=0.2, **base),
        pose(REST, squash=-0.02, hop=6, arm_l=up, arm_r=up, ear_l=-5, ear_r=-5, tail=0.8, sparkles=1, **base),
        pose(REST, squash=-0.012, hop=10, arm_l=up, arm_r=up, ear_l=-7, ear_r=-7, tail=1.0, sparkles=2, **base),
        pose(REST, squash=0.0, hop=6, arm_l=up, arm_r=up, ear_l=-3, ear_r=-3, tail=0.7, sparkles=3, **base),
        pose(REST, squash=0.055, bob=2, arm_l=mid, arm_r=mid, ear_l=7, ear_r=7, tail=0.1, sparkles=2, **base),
        pose(REST, squash=0.0, arm_l=mid, arm_r=mid, ear_l=0, ear_r=0, tail=0.4, sparkles=1, **base),
    ]


def _sleep():
    base = pose(REST, eyes="closed", mouth="w", tilt=6.0, nod=6.0, ear_l=16.0, ear_r=20.0, tail=-1.0,
                arm_l=(7.0, 2.0), arm_r=(7.0, 2.0), glasses=3.5)
    return [pose(base, squash=0.012, zzz=0.0), pose(base, squash=0.028, bob=1.5, zzz=0.3, nod=7.5),
            pose(base, squash=0.012, zzz=0.6, mouth="open_s"),
            pose(base, squash=-0.004, bob=-1.0, zzz=0.9, nod=5.0, mouth="open_s")]


def _wave():
    base = dict(eyes="open", mouth="smile", hand_l="open", tail=0.6)
    lo, hi = (104.0, 116.0), (104.0, 154.0)
    return [
        pose(REST, arm_l=(64.0, 98.0), eyes="open", mouth="open_s", hand_l="open", tail=0.3),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-4, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-6, **base),
        pose(REST, arm_l=hi, tilt=-3.0, ear_l=-4, **base),
        pose(REST, arm_l=lo, tilt=-4.0, ear_l=-6, **base),
        pose(REST, arm_l=(64.0, 98.0), mouth="w", hand_l="open", tail=0.3),
    ]


def _rim(slip, tilt=0.0):
    """The spot on the nose side of the screen-left rim where the finger pushes (body coordinates)."""
    a = math.radians(58.0)
    x = -(EYE_X + 0.5) + (GL_R + 1.5) * math.cos(a)
    y = EYE_Y + 0.5 + slip + (GL_R + 1.5) * math.sin(a)
    return _head_pt({"tilt": tilt}, x, y)


def _special():
    """Pushes the glasses back up the nose with one finger; the lenses glint on the last frame."""
    slip = 8.0

    def push(s, tilt=0.0):
        return aim(-1, _rim(s, tilt), reach=FINGER)
    ready = aim(-1, (_rim(slip)[0] - 6.0, _rim(slip)[1] + 20.0), reach=FINGER)
    return [
        pose(REST, glasses=slip, look=(0.0, 0.7), lid=0.46, ear_l=4, ear_r=4, tail=-0.2),
        pose(REST, glasses=slip, look=(-0.3, 0.8), lid=0.46, arm_l=(46.0, 96.0), hand_l="point", tail=0.0),
        pose(REST, glasses=slip, look=(-0.2, 0.6), arm_l=ready, hand_l="point", tail=0.2),
        pose(REST, glasses=slip, arm_l=push(slip), hand_l="point", eyes="closed", tail=0.4),
        pose(REST, glasses=slip * 0.45, arm_l=push(slip * 0.45), hand_l="point", eyes="closed", nod=-0.6,
             tail=0.6),
        pose(REST, glasses=-0.5, arm_l=push(-0.5), hand_l="point", eyes="closed", nod=-1.2, ear_l=-4,
             ear_r=-4, tail=0.8),
        pose(REST, glasses=-0.5, arm_l=push(-0.5), hand_l="point", glint=0.5, nod=-1.2, ear_l=-5, ear_r=-5,
             tail=0.9),
        pose(REST, glasses=-0.5, arm_l=push(-0.5), hand_l="point", glint=1.0, nod=-1.2, ear_l=-6, ear_r=-6,
             tail=1.0),
    ]


FILM_ARM = (56.0, 166.0)


def _film():
    """Optional extra: filming with the camcorder, the red REC light blinking."""
    base = pose(REST, prop="camcorder", hand_l="grip", arm_l=FILM_ARM, eyes="open", look=(-0.5, 0.1),
                tilt=-2.0)
    frames = []
    n = 6
    for i in range(n):
        sway = cycle(i, n)
        frames.append(pose(base, rec=(i % 2 == 0), arm_l=(FILM_ARM[0] + 2.0 * sway, FILM_ARM[1] + 3.0 * sway),
                           bob=0.8 * sway, tail=0.5 * cycle(i, n, phase=0.2),
                           ear_r=-4.0 if i == 4 else 0.0))
    return frames


COOK_ARM = (30.0, 78.0)


def _cook():
    """Optional extra: the apron on, stirring with a ladle."""
    base = pose(REST, outfit="apron", prop="ladle", hand_l="grip", look=(-0.5, 0.8), lid=0.42)
    frames = []
    n = 6
    for i in range(n):
        t = i / float(n)
        frames.append(pose(base, stir=t, arm_l=(COOK_ARM[0] + 5.0 * math.sin(2 * math.pi * t),
                                                COOK_ARM[1] + 7.0 * math.cos(2 * math.pi * t)),
                           bob=0.8 * math.sin(2 * math.pi * t), tail=0.5 * cycle(i, n, phase=0.3),
                           nod=1.0))
    return frames


ANIMS = {
    "idle": anim(_idle(), fps=6, loop=True),
    "blink": anim(_blink(), fps=12, loop=False),
    "talk": anim(_talk(), fps=8, loop=True),
    "happy": anim(_happy(), fps=10, loop=False),
    "sleep": anim(_sleep(), fps=2, loop=True),
    "wave": anim(_wave(), fps=8, loop=False),
    "look_left": anim([pose(REST, look=(-1.0, 0.0), tilt=-2.0, ear_l=-4.0)], fps=1, loop=False),
    "look_right": anim([pose(REST, look=(1.0, 0.0), tilt=2.0, ear_r=-4.0)], fps=1, loop=False),
    "special": anim(_special(), fps=6, loop=False),
    "film": anim(_film(), fps=4, loop=True),
    "cook": anim(_cook(), fps=6, loop=True),
}

#: the 512 px still: a small open-pawed wave (pink pads), the tiny tongue-out, a sparkle
PORTRAIT = pose(REST, big=True, mouth="blep", arm_l=(104.0, 150.0), hand_l="open", tilt=-3.0, tail=0.8,
                sparkles=1, ear_l=-4.0)
