"""lib2d: the 2D sticker-sprite toolkit (dev-time only; the app never imports it).

A rig module (``art/rigs/<id>.py``) needs just this::

    from lib2d import *            # or pick names

    CHAR_ID = "nova"               # cast id, also the folder name under assets/sprites/
    HEIGHT = 1.0                   # relative figure height (Nova = 1.0, ear tips at top_y(HEIGHT))
    ANIMS = {"idle": anim([...poses...], fps=6, loop=True), ...}
    PORTRAIT = {...pose...}        # optional: the 512 px still (default: first idle frame)

    def draw(pose) -> str:         # one frame as a complete SVG document on a 512 x 512 viewBox
        return sticker(part, part, ..., ink=INK)

See docs/ART_PIPELINE.md for the walkthrough and ``art/rigs/nova.py`` for the reference rig.
"""
from __future__ import annotations

from .svg import (Node, circle, clip, detail, ellipse, flatten, g, line, num, outlined, path, polygon,
                  polyline, rect, rotate, scale, serialize, silhouette, translate)
from .geom import (P, along, arc_pts, band, bezier, blob, capsule, clamp, ease, lerp, lerp_pt, lerp_pts,
                   mirror, mix, polar, poly, ribbon, rot, smooth, sym)
from .sticker import (BASELINE, BORDER, CANVAS, CONTOUR, CX, EDGE, FIG_H, PINK, SHADOW, WHITE, document,
                      dot, guides, heart, sparkle, sticker, top_y, zzz)
from .poses import CAMEO_ANIMS, REQUIRED_ANIMS, anim, cycle, hold, pose, tween, validate_rig

__all__ = [
    # scene graph
    "Node", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "g", "detail", "clip",
    "translate", "rotate", "scale", "outlined", "silhouette", "serialize", "flatten", "num",
    # geometry
    "P", "smooth", "blob", "poly", "sym", "mirror", "bezier", "arc_pts", "capsule", "ribbon", "band",
    "along", "rot", "polar", "lerp", "lerp_pt", "lerp_pts", "clamp", "ease", "mix",
    # sticker finish and stage
    "sticker", "document", "guides", "sparkle", "zzz", "heart", "dot", "top_y",
    "CANVAS", "CX", "BASELINE", "FIG_H", "BORDER", "EDGE", "CONTOUR", "PINK", "WHITE", "SHADOW",
    # animation model
    "pose", "tween", "cycle", "hold", "anim", "validate_rig", "REQUIRED_ANIMS", "CAMEO_ANIMS",
]
