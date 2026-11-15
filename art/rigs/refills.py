"""THE REFILLS: background cast (cameo).  Same house style as ``nova.py`` / ``duskie.py``, simpler.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 nine identical small round birds heaped in a low pyramid (4 + 3 + 2) and drawn as ONE sprite; MH2 orange
beaks; MH3 one dot eye each (with a pale ring); MH4 in the talk animation different birds open their beaks on
alternate frames.  Height 0.45 of Nova, wide.  Special (SPEC_V2 section 8): they all hop once.

Coordinates: drawn around x = 0, canvas y, feet on BASELINE; :func:`lib2d.chibi.figure` centres them.
"""
from __future__ import annotations

from lib2d import (BASELINE, CX, anim, blob, circle, clip, detail, ellipse, g, line, mix, outlined, path, poly,
                   pose, sparkle, sticker, translate)
from lib2d.chibi import figure

CHAR_ID = "refills"
HEIGHT = 0.45
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, The Refills)
BODY = "#6f7480"
WING = "#585d68"
BELLY = "#8b909b"
BEAK = "#f0a23a"
EYE = "#22242a"
# derived
INK = mix(EYE, WING, 0.25)
RING = mix(BELLY, "#ffffff", 0.55)    # the pale eye ring
BEAK_SH = mix(BEAK, "#b86a1a", 0.5)
MOUTH_IN = mix(INK, "#c25a5a", 0.35)
BODY_SH = mix(BODY, WING, 0.55)

W = 3.2
R = 37.0              # bird radius

# (x, y of the centre, facing: -1 left, 1 right, 0 straight at us) in drawing order: back row first, and in
# each row the outer birds first so every beak (pointing outwards) sits on top of its neighbour
BIRDS = [(-36, BASELINE - R - 114, -1), (36, BASELINE - R - 114, 0),
         (-72, BASELINE - R - 58, -1), (72, BASELINE - R - 58, 1), (0, BASELINE - R - 58, 0),
         (-108, BASELINE - R, -1), (108, BASELINE - R, 1), (-36, BASELINE - R, -1), (36, BASELINE - R, 1)]

DEFAULTS = {"bobs": (0.0,) * 9, "open": (0,) * 9, "eyes": "open", "shut": (0,) * 9, "hop": 0.0, "squash": 0.0,
            "jump": (0.0,) * 9, "sparkles": 0}


def _p(pin):
    p = dict(DEFAULTS)
    p.update(pin or {})
    return p


def _beak(f, is_open):
    """MH2: closed = one small wedge; open = two wedges with the mouth showing (MH4)."""
    if f == 0:   # facing us: a little downward wedge under the eyes
        if not is_open:
            return [path(poly([(-8, 2), (8, 2), (0, 14)]), fill=BEAK)], []
        return ([path(poly([(-8, 0), (8, 0), (0, 7)]), fill=BEAK), path(poly([(-6, 10), (6, 10), (0, 18)]), fill=BEAK),
                 path(poly([(-6, 4), (6, 4), (6, 11), (-6, 11)]), fill=MOUTH_IN)], [])
    if not is_open:
        return [path(poly([(f * 26, -10), (f * 46, -2), (f * 26, 5)]), fill=BEAK)], \
            [line(f * 28, -2.5, f * 40, -2, stroke=BEAK_SH, stroke_width=1.6)]
    return [path(poly([(f * 26, -12), (f * 46, -9), (f * 27, -3)]), fill=BEAK),
            path(poly([(f * 27, 2), (f * 42, 8), (f * 26, 7)]), fill=BEAK),
            path(poly([(f * 25, -4), (f * 36, -4), (f * 36, 4), (f * 25, 4)]), fill=MOUTH_IN)], []


