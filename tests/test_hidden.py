"""SPEC_V2 section 9 (pawtation/hidden.py and the places it touches). Temp homes and temp packs only: config,
state and the packs folder are pointed at a temp dir that is removed afterwards. The code and passcode below are
throwaway test values."""
import contextlib
import io
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pawtation import cast, cli, core, hidden, pets
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent
CODE, PASS = "Tq7Wm2Zx", "4815162342"           # test values only
SENT = "QQSEALEDSENTINELQQ"
UNLOCKED = {"unlocked": True, "confirmed_on": "2026-11-01"}
REAL_RANDOM = random.Random


def mktmp(case):
    d = tempfile.mkdtemp(prefix="pawtation-hw-")
    case.addCleanup(shutil.rmtree, d, ignore_errors=True)
    return Path(d)


def isolate_plugins(case):
    """cli.main()/build_ctx() load the repo's plugins into module-level registries; restore them afterwards."""
    from pawtation import plugins, saves
    lists = (pets.CHAT_HOOKS, core.SCORE_HOOKS, plugins.LOADED, plugins.ERRORS)
    dicts = (plugins.EVENTS, plugins.COMMANDS, saves.PROGRESS_PARSERS)
    kept = ([list(x) for x in lists], [dict(x) for x in dicts], set(plugins.FAILED), json.dumps(pets.PETS))

    def restore():
        for x, old in zip(lists, kept[0]):
            x[:] = old
        for x, old in zip(dicts, kept[1]):
            x.clear(); x.update(old)
        plugins.FAILED.clear(); plugins.FAILED.update(kept[2])
        pets.PETS.clear(); pets.PETS.update(json.loads(kept[3]))
    case.addCleanup(restore)


class Base(unittest.TestCase):
    def setUp(self):
        self.home = mktmp(self)
        kept = (core.CONFIG_PATH, core.STATE_PATH, cast.PACKS_DIR, hidden.ITERATIONS)

        def restore():
            hidden.close()
            core.CONFIG_PATH, core.STATE_PATH, cast.PACKS_DIR, hidden.ITERATIONS = kept
            cast.reload()
        self.addCleanup(restore)
        core.CONFIG_PATH, core.STATE_PATH = self.home / "config.json", self.home / "state.json"
        cast.PACKS_DIR = self.home / "packs"
        cast.PACKS_DIR.mkdir()
        hidden.ITERATIONS = 1000
        hidden.close()
        cast.reload()
        isolate_plugins(self)

    def state(self, configured=True, unlocked=True):
        st = {"afterdark": dict(UNLOCKED) if unlocked else {"unlocked": False},
              "scene": {"who": sorted(cast.default_group()), "until": 4102444800, "manual": True}}
        if configured:
            self.assertEqual(hidden.setup(st, CODE, PASS)[0], True)
        return st

    def sealed_pack(self, gallery=False):
        folder = cast.PACKS_DIR / "zz"
        folder.mkdir()
        group = sorted(cast.default_group())
        (folder / "pack.json").write_text(json.dumps({"name": "Pack " + SENT, "rating": "hidden"}), encoding="utf-8")
        lines = {"jokes": [[cast.name(c), SENT] for c in cast.regulars()],
                 "fortunes": [[cast.name(c), SENT] for c in cast.regulars()],
                 "idle": {c: [SENT] for c in cast.regulars()}, "greeting": {c: [SENT] for c in cast.regulars()},
                 "game_quips": {"paper-mario-ttyd": {c: SENT for c in cast.regulars()}}}
        (folder / "pets.json").write_text(json.dumps(lines), encoding="utf-8")
        scenes = {"version": 1, "scenes": [{"id": "zz-" + w, "who": group, "when": w, "weight": 1000,
                                            "lines": [[group[0], SENT]]} for w in ("any", "zzwhen", "rotated")]}
        (folder / "scenes.json").write_text(json.dumps(scenes), encoding="utf-8")
        if gallery:
            (folder / "gallery").mkdir()
        cast.reload()
        return folder


