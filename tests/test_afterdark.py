"""After Dark end-to-end audit (docs/SPEC_V2.md section 4), through the real CLI commands rather than the brain.

tests/test_cast.py (Lockdown) brute-forces the PetBrain / cast API and tests/test_gui.py covers the app window. This
file drives `pawtation.cli.main` in-process against a temp home, a temp library, a temp SD card and a temp After Dark
tree full of a sentinel, so the shipped data/ is never touched and the real config/state are never read.

Paths checked while LOCKED: init, scan, status, plan --commit, sync --go (stdout and /pawtation/quips.txt), cast,
scene (every `--when`), chat (piped), wrapped, doctor, afterdark --status, the plugin chat-hook context. Then: under-18,
future and garbage dates stay locked; an adult date unlocks; card quips stay all-rated; the date never reaches the
state file or any output; --lock hides it all again."""
import builtins
import contextlib
import datetime
import io
import json
import struct
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pawtation import afterdark, cast, cli, core, discimage, pets

SENTINEL = "QQNIGHTSENTINELQQ"
ADULT = "1984-07-09"                                    # an arbitrary test date, not anyone's birthday on record
WHENS = ["any", "night", "morning", "arrive", "leave", "rotated", "synced", "due"]


def mktmp(case):
    """A temp folder that is removed when the test finishes."""
    d = tempfile.mkdtemp()
    case.addCleanup(shutil.rmtree, d, ignore_errors=True)
    return Path(d)


def isolate_plugins(case):
    """cli.main() loads the repo's plugins/ into module-level registries; put them back afterwards so later tests
    (tests/test_features.py Plugins) see a clean slate."""
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


def disc(code6: str, title: str, size: int = 64 * 1024) -> bytes:
    head = bytearray(0x60)
    head[:6] = code6.encode(); head[0x1C:0x20] = struct.pack(">I", discimage.GC_MAGIC)
    head[0x20:0x20 + len(title)] = title.encode()
    return bytes(head) + b"\0" * (size - len(head))


