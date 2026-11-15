"""Desktop app (tkinter, ships with Python on Windows/macOS; Linux: `sudo apt install python3-tk`).

Thin layer over core/pets/saves: no rotation or sync logic lives here.
Add a feature = add a function in core, then a button here.

Design notes for future agents
* Every modal dialog goes through a small overridable method on App (ask_yes_no, ask_directory,
  ask_file, show_info, show_error, choose_card) so tests can monkeypatch them.
* Sync runs in a daemon worker thread. The worker only puts tuples on `self.events` (a queue.Queue);
  the UI thread drains it from `_poll_events` (after(100)). tkinter is never touched from the worker.
"""
from __future__ import annotations

import queue
import threading
import time
import traceback

try:                                    # tkinter may be missing (Linux without python3-tk): the CLI must still import us
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, messagebox, ttk
    HAVE_TK = True
except Exception:                       # pragma: no cover - depends on the machine
    tk = tkfont = filedialog = messagebox = ttk = None
    HAVE_TK = False

from . import core, pets, plugins, saves
from .core import Catalog

PAW = "(=^.^=) "                        # title prefix when a rotation is due (ASCII: safe on every Tk build)
SHORTCUTS = [("Ctrl+R", "Rescan the library"), ("Ctrl+P", "Plan a new rotation"), ("Ctrl+S", "Sync a card"),
             ("Ctrl+F", "Focus the game search box"), ("Enter", "Send chat message"),
             ("Double-click a game", "Ask the pets about it"), ("F1", "This help")]

# "GameCube indigo": deep indigo + lilac + warm cream (dark), pale lilac paper (light).
THEMES = {
    "dark": dict(bg="#1d1646", panel="#2a2160", field="#140f36", fg="#f7ecd3", dim="#b9aee0", accent="#b8a4f5",
                 accent_fg="#1d1646", button="#3b2f84", button_hover="#4d3fa3", border="#4a3d99",
                 mochi="#cdb9ff", biscuit="#ffc27a", you="#f7ecd3", ok="#8fe0a8", warn="#ffd479", bar="#ffcf7d"),
    "light": dict(bg="#eee9ff", panel="#fbf9ff", field="#ffffff", fg="#241a5c", dim="#5d5391", accent="#5b3fc4",
                  accent_fg="#ffffff", button="#d9cffa", button_hover="#c7b9f5", border="#b5a8e8",
                  mochi="#5b3fc4", biscuit="#a24b00", you="#241a5c", ok="#17703a", warn="#8a5a00", bar="#7a4cd8"),
}


def fmt_bytes(n: float) -> str:
    n = float(n)
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    return f"{n / 1024 ** 2:.0f} MB"


def fmt_eta(sec: float) -> str:
    sec = int(max(0, sec))
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


def card_sort_key(cid: str):
    """Numeric card ids sort numerically (2 before 10); non-numeric ids after, no card last."""
    if cid in ("", "-", None):
        return (2, 0, "")
    return (0, int(cid), "") if str(cid).isdigit() else (1, 0, str(cid))


