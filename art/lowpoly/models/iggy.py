"""IGGY (fennec fox) as a papercraft low-poly bust. Canon: docs/CHARACTERS.md (Iggy).

Built the same way as ``nova.py`` (read that first): lofted head with a flat facet under each eye,
markings as painted facets or ``decal`` patches, the same cameras and lighting, so the busts read
as one set. Iggy is the smaller one: the head is about 0.87 of Nova's and sits a little lower, but
the bust is cut at the same height (``BASE_Y``) so they share a ground line.

    build(turn, nod, tilt)   the whole bust (cached; do not modify the returned mesh)
    JOBS                     iggy_bust, iggy_icon, iggy_spin

The model faces +z; +x is the viewer's right (Iggy's own left).
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..mesh import (UNLIT, Mesh, clip_halfplane, compose, cone_between, decal, decals, facet_angles, icosphere,
                    loft, merge, ngon, polygon, prism, ring, rot_x, rot_y, rot_z, scale, star4, stroke, translate, tube,
                    v_cross, v_dot, v_norm)
from ..pipeline import Job
from ..render import Camera, Scene, Shadow, house_lighting, house_outline

# ---- palette (docs/CHARACTERS.md, Iggy) -----------------------------------------------------------
FUR = "#d2b48c"
FUR_LIGHT = "#e6d3b3"
FUR_SHADE = "#b89a70"
PERI = "#7582b5"
PERI_DARK = "#5a6699"
IRIS = "#5aa04c"
IRIS_HI = "#8ed07a"
NOSE = "#4a4648"
PINK = "#f7a8c4"          # tongue
FRAME = "#1c1b22"         # glasses
LENS = "#dfeaf7"          # the pale lens sheen (a solid stand-in for 25% white)
GLINT = "#ffffff"
TEE = "#24222b"
TEE_SHADE = "#15141b"
FEATHER = "#9aa0a8"
CORD = "#6f747c"
STAR = "#fff3b0"
STAR_PINK = "#ffd1ea"

BASE_Y = -2.25            # same cut as Nova, so the busts share a ground line
HEAD_ANGLES = facet_angles([16, 50, 80, 108, 136, 164])
FRONT = (0, 1, 2, 10, 11)

# ---- head -----------------------------------------------------------------------------------------
#             y     rx    rz front  rz back      (bottom to top)
HEAD_RINGS = [(-0.80, 0.52, 0.56, 0.44),
              (-0.58, 0.84, 0.76, 0.64),
              (-0.32, 0.95, 0.80, 0.76),      # cheeks: widest
              (0.20, 0.87, 0.76, 0.78),       # brow line; the eyes sit in the band below
              (0.42, 0.68, 0.61, 0.67),
              (0.58, 0.40, 0.36, 0.42)]


def _head():
    def colour(k, i):
        return FUR_LIGHT if (k == 0 and i in FRONT) else FUR

    rings = [ring(y, rx, rzf, rz_back=rzb, angles=HEAD_ANGLES) for y, rx, rzf, rzb in HEAD_RINGS]
    return loft(rings, colour, cap_start=(0.0, -0.92, 0.08), cap_end=(0.0, 0.66, -0.02), alternate="facet",
                cap_color=lambda k, i: FUR_LIGHT if (k < 0 and i in FRONT) else FUR)


MUZZLE_BASE = (0.0, -0.40, 0.44)
MUZZLE_TIP = (0.0, -0.50, 1.14)


def _muzzle():
    """A short pointed fox muzzle: a squashed cone, pale underneath, tan on top."""
    m = cone_between(MUZZLE_BASE, MUZZLE_TIP, 0.36, 0.10, 8, FUR, cap_start=False)
    y0 = MUZZLE_BASE[1]
    m.warp(lambda p: (p[0] * 1.05, y0 + (p[1] - y0) * 0.88, p[2]))
    m.paint(FUR_LIGHT, lambda c, n, i: n[1] < 0.15)
    return m


def _nose():
    return icosphere((0.115, 0.08, 0.075), 0, NOSE).translate(MUZZLE_TIP[0], MUZZLE_TIP[1] + 0.03, MUZZLE_TIP[2])


def _mouth(muzzle):
    out = decals(muzzle, stroke([(0.0, -0.505), (0.0, -0.565)], 0.026), TEE_SHADE)
    smile = [(-0.19, -0.55), (-0.10, -0.60), (0.0, -0.565), (0.10, -0.60), (0.20, -0.54)]
    out.extend(decals(muzzle, stroke(smile, 0.028), TEE_SHADE))
    # a small fang on Iggy's left (viewer's right), pointing down from the smile
    out.extend(decal(muzzle, [(0.072, -0.597), (0.122, -0.594), (0.10, -0.648)], "#ffffff", layer=2))
    out.extend(decal(muzzle, ngon(6, 0.045, 0.045, cx=-0.05, cy=-0.618), PINK, layer=1))     # tiny blep
    return out


def _cheek_ruffs():
    """Big fluffy cheek ruffs: a fan of flat spikes, tan with pale undersides."""
    side = icosphere((0.34, 0.36, 0.30), 1, FUR).rotate_z(20).translate(0.70, -0.46, 0.14)
    side.paint(FUR_LIGHT, lambda c, n, i: n[1] < -0.35)
    for base, tip, r, col in [((0.74, -0.16, 0.20), (1.30, -0.32, 0.02), 0.26, FUR),
                              ((0.74, -0.44, 0.22), (1.30, -0.78, 0.04), 0.27, FUR),
                              ((0.56, -0.66, 0.30), (0.88, -1.08, 0.24), 0.22, FUR_LIGHT)]:
        side.extend(cone_between(base, tip, r, 0.0, 3, col))
    return merge(side, side.mirrored("x"))


# ---- eyes, glasses and face marks ------------------------------------------------------------------
EYE_ANGLE = 33.0
EYE_Y = -0.08
EYE_R = 0.255


def _eye_frame(head, side):
    """``(point, normal)`` where the eye of ``side`` (+1 viewer's right) sits on its head facet."""
    a = math.radians(EYE_ANGLE * side)
    out_dir = (math.sin(a), 0.0, math.cos(a))
    start = (out_dir[0] * 3.0, EYE_Y, out_dir[2] * 3.0)
    hit = head.raycast(start, (-out_dir[0], 0.0, -out_dir[2]))
    n = head.normal(hit[1])
    point = (start[0] - out_dir[0] * hit[0], EYE_Y, start[2] - out_dir[2] * hit[0])
    return point, n


def _eye(head, side):
    point, n = _eye_frame(head, side)
    origin = (point[0] + n[0] * 2.0, point[1] + n[1] * 2.0, point[2] + n[2] * 2.0)
    kw = {"origin": origin, "forward": (-n[0], -n[1], -n[2])}

    def lidded(outline):        # a soft, unimpressed upper lid
        return clip_halfplane(outline, (0.0, 0.13), (0.0, 1.0))

    inward = -0.02 * side
    out = decal(head, lidded(ngon(18, EYE_R)), "#ffffff", layer=1, **kw)
    iris = ngon(14, 0.20, cx=inward, cy=-0.035)
    out.extend(decal(head, lidded(iris), IRIS, layer=2, **kw))
    out.extend(decal(head, lidded(clip_halfplane(iris, (0.0, -0.12), (0.0, 1.0))), IRIS_HI, layer=3, **kw))
    out.extend(decal(head, lidded(ngon(8, 0.085, 0.11, cx=inward, cy=-0.04)), TEE_SHADE, layer=4, **kw))
    out.extend(decal(head, ngon(4, 0.045, cx=inward - 0.08, cy=0.0), "#ffffff", layer=5, flags=UNLIT, **kw))
    lid = [(-EYE_R + 0.02, 0.13), (EYE_R - 0.02, 0.13)]
    out.extend(decals(head, stroke(lid, 0.034), TEE_SHADE, layer=5, **kw))
    # the short periwinkle mark under each eye, sweeping out towards the ruff
    mark = [(-0.05 * side, -0.31), (0.10 * side, -0.33), (0.24 * side, -0.27)]
    out.extend(decals(head, stroke(mark, 0.075), PERI, layer=1, **kw))
    return out


def _forehead(head):
    """Three small periwinkle dots in an arc and a small diamond below them, between the eyes."""
    out = Mesh()
    for x, y in [(-0.12, 0.25), (0.0, 0.30), (0.12, 0.25)]:
        out.extend(decal(head, ngon(5, 0.045, cx=x, cy=y), PERI, layer=1))
    out.extend(decal(head, [(0.0, 0.07), (0.055, 0.15), (0.0, 0.23), (-0.055, 0.15)], PERI, layer=1))
    return out


LENS_OUT = 0.335
LENS_IN = 0.29
LENS_PROUD = 0.10          # how far the lenses stand off the face


def _lens_basis(n):
    """Right/up unit vectors in the plane of a lens whose outward normal is ``n``."""
    u = v_norm(v_cross((0.0, 1.0, 0.0), n))
    v = v_cross(n, u)
    return u, v


def _to3(c, u, v, n, x, y, lift=0.0):
    return (c[0] + u[0] * x + v[0] * y + n[0] * lift,
            c[1] + u[1] * x + v[1] * y + n[1] * lift,
            c[2] + u[2] * x + v[2] * y + n[2] * lift)


def _rim(c, u, v, n, r_out, r_in, depth, segs, color):
    """A flat round frame (an annulus with thickness) centred on ``c``, facing ``n``."""
    m = Mesh()
    h = depth / 2.0
    for j in range(segs):
        a0 = 2.0 * math.pi * j / segs
        a1 = 2.0 * math.pi * (j + 1) / segs
        o0 = (math.cos(a0), math.sin(a0))
        o1 = (math.cos(a1), math.sin(a1))
        fo0, fo1 = _to3(c, u, v, n, o0[0] * r_out, o0[1] * r_out, h), _to3(c, u, v, n, o1[0] * r_out, o1[1] * r_out, h)
        fi0, fi1 = _to3(c, u, v, n, o0[0] * r_in, o0[1] * r_in, h), _to3(c, u, v, n, o1[0] * r_in, o1[1] * r_in, h)
        bo0, bo1 = _to3(c, u, v, n, o0[0] * r_out, o0[1] * r_out, -h), _to3(c, u, v, n, o1[0] * r_out, o1[1] * r_out, -h)
        bi0, bi1 = _to3(c, u, v, n, o0[0] * r_in, o0[1] * r_in, -h), _to3(c, u, v, n, o1[0] * r_in, o1[1] * r_in, -h)
        m.add_tri(fi0, fo0, fo1, color).add_tri(fi0, fo1, fi1, color)        # front face
        m.add_tri(bo0, bi0, bi1, color).add_tri(bo0, bi1, bo1, color)        # back face
        m.add_tri(fo0, bo0, bo1, color).add_tri(fo0, bo1, fo1, color)        # outer edge
        m.add_tri(bi0, fi0, fi1, color).add_tri(bi0, fi1, bi1, color)        # inner edge
    return m


def _glasses(head):
    """Round thin black frames standing proud of the face, a pale sheen and a glint on each lens,
    a bridge over the nose and temple arms running back to the ears."""
    out = Mesh()
    inner_pts = {}
    for side in (1, -1):
        point, n = _eye_frame(head, side)
        # stand the lens a little proud, and turn it a touch more to the front than the facet
        n = v_norm((n[0] * 0.8, n[1] * 0.5, n[2] + 0.25))
        c = (point[0] + n[0] * LENS_PROUD, point[1] + 0.01, point[2] + n[2] * LENS_PROUD)
        u, v = _lens_basis(n)
        out.extend(_rim(c, u, v, n, LENS_OUT, LENS_IN, 0.045, 12, FRAME))
        # the lens itself: two diagonal sheen bands clipped to the circle, so the eye shows through
        disc = ngon(12, LENS_IN, rot=15.0)
        for (p, q, col, lift) in [((0.02, 0.0), (0.16, 0.0), LENS, 0.0), ((0.20, 0.0), (0.25, 0.0), GLINT, 0.0)]:
            band = clip_halfplane(disc, _rot2(p, 40.0), _rot2((-1.0, 0.0), 40.0))
            band = clip_halfplane(band, _rot2(q, 40.0), _rot2((1.0, 0.0), 40.0))
            if side < 0:
                band = [(-x, y) for x, y in reversed(band)]
            pts = [_to3(c, u, v, n, x, y, 0.004) for x, y in band]
            out.extend(polygon(pts, col, flags=UNLIT if col == GLINT else 0))
        out.extend(polygon([_to3(c, u, v, n, x, y, 0.006) for x, y in ngon(4, 0.05, cx=-0.13 * side, cy=0.15)],
                           GLINT, flags=UNLIT))
        inner_pts[side] = (_to3(c, u, v, n, -side * LENS_OUT * 0.97, 0.04), _to3(c, u, v, n, side * LENS_OUT, 0.03), n)
    left_in, right_in = inner_pts[-1][0], inner_pts[1][0]
    mid = (0.0, (left_in[1] + right_in[1]) / 2.0 + 0.06, max(left_in[2], right_in[2]) + 0.06)
    out.extend(tube([left_in, mid, right_in], 0.024, 4, FRAME))
    for side in (1, -1):
        outer = inner_pts[side][1]
        back = (side * 0.92, EYE_Y + 0.1, -0.15)
        midp = (side * 0.95, EYE_Y + 0.08, (outer[2] + back[2]) / 2.0 + 0.05)
        out.extend(tube([outer, midp, back], 0.022, 4, FRAME))
    return out


def _rot2(p, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (p[0] * c - p[1] * s, p[0] * s + p[1] * c)


# ---- hair: the messy fringe ------------------------------------------------------------------------
def _fringe():
    """Flat blades flopping forward over the forehead (tan, with periwinkle streaks) and a crown tuft."""
    out = Mesh()
    blades = [  # base (on the crown front), tip, radius, colour
        ((-0.34, 0.60, 0.30), (-0.66, 0.20, 0.86), 0.26, FUR),
        ((-0.14, 0.68, 0.28), (-0.30, 0.30, 0.98), 0.26, PERI),
        ((0.06, 0.70, 0.28), (0.06, 0.40, 1.00), 0.25, FUR),
        ((0.26, 0.66, 0.28), (0.44, 0.30, 0.94), 0.25, FUR),
        ((0.44, 0.56, 0.28), (0.72, 0.22, 0.80), 0.22, PERI),
        ((-0.52, 0.46, 0.30), (-0.90, 0.12, 0.62), 0.20, FUR),
        # crown tufts: messy, sticking up and back between the ears
        ((0.0, 0.50, 0.10), (0.12, 1.10, 0.05), 0.26, FUR),
        ((-0.18, 0.50, 0.0), (-0.38, 1.00, -0.18), 0.22, PERI),
        ((0.20, 0.48, -0.05), (0.42, 0.96, -0.24), 0.22, FUR),
        ((0.0, 0.42, -0.30), (-0.05, 0.86, -0.62), 0.22, FUR),
    ]
    for base, tip, r, col in blades:
        out.extend(cone_between(base, tip, r, 0.0, 3, col))
    return out


# ---- ears ------------------------------------------------------------------------------------------
EAR_H = 2.0
EAR_TILT = 40.0
EAR_TURN = 22.0
EAR_SEAT = (0.48, 0.30, -0.10)
#               v     half-width back   cup
EAR_LEVELS = [(0.00, 0.54, 0.22, 0.05),
              (0.12, 0.72, 0.30, 0.15),
              (0.30, 0.74, 0.30, 0.19),
              (0.48, 0.64, 0.26, 0.16),
              (0.66, 0.48, 0.19, 0.12),
              (0.82, 0.29, 0.12, 0.06),
              (0.94, 0.11, 0.05, 0.02)]
EAR_BACK_PERI = 1        # back of the ear is periwinkle from this level up
EAR_TIP_PERI = 4         # front rim is periwinkle from this level up (the tips)


def _ear():
    """Viewer's-right ear, base at the origin, pointing up, cup facing +z.

    Each level is a 7-point crescent: cup centre, pale edge (right), rim (right), back right,
    back left, rim (left), pale edge (left).
    """
    rings = []
    for v, hw, back, cup in EAR_LEVELS:
        y = v * EAR_H
        rings.append([(0.0, y, -cup),
                      (0.70 * hw, y, -cup * 0.45),
                      (hw, y, 0.0),
                      (0.50 * hw, y, -back),
                      (-0.50 * hw, y, -back),
                      (-hw, y, 0.0),
                      (-0.70 * hw, y, -cup * 0.45)])

    def colour(k, i):
        if i in (0, 6):
            return PERI if k >= EAR_TIP_PERI + 1 else FUR_LIGHT
        if i in (1, 5):
            return PERI if k >= EAR_TIP_PERI else FUR
        return PERI if k >= EAR_BACK_PERI else FUR

    tip = (0.0, EAR_H, -0.02)
    return loft(rings, colour, cap_end=tip, alternate=False,
                cap_color=lambda k, i: FUR_LIGHT if i in (0, 6) else PERI)


def _ear_tufts():
    """Fluffy pale tufts at the base of the cup, in ear space."""
    out = Mesh()
    for base, tip, r in [((-0.18, 0.08, 0.02), (-0.30, 0.62, 0.10), 0.12),
                         ((0.05, 0.06, 0.02), (0.12, 0.52, 0.12), 0.11),
                         ((0.26, 0.10, 0.0), (0.46, 0.46, 0.08), 0.10)]:
        out.extend(cone_between(base, tip, r, 0.0, 4, FUR_LIGHT, squash=0.5))
    return out


def _ears():
    right = merge(_ear(), _ear_tufts())
    right.rotate_y(EAR_TURN).rotate_x(-8).rotate_z(-EAR_TILT).translate(*EAR_SEAT)
    return merge(right, right.mirrored("x"))


# ---- neck, black tee, pendant ----------------------------------------------------------------------
SEG = 12
TORSO_RINGS = [(BASE_Y, 0.80, 0.46),
               (-1.98, 0.88, 0.50),
               (-1.70, 0.92, 0.48),
               (-1.50, 0.75, 0.42),
               (-1.37, 0.46, 0.36),
               (-1.31, 0.36, 0.32)]


def _neck():
    return cone_between((0.0, -0.60, 0.0), (0.0, -1.42, 0.0), 0.34, 0.38, 10, FUR)


def _chest_ruff():
    out = Mesh()
    for base, tip, r in [((0.0, -0.90, 0.28), (0.0, -1.45, 0.48), 0.24),
                         ((0.24, -0.90, 0.22), (0.36, -1.40, 0.40), 0.20),
                         ((-0.24, -0.90, 0.22), (-0.36, -1.40, 0.40), 0.20)]:
        out.extend(cone_between(base, tip, r, 0.0, 4, FUR_LIGHT, squash=0.5))
    return out


def _torso():
    rings = [ring(y, rx, rz, SEG) for y, rx, rz in TORSO_RINGS]
    top = len(TORSO_RINGS) - 2
    return loft(rings, lambda k, i: TEE_SHADE if k == top else TEE, cap_start=True, cap_end=True,
                cap_color=TEE_SHADE, alternate="facet")


def _zigzag(torso):
    """The one periwinkle zigzag band across the chest of the black tee."""
    pts = []
    n = 8
    for j in range(n + 1):
        x = -0.78 + 1.56 * j / n
        pts.append((x, -2.02 + (0.07 if j % 2 else -0.07)))
    return decals(torso, stroke(pts, 0.075), PERI, layer=1)


def _sleeves():
    p0, p1 = (0.78, -1.58, 0.0), (1.08, -1.96, 0.03)
    axis = v_norm((p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2]))
    p2 = (p1[0] + axis[0] * 0.15, p1[1] + axis[1] * 0.15, p1[2] + axis[2] * 0.15)
    s = cone_between(p0, p1, 0.30, 0.26, 8, TEE, squash=0.88)
    s.paint(TEE_SHADE, lambda c, n, i: v_dot(n, axis) > 0.9)
    s.extend(cone_between(p1, p2, 0.18, 0.17, 8, FUR, squash=0.9))
    return merge(s, s.mirrored("x"))


def _pendant():
    """A grey feather on a cord, hanging over the tee."""
    out = Mesh()
    for side in (1, -1):
        path = [(side * 0.30, -1.30, 0.22), (side * 0.20, -1.50, 0.44), (side * 0.06, -1.64, 0.50), (0.0, -1.67, 0.505)]
        out.extend(tube(path, 0.02, 4, CORD, cap_start=False, cap_end=False))
    out.extend(icosphere(0.045, 0, CORD).translate(0.0, -1.68, 0.52))
    leaf = [(0.0, 0.0), (0.055, -0.06), (0.06, -0.16), (0.03, -0.26), (0.0, -0.31), (-0.035, -0.22),
            (-0.05, -0.12), (-0.04, -0.04)]
    feather = prism(leaf, 0.03, FEATHER, side_color=CORD)
    # a spine down the middle as a darker sliver on the front
    feather.extend(polygon([(-0.008, -0.03, 0.016), (0.008, -0.03, 0.016), (0.0, -0.28, 0.016)], CORD))
    feather.scale(1.45, 1.45, 1.0).rotate_z(-8).rotate_x(-6).translate(0.0, -1.70, 0.53)
    out.extend(feather)
    return out


# ---- assembly --------------------------------------------------------------------------------------
NECK_PIVOT = (0.0, -0.85, 0.0)
HEAD_SCALE = 0.86
HEAD_DROP = 0.10          # and sits a little lower, on a shorter neck
BODY_SCALE = 0.92


@lru_cache(maxsize=None)
def parts():
    head = _head()
    muzzle = _muzzle()
    torso = _torso()
    top = merge(head, muzzle, _nose(), _mouth(muzzle), _cheek_ruffs(), _eye(head, 1), _eye(head, -1),
                _forehead(head), _glasses(head), _fringe(), _ears())
    bottom = merge(_neck(), _chest_ruff(), torso, _zigzag(torso), _sleeves(), _pendant())
    # Iggy is the small one: the head (modelled at Nova's working scale) shrinks about the neck
    # pivot, the shoulders get narrower; the cut at BASE_Y stays where it is
    px, py, pz = NECK_PIVOT
    top.transform(compose(translate(-px, -py, -pz), scale(HEAD_SCALE), translate(px, py - HEAD_DROP, pz)))
    bottom.transform(scale(BODY_SCALE, 1.0, BODY_SCALE))
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
SHADOW = dict(center=(0.0, BASE_Y, 0.0), radius=(0.98, 0.72), opacity=0.30)


def _stage(cam, shadow=True):
    return Scene(cam, house_lighting(), shadow=Shadow(**SHADOW) if shadow else None, outline=house_outline())


def _sparkles(items):
    out = Mesh()
    for (x, y, z), size, colour in items:
        out.extend(star4(size, 0.34, size * 0.5, colour, colour).rotate_y(20).translate(x, y, z))
    return out


def _wide_camera():
    """Same camera as Nova's turntable, so the two spins are to scale."""
    return Camera(target=(0.0, 0.13, 0.0), pitch=7.0, distance=17.0, fov=17.9)


def bust_scene(i=0, n=1):
    """Hero still: Nova's camera, mirrored pose (shoulders turned to the viewer's right)."""
    cam = Camera(target=(0.0, 0.22, 0.0), pitch=7.0, distance=17.0, fov=18.7)
    scene = _stage(cam)
    scene.add(build(turn=-12.0, nod=-3.0, tilt=6.0), rot_y(32.0))
    scene.add(_sparkles([((2.05, 1.55, 0.3), 0.20, STAR), ((-2.10, 0.20, 0.2), 0.15, STAR_PINK),
                         ((1.85, -0.95, 0.6), 0.13, STAR_PINK), ((-1.55, 1.95, 0.0), 0.11, STAR_PINK),
                         ((-1.95, -1.45, 0.3), 0.11, STAR)]))
    return scene


def icon_scene(i=0, n=1):
    """App icon: straight on, ears to collar."""
    cam = Camera(target=(0.0, 0.08, 0.0), pitch=3.0, distance=17.0, fov=12.6)
    return _stage(cam, shadow=False).add(build())


def spin_scene(i=0, n=24):
    return _stage(_wide_camera()).add(build(), rot_y(360.0 * i / n))


def view_scene(turn, size_cam=None):
    """For checking: the bust turned by ``turn`` degrees under the turntable camera."""
    return _stage(size_cam or _wide_camera()).add(build(), rot_y(turn))


JOBS = [
    Job("iggy_bust", (512, 512), bust_scene),
    Job("iggy_icon", (256, 256), icon_scene),
    Job("iggy_spin", (192, 192), spin_scene, frames=24, fps=12),
]
