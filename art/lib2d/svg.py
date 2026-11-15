"""A tiny SVG scene graph: nodes, shapes, groups, clips and the two passes the sticker look needs.

Everything a rig draws is a tree of :class:`Node` objects.  Keeping a tree (instead of gluing strings) is what
lets :func:`silhouette` re-draw the same geometry "fatter" in one flat colour.  That one trick gives us the
ink outline, the thicker outer contour, the white die-cut border, the pink edge and the drop shadow without
any SVG feature that a fallback rasteriser might not support.

Only plain SVG 1.1 comes out: paths, basic shapes, groups, transforms, clipPath, and (in ``sticker.py``) one
Gaussian blur for the shadow.  No CSS, no text, no gradients.
"""
from __future__ import annotations

from typing import Any, Iterable, List, Optional, Sequence, Union

__all__ = [
    "Node", "num", "path", "circle", "ellipse", "rect", "line", "polyline", "polygon", "g", "detail",
    "clip", "translate", "rotate", "scale", "outlined", "silhouette", "serialize", "flatten",
]

SHAPES = ("path", "circle", "ellipse", "rect", "line", "polyline", "polygon")


def num(v: Any) -> str:
    """Format a number for SVG: two decimals, no trailing zeros, never '-0'."""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        s = ("%.2f" % v).rstrip("0").rstrip(".")
        return "0" if s in ("-0", "") else s
    return str(v)


class Node:
    """One SVG element.

    ``sil`` controls the die-cut silhouette: ``None`` (default) means "counts", ``False`` means "paint only"
    (markings, faces, whiskers: anything that must not grow the white border).  A ``False`` on a group hides
    the whole subtree from the silhouette.  ``clip`` (a list of shape nodes) clips the node's children to the
    union of those shapes; clipped groups never count towards the silhouette because their content is inside
    something else by construction.
    """

    __slots__ = ("tag", "attrs", "kids", "sil", "clip")

    def __init__(self, tag: str, attrs: Optional[dict] = None, kids: Optional[Sequence[Any]] = None,
                 sil: Optional[bool] = None, clip: Optional[Sequence["Node"]] = None) -> None:
        self.tag = tag
        self.attrs = dict(attrs or {})
        self.kids = flatten(kids or [])
        self.sil = sil
        self.clip = flatten(clip) if clip else None

    def copy(self, **attrs: Any) -> "Node":
        """Shallow copy with some attributes replaced (children are shared, never mutated)."""
        a = dict(self.attrs)
        a.update(_norm(attrs))
        return Node(self.tag, a, self.kids, self.sil, self.clip)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<Node %s %d kids>" % (self.tag, len(self.kids))


def flatten(items: Any) -> List[Node]:
    """Flatten nested lists/tuples of nodes and drop ``None`` so rigs can write ``[a, cond and b, [c, d]]``."""
    out: List[Node] = []
    if items is None or items is False:
        return out
    if isinstance(items, Node):
        return [items]
    for it in items:
        if it is None or it is False:
            continue
        if isinstance(it, Node):
            out.append(it)
        else:
            out.extend(flatten(it))
    return out


def _norm(attrs: dict) -> dict:
    """``stroke_width=3`` -> ``{"stroke-width": 3}``; ``None`` values are dropped."""
    return {k.replace("_", "-"): v for k, v in attrs.items() if v is not None}


def _shape(tag: str, base: dict, attrs: dict) -> Node:
    sil = attrs.pop("sil", None)
    a = dict(base)
    a.update(_norm(attrs))
    return Node(tag, a, sil=sil)


# ------------------------------------------------------------------ shapes

def path(d: Any, **attrs: Any) -> Node:
    """A path.  ``d`` may be a string or anything with ``__str__`` (see ``geom.P``)."""
    return _shape("path", {"d": str(d)}, attrs)


def circle(cx: float, cy: float, r: float, **attrs: Any) -> Node:
    return _shape("circle", {"cx": cx, "cy": cy, "r": r}, attrs)


def ellipse(cx: float, cy: float, rx: float, ry: float, rot: float = 0.0, **attrs: Any) -> Node:
    """An ellipse; ``rot`` (degrees, clockwise on screen) turns it about its own centre."""
    if rot:
        attrs.setdefault("transform", rotate(rot, cx, cy))
    return _shape("ellipse", {"cx": cx, "cy": cy, "rx": rx, "ry": ry}, attrs)


def rect(x: float, y: float, w: float, h: float, r: float = 0.0, **attrs: Any) -> Node:
    base = {"x": x, "y": y, "width": w, "height": h}
    if r:
        base["rx"] = r
    return _shape("rect", base, attrs)


def line(x1: float, y1: float, x2: float, y2: float, **attrs: Any) -> Node:
    """A straight stroke.  Give it ``stroke`` and ``stroke_width``; caps are round unless you say otherwise."""
    attrs.setdefault("fill", "none")
    attrs.setdefault("stroke_linecap", "round")
    return _shape("line", {"x1": x1, "y1": y1, "x2": x2, "y2": y2}, attrs)


def _pts(points: Iterable[Sequence[float]]) -> str:
    return " ".join("%s,%s" % (num(float(p[0])), num(float(p[1]))) for p in points)


def polyline(points: Iterable[Sequence[float]], **attrs: Any) -> Node:
    """An open stroked polyline (round joins and caps by default): handy for limbs and tails."""
    attrs.setdefault("fill", "none")
    attrs.setdefault("stroke_linecap", "round")
    attrs.setdefault("stroke_linejoin", "round")
    return _shape("polyline", {"points": _pts(points)}, attrs)


def polygon(points: Iterable[Sequence[float]], **attrs: Any) -> Node:
    return _shape("polygon", {"points": _pts(points)}, attrs)


