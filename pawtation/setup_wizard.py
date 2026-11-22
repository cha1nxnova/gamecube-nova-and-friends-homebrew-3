"""'Set up my GameCube': one window that walks through everything between a fresh download of Pawtation and
playing on the console (docs/GAMECUBE_GUIDE.md, made clickable).

Steps: your games -> your game cards -> get Swiss -> the boot card -> first rotation -> on the GameCube.
Each step only calls what the rest of the app already does (core, swissget, and the App's own plan / sync flows),
so the wizard adds no new way to touch a card. Like gui.py, every colour and font comes from the App's theme.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import webbrowser
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from . import core, paths, swissget

STEPS = [("library", "Your games"), ("cards", "Your game cards"), ("swiss", "Get Swiss"),
         ("boot", "The boot card"), ("plan", "First rotation"), ("console", "On the GameCube")]
SIZES = ("2", "4", "8", "16", "32", "64", "128", "256", "512")
GUIDE = "docs/GAMECUBE_GUIDE.md"


def guide_path() -> Path:
    """The guide next to Pawtation.exe (it ships in the download, so it stays after the app closes and opens from
    a normal folder), else the copy bundled inside the app."""
    beside = paths.ROOT / Path(GUIDE).name
    return beside if beside.is_file() else paths.BUNDLE / GUIDE


def boot_candidates() -> list[dict]:
    """Drives that could be the boot card, best first: removable and small. Never the system drive (core rules)."""
    out = []
    for vol in core.candidate_volumes():
        info = core.volume_info(str(vol))
        if not info.get("total"):
            continue
        if info.get("removable") is False:                     # Windows says it is a fixed disk: not an SD card
            continue
        label = core.load_manifest(vol).get("card_id")
        too_big = info["total"] > core.BOOT_MAX_BYTES
        fs = info.get("fs")
        if label is not None:
            note, good = f"this is game card {label}, not the boot card", False
        elif too_big:
            note, good = "too big for a boot card (2 GB or smaller)", False
        elif fs and fs.lower() not in core.FAT_NAMES:
            note, good = f"formatted as {fs}; format it as FAT first", False
        else:
            note, good = "looks right", True
        has = (vol / "autoexec.dol").is_file()
        out.append({"path": str(vol), "total": info["total"], "fs": fs, "note": note + (" (already has Swiss)" if has else ""),
                    "good": good})
    out.sort(key=lambda d: (not d["good"], d["total"]))
    return out


class SetupWizard:
    """A non-modal window owned by the App. `app` provides theme (c, fonts, space, button), dialogs
    (ask_yes_no, show_info, show_error, ask_directory, ask_file) and the plan / sync / refresh flows."""

    c = property(lambda self: self.app.c)                     # read live: a theme switch (F2) recolours the wizard
    fonts = property(lambda self: self.app.fonts)

    def __init__(self, app):
        self.app = app
        self.closed = False
        self.step = 0
        self.events: "queue.Queue" = queue.Queue()
        self.cancel = threading.Event()
        self.worker = None
        self.boot_choice = None
        self.win = tk.Toplevel(app)
        self.win.title("Set up your GameCube")
        self.win.configure(bg=self.c["bg"])
        self.win.transient(app)
        self.win.minsize(940, 540)                              # steady size: steps don't make the window jump
        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.side = side = tk.Frame(self.win, bg=self.c["surface_alt"])
        side.pack(side="left", fill="y")
        self.title_lab = tk.Label(side, text="GameCube setup", bg=self.c["surface_alt"], fg=self.c["ink"],
                                  font=self.fonts["title"], padx=16, pady=12, anchor="w")
        self.title_lab.pack(fill="x")
        self.step_labels = []
        for i, (_k, title) in enumerate(STEPS):
            lab = tk.Label(side, text=f"{i + 1}. {title}", bg=self.c["surface_alt"], fg=self.c["ink_muted"],
                           font=self.fonts["body"], padx=16, pady=6, anchor="w", cursor="hand2")
            lab.pack(fill="x")
            lab.bind("<Button-1>", lambda _e, n=i: self.go(n))
            self.step_labels.append(lab)
        self.main = main = tk.Frame(self.win, bg=self.c["bg"])
        main.pack(side="left", fill="both", expand=True)
        self.body = tk.Frame(main, bg=self.c["surface"], highlightthickness=2, highlightbackground=self.c["line"])
        self.body.pack(fill="both", expand=True, padx=16, pady=(16, 8))
        self.foot = foot = tk.Frame(main, bg=self.c["bg"])
        foot.pack(fill="x", padx=16, pady=(0, 16))
        self.back_btn = app.button(foot, "Back", lambda: self.go(self.step - 1), "secondary")
        self.back_btn.pack(side="left")
        self.next_btn = app.button(foot, "Next", self.next, "primary")
        self.next_btn.pack(side="right")
        self.go(0)
        self.win.update_idletasks()
        x = app.winfo_rootx() + max(0, (app.winfo_width() - self.win.winfo_reqwidth()) // 2)
        y = app.winfo_rooty() + max(0, (app.winfo_height() - self.win.winfo_reqheight()) // 4)
        self.win.geometry(f"+{x}+{y}")

    # ---------- layout helpers ----------
    def heading(self, text):
        tk.Label(self.body, text=text, bg=self.c["surface"], fg=self.c["ink"], font=self.fonts["title"], anchor="w",
                 padx=16, pady=12).pack(fill="x")

    def para(self, text, muted=False):
        lab = tk.Label(self.body, text=text, bg=self.c["surface"], fg=self.c["ink_muted" if muted else "ink"],
                       font=self.fonts["small" if muted else "body"], justify="left", wraplength=520, anchor="w", padx=16)
        lab.pack(fill="x", pady=(0, 8))
        return lab

    def status(self, text, kind="ok"):
        fg = {"ok": "success", "warn": "danger", "info": "ink_muted"}[kind]
        mark = {"ok": "✓ ", "warn": "⚠ ", "info": ""}[kind]
        lab = tk.Label(self.body, text=mark + text, bg=self.c["surface"], fg=self.c[fg], font=self.fonts["body_strong"],
                       justify="left", wraplength=520, anchor="w", padx=16)
        lab.pack(fill="x", pady=(0, 8))
        return lab

    def row(self):
        f = tk.Frame(self.body, bg=self.c["surface"])
        f.pack(fill="x", padx=16, pady=(4, 8))
        return f

    def btn(self, parent, text, fn, variant="secondary"):
        b = self.app.button(parent, text, fn, variant, on="surface")
        b.pack(side="left", padx=(0, 8))
        return b

    def retheme(self):
        """Called by App.apply_theme: recolour the frame and redraw the current step in the new palette."""
        if not self.alive():
            return
        c = self.c
        for w, role in ((self.win, "bg"), (self.side, "surface_alt"), (self.main, "bg"), (self.foot, "bg")):
            w.configure(bg=c[role])
        self.title_lab.configure(bg=c["surface_alt"], fg=c["ink"])
        self.body.configure(bg=c["surface"], highlightbackground=c["line"])
        if not self.busy():
            self.go(self.step)

    def alive(self):
        try:
            return not self.closed and bool(self.win.winfo_exists())
        except tk.TclError:                                     # the whole App is gone
            return False

    def copying(self):
        """True (and says so) while a card is being copied: the wizard never writes to a card or changes the plan
        meanwhile, just like the main window."""
        if self.app.syncing:
            self.app.show_info("A card is being copied", "Wait for it to finish (or press Cancel in the main window).")
            return True
        return False

    # ---------- navigation ----------
    def go(self, n):
        if not self.alive() or self.busy():                     # e.g. closed while one of its dialogs was open
            return
        n = max(0, min(len(STEPS) - 1, n))
        self.step = n
        for w in self.body.winfo_children():
            w.destroy()
        self.app._themed[:] = [w for w in self.app._themed                 # forget buttons of the previous step
                               if not (isinstance(w, tk.Widget) and not w.winfo_exists())]
        for i, lab in enumerate(self.step_labels):
            here = i == n
            lab.configure(bg=self.c["primary_soft" if here else "surface_alt"], fg=self.c["ink" if here else "ink_muted"],
                          font=self.fonts["body_strong" if here else "body"])
        getattr(self, "step_" + STEPS[n][0])()
        self.back_btn.configure(state="normal" if n else "disabled")
        self.next_btn.configure(text="Finish" if n == len(STEPS) - 1 else "Next")

    def next(self):
        if not self.alive() or self.busy():
            return
        leave = getattr(self, "leave_" + STEPS[self.step][0], None)
        if leave is not None and leave() is False:
            return
        if self.step == len(STEPS) - 1:
            self.finish()
        else:
            self.go(self.step + 1)

    def busy(self):
        return self.worker is not None and self.worker.is_alive()

    def close(self):
        self.closed = True
        self.cancel.set()                                       # a download stops at its next chunk; nothing is left
        self.app._cancel("setup-poll")
        self.win.destroy()

    def finish(self):
        self.closed = True
        self.app.cfg = core.update_config(setup_done=True)
        self.app._cancel("setup-poll")
        self.win.destroy()
        self.app.say("GameCube setup done. Have fun! Swap cards with Swiss running, never with the power off.")

    # ---------- 1. your games ----------
    def step_library(self):
        self.heading("Where are your games?")
        self.para("Pick the folder (or drive) that holds your GameCube disc images: .iso files, or .rvz/.gcz/.ciso ones "
                  "to convert later. Pawtation only reads this folder; it never changes your games.")
        lib = self.app.cfg.get("library_dir")
        roms = self.app.roms
        if lib and os.path.isdir(lib):
            ok = [r for r in roms if r.launchable]
            self.status(f"{lib}: {len(roms)} games found, {len(ok)} ready for cards.", "ok" if ok else "warn")
            if len(ok) < len(roms):
                self.para(f"{len(roms) - len(ok)} can't go on a card yet (compressed, not a GameCube image, or a disc "
                          "missing); the game list says why.", muted=True)
        else:
            self.status("No games folder chosen yet." if not lib else f"Folder not found: {lib} (drive unplugged?)", "warn")
        r = self.row()
        self.btn(r, "Choose folder…", self.pick_library, "primary")

    def pick_library(self):
        if self.copying():
            return
        d = self.app.ask_directory("Folder with your GameCube disc images", self.app.cfg.get("library_dir") or "")
        if d:
            self.app.cfg = core.update_config(library_dir=d)
            self.app.refresh(announce=True)
            self.go(self.step)

    # ---------- 2. your game cards ----------
    def step_cards(self):
        self.heading("Your game cards")
        self.para("How many SD cards will hold games, and what size is printed on each? (Don't count the small boot "
                  "card.) Format game cards as FAT32 or exFAT on the computer first.")
        cards = {k: v for k, v in self.app.cfg["cards"].items() if isinstance(v, dict)}
        ids = [k for k in core.card_ids(self.app.cfg) if k in cards and str(k).isdigit()]
        r = self.row()
        tk.Label(r, text="Number of game cards", bg=self.c["surface"], fg=self.c["ink"],
                 font=self.fonts["body"]).pack(side="left", padx=(0, 8))
        self.count = tk.StringVar(self.win, value=str(len(ids) or 1))
        spin = ttk.Spinbox(r, from_=1, to=12, width=4, textvariable=self.count, command=self._redraw_sizes,
                           font=self.fonts["body"])
        spin.pack(side="left")
        spin.bind("<KeyRelease>", lambda _e: self._redraw_sizes())
        self.sizes_box = tk.Frame(self.body, bg=self.c["surface"])
        self.sizes_box.pack(fill="x", padx=16)
        self.size_vars = {k: tk.StringVar(self.win, value=f"{float(cards[k].get('capacity_gb', 8) or 8):g}") for k in ids}
        self._redraw_sizes()

    def _count(self):
        try:
            return max(1, min(12, int(self.count.get())))
        except (TypeError, ValueError):
            return 1

    def _redraw_sizes(self):
        for w in self.sizes_box.winfo_children():
            w.destroy()
        for i in range(1, self._count() + 1):
            k = str(i)
            self.size_vars.setdefault(k, tk.StringVar(self.win, value="32"))
            f = tk.Frame(self.sizes_box, bg=self.c["surface"])
            f.pack(fill="x", pady=2)
            tk.Label(f, text=f"Card {k}", width=8, anchor="w", bg=self.c["surface"], fg=self.c["ink"],
                     font=self.fonts["body"]).pack(side="left")
            ttk.Combobox(f, textvariable=self.size_vars[k], values=SIZES, width=6,
                         font=self.fonts["body"]).pack(side="left")
            tk.Label(f, text="GB", bg=self.c["surface"], fg=self.c["ink_muted"],
                     font=self.fonts["body"]).pack(side="left", padx=4)

    def leave_cards(self):
        old = {k: dict(v) for k, v in self.app.cfg["cards"].items() if isinstance(v, dict)}
        new = {}
        for i in range(1, self._count() + 1):
            k = str(i)
            try:
                gb = float(self.size_vars[k].get().strip().lower().replace("gb", "").strip())
            except (ValueError, KeyError):
                self.app.show_error("Card size", f"Card {k}: type the size printed on the card, e.g. 32.")
                return False
            if not 0 < gb <= 2048:
                self.app.show_error("Card size", f"Card {k}: {gb:g} GB is not a size an SD card comes in.")
                return False
            card = old.get(k, {"label": f"Card {k}", "mount": ""})
            card["capacity_gb"] = gb
            new[k] = card
        if new != old and self.copying():
            return False
        dropped = sorted(set(old) - set(new), key=lambda x: (len(x), x))
        if dropped and not self.app.ask_yes_no("Fewer cards", "Stop using card " + ", ".join(dropped) + "? Games already "
                                               "on it stay there; Pawtation just stops planning for it."):
            return False
        self.app.cfg = core.update_config(cards=new)
        self.app.refresh(announce=False)
        return True

    # ---------- 3. get Swiss ----------
    def step_swiss(self):
        self.heading("Get Swiss")
        self.para("Swiss is the free program that lets the GameCube start games from an SD card. Pawtation can "
                  "download the newest official release for you from its GitHub page and keep only the file the "
                  "Action Replay needs. Swiss itself is used exactly as released.")
        dol = swissget.boot_file(self.app.cfg)              # chosen, or already downloaded (no need to go online)
        if dol and dol != self.app.cfg["boot_card"].get("swiss_dol"):
            boot = self.app.cfg["boot_card"]                # e.g. the Pawtation folder was moved: remember the new place
            self.app.cfg = core.update_config(boot_card={**boot, "swiss_dol": dol})
        if dol:
            self.status(f"Ready: {dol}")
            self.para("Download again to check for a newer release.", muted=True)
        else:
            self.status("Not downloaded yet.", "info")
        r = self.row()
        self.dl_btn = self.btn(r, "Download Swiss", self.download, "primary")
        self.btn(r, "I have the file…", self.use_file)
        self.btn(r, "I have the unpacked folder…", self.use_folder, "ghost")
        self.swiss_msg = self.status("", "info")
        self.para(f"Releases page: {swissget.RELEASES_PAGE}. This is the only thing in Pawtation that goes online.",
                  muted=True)

    def _remember(self, rec):
        boot = self.app.cfg["boot_card"]
        self.app.cfg = core.update_config(boot_card={**boot, "swiss_dol": rec["files"][swissget.AUTOEXEC]})

    def download(self):
        if self.busy():
            return
        self.cancel.clear()
        self.dl_btn.configure(state="disabled")
        self.swiss_msg.configure(text="Asking GitHub for the newest release…", fg=self.c["ink_muted"])
        events, cancel = self.events, self.cancel

        def work():                                             # never touches tkinter
            try:
                rec = swissget.get_latest(progress=lambda d, t: events.put(("progress", d, t)), cancel=cancel.is_set)
                events.put(("done", rec))
            except swissget.SwissError as e:
                events.put(("error", str(e)))
            except Exception as e:                              # anything else: say it plainly, never crash the app
                events.put(("error", f"{type(e).__name__}: {e}"))

        self.worker = threading.Thread(target=work, name="pawtation-swiss", daemon=True)
        self.worker.start()
        self.app._schedule("setup-poll", 100, self._poll)       # the App's timer: cancelled cleanly when it closes

    def _poll(self):
        try:
            if not self.win.winfo_exists():
                return
        except tk.TclError:
            return
        try:
            while True:
                ev = self.events.get_nowait()
                if ev[0] == "progress":
                    _k, done, total = ev
                    pct = f" {100 * done // total}%" if total else ""
                    self.swiss_msg.configure(text=f"Downloading Swiss…{pct}")
                elif ev[0] == "done":
                    self.worker = None
                    if ev[1] is None:
                        self.swiss_msg.configure(text="Stopped.")
                    else:
                        self._remember(ev[1])
                        self.go(self.step)
                    return
                elif ev[0] == "error":
                    self.worker = None
                    self.dl_btn.configure(state="normal")
                    self.swiss_msg.configure(text="⚠ " + ev[1], fg=self.c["danger"])
                    return
        except queue.Empty:
            pass
        self.app._schedule("setup-poll", 100, self._poll)

    def use_file(self):
        f = self.app.ask_file("Swiss release (.tar.xz) or ActionReplay/AUTOEXEC.DOL",
                              (("Swiss release or DOL", "*.tar.xz *.DOL *.dol"), ("All files", "*.*")))
        if f:
            self._use(f)

    def use_folder(self):
        d = self.app.ask_directory("The folder you unpacked the Swiss release into")
        if d:
            self._use(d)

    def _use(self, path):
        try:
            rec = swissget.from_local(path)
        except swissget.SwissError as e:
            self.app.show_error("Swiss", str(e))
            return
        self._remember(rec)
        if rec.get("note"):
            self.app.show_info("Swiss", rec["note"] + ".")
        self.go(self.step)

    def leave_swiss(self):
        if swissget.boot_file(self.app.cfg):
            return True
        return self.app.ask_yes_no("No Swiss yet", "The boot card needs Swiss. Skip this step for now?")

    # ---------- 4. the boot card ----------
    def step_boot(self):
        self.heading("The boot card")
        self.para("Put the small boot card (2 GB or smaller) in the computer. It needs to be formatted as FAT "
                  "(on Windows: right-click the drive in File Explorer → Format → File system FAT). Pawtation puts "
                  "Swiss on it as autoexec.dol and touches nothing else on it.")
        dol = swissget.boot_file(self.app.cfg)
        if not dol:
            self.status("Get Swiss first (step 3).", "warn")
            return
        drives = boot_candidates()
        self.boot_choice = tk.StringVar(self.win, value=next((d["path"] for d in drives if d["good"]), ""))
        if drives:
            for d in drives:
                tk.Radiobutton(self.body, text=f"{d['path']}   {core.fmt_gb(d['total'])}   {d['fs'] or ''}   {d['note']}",
                               variable=self.boot_choice, value=d["path"], bg=self.c["surface"], fg=self.c["ink"],
                               selectcolor=self.c["surface"], activebackground=self.c["primary_soft"],
                               font=self.fonts["body"], anchor="w", highlightthickness=0).pack(fill="x", padx=24)
        else:
            self.status("No SD card found. Put the boot card in and press Look again.", "info")
        self.backup = tk.BooleanVar(self.win, value=False)
        tk.Checkbutton(self.body, text="Also add the backup-route files (SDLOADER.BIN + swiss.dol), for Action Replay "
                       "discs that don't start autoexec.dol", variable=self.backup, bg=self.c["surface"], fg=self.c["ink"],
                       selectcolor=self.c["surface"], activebackground=self.c["surface"], font=self.fonts["small"],
                       anchor="w", wraplength=520, justify="left",
                       highlightthickness=0).pack(fill="x", padx=16, pady=(6, 0))
        r = self.row()
        self.btn(r, "Put Swiss on this card", self.write_boot, "primary")
        self.btn(r, "Look again", lambda: self.go(self.step))
        self.btn(r, "Another folder…", self.pick_boot, "ghost")

    def pick_boot(self):
        if self.copying():
            return
        d = self.app.ask_directory("The boot card (2 GB or smaller)")
        if d:
            self.boot_choice.set(d)
            self.write_boot()

    def write_boot(self):
        if self.copying():
            return
        mount = self.boot_choice.get() if self.boot_choice is not None else ""
        if not mount:
            self.app.show_error("Boot card", "Choose the boot card first.")
            return
        dol = swissget.boot_file(self.app.cfg)
        if not dol:
            self.app.show_error("Boot card", "Get Swiss first (step 3).")
            return
        extras = {}
        if getattr(self, "backup", None) is not None and self.backup.get():
            extras = dict(swissget.companions(Path(dol)))
            if len(extras) < 2:
                self.app.show_error("Boot card", "The backup-route files were not found next to the Swiss file. "
                                    "Use Download Swiss (step 3) to get them.")
                return
        force = False
        try:
            try:
                rep = core.prepare_boot_card(mount, dol, dry_run=True, log=lambda *_: None, extras=extras)
            except core.GameCardError as e:
                if not self.app.ask_yes_no("This is a game card", f"{e}\n\nPut Swiss on it anyway?"):
                    return
                force = True
                rep = core.prepare_boot_card(mount, dol, dry_run=True, log=lambda *_: None, force=True, extras=extras)
            text = f"Put Swiss on {mount} as autoexec.dol?"
            if rep["warnings"]:
                text += "\n\nPlease check:\n- " + "\n- ".join(rep["warnings"])
            if not self.app.ask_yes_no("Boot card", text):
                return
            rep = core.prepare_boot_card(mount, dol, dry_run=False, log=lambda *_: None, force=force, extras=extras)
        except Exception as e:
            self.app.show_error("Boot card", str(e))
            return
        boot = self.app.cfg["boot_card"]
        self.app.cfg = core.update_config(boot_card={**boot, "mount": mount})
        self.app.show_info("Boot card", "Swiss was already on this card." if rep.get("unchanged") else
                           f"Done: {rep['target']}\n\nLabel this card BOOT so it never ends up in the rotation.")
        self.go(self.step + 1)

    # ---------- 5. first rotation ----------
    def step_plan(self):
        self.heading("First rotation")
        self.para("Pawtation picks this season's games (your pinned favourites first) and copies them to your game "
                  "cards, one card at a time. Keep the drive with your games plugged in while copying.")
        plan = core.current_plan(self.app.state)
        if plan:
            by = {r.key: r.title for r in self.app.roms}
            for cid in core.card_ids({"cards": {k: 1 for k in plan}}):
                names = ", ".join(by.get(k, k) for k in plan[cid][:6]) + (" …" if len(plan[cid]) > 6 else "")
                self.para(f"Card {cid}: {names or '(empty)'}")
            self.status("Plan saved. Now put a game card in and press Copy to a card.", "ok")
        else:
            self.status("No plan yet.", "info")
        r = self.row()
        self.btn(r, "Plan this season", self._plan, "primary" if not plan else "secondary")
        self.btn(r, "Copy to a card…", self._sync, "primary" if plan else "secondary")
        self.para("Copying runs in the main window (with a progress bar and Cancel). Repeat it for each game card.",
                  muted=True)

    def _plan(self):
        if self.copying():
            return
        self.app.plan()
        self.go(self.step)

    def _sync(self):
        if self.copying():
            return
        self.app.sync_card()

    # ---------- 6. on the GameCube ----------
    def step_console(self):
        self.heading("On the GameCube")
        for line in ("1. Power off. Real memory card in Slot A; the GC2SD with the BOOT card in Slot B.",
                     "2. Put the Action Replay disc in and power on. Swiss should start by itself.",
                     "3. With Swiss still running, swap the boot card for a game card, then pick the SD device again "
                     "in Swiss. Never power off to swap: the Action Replay can only start Swiss from the boot card.",
                     "4. Open games, choose one, press A. Saves go to the real memory card in Slot A.",
                     "Nothing yet? Try the GC2SD in Slot A, and check the boot card is 2 GB or smaller and FAT. "
                     "Still the Action Replay menu? Go back to step 4 and tick the backup-route box."):
            self.para(line)
        r = self.row()
        self.btn(r, "Open the full guide", self.open_guide)

    def open_guide(self):
        g = guide_path()
        if not g.is_file():
            self.app.show_error("Guide", f"The guide is not in this copy of Pawtation ({GUIDE}).")
            return
        try:
            if sys.platform.startswith("win"):
                try:
                    os.startfile(str(g))                        # the app registered for .md, if any
                except OSError:
                    subprocess.Popen(["notepad.exe", str(g)])   # plain Windows has no .md handler: Notepad reads it
            else:
                webbrowser.open(g.as_uri())
        except Exception as e:
            self.app.show_error("Guide", f"Could not open {g}: {e}")