def _bird(i, p):
    x, y, f = BIRDS[i]
    y += float(p["bobs"][i]) - float(p["jump"][i])
    is_open = float(p["open"][i]) >= 0.5
    shut = p["eyes"] == "closed" or float(p["shut"][i]) >= 0.5
    body_d = blob([(0, -R * 0.94), (R * 0.72, -R * 0.66), (R, 0), (R * 0.74, R * 0.7), (0, R * 0.96),
                   (-R * 0.74, R * 0.7), (-R, 0), (-R * 0.72, -R * 0.66)])
    body = path(body_d, fill=BODY)
    beak, beak_paint = _beak(f, is_open)
    tuft = path("M-2 %g Q2 %g 8 %g" % (-R * 0.9, -R * 1.22, -R * 1.12), fill="none", stroke=BODY, stroke_width=4.0,
                stroke_linecap="round")
    bx = f * 5.0
    marks = [path(blob([(-R, R * 0.2), (0, R * 0.42), (R, R * 0.2), (R, R * 1.2), (-R, R * 1.2)]), fill=BODY_SH),
             ellipse(bx, R * 0.38, R * 0.58, R * 0.46, fill=BELLY),
             ellipse(-f * 18 if f else -24, 6, 13, 20, rot=-f * 18 if f else 14, fill=WING)]
    if f == 0:
        marks.append(ellipse(24, 6, 13, 20, rot=-14, fill=WING))
    eyes = []
    ex_list = [(-12.0, -10.0), (12.0, -10.0)] if f == 0 else [(f * 12.0, -11.0)]
    for ex, ey in ex_list:
        if shut:
            eyes.append(path("M%g %g Q%g %g %g %g" % (ex - 6, ey, ex, ey + 5, ex + 6, ey), fill="none", stroke=EYE,
                             stroke_width=2.8, stroke_linecap="round"))
        else:   # MH3: a dot eye with a pale ring and a glint
            eyes += [circle(ex, ey, 8.0, fill=RING), circle(ex, ey, 5.4, fill=EYE),
                     circle(ex - 1.6, ey - 1.8, 1.8, fill="#ffffff")]
    feet = []
    if i >= 5 and float(p["jump"][i]) < 0.5:     # only the bottom row shows its feet
        feet = [line(dx, R * 0.9, dx + 1, R + 2.0, stroke=BEAK, stroke_width=4.0) for dx in (-9.0, 9.0)]
    return g(outlined(tuft, body, beak, *feet, ink=INK, width=W),
             detail(clip(body, marks), [b.copy(stroke=INK, stroke_width=1.8, stroke_linejoin="round") for b in beak] if f == 0 else beak,
                    eyes, beak_paint), transform=translate(x, y))


SPARKLES = {1: [(-150, 300, 11, BEAK), (150, 330, 9, RING)]}


def draw(pose_in=None, guide=False):
    p = _p(pose_in)
    extras = [sparkle(CX + x, y, r, fill=c, ink=INK) for (x, y, r, c) in SPARKLES.get(p["sparkles"], [])]
    birds = [_bird(i, p) for i in range(len(BIRDS))]
    fig = figure(birds, p)
    return sticker(fig, extras, ink=INK, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

REST = pose()
A = (1, 0, 0, 1, 0, 1, 0, 1, 0)     # MH4: these beaks open on talk frame 0 ...
B = tuple(1 - v for v in A)        # ... and the other birds' on frame 1

ANIMS = {
    # a shuffle in the heap: a couple of birds settle, one blinks
    "idle": anim([pose(REST),
                  pose(REST, bobs=(1.5, 0, 1.0, 0, 1.5, 0, 0, 0, 0), shut=(0, 0, 0, 0, 1, 0, 0, 0, 0)),
                  pose(REST, bobs=(0, 1.5, 0, 1.0, 0, 0, 0, 0, 0))], fps=4, loop=True),
    "talk": anim([pose(REST, open=A), pose(REST, open=B)], fps=6, loop=True),
    "blink": anim([pose(REST, eyes="closed")], fps=8, loop=False),
    # special: they all hop once (a little out of step)
    "special": anim([pose(REST, squash=0.04),
                     pose(REST, jump=(14, 18, 16, 20, 15, 18, 22, 19, 16), open=(1,) * 9, sparkles=1),
                     pose(REST, jump=(6, 9, 8, 10, 7, 9, 12, 10, 8), open=(1,) * 9),
                     pose(REST, squash=0.03)], fps=8, loop=False),
}
