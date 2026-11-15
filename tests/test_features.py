"""Tests for the fork features: multi-disc, safe sync, containers, matcher, patching, saves, pets, plugins, CLI.
Everything runs in temp dirs; nothing here can touch a real config, library or SD card."""
import contextlib, io, json, os, random, struct, subprocess, sys, tempfile, unittest, zlib
from pathlib import Path

from pawtation import core, discimage, patching, pets, plugins, saves
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent
MAGIC = struct.pack(">I", discimage.GC_MAGIC)


def disc_bytes(code6: str, title: str, size: int, disc: int = 1, fill: bytes = b"\0") -> bytes:
    head = bytearray(0x60)
    head[:6] = code6.encode(); head[6] = disc - 1; head[0x1C:0x20] = MAGIC
    head[0x20:0x20 + len(title)] = title.encode()
    return bytes(head) + fill * (size - len(head))


def quiet(*_a, **_k):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lib = self.tmp / "lib"; self.lib.mkdir()
        self.sd = self.tmp / "sd"; self.sd.mkdir()
        self.cfg = json.loads(json.dumps(core.DEFAULT_CONFIG))
        self.cfg.update(library_dir=str(self.lib), reserve_mb=0, mods_dir=str(self.tmp / "mods"))
        self.cfg["cards"] = {str(i): {"label": f"C{i}", "capacity_gb": 1, "mount": ""} for i in (1, 2)}
        self.cat = Catalog()
        self.state = {"ratings": {}, "history": [], "last_on_card": {}, "last_rotation_ts": 0,
                      "pets": {p: {"affection": 5, "energy": 5} for p in ("mochi", "biscuit")}, "plays": {}}

    def add(self, name, code6, title="T", kb=64, disc=1):
        (self.lib / name).write_bytes(disc_bytes(code6, title, kb * 1024, disc))

    def scan(self):
        return core.scan_library(self.cfg, self.cat)

    def sync(self, keys, card="1", **kw):
        kw.setdefault("log", quiet)
        return core.sync_card(self.cfg, card, keys, self.scan(), str(self.sd), **kw)


class MultiDisc(Base):
    def test_two_discs_become_one_game_and_both_copy(self):
        self.add("Resident Evil 4 (USA) (Disc 1).iso", "G4BE08", kb=64, disc=1)
        self.add("Resident Evil 4 (USA) (Disc 2).iso", "G4BE08", kb=32, disc=2)
        self.add("Resident Evil 4 (USA) (Disc 1) copy.iso", "G4BE08", kb=64, disc=1)      # duplicate dump is ignored
        roms = self.scan()
        self.assertEqual(len(roms), 1)
        r = roms[0]
        self.assertEqual([d["disc"] for d in r.discs], [1, 2])
        self.assertEqual(r.size, (64 + 32) * 1024)
        rep = self.sync([r.key], dry_run=False)
        self.assertEqual(rep["errors"], [])
        folder = self.sd / "games" / core.safe_name(r.title)
        self.assertEqual(sorted(p.name for p in folder.iterdir()), ["disc1.iso", "disc2.iso"])
        self.assertEqual((folder / "disc2.iso").stat().st_size, 32 * 1024)
        again = self.sync([r.key], dry_run=False)
        self.assertEqual((len(again["kept"]), again["copied"]), (2, []))
        gone = self.sync([], dry_run=False)
        self.assertEqual(len(gone["removed"]), 2)
        self.assertFalse(folder.exists())

    def test_disc_number_from_filename_when_header_unreadable(self):
        (self.lib / "Mystery Thing (Disc 1).iso").write_bytes(b"x" * 100)
        (self.lib / "Mystery Thing (Disc 2).iso").write_bytes(b"y" * 100)
        roms = self.scan()
        self.assertEqual(len(roms), 1)
        self.assertEqual(len(roms[0].discs), 2)


