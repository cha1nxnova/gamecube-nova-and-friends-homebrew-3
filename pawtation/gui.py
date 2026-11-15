"""Desktop app (tkinter, ships with Python on Windows/macOS; Linux: `sudo apt install python3-tk`).

Thin layer over core / pets / cast / afterdark / saves: no rotation, sync, presence or content logic lives here.
Add a feature = add a function in core (or the brain), then a button here.

Design notes for future agents
* Every colour, font, size and duration comes from pawtation.theme (docs/DESIGN_SYSTEM.md). No hex literals in
  this file: tests/test_gui.py greps for them.
* Every modal dialog goes through a small overridable method on App (ask_yes_no, ask_directory, ask_file,
  show_info, show_error, choose_card, ask_birthdate, ask_afterdark_unlocked) so tests can monkeypatch them.
* Sync runs in a daemon worker thread. The worker only puts tuples on `self.events` (a queue.Queue); the UI
  thread drains it from `_poll_events`. tkinter is never touched from the worker.
* Every after() goes through App._schedule(name, ...) so destroy() can cancel all of them (no "invalid command
  name" noise at exit). Reduced motion (theme.reduce_motion_requested) schedules nothing but the countdown
  (and the sync queue poll while a sync runs).
* Character ids are never hard-coded: chips and meters come from cast.regulars(), sprites from the manifest.
  After Dark content is only ever reached through the brain (which hides it while locked).
* Pill buttons and the chunky progress bar are Canvas-drawn. Set config "gui_plain_widgets": true (or env
  PAWTATION_PLAIN_WIDGETS=1) for the plain ttk fallback; both paths offer the same configure/cget/invoke.
"""
from __future__ import annotations

import math
import os
import queue
import random
import threading
import time
import traceback

try:                                    # tkinter may be missing (Linux without python3-tk): the CLI must still import us
    import tkinter as tk
    import tkinter.font as tkfont
    from tkinter import filedialog, ttk
    HAVE_TK = True
except Exception:                       # pragma: no cover - depends on the machine
    tk = tkfont = filedialog = ttk = None
    HAVE_TK = False

from . import afterdark, cast, core, hidden, pets, plugins, saves, sprites, theme
from .core import Catalog

PAW = "(=^.^=) "                        # title prefix when a rotation is due (ASCII: safe on every Tk build)
SCENE_STEP_MS = 2200                    # one hang-out line about every 2.2 s
PRESENCE_EVERY_S = 60                   # cast.step roughly once a minute
SLEEPY_AFTER_S = 600                    # at night, nothing for 10 minutes -> they doze off
SHORTCUTS = [("Ctrl+R", "Rescan the library"), ("Ctrl+P", "Plan a new rotation"), ("Ctrl+S", "Sync a card"),
             ("Ctrl+F", "Focus the game search box"), ("F1", "This help"), ("F2", "Switch light / dark theme"),
             ("1 to 5", "Rate the selected game"), ("Enter", "Send a chat message"),
             ("Double-click a game", "Ask whoever is home about it"), ("Click a character", "Pet them"),
             ("Click the stage", "Next line of a hang-out")]


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


def split_line(line: str):
    """'Nova: hello' -> ('nova', 'hello'); '(stage direction)' -> (None, text); anything else -> ('', line)."""
    text = str(line).strip()
    if text.startswith("(") and text.endswith(")"):
        return None, text
    head, sep, rest = text.partition(":")
    if sep and 0 < len(head) <= 24:
        cid = cast.resolve(head.strip())
        if cid:
            return cid, rest.strip()
    return "", text


def plain_requested(cfg) -> bool:
    if str(os.environ.get("PAWTATION_PLAIN_WIDGETS", "")).strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(cfg and cfg.get("gui_plain_widgets") is True)


