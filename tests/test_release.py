"""Release-review regressions (wave 3): scripts/doctor.py, the `cast` table, and collection lines. Temp homes only."""
import contextlib
import io
import json
import os
import random
import subprocess
import sys
import shutil
import tempfile
import unittest
from pathlib import Path

from pawtation import cast, cli, core, pets
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent


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


class Doctor(unittest.TestCase):
    def run_doctor(self, state):
        home = mktmp(self)
        (home / "state.json").write_text(json.dumps(state), encoding="utf-8")
        env = dict(os.environ, PAWTATION_HOME=str(home))
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "doctor.py")], cwd=str(ROOT), env=env,
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("Traceback", r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in home.iterdir()), ["state.json"])        # read-only
        return r.stdout

    def test_reports_art_theme_and_afterdark_without_details(self):
        out = self.run_doctor({})
        for needle in ("sprites:", "low-poly renders:", "theme file", "After Dark: locked", "Swiss: "):
            self.assertIn(needle, out)
        self.assertNotIn("[FAIL]", out)
        out = self.run_doctor({"afterdark": {"unlocked": True, "confirmed_on": "2026-11-15"}})
        self.assertIn("After Dark: unlocked", out)
        self.assertNotIn("2026-11-15", out)


class CliCastTable(unittest.TestCase):
    def test_columns_stay_aligned_with_long_names(self):
        isolate_plugins(self)
        home = mktmp(self)
        old = (core.CONFIG_PATH, core.STATE_PATH)
        self.addCleanup(lambda: (setattr(core, "CONFIG_PATH", old[0]), setattr(core, "STATE_PATH", old[1])))
        core.CONFIG_PATH, core.STATE_PATH = home / "config.json", home / "state.json"
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(cli.main(["cast"]), 0)
        rows = [l for l in out.getvalue().splitlines() if l.startswith("  ") and l.rstrip().endswith((" home", " out"))]
        self.assertEqual(len(rows), len(cast.characters()))
        role_col = {l.index(cast.character(cid)["role"], 2 + len(c["name"]) + len(c["species"]))
                    for l, (cid, c) in zip(rows, cast.characters().items())}
        self.assertEqual(len(role_col), 1, out.getvalue())


class HiddenRatedPacks(unittest.TestCase):
    """SPEC_V2 section 9: a pack rated "hidden" is never loaded, listed or counted by the ordinary engine, not even
    while After Dark is unlocked (it used to fall through to the After Dark tier). Odd pack.json shapes never crash."""

    def test_hidden_packs_stay_out_even_when_unlocked(self):
        tmp = mktmp(self)
        old = cast.PACKS_DIR
        self.addCleanup(lambda: (setattr(cast, "PACKS_DIR", old), cast.reload()))
        cast.PACKS_DIR = tmp
        line = {"idle": {c: ["QQHIDDENQQ"] for c in cast.regulars()}}
        scene = {"version": 1, "scenes": [{"id": "h", "who": sorted(cast.default_group()), "when": "any",
                                            "rating": "afterdark", "lines": [[cast.default_group()[0], "QQHIDDENQQ"]]}]}
        for name, meta in (("h", {"name": "QQHIDDENQQ", "rating": "hidden"}), ("odd", [1, 2]), ("str", "x")):
            (tmp / name).mkdir()
            (tmp / name / "pack.json").write_text(json.dumps(meta), encoding="utf-8")
        (tmp / "h" / "pets.json").write_text(json.dumps(line), encoding="utf-8")
        (tmp / "h" / "scenes.json").write_text(json.dumps(scene), encoding="utf-8")
        cast.reload()
        for unlocked in (False, True):
            blob = json.dumps([cast.packs(unlocked), cast.all_scenes(unlocked), cast.extra_pets(unlocked)], default=str)
            self.assertNotIn("QQHIDDENQQ", blob)
        self.assertEqual(sorted(p["path"].name for p in cast.packs(True)), ["odd", "str"])   # fail closed: After Dark


class Collection(unittest.TestCase):
    def test_a_trio_never_repeats_a_collection_line(self):
        state = {"scene": {"who": sorted(cast.regulars()), "until": 4102444800, "manual": True}}
        b = pets.PetBrain(state, Catalog(), random.Random(3))
        roms = [core.Rom(path=f"{i}.iso", size=1, code6=None, internal_title=None, key=f"k{i}", title=f"T{i}",
                         in_catalog=False, tags=[]) for i in range(3)]
        for got in (b.collection(roms), b.collection([])):
            texts = [l.split(": ", 1)[-1] for l in got]
            self.assertTrue(texts)
            self.assertEqual(len(texts), len(set(texts)), got)


if __name__ == "__main__":
    unittest.main()


class SyncProgressOutput(unittest.TestCase):
    """`sync --go`: the carriage-return percentage line never runs into core's "copy ..." log lines."""

    def run_sync(self, go):
        from unittest import mock
        import argparse

        def fake_sync(cfg, cid, keys, roms, mount, dry_run=True, log=print, progress=None, **kw):
            progress = progress or (lambda i: None)
            for n, title in enumerate(("Alpha", "Beta")):
                log(f"{'' if not dry_run else '[dry-run] '}copy {title} -> games/{title}.iso")
                for done in range(1, 4):
                    progress({"phase": "copy", "title": title, "all_done": n * 3 + done, "all_total": 6})
            progress({"phase": "done", "all_done": 6, "all_total": 6})
            return {"copied": ["a", "b"], "removed": [], "kept": [], "warnings": [], "errors": []}

        class Brain:
            def __init__(self, *a, **k): pass
            def card_quips(self, keys): return []
            def event(self, *a, **k): return []

        clock = iter(range(0, 1000))
        a = argparse.Namespace(mount=None, go=go, verify=False, force=False)
        out = io.StringIO()
        with mock.patch.object(cli.core, "sync_card", fake_sync), \
                mock.patch.object(cli.core, "current_plan", lambda st: {"1": ["k"]}), \
                mock.patch.object(cli.core, "resolve_mount", lambda cfg, cid, m=None: "/card"), \
                mock.patch.object(cli, "library_missing", lambda cfg: ""), \
                mock.patch.object(cli.pets, "PetBrain", Brain), \
                mock.patch.object(cli.plugins, "fire", lambda *a, **k: None), \
                mock.patch.object(cli.time, "time", lambda: float(next(clock))), \
                contextlib.redirect_stdout(out):
            self.assertTrue(cli._sync_one({}, {}, None, [], "1", a))
        return out.getvalue()

    def test_each_copy_line_starts_clean_and_once(self):
        text = self.run_sync(go=True)
        self.assertIn("%", text)                                           # the percentage is still shown
        shown = [seg.split("\r")[-1] for seg in text.split("\n")]          # what a terminal leaves on each line
        for title in ("Alpha", "Beta"):
            self.assertEqual(shown.count(f"copy {title} -> games/{title}.iso"), 1, text)
        self.assertFalse([l for l in shown if "%" in l and "copy" in l], text)
        self.assertTrue(any(l.startswith("Card 1 @ /card: DONE") for l in shown), text)

    def test_dry_run_output_is_unchanged(self):
        text = self.run_sync(go=False)
        self.assertNotIn("\r", text)
        self.assertEqual(text.splitlines()[:3], ["[dry-run] copy Alpha -> games/Alpha.iso",
                                                 "[dry-run] copy Beta -> games/Beta.iso", ""])
