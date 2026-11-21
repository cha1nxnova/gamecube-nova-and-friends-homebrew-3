"""Pawtation core: config, library scan, catalog matching, rotation planner, SD sync.

Pure standard library. No network (the optional Swiss download lives in swissget.py). Everything here is UI-agnostic so the CLI,
the desktop GUI, and any future front-end (web, GameCube-side) share one brain.
"""
from __future__ import annotations

import json
import math
import os
import random
import re
import shutil
import string
import sys
import time
import zlib
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from . import discimage, paths

ROOT = paths.ROOT                    # your own files: config, state, packs/, mods/, plugins/ (next to Pawtation.exe when packaged)
BUNDLE = paths.BUNDLE                # files that ship with the app and are only read: data/, assets/
DATA_DIR = BUNDLE / "data"
# Your settings + ratings live next to the app by default. Set PAWTATION_HOME to keep them elsewhere
# (handy for a second profile, or for tests that must not touch your real files).
HOME = Path(os.environ.get("PAWTATION_HOME") or ROOT)
CONFIG_PATH = HOME / "config.json"
STATE_PATH = HOME / "state.json"
MANIFEST_NAME = ".pawtation.json"   # written to each SD card root; only files listed here are ever deleted

DEFAULT_CONFIG = {
    "library_dir": "",                       # folder holding your legally acquired disc images
    "extensions": [".iso", ".gcm", ".ciso", ".gcz", ".rvz", ".wia"],   # compressed ones are listed, never copied
    "games_subdir": "games",                 # folder on the SD card Swiss scans
    "rotation_days": 14,                     # length of one rotation "season"
    "reserve_mb": 256,                       # free space left on each card (Swiss, saves, slack)
    "seed": 0,                               # 0 = different shuffle each season, else fixed
    "max_games_per_card": 0,                 # 0 = unlimited, otherwise hard cap
    # Boot card: a SEPARATE small standard SD (<= 2 GB; the Action Replay SD Media Launcher does not read SDHC/SDXC)
    # holding Swiss as autoexec.dol. Never rotated. Boot from it, then swap in a game card and refresh Swiss.
    "boot_card": {"label": "Boot card (<=2GB)", "mount": "", "swiss_dol": ""},
    "saves_dir": "",                         # folder of exported .gci saves (GC2SD adapters cannot hold saves; use a real memory card)
    "mods_dir": "",                          # per-game extras staged onto cards (default: <app>/mods). See docs/MODDING.md
    "verify_copies": False,                  # re-read every copied file and compare checksums (slower, safer)
    "export_quips": True,                    # write /pawtation/quips.txt on each card for a future on-console companion
    # Add a card by adding an entry. The planner/GUI/CLI adapt automatically.
    "cards": {
        "1": {"label": "Card 1", "capacity_gb": 8, "mount": ""},
        "2": {"label": "Card 2", "capacity_gb": 8, "mount": ""},
        "3": {"label": "Card 3", "capacity_gb": 8, "mount": ""},
        "4": {"label": "Card 4", "capacity_gb": 8, "mount": ""},
        "5": {"label": "Card 5", "capacity_gb": 8, "mount": ""},
    },
    # Favorites are pinned one-per-card in this order (title keys from catalog.json).
    "pinned": ["paper-mario-ttyd", "animal-crossing", "soulcalibur-ii",
               "mario-kart-double-dash", "chibi-robo"],
}


# ---------- json helpers ----------
def load_json(path: Path, default):
    """Read JSON; a missing, unreadable or corrupt file yields `default` (never raises)."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default
    return data if default is None or isinstance(data, type(default)) else default


def save_json(path: Path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(obj, indent=2, ensure_ascii=False))
        f.flush()
        os.fsync(f.fileno())                 # the card manifest lives on removable media: be on disk before the rename
    os.replace(tmp, path)


def load_config() -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    user = load_json(CONFIG_PATH, {})
    for k, v in user.items():
        if k != "cards" and isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)                 # nested settings (boot_card): keep defaults for keys the user omitted
        else:
            cfg[k] = v                       # "cards" is replaced whole: the user's list IS the list
    if not isinstance(cfg.get("cards"), dict):
        cfg["cards"] = {}
    if not isinstance(cfg.get("pinned"), list):
        cfg["pinned"] = []
    for k in ("boot_card",):                 # nested settings must stay dicts ("boot_card": "E:\\" would crash callers)
        if not isinstance(cfg.get(k), dict):
            cfg[k] = dict(DEFAULT_CONFIG[k])
    return cfg


def update_config(**changes) -> dict:
    """Change a few keys in the user's config.json without rewriting the rest. Returns the fresh merged config."""
    user = load_json(CONFIG_PATH, None)
    if not isinstance(user, dict):
        if CONFIG_PATH.exists():                 # unreadable/corrupt: keep the user's text rather than silently wiping it
            shutil.copyfile(CONFIG_PATH, CONFIG_PATH.with_name(CONFIG_PATH.name + ".bak"))
        user = {}
    user.update(changes)
    save_json(CONFIG_PATH, user)
    return load_config()


def mods_dir(cfg) -> Path:
    return Path(cfg.get("mods_dir") or (ROOT / "mods"))


def load_state() -> dict:
    from . import afterdark, cast         # imported here: cast imports this module
    st = load_json(STATE_PATH, {})
    st.setdefault("ratings", {})          # key -> 1..5
    st.setdefault("history", [])          # list of {"ts","season","plan"}
    st.setdefault("last_rotation_ts", 0)
    st.setdefault("last_on_card", {})     # key -> ts it last got loaded onto any card
    st.setdefault("pets", {})             # cast id -> {"affection", "energy"} for every non-cameo character
    st.setdefault("plays", {})            # key -> manual play count (GUI "I played this" button)
    cb = st.get("card_bytes")                    # card id -> measured bytes (note_card_size); anything odd is dropped
    st["card_bytes"] = {str(k): int(v) for k, v in cb.items() if isinstance(v, (int, float)) and not isinstance(v, bool)
                        and math.isfinite(v) and 0 < v < 2**62} if isinstance(cb, dict) else {}
    for k, kind in (("ratings", dict), ("history", list), ("last_on_card", dict), ("pets", dict), ("plays", dict)):
        if not isinstance(st[k], kind):          # a hand-edited or damaged state.json must not take the app down
            st[k] = kind()
    st["ratings"] = {k: int(v) for k, v in st["ratings"].items() if isinstance(v, (int, float)) and 1 <= v <= 5}
    st["last_on_card"] = {k: v for k, v in st["last_on_card"].items() if isinstance(v, (int, float))}
    st["history"] = [h for h in st["history"] if isinstance(h, dict) and isinstance(h.get("plan"), dict)]
    if not isinstance(st["last_rotation_ts"], (int, float)):
        st["last_rotation_ts"] = 0
    for pet in cast.regulars():           # entries for anyone else (v1's mochi / biscuit) are left as they are
        p = st["pets"].get(pet)
        if not (isinstance(p, dict) and all(isinstance(p.get(f), (int, float)) for f in ("affection", "energy"))):
            st["pets"][pet] = {"affection": 5, "energy": 5}
    st["scene"] = cast.clean_scene_state(st.get("scene"))           # who is home: {"who": [ids], "until": ts, "manual": bool}
    st["afterdark"] = afterdark.clean_state(st.get("afterdark"))    # {"unlocked": False} or {"unlocked": True, "confirmed_on"}
    if "hw" in st:                                                  # SPEC_V2 section 9; damaged = not configured
        from . import hidden
        hw = hidden.clean_state(st["hw"])
        if hw is None:
            st.pop("hw")
        else:
            st["hw"] = hw
    return st


