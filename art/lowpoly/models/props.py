"""Props: a small optical disc, an SD card and a four-point star.

Everything here is generic on purpose: the disc is an iridescent pink-lilac ring with no maker's
logo or trade dress, and the card carries a star instead of any logo.

    disc(spin=0)     radius 1, lying in the xy plane, shiny side towards +z, label side towards -z
    sd_card()        0.75 wide, 1.0 tall, label towards +z, contacts on the back
    star(...)        ``lowpoly.mesh.star4`` in the house colours
"""
from __future__ import annotations

import math
from functools import lru_cache

from ..mesh import Mesh, box, compose, decal, merge, mix, ngon, prism, rect, rot_x, rot_y, rot_z, star4, star4_outline
from ..pipeline import Job
from ..render import Camera, Scene, Shadow, house_lighting

HOT_PINK = "#ff4fa3"
PINK = "#ff6fb8"
LILAC = "#b592ff"
PEARL = "#fff4fc"
ICE = "#a5e2ff"
LABEL = "#ff7fbf"
LABEL_LIGHT = "#ffd1ea"
HUB = "#f3e8ff"
STAR = "#fff3b0"

DISC_SEGMENTS = 20
#  radius of each ring of the disc, hole to rim
DISC_RADII = (0.15, 0.33, 0.40, 0.72, 1.0)
DISC_THICK = 0.07


def _iridescent(a, ring_index):
    """Colour of the shiny side at angle ``a`` (radians): pink to lilac with two pearly glints.

    The pattern is deliberately lopsided (one broad glint, one narrow) so a spin is visible.
    """
    a = a + 0.35 * ring_index                     # the outer band lags: reads as a swirl
    base = mix(PINK, LILAC, 0.5 + 0.5 * math.sin(a))
    base = mix(base, HOT_PINK, 0.45 * max(0.0, math.sin(a * 2.0 + 1.0)))
    base = mix(base, ICE, 0.55 * max(0.0, math.sin(a * 3.0 - 0.4)) ** 2)
    glint = max(0.0, math.cos(a - 0.6)) ** 8
    glint2 = 0.8 * max(0.0, math.cos(a - 0.6 - math.pi)) ** 20
    return mix(base, PEARL, min(1.0, glint + glint2))


@lru_cache(maxsize=None)
def _disc():
    n = DISC_SEGMENTS
    h = DISC_THICK / 2.0
    m = Mesh()

    def ring_pts(r, z):
        return [m.add_vertex((r * math.cos(2 * math.pi * j / n), r * math.sin(2 * math.pi * j / n), z))
                for j in range(n)]

    front = [ring_pts(r, h) for r in DISC_RADII]
    back = [ring_pts(r, -h) for r in DISC_RADII]
    for k in range(len(DISC_RADII) - 1):
        for j in range(n):
            j2 = (j + 1) % n
            a = 2 * math.pi * (j + 0.5) / n
            if k == 0:
                shiny, label = HUB, HUB                       # clear plastic hub
            elif k == 1:
                shiny, label = HOT_PINK, PEARL                # the stacking ring
            else:
                shiny = _iridescent(a, k - 2)
                label = LABEL if (j % 2 == 0 or k == 2) else mix(LABEL, LABEL_LIGHT, 0.45)
            a0, b0, c0, d0 = front[k][j], front[k + 1][j], front[k + 1][j2], front[k][j2]
            m.add_face(a0, b0, c0, shiny)
            m.add_face(a0, c0, d0, shiny)
            a1, b1, c1, d1 = back[k][j], back[k + 1][j], back[k + 1][j2], back[k][j2]
            m.add_face(a1, c1, b1, label)
            m.add_face(a1, d1, c1, label)
    for j in range(n):                                        # outer rim and the wall of the hole
        j2 = (j + 1) % n
        o_f, o_f2, o_b, o_b2 = front[-1][j], front[-1][j2], back[-1][j], back[-1][j2]
        m.add_face(o_f, o_b, o_b2, HOT_PINK)
        m.add_face(o_f, o_b2, o_f2, HOT_PINK)
        i_f, i_f2, i_b, i_b2 = front[0][j], front[0][j2], back[0][j], back[0][j2]
        m.add_face(i_f, i_b2, i_b, LILAC)
        m.add_face(i_f, i_f2, i_b2, LILAC)
    # a four-point star on the label side instead of any logo
    back_plate = box((2.2, 2.2, 0.001), LABEL).translate(0.0, 0.0, -h)
    m.extend(decal(back_plate, star4_outline(0.20, 0.07, cx=0.0, cy=0.56), PEARL,
                   origin=(0.0, 0.0, -5.0), forward=(0.0, 0.0, 1.0), layer=1))
    return m