class SafeSync(Base):
    def setUp(self):
        super().setUp()
        self.add("ttyd.iso", "G8ME01"); self.add("chibi.iso", "GGTE01"); self.add("mkdd.iso", "GM4E01", kb=512)

    def test_hostile_manifest_cannot_delete_outside_card(self):
        victim = self.tmp / "victim.txt"; victim.write_text("precious")
        inside = self.sd / "user.iso"; inside.write_text("mine")
        (self.sd / core.MANIFEST_NAME).write_text(json.dumps({"card_id": "1", "files": {
            "a": "../victim.txt", "b": str(victim), "c": "games/../../victim.txt", "d": "C:\\x", "e": 7}}))
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertTrue(victim.exists()); self.assertTrue(inside.exists())
        self.assertGreaterEqual(len(rep["warnings"]), 4)
        self.assertEqual(len(rep["copied"]) - 1, 1 - 1 + 0)        # exactly the game (+ nothing else; quips not passed)

    def test_corrupt_manifest_is_survivable(self):
        (self.sd / core.MANIFEST_NAME).write_text("{not json")
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertEqual(rep["errors"], [])
        (self.sd / core.MANIFEST_NAME).write_text(json.dumps([1, 2]))
        self.assertEqual(self.sync(["paper-mario-ttyd"], dry_run=False)["errors"], [])
        self.assertTrue((self.sd / "games" / "Chibi-Robo!" / "game.iso").exists())   # forgotten by the bad manifest, so left alone

    def test_wrong_card_refused_unless_forced(self):
        self.sync(["chibi-robo"], card="1", dry_run=False)
        rep = self.sync(["paper-mario-ttyd"], card="2", dry_run=False)
        self.assertTrue(rep["errors"]); self.assertEqual(rep["copied"], [])
        self.assertTrue((self.sd / "games" / "Chibi-Robo!" / "game.iso").exists())
        rep = self.sync(["paper-mario-ttyd"], card="2", dry_run=False, force=True)
        self.assertEqual(rep["errors"], [])
        self.assertEqual(core.find_cards([self.sd]), {"2": str(self.sd)})

    def test_never_overwrites_a_file_it_does_not_own(self):
        mine = self.sd / "games" / "Chibi-Robo!"; mine.mkdir(parents=True)
        (mine / "game.iso").write_text("the user's own copy")
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertEqual(len(rep["errors"]), 1)
        self.assertEqual((mine / "game.iso").read_text(), "the user's own copy")
        self.sync([], dry_run=False)
        self.assertTrue((mine / "game.iso").exists())

    def test_cancel_leaves_no_partial_file_and_resumes(self):
        old = core.COPY_CHUNK; core.COPY_CHUNK = 16 * 1024
        self.addCleanup(setattr, core, "COPY_CHUNK", old)
        seen = []
        rep = self.sync(["chibi-robo", "mario-kart-double-dash"], dry_run=False,
                        progress=seen.append, cancel=lambda: sum(1 for i in seen if i["title"].startswith("Mario Kart")) >= 3)
        self.assertTrue(rep["cancelled"])
        self.assertEqual(list(self.sd.rglob("*.part")), [])
        self.assertTrue((self.sd / "games" / "Chibi-Robo!" / "game.iso").exists())
        self.assertFalse((self.sd / "games" / "Mario Kart Double Dash!!" / "game.iso").exists())
        m = core.load_manifest(self.sd)
        self.assertEqual(list(m["files"]), ["chibi-robo"])          # manifest saved after each finished file
        rep = self.sync(["chibi-robo", "mario-kart-double-dash"], dry_run=False)
        self.assertEqual((len(rep["kept"]), len(rep["copied"]), rep["cancelled"]), (1, 1, False))

    def test_progress_reports_bytes_and_verify_passes(self):
        seen = []
        rep = self.sync(["mario-kart-double-dash"], dry_run=False, progress=seen.append, verify=True)
        self.assertEqual(rep["errors"], [])
        copies = [i for i in seen if i["phase"] == "copy"]
        self.assertEqual(copies[-1]["all_done"], copies[-1]["all_total"])
        self.assertEqual(copies[-1]["all_total"], 512 * 1024)
        self.assertIn("verify", {i["phase"] for i in seen}); self.assertEqual(seen[-1]["phase"], "done")
        self.assertEqual(rep["bytes_copied"], 512 * 1024)

    def test_verify_catches_a_bad_card(self):
        real = core.file_crc32
        core.file_crc32 = lambda p, cancel=None: 12345
        self.addCleanup(setattr, core, "file_crc32", real)
        rep = self.sync(["chibi-robo"], dry_run=False, verify=True)
        self.assertEqual(len(rep["errors"]), 1)
        self.assertFalse((self.sd / "games" / "Chibi-Robo!" / "game.iso").exists())
        self.assertNotIn("chibi-robo", core.load_manifest(self.sd)["files"])

    def test_dry_run_changes_nothing(self):
        before = sorted(str(p) for p in self.sd.rglob("*"))
        rep = self.sync(["chibi-robo"], quips=["Mochi: hi"])
        self.assertEqual(len(rep["copied"]), 2)
        self.assertEqual(sorted(str(p) for p in self.sd.rglob("*")), before)

    def test_missing_game_is_a_warning_not_a_crash(self):
        rep = self.sync(["not-in-library", "chibi-robo"], dry_run=False)
        self.assertEqual(len(rep["warnings"]), 1); self.assertEqual(len(rep["copied"]), 1)

    def test_mods_overlay_and_quips_are_tracked_and_cleaned(self):
        m = self.tmp / "mods" / "chibi-robo" / "card" / "swiss" / "cheats"; m.mkdir(parents=True)
        (m / "GGTE01.txt").write_text("my own notes")
        bad = self.tmp / "mods" / "chibi-robo" / "card" / "games"; bad.mkdir()
        (bad / "evil.iso").write_text("x")                                   # mods may not write into the games folder
        (self.sd / "swiss").mkdir(); (self.sd / "swiss" / "swiss.ini").write_text("user settings")
        rep = self.sync(["chibi-robo"], dry_run=False, quips=["Mochi: hi", "Biscuit: caf\u00e9!!"])
        self.assertEqual(rep["errors"], [])
        self.assertEqual((self.sd / "swiss" / "cheats" / "GGTE01.txt").read_text(), "my own notes")
        self.assertEqual((self.sd / "pawtation" / "quips.txt").read_text(), "Mochi: hi\nBiscuit: caf!!\n")
        self.assertFalse((self.sd / "games" / "evil.iso").exists())
        rep = self.sync(["paper-mario-ttyd"], dry_run=False)                 # chibi rotates out, no quips this time
        self.assertFalse((self.sd / "swiss" / "cheats").exists())
        self.assertFalse((self.sd / "pawtation").exists())
        self.assertEqual((self.sd / "swiss" / "swiss.ini").read_text(), "user settings")

    def test_mod_never_replaces_users_own_file(self):
        m = self.tmp / "mods" / "chibi-robo" / "card"; m.mkdir(parents=True)
        (m / "swiss.ini").write_text("from mod")
        (self.sd / "swiss.ini").write_text("user")
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertEqual((self.sd / "swiss.ini").read_text(), "user")
        self.assertTrue(any("not ours" in w for w in rep["warnings"]))

    def test_safe_name(self):
        self.assertEqual(core.safe_name("Mario Kart: Double Dash!!"), "Mario Kart Double Dash!!")
        self.assertEqual(core.safe_name("Super Smash Bros."), "Super Smash Bros")
        self.assertEqual(core.safe_name("CON"), "CON_")
        self.assertEqual(core.safe_name('<>:"/\\|?*'), "game")
        for rel in ("/abs", "a/../b", "..", "a\\b", "C:/x", "", "a//b"):
            self.assertIsNone(core.card_path(self.sd, rel), rel)
        self.assertEqual(core.card_path(self.sd, "games/A/game.iso"), self.sd / "games" / "A" / "game.iso")