def save_state(st):
    save_json(STATE_PATH, st)


# ---------- catalog ----------
def load_catalog() -> list[dict]:
    games = load_json(DATA_DIR / "catalog.json", {"games": []}).get("games", [])
    return clean_catalog(games)


def clean_catalog(games) -> list[dict]:
    """Drop or repair malformed entries so one bad hand edit cannot stop the app from starting."""
    out = []
    for g in games if isinstance(games, list) else []:
        if not (isinstance(g, dict) and isinstance(g.get("key"), str) and isinstance(g.get("title"), str)
                and g["key"] and g["title"]):
            continue
        g = dict(g)
        for k in ("aliases", "tags", "genres"):
            g[k] = [x for x in g.get(k) or [] if isinstance(x, str)] if isinstance(g.get(k), list) else []
        if not (isinstance(g.get("code4"), str) and len(g["code4"]) == 4):
            g.pop("code4", None)
        out.append(g)
    return out


def norm(s: str) -> str:
    s = s.lower().replace("&", "and")
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)        # strip [GXXE01] and (USA) tags
    return re.sub(r"[^a-z0-9]+", "", s)


def norm_loose(s: str) -> str:
    """norm() plus dump-set naming habits: 'Legend of Zelda, The - The Wind Waker' == 'The Legend of Zelda: The Wind Waker',
    and a leading 'The' never matters."""
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    s = re.sub(r"^(.*?), (the|a|an)\b", r"\2 \1", s.strip(), flags=re.I)
    n = norm(s)
    return n[3:] if n.startswith("the") and len(n) > 6 else n


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-") or "game"


class Catalog:
    def __init__(self, games=None):
        self.games = clean_catalog(games) if games is not None else load_catalog()
        self.by_key = {g["key"]: g for g in self.games}
        self.by_code4 = {g["code4"]: g for g in self.games if g.get("code4")}
        self.by_name = {}
        for g in self.games:
            for name in [g["title"], *g.get("aliases", [])]:
                self.by_name.setdefault(norm(name), g)
                self.by_name.setdefault(norm_loose(name), g)

    def match(self, code6: str | None, filename: str) -> dict | None:
        """Disc ID first, then exact (normalised) file name, then a careful fuzzy fallback.

        The fallback only accepts a catalog name found *inside* the file name, takes the LONGEST such name
        ("Sonic Adventure 2 Battle" beats "Sonic Adventure 2"), and refuses a hit that is directly followed
        by a digit ("Mario Party 4" must not claim "Mario Party 40..."). A file name that is merely a
        prefix of a title is accepted only when exactly one game could be meant."""
        exact = self.by_name.get(norm(Path(filename).stem))
        if exact and not exact.get("code4") and code6 and code6[:4] in self.by_code4:
            return exact                             # a mod with its own catalog entry, still carrying the original ID
        if code6 and code6[:4] in self.by_code4:
            return self.by_code4[code6[:4]]
        stem = norm(Path(filename).stem)
        stem = re.sub(r"(disc|disk|cd)[1-9]$", "", stem) or stem
        if stem in self.by_name:
            return self.by_name[stem]
        stem = norm_loose(re.sub(r"(?i)[\s_\-]*\(?(disc|disk|cd)[\s_]*[1-9]\)?\s*$", "", Path(filename).stem))
        if stem in self.by_name:
            return self.by_name[stem]
        if len(stem) < 8:
            return None
        best, best_len = None, 0
        for n, g in self.by_name.items():
            if len(n) < 8 or len(n) <= best_len:
                continue
            at = stem.find(n)
            if at < 0:
                continue
            after = stem[at + len(n):at + len(n) + 1]
            if after.isdigit():
                continue
            best, best_len = g, len(n)
        if best:
            return best
        owners = {g["key"]: g for n, g in self.by_name.items() if n.startswith(stem)}
        return next(iter(owners.values())) if len(owners) == 1 else None


# ---------- library ----------
# What stock Swiss will actually start (docs/RESEARCH_NOTES.md A7). Compressed images are still *recognised* in your
# library so you can see them, but they are kept off the cards until you convert them (Dolphin or NKit -> ISO).
LAUNCHABLE_EXTS = {".iso", ".gcm"}
DUPLICATES: list = []     # [(ignored path, kept path)] from the most recent scan_library (shown by `scan`)


@dataclass
class Rom:
    path: str                     # disc 1
    size: int                     # total bytes of ALL discs (what the planner budgets)
    code6: str | None
    internal_title: str | None
    key: str                      # catalog key, or slug of filename if unknown
    title: str
    in_catalog: bool
    tags: list = field(default_factory=list)
    discs: list = field(default_factory=list)   # [{"path","size","disc"}] sorted by disc number; len > 1 = multi-disc

    @property
    def launchable(self) -> bool:
        """False for compressed containers (.ciso/.gcz/.rvz: Swiss refuses them), for a file with no GameCube disc
        header (an empty file, another console's ISO, a mis-named CISO) and for a set with a disc missing."""
        return (all(Path(d["path"]).suffix.lower() in LAUNCHABLE_EXTS and d.get("header_ok", True) for d in self.discs)
                and [d["disc"] for d in self.discs] == list(range(1, len(self.discs) + 1)))   # no missing disc

    @property
    def why_not_launchable(self) -> str:
        """Plain words for the first reason launchable is False ('' if it is launchable)."""
        if any(Path(d["path"]).suffix.lower() not in LAUNCHABLE_EXTS for d in self.discs):
            return ("compressed image (.ciso/.gcz/.rvz/.wia); Swiss cannot start these, "
                    "convert to .iso with Dolphin or NKit first")
        if not all(d.get("header_ok", True) for d in self.discs):
            return "not a GameCube disc image (no GameCube disc header in the file)"
        if not self.launchable:
            return "a disc is missing from the set"
        return ""

    @property
    def why_short(self) -> str:
        """A few words for a table column ('' if launchable)."""
        why = self.why_not_launchable
        return ("convert to .iso first" if why.startswith("compressed") else
                "not a GameCube disc image" if why.startswith("not a GameCube") else
                "a disc is missing" if why else "")

    def __post_init__(self):
        if not self.discs:
            self.discs = [{"path": self.path, "size": self.size, "disc": 1}]


def read_disc_header(path: Path):
    """(code6, internal title) from a disc image, or (None, None). Handles ISO/GCM/CISO/GCZ/RVZ (see discimage.py)."""
    h = discimage.read_header(path)
    return (h["code6"], h["title"]) if h else (None, None)


