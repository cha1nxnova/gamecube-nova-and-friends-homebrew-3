"""PICKLE the lumpy low-poly cat: background cast (cameo), and the one sprite drawn FACETED.

Canon: docs/CHARACTERS.md "Background cast".  Must-haves, numbered in comments:
MH1 faceted even as a 2D sprite: straight edges only, three flat tones, no curves and no ink line inside the
shape (the sticker border still wraps him); MH2 an upright lumpy bean with no neck and a short thick tail
sticking straight out to one side with a dark tip; MH3 two small dark triangle ears; MH4 two dot eyes set wide
apart and a "w" mouth; the expression never changes.

How the facets are made: the bean is a coarse 3D mesh (rows of latitude round the front half of a lumpy
ellipsoid), projected straight on to the screen.  Each triangle's normal is lit by one fixed light from the
upper left and snapped to one of the three body tones, so the shading behaves like a real flat-shaded model
from a 2001 tech demo.  Everything is ``polygon``: no curve command appears anywhere in his SVG except in the
house sparkle (which he never gets: his expression never changes).
"""
from __future__ import annotations

import math

from lib2d import anim, detail, g, mix, polygon, polyline, pose, sticker
from lib2d.chibi import figure

CHAR_ID = "pickle"
HEIGHT = 0.50
CAMEO = True
PORTRAIT = False      # cameos: 96 and 192 px only

# ------------------------------------------------------------------ palette (docs/CHARACTERS.md, Pickle)
BODY = "#b9d56e"
SHADE = "#97b650"
LIGHT = "#d3e696"
DARK = "#3f5a2a"      # ears and tail tip
FACE = "#26301c"      # eyes and mouth
INK = FACE            # the outer contour only (MH1: no ink inside the shape)
DARK_LO = mix(DARK, FACE, 0.45)
DARK_HI = mix(DARK, SHADE, 0.30)

DEFAULTS = {"mouth": "w", "squash": 0.0, "hop": 0.0}

# ------------------------------------------------------------------ the mesh (MH2)

# (canvas y, radius) of each ring, top pole to the flat base; x lean per ring makes the bean lumpy
RINGS = [(266.0, 0.0), (278.0, 30.0), (304.0, 47.0), (348.0, 55.0), (398.0, 62.0), (440.0, 57.0),
         (471.0, 38.0)]
LEAN = [0.0, -1.5, -2.5, 0.5, 3.0, 1.0, 0.0]
COLS = 5                      # segments round the visible front half (-90 .. 90 degrees)
LUMP = 0.10
LIGHT_DIR = (-0.42, -0.58, 0.70)  # x right, y DOWN (screen), z towards the viewer


def _hash(i, j):
    v = math.sin(i * 12.9898 + j * 78.233) * 43758.5453
    return (v - math.floor(v)) * 2.0 - 1.0


def _vertex(i, j):
    y, r = RINGS[i]
    phi = math.radians(-90.0 + 180.0 * j / COLS)
    if 0 < i < len(RINGS) - 1 and 0 < j < COLS:
        r *= 1.0 + LUMP * _hash(i, j)
    return (LEAN[i] + r * math.sin(phi), y, r * math.cos(phi))


def _tone(a, b, c):
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    n = (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)
    m = math.sqrt(n[0] ** 2 + n[1] ** 2 + n[2] ** 2) or 1.0
    n = (n[0] / m, n[1] / m, n[2] / m)
    if n[2] < 0:
        n = (-n[0], -n[1], -n[2])
    lm = math.sqrt(sum(k * k for k in LIGHT_DIR))
    d = sum(n[k] * LIGHT_DIR[k] for k in range(3)) / lm
    return LIGHT if d > 0.80 else BODY if d > 0.45 else SHADE


def _facet(pts, fill):
    return polygon([(p[0], p[1]) for p in pts], fill=fill)