class Planner(Base):
    def test_pin_falls_through_when_its_card_is_too_small_and_seed_is_stable(self):
        for i, (code, kb) in enumerate([("G8ME01", 900), ("GAFE01", 900), ("GGTE01", 64), ("GM4E01", 64)]):
            self.add(f"g{i}.iso", code, kb=kb)
        self.cfg["cards"] = {"10": {"label": "big", "capacity_gb": 1 / 1024, "mount": ""},
                             "2": {"label": "small", "capacity_gb": 0.5 / 1024, "mount": ""}}
        self.cfg["seed"] = 7
        roms = self.scan()
        self.assertEqual(core.card_ids(self.cfg), ["2", "10"])              # numeric order, not "10" < "2"
        plan = core.plan_rotation(self.cfg, self.state, roms, now=1000.0)
        self.assertEqual(plan, core.plan_rotation(self.cfg, self.state, list(reversed(roms)), now=1000.0))
        self.assertIn("paper-mario-ttyd", plan["10"])                       # pin 0 wanted card "2" but only fits on "10"
        self.assertEqual([r.key for r in core.unplaced(plan, roms)], ["animal-crossing"])
        by = {r.key: r for r in roms}
        for cid, keys in plan.items():
            self.assertLessEqual(sum(by[k].size for k in keys), core.card_budget(self.cfg, self.cfg["cards"][cid]))

    def test_config_merge_and_corrupt_files(self):
        home = self.tmp / "home"; home.mkdir()
        old = (core.CONFIG_PATH, core.STATE_PATH)
        core.CONFIG_PATH, core.STATE_PATH = home / "config.json", home / "state.json"
        self.addCleanup(lambda: setattr(core, "CONFIG_PATH", old[0]) or setattr(core, "STATE_PATH", old[1]))
        core.CONFIG_PATH.write_text(json.dumps({"boot_card": {"mount": "E:"}, "cards": {"9": {"label": "x", "capacity_gb": 4}}}))
        cfg = core.load_config()
        self.assertEqual(cfg["boot_card"]["label"], core.DEFAULT_CONFIG["boot_card"]["label"])
        self.assertEqual(list(cfg["cards"]), ["9"])
        self.assertEqual(core.update_config(rotation_days=7)["rotation_days"], 7)
        self.assertEqual(json.loads(core.CONFIG_PATH.read_text())["boot_card"], {"mount": "E:"})
        core.STATE_PATH.write_text("garbage")
        self.assertEqual(core.load_state()["ratings"], {})