def _base_name(p: Path) -> str:
    """File name without its image extension (and without ".nkit"), lowercase: the sort key that puts an original
    before its "- patched" / " copy" / " (1)" siblings."""
    n = p.name.lower()
    if p.suffix:
        n = n[: -len(p.suffix)]
    return n[:-5] if n.endswith(".nkit") else n


def scan_library(cfg, catalog: Catalog | None = None) -> list[Rom]:
    """Find disc images under library_dir. Multi-disc games become ONE Rom with several `discs`."""
    catalog = catalog or Catalog()
    lib = cfg.get("library_dir")
    if not lib or not Path(lib).is_dir():
        return []
    exts = {e.lower() for e in cfg["extensions"]} | set(discimage.READERS)   # an old config.json may lack .rvz/.wia
    roms: dict[str, Rom] = {}
    DUPLICATES.clear()
    # "Game (USA).iso" must come before "Game (USA) - patched.iso" / "Game (USA) copy.iso" (a plain sort puts the space
    # first), so the original is the one kept when two files are the same disc
    for p in sorted(Path(lib).rglob("*"), key=lambda q: (str(q.parent), _base_name(q), q.name)):
        try:
            if not (p.is_file() and p.suffix.lower() in exts) or p.name.startswith("."):
                continue
            size = p.stat().st_size
        except OSError:
            continue
        h = discimage.read_header(p)
        if h and h.get("wii"):                       # a Wii disc in the folder: not ours to rotate
            continue
        if h and not h["magic_ok"]:                  # starts like a game ID but is not a GameCube disc: go by file name
            h = None
        code, internal = (h["code6"], h["title"]) if h else (None, None)
        disc_no = h["disc"] if h else discimage.disc_from_filename(p.name)
        g = catalog.match(code, p.name)
        key = g["key"] if g else slugify(internal or re.sub(r"\(.*?\)|\[.*?\]", " ", p.stem))
        disc = {"path": str(p), "size": size, "disc": disc_no,
                "header_ok": bool(h) or p.suffix.lower() not in LAUNCHABLE_EXTS}   # compressed: judged by extension
        if key not in roms:
            roms[key] = Rom(str(p), size, code, internal, key, g["title"] if g else (internal or p.stem),
                            bool(g), list(g.get("tags", [])) if g else [], [disc])
            continue
        rom = roms[key]
        same = [d for d in rom.discs if d["disc"] == disc_no]
        if same:                                     # duplicate dump of the same disc: keep the first...
            old = same[0]

            def rank(d):                             # a startable file with a real header beats one without
                return (Path(d["path"]).suffix.lower() in LAUNCHABLE_EXTS and d["header_ok"], d["header_ok"])
            if rank(disc) <= rank(old):
                DUPLICATES.append((str(p), old["path"]))
                continue
            DUPLICATES.append((old["path"], str(p)))  # ...unless this one is the better file
            rom.discs.remove(old)
        rom.discs.append(disc)
        if disc_no == 1 and h:                       # the better file's own header, not the one it replaced
            rom.code6, rom.internal_title = code, internal
            if not rom.in_catalog:
                rom.title = internal or rom.title
        rom.discs.sort(key=lambda d: d["disc"])
        rom.size = sum(d["size"] for d in rom.discs)
        rom.path = rom.discs[0]["path"]
    return list(roms.values())


# ---------- rotation planner ----------
def card_ids(cfg) -> list[str]:
    return sorted(cfg["cards"], key=lambda c: (0, int(c), "") if str(c).isascii() and str(c).isdigit() else (1, 0, str(c)))


CARD_LABEL_SHARE = 0.95      # a card labelled "32 GB" (decimal) holds a little less once formatted; plan safely below it


def card_budget(cfg, card: dict, real_bytes=None) -> int:
    """Bytes the planner may fill on one card. capacity_gb is the size printed on the card (decimal GB, as sold).
    real_bytes, when a sync has measured the card (state["card_bytes"]), replaces the estimate, but never goes
    above capacity_gb, so a deliberately small setting is respected."""
    try:
        gb = float(card.get("capacity_gb", 0)) if isinstance(card, dict) else 0.0
    except (TypeError, ValueError):
        gb = 0.0
    gb = gb if gb == gb and gb > 0 else 0.0                     # NaN / negative -> 0
    base = gb * 1000**3 * CARD_LABEL_SHARE
    if isinstance(real_bytes, (int, float)) and not isinstance(real_bytes, bool) and real_bytes > 0:
        base = min(gb * 1000**3, real_bytes * 0.995)            # measured: keep a sliver for folders and the manifest
    return max(0, int(base) - int(cfg["reserve_mb"]) * 1024**2)


def note_card_size(state: dict, card_id: str, mount: str) -> bool:
    """Remember a card's real size after a sync so the next plan budgets with it (state is additive).
    True if something changed (the caller then saves state)."""
    try:
        total = int(shutil.disk_usage(mount).total)
    except (OSError, TypeError, ValueError):
        return False
    if not isinstance(state.get("card_bytes"), dict):
        state["card_bytes"] = {}
    if state["card_bytes"].get(str(card_id)) == total:
        return False
    state["card_bytes"][str(card_id)] = total
    return True


STALE_CAP_DAYS = 48.0


def game_score(rom: Rom, state: dict, now: float) -> float:
    """Higher = more deserving of a slot. Ratings dominate, staleness breaks ties, a little jitter stays fun."""
    rating = state["ratings"].get(rom.key, 3)
    rating = rating if isinstance(rating, (int, float)) else 3
    last = state["last_on_card"].get(rom.key, 0)
    last = last if isinstance(last, (int, float)) else 0
    # staleness tops out below one star (48 days -> 6.9 points, plus at most 3 of jitter < 10), so a 1-star game that
    # has rested longer never pushes out a 5-star one; it only breaks ties between games rated the same
    days_off = min(STALE_CAP_DAYS, max(0.0, now - last) / 86400) if last else STALE_CAP_DAYS
    return rating * 10 + days_off / 7.0


SCORE_HOOKS: list = []   # plugins may append fn(rom, state, now) -> float bonus (see pawtation/plugins.py)


