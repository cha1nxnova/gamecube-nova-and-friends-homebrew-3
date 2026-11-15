"""DUSKIE (golden jackal) as a papercraft low-poly bust, plus the three-bust group shot.

Canon: docs/CHARACTERS.md (Duskie). Built like ``nova.py`` and ``iggy.py`` (same cameras, lighting
and ground line). Duskie sits between the two in head size, with smaller upright ears, a longer
canine muzzle and a sturdier neck and shoulders. His tee has a low back neckline, so the mottled
saddle (black, grey and brown-gold dashes) shows on the nape and upper back in the turntable.

    build(turn, nod, tilt)   the whole bust (cached; do not modify the returned mesh)
    JOBS                     duskie_bust, duskie_icon, duskie_spin, trio_busts

The model faces +z; +x is the viewer's right (Duskie's own left).
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..mesh import (UNLIT, Mesh, clip_halfplane, compose, cone_between, decal, decals, facet_angles, icosphere,
                    loft, merge, ngon, ring, rot_x, rot_y, rot_z, star4, stroke, translate, v_dot, v_norm)
from ..pipeline import Job
from ..render import Camera, Scene, Shadow, house_lighting, house_outline

# ---- palette (docs/CHARACTERS.md, Duskie) ---------------------------------------------------------
GOLD = "#ffd37c"
GOLD_DEEP = "#fec349"
CREAM = "#fdebc8"
BROWN = "#b5832a"          # ear backs and tips, brow dots, freckles, saddle
SADDLE_BLACK = "#2a2a2a"
SADDLE_GREY = "#8a8a8a"
IRIS = "#79bff0"
IRIS_LO = "#4a98d6"
NOSE = "#1f1c1a"
TEE = "#9fd3f5"
TEE_SHADE = "#7fb6dd"      # a shade of the (project-choice) sky-blue tee
INK = "#1f1c1a"
STAR = "#fff3b0"
STAR_PINK = "#ffd1ea"

BASE_Y = -2.25
SEG = 12
HEAD_ANGLES = facet_angles([16, 52, 80, 108, 136, 164])
FRONT = (0, 1, 2, 10, 11)

# ---- head -----------------------------------------------------------------------------------------
#             y     rx    rz front  rz back
HEAD_RINGS = [(-0.74, 0.60, 0.62, 0.50),
              (-0.50, 0.92, 0.82, 0.70),
              (-0.24, 1.01, 0.86, 0.84),      # cheeks
              (0.32, 0.93, 0.81, 0.86),       # brow line
              (0.56, 0.72, 0.64, 0.72),
              (0.72, 0.42, 0.37, 0.44)]


def _head():
    def colour(k, i):
        return CREAM if (k == 0 and i in FRONT) else GOLD

    rings = [ring(y, rx, rzf, rz_back=rzb, angles=HEAD_ANGLES) for y, rx, rzf, rzb in HEAD_RINGS]
    return loft(rings, colour, cap_start=(0.0, -0.88, 0.10), cap_end=(0.0, 0.81, -0.02), alternate="facet",
                cap_color=lambda k, i: CREAM if (k < 0 and i in FRONT) else GOLD)


MUZZLE_BASE = (0.0, -0.36, 0.44)
MUZZLE_TIP = (0.0, -0.48, 1.34)


def _muzzle():
    """A long canine muzzle: golden bridge, cream sides and underside."""
    m = cone_between(MUZZLE_BASE, MUZZLE_TIP, 0.42, 0.19, 8, GOLD, cap_start=False)
    y0 = MUZZLE_BASE[1]
    m.warp(lambda p: (p[0] * 1.05, y0 + (p[1] - y0) * 0.86, p[2]))
    m.paint(CREAM, lambda c, n, i: n[1] < 0.55)
    return m


def _nose():
    return icosphere((0.16, 0.11, 0.11), 0, NOSE).translate(MUZZLE_TIP[0], MUZZLE_TIP[1] + 0.05, MUZZLE_TIP[2] + 0.01)


def _grin(muzzle):
    """An easy grin along each side of the muzzle, turning up at the back corner, projected from the side."""
    out = Mesh()
    zy = [(1.22, -0.55), (1.06, -0.57), (0.92, -0.545), (0.82, -0.49)]
    for side in (1, -1):
        # a projector on the +x side looking -x has its "right" along -z, and the mirror on -x along +z
        pts = [(-side * z, y) for z, y in zy]
        out.extend(decals(muzzle, stroke(pts, 0.04), INK, origin=(side * 5.0, 0.0, 0.0),
                          forward=(-side, 0.0, 0.0), layer=1))
    return out


def _cheek_tufts():
    side = Mesh()
    for base, tip, r, col in [((0.86, -0.22, 0.10), (1.30, -0.42, -0.14), 0.20, GOLD),
                              ((0.78, -0.48, 0.16), (1.16, -0.76, -0.04), 0.18, CREAM)]:
        side.extend(cone_between(base, tip, r, 0.0, 3, col))
    return merge(side, side.mirrored("x"))


# ---- eyes and face marks ---------------------------------------------------------------------------
EYE_ANGLE = 33.0
EYE_Y = 0.06
EYE_R = 0.25


def _eye_kw(head, side):
    a = math.radians(EYE_ANGLE * side)
    out_dir = (math.sin(a), 0.0, math.cos(a))
    start = (out_dir[0] * 3.0, EYE_Y, out_dir[2] * 3.0)
    hit = head.raycast(start, (-out_dir[0], 0.0, -out_dir[2]))
    n = head.normal(hit[1])
    point = (start[0] - out_dir[0] * hit[0], EYE_Y, start[2] - out_dir[2] * hit[0])
    origin = (point[0] + n[0] * 2.0, point[1] + n[1] * 2.0, point[2] + n[2] * 2.0)
    return {"origin": origin, "forward": (-n[0], -n[1], -n[2])}


def _eye(head, side):
    """A friendly eye: open on top, the lower lid pushed up by the grin."""
    kw = _eye_kw(head, side)

    def shaped(outline):
        return clip_halfplane(clip_halfplane(outline, (0.0, -0.15), (0.0, -1.0)), (0.0, 0.19), (0.0, 1.0))

    inward = -0.02 * side
    out = decal(head, shaped(ngon(18, EYE_R)), "#ffffff", layer=1, **kw)
    iris = ngon(14, 0.19, cx=inward, cy=0.0)
    out.extend(decal(head, shaped(iris), IRIS, layer=2, **kw))
    out.extend(decal(head, shaped(clip_halfplane(iris, (0.0, 0.05), (0.0, -1.0))), IRIS_LO, layer=3, **kw))
    out.extend(decal(head, ngon(8, 0.08, 0.10, cx=inward, cy=0.0), INK, layer=4, **kw))
    out.extend(decal(head, ngon(4, 0.045, cx=inward - 0.075, cy=0.06), "#ffffff", layer=5, flags=UNLIT, **kw))
    # upper lid line with a little flick at the outer corner
    x0, x1 = -EYE_R, EYE_R
    pts = [(x0 + 0.02, 0.10), (-0.10, 0.19), (0.10, 0.19), (x1 - 0.02, 0.10)]
    if side > 0:
        pts.append((x1 + 0.06, 0.15))
    else:
        pts.insert(0, (x0 - 0.06, 0.15))
    out.extend(decals(head, stroke(pts, 0.034), INK, layer=5, **kw))
    # brow dot, above the eye towards the inner corner
    out.extend(decal(head, ngon(6, 0.07, 0.06, cx=-0.04 * side, cy=0.40), BROWN, layer=1, **kw))
    # freckles: a scatter of small dots below the outer corner of the eye, across the cheek
    for fx, fy in [(0.06, -0.34), (0.18, -0.30), (0.28, -0.38), (0.12, -0.46), (0.24, -0.50), (0.36, -0.28)]:
        out.extend(decal(head, ngon(5, 0.032, cx=fx * side, cy=fy), BROWN, layer=1, **kw))
    return out


# ---- ears: small and upright -----------------------------------------------------------------------
EAR_H = 1.12
EAR_TILT = 13.0
EAR_TURN = 16.0
EAR_SEAT = (0.50, 0.50, -0.12)
#               v     half-width back   cup
EAR_LEVELS = [(0.00, 0.40, 0.18, 0.05),
              (0.18, 0.43, 0.20, 0.11),
              (0.40, 0.37, 0.17, 0.11),
              (0.62, 0.27, 0.13, 0.08),
              (0.82, 0.15, 0.08, 0.04),
              (0.94, 0.06, 0.03, 0.01)]
EAR_BACK_BROWN = 2       # the back is brown-gold from this level up
EAR_TIP_BROWN = 3        # the front rim (the tip) is brown-gold from this level up


def _ear():
    rings = []
    for v, hw, back, cup in EAR_LEVELS:
        y = v * EAR_H
        rings.append([(0.0, y, -cup),
                      (0.68 * hw, y, -cup * 0.45),
                      (hw, y, 0.0),
                      (0.50 * hw, y, -back),
                      (-0.50 * hw, y, -back),
                      (-hw, y, 0.0),
                      (-0.68 * hw, y, -cup * 0.45)])

    def colour(k, i):
        if i in (0, 6):
            return CREAM
        if i in (1, 5):
            return BROWN if k >= EAR_TIP_BROWN else GOLD
        return BROWN if k >= EAR_BACK_BROWN else GOLD

    return loft(rings, colour, cap_end=(0.0, EAR_H, -0.02), alternate=False,
                cap_color=lambda k, i: BROWN)


def _ear_fluff():
    out = Mesh()
    for base, tip, r in [((-0.10, 0.06, 0.02), (-0.16, 0.42, 0.08), 0.09),
                         ((0.10, 0.06, 0.02), (0.18, 0.36, 0.08), 0.08)]:
        out.extend(cone_between(base, tip, r, 0.0, 3, CREAM))
    return out


def _ears():
    right = merge(_ear(), _ear_fluff())
    right.rotate_y(EAR_TURN).rotate_x(-6).rotate_z(-EAR_TILT).translate(*EAR_SEAT)
    return merge(right, right.mirrored("x"))


def _crown():
    """A short tuft of golden fur on the crown and two at the nape, so the head is not bald from behind."""
    out = Mesh()
    for base, tip, r in [((0.0, 0.72, 0.15), (0.06, 0.98, 0.30), 0.16),
                         ((0.0, 0.55, -0.55), (0.0, 0.62, -0.92), 0.18)]:
        out.extend(cone_between(base, tip, r, 0.0, 3, GOLD))
    return out


# ---- neck, shoulders, sky-blue tee, saddle --------------------------------------------------------
TORSO_RINGS = [(BASE_Y, 0.96, 0.54),
               (-1.95, 1.06, 0.60),
               (-1.62, 1.10, 0.57),
               (-1.40, 0.90, 0.50),
               (-1.24, 0.58, 0.44),
               (-1.17, 0.46, 0.40)]
NECKLINE_BACK = -1.66    # the tee's back neckline: faces above this, behind, are fur


def _neck():
    m = cone_between((0.0, -0.55, 0.0), (0.0, -1.32, 0.0), 0.40, 0.46, 10, GOLD)
    m.paint(CREAM, lambda c, n, i: n[2] > 0.55 and c[1] < -0.62)        # cream throat
    return m


def _torso():
    rings = [ring(y, rx, rz, SEG) for y, rx, rz in TORSO_RINGS]
    top = len(TORSO_RINGS) - 2
    m = loft(rings, lambda k, i: TEE_SHADE if k == top else TEE, cap_start=True, cap_end=True,
             cap_color=TEE_SHADE, alternate="facet")
    # low back neckline: the nape and upper back are fur (where the saddle is)
    m.paint(GOLD, lambda c, n, i: c[1] > NECKLINE_BACK and c[2] < -0.12)
    m.paint(GOLD, lambda c, n, i: c[1] > -1.30)                          # the cap round the neck
    return m


def _saddle(neck, torso):
    """Short mottled dashes (black, grey, brown-gold) scattered over the nape and upper back."""
    out = Mesh()
    colours = (SADDLE_BLACK, SADDLE_GREY, BROWN)
    seed = 7
    # projector behind the model looking forward: its "right" is -x, which does not matter here
    kw = {"origin": (0.0, 0.0, -10.0), "forward": (0.0, 0.0, 1.0)}
    placed = 0
    for row in range(9):
        y = -0.80 - row * 0.105
        half = 0.20 + 0.06 * row if y > -1.30 else 0.52 + 0.02 * row
        count = 3 if y > -1.30 else 5
        for j in range(count):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            jitter = ((seed >> 8) % 100) / 100.0 - 0.5
            x = -half + (2.0 * half) * (j + 0.5 + 0.5 * jitter) / count
            target = neck if y > -1.24 else torso
            dash = ngon(5, 0.045, 0.085, cx=x, cy=y + 0.03 * jitter, rot=20.0 * jitter)
            try:
                out.extend(decal(target, dash, colours[(row + j + (seed >> 12)) % 3], layer=1, **kw))
                placed += 1
            except ValueError:
                pass
    return out


def _sleeves():
    p0, p1 = (0.96, -1.52, 0.0), (1.32, -1.94, 0.03)
    axis = v_norm((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
    p2 = (p1[0] + axis[0] * 0.17, p1[1] + axis[1] * 0.17, p1[2] + axis[2] * 0.17)
    s = cone_between(p0, p1, 0.35, 0.30, 8, TEE, squash=0.88)
    s.paint(TEE_SHADE, lambda c, n, i: v_dot(n, axis) > 0.9)
    s.extend(cone_between(p1, p2, 0.22, 0.21, 8, GOLD, squash=0.9))
    return merge(s, s.mirrored("x"))


def _shoulder_freckles(neck):
    """A few freckles where the neck meets the shoulders, front side."""
    out = Mesh()
    for x, y in [(0.30, -1.12), (0.36, -1.02), (-0.30, -1.10), (-0.35, -1.00)]:
        out.extend(decal(neck, ngon(5, 0.028, cx=x, cy=y), BROWN, layer=1))
    return out


# ---- assembly --------------------------------------------------------------------------------------
NECK_PIVOT = (0.0, -0.80, 0.0)


@lru_cache(maxsize=None)
def parts():
    head = _head()
    muzzle = _muzzle()
    neck = _neck()
    torso = _torso()
    top = merge(head, muzzle, _nose(), _grin(muzzle), _cheek_tufts(), _eye(head, 1), _eye(head, -1),
                _ears(), _crown())
    bottom = merge(neck, torso, _saddle(neck, torso), _shoulder_freckles(neck), _sleeves())
    return top, bottom


@lru_cache(maxsize=64)
def build(turn=0.0, nod=0.0, tilt=0.0):
    """The whole bust as one mesh (cached, read-only). Pose as in ``nova.build``."""
    head, body = parts()
    if turn or nod or tilt:
        px, py, pz = NECK_PIVOT
        pose = compose(translate(-px, -py, -pz), rot_z(tilt), rot_x(nod), rot_y(turn), translate(px, py, pz))
        head = head.copy().transform(pose)
    return merge(head, body)


# ---- scenes ----------------------------------------------------------------------------------------
def _shadow(x=0.0, r=(1.20, 0.88)):
    return Shadow(center=(x, BASE_Y, 0.0), radius=r, opacity=0.30)


def _stage(cam, shadow=True):
    return Scene(cam, house_lighting(), shadow=_shadow() if shadow else None, outline=house_outline())


def _sparkles(items):
    out = Mesh()
    for (x, y, z), size, colour in items:
        out.extend(star4(size, 0.34, size * 0.5, colour, colour).rotate_y(-20).translate(x, y, z))
    return out


def _wide_camera():
    return Camera(target=(0.0, 0.13, 0.0), pitch=7.0, distance=17.0, fov=17.9)


def bust_scene(i=0, n=1):
    """Hero still: three-quarter view with the head turned back, chin up a little, like Nova's."""
    cam = Camera(target=(0.0, 0.10, 0.0), pitch=7.0, distance=17.0, fov=18.7)
    scene = _stage(cam)
    scene.add(build(turn=14.0, nod=-4.0, tilt=-4.0), rot_y(-36.0))
    scene.add(_sparkles([((-2.05, 1.40, 0.3), 0.20, STAR), ((2.10, 0.50, 0.2), 0.15, STAR_PINK),
                         ((-1.90, -1.00, 0.6), 0.13, STAR_PINK), ((1.55, 1.85, 0.0), 0.11, STAR),
                         ((2.00, -1.40, 0.3), 0.11, STAR)]))
    return scene