class Storage(Base):
    def test_only_hashes_are_stored(self):
        st = self.state()
        core.save_state(st)
        raw = core.STATE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(CODE, raw)
        self.assertNotIn(PASS, raw)
        hw = json.loads(raw)["hw"]
        self.assertEqual(sorted(hw), ["code", "fails", "pass", "v", "wait_until"])
        for rec in (hw["code"], hw["pass"]):
            self.assertEqual(sorted(rec), ["hash", "iter", "salt"])
            self.assertEqual(len(bytes.fromhex(rec["salt"])), 16)
            self.assertEqual(rec["iter"], 1000)
        self.assertNotEqual(hw["code"]["salt"], hw["pass"]["salt"])
        self.assertEqual(hidden.clean_state(core.load_state()["hw"]), hidden.clean_state(hw))

    def test_default_iterations_meet_the_spec(self):
        src = (ROOT / "pawtation" / "hidden.py").read_text(encoding="utf-8")
        self.assertIn("ITERATIONS = 200000", src)

    def test_stored_iteration_count_is_used(self):
        st = self.state()
        hidden.ITERATIONS = 2000                             # a later change does not break older records
        self.assertTrue(hidden.check_code(st, CODE))
        self.assertTrue(hidden.try_open(st, PASS, now=1000))

    def test_damaged_records_read_as_unconfigured(self):
        for bad in ({"v": 1}, [], "x", {"code": {"salt": "zz", "hash": "00", "iter": 5}, "pass": {}}):
            core.save_json(core.STATE_PATH, {"hw": bad})
            st = core.load_state()
            self.assertNotIn("hw", st)
            self.assertFalse(hidden.is_configured(st))

    def test_setup_validation(self):
        for code, passcode in (("Tq7Wm2Z", PASS), ("Tq7Wm2Zxy", PASS), ("Tq7Wm2Z!", PASS), ("Tq7Wm2Zé", PASS),
                               (CODE, "481516234"), (CODE, "48151623420"), (CODE, "48151623a2"),
                               (CODE, "٤٨١٥١٦٢٣٤٢"), (None, PASS), (CODE, 4815162342)):
            st = {}
            ok, msg = hidden.setup(st, code, passcode)
            self.assertFalse(ok, (code, passcode))
            self.assertNotIn("hw", st)
            self.assertNotIn(str(code), msg); self.assertNotIn(str(passcode), msg)
        st = {}
        self.assertEqual(hidden.setup(st, CODE, PASS), (True, hidden.MSG_SET))
        hidden.clear(st)
        self.assertNotIn("hw", st)


