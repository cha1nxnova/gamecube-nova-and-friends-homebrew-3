"""Regression tests for the 2026-11-21 review of the card, boot and sync code.
Everything runs in temp dirs; nothing here can touch a real config, state, library or SD card."""
import argparse, contextlib, io, json, os, struct, time, unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock

from pawtation import cli, core, saves
from test_features import Base, disc_bytes, mktmp, quiet

Usage = namedtuple("Usage", "total used free")


class Fixture(Base):
    def setUp(self):
        super().setUp()
        self.cfg["pinned"] = []
        self.add("ttyd.iso", "G8ME01"); self.add("chibi.iso", "GGTE01"); self.add("mkdd.iso", "GM4E01")

    def card_iso(self, folder):
        return self.sd / "games" / folder / "game.iso"


class LibraryOffline(Fixture):
    def test_unplugged_library_never_empties_a_card(self):
        self.assertEqual(self.sync(["chibi-robo", "paper-mario-ttyd"], dry_run=False)["errors"], [])
        rep = core.sync_card(self.cfg, "1", ["chibi-robo", "paper-mario-ttyd"], [], str(self.sd), dry_run=False, log=quiet)
        self.assertEqual(rep["removed"], [])
        self.assertTrue(self.card_iso("Chibi-Robo!").exists())
        m = core.load_manifest(self.sd)
        self.assertEqual(set(m["files"]), {"chibi-robo", "paper-mario-ttyd"})
        self.assertEqual(m["titles"]["chibi-robo"], "Chibi-Robo!")               # titles survive a run without the library

    def test_compressed_replacement_keeps_the_working_iso(self):
        self.sync(["chibi-robo"], dry_run=False)
        (self.lib / "chibi.iso").unlink()
        (self.lib / "chibi.ciso").write_bytes(b"CISO" + b"\0" * 0x8000)
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertTrue(self.card_iso("Chibi-Robo!").exists())
        self.assertEqual(rep["removed"], [])

    def test_a_game_that_rotated_out_is_still_removed(self):
        self.sync(["chibi-robo"], dry_run=False)
        self.sync(["paper-mario-ttyd"], dry_run=False)
        self.assertFalse(self.card_iso("Chibi-Robo!").exists())

    def test_cli_refuses_when_the_library_folder_is_missing(self):
        self.cfg["library_dir"] = str(self.tmp / "unplugged")
        a = argparse.Namespace(mount=str(self.sd), go=True, verify=False, force=False)
        out = io.StringIO()
        with mock.patch.object(core, "current_plan", lambda st: {"1": ["chibi-robo"]}), contextlib.redirect_stdout(out):
            self.assertFalse(cli._sync_one(self.cfg, {}, None, [], "1", a))
        self.assertIn("Library folder not found", out.getvalue())


class InterruptedCopies(Fixture):
    def test_stale_temp_file_does_not_block_the_retry(self):
        size = (self.lib / "chibi.iso").stat().st_size
        dest = self.card_iso("Chibi-Robo!"); dest.parent.mkdir(parents=True)
        (dest.parent / ("game.iso" + core.PART_TAG + "0")).write_bytes(b"x" * size)   # from a pulled card
        (self.sd / core.MANIFEST_NAME).write_text(json.dumps({"card_id": "1", "pending": ["games/Chibi-Robo!/game.iso"]}))
        cap = size + size // 2                                                    # room for one copy, not two

        def usage(_p):
            used = sum(p.stat().st_size for p in self.sd.rglob("*") if p.is_file())
            return Usage(cap, used, cap - used)
        with mock.patch.object(core.shutil, "disk_usage", usage):
            rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertEqual(rep["errors"], [])
        self.assertTrue(dest.exists())
        self.assertEqual(list(self.sd.rglob("*" + core.PART_TAG + "*")), [])

    def test_cancelled_recopy_keeps_ownership_of_the_file_on_the_card(self):
        old = core.COPY_CHUNK; core.COPY_CHUNK = 4 * 1024
        self.addCleanup(setattr, core, "COPY_CHUNK", old)
        dest = self.card_iso("Chibi-Robo!"); dest.parent.mkdir(parents=True)
        dest.write_bytes(b"finished copy, recorded only as pending")
        (self.sd / core.MANIFEST_NAME).write_text(json.dumps({"card_id": "1", "pending": ["games/Chibi-Robo!/game.iso"]}))
        seen = []
        rep = self.sync(["chibi-robo"], dry_run=False, progress=seen.append,
                        cancel=lambda: sum(1 for i in seen if i.get("phase") == "copy") >= 2)
        self.assertTrue(rep["cancelled"])
        self.assertIn("games/Chibi-Robo!/game.iso", core.load_manifest(self.sd)["pending"])
        self.sync([], dry_run=False)                                            # so it can still be cleaned up later
        self.assertFalse(dest.exists())


