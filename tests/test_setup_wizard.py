"""The 'Set up your GameCube' wizard, driven step by step in a real window (needs tkinter and a display:
xvfb-run -a python3.12 -m unittest discover -s tests). Config, state and downloads go to a temp folder; SD cards
are temp folders; GitHub is the fake from test_swissget. Nothing goes online."""
import atexit, re, shutil, tempfile, time, unittest
from pathlib import Path
from unittest import mock

HOME = tempfile.mkdtemp(prefix="pawtation-wizard-")
atexit.register(shutil.rmtree, HOME, True)
WIZARD_PY = Path(__file__).resolve().parent.parent / "pawtation" / "setup_wizard.py"

try:
    import tkinter
    _r = tkinter.Tk(); _r.destroy()
    DISPLAY = True
except Exception:
    DISPLAY = False

from pawtation import core, swissget                    # noqa: E402
from test_swissget import FakeGitHub, fake_release      # noqa: E402
from test_gui import fake_iso                           # noqa: E402

_REAL = {}


def setUpModule():
    _REAL["paths"] = (core.CONFIG_PATH, core.STATE_PATH, core.HOME)
    core.CONFIG_PATH, core.STATE_PATH, core.HOME = Path(HOME) / "config.json", Path(HOME) / "state.json", Path(HOME)


def tearDownModule():
    core.CONFIG_PATH, core.STATE_PATH, core.HOME = _REAL["paths"]
    shutil.rmtree(HOME, ignore_errors=True)


class Source(unittest.TestCase):
    def test_no_hex_colour_literals(self):
        hits = re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", WIZARD_PY.read_text(encoding="utf-8"))
        self.assertEqual(hits, [], "setup_wizard.py must take every colour from the App's theme")

    def test_the_guide_ships_where_the_wizard_looks(self):
        from pawtation import paths
        self.assertTrue((paths.BUNDLE / "docs" / "GAMECUBE_GUIDE.md").is_file())


