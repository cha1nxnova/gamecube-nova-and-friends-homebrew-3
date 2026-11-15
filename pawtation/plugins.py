"""Plugins: drop a .py file into <app>/plugins/ and it is loaded at start-up. No packaging, no installs.

A plugin defines `register(api)`. Everything a mod is likely to want is on `api`:

    def register(api):
        api.progress_parser("G8ME", lambda raw: "..." )          # read real progress out of a .gci
        api.chat(r"\bboop\b", lambda brain, m, ctx: "Mochi: Boop received.")
        api.score(lambda rom, state, now: 5 if "cozy" in rom.tags else 0)   # nudge the rotation planner
        api.on("synced", lambda card_id, report, **kw: print("card", card_id, "done"))
        api.command("hello", lambda args: print("hi"), help="say hi")       # python -m pawtation hello

Events fired by the app: "planned" (plan=, roms=), "synced" (card_id=, report=, mount=).
A plugin that raises is reported and skipped; it can never stop the app or a sync.
Plugins are plain Python with your user's full permissions: only install ones you wrote or have read.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from . import core, pets, saves

PLUGIN_DIR = core.ROOT / "plugins"
EVENTS: dict[str, list] = {}
COMMANDS: dict[str, tuple] = {}       # name -> (fn(list_of_args), help)
LOADED: list[str] = []
FAILED: set = set()
ERRORS: list[str] = []


class Api:
    core, pets, saves = core, pets, saves

    def progress_parser(self, code4: str, fn):
        saves.PROGRESS_PARSERS[code4] = fn

    def chat(self, pattern: str, fn):
        pets.CHAT_HOOKS.append((re.compile(pattern, re.I), fn))

    def score(self, fn):
        core.SCORE_HOOKS.append(fn)

    def on(self, event: str, fn):
        EVENTS.setdefault(event, []).append(fn)

    def command(self, name: str, fn, help: str = ""):
        COMMANDS[name] = (fn, help)

    def pet_content(self, bucket: str, pet: str, lines):
        """Add lines to a per-pet bucket of data/pets.json at runtime (the file itself is not modified)."""
        pets.PETS.setdefault(bucket, {}).setdefault(pet, []).extend(lines)


def load_plugins(folder: Path | None = None) -> list[str]:
    """Import every *.py in the plugins folder (alphabetical; names starting with _ are skipped). Idempotent."""
    folder = Path(folder or PLUGIN_DIR)
    if not folder.is_dir():
        return LOADED
    api = Api()
    for path in sorted(folder.glob("*.py")):
        name = path.stem
        if name.startswith("_") or name in LOADED or name in FAILED:
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"pawtation_plugin_{name}", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if callable(getattr(mod, "register", None)):
                mod.register(api)
            LOADED.append(name)
        except KeyboardInterrupt:
            raise
        except BaseException as e:               # includes a plugin calling sys.exit(): report it, carry on
            FAILED.add(name)
            ERRORS.append(f"{path.name}: {type(e).__name__}: {e}")
            print(f"[pawtation] plugin {path.name} failed to load: {e}", file=sys.stderr)
    return LOADED


def fire(event: str, **kw) -> None:
    for fn in EVENTS.get(event, []):
        try:
            fn(**kw)
        except Exception as e:
            print(f"[pawtation] plugin hook for '{event}' failed: {e}", file=sys.stderr)