class Containers(Base):
    HEAD = disc_bytes("GM4E01", "Mario Kart", 0x60, disc=2)

    def test_ciso(self):
        p = self.lib / "a.ciso"
        blockmap = b"\x01" + b"\0" * (0x8000 - 9)
        p.write_bytes(b"CISO" + struct.pack("<I", 0x200000) + blockmap + self.HEAD + b"\0" * 100)
        self.assertEqual(discimage.read_header(p)["code6"], "GM4E01")
        self.assertEqual(discimage.read_header(p)["disc"], 2)

    def test_gcz_compressed_and_raw(self):
        block = self.HEAD + b"\0" * (0x4000 - len(self.HEAD))
        comp = zlib.compress(block)
        for name, payload, flag in (("z.gcz", comp, 0), ("raw.gcz", block, 1 << 63)):
            hdr = struct.pack("<IIQQII", discimage.GCZ_MAGIC, 0, len(payload) * 2, 0x8000, 0x4000, 2)
            ptrs = struct.pack("<QQ", flag | 0, flag | len(payload))
            p = self.lib / name
            p.write_bytes(hdr + ptrs + struct.pack("<II", 0, 0) + payload + payload)
            h = discimage.read_header(p)
            self.assertEqual((h["code6"], h["title"], h["magic_ok"]), ("GM4E01", "Mario Kart", True), name)

    def test_rvz_and_garbage(self):
        p = self.lib / "a.rvz"
        p.write_bytes(b"RVZ\x01" + b"\0" * (discimage.WIA_DISC_HEADER_OFFSET - 4) + self.HEAD)
        self.assertEqual(discimage.read_header(p)["code6"], "GM4E01")
        for name, data in (("e.iso", b""), ("s.gcz", b"\x01\xc0\x0b\xb1"), ("t.ciso", b"CISO"), ("u.rvz", b"nope"), ("v.txt", b"x")):
            q = self.lib / name; q.write_bytes(data)
            self.assertIsNone(discimage.read_header(q), name)
        self.assertEqual(discimage.disc_from_filename("Game (Disc 2).iso"), 2)
        self.assertEqual(discimage.disc_from_filename("Disco Party.iso"), 1)

    def test_compressed_image_is_matched_by_header(self):
        p = self.lib / "unhelpful name.ciso"
        p.write_bytes(b"CISO" + struct.pack("<I", 0x200000) + b"\x01" + b"\0" * (0x8000 - 9) + disc_bytes("GM4E01", "x", 0x60))
        roms = self.scan()
        self.assertEqual([r.key for r in roms], ["mario-kart-double-dash"])
        self.assertFalse(roms[0].launchable)                                 # recognised, but Swiss cannot start it
        self.assertEqual(core.plan_rotation(self.cfg, self.state, roms), {"1": [], "2": []})
        rep = self.sync(["mario-kart-double-dash"], dry_run=False)
        self.assertEqual((rep["copied"], len(rep["errors"])), ([], 1))