def _bean():
    verts = [[_vertex(i, j) for j in range(COLS + 1)] for i in range(len(RINGS))]
    # an underlay of the whole outline in the mid tone hides antialiasing seams between facets
    rim = [v for v in (row[0] for row in verts)] + [v for v in (row[-1] for row in reversed(verts))]
    out = [_facet(rim, BODY)]
    for i in range(len(RINGS) - 1):
        for j in range(COLS):
            a, b, c, d = verts[i][j], verts[i][j + 1], verts[i + 1][j + 1], verts[i + 1][j]
            tris = [(a, b, c), (a, c, d)] if (i + j) % 2 == 0 else [(a, b, d), (b, c, d)]
            for t in tris:
                if abs((t[1][0] - t[0][0]) * (t[2][1] - t[0][1]) - (t[2][0] - t[0][0]) * (t[1][1] - t[0][1])) < 1:
                    continue                                             # degenerate on screen (the pole)
                out.append(_facet(t, _tone(*t)))
    # same-tone neighbours get a hairline in their own colour (no seams); lighter tones are drawn first so a
    # darker facet's hairline lands on the boundary, never a light line on a dark facet
    order = {LIGHT: 0, BODY: 1, SHADE: 2}
    facets = sorted(out[1:], key=lambda n: order[n.attrs["fill"]])
    return [out[0]] + [n.copy(stroke=n.attrs["fill"], stroke_width=0.9, stroke_linejoin="bevel") for n in facets]


# ------------------------------------------------------------------ ears, tail, feet  (MH3, MH2)

def _ears():
    out = []
    for s in (-1, 1):
        base_o, base_i, tip = (s * 46, 292), (s * 12, 280), (s * 34, 259)
        mid = (s * 29, 286)
        lit, dim = (DARK_HI, DARK) if s < 0 else (DARK, DARK_LO)
        out += [_facet([base_o, mid, tip], lit), _facet([mid, base_i, tip], dim)]
    return out


def _tail():
    x0, xm, x1 = 44.0, 82.0, 104.0
    top, hi, lo, bot = 400.0, 407.0, 425.0, 432.0
    out = [
        _facet([(x0, top + 1), (xm, top), (xm, hi), (x0, hi + 1)], LIGHT),     # upper bevel
        _facet([(x0, hi + 1), (xm, hi), (xm, lo), (x0, lo + 1)], BODY),         # front face
        _facet([(x0, lo + 1), (xm, lo), (xm, bot), (x0, bot + 1)], SHADE),      # under bevel
        # MH2: the dark tip
        _facet([(xm, top), (x1, top - 1), (x1, hi - 1), (xm, hi)], DARK_HI),
        _facet([(xm, hi), (x1, hi - 1), (x1, lo - 1), (xm, lo)], DARK),
        _facet([(xm, lo), (x1, lo - 1), (x1, bot - 1), (xm, bot)], DARK_LO),
        _facet([(x1, top - 1), (x1 + 7, hi), (x1 + 7, lo), (x1, bot - 1)], DARK_LO),   # end cap
    ]
    return out


def _feet():
    out = []
    for s in (-1, 1):
        xi, xo = s * 8.0, s * 40.0
        out += [_facet([(xo + s * 2, 456), (xi, 456), (xi - s * 2, 461), (xo + s * 4, 461)], LIGHT),
                _facet([(xo + s * 4, 461), (xi - s * 2, 461), (xi - s * 2, 471), (xo + s * 5, 471)],
                       BODY if s < 0 else SHADE)]
    return out


# ------------------------------------------------------------------ face  (MH4: never changes)

def _face(p):
    out = []
    for s in (-1, 1):                                   # dot eyes, wide apart: octagons, not circles
        cx, cy, r = s * 31.0, 336.0, 6.6
        out.append(polygon([(cx + r * math.cos(math.radians(22.5 + 45 * k)),
                             cy + r * math.sin(math.radians(22.5 + 45 * k))) for k in range(8)], fill=FACE))
    if p["mouth"] == "w":
        out.append(polyline([(-13, 350), (-6.5, 357), (0, 351), (6.5, 357), (13, 350)], stroke=FACE,
                            stroke_width=3.4, stroke_linejoin="miter", stroke_linecap="square"))
    else:                                               # talk: the "w" opens into a small triangle
        out.append(polygon([(-8, 350), (8, 350), (0, 361)], fill=FACE, stroke=FACE, stroke_width=2.4,
                           stroke_linejoin="miter"))
    return detail(out)


def draw(pose_in=None, guide=False):
    p = dict(DEFAULTS)
    p.update(pose_in or {})
    fig = figure([g(_ears()), g(_tail()), g(_bean()), g(_feet()), _face(p)], p)
    return sticker(fig, ink=INK, contour=2.4, guide=HEIGHT if guide else None)


# ------------------------------------------------------------------ animations (SPEC_V2 section 8)

ANIMS = {
    "idle": anim([pose(), pose(squash=0.022)], fps=3, loop=True),          # a tiny bob onto his base
    "talk": anim([pose(mouth="tri"), pose(mouth="w")], fps=6, loop=True),
}
