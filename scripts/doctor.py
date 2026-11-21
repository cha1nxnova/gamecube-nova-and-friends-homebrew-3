#!/usr/bin/env python3
"""Environment check for Pawtation. Run: python scripts/doctor.py   (or: python -m pawtation doctor)

Read-only: it never writes config, state, cards or assets. It reports whether After Dark is locked or unlocked and
nothing more about it (no dates, no pack names)."""
import json, os, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ok = lambda m: print(f"  [ok]   {m}")
warn = lambda m: print(f"  [warn] {m}")
bad = lambda m: print(f"  [FAIL] {m}")


def section(title):
    print(title)


section("Pawtation doctor")
(ok if sys.version_info >= (3, 9) else bad)(f"Python {sys.version.split()[0]} (need 3.9+)")
try:
    import tkinter; ok("tkinter available (GUI will work)")
except ImportError:
    warn("tkinter missing: GUI unavailable. Linux: sudo apt install python3-tk. CLI still works.")

section("Library and cards")
try:
    from pawtation import core
    cfg = core.load_config(); ok("core imports")
    lib = cfg.get("library_dir")
    roms = []
    if lib and Path(lib).is_dir():
        roms = core.scan_library(cfg); ok(f"library: {len(roms)} games found in {lib}")
        keys = {r.key for r in roms}
        miss = [k for k in cfg["pinned"] if k not in keys]
        (warn if miss else ok)("pinned missing from library: " + ", ".join(miss) if miss else "all pinned games present")
    else:
        warn("library_dir not set/found. Run: python -m pawtation init --library PATH")
    for cid, c in cfg["cards"].items():
        m = c.get("mount")
        if m and not Path(m).is_dir(): warn(f"card {cid} mount not found: {m}")
    for r in [r for r in roms if not r.launchable]:
        warn(f"not copied to cards: {r.title}: {r.why_not_launchable}")
    found = core.find_cards()
    ok("plugged-in Pawtation cards: " + (", ".join(f"{k} at {v}" for k, v in found.items()) or "none right now"))
    from pawtation import plugins
    plugins.load_plugins()
    ok("plugins: " + (", ".join(plugins.LOADED) or "none"))
    for e in plugins.ERRORS: bad("plugin " + e)
    cat = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["games"]
    ok(f"catalog: {len(cat)} titles")
except Exception as e:
    bad(f"core failed: {type(e).__name__}: {e}")

section("Cast, art and theme")
try:
    from pawtation import cast, sprites
    chars = cast.characters()
    ok(f"cast: {len(chars)} characters ({cast.names(cast.regulars())} and {len(cast.cameos())} cameos)")
    if sprites.load_manifest():
        drawn = [c for c in chars if sprites.has(c)]
        missing = [c for c in chars if not sprites.has(c)]
        broken = [c for c in drawn if not sprites.frames(c, "idle", min(sprites.available_sizes() or [96]))]
        ok(f"sprites: {len(drawn)}/{len(chars)} characters, sizes {sprites.available_sizes()}")
        if missing: warn("no sprites (text fallback): " + ", ".join(missing))
        if broken: warn("sprite manifest lists files that are missing: " + ", ".join(broken))
    else:
        warn("assets/sprites/manifest.json missing or unreadable: the app shows text instead of sprites")
    renders = sprites._renders(None) if hasattr(sprites, "_renders") else {}
    have = [n for n in renders if sprites.render(n)]
    (ok if have else warn)(f"low-poly renders: {len(have)}/{len(renders)} present" if renders else "low-poly renders: none")
except Exception as e:
    bad(f"cast/sprites failed: {type(e).__name__}: {e}")
try:
    from pawtation import theme
    json.loads(theme.THEME_PATH.read_text(encoding="utf-8"))          # valid JSON at all? (load() repairs quietly)
    problems = theme.check()
    (warn if problems else ok)(f"theme file: {len(problems)} problem(s)" if problems
                               else f"theme file valid ({', '.join(theme.names())}; contrast checks pass)")
    for p in problems[:8]: warn("  " + p)
except (OSError, ValueError) as e:
    warn(f"data/theme.json unreadable ({type(e).__name__}); the app uses its built-in copy")
except Exception as e:
    bad(f"theme failed: {type(e).__name__}: {e}")
try:
    from pawtation import afterdark
    ok("After Dark: " + ("unlocked" if afterdark.is_unlocked(core.load_state()) else "locked"))
except Exception as e:
    bad(f"After Dark state unreadable: {type(e).__name__}")

section("Tools")
for tool, why in [("xdelta3", "optional: applying .xdelta mod patches"), ("git", "version control")]:
    (ok if shutil.which(tool) else warn)(f"{tool}: {'found' if shutil.which(tool) else 'not found'} ({why})")
try:
    boot = core.load_config().get("boot_card", {})
    boot = boot if isinstance(boot, dict) else {}
    dol = str(boot.get("swiss_dol") or "")
    if not dol:
        warn("Swiss: no boot file set yet; get the official release and see docs/GAMECUBE_GUIDE.md")
    elif not Path(dol).is_file():
        warn(f"Swiss: boot_card.swiss_dol is set but the file is not there: {dol}")
    elif Path(dol).name.lower() != "autoexec.dol":
        warn(f"Swiss: boot file is {Path(dol).name}; the guide uses the release's ActionReplay/AUTOEXEC.DOL")
    else:
        ok(f"Swiss: boot file set ({dol})")
except Exception as e:
    warn(f"Swiss: could not check the boot file setting ({type(e).__name__})")
print("Done. New here? README.md. Changing things? HANDOFF.md and docs/MODDING.md.")