class CliAfterDark(unittest.TestCase):
    def setUp(self):
        isolate_plugins(self)
        self.tmp = mktmp(self)
        self.home, self.lib, self.sd = self.tmp / "home", self.tmp / "lib", self.tmp / "sd"
        for d in (self.home, self.lib, self.sd):
            d.mkdir()
        self.ad, self.packs = self.tmp / "data" / "afterdark", self.tmp / "packs"
        self.ad.mkdir(parents=True); self.packs.mkdir()
        old = (core.CONFIG_PATH, core.STATE_PATH, cast.AFTERDARK_DIR, cast.PACKS_DIR)

        def restore():
            core.CONFIG_PATH, core.STATE_PATH, cast.AFTERDARK_DIR, cast.PACKS_DIR = old
            cast.reload()
        self.addCleanup(restore)
        core.CONFIG_PATH, core.STATE_PATH = self.home / "config.json", self.home / "state.json"
        cast.AFTERDARK_DIR, cast.PACKS_DIR = self.ad, self.packs
        cast.reload()
        self.lib.joinpath("ttyd.iso").write_bytes(disc("G8ME01", "PAPER MARIO"))
        self.lib.joinpath("chibi.iso").write_bytes(disc("GCBE7D", "CHIBI-ROBO"))

    # ---- helpers
    def run_cli(self, *args, typed=()):
        """cli.main in-process; `typed` feeds input() (then EOF). Returns (exit code, everything printed)."""
        feed = list(typed)

        def fake_input(prompt=""):
            out.write(str(prompt))
            if not feed:
                raise EOFError
            return feed.pop(0)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out), mock.patch.object(builtins, "input", fake_input):
            try:
                code = cli.main(list(args))
            except SystemExit as e:
                code = e.code
        return code or 0, out.getvalue()

    def plant(self, keys):
        """Sentinel After Dark content in every place it can live: the built-in tier, an afterdark pack, a pack with
        no pack.json, and afterdark-rated scenes hidden inside an all-rated pack."""
        regs = cast.regulars()
        per = {c: [f"{SENTINEL} {c}"] for c in cast.characters()}
        doc = {b: per for b in ("greeting", "idle", "arrive", "leave", "absent", "study_break", "ranked", "synced",
                                "rotated", "rotation_due")}
        doc.update(jokes=[[cast.name(c), f"{SENTINEL} joke"] for c in regs],
                   fortunes=[[cast.name(c), f"{SENTINEL} fortune"] for c in regs],
                   game_quips={k: {c: f"{SENTINEL} quip" for c in regs} for k in keys},
                   tag_quips={t: {c: f"{SENTINEL} tag" for c in regs} for t in ("cozy", "rpg", "party", "racing", "action")})
        groups = sorted({tuple(sorted(g)) for g in (regs, regs[:1], regs[1:2], regs[:2], [regs[0], regs[2]], regs[1:])})
        scenes = [{"id": f"ad-{i}-{w}", "who": list(g), "when": w, "rating": "afterdark", "weight": 1000,
                   "lines": [[g[0], f"{SENTINEL} scene"], [g[-1], f"{SENTINEL} reply"]]}
                  for i, g in enumerate(groups) for w in WHENS]
        put = lambda p, o: (p.parent.mkdir(parents=True, exist_ok=True), p.write_text(json.dumps(o), encoding="utf-8"))
        put(self.ad / "pets.json", doc); put(self.ad / "scenes.json", {"version": 1, "scenes": scenes})
        put(self.packs / "spicy" / "pack.json", {"name": "Spicy", "rating": "afterdark"})
        put(self.packs / "spicy" / "pets.json", doc)
        put(self.packs / "unlabelled" / "pets.json", doc)
        put(self.packs / "cozy" / "pack.json", {"name": "Cozy", "rating": "all"})
        put(self.packs / "cozy" / "scenes.json", {"version": 1, "scenes": scenes})
        cast.reload()

    def every_path(self, card_go=True):
        """Every CLI path that prints character content. Returns the combined output."""
        outs = []
        for cmd in (["status"], ["cast"], ["cast", "--everyone"], ["wrapped"], ["doctor"], ["afterdark", "--status"]):
            code, out = self.run_cli(*cmd); self.assertEqual(code, 0, f"{cmd}: {out}"); outs.append(out)
        for group in (["--everyone"], ["--gather", "nova"], ["--gather", "iggy", "nova"], ["--gather", "duskie", "nova"]):
            self.run_cli("cast", *group)
            for when in WHENS + ["game:paper-mario-the-thousand-year-door", "tag:cozy"]:
                for _ in range(2):
                    outs.append(self.run_cli("scene", "--when", when)[1])
            outs.append(self.run_cli("chat", typed=["hello", "hang out", "scene", "tell me a joke", "fortune", "who is home",
                                                    "after dark", "unlock after dark " + ADULT, "nova", "iggy", "duskie",
                                                    "study break", "quit"])[1])
        if card_go:
            code, out = self.run_cli("sync", "1", "--mount", str(self.sd), "--go", "--verify")
            self.assertEqual(code, 0, out); outs.append(out)
        return "\n".join(outs)

    def card_text(self):
        q = self.sd / "pawtation" / "quips.txt"
        return q.read_text(encoding="utf-8") if q.exists() else ""

    # ---- the audit
    def test_cli_paths_locked_unlocked_and_relocked(self):
        code, out = self.run_cli("init", "--library", str(self.lib)); self.assertEqual(code, 0, out)
        cfg = json.loads(core.CONFIG_PATH.read_text()); cfg.update(reserve_mb=0, mods_dir=str(self.tmp / "mods"))
        cfg["cards"] = {"1": {"label": "One", "capacity_gb": 1, "mount": ""}}
        core.CONFIG_PATH.write_text(json.dumps(cfg))
        self.assertIn("2 games", self.run_cli("scan")[1])
        keys = [r.key for r in core.scan_library(core.load_config(), core.Catalog())]
        self.plant(keys)
        code, out = self.run_cli("plan", "--commit"); self.assertEqual(code, 0, out)
        locked = out + self.every_path()
        self.assertNotIn(SENTINEL, locked)
        self.assertTrue(self.card_text().strip()); self.assertNotIn(SENTINEL, self.card_text())
        self.assertNotIn("afterdark", cast._CACHE.get("tiers", {}))         # never even read while locked

        # dates that must not unlock; none of them may be echoed or stored
        today = datetime.date.today()
        young = today.replace(year=today.year - 17).isoformat() if not (today.month == 2 and today.day == 29) else "2015-01-01"
        future = (today + datetime.timedelta(days=400)).isoformat()
        for bad in (young, future, "1984-02-30", "not a date", "", "99/99/1999", "0001-01-01"):
            code, out = self.run_cli("afterdark", typed=[bad])
            self.assertEqual(code, 1, (bad, out)); self.assertIn("locked", out)
            if any(ch.isdigit() for ch in bad):                              # date-shaped input is never echoed
                self.assertNotIn(bad, out)
                self.assertNotIn(bad, core.STATE_PATH.read_text(encoding="utf-8"))
            self.assertFalse(afterdark.is_unlocked(core.load_state()))
        self.assertNotIn(SENTINEL, self.every_path(card_go=False))

        # an adult date unlocks, once
        code, out = self.run_cli("afterdark", typed=[ADULT]); self.assertEqual(code, 0, out)
        self.assertTrue(afterdark.is_unlocked(core.load_state()))
        self.assertEqual(set(core.load_state()["afterdark"]), {"unlocked", "confirmed_on"})
        code, out = self.run_cli("afterdark", typed=["should not be asked"]); self.assertIn("is unlocked", out)
        self.assertNotIn("Date of birth", out)
        unlocked = self.every_path()
        self.assertIn(SENTINEL, unlocked)                                    # so the locked hunt above meant something
        self.assertNotIn(SENTINEL, self.card_text())                          # card quips are all-rated, always
        for text in (unlocked, core.STATE_PATH.read_text(encoding="utf-8"), core.CONFIG_PATH.read_text(encoding="utf-8")):
            self.assertNotIn(ADULT, text); self.assertNotIn("1984", text)

        # lock again: gone everywhere
        code, out = self.run_cli("afterdark", "--lock"); self.assertEqual(code, 0, out)
        self.assertFalse(afterdark.is_unlocked(core.load_state()))
        self.assertNotIn(SENTINEL, self.every_path())
        self.assertNotIn(SENTINEL, self.card_text())

    def test_plugin_chat_hooks_see_no_afterdark_content_while_locked(self):
        self.plant(["pikmin-2"])
        seen = []

        def hook(brain, match, ctx):
            seen.append(json.dumps(ctx, default=str))
            seen.extend([brain.joke(), brain.fortune(), *brain.duo("greeting"), *(brain.scene() or [])])
            return "hooked"
        pets.CHAT_HOOKS.append((__import__("re").compile("plugtest"), hook))
        self.addCleanup(pets.CHAT_HOOKS.pop)
        state = {}
        brain = pets.PetBrain(state, core.Catalog())
        for _ in range(20):
            self.assertEqual(brain.reply("plugtest"), "hooked")
        self.assertTrue(seen); self.assertNotIn(SENTINEL, "\n".join(seen))
        afterdark.unlock(state, afterdark.parse_date(ADULT))
        for _ in range(20):
            brain.reply("plugtest")
        self.assertIn(SENTINEL, "\n".join(seen))                             # the hunt can see it once unlocked


if __name__ == "__main__":
    unittest.main()
