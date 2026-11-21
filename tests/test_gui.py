"""GUI tests. Skipped unless tkinter imports AND a display exists (run: xvfb-run -a python3.12 -m unittest discover -s tests).

Safety: config/state are pointed at a temp dir for this module (setUpModule) and every test asserts it before
building a window. SD cards are temp dirs; disc images are sparse fakes with the GameCube magic word."""
import atexit
import datetime
import json
import os
import re
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOME = tempfile.mkdtemp(prefix="pawtation-gui-")
atexit.register(shutil.rmtree, HOME, True)    # also when the module is imported but its tests never run
GUI_PY = Path(__file__).resolve().parent.parent / "pawtation" / "gui.py"
SENTINEL = "ZZGUIAFTERDARKZZ"

try:
    import tkinter
    _r = tkinter.Tk(); _r.destroy()
    DISPLAY = True
except Exception:
    DISPLAY = False

from pawtation import afterdark, cast, core, sprites   # noqa: E402
if DISPLAY:
    from pawtation import gui                   # noqa: E402


_REAL = {}


def setUpModule():
    """Point config/state at a temp dir for this module only. (An env var is not enough: under `unittest discover`
    another test module has usually imported pawtation.core already, with the real paths baked in.)"""
    _REAL["paths"] = (core.CONFIG_PATH, core.STATE_PATH)
    core.CONFIG_PATH, core.STATE_PATH = Path(HOME) / "config.json", Path(HOME) / "state.json"
    for key in ("PAWTATION_REDUCE_MOTION", "PAWTATION_PLAIN_WIDGETS"):
        _REAL[key] = os.environ.pop(key, None)


def tearDownModule():
    core.CONFIG_PATH, core.STATE_PATH = _REAL["paths"]
    shutil.rmtree(HOME, ignore_errors=True)      # the temp home made at import time
    for key in ("PAWTATION_REDUCE_MOTION", "PAWTATION_PLAIN_WIDGETS"):
        if _REAL.get(key) is not None:
            os.environ[key] = _REAL[key]


class SlowQueue(__import__("queue").Queue):
    """The worker's event queue, slowed down so a test can catch a sync half-way (sparse fakes copy very fast)."""

    def put(self, item, *a, **k):
        super().put(item, *a, **k)
        if item and item[0] == "progress":
            time.sleep(0.002)


def fake_iso(path: Path, code6: str, title: str, mb: float):
    head = code6.encode() + b"\0" * 22 + bytes.fromhex("c2339f3d") + title.encode().ljust(0x40, b"\0")
    with open(path, "wb") as f:
        f.write(head)
        f.truncate(int(mb * 1024 * 1024))


class SourceTests(unittest.TestCase):
    """Runs everywhere (no display needed)."""

    def test_no_hex_colour_literals_in_gui(self):
        text = GUI_PY.read_text(encoding="utf-8")
        hits = re.findall(r"#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b", text)
        self.assertEqual(hits, [], "gui.py must take every colour from pawtation.theme")

    def test_import_never_crashes_and_run_is_friendly(self):
        import importlib
        mod = importlib.import_module("pawtation.gui")
        self.assertTrue(callable(mod.run))
        self.assertEqual(mod.split_line("(they nod)")[0], None)


