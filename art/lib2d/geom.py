"""Geometry helpers for rigs: points, smooth blobs, limbs, ribbons (tails) and colour mixing.

All functions are pure and return either points (``(x, y)`` tuples), path data strings, or hex colours.
Angles are degrees, clockwise on screen (SVG's y axis points down), 0 degrees = pointing right unless a
function says otherwise.
"""
from __future__ import annotations

import math
from typing import Callable, List, Optional, Sequence, Tuple, Union

from .svg import num

__all__ = [
    "Pt", "lerp", "lerp_pt", "lerp_pts", "clamp", "rot", "polar", "mirror", "sym", "smooth", "blob", "poly",
    "bezier", "arc_pts", "capsule", "ribbon", "band", "along", "mix", "ease", "P",
]

Pt = Tuple[float, float]
Width = Union[float, Sequence[float], Callable[[float], float]]


# ------------------------------------------------------------------ numbers and points

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if v < lo else hi if v > hi else v


def ease(t: float) -> float:
    """Smoothstep: slow in, slow out."""
    t = clamp(t)
    return t * t * (3.0 - 2.0 * t)


def lerp_pt(a: Sequence[float], b: Sequence[float], t: float) -> Pt:
    return (lerp(a[0], b[0], t), lerp(a[1], b[1], t))


def lerp_pts(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]], t: float) -> List[Pt]:
    """Blend two point lists of the same length (two key shapes of a tail, an arm, a mouth)."""
    return [lerp_pt(p, q, t) for p, q in zip(a, b)]


def rot(p: Sequence[float], deg: float, origin: Sequence[float] = (0.0, 0.0)) -> Pt:
    """Rotate ``p`` clockwise on screen by ``deg`` about ``origin``."""
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    x, y = p[0] - origin[0], p[1] - origin[1]
    return (origin[0] + x * c - y * s, origin[1] + x * s + y * c)


def polar(origin: Sequence[float], deg: float, dist: float) -> Pt:
    """The point ``dist`` away from ``origin`` in direction ``deg`` (0 = right, 90 = down, -90 = up)."""
    r = math.radians(deg)
    return (origin[0] + math.cos(r) * dist, origin[1] + math.sin(r) * dist)


def mirror(points: Sequence[Sequence], cx: float = 0.0) -> List[tuple]:
    """Reflect points left/right about ``x = cx`` and reverse their order (corner flags are kept)."""
    out = []
    for p in reversed(list(points)):
        out.append((2.0 * cx - p[0], p[1]) + tuple(p[2:]))
    return out


def sym(half: Sequence[Sequence], cx: float = 0.0) -> List[tuple]:
    """Build a left/right symmetric outline from its right half.

    ``half`` runs from the top point on the centre line, down the right-hand side, to the bottom point on the
    centre line.  Points that sit on the centre line are not duplicated.
    """
    half = [tuple(p) for p in half]
    left = [p for p in mirror(half, cx) if abs(p[0] - cx) > 1e-6]
    return half + left


# ------------------------------------------------------------------ paths

def _f(p: Sequence[float]) -> str:
    return "%s %s" % (num(float(p[0])), num(float(p[1])))


def poly(points: Sequence[Sequence[float]], closed: bool = True) -> str:
    """Straight-edged path through ``points``."""
    d = "M" + " L".join(_f(p) for p in points)
    return d + "Z" if closed else d


def smooth(points: Sequence[Sequence], closed: bool = True, tension: float = 1.0) -> str:
    """A smooth curve through ``points`` (Catmull-Rom converted to cubic Beziers).

    A point may carry a third element ``"c"`` to make it a sharp **corner**: ``(106, 24, "c")``.  That is how
    fur tufts, ear notches and toes are drawn: round everywhere, pointed where you say so.  ``tension`` below
    1 pulls the curve tighter towards straight segments.
    """
    pts = [(float(p[0]), float(p[1])) for p in points]
    corner = [len(p) > 2 and p[2] == "c" for p in points]
    n = len(pts)
    if n < 2:
        return ""
    k = tension / 6.0
    segs = n if closed else n - 1
    d = ["M" + _f(pts[0])]
    for i in range(segs):
        a, b = i, (i + 1) % n
        p0, p1 = pts[a], pts[b]
        if corner[a] or (not closed and a == 0):
            c1 = (p0[0] + (p1[0] - p0[0]) / 3.0, p0[1] + (p1[1] - p0[1]) / 3.0)
        else:
            pm = pts[(a - 1) % n]
            c1 = (p0[0] + (p1[0] - pm[0]) * k, p0[1] + (p1[1] - pm[1]) * k)
        if corner[b] or (not closed and b == n - 1):
            c2 = (p1[0] - (p1[0] - p0[0]) / 3.0, p1[1] - (p1[1] - p0[1]) / 3.0)
        else:
            pn = pts[(b + 1) % n]
            c2 = (p1[0] - (pn[0] - p0[0]) * k, p1[1] - (pn[1] - p0[1]) * k)
        d.append("C%s %s %s" % (_f(c1), _f(c2), _f(p1)))
    if closed:
        d.append("Z")
    return "".join(d)