def plan_rotation(cfg, state, roms: list[Rom], now: float | None = None) -> dict:
    """Return {card_id: [rom_key,...]}. Pins first (one favorite per card, in order), then
    greedy fill by score. Each game appears on at most one card per season."""
    now = time.time() if now is None else now
    season = next_season(state)
    rng = random.Random(cfg["seed"] or (season * 7919))
    by_key = {r.key: r for r in roms}
    cards = cfg["cards"]
    ids = card_ids(cfg)
    plan = {c: [] for c in ids}
    measured = state.get("card_bytes") if isinstance(state.get("card_bytes"), dict) else {}
    free = {c: card_budget(cfg, cards[c], measured.get(c)) for c in ids}
    cap = cfg["max_games_per_card"]
    used = set()

    def place(cid, rom):
        if rom.key in used or rom.size > free[cid] or (cap and len(plan[cid]) >= cap):
            return False
        plan[cid].append(rom.key); free[cid] -= rom.size; used.add(rom.key)
        return True

    for i, key in enumerate(cfg["pinned"]):                     # favorites: one per card, wrap if more pins than cards
        if key in by_key and ids and by_key[key].launchable:
            start = i % len(ids)
            for cid in ids[start:] + ids[:start]:               # preferred card first; fall through if it can't fit
                if place(cid, by_key[key]):
                    break

    def score(r):
        bonus = 0.0
        for hook in SCORE_HOOKS:
            try:
                bonus += float(hook(r, state, now) or 0)
            except Exception:                                   # a broken plugin must not break rotation
                pass
        return game_score(r, state, now) + bonus + rng.random() * 3

    rest = sorted((r for r in roms if r.key not in used and r.launchable), key=lambda r: r.key)   # stable base order -> reproducible seeds
    scored = sorted(((score(r), r) for r in rest), key=lambda t: -t[0])
    for _s, rom in scored:                                      # each game goes to the card with most free space
        for cid in sorted(ids, key=lambda c: -free[c]):
            if place(cid, rom):
                break
    return plan


def next_season(state) -> int:
    """History is capped, so count from the last entry's season number rather than the list length."""
    hist = state.get("history") or []
    last = hist[-1].get("season") if hist else 0
    return (last if isinstance(last, int) else len(hist)) + 1


def unplaced(plan: dict, roms: list[Rom]) -> list[Rom]:
    """Games that did not make it onto any card this season (too big, or simply out of room)."""
    on = {k for keys in plan.values() for k in keys}
    return [r for r in roms if r.key not in on]


def current_plan(state) -> dict:
    return state["history"][-1]["plan"] if state.get("history") else {}


def rotation_due(cfg, state, now=None) -> tuple[bool, float]:
    """(is_due, seconds_remaining)."""
    now = time.time() if now is None else now
    last = state.get("last_rotation_ts", 0)
    if not last:
        return True, 0.0
    remaining = last + float(cfg["rotation_days"]) * 86400 - now
    return remaining <= 0, max(0.0, remaining)


