"""Sprite manifest, PNG validity, the runtime loader and the rigs (no Chromium needed)."""
from __future__ import annotations

import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from xml.dom import minidom

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "art"))

from pawtation import sprites  # noqa: E402

SPRITES = ROOT / "assets" / "sprites"
MAINS = ("nova", "iggy", "duskie")
REQUIRED = {"idle": (4, 8), "blink": (2, 3), "talk": (2, 4), "happy": (4, 6), "sleep": (2, 4),
            "wave": (4, 6), "look_left": (1, 1), "look_right": (1, 1), "special": (4, 8)}
SIG = b"\x89PNG\r\n\x1a\n"


def png_info(path: Path):
    """(width, height, colour_type, has_trns) from the signature and IHDR / tRNS chunks."""
    data = path.read_bytes()
    assert data[:8] == SIG, "%s: bad PNG signature" % path
    length, kind = struct.unpack(">I4s", data[8:16])
    assert kind == b"IHDR" and length == 13, "%s: no IHDR" % path
    w, h, depth, ctype = struct.unpack(">IIBB", data[16:26])
    return w, h, ctype, (b"tRNS" in data[:2048])


def write_png(path: Path, size=4):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(SIG + struct.pack(">I4s", 13, b"IHDR") + struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))


class ManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = json.loads((SPRITES / "manifest.json").read_text(encoding="utf-8"))

    def test_schema(self):
        self.assertEqual(self.m["version"], 1)
        self.assertEqual(self.m["sizes"], [96, 192])
        for cid, c in self.m["characters"].items():
            self.assertTrue(c["anims"], cid)
            for name, a in c["anims"].items():
                self.assertIsInstance(a["fps"], int)
                self.assertIsInstance(a["loop"], bool)
                self.assertTrue(a["frames"])
                for f in a["frames"]:
                    self.assertIn("{size}", f)

    def test_every_frame_is_a_square_png_with_alpha(self):
        for cid, c in self.m["characters"].items():
            for name, a in c["anims"].items():
                for rel in a["frames"]:
                    for size in self.m["sizes"]:
                        p = SPRITES / rel.replace("{size}", str(size))
                        self.assertTrue(p.is_file(), p)
                        w, h, ctype, trns = png_info(p)
                        self.assertEqual((w, h), (size, size), p)
                        self.assertTrue(ctype in (6, 4) or (ctype == 3 and trns), "%s has no alpha" % p)
            portrait = c.get("portrait")
            if portrait:
                self.assertEqual(png_info(SPRITES / portrait)[:2], (512, 512))

    def test_required_animations(self):
        for cid in MAINS:
            self.assertIn(cid, self.m["characters"], cid)
            anims = self.m["characters"][cid]["anims"]
            for name, (lo, hi) in REQUIRED.items():
                self.assertIn(name, anims, "%s/%s" % (cid, name))
                self.assertTrue(lo <= len(anims[name]["frames"]) <= hi, "%s/%s" % (cid, name))

    def test_cameos_present_have_idle_and_talk(self):
        cast = json.loads((ROOT / "data" / "cast.json").read_text(encoding="utf-8"))["characters"]
        for cid, v in cast.items():
            if v.get("role") == "cameo" and cid in self.m["characters"]:
                anims = self.m["characters"][cid]["anims"]
                self.assertIn("idle", anims, cid)
                self.assertIn("talk", anims, cid)