if HAVE_TK:
    def rounded(cv, x0, y0, x1, y1, r, **kw):
        """A rounded rectangle (smoothed polygon) on a Canvas; r >= half the height gives a pill."""
        r = max(0.0, min(float(r), (x1 - x0) / 2.0, (y1 - y0) / 2.0))
        pts = []
        for cx, cy, start in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            for k in range(7):                                  # a quarter circle in 15 degree steps
                a = math.radians(start + k * 15)
                pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
        return cv.create_polygon(pts, **kw)

    class Flow(ttk.Frame):
        """Frame that wraps its children onto extra rows when it is too narrow (buttons never run off-screen)."""

        def __init__(self, master, **kw):
            super().__init__(master, **kw)
            self.items = []
            self._cols = 0
            self.bind("<Configure>", lambda e: self.relayout(e.width))

        def add(self, widget, padx=2, pady=2):
            self.items.append((widget, padx, pady))
            self.relayout(self.winfo_width() if self.winfo_width() > 1 else 400, force=True)
            return widget

        def clear(self):
            for w, _px, _py in self.items:
                w.destroy()
            self.items, self._cols = [], 0

        def relayout(self, width, force=False):
            if not self.items:
                return
            sizes = [(w.winfo_reqwidth() + 2 * px, w.winfo_reqheight() + 2 * py) for w, px, py in self.items]
            x = y = row_h = 0
            place = []
            for wd, ht in sizes:                                # greedy wrap; every row packs left on its own
                if x and x + wd > width:
                    x, y, row_h = 0, y + row_h, 0
                place.append((x, y, ht))
                x += wd
                row_h = max(row_h, ht)
            key = (tuple(place), y + row_h)
            if key == self._cols and not force:
                return
            self._cols = key
            for (w, px, py), (wx, wy, _ht) in zip(self.items, place):
                w.place(x=wx + px, y=wy + py)
            self.configure(height=max(1, y + row_h))

    # ------------------------------------------------------------------------------------------ buttons
    VARIANTS = {   # variant -> (fill, hover, active, border, text, hover text)
        "primary": ("primary", "primary_hover", "primary_active", "line", "primary_ink", "primary_ink"),
        "secondary": ("accent_soft", "accent_hover", "accent_active", "accent", "accent_text", "accent_ink"),
        "ghost": (None, "primary_soft", "surface_alt", None, "primary_text", "primary_text"),
        "danger": ("danger", "danger_hover", "danger_active", "danger", "danger_ink", "danger_ink"),
        "soft": ("primary_soft", "primary_hover", "primary_active", "line", "primary_text", "primary_ink"),
        "outline": ("header", "@header_hover", "keyline", "header_ink", "header_ink", "header_ink"),
        "lit": ("gold", "gold", "gold_soft", "header_ink", "gold_ink", "gold_ink"),
    }

    class PillButton(tk.Canvas):
        """Canvas pill button (design system 3.2): hover / pressed / disabled / focus ring / busy, Enter and Space
        activate it. Same configure(text=, state=, command=) / cget / invoke surface as ttk.Button."""

        def __init__(self, master, app, text, command=None, variant="secondary", on="bg", small=False):
            self.app, self._text, self._cmd = app, text, command
            self.variant, self.on, self.small = variant, on, small
            self._state, self._hover, self._press, self._focus = "normal", False, False, False
            super().__init__(master, highlightthickness=0, bd=0, takefocus=1, cursor="hand2")
            for seq, fn in (("<Enter>", self._enter), ("<Leave>", self._leave), ("<ButtonPress-1>", self._down),
                            ("<ButtonRelease-1>", self._up), ("<FocusIn>", self._focus_in),
                            ("<FocusOut>", self._focus_out), ("<KeyPress-space>", self._key),
                            ("<KeyPress-Return>", self._key)):
                self.bind(seq, fn)
            app._themed.append(self)
            self.retheme()

        # ttk.Button-compatible surface
        def configure(self, cnf=None, **kw):
            if isinstance(cnf, dict):
                kw.update(cnf)
                cnf = None
            if cnf is not None:
                return super().configure(cnf)
            redraw = False
            if "text" in kw:
                self._text, redraw = str(kw.pop("text")), True
            if "command" in kw:
                self._cmd = kw.pop("command")
            if "state" in kw:
                self._state, redraw = str(kw.pop("state")), True
                self.configure_cursor()
            if kw:
                super().configure(**kw)
            if redraw:
                self.retheme()
        config = configure

        def configure_cursor(self):
            super().configure(cursor="hand2" if self._state == "normal" else "")

        def cget(self, key):
            if key == "text":
                return self._text
            if key == "state":
                return self._state
            return super().cget(key)

        def invoke(self):
            if self._state == "normal" and callable(self._cmd):
                return self._cmd()
            return None

        def _enter(self, _e):
            self._hover = True
            self.retheme()

        def _leave(self, _e):
            self._hover = self._press = False
            self.retheme()

        def _down(self, _e):
            if self._state == "normal":
                self._press = True
                self.focus_set()
                self.retheme()

        def _up(self, e):
            was = self._press
            self._press = False
            self.retheme()
            inside = 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height()
            if was and inside:
                self.invoke()

        def _key(self, _e):
            self.invoke()
            return "break"

        def _focus_in(self, _e):
            self._focus = True
            self.retheme()

        def _focus_out(self, _e):
            self._focus = False
            self.retheme()

        def retheme(self):
            app, c = self.app, self.app.c
            font = app.fonts["tag" if self.small else "body_strong"]
            pad = app.space(4 if self.small else 5)             # 12 / 16 px
            h = app.size("control_sm" if self.small else "control")
            ring = app.tok["keyline"]["focus"] + app.tok["keyline"]["focus_gap"]
            w = font.measure(self._text) + 2 * pad
            on = c[self.on]
            fill, hover, active, border, ink, hover_ink = VARIANTS.get(self.variant, VARIANTS["secondary"])
            role = lambda r: on if r is None else theme.mix(c["header"], c["keyline"], 0.3) if r == "@header_hover" else c[r]
            if self._state != "normal":
                f, b, t = c["disabled"], c["line_soft"], c["disabled_ink"]
                if self.variant == "ghost":
                    f = b = on
            elif self._press:
                f, b, t = role(active), role(border or active), c[hover_ink]
            elif self._hover:
                f, b, t = role(hover), role(border or hover), c[hover_ink]
            else:
                f, b, t = role(fill), role(border or fill), c[ink]
            super().configure(width=w + 2 * ring, height=h + 2 * ring, bg=on)
            self.delete("all")
            dy = 1 if self._press else 0
            if self._focus and self._state == "normal":
                ring_col = c["keyline"] if self.on in ("header", "primary") else c["focus"]
                rounded(self, 1, 1, w + 2 * ring - 1, h + 2 * ring - 1, h, fill="", outline=ring_col,
                        width=app.tok["keyline"]["focus"])
            rounded(self, ring, ring + dy, ring + w, ring + h + dy - 1, h, fill=f, outline=b,
                    width=app.tok["keyline"]["control"])
            self.create_text(ring + w / 2, ring + h / 2 + dy, text=self._text, fill=t, font=font)

    class ChunkyBar(tk.Canvas):
        """The 22 px progress bar (design system 3.6) bound to a DoubleVar (0..100); busy = moving stripes."""

        def __init__(self, master, app, variable):
            self.app, self.var, self.busy, self._shift = app, variable, False, 0
            super().__init__(master, height=app.size("progress") + 4, highlightthickness=0, bd=0)
            variable.trace_add("write", lambda *_: self.redraw())
            self.bind("<Configure>", lambda _e: self.redraw())
            app._themed.append(self)

        def retheme(self):
            self.redraw()

        def set_busy(self, busy):
            self.busy = bool(busy)
            self.redraw()
            if self.busy and not self.app.reduced:
                self.app._schedule("stripe", self.app.motion["stripe"] // 4 or 175, self._stripe)

        def _stripe(self):
            if not self.busy:
                return
            self._shift = (self._shift + 6) % 24
            self.redraw()
            self.app._schedule("stripe", max(60, self.app.motion["stripe"] // 4), self._stripe)

        def redraw(self):
            c, app = self.app.c, self.app
            try:
                frac = max(0.0, min(1.0, float(self.var.get()) / 100.0))
            except (tk.TclError, ValueError):
                frac = 0.0
            w, h = max(40, self.winfo_width()), app.size("progress")
            self.configure(bg=c["surface"])
            self.delete("all")
            y0, y1 = 2, 2 + h
            rounded(self, 2, y0, w - 2, y1, h, fill=c["primary_soft"], outline="")
            if self.busy:
                fx = w - 2
                rounded(self, 2, y0, fx, y1, h, fill=c["primary"], outline="")
                for x in range(-h + self._shift, w, 24):
                    x0, x1 = max(2 + h / 2, x), min(fx - h / 2, x + 10)
                    if x1 > x0:
                        self.create_polygon(x0, y1 - 3, x1, y1 - 3, x1 + 6, y0 + 3, x0 + 6, y0 + 3,
                                            fill=c["primary_hover"], outline="")
            elif frac > 0:
                fx = 2 + max(h, (w - 4) * frac)
                rounded(self, 2, y0, fx, y1, h, fill=c["primary"], outline="")
                self.create_text(min(fx - h / 2, w - h / 2 - 2), (y0 + y1) / 2, text="✦", fill=c["keyline"],
                                 font=app.fonts["body_strong"])
            rounded(self, 2, y0, w - 2, y1, h, fill="", outline=c["line"], width=app.tok["keyline"]["control"])

    # ------------------------------------------------------------------------------------------ the stage
    class Stage:
        """The mascot stage (design system 3.7): whoever is home stands on one floor line, drawn from the sticker
        sprites (ASCII art from pets.json when a sprite is missing). Speech bubbles carry a name tag."""

        def __init__(self, app, parent):
            self.app = app
            self.cv = tk.Canvas(parent, highlightthickness=0, bd=0, height=app.size("stage"), width=400)
            self.actors = {}           # cid -> dict(x, tx, kind, img, items, anim, frame, next_at, override, until, ...)
            self.images = {}           # png path -> PhotoImage (references must be kept)
            self.frame_cache = {}      # (cid, anim, size) -> [PhotoImage]
            self.size = app.sprite_px("stage")
            self.queue = []            # bubbles waiting: (cid, text)
            self.speaker = None
            self.bubble_at = 0.0
            self.cv.bind("<Configure>", lambda _e: self.relayout(redraw=True))
            self.cv.bind("<Button-1>", self._click)

        # ---- images
        def _image(self, path):
            key = str(path)
            if key not in self.images:
                try:
                    self.images[key] = tk.PhotoImage(master=self.cv, file=key)
                except Exception:
                    self.images[key] = None
            return self.images[key]

        def frames(self, cid, anim, size=None):
            size = size or self.actor_px(cid)
            key = (cid, anim, size)
            if key not in self.frame_cache:
                out = []
                try:
                    for p in sprites.frames(cid, anim, size, pack_dirs=self.app.pack_dirs()):
                        img = self._image(p)
                        if img is None:
                            out = []
                            break
                        out.append(img)
                except Exception:
                    out = []
                self.frame_cache[key] = out
            return self.frame_cache[key]

        def forget_images(self):
            self.frame_cache.clear()

        # ---- geometry
        def dims(self):
            w = max(200, self.cv.winfo_width() if self.cv.winfo_width() > 1 else int(self.cv.cget("width")))
            h = max(120, self.cv.winfo_height() if self.cv.winfo_height() > 1 else int(self.cv.cget("height")))
            return w, h

        def floor_y(self):
            w, h = self.dims()
            return int((h - 4) * self.app.tok["sprite"]["baseline"])

        def actor_px(self, cid):
            """Sprite size for one character: a cameo walk-on stays at the walk-on size beside large mains."""
            sp = self.app.tok["sprite"]
            if self.size >= sp["stage"] and cast.role(cid) == "cameo":
                return min(self.size, int(sp.get("cameo", sp["stage_compact"])))
            return self.size

        def _split(self):
            here = [cid for cid in self.order() if not self.actors[cid].get("leaving")]
            return ([c for c in here if cast.role(c) != "cameo"], [c for c in here if cast.role(c) == "cameo"])

        def tag_width(self, cid):
            app = self.app
            name, pron = cast.name(cid), cast.character(cid).get("pronouns", "")
            tw = app.fonts["tag"].measure(name) + ((5 + app.fonts["small"].measure(pron)) if pron else 0)
            return tw + 2 * app.space(4)

        def plan(self, s, w, regs, cams):
            """(x positions, fits) for mains at size `s` with walk-ons at the right edge. `fits` is False when
            the mains' name tags would overlap each other or a walk-on's, or a sticker would leave the stage."""
            sp = self.app.tok["sprite"]
            inner = w - self.app.tok["elevation"]["card"][0] - 6
            right = inner - sp["pad"]
            out = {}
            for cid in cams:                                    # walk-ons stand at the edge of the stage
                room = max(int(self.actor_px(cid) * 0.8), self.tag_width(cid) + 6) if s >= sp["stage"] else \
                    max(int(s * 0.8), self.tag_width(cid) + 6)
                out[cid] = right - room / 2.0
                right -= room
            tw = [self.tag_width(c) for c in regs] or [0]
            pair = max([(x + y) / 2.0 + 6 for x, y in zip(tw, tw[1:])] or [0])    # neighbouring tags never touch
            half = s * 0.34                                     # half the visible sticker (transparent margins)
            ends = max(half, tw[0] / 2.0) + max(half, tw[-1] / 2.0)
            room = right - sp["pad"]
            if s >= sp["stage"]:
                # big stickers may overlap a little; squeeze further only when a walk-on needs the room
                steps = [s - max(sp["overlap"], s // 4), s - s // 3, int(s * 0.625)]
            else:
                steps = [s + sp["gap_compact"], s]
            steps = [max(st, pair) for st in steps]
            n = max(1, len(regs))
            step = next((st for st in steps if (n - 1) * st + ends <= room), steps[-1])
            fits = (n - 1) * step + ends <= room
            cx = (sp["pad"] + right) / 2.0
            start = cx - (len(regs) - 1) * step / 2.0
            for i, cid in enumerate(regs):
                out[cid] = start + i * step
            return out, fits

        def pick_size(self):
            want = self.app.cfg.get("gui_sprite_size", "auto")
            if want in (96, 192) or str(want) in ("96", "192"):
                return int(want)
            sp = self.app.tok["sprite"]
            big, small = int(sp["stage"]), int(sp["stage_compact"])
            w, h = self.dims()
            regs, cams = self._split()
            if len(regs) >= 4:                                 # four or more: always the compact stage
                return small
            if h < self.app.size("stage"):                     # no headroom for the bubble over big stickers
                return small
            return big if self.plan(big, w, regs, cams)[1] else small

        def targets(self):
            regs, cams = self._split()
            return self.plan(self.size, self.dims()[0], regs, cams)[0]

        def order(self):
            return cast.order(list(self.actors))

        # ---- cast changes
        def set_cast(self, who, arrived=()):
            """Make the stage show exactly `who`; newcomers walk in (and wave), leavers walk off."""
            who = cast.order(who)
            w, _h = self.dims()
            for cid in list(self.actors):
                if cid not in who and not self.actors[cid].get("leaving"):
                    a = self.actors[cid]
                    if self.app.reduced:
                        self._remove(cid)
                    else:
                        a["leaving"] = True
                        a["tx"] = w + self.size if a["x"] > w / 2 or cast.role(cid) == "cameo" else -self.size
            for cid in who:
                if cid in self.actors and not self.actors[cid].get("leaving"):
                    continue
                if cid in self.actors:
                    self._remove(cid)
                self.actors[cid] = {"x": 0.0, "tx": 0.0, "kind": "", "img": None, "anim": "idle", "frame": 0,
                                    "next_at": 0.0, "override": None, "until": 0.0, "leaving": False,
                                    "blink_at": time.monotonic() + self._blink_gap(),
                                    "special_at": time.monotonic() + random.uniform(25, 70), "mood": ""}
            new_size = self.pick_size()
            if new_size != self.size:
                self.size = new_size
            tx = self.targets()
            for cid, x in tx.items():
                a = self.actors[cid]
                a["tx"] = x
                fresh = not a["kind"]
                if fresh:
                    if cid in arrived and not self.app.reduced:
                        a["x"] = (w + self.size) if cast.role(cid) == "cameo" or x > w / 2 else -self.size / 2.0
                        self.play(cid, "wave", 2.4)
                    else:
                        a["x"] = x
            self.relayout(redraw=True, keep_x=True)

        def _remove(self, cid):
            self.cv.delete("actor:" + cid)
            self.actors.pop(cid, None)
            if self.speaker == cid:
                self.hide_bubble()

        def present(self):
            return [c for c in self.order() if not self.actors[c].get("leaving")]

        # ---- drawing
        def relayout(self, redraw=False, keep_x=False):
            if not self.app.winfo_exists():
                return
            new = self.pick_size()
            if new != self.size:
                self.size = new
                redraw = True
            for cid, x in self.targets().items():
                a = self.actors[cid]
                a["tx"] = x
                if not keep_x or self.app.reduced:
                    a["x"] = x
            if redraw:
                self.draw_backdrop()
                for cid in list(self.actors):
                    self.draw_actor(cid)
                if self.speaker and self.speaker in self.actors and self._bubble_text:
                    self.show_bubble(self.speaker, self._bubble_text, requeue=False)

        _bubble_text = ""

        def draw_backdrop(self):
            c, cv, app = self.app.c, self.cv, self.app
            w, h = self.dims()
            sh = app.tok["elevation"]["card"]
            cv.configure(bg=c["bg"])
            cv.delete("bg")
            r = app.tok["radius"]["lg"]
            rounded(cv, sh[0] + 1, sh[1] + 1, w - 1, h - 1, r, fill=c["shadow"], outline="", tags="bg")
            rounded(cv, 2, 2, w - sh[0] - 2, h - sh[1] - 2, r, fill=c["stage"], outline="", tags="bg")
            fy = self.floor_y()
            iw = w - sh[0] - 4
            cx = iw / 2.0
            outer = theme.mix(c["stage"], c["stage_glow"], 0.55)
            cv.create_oval(cx - iw * 0.48, fy - h * 0.82, cx + iw * 0.48, fy + h * 0.5, fill=outer, outline="",
                           tags="bg")
            cv.create_oval(cx - iw * 0.32, fy - h * 0.6, cx + iw * 0.32, fy + h * 0.35, fill=c["stage_glow"],
                           outline="", tags="bg")
            cv.create_oval(-iw * 0.15, fy - 14, iw * 1.15, fy + h * 0.9, fill=c["stage_floor"], outline=c["line"],
                           width=2, tags="bg")
            rng = random.Random(7)
            for i in range(4):
                x, y = rng.uniform(0.05, 0.95) * iw, rng.uniform(0.12, 0.55) * fy
                cv.create_text(x, y, text="✦", fill=c["keyline"] if i % 2 else c["gold"],
                               font=app.fonts["body_strong" if i % 2 else "small"], tags="bg")
            # the panel edge goes on top of the glow but under the characters
            rounded(cv, 2, 2, w - sh[0] - 2, h - sh[1] - 2, r, fill="", outline=c["line"],
                    width=app.tok["keyline"]["sticker"], tags=("bg", "edge"))
            cv.tag_lower("bg")

        def _tag_colors(self, cid):
            return theme.character_colors(self.app.c, cid, cast.character(cid))

        def draw_tag(self, x, y, cid, tags, anchor="center"):
            """Name tag pill: fill = the character's role colour, 'Name pronouns' (design system 3.7)."""
            cv, app = self.cv, self.app
            fill, ink = self._tag_colors(cid)
            name = cast.name(cid)
            pron = cast.character(cid).get("pronouns", "")
            f1, f2 = app.fonts["tag"], app.fonts["small"]
            gap = 5 if pron else 0
            tw = f1.measure(name) + gap + (f2.measure(pron) if pron else 0)
            ph = app.size("control_sm") - 6
            pw = tw + 2 * app.space(4)
            x0 = x - pw / 2.0 if anchor == "center" else x
            inner = self.dims()[0] - app.tok["elevation"]["card"][0] - 6
            x0 = max(6, min(inner - pw, x0))                    # keep the whole pill on the stage
            rounded(cv, x0, y - ph / 2.0, x0 + pw, y + ph / 2.0, ph, fill=fill, outline=app.c["keyline"], width=2,
                    tags=tags)
            tx = x0 + app.space(4)
            cv.create_text(tx, y, text=name, anchor="w", fill=ink, font=f1, tags=tags)
            if pron:
                cv.create_text(tx + f1.measure(name) + gap, y, text=pron, anchor="w", fill=ink, font=f2, tags=tags)
            return pw

        def _mood_art(self, cid, anim):
            mood = "art_sleep" if anim == "sleep" else "art_happy" if anim in ("happy", "wave", "special") else "art"
            try:
                return self.app.brain.art(cid, mood).rstrip("\n")
            except Exception:
                return ""

        def draw_actor(self, cid):
            a = self.actors.get(cid)
            if not a:
                return
            cv, app, s = self.cv, self.app, self.actor_px(cid)
            tag = "actor:" + cid
            cv.delete(tag)
            fy = self.floor_y()
            tags = (tag, "actor")
            idle = self.frames(cid, "idle")
            anim = self.current_anim(cid)
            if idle:
                frames = self.frames(cid, anim) or idle
                img = frames[a["frame"] % len(frames)] if not app.reduced else idle[0]
                a["kind"] = "sprite"
                a["img"] = cv.create_image(a["x"], fy + s * (1 - app.tok["sprite"]["baseline"]), image=img,
                                           anchor="s", tags=tags)
            else:
                a["kind"] = "text"
                art = self._mood_art(cid, anim if not app.reduced else "idle")
                a["mood"] = anim
                if art.strip():
                    font = app.fonts["mono"] if s >= 192 else app.fonts["mono_small"]
                    a["img"] = cv.create_text(a["x"], fy - 10, text=art, anchor="s", fill=app.c["ink"], font=font,
                                              justify="left", tags=tags)
                else:                                           # no art at all: a round token with an initial
                    fill, ink = self._tag_colors(cid)
                    r = s * 0.28
                    cv.create_oval(a["x"] - r, fy - 12 - 2 * r, a["x"] + r, fy - 12, fill=fill,
                                   outline=app.c["keyline"], width=3, tags=tags)
                    a["img"] = cv.create_text(a["x"], fy - 12 - r, text=cast.name(cid)[:1], fill=ink,
                                              font=app.fonts["display"], tags=tags)
            ty = min(fy + 2, self.dims()[1] - app.tok["elevation"]["card"][1] - 18)
            self.draw_tag(a["x"], ty, cid, tags)
            cv.tag_raise("bubble")

        # ---- animation
        def _blink_gap(self):
            m = self.app.motion
            return random.uniform(m["blink_min"], m["blink_max"]) / 1000.0

        def play(self, cid, anim, seconds=None):
            """Play `anim` on one character for `seconds` (default: one pass of the animation)."""
            a = self.actors.get(cid)
            if not a or self.app.reduced:
                return
            if seconds is None:
                info = sprites.anim_info(cid, anim) or {"count": 4, "fps": 8}
                seconds = info["count"] / float(max(1, info["fps"]))
            a["override"], a["until"], a["frame"] = anim, time.monotonic() + seconds, 0
            self.start()

        def base_anim(self, cid):
            app = self.app
            if cast.role(cid) != "cameo":
                try:
                    if app.brain.mood(cid) == "sleep":
                        return "sleep"
                except Exception:
                    pass
                if app.night and time.time() - app.last_action > SLEEPY_AFTER_S:
                    return "sleep"
            return "idle"

        def current_anim(self, cid):
            a = self.actors[cid]
            if self.speaker == cid:
                return "talk"
            if self.speaker and self.speaker in self.actors and a.get("override") in (None, "look_left", "look_right"):
                return "look_left" if self.actors[self.speaker]["x"] < a["x"] else "look_right"
            if a["override"] and time.monotonic() < a["until"]:
                return a["override"]
            return self.base_anim(cid)

        def start(self):
            if not self.app.reduced and "anim" not in self.app._after:
                self.app._schedule("anim", 10, self.tick)

        def tick(self):
            app = self.app
            if app.reduced or not self.actors:
                return
            now = time.monotonic()
            fps_cap = max(1, app.motion["sprite_fps_max"])
            for cid in list(self.actors):
                a = self.actors[cid]
                moved = False
                if abs(a["x"] - a["tx"]) > 0.5:                 # walk towards the spot
                    d = a["tx"] - a["x"]
                    a["x"] += max(-14.0, min(14.0, d))
                    moved = True
                if a.get("leaving") and abs(a["x"] - a["tx"]) <= 0.5:
                    self._remove(cid)
                    self.relayout(keep_x=True)
                    continue
                if a["override"] and now >= a["until"]:
                    a["override"] = None
                if not a["override"] and self.speaker is None:
                    if now >= a["blink_at"]:
                        a["blink_at"] = now + self._blink_gap()
                        if self.base_anim(cid) == "idle" and self.frames(cid, "blink"):
                            self.play(cid, "blink")
                    elif now >= a["special_at"]:
                        a["special_at"] = now + random.uniform(30, 90)
                        if self.base_anim(cid) == "idle" and self.frames(cid, "special"):
                            self.play(cid, "special")
                anim = self.current_anim(cid)
                if a["kind"] == "text":
                    if anim != a.get("mood") or moved:
                        self.draw_actor(cid)
                    continue
                frames = self.frames(cid, anim) or self.frames(cid, "idle")
                if not frames:
                    continue
                if anim != a["anim"]:
                    a["anim"], a["frame"], a["next_at"] = anim, 0, 0.0
                if now >= a["next_at"]:
                    info = sprites.anim_info(cid, anim) or {"fps": 6}
                    a["frame"] = (a["frame"] + 1) % len(frames)
                    a["next_at"] = now + 1.0 / min(fps_cap, max(1, info["fps"]))
                img = frames[a["frame"] % len(frames)]
                try:
                    self.cv.itemconfigure(a["img"], image=img)
                    if moved:
                        self.cv.move("actor:" + cid, 0, 0)
                        self.draw_actor(cid)
                except tk.TclError:
                    pass
            app._schedule("anim", max(40, 1000 // fps_cap), self.tick)

        # ---- props
        def prop(self, cid, name, ms=1200):
            a = self.actors.get(cid)
            if not a or self.app.reduced:
                return
            imgs = self.frames(sprites.PROPS, name, self.app.tok["sprite"]["stage_compact"])
            if not imgs:
                return
            self.cv.delete("prop")
            self.cv.create_image(a["x"] + self.size * 0.3, self.floor_y() - self.size * 0.85, image=imgs[0],
                                 tags=("prop",))
            self.app._schedule("prop", ms, lambda: self.cv.delete("prop"))

        # ---- speech bubbles
        def speak(self, cid, text, now=False):
            """Queue a bubble; with reduced motion only the latest line is shown (no timers)."""
            if self.app.reduced or now:
                self.queue = []
                self.show_bubble(cid, text)
                return
            showing = self.speaker is not None and time.monotonic() - self.bubble_at < (SCENE_STEP_MS - 200) / 1000.0
            if showing or self.queue:
                self.queue.append((cid, text))
                if "bubble" not in self.app._after:
                    self.app._schedule("bubble", SCENE_STEP_MS, self.next_bubble)
            else:
                self.show_bubble(cid, text)

        def next_bubble(self):
            if self.queue:
                cid, text = self.queue.pop(0)
                self.show_bubble(cid, text)
            else:
                self.hide_bubble()

        def show_bubble(self, cid, text, requeue=True):
            cv, app, c = self.cv, self.app, self.app.c
            cv.delete("bubble")
            if cid not in self.actors:
                return
            self.speaker, self._bubble_text, self.bubble_at = cid, text, time.monotonic()
            w, h = self.dims()
            sh = app.tok["elevation"]["card"]
            inner = w - sh[0] - 4
            compact = h < app.size("stage")
            pad = app.space(4 if compact else 5)
            bw = min(inner - 28, max(240, int(inner * (0.94 if compact else 0.72))))
            sx = self.actors[cid]["tx"]
            bx = max(14, min(inner - 14 - bw, sx - bw / 2.0))
            by = 16 if compact else 22
            t = cv.create_text(bx + pad, by + pad + (2 if compact else 4), text=text, anchor="nw", width=bw - 2 * pad, fill=c["ink"],
                               font=app.fonts["body"], tags="bubble")
            x0, y0, x1, y1 = cv.bbox(t)
            by1 = y1 + pad - 4
            body = rounded(cv, bx, by, bx + bw, by1, app.tok["radius"]["md"], fill=c["surface"], outline=c["line"],
                           width=app.tok["keyline"]["control"], tags="bubble")
            tx = max(bx + 22, min(bx + bw - 22, sx))
            tail = cv.create_polygon(tx - 9, by1 - 1, tx + 9, by1 - 1, tx, by1 + 11, fill=c["surface"],
                                     outline=c["line"], width=app.tok["keyline"]["control"], tags="bubble")
            cover = cv.create_line(tx - 7, by1 - 1, tx + 7, by1 - 1, fill=c["surface"], width=3, tags="bubble")
            cv.tag_raise(t)
            del body, tail, cover
            self.draw_tag(bx + 10, by, cid, ("bubble",), anchor="w")
            cv.tag_raise("bubble")
            if requeue and not app.reduced:
                hold = SCENE_STEP_MS if self.queue else app.motion["bubble_hold"]
                app._schedule("bubble", hold, self.next_bubble)
            if not app.reduced:
                self.start()

        def hide_bubble(self):
            self.cv.delete("bubble")
            self.speaker, self._bubble_text = None, ""
            self.app._cancel("bubble")

        def advance(self):
            """Click on the stage: show the next queued bubble now. Returns True if something advanced."""
            if self.queue:
                self.app._cancel("bubble")
                self.next_bubble()
                return True
            return False

        def _click(self, e):
            hit = self.cv.find_withtag("current")
            tags = self.cv.gettags(hit[0]) if hit else ()
            who = next((t.split(":", 1)[1] for t in tags if t.startswith("actor:")), None)
            if who and who in self.actors and not self.actors[who].get("leaving"):
                self.app.pet_character(who)
            else:
                self.app.advance()

        def retheme(self):
            self.relayout(redraw=True)

    # ------------------------------------------------------------------------------------------ the app
    class App(tk.Tk):
        COLUMNS = [("fav", "♥", 34, "center"), ("game", "Game", 220, "w"), ("card", "Card", 80, "center"),
                   ("size", "Size", 74, "e"), ("discs", "Discs", 62, "center"), ("rating", "Rating", 92, "w"),
                   ("tags", "Tags", 150, "w")]

        def __init__(self):
            super().__init__()
            self.withdraw()
            self._after = {}
            self._closing = False
            self._themed = []           # widgets with a retheme() method
            self._paints = []           # (widget, {option: role}) for plain tk widgets
            self.cfg, self.state, self.cat = core.load_config(), core.load_state(), Catalog()
            self.roms, self.saves = [], {}
            self.brain = pets.PetBrain(self.state, self.cat)
            self.tok = theme.tokens()
            self.reduced = theme.reduce_motion_requested(self.cfg)
            self.motion = theme.motion(self.reduced)
            self.plain = plain_requested(self.cfg)
            self.theme_name = theme.resolve(self.cfg.get("gui_theme"))
            self.c = theme.load(self.theme_name)
            self.base_title = "Pawtation - " + pets.PETS.get("title", "")
            self.night = cast.time_when() == "night"
            self.last_action = time.time()
            self._last_step = time.time()
            self._scene_queue = []
            # sync / worker state
            self.events: "queue.Queue" = queue.Queue()
            self.cancel_event = threading.Event()
            self.worker = None
            self.syncing = False
            self.sync_info = {}
            self._sync_started = 0.0
            self._sync_mount = ""
            self.last_report = None
            self._loop_frames, self._loop_i = [], 0
            # misc state
            self.sort_col, self.sort_rev = "card", False
            self._nagged = False
            self._flash_left = 0
            self._due_marked = False
            self.last_error = None
            self._mounted = {}
            self.title(self.base_title)
            lw, lh = self.tok["layout"]["window_min"]
            dw, dh = self.tok["layout"]["window_default"]
            self.minsize(lw, lh)
            self.geometry(f"{dw}x{dh}")
            self._icon()
            self._style = ttk.Style(self)
            try:
                self._style.theme_use("clam")
            except tk.TclError:
                pass
            self._fonts()
            self._build()
            self.apply_theme(self.theme_name, save=False)
            self._bind_keys()
            self.bind("<Configure>", self._on_resize, add="+")
            self.protocol("WM_DELETE_WINDOW", self.on_close)
            try:                                             # an expired group moves on quietly at start-up
                cast.step(self.state, rng=self.brain.rng)
            except Exception:
                pass
            self.refresh(announce=False)
            self._update_meters()
            self.deiconify()
            self.update_idletasks()
            self._place_sash()
            self.stage.set_cast(self.brain.home())
            self._update_chips()
            for line in self.brain.duo("greeting"):
                self.say(line)
            for line in (self.brain.collection(self.roms) if self.roms else []):
                self.say(line)
            if not self.roms:
                self.say(self._empty_line())
            self._tick()

        # ---------- dialogs (override / monkeypatch in tests) ----------
        def ask_yes_no(self, title, text):
            return bool(self._dialog(title, text, [("No", False, "secondary"), ("Yes", True, "primary")],
                                     default=False, cancel=False))

        def show_info(self, title, text):
            self._dialog(title, text, [("OK", True, "primary")], default=True, cancel=True)

        def show_error(self, title, text):
            first, _sep, rest = str(text).partition("\n\n")
            self._dialog(title, first, [("Close", True, "secondary")], default=True, cancel=True,
                         detail=rest.strip() or None, icon="error")

        def ask_directory(self, title, initial=""):
            return filedialog.askdirectory(title=title, parent=self, initialdir=initial or None, mustexist=True) or None

        def ask_file(self, title, filetypes=(("All files", "*.*"),), initial=""):
            return filedialog.askopenfilename(title=title, parent=self, filetypes=filetypes,
                                              initialdir=initial or None) or None

        def choose_card(self, options, prompt="Which card is inserted?"):
            """Return one of `options` or None if cancelled / window closed."""
            labels = [(cid, f"Card {cid}  ({self.cfg['cards'].get(cid, {}).get('label', 'Card ' + str(cid))})")
                      for cid in options]
            return self._dialog("Sync a card", prompt, [("Cancel", None, "secondary"), ("Choose", "@choice", "primary")],
                                default="@choice", cancel=None, choices=labels)

        def ask_birthdate(self, check):
            """The After Dark gate (design system 3.8). `check(text) -> (ok, message)` does the work; the typed date
            is handed over once and never kept. Returns True when After Dark ended up unlocked."""
            return self._dialog("After Dark", None, [], gate=check)

        def ask_afterdark_unlocked(self):
            """After Dark is already on: offer to lock it again. Returns True to lock."""
            day = afterdark.confirmed_on(self.state) or "earlier"
            body = (f"After Dark is on (since {day}). It will not ask for a date of birth again while it stays on. "
                    "You can lock it again at any time.")
            return bool(self._dialog("After Dark", body, [("Keep it on", False, "secondary"),
                                                         ("Lock again", True, "ghost")],
                                     default=False, cancel=False, tag="optional · 18+"))

        def report_callback_exception(self, exc, val, tb):
            text = "".join(traceback.format_exception(exc, val, tb))
            self.last_error = text
            try:
                self.show_error("Pawtation hit a snag", f"{val}\n\n{text[-1500:]}")
            except Exception:
                print(text)

        def _dialog(self, title, body, buttons, default=None, cancel=None, detail=None, icon=None, tag=None,
                    choices=None, gate=None):
            """One themed modal dialog for everything: confirm, info, error, card choice and the After Dark gate."""
            c = self.c
            win = tk.Toplevel(self)
            win.withdraw()
            win.title(title)
            win.transient(self)
            win.configure(bg=c["bg"])
            win.resizable(False, False)
            out = {"v": cancel}
            card = tk.Frame(win, bg=c["surface"], highlightthickness=2, highlightbackground=c["line"],
                            highlightcolor=c["line"])
            card.pack(fill="both", expand=True, padx=self.space(6), pady=self.space(6))
            inner = tk.Frame(card, bg=c["surface"])
            inner.pack(fill="both", expand=True, padx=self.space(6), pady=self.space(5))
            head = tk.Frame(inner, bg=c["surface"])
            head.pack(fill="x", anchor="w")
            if icon == "error":
                tk.Label(head, text="✕", bg=c["surface"], fg=c["danger"], font=self.fonts["title"]).pack(side="left",
                                                                                                      padx=(0, 8))
            tk.Label(head, text=title, bg=c["surface"], fg=c["ink"], font=self.fonts["title"]).pack(side="left")
            if tag or gate:
                tk.Label(head, text=tag or "optional · 18+", bg=c["surface_alt"], fg=c["ink_muted"],
                         font=self.fonts["tag"], padx=8, pady=1).pack(side="left", padx=10)
            wrap = 460
            if body:
                tk.Label(inner, text=body, bg=c["surface"], fg=c["ink"], font=self.fonts["body"], justify="left",
                         wraplength=wrap, anchor="w").pack(fill="x", pady=(self.space(4), 0))
            if detail:
                box = tk.Text(inner, height=min(10, detail.count("\n") + 2), width=60, wrap="word", bg=c["surface_alt"],
                              fg=c["ink"], font=self.fonts["mono"], relief="flat", padx=8, pady=6, borderwidth=0)
                box.insert("1.0", detail)
                box.configure(state="disabled")
                box.pack(fill="both", expand=True, pady=(self.space(4), 0))
            var = None
            if choices:
                var = tk.StringVar(win, value=choices[0][0])
                for cid, label in choices:
                    tk.Radiobutton(inner, text=label, variable=var, value=cid, bg=c["surface"], fg=c["ink"],
                                   selectcolor=c["surface"], activebackground=c["primary_soft"],
                                   activeforeground=c["ink"], highlightthickness=0, font=self.fonts["body"],
                                   anchor="w").pack(fill="x", padx=8, pady=1)
            gate_ui = {}
            if gate:
                tk.Label(inner, text=("After Dark adds flirtier late-night banter between the characters. Nothing "
                                      "else in Pawtation needs it, and you can leave it off.\n\nTo turn it on, enter "
                                      "your date of birth once. Pawtation checks that you are 18 or older and keeps "
                                      "only today's date as the confirmation. Your date of birth is not saved."),
                         bg=c["surface"], fg=c["ink"], font=self.fonts["body"], justify="left", wraplength=wrap,
                         anchor="w").pack(fill="x", pady=(self.space(4), 0))
                tk.Label(inner, text="Date of birth", bg=c["surface"], fg=c["ink"], font=self.fonts["body_strong"],
                         anchor="w").pack(fill="x", pady=(self.space(5), 2))
                dob = tk.StringVar(win)
                entry = ttk.Entry(inner, textvariable=dob, width=18, font=self.fonts["body"])
                entry.pack(anchor="w")
                hint = tk.Label(inner, text=("YYYY-MM-DD. Also accepts MM/DD/YYYY or DD.MM.YYYY. You can turn After "
                                             "Dark off again at any time."),
                                bg=c["surface"], fg=c["ink_muted"], font=self.fonts["small"], justify="left",
                                wraplength=wrap, anchor="w")
                hint.pack(fill="x", pady=(2, 0))
                msg = tk.Label(inner, text="", bg=c["surface"], fg=c["danger"], font=self.fonts["body_strong"],
                               justify="left", wraplength=wrap, anchor="w")
                gate_ui.update(dob=dob, entry=entry, msg=msg, hint=hint)
                out["v"] = afterdark.is_unlocked(self.state)
            foot = tk.Frame(inner, bg=c["surface"])
            foot.pack(fill="x", pady=(self.space(6), 0))
            made = []

            def finish(value):
                out["v"] = value
                win.destroy()

            def pick(value):
                if value == "@choice":
                    value = var.get() if var is not None else None
                finish(value)

            def do_check(_e=None):
                text = gate_ui["dob"].get()
                gate_ui["dob"].set("")                         # the typed date leaves the field at once
                ok, message = gate(text)
                text = None
                if ok:
                    finish(True)
                    return
                gate_ui["entry"].pack_forget()
                gate_ui["hint"].pack_forget()
                gate_ui["msg"].configure(text="✕ " + message)
                gate_ui["msg"].pack(fill="x", pady=(self.space(4), 0))
                gate_ui["check"].destroy()
                gate_ui["notnow"].configure(text="Close")
                gate_ui["notnow"].focus_set()

            if gate:
                buttons = [("Not now", False, "secondary"), ("Check and turn on", "@check", "primary")]
                default, cancel = False, False
            for label, value, variant in buttons:
                cmd = do_check if value == "@check" else (lambda v=value: pick(v))
                b = self.button(foot, label, cmd, variant, on="surface")
                made.append((b, value))
                if value == "@check":
                    gate_ui["check"] = b
                if gate and value is False:
                    gate_ui["notnow"] = b
            for b, _v in reversed(made):
                b.pack(side="right", padx=(self.space(3), 0))
            win.bind("<Escape>", lambda _e: finish(cancel if not gate else afterdark.is_unlocked(self.state)))
            win.protocol("WM_DELETE_WINDOW", lambda: finish(cancel if not gate else afterdark.is_unlocked(self.state)))
            if gate:
                gate_ui["entry"].bind("<Return>", do_check)
            win.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_reqwidth()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - win.winfo_reqheight()) // 3)
            win.geometry(f"+{x}+{y}")
            win.deiconify()
            focus = next((b for b, v in made if v == default), made[0][0] if made else None)
            if gate:
                focus = gate_ui["notnow"]
            if focus is not None:
                focus.focus_set()
                win.bind("<Return>", lambda _e: focus.invoke() if win.focus_get() is not gate_ui.get("entry") else None)
            try:
                win.grab_set()
            except tk.TclError:
                pass
            self.wait_window(win)
            return out["v"]

        # ---------- scheduling helpers ----------
        def _schedule(self, name, ms, fn):
            if self._closing:
                return
            self._cancel(name)

            def run():
                self._after.pop(name, None)
                if not self._closing:
                    fn()
            self._after[name] = self.after(max(0, int(ms)), run)

        def _cancel(self, name):
            old = self._after.pop(name, None)
            if old:
                try:
                    self.after_cancel(old)
                except Exception:
                    pass

        def destroy(self):
            self._closing = True
            hidden.close()                                   # section 9: quitting always locks it again
            for name in list(self._after):
                self._cancel(name)
            self._after.clear()
            super().destroy()

        # ---------- theme plumbing ----------
        def space(self, i):
            return self.tok["space"][i]

        def size(self, key):
            return self.tok["size"][key]

        def sprite_px(self, key):
            return self.tok["sprite"][key]

        def paint(self, widget, **roles):
            self._paints.append((widget, roles))
            try:
                widget.configure(**{k: self.c[v] for k, v in roles.items()})
            except tk.TclError:
                pass
            return widget

        def _fonts(self):
            try:
                installed = tkfont.families(self)
            except tk.TclError:
                installed = ()
            fams = theme.fonts(installed)
            default = tkfont.nametofont("TkDefaultFont").actual("family")
            fixed = tkfont.nametofont("TkFixedFont").actual("family")
            scale = self.cfg.get("ui_scale", 1.0) if isinstance(self.cfg.get("ui_scale"), (int, float)) else 1.0
            self.fonts = {}
            for style, spec in self.tok["type"]["scale"].items():
                fam = fams.get(spec["family"]) or (fixed if spec["family"] == "mono" else default)
                self.fonts[style] = tkfont.Font(self, family=fam, size=theme.tk_size(spec["px"], scale),
                                                weight=spec.get("weight", "normal"))
            mono = self.tok["type"]["scale"]["mono"]
            self.fonts["mono_small"] = tkfont.Font(self, family=self.fonts["mono"].actual("family"),
                                                   size=theme.tk_size(max(9, mono["px"] - 4), scale))
            self.fonts["italic"] = self.fonts["body"].copy()
            self.fonts["italic"].configure(slant="italic")

        def button(self, parent, text, command, variant="secondary", on="bg", small=False):
            if self.plain:
                return ttk.Button(parent, text=text, command=command,
                                  style=("Small." if small else "") + variant.capitalize() + ".TButton")
            return PillButton(parent, self, text, command, variant=variant, on=on, small=small)

        def frame(self, parent, role="bg", **kw):
            return self.paint(tk.Frame(parent, **kw), bg=role)

        def label(self, parent, text="", role="bg", fg="ink", font="body", **kw):
            w = tk.Label(parent, text=text, font=self.fonts[font], **kw)
            return self.paint(w, bg=role, fg=fg)

        def _icon(self):
            try:
                p = sprites.render("nova_icon")
                if p:
                    self._icon_img = tk.PhotoImage(master=self, file=str(p))
                    self.iconphoto(True, self._icon_img)
            except Exception:
                self._icon_img = None

        def pack_dirs(self):
            try:
                return [p["path"] for p in cast.packs(self.brain.unlocked(), sealed=True)]
            except Exception:
                return []

        # ---------- layout ----------
        def _build(self):
            g = self.tok["layout"]["gutter"]
            root = self.frame(self)
            root.pack(fill="both", expand=True)
            self.root_frame = root
            self._build_header(root)
            self.status = tk.StringVar(self)
            st = self.label(root, "", "bg", "ink_muted", "small", anchor="w", textvariable=self.status)
            st.pack(side="bottom", fill="x", padx=g, pady=(0, 4))
            body = tk.PanedWindow(root, orient="horizontal", sashwidth=8, bd=0, opaqueresize=True)
            self.paint(body, bg="bg")
            body.pack(fill="both", expand=True, padx=g, pady=(self.space(4), self.space(2)))
            left = self.frame(body)
            right = self.frame(body)
            body.add(left, minsize=480, stretch="always")
            body.add(right, minsize=self.tok["layout"]["side_panel"] - 20, stretch="always")
            self.body = body
            self.left, self.right = left, right
            self.banner = self.frame(left, "gold_soft", highlightthickness=2)
            self.paint(self.banner, highlightbackground="warning", highlightcolor="warning")
            self.label(self.banner, "◆ Rotation due.", "gold_soft", "warning", "body_strong").pack(side="left",
                                                                                                    padx=(12, 4))
            self.banner_text = self.label(self.banner, "Plan a new one with the pink button when you feel like it.",
                                          "gold_soft", justify="left", anchor="w")
            self.banner_text.pack(side="left", fill="x", expand=True, pady=6)
            self.button(self.banner, "×", self.hide_banner, "ghost", on="gold_soft", small=True).pack(side="right",
                                                                                                    padx=4)
            self.banner_text.bind("<Configure>", lambda e: self.banner_text.configure(wraplength=max(120, e.width - 4)))
            self._build_left(left)
            self._build_right(right)

        def _on_resize(self, e):
            """Tall stage (192 px sprites) when the window has the height for it, else the compact stage."""
            if e.widget is not self or self._closing:
                return
            want = self.size("stage") if e.height >= 800 else self.size("stage_compact")
            if int(self.stage.cv.cget("height")) != want:
                self.stage.cv.configure(height=want)
            compact = e.height < 760
            if compact != self.compact:
                self.compact = compact
                self._build_actions()
            w = e.width
            if getattr(self, "_last_w", None) != w:
                self._last_w = w
                self._place_sash(w - 2 * self.tok["layout"]["gutter"])

        def _fit_columns(self):
            """Give the Game column the spare width (up to its longest title) once Tags has room for its
            longest entry (up to twice its base width); Tags takes whatever is left."""
            tree = getattr(self, "tree", None)
            if tree is None:
                return
            try:
                avail = tree.winfo_width()
                if avail <= 1:
                    return
                base = {c[0]: c[2] for c in self.COLUMNS}
                fixed = sum(w for cid, w in base.items() if cid not in ("game", "tags"))
                font = self.fonts["body_strong"]
                rows = tree.get_children("")
                need = max([font.measure(str(tree.set(i, "game"))) for i in rows] or [0]) + self.space(6)
                tneed = max([font.measure(str(tree.set(i, "tags"))) for i in rows] or [0]) + self.space(4)
                tneed = max(base["tags"], min(tneed, base["tags"] * 2))
                game = max(base["game"], min(need, avail - fixed - tneed - 4))
                tags = max(base["tags"], avail - fixed - game - 4)
                if int(tree.column("game", "width")) != game:
                    tree.column("game", width=game)
                if int(tree.column("tags", "width")) != tags:
                    tree.column("tags", width=tags)
            except (tk.TclError, KeyError, ValueError):
                pass

        def _place_sash(self, w=None):
            try:
                w = w or self.body.winfo_width()
                side = max(self.tok["layout"]["side_panel"], int(w * 0.42))
                self.body.sash_place(0, max(480, w - side), 0)
            except tk.TclError:
                pass

        def _build_header(self, root):
            hd = self.frame(root, "header", height=self.size("header"))
            hd.pack(fill="x")
            hd.pack_propagate(False)
            g = self.tok["layout"]["gutter"]
            self.label(hd, "✦ Pawtation", "header", "header_ink", "display").pack(side="left", padx=(g, 8))
            self.help_btn = self.button(hd, "Help  F1", self.show_help, "outline", on="header", small=True)
            self.help_btn.pack(side="right", padx=(4, g))
            self.theme_btn = self.button(hd, "Theme", self.toggle_theme, "outline", on="header", small=True)
            self.theme_btn.pack(side="right", padx=4)
            self.moon_btn = self.button(hd, "☾", self.open_afterdark, "outline", on="header", small=True)
            self.moon_btn.pack(side="right", padx=4)
            self.timer_var = tk.StringVar(self)
            self.timer = tk.Label(hd, textvariable=self.timer_var, font=self.fonts["body_strong"], padx=12, pady=3,
                                  highlightthickness=2)
            self.timer.pack(side="right", padx=8)
            self._timer_colors()

        def _timer_colors(self):
            c = self.c
            if self._due_marked:
                self.timer.configure(bg=c["gold"], fg=c["gold_ink"], highlightbackground=c["header_ink"])
            else:
                self.timer.configure(bg=c["keyline"], fg=c["primary_ink"], highlightbackground=c["header_ink"])

        def _build_left(self, left):
            left.columnconfigure(0, weight=1)
            bar = Flow(left)
            bar.grid(row=1, column=0, sticky="ew", pady=(0, 4))
            self.buttons = {}
            for key, text, fn, variant in [("plan", "Plan new rotation", self.plan, "primary"),
                                           ("sync", "Sync a card…", self.sync_card, "secondary"),
                                           ("library", "Pick library folder", self.pick_library, "secondary"),
                                           ("rescan", "Rescan", self.refresh, "ghost"),
                                           ("boot", "Boot card…", self.boot_card, "ghost")]:
                self.buttons[key] = bar.add(self.button(bar, text, fn, variant, small=True), padx=1, pady=0)
            self.guarded = [self.buttons[k] for k in ("library", "rescan", "plan", "sync", "boot")]
            sf = self.frame(left)
            sf.grid(row=2, column=0, sticky="ew", pady=2)
            self.search_var = tk.StringVar(self)
            self.search_var.trace_add("write", lambda *_: self._populate())
            self.search = ttk.Entry(sf, textvariable=self.search_var, style="Search.TEntry", font=self.fonts["body"])
            self.search.pack(side="left", fill="x", expand=True)
            self.search_hint = self.label(sf, "Search games, tags, cards", "surface", "ink_muted", "body")
            self.search_hint.place(in_=self.search, x=10, rely=0.5, anchor="w")
            self.search_hint.bind("<Button-1>", lambda _e: self.search.focus_set())
            self.button(sf, "Clear", lambda: self.search_var.set(""), "ghost", small=True).pack(side="left", padx=2)
            self.chips_cards = Flow(left)
            self.chips_cards.grid(row=3, column=0, sticky="ew", pady=2)
            tcard = self.frame(left, "line_soft", highlightthickness=2)
            self.paint(tcard, highlightbackground="line", highlightcolor="line")
            tcard.grid(row=4, column=0, sticky="nsew", pady=(2, 0))
            left.rowconfigure(4, weight=1)
            self.tree = ttk.Treeview(tcard, columns=[c[0] for c in self.COLUMNS], show="headings", height=6,
                                     selectmode="browse")
            for cid, text, w, anchor in self.COLUMNS:
                self.tree.heading(cid, text=text, command=lambda c=cid: self.sort_by(c))
                self.tree.column(cid, width=w, minwidth=30, anchor=anchor, stretch=(cid == "tags"))
            sb = ttk.Scrollbar(tcard, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=sb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            sb.pack(side="left", fill="y")
            self.tree.bind("<Double-1>", self.on_game_double)
            self.tree.bind("<Configure>", lambda _e: self._fit_columns(), add="+")
            self.tree.bind("<<TreeviewSelect>>", lambda _e: self._sync_pin_button())
            for n in range(1, 6):
                self.tree.bind(f"<Key-{n}>", lambda _e, n=n: self.rate(n))
            # empty state, placed over the table when there is nothing to show
            self.empty = self.frame(tcard, "surface")
            self.empty_title = self.label(self.empty, "", "surface", "ink", "title")
            self.empty_title.pack(pady=(0, 4))
            self.empty_body = self.label(self.empty, "", "surface", "ink_muted", "body", wraplength=360,
                                         justify="center")
            self.empty_body.pack()
            self.empty_btn = self.button(self.empty, "Pick library folder", self.pick_library, "primary", on="surface")
            self.empty_btn.pack(pady=8)
            acts = Flow(left)
            acts.grid(row=5, column=0, sticky="ew", pady=(4, 0))
            acts.add(self.label(acts, "Rate:", "bg", "ink_muted", "small"), pady=6)
            for n in range(1, 6):
                acts.add(self.button(acts, f"{n}★", lambda n=n: self.rate(n), "ghost", small=True), padx=0, pady=0)
            self.pin_btn = acts.add(self.button(acts, "♥ Pin favourite", self.toggle_pin, "ghost", small=True), padx=4,
                                    pady=0)
            # sync card
            pf = self.frame(left, "surface", highlightthickness=2)
            self.paint(pf, highlightbackground="line", highlightcolor="line")
            pf.grid(row=6, column=0, sticky="ew", pady=(6, 0))
            pf.columnconfigure(1, weight=1)
            self.loop = tk.Canvas(pf, width=128, height=96, highlightthickness=0, bd=0)
            self.paint(self.loop, bg="surface")
            self.prog_var = tk.DoubleVar(self, value=0)
            if self.plain:
                self.prog = ttk.Progressbar(pf, variable=self.prog_var, maximum=100, mode="determinate",
                                            style="Chunky.Horizontal.TProgressbar")
            else:
                self.prog = ChunkyBar(pf, self, self.prog_var)
            self.prog.grid(row=0, column=1, sticky="ew", padx=10, pady=(8, 2))
            self.prog_text = tk.StringVar(self, value="Idle. Plan a rotation, then sync a card.")
            self.eta_text = tk.StringVar(self, value="")
            self.prog_label = self.label(pf, "", "surface", "ink", "body_strong", anchor="w", justify="left",
                                         textvariable=self.prog_text)
            self.prog_label.grid(row=1, column=1, sticky="ew", padx=10)
            self.eta_label = self.label(pf, "", "surface", "ink_muted", "small", anchor="w", justify="left",
                                        textvariable=self.eta_text)
            self.eta_label.grid(row=2, column=1, sticky="ew", padx=10, pady=(0, 8))
            self.cancel_btn = self.button(pf, "Cancel sync", self.cancel_sync, "secondary", on="surface", small=True)
            self.cancel_btn.configure(state="disabled")
            self.cancel_btn.grid(row=0, column=2, rowspan=3, padx=(0, 8))
            pf.bind("<Configure>", lambda e: [w.configure(wraplength=max(160, e.width - 300))
                                              for w in (self.prog_label, self.eta_label)])
            self.sync_card_frame = pf

        def _build_right(self, right):
            right.columnconfigure(0, weight=1)
            self.stage = Stage(self, right)
            self._themed.append(self.stage)
            self.stage.cv.grid(row=0, column=0, sticky="ew")
            self.home_row = Flow(right)
            self.home_row.grid(row=1, column=0, sticky="ew", pady=(4, 0))
            self.chips = {}
            self.meters = tk.Canvas(right, highlightthickness=0, bd=0, height=20 * max(1, len(cast.regulars())))
            self.paint(self.meters, bg="bg")
            self.meters.grid(row=2, column=0, sticky="ew", pady=(2, 2))
            self.meters.bind("<Configure>", lambda _e: self._update_meters())
            logf = self.frame(right, "surface", highlightthickness=2)
            self.paint(logf, highlightbackground="line", highlightcolor="line")
            logf.grid(row=3, column=0, sticky="nsew", pady=2)
            right.rowconfigure(3, weight=1)
            self.log = tk.Text(logf, height=3, width=34, wrap="word", state="disabled", relief="flat", padx=10, pady=6,
                               borderwidth=0, font=self.fonts["body"], highlightthickness=0)
            lsb = ttk.Scrollbar(logf, orient="vertical", command=self.log.yview)
            self.log.configure(yscrollcommand=lsb.set)
            self.log.pack(side="left", fill="both", expand=True)
            lsb.pack(side="left", fill="y")
            self.act_flow = Flow(right)
            self.act_flow.grid(row=4, column=0, sticky="ew", pady=(2, 0))
            self.compact = False
            self._build_actions()
            er = self.frame(right)
            er.grid(row=5, column=0, sticky="ew", pady=(4, 0))
            self.entry = ttk.Entry(er, style="Search.TEntry", font=self.fonts["body"])
            self.entry.pack(side="left", fill="x", expand=True)
            self.entry.bind("<Return>", self.chat)
            self.button(er, "Send", self.chat, "primary", small=True).pack(side="left", padx=(4, 0))
            self._build_home_row()

        def _build_home_row(self):
            self.home_row.clear()
            self.chips = {}
            for cid in cast.regulars():
                chip = tk.Frame(self.home_row, highlightthickness=2, cursor="hand2")
                dot = tk.Canvas(chip, width=14, height=14, highlightthickness=0, bd=0)
                dot.pack(side="left", padx=(8, 4))
                name = tk.Label(chip, text=cast.name(cid), font=self.fonts["tag"])
                name.pack(side="left")
                where = tk.Label(chip, text="", font=self.fonts["small"])
                where.pack(side="left", padx=(4, 4))
                btn = self.button(chip, "Invite", lambda c=cid: self.toggle_presence(c), "soft", on="surface",
                                  small=True)
                btn.pack(side="left", padx=(0, 2))
                for w in (chip, dot, name, where):
                    w.bind("<Button-1>", lambda _e, c=cid: self.toggle_presence(c))
                self.chips[cid] = {"frame": chip, "dot": dot, "name": name, "where": where, "button": btn}
                self.home_row.add(chip, padx=2, pady=2)

        def _tools(self):
            return [("Joke", self.act_joke), ("Suggest", self.act_suggest), ("Rankings", self.act_rankings),
                    ("Fortune", self.act_fortune), ("Study break", self.act_study), ("Wrapped", self.act_wrapped)]

        def _build_actions(self):
            """Activities (from pets.json) and tools. Short windows fold them into two menus to keep the log visible."""
            acts = self.act_flow
            acts.clear()
            self._group_buttons = []
            activities = [(str(a.get("verb", n) if isinstance(a, dict) else n), (lambda n=n: self.do_activity(n)))
                          for n, a in self.brain.activities().items()]
            for text, fn, variant in [("Hang out", self.hang_out, "primary"), ("Everyone", self.everyone, "secondary"),
                                      ("Surprise me", self.surprise, "secondary")]:
                self._group_buttons.append(acts.add(self.button(acts, text, fn, variant, small=True), padx=1, pady=1))
            if self.compact:
                for text, items in (("Activities ▾", activities), ("Ask ▾", self._tools())):
                    acts.add(self.button(acts, text, None, "ghost", small=True), padx=0, pady=1)
                    b = acts.items[-1][0]
                    b.configure(command=lambda b=b, items=items: self._popup(b, items))
            else:
                for text, fn in activities:
                    acts.add(self.button(acts, text, fn, "secondary", small=True), padx=1, pady=1)
                for text, fn in self._tools():
                    acts.add(self.button(acts, text, fn, "ghost", small=True), padx=0, pady=1)
            self._update_chips()

        def _popup(self, anchor, items):
            c = self.c
            menu = tk.Menu(self, tearoff=False, bg=c["surface"], fg=c["ink"], activebackground=c["primary_soft"],
                           activeforeground=c["ink"], font=self.fonts["body"], bd=1, relief="solid")
            for text, fn in items:
                menu.add_command(label=text, command=fn)
            try:
                menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
            finally:
                menu.grab_release()

        def _bind_keys(self):
            for seq, fn in (("<Control-r>", self.refresh), ("<Control-p>", self.plan), ("<Control-s>", self.sync_card),
                            ("<Control-f>", self.focus_search), ("<F1>", self.show_help), ("<F2>", self.toggle_theme)):
                self.bind_all(seq, lambda e, fn=fn: (fn(), "break")[1])

        def focus_search(self, _e=None):
            self.search.focus_set()
            self.search.select_range(0, "end")

        def show_help(self, _e=None):
            self.show_info("Pawtation help", "Keyboard shortcuts\n\n" + "\n".join(f"{k}:  {v}" for k, v in SHORTCUTS)
                           + "\n\nThe ☾ button in the header is the optional After Dark setting (18+, off by default).")

        # ---------- theme ----------
        def _style_ttk(self):
            c, s, f = self.c, self._style, self.fonts
            s.configure(".", background=c["bg"], foreground=c["ink"], fieldbackground=c["surface"],
                        bordercolor=c["line"], lightcolor=c["surface"], darkcolor=c["surface"],
                        troughcolor=c["primary_soft"], focuscolor=c["focus"], insertcolor=c["ink"],
                        selectbackground=c["selection"], selectforeground=c["selection_ink"], font=f["body"])
            s.configure("TFrame", background=c["bg"])
            s.configure("TLabel", background=c["bg"], foreground=c["ink"])
            for name in ("TEntry", "Search.TEntry"):
                s.configure(name, fieldbackground=c["surface"], foreground=c["ink"], bordercolor=c["line"],
                            lightcolor=c["line"], darkcolor=c["line"], insertcolor=c["ink"], padding=(10, 6))
                s.map(name, bordercolor=[("focus", c["focus"])], lightcolor=[("focus", c["focus"])],
                      darkcolor=[("focus", c["focus"])], fieldbackground=[("disabled", c["disabled"])])
            s.configure("Treeview", background=c["surface"], fieldbackground=c["surface"], foreground=c["ink"],
                        rowheight=self.size("row"), bordercolor=c["line_soft"], font=f["body"])
            s.map("Treeview", background=[("selected", c["selection"])],
                  foreground=[("selected", c["selection_ink"])])
            s.configure("Treeview.Heading", background=c["surface_alt"], foreground=c["ink"], font=f["heading"],
                        relief="flat", padding=(6, 4), bordercolor=c["line_soft"], lightcolor=c["surface_alt"],
                        darkcolor=c["surface_alt"])
            s.map("Treeview.Heading", background=[("active", c["primary_soft"])])
            for orient in ("Vertical", "Horizontal"):
                s.configure(f"{orient}.TScrollbar", background=c["surface_alt"], troughcolor=c["surface"],
                            bordercolor=c["line_soft"], arrowcolor=c["ink"], lightcolor=c["surface_alt"],
                            darkcolor=c["surface_alt"])
                s.map(f"{orient}.TScrollbar", background=[("active", c["primary_soft"])])
            s.configure("Chunky.Horizontal.TProgressbar", background=c["primary"], troughcolor=c["primary_soft"],
                        bordercolor=c["line"], lightcolor=c["primary"], darkcolor=c["primary"],
                        thickness=self.size("progress"))
            for variant, (fill, hover, active, border, ink, hover_ink) in VARIANTS.items():
                on = c["bg"]
                role = lambda r: on if r is None else theme.mix(c["header"], c["keyline"], 0.3) if r == "@header_hover" else c[r]
                for prefix, font, pad in (("", f["body_strong"], (16, 6)), ("Small.", f["tag"], (12, 3))):
                    name = f"{prefix}{variant.capitalize()}.TButton"
                    s.configure(name, background=role(fill), foreground=c[ink], bordercolor=role(border or fill),
                                lightcolor=role(fill), darkcolor=role(fill), font=font, padding=pad,
                                focuscolor=c["focus"], relief="solid", borderwidth=2)
                    s.map(name, background=[("disabled", c["disabled"]), ("pressed", role(active)),
                                            ("active", role(hover))],
                          foreground=[("disabled", c["disabled_ink"]), ("pressed", c[hover_ink]),
                                      ("active", c[hover_ink])],
                          bordercolor=[("disabled", c["line_soft"]), ("focus", c["focus"])],
                          lightcolor=[("disabled", c["disabled"])], darkcolor=[("disabled", c["disabled"])])

        def apply_theme(self, name, save=True):
            name = theme.resolve(name)
            self.theme_name = name
            self.c = c = theme.load(name)
            self.configure(bg=c["bg"])
            self._style_ttk()
            for w, roles in list(self._paints):
                try:
                    w.configure(**{k: c[v] for k, v in roles.items()})
                except tk.TclError:
                    pass
            self.log.configure(bg=c["surface"], fg=c["ink"], insertbackground=c["ink"],
                               selectbackground=c["selection"], selectforeground=c["selection_ink"])
            self.log.tag_configure("name", font=self.fonts["body_strong"], foreground=c["ink"])
            self.log.tag_configure("you", font=self.fonts["body_strong"], foreground=c["primary_text"])
            self.log.tag_configure("err", foreground=c["danger"])
            self.log.tag_configure("dir", foreground=c["ink_muted"], font=self.fonts["italic"])
            self.log.tag_configure("sys", foreground=c["ink_muted"])
            for cid in cast.characters():
                self.log.tag_configure("dot:" + cid, foreground=theme.character_colors(c, cid, cast.character(cid))[0])
            self.tree.tag_configure("odd", background=c["surface_alt"])
            self.tree.tag_configure("even", background=c["surface"])
            self.tree.tag_configure("pinned", foreground=c["primary_text"], font=self.fonts["body_strong"])
            self.tree.tag_configure("convert", foreground=c["ink_muted"], font=self.fonts["italic"])
            self._timer_colors()
            for w in list(self._themed):
                try:
                    w.retheme()
                except tk.TclError:
                    pass
            self.theme_btn.configure(text=f"{theme.label(name)} theme")
            self._update_moon()
            if hasattr(self, "chips"):
                self._update_chips()
                self._update_meters()
                self._update_strip()
                if self._loop_frames:
                    self._show_loop_frame()
            if save:
                try:
                    core.update_config(gui_theme=name)
                    self.cfg["gui_theme"] = name
                except OSError as e:
                    self.say(f"(could not save theme: {e})", "err")

        def toggle_theme(self, _e=None):
            names = theme.names()
            i = names.index(self.theme_name) if self.theme_name in names else 0
            self.apply_theme(names[(i + 1) % len(names)])

        # ---------- chat log + bubbles ----------
        def say(self, text, tag=None):
            """Append to the chat log; a character's line also shows as a bubble over that character."""
            for line in str(text).split("\n"):
                if not line.strip():
                    continue
                self._log_line(line, tag)

        def _log_line(self, line, tag=None):
            self.log.configure(state="normal")
            cid, body = split_line(line) if tag is None else ("", line)
            if tag is None and line.lstrip().lower().startswith("you:"):
                tag = "you"
            if tag:
                self.log.insert("end", line + "\n", tag)
            elif cid is None:
                self.log.insert("end", body + "\n", "dir")
            elif cid:
                self.log.insert("end", "● ", "dot:" + cid)
                self.log.insert("end", cast.name(cid) + ": ", "name")
                self.log.insert("end", body + "\n")
            else:
                self.log.insert("end", line + "\n")
            self.log.insert("end", "\n", "sys")
            self.log.see("end")
            self.log.configure(state="disabled")
            if cid and not tag and cid in self.stage.present():
                self.stage.speak(cid, body)

        def _empty_line(self):
            nova = cast.mains()[0] if cast.mains() else "nova"
            return (f"{cast.name(nova)}: The shelf is empty. Point me at your library folder and I will count every "
                    "disc. Twice.")

        def _update_meters(self):
            cv, c = self.meters, self.c
            cv.delete("all")
            w = max(300, cv.winfo_width())
            f, fs = self.fonts["tag"], self.fonts["small"]
            name_w = max([f.measure(cast.name(p)) for p in cast.regulars()] + [40]) + 8
            bar_w = max(40, int((w - 24 - name_w - 2 * (fs.measure("Affection") + fs.measure("20/20") + 24)) / 2))
            mh = self.size("meter")
            for i, cid in enumerate(cast.regulars()):
                y = 10 + i * 20
                fill, _ink = theme.character_colors(c, cid, cast.character(cid))
                cv.create_oval(2, y - 5, 12, y + 5, fill=fill, outline=c["line"])
                cv.create_text(18, y, text=cast.name(cid), anchor="w", fill=c["ink"], font=f)
                s = self.state.get("pets", {}).get(cid, {}) if isinstance(self.state.get("pets"), dict) else {}
                x = 18 + name_w
                for label, key, mx, col in (("Affection", "affection", 20, "primary"), ("Energy", "energy", 10, "gold")):
                    v = s.get(key, 0) if isinstance(s.get(key), (int, float)) else 0
                    cv.create_text(x, y, text=label, anchor="w", fill=c["ink_muted"], font=fs)
                    x += fs.measure("Affection") + 6
                    cv.create_rectangle(x, y - mh / 2, x + bar_w, y + mh / 2, fill=c["surface_alt"], outline=c["line"])
                    if v > 0:
                        cv.create_rectangle(x + 1, y - mh / 2 + 1, x + 1 + (bar_w - 2) * min(1.0, v / mx), y + mh / 2 - 1,
                                            fill=c[col], outline="")
                    x += bar_w + 6
                    cv.create_text(x, y, text=f"{v:g}/{mx}", anchor="w", fill=c["ink"], font=fs)
                    x += fs.measure("20/20") + 12

        _update_bars = _update_meters                         # v1 name

        def _update_chips(self):
            home, c = self.brain.home(), self.c
            for cid, ch in self.chips.items():
                if cid.startswith("_"):
                    continue
                here = cid in home
                bg = c["surface"] if here else c["bg"]
                ch["frame"].configure(bg=bg, highlightbackground=c["line"] if here else c["line_soft"],
                                      highlightcolor=c["focus"])
                fill, _ink = theme.character_colors(c, cid, cast.character(cid))
                ch["dot"].configure(bg=bg)
                ch["dot"].delete("all")
                ch["dot"].create_oval(2, 2, 12, 12, fill=fill if here else bg, outline=c["line"], width=2)
                ch["name"].configure(bg=bg, fg=c["ink"])
                ch["where"].configure(bg=bg, fg=c["ink_muted"], text="home" if here else "out")
                b = ch["button"]
                if isinstance(b, PillButton):
                    b.on, b.variant = ("surface", "secondary") if here else ("bg", "soft")
                b.configure(text="Send out" if here else "Invite", state="disabled" if self.syncing else "normal")
            for b in getattr(self, "_group_buttons", [])[1:]:     # Hang out stays available during a sync
                b.configure(state="disabled" if self.syncing else "normal")

        # ---------- presence ----------
        def _touch(self):
            self.last_action = time.time()

        def _after_brain(self, before=None):
            """Bring the stage and chips in line with who the brain says is home now."""
            now = self.brain.home()
            before = before if before is not None else self.stage.present()
            arrived = [p for p in now if p not in before]
            self.stage.set_cast(now, arrived)
            self._update_chips()
            self._update_meters()
            self._save()

        def step_presence(self, force=False):
            if not force and time.time() - self._last_step < PRESENCE_EVERY_S:
                return
            self._last_step = time.time()
            before = self.stage.present()
            change = cast.step(self.state, rng=self.brain.rng)
            if change.get("changed"):
                lines = self.brain.presence_lines(change)
                self._after_brain(before)
                for line in lines:
                    self.say(line)
            self.night = cast.time_when() == "night"

        def toggle_presence(self, cid):
            if self.syncing:
                return
            self._touch()
            before = self.stage.present()
            lines = self.brain.send_out([cid]) if cid in self.brain.home() else self.brain.invite([cid])
            self._after_brain(before)
            for line in lines:
                self.say(line)

        def everyone(self):
            self._touch()
            before = self.stage.present()
            lines = self.brain.everyone()
            self._after_brain(before)
            for line in lines:
                self.say(line)

        def surprise(self):
            self._touch()
            before = self.stage.present()
            change = cast.shuffle(self.state, rng=self.brain.rng)
            lines = self.brain.presence_lines(change)
            self._after_brain(before)
            for line in lines or [self.brain.home_line()]:
                self.say(line)

        def hang_out(self):
            self._touch()
            self.step_presence()
            self._scene_queue = list(self.brain.scene())
            self._cancel("scene")
            self._scene_next()

        def _scene_next(self):
            if not self._scene_queue:
                return
            line = self._scene_queue.pop(0)
            cid, body = split_line(line)
            if cid and cid in self.stage.present():
                self._log_line(line)
                self.stage.speak(cid, body, now=True)
            else:
                self.say(line)
            if self._scene_queue and not self.reduced:
                self._schedule("scene", SCENE_STEP_MS, self._scene_next)

        def advance(self):
            """Stage click: next hang-out line, else the next queued bubble."""
            if self._scene_queue:
                self._cancel("scene")
                self._scene_next()
            else:
                self.stage.advance()

        def pet_character(self, cid):
            if cast.role(cid) == "cameo":
                self.say(self.brain.say(cid, "greeting"))
                return
            acts = self.brain.activities()
            name = "pet" if "pet" in acts else next(iter(acts), None)
            if name:
                self.do_activity(name, pet=cid)

        # ---------- After Dark ----------
        def _update_moon(self):
            on = afterdark.is_unlocked(self.state)
            b = self.moon_btn
            if isinstance(b, PillButton):
                b.variant = "lit" if on else "outline"
            elif not self.plain:
                pass
            else:
                b.configure(style="Small." + ("Lit" if on else "Outline") + ".TButton")
            b.configure(text="☾ on" if on else "☾")

        def open_afterdark(self, _e=None):
            if afterdark.is_unlocked(self.state):
                if self.ask_afterdark_unlocked():
                    self._close_sealed()
                    afterdark.lock(self.state)
                    self.brain.unlocked()                      # drops the tier from memory
                    self._save()
                    self.stage.forget_images()
                    self.say("After Dark is locked again.", "sys")
            else:
                state = self.state

                def check(text):
                    born = afterdark.parse_date(text)
                    ok, message = afterdark.unlock(state, born)
                    self._save()
                    return ok, message

                if self.ask_birthdate(check) and afterdark.is_unlocked(self.state):
                    self.stage.forget_images()
                    self.say("After Dark is on. The moon button locks it again at any time.", "sys")
            self._update_moon()
            self.stage.relayout(redraw=True)

        # ---------- section 9 (docs/SPEC_V2.md) ----------
        # Nothing here creates a widget, label, menu entry or log line until the right code has been typed.
        def _sealed_prompt_open(self):
            """A bare, untitled prompt holding one masked entry. Enter submits; Escape or closing dismisses."""
            old = getattr(self, "_sealed_prompt", None)
            if old is not None:
                try:
                    old.destroy()
                except tk.TclError:
                    pass
            c = self.c
            win = tk.Toplevel(self)
            win.withdraw()
            win.title("")
            win.transient(self)
            win.configure(bg=c["bg"])
            win.resizable(False, False)
            card = tk.Frame(win, bg=c["surface"], highlightthickness=2, highlightbackground=c["line"],
                            highlightcolor=c["line"])
            card.pack(fill="both", expand=True, padx=self.space(4), pady=self.space(4))
            var = tk.StringVar(win)
            entry = tk.Entry(card, textvariable=var, show="•", width=14, font=self.fonts["body"], relief="flat",
                             bg=c["surface_alt"], fg=c["ink"], insertbackground=c["ink"], highlightthickness=0)
            entry.pack(padx=self.space(5), pady=self.space(5))

            def dismiss(_e=None):
                var.set("")
                self._sealed_prompt = None
                try:
                    win.destroy()
                except tk.TclError:
                    pass

            def submit(_e=None):
                text = var.get()
                dismiss()
                ok = hidden.try_open(self.state, text)
                text = None
                self._save()                                   # the throttle survives a restart
                if ok:
                    self._sealed_window_open()
                return "break"

            entry.bind("<Return>", submit)
            win.bind("<Escape>", dismiss)
            win.protocol("WM_DELETE_WINDOW", dismiss)
            win.update_idletasks()
            x = self.winfo_rootx() + max(0, (self.winfo_width() - win.winfo_reqwidth()) // 2)
            y = self.winfo_rooty() + max(0, (self.winfo_height() - win.winfo_reqheight()) // 3)
            win.geometry(f"+{x}+{y}")
            win.deiconify()
            entry.focus_force()
            self._sealed_prompt = win
            self._sealed_entry = entry
            return win

        def _sealed_window_open(self):
            """The opened section: pack list, a gallery for the selected pack, and a scene button."""
            if getattr(self, "_sealed_win", None) is not None:
                try:
                    self._sealed_win.lift()
                    return self._sealed_win
                except tk.TclError:
                    self._sealed_win = None
            self.stage.forget_images()                         # sprite overrides from the packs may apply now
            self.stage.relayout(redraw=True)
            c = self.c
            win = tk.Toplevel(self)
            win.title("The Hidden World")
            win.configure(bg=c["bg"])
            win.minsize(420, 260)
            self._sealed_win = win
            self._sealed_ui = ui = {"images": [], "i": 0, "img": None, "packs": hidden.packs()}
            win.protocol("WM_DELETE_WINDOW", self._close_sealed)
            win.bind("<Escape>", lambda _e: self._close_sealed())
            card = tk.Frame(win, bg=c["surface"], highlightthickness=2, highlightbackground=c["line"],
                            highlightcolor=c["line"])
            card.pack(fill="both", expand=True, padx=self.space(6), pady=self.space(6))
            inner = tk.Frame(card, bg=c["surface"])
            inner.pack(fill="both", expand=True, padx=self.space(6), pady=self.space(5))
            tk.Label(inner, text="The Hidden World", bg=c["surface"], fg=c["ink"], font=self.fonts["title"],
                     anchor="w").pack(fill="x")
            if not ui["packs"]:
                ui["empty"] = tk.Label(inner, text="Nothing here yet.", bg=c["surface"], fg=c["ink_muted"],
                                       font=self.fonts["body"], anchor="w")
                ui["empty"].pack(fill="x", pady=(self.space(4), 0))
                foot = tk.Frame(inner, bg=c["surface"])
                foot.pack(fill="x", side="bottom", pady=(self.space(6), 0))
                self.button(foot, "Close", self._close_sealed, "secondary", on="surface").pack(side="right")
                return win
            body = tk.Frame(inner, bg=c["surface"])
            body.pack(fill="both", expand=True, pady=(self.space(4), 0))
            lb = tk.Listbox(body, exportselection=False, activestyle="none", width=22, relief="flat",
                            bg=c["surface_alt"], fg=c["ink"], selectbackground=c["primary_soft"],
                            selectforeground=c["ink"], highlightthickness=0, font=self.fonts["body"])
            for p in ui["packs"]:
                lb.insert("end", p["name"])
            lb.pack(side="left", fill="y")
            right = tk.Frame(body, bg=c["surface"])
            right.pack(side="left", fill="both", expand=True, padx=(self.space(5), 0))
            ui["view"] = tk.Label(right, text="", bg=c["surface_alt"], fg=c["ink_muted"], font=self.fonts["body"],
                                  width=48, height=16)
            ui["view"].pack(fill="both", expand=True)
            nav = tk.Frame(right, bg=c["surface"])
            nav.pack(fill="x", pady=(self.space(3), 0))
            ui["prev"] = self.button(nav, "Previous", lambda: self._sealed_show(-1), "secondary", on="surface", small=True)
            ui["prev"].pack(side="left")
            ui["count"] = tk.Label(nav, text="", bg=c["surface"], fg=c["ink_muted"], font=self.fonts["small"])
            ui["count"].pack(side="left", padx=self.space(3))
            ui["next"] = self.button(nav, "Next", lambda: self._sealed_show(1), "secondary", on="surface", small=True)
            ui["next"].pack(side="left")
            ui["play"] = self.button(nav, "Play a scene", self._sealed_play, "primary", on="surface", small=True)
            ui["play"].pack(side="right")
            ui["list"] = lb
            lb.bind("<<ListboxSelect>>", lambda _e: self._sealed_select())
            lb.selection_set(0)
            self._sealed_select()
            return win

        def _sealed_pack(self):
            ui = getattr(self, "_sealed_ui", None) or {}
            lb = ui.get("list")
            sel = lb.curselection() if lb is not None else ()
            return ui["packs"][sel[0]] if sel and sel[0] < len(ui.get("packs", [])) else None

        def _sealed_scenes(self, pack):
            if pack is None or not hidden.is_open():
                return []
            src = "pack:" + pack["path"].name
            return [s for s in cast.all_scenes(self.brain.unlocked()) if s["source"] == src and not s["needs"]]

        def _sealed_select(self):
            ui, pack = self._sealed_ui, self._sealed_pack()
            ui["images"], ui["i"] = (hidden.gallery(pack["path"]) if pack else []), 0
            state = "normal" if self._sealed_scenes(pack) else "disabled"
            ui["play"].configure(state=state)
            self._sealed_show(0)

        def _sealed_show(self, step):
            ui = self._sealed_ui
            files = ui["images"]
            if not files:
                ui["img"] = None
                ui["view"].configure(image="", text="No pictures.")
                ui["count"].configure(text="")
                return
            ui["i"] = (ui["i"] + step) % len(files)
            img = None
            try:
                img = tk.PhotoImage(master=self._sealed_win, file=str(files[ui["i"]]))
                w, h = max(1, ui["view"].winfo_width()), max(1, ui["view"].winfo_height())
                w, h = max(w, 360), max(h, 280)
                k = max(1, -(-img.width() // w), -(-img.height() // h))
                if k > 1:
                    img = img.subsample(k, k)
            except (tk.TclError, OSError):
                img = None
            ui["img"] = img                                    # keep a reference or Tk drops the picture
            if img is None:
                ui["view"].configure(image="", text="(could not show " + files[ui["i"]].name + ")")
            else:
                ui["view"].configure(image=img, text="")
            ui["count"].configure(text=f"{ui['i'] + 1} / {len(files)}")

        def _sealed_play(self):
            scenes = self._sealed_scenes(self._sealed_pack())
            if not scenes:
                return
            scene = self.brain.rng.choice(scenes)
            self._scene_queue = cast.play(scene)
            self._cancel("scene")
            self._scene_next()

        def _close_sealed(self):
            """Lock section 9 again and drop everything it brought in (content, sprites, queued scene lines)."""
            was = hidden.is_open() or getattr(self, "_sealed_win", None) is not None
            hidden.close()
            win, self._sealed_win, self._sealed_ui = getattr(self, "_sealed_win", None), None, None
            if win is not None:
                try:
                    win.destroy()
                except tk.TclError:
                    pass
            if was and not self._closing:
                self._scene_queue = []
                self._cancel("scene")
                self.stage.forget_images()
                self.stage.relayout(redraw=True)

        # ---------- pet features ----------
        def _save(self):
            core.save_state(self.state)

        def _pet_call(self, name, *args):
            """Call an optional PetBrain feature; returns None if the build lacks it."""
            fn = getattr(self.brain, name, None)
            return fn(*args) if callable(fn) else None

        def _say_feature(self, name, *args):
            self._touch()
            self.step_presence()
            before = self.stage.present()
            out = self._pet_call(name, *args)
            if out is None:
                self.say(f"(This build has no '{name}' yet.)", "sys")
            else:
                self.say("\n".join(out) if isinstance(out, (list, tuple)) else str(out))
            self._after_brain(before)

        def act_joke(self): self._say_feature("joke")
        def act_suggest(self): self._say_feature("suggest", self.roms)
        def act_rankings(self): self._say_feature("ranking", self.roms)
        def act_fortune(self): self._say_feature("fortune")
        def act_study(self): self._say_feature("study_break")
        def act_wrapped(self): self._say_feature("wrapped", self.roms)

        def do_activity(self, name, pet=None):
            self._touch()
            self.step_presence()
            pet = pet if pet in self.brain.speakers() else self.brain.rng.choice(self.brain.speakers())
            self.say(self.brain.activity(pet, name))
            self._save()
            self._update_meters()
            mood = self.brain.mood(pet)
            self.stage.play(pet, "sleep" if mood == "sleep" else "happy", 2.0)
            if name == "pet":
                self.stage.prop(pet, "heart")

        def chat(self, _evt=None):
            t = self.entry.get().strip()
            if not t:
                return
            if hidden.check_code(self.state, t):               # swallowed: never logged, never answered
                self.entry.delete(0, "end")
                t = None
                self._sealed_prompt_open()
                return
            self._touch()
            self.entry.delete(0, "end")
            self.say("You: " + t, "you")
            self.step_presence()
            before = self.stage.present()
            reply = self.brain.reply(t, self.roms, self.saves)
            self._after_brain(before)
            self.say(reply)
            self._update_meters()

        # ---------- game list ----------
        def _where(self):
            return {k: cid for cid, keys in core.current_plan(self.state).items() for k in keys}

        def _row(self, r, where):
            stars = int(self.state["ratings"].get(r.key, 0) or 0)
            pinned = r.key in self.cfg["pinned"]
            return dict(fav="♥" if pinned else "", game=r.title, card=where.get(r.key, "-"), size=core.fmt_gb(r.size),
                        discs=len(r.discs), rating=("★" * stars + "☆" * (5 - stars)) if stars else "",
                        tags=", ".join(r.tags) if r.launchable else "⚠ convert to .iso first")

        def _sort_value(self, r, where, col):
            if col == "fav": return 0 if r.key in self.cfg["pinned"] else 1
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
            if q:
                self.search_hint.place_forget()
            else:
                self.search_hint.place(in_=self.search, x=10, rely=0.5, anchor="w")
            rows = [r for r in self.roms if not q or q in r.title.lower() or q in r.key
                    or any(q in t.lower() for t in r.tags) or q == str(where.get(r.key, "")).lower()]
            rows.sort(key=lambda r: (self._sort_value(r, where, self.sort_col), r.title.lower()), reverse=self.sort_rev)
            self.tree.delete(*self.tree.get_children())
            for i, r in enumerate(rows):
                d = self._row(r, where)
                tags = ["odd" if i % 2 else "even"]
                if r.key in self.cfg["pinned"]:
                    tags.append("pinned")
                if not r.launchable:
                    tags.append("convert")
                self.tree.insert("", "end", iid=r.key, values=[d[c[0]] for c in self.COLUMNS], tags=tags)
            if sel and self.tree.exists(sel):
                self.tree.selection_set(sel)
            for cid, text, *_ in self.COLUMNS:
                arrow = (" ▲" if not self.sort_rev else " ▼") if cid == self.sort_col else ""
                self.tree.heading(cid, text=text + arrow)
            self._fit_columns()
            self._sync_pin_button()
            if not self.roms:
                lib = self.cfg.get("library_dir")
                self._show_empty("The shelf is empty." if not lib else "No disc images found.",
                                 ("Point Pawtation at your library folder and it will count every disc.\n"
                                  "Nothing is copied or changed until you press Sync.") if not lib else
                                 f"Nothing in {lib} looks like a GameCube disc image. Pick another folder?",
                                 "Pick library folder", self.pick_library)
            elif not rows:
                self._show_empty("Nothing matches that.", "Try fewer words, or clear the filter.", "Clear search",
                                 lambda: self.search_var.set(""))
            else:
                self.empty.place_forget()
            pinned = sum(1 for r in self.roms if r.key in self.cfg["pinned"])
            self.status.set(f"✓ {len(rows)}/{len(self.roms)} games shown · {pinned} pinned · library: "
                            f"{self.cfg.get('library_dir') or '(not set)'}"
                            + (" · reduced motion" if self.reduced else ""))

        def _show_empty(self, title, body, button, fn):
            self.empty_title.configure(text=title)
            self.empty_body.configure(text=body)
            self.empty_btn.configure(text=button, command=fn)
            self.empty.place(relx=0.5, rely=0.55, anchor="center")
            self.empty.lift()

        def selected_key(self):
            sel = self.tree.selection() if hasattr(self, "tree") else ()
            return sel[0] if sel else None

        def _rom(self, key):
            return next((r for r in self.roms if r.key == key), None)

        def _sync_pin_button(self):
            key = self.selected_key()
            self.pin_btn.configure(text="♥ Unpin favourite" if key and key in self.cfg["pinned"] else "♥ Pin favourite")

        def _update_strip(self):
            flow, c = self.chips_cards, self.c
            flow.clear()
            by = {r.key: r for r in self.roms}
            plan = core.current_plan(self.state)
            ids = sorted(set(self.cfg["cards"]) | set(plan), key=card_sort_key)
            if not ids:
                flow.add(self.label(flow, "No SD cards set up yet (config.json -> cards). I will do the maths.",
                                    "bg", "ink_muted", "small"))
                return
            for cid in ids:
                card = self.cfg["cards"].get(cid)
                used = sum(by[k].size for k in plan.get(cid, []) if k in by)
                cap_gb = float(card.get("capacity_gb", 0) or 0) if card else 0.0
                label = card.get("label", f"Card {cid}") if card else f"Card {cid}"
                if not card:
                    status, fg, bg, border = "not set up", "disabled_ink", "disabled", "line_soft"
                elif cap_gb and used > cap_gb * 1024 ** 3:
                    status, fg, bg, border = "⚠ too full", "danger", "surface", "line"
                elif cid in self._mounted:
                    status, fg, bg, border = "● inserted", "success", "primary_soft", "line"
                elif plan.get(cid):
                    status, fg, bg, border = f"{len(plan[cid])} planned", "ink_muted", "surface", "line"
                else:
                    status, fg, bg, border = "empty", "ink_muted", "surface", "line"
                chip = tk.Frame(flow, bg=c[bg], highlightthickness=2, highlightbackground=c[border])
                tk.Label(chip, text=f"{label}  {fmt_bytes(used)} / {cap_gb:g} GB" if card else label, bg=c[bg],
                         fg=c["ink"] if card else c["disabled_ink"], font=self.fonts["tag"]).pack(anchor="w", padx=8)
                tk.Label(chip, text=status, bg=c[bg], fg=c[fg], font=self.fonts["small"]).pack(anchor="w", padx=8)
                flow.add(chip, padx=2, pady=2)

        def refresh(self, announce=False):
            self.cfg = core.load_config()
            self.roms = core.scan_library(self.cfg, self.cat)
            self.saves = saves.scan_saves(self.cfg.get("saves_dir", ""))
            try:
                self._mounted = core.find_cards()
            except Exception:
                self._mounted = {}
            self._update_strip()
            self._populate()
            if announce:
                for line in (self.brain.collection(self.roms) if self.roms else [self._empty_line()]):
                    self.say(line)
            return self.roms

        def on_game_double(self, _evt=None):
            key = self.selected_key()
            if not key:
                return
            self._touch()
            rom = self._rom(key)
            title = rom.title if rom else key
            home = self.brain.speakers()
            pet = self.brain.rng.choice(home)
            lines = self.brain.game_scene(key)
            if lines:
                self._scene_queue = list(lines)
                self._scene_next()
                return
            q = self.brain.game_quip(pet, key) or next((self.brain.game_quip(p, key) for p in home if p != pet
                                                        and self.brain.game_quip(p, key)), None)
            self.say(q or self.brain._line(pet, f"{title}. No strong feelings yet. Rate it and I might."))

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
            self.status.set(f"Rated {title}: {n} of 5 stars.")
            home = self.brain.speakers()
            first = self.brain.rng.choice(home)
            self.say(self.brain.say(first, "ranked", game=title))
            other = next((p for p in home if p != first), None)
            if other:
                q = self.brain.game_quip(other, key)
                if q:
                    self.say(q)

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

        def plan(self, _e=None):
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
            if self.ask_yes_no("New rotation", text + "\n\nCommit this plan and restart the timer? Nothing is copied "
                                                      "until you sync a card."):
                core.commit_plan(self.state, plan)
                plugins.fire("planned", plan=plan, roms=self.roms)
                self._save()
                self.refresh()
                self._tick(reschedule=False)
                self.hide_banner()
                for line in self.brain.event("rotated"):
                    self.say(line)
                for p in self.stage.present():
                    self.stage.play(p, "happy", 2.0)

        # ---------- countdown ----------
        def _tick(self, reschedule=True):
            if self._closing:
                return
            due, rem = core.rotation_due(self.cfg, self.state)
            if due:
                self.timer_var.set("◆ Rotation due")
                self._mark_due()
            else:
                self.timer_var.set("Next rotation in " + core.fmt_remaining(rem))
                self._unmark_due()
            if reschedule:
                try:
                    self.step_presence()
                except Exception:
                    pass
                self._schedule("tick", 30000, self._tick)

        def _mark_due(self):
            if self._due_marked:
                return
            self._due_marked = True
            self._timer_colors()
            if not self._nagged:                               # nag ONCE per app session
                self._nagged = True
                self.banner.grid(row=0, column=0, sticky="ew", pady=(0, 6))
                lines = self._pet_call("due_nag") or self.brain.duo("rotation_due", days=0)
                for line in lines:
                    self.say(line)
            if self.reduced:
                self.title(PAW + self.base_title)
            else:
                self._flash_left = 10
                self._flash()

        def hide_banner(self):
            self.banner.grid_remove()

        def _unmark_due(self):
            if not self._due_marked:
                return
            self._due_marked = False
            self._flash_left = 0
            self._cancel("flash")
            self.title(self.base_title)
            self._timer_colors()

        def _flash(self):
            if self._closing or not self._due_marked:
                return
            if self._flash_left > 0:
                self._flash_left -= 1
                self.title(self.base_title if self.title().startswith(PAW) else PAW + self.base_title)
                self._schedule("flash", 1000, self._flash)
            else:
                self.title(PAW + self.base_title)              # stays marked

        # ---------- card picking ----------
        def pick_mount(self, cid, title=None):
            """Auto-detected mount first, then config, then a directory chooser. Offers to remember a chosen folder."""
            auto = core.find_cards().get(str(cid))
            if auto:
                return auto
            configured = self.cfg["cards"].get(str(cid), {}).get("mount")
            if configured and os.path.isdir(configured):
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
            if isinstance(self.prog, ChunkyBar):
                self.prog.set_busy(False)
            self._update_chips()
            if busy:
                self._start_loop()
            else:
                self._stop_loop()

        def _start_loop(self):
            self._loop_frames, self._loop_i = [], 0
            try:
                paths, fps = sprites.render_frames("sync_loop")
                for p in paths:
                    img = tk.PhotoImage(master=self, file=str(p))
                    if img.width() > 160:
                        img = img.subsample(2)
                    self._loop_frames.append(img)
                self._loop_fps = max(1, min(fps or 12, self.motion["sprite_fps_max"] or 12))
            except Exception:
                self._loop_frames = []
            if not self._loop_frames:
                return
            self.loop.grid(row=0, column=0, rowspan=3, padx=(8, 0), pady=6)
            self._show_loop_frame()
            if not self.reduced:
                self._schedule("loop", 1000 // self._loop_fps, self._loop_tick)

        def _show_loop_frame(self):
            self.loop.delete("all")
            if self._loop_frames:
                img = self._loop_frames[self._loop_i % len(self._loop_frames)]
                self.loop.configure(width=img.width(), height=img.height())
                self.loop.create_image(0, 0, image=img, anchor="nw")

        def _loop_tick(self):
            if not self.syncing or not self._loop_frames:
                return
            self._loop_i += 1
            self._show_loop_frame()
            self._schedule("loop", 1000 // self._loop_fps, self._loop_tick)

        def _stop_loop(self):
            self._cancel("loop")
            self._loop_frames = []
            self.loop.delete("all")
            self.loop.grid_remove()

        def sync_card(self, _e=None):
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
                    if not self.ask_yes_no("This card says it is a different card",
                                           "\n".join(rep["errors"]) + "\n\nUse this card anyway (re-purpose it)? "
                                           "Files Pawtation did not write are never touched."):
                        return
                    force = True
                    rep = core.sync_card(self.cfg, cid, keys, self.roms, mount, dry_run=True, log=lambda *_: None, force=True)
            except Exception as e:
                self.show_error("Sync", f"Could not check the card: {e}")
                return
            if rep["errors"] and not (rep["copied"] or rep["removed"]):
                self.show_error("Sync", "Cannot sync:\n" + "\n".join(rep["errors"]))
                return
            text = (f"Card {cid} at {mount}\nCopy {len(rep['copied'])}, remove {len(rep['removed'])}, keep {len(rep['kept'])}."
                    "\nThat was a dry run: nothing has been written yet.")
            if rep["errors"]:                                   # per-game problems: those games are skipped, the rest can go
                text += "\n\nWill be skipped:\n- " + "\n- ".join(rep["errors"])
            if rep["warnings"]:
                text += "\n\nWarnings:\n- " + "\n- ".join(rep["warnings"])
            if not self.ask_yes_no(f"Sync card {cid} for real?", text + "\n\nProceed?"):
                return
            self.start_sync(cid, keys, mount, force)

        def start_sync(self, cid, keys, mount, force=False):
            self.cancel_event.clear()
            self._sync_mount = mount
            self.sync_info = {}
            self._sync_started = time.time()
            self._set_busy(True)
            self.prog_var.set(0)
            if isinstance(self.prog, ChunkyBar):
                self.prog.set_busy(True)
            self.prog_text.set(f"Starting card {cid}...")
            self.eta_text.set("")
            quips = self._pet_call("card_quips", keys) if self.cfg.get("export_quips", True) else None
            cfg, roms = dict(self.cfg), list(self.roms)
            events, cancel = self.events, self.cancel_event

            def work():                                         # NEVER touch tkinter in here
                try:
                    rep = core.sync_card(cfg, cid, keys, roms, mount, dry_run=False, log=lambda *_: None,
                                         progress=lambda info: events.put(("progress", dict(info))),
                                         cancel=cancel.is_set, quips=quips, force=force)
                    events.put(("done", cid, rep))
                except BaseException as e:                      # reported via the queue
                    events.put(("error", cid, f"{type(e).__name__}: {e}\n{traceback.format_exc()}"))

            self.worker = threading.Thread(target=work, name="pawtation-sync", daemon=True)
            self.worker.start()
            self._schedule("poll", 100, self._poll_events)

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
            if self.syncing or not self.events.empty():
                self._schedule("poll", 100, self._poll_events)

        def _on_progress(self, info):
            self.sync_info = info
            phase = info.get("phase")
            total, done = info.get("all_total") or 0, info.get("all_done") or 0
            if isinstance(self.prog, ChunkyBar) and self.prog.busy and total:
                self.prog.set_busy(False)
            pct = 100.0 * done / total if total else 0
            self.prog_var.set(pct)
            title = info.get("title", "")
            if phase == "copy":
                self.prog_text.set(f"{pct:.0f}%  Copying {title}: {fmt_bytes(info.get('file_done', 0))} of "
                                   f"{fmt_bytes(info.get('file_total', 0))}")
            elif phase == "verify":
                self.prog_text.set(f"{pct:.0f}%  Verifying {title}")
            elif phase == "remove":
                self.prog_text.set(f"Removing {title or info.get('rel', '')}")
            elapsed = max(0.001, time.time() - self._sync_started)
            if done and total and phase in ("copy", "verify"):
                speed = done / elapsed
                self.eta_text.set(f"{fmt_bytes(done)} of {fmt_bytes(total)} · {speed / 1024 ** 2:.1f} MB/s · about "
                                  f"{fmt_eta((total - done) / speed)} left")

        def _on_done(self, cid, rep):
            self.last_report = rep
            self._set_busy(False)
            self.worker = None
            self.prog_var.set(100 if not rep.get("cancelled") else self.prog_var.get())
            for e in rep["errors"]:
                self.say("✕ " + e, "err")
            for w in rep["warnings"]:
                self.say("⚠ " + w, "err")
            if rep.get("cancelled"):
                self.prog_text.set("Cancelled. Finished files stay on the card; run sync again to resume.")
                self.eta_text.set("Nothing is deleted that Pawtation did not put there.")
            else:
                self.prog_text.set(f"✓ Card {cid} synced: copied {len(rep['copied'])}, removed {len(rep['removed'])}, "
                                   f"kept {len(rep['kept'])}.")
                self.eta_text.set("")
                if not rep["errors"]:
                    for line in self.brain.event("synced", card=cid):
                        self.say(line)
                    for p in self.stage.present():
                        self.stage.play(p, "happy", 2.4)
                    plugins.fire("synced", card_id=cid, report=rep, mount=self._sync_mount)
            self.refresh()

        def _on_worker_error(self, cid, text):
            self._set_busy(False)
            self.worker = None
            self.prog_text.set("✕ Sync failed. Files Pawtation did not write are never touched.")
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
