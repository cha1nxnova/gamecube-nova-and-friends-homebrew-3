"""Flat-shaded software renderer: z-buffer rasteriser, supersampling, rim light, PNG out.

Pure standard library. The whole public API:

    cam   = Camera(target=(0, 0, 0), yaw=0, pitch=8, distance=14, fov=24)     # perspective
    cam   = Camera(target=(0, 0, 0), ortho=5.0)                               # orthographic
    scene = Scene(cam, lighting=house_lighting(), shadow=Shadow(...), outline=house_outline())
    scene.add(mesh)                              # as modelled
    scene.add(mesh, rot_y(30))                   # or with a transform (lowpoly.mesh matrices)
    image = render(scene, 192, 192, ss=3)        # -> Image (straight-alpha RGBA, transparent bg)
    image.save("out.png")

How a frame is made: every triangle is moved into camera space, back faces are dropped, the
face gets ONE colour from the lighting (flat shading), and it is scan-converted into a depth
buffer and a buffer of face ids at ``ss`` times the output size. The id buffer is then turned
into colours and box-filtered down, which is what smooths the edges. The optional silhouette
outline and the soft ground shadow are added last.

Lights are fixed to the CAMERA, not the world (directions are given as seen on screen:
x right, y up, z towards the viewer), so a model spinning on a turntable keeps its pink rim on
the same side of the picture.
"""
from __future__ import annotations

import math

from . import png
from .mesh import IDENTITY, TWO_SIDED, UNLIT, mat_mul, rgb, v_norm

HOT_PINK = "#ff4fa3"
_NEAR = 0.05


# ----------------------------------------------------------------------------------------------
# camera

class Camera:
    """Looks at ``target`` from ``distance`` away.

    ``yaw`` walks the camera round the model towards the viewer's right, ``pitch`` lifts it
    (positive looks down on the model); both in degrees. Give ``fov`` (vertical field of view,
    degrees) for perspective, or ``ortho`` (how many world units fit the image height) for an
    orthographic view. For a turntable leave the camera alone and rotate the model.
    """

    def __init__(self, target=(0.0, 0.0, 0.0), yaw=0.0, pitch=0.0, distance=12.0, fov=26.0, ortho=None):
        self.target = tuple(float(c) for c in target)
        self.yaw = float(yaw)
        self.pitch = float(pitch)
        self.distance = float(distance)
        self.fov = float(fov)
        self.ortho = None if ortho is None else float(ortho)

    def view_matrix(self):
        """World -> camera space (x right, y up, the camera looks down -z)."""
        yw, pt = math.radians(self.yaw), math.radians(self.pitch)
        back = (math.sin(yw) * math.cos(pt), math.sin(pt), math.cos(yw) * math.cos(pt))   # target -> camera
        right = (math.cos(yw), 0.0, -math.sin(yw))       # from the yaw alone: still defined looking straight down
        up = (back[1] * right[2] - back[2] * right[1],
              back[2] * right[0] - back[0] * right[2],
              back[0] * right[1] - back[1] * right[0])
        tx, ty, tz = self.target
        ex, ey, ez = tx + back[0] * self.distance, ty + back[1] * self.distance, tz + back[2] * self.distance
        return (right[0], right[1], right[2], -(right[0] * ex + right[1] * ey + right[2] * ez),
                up[0], up[1], up[2], -(up[0] * ex + up[1] * ey + up[2] * ez),
                back[0], back[1], back[2], -(back[0] * ex + back[1] * ey + back[2] * ez))

    def pixels_per_unit(self, height, depth=None):
        """Output pixels per world unit at ``depth`` in front of the camera (default: at the target)."""
        if self.ortho is not None:
            return height / self.ortho
        d = self.distance if depth is None else depth
        return (height / 2.0) / math.tan(math.radians(self.fov) / 2.0) / d

    def project(self, point, width, height):
        """World point -> ``(x, y, depth)`` in output pixels (y down), or None if behind the camera."""
        m = self.view_matrix()
        x = m[0] * point[0] + m[1] * point[1] + m[2] * point[2] + m[3]
        y = m[4] * point[0] + m[5] * point[1] + m[6] * point[2] + m[7]
        d = -(m[8] * point[0] + m[9] * point[1] + m[10] * point[2] + m[11])
        if self.ortho is not None:
            k = height / self.ortho
        else:
            if d <= _NEAR:
                return None
            k = (height / 2.0) / math.tan(math.radians(self.fov) / 2.0) / d
        return (width / 2.0 + x * k, height / 2.0 - y * k, d)