class ReplacedDump(Fixture):
    def test_a_replaced_dump_of_the_same_size_is_copied_again(self):
        self.sync(["chibi-robo"], dry_run=False)
        src = self.lib / "chibi.iso"
        src.write_bytes(disc_bytes("GGTE01", "T", src.stat().st_size, fill=b"\1"))
        later = time.time() + 60
        os.utime(src, (later, later))
        rep = self.sync(["chibi-robo"], dry_run=False)
        self.assertIn("games/Chibi-Robo!/game.iso", rep["copied"])
        self.assertEqual(self.card_iso("Chibi-Robo!").read_bytes(), src.read_bytes())
        self.assertEqual(self.sync(["chibi-robo"], dry_run=False)["copied"], [])  # and then it is up to date

    def test_old_manifests_without_a_source_record_are_kept_not_recopied(self):
        self.sync(["chibi-robo"], dry_run=False)
        m = json.loads((self.sd / core.MANIFEST_NAME).read_text()); m.pop("src", None)
        (self.sd / core.MANIFEST_NAME).write_text(json.dumps(m))
        self.assertEqual(self.sync(["chibi-robo"], dry_run=False)["copied"], [])
        self.assertIn("games/Chibi-Robo!/game.iso", core.load_manifest(self.sd)["src"])


class Ordering(Fixture):
    def test_pinned_favourites_are_copied_first(self):
        self.cfg["pinned"] = ["mario-kart-double-dash"]
        order = []
        self.sync(["chibi-robo", "mario-kart-double-dash", "paper-mario-ttyd"], dry_run=False,
                  progress=lambda i: i.get("phase") == "copy" and (not order or order[-1] != i["title"]) and order.append(i["title"]))
        self.assertTrue(order[0].startswith("Mario Kart"), order)

    def test_original_is_kept_over_its_patched_copy(self):
        self.add("Chibi-Robo (USA).iso", "GGTE01"); self.add("Chibi-Robo (USA) - patched.iso", "GGTE01")
        (self.lib / "chibi.iso").unlink()
        rom = {r.key: r for r in self.scan()}["chibi-robo"]
        self.assertEqual(Path(rom.path).name, "Chibi-Robo (USA).iso")


class ScanChecks(Fixture):
    def test_headerless_iso_is_listed_but_never_launchable(self):
        (self.lib / "Katamari Damacy (USA).iso").write_bytes(b"\0" * 0x9000)    # a PS2 image: no GameCube header
        rom = {r.key: r for r in self.scan()}["katamari-damacy"]
        self.assertFalse(rom.launchable)
        self.assertIn("not a GameCube disc image", rom.why_not_launchable)

    def test_a_good_dump_wins_over_an_empty_file_of_the_same_game(self):
        (self.lib / "a").mkdir(); (self.lib / "a" / "Pikmin 2 (USA).iso").write_bytes(b"")
        (self.lib / "b").mkdir(); (self.lib / "b" / "Pikmin 2 (USA).iso").write_bytes(disc_bytes("GPVE01", "T", 64 * 1024))
        rom = [r for r in self.scan() if r.key == "pikmin-2"][0]
        self.assertTrue(rom.launchable); self.assertIn(str(Path("b") / "Pikmin 2"), rom.path)

    def test_rvz_is_listed_even_with_an_old_extension_list(self):
        self.cfg["extensions"] = [".iso", ".gcm", ".ciso", ".gcz"]               # what `init` wrote before this fix
        (self.lib / "Mario Party 4 (USA).rvz").write_bytes(b"RVZ\x01" + b"\0" * 0x200)
        roms = {r.key: r for r in self.scan()}
        hit = [r for r in roms.values() if r.path.endswith(".rvz")]
        self.assertEqual(len(hit), 1); self.assertFalse(hit[0].launchable)


class Budget(unittest.TestCase):
    def test_capacity_is_the_decimal_size_printed_on_the_card(self):
        cfg = {"reserve_mb": 0}
        self.assertEqual(core.card_budget(cfg, {"capacity_gb": 32}), int(32 * 1000**3 * core.CARD_LABEL_SHARE))
        self.assertLess(core.card_budget(cfg, {"capacity_gb": 32}), 31_914_983_424)   # a real "32 GB" card
        self.assertEqual(core.card_budget(cfg, {"capacity_gb": 32}, 31_914_983_424), int(31_914_983_424 * 0.995))
        self.assertEqual(core.card_budget(cfg, {"capacity_gb": 8}, 31_914_983_424), 8 * 1000**3)   # a small setting wins
        self.assertEqual(core.card_budget(cfg, {"capacity_gb": float("nan")}), 0)

    def test_note_card_size_reports_changes_only(self):
        st, d = {}, mktmp(self)
        self.assertTrue(core.note_card_size(st, "1", str(d)))
        self.assertFalse(core.note_card_size(st, "1", str(d)))
        self.assertFalse(core.note_card_size(st, "2", str(d / "missing")))


class Scoring(unittest.TestCase):
    def test_a_stale_one_star_game_never_beats_a_fresh_five_star_one(self):
        now = 10**9
        st = {"ratings": {"fav": 5, "meh": 1}, "last_on_card": {"fav": now - 14 * 86400}}
        fav = core.Rom("f.iso", 1, None, None, "fav", "Fav", True)
        meh = core.Rom("m.iso", 1, None, None, "meh", "Meh", True)
        self.assertGreater(core.game_score(fav, st, now), core.game_score(meh, st, now) + 3)   # + max jitter


