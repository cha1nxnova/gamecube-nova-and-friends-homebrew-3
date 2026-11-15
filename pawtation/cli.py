"""Command line: python -m pawtation <command>. The GUI calls the same functions."""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from . import core, patching, pets, plugins, saves
from .core import Catalog


def build_ctx():
    plugins.load_plugins()
    cfg, state, cat = core.load_config(), core.load_state(), Catalog()
    return cfg, state, cat, core.scan_library(cfg, cat)


def cmd_init(a):
    if core.CONFIG_PATH.exists() and not a.force:
        print("config.json already exists (use --force to overwrite)."); return
    cfg = json.loads(json.dumps(core.DEFAULT_CONFIG)); cfg["library_dir"] = a.library or ""
    core.save_json(core.CONFIG_PATH, cfg); print(f"Wrote {core.CONFIG_PATH}")


def cmd_scan(a):
    cfg, state, cat, roms = build_ctx()
    if not roms:
        print("No discs found. Set library_dir in config.json (or run `init --library PATH`)."); return
    for r in sorted(roms, key=lambda r: r.title.lower()):
        flag = "" if r.in_catalog else "  (not in catalog)"
        discs = f"  [{len(r.discs)} discs]" if len(r.discs) > 1 else ""
        mods = f"  [+{len(core.mod_files(cfg, r.key))} mod files]" if core.mod_files(cfg, r.key) else ""
        if not r.launchable:
            flag += "  (compressed: convert to .iso with Dolphin/NKit before it can go on a card)"
        print(f"{r.code6 or '------'}  {core.fmt_gb(r.size):>8}  {r.title}{discs}{mods}{flag}")
    print(f"\n{len(roms)} games, {core.fmt_gb(sum(r.size for r in roms))} total")
    missing = [k for k in cfg["pinned"] if k not in {r.key for r in roms}]
    if missing:
        print("Pinned but not found in library:", ", ".join(cat.by_key[k]["title"] if k in cat.by_key else k for k in missing))


def cmd_status(a):
    cfg, state, cat, roms = build_ctx()
    due, rem = core.rotation_due(cfg, state)
    print("Rotation due NOW!" if due else f"Next rotation in {core.fmt_remaining(rem)}")
    titles = {r.key: r.title for r in roms}
    for cid, keys in core.current_plan(state).items():
        label = cfg["cards"].get(cid, {}).get("label", "?")
        print(f"Card {cid} ({label}): " + ", ".join(titles.get(k) or cat.by_key.get(k, {}).get("title", k) for k in keys))
    if due:
        for line in pets.PetBrain(state, cat).due_nag(): print(line)


def cmd_plan(a):
    cfg, state, cat, roms = build_ctx()
    if not cfg["cards"]:
        print("No cards configured. Add some under \"cards\" in config.json."); return
    plan = core.plan_rotation(cfg, state, roms)
    by = {r.key: r for r in roms}
    for cid, keys in plan.items():
        used = sum(by[k].size for k in keys)
        print(f"\nCard {cid} ({cfg['cards'][cid].get('label', cid)}) {core.fmt_gb(used)} / {cfg['cards'][cid].get('capacity_gb', '?')} GB")
        for k in keys:
            print(f"  - {by[k].title}" + ("  (pinned)" if k in cfg["pinned"] else ""))
    left = core.unplaced(plan, roms)
    if left:
        print(f"\nResting this season ({len(left)}): " + ", ".join(r.title for r in left[:12]) + ("..." if len(left) > 12 else ""))
    if a.commit:
        core.commit_plan(state, plan); core.save_state(state); plugins.fire("planned", plan=plan, roms=roms)
        print("\nPlan committed; timer reset.")
    else:
        print("\n(preview only; add --commit to save it and restart the timer)")


def _sync_one(cfg, state, cat, roms, cid, a) -> bool:
    plan = core.current_plan(state)
    keys = plan.get(cid)
    if keys is None:
        print(f"Card {cid} is not in the current plan."); return False
    mount = core.resolve_mount(cfg, cid, a.mount)
    if not mount:
        print(f"Card {cid}: not found. Give --mount PATH (or set cards.{cid}.mount in config.json; "
              "cards synced once are found automatically when plugged in)."); return False
    last = [0.0]

    def progress(i):
        if i.get("phase") == "copy" and i.get("all_total") and time.time() - last[0] > 0.5:
            last[0] = time.time()
            pct = 100 * i["all_done"] // i["all_total"]
            print(f"\r  {pct:3d}%  {i['title'][:50]:<50}", end="", flush=True)
        elif i.get("phase") == "done" and last[0]:
            print("\r" + " " * 60 + "\r", end="")

    quips = pets.PetBrain(state, cat).card_quips(keys)
    try:
        rep = core.sync_card(cfg, cid, keys, roms, mount, dry_run=not a.go, progress=progress if a.go else None,
                             verify=True if a.verify else None, quips=quips, force=a.force)
    except KeyboardInterrupt:
        print("\nStopped. Files already finished stay on the card; re-run to continue."); return False
    except OSError as e:
        print(f"Card {cid}: {e}"); return False
    print(f"\nCard {cid} @ {mount}: {'DONE' if a.go else 'DRY RUN (add --go to copy)'}: "
          f"{len(rep['copied'])} copy, {len(rep['removed'])} remove, {len(rep['kept'])} keep")
    for w in rep["warnings"]: print("WARNING:", w)
    for e in rep["errors"]: print("ERROR:", e)
    if a.go and not rep["errors"]:
        plugins.fire("synced", card_id=cid, report=rep, mount=mount)
        for line in pets.PetBrain(state, cat).duo("synced", card=cid): print(line)
    return not rep["errors"]