class LoaderTests(unittest.TestCase):
    def test_real_assets(self):
        self.assertEqual(sprites.available_sizes(), [96, 192])
        for cid in MAINS:
            self.assertTrue(sprites.has(cid))
            self.assertIn(cid, sprites.characters())
            fr = sprites.frames(cid, "idle", 96)
            info = sprites.anim_info(cid, "idle")
            self.assertEqual(len(fr), info["count"])
            self.assertTrue(info["loop"])
        self.assertNotIn("props", sprites.characters())
        self.assertEqual(len(sprites.frames("props", "heart", 192)), 1)
        self.assertIsNone(sprites.anim_info("nova", "nope"))
        self.assertEqual(sprites.frames("nobody", "idle", 96), [])
        self.assertFalse(sprites.has("nobody"))

    def test_renders(self):
        p = sprites.render("nova_bust")
        self.assertTrue(p is None or p.is_file())
        fr, fps = sprites.render_frames("nova_spin")
        self.assertEqual(bool(fr), fps > 0)
        self.assertIsNone(sprites.render("nope"))
        self.assertEqual(sprites.render_frames("nope"), ([], 0))

    def _tmp(self):
        td = tempfile.TemporaryDirectory()
        self.addCleanup(td.cleanup)
        return Path(td.name)

    def test_tolerates_bad_manifests(self):
        root = self._tmp()
        self.assertEqual(sprites.load_manifest(root), {})
        self.assertEqual(sprites.frames("nova", "idle", 96, root=root), [])
        (root / "sprites").mkdir()
        for text in ("", "{not json", "[]", "null", '{"characters": []}', '{"characters": {"a": 5}}',
                     '{"characters": {"a": {"anims": {"idle": {"frames": "x"}}}}, "sizes": "x"}',
                     '{"characters": {"a": {"anims": {"idle": {"frames": [1, null]}}}}}'):
            (root / "sprites" / "manifest.json").write_text(text, encoding="utf-8")
            self.assertEqual(sprites.frames("a", "idle", 96, root=root), [], text)
            self.assertIsNone(sprites.anim_info("a", "idle", root), text)
            self.assertIsInstance(sprites.characters(root), list)
            self.assertIsInstance(sprites.available_sizes(root), list)
        (root / "renders").mkdir()
        (root / "renders" / "manifest.json").write_text('{"renders": {"x": 3, "y": {"frames": [1]}}}')
        self.assertIsNone(sprites.render("x", root))
        self.assertEqual(sprites.render_frames("y", root), ([], 0))

    def test_missing_files_skipped_and_asset_patch(self):
        root = self._tmp()
        (root / "sprites").mkdir()
        man = {"version": 1, "sizes": [96], "characters": {"a": {"anims": {
            "idle": {"fps": 4, "loop": True, "frames": ["a/{size}/idle_00.png", "a/{size}/idle_01.png"]}}}}}
        (root / "sprites" / "manifest.json").write_text(json.dumps(man))
        write_png(root / "sprites" / "a" / "96" / "idle_01.png")
        old = sprites.ASSETS
        sprites.ASSETS = root
        try:
            self.assertEqual([p.name for p in sprites.frames("a", "idle", 96)], ["idle_01.png"])
            self.assertEqual(sprites.anim_info("a", "idle"), {"fps": 4, "loop": True, "count": 2})
        finally:
            sprites.ASSETS = old

    def test_pack_override_order(self):
        root = self._tmp()
        (root / "sprites").mkdir()
        man = {"sizes": [96], "characters": {"a": {"anims": {"idle": {"fps": 4, "loop": True, "frames": [
            "a/{size}/idle_00.png", "a/{size}/idle_01.png"]}}}}}
        (root / "sprites" / "manifest.json").write_text(json.dumps(man))
        for i in (0, 1):
            write_png(root / "sprites" / "a" / "96" / ("idle_%02d.png" % i))
        p1, p2 = root / "p1", root / "p2"
        write_png(p1 / "sprites" / "a" / "96" / "idle_00.png")
        write_png(p2 / "sprites" / "a" / "96" / "idle_00.png")
        write_png(p2 / "sprites" / "a" / "96" / "idle_01.png")
        got = sprites.frames("a", "idle", 96, pack_dirs=[p1, p2], root=root)
        self.assertEqual(got, [p1 / "sprites/a/96/idle_00.png", p2 / "sprites/a/96/idle_01.png"])
        got = sprites.frames("a", "idle", 96, pack_dirs=[p2, p1], root=root)
        self.assertEqual(got[0], p2 / "sprites/a/96/idle_00.png")
        self.assertEqual(sprites.frames("a", "idle", 96, pack_dirs=[root / "none"], root=root)[0].parent,
                         root / "sprites/a/96")

    def test_no_tkinter_import(self):
        self.assertNotIn("tkinter", Path(sprites.__file__).read_text(encoding="utf-8").replace(
            "never imports tkinter", ""))


class RigTests(unittest.TestCase):
    def test_rigs_import_and_draw_well_formed_xml(self):
        import build  # art/build.py: imports no rasteriser at import time
        from lib2d import validate_rig
        paths = build.rig_paths()
        self.assertGreaterEqual(len(paths), 4)
        cameos = build.cameo_ids()
        for path in paths:
            mod = build.load_rig(path)
            self.assertEqual(mod.CHAR_ID, path.stem)
            self.assertEqual(validate_rig(mod, cameo=bool(getattr(mod, "CAMEO", path.stem in cameos))), [],
                             path.name)
            for name, a in mod.ANIMS.items():
                try:
                    minidom.parseString(mod.draw(a["frames"][0]))
                except Exception as exc:
                    self.fail("%s/%s first frame is not well-formed XML: %s" % (path.stem, name, exc))


if __name__ == "__main__":
    unittest.main()