@unittest.skipUnless(DISPLAY, "tkinter or a display is not available")
class GuiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(dir=HOME))
        self.addCleanup(shutil.rmtree, str(self.tmp), ignore_errors=True)
        assert str(core.CONFIG_PATH).startswith(HOME), "refusing to run GUI tests against the real config"
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
        self.app = self.make()

    def make(self):
        assert str(core.CONFIG_PATH).startswith(HOME)
        a = gui.App()
        self.msgs = getattr(self, "msgs", [])
        a.ask_yes_no = lambda t, x: (self.msgs.append((t, x)) or True)
        a.show_info = lambda t, x: self.msgs.append((t, x))
        a.show_error = lambda t, x: self.msgs.append((t, x))
        a.choose_card = lambda opts: "1"
        a.ask_directory = lambda t, i="": str(self.card)
        a.ask_birthdate = lambda check: self.fail("ask_birthdate was not expected")
        a.update()
        return a

    def tearDown(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def pump(self, cond, timeout=30, app=None):
        app = app or self.app
        t0 = time.time()
        while not cond() and time.time() - t0 < timeout:
            app.update(); time.sleep(0.01)
        app.update()
        self.assertTrue(cond(), "timed out")

    def log(self, app=None):
        return (app or self.app).log.get("1.0", "end")

    # ---------------- version-1 behaviour ----------------
    def test_empty_config_launches(self):
        core.update_config(library_dir="")
        a = gui.App(); a.show_info = lambda t, x: self.msgs.append((t, x)); a.update()
        self.assertEqual(a.roms, []); a.plan()
        self.assertTrue(a.empty.winfo_ismapped())                 # the empty-library state is showing
        a.destroy()
        self.assertTrue(any("No games" in x for _t, x in self.msgs))

    def test_refresh_lists_games(self):
        self.assertEqual(len(self.app.tree.get_children()), 3)
        self.app.search_var.set("paper"); self.app.update()
        self.assertEqual(len(self.app.tree.get_children()), 1)
        self.app.search_var.set("zzzz nothing"); self.app.update()
        self.assertTrue(self.app.empty.winfo_ismapped())
        self.app.search_var.set(""); self.app.update()
        self.assertFalse(self.app.empty.winfo_ismapped())

    def test_rate_including_unknown_game(self):
        self.app.rate(5, key="paper-mario-ttyd")
        self.assertEqual(self.app.state["ratings"]["paper-mario-ttyd"], 5)
        self.assertIn("★★★★★", self.app.tree.item("paper-mario-ttyd", "values")[5])
        unk = next(r.key for r in self.app.roms if not r.in_catalog)
        self.app.tree.selection_set(unk); self.app.rate(2)
        self.assertEqual(self.app.state["ratings"][unk], 2)

    def test_pin_and_sort(self):
        k = "mario-kart-double-dash"
        before = k in core.load_config()["pinned"]
        self.app.toggle_pin(k)
        self.assertEqual(k in core.load_config()["pinned"], not before)
        self.assertEqual("pinned" in self.app.tree.item(k, "tags"), not before)
        self.assertEqual(self.app.tree.item(k, "values")[0] == "♥", not before)
        self.app.toggle_pin(k)
        self.assertEqual(k in core.load_config()["pinned"], before)
        self.app.sort_by("size"); self.app.sort_by("size")
        self.assertIn("▼", self.app.tree.heading("size", "text"))
        self.assertEqual(gui.card_sort_key("2") < gui.card_sort_key("10"), True)

    def test_threaded_sync(self):
        self.app.plan()
        plan = core.current_plan(self.app.state)
        self.app.choose_card = lambda opts: next(c for c in opts if plan[c])
        self.app.sync_card()
        self.assertTrue(self.app.syncing)
        self.assertEqual(str(self.app.buttons["sync"].cget("state")), "disabled")
        self.pump(lambda: not self.app.syncing)
        self.assertEqual(self.app.last_report["errors"], [])
        files = [p for p in (self.card / "games").rglob("*") if p.is_file()]
        self.assertTrue(files)
        self.assertFalse([p for p in self.card.rglob("*.part")])
        self.assertEqual(str(self.app.buttons["sync"].cget("state")), "normal")
        self.assertIn("synced", self.app.prog_text.get())

    def test_cancel_leaves_no_part_file(self):
        big = Path(core.load_config()["library_dir"]) / "big.iso"
        fake_iso(big, "GS2E41", "Big", 64)
        core.update_config(cards={"1": {"label": "C1", "capacity_gb": 0.2, "mount": ""}})
        old = core.COPY_CHUNK; core.COPY_CHUNK = 64 * 1024
        try:
            a = self.app; a.refresh(); a.events = SlowQueue()
            a.start_sync("1", [r.key for r in a.roms if r.path.endswith("big.iso")], str(self.card))
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
        first = self.app.theme_name
        self.app.toggle_theme(); self.app.update()
        second = core.load_config()["gui_theme"]
        self.assertNotEqual(second, first)
        self.assertEqual(self.app.c["bg"], gui.theme.load(second)["bg"])
        self.assertEqual(str(self.app.cget("bg")), gui.theme.load(second)["bg"])
        self.app.focus_force(); self.app.update()                   # key events go to the focused window
        if self.app.focus_get() is None:
            self.skipTest("this desktop session does not give the test window keyboard focus (F2 part not run)")
        self.app.event_generate("<F2>"); self.app.update()
        self.assertEqual(core.load_config()["gui_theme"], first)

    def test_nag_once_and_pet_buttons(self):
        self.assertTrue(self.app._nagged)          # fresh state is "due": nagged once during construction
        self.assertTrue(self.app.banner.winfo_ismapped())
        n1 = len(self.log())
        self.app._tick(reschedule=False); self.app._tick(reschedule=False)
        self.assertEqual(n1, len(self.log()))
        self.assertTrue(self.app.title().startswith(gui.PAW))
        for fn in (self.app.act_joke, self.app.act_suggest, self.app.act_rankings, self.app.act_fortune,
                   self.app.act_study, self.app.act_wrapped):
            fn()
        self.app.do_activity("pet"); self.app.entry.insert(0, "hello"); self.app.chat()
        self.assertGreater(len(self.log()), n1)
        self.assertIn("You: hello", self.log())

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
            a = self.app; a.refresh(); a.events = SlowQueue()
            a.start_sync("1", [r.key for r in a.roms if r.path.endswith("big.iso")], str(self.card))
            self.pump(lambda: a.sync_info.get("file_done", 0) > 0)
            a.on_close()
        finally:
            core.COPY_CHUNK = old
        self.assertEqual(list(self.card.rglob("*.part")), [])

    # ---------------- the stage and who is home ----------------
    def image_items(self, cid, app=None):
        cv = (app or self.app).stage.cv
        return [i for i in cv.find_withtag("actor:" + cid) if cv.type(i) == "image"]

    def test_stage_one_sprite_per_present_character_and_gather(self):
        a = self.app
        home = a.brain.home()
        self.assertEqual(a.stage.present(), home)
        for cid in home:
            if sprites.frames(cid, "idle", a.stage.size):
                self.assertEqual(len(self.image_items(cid)), 1, cid)
        a.everyone(); a.update()
        self.assertEqual(set(a.stage.present()), set(cast.regulars()))
        self.assertEqual(set(a.brain.home()), set(cast.regulars()))
        for cid in cast.regulars():
            self.assertEqual(a.stage.actors[cid]["kind"], "sprite" if sprites.has(cid) else "text")

    def needs_screen(self, w, h):
        if self.app.winfo_screenwidth() < w or self.app.winfo_screenheight() < h:
            self.skipTest(f"needs a screen of at least {w}x{h} (this one is "
                          f"{self.app.winfo_screenwidth()}x{self.app.winfo_screenheight()})")

    def test_stage_sprite_size_rule(self):
        """Up to three regulars get the large stickers on a wide, tall stage (a walk-on stays small beside them);
        the compact size only when they do not fit. Name tags never overlap."""
        self.needs_screen(1400, 900)
        a = self.app
        a.geometry("1400x900+0+0")
        a.everyone()
        for _ in range(20):
            a.update(); time.sleep(0.01)
        st, sp = a.stage, a.tok["sprite"]
        regs = st.present()
        w, h = st.dims()
        self.assertGreaterEqual(h, a.size("stage"))
        self.assertEqual(st.size, sp["stage"], (w, h))
        cam = cast.cameos()[0]
        st.set_cast(regs + [cam]); a.update()
        self.assertEqual(st.size, sp["stage"])
        self.assertEqual(st.actor_px(cam), sp["cameo"])
        xs = st.targets()
        order = sorted(xs, key=xs.get)
        for left, right in zip(order, order[1:]):
            gap = xs[right] - xs[left] - (st.tag_width(left) + st.tag_width(right)) / 2.0
            self.assertGreater(gap, 0, (left, right))
        inner = w - a.tok["elevation"]["card"][0] - 6
        self.assertLessEqual(xs[order[-1]] + st.tag_width(order[-1]) / 2.0, inner)
        self.assertGreaterEqual(xs[order[0]] - st.tag_width(order[0]) / 2.0, 0)
        # a stage too narrow for three large stickers falls back to the compact size
        self.assertFalse(st.plan(sp["stage"], 360, regs, [])[1])
        self.assertTrue(st.plan(sp["stage"], 560, regs, [])[1])

    def test_game_list_fits_the_smallest_window(self):
        """At the minimum window size (and so on any laptop screen) no column is cut off at the right edge: the
        least important columns are hidden instead, and Game stays readable."""
        a = self.app
        w, h = a.tok["layout"]["window_min"]
        a.geometry(f"{w}x{h}+0+0")
        for _ in range(20):
            a.update(); time.sleep(0.01)
        a._place_sash(); a.update(); a._fit_columns(); a.update()
        shown = [str(c) for c in a.tree["displaycolumns"]]
        self.assertLessEqual(sum(int(a.tree.column(c, "width")) for c in shown), a.tree.winfo_width())
        self.assertIn("game", shown); self.assertIn("rating", shown)
        self.assertGreaterEqual(int(a.tree.column("game", "width")), a.GAME_MIN)
        self.assertEqual(shown, [c[0] for c in a.COLUMNS if c[0] in shown])          # order kept

    def test_game_column_takes_spare_width(self):
        self.needs_screen(1400, 900)
        a = self.app
        a.geometry("1400x900+0+0")
        for _ in range(10):
            a.update(); time.sleep(0.01)
        a._fit_columns()
        self.assertGreaterEqual(int(a.tree.column("game", "width")), dict((c[0], c[2]) for c in a.COLUMNS)["game"])
        self.assertEqual([str(c) for c in a.tree["displaycolumns"]], [c[0] for c in a.COLUMNS])   # all shown when wide
        total = sum(int(a.tree.column(c[0], "width")) for c in a.COLUMNS)
        self.assertLessEqual(total, a.tree.winfo_width())

    def test_chips_invite_and_send_out(self):
        a = self.app
        cast.gather(a.state, [cast.mains()[0]]); a._after_brain(); a.update()
        guest = next(p for p in cast.regulars() if p not in a.brain.home())
        a.toggle_presence(guest); a.update()
        self.assertIn(guest, a.brain.home())
        self.assertIn(guest, a.stage.present())
        self.assertEqual(a.chips[guest]["button"].cget("text"), "Send out")
        a.toggle_presence(guest); a.update()
        self.assertNotIn(guest, a.brain.home())
        self.assertNotIn(guest, a.stage.present())
        self.assertEqual(a.chips[guest]["button"].cget("text"), "Invite")
        only = a.brain.home()                                     # the last main cannot leave: the engine says so
        self.assertEqual(len(only), 1)
        n = len(self.log())
        a.toggle_presence(only[0]); a.update()
        self.assertEqual(a.brain.home(), only)
        self.assertGreater(len(self.log()), n)

    def test_surprise_me_keeps_a_main_home(self):
        for _ in range(5):
            self.app.surprise()
            self.assertTrue(any(cast.role(p) == "main" for p in self.app.brain.home()))
            self.assertEqual(set(self.app.stage.present()), set(self.app.brain.home()))

    def test_hang_out_plays_lines_one_at_a_time(self):
        a = self.app
        a.everyone(); a.update()
        before = len(self.log())
        a.hang_out(); a.update()
        if a._scene_queue:
            self.assertIn("scene", a._after)                          # the next line is on a ~2.2 s timer
        steps = 0
        while a._scene_queue and steps < 10:
            a.advance(); steps += 1
        self.assertGreater(len(self.log()), before)
        self.assertFalse(a._scene_queue)

    def test_bubble_shows_name_and_pronouns(self):
        a = self.app
        cid = a.brain.home()[0]
        a.stage.queue = []
        a.stage.hide_bubble()
        a.say(f"{cast.name(cid)}: Testing one two.")
        texts = [a.stage.cv.itemcget(i, "text") for i in a.stage.cv.find_withtag("bubble")
                 if a.stage.cv.type(i) == "text"]
        self.assertIn(cast.name(cid), texts)
        self.assertIn(cast.character(cid)["pronouns"], texts)
        self.assertIn("Testing one two.", texts)
        self.assertEqual(a.stage.speaker, cid)

    def test_click_character_pets_them(self):
        a = self.app
        cid = a.brain.speakers()[0]
        before = a.state["pets"][cid]["affection"]
        a.pet_character(cid)
        self.assertGreaterEqual(a.state["pets"][cid]["affection"], before)
        self.assertIn(cast.name(cid) + ":", self.log())

    def test_ascii_fallback_without_assets(self):
        empty = self.tmp / "no-assets"; empty.mkdir()
        old = sprites.ASSETS
        sprites.ASSETS = empty
        try:
            a = self.make()
            a.everyone(); a.update()
            for cid in a.stage.present():
                self.assertEqual(a.stage.actors[cid]["kind"], "text", cid)
                self.assertEqual(self.image_items(cid, a), [])
                self.assertTrue(a.stage.cv.find_withtag("actor:" + cid))
            a.hang_out(); a.do_activity("pet"); a.update()
            a.destroy()
        finally:
            sprites.ASSETS = old

    def test_plain_widget_fallback_works(self):
        os.environ["PAWTATION_PLAIN_WIDGETS"] = "1"
        try:
            a = self.make()
            self.assertIsInstance(a.buttons["plan"], gui.ttk.Button)
            a.plan()
            self.assertTrue(core.current_plan(a.state))
            a.toggle_theme(); a.update()
            a.destroy()
        finally:
            del os.environ["PAWTATION_PLAIN_WIDGETS"]

    # ---------------- After Dark ----------------
    def test_afterdark_gate(self):
        a = self.app
        today = datetime.date.today()
        young = today.replace(year=today.year - 12).isoformat()
        adult = "1990-03-04"
        seen = []

        def gate(text):
            def ask(check):
                ok, msg = check(text)
                seen.append(msg)
                return ok
            return ask
        a.ask_birthdate = gate(young)
        a.open_afterdark()
        self.assertFalse(afterdark.is_unlocked(a.state))
        self.assertTrue(seen and young not in seen[-1])
        a.ask_birthdate = gate("not a date")
        a.open_afterdark()
        self.assertFalse(afterdark.is_unlocked(a.state))
        a.ask_birthdate = gate(adult)
        a.open_afterdark()
        self.assertTrue(afterdark.is_unlocked(a.state))
        self.assertIn("on", a.moon_btn.cget("text"))
        for f in (core.STATE_PATH, core.CONFIG_PATH):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn(adult, text); self.assertNotIn("1990", text); self.assertNotIn(young, text)
        self.assertNotIn(adult, self.log())
        a.ask_birthdate = lambda check: self.fail("asked for a date again")
        a.ask_afterdark_unlocked = lambda: False                  # keep it on
        a.open_afterdark()
        self.assertTrue(afterdark.is_unlocked(a.state))
        a.ask_afterdark_unlocked = lambda: True                   # lock again
        a.open_afterdark()
        self.assertFalse(afterdark.is_unlocked(a.state))
        self.assertFalse(afterdark.is_unlocked(core.load_state()))
        self.assertEqual(a.moon_btn.cget("text"), "☾")

    def test_afterdark_content_unreachable_while_locked(self):
        """A sentinel in a temp After Dark data dir (patched the way tests/test_cast.py does) never reaches the log
        while locked, over many hang-outs, jokes, chats and activities; unlocking makes it reachable."""
        data = self.tmp / "addata"; (data / "afterdark").mkdir(parents=True)
        packs = self.tmp / "packs"; packs.mkdir()
        regs = cast.regulars()
        per = {cid: [f"{SENTINEL} {cid}"] for cid in regs}
        doc = {b: per for b in ("greeting", "idle", "arrive", "leave", "absent", "study_break", "ranked", "synced",
                                "rotated", "rotation_due")}
        doc.update(jokes=[[cast.name(c), f"{SENTINEL} joke"] for c in regs],
                   fortunes=[[cast.name(c), f"{SENTINEL} fortune"] for c in regs],
                   activities={"pet": dict({"verb": "Pet", "needs": "none", "affection": 1, "energy": 0}, **per)})
        groups = [sorted(regs)] + [sorted(g) for g in (regs[:1], regs[:2])]
        scenes = [{"id": f"ad-{i}-{w}", "who": g, "when": w, "rating": "afterdark", "weight": 500,
                   "lines": [[g[0], f"{SENTINEL} scene"], [g[-1], f"{SENTINEL} reply"]]}
                  for i, g in enumerate(groups) for w in ("any", "night", "morning", "arrive", "leave")]
        (data / "afterdark" / "pets.json").write_text(json.dumps(doc), encoding="utf-8")
        (data / "afterdark" / "scenes.json").write_text(json.dumps({"version": 1, "scenes": scenes}), encoding="utf-8")
        old = (cast.AFTERDARK_DIR, cast.PACKS_DIR)
        cast.AFTERDARK_DIR, cast.PACKS_DIR = data / "afterdark", packs
        cast.reload()
        try:
            a = self.app
            a.everyone()
            for i in range(25):
                a.hang_out()
                while a._scene_queue:
                    a.advance()
                a.act_joke(); a.act_fortune(); a.act_study(); a.do_activity("pet")
                a.entry.insert(0, ["hello", "hang out", "tell me a joke", "after dark", "who is home"][i % 5]); a.chat()
            a.update()
            self.assertNotIn(SENTINEL, self.log())
            self.assertNotIn(SENTINEL, core.STATE_PATH.read_text(encoding="utf-8"))
            a.ask_birthdate = lambda check: check("1990-03-04")[0]
            a.open_afterdark()
            self.assertTrue(afterdark.is_unlocked(a.state))
            for _ in range(10):
                a.hang_out()
                while a._scene_queue:
                    a.advance()
            self.assertIn(SENTINEL, self.log())                   # the fixture is live: the lock was what hid it
        finally:
            cast.AFTERDARK_DIR, cast.PACKS_DIR = old
            cast.reload()

    # ---------------- motion and shutdown ----------------
    def test_reduce_motion_creates_no_animation_timers(self):
        os.environ["PAWTATION_REDUCE_MOTION"] = "1"
        try:
            a = self.make()
            self.assertTrue(a.reduced)
            a.everyone(); a.hang_out(); a.do_activity("pet"); a.act_joke(); a.surprise(); a.advance()
            a.update()
            self.assertTrue(set(a._after) <= {"tick"}, a._after)
            for cid in a.stage.present():
                self.assertNotIn(cid, [k for k in a.stage.actors if a.stage.actors[k].get("override")])
            a.destroy()
        finally:
            del os.environ["PAWTATION_REDUCE_MOTION"]

    def test_close_during_animation_leaves_no_pending_after(self):
        a = self.make()
        a.everyone(); a.hang_out(); a.do_activity("pet"); a.say(f"{cast.name(a.brain.home()[0])}: one\n"
                                                               f"{cast.name(a.brain.home()[-1])}: two")
        for _ in range(20):
            a.update(); time.sleep(0.01)
        pending = list(a._after.values())
        self.assertIn("anim", a._after)
        interp = a.tk
        a.destroy()
        left = interp.call("after", "info")
        left = left if isinstance(left, tuple) else tuple(str(left).split())
        self.assertFalse([i for i in pending if i in left], left)       # every after() we made was cancelled



@unittest.skipUnless(DISPLAY, "tkinter or a display is not available")
class SealedSectionGui(unittest.TestCase):
    """SPEC_V2 section 9 in the window: nothing visible before it is opened; the bare prompt; the opened window."""
    CODE, PASS = "Tq7Wm2Zx", "4815162342"           # test values only

    def setUp(self):
        from pawtation import hidden
        self.hidden = hidden
        assert str(core.CONFIG_PATH).startswith(HOME), "refusing to run GUI tests against the real config"
        self.tmp = Path(tempfile.mkdtemp(dir=HOME))
        self.addCleanup(shutil.rmtree, str(self.tmp), ignore_errors=True)
        kept = (cast.PACKS_DIR, hidden.ITERATIONS)

        def restore():
            hidden.close()
            cast.PACKS_DIR, hidden.ITERATIONS = kept
            cast.reload()
        self.addCleanup(restore)
        cast.PACKS_DIR = self.tmp / "packs"
        cast.PACKS_DIR.mkdir()
        hidden.ITERATIONS = 1000
        cast.reload()
        for f in (core.CONFIG_PATH, core.STATE_PATH):
            if f.exists():
                f.unlink()
        core.update_config(library_dir="")
        st = core.load_state()
        st["afterdark"] = {"unlocked": True, "confirmed_on": "2026-11-01"}
        self.assertTrue(hidden.setup(st, self.CODE, self.PASS)[0])
        core.save_state(st)
        self.msgs = []
        self.app = gui.App()
        self.app.show_info = lambda t, x: self.msgs.append((t, x))
        self.app.show_error = lambda t, x: self.msgs.append((t, x))
        self.app.update()
        self.addCleanup(self._destroy)

    def _destroy(self):
        try:
            self.app.destroy()
        except Exception:
            pass

    def walk(self, w):
        yield w
        for child in w.winfo_children():
            yield from self.walk(child)

    def texts(self, root):
        out = []
        for w in self.walk(root):
            for opt in ("text", "title"):
                if w.winfo_class() in ("Entry", "TEntry"):              # "text" would abbreviate to textvariable
                    continue
                try:
                    out.append(str(w.cget(opt)))
                except Exception:
                    pass
            if isinstance(w, tkinter.Canvas):
                for item in w.find_all():
                    try:
                        out.append(str(w.itemcget(item, "text")))
                    except Exception:
                        pass
            if isinstance(w, tkinter.Menu):
                for i in range((w.index("end") or -1) + 1):
                    try:
                        out.append(str(w.entrycget(i, "label")))
                    except Exception:
                        pass
            if isinstance(w, (tkinter.Toplevel, tkinter.Tk)):
                out.append(w.title())
        return out

    def type_line(self, text):
        self.app.entry.delete(0, "end")
        self.app.entry.insert(0, text)
        self.app.chat()
        self.app.update()

    def test_nothing_mentions_it_before_it_is_opened(self):
        a = self.app
        blob = self.texts(a)
        a.show_help()
        blob += [x for m in self.msgs for x in m]
        blob += [t for t, _fn in a._tools()] + [str(x) for x in a.brain.activities()]
        blob += [a.status.get(), a.log.get("1.0", "end"), a.title()]
        popups = []
        a._popup = lambda anchor, items: popups.extend(t for t, _fn in items)
        blob += popups
        self.assertTrue(any("Help" in t or "help" in t for t in blob))       # the walk did see real text
        hits = [t for t in blob if "hidden" in t.lower() or "hw-setup" in t]
        self.assertEqual(hits, [])
        self.assertIsNone(getattr(a, "_sealed_win", None))

    def test_wrong_code_is_logged_and_answered(self):
        before = self.app.log.get("1.0", "end")
        self.type_line("Tq7Wm2Zy")
        after = self.app.log.get("1.0", "end")
        self.assertIn("You: Tq7Wm2Zy", after)
        self.assertGreater(len(after.split("You: Tq7Wm2Zy", 1)[1].strip()), 0)     # somebody answered
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertIsNone(getattr(self.app, "_sealed_prompt", None))

    def test_full_flow(self):
        a = self.app
        before = a.log.get("1.0", "end")
        self.type_line(self.CODE)
        self.assertEqual(a.entry.get(), "")
        self.assertEqual(a.log.get("1.0", "end"), before)                  # swallowed: nothing logged
        prompt = a._sealed_prompt
        self.assertEqual(prompt.title(), "")
        kinds = [w.winfo_class() for w in self.walk(prompt)]
        self.assertNotIn("Label", kinds)
        self.assertEqual(kinds.count("Entry"), 1)
        self.assertEqual(a._sealed_entry.cget("show"), "•")
        self.assertTrue(all(t in ("", "None") for t in self.texts(prompt)), self.texts(prompt))
        a._sealed_entry.insert(0, self.PASS)
        a._sealed_entry.event_generate("<Return>")
        a.update()
        self.assertFalse(prompt.winfo_exists())
        self.assertTrue(self.hidden.is_open())
        win = a._sealed_win
        self.assertEqual(win.title(), "The Hidden World")
        self.assertIn("Nothing here yet.", self.texts(win))
        self.assertEqual(a.log.get("1.0", "end"), before)
        self.assertEqual(core.load_state()["hw"]["fails"], 0)
        raw = core.STATE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(self.CODE, raw); self.assertNotIn(self.PASS, raw)
        a.tk.call(win.protocol("WM_DELETE_WINDOW"))                       # the window's close button
        a.update()
        self.assertFalse(win.winfo_exists())
        self.assertFalse(self.hidden.is_open())
        self.assertIsNone(a._sealed_win)

    def test_wrong_passcode_just_closes(self):
        a = self.app
        before = a.log.get("1.0", "end")
        self.type_line(self.CODE)
        prompt = a._sealed_prompt
        a._sealed_entry.insert(0, "0000000000")
        a._sealed_entry.event_generate("<Return>")
        a.update()
        self.assertFalse(prompt.winfo_exists())
        self.assertFalse(self.hidden.is_open())
        self.assertIsNone(getattr(a, "_sealed_win", None))
        self.assertEqual(a.log.get("1.0", "end"), before)
        self.assertEqual(core.load_state()["hw"]["fails"], 1)             # the throttle was saved

    def test_pack_gallery_and_quit_locks(self):
        folder = cast.PACKS_DIR / "mine"
        (folder / "gallery").mkdir(parents=True)
        (folder / "pack.json").write_text(json.dumps({"name": "Mine", "rating": "hidden"}), encoding="utf-8")
        img = tkinter.PhotoImage(master=self.app, width=900, height=40)
        img.put("red", to=(0, 0, 900, 40))
        img.write(str(folder / "gallery" / "a.png"), format="png")
        (folder / "gallery" / "b.gif").write_bytes(b"not really a gif")
        cast.reload()
        self.assertTrue(self.hidden.try_open(self.app.state, self.PASS))
        win = self.app._sealed_window_open()
        self.app.update()
        ui = self.app._sealed_ui
        self.assertEqual(ui["list"].get(0, "end"), ("Mine",))
        self.assertEqual(len(ui["images"]), 2)
        self.assertIsNotNone(ui["img"])
        self.assertLessEqual(ui["img"].width(), 450)                      # subsampled to fit
        self.assertEqual(ui["count"].cget("text"), "1 / 2")
        self.app._sealed_show(1)                                          # a broken file shows a note, not a crash
        self.assertIsNone(ui["img"])
        self.assertEqual(str(ui["play"].cget("state")), "disabled")       # no scenes in this pack
        self.app.destroy()
        self.assertFalse(self.hidden.is_open())


if __name__ == "__main__":
    unittest.main()