def icon_scene(i=0, n=1):
    cam = Camera(target=(0.0, 0.0, 0.0), pitch=3.0, distance=17.0, fov=11.8)
    return _stage(cam, shadow=False).add(build())


def spin_scene(i=0, n=24):
    return _stage(_wide_camera()).add(build(), rot_y(360.0 * i / n))


def view_scene(turn):
    """For checking: the bust turned by ``turn`` degrees under the turntable camera."""
    return _stage(_wide_camera()).add(build(), rot_y(turn))


TRIO_SPACING = 3.75


def trio_scene(i=0, n=1):
    """The three busts side by side: Iggy (left), Nova (centre), Duskie (right), turned a little
    towards the middle. Same distance and ground line for all three, so the sizes are true."""
    from . import iggy, nova           # local import: the job list of this module stays importable alone
    cam = Camera(target=(0.0, 0.18, 0.0), pitch=6.0, distance=17.0, fov=20.0)
    s = TRIO_SPACING
    scene = Scene(cam, house_lighting(), outline=house_outline(),
                  shadow=[_shadow(-s, (0.98, 0.72)), _shadow(0.0, (1.15, 0.85)), _shadow(s)])
    scene.add(iggy.build(turn=-6.0, nod=-2.0, tilt=4.0), compose(rot_y(24.0), translate(-s, 0.0, 0.0)))
    scene.add(nova.build(nod=-2.0), rot_y(0.0))
    scene.add(build(turn=6.0, nod=-2.0, tilt=-3.0), compose(rot_y(-24.0), translate(s, 0.0, 0.0)))
    scene.add(_sparkles([((-5.9, 0.6, 0.0), 0.20, STAR_PINK), ((-1.9, 2.3, 0.0), 0.16, STAR),
                         ((1.95, 2.25, 0.0), 0.17, STAR_PINK), ((5.6, 1.5, 0.0), 0.21, STAR),
                         ((-5.3, -1.2, 0.3), 0.13, STAR), ((5.35, -1.3, 0.3), 0.13, STAR_PINK)]))
    return scene


JOBS = [
    Job("duskie_bust", (512, 512), bust_scene),
    Job("duskie_icon", (256, 256), icon_scene),
    Job("duskie_spin", (192, 192), spin_scene, frames=24, fps=12),
    Job("trio_busts", (1200, 520), trio_scene),
]
