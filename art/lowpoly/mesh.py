"""Triangle meshes with ONE COLOUR PER FACE, and the primitives the low-poly models are built from.

Conventions (the whole package uses them):

* Right-handed, y up. A character faces **+z** (towards the default camera); **+x is the viewer's
  right** (the character's own left). Units are arbitrary; Nova's head is about 2 wide.
* A face is three vertex indices, counter-clockwise when seen from outside. Faces carry a colour
  (floats 0..1, sRGB), flag bits (``UNLIT``, ``TWO_SIDED``) and a depth ``bias`` used by decals.
* Colours may be given as ``"#rrggbb"`` or an ``(r, g, b)`` float tuple everywhere.
* Transforms are 3x4 affine matrices (12-tuples, row major). ``compose(a, b, c)`` applies ``a``
  first, then ``b``, then ``c``. Mesh transform methods work in place and return ``self`` so
  they chain: ``ellipsoid(...).scale(1, 0.8, 1).rotate_z(-15).translate(0.4, 1, 0)``.
* Angles are degrees. ``rotate_y(+a)`` turns the front (+z) towards the viewer's right (+x);
  ``rotate_x(+a)`` tips the top (+y) forwards (+z); ``rotate_z(+a)`` tips the top to the viewer's
  left (-x).

Primitives (all return a new ``Mesh``): ``icosphere``, ``ellipsoid``, ``box``, ``cylinder``,
``cone_between``, ``loft``, ``tube``, ``prism``, ``polygon``, ``star4`` and ``decal`` (a flat
coloured patch shrink-wrapped onto another mesh: how eyes, dashes and prints are made).
2D outline helpers for decals and prisms: ``ngon``, ``rect``, ``star4_outline``, ``stroke``,
``clip_halfplane``, ``mirror2d``.
"""
from __future__ import annotations

import math

UNLIT = 1        # face colour is used as is (glints, glows)
TWO_SIDED = 2    # never back-face culled; lit as if it faced the camera (whiskers, paper flaps)

DECAL_LIFT = 0.006   # how far each decal layer floats above its surface (world units)
DECAL_BIAS = 0.035   # depth-test head start each decal layer gets (world units)


# ----------------------------------------------------------------------------------------------
# colours and small vector helpers

def rgb(color):
    """``"#rrggbb"`` or an ``(r, g, b)`` tuple -> ``(r, g, b)`` floats in 0..1."""
    if isinstance(color, str):
        s = color.lstrip("#")
        if len(s) != 6:
            raise ValueError("colour must look like #rrggbb: %r" % (color,))
        return (int(s[0:2], 16) / 255.0, int(s[2:4], 16) / 255.0, int(s[4:6], 16) / 255.0)
    r, g, b = color
    return (float(r), float(g), float(b))