def blob(points: Sequence[Sequence], tension: float = 1.0) -> str:
    """Closed smooth shape through ``points``: the workhorse for heads, ears, hands and markings."""
    return smooth(points, closed=True, tension=tension)


def bezier(p0: Sequence[float], p1: Sequence[float], p2: Sequence[float], p3: Sequence[float],
           n: int = 32) -> List[Pt]:
    """``n + 1`` points along a cubic Bezier (use it to make the spine of a tail)."""
    out = []
    for i in range(n + 1):
        t = i / float(n)
        u = 1.0 - t
        b0, b1, b2, b3 = u * u * u, 3 * u * u * t, 3 * u * t * t, t * t * t
        out.append((b0 * p0[0] + b1 * p1[0] + b2 * p2[0] + b3 * p3[0],
                    b0 * p0[1] + b1 * p1[1] + b2 * p2[1] + b3 * p3[1]))
    return out


def arc_pts(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float, n: int = 12) -> List[Pt]:
    """Points on an ellipse from angle ``a0`` to ``a1`` (degrees, 0 = right, 90 = down)."""
    out = []
    for i in range(n + 1):
        a = math.radians(lerp(a0, a1, i / float(n)))
        out.append((cx + math.cos(a) * rx, cy + math.sin(a) * ry))
    return out


def capsule(p0: Sequence[float], p1: Sequence[float], r0: float, r1: Optional[float] = None) -> str:
    """A limb segment: a rounded sausage from ``p0`` (radius ``r0``) to ``p1`` (radius ``r1``)."""
    r1 = r0 if r1 is None else r1
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ang = math.degrees(math.atan2(dy, dx))
    a = arc_pts(p0[0], p0[1], r0, r0, ang + 90, ang + 270, 10)
    b = arc_pts(p1[0], p1[1], r1, r1, ang - 90, ang + 90, 10)
    return poly(a + b)