if HAVE_TK:
    class Flow(ttk.Frame):
        """Frame that wraps its children onto extra rows when it is too narrow (buttons never run off-screen)."""

        def __init__(self, master, **kw):
            super().__init__(master, **kw)
            self.items = []
            self._cols = 0
            self.bind("<Configure>", lambda e: self.relayout(e.width))

        def add(self, widget, padx=2, pady=2):
            self.items.append((widget, padx, pady))
            self.relayout(self.winfo_width() or 400, force=True)
            return widget

        def relayout(self, width, force=False):
            if not self.items:
                return
            widths = [w.winfo_reqwidth() + 2 * px for w, px, _ in self.items]
            cols, used = 0, 0
            for wd in widths:
                if cols and used + wd > width:
                    break
                used += wd
                cols += 1
            cols = max(1, cols)
            if cols == self._cols and not force:
                return
            self._cols = cols
            for i, (w, px, py) in enumerate(self.items):
                w.grid(row=i // cols, column=i % cols, padx=px, pady=py, sticky="w")


    class App(tk.Tk):
        COLUMNS = [("game", "Game", 210, "w"), ("card", "Card", 46, "center"), ("size", "Size", 68, "e"),
                   ("discs", "Discs", 46, "center"), ("rating", "Rating", 68, "w"), ("tags", "Tags", 110, "w")]

        def __init__(self):
            super().__init__()
            self.withdraw()
            self.cfg, self.state, self.cat = core.load_config(), core.load_state(), Catalog()
            self.roms, self.saves = [], {}
            self.brain = pets.PetBrain(self.state, self.cat)
            self.theme_name = self.cfg.get("gui_theme") if self.cfg.get("gui_theme") in THEMES else "dark"
            self.base_title = "Pawtation - " + pets.PETS.get("title", "")
            self.minsize(900, 600)
            self.geometry("980x640")
            # sync / worker state
            self.events: "queue.Queue" = queue.Queue()
            self.cancel_event = threading.Event()
            self.worker = None
            self.syncing = False
            self.sync_info = {}
            self._sync_started = 0.0
            self.last_report = None
            # misc state
            self.sort_col, self.sort_rev = "card", False
            self._after = {}
            self._closing = False
            self._nagged = False
            self._flash_left = 0
            self._due_marked = False
            self.last_error = None
            self.title(self.base_title)
            self._style = ttk.Style(self)
            try:
                self._style.theme_use("clam")
            except tk.TclError:
                pass
            self._fonts()
            self._build()
            self.apply_theme(self.theme_name, save=False)
            self._bind_keys()
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            self.refresh(announce=True)
            self._update_bars()
            self._tick()
            self._schedule("poll", 100, self._poll_events)
            self.deiconify()
            self.update_idletasks()
            try:
                self.body.sashpos(0, int(self.winfo_width() * 0.58))
            except tk.TclError:
                pass
            for line in self.brain.duo("greeting"):
                self.say(line)

        # ---------- dialogs (override / monkeypatch in tests) ----------
        def ask_yes_no(self, title, text):
            return messagebox.askyesno(title, text, parent=self)

        def show_info(self, title, text):
            messagebox.showinfo(title, text, parent=self)

        def show_error(self, title, text):
            messagebox.showerror(title, text, parent=self)

        def ask_directory(self, title, initial=""):
            return filedialog.askdirectory(title=title, parent=self, initialdir=initial or None, mustexist=True) or None

        def ask_file(self, title, filetypes=(("All files", "*.*"),), initial=""):
            return filedialog.askopenfilename(title=title, parent=self, filetypes=filetypes,
                                              initialdir=initial or None) or None

        def choose_card(self, options, prompt="Which card is inserted?"):
            """Return one of `options` or None if cancelled / window closed."""
            win = tk.Toplevel(self)
            win.title(prompt)
            win.transient(self)
            win.configure(bg=THEMES[self.theme_name]["bg"])
            ttk.Label(win, text=prompt, padding=(12, 10, 12, 2)).pack(anchor="w")
            var = tk.StringVar(value=options[0])
            for cid in options:
                label = self.cfg["cards"].get(cid, {}).get("label", f"Card {cid}")
                ttk.Radiobutton(win, text=f"Card {cid}  ({label})", variable=var, value=cid).pack(anchor="w", padx=16, pady=2)
            out = {"v": None}

            def ok(_e=None):
                out["v"] = var.get()
                win.destroy()
            row = ttk.Frame(win, padding=10)
            row.pack(fill="x")
            ttk.Button(row, text="OK", command=ok).pack(side="right", padx=2)
            ttk.Button(row, text="Cancel", command=win.destroy).pack(side="right", padx=2)
            win.bind("<Return>", ok)
            win.bind("<Escape>", lambda _e: win.destroy())
            win.protocol("WM_DELETE_WINDOW", win.destroy)         # closing the window = cancel (returns None)
            win.grab_set()
            self.wait_window(win)
            return out["v"]

        def report_callback_exception(self, exc, val, tb):
            text = "".join(traceback.format_exception(exc, val, tb))
            self.last_error = text
            try:
                self.show_error("Pawtation hit a snag", f"{val}\n\n{text[-1500:]}")
            except Exception:
                print(text)

        # ---------- scheduling helpers ----------
        def _schedule(self, name, ms, fn):
            if self._closing:
                return
            old = self._after.pop(name, None)
            if old:
                try:
                    self.after_cancel(old)
                except tk.TclError:
                    pass
            self._after[name] = self.after(ms, fn)

        def destroy(self):
            self._closing = True
            for aid in self._after.values():
                try:
                    self.after_cancel(aid)
                except Exception:
                    pass
            self._after.clear()
            super().destroy()

        # ---------- layout ----------
        def _fonts(self):
            base = tkfont.nametofont("TkDefaultFont")
            self.f_base = base
            self.f_bold = base.copy(); self.f_bold.configure(weight="bold")
            self.f_big = base.copy(); self.f_big.configure(weight="bold", size=base.cget("size") + 3)
            self.f_mono = tkfont.nametofont("TkFixedFont").copy(); self.f_mono.configure(size=13, weight="bold")

        def _build(self):
            root = ttk.Frame(self, padding=(10, 8, 10, 4)); root.pack(fill="both", expand=True)
            self.root_frame = root
            # header
            head = ttk.Frame(root); head.pack(fill="x")
            ttk.Label(head, text="Pawtation", style="Title.TLabel").pack(side="left")
            self.timer_var = tk.StringVar()
            ttk.Label(head, textvariable=self.timer_var, style="Timer.TLabel").pack(side="right")
            bar = Flow(root); bar.pack(fill="x", pady=(4, 2))
            self.buttons = {}
            for key, text, fn in [("library", "Pick library folder", self.pick_library), ("rescan", "Rescan", self.refresh),
                                  ("plan", "Plan new rotation", self.plan), ("sync", "Sync a card...", self.sync_card),
                                  ("boot", "Boot card...", self.boot_card), ("theme", "Light/Dark", self.toggle_theme),
                                  ("help", "Help (F1)", self.show_help)]:
                self.buttons[key] = bar.add(ttk.Button(bar, text=text, command=fn))
            self.guarded = [self.buttons[k] for k in ("library", "rescan", "plan", "sync", "boot")]

            body = ttk.PanedWindow(root, orient="horizontal"); body.pack(fill="both", expand=True, pady=4)
            left = ttk.Frame(body); body.add(left, weight=3)
            right = ttk.Frame(body, padding=(8, 0, 0, 0)); body.add(right, weight=2)
            self._build_left(left)
            self._build_right(right)
            self.body = body
            self.status = tk.StringVar()
            ttk.Label(root, textvariable=self.status, style="Dim.TLabel").pack(fill="x", pady=(2, 0))

        def _build_left(self, left):
            sf = ttk.Frame(left); sf.pack(fill="x")
            ttk.Label(sf, text="Search:").pack(side="left")
            self.search_var = tk.StringVar()
            self.search_var.trace_add("write", lambda *_: self._populate())
            self.search = ttk.Entry(sf, textvariable=self.search_var); self.search.pack(side="left", fill="x", expand=True, padx=6)
            ttk.Button(sf, text="x", width=2, command=lambda: self.search_var.set("")).pack(side="left")

            self.strip_var = tk.StringVar()
            self.strip = ttk.Label(left, textvariable=self.strip_var, style="Strip.TLabel", justify="left")
            self.strip.pack(fill="x", pady=4)
            self.strip.bind("<Configure>", lambda e: self.strip.configure(wraplength=max(200, e.width - 12)))

            tf = ttk.Frame(left); tf.pack(fill="both", expand=True)
            self.tree = ttk.Treeview(tf, columns=[c[0] for c in self.COLUMNS], show="headings", height=10, selectmode="browse")
            for cid, text, w, anchor in self.COLUMNS:
                self.tree.heading(cid, text=text, command=lambda c=cid: self.sort_by(c))
                self.tree.column(cid, width=w, minwidth=40, anchor=anchor, stretch=(cid in ("game", "tags")))
            sb = ttk.Scrollbar(tf, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.pack(side="left", fill="both", expand=True); sb.pack(side="left", fill="y")
            self.tree.bind("<Double-1>", self.on_game_double)
            self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_pin_button())

            acts = Flow(left); acts.pack(fill="x", pady=(6, 0))
            acts.add(ttk.Label(acts, text="Rate selected:"))
            for n in range(1, 6):
                acts.add(ttk.Button(acts, text=f"{n}★", width=4, command=lambda n=n: self.rate(n)), padx=1)
            self.pin_btn = acts.add(ttk.Button(acts, text="Pin favorite", command=self.toggle_pin), padx=8)

            # sync progress
            pf = ttk.LabelFrame(left, text="Card sync", padding=6); pf.pack(fill="x", pady=(8, 0))
            self.prog_var = tk.DoubleVar(value=0)
            self.prog = ttk.Progressbar(pf, variable=self.prog_var, maximum=100, mode="determinate")
            self.prog.pack(fill="x")
            row = ttk.Frame(pf); row.pack(fill="x", pady=(4, 0))
            self.prog_text = tk.StringVar(value="Idle. Plan a rotation, then sync a card.")
            self.eta_text = tk.StringVar(value="")
            lab = ttk.Frame(row); lab.pack(side="left", fill="x", expand=True)
            self.prog_label = ttk.Label(lab, textvariable=self.prog_text, anchor="w"); self.prog_label.pack(fill="x")
            ttk.Label(lab, textvariable=self.eta_text, style="Dim.TLabel", anchor="w").pack(fill="x")
            self.cancel_btn = ttk.Button(row, text="Cancel", command=self.cancel_sync, state="disabled")
            self.cancel_btn.pack(side="right", padx=(6, 0))
            lab.bind("<Configure>", lambda e: self.prog_label.configure(wraplength=max(150, e.width - 4)))

        def _build_right(self, right):
            arts = ttk.Frame(right, style="Panel.TFrame", padding=6); arts.pack(fill="x")
            self.mochi_art, self.bisc_art = tk.StringVar(), tk.StringVar()
            self.bars = {}
            for pet, var, col in (("mochi", self.mochi_art, 0), ("biscuit", self.bisc_art, 1)):
                cell = ttk.Frame(arts, style="Panel.TFrame"); cell.grid(row=0, column=col, sticky="n", padx=8)
                arts.columnconfigure(col, weight=1)
                ttk.Label(cell, textvariable=var, font=self.f_mono, justify="left", style="Art.TLabel").pack()
                ttk.Label(cell, text=pets.CHARS.get(pet, {}).get("name", pet), style="PetName.TLabel").pack()
                for kind, label, mx in (("affection", "love", 20), ("energy", "energy", 10)):
                    r = ttk.Frame(cell, style="Panel.TFrame"); r.pack(fill="x", pady=1)
                    ttk.Label(r, text=label, width=6, style="Dim.Panel.TLabel").pack(side="left")
                    pb = ttk.Progressbar(r, maximum=mx, length=90, style="Pet.Horizontal.TProgressbar"); pb.pack(side="left")
                    self.bars[(pet, kind)] = pb
            logf = ttk.Frame(right); logf.pack(fill="both", expand=True, pady=6)
            self.log = tk.Text(logf, height=8, width=34, wrap="word", state="disabled", relief="flat", padx=8, pady=6, borderwidth=0)
            lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
            self.log.configure(yscrollcommand=lsb.set)
            self.log.pack(side="left", fill="both", expand=True); lsb.pack(side="left", fill="y")
            acts = Flow(right); acts.pack(fill="x")
            for name, act in pets.PETS.get("activities", {}).items():
                acts.add(ttk.Button(acts, text=act.get("verb", name), command=lambda n=name: self.do_activity(n)), padx=1)
            tools = Flow(right); tools.pack(fill="x")
            for text, fn in [("Joke", self.act_joke), ("Suggest", self.act_suggest), ("Rankings", self.act_rankings),
                             ("Fortune", self.act_fortune), ("Study break", self.act_study), ("Wrapped", self.act_wrapped)]:
                tools.add(ttk.Button(tools, text=text, command=fn), padx=1)
            er = ttk.Frame(right); er.pack(fill="x", pady=(6, 0))
            ttk.Label(er, text="Chat:").pack(side="left")
            self.entry = ttk.Entry(er); self.entry.pack(side="left", fill="x", expand=True, padx=6)
            self.entry.bind("<Return>", self.chat)
            ttk.Button(er, text="Send", command=self.chat).pack(side="left")
            self._art("art")

        def _bind_keys(self):
            for seq, fn in (("<Control-r>", self.refresh), ("<Control-p>", self.plan), ("<Control-s>", self.sync_card),
                            ("<Control-f>", self.focus_search), ("<F1>", self.show_help)):
                self.bind_all(seq, lambda e, fn=fn: (fn(), "break")[1])

        def focus_search(self, _e=None):
            self.search.focus_set()
            self.search.select_range(0, "end")

        def show_help(self, _e=None):
            self.show_info("Pawtation help", "Keyboard shortcuts\n\n" + "\n".join(f"{k:<20}{v}" for k, v in SHORTCUTS))

        # ---------- theme ----------
        def apply_theme(self, name, save=True):
            if name not in THEMES:
                name = "dark"
            self.theme_name = name
            c = THEMES[name]
            s = self._style
            self.configure(bg=c["bg"])
            s.configure(".", background=c["bg"], foreground=c["fg"], fieldbackground=c["field"], bordercolor=c["border"],
                        lightcolor=c["panel"], darkcolor=c["panel"], troughcolor=c["field"], focuscolor=c["accent"],
                        insertcolor=c["fg"])
            s.configure("TFrame", background=c["bg"])
            s.configure("Panel.TFrame", background=c["panel"])
            s.configure("TLabel", background=c["bg"], foreground=c["fg"])
            s.configure("Dim.TLabel", foreground=c["dim"])
            s.configure("Panel.TLabel", background=c["panel"])
            s.configure("Dim.Panel.TLabel", background=c["panel"], foreground=c["dim"])
            s.configure("Title.TLabel", font=self.f_big, foreground=c["accent"])
            s.configure("Timer.TLabel", font=self.f_bold, foreground=c["warn"] if self._due_marked else c["fg"])
            s.configure("Strip.TLabel", background=c["panel"], foreground=c["fg"], padding=(8, 4))
            s.configure("Art.TLabel", background=c["panel"], foreground=c["accent"])
            s.configure("PetName.TLabel", background=c["panel"], foreground=c["fg"], font=self.f_bold)
            s.configure("TLabelframe", background=c["bg"], bordercolor=c["border"])
            s.configure("TLabelframe.Label", background=c["bg"], foreground=c["accent"], font=self.f_bold)
            s.configure("TButton", background=c["button"], foreground=c["fg"], bordercolor=c["border"], padding=(8, 4))
            s.map("TButton", background=[("disabled", c["panel"]), ("pressed", c["accent"]), ("active", c["button_hover"])],
                  foreground=[("disabled", c["dim"]), ("pressed", c["accent_fg"])])
            s.configure("TEntry", fieldbackground=c["field"], foreground=c["fg"], insertcolor=c["fg"])
            s.configure("TRadiobutton", background=c["bg"], foreground=c["fg"], indicatorcolor=c["field"])
            s.map("TRadiobutton", background=[("active", c["bg"])], indicatorcolor=[("selected", c["accent"])])
            s.configure("Treeview", background=c["field"], fieldbackground=c["field"], foreground=c["fg"], rowheight=24,
                        bordercolor=c["border"])
            s.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", c["accent_fg"])])
            s.configure("Treeview.Heading", background=c["button"], foreground=c["fg"], font=self.f_bold, relief="flat", padding=4)
            s.map("Treeview.Heading", background=[("active", c["button_hover"])])
            s.configure("Horizontal.TProgressbar", background=c["accent"], troughcolor=c["field"], bordercolor=c["border"])
            s.configure("Pet.Horizontal.TProgressbar", background=c["bar"], troughcolor=c["field"], bordercolor=c["border"],
                        thickness=8)
            s.configure("TScrollbar", background=c["button"], troughcolor=c["field"], bordercolor=c["border"], arrowcolor=c["fg"])
            s.configure("TPanedwindow", background=c["bg"])
            s.configure("Sash", sashthickness=6)
            self.log.configure(bg=c["field"], fg=c["fg"], insertbackground=c["fg"], selectbackground=c["accent"],
                               selectforeground=c["accent_fg"])
            for tag in ("mochi", "biscuit", "you", "err"):
                self.log.tag_configure(tag, foreground=c.get(tag, c["warn"]) if tag != "err" else c["warn"])
            self.log.tag_configure("you", font=self.f_bold)
            self.tree.tag_configure("pinned", foreground=c["accent"] if name == "dark" else c["accent"])
            if save:
                try:
                    core.update_config(gui_theme=name)
                    self.cfg["gui_theme"] = name
                except OSError as e:
                    self.say(f"(could not save theme: {e})", "err")

        def toggle_theme(self):
            self.apply_theme("light" if self.theme_name == "dark" else "dark")

        # ---------- pet panel ----------
        def _art(self, mood):
            suffix = "art" if mood == "art" else "art_" + mood
            self.mochi_art.set(self.brain.art("mochi", suffix))
            self.bisc_art.set(self.brain.art("biscuit", suffix))

        def say(self, text, tag=None):
            if tag is None:
                low = text.lstrip().lower()
                tag = "mochi" if low.startswith("mochi:") else "biscuit" if low.startswith("biscuit:") else "you" if low.startswith("you:") else None
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n\n", tag or ())
            self.log.see("end")
            self.log.configure(state="disabled")

        def _update_bars(self):
            for (pet, kind), pb in self.bars.items():
                pb["value"] = self.state["pets"].get(pet, {}).get(kind, 0)

        def _save(self):
            core.save_state(self.state)

        def _pet_call(self, name, *args):
            """Call an optional PetBrain feature; returns None if the supervisor's build lacks it."""
            fn = getattr(self.brain, name, None)
            return fn(*args) if callable(fn) else None

        def _say_feature(self, name, *args):
            out = self._pet_call(name, *args)
            if out is None:
                self.say(f"Mochi: I haven't learned '{name}' yet.")
            else:
                self.say("\n".join(out) if isinstance(out, (list, tuple)) else str(out))

        def act_joke(self): self._say_feature("joke")
        def act_suggest(self): self._say_feature("suggest", self.roms)
        def act_rankings(self): self._say_feature("ranking", self.roms)
        def act_fortune(self): self._say_feature("fortune")
        def act_study(self): self._say_feature("study_break")
        def act_wrapped(self): self._say_feature("wrapped", self.roms)

        def do_activity(self, name):
            pet = self.brain.rng.choice(["mochi", "biscuit"])
            self.say(self.brain.activity(pet, name))
            self._save()
            self._update_bars()
            self._art("sleep" if name == "nap" else "happy")
            self._schedule("art", 2500, lambda: self._art("art"))

        def chat(self, _evt=None):
            t = self.entry.get().strip()
            if not t:
                return
            self.entry.delete(0, "end")
            self.say("You: " + t)
            self.say(self.brain.reply(t, self.roms, self.saves))
            self._save()
            self._update_bars()

        # ---------- game list ----------
        def _where(self):
            return {k: cid for cid, keys in core.current_plan(self.state).items() for k in keys}

        def _row(self, r, where):
            stars = self.state["ratings"].get(r.key, 0)
            pinned = r.key in self.cfg["pinned"]
            return dict(game=("♥ " if pinned else "") + r.title, card=where.get(r.key, "-"), size=core.fmt_gb(r.size),
                        discs=len(r.discs), rating="★" * stars,
                        tags=", ".join(r.tags) if r.launchable else "convert to .iso first")

        def _sort_value(self, r, where, col):
            if col == "game": return r.title.lower()
            if col == "card": return card_sort_key(where.get(r.key, "-"))
            if col == "size": return r.size
            if col == "discs": return len(r.discs)
            if col == "rating": return self.state["ratings"].get(r.key, 0)
            return ", ".join(r.tags).lower()

        def sort_by(self, col):
            self.sort_rev = (not self.sort_rev) if col == self.sort_col else False
            self.sort_col = col
            self._populate()

        def _populate(self):
            if not hasattr(self, "tree"):
                return
            sel = self.selected_key()
            where = self._where()
            q = self.search_var.get().strip().lower()
            rows = [r for r in self.roms if not q or q in r.title.lower() or q in r.key or any(q in t.lower() for t in r.tags)]
            rows.sort(key=lambda r: (self._sort_value(r, where, self.sort_col), r.title.lower()), reverse=self.sort_rev)
            self.tree.delete(*self.tree.get_children())
            for r in rows:
                d = self._row(r, where)
                self.tree.insert("", "end", iid=r.key, values=[d[c[0]] for c in self.COLUMNS],
                                 tags=("pinned",) if r.key in self.cfg["pinned"] else ())
            if sel and self.tree.exists(sel):
                self.tree.selection_set(sel)
            for cid, text, *_ in self.COLUMNS:
                arrow = (" ▲" if not self.sort_rev else " ▼") if cid == self.sort_col else ""
                self.tree.heading(cid, text=text + arrow)
            self._sync_pin_button()
            shown = len(rows)
            self.status.set(f"{shown}/{len(self.roms)} games shown | library: {self.cfg.get('library_dir') or '(not set)'}")

        def selected_key(self):
            sel = self.tree.selection() if hasattr(self, "tree") else ()
            return sel[0] if sel else None

        def _rom(self, key):
            return next((r for r in self.roms if r.key == key), None)

        def _sync_pin_button(self):
            key = self.selected_key()
            self.pin_btn.configure(text="Unpin favorite" if key and key in self.cfg["pinned"] else "Pin favorite")

        def _update_strip(self):
            by = {r.key: r for r in self.roms}
            plan = core.current_plan(self.state)
            parts = []
            for cid in sorted(set(self.cfg["cards"]) | set(plan), key=card_sort_key):
                card = self.cfg["cards"].get(cid)
                used = sum(by[k].size for k in plan.get(cid, []) if k in by)
                cap = f"{float(card.get('capacity_gb', 0)):g} GB" if card else "?"
                label = card.get("label", f"Card {cid}") if card else f"Card {cid}"
                parts.append(f"{label}: {fmt_bytes(used)} / {cap}")
            self.strip_var.set("  |  ".join(parts) if parts else "No cards configured (see config.json -> cards).")

        def refresh(self, announce=False):
            self.cfg = core.load_config()
            self.roms = core.scan_library(self.cfg, self.cat)
            self.saves = saves.scan_saves(self.cfg.get("saves_dir", ""))
            self._update_strip()
            self._populate()
            if announce or not self.roms:
                bucket = "empty" if not self.roms else "few" if len(self.roms) < 12 else "many"
                lines = pets.PETS.get("state_of_collection", {}).get(bucket) or ["..."]
                if bucket != "empty" or announce:
                    self.say(self.brain._line("mochi", self.brain.rng.choice(lines)))
            return self.roms

        def on_game_double(self, _evt=None):
            key = self.selected_key()
            if not key:
                return
            rom = self._rom(key)
            title = rom.title if rom else key
            pet = self.brain.rng.choice(["mochi", "biscuit"])
            q = self.brain.game_quip(pet, key) or self.brain.game_quip(pets.other(pet), key)
            self.say(q or self.brain._line(pet, f"{title}. I have no strong feelings yet. Rate it and I might."))

        def rate(self, n, key=None):
            key = key or self.selected_key()
            if not key:
                self.show_info("Rate", "Select a game first.")
                return
            rom = self._rom(key)
            title = rom.title if rom else self.cat.by_key.get(key, {}).get("title", key)
            self.state["ratings"][key] = n
            self._save()
            self._populate()
            self.say(self.brain.say("mochi", "ranked", game=title))
            q = self.brain.game_quip("biscuit", key)
            self.say(q or self.brain._line("biscuit", f"{title}: {n} stars! I wrote it down with my paw."))

        def toggle_pin(self, key=None):
            key = key or self.selected_key()
            if not key:
                self.show_info("Pin", "Select a game first.")
                return
            pinned = list(self.cfg["pinned"])
            if key in pinned:
                pinned.remove(key)
            else:
                pinned.append(key)
            self.cfg = core.update_config(pinned=pinned)
            self._populate()

        # ---------- library / plan ----------
        def pick_library(self):
            d = self.ask_directory("Folder with your legally acquired GameCube disc images", self.cfg.get("library_dir", ""))
            if d:
                self.cfg = core.update_config(library_dir=d)
                self.refresh(announce=True)

        def plan(self):
            if self.syncing:
                return
            if not self.roms:
                self.show_info("Plan", "No games found yet. Pick your library folder first.")
                return
            if not self.cfg["cards"]:
                self.show_info("Plan", "No cards are configured (config.json -> cards).")
                return
            plan = core.plan_rotation(self.cfg, self.state, self.roms)
            by = {r.key: r for r in self.roms}
            lines = []
            for cid in sorted(plan, key=card_sort_key):
                titles = ", ".join(by[k].title for k in plan[cid]) or "(empty)"
                lines.append(f"Card {cid}: {titles}")
            left = core.unplaced(plan, self.roms)
            text = "\n".join(lines)
            if left:
                text += f"\n\nNot placed this season ({len(left)}): " + ", ".join(r.title for r in left[:8]) + ("..." if len(left) > 8 else "")
            if self.ask_yes_no("New rotation", text + "\n\nCommit this plan and restart the timer?"):
                core.commit_plan(self.state, plan)
                plugins.fire("planned", plan=plan, roms=self.roms)
                self._save()
                self.refresh()
                self._tick(reschedule=False)
                for line in self.brain.duo("rotated"):
                    self.say(line)

        # ---------- countdown ----------
        def _tick(self, reschedule=True):
            if self._closing:
                return
            due, rem = core.rotation_due(self.cfg, self.state)
            if due:
                self.timer_var.set("Rotation due NOW")
                self._mark_due()
            else:
                self.timer_var.set("Next rotation in " + core.fmt_remaining(rem))
                self._unmark_due()
            if reschedule:
                self._schedule("tick", 30000, self._tick)

        def _mark_due(self):
            if self._due_marked:
                return
            self._due_marked = True
            self._style.configure("Timer.TLabel", foreground=THEMES[self.theme_name]["warn"])
            self._flash_left = 10
            self._flash()
            if not self._nagged:                       # nag ONCE per app session
                self._nagged = True
                lines = self._pet_call("due_nag") or self.brain.duo("rotation_due", days=0)
                for line in lines:
                    self.say(line)

        def _unmark_due(self):
            if not self._due_marked:
                return
            self._due_marked = False
            self._flash_left = 0
            self.title(self.base_title)
            self._style.configure("Timer.TLabel", foreground=THEMES[self.theme_name]["fg"])

        def _flash(self):
            if self._closing or not self._due_marked:
                return
            if self._flash_left > 0:
                self._flash_left -= 1
                self.title(self.base_title if self.title().startswith(PAW) else PAW + self.base_title)
                self._schedule("flash", 1000, self._flash)
            else:
                self.title(PAW + self.base_title)       # stays marked

        # ---------- card picking ----------
        def pick_mount(self, cid, title=None):
            """Auto-detected mount first, then config, then a directory chooser. Offers to remember a chosen folder."""
            auto = core.find_cards().get(str(cid))
            if auto:
                return auto
            configured = self.cfg["cards"].get(str(cid), {}).get("mount")
            if configured and __import__("os").path.isdir(configured):
                return configured
            d = self.ask_directory(title or f"Select the mounted SD card for card {cid}", configured or "")
            if d and d != configured and self.ask_yes_no("Remember?", f"Remember {d} as the mount for card {cid}?"):
                cards = {k: dict(v) for k, v in self.cfg["cards"].items()}
                cards.setdefault(str(cid), {"label": f"Card {cid}", "capacity_gb": 8})["mount"] = d
                self.cfg = core.update_config(cards=cards)
            return d

        # ---------- sync ----------
        def _set_busy(self, busy):
            self.syncing = busy
            for b in self.guarded:
                b.configure(state="disabled" if busy else "normal")
            self.cancel_btn.configure(state="normal" if busy else "disabled")

        def sync_card(self):
            if self.syncing:
                return
            plan = core.current_plan(self.state)
            if not plan:
                self.show_info("Sync", "Plan a rotation first.")
                return
            cid = self.choose_card(sorted(plan, key=card_sort_key))
            if not cid:
                return
            mount = self.pick_mount(cid)
            if not mount:
                return
            keys = plan[cid]
            force = False
            try:
                rep = core.sync_card(self.cfg, cid, keys, self.roms, mount, dry_run=True, log=lambda *_: None)
                if any("labelled as card" in e for e in rep["errors"]):
                    if not self.ask_yes_no("Different card", "\n".join(rep["errors"]) + "\n\nUse this card anyway (re-purpose it)?"):
                        return
                    force = True
                    rep = core.sync_card(self.cfg, cid, keys, self.roms, mount, dry_run=True, log=lambda *_: None, force=True)
            except Exception as e:
                self.show_error("Sync", f"Could not check the card: {e}")
                return
            if rep["errors"] and not (rep["copied"] or rep["removed"]):
                self.show_error("Sync", "Cannot sync:\n" + "\n".join(rep["errors"]))
                return
            text = (f"Card {cid} at {mount}\nCopy {len(rep['copied'])}, remove {len(rep['removed'])}, keep {len(rep['kept'])}.")
            if rep["errors"]:                                   # per-game problems: those games are skipped, the rest can go
                text += "\n\nWill be skipped:\n- " + "\n- ".join(rep["errors"])
            if rep["warnings"]:
                text += "\n\nWarnings:\n- " + "\n- ".join(rep["warnings"])
            if not self.ask_yes_no("Confirm sync", text + "\n\nProceed?"):
                return
            self.start_sync(cid, keys, mount, force)

        def start_sync(self, cid, keys, mount, force=False):
            self.cancel_event.clear()
            self._sync_mount = mount
            self.sync_info = {}
            self._sync_started = time.time()
            self._set_busy(True)
            self.prog_var.set(0)
            self.prog_text.set("Starting...")
            self.eta_text.set("")
            quips = self._pet_call("card_quips", keys) if self.cfg.get("export_quips", True) else None
            cfg, roms = dict(self.cfg), list(self.roms)
            events = self.events

            def work():                                         # NEVER touch tkinter in here
                try:
                    rep = core.sync_card(cfg, cid, keys, roms, mount, dry_run=False, log=lambda *_: None,
                                         progress=lambda info: events.put(("progress", dict(info))),
                                         cancel=self.cancel_event.is_set, quips=quips, force=force)
                    events.put(("done", cid, rep))
                except BaseException as e:                      # reported via the queue
                    events.put(("error", cid, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))

            self.worker = threading.Thread(target=work, name="pawtation-sync", daemon=True)
            self.worker.start()

        def cancel_sync(self):
            if self.syncing:
                self.cancel_event.set()
                self.prog_text.set("Cancelling after the current chunk...")

        def _poll_events(self):
            if self._closing:
                return
            try:
                while True:
                    ev = self.events.get_nowait()
                    if ev[0] == "progress":
                        self._on_progress(ev[1])
                    elif ev[0] == "done":
                        self._on_done(ev[1], ev[2])
                    elif ev[0] == "error":
                        self._on_worker_error(ev[1], ev[2])
            except queue.Empty:
                pass
            self._schedule("poll", 100, self._poll_events)

        def _on_progress(self, info):
            self.sync_info = info
            phase = info.get("phase")
            total, done = info.get("all_total") or 0, info.get("all_done") or 0
            self.prog_var.set(100.0 * done / total if total else 0)
            if phase == "copy":
                self.prog_text.set(f"Copying {info.get('title', '')} — {fmt_bytes(info.get('file_done', 0))} / {fmt_bytes(info.get('file_total', 0))}")
            elif phase == "verify":
                self.prog_text.set(f"Verifying {info.get('title', '')}")
            elif phase == "remove":
                self.prog_text.set(f"Removing {info.get('title') or info.get('rel', '')}")
            elapsed = max(0.001, time.time() - self._sync_started)
            if done and total and phase in ("copy", "verify"):
                speed = done / elapsed
                self.eta_text.set(f"{fmt_bytes(done)} / {fmt_bytes(total)}   {speed / 1024 ** 2:.1f} MB/s   ETA {fmt_eta((total - done) / speed)}")

        def _on_done(self, cid, rep):
            self.last_report = rep
            self._set_busy(False)
            self.worker = None
            self.prog_var.set(100 if not rep.get("cancelled") else self.prog_var.get())
            for e in rep["errors"]:
                self.say("ERROR: " + e, "err")
            for w in rep["warnings"]:
                self.say("Warning: " + w, "err")
            if rep.get("cancelled"):
                self.prog_text.set("Cancelled. Finished files stay on the card; run sync again to resume.")
                self.say(f"Mochi: Card {cid} sync cancelled. I did not mind. Much.")
            else:
                self.prog_text.set(f"Done: card {cid} copied {len(rep['copied'])}, removed {len(rep['removed'])}, kept {len(rep['kept'])}.")
                self.eta_text.set("")
                if not rep["errors"]:
                    self.say(self.brain.say("mochi", "synced", card=cid))
                    self.say(self.brain.say("biscuit", "synced", card=cid))
                    plugins.fire("synced", card_id=cid, report=rep, mount=self._sync_mount)
            self.refresh()

        def _on_worker_error(self, cid, text):
            self._set_busy(False)
            self.worker = None
            self.prog_text.set("Sync failed.")
            self.last_error = text
            self.show_error("Sync failed", text[:1500])

        def on_close(self):
            if self.syncing:
                if not self.ask_yes_no("Sync in progress", "A card is still being written. Cancel the copy and quit?"):
                    return
                self.cancel_event.set()
                w = self.worker
                self.prog_text.set("Waiting for the copy to stop...")
                while w and w.is_alive():                      # let the worker finish its chunk and tidy .part files
                    self.update()
                    time.sleep(0.05)
            self.destroy()

        # ---------- boot card ----------
        def boot_card(self):
            if self.syncing:
                return
            boot = self.cfg.get("boot_card", {})
            mount = self.ask_directory("Select the BOOT card (small standard SD, <= 2 GB)", boot.get("mount", ""))
            if not mount:
                return
            dol = self.ask_file("Select the Swiss .dol (official release)", (("DOL files", "*.dol"), ("All files", "*.*")),
                                boot.get("swiss_dol", ""))
            if not dol:
                return
            try:
                rep = core.prepare_boot_card(mount, dol, dry_run=True, log=lambda *_: None)
            except Exception as e:
                self.show_error("Boot card", str(e))
                return
            text = f"Copy {dol}\n  -> {rep['target']}"
            if rep["warnings"]:
                text += "\n\nWarnings:\n- " + "\n- ".join(rep["warnings"])
            if not self.ask_yes_no("Boot card", text + "\n\nProceed?"):
                return
            try:
                rep = core.prepare_boot_card(mount, dol, dry_run=False, log=lambda *_: None)
            except Exception as e:
                self.show_error("Boot card", str(e))
                return
            self.show_info("Boot card", f"Wrote {rep['target']}")
            if (mount, dol) != (boot.get("mount"), boot.get("swiss_dol")) and self.ask_yes_no("Remember?", "Remember these boot card paths?"):
                self.cfg = core.update_config(boot_card={**boot, "mount": mount, "swiss_dol": dol})


def run():
    if not HAVE_TK:
        print("Pawtation's window needs tkinter, which this Python does not have.\n"
              "  Windows/macOS: reinstall Python from python.org (tcl/tk is included).\n"
              "  Debian/Ubuntu: sudo apt install python3-tk\n"
              "You can still use the command line: python -m pawtation --help")
        return 1
    try:
        app = App()
    except tk.TclError as e:
        print(f"Could not open a window ({e}). Is a display available? Try the CLI: python -m pawtation --help")
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    run()
