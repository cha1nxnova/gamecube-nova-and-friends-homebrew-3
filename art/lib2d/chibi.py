"""Small shared parts for the background-cast (cameo) rigs: eyes, mouths, the figure transform.

Cameos are drawn in the same hand as Nova, Iggy and Duskie, only smaller and simpler, so these helpers are
scaled-down, parametric versions of the parts in ``art/rigs/duskie.py`` (eyes built the same way: ink ring,
lid colour, white, two-tone iris, pupil, two highlights, a lash line on the upper lid).

Import explicitly (``from lib2d.chibi import eye, figure``); nothing here is re-exported by ``lib2d``.
Everything returns paint-only nodes unless it says otherwise.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

from .svg import Node, circle, clip, ellipse, g, path, rotate, scale, translate
from .sticker import BASELINE, CX

__all__ = ["eye", "w_mouth", "open_mouth", "figure"]


def eye(ex: float, ey: float, rx: float, ry: float, *, ink: str, lid_fill: str, iris: str, iris_lo: str,
        white: str = "#ffffff", pupil: Optional[str] = None, lid: float = 0.15, state: str = "open",
        look: Sequence[float] = (0.0, 0.0), arch: float = 1.0, lash: Optional[float] = None,
        closed_width: Optional[float] = None) -> List[Node]:
    """One eye.  ``state``: "open" | "closed" (relaxed arc down) | "happy" (arc up).

    ``lid`` is how far the upper lid is down (0 wide .. 1 shut); ``arch`` 1 = round friendly lid, 0 = a
    straight sleepy lid.  ``look`` moves the iris (-1 .. 1 each).
    """
    s = rx / 21.0
    if state in ("closed", "happy"):
        if state == "closed":
            d = "M%g %g Q%g %g %g %g" % (ex - 0.92 * rx, ey + 0.15 * ry, ex, ey + 0.8 * ry, ex + 0.92 * rx,
                                         ey + 0.15 * ry)
        else:
            d = "M%g %g Q%g %g %g %g" % (ex - 0.92 * rx, ey + 0.45 * ry, ex, ey - 0.55 * ry, ex + 0.92 * rx,
                                         ey + 0.45 * ry)
        w = closed_width if closed_width is not None else max(4.4, 6.6 * s)
        return [path(d, fill="none", stroke=ink, stroke_width=w, stroke_linecap="round")]
    lx, ly = float(look[0]), float(look[1])
    lid_y = ey - ry + 2 * ry * lid
    lid_d = "M%g %g Q%g %g %g %g" % (ex - 1.65 * rx, lid_y + 0.45 * ry * arch, ex, lid_y - 0.72 * ry * arch,
                                     ex + 1.65 * rx, lid_y + 0.45 * ry * arch)
    low_y = ey + ry
    opening = path("%s L%g %g L%g %gZ" % (lid_d, ex + 1.65 * rx, low_y + 2, ex - 1.65 * rx, low_y + 2))
    ix, iy = ex + lx * 0.32 * rx, ey + 0.16 * ry + ly * 0.2 * ry
    ir = 0.86 * rx
    inside = [
        ellipse(ex, ey, rx + 3, ry + 3, fill=white),
        clip(circle(ix, iy, ir),
             circle(ix, iy, ir + 1, fill=iris),
             circle(ix, iy + 0.85 * ir, ir, fill=iris_lo)),
        ellipse(ix, iy + 0.5, 0.38 * rx, 0.45 * ry, fill=pupil or ink),
        circle(ix - 0.3 * rx, iy - 0.25 * ry, max(2.2, 0.25 * rx), fill="#ffffff"),
        circle(ix + 0.3 * rx, iy + 0.36 * ry, max(1.1, 0.1 * rx), fill="#ffffff"),
    ]
    lw = lash if lash is not None else max(3.8, 5.2 * s)
    return [
        ellipse(ex, ey, rx + 2.4, ry + 2.4, fill=ink),
        ellipse(ex, ey, rx, ry, fill=lid_fill),
        clip(ellipse(ex, ey, rx, ry), clip(opening, inside)),
        clip(ellipse(ex, ey, rx + 3.4, ry + 4.5),
             path(lid_d, fill="none", stroke=ink, stroke_width=lw, stroke_linecap="round")),
    ]


def w_mouth(cx: float, cy: float, w: float, h: float, *, ink: str, width: float = 2.6,
            philtrum: float = 0.0) -> Node:
    """The cat "w": two little arcs meeting under the nose at ``(cx, cy)``; ``philtrum`` = line up to the nose."""
    d = "M%g %g Q%g %g %g %g Q%g %g %g %g" % (cx - w, cy - h * 0.25, cx - w * 0.5, cy + h, cx, cy,
                                              cx + w * 0.5, cy + h, cx + w, cy - h * 0.25)
    out = [path(d, fill="none", stroke=ink, stroke_width=width, stroke_linecap="round",
                stroke_linejoin="round")]
    if philtrum:
        out.append(path("M%g %g L%g %g" % (cx, cy - philtrum, cx, cy), fill="none", stroke=ink,
                        stroke_width=width * 0.9, stroke_linecap="round"))
    return g(out)


def open_mouth(cx: float, cy: float, w: float, depth: float, *, ink: str, inner: str, tongue: str,
               width: float = 2.4) -> Node:
    """An open mouth hanging from ``(cx, cy)``: a soft "D" with a tongue at the bottom."""
    d = "M%g %g Q%g %g %g %g C%g %g %g %g %g %gZ" % (
        cx - w, cy, cx, cy - 2.0, cx + w, cy,
        cx + w * 1.05, cy + depth * 1.25, cx - w * 1.05, cy + depth * 1.25, cx - w, cy)
    return g(path(d, fill=inner, stroke=ink, stroke_width=width, stroke_linejoin="round"),
             clip(path(d), ellipse(cx, cy + depth * 1.02, w * 0.72, depth * 0.48, fill=tongue)))


def figure(parts: Any, p: dict) -> Node:
    """Move a figure drawn around x = 0 (feet on BASELINE) to the canvas centre, applying the common pose
    keys ``hop`` (units up), ``sway`` (degrees about the feet) and ``squash`` (+ squashes onto the feet)."""
    sq = float(p.get("squash", 0.0) or 0.0)
    return g(parts, transform="%s %s %s %s %s" % (
        translate(CX, -float(p.get("hop", 0.0) or 0.0)), translate(0, BASELINE),
        rotate(float(p.get("sway", 0.0) or 0.0)), scale(1 + sq * 0.55, 1 - sq), translate(0, -BASELINE)))