def _spine_frames(spine: Sequence[Sequence[float]]) -> Tuple[List[float], List[Pt], float]:
    """Cumulative arc length, unit normals and total length of a polyline."""
    n = len(spine)
    acc = [0.0]
    for i in range(1, n):
        acc.append(acc[-1] + math.hypot(spine[i][0] - spine[i - 1][0], spine[i][1] - spine[i - 1][1]))
    total = acc[-1] or 1.0
    normals = []
    for i in range(n):
        a, b = spine[max(i - 1, 0)], spine[min(i + 1, n - 1)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        m = math.hypot(dx, dy) or 1.0
        normals.append((-dy / m, dx / m))
    return acc, normals, total


def _width_fn(width: Width) -> Callable[[float], float]:
    if callable(width):
        return width
    if isinstance(width, (int, float)):
        w = float(width)
        return lambda t: w
    ws = [float(v) for v in width]

    def fn(t: float) -> float:
        x = clamp(t) * (len(ws) - 1)
        i = min(int(x), len(ws) - 2)
        return lerp(ws[i], ws[i + 1], x - i)
    return fn


def along(spine: Sequence[Sequence[float]], t: float) -> Tuple[Pt, Pt]:
    """The point at fraction ``t`` (0..1 by arc length) of a polyline, and the unit tangent there."""
    acc, normals, total = _spine_frames(spine)
    want = clamp(t) * total
    for i in range(1, len(spine)):
        if acc[i] >= want:
            seg = (acc[i] - acc[i - 1]) or 1.0
            u = (want - acc[i - 1]) / seg
            p = lerp_pt(spine[i - 1], spine[i], u)
            nx, ny = lerp_pt(normals[i - 1], normals[i], u)
            m = math.hypot(nx, ny) or 1.0
            return p, (ny / m, -nx / m)
    nx, ny = normals[-1]
    return (float(spine[-1][0]), float(spine[-1][1])), (ny, -nx)


def ribbon(spine: Sequence[Sequence[float]], width: Width) -> str:
    """A tail (or scarf, or cheese string): a strip of varying width along ``spine`` with round ends.

    ``width`` is the full width: a number, a list of widths spread evenly from root to tip, or a function of
    ``t`` (0 at the root, 1 at the tip).  A bushy fox tail is just ``[14, 46, 52, 30, 6]``.
    """
    acc, normals, total = _spine_frames(spine)
    wf = _width_fn(width)
    left, right = [], []
    for i, p in enumerate(spine):
        h = wf(acc[i] / total) / 2.0
        nx, ny = normals[i]
        left.append((p[0] + nx * h, p[1] + ny * h))
        right.append((p[0] - nx * h, p[1] - ny * h))
    # round caps
    def cap(i: int, flip: bool) -> List[Pt]:
        nx, ny = normals[i]
        h = wf(acc[i] / total) / 2.0
        a = math.degrees(math.atan2(ny, nx))
        pts = arc_pts(spine[i][0], spine[i][1], h, h, a, a - 180 if not flip else a + 180, 8)
        return pts[1:-1]
    return poly(left + cap(len(spine) - 1, False) + right[::-1] + cap(0, True)[::-1])


def band(spine: Sequence[Sequence[float]], width: Width, t0: float, t1: float, zig: float = 0.0,
         teeth: int = 3, over: float = 2.0) -> str:
    """A stripe across a :func:`ribbon` between fractions ``t0`` and ``t1``, optionally with jagged edges.

    Draw it clipped to the ribbon (``clip(tail_shape, path(band(...)))``).  ``zig`` is how far the teeth of
    the edge reach along the tail, ``teeth`` how many points each edge has.  ``t1`` may be > 1 for a tip.
    """
    wf = _width_fn(width)

    def edge(t: float, sign: float) -> List[Pt]:
        p, tan = along(spine, t)
        ext = max(t - 1.0, 0.0) * _spine_frames(spine)[2]
        p = (p[0] + tan[0] * ext, p[1] + tan[1] * ext)
        nx, ny = -tan[1], tan[0]
        h = wf(clamp(t)) / 2.0 + over
        pts = []
        steps = max(teeth * 2, 1)
        for i in range(steps + 1):
            u = -1.0 + 2.0 * i / steps
            off = (zig if i % 2 else -zig) * sign if zig else 0.0
            pts.append((p[0] + nx * h * u + tan[0] * off, p[1] + ny * h * u + tan[1] * off))
        return pts

    a = edge(t0, 1.0)
    b = edge(t1, -1.0)
    mid: List[Pt] = []
    steps = 6
    side_a, side_b = [], []
    for i in range(1, steps):
        t = lerp(t0, min(t1, 1.0), i / float(steps))
        p, tan = along(spine, t)
        nx, ny = -tan[1], tan[0]
        h = wf(clamp(t)) / 2.0 + over
        side_a.append((p[0] + nx * h, p[1] + ny * h))
        side_b.append((p[0] - nx * h, p[1] - ny * h))
    del mid
    return poly(a + side_a + b[::-1] + side_b[::-1])


# ------------------------------------------------------------------ colour

def _rgb(h: str) -> Tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def mix(a: str, b: str, t: float) -> str:
    """Blend two hex colours (``t = 0`` gives ``a``).  Use it to derive a shade tone from the palette."""
    ra, ga, ba = _rgb(a)
    rb, gb, bb = _rgb(b)
    return "#%02x%02x%02x" % (int(round(lerp(ra, rb, t))), int(round(lerp(ga, gb, t))),
                              int(round(lerp(ba, bb, t))))


# ------------------------------------------------------------------ hand-written paths

class P:
    """A small path builder for the cases where you want exact Bezier control.

    ``P().M(0, 0).C(10, 0, 20, 10, 20, 20).L(0, 20).Z()``; ``str(p)`` (or passing it to ``path``) gives the
    ``d`` attribute.  Coordinates are absolute.
    """

    def __init__(self) -> None:
        self._d: List[str] = []

    def _add(self, cmd: str, *v: float) -> "P":
        self._d.append(cmd + " ".join(num(float(x)) for x in v))
        return self

    def M(self, x: float, y: float) -> "P":
        return self._add("M", x, y)

    def L(self, x: float, y: float) -> "P":
        return self._add("L", x, y)

    def Q(self, x1: float, y1: float, x: float, y: float) -> "P":
        return self._add("Q", x1, y1, x, y)

    def C(self, x1: float, y1: float, x2: float, y2: float, x: float, y: float) -> "P":
        return self._add("C", x1, y1, x2, y2, x, y)

    def A(self, rx: float, ry: float, x: float, y: float, large: int = 0, sweep: int = 1) -> "P":
        self._d.append("A%s %s 0 %d %d %s %s" % (num(float(rx)), num(float(ry)), large, sweep,
                                                  num(float(x)), num(float(y))))
        return self

    def Z(self) -> "P":
        self._d.append("Z")
        return self

    def __str__(self) -> str:
        return "".join(self._d)