@unittest.skipUnless(DISPLAY, "tkinter or a display is not available")
class Wizard(unittest.TestCase):
    def setUp(self):
        from pawtation import gui
        assert str(core.CONFIG_PATH).startswith(HOME), "refusing to run against the real config"
        for f in (core.CONFIG_PATH, core.STATE_PATH):
            if f.exists():
                f.unlink()
        shutil.rmtree(Path(HOME) / "swiss", ignore_errors=True)
        self.tmp = Path(tempfile.mkdtemp(dir=HOME))
        self.addCleanup(shutil.rmtree, str(self.tmp), ignore_errors=True)
        self.lib = self.tmp / "lib"; self.lib.mkdir()
        fake_iso(self.lib / "a.iso", "G8ME01", "Paper Mario", 2)
        fake_iso(self.lib / "b.iso", "GM4E01", "MKDD", 2)
        self.boot = self.tmp / "boot"; self.boot.mkdir()
        self.msgs = []
        self.app = gui.App()
        self.addCleanup(self.app.destroy)
        a = self.app
        a.ask_yes_no = lambda t, x: (self.msgs.append((t, x)) or True)
        a.show_info = lambda t, x: self.msgs.append((t, x))
        a.show_error = lambda t, x: self.msgs.append(("ERROR " + t, x))
        a.ask_directory = lambda t, i="": str(self.lib)
        a.update()

    def pump(self, cond, timeout=20):
        t0 = time.time()
        while not cond() and time.time() - t0 < timeout:
            self.app.update(); time.sleep(0.01)
        self.app.update()
        self.assertTrue(cond(), "timed out")

    def test_first_run_wants_the_wizard_and_only_one_opens(self):
        self.assertTrue(self.app.wants_setup())
        w = self.app.open_setup()
        self.assertIs(self.app.open_setup(), w)

    def test_walk_through_every_step(self):
        w = self.app.open_setup(); self.app.update()
        # 1. games
        w.pick_library()
        self.assertEqual(core.load_config()["library_dir"], str(self.lib))
        self.assertEqual(len(self.app.roms), 2)
        w.next(); self.assertEqual(w.step, 1)
        # 2. cards
        w.count.set("2"); w._redraw_sizes()
        w.size_vars["1"].set("32"); w.size_vars["2"].set("64 GB")
        w.next(); self.assertEqual(w.step, 2)
        cards = core.load_config()["cards"]
        self.assertEqual(sorted(cards), ["1", "2"])
        self.assertEqual((cards["1"]["capacity_gb"], cards["2"]["capacity_gb"]), (32.0, 64.0))
        # 3. Swiss (the fake GitHub)
        gh = FakeGitHub(fake_release(self.tmp))
        with mock.patch.object(swissget.urllib.request, "urlopen", gh):
            w.download()
            self.pump(lambda: not w.busy() and core.load_config()["boot_card"].get("swiss_dol"))
        self.assertTrue(core.load_config()["boot_card"]["swiss_dol"].endswith("AUTOEXEC.DOL"))
        w.next(); self.assertEqual(w.step, 3)
        # 4. boot card
        w.boot_choice.set(str(self.boot))
        w.write_boot()
        self.assertEqual((self.boot / "autoexec.dol").read_bytes(), b"AR-DOL")
        self.assertEqual(core.load_config()["boot_card"]["mount"], str(self.boot))
        self.assertEqual(w.step, 4)
        # 5. first rotation
        w._plan()
        self.assertTrue(core.current_plan(core.load_state()))
        w.next(); self.assertEqual(w.step, 5)
        # 6. finish
        w.next()
        self.assertTrue(core.load_config()["setup_done"])
        self.assertFalse(self.app.wants_setup())

    def test_build_smoke_report(self):
        import json
        from pawtation import gui
        out = self.tmp / "smoke.json"
        self.assertEqual(gui._smoke_report(self.app, str(out)), 0)
        r = json.loads(out.read_text())
        self.assertTrue(r["ok"]); self.assertTrue(r["guide"]); self.assertGreater(r["catalog"], 600)
        self.app.destroy()                                     # the report closed the window: closing again is safe

    def test_bad_card_sizes_are_refused(self):
        w = self.app.open_setup(); w.go(1)
        w.count.set("1"); w._redraw_sizes(); w.size_vars["1"].set("lots")
        w.next()
        self.assertEqual(w.step, 1)
        self.assertTrue(any(t.startswith("ERROR") for t, _x in self.msgs))

    def test_a_game_card_is_never_used_as_the_boot_card_without_asking(self):
        dol = self.tmp / "AUTOEXEC.DOL"; dol.write_bytes(b"AR")
        self.app.cfg = core.update_config(boot_card={"label": "b", "mount": "", "swiss_dol": str(dol)})
        (self.boot / core.MANIFEST_NAME).write_text('{"card_id": "1"}')
        w = self.app.open_setup(); w.go(3)
        self.app.ask_yes_no = lambda t, x: (self.msgs.append((t, x)) or False)    # say no
        w.boot_choice.set(str(self.boot)); w.write_boot()
        self.assertFalse((self.boot / "autoexec.dol").exists())
        self.assertTrue(any("game card" in t.lower() for t, _x in self.msgs))

    def test_a_failed_download_is_shown_and_the_app_keeps_running(self):
        w = self.app.open_setup(); w.go(2)
        with mock.patch.object(swissget.urllib.request, "urlopen", FakeGitHub(fake_release(self.tmp), api_status=403)):
            w.download()
            self.pump(lambda: not w.busy())
            self.app.update()
        self.assertIn("GitHub", w.swiss_msg.cget("text"))
        self.assertFalse(core.load_config()["boot_card"].get("swiss_dol"))

    def test_closing_mid_download_cancels_it(self):
        w = self.app.open_setup(); w.go(2)
        slow = FakeGitHub(fake_release(self.tmp))
        with mock.patch.object(swissget, "CHUNK", 16), mock.patch.object(swissget.urllib.request, "urlopen", slow):
            w.download(); w.close()
            self.pump(lambda: not w.busy())
        self.assertIsNone(swissget.cached())


if __name__ == "__main__":
    unittest.main()
