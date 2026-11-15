"""The die-cut sticker look and the shared stage geometry every rig draws on.

Stage: a 512 x 512 viewBox.  Feet stand on :data:`BASELINE` (92 % of the height).  A character whose rig says
``HEIGHT = 1.0`` (Nova) reaches up to ``top_y(1.0)``; shorter characters use ``top_y(HEIGHT)`` so that two
sprites of the same pixel size sit side by side at the right relative heights.

:func:`sticker` wraps a rig's art in the house finish, from the bottom layer up:

1. soft drop shadow (the only blur in the whole pipeline),
2. thin hot-pink edge,
3. thick white die-cut border,
4. a slightly fatter ink contour around the whole figure,
5. the art itself.

Layers 1-4 are all :func:`lib2d.svg.silhouette` passes over the same nodes, so the border always follows the
drawing exactly, including props, sparkles and zzz.
"""
from __future__ import annotations

from typing import Any, List, Optional

from .svg import (Node, circle, detail, flatten, g, line, outlined, path, polyline, serialize, silhouette,
                  translate)
from .geom import poly

__all__ = [
    "CANVAS", "CX", "BASELINE", "FIG_H", "top_y", "PINK", "WHITE", "SHADOW", "BORDER", "EDGE", "CONTOUR",
    "sticker", "document", "sparkle", "zzz", "heart", "guides",
]

CANVAS = 512            # viewBox is 0 0 CANVAS CANVAS
CX = CANVAS / 2.0       # centre line: characters are centred on it
BASELINE = 471.0        # feet line: 92 % of the canvas height (SPEC_V2 section 5)
FIG_H = 424.0           # height in units of a HEIGHT = 1.0 figure, ear tips to feet

PINK = "#ff4fa3"        # the sticker's thin outer edge (art direction, fixed)
WHITE = "#ffffff"       # the die-cut border
SHADOW = "#1b1c30"      # drop shadow colour (drawn at low opacity)

BORDER = 15.0           # white border width, units
EDGE = 4.5              # pink edge width outside the white, units
CONTOUR = 1.6           # extra ink on the outermost contour, units


def top_y(height: float = 1.0) -> float:
    """The y of the top of a figure of relative ``height`` (ear tips for HEIGHT = 1.0 are at y = 47)."""
    return BASELINE - FIG_H * height


def document(body: str, defs: str = "", size: int = CANVAS) -> str:
    """Wrap SVG markup in the root element every rig returns."""
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d">'
            "%s%s</svg>" % (CANVAS, CANVAS, size, size, ("<defs>%s</defs>" % defs) if defs else "", body))


def guides(height: float = 1.0) -> Node:
    """Debug overlay: baseline, centre line and the top line for ``height`` (``sticker(..., guide=HEIGHT)``)."""
    top = top_y(height)
    kw = {"stroke": "#00d0ff", "stroke_width": 1, "stroke_dasharray": "6 4", "sil": False}
    return detail(line(0, BASELINE, CANVAS, BASELINE, **kw), line(0, top, CANVAS, top, **kw),
                  line(CX, 0, CX, CANVAS, **kw))


def sticker(*art: Any, ink: str, border: float = BORDER, edge: float = EDGE, contour: float = CONTOUR,
            shadow: bool = True, guide: Optional[float] = None) -> str:
    """Finish a drawing as a die-cut sticker and return the complete SVG document.

    ``art`` is the rig's node tree in back-to-front order.  ``ink`` is the character's shadow / ink colour and
    is used for the outer contour.  Pass ``border=0`` for a borderless render (the contour is still drawn).
    ``guide=HEIGHT`` overlays the baseline and height guides while you are designing.
    """
    nodes = flatten(art)
    layers: List[Node] = []
    defs = ""
    if border > 0:
        if shadow:
            defs = ('<filter id="soft" x="-20%" y="-20%" width="140%" height="140%">'
                    '<feGaussianBlur stdDeviation="4.5"/></filter>')
            layers.append(g(g(*silhouette(nodes, border + edge - 2.0, SHADOW), transform=translate(0, 6.5)),
                            filter="url(#soft)", opacity=0.34))
        if edge > 0:
            layers.append(g(*silhouette(nodes, border + edge, PINK)))
        layers.append(g(*silhouette(nodes, border, WHITE)))
    if contour > 0:
        layers.append(g(*silhouette(nodes, contour, ink)))
    layers.extend(nodes)
    if guide is not None:
        layers.append(guides(guide))
    return document(serialize(layers), defs)


# ------------------------------------------------------------------ shared decorations (speech-free props)

def _star_pts(cx: float, cy: float, r: float, pinch: float) -> list:
    """Four-point sparkle outline: long points on the axes, pinched in between."""
    q = r * pinch
    return [(cx, cy - r), (cx + q, cy - q), (cx + r, cy), (cx + q, cy + q),
            (cx, cy + r), (cx - q, cy + q), (cx - r, cy), (cx - q, cy - q)]


def sparkle(cx: float, cy: float, r: float = 14.0, fill: str = "#ffffff", ink: str = SHADOW,
            width: float = 2.6, pinch: float = 0.24) -> Node:
    """The house decoration: a small four-point star.  ``r`` is the tip radius; use 8-18 at sprite scale."""
    return outlined(path(poly(_star_pts(cx, cy, r, pinch)), fill=fill, stroke_linejoin="round"),
                    ink=ink, width=width)


def zzz(x: float, y: float, size: float = 20.0, fill: str = "#ffffff", ink: str = SHADOW,
        count: int = 3, drift: float = 0.0) -> Node:
    """Sleep "Z"s rising up and to the right from ``(x, y)``, each one bigger than the last.

    Drawn as strokes (no fonts, so every rasteriser gives the same result).  ``drift`` (0..1) slides the
    letters along their path so an animation can make them float.
    """
    out = []
    for i in range(count):
        k = i + drift
        s = size * (0.62 + 0.3 * k)
        zx = x + k * size * 1.05
        zy = y - k * size * 1.25
        pts = [(zx, zy), (zx + s, zy), (zx, zy + s), (zx + s, zy + s)]
        w = max(s * 0.24, 3.0)
        out.append(outlined(polyline(pts, stroke=fill, stroke_width=w), ink=ink, width=2.4))
    return g(*out)


def heart(cx: float, cy: float, r: float = 12.0, fill: str = "#ff4fa3", ink: str = SHADOW,
          width: float = 2.6) -> Node:
    """A small heart, ``r`` is roughly half its width."""
    d = ("M%.2f %.2f C%.2f %.2f %.2f %.2f %.2f %.2f C%.2f %.2f %.2f %.2f %.2f %.2f "
         "C%.2f %.2f %.2f %.2f %.2f %.2f C%.2f %.2f %.2f %.2f %.2f %.2fZ") % (
        cx, cy + r,
        cx - r * 0.35, cy + r * 0.7, cx - r, cy + r * 0.25, cx - r, cy - r * 0.3,
        cx - r, cy - r, cx - r * 0.15, cy - r, cx, cy - r * 0.35,
        cx + r * 0.15, cy - r, cx + r, cy - r, cx + r, cy - r * 0.3,
        cx + r, cy + r * 0.25, cx + r * 0.35, cy + r * 0.7, cx, cy + r)
    return outlined(path(d, fill=fill), ink=ink, width=width)


def dot(cx: float, cy: float, r: float, fill: str) -> Node:
    """A paint-only dot (freckles, spots, highlights)."""
    return circle(cx, cy, r, fill=fill, sil=False)