class Matcher(unittest.TestCase):
    def test_real_world_filenames(self):
        cat = Catalog()
        cases = {"Legend of Zelda, The - The Wind Waker (USA).iso": "wind-waker",
                 "Resident Evil 4 (USA) (Disc 2).iso": "resident-evil-4",
                 "Viewtiful Joe 2.iso": "viewtiful-joe-2",
                 "Sonic Adventure 2 Battle (USA).iso": "sonic-adventure-2-battle",
                 "Super Monkey Ball Adventure [GMBE].iso": "super-monkey-ball-adventure",
                 "Paper Mario - The Thousand-Year Door (USA).iso": "paper-mario-ttyd",
                 "Pikmin 2 (USA).iso": "pikmin-2", "Pikmin (USA).iso": "pikmin",
                 "Incredibles, The (USA).iso": "the-incredibles"}
        for fn, key in cases.items():
            g = cat.match(None, fn)
            self.assertEqual(g and g["key"], key, fn)
        self.assertIsNone(cat.match(None, "holiday photos 2019.iso"))
        self.assertIsNone(cat.match(None, "Mario Party 44 Fan Edition.iso"))
        self.assertEqual(cat.match("GRSEAF", "whatever.iso")["key"], "soulcalibur-ii")   # disc ID beats file name


def bps_varint(n: int) -> bytes:
    out = bytearray()
    while True:
        x = n & 0x7F; n >>= 7
        if n == 0:
            out.append(0x80 | x); return bytes(out)
        out.append(x); n -= 1


def make_bps(src: bytes, target: bytes, actions: bytes) -> bytes:
    body = b"BPS1" + bps_varint(len(src)) + bps_varint(len(target)) + bps_varint(0) + actions
    body += struct.pack("<II", zlib.crc32(src), zlib.crc32(target))
    return body + struct.pack("<I", zlib.crc32(body))


class Patching(Base):
    def test_bps_all_four_actions(self):
        src = bytes(range(200))
        # SourceRead 10 | TargetRead "HELLO" | SourceCopy 8 bytes from src[100] | TargetCopy 20 (RLE of the last byte)
        act = lambda cmd, n: bps_varint(((n - 1) << 2) | cmd)
        actions = (act(0, 10) + act(1, 5) + b"HELLO" + act(2, 8) + bps_varint(100 << 1)
                   + act(3, 20) + bps_varint(22 << 1))
        target = src[:10] + b"HELLO" + src[100:108] + bytes([src[107]]) * 20
        s, p, o = self.tmp / "s.bin", self.tmp / "p.bps", self.tmp / "o.bin"
        s.write_bytes(src); p.write_bytes(make_bps(src, target, actions))
        rep = patching.apply_patch(s, p, o)
        self.assertEqual(o.read_bytes(), target); self.assertEqual(rep["format"], "bps")
        self.assertEqual(s.read_bytes(), src)                                # original untouched
        with self.assertRaises(patching.PatchError):                         # refuses to overwrite
            patching.apply_patch(s, p, o)

    def test_bps_rejects_wrong_source_and_corrupt_patch(self):
        src = b"A" * 50
        good = make_bps(src, src, bps_varint(((50 - 1) << 2) | 0))
        s, p = self.tmp / "s.bin", self.tmp / "p.bps"
        s.write_bytes(b"B" * 50); p.write_bytes(good)
        with self.assertRaisesRegex(patching.PatchError, "checksum"):
            patching.apply_patch(s, p, self.tmp / "o1.bin")
        s.write_bytes(src); p.write_bytes(good[:-1] + bytes([good[-1] ^ 1]))
        with self.assertRaisesRegex(patching.PatchError, "corrupt"):
            patching.apply_patch(s, p, self.tmp / "o2.bin")
        p.write_bytes(make_bps(src, src, bps_varint(((60 - 1) << 2) | 0)))  # writes past target
        with self.assertRaises(patching.PatchError):
            patching.apply_patch(s, p, self.tmp / "o3.bin")
        self.assertEqual(sorted(x.name for x in self.tmp.glob("o*")), [])   # no leftovers, no .part

    def test_ips(self):
        s, p, o = self.tmp / "s.bin", self.tmp / "p.ips", self.tmp / "o.bin"
        s.write_bytes(b"0123456789")
        p.write_bytes(b"PATCH" + (2).to_bytes(3, "big") + (3).to_bytes(2, "big") + b"abc"
                      + (12).to_bytes(3, "big") + (0).to_bytes(2, "big") + (4).to_bytes(2, "big") + b"Z" + b"EOF")
        patching.apply_patch(s, p, o)
        self.assertEqual(o.read_bytes(), b"01abc56789\0\0ZZZZ")
        p.write_bytes(b"PATCH" + (2).to_bytes(3, "big"))
        with self.assertRaises(patching.PatchError):
            patching.apply_patch(s, p, self.tmp / "o2.bin")
        with self.assertRaises(patching.PatchError):
            patching.apply_patch(s, self.tmp / "x.zip", self.tmp / "o3.bin")