# ----------------------------------------------------------------------------------------------
# lighting

class Lighting:
    """Flat-shading recipe. Directions point FROM the surface TO the light, in screen terms
    (x right, y up, z towards the viewer).

    ``colour = albedo * (ambient + sum(light_colour * max(0, n.dir)))  + sheen * key
               + rim_colour * rim_strength * max(0, n.rim_dir) ** rim_power
               + edge_colour * edge_strength * (1 - n.view) ** edge_power``

    * ``lights``: list of ``(direction, colour)``; the first is the key light (it alone drives
      ``sheen``, a small albedo-independent lift that keeps very dark fur readable).
    * ``rim``: the coloured back light. It is ADDED, so it glows on dark and light faces alike.
    * ``edge``: a faint glow on any face that is nearly edge-on to the camera, so the side away
      from the rim light still gets a hint of colour.
    """

    def __init__(self, ambient, lights, rim_dir=None, rim_color=HOT_PINK, rim_strength=0.0, rim_power=1.0,
                 edge_color=HOT_PINK, edge_strength=0.0, edge_power=3.0, sheen=0.0):
        self.ambient = rgb(ambient)
        self.lights = [(v_norm(d), rgb(c)) for d, c in lights]
        self.rim_dir = None if rim_dir is None else v_norm(rim_dir)
        self.rim_color = rgb(rim_color)
        self.rim_strength = float(rim_strength)
        self.rim_power = float(rim_power)
        self.edge_color = rgb(edge_color)
        self.edge_strength = float(edge_strength)
        self.edge_power = float(edge_power)
        self.sheen = float(sheen)

    def shade(self, albedo, n, view):
        """Colour of a face with unit normal ``n`` seen along unit vector ``view`` (surface -> camera)."""
        lr, lg, lb = self.ambient
        key = 0.0
        first = True
        for d, c in self.lights:
            k = n[0] * d[0] + n[1] * d[1] + n[2] * d[2]
            if k > 0.0:
                lr += c[0] * k
                lg += c[1] * k
                lb += c[2] * k
                if first:
                    key = k
            first = False
        r, g, b = albedo[0] * lr, albedo[1] * lg, albedo[2] * lb
        if self.sheen and key > 0.0 and self.lights:
            kc = self.lights[0][1]
            s = self.sheen * key
            r += kc[0] * s
            g += kc[1] * s
            b += kc[2] * s
        if self.rim_dir is not None and self.rim_strength:
            d = self.rim_dir
            k = n[0] * d[0] + n[1] * d[1] + n[2] * d[2]
            if k > 0.0:
                t = self.rim_strength * (k ** self.rim_power)
                r += self.rim_color[0] * t
                g += self.rim_color[1] * t
                b += self.rim_color[2] * t
        if self.edge_strength:
            k = 1.0 - max(0.0, n[0] * view[0] + n[1] * view[1] + n[2] * view[2])
            t = self.edge_strength * (k ** self.edge_power)
            r += self.edge_color[0] * t
            g += self.edge_color[1] * t
            b += self.edge_color[2] * t
        return (r, g, b)


def house_lighting(rim=1.0):
    """The project look: warm white key from the upper left front, soft cool fill from the right,
    a touch of bounce from below so chins are not grey, and a hot-pink (#ff4fa3) rim from behind
    right. ``rim`` scales the pink (0 turns it off)."""
    return Lighting(
        ambient=(0.46, 0.46, 0.53),
        lights=[((-0.48, 0.52, 0.71), (0.60, 0.56, 0.48)),      # key: warm white, upper left front
                ((0.78, -0.10, 0.50), (0.12, 0.15, 0.22)),      # fill: soft and cool, from the right
                ((0.0, -0.85, 0.53), (0.13, 0.10, 0.12))],      # bounce: a little warmth from the ground
        rim_dir=(0.74, 0.25, -0.62), rim_color=HOT_PINK, rim_strength=1.00 * rim, rim_power=1.6,
        edge_color=HOT_PINK, edge_strength=0.22 * rim, edge_power=3.0,
        sheen=0.07)


def plain_lighting():
    """One white light straight from the camera plus ambient: for tests and diagnostics."""
    return Lighting(ambient=(0.35, 0.35, 0.35), lights=[((0.0, 0.0, 1.0), (0.65, 0.65, 0.65))])