def cmd_sync(a):
    cfg, state, cat, roms = build_ctx()
    if not state["history"]:
        print("No committed plan yet. Run: plan --commit"); return 1
    if a.card == "all":
        if a.mount:
            print("--mount cannot be combined with 'all' (each card has its own path)."); return 1
        found = [c for c in core.card_ids(cfg) if core.resolve_mount(cfg, c)]
        if not found:
            print("No plugged-in cards recognised. Sync each card once with --mount so it gets labelled."); return 1
        return 0 if all([_sync_one(cfg, state, cat, roms, c, a) for c in found]) else 1
    return 0 if _sync_one(cfg, state, cat, roms, a.card, a) else 1


def cmd_cards(a):
    cfg, state, cat, roms = build_ctx()
    found = core.find_cards()
    plan = core.current_plan(state)
    for cid in core.card_ids(cfg):
        c = cfg["cards"][cid]
        where = c.get("mount") or found.get(cid)
        print(f"Card {cid}  {c.get('label', ''):<14} {c.get('capacity_gb', '?')} GB  "
              f"{'mounted at ' + where if where and os.path.isdir(where) else 'not plugged in'}  "
              f"({len(plan.get(cid, []))} games planned)")
        if where and os.path.isdir(where):
            on = core.card_contents(where)["titles"]
            for k, t in sorted(on.items(), key=lambda kv: kv[1].lower()):
                print(f"    {'  ' if k in plan.get(cid, []) else '- '}{t}" + ("" if k in plan.get(cid, []) else "   (rotates out on next sync)"))
    extra = {k: v for k, v in found.items() if k not in cfg["cards"]}
    for cid, where in extra.items():
        print(f"Card {cid}  (not in config.json)  mounted at {where}")


def cmd_boot_card(a):
    cfg = core.load_config()
    mount = a.mount or cfg["boot_card"].get("mount")
    dol = a.swiss_dol or cfg["boot_card"].get("swiss_dol")
    if not mount or not dol:
        print("Need --mount PATH and --swiss-dol PATH (a swiss .dol from an official release; or set boot_card in config.json)."); return 1
    try:
        rep = core.prepare_boot_card(mount, dol, dry_run=not a.go)
    except OSError as e:
        print("ERROR:", e); return 1
    for w in rep["warnings"]: print("WARNING:", w)
    print("DONE" if a.go else "DRY RUN (add --go to copy)")


def cmd_mods(a):
    cfg, state, cat, roms = build_ctx()
    base = core.mods_dir(cfg)
    if a.new:
        hits = pets.PetBrain(state, cat).find_games(a.new, roms) or [g for g in [cat.match(None, a.new)] if g]
        if len(hits) != 1:
            print("Which game? " + (", ".join(getattr(h, "title", None) or h["title"] for h in hits[:8]) or "no match in library or catalog")); return 1
        key = getattr(hits[0], "key", None) or hits[0]["key"]
        (base / key / "card").mkdir(parents=True, exist_ok=True)
        note = base / key / "README.md"
        if not note.exists():
            note.write_text(f"# Mods for {key}\n\nEverything under `card/` is copied to the same path on the SD card whenever this "
                            "game rotates onto it,\nand removed again when it rotates off. See docs/MODDING.md.\n", encoding="utf-8")
        print(f"Created {base / key / 'card'}"); return 0
    print(f"Mods folder: {base}")
    any_ = False
    if base.is_dir():
        for d in sorted(p for p in base.iterdir() if p.is_dir()):
            files = core.mod_files(cfg, d.name)
            if files:
                any_ = True
                known = d.name in cat.by_key or d.name in {r.key for r in roms}
                print(f"\n{cat.by_key.get(d.name, {}).get('title', d.name)}  [{d.name}]" + ("" if known else "   (!) no game with this key"))
                for rel in files: print(f"   -> {rel}")
    if not any_:
        print("No mod files yet. Start one with: python -m pawtation mods --new \"paper mario\"")
    if plugins.LOADED or plugins.ERRORS:
        print("\nPlugins loaded: " + (", ".join(plugins.LOADED) or "none"))
        for e in plugins.ERRORS: print("Plugin error:", e)


