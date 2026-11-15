"""Low-poly renderer (art/lowpoly, docs/ART_LOWPOLY.md) and its committed output (assets/renders,
docs/SPEC_V2.md section 5).

The PNG writer is checked against an independent decoder written here with zlib + struct, the
rasteriser against a cube whose silhouette can be counted by hand, and every file the manifest
lists must be an RGBA PNG of the stated size.  Renders in this file are 32-48 px so the whole
module runs in about a second.  No display, no network, nothing written outside a temp folder.
"""
from __future__ import annotations

import json
import re
import struct
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RENDERS = REPO / "assets" / "renders"
sys.path.insert(0, str(REPO / "art"))       # art/ is dev-time only and not a package: import "lowpoly" from it

from lowpoly import mesh, pipeline, png, render  # noqa: E402
from lowpoly.models import duskie, iggy, nova, props  # noqa: E402

# What the first build wave must ship: name -> (width, height, frame count; 1 = a still).
REQUIRED = {
    "nova_bust": (512, 512, 1),
    "nova_icon": (256, 256, 1),
    "nova_spin": (192, 192, 24),
    "disc_spin": (96, 96, 12),
    "sync_loop": (256, 192, 24),
}

# Added in wave 3: low-poly Iggy and Duskie and the group shot.
REQUIRED_WAVE3 = {
    "iggy_bust": (512, 512, 1),
    "iggy_icon": (256, 256, 1),
    "iggy_spin": (192, 192, 24),
    "duskie_bust": (512, 512, 1),
    "duskie_icon": (256, 256, 1),
    "duskie_spin": (192, 192, 24),
    "trio_busts": (1200, 520, 1),
}

RED, GREEN, BLUE = (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)


def independent_decode(data):
    """Decode an 8-bit RGBA PNG with nothing but zlib + struct (does not use lowpoly.png).

    Returns ``(width, height, rgba bytes)``.  Handles the filter types 0-4 so it can read any
    conforming non-interlaced file.
    """
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "bad PNG signature"
    pos, header, idat, tags = 8, None, b"", []
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        assert crc == (zlib.crc32(tag + body) & 0xFFFFFFFF), "bad CRC in %r" % tag
        tags.append(tag)
        if tag == b"IHDR":
            header = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length
    assert tags[0] == b"IHDR" and tags[-1] == b"IEND", tags
    width, height, depth, ctype, comp, filt, interlace = header
    assert (depth, ctype, comp, filt, interlace) == (8, 6, 0, 0, 0), header
    raw = zlib.decompress(idat)
    stride = width * 4
    assert len(raw) == (stride + 1) * height
    out = bytearray()
    prev = bytearray(stride)
    for y in range(height):
        ftype = raw[y * (stride + 1)]
        row = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = row[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if ftype == 1:
                row[i] = (row[i] + a) & 255
            elif ftype == 2:
                row[i] = (row[i] + b) & 255
            elif ftype == 3:
                row[i] = (row[i] + ((a + b) >> 1)) & 255
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                row[i] = (row[i] + (a if (pa <= pb and pa <= pc) else (b if pb <= pc else c))) & 255
            else:
                assert ftype == 0, "unknown filter %d" % ftype
        out += row
        prev = row
    return width, height, bytes(out)


def make_pattern(width, height):
    """Deterministic RGBA bytes with gradients, noise and every alpha value."""
    px = bytearray()
    seed = 12345
    for y in range(height):
        for x in range(width):
            seed = (seed * 1103515245 + 12345) & 0x7FFFFFFF
            px += bytes(((x * 255) // max(1, width - 1), (y * 255) // max(1, height - 1),
                         (seed >> 8) & 255, (x * 37 + y * 91) & 255))
    return bytes(px)


def flat_lighting():
    """Every face keeps exactly its own colour: makes rendered pixels predictable."""
    return render.Lighting(ambient=(1.0, 1.0, 1.0), lights=[])


def front_camera(units=4.0):
    return render.Camera(target=(0.0, 0.0, 0.0), ortho=units)


def scene_of(*items, **kwargs):
    scene = render.Scene(kwargs.pop("camera", None) or front_camera(), kwargs.pop("lighting", None) or flat_lighting(),
                         **kwargs)
    for item in items:
        if isinstance(item, tuple):
            scene.add(*item)
        else:
            scene.add(item)
    return scene


def rgb8(color):
    return tuple(int(round(c * 255)) for c in mesh.rgb(color))


class PngCodec(unittest.TestCase):
    def test_round_trip_against_an_independent_decoder(self):
        for w, h in [(1, 1), (7, 5), (33, 17), (64, 64)]:
            pixels = make_pattern(w, h)
            data = png.encode_png(w, h, pixels)
            self.assertEqual(independent_decode(data), (w, h, pixels), "%dx%d" % (w, h))
            dw, dh, back = png.decode_png(data)                 # and the project's own reader agrees
            self.assertEqual((dw, dh, bytes(back)), (w, h, pixels))

    def test_header_and_chunks(self):
        data = png.encode_png(3, 2, bytes(3 * 2 * 4))
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(struct.unpack(">I4sIIBBBBB", data[8:8 + 21]), (13, b"IHDR", 3, 2, 8, 6, 0, 0, 0))
        self.assertEqual(data[-12:-4], b"\x00\x00\x00\x00IEND")
        info = png.png_info(data)
        self.assertEqual((info["width"], info["height"], info["bit_depth"], info["color_type"]), (3, 2, 8, 6))
        self.assertTrue(info["has_alpha"])

    def test_encoding_is_deterministic(self):
        pixels = make_pattern(20, 9)
        self.assertEqual(png.encode_png(20, 9, pixels), png.encode_png(20, 9, bytearray(pixels)))

    def test_write_and_read_a_file(self):
        pixels = make_pattern(9, 4)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "t.png"
            size = png.write_png(path, 9, 4, pixels)
            self.assertEqual(size, path.stat().st_size)
            self.assertEqual(independent_decode(path.read_bytes()), (9, 4, pixels))
            w, h, back = png.read_png(path)
            self.assertEqual((w, h, bytes(back)), (9, 4, pixels))

    def test_bad_input_is_refused(self):
        with self.assertRaises(ValueError):
            png.encode_png(2, 2, bytes(15))                     # wrong length
        with self.assertRaises(ValueError):
            png.encode_png(0, 2, b"")
        good = png.encode_png(2, 2, bytes(16))
        with self.assertRaises(ValueError):
            png.decode_png(b"not a png at all")
        broken = bytearray(good)
        broken[20] ^= 0xFF                                      # inside IHDR: the CRC no longer matches
        with self.assertRaises(ValueError):
            png.decode_png(bytes(broken))
        with self.assertRaises(ValueError):
            png.png_info(good[:-12])                            # IEND cut off

    def test_reads_rgb_and_every_filter_type(self):
        w, h = 5, 4
        rows = [bytes(v for x in range(w) for v in (x * 40 + y * 3, y * 60, (x * y * 10) & 255)) for y in range(h)]
        want = b"".join(bytes(v for i in range(0, len(r), 3) for v in (r[i], r[i + 1], r[i + 2], 255)) for r in rows)
        raw = bytearray()
        prev = bytes(w * 3)
        for y, row in enumerate(rows):
            ftype = y % 5 if y % 5 else 4                       # 4, 1, 2, 3
            raw.append(ftype)
            for i in range(len(row)):
                a = row[i - 3] if i >= 3 else 0
                b = prev[i]
                c = prev[i - 3] if i >= 3 else 0
                if ftype == 1:
                    pred = a
                elif ftype == 2:
                    pred = b
                elif ftype == 3:
                    pred = (a + b) >> 1
                else:
                    p = a + b - c
                    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                    pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                raw.append((row[i] - pred) & 255)
            prev = row

        def chunk(tag, body):
            return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

        data = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))
        dw, dh, got = png.decode_png(data)
        self.assertEqual((dw, dh, bytes(got)), (w, h, want))