def gci(code4="G8ME", name="save", blocks=1, comment=(b"Paper Mario", b"File 1  12:34"), comment_at=0x20, mod=1000):
    raw = bytearray(0x40 + 0x2000 * blocks)
    raw[0:4] = code4.encode(); raw[4:6] = b"01"; raw[8:8 + len(name)] = name.encode()
    raw[0x28:0x2C] = mod.to_bytes(4, "big"); raw[0x38:0x3A] = blocks.to_bytes(2, "big")
    raw[0x3C:0x40] = comment_at.to_bytes(4, "big")
    if comment_at != 0xFFFFFFFF:
        for i, c in enumerate(comment):
            at = 0x40 + comment_at + 32 * i
            raw[at:at + len(c)] = c
    return bytes(raw)


class Saves(Base):
    def test_comment_and_wrappers_and_newest_wins(self):
        d = self.tmp / "saves"; d.mkdir()
        (d / "old.gci").write_bytes(gci(mod=10)); (d / "new.gcs").write_bytes(b"\0" * 0x110 + gci(mod=99, comment=(b"Paper Mario", b"File 2")))
        (d / "none.gci").write_bytes(gci(code4="GAFE", comment_at=0xFFFFFFFF))
        (d / "junk.gci").write_bytes(b"\xff" * 10); (d / "notes.txt").write_text("hi")
        found = saves.scan_saves(str(d))
        self.assertEqual(sorted(found), ["G8ME", "GAFE"])
        self.assertEqual(found["G8ME"]["comment"], ["Paper Mario", "File 2"])
        self.assertEqual(found["GAFE"]["comment"], [])
        self.assertNotIn("progress", found["G8ME"])                          # no parser shipped -> nothing claimed
        out = pets.PetBrain(self.state, self.cat, random.Random(1)).save_report(found)
        self.assertIn("File 2", out); self.assertIn("Animal Crossing", out)

    def test_progress_parser_hook_is_fault_tolerant(self):
        p = self.tmp / "a.gci"; p.write_bytes(gci())
        self.addCleanup(saves.PROGRESS_PARSERS.clear)
        saves.PROGRESS_PARSERS["G8ME"] = lambda raw: 1 / 0
        self.assertNotIn("progress", saves.parse_gci(p))
        saves.PROGRESS_PARSERS["G8ME"] = lambda raw: "Chapter test"
        self.assertEqual(saves.parse_gci(p)["progress"], "Chapter test")