class Mounts(Fixture):
    def test_a_remembered_drive_letter_never_overrides_the_card_label(self):
        self.sync(["chibi-robo"], card="2", dry_run=False)                       # the card in the reader is card 2
        self.cfg["cards"]["1"]["mount"] = str(self.sd)                           # card 1 was remembered at the same letter
        with mock.patch.object(core, "find_cards", lambda volumes=None: {}):
            self.assertIsNone(core.resolve_mount(self.cfg, "1"))
            self.cfg["cards"]["2"]["mount"] = str(self.sd)
            self.assertEqual(core.resolve_mount(self.cfg, "2"), str(self.sd))
            self.assertEqual(core.labelled_cards(self.cfg), {"2": str(self.sd)})

    def test_sync_all_refuses_force(self):
        a = argparse.Namespace(card="all", mount=None, go=True, verify=False, force=True)
        st = {"history": [{"plan": {"1": []}}]}
        out = io.StringIO()
        with mock.patch.object(cli, "build_ctx", lambda: (self.cfg, st, None, [])), contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_sync(a), 1)
        self.assertIn("--force cannot be combined", out.getvalue())


class BootCard(unittest.TestCase):
    def setUp(self):
        self.tmp = mktmp(self)
        self.card = self.tmp / "boot"; self.card.mkdir()
        self.ar = self.tmp / "AUTOEXEC.DOL"; self.ar.write_bytes(b"AR build")

    def test_game_cards_are_refused_unless_forced(self):
        (self.card / core.MANIFEST_NAME).write_text("{}")
        with self.assertRaises(core.GameCardError):
            core.prepare_boot_card(str(self.card), str(self.ar), dry_run=False, log=quiet)
        self.assertFalse((self.card / "autoexec.dol").exists())
        core.prepare_boot_card(str(self.card), str(self.ar), dry_run=False, log=quiet, force=True)
        self.assertTrue((self.card / "autoexec.dol").exists())

    def test_names_a_file_that_is_not_the_action_replay_build(self):
        other = self.tmp / "swiss_r2119.dol"; other.write_bytes(b"main")
        warns = core.prepare_boot_card(str(self.card), str(other), log=quiet)["warnings"]
        self.assertTrue(any("ActionReplay/AUTOEXEC.DOL" in w for w in warns))
        self.assertFalse(any("ActionReplay/AUTOEXEC.DOL" in w
                             for w in core.prepare_boot_card(str(self.card), str(self.ar), log=quiet)["warnings"]))

    def test_a_retry_never_overwrites_the_backup(self):
        (self.card / "autoexec.dol").write_bytes(b"known good")
        core.prepare_boot_card(str(self.card), str(self.ar), dry_run=False, log=quiet)
        rep = core.prepare_boot_card(str(self.card), str(self.ar), dry_run=False, log=quiet)
        self.assertTrue(rep["unchanged"])
        self.assertEqual((self.card / "autoexec.dol.bak").read_bytes(), b"known good")
        self.assertEqual((self.card / "autoexec.dol").read_bytes(), b"AR build")
        self.assertEqual([p.name for p in self.card.iterdir() if core.PART_TAG in p.name], [])

    def test_cli_prints_warnings_before_writing(self):
        (self.card / core.MANIFEST_NAME).write_text("{}")
        a = argparse.Namespace(mount=str(self.card), swiss_dol=str(self.ar), go=True, force=False)
        out = io.StringIO()
        with mock.patch.object(core, "load_config", lambda: json.loads(json.dumps(core.DEFAULT_CONFIG))), \
                contextlib.redirect_stdout(out):
            self.assertEqual(cli.cmd_boot_card(a), 1)
        self.assertIn("GAME cards", out.getvalue())
        self.assertFalse((self.card / "autoexec.dol").exists())


class ConfigAndSaves(unittest.TestCase):
    def test_a_string_boot_card_setting_falls_back_to_the_default_shape(self):
        home = mktmp(self)
        (home / "config.json").write_text(json.dumps({"boot_card": "E:\\"}))
        with mock.patch.object(core, "CONFIG_PATH", home / "config.json"):
            self.assertIsInstance(core.load_config()["boot_card"], dict)

    def test_save_text_uses_the_region_encoding(self):
        self.assertEqual(saves._text(b"Pok\xe9mon Colosseum\0junk"), "Pokémon Colosseum")
        self.assertEqual(saves._text("ゼルダ".encode("cp932"), japanese=True), "ゼルダ")

    def test_a_us_save_comment_is_read_as_windows_1252(self):
        d = mktmp(self)
        head = bytearray(0x40)
        head[0:6] = b"GC6E01"; head[0x3C:0x40] = struct.pack(">I", 0)
        body = b"Pok\xe9mon Colosseum".ljust(32, b"\0") + b"Donn\xe9es".ljust(32, b"\0")
        (d / "save.gci").write_bytes(bytes(head) + body + b"\0" * 0x2000)
        self.assertEqual(saves.parse_gci(d / "save.gci")["comment"], ["Pokémon Colosseum", "Données"])


if __name__ == "__main__":
    unittest.main()