class MeshBasics(unittest.TestCase):
    def test_primitive_triangle_counts(self):
        self.assertEqual(len(mesh.box()), 12)
        self.assertEqual([len(mesh.icosphere(1.0, s)) for s in (0, 1, 2)], [20, 80, 320])
        self.assertEqual(len(mesh.ellipsoid(segments=8, rings=4)), 8 * (2 * 4 - 2))
        self.assertEqual(len(mesh.cylinder(segments=6)), 6 * 4)
        self.assertEqual(len(mesh.cylinder(segments=6, radius_top=0)), 6 * 2)
        self.assertEqual(len(mesh.star4()), 16)
        self.assertEqual(len(mesh.tube([(0, 0, 0), (0, 1, 0), (0.5, 2, 0)], [0.3, 0.2, 0.0], segments=5)), 5 * 2 + 5 + 5)

    def test_closed_primitives_face_outwards(self):
        """Every face of a convex solid centred on the origin must have its normal pointing away from it."""
        solids = [mesh.box((2, 1, 3)), mesh.icosphere((1.0, 0.6, 0.8), 1), mesh.ellipsoid((1, 0.7, 0.9), 8, 5),
                  mesh.cylinder(1.0, 2.0, 7).translate(0, -1, 0), mesh.star4(),
                  mesh.cone_between((0, -1, 0), (0, 1, 0), 0.8, 0.0, 6),
                  mesh.prism(mesh.ngon(7, 1.0), 0.5)]
        for m in solids:
            for fi in range(len(m)):
                self.assertGreater(mesh.v_dot(m.centroid(fi), m.normal(fi)), 0.0)
            mirrored = m.mirrored("x")                         # a mirror must not turn it inside out
            for fi in range(len(mirrored)):
                self.assertGreater(mesh.v_dot(mirrored.centroid(fi), mirrored.normal(fi)), 0.0)

    def test_transforms_follow_the_documented_handedness(self):
        def moved(m, p):
            return tuple(round(c, 6) for c in mesh.apply(m, p))

        self.assertEqual(moved(mesh.rot_y(90), (0, 0, 1)), (1, 0, 0))       # front turns to the viewer's right
        self.assertEqual(moved(mesh.rot_x(90), (0, 1, 0)), (0, 0, 1))       # top tips forwards
        self.assertEqual(moved(mesh.rot_z(90), (0, 1, 0)), (-1, 0, 0))      # top tips to the viewer's left
        both = mesh.compose(mesh.translate(1, 0, 0), mesh.scale(2))         # first move, then scale
        self.assertEqual(moved(both, (0, 0, 0)), (2, 0, 0))

    def test_paint_recolours_by_region_rule(self):
        m = mesh.box((2, 2, 2), "#000000")
        n = m.paint("#ffffff", lambda c, nrm, i: c[1] > 0.5)               # only the lid
        self.assertEqual(n, 2)
        self.assertEqual(sorted(set(m.colors)), [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)])
        self.assertEqual(m.paint("#ff0000", lambda c, nrm, i: c[1] > 5), 0)  # a rule that matches nothing says so

    def test_raycast_and_decal(self):
        target = mesh.box((2, 2, 2))
        t, _face = target.raycast((0.2, 0.1, 5.0), (0, 0, -1))
        self.assertAlmostEqual(t, 4.0)
        self.assertIsNone(target.raycast((3.0, 0.0, 5.0), (0, 0, -1)))
        patch = mesh.decal(target, mesh.rect(0.5, 0.5), RED)
        self.assertEqual(len(patch), 4)
        for v in patch.verts:
            self.assertAlmostEqual(v[2], 1.0 + mesh.DECAL_LIFT)
        self.assertTrue(all(b > 0 for b in patch.bias))
        with self.assertRaises(ValueError):                               # a decal that misses must not pass silently
            mesh.decal(target, mesh.rect(0.5, 0.5, cx=3.0), RED)

    def test_outline_helpers(self):
        half = mesh.clip_halfplane(mesh.rect(2, 2), (0, 0), (0, 1))        # keep what is below y=0
        self.assertEqual(sorted(set(round(y, 6) for _x, y in half)), [-1.0, 0.0])
        self.assertEqual(len(mesh.stroke([(0, 0), (1, 0), (1, 1)], 0.1)), 3)  # two segments and one joint
        self.assertEqual(len(mesh.facet_angles([16, 52, 80, 108, 136, 164])), 12)
        self.assertEqual(mesh.rgb("#ff8000"), (1.0, 128 / 255.0, 0.0))
        with self.assertRaises(ValueError):
            mesh.rgb("#fff")