def disc(spin=0.0):
    """The disc, turned ``spin`` degrees about its own axis (a new mesh each call)."""
    return _disc().copy().rotate_z(spin)


@lru_cache(maxsize=None)
def sd_card():
    """A generic memory card: plum body with a clipped corner, pink label with a star, gold contacts."""
    w, t, c = 0.75, 1.0, 0.16
    outline = [(-w / 2, -t / 2), (w / 2, -t / 2), (w / 2, t / 2 - c), (w / 2 - c, t / 2), (-w / 2, t / 2)]
    body = prism(outline, 0.07, "#3b2a5e", side_color="#2c1f49", back_color="#33244f")
    out = merge(body)
    out.extend(decal(body, rect(0.56, 0.60, cy=-0.12), LABEL_LIGHT, layer=1))
    out.extend(decal(body, rect(0.56, 0.11, cy=-0.365), HOT_PINK, layer=2))
    out.extend(decal(body, star4_outline(0.15, 0.055, cx=0.0, cy=-0.04), "#f52fd2", layer=2))
    out.extend(box((0.035, 0.13, 0.05), "#fff0fb").translate(-w / 2 - 0.004, 0.10, 0.0))    # lock switch
    for k in range(7):                                                                       # contacts
        x = -0.29 + k * 0.075            # world x; the projector behind the card sees it mirrored
        out.extend(decal(body, rect(0.05, 0.17, cx=-x, cy=0.37), "#f2c14e",
                         origin=(0.0, 0.0, -5.0), forward=(0.0, 0.0, 1.0), layer=1))
    return out


def star(radius=1.0, color=STAR, color2="#ffd96b"):
    return star4(radius, 0.36, radius * 0.5, color, color2)


# ---- scenes ----------------------------------------------------------------------------------------
def disc_scene(i=0, n=12):
    """The disc tilted towards the camera, turning once on its own axis."""
    cam = Camera(target=(0.0, 0.0, 0.0), pitch=0.0, ortho=2.5)
    scene = Scene(cam, house_lighting(rim=0.6), shadow=Shadow((0.0, -1.02, 0.0), (0.80, 0.50), opacity=0.22))
    return scene.add(disc(spin=-360.0 * i / n), compose(rot_x(-58.0), rot_z(-12.0)))


def card_scene(i=0, n=1):
    cam = Camera(target=(0.0, 0.0, 0.0), pitch=10.0, ortho=1.5)
    scene = Scene(cam, house_lighting(rim=0.7), shadow=Shadow((0.0, -0.56, 0.0), (0.42, 0.30), opacity=0.25))
    return scene.add(sd_card(), compose(rot_y(-28.0), rot_z(8.0)))


def star_scene(i=0, n=1):
    cam = Camera(target=(0.0, 0.0, 0.0), ortho=2.4)
    return Scene(cam, house_lighting(rim=0.5)).add(star(), rot_y(-18.0))


JOBS = [
    Job("disc_spin", (96, 96), disc_scene, frames=12, fps=12),
    Job("sd_card", (128, 128), card_scene),
    Job("star", (64, 64), star_scene),
]