# ----------------------------------------------------------------------------------------------
# scene extras

class Shadow:
    """A soft elliptical shadow on the ground under the model.

    ``center`` is a world point on the ground, ``radius`` the shadow's half-width in world units
    (``(rx, rz)`` for an oval), ``opacity`` its darkest alpha. It is drawn under everything else
    and squashed by the camera pitch (never thinner than ``min_squash`` so it shows at eye level).
    """

    def __init__(self, center=(0.0, 0.0, 0.0), radius=1.0, opacity=0.32, color="#2a1436", min_squash=0.2):
        self.center = tuple(float(c) for c in center)
        self.radius = (radius, radius) if isinstance(radius, (int, float)) else (radius[0], radius[1])
        self.opacity = float(opacity)
        self.color = rgb(color)
        self.min_squash = float(min_squash)


class Outline:
    """A thin line drawn just inside the silhouette.

    ``color=None`` darkens each face's own colour (``strength`` 0..1 is how far towards black);
    with a colour, edge pixels are blended ``strength`` of the way to it. ``width`` is in output
    pixels.
    """

    def __init__(self, color=None, strength=0.45, width=1.0):
        self.color = None if color is None else rgb(color)
        self.strength = float(strength)
        self.width = float(width)


def house_outline():
    """The project's silhouette edge: one output pixel, each face's own colour 30% darker. It keeps
    white fur and pale props readable on a white or pale pink page and is invisible on dark ones."""
    return Outline(color=None, strength=0.30, width=1.0)


class Scene:
    """What to draw: a camera, lighting, meshes (each with an optional transform) and extras."""

    def __init__(self, camera, lighting=None, shadow=None, outline=None):
        self.camera = camera
        self.lighting = lighting if lighting is not None else house_lighting()
        self.shadow = shadow
        self.outline = outline
        self.items = []

    def add(self, mesh, transform=None):
        """Add a mesh, optionally moved by a ``lowpoly.mesh`` transform. Returns the scene."""
        self.items.append((mesh, transform))
        return self

    def triangle_count(self):
        return sum(len(m) for m, _t in self.items)


# ----------------------------------------------------------------------------------------------
# images

class Image:
    """Straight-alpha RGBA pixels, rows top to bottom."""

    def __init__(self, width, height, pixels=None):
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 4) if pixels is None else pixels

    def pixel(self, x, y):
        i = (y * self.width + x) * 4
        return tuple(self.pixels[i:i + 4])

    def covered(self, threshold=1):
        """How many pixels have alpha >= ``threshold``."""
        return sum(1 for a in self.pixels[3::4] if a >= threshold)

    def save(self, path):
        """Write a PNG; returns the file size in bytes."""
        return png.write_png(path, self.width, self.height, self.pixels)

    def flattened(self, background="#ffffff"):
        """A copy composited onto an opaque background colour (for previews)."""
        br, bg, bb = [int(round(c * 255)) for c in rgb(background)]
        out = bytearray(len(self.pixels))
        px = self.pixels
        for i in range(0, len(px), 4):
            a = px[i + 3]
            if a == 255:
                out[i:i + 4] = px[i:i + 4]
            elif a == 0:
                out[i], out[i + 1], out[i + 2], out[i + 3] = br, bg, bb, 255
            else:
                out[i] = (px[i] * a + br * (255 - a) + 127) // 255
                out[i + 1] = (px[i + 1] * a + bg * (255 - a) + 127) // 255
                out[i + 2] = (px[i + 2] * a + bb * (255 - a) + 127) // 255
                out[i + 3] = 255
        return Image(self.width, self.height, out)