class CubeRender(unittest.TestCase):
    """A 2-unit cube seen straight on by an orthographic camera that fits 4 units into the frame:
    the silhouette is exactly the middle half of the picture."""

    def test_silhouette_pixel_count(self):
        for size, ss in [(32, 1), (40, 1), (48, 3)]:
            image = render.render(scene_of(mesh.box((2, 2, 2), RED)), size, size, ss=ss)
            self.assertEqual((image.width, image.height, len(image.pixels)), (size, size, size * size * 4))
            self.assertEqual(image.covered(255), (size // 2) ** 2, "size %d ss %d" % (size, ss))
            self.assertEqual(image.covered(1), (size // 2) ** 2)          # edges fall on pixel borders: no fringe
            q = size // 4
            self.assertEqual(image.pixel(q, q), (255, 0, 0, 255))         # first pixel inside
            self.assertEqual(image.pixel(q - 1, q), (0, 0, 0, 0))         # last pixel outside: fully transparent
            self.assertEqual(image.pixel(size - q - 1, size - q - 1), (255, 0, 0, 255))
            self.assertEqual(image.pixel(size - q, size - q - 1), (0, 0, 0, 0))

    def test_rendering_is_deterministic(self):
        def once():
            cam = render.Camera(target=(0, 0, 0), yaw=30, pitch=20, distance=9, fov=30)
            s = render.Scene(cam, render.house_lighting(), outline=render.Outline(),
                             shadow=render.Shadow((0, -1, 0), 1.4))
            s.add(mesh.box((2, 2, 2), "#e8894a"), mesh.rot_y(20))
            return bytes(render.render(s, 40, 40, ss=3).pixels)

        self.assertEqual(once(), once())

    def test_supersampling_softens_only_the_edge(self):
        turned = (mesh.box((2, 2, 2), RED), mesh.rot_z(30))
        hard = render.render(scene_of(turned), 40, 40, ss=1)
        soft = render.render(scene_of(turned), 40, 40, ss=3)
        self.assertEqual(hard.covered(1), hard.covered(255))               # one sample per pixel: all or nothing
        partial = soft.covered(1) - soft.covered(255)
        self.assertGreater(partial, 20)                                    # a fringe of part-covered pixels...
        self.assertLess(partial, 120)                                      # ...and only a fringe
        area = sum(soft.pixels[3::4]) / 255.0                              # coverage adds up to the true area
        self.assertAlmostEqual(area, 400.0, delta=2.0)
        self.assertEqual(soft.pixel(20, 20), (255, 0, 0, 255))             # colours are not smeared inside

    def test_nearer_faces_hide_farther_ones(self):
        far = mesh.box((2, 2, 0.2), BLUE).translate(0, 0, -1)
        near = mesh.box((1, 1, 0.2), RED).translate(0, 0, 1)
        for items in ([far, near], [near, far]):                           # the order of drawing must not matter
            image = render.render(scene_of(*items), 40, 40, ss=1)
            self.assertEqual(image.pixel(20, 20), (255, 0, 0, 255))        # the near box wins in the middle
            self.assertEqual(image.pixel(12, 12), (0, 0, 255, 255))        # the far box shows round it
            self.assertEqual(image.covered(255), 400)                      # 20 x 20: the far box's silhouette
            reds = sum(1 for i in range(0, len(image.pixels), 4) if image.pixels[i] == 255)
            self.assertEqual(reds, 100)                                    # 10 x 10

    def test_depth_buffer_not_culling_decides(self):
        """With culling switched off (TWO_SIDED) the cube's far side is rasterised too and must lose."""
        cube = mesh.box((2, 2, 2), GREEN)
        cube.paint(RED, lambda c, n, i: n[2] > 0.5)                        # front face
        cube.paint(BLUE, lambda c, n, i: n[2] < -0.5)                      # back face
        cube.set_flags(mesh.TWO_SIDED)
        for camera in (front_camera(), render.Camera(target=(0, 0, 0), distance=8, fov=30)):
            front = render.render(scene_of(cube, camera=camera), 40, 40, ss=1)
            self.assertEqual(front.pixel(20, 20), (255, 0, 0, 255))
            back = render.render(scene_of((cube, mesh.rot_y(180)), camera=camera), 40, 40, ss=1)
            self.assertEqual(back.pixel(20, 20), (0, 0, 255, 255))

    def test_intersecting_meshes_split_along_the_depth_line(self):
        """Two crossed slabs: each must be in front on its own side (a painter's algorithm could not do this)."""
        a = (mesh.box((3, 1, 0.1), RED), mesh.rot_y(35))                   # the viewer's right end comes forward
        b = (mesh.box((3, 1, 0.1), BLUE), mesh.rot_y(-35))
        image = render.render(scene_of(a, b), 40, 40, ss=1)
        self.assertEqual(image.pixel(8, 20)[:3], (255, 0, 0))              # viewer's left: the red slab is nearer
        self.assertEqual(image.pixel(31, 20)[:3], (0, 0, 255))
        flipped = render.render(scene_of(b, a), 40, 40, ss=1)
        self.assertEqual(bytes(image.pixels), bytes(flipped.pixels))

    def test_back_faces_are_culled_unless_two_sided(self):
        square = [(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)]         # counter-clockwise from +z
        facing = mesh.polygon(square, RED)
        self.assertEqual(render.render(scene_of(facing), 32, 32, ss=1).covered(), 256)
        self.assertEqual(render.render(scene_of((facing, mesh.rot_y(180))), 32, 32, ss=1).covered(), 0)
        paper = mesh.polygon(square, RED, two_sided=True)
        self.assertEqual(render.render(scene_of((paper, mesh.rot_y(180))), 32, 32, ss=1).covered(), 256)

    def test_perspective_makes_near_things_bigger(self):
        cam = render.Camera(target=(0, 0, 0), distance=8, fov=30)
        near = render.render(scene_of(mesh.box((1, 1, 0.01), RED).translate(0, 0, 3), camera=cam), 48, 48, ss=1)
        far = render.render(scene_of(mesh.box((1, 1, 0.01), RED).translate(0, 0, -3), camera=cam), 48, 48, ss=1)
        self.assertGreater(near.covered(), 3 * far.covered())
        x, y, depth = cam.project((0.0, 0.0, 0.0), 48, 48)
        self.assertEqual((round(x, 6), round(y, 6), round(depth, 6)), (24.0, 24.0, 8.0))
        self.assertIsNone(cam.project((0.0, 0.0, 20.0), 48, 48))           # behind the camera

    def test_camera_yaw_and_pitch(self):
        cube = mesh.box((2, 2, 2), GREEN)
        cube.paint(RED, lambda c, n, i: n[0] > 0.5)                        # the side on the viewer's right
        cube.paint(BLUE, lambda c, n, i: n[1] > 0.5)                       # the lid
        yawed = render.render(scene_of(cube, camera=render.Camera(yaw=90, ortho=4.0)), 32, 32, ss=1)
        self.assertEqual(yawed.pixel(16, 16), (255, 0, 0, 255))            # walked round to the right-hand side
        above = render.render(scene_of(cube, camera=render.Camera(pitch=90, ortho=4.0)), 32, 32, ss=1)
        self.assertEqual(above.pixel(16, 16), (0, 0, 255, 255))            # looking straight down

    def test_flat_shading_one_colour_per_face(self):
        cube = (mesh.box((2, 2, 2), "#808080"), mesh.compose(mesh.rot_y(40), mesh.rot_x(25)))
        image = render.render(scene_of(cube, lighting=render.house_lighting()), 48, 48, ss=1)
        colours = set(image.pixel(x, y) for y in range(48) for x in range(48)) - {(0, 0, 0, 0)}
        self.assertEqual(len(colours), 3)                                  # three visible faces, three flat colours

    def test_house_lighting_has_a_pink_rim_from_behind_right(self):
        light = render.house_lighting()
        black = (0.0, 0.0, 0.0)
        view = (0.0, 0.0, 1.0)
        rim = light.shade(black, mesh.v_norm((0.80, 0.28, -0.53)), view)   # a face turned towards the rim light
        self.assertGreater(rim[0], 0.6)                                    # it glows even on black...
        self.assertGreater(rim[0], rim[2])                                 # ...pink: red over blue over green
        self.assertGreater(rim[2], rim[1])
        front = light.shade(black, (0.0, 0.0, 1.0), view)
        self.assertLess(max(front), 0.1)                                   # no rim on faces looking at the camera
        left = light.shade((0.5, 0.5, 0.5), mesh.v_norm((-0.5, 0.5, 0.7)), view)
        right = light.shade((0.5, 0.5, 0.5), mesh.v_norm((0.5, -0.5, 0.7)), view)
        self.assertGreater(sum(left), sum(right))                          # the key light is upper left
        self.assertGreater(left[0], left[2])                               # and warm
        off = render.house_lighting(rim=0.0).shade(black, mesh.v_norm((0.80, 0.28, -0.53)), view)
        self.assertLess(max(off), 0.02)

    def test_unlit_faces_keep_their_colour(self):
        glint = mesh.box((2, 2, 2), "#ffffff").set_flags(mesh.UNLIT)
        image = render.render(scene_of(glint, lighting=render.house_lighting()), 32, 32, ss=1)
        self.assertEqual(image.pixel(16, 16), (255, 255, 255, 255))

    def test_decal_wins_over_the_surface_it_sits_on(self):
        base = mesh.box((2, 2, 2), BLUE)
        patch = mesh.decal(base, mesh.rect(1.0, 1.0), RED)
        image = render.render(scene_of(mesh.merge(base, patch)), 40, 40, ss=1)
        self.assertEqual(image.pixel(20, 20), (255, 0, 0, 255))
        self.assertEqual(image.pixel(12, 12), (0, 0, 255, 255))

    def test_outline_darkens_only_the_silhouette(self):
        plain = render.render(scene_of(mesh.box((2, 2, 2), RED)), 40, 40, ss=1)
        lined = render.render(scene_of(mesh.box((2, 2, 2), RED), outline=render.Outline(strength=0.5, width=1.0)),
                              40, 40, ss=1)
        self.assertEqual(lined.covered(255), plain.covered(255))           # drawn inside: the silhouette is unchanged
        self.assertEqual(lined.pixel(20, 20), (255, 0, 0, 255))
        self.assertEqual(lined.pixel(10, 20), (128, 0, 0, 255))            # the outermost ring is darker
        self.assertEqual(lined.pixel(11, 20), (255, 0, 0, 255))
        dark = sum(1 for y in range(40) for x in range(40) if lined.pixel(x, y) == (128, 0, 0, 255))
        self.assertEqual(dark, 4 * 20 - 4)                                 # exactly the one-pixel border
        tinted = render.render(scene_of(mesh.box((2, 2, 2), RED), outline=render.Outline("#0000ff", 1.0, 1.0)),
                               40, 40, ss=1)
        self.assertEqual(tinted.pixel(10, 20), (0, 0, 255, 255))

    def test_ground_shadow_is_soft_and_under_the_model(self):
        cam = render.Camera(target=(0, 0, 0), pitch=25, ortho=5.0)
        bare = render.render(scene_of(mesh.box((1, 1, 1), RED), camera=cam), 48, 48, ss=1)
        shadow = render.Shadow(center=(0.0, -0.5, 0.0), radius=1.8, opacity=0.4, color="#000000")
        image = render.render(scene_of(mesh.box((1, 1, 1), RED), camera=cam, shadow=shadow), 48, 48, ss=1)
        self.assertGreater(image.covered(1), bare.covered(1))
        for y in range(48):
            for x in range(48):
                if bare.pixel(x, y)[3] == 255:                             # the model's own pixels are untouched
                    self.assertEqual(image.pixel(x, y), bare.pixel(x, y))
        alphas = sorted(set(image.pixel(x, y)[3] for y in range(48) for x in range(48)
                            if bare.pixel(x, y)[3] == 0))
        self.assertGreater(len(alphas), 8)                                 # a gradient, not a hard disc
        self.assertLessEqual(max(alphas), int(0.4 * 255) + 1)
        self.assertEqual(image.pixel(0, 0), (0, 0, 0, 0))

    def test_image_helpers(self):
        image = render.render(scene_of(mesh.box((2, 2, 2), RED)), 32, 32, ss=1)
        flat = image.flattened("#00ff00")
        self.assertEqual(flat.pixel(0, 0), (0, 255, 0, 255))
        self.assertEqual(flat.pixel(16, 16), (255, 0, 0, 255))
        sheet = render.contact_sheet([image, image, image], columns=2, gap=2)
        self.assertEqual((sheet.width, sheet.height), (2 * 32 + 3 * 2, 2 * 32 + 3 * 2))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cube.png"
            image.save(path)
            self.assertEqual(independent_decode(path.read_bytes()), (32, 32, bytes(image.pixels)))
        with self.assertRaises(ValueError):
            render.render(scene_of(mesh.box()), 0, 10)


class NovaModel(unittest.TestCase):
    """Canon checks that can be made on the mesh or on a thumbnail (docs/CHARACTERS.md, Nova)."""

    @classmethod
    def setUpClass(cls):
        cls.bust = nova.build()

    def view(self, turn=0.0, size=48):
        cam = render.Camera(target=(0.0, 0.2, 0.0), ortho=6.0)
        scene = render.Scene(cam, flat_lighting()).add(self.bust, mesh.rot_y(turn))
        return cam, render.render(scene, size, size, ss=1)

    def test_triangle_budget(self):
        self.assertGreaterEqual(len(self.bust), 300)
        self.assertLessEqual(len(self.bust), 1500)
        self.assertEqual(len(self.bust.colors), len(self.bust.faces))
        self.assertEqual(len(self.bust.flags), len(self.bust.faces))
        self.assertEqual(len(self.bust.bias), len(self.bust.faces))

    def test_only_canon_colours(self):
        allowed = set(mesh.rgb(c) for c in (
            nova.NAVY, nova.NAVY_SHADE, nova.WHITE, nova.WHITE_SHADE, nova.EAR_IN, nova.EAR_PERI, nova.IRIS,
            nova.IRIS_HI, nova.IRIS_LO, nova.NOSE, nova.TONGUE, nova.TEE, nova.TEE_SHADE, nova.SMILEY,
            nova.SMILEY_INK, "#ffffff"))
        self.assertLessEqual(set(self.bust.colors), allowed)
        for needed in (nova.NAVY, nova.WHITE, nova.EAR_IN, nova.EAR_PERI, nova.IRIS, nova.NOSE, nova.TEE,
                       nova.SMILEY):
            self.assertIn(mesh.rgb(needed), set(self.bust.colors), needed)

    def test_ears_are_the_star(self):
        """Must-have 1: each ear is roughly as tall as the whole head, and they stand well apart."""
        (x0, y0, _z0), (x1, y1, _z1) = self.bust.bounds()
        head_top = max(y for y, _rx, _rzf, _rzb in nova.HEAD_RINGS)
        head_bottom = min(y for y, _rx, _rzf, _rzb in nova.HEAD_RINGS)
        head_height = head_top - head_bottom
        self.assertGreaterEqual(y1 - head_top, 0.95 * head_height)
        head_width = 2 * max(rx for _y, rx, _rzf, _rzb in nova.HEAD_RINGS)
        self.assertGreater(x1 - x0, 1.25 * head_width)                     # the ears overhang the head
        self.assertAlmostEqual(x0, -x1, places=6)                          # and he is symmetric
        self.assertAlmostEqual(y0, nova.BASE_Y, places=6)

    def test_front_view_reads_as_nova(self):
        cam, image = self.view(0.0)

        def at(point):
            x, y, _d = cam.project(point, image.width, image.height)
            return image.pixel(int(x), int(y))[:3]

        self.assertEqual(at((0.0, 0.62, 1.2)), rgb8(nova.NAVY))            # forehead between the dashes: the mask
        self.assertEqual(at((0.0, -0.62, 1.2)), rgb8(nova.WHITE))          # chin: white lower face
        self.assertEqual(at((0.55, -1.9, 1.2)), rgb8(nova.TEE))            # orange tee
        self.assertEqual(at((0.0, -1.0, 1.2)), rgb8(nova.WHITE))           # the white dash on the navy neck
        self.assertEqual(at((0.0, -1.15, 1.2)), rgb8(nova.NAVY))
        found = set(image.pixel(x, y)[:3] for y in range(image.height) for x in range(image.width))
        for needed in (nova.IRIS, nova.EAR_IN, nova.EAR_PERI, nova.SMILEY):
            self.assertIn(rgb8(needed), found, needed)

    def test_back_of_the_head_is_navy(self):
        cam, image = self.view(180.0)
        counts = {}
        for y in range(image.height):
            for x in range(image.width):
                px = image.pixel(x, y)
                if px[3] == 255:
                    counts[px[:3]] = counts.get(px[:3], 0) + 1
        total = float(sum(counts.values()))
        self.assertGreater(counts.get(rgb8(nova.NAVY), 0) / total, 0.55)   # head, ear backs and neck
        self.assertNotIn(rgb8(nova.IRIS), counts)                          # no face from behind
        self.assertNotIn(rgb8(nova.SMILEY), counts)
        self.assertNotIn(rgb8(nova.EAR_PERI), counts)                      # ear backs are navy, not the inner colour
        x, y, _d = cam.project((0.0, 0.1, -1.2), image.width, image.height)
        self.assertEqual(image.pixel(int(x), int(y))[:3], rgb8(nova.NAVY))

    def test_side_view_still_shows_the_marks(self):
        _cam, image = self.view(-90.0)                                     # his own left side towards the camera
        found = set(image.pixel(x, y)[:3] for y in range(image.height) for x in range(image.width))
        for needed in (nova.NAVY, nova.WHITE, nova.TEE):
            self.assertIn(rgb8(needed), found, needed)

    def test_head_pose_moves_the_head_and_not_the_shoulders(self):
        still = nova.build()
        posed = nova.build(turn=15.0, nod=4.0, tilt=-5.0)
        self.assertEqual(len(posed), len(still))
        self.assertIs(nova.build(), still)                                 # cached: scenes can share it
        moved = [i for i, (a, b) in enumerate(zip(still.verts, posed.verts)) if a != b]
        self.assertTrue(moved)
        head, body = nova.parts()
        self.assertEqual(len(moved), len(head.verts))                      # every head vertex...
        self.assertEqual(max(moved), len(head.verts) - 1)                  # ...and nothing after them
        low = min(v[1] for v in posed.verts)
        self.assertAlmostEqual(low, nova.BASE_Y, places=6)                 # the base still sits on the ground

    def test_turntable_frames_stay_inside_the_picture(self):
        for i in (0, 3, 6, 9, 12, 18):
            scene = nova.spin_scene(i, 24)
            image = render.render(scene, 48, 48, ss=1)
            self.assertGreater(image.covered(255), 300)
            edge = [image.pixel(x, 0)[3] for x in range(48)] + [image.pixel(0, y)[3] for y in range(48)]
            edge += [image.pixel(47, y)[3] for y in range(48)]
            self.assertEqual(max(edge), 0, "frame %d touches the border" % i)


class Props(unittest.TestCase):
    def test_props_build_and_stay_small(self):
        self.assertLessEqual(len(props.disc()), 600)
        self.assertLessEqual(len(props.sd_card()), 200)
        self.assertEqual(len(props.star()), 16)
        (x0, y0, z0), (x1, y1, z1) = props.disc().bounds()
        self.assertAlmostEqual(x1, 1.0, places=6)
        self.assertAlmostEqual(y0, -1.0, places=6)
        self.assertLess(z1 - z0, 0.2)                                      # a disc, not a puck

    def test_disc_has_a_hole_and_spins(self):
        cam = front_camera(2.5)
        a = render.render(render.Scene(cam, flat_lighting()).add(props.disc(0.0)), 48, 48, ss=1)
        b = render.render(render.Scene(cam, flat_lighting()).add(props.disc(90.0)), 48, 48, ss=1)
        self.assertEqual(a.pixel(24, 24), (0, 0, 0, 0))                    # you can see through the middle
        self.assertEqual(a.pixel(24, 10)[3], 255)
        self.assertEqual(a.covered(255), b.covered(255))                   # same silhouette...
        self.assertNotEqual(bytes(a.pixels), bytes(b.pixels))              # ...different facets: the spin shows
        colours = set(a.pixel(x, y)[:3] for y in range(48) for x in range(48) if a.pixel(x, y)[3])
        self.assertGreater(len(colours), 12)                               # iridescent, not one flat pink

    def test_sync_loop_disc_passes_behind_and_in_front(self):
        """Frame 0 has the disc in front of the tee; half a loop later it is behind the head and ears."""
        w, h = 64, 48

        def disc_pixels(i):
            """How many pixels the disc changes in frame ``i`` (the frame with and without its last item)."""
            scene = nova.sync_scene(i, 24)
            self.assertEqual(len(scene.items), 2)                          # the posed bust, then the disc
            scene.lighting = flat_lighting()
            scene.outline = scene.shadow = None
            with_disc = render.render(scene, w, h, ss=1)
            scene.items.pop()
            base = render.render(scene, w, h, ss=1)
            self.assertGreater(base.covered(255), 200)
            return sum(1 for k in range(0, len(base.pixels), 4) if base.pixels[k:k + 4] != with_disc.pixels[k:k + 4])

        in_front, behind = disc_pixels(0), disc_pixels(12)
        self.assertGreater(in_front, 25)                                   # the whole disc shows in front
        self.assertLess(behind, in_front * 0.6)                            # most of it is hidden behind him
        self.assertGreater(disc_pixels(6), 15)                             # and it is out in the open at the side

    def test_sync_loop_frames_stay_inside_the_picture(self):
        for i in range(0, 24, 3):
            image = render.render(nova.sync_scene(i, 24), 64, 48, ss=1)
            edge = [image.pixel(x, 0)[3] for x in range(64)] + [image.pixel(0, y)[3] for y in range(48)]
            edge += [image.pixel(63, y)[3] for y in range(48)]
            self.assertEqual(max(edge), 0, "frame %d touches the border" % i)


class Pipeline(unittest.TestCase):
    def test_job_and_manifest_entry_shapes(self):
        still = pipeline.Job("thing", (64, 32), lambda i, n: None)
        self.assertEqual(still.filenames(), ["thing.png"])
        self.assertEqual(pipeline.manifest_entry(still), {"file": "thing.png", "size": [64, 32]})
        anim = pipeline.Job("turn", (16, 16), lambda i, n: None, frames=3, fps=8)
        self.assertEqual(anim.filenames(), ["turn_00.png", "turn_01.png", "turn_02.png"])
        self.assertEqual(pipeline.manifest_entry(anim),
                         {"frames": ["turn_00.png", "turn_01.png", "turn_02.png"], "fps": 8, "size": [16, 16]})
        with self.assertRaises(ValueError):
            pipeline.Job("Bad Name", (1, 1), lambda i, n: None)

    def test_discover_finds_every_required_job(self):
        jobs = dict((job.name, (mod, job)) for mod, job in pipeline.discover())
        for name, (w, h, frames) in REQUIRED.items():
            self.assertIn(name, jobs)
            self.assertEqual((jobs[name][1].size, jobs[name][1].frames), ((w, h), frames), name)
        self.assertEqual(sorted(j.name for _m, j in pipeline.select(pipeline.discover(), ["props"])),
                         sorted(j.name for j in props.JOBS))
        with self.assertRaises(ValueError):
            pipeline.select(pipeline.discover(), ["no_such_model"])

    def test_run_writes_files_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "renders"
            report = pipeline.run(only=["star", "disc_spin"], frames=3, out_dir=out, processes=1, log=None)
            self.assertEqual(report["disc_spin"]["frames"], 3)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["version"], 1)
            self.assertEqual(manifest["renders"]["star"], {"file": "star.png", "size": [64, 64]})
            self.assertEqual(manifest["renders"]["disc_spin"]["frames"],
                             ["disc_spin_00.png", "disc_spin_01.png", "disc_spin_02.png"])
            self.assertEqual(sorted(p.name for p in out.iterdir()),
                             ["disc_spin_00.png", "disc_spin_01.png", "disc_spin_02.png", "manifest.json", "star.png"])
            w, h, _px = independent_decode((out / "disc_spin_01.png").read_bytes())
            self.assertEqual((w, h), (96, 96))
            # a shorter re-run removes the frames it no longer lists and keeps other entries
            pipeline.run(only=["disc_spin"], frames=2, out_dir=out, processes=1, log=None)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["renders"]["disc_spin"]["frames"]), 2)
            self.assertIn("star", manifest["renders"])
            self.assertFalse((out / "disc_spin_02.png").exists())

    def test_build_script_lists_jobs(self):
        import contextlib
        import importlib.util
        import io

        spec = importlib.util.spec_from_file_location("lowpoly_build", str(REPO / "art" / "lowpoly" / "build.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.assertEqual(module.main(["--list", "--only", "nova"]), 0)
        listed = [line.split()[0] for line in buf.getvalue().splitlines()]
        self.assertEqual(sorted(listed), sorted(j.name for j in nova.JOBS))
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(["--list", "--only", "nope"]), 2)


class CommittedRenders(unittest.TestCase):
    """assets/renders/manifest.json (docs/SPEC_V2.md section 5) and the files it lists."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((RENDERS / "manifest.json").read_text(encoding="utf-8"))

    def entries(self):
        for name, entry in sorted(self.manifest["renders"].items()):
            files = [entry["file"]] if "file" in entry else list(entry["frames"])
            yield name, entry, files

    def test_schema(self):
        self.assertEqual(self.manifest["version"], 1)
        self.assertEqual(sorted(self.manifest), ["renders", "version"])
        self.assertIsInstance(self.manifest["renders"], dict)
        for name, entry in self.manifest["renders"].items():
            self.assertRegex(name, r"^[a-z0-9_]+$")
            size = entry.get("size")
            self.assertTrue(isinstance(size, list) and len(size) == 2, name)
            self.assertTrue(all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in size), name)
            if "file" in entry:                                            # a still
                self.assertEqual(sorted(entry), ["file", "size"], name)
                self.assertEqual(entry["file"], name + ".png")
            else:                                                          # a frame strip
                self.assertEqual(sorted(entry), ["fps", "frames", "size"], name)
                self.assertIsInstance(entry["fps"], int)
                self.assertTrue(1 <= entry["fps"] <= 60, name)
                self.assertGreaterEqual(len(entry["frames"]), 2, name)
                self.assertEqual(entry["frames"], ["%s_%02d.png" % (name, i) for i in range(len(entry["frames"]))])

    def test_required_renders_are_listed(self):
        for name, (w, h, frames) in REQUIRED.items():
            self.assertIn(name, self.manifest["renders"])
            entry = self.manifest["renders"][name]
            self.assertEqual(entry["size"], [w, h], name)
            if frames == 1:
                self.assertEqual(entry.get("file"), name + ".png")
            else:
                self.assertEqual(len(entry["frames"]), frames, name)
                self.assertEqual(entry["fps"], 12, name)

    def test_every_listed_file_is_an_rgba_png_of_the_stated_size(self):
        count = 0
        for name, entry, files in self.entries():
            for fname in files:
                self.assertNotIn("/", fname)
                self.assertNotIn("\\", fname)
                path = RENDERS / fname
                self.assertTrue(path.is_file(), "%s is listed but missing" % fname)
                info = png.png_info(path.read_bytes())                     # also checks every chunk CRC
                self.assertEqual([info["width"], info["height"]], entry["size"], fname)
                self.assertEqual((info["bit_depth"], info["color_type"], info["interlace"]), (8, 6, 0), fname)
                self.assertTrue(info["has_alpha"], fname)
                count += 1
        self.assertGreaterEqual(count, 62)                                 # 2 stills + 24 + 12 + 24 frames

    def test_folder_holds_exactly_what_the_manifest_lists(self):
        listed = set(f for _n, _e, files in self.entries() for f in files)
        on_disk = set(p.name for p in RENDERS.iterdir() if p.suffix.lower() == ".png")
        self.assertEqual(on_disk, listed)

    def test_backgrounds_are_transparent_and_the_subject_is_not(self):
        """Decode a sample of the files completely (with the independent decoder) and look at the alpha."""
        sample = ["nova_icon.png", "nova_spin_00.png", "nova_spin_12.png", "disc_spin_03.png", "sync_loop_06.png"]
        for fname in sample:
            w, h, px = independent_decode((RENDERS / fname).read_bytes())
            alpha = px[3::4]
            for corner in (0, w - 1, (h - 1) * w, h * w - 1):
                self.assertEqual(alpha[corner], 0, "%s: corner is not transparent" % fname)
            opaque = sum(1 for a in alpha if a == 255) / float(w * h)
            self.assertGreater(opaque, 0.08, fname)
            self.assertLess(opaque, 0.85, fname)
            self.assertGreater(sum(1 for a in alpha if 0 < a < 255), 20, "%s: edges are not anti-aliased" % fname)

    def test_animations_actually_move_and_loop(self):
        for name in ("nova_spin", "disc_spin", "sync_loop"):
            frames = self.manifest["renders"][name]["frames"]
            data = [(RENDERS / f).read_bytes() for f in frames]
            self.assertEqual(len(set(data)), len(data), "%s has duplicate frames" % name)

    def test_app_can_ignore_everything_else_in_the_folder(self):
        extra = sorted(p.name for p in RENDERS.iterdir() if p.suffix.lower() != ".png")
        self.assertEqual(extra, ["manifest.json"])
        text = (RENDERS / "manifest.json").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"[A-Za-z]:\\|/home/|/tmp/", text))    # relative names only


class FriendsModels(unittest.TestCase):
    """Iggy and Duskie: budgets, canon colours, relative size, and that each reads from the front and back."""

    def view(self, module, turn=0.0, size=48):
        cam = render.Camera(target=(0.0, 0.2, 0.0), ortho=6.0)
        scene = render.Scene(cam, flat_lighting()).add(module.build(), mesh.rot_y(turn))
        image = render.render(scene, size, size, ss=1)
        return set(image.pixel(x, y)[:3] for y in range(size) for x in range(size) if image.pixel(x, y)[3] == 255)

    def test_triangle_budget_and_symmetry(self):
        for module in (iggy, duskie):
            bust = module.build()
            self.assertGreaterEqual(len(bust), 300, module.__name__)
            self.assertLessEqual(len(bust), 2000, module.__name__)
            (x0, y0, _z0), (x1, _y1, _z1) = bust.bounds()
            self.assertAlmostEqual(x0, -x1, places=6)
            self.assertAlmostEqual(y0, module.BASE_Y, places=6)
            self.assertAlmostEqual(module.BASE_Y, nova.BASE_Y, places=6)       # one ground line for the set

    def test_iggy_is_the_smallest_and_has_the_widest_ears(self):
        def head_top(module):
            return module.build().bounds()[1][1]
        self.assertLess(head_top(iggy), head_top(duskie))
        self.assertLess(head_top(duskie), head_top(nova))
        def head_width(module):
            (x0, _y0, _z0), (x1, _y1, _z1) = module.parts()[0].bounds()
            return x1 - x0
        self.assertGreater(head_width(iggy), head_width(duskie))            # fennec ears spread wide

    def test_iggy_reads_as_iggy(self):
        front = self.view(iggy, 0.0)
        for needed in (iggy.FUR, iggy.PERI, iggy.IRIS, iggy.FRAME, iggy.TEE, iggy.NOSE):
            self.assertIn(rgb8(needed), front, needed)
        back = self.view(iggy, 180.0)
        self.assertIn(rgb8(iggy.PERI), back)                                # periwinkle ear backs
        self.assertNotIn(rgb8(iggy.IRIS), back)

    def test_duskie_reads_as_duskie(self):
        front = self.view(duskie, 0.0)
        for needed in (duskie.GOLD, duskie.CREAM, duskie.IRIS, duskie.NOSE, duskie.TEE, duskie.BROWN):
            self.assertIn(rgb8(needed), front, needed)
        self.assertNotIn(rgb8(duskie.SADDLE_BLACK), front)                  # the saddle is a back marking
        back = self.view(duskie, 180.0)
        for needed in (duskie.SADDLE_BLACK, duskie.SADDLE_GREY, duskie.BROWN):
            self.assertIn(rgb8(needed), back, needed)
        self.assertNotIn(rgb8(duskie.IRIS), back)

    def test_head_pose_keeps_the_ground_line(self):
        for module in (iggy, duskie):
            posed = module.build(turn=12.0, nod=-3.0, tilt=5.0)
            self.assertEqual(len(posed), len(module.build()))
            self.assertAlmostEqual(min(v[1] for v in posed.verts), module.BASE_Y, places=6)

    def test_turntable_frames_stay_inside_the_picture(self):
        for module in (iggy, duskie):
            for i in (0, 6, 12, 18):
                image = render.render(module.spin_scene(i, 24), 48, 48, ss=1)
                self.assertGreater(image.covered(255), 200)
                edge = [image.pixel(x, 0)[3] for x in range(48)] + [image.pixel(0, y)[3] for y in range(48)]
                edge += [image.pixel(47, y)[3] for y in range(48)]
                self.assertEqual(max(edge), 0, "%s frame %d touches the border" % (module.__name__, i))

    def test_scene_takes_a_list_of_shadows(self):
        cube = mesh.box(1.0, "#ffffff")
        one = render.render(scene_of(cube, shadow=render.Shadow((0, -0.5, 0), 1.5, 0.5)), 32, 32, ss=1)
        two = render.render(scene_of(cube, shadow=[render.Shadow((0, -0.5, 0), 1.5, 0.5)]), 32, 32, ss=1)
        self.assertEqual(one.pixels, two.pixels)


class CommittedRendersWave3(unittest.TestCase):
    """The new manifest entries are valid RGBA PNGs of the stated size, next to the old ones."""

    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((RENDERS / "manifest.json").read_text(encoding="utf-8"))

    def test_new_entries_are_listed_and_the_old_ones_kept(self):
        for name in list(REQUIRED) + list(REQUIRED_WAVE3):
            self.assertIn(name, self.manifest["renders"], name)

    def test_new_files_are_rgba_pngs_of_the_stated_size(self):
        for name, (w, h, frames) in REQUIRED_WAVE3.items():
            entry = self.manifest["renders"][name]
            self.assertEqual(entry["size"], [w, h], name)
            files = [entry["file"]] if frames == 1 else entry["frames"]
            self.assertEqual(len(files), frames, name)
            for fname in files:
                info = png.png_info((RENDERS / fname).read_bytes())
                self.assertEqual((info["width"], info["height"]), (w, h), fname)
                self.assertEqual((info["bit_depth"], info["color_type"]), (8, 6), fname)

    def test_new_stills_have_transparent_corners(self):
        for fname in ("iggy_icon.png", "duskie_icon.png", "trio_busts.png"):
            w, h, px = independent_decode((RENDERS / fname).read_bytes())
            alpha = px[3::4]
            for corner in (0, w - 1, (h - 1) * w, h * w - 1):
                self.assertEqual(alpha[corner], 0, fname)


if __name__ == "__main__":
    unittest.main()