def mix(a, b, t):
    """Blend two colours: ``t=0`` gives ``a``, ``t=1`` gives ``b``."""
    a, b = rgb(a), rgb(b)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def v_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_scale(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def v_len(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def v_norm(a):
    n = v_len(a)
    if n < 1e-12:
        return (0.0, 0.0, 0.0)
    return (a[0] / n, a[1] / n, a[2] / n)


# ----------------------------------------------------------------------------------------------
# 3x4 affine transforms

IDENTITY = (1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0)


def translate(x=0.0, y=0.0, z=0.0):
    return (1.0, 0.0, 0.0, float(x), 0.0, 1.0, 0.0, float(y), 0.0, 0.0, 1.0, float(z))


def scale(sx, sy=None, sz=None):
    if sy is None:
        sy = sx
    if sz is None:
        sz = sx
    return (float(sx), 0.0, 0.0, 0.0, 0.0, float(sy), 0.0, 0.0, 0.0, 0.0, float(sz), 0.0)


def rot_x(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (1.0, 0.0, 0.0, 0.0, 0.0, c, -s, 0.0, 0.0, s, c, 0.0)


def rot_y(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (c, 0.0, s, 0.0, 0.0, 1.0, 0.0, 0.0, -s, 0.0, c, 0.0)


def rot_z(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return (c, -s, 0.0, 0.0, s, c, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0)


def mat_mul(a, b):
    """The transform that applies ``b`` first, then ``a``."""
    return (
        a[0] * b[0] + a[1] * b[4] + a[2] * b[8],
        a[0] * b[1] + a[1] * b[5] + a[2] * b[9],
        a[0] * b[2] + a[1] * b[6] + a[2] * b[10],
        a[0] * b[3] + a[1] * b[7] + a[2] * b[11] + a[3],
        a[4] * b[0] + a[5] * b[4] + a[6] * b[8],
        a[4] * b[1] + a[5] * b[5] + a[6] * b[9],
        a[4] * b[2] + a[5] * b[6] + a[6] * b[10],
        a[4] * b[3] + a[5] * b[7] + a[6] * b[11] + a[7],
        a[8] * b[0] + a[9] * b[4] + a[10] * b[8],
        a[8] * b[1] + a[9] * b[5] + a[10] * b[9],
        a[8] * b[2] + a[9] * b[6] + a[10] * b[10],
        a[8] * b[3] + a[9] * b[7] + a[10] * b[11] + a[11],
    )


def compose(*steps):
    """``compose(a, b, c)``: apply ``a`` first, then ``b``, then ``c``."""
    out = IDENTITY
    for m in steps:
        out = mat_mul(m, out)
    return out


def apply(m, p):
    x, y, z = p
    return (m[0] * x + m[1] * y + m[2] * z + m[3],
            m[4] * x + m[5] * y + m[6] * z + m[7],
            m[8] * x + m[9] * y + m[10] * z + m[11])


def mat_det(m):
    return (m[0] * (m[5] * m[10] - m[6] * m[9])
            - m[1] * (m[4] * m[10] - m[6] * m[8])
            + m[2] * (m[4] * m[9] - m[5] * m[8]))


# ----------------------------------------------------------------------------------------------
# the mesh

class Mesh:
    """A bag of triangles with per-face colour, flags and depth bias."""

    __slots__ = ("verts", "faces", "colors", "flags", "bias")

    def __init__(self):
        self.verts = []    # [(x, y, z)]
        self.faces = []    # [(i, j, k)]  counter-clockwise seen from outside
        self.colors = []   # [(r, g, b)]  one per face
        self.flags = []    # [int]        UNLIT | TWO_SIDED
        self.bias = []     # [float]      depth head start, world units (decals)

    def __len__(self):
        return len(self.faces)

    # ---- building -------------------------------------------------------------------------
    def add_vertex(self, p):
        self.verts.append((float(p[0]), float(p[1]), float(p[2])))
        return len(self.verts) - 1

    def add_face(self, a, b, c, color, flags=0, bias=0.0):
        self.faces.append((a, b, c))
        self.colors.append(rgb(color))
        self.flags.append(flags)
        self.bias.append(bias)

    def add_tri(self, p0, p1, p2, color, flags=0, bias=0.0):
        """Add a loose triangle from three points."""
        a = self.add_vertex(p0)
        self.add_vertex(p1)
        self.add_vertex(p2)
        self.add_face(a, a + 1, a + 2, color, flags, bias)
        return self

    def extend(self, *others):
        """Merge other meshes into this one (they are left untouched)."""
        for other in others:
            base = len(self.verts)
            self.verts.extend(other.verts)
            self.faces.extend((a + base, b + base, c + base) for a, b, c in other.faces)
            self.colors.extend(other.colors)
            self.flags.extend(other.flags)
            self.bias.extend(other.bias)
        return self

    def copy(self):
        m = Mesh()
        m.verts = list(self.verts)
        m.faces = list(self.faces)
        m.colors = list(self.colors)
        m.flags = list(self.flags)
        m.bias = list(self.bias)
        return m

    # ---- transforms (in place, chainable) ---------------------------------------------------
    def transform(self, m):
        self.verts = [apply(m, v) for v in self.verts]
        if mat_det(m) < 0:      # a mirror turns every face inside out: put them back
            self.flip()
        return self

    def translate(self, x=0.0, y=0.0, z=0.0):
        return self.transform(translate(x, y, z))

    def scale(self, sx, sy=None, sz=None):
        return self.transform(scale(sx, sy, sz))

    def rotate_x(self, deg):
        return self.transform(rot_x(deg))

    def rotate_y(self, deg):
        return self.transform(rot_y(deg))

    def rotate_z(self, deg):
        return self.transform(rot_z(deg))

    def warp(self, fn):
        """Move every vertex: ``fn((x, y, z)) -> (x, y, z)``. For tapers, bends and bulges."""
        self.verts = [tuple(float(c) for c in fn(v)) for v in self.verts]
        return self

    def flip(self):
        """Reverse the winding of every face (turn the mesh inside out)."""
        self.faces = [(a, c, b) for a, b, c in self.faces]
        return self

    def mirrored(self, axis="x"):
        """A mirrored copy (across the plane where ``axis`` is 0), still facing outwards."""
        s = {"x": (-1, 1, 1), "y": (1, -1, 1), "z": (1, 1, -1)}[axis]
        return self.copy().transform(scale(*s))

    # ---- queries ----------------------------------------------------------------------------
    def centroid(self, fi):
        a, b, c = self.faces[fi]
        p, q, r = self.verts[a], self.verts[b], self.verts[c]
        return ((p[0] + q[0] + r[0]) / 3.0, (p[1] + q[1] + r[1]) / 3.0, (p[2] + q[2] + r[2]) / 3.0)

    def normal(self, fi):
        a, b, c = self.faces[fi]
        p = self.verts[a]
        return v_norm(v_cross(v_sub(self.verts[b], p), v_sub(self.verts[c], p)))

    def bounds(self):
        """``((min x, min y, min z), (max x, max y, max z))``."""
        if not self.verts:
            return ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
        xs, ys, zs = zip(*self.verts)
        return ((min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs)))

    def raycast(self, origin, direction):
        """Nearest hit of a ray: ``(t, face index)`` with the point at ``origin + t*direction``, or None."""
        ox, oy, oz = origin
        dx, dy, dz = direction
        best_t = None
        best_f = -1
        verts = self.verts
        for fi, (ia, ib, ic) in enumerate(self.faces):
            ax, ay, az = verts[ia]
            bx, by, bz = verts[ib]
            cx, cy, cz = verts[ic]
            e1x, e1y, e1z = bx - ax, by - ay, bz - az
            e2x, e2y, e2z = cx - ax, cy - ay, cz - az
            px = dy * e2z - dz * e2y
            py = dz * e2x - dx * e2z
            pz = dx * e2y - dy * e2x
            det = e1x * px + e1y * py + e1z * pz
            if -1e-12 < det < 1e-12:
                continue
            inv = 1.0 / det
            tx, ty, tz = ox - ax, oy - ay, oz - az
            u = (tx * px + ty * py + tz * pz) * inv
            if u < -1e-9 or u > 1.0 + 1e-9:
                continue
            qx = ty * e1z - tz * e1y
            qy = tz * e1x - tx * e1z
            qz = tx * e1y - ty * e1x
            v = (dx * qx + dy * qy + dz * qz) * inv
            if v < -1e-9 or u + v > 1.0 + 1e-9:
                continue
            t = (e2x * qx + e2y * qy + e2z * qz) * inv
            if t > 1e-9 and (best_t is None or t < best_t):
                best_t, best_f = t, fi
        if best_t is None:
            return None
        return best_t, best_f

    # ---- colouring --------------------------------------------------------------------------
    def paint(self, color, where=None):
        """Recolour faces. ``where(centre, normal, face_index) -> bool`` picks them (default: all).

        This is the "region rule" tool: ``head.paint(WHITE, lambda c, n, i: c[1] < -0.2 and c[2] > 0)``
        makes every face whose centre is below y=-0.2 and in the front half white. Returns the
        number of faces painted, so a rule that matches nothing is easy to spot.
        """
        col = rgb(color)
        count = 0
        for fi in range(len(self.faces)):
            if where is None or where(self.centroid(fi), self.normal(fi), fi):
                self.colors[fi] = col
                count += 1
        return count

    def set_flags(self, flags, where=None):
        """Set flag bits (``UNLIT``, ``TWO_SIDED``) on all faces or on those ``where`` picks."""
        for fi in range(len(self.faces)):
            if where is None or where(self.centroid(fi), self.normal(fi), fi):
                self.flags[fi] |= flags
        return self


def merge(*meshes):
    """A new mesh holding all the given meshes."""
    return Mesh().extend(*meshes)


# ----------------------------------------------------------------------------------------------
# lofting: the workhorse. Everything round is rings of points stitched together.

def ring(y, rx, rz=None, segments=12, phase=0.5, rz_back=None, cx=0.0, cz=0.0, angles=None):
    """A horizontal ellipse of ``segments`` points at height ``y``, ready for ``loft``.

    Point ``j`` sits at angle ``(j - phase) * 360/segments`` measured from the front (+z) towards
    the viewer's right (+x). With ``phase=0.5`` (default) a flat facet faces the camera and
    facet ``i`` is centred on angle ``i * 360/segments``; with ``phase=0`` an edge faces it.
    ``rz_back`` gives the back half its own depth (for heads that are flatter in front).
    ``angles`` (degrees, increasing) places the points by hand instead, for facets of unequal
    width; ``facet_angles`` builds a left-right symmetric list.
    """
    if rz is None:
        rz = rx
    if rz_back is None:
        rz_back = rz
    if angles is None:
        angles = [(j - phase) * 360.0 / segments for j in range(segments)]
    pts = []
    for deg in angles:
        a = math.radians(deg)
        c = math.cos(a)
        pts.append((cx + rx * math.sin(a), y, cz + (rz if c >= 0 else rz_back) * c))
    return pts


def facet_angles(half):
    """Ring angles for a left-right symmetric ring with a facet facing the camera.

    ``half`` lists the edge angles on the viewer's right, front to back, for example
    ``[16, 52, 80, 108, 136, 164]``: the front facet spans -16..16, the next 16..52, and so on,
    and the last one closes across the back (164..196). Returns ``2 * len(half)`` angles in the
    order ``ring(angles=...)`` wants, so facet ``i`` is the one that starts at ``half[i - 1]``
    (facet 0 is the front) and facet ``len(angles) - i`` is its mirror image.
    """
    return [-half[0]] + list(half) + [360.0 - a for a in reversed(half[1:])]


def loft(rings, color, cap_start=None, cap_end=None, alternate=True, cap_color=None):
    """Stitch a stack of closed rings (equal point counts) into a faceted skin.

    * Order the rings from start to end, and each ring's points counter-clockwise when you look
      from the end back towards the start (``ring()`` and ``cone_between`` already do).
    * ``color`` is one colour, or ``color(k, i)`` returning the colour of the quad between ring
      ``k`` and ``k+1`` at segment ``i`` (between point ``i`` and ``i+1``): exact per-facet control.
    * ``cap_start`` / ``cap_end``: ``None`` leaves the end open, ``True`` closes it with a fan to
      the ring's centre, a point ``(x, y, z)`` closes it with a fan to that apex (a pole or tip).
      Cap fans use ``cap_color`` (same forms as ``color``; ``k`` is -1 for the start cap and
      ``len(rings) - 1`` for the end cap) or fall back to ``color``.
    * ``alternate`` picks each quad's diagonal: ``True`` flips every other one (a diamond
      pattern, left-right symmetric when an EDGE faces the camera, ``phase=0``); ``"facet"``
      does the same but mirrored about the front facet (use it with ``phase=0.5`` rings and an
      even point count); ``False`` keeps them all the same way.
    """
    if len(rings) < 2:
        raise ValueError("loft needs at least two rings")
    n = len(rings[0])
    for r in rings:
        if len(r) != n:
            raise ValueError("every ring in a loft needs the same number of points")
    m = Mesh()
    for r in rings:
        for p in r:
            m.add_vertex(p)

    def col(fn, k, i):
        return fn(k, i) if callable(fn) else fn

    for k in range(len(rings) - 1):
        for i in range(n):
            j = (i + 1) % n
            a, b = k * n + i, k * n + j
            c, d = (k + 1) * n + j, (k + 1) * n + i
            q = col(color, k, i)
            if alternate == "facet":
                odd = (k + min(i, n - i)) % 2
                if i > n // 2:
                    odd = 1 - odd
            else:
                odd = alternate and (k + i) % 2
            if odd:
                m.add_face(a, b, d, q)
                m.add_face(b, c, d, q)
            else:
                m.add_face(a, b, c, q)
                m.add_face(a, c, d, q)

    cc = cap_color if cap_color is not None else color
    if cap_start is not None and cap_start is not False:
        apex = _centre(rings[0]) if cap_start is True else cap_start
        ai = m.add_vertex(apex)
        for i in range(n):
            m.add_face(ai, (i + 1) % n, i, col(cc, -1, i))
    if cap_end is not None and cap_end is not False:
        last = (len(rings) - 1) * n
        apex = _centre(rings[-1]) if cap_end is True else cap_end
        ai = m.add_vertex(apex)
        for i in range(n):
            m.add_face(ai, last + i, last + (i + 1) % n, col(cc, len(rings) - 1, i))
    return m


def _centre(points):
    n = float(len(points))
    return (sum(p[0] for p in points) / n, sum(p[1] for p in points) / n, sum(p[2] for p in points) / n)


def _frame(axis):
    """Two unit vectors ``u, v`` perpendicular to ``axis`` with ``u x v = axis``."""
    d = v_norm(axis)
    ref = (0.0, 1.0, 0.0) if abs(d[1]) < 0.9 else (1.0, 0.0, 0.0)
    u = v_norm(v_cross(d, ref))
    v = v_cross(d, u)
    return d, u, v


def _circle(centre, u, v, ra, rb, segments, phase):
    pts = []
    for j in range(segments):
        a = math.radians((j - phase) * 360.0 / segments)
        ca, sa = math.cos(a) * ra, math.sin(a) * rb
        pts.append((centre[0] + u[0] * ca + v[0] * sa,
                    centre[1] + u[1] * ca + v[1] * sa,
                    centre[2] + u[2] * ca + v[2] * sa))
    return pts


# ----------------------------------------------------------------------------------------------
# primitives

def ellipsoid(radii=(1.0, 1.0, 1.0), segments=12, rings=6, color="#ffffff", phase=0.5):
    """A latitude/longitude ellipsoid centred on the origin with its poles on the y axis.

    ``rings`` is the number of latitude bands (so ``rings - 1`` rings of vertices plus two poles);
    ``segments * (2 * rings - 2)`` triangles. ``color`` may be ``color(k, i)`` as in ``loft``.
    """
    rx, ry, rz = radii
    stack = []
    for k in range(1, rings):
        lat = -90.0 + 180.0 * k / rings
        c, s = math.cos(math.radians(lat)), math.sin(math.radians(lat))
        stack.append(ring(ry * s, rx * c, rz * c, segments, phase))
    return loft(stack, color, cap_start=(0.0, -ry, 0.0), cap_end=(0.0, ry, 0.0))


_ICO_T = (1.0 + math.sqrt(5.0)) / 2.0
_ICO_VERTS = [(-1, _ICO_T, 0), (1, _ICO_T, 0), (-1, -_ICO_T, 0), (1, -_ICO_T, 0),
              (0, -1, _ICO_T), (0, 1, _ICO_T), (0, -1, -_ICO_T), (0, 1, -_ICO_T),
              (_ICO_T, 0, -1), (_ICO_T, 0, 1), (-_ICO_T, 0, -1), (-_ICO_T, 0, 1)]
_ICO_FACES = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11),
              (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8),
              (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
              (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]


def icosphere(radii=(1.0, 1.0, 1.0), subdivisions=1, color="#ffffff"):
    """An icosphere (20, 80, 320... triangles for 0, 1, 2 subdivisions) scaled to ``radii``."""
    if isinstance(radii, (int, float)):
        radii = (radii, radii, radii)
    verts = [v_norm(v) for v in _ICO_VERTS]
    faces = list(_ICO_FACES)
    for _ in range(subdivisions):
        cache = {}

        def mid(i, j):
            key = (i, j) if i < j else (j, i)
            if key not in cache:
                a, b = verts[i], verts[j]
                verts.append(v_norm(((a[0] + b[0]) / 2.0, (a[1] + b[1]) / 2.0, (a[2] + b[2]) / 2.0)))
                cache[key] = len(verts) - 1
            return cache[key]

        nxt = []
        for a, b, c in faces:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nxt += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        faces = nxt
    m = Mesh()
    for v in verts:
        m.add_vertex((v[0] * radii[0], v[1] * radii[1], v[2] * radii[2]))
    for a, b, c in faces:
        m.add_face(a, b, c, color)
    return m


def box(size=(1.0, 1.0, 1.0), color="#ffffff"):
    """An axis-aligned box centred on the origin (12 triangles)."""
    if isinstance(size, (int, float)):
        size = (size, size, size)
    hx, hy, hz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    m = Mesh()
    for x, y, z in [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
                    (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]:
        m.add_vertex((x, y, z))
    for a, b, c, d in [(4, 5, 6, 7), (1, 0, 3, 2), (5, 1, 2, 6), (0, 4, 7, 3), (7, 6, 2, 3), (0, 1, 5, 4)]:
        m.add_face(a, b, c, color)
        m.add_face(a, c, d, color)
    return m


def cone_between(p0, p1, r0, r1, segments=8, color="#ffffff", cap_start=True, cap_end=True,
                 squash=1.0, phase=0.5):
    """A tapered tube from point ``p0`` (radius ``r0``) to ``p1`` (radius ``r1``).

    ``r1=0`` makes a spike with its tip at ``p1`` (``r0=0`` puts the tip at ``p0``). ``squash``
    scales the second cross-section axis to make it oval. ``color`` may be ``color(k, i)``.
    """
    d, u, v = _frame(v_sub(p1, p0))
    rings_ = []
    start, end = cap_start, cap_end
    if r0 > 0:
        rings_.append(_circle(p0, u, v, r0, r0 * squash, segments, phase))
    else:
        start = tuple(p0)
    if r1 > 0:
        rings_.append(_circle(p1, u, v, r1, r1 * squash, segments, phase))
    else:
        end = tuple(p1)
    if len(rings_) == 2:
        return loft(rings_, color, cap_start=start, cap_end=end)
    # a pure cone: one ring and an apex
    only = rings_[0]
    m = Mesh()
    for p in only:
        m.add_vertex(p)
    n = len(only)

    def col(k, i):
        return color(k, i) if callable(color) else color

    if r1 <= 0:   # tip at p1
        ai = m.add_vertex(p1)
        for i in range(n):
            m.add_face(ai, i, (i + 1) % n, col(0, i))
        if cap_start:
            ci = m.add_vertex(p0)
            for i in range(n):
                m.add_face(ci, (i + 1) % n, i, col(-1, i))
    else:         # tip at p0
        ai = m.add_vertex(p0)
        for i in range(n):
            m.add_face(ai, (i + 1) % n, i, col(0, i))
        if cap_end:
            ci = m.add_vertex(p1)
            for i in range(n):
                m.add_face(ci, i, (i + 1) % n, col(1, i))
    return m


def cylinder(radius=1.0, height=1.0, segments=12, color="#ffffff", radius_top=None, caps=True):
    """An upright cylinder (or cone, with ``radius_top=0``) from y=0 to y=``height``."""
    if radius_top is None:
        radius_top = radius
    return cone_between((0.0, 0.0, 0.0), (0.0, height, 0.0), radius, radius_top, segments, color,
                        cap_start=caps, cap_end=caps)


def tube(path, radii, segments=6, color="#ffffff", cap_start=True, cap_end=True, squash=1.0):
    """A lofted tube along a list of 3D points (tails, arms, cords).

    ``radii`` is one radius or one per path point; a final radius of 0 closes the tube to a
    point. ``color`` may be ``color(k, i)`` where ``k`` is the path segment: tail bands are
    ``lambda k, i: WHITE if k % 2 else NAVY``.
    """
    n = len(path)
    if n < 2:
        raise ValueError("a tube needs at least two path points")
    if isinstance(radii, (int, float)):
        radii = [radii] * n
    if len(radii) != n:
        raise ValueError("give one radius per path point")
    tangents = []
    for k in range(n):
        a = path[max(k - 1, 0)]
        b = path[min(k + 1, n - 1)]
        tangents.append(v_norm(v_sub(b, a)))
    _d, u, _v = _frame(tangents[0])
    rings_ = []
    end = cap_end
    for k in range(n):
        t = tangents[k]
        u = v_norm(v_sub(u, v_scale(t, v_dot(u, t))))     # parallel transport: no twisting
        v = v_cross(t, u)
        if k == n - 1 and radii[k] <= 0:
            end = tuple(path[k])
            break
        rings_.append(_circle(path[k], u, v, radii[k], radii[k] * squash, segments, 0.5))
    return loft(rings_, color, cap_start=cap_start, cap_end=end)


def prism(outline, depth, color="#ffffff", side_color=None, back_color=None):
    """Extrude a 2D outline (counter-clockwise ``(x, y)`` points) along z, centred on z=0.

    The outline must be star-shaped around its centroid (any convex shape, a star, a card with a
    clipped corner). The front face looks towards +z.
    """
    side_color = color if side_color is None else side_color
    back_color = color if back_color is None else back_color
    n = len(outline)
    cx = sum(p[0] for p in outline) / float(n)
    cy = sum(p[1] for p in outline) / float(n)
    h = depth / 2.0
    m = Mesh()
    for x, y in outline:
        m.add_vertex((x, y, h))
    for x, y in outline:
        m.add_vertex((x, y, -h))
    cf = m.add_vertex((cx, cy, h))
    cb = m.add_vertex((cx, cy, -h))
    for i in range(n):
        j = (i + 1) % n
        m.add_face(cf, i, j, color)
        m.add_face(cb, n + j, n + i, back_color)
        m.add_face(i, n + j, j, side_color)
        m.add_face(i, n + i, n + j, side_color)
    return m


def polygon(points, color="#ffffff", two_sided=False, flags=0):
    """A flat fan through 3D ``points`` (counter-clockwise seen from its front)."""
    m = Mesh()
    for p in points:
        m.add_vertex(p)
    f = flags | (TWO_SIDED if two_sided else 0)
    for i in range(1, len(points) - 1):
        m.add_face(0, i, i + 1, color, f)
    return m


def star4(radius=1.0, inner=0.36, depth=0.24, color="#fff3b0", color2=None):
    """A faceted four-point star (16 triangles) in the xy plane, points on the axes."""
    color2 = color if color2 is None else color2
    pts = star4_outline(radius, inner)
    m = Mesh()
    for x, y in pts:
        m.add_vertex((x, y, 0.0))
    front = m.add_vertex((0.0, 0.0, depth / 2.0))
    back = m.add_vertex((0.0, 0.0, -depth / 2.0))
    n = len(pts)
    for i in range(n):
        j = (i + 1) % n
        c = color if i % 2 == 0 else color2
        m.add_face(front, i, j, c)
        m.add_face(back, j, i, c)
    return m


# ----------------------------------------------------------------------------------------------
# 2D outlines (for decals and prisms). All are counter-clockwise lists of (x, y).

def ngon(n, rx, ry=None, cx=0.0, cy=0.0, rot=0.0):
    """A regular ``n``-gon (an ellipse if ``ry`` differs). ``rot`` in degrees; 0 puts a point at the top."""
    if ry is None:
        ry = rx
    pts = []
    for i in range(n):
        a = math.radians(90.0 + rot + 360.0 * i / n)
        pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
    return pts


def rect(w, h, cx=0.0, cy=0.0, rot=0.0):
    """A ``w`` by ``h`` rectangle centred on ``(cx, cy)``, optionally rotated by ``rot`` degrees."""
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for x, y in [(-w / 2.0, -h / 2.0), (w / 2.0, -h / 2.0), (w / 2.0, h / 2.0), (-w / 2.0, h / 2.0)]:
        out.append((cx + x * c - y * s, cy + x * s + y * c))
    return out


def star4_outline(radius=1.0, inner=0.36, cx=0.0, cy=0.0):
    pts = []
    for i in range(8):
        a = math.radians(90.0 + 45.0 * i)
        r = radius if i % 2 == 0 else inner
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return pts


def mirror2d(outline):
    """Flip an outline left-right (keeps it counter-clockwise)."""
    return [(-x, y) for x, y in reversed(outline)]


def stroke(points, width):
    """A thick polyline as a list of convex outlines (one quad per segment, a diamond per joint)."""
    out = []
    h = width / 2.0
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        dx, dy = x1 - x0, y1 - y0
        ln = math.hypot(dx, dy)
        if ln < 1e-9:
            continue
        nx, ny = -dy / ln * h, dx / ln * h
        out.append([(x0 - nx, y0 - ny), (x1 - nx, y1 - ny), (x1 + nx, y1 + ny), (x0 + nx, y0 + ny)])
    for x, y in points[1:-1]:
        out.append(ngon(4, h, h, x, y))
    return out


def clip_halfplane(outline, point, normal):
    """Keep the part of a convex outline on the side of a line that ``normal`` points AWAY from.

    The line passes through ``point``; ``normal`` is ``(nx, ny)``. ``clip_halfplane(circle,
    (0, 0.05), (0, 1))`` cuts a circle flat at y=0.05 and keeps what is below: a half-closed eye.
    """
    px, py = point
    nx, ny = normal
    out = []
    n = len(outline)
    for i in range(n):
        ax, ay = outline[i]
        bx, by = outline[(i + 1) % n]
        da = (ax - px) * nx + (ay - py) * ny
        db = (bx - px) * nx + (by - py) * ny
        if da <= 0:
            out.append((ax, ay))
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            out.append((ax + (bx - ax) * t, ay + (by - ay) * t))
    return out


# ----------------------------------------------------------------------------------------------
# decals: flat coloured patches shrink-wrapped onto a surface

def decal(target, outline, color, origin=(0.0, 0.0, 10.0), forward=(0.0, 0.0, -1.0),
          up=(0.0, 1.0, 0.0), layer=1, flags=0, detail=1):
    """Project a 2D outline onto ``target`` and return it as a thin coloured patch.

    Think of a slide projector standing at ``origin`` and pointing along ``forward``: the
    outline's ``(x, y)`` are measured in the projector's own right/up directions, each point is
    shot at the target, and the patch is laid where the rays land. With the defaults the
    projector looks at the front of the model, so outline coordinates are simply the model's
    x and y as seen from the front.

    * ``layer``: 1 for a patch on the bare surface, 2 for a patch on top of a layer-1 patch, and
      so on. Higher layers float a hair further out and win the depth test.
    * ``detail``: 1 fans straight from the centre to the outline; 2 or 3 add inner rings so a big
      patch follows a curved surface more closely.
    * The outline must be counter-clockwise and star-shaped around its centroid.
    * Raises ``ValueError`` if a ray misses the target, so a misplaced decal is caught at build
      time instead of leaving a hole.

    The patch only shows from the side the projector is on (it is a sticker, not a solid).
    """
    f = v_norm(forward)
    upv = v_sub(up, v_scale(f, v_dot(up, f)))
    upv = v_norm(upv)
    right = v_cross(f, upv)
    n = len(outline)
    cx = sum(p[0] for p in outline) / float(n)
    cy = sum(p[1] for p in outline) / float(n)
    lift = DECAL_LIFT * layer

    def shoot(x, y):
        start = (origin[0] + right[0] * x + upv[0] * y,
                 origin[1] + right[1] * x + upv[1] * y,
                 origin[2] + right[2] * x + upv[2] * y)
        hit = target.raycast(start, f)
        if hit is None:
            raise ValueError("decal point (%.3f, %.3f) misses the target surface" % (x, y))
        t = hit[0] - lift
        return (start[0] + f[0] * t, start[1] + f[1] * t, start[2] + f[2] * t)

    m = Mesh()
    centre = m.add_vertex(shoot(cx, cy))
    prev = None
    for d in range(1, detail + 1):
        k = d / float(detail)
        cur = [m.add_vertex(shoot(cx + (x - cx) * k, cy + (y - cy) * k)) for x, y in outline]
        for i in range(n):
            j = (i + 1) % n
            if prev is None:
                m.add_face(centre, cur[i], cur[j], color, flags, DECAL_BIAS * layer)
            else:
                m.add_face(prev[i], cur[i], cur[j], color, flags, DECAL_BIAS * layer)
                m.add_face(prev[i], cur[j], prev[j], color, flags, DECAL_BIAS * layer)
        prev = cur
    return m


def decals(target, outlines, color, **kwargs):
    """``decal`` for a list of outlines (for example the output of ``stroke``), merged."""
    out = Mesh()
    for o in outlines:
        out.extend(decal(target, o, color, **kwargs))
    return out