# ------------------------------------------------------------------ groups

def g(*kids: Any, **attrs: Any) -> Node:
    """A group.  ``transform=``, ``opacity=`` and ``sil=False`` are the attributes you will actually use."""
    sil = attrs.pop("sil", None)
    return Node("g", _norm(attrs), kids, sil=sil)


def detail(*kids: Any, **attrs: Any) -> Node:
    """A group of pure paint: drawn normally, ignored by the outline and the die-cut border."""
    attrs["sil"] = False
    return g(*kids, **attrs)


def clip(shapes: Any, *kids: Any, **attrs: Any) -> Node:
    """Draw ``kids`` clipped to the union of ``shapes`` (markings inside a body part, an iris inside an eye)."""
    return Node("g", _norm(attrs), kids, sil=False, clip=flatten(shapes))


# ------------------------------------------------------------------ transforms (strings for transform=)

def translate(x: float, y: float = 0.0) -> str:
    return "translate(%s %s)" % (num(float(x)), num(float(y)))


def rotate(deg: float, cx: float = 0.0, cy: float = 0.0) -> str:
    """Clockwise on screen (SVG's y axis points down)."""
    if cx or cy:
        return "rotate(%s %s %s)" % (num(float(deg)), num(float(cx)), num(float(cy)))
    return "rotate(%s)" % num(float(deg))


def scale(sx: float, sy: Optional[float] = None, cx: float = 0.0, cy: float = 0.0) -> str:
    """Scale about ``(cx, cy)``.  ``scale(-1, 1, 256)`` mirrors left/right about the canvas centre line."""
    sy = sx if sy is None else sy
    s = "scale(%s %s)" % (num(float(sx)), num(float(sy)))
    if cx or cy:
        return "%s %s %s" % (translate(cx, cy), s, translate(-cx, -cy))
    return s


# ------------------------------------------------------------------ the two passes

def _has(v: Any) -> bool:
    return v is not None and str(v) != "none"


def silhouette(nodes: Any, grow: float, color: str) -> List[Node]:
    """The same geometry, flat ``color``, every edge pushed out by ``grow`` units.

    Filled shapes become fill + stroke in ``color`` (stroke width = their own stroke + 2 x grow); stroke-only
    shapes keep no fill and get a fatter stroke.  Nodes marked ``sil=False`` and clipped groups are left out.
    """
    out: List[Node] = []
    for n in flatten(nodes):
        if n.sil is False or n.clip:
            continue
        if n.tag == "g":
            kids = silhouette(n.kids, grow, color)
            if kids:
                a = {k: v for k, v in n.attrs.items() if k == "transform"}
                out.append(Node("g", a, kids))
            continue
        if n.tag not in SHAPES:
            continue
        a = dict(n.attrs)
        sw = float(a.get("stroke-width", 1.0)) if _has(a.get("stroke")) else 0.0
        filled = n.tag not in ("line", "polyline") and str(a.get("fill", "black")) != "none"
        if not filled and not sw:
            continue
        for k in ("opacity", "fill-opacity", "stroke-opacity", "stroke-dasharray"):
            a.pop(k, None)
        a["fill"] = color if filled else "none"
        a["stroke"] = color
        a["stroke-width"] = sw + 2.0 * grow
        a["stroke-linejoin"] = "round"
        a.setdefault("stroke-linecap", "round")
        out.append(Node(n.tag, a))
    return out


def outlined(*shapes: Any, ink: str, width: float = 3.5, **attrs: Any) -> Node:
    """One body part: the union of ``shapes`` with a single ink line of ``width`` units around the outside.

    The shapes are drawn twice: first fattened in ``ink``, then normally on top.  Where two shapes of the same
    part meet (navy upper arm into white glove, leg into foot) there is deliberately no line, which is how fur
    colour changes are drawn in this house style.  Give the shapes their fills and **no stroke**; stroke-only
    shapes (``line``, ``polyline``) work too and are how limbs and slim tails are usually drawn.
    """
    under = silhouette(shapes, width, ink)
    return g(g(*under), detail(*shapes), **attrs)


# ------------------------------------------------------------------ serialisation

def _esc(v: Any) -> str:
    return num(v).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


class _Ctx:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.n = 0

    def next_id(self) -> str:
        self.n += 1
        return "%sc%d" % (self.prefix, self.n)


def _emit(n: Node, ctx: _Ctx, out: List[str]) -> None:
    attrs = "".join(' %s="%s"' % (k, _esc(v)) for k, v in n.attrs.items())
    if n.clip:
        cid = ctx.next_id()
        out.append('<clipPath id="%s">' % cid)
        for c in n.clip:
            # clip shapes are geometry only: paint attributes are irrelevant, nested clips are not allowed
            a = "".join(' %s="%s"' % (k, _esc(v)) for k, v in c.attrs.items()
                        if k in ("d", "cx", "cy", "r", "rx", "ry", "x", "y", "width", "height", "points",
                                 "transform"))
            out.append("<%s%s/>" % (c.tag, a))
        out.append("</clipPath>")
        attrs += ' clip-path="url(#%s)"' % cid
    if n.kids:
        out.append("<%s%s>" % (n.tag, attrs))
        for k in n.kids:
            _emit(k, ctx, out)
        out.append("</%s>" % n.tag)
    else:
        out.append("<%s%s/>" % (n.tag, attrs))


def serialize(nodes: Any, prefix: str = "") -> str:
    """Nodes -> SVG markup (no ``<svg>`` wrapper).  Clip ids are numbered in document order: deterministic."""
    out: List[str] = []
    ctx = _Ctx(prefix)
    for n in flatten(nodes):
        _emit(n, ctx, out)
    return "".join(out)


NodeLike = Union[Node, Sequence[Any], None]