def contact_sheet(images, columns=6, background="#ffffff", gap=4):
    """Lay images out in a grid on an opaque background: handy for eyeballing a whole animation."""
    if not images:
        raise ValueError("no images")
    cw = max(im.width for im in images)
    ch = max(im.height for im in images)
    rows = (len(images) + columns - 1) // columns
    w = columns * cw + (columns + 1) * gap
    h = rows * ch + (rows + 1) * gap
    br, bg, bb = [int(round(c * 255)) for c in rgb(background)]
    sheet = bytearray(bytes([br, bg, bb, 255]) * (w * h))
    for n, im in enumerate(images):
        flat = im.flattened(background)
        ox = gap + (n % columns) * (cw + gap)
        oy = gap + (n // columns) * (ch + gap)
        for y in range(im.height):
            dst = ((oy + y) * w + ox) * 4
            sheet[dst:dst + im.width * 4] = flat.pixels[y * im.width * 4:(y + 1) * im.width * 4]
    return Image(w, h, sheet)


# ----------------------------------------------------------------------------------------------
# the renderer

def _to8(c):
    v = int(c * 255.0 + 0.5)
    return 0 if v < 0 else (255 if v > 255 else v)


def _pack(r, g, b):
    """Opaque colour as one integer with 16 bits per channel, so samples can simply be summed."""
    return _to8(r) | (_to8(g) << 16) | (_to8(b) << 32) | (255 << 48)


def _collect(scene, W, H):
    """Shade and project every visible face. Returns ``(triangles, lut)`` in sample coordinates."""
    cam = scene.camera
    light = scene.lighting
    view = cam.view_matrix()
    ortho = cam.ortho is not None
    if ortho:
        k_ortho = H / cam.ortho
    else:
        k_persp = (H / 2.0) / math.tan(math.radians(cam.fov) / 2.0)
    hw, hh = W / 2.0, H / 2.0
    lut = [0]          # packed colour per face id; id 0 is "nothing here"
    tris = []
    for mesh, xf in scene.items:
        m = view if xf is None else mat_mul(view, xf)
        m0, m1, m2, m3, m4, m5, m6, m7, m8, m9, m10, m11 = m
        vv = [(m0 * x + m1 * y + m2 * z + m3, m4 * x + m5 * y + m6 * z + m7, m8 * x + m9 * y + m10 * z + m11)
              for x, y, z in mesh.verts]
        colors, flags, bias = mesh.colors, mesh.flags, mesh.bias
        for fi, (ia, ib, ic) in enumerate(mesh.faces):
            ax, ay, az = vv[ia]
            bx, by, bz = vv[ib]
            cx, cy, cz = vv[ic]
            ux, uy, uz = bx - ax, by - ay, bz - az
            wx, wy, wz = cx - ax, cy - ay, cz - az
            nx, ny, nz = uy * wz - uz * wy, uz * wx - ux * wz, ux * wy - uy * wx
            ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            if ln < 1e-12:
                continue
            nx, ny, nz = nx / ln, ny / ln, nz / ln
            if ortho:
                vx, vy, vz = 0.0, 0.0, 1.0
            else:
                if az > -_NEAR or bz > -_NEAR or cz > -_NEAR:
                    continue        # no near-plane clipping: keep models in front of the camera
                mx, my, mz = -(ax + bx + cx) / 3.0, -(ay + by + cy) / 3.0, -(az + bz + cz) / 3.0
                ml = math.sqrt(mx * mx + my * my + mz * mz)
                vx, vy, vz = mx / ml, my / ml, mz / ml
            facing = nx * vx + ny * vy + nz * vz
            fl = flags[fi]
            if facing <= 0.0:
                if not fl & TWO_SIDED:
                    continue        # back-face culling
                nx, ny, nz = -nx, -ny, -nz
            if fl & UNLIT:
                r, g, b = colors[fi]
            else:
                r, g, b = light.shade(colors[fi], (nx, ny, nz), (vx, vy, vz))
            lut.append(_pack(r, g, b))
            bs = bias[fi]
            if ortho:
                tris.append((len(lut) - 1,
                             hw + ax * k_ortho, hh - ay * k_ortho, az + bs,
                             hw + bx * k_ortho, hh - by * k_ortho, bz + bs,
                             hw + cx * k_ortho, hh - cy * k_ortho, cz + bs))
            else:
                da, db, dc = -az, -bz, -cz
                tris.append((len(lut) - 1,
                             hw + ax * k_persp / da, hh - ay * k_persp / da, 1.0 / max(da - bs, _NEAR * 0.5),
                             hw + bx * k_persp / db, hh - by * k_persp / db, 1.0 / max(db - bs, _NEAR * 0.5),
                             hw + cx * k_persp / dc, hh - cy * k_persp / dc, 1.0 / max(dc - bs, _NEAR * 0.5)))
    return tris, lut


def _rasterise(tris, W, H, zb, ib):
    """Scan-convert triangles into the depth buffer ``zb`` and the face-id buffer ``ib``.

    Depth values are "bigger is nearer" and linear across the screen (camera z for orthographic
    views, 1/distance for perspective), so one plane equation per triangle is exact. A sample is
    inside a triangle when its centre is; shared edges are computed identically for both
    neighbours, so there are no cracks.
    """
    ceil = math.ceil
    for fid, x0, y0, q0, x1, y1, q1, x2, y2, q2 in tris:
        if y1 < y0:
            x0, y0, q0, x1, y1, q1 = x1, y1, q1, x0, y0, q0
        if y2 < y0:
            x0, y0, q0, x2, y2, q2 = x2, y2, q2, x0, y0, q0
        if y2 < y1:
            x1, y1, q1, x2, y2, q2 = x2, y2, q2, x1, y1, q1
        ys = int(ceil(y0 - 0.5))
        ye = int(ceil(y2 - 0.5))           # exclusive
        if ys < 0:
            ys = 0
        if ye > H:
            ye = H
        if ys >= ye:
            continue
        det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
        if -1e-12 < det < 1e-12:
            continue
        A = ((q1 - q0) * (y2 - y0) - (q2 - q0) * (y1 - y0)) / det
        B = ((x1 - x0) * (q2 - q0) - (x2 - x0) * (q1 - q0)) / det
        C = q0 - A * x0 - B * y0
        s02 = (x2 - x0) / (y2 - y0)
        s01 = (x1 - x0) / (y1 - y0) if y1 > y0 else 0.0
        s12 = (x2 - x1) / (y2 - y1) if y2 > y1 else 0.0
        for y in range(ys, ye):
            yc = y + 0.5
            xa = x0 + (yc - y0) * s02
            if yc < y1:
                xb = x0 + (yc - y0) * s01
            else:
                xb = x1 + (yc - y1) * s12
            if xa > xb:
                xa, xb = xb, xa
            xs = int(ceil(xa - 0.5))
            xe = int(ceil(xb - 0.5))       # exclusive
            if xs < 0:
                xs = 0
            if xe > W:
                xe = W
            if xs >= xe:
                continue
            q = A * (xs + 0.5) + B * yc + C
            base = y * W
            for i in range(base + xs, base + xe):
                if q > zb[i]:
                    zb[i] = q
                    ib[i] = fid
                q += A


def _outline_pass(ib, W, H, radius, lut, outline):
    """Mark the samples within ``radius`` of the silhouette and give them outline colours."""
    nfaces = len(lut)
    # Each row's coverage becomes one big integer (8 bits per sample) so the neighbourhood test
    # is a handful of shifts and ANDs instead of a Python loop over every sample.
    full = int.from_bytes(b"\x01" * W, "little")
    masks = []
    for y in range(H):
        row = ib[y * W:(y + 1) * W]
        masks.append(int.from_bytes(bytes([1 if v else 0 for v in row]), "little") if any(row) else 0)
    horiz = []
    for m in masks:
        h = m
        if m:
            for k in range(1, radius + 1):
                lo = int.from_bytes(b"\x01" * min(k, W), "little")                 # off-image counts as covered
                hi = lo << (8 * (W - min(k, W)))
                h &= ((m << (8 * k)) & full) | lo
                h &= (m >> (8 * k)) | hi
        horiz.append(h)
    for y in range(H):
        m = masks[y]
        if not m:
            continue
        e = horiz[y]
        for j in range(1, radius + 1):
            if y - j >= 0:
                e &= horiz[y - j]
            if y + j < H:
                e &= horiz[y + j]
        edge = (m & ~e).to_bytes(W, "little")
        pos = edge.find(b"\x01")
        base = y * W
        while pos != -1:
            ib[base + pos] += nfaces
            pos = edge.find(b"\x01", pos + 1)
    s = outline.strength
    extra = []
    for packed in lut:
        r, g, b = packed & 0xFFFF, (packed >> 16) & 0xFFFF, (packed >> 32) & 0xFFFF
        if outline.color is None:
            r, g, b = r * (1.0 - s), g * (1.0 - s), b * (1.0 - s)
        else:
            oc = outline.color
            r, g, b = r + (oc[0] * 255.0 - r) * s, g + (oc[1] * 255.0 - g) * s, b + (oc[2] * 255.0 - b) * s
        extra.append(_pack(r / 255.0, g / 255.0, b / 255.0) if packed else 0)
    lut.extend(extra)


def _resolve(ib, lut, W, H, ss, width, height):
    """Turn face ids into colours and box-filter ``ss`` x ``ss`` samples into each output pixel."""
    out = bytearray(width * height * 4)
    n2 = ss * ss
    cache = {0: b"\x00\x00\x00\x00"}
    for Y in range(height):
        rows = []
        empty = True
        for k in range(ss):
            seg = ib[(Y * ss + k) * W:(Y * ss + k + 1) * W]
            if empty and any(seg):
                empty = False
            rows.append(seg)
        if empty:
            continue
        cols = []
        for seg in rows:
            line = [lut[i] for i in seg]
            for j in range(ss):
                cols.append(line[j::ss])
        o = Y * width * 4
        for s in map(sum, zip(*cols)):
            px = cache.get(s)
            if px is None:
                a = s >> 48
                # premultiplied sums -> straight alpha: colour is the mean of the covered samples
                px = bytes(((((s & 0xFFFF) * 255 + a // 2) // a),
                            ((((s >> 16) & 0xFFFF) * 255 + a // 2) // a),
                            ((((s >> 32) & 0xFFFF) * 255 + a // 2) // a),
                            (a + n2 // 2) // n2))
                cache[s] = px
            out[o:o + 4] = px
            o += 4
    return out


def _shadow_pass(pixels, width, height, cam, shadow):
    """Composite a soft dark ellipse UNDER what is already in ``pixels``."""
    p = cam.project(shadow.center, width, height)
    if p is None:
        return
    cx, cy, depth = p
    ppu = cam.pixels_per_unit(height, depth)
    squash = max(abs(math.sin(math.radians(cam.pitch))), shadow.min_squash)
    rx = shadow.radius[0] * ppu
    ry = shadow.radius[1] * ppu * squash
    if rx < 0.5 or ry < 0.5:
        return
    sr, sg, sb = [c * 255.0 for c in shadow.color]
    x0, x1 = max(0, int(cx - rx)), min(width - 1, int(cx + rx) + 1)
    y0, y1 = max(0, int(cy - ry)), min(height - 1, int(cy + ry) + 1)
    for y in range(y0, y1 + 1):
        dy = (y + 0.5 - cy) / ry
        for x in range(x0, x1 + 1):
            dx = (x + 0.5 - cx) / rx
            d2 = dx * dx + dy * dy
            if d2 >= 1.0:
                continue
            i = (y * width + x) * 4
            a = pixels[i + 3] / 255.0
            if a >= 1.0:
                continue
            t = 1.0 - d2
            sa = shadow.opacity * t * t * (3.0 - 2.0 * t) * (1.0 - a)      # smooth falloff, under the model
            oa = a + sa
            if oa <= 0.0:
                continue
            pixels[i] = int((pixels[i] * a + sr * sa) / oa + 0.5)
            pixels[i + 1] = int((pixels[i + 1] * a + sg * sa) / oa + 0.5)
            pixels[i + 2] = int((pixels[i + 2] * a + sb * sa) / oa + 0.5)
            pixels[i + 3] = int(oa * 255.0 + 0.5)


def render(scene, width, height, ss=3):
    """Render ``scene`` to an ``Image`` of ``width`` x ``height`` pixels on a transparent background.

    ``ss`` is the supersampling factor: the frame is rasterised at ``ss`` times the size and
    box-filtered down (3 is the house setting; 1 is fastest and jagged).
    """
    if width <= 0 or height <= 0 or ss <= 0:
        raise ValueError("width, height and ss must be positive")
    W, H = width * ss, height * ss
    tris, lut = _collect(scene, W, H)
    zb = [-1e300] * (W * H)
    ib = [0] * (W * H)
    _rasterise(tris, W, H, zb, ib)
    if scene.outline is not None and scene.outline.strength > 0:
        radius = max(1, int(round(scene.outline.width * ss)))
        _outline_pass(ib, W, H, radius, lut, scene.outline)
    pixels = _resolve(ib, lut, W, H, ss, width, height)
    # ``scene.shadow`` is one Shadow or (for group shots) a list/tuple of them
    shadows = scene.shadow if isinstance(scene.shadow, (list, tuple)) else [scene.shadow]
    for shadow in shadows:
        if shadow is not None and shadow.opacity > 0:
            _shadow_pass(pixels, width, height, scene.camera, shadow)
    return Image(width, height, pixels)
