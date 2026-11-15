"""GUI tests. Skipped unless tkinter imports AND a display exists (run: xvfb-run -a python3.12 -m unittest discover -s tests)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="pawtation-gui-")
os.environ["PAWTATION_HOME"] = HOME            # before importing pawtation: never touch the real config

try:
    import tkinter
    _r = tkinter.Tk(); _r.destroy()
    DISPLAY = True
except Exception:
    DISPLAY = False

from pawtation import core                      # noqa: E402
if DISPLAY:
    from pawtation import gui                   # noqa: E402


def fake_iso(path: Path, code6: str, title: str, mb: float):
    head = code6.encode() + b"\0" * 26 + title.encode().ljust(0x40, b"\0")
    with open(path, "wb") as f:
        f.write(head)
        f.truncate(int(mb * 1024 * 1024))


@unittest.skipUnless(DISPLAY, "tkinter or a display is not available")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=HOME))
        for f in (core.CONFIG_PATH, core.STATE_PATH):
            if f.exists():
                f.unlink()
        lib = self.tmp / "lib"; lib.mkdir()
        fake_iso(lib / "a.iso", "G8ME01", "Paper Mario", 4)
        fake_iso(lib / "b.iso", "GM4E01", "MKDD", 4)
        fake_iso(lib / "c.iso", "ZZZE00", "Not In Catalog", 3)
        core.update_config(library_dir=str(lib), reserve_mb=1,
                           cards={str(i): {"label": f"C{i}", "capacity_gb": 0.02, "mount": ""} for i in (1, 2, 10)})
        self.card = self.tmp / "sd"; self.card.mkdir()
        self.app = gui.App()
        self.msgs = []
        self.app.ask_yes_no = lambda t, x: (self.msgs.append((t, x)) or True)
        self.app.show_info = lambda t, x: self.msgs.append((t, x))
        self.app.show_error = lambda t, x: self.msgs.append((t, x))
        self.app.choose_card = lambda opts: "1"
        self.app.ask_directory = lambda t, i="": str(self.card)

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def pump(self, cond, timeout=30):
        t0 = time.time()
        while not cond() and time.time() - t0 < timeout:
            self.app.update(); time.sleep(0.01)
        self.app.update()
        self.assertTrue(cond(), "timed out")

    def test_empty_config_launches(self):
        core.CONFIG_PATH.unlink()
        a = gui.App(); a.update(); self.assertEqual(a.roms, []); a.plan(); a.destroy()

    def test_refresh_lists_games(self):
        self.assertEqual(len(self.app.tree.get_children()), 3)
        self.app.search_var.set("paper"); self.app.update()
        self.assertEqual(len(self.app.tree.get_children()), 1)

    def test_rate_including_unknown_game(self):
        self.app.rate(5, key="paper-mario-ttyd")
        self.assertEqual(self.app.state["ratings"]["paper-mario-ttyd"], 5)
        unk = next(r.key for r in self.app.roms if not r.in_catalog)
        self.app.tree.selection_set(unk); self.app.rate(2)
        self.assertEqual(self.app.state["ratings"][unk], 2)

    def test_pin_and_sort(self):
        self.app.toggle_pin("mario-kart-double-dash")
        self.assertIn("mario-kart-double-dash", core.load_config()["pinned"])
        self.app.toggle_pin("mario-kart-double-dash")
        self.assertNotIn("mario-kart-double-dash", core.load_config()["pinned"])
        self.app.sort_by("size"); self.app.sort_by("size")
        self.assertEqual(gui.card_sort_key("2") < gui.card_sort_key("10"), True)

    def _plan_and_sync(self):
        self.app.plan()
        self.assertTrue(core.current_plan(self.app.state))
        self.app.sync_card()

    def test_threaded_sync(self):
        self.app.plan()
        plan = core.current_plan(self.app.state)
        self.app.choose_card = lambda opts: next(c for c in opts if plan[c])
        self.app.sync_card()
        self.assertTrue(self.app.syncing)
        self.pump(lambda: not self.app.syncing)
        self.assertEqual(self.app.last_report["errors"], [])
        files = [p for p in (self.card / "games").rglob("*") if p.is_file()]
        self.assertTrue(files)
        self.assertFalse([p for p in self.card.rglob("*.part")])
        self.assertEqual(str(self.app.buttons["sync"].cget("state")), "normal")

    def test_cancel_leaves_no_part_file(self):
        big = Path(core.load_config()["library_dir"]) / "big.iso"
        fake_iso(big, "GS2E41", "Big", 64)
        core.update_config(cards={"1": {"label": "C1", "capacity_gb": 0.2, "mount": ""}})
        old = core.COPY_CHUNK; core.COPY_CHUNK = 64 * 1024
        try:
            a = self.app; a.refresh()
            a.start_sync("1", [r.key for r in a.roms if r.key.startswith("big") or r.title == "Big"], str(self.card))
            self.pump(lambda: a.sync_info.get("phase") == "copy" and a.sync_info.get("file_done", 0) > 0)
            a.cancel_sync()
            self.pump(lambda: not a.syncing)
        finally:
            core.COPY_CHUNK = old
        self.assertTrue(a.last_report["cancelled"])
        self.assertEqual(list(self.card.rglob("*.part")), [])

    def test_force_flow_for_other_card(self):
        self.app.plan()
        core.save_json(self.card / core.MANIFEST_NAME, {"card_id": "2", "files": {}, "more_files": {}})
        plan = core.current_plan(self.app.state)
        self.app.choose_card = lambda opts: next(c for c in opts if plan[c] and c != "2")
        self.app.sync_card()
        self.assertTrue(any("anyway" in x for _t, x in self.msgs))
        self.pump(lambda: not self.app.syncing)
        self.assertEqual(self.app.last_report["errors"], [])

    def test_worker_error_reported(self):
        orig = core.sync_card
        core.sync_card = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        try:
            self.app.start_sync("1", [], str(self.card))
            self.pump(lambda: not self.app.syncing)
        finally:
            core.sync_card = orig
        self.assertTrue(any("boom" in x for _t, x in self.msgs))

    def test_boot_card(self):
        dol = self.tmp / "swiss.dol"; dol.write_bytes(b"dol")
        boot = self.tmp / "boot"; boot.mkdir()
        self.app.ask_directory = lambda t, i="": str(boot)
        self.app.ask_file = lambda *a, **k: str(dol)
        self.app.boot_card()
        self.assertEqual((boot / "autoexec.dol").read_bytes(), b"dol")

    def test_theme_toggle_saved(self):
        self.app.toggle_theme(); self.app.update()
        self.assertEqual(core.load_config()["gui_theme"], "light")
        self.app.toggle_theme(); self.app.update()
        self.assertEqual(core.load_config()["gui_theme"], "dark")

    def test_nag_once_and_pet_buttons(self):
        n0 = len(self.app.log.get("1.0", "end"))
        self.app._tick(reschedule=False)
        n1 = len(self.app.log.get("1.0", "end"))
        self.app._tick(reschedule=False)
        self.assertEqual(n1, len(self.app.log.get("1.0", "end")))
        self.assertGreater(n1, n0)
        for fn in (self.app.act_joke, self.app.act_suggest, self.app.act_rankings, self.app.act_fortune,
                   self.app.act_study, self.app.act_wrapped):
            fn()
        self.app.do_activity("pet"); self.app.entry.insert(0, "hello"); self.app.chat()

    def test_callback_exception_is_shown(self):
        try:
            raise ValueError("kaboom")
        except ValueError:
            self.app.report_callback_exception(*sys.exc_info())
        self.assertTrue(any("kaboom" in x for _t, x in self.msgs))

    def test_close_during_sync_waits(self):
        big = Path(core.load_config()["library_dir"]) / "big.iso"
        fake_iso(big, "GS2E41", "Big", 64)
        core.update_config(cards={"1": {"label": "C1", "capacity_gb": 0.2, "mount": ""}})
        old = core.COPY_CHUNK; core.COPY_CHUNK = 64 * 1024
        try:
            a = self.app; a.refresh()
            a.start_sync("1", [r.key for r in a.roms if r.title == "Big"], str(self.card))
            self.pump(lambda: a.sync_info.get("file_done", 0) > 0)
            a.on_close()
        finally:
            core.COPY_CHUNK = old
        self.assertEqual(list(self.card.rglob("*.part")), [])


if __name__ == "__main__":
    unittest.main()