def cmd_patch(a):
    out = a.out or str(Path(a.source).with_name(Path(a.source).stem + " [patched]" + Path(a.source).suffix))
    try:
        rep = patching.apply_patch(a.source, a.patch, out)
    except (patching.PatchError, OSError) as e:
        print("ERROR:", e); return 1
    h = core.discimage.read_header(rep["out"])
    print(f"Wrote {rep['out']} ({core.fmt_gb(rep['size'])}, {rep['format']}). Your original is untouched."
          + (f" Disc ID: {h['code6']}." if h else ""))


def cmd_saves(a):
    cfg, state, cat, roms = build_ctx()
    print(pets.PetBrain(state, cat).save_report(saves.scan_saves(cfg.get("saves_dir", ""))))


def cmd_wrapped(a):
    cfg, state, cat, roms = build_ctx()
    print(pets.PetBrain(state, cat).wrapped(roms))


def cmd_doctor(a):
    import runpy
    runpy.run_path(str(core.ROOT / "scripts" / "doctor.py"), run_name="__main__")


def cmd_rate(a):
    cfg, state, cat, roms = build_ctx()
    brain = pets.PetBrain(state, cat)
    print(brain.rate(a.title, a.stars, roms)); core.save_state(state)


def cmd_chat(a):
    cfg, state, cat, roms = build_ctx()
    brain = pets.PetBrain(state, cat)
    sv = saves.scan_saves(cfg.get("saves_dir", ""))
    print(pets.PETS.get("title", "")); print(brain.art("mochi")); print(brain.art("biscuit"))
    for l in brain.duo("greeting"): print(l)
    if core.rotation_due(cfg, state)[0] and roms:
        for l in brain.due_nag(): print(l)
    print("(type 'quit' to leave, 'help' for ideas)")
    try:
        while True:
            try: t = input("> ")
            except EOFError: break
            if t.strip().lower() in ("q", "quit", "exit", "bye"): break
            if t.strip():
                print(brain.reply(t, roms, sv))
    except KeyboardInterrupt:
        print()
    core.save_state(state)


def _gui(a):
    try:
        from . import gui
    except ImportError as e:
        print(f"The desktop app needs tkinter ({e}). Linux: sudo apt install python3-tk. The CLI works without it."); return 1
    plugins.load_plugins()
    return gui.run()


def main(argv=None):
    p = argparse.ArgumentParser(prog="pawtation", description="Rotate GameCube games across GC2SD cards, with Mochi & Biscuit.")
    sub = p.add_subparsers(dest="cmd", required=True)
    def add(name, fn, help):
        sp = sub.add_parser(name, help=help, description=help); sp.set_defaults(f=fn); return sp
    s = add("init", cmd_init, "write a starter config.json"); s.add_argument("--library"); s.add_argument("--force", action="store_true")
    add("scan", cmd_scan, "list the disc images found in your library")
    add("status", cmd_status, "timer + what is on each card this season")
    s = add("plan", cmd_plan, "preview (or --commit) a new rotation"); s.add_argument("--commit", action="store_true")
    s = add("sync", cmd_sync, "make an SD card match the plan (dry run unless --go)")
    s.add_argument("card", help="card id, or 'all' for every plugged-in card Pawtation recognises")
    s.add_argument("--mount"); s.add_argument("--go", action="store_true")
    s.add_argument("--verify", action="store_true", help="re-read each copy and compare checksums")
    s.add_argument("--force", action="store_true", help="use a card even if it is labelled as a different card")
    add("cards", cmd_cards, "which cards are plugged in and what is on them")
    s = add("rate", cmd_rate, "rate a game 1-5"); s.add_argument("title"); s.add_argument("stars", type=int, choices=range(1, 6))
    s = add("boot-card", cmd_boot_card, "copy your Swiss .dol to a boot card as autoexec.dol")
    s.add_argument("--mount"); s.add_argument("--swiss-dol"); s.add_argument("--go", action="store_true")
    s = add("mods", cmd_mods, "list per-game mod files and plugins"); s.add_argument("--new", metavar="GAME", help="create a mods folder for a game")
    s = add("patch", cmd_patch, "apply a .bps/.ips/.xdelta patch to a COPY of your own image")
    s.add_argument("source"); s.add_argument("patch"); s.add_argument("--out")
    add("saves", cmd_saves, "what your exported .gci saves say about themselves")
    add("wrapped", cmd_wrapped, "season recap")
    add("doctor", cmd_doctor, "check this computer is ready")
    add("chat", cmd_chat, "talk to Mochi and Biscuit")
    add("gui", _gui, "desktop app (needs tkinter)")
    plugins.load_plugins()
    for name, (fn, help) in plugins.COMMANDS.items():
        if name not in sub.choices:
            sp = add(name, (lambda fn: lambda a: fn(a.args))(fn), help or "plugin command"); sp.add_argument("args", nargs="*")
    a = p.parse_args(argv)
    return a.f(a) or 0