def fmt_remaining(sec: float) -> str:
    d, h, m = int(sec // 86400), int(sec % 86400 // 3600), int(sec % 3600 // 60)
    return f"{d}d {h}h {m}m" if d or h else f"{m}m"


def commit_plan(state, plan, now=None):
    now = time.time() if now is None else now
    season = next_season(state)
    state["history"].append({"ts": now, "season": season, "plan": plan})
    state["history"] = state["history"][-50:]
    for keys in plan.values():
        for k in keys:
            state["last_on_card"][k] = now
    state["last_rotation_ts"] = now


# ---------- SD sync ----------
_WIN_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
COPY_CHUNK = 4 * 1024 * 1024
QUIPS_REL = "pawtation/quips.txt"


def safe_name(title: str) -> str:
    """A folder name that is legal on FAT32/exFAT (and Windows): no reserved characters, no trailing dot/space."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "", title)
    name = re.sub(r"\s+", " ", name).strip()[:80].rstrip(". ")
    if name.split(".")[0].strip().lower() in _WIN_RESERVED:
        name = "_" + name
    return name or "game"


def disc_filename(disc_no: int, suffix: str, multi: bool = False) -> str:
    """File name inside a game's folder: game.iso, or disc1.iso/disc2.iso for multi-disc games. Swiss pairs discs by
    their headers and prefers two names that differ only in the disc digit (docs/RESEARCH_NOTES.md A7)."""
    return (f"disc{disc_no}" if multi else "game") + suffix.lower()


def card_path(mount_p: Path, rel: str) -> Path | None:
    """Resolve a manifest-relative path, or None if it could escape the card: absolute, drive letter, '..', a name
    Windows would alias (trailing dot/space, CON, NUL...), or any existing component that is a symlink.
    The manifest lives on removable media, so it is treated as untrusted input."""
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel or "//" in rel or rel.startswith("/"):
        return None
    parts = PurePosixPath(rel).parts
    for p in parts:
        if p in ("..", ".", "") or p != p.rstrip(". ") or p.split(".")[0].lower() in _WIN_RESERVED:
            return None
    cur = Path(mount_p)
    for p in parts:
        cur = cur / p
        if cur.is_symlink():
            return None
    return cur


def load_manifest(mount_p: Path) -> dict:
    """The card's manifest with every field forced into its expected shape (anything else is dropped)."""
    m = load_json(Path(mount_p) / MANIFEST_NAME, {})
    files = m.get("files") if isinstance(m.get("files"), dict) else {}
    more = m.get("more_files") if isinstance(m.get("more_files"), dict) else {}
    aux = m.get("aux") if isinstance(m.get("aux"), dict) else {}
    titles = m.get("titles") if isinstance(m.get("titles"), dict) else {}
    m["files"] = {str(k): v for k, v in files.items() if isinstance(v, str)}
    m["more_files"] = {str(k): [r for r in v if isinstance(r, str)] for k, v in more.items() if isinstance(v, list)}
    m["aux"] = {k: str(v) for k, v in aux.items() if isinstance(k, str)}
    m["titles"] = {str(k): str(v) for k, v in titles.items()}
    m["pending"] = [r for r in m.get("pending", []) if isinstance(r, str)] if isinstance(m.get("pending"), list) else []
    src = m.get("src") if isinstance(m.get("src"), dict) else {}  # rel -> [size, mtime] of the library file it came from
    m["src"] = {}
    for k, v in src.items():                     # untrusted: NaN, Infinity, 1e400 and friends are dropped, not crashed on
        if isinstance(v, list) and len(v) == 2 and all(isinstance(x, (int, float)) and not isinstance(x, bool)
                                                       and math.isfinite(x) and abs(x) < 2**62 for x in v):
            m["src"][str(k)] = [int(v[0]), int(v[1])]
    return m


def _src_sig(p: Path) -> list | None:
    """[size, whole-second mtime] of a library file: enough to notice that a dump was replaced or re-patched."""
    try:
        st = Path(p).stat()
    except OSError:
        return None
    return [int(st.st_size), int(st.st_mtime)]


def _sig_match(a, b) -> bool:
    """Same size and the same time to within 2 s (FAT/exFAT granularity), or exactly one hour apart: Windows shows the
    times of files on a FAT32 drive shifted by an hour after a daylight-saving change."""
    if not (a and b) or a[0] != b[0]:
        return False
    d = abs(a[1] - b[1])
    return d <= 2 or abs(d - 3600) <= 2


def _manifest_rels(manifest: dict, key: str) -> list[str]:
    rels = [manifest["files"][key]] if key in manifest["files"] else []
    return rels + list(manifest["more_files"].get(key, []))


def mod_files(cfg, key: str) -> dict[str, Path]:
    """Extras for one game: every file under <mods_dir>/<key>/card/ maps to the same relative path on the SD card
    (e.g. mods/paper-mario-ttyd/card/swiss/cheats/G8ME01.txt -> <card>/swiss/cheats/G8ME01.txt)."""
    base = mods_dir(cfg) / key / "card"
    out = {}
    if base.is_dir():
        for p in sorted(base.rglob("*")):
            if p.is_file() and not p.name.startswith("."):
                out[p.relative_to(base).as_posix()] = p
    return out


PART_TAG = ".pawtation-part"     # temp files are "<name>.pawtation-partN": a name only this tool uses


def _open_part(dest: Path):
    """Create a fresh temp file next to dest, never following a symlink and never reusing someone else's file.
    Left-over temp files of ours (same naming pattern, from a crash or a pulled card) are cleared first."""
    try:
        for stale in dest.parent.glob(dest.name + PART_TAG + "*"):
            stale.unlink()
    except OSError:
        pass
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    for i in range(100):
        part = dest.with_name(f"{dest.name}{PART_TAG}{i}")
        try:
            return part, os.fdopen(os.open(part, flags, 0o644), "wb")
        except FileExistsError:
            continue
    raise OSError(f"could not create a temporary file next to {dest}")


def _write_atomic(dest: Path, chunks, tick=lambda n: None, cancel=lambda: False) -> int | None:
    """Write chunks to a temp file, fsync, then rename onto dest: a pulled card never leaves a half file under the
    real name. Returns the CRC32 of what was written, or None if cancelled (nothing is left behind)."""
    part, fo = _open_part(dest)
    crc, finished = 0, False
    try:
        with fo:
            for chunk in chunks:
                if cancel():
                    break
                fo.write(chunk)
                crc = zlib.crc32(chunk, crc)
                tick(len(chunk))
            else:
                finished = True
                fo.flush(); os.fsync(fo.fileno())
        if finished:
            os.replace(part, dest)
            return crc
        return None
    finally:
        if not finished or part.exists():
            try: part.unlink()
            except OSError: pass


def _read_chunks(src: Path):
    with open(src, "rb") as fi:
        while True:
            chunk = fi.read(COPY_CHUNK)
            if not chunk:
                return
            yield chunk


def _copy_stream(src: Path, dest: Path, tick, cancel) -> int | None:
    return _write_atomic(dest, _read_chunks(src), tick, cancel)


def _drop_cache(path: Path) -> None:
    """Ask the OS to forget its cached copy of a file we just wrote, so a re-read really reads the card.
    Works on Linux (posix_fadvise); elsewhere it does nothing and the re-read may come from memory."""
    if not hasattr(os, "posix_fadvise"):
        return
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            os.fsync(fd)
            os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
        finally:
            os.close(fd)
    except OSError:
        pass


def file_crc32(path: Path, cancel=lambda: False) -> int | None:
    crc = 0
    with open(path, "rb") as f:
        while True:
            if cancel():
                return None
            chunk = f.read(COPY_CHUNK)
            if not chunk:
                return crc
            crc = zlib.crc32(chunk, crc)


def _rm_tracked(mount_p: Path, rel: str, stop_at: set) -> None:
    target = card_path(mount_p, rel)
    if target is None:
        return
    if target.is_file():
        target.unlink()
    parent = target.parent
    while parent not in stop_at and parent != mount_p and mount_p in parent.parents:   # tidy now-empty folders we made
        try:
            for stale in parent.glob("*" + PART_TAG + "*"):
                stale.unlink()
            parent.rmdir()
        except OSError:
            break
        parent = parent.parent


def sync_card(cfg, card_id: str, keys: list[str], roms: list[Rom], mount: str, dry_run=True, log=print,
              progress=None, cancel=None, verify=None, quips=None, force=False) -> dict:
    """Make the card hold exactly `keys` inside <mount>/<games_subdir>, touching ONLY files this tool
    previously wrote (tracked in the card's manifest). Your Swiss files and saves are never deleted.
    Copies are sequential into freed space to keep files contiguous (Swiss prefers unfragmented files).

    progress: optional fn(dict) called often with {"phase": "remove"|"copy"|"verify"|"done", "title", "rel",
              "file_done", "file_total", "all_done", "all_total"} (bytes). Safe to ignore.
    cancel:   optional fn() -> bool polled between chunks; True stops cleanly (finished files stay, manifest saved).
    verify:   re-read each copied file and compare CRC32 (default: cfg["verify_copies"]).
    quips:    optional list of plain lines written to /pawtation/quips.txt (tracked, so it is cleaned up too).
    force:    sync even if the card's manifest says it is a different card.
    Returns {"removed","copied","kept","errors","warnings","cancelled","bytes_copied"}.

    How it stays safe: every path from the manifest goes through card_path(); a file is "ours" only if the manifest
    lists it (or lists it as pending, i.e. a copy that was interrupted); the manifest is written BEFORE a copy
    starts (pending) and after it ends, so a crash at any point leaves something the next run can clean up."""
    card_id = str(card_id)
    mount_p = Path(mount)
    if not mount_p.is_dir():
        raise FileNotFoundError(f"Mount path not found: {mount}")
    progress = progress or (lambda info: None)
    stop = [False]
    user_cancel = cancel or (lambda: False)

    def cancel():                                               # latches: once cancelled, always cancelled
        if not stop[0] and user_cancel():
            stop[0] = True
        return stop[0]

    verify = cfg.get("verify_copies", False) if verify is None else verify
    sub = safe_name(str(cfg["games_subdir"]).strip("/\\")) or "games"
    games_dir = mount_p / sub
    manifest_p = mount_p / MANIFEST_NAME
    manifest = load_manifest(mount_p)
    by_key = {r.key: r for r in roms}
    want = {k: by_key[k] for k in keys if k in by_key}
    report = {"removed": [], "copied": [], "kept": [], "errors": [], "warnings": [], "cancelled": False, "bytes_copied": 0,
              "refused": ""}     # "link" | "damaged_manifest" | "wrong_card" when nothing was done to this card
    tag = "[dry] " if dry_run else ""

    for k in keys:
        if k not in by_key:
            report["warnings"].append(f"{k}: planned for this card but not found in the library (rescan? is the library "
                                      "drive plugged in?). Anything already on the card for it is left as it is.")
    if games_dir.is_symlink() or manifest_p.is_symlink():
        report["errors"].append("The games folder or manifest on this card is a link to somewhere else. Nothing was changed.")
        report["refused"] = "link"
        return report
    if manifest_p.is_file() and not isinstance(load_json(manifest_p, None), dict):
        bad = manifest_p.with_name(MANIFEST_NAME + ".bad")
        if not force:
            report["errors"].append(f"This card's {MANIFEST_NAME} is damaged (unreadable), so Pawtation cannot tell which "
                                    "files are its own. Nothing was changed. Restore the file if you have a copy, or "
                                    f"use force / --force to start a new one (the damaged file is kept as {bad.name}).")
            report["refused"] = "damaged_manifest"
            return report
        report["warnings"].append(f"{MANIFEST_NAME} was damaged; starting a new one (old copy kept as {bad.name}). "
                                  "Games already on the card are not recognised as Pawtation's and stay untouched.")
        if not dry_run:
            try:
                shutil.copyfile(manifest_p, bad)
            except OSError as e:
                report["errors"].append(f"could not back up the damaged {MANIFEST_NAME} ({e}). Nothing was changed.")
                return report
    other = manifest.get("card_id")
    if other is not None and str(other) != card_id:
        msg = f"This SD card is labelled as card {other}, not card {card_id}."
        if not force:
            report["errors"].append(msg + " Nothing was changed. (Use force / --force to re-purpose it.)")
            report["refused"] = "wrong_card"
            return report
        report["warnings"].append(msg + " Re-purposing it as requested.")

    def save_manifest():
        if dry_run:
            return
        label = cfg["cards"].get(card_id, {}).get("label", f"Card {card_id}") if isinstance(cfg["cards"].get(card_id), dict) else f"Card {card_id}"
        manifest.update({"card_id": card_id, "label": label, "updated": int(time.time()), "schema": 2,
                         "titles": {k: want[k].title if k in want else manifest["titles"].get(k, k)
                                    for k in manifest["files"]}})
        save_json(manifest_p, manifest)

    def set_rels(key, rels):
        order = [r for r, _s, _n in wanted_files.get(key, []) if r in rels] + [r for r in rels if r not in wanted_rels]
        if order:
            manifest["files"][key] = order[0]
            manifest["more_files"][key] = order[1:]
            if not order[1:]:
                manifest["more_files"].pop(key, None)
        else:
            manifest["files"].pop(key, None); manifest["more_files"].pop(key, None)

    # -- what should be on the card
    wanted_files: dict[str, list] = {}                          # key -> [(rel, src Path, size)]
    claimed: dict[str, str] = {}                                # folder (lowercase) -> key, FAT is case-insensitive
    for key in sorted(want):                                    # sorted: folder choice never depends on plan order
        rom = want[key]
        if not rom.launchable:
            report["errors"].append(f"{rom.title}: {rom.why_not_launchable}. Not copied; anything already on the card "
                                    "for it is left as it is.")
            wanted_files[key] = []
            continue
        folder = None
        m = re.fullmatch(re.escape(sub) + r"/([^/]+)/[^/]+", manifest["files"].get(key, ""))
        if m and safe_name(m.group(1)) == m.group(1) and m.group(1).lower() not in claimed:
            folder = m.group(1)                                 # already on the card: keep its folder (no needless recopy)
        base, n = safe_name(rom.title), 1
        while folder is None or claimed.get(folder.lower(), key) != key:
            folder = base if n == 1 else safe_name(f"{base[:70]} ({n})")
            n += 1
        claimed[folder.lower()] = key
        multi = len(rom.discs) > 1
        wanted_files[key] = [(f"{sub}/{folder}/{disc_filename(d['disc'], Path(d['path']).suffix, multi)}", Path(d["path"]), d["size"])
                             for d in rom.discs]
    wanted_rels = {rel for files in wanted_files.values() for rel, _s, _n in files}
    # Planned games with nothing to copy (library drive unplugged, file renamed or now compressed, a disc missing):
    # whatever is already on the card for them stays. Removing it would empty the card of games the plan still wants.
    held = {k for k in keys if not wanted_files.get(k)}
    held_rels = {rel for k in held for rel in _manifest_rels(manifest, k)}
    wanted_aux: dict[str, tuple] = {}                           # rel -> (src Path | bytes, owner)
    for key in sorted(want):
        if wanted_files.get(key):
            for rel, src in mod_files(cfg, key).items():
                wanted_aux.setdefault(rel, (src, key))
    if quips and cfg.get("export_quips", True):
        text = "\n".join(str(q).encode("ascii", "ignore").decode() for q in quips) + "\n"
        wanted_aux[QUIPS_REL] = (text.encode("ascii"), "pawtation")

    # -- remove what rotated out (tracked files only)
    gone: set = set()                                           # rels removed (or, in a dry run, that would be)

    def remove(rel, title, stop_at):
        """True if rel is (or would be) gone afterwards."""
        if card_path(mount_p, rel) is None:
            report["warnings"].append(f"ignored unsafe path in card manifest: {rel!r}")
            return True                                         # forget it; we will never touch it
        log(f"{tag}remove {rel}")
        progress({"phase": "remove", "title": title, "rel": rel})
        if not dry_run:
            try:
                _rm_tracked(mount_p, rel, stop_at)
            except OSError as e:
                report["errors"].append(f"could not remove {rel}: {e}")
                return False                                    # still there: keep it in the manifest
        report["removed"].append(rel); gone.add(rel)
        if not dry_run:
            manifest["src"].pop(rel, None)
        return True

    try:
        for rel in list(manifest["pending"]):                   # an interrupted copy from last time
            if rel not in wanted_rels and rel not in wanted_aux and rel not in held_rels:
                if remove(rel, rel, {games_dir}):
                    manifest["pending"].remove(rel)
        for key in list(dict.fromkeys(list(manifest["files"]) + list(manifest["more_files"]))):
            if key in held:
                continue
            old = _manifest_rels(manifest, key)
            keep = {rel for rel, _s, _n in wanted_files.get(key, [])}
            left = [rel for rel in old if rel in keep
                    or (rel not in gone and not remove(rel, manifest["titles"].get(key, key), {games_dir}))]
            set_rels(key, left)
        for rel in list(manifest["aux"]):
            if rel not in wanted_aux and manifest["aux"][rel] not in held and (rel in gone or remove(rel, rel, set())):
                manifest["aux"].pop(rel, None)
        save_manifest()
    except OSError as e:
        report["errors"].append(f"could not update the card ({e}). Stopped; is it write-protected or failing?")
        return report

    # -- decide what needs copying
    ambiguous = {kept for _ignored, kept in DUPLICATES}         # library files that have a same-disc twin (last scan)
    todo = []                                                   # (key, rel, src, size, title)
    for key, files in wanted_files.items():
        ours = set(_manifest_rels(manifest, key)) | set(manifest["pending"])
        game_todo = []
        for rel, src, size in files:
            dest = card_path(mount_p, rel)
            if dest is None:
                report["errors"].append(f"{want[key].title}: cannot use {rel} on this card (a link is in the way). Skipped.")
                game_todo = None; break
            try:
                there = dest.exists() and rel not in gone
                same = rel in _manifest_rels(manifest, key) and dest.is_file() and dest.stat().st_size == size
            except OSError:
                there = same = False
            sig, cur = manifest["src"].get(rel), _src_sig(src)
            if same and sig is not None and not _sig_match(sig, cur):
                same = False                                    # the library file was replaced: copy it again
            if same and sig is None and str(src) in ambiguous:
                same = False                                    # copied before tracking began, and the library holds
                                                                # two files for this disc: refresh once to be sure
            if same:
                if sig is None and cur and not dry_run:
                    manifest["src"][rel] = cur                  # older manifests: start tracking from here
                report["kept"].append(rel)
            elif there and rel not in ours:
                report["errors"].append(f"{rel} already exists on the card and was not put there by Pawtation; "
                                        f"left untouched ({want[key].title} skipped)")
                game_todo = None; break
            else:
                game_todo.append((key, rel, src, size, want[key].title))
        todo += game_todo or []
    pins = [k for k in cfg.get("pinned", []) if isinstance(k, str)]
    todo.sort(key=lambda t: pins.index(t[0]) if t[0] in pins else len(pins))   # stable: favourites first if space runs out
    all_total = sum(t[3] for t in todo)
    try:
        free_now = shutil.disk_usage(mount_p).free
    except OSError:
        free_now = None
    reserve = int(cfg["reserve_mb"]) * 1024**2
    if dry_run and free_now is not None:
        freed = 0
        for rel in report["removed"]:
            p = card_path(mount_p, rel)
            try: freed += p.stat().st_size if p and p.is_file() else 0
            except OSError: pass
        if free_now + freed - all_total < reserve:
            report["warnings"].append(f"Tight fit: needs {fmt_gb(all_total)}, about {fmt_gb(free_now + freed)} would be free.")

    # -- copy what rotated in, one file at a time
    all_done = 0
    skip_keys: set = set()
    for i, (key, rel, src, size, title) in enumerate(todo):
        if cancel():
            break
        if key in skip_keys:
            continue
        dest = card_path(mount_p, rel)
        log(f"{tag}copy {title} -> {rel}")
        if dry_run:
            report["copied"].append(rel); continue
        try:
            game_bytes = sum(t[3] for t in todo[i:] if t[0] == key)     # all remaining discs must fit, or none go
            for t in todo[i:]:                                  # an interrupted copy's temp file still takes space
                d = card_path(mount_p, t[1]) if t[0] == key else None
                if d is not None and d.parent.is_dir():
                    for stale in d.parent.glob(d.name + PART_TAG + "*"):
                        try: stale.unlink()
                        except OSError: pass
            free = shutil.disk_usage(mount_p).free
            if free - game_bytes < reserve:
                old_here = []                                   # our own outdated copies of the discs still to copy
                for t in todo[i:]:
                    d = card_path(mount_p, t[1]) if t[0] == key else None
                    if d is not None and t[1] not in gone and t[1] in _manifest_rels(manifest, key) and d.is_file():
                        old_here.append((t[1], d, d.stat().st_size))
                if not old_here or free + sum(s for _r, _d, s in old_here) - game_bytes < reserve:
                    report["errors"].append(f"not enough space for {title}"); skip_keys.add(key); continue
                for r, _d, _s in old_here:                      # still ours if anything stops halfway
                    if r not in manifest["pending"]:
                        manifest["pending"].append(r)
                save_manifest()
                for r, d, _s in old_here:
                    d.unlink(); gone.add(r); manifest["src"].pop(r, None)
                report["warnings"].append(f"{title}: the library copy changed and the card is full, so the old copy was "
                                          "removed first to make room (if this copy is stopped, the next sync puts it back)")
            if dest is None:
                raise OSError("a link is in the way")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if card_path(mount_p, rel) is None:
                raise OSError("a link is in the way")
            if rel not in manifest["pending"]:
                manifest["pending"].append(rel)
            save_manifest()                                     # recorded BEFORE writing: a crash leaves a file we own
            done = [0]

            def tick(n, _rel=rel, _title=title, _size=size, _base=all_done, _done=done):
                _done[0] += n
                progress({"phase": "copy", "title": _title, "rel": _rel, "file_done": _done[0], "file_total": _size,
                          "all_done": _base + _done[0], "all_total": all_total})

            crc = _copy_stream(src, dest, tick, cancel)
            ok = crc is not None
            if ok and verify:
                progress({"phase": "verify", "title": title, "rel": rel, "file_done": size, "file_total": size,
                          "all_done": all_done + size, "all_total": all_total})
                _drop_cache(dest)
                back = file_crc32(dest, cancel)
                if back is not None and back != crc:
                    dest.unlink()
                    report["errors"].append(f"verification FAILED for {title} (card may be failing); copy removed")
                    ok = False; skip_keys.add(key)
            if ok or not dest.exists():                         # a cancelled re-copy must not forget a file we own
                manifest["pending"].remove(rel)
            if ok:
                set_rels(key, [r for r in _manifest_rels(manifest, key) if r != rel] + [rel])
                sig = _src_sig(src)
                if sig:
                    manifest["src"][rel] = sig
            save_manifest()                                     # after every file: a pulled card stays consistent
            if not ok:
                continue
        except OSError as e:
            report["errors"].append(f"could not copy {title}: {e}"); skip_keys.add(key); continue
        all_done += size
        report["bytes_copied"] += size
        report["copied"].append(rel)

    # -- small extras (mods, quips)
    for rel, (src, owner) in wanted_aux.items():
        if cancel():
            break
        dest = card_path(mount_p, rel)
        if dest is None or rel.lower() == MANIFEST_NAME or rel.split("/")[0].lower() == sub.lower() or PART_TAG in rel:
            report["warnings"].append(f"mod file skipped (not allowed there): {rel}"); continue
        try:
            data = src if isinstance(src, bytes) else src.read_bytes()
            if dest.exists() and rel not in gone and rel not in manifest["aux"] and rel not in manifest["pending"]:
                report["warnings"].append(f"{rel} already exists on the card and is not ours; left untouched"); continue
            if rel in manifest["aux"] and dest.is_file() and dest.read_bytes() == data:
                report["kept"].append(rel); continue
            log(f"{tag}copy extra ({owner}) -> {rel}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                if card_path(mount_p, rel) is None:
                    raise OSError("a link is in the way")
                manifest["pending"].append(rel); save_manifest()
                _write_atomic(dest, [data])
                manifest["pending"].remove(rel)
                manifest["aux"][rel] = owner
            report["copied"].append(rel)
        except OSError as e:
            report["errors"].append(f"could not copy extra {rel}: {e}")

    report["cancelled"] = stop[0]
    try:
        save_manifest()
    except OSError as e:
        report["errors"].append(f"could not save the card manifest: {e}")
    progress({"phase": "done", "all_done": all_done, "all_total": all_total})
    return report


def fmt_gb(n: int) -> str:
    return f"{n / 1000**3:.2f} GB"                              # decimal, like the size printed on an SD card


# ---------- finding SD cards ----------
def candidate_volumes() -> list[Path]:
    """Mounted volumes that could be SD cards (best effort, read-only; never the system drive)."""
    out = []
    if os.name == "nt":
        sysdrive = os.environ.get("SystemDrive", "C:").upper()
        for letter in string.ascii_uppercase:
            if f"{letter}:" != sysdrive and letter not in "AB":
                out.append(Path(f"{letter}:\\"))
    else:
        user = os.environ.get("USER") or os.environ.get("LOGNAME") or ""
        for base in ("/Volumes", f"/media/{user}", f"/run/media/{user}", "/media", "/mnt"):
            try:
                out += [p for p in sorted(Path(base).iterdir()) if p.is_dir()]
            except OSError:
                pass
    seen, uniq = set(), []
    for p in out:
        try:
            if p.is_dir() and str(p) not in seen:
                seen.add(str(p)); uniq.append(p)
        except OSError:
            pass
    return uniq


def find_cards(volumes=None) -> dict[str, str]:
    """{card_id: mount path} for every mounted volume that carries a Pawtation manifest."""
    found = {}
    for vol in (candidate_volumes() if volumes is None else volumes):
        try:
            m = load_json(Path(vol) / MANIFEST_NAME, {})
        except OSError:
            continue
        if m.get("card_id") is not None:
            found.setdefault(str(m["card_id"]), str(vol))
    return found


def configured_mount(cfg, card_id: str) -> str | None:
    """The mount remembered in config.json for a card, but only if a folder is there and it is not labelled as a
    DIFFERENT card. With one card reader every card is remembered at the same drive letter, so the letter alone
    says nothing about which card is in it."""
    c = cfg["cards"].get(str(card_id))
    conf = c.get("mount") if isinstance(c, dict) else None
    if not conf or not isinstance(conf, str) or not os.path.isdir(conf):
        return None
    other = load_manifest(Path(conf)).get("card_id")
    return conf if other is None or str(other) == str(card_id) else None


def labelled_cards(cfg) -> dict[str, str]:
    """{card_id: mount} for configured cards that are plugged in AND carry their own Pawtation label (what `sync all`
    means by 'every plugged-in card Pawtation has labelled before')."""
    found = {c: m for c, m in find_cards().items() if c in cfg["cards"]}
    for cid in card_ids(cfg):
        conf = configured_mount(cfg, cid)
        if cid not in found and conf and str(load_manifest(Path(conf)).get("card_id")) == cid:
            found[cid] = conf
    return found


def resolve_mount(cfg, card_id: str, explicit: str | None = None) -> str | None:
    """--mount wins, then a mounted card whose own label is this card, then the remembered mount (only if a folder is
    there and it is not labelled as another card)."""
    return explicit or find_cards().get(str(card_id)) or configured_mount(cfg, card_id)


def card_contents(mount: str) -> dict:
    """What Pawtation believes is on a card: {"card_id","label","updated","titles":{key:title}} (empty if unmanaged)."""
    m = load_manifest(Path(mount))
    return {"card_id": m.get("card_id"), "label": m.get("label"), "updated": m.get("updated"),
            "titles": {str(k): str(m["titles"].get(k, k)) for k in m["files"]}}


def volume_info(path: str) -> dict:
    """Best-effort facts about the drive holding path: {"fs", "removable", "total", "free", "label"} (None when
    unknown). Read-only. Windows asks the OS; Linux reads /proc/mounts; elsewhere only the sizes are known."""
    out = {"fs": None, "removable": None, "total": None, "free": None, "label": None}
    try:
        u = shutil.disk_usage(path)
        out["total"], out["free"] = u.total, u.free
    except OSError:
        return out
    if os.name == "nt":
        try:
            import ctypes
            k32 = ctypes.windll.kernel32
            root = ctypes.create_unicode_buffer(261)
            if k32.GetVolumePathNameW(str(path), root, 261):
                fs, label = ctypes.create_unicode_buffer(261), ctypes.create_unicode_buffer(261)
                if k32.GetVolumeInformationW(root.value, label, 261, None, None, None, fs, 261):
                    out["fs"], out["label"] = fs.value or None, label.value or None
                out["removable"] = k32.GetDriveTypeW(root.value) == 2          # DRIVE_REMOVABLE (SD readers)
        except Exception:
            pass
    elif os.path.exists("/proc/mounts"):
        try:
            real, best = os.path.realpath(path), ""
            for line in Path("/proc/mounts").read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    mnt = parts[1].replace("\\040", " ")
                    if (real == mnt or real.startswith(mnt.rstrip("/") + "/")) and len(mnt) >= len(best):
                        best, out["fs"] = mnt, parts[2]
        except OSError:
            pass
    return out


FAT_NAMES = {"fat", "fat12", "fat16", "fat32", "vfat", "msdos"}


# ---------- boot card (Action Replay SD Media Launcher) ----------
BOOT_MAX_BYTES = int(2.1 * 1024**3)   # AR SD Media Launcher: standard SD only, 2 GB max (not SDHC/SDXC)


class GameCardError(OSError):
    """prepare_boot_card refused: the chosen card is one of the rotated game cards."""


def prepare_boot_card(mount: str, swiss_dol: str, dry_run=True, log=print, force=False) -> dict:
    """Copy the release's ActionReplay/AUTOEXEC.DOL to <mount>/autoexec.dol so the Action Replay starts Swiss.
    We never download Swiss; the owner passes the file from an official release (docs/GAMECUBE_GUIDE.md).
    Refuses a card carrying a Pawtation game-card label unless force. Warnings come back BEFORE anything is written
    in a dry run, so callers can show them first. The copy is atomic; an existing, different autoexec.dol is kept as
    autoexec.dol.bak (one generation), and an identical one is left alone (so a retry never overwrites the backup)."""
    m, d = Path(mount), Path(swiss_dol)
    if not m.is_dir():
        raise FileNotFoundError(f"Mount path not found: {mount}")
    if not d.is_file() or d.suffix.lower() != ".dol":
        raise FileNotFoundError(f"Swiss DOL not found (need a .dol file): {swiss_dol}")
    if (m / MANIFEST_NAME).exists() and not force:
        raise GameCardError(f"{mount} is one of your GAME cards (it has a Pawtation label), not the boot card. "
                            "Nothing was written. (Use force / --force if you really mean this card.)")
    warn = []
    if shutil.disk_usage(m).total > BOOT_MAX_BYTES:
        warn.append("Card is larger than 2 GB: the Action Replay SD Media Launcher likely won't read it (SDHC/SDXC unsupported).")
    if (m / MANIFEST_NAME).exists():
        warn.append("This is one of your GAME cards (it has a Pawtation label); writing to it anyway as asked.")
    fs = volume_info(str(m)).get("fs")
    if fs and fs.lower() not in FAT_NAMES:
        warn.append(f"The card is formatted as {fs}; the Action Replay needs FAT (Windows offers FAT for a card this "
                    "small). Format it as FAT first.")
    if d.name.lower() != "autoexec.dol":
        warn.append(f"{d.name} is not the release's ActionReplay/AUTOEXEC.DOL, which is the file the guide uses for an "
                    "Action Replay boot card. The Action Replay may not start it.")
    if not os.path.ismount(str(m)):
        warn.append("This folder is not the top of a card; the Action Replay only looks in the card's top folder.")
    target = m / "autoexec.dol"
    new = d.read_bytes()
    same = target.is_file() and target.read_bytes() == new
    log(f"{tag_dry(dry_run)}{'already there: ' if same else 'copy '}{d.name} -> {target}")
    if not dry_run and not same:
        if target.is_file():
            shutil.copyfile(target, m / "autoexec.dol.bak")
        _write_atomic(target, [new])
    return {"target": str(target), "warnings": warn, "unchanged": same}


def tag_dry(dry_run: bool) -> str:
    return "[dry] " if dry_run else ""
