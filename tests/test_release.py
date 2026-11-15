"""Release-review regressions (wave 3): scripts/doctor.py, the `cast` table, and collection lines. Temp homes only."""
import contextlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from pawtation import cast, cli, core, pets
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent


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
        home = Path(tempfile.mkdtemp())
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
        for needle in ("sprites:", "low-poly renders:", "theme file", "After Dark: locked", "Swiss build workspace"):
            self.assertIn(needle, out)
        self.assertNotIn("[FAIL]", out)
        out = self.run_doctor({"afterdark": {"unlocked": True, "confirmed_on": "2026-11-15"}})
        self.assertIn("After Dark: unlocked", out)
        self.assertNotIn("2026-11-15", out)


class CliCastTable(unittest.TestCase):
    def test_columns_stay_aligned_with_long_names(self):
        isolate_plugins(self)
        home = Path(tempfile.mkdtemp())
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
        tmp = Path(tempfile.mkdtemp())
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
