"""NOVA (serval) as a papercraft low-poly bust. Canon: docs/CHARACTERS.md.

The model faces +z; +x is the viewer's right. The head is about 2 units wide and centred on the
origin, the ear tips reach y = +2.6 and the bust is cut flat at y = -2.42.

    build()            the whole bust (cached; do not modify the returned mesh)
    bust_scene() ...   the scene functions behind the render jobs in ``JOBS``

How it is put together (a pattern the other characters can copy):
  * big forms are ``loft``-ed rings, with a flat facet facing the camera (``ring(..., phase=0.5)``)
    so each eye sits on ONE flat facet of the head;
  * the large markings (white lower face, tee collar, inner ears) are painted per facet, by ring
    and segment index or with a region rule (``Mesh.paint``);
  * the small markings (eyes, forehead dashes, freckles, mouth, neck dash, the smiley) are
    ``decal`` patches projected onto the forms.
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..mesh import (UNLIT, Mesh, clip_halfplane, compose, cone_between, decal, decals, facet_angles, icosphere,
                    loft, merge, mirror2d, ngon, polygon, rect, ring, rot_x, rot_y, scale, star4, stroke, translate,
                    v_dot, v_norm)
from ..pipeline import Job
from ..render import Camera, Scene, Shadow, house_lighting
from . import props

# ---- palette (docs/CHARACTERS.md, Nova) -----------------------------------------------------------
NAVY = "#2b2d42"
NAVY_SHADE = "#1b1c30"
WHITE = "#f1eff8"
WHITE_SHADE = "#d9d6ea"
EAR_IN = "#e9e7f7"
EAR_PERI = "#a9b4e6"
IRIS = "#3d8fe0"
IRIS_HI = "#7cc4ff"
IRIS_LO = "#1f6fc4"
NOSE = "#e9cfe2"
TONGUE = "#ee7fa6"
TEE = "#e8894a"
TEE_SHADE = "#cf7137"
SMILEY = "#f7bd45"
SMILEY_INK = "#c98a1e"
STAR = "#fff3b0"
MAGENTA = "#f52fd2"

SEG = 12                 # facets round the head and torso
# Head facet edges on the viewer's right, front to back (degrees). Facet 0 faces the camera,
# facets 1 and 11 (16..52 degrees) are wide and flat: one eye sits on each.
HEAD_ANGLES = facet_angles([16, 52, 80, 108, 136, 164])
EYE_ANGLE = 34.0
FRONT = (0, 1, 2, 10, 11)   # head facets that carry the white lower face
BASE_Y = -2.25           # where the bust is cut


# ---- head -----------------------------------------------------------------------------------------
#             y     rx    rz front  rz back      (bottom to top)
HEAD_RINGS = [(-0.68, 0.66, 0.68, 0.52),
              (-0.44, 0.96, 0.87, 0.74),
              (-0.17, 1.06, 0.91, 0.88),      # the mask line: white below, navy above
              (0.43, 1.03, 0.89, 0.90),       # brow line; the band between is where the eyes sit
              (0.68, 0.80, 0.70, 0.77),
              (0.85, 0.47, 0.40, 0.48)]


def _head():
    def colour(k, i):
        return WHITE if (k < 2 and i in FRONT) else NAVY

    rings = [ring(y, rx, rzf, rz_back=rzb, angles=HEAD_ANGLES) for y, rx, rzf, rzb in HEAD_RINGS]
    return loft(rings, colour, cap_start=(0.0, -0.84, 0.10), cap_end=(0.0, 0.95, -0.02), alternate="facet",
                cap_color=lambda k, i: WHITE if (k < 0 and i in FRONT) else NAVY)


def _muzzle():
    m = icosphere((0.48, 0.31, 0.36), 1, WHITE).translate(0.0, -0.41, 0.73)
    # the bridge of the nose stays navy: the muzzle faces that look upwards, near the middle
    m.paint(NAVY, lambda c, n, i: n[1] > 0.45 and abs(c[0]) < 0.17)
    return m


def _nose():
    r = ring(0.03, 0.115, 0.06, 6)
    return loft([r, r], NOSE, cap_start=(0.0, -0.085, 0.015), cap_end=(0.0, 0.06, -0.02)).translate(0.0, -0.265, 1.045)


def _mouth(muzzle):
    out = decals(muzzle, stroke([(0.0, -0.355), (0.0, -0.465)], 0.028), NAVY_SHADE)
    smirk = [(-0.245, -0.425), (-0.125, -0.525), (0.0, -0.465), (0.125, -0.525), (0.255, -0.405)]
    out.extend(decals(muzzle, stroke(smirk, 0.03), NAVY_SHADE))
    out.extend(decal(muzzle, ngon(6, 0.06, 0.07, cx=0.0, cy=-0.56), TONGUE, layer=1))        # blep
    return out


def _cheek_tufts():
    """A white spike on each cheek where the mask line flares, with a smaller navy one above it."""
    big = cone_between((0.80, -0.38, 0.24), (1.30, -0.56, 0.10), 0.19, 0.0, 4, WHITE, squash=1.6)
    low = cone_between((0.72, -0.54, 0.30), (1.06, -0.78, 0.20), 0.14, 0.0, 4, WHITE, squash=1.4)
    small = cone_between((0.90, -0.06, 0.14), (1.25, -0.11, 0.0), 0.11, 0.0, 4, NAVY, squash=1.5)
    side = merge(big, low, small)
    return merge(side, side.mirrored("x"))


def _whiskers():
    side = Mesh()
    for tip in [(1.02, -0.19, 0.64), (1.10, -0.41, 0.60), (0.98, -0.63, 0.62)]:
        base = (0.40, -0.39 + (tip[1] + 0.41) * 0.15, 0.91)
        side.extend(polygon([(base[0], base[1] - 0.012, base[2]), tip, (base[0], base[1] + 0.012, base[2])],
                            WHITE, two_sided=True))
    return merge(side, side.mirrored("x"))


# ---- eyes -----------------------------------------------------------------------------------------
EYE_Y = 0.13       # height of the eye centre: the middle of the band between the mask and brow lines
EYE_R = 0.295


def _eye(head, side):
    """One half-lidded eye on the wide head facet. ``side`` is +1 (viewer's right) or -1."""
    a = math.radians(EYE_ANGLE * side)
    out_dir = (math.sin(a), 0.0, math.cos(a))
    start = (out_dir[0] * 3.0, EYE_Y, out_dir[2] * 3.0)
    hit = head.raycast(start, (-out_dir[0], 0.0, -out_dir[2]))
    n = head.normal(hit[1])                         # shoot along the facet's own normal: no distortion
    point = (start[0] - out_dir[0] * hit[0], EYE_Y, start[2] - out_dir[2] * hit[0])
    origin = (point[0] + n[0] * 2.0, point[1] + n[1] * 2.0, point[2] + n[2] * 2.0)
    kw = {"origin": origin, "forward": (-n[0], -n[1], -n[2])}

    # the upper lid is a straight line through (0, 0.02) that droops a hair towards the outer corner
    # (relaxed and smug, not cross); the lower lid pushes up a little, the way a pleased cat squints
    lid_p, lid_slope = (0.0, 0.035), -0.035 * side
    lid_n = _unit2((-lid_slope, 1.0))

    def lidded(outline):
        return clip_halfplane(clip_halfplane(outline, lid_p, lid_n), (0.0, -0.25), (0.0, -1.0))

    inward = -0.025 * side
    out = decal(head, lidded(ngon(20, EYE_R)), WHITE, layer=1, **kw)
    iris = ngon(16, 0.225, cx=inward, cy=-0.06)
    out.extend(decal(head, lidded(iris), IRIS, layer=2, **kw))
    out.extend(decal(head, lidded(clip_halfplane(iris, (0.0, -0.155), (0.0, 1.0))), IRIS_HI, layer=3, **kw))
    out.extend(decal(head, lidded(ngon(8, 0.082, 0.135, cx=inward, cy=-0.065)), NAVY_SHADE, layer=4, **kw))
    out.extend(decal(head, ngon(4, 0.052, cx=inward - 0.095, cy=-0.04), "#ffffff", layer=5, flags=UNLIT, **kw))
    x0, x1 = -EYE_R + 0.01, EYE_R - 0.01
    if side > 0:
        x1 += 0.055     # a little flick past the outer corner
    else:
        x0 -= 0.055
    line = [(x0, lid_p[1] + lid_slope * x0), (x1, lid_p[1] + lid_slope * x1)]
    out.extend(decals(head, stroke(line, 0.036), NAVY_SHADE, layer=5, **kw))
    # freckles: three tiny white dots at the outer corner
    for fx, fy in [(0.375, -0.12), (0.435, -0.19), (0.445, -0.045)]:
        out.extend(decal(head, ngon(4, 0.036, cx=fx * side, cy=fy), WHITE, layer=1, **kw))
    return out


def _unit2(v):
    ln = math.hypot(v[0], v[1])
    return (v[0] / ln, v[1] / ln)


def _forehead(head):
    """Two white vertical dashes above the inner corners of the eyes, and a small wedge behind."""
    out = Mesh()
    for side in (1, -1):
        dash = ngon(6, 0.05, 0.19, cx=0.17, cy=0.665, rot=-5.0)
        if side < 0:
            dash = mirror2d(dash)
        out.extend(decal(head, dash, WHITE, layer=1, detail=2))
    # the reference sheet's back view has a small white wedge at the crown, between the ears
    wedge = [(0.0, 0.56), (0.075, 0.87), (-0.075, 0.87)]
    out.extend(decal(head, wedge, WHITE, origin=(0.0, 0.0, -10.0), forward=(0.0, 0.0, 1.0), layer=1, detail=2))
    return out


# ---- ears: the star of the show --------------------------------------------------------------------
EAR_H = 1.95
#               v     half-width  back   cup    (v is the fraction of EAR_H; depths are how far the
EAR_LEVELS = [(0.00, 0.36, 0.22, 0.04, 0.36),      # back bulges and how deep the inner cup is; the last
              (0.12, 0.50, 0.28, 0.12, 0.46),      # column is how much of the half-width the periwinkle
              (0.30, 0.62, 0.29, 0.16, 0.48),      # patch takes at that level)
              (0.50, 0.66, 0.25, 0.15, 0.40),
              (0.70, 0.60, 0.20, 0.12, 0.22),
              (0.86, 0.45, 0.14, 0.08, 0.20),
              (0.96, 0.25, 0.09, 0.04, 0.20)]
EAR_PERI_TOP = 4          # the periwinkle patch fills the middle of the cup up to this level


def _ear():
    """The viewer's-right ear, base at the origin, pointing up, cup facing +z.

    Each level is a 9-point crescent: cup centre, periwinkle edge, pale edge, rim (right), two
    points round the back, rim (left), pale edge, periwinkle edge.
    """
    rings = []
    for v, hw, back, cup, peri in EAR_LEVELS:
        y = v * EAR_H
        lean = 0.06 * math.sin(v * math.pi)             # the outer edge bows out a little more
        rings.append([(lean, y, -cup),
                      (lean + peri * hw, y, -cup * 0.80),
                      (lean + 0.80 * hw, y, -cup * 0.30),
                      (lean + hw, y, 0.0),
                      (lean + 0.52 * hw, y, -back),
                      (lean - 0.52 * hw, y, -back),
                      (lean - hw, y, 0.0),
                      (lean - 0.80 * hw, y, -cup * 0.30),
                      (lean - peri * hw, y, -cup * 0.80)])

    def colour(k, i):
        if i in (0, 8):
            return EAR_PERI if k < EAR_PERI_TOP else EAR_IN
        if i in (1, 7):
            return EAR_IN
        return NAVY

    tip = (0.03, EAR_H, -0.03)
    return loft(rings, colour, cap_end=tip, alternate=False,
                cap_color=lambda k, i: EAR_IN if i in (0, 1, 7, 8) else NAVY)


def _ear_hairs():
    """Three long fine hairs sweeping up from the inner edge of the (viewer's right) ear, in ear space."""
    out = Mesh()
    for (bx, by), (tx, ty) in [((-0.40, 0.50), (-0.14, 1.30)), ((-0.36, 0.44), (0.02, 1.06)),
                               ((-0.30, 0.38), (0.12, 0.80))]:
        out.extend(polygon([(bx - 0.017, by, 0.02), (bx + 0.017, by, 0.02), (tx, ty, 0.02)], NAVY, two_sided=True))
    return out


def _ears():
    right = merge(_ear(), _ear_hairs())
    # turn the cup slightly outwards, lean it back a little, tip it outwards, then seat it in the head
    right.rotate_y(22).rotate_x(-7).rotate_z(-20).translate(0.50, 0.52, -0.06)
    return merge(right, right.mirrored("x"))


# ---- neck and the orange tee -----------------------------------------------------------------------
#               y      rx    rz       (bottom to top)
TORSO_RINGS = [(BASE_Y, 0.88, 0.50),
               (-1.95, 0.98, 0.55),
               (-1.62, 1.02, 0.52),
               (-1.40, 0.82, 0.46),
               (-1.24, 0.50, 0.40),
               (-1.17, 0.40, 0.36)]


def _neck():
    return cone_between((0.0, -0.60, 0.0), (0.0, -1.30, 0.0), 0.32, 0.36, 10, NAVY)


def _neck_dashes(neck):
    out = decal(neck, rect(0.24, 0.07, cx=0.0, cy=-0.99), WHITE, layer=1, detail=2)
    a = math.radians(52.0)                       # a second, shorter dash round the side
    d = (math.sin(a), 0.0, math.cos(a))
    out.extend(decal(neck, rect(0.15, 0.06, cx=0.0, cy=-1.08), WHITE, origin=(d[0] * 5.0, 0.0, d[2] * 5.0),
                     forward=(-d[0], 0.0, -d[2]), layer=1))
    return out


def _torso():
    rings = [ring(y, rx, rz, SEG) for y, rx, rz in TORSO_RINGS]
    top = len(TORSO_RINGS) - 2
    return loft(rings, lambda k, i: TEE_SHADE if k == top else TEE, cap_start=True, cap_end=True,
                cap_color=TEE_SHADE, alternate="facet")


def _sleeves():
    p0, p1 = (0.86, -1.55, 0.0), (1.20, -1.95, 0.03)
    axis = v_norm((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
    p2 = (p1[0] + axis[0] * 0.17, p1[1] + axis[1] * 0.17, p1[2] + axis[2] * 0.17)
    s = cone_between(p0, p1, 0.33, 0.28, 8, TEE, squash=0.88)
    s.paint(TEE_SHADE, lambda c, n, i: v_dot(n, axis) > 0.9)        # the sleeve opening
    s.extend(cone_between(p1, p2, 0.20, 0.19, 8, NAVY, squash=0.9))  # a stub of navy arm
    return merge(s, s.mirrored("x"))


def _smiley(torso):
    cx, cy, r = 0.0, -1.86, 0.25
    out = decal(torso, ngon(12, r, cx=cx, cy=cy), SMILEY, layer=1, detail=2)
    for ex in (-0.088, 0.088):
        out.extend(decal(torso, ngon(6, 0.027, 0.052, cx=cx + ex, cy=cy + 0.06), SMILEY_INK, layer=2))
    smile = [(cx + 0.152 * math.sin(math.radians(a)), cy - 0.01 - 0.138 * math.cos(math.radians(a)))
             for a in (-62, -31, 0, 31, 62)]
    out.extend(decals(torso, stroke(smile, 0.032), SMILEY_INK, layer=2))
    return out


# ---- assembly --------------------------------------------------------------------------------------
@lru_cache(maxsize=None)
def build():
    """The whole bust as one mesh. Cached: treat the result as read-only."""
    head = _head()
    muzzle = _muzzle()
    neck = _neck()
    torso = _torso()
    return merge(head, muzzle, _nose(), _mouth(muzzle), _cheek_tufts(), _whiskers(),
                 _eye(head, 1), _eye(head, -1), _forehead(head), _ears(),
                 neck, _neck_dashes(neck), torso, _sleeves(), _smiley(torso))


def bounds():
    return build().bounds()


# ---- scenes ----------------------------------------------------------------------------------------
def _ground(radius=(1.15, 0.85), opacity=0.30):
    return Shadow(center=(0.0, BASE_Y, 0.0), radius=radius, opacity=opacity)


def _sparkles(seed_positions):
    out = Mesh()
    for (x, y, z), size, colour in seed_positions:
        out.extend(star4(size, 0.34, size * 0.5, colour, colour).rotate_y(-20).translate(x, y, z))
    return out


def bust_scene(i=0, n=1):
    """The hero still: three-quarter view, turned towards the key light, a few sparkles."""
    cam = Camera(target=(0.0, 0.10, 0.0), pitch=7.0, distance=17.0, fov=19.5)
    scene = Scene(cam, house_lighting(), shadow=_ground())
    scene.add(build(), rot_y(-32.0))
    scene.add(_sparkles([((-1.95, 1.55, 0.3), 0.20, STAR), ((1.92, 0.55, 0.2), 0.14, "#ffd1ea"),
                         ((-1.75, -0.95, 0.6), 0.12, "#ffd1ea"), ((1.72, 2.25, -0.2), 0.11, STAR)]))
    return scene


def icon_scene(i=0, n=1):
    """App icon: straight on, cropped to the head, ears and shoulders."""
    cam = Camera(target=(0.0, 0.55, 0.0), pitch=3.0, distance=17.0, fov=15.6)
    return Scene(cam, house_lighting()).add(build())


def spin_scene(i=0, n=24):
    """Turntable: the camera and lights stay put, the bust turns one full circle."""
    cam = Camera(target=(0.0, 0.04, 0.0), pitch=7.0, distance=17.0, fov=18.0)
    scene = Scene(cam, house_lighting(), shadow=_ground())
    return scene.add(build(), rot_y(360.0 * i / n))


def sync_scene(i=0, n=24):
    """The copy-to-card loop: a disc orbits his head once, and he follows it a little with his nose."""
    t = 2.0 * math.pi * i / n
    cam = Camera(target=(0.0, 0.04, 0.0), pitch=7.0, distance=17.0, fov=18.4)
    scene = Scene(cam, house_lighting(), shadow=_ground())
    scene.add(build(), rot_y(11.0 * math.sin(t)))
    # the orbit is tilted so the disc passes in front at collar height and behind at ear height
    radius, tilt = 2.40, math.radians(27.0)
    x, z = radius * math.sin(t), radius * math.cos(t)
    y = 0.10 - z * math.tan(tilt)
    scene.add(props.disc(spin=-2.0 * 360.0 * i / n), compose(scale(0.60), rot_x(-62.0), translate(x, y, z)))
    return scene


JOBS = [
    Job("nova_bust", (512, 512), bust_scene),
    Job("nova_icon", (256, 256), icon_scene),
    Job("nova_spin", (192, 192), spin_scene, frames=24, fps=12),
    Job("sync_loop", (256, 192), sync_scene, frames=24, fps=12),
]
