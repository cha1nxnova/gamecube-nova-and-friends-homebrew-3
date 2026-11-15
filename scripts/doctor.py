#!/usr/bin/env python3
"""Environment check for Pawtation. Run: python scripts/doctor.py"""
import json, shutil, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
ok = lambda m: print(f"  [ok]   {m}")
warn = lambda m: print(f"  [warn] {m}")
bad = lambda m: print(f"  [FAIL] {m}")

print("Pawtation doctor")
(ok if sys.version_info >= (3, 9) else bad)(f"Python {sys.version.split()[0]} (need 3.9+)")
try:
    import tkinter; ok("tkinter available (GUI will work)")
except ImportError:
    warn("tkinter missing: GUI unavailable. Linux: sudo apt install python3-tk. CLI still works.")
try:
    from pawtation import core
    cfg = core.load_config(); ok("core imports")
    lib = cfg.get("library_dir")
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
    for r in [r for r in roms if not r.launchable] if lib and Path(lib).is_dir() else []:
        warn(f"compressed image, Swiss cannot start it (convert to .iso with Dolphin/NKit): {r.title}")
    found = core.find_cards()
    ok("plugged-in Pawtation cards: " + (", ".join(f"{k} at {v}" for k, v in found.items()) or "none right now"))
    from pawtation import plugins
    plugins.load_plugins()
    ok("plugins: " + (", ".join(plugins.LOADED) or "none"))
    for e in plugins.ERRORS: bad("plugin " + e)
    cat = json.loads((ROOT / "data" / "catalog.json").read_text(encoding="utf-8"))["games"]
    ok(f"catalog: {len(cat)} titles")
except Exception as e:
    bad(f"core failed: {e}")
for tool, why in [("xdelta3", "optional: applying .xdelta mod patches"), ("git", "forking/version control"),
                  ("docker", "optional Swiss build container (Path B only)"), ("powerpc-eabi-gcc", "devkitPPC toolchain (Path B only)")]:
    (ok if shutil.which(tool) else warn)(f"{tool}: {'found' if shutil.which(tool) else 'not found'} ({why})")
print("Done. New here? README.md. Changing things? HANDOFF.md and docs/MODDING.md.")
