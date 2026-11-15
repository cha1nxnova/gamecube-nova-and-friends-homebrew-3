import tempfile, unittest, time
from pathlib import Path
from pawtation import core, pets, saves
from pawtation.core import Catalog


def fake_iso(path: Path, code6: str, title: str, mb: float):
    head = code6.encode() + b"\0" * 26 + title.encode().ljust(0x40, b"\0")
    path.write_bytes(head + b"\0" * (int(mb * 1024 * 1024) - len(head)))


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        lib = self.tmp / "lib"; lib.mkdir()
        fake_iso(lib / "ttyd.iso", "G8ME01", "Paper Mario", 4)
        fake_iso(lib / "Mario Kart Double Dash.iso", "GM4E01", "MKDD", 4)
        fake_iso(lib / "chibi.gcm", "GGTE01", "Chibi", 4)
        fake_iso(lib / "sc2.iso", "GRSEAF", "SC2", 4)
        fake_iso(lib / "mystery.iso", "ZZZE00", "Mystery Game", 3)
        fake_iso(lib / "Pikmin 2 (USA).iso", "XXXXXX", "x", 3)      # matched by name fallback
        self.cfg = core.load_config()
        self.cfg.update(library_dir=str(lib), reserve_mb=1)
        self.cfg["cards"] = {str(i): {"label": f"C{i}", "capacity_gb": 9 / 1024, "mount": ""} for i in range(1, 4)}
        self.cat = Catalog(); self.state = core.load_state()
        self.state["history"] = []; self.state["ratings"] = {}; self.state["last_on_card"] = {}

    def test_scan_matches(self):
        roms = core.scan_library(self.cfg, self.cat)
        keys = {r.key: r for r in roms}
        self.assertIn("paper-mario-ttyd", keys)
        self.assertIn("mario-kart-double-dash", keys)
        self.assertIn("chibi-robo", keys)              # .gcm header match
        self.assertIn("pikmin-2", keys)                # filename match
        self.assertIn("mystery-game", keys); self.assertFalse(keys["mystery-game"].in_catalog)

    def test_plan_pins_and_capacity(self):
        roms = core.scan_library(self.cfg, self.cat)
        plan = core.plan_rotation(self.cfg, self.state, roms)
        by = {r.key: r for r in roms}
        for cid, ks in plan.items():
            self.assertLessEqual(sum(by[k].size for k in ks), core.card_budget(self.cfg, self.cfg["cards"][cid]))
        flat = [k for ks in plan.values() for k in ks]
        self.assertEqual(len(flat), len(set(flat)))    # no duplicates across cards
        self.assertIn("paper-mario-ttyd", plan["1"])   # first pin -> card 1

    def test_sync_only_touches_manifest_files(self):
        roms = core.scan_library(self.cfg, self.cat)
        mount = self.tmp / "sd"; (mount / "games" / "mine").mkdir(parents=True)
        (mount / "games" / "mine" / "keep.iso").write_bytes(b"user file")
        (mount / "swiss.dol").write_bytes(b"x")
        dry = core.sync_card(self.cfg, "1", ["paper-mario-ttyd"], roms, str(mount), dry_run=True, log=lambda *_: None)
        self.assertEqual(len(dry["copied"]), 1); self.assertFalse((mount / ".pawtation.json").exists())
        core.sync_card(self.cfg, "1", ["paper-mario-ttyd"], roms, str(mount), dry_run=False, log=lambda *_: None)
        rep = core.sync_card(self.cfg, "1", ["chibi-robo"], roms, str(mount), dry_run=False, log=lambda *_: None)
        self.assertEqual(len(rep["removed"]), 1)
        self.assertTrue((mount / "games" / "mine" / "keep.iso").exists())
        self.assertTrue((mount / "swiss.dol").exists())

    def test_timer(self):
        due, _ = core.rotation_due(self.cfg, self.state); self.assertTrue(due)
        core.commit_plan(self.state, {"1": []})
        due, rem = core.rotation_due(self.cfg, self.state); self.assertFalse(due); self.assertGreater(rem, 0)

    def test_gci_and_pets(self):
        raw = bytearray(0x40); raw[0:4] = b"G8ME"; raw[8:12] = b"save"
        raw[0x28:0x2C] = (1000).to_bytes(4, "big"); raw[0x38:0x3A] = (3).to_bytes(2, "big")
        p = self.tmp / "a.gci"; p.write_bytes(bytes(raw))
        info = saves.parse_gci(p); self.assertEqual((info["code4"], info["blocks"]), ("G8ME", 3))
        roms = core.scan_library(self.cfg, self.cat)
        brain = pets.PetBrain(self.state, self.cat)
        self.assertRegex(brain.reply("tell me a joke"), r"^(Mochi|Biscuit):")
        self.assertRegex(brain.reply("rate paper mario 5", roms), r"^(Mochi|Biscuit):")
        self.assertEqual(self.state["ratings"].get("paper-mario-ttyd"), 5)
        self.assertTrue(brain.reply("suggest something", roms))
        self.assertTrue(brain.reply("pet", roms))
        self.assertNotIn("katamari-damacy", self.cat.by_key); self.assertIn("animal-crossing", core.DEFAULT_CONFIG["pinned"])

    def test_boot_card(self):
        mount = self.tmp / "boot"; mount.mkdir(); dol = self.tmp / "swiss.dol"; dol.write_bytes(b"DOL")
        r = core.prepare_boot_card(str(mount), str(dol), dry_run=True, log=lambda *_: None)
        self.assertFalse((mount / "autoexec.dol").exists())
        core.prepare_boot_card(str(mount), str(dol), dry_run=False, log=lambda *_: None)
        self.assertEqual((mount / "autoexec.dol").read_bytes(), b"DOL")
        with self.assertRaises(FileNotFoundError):
            core.prepare_boot_card(str(mount), str(self.tmp / "nope.txt"))

if __name__ == "__main__":
    unittest.main()