class Chat(Base):
    def setUp(self):
        super().setUp()
        for n, c in (("a.iso", "G8ME01"), ("b.iso", "GPIE01"), ("c.iso", "GPVE01"), ("d.iso", "GMSE01")):
            self.add(n, c, kb=1)
        self.roms = self.scan()
        self.state["history"] = [{"ts": 1, "season": 1, "plan": {"1": ["pikmin-2"], "2": []}}]
        self.brain = pets.PetBrain(self.state, self.cat, random.Random(3))

    def lines(self, bucket):
        return {f"{pets.CHARS[p]['name']}: {l}" for p in pets.NAMES for l in pets.PETS[bucket][p]}

    def test_small_talk_is_not_hijacked(self):
        self.assertIn(self.brain.reply("hi", self.roms), self.lines("greeting"))
        for text in ("this is super", "display the catalog", "snap", "my treatment plan is due", "they said so"):
            self.assertIn(self.brain.reply(text, self.roms), self.lines("idle"), text)
        before = json.dumps(self.state["pets"])
        self.brain.reply("carpet competition", self.roms)
        self.assertEqual(json.dumps(self.state["pets"]), before)             # no accidental activity

    def test_intents(self):
        self.assertIn("card 1", self.brain.reply("where is pikmin 2?", self.roms))
        self.assertIn("resting", self.brain.reply("where is paper mario", self.roms))
        self.assertIn("several", self.brain.reply("rate mario 5", self.roms)); self.assertEqual(self.state["ratings"], {})
        self.brain.reply("rate pikmin 2 4", self.roms); self.brain.reply("rate pikmin 2", self.roms)
        self.assertEqual(self.state["ratings"], {"pikmin-2": 4})
        self.assertIn("Pikmin 2", self.brain.reply("rank", self.roms))
        self.assertIn("WRAPPED", self.brain.reply("wrapped", self.roms))
        self.assertTrue(self.brain.reply("biscuit play fetch", self.roms).startswith("Biscuit:"))
        self.assertEqual(self.state["pets"]["biscuit"]["energy"], 3)
        self.assertTrue(self.brain.reply("mochi, tell me about super mario sunshine", self.roms).startswith("Mochi:"))
        for text in ("joke", "fortune", "i'm so tired", "help", "what should i play", "saves", ""):
            self.assertTrue(self.brain.reply(text, self.roms, {}), text)
        self.assertEqual(len(self.brain.collection([])), 2)
        self.assertNotIn("...", self.brain.collection([])[0])
        q = self.brain.card_quips(["pikmin-2", "paper-mario-ttyd"])
        self.assertTrue(q and all("\n" not in x for x in q))

    def test_bad_content_cannot_crash(self):
        pets.PETS["idle"]["mochi"].append("stray {brace and {unknown}")
        self.addCleanup(pets.PETS["idle"]["mochi"].pop)
        b = pets.PetBrain({}, self.cat, random.Random(0))                    # bare state dict is fine too
        for _ in range(40):
            self.assertTrue(b.say("mochi", "idle", game="x"))


class Plugins(Base):
    def test_plugin_hooks_and_broken_plugin(self):
        d = self.tmp / "plugins"; d.mkdir()
        (d / "good.py").write_text(
            "def register(api):\n"
            "    api.progress_parser('ZZZZ', lambda raw: 'ok')\n"
            "    api.chat(r'\\bboop\\b', lambda brain, m, ctx: 'Mochi: Boop received.')\n"
            "    api.score(lambda rom, state, now: 1000 if rom.key == 'chibi-robo' else 0)\n"
            "    api.on('synced', lambda **kw: 1/0)\n"
            "    api.command('hello', lambda args: None, help='hi')\n")
        (d / "broken.py").write_text("raise RuntimeError('nope')\n")
        (d / "_skipped.py").write_text("raise SystemExit\n")
        keep = (list(pets.CHAT_HOOKS), list(core.SCORE_HOOKS), dict(saves.PROGRESS_PARSERS), list(plugins.LOADED),
                list(plugins.ERRORS), dict(plugins.EVENTS), dict(plugins.COMMANDS))
        def restore():
            pets.CHAT_HOOKS[:] = keep[0]; core.SCORE_HOOKS[:] = keep[1]
            saves.PROGRESS_PARSERS.clear(); saves.PROGRESS_PARSERS.update(keep[2])
            plugins.LOADED[:] = keep[3]; plugins.ERRORS[:] = keep[4]
            plugins.EVENTS.clear(); plugins.EVENTS.update(keep[5]); plugins.COMMANDS.clear(); plugins.COMMANDS.update(keep[6])
        self.addCleanup(restore)
        with contextlib.redirect_stderr(io.StringIO()):
            plugins.load_plugins(d)
            plugins.fire("synced", card_id="1")                              # raising hook is contained
        self.assertIn("good", plugins.LOADED); self.assertNotIn("broken", plugins.LOADED)
        self.assertTrue(any("broken.py" in e for e in plugins.ERRORS))
        self.assertEqual(pets.PetBrain(self.state, self.cat).reply("boop"), "Mochi: Boop received.")
        self.assertIn("hello", plugins.COMMANDS)
        self.add("a.iso", "GGTE01", kb=600); self.add("b.iso", "GPIE01", kb=600)
        self.cfg["cards"] = {"1": {"label": "c", "capacity_gb": 1 / 1024, "mount": ""}}; self.cfg["pinned"] = []
        self.assertEqual(core.plan_rotation(self.cfg, self.state, self.scan())["1"], ["chibi-robo"])