class Gate(Base):
    def test_inert_when_unconfigured(self):
        st = self.state(configured=False)
        before = json.dumps(st, sort_keys=True)
        self.assertFalse(hidden.check_code(st, CODE))
        self.assertFalse(hidden.try_open(st, PASS))
        self.assertFalse(hidden.is_open())
        self.assertEqual(hidden.packs(), [])
        self.assertEqual(json.dumps(st, sort_keys=True), before)

    def test_needs_after_dark(self):
        st = self.state(unlocked=False)
        self.assertFalse(hidden.check_code(st, CODE))
        self.assertFalse(hidden.try_open(st, PASS))
        self.assertFalse(hidden.is_open())
        st["afterdark"] = dict(UNLOCKED)
        self.assertTrue(hidden.check_code(st, CODE))
        self.assertTrue(hidden.check_code(st, "  " + CODE + " "))

    def test_check_code_rejects_and_never_mutates(self):
        st = self.state()
        before = json.dumps(st, sort_keys=True)
        for text in (CODE.lower(), CODE[:-1], CODE + "1", "", None, 12345678, "Tq7Wm2Zy"):
            self.assertFalse(hidden.check_code(st, text), text)
        self.assertTrue(hidden.check_code(st, CODE))
        self.assertEqual(json.dumps(st, sort_keys=True), before)

    def test_throttle_schedule_persists(self):
        st = self.state()
        t = 1_000_000.0
        for i in range(4):
            self.assertFalse(hidden.try_open(st, "0000000000", now=t))
            self.assertEqual(st["hw"]["wait_until"], 0)
        self.assertFalse(hidden.try_open(st, "0000000000", now=t))           # 5th wrong: one minute
        self.assertEqual((st["hw"]["fails"], st["hw"]["wait_until"]), (5, t + 60))
        core.save_state(st)
        st = core.load_state()
        self.assertEqual((st["hw"]["fails"], st["hw"]["wait_until"]), (5, t + 60))
        with mock.patch.object(hidden, "_hash", side_effect=AssertionError("hashed during a wait")):
            self.assertFalse(hidden.try_open(st, PASS, now=t + 59))         # refused, not even hashed
        self.assertEqual(st["hw"]["fails"], 5)
        self.assertFalse(hidden.try_open(st, "0000000000", now=t + 60))     # 6th wrong: two minutes
        self.assertEqual((st["hw"]["fails"], st["hw"]["wait_until"]), (6, t + 60 + 120))
        self.assertFalse(hidden.try_open(st, "0000000000", now=t + 180))    # 7th wrong: four minutes
        self.assertEqual(st["hw"]["wait_until"], t + 180 + 240)
        self.assertFalse(hidden.try_open(st, PASS, now=t + 400))
        self.assertFalse(hidden.is_open())
        self.assertTrue(hidden.try_open(st, PASS, now=t + 420))
        self.assertEqual((st["hw"]["fails"], st["hw"]["wait_until"]), (0, 0))

    def test_open_flag_is_per_process_and_close_clears_it(self):
        st = self.state()
        self.assertTrue(hidden.try_open(st, PASS))
        self.assertTrue(hidden.is_open())
        core.save_state(st)
        self.assertNotIn("open", core.STATE_PATH.read_text(encoding="utf-8").lower().replace("wait_until", ""))
        env = dict(os.environ, PAWTATION_HOME=str(self.home))
        r = subprocess.run([sys.executable, "-c", "from pawtation import hidden; print(hidden.is_open())"],
                           cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(r.stdout.strip(), "False", r.stderr)
        hidden.close()
        self.assertFalse(hidden.is_open())
        self.assertEqual(hidden.packs(), [])


class Engine(Base):
    def brain(self, st):
        return pets.PetBrain(st, Catalog(), REAL_RANDOM(4))

    def public_text(self, st):
        """Everything the ordinary engine paths produce, as one blob."""
        b = self.brain(st)
        out = []
        for _ in range(25):
            out += [b.reply("joke"), b.reply("tell me a fortune"), b.reply("hello"), b.joke(), b.fortune()]
            out += b.scene() + b.scene("zzwhen") + b.event("rotated") + b.duo("greeting")
            out += [b.say(c, "idle") for c in b.home()]
        out += b.card_quips(["paper-mario-ttyd"])
        out.append(json.dumps([cast.packs(True), cast.packs(False), cast.all_scenes(False),
                               cast.extra_pets(False)], default=str))
        return "\n".join(str(x) for x in out)

    def side_outputs(self, st):
        """cast listing, wrapped, doctor and the card quips file input: never see section 9, open or not."""
        core.save_state(st)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.main(["cast"])
            cli.main(["wrapped"])
            try:
                cli.main(["doctor"])
            except SystemExit:
                pass
        quips = self.brain(st).card_quips(["paper-mario-ttyd"], limit=400)
        return buf.getvalue() + "\n".join(quips)

    def test_unreachable_while_closed(self):
        self.sealed_pack()
        st = self.state()
        st["history"] = [{"ts": 1, "season": 1, "plan": {"1": ["paper-mario-ttyd"]}}]
        self.assertNotIn(SENT, self.public_text(st))
        self.assertNotIn(SENT, json.dumps([cast.all_scenes(True), cast.extra_pets(True),
                                           cast.packs(True, sealed=True)], default=str))
        self.assertNotIn(SENT, self.side_outputs(st))

    def test_reachable_only_while_open_and_unlocked(self):
        self.sealed_pack()
        st = self.state()
        self.assertTrue(hidden.try_open(st, PASS))
        self.assertIn(SENT, json.dumps([cast.all_scenes(True), cast.extra_pets(True)]))
        self.assertIn(SENT, "\n".join(self.brain(st).scene("zzwhen")))
        self.assertEqual([p["path"].name for p in cast.packs(True, sealed=True)], ["zz"])
        self.assertEqual([p["path"].name for p in hidden.packs()], ["zz"])
        # never for a locked caller, card quips, the plain pack list, cast, wrapped or doctor
        self.assertNotIn(SENT, json.dumps([cast.all_scenes(False), cast.extra_pets(False), cast.packs(True),
                                           cast.packs(False, sealed=True)], default=str))
        self.assertNotIn(SENT, "\n".join(self.brain(st).card_quips(["paper-mario-ttyd"], limit=400)))
        self.assertNotIn(SENT, self.side_outputs(st))
        locked = dict(st, afterdark={"unlocked": False})
        self.assertNotIn(SENT, "\n".join(self.brain(locked).scene("zzwhen")))
        hidden.close()
        self.assertNotIn(SENT, json.dumps([cast.all_scenes(True), cast.extra_pets(True),
                                           cast.packs(True, sealed=True)], default=str))
        self.assertNotIn(SENT, "\n".join(self.brain(st).scene("zzwhen")))


class Cli(Base):
    def run_chat(self, st, lines):
        core.save_state(st)
        out = io.StringIO()
        with mock.patch.object(pets.random, "Random", lambda *a, **k: REAL_RANDOM(5)), \
                mock.patch("sys.stdin", io.StringIO("".join(l + "\n" for l in lines))), \
                contextlib.redirect_stdout(out):
            cli.cmd_chat(None)
        return out.getvalue()

    def test_wrong_code_is_an_ordinary_message(self):
        wrong = "Tq7Wm2Zy"
        with_feature = self.run_chat(self.state(), [wrong, "quit"])
        without = self.run_chat(self.state(configured=False), [wrong, "quit"])
        self.assertEqual(with_feature, without)
        self.assertNotIn("Hidden", with_feature)

    def test_wrong_passcode_prints_nothing(self):
        st = self.state()
        plain = self.run_chat(st, ["", "quit"])                          # the same as pressing Enter on nothing
        st = self.state()
        got = self.run_chat(st, [CODE, "0000000000", "quit"])
        self.assertEqual(got, plain)
        self.assertEqual(core.load_state()["hw"]["fails"], 1)            # the throttle was saved
        self.assertFalse(hidden.is_open())

    def test_right_passcode_lists_and_closes_on_exit(self):
        got = self.run_chat(self.state(), [CODE, PASS, "quit"])
        self.assertIn("The Hidden World", got)
        self.assertIn("Nothing here yet.", got)
        self.assertNotIn(CODE, got); self.assertNotIn(PASS, got)
        self.assertFalse(hidden.is_open())
        self.sealed_pack()
        got = self.run_chat(self.state(), [CODE, PASS, "quit"])
        self.assertIn("Pack " + SENT, got)
        self.assertNotIn("Nothing here yet.", got)
        self.assertFalse(hidden.is_open())

    def test_code_needs_after_dark_in_chat(self):
        got = self.run_chat(self.state(unlocked=False), [CODE, "quit"])
        self.assertNotIn("The Hidden World", got)

    def setup_cmd(self, args, lines):
        out = io.StringIO()
        with mock.patch("sys.stdin", io.StringIO("".join(l + "\n" for l in lines))), contextlib.redirect_stdout(out):
            rc = cli.main(["hw-setup"] + args)
        return rc, out.getvalue()

    def test_setup_command(self):
        rc, out = self.setup_cmd([], [CODE, CODE, PASS, PASS])
        self.assertEqual(rc, 0, out)
        self.assertNotIn(CODE, out); self.assertNotIn(PASS, out)
        raw = core.STATE_PATH.read_text(encoding="utf-8")
        self.assertNotIn(CODE, raw); self.assertNotIn(PASS, raw)
        self.assertTrue(hidden.is_configured(core.load_state()))
        rc, out = self.setup_cmd(["--clear"], [])
        self.assertEqual(rc, 0)
        self.assertFalse(hidden.is_configured(core.load_state()))
        for lines in ([CODE, CODE[:-1] + "q", PASS, PASS], [CODE, CODE, PASS, PASS[:-1] + "0"],
                      ["short", "short", PASS, PASS], [CODE, CODE, "12345", "12345"], []):
            rc, out = self.setup_cmd([], lines)
            self.assertEqual(rc, 1, lines)
            self.assertNotIn(CODE, out); self.assertNotIn(PASS, out)
            self.assertFalse(hidden.is_configured(core.load_state()))

    def test_setup_through_the_real_entry_point(self):
        env = dict(os.environ, PAWTATION_HOME=str(self.home))
        r = subprocess.run([sys.executable, "-m", "pawtation", "hw-setup"], cwd=str(ROOT), env=env,
                           input=f"{CODE}\n{CODE}\n{PASS}\n{PASS}\n", capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        for blob in (r.stdout, r.stderr, (self.home / "state.json").read_text(encoding="utf-8")):
            self.assertNotIn(CODE, blob); self.assertNotIn(PASS, blob)
        hw = json.loads((self.home / "state.json").read_text(encoding="utf-8"))["hw"]
        self.assertGreaterEqual(hw["code"]["iter"], 200000)
        self.assertGreaterEqual(hw["pass"]["iter"], 200000)


class Secrecy(unittest.TestCase):
    def test_help_never_mentions_it(self):
        home = mktmp(self)
        env = dict(os.environ, PAWTATION_HOME=str(home))
        run = lambda args: subprocess.run([sys.executable, "-m", "pawtation"] + args, cwd=str(ROOT), env=env,
                                          capture_output=True, text=True, timeout=60)
        top = run(["--help"])
        self.assertEqual(top.returncode, 0, top.stderr)
        import re
        names = re.search(r"\{([a-z0-9_,-]+)\}", top.stdout).group(1).split(",")    # argparse's choices list
        self.assertIn("scan", names)
        self.assertNotIn("hw-setup", names)
        texts = [top.stdout + top.stderr]
        for name in names:
            r = run([name, "--help"])
            texts.append(r.stdout + r.stderr)
        for t in texts:
            self.assertNotIn("hw-setup", t)
            self.assertNotIn("hidden", t.lower())
        bad = run(["hw-setup", "--help"])                              # odd arguments: argparse refuses as usual
        self.assertNotIn("hw-setup ", bad.stdout + bad.stderr.replace("'hw-setup'", ""))
        self.assertNotIn("hidden", (bad.stdout + bad.stderr).lower())
        self.assertEqual(sorted(p.name for p in home.iterdir()), [])  # --help wrote nothing

    def test_readme_is_silent(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("hidden world", text.lower())
        self.assertNotIn("hw-setup", text)


if __name__ == "__main__":
    unittest.main()