class CliEndToEnd(Base):
    def run_cli(self, *args, stdin=None):
        env = dict(os.environ, PAWTATION_HOME=str(self.tmp / "home"), PYTHONPATH=str(ROOT))
        r = subprocess.run([sys.executable, "-m", "pawtation", *args], cwd=str(ROOT), env=env, input=stdin,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def test_full_season(self):
        (self.tmp / "home").mkdir()
        self.add("Paper Mario - The Thousand-Year Door (USA).iso", "G8ME01"); self.add("x.gcm", "GGTE01")
        self.add("RE4 d1.iso", "G4BE08", disc=1); self.add("RE4 d2.iso", "G4BE08", disc=2)
        code, out = self.run_cli("init", "--library", str(self.lib)); self.assertEqual(code, 0, out)
        cfgp = self.tmp / "home" / "config.json"
        cfg = json.loads(cfgp.read_text()); cfg["cards"] = {"1": {"label": "One", "capacity_gb": 1, "mount": ""}}
        cfg["reserve_mb"] = 0; cfg["mods_dir"] = str(self.tmp / "mods"); cfgp.write_text(json.dumps(cfg))
        self.assertFalse((ROOT / "config.json").exists() and "One" in (ROOT / "config.json").read_text())
        code, out = self.run_cli("scan"); self.assertIn("[2 discs]", out); self.assertIn("3 games", out)
        code, out = self.run_cli("status"); self.assertIn("due NOW", out)
        code, out = self.run_cli("sync", "1", "--mount", str(self.sd)); self.assertEqual(code, 1); self.assertIn("plan --commit", out)
        code, out = self.run_cli("plan", "--commit"); self.assertIn("(pinned)", out); self.assertIn("committed", out)
        code, out = self.run_cli("sync", "1", "--mount", str(self.sd)); self.assertIn("DRY RUN", out)
        self.assertEqual(list(self.sd.iterdir()), [])
        code, out = self.run_cli("sync", "1", "--mount", str(self.sd), "--go", "--verify"); self.assertEqual(code, 0, out)
        self.assertEqual(len(list(self.sd.rglob("*.iso"))) + len(list(self.sd.rglob("*.gcm"))), 4)
        self.assertTrue((self.sd / "pawtation" / "quips.txt").read_text().strip())
        code, out = self.run_cli("sync", "2", "--mount", str(self.sd)); self.assertEqual(code, 1)
        code, out = self.run_cli("mods", "--new", "chibi"); self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / "mods" / "chibi-robo" / "card").is_dir())
        for cmd in (["cards"], ["mods"], ["wrapped"], ["saves"], ["status"], ["rate", "chibi", "5"], ["doctor"]):
            code, out = self.run_cli(*cmd); self.assertEqual(code, 0, f"{cmd}: {out}"); self.assertNotIn("Traceback", out)
        code, out = self.run_cli("chat", stdin="hello\njoke\nfetch\nwhere is chibi robo\nquit\n")
        self.assertEqual(code, 0, out); self.assertIn("card 1", out)
        code, out = self.run_cli("boot-card", "--mount", str(self.tmp / "nope"), "--swiss-dol", "x.dol"); self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
