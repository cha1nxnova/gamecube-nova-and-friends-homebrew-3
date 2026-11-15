"""Pawtation core: config, library scan, catalog matching, rotation planner, SD sync.

Pure standard library. No network. Everything here is UI-agnostic so the CLI,
the desktop GUI, and any future front-end (web, GameCube-side) share one brain.
"""
from __future__ import annotations

import json
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

from . import discimage

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
# Your settings + ratings live next to the app by default. Set PAWTATION_HOME to keep them elsewhere
# (handy for a second profile, or for tests that must not touch your real files).
HOME = Path(os.environ.get("PAWTATION_HOME") or ROOT)
CONFIG_PATH = HOME / "config.json"
STATE_PATH = HOME / "state.json"
MANIFEST_NAME = ".pawtation.json"   # written to each SD card root; only files listed here are ever deleted

DEFAULT_CONFIG = {
    "library_dir": "",                       # folder holding your legally acquired disc images
    "extensions": [".iso", ".gcm", ".ciso", ".gcz"],
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
    return data if isinstance(data, type(default)) else default


def save_json(path: Path, obj):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
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
    return cfg


def update_config(**changes) -> dict:
    """Change a few keys in the user's config.json without rewriting the rest. Returns the fresh merged config."""
    user = load_json(CONFIG_PATH, {})
    user.update(changes)
    save_json(CONFIG_PATH, user)
    return load_config()


def mods_dir(cfg) -> Path:
    return Path(cfg.get("mods_dir") or (ROOT / "mods"))


def load_state() -> dict:
    st = load_json(STATE_PATH, {})
    st.setdefault("ratings", {})          # key -> 1..5
    st.setdefault("history", [])          # list of {"ts","season","plan"}
    st.setdefault("last_rotation_ts", 0)
    st.setdefault("last_on_card", {})     # key -> ts it last got loaded onto any card
    st.setdefault("pets", {"mochi": {"affection": 5, "energy": 5}, "biscuit": {"affection": 5, "energy": 5}})
    st.setdefault("plays", {})            # key -> manual play count (GUI "I played this" button)
    for pet in ("mochi", "biscuit"):
        st["pets"].setdefault(pet, {"affection": 5, "energy": 5})
    return st


def save_state(st):
    save_json(STATE_PATH, st)


# ---------- catalog ----------
def load_catalog() -> list[dict]:
    games = load_json(DATA_DIR / "catalog.json", {"games": []}).get("games", [])
    return [g for g in games if isinstance(g, dict) and g.get("key") and g.get("title")]


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
        self.games = games if games is not None else load_catalog()
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
        """False for compressed containers (.ciso/.gcz/.rvz): Swiss refuses them, so they never go on a card."""
        return all(Path(d["path"]).suffix.lower() in LAUNCHABLE_EXTS for d in self.discs)

    def __post_init__(self):
        if not self.discs:
            self.discs = [{"path": self.path, "size": self.size, "disc": 1}]


def read_disc_header(path: Path):
    """(code6, internal title) from a disc image, or (None, None). Handles ISO/GCM/CISO/GCZ/RVZ (see discimage.py)."""
    h = discimage.read_header(path)
    return (h["code6"], h["title"]) if h else (None, None)


def scan_library(cfg, catalog: Catalog | None = None) -> list[Rom]:
    """Find disc images under library_dir. Multi-disc games become ONE Rom with several `discs`."""
    catalog = catalog or Catalog()
    lib = cfg.get("library_dir")
    if not lib or not Path(lib).is_dir():
        return []
    exts = {e.lower() for e in cfg["extensions"]}
    roms: dict[str, Rom] = {}
    for p in sorted(Path(lib).rglob("*")):
        try:
            if not (p.is_file() and p.suffix.lower() in exts) or p.name.startswith("."):
                continue
            size = p.stat().st_size
        except OSError:
            continue
        h = discimage.read_header(p)
        code, internal = (h["code6"], h["title"]) if h else (None, None)
        disc_no = h["disc"] if h else discimage.disc_from_filename(p.name)
        g = catalog.match(code, p.name)
        key = g["key"] if g else slugify(internal or re.sub(r"\(.*?\)|\[.*?\]", " ", p.stem))
        disc = {"path": str(p), "size": size, "disc": disc_no}
        if key not in roms:
            roms[key] = Rom(str(p), size, code, internal, key, g["title"] if g else (internal or p.stem),
                            bool(g), list(g.get("tags", [])) if g else [], [disc])
            continue
        rom = roms[key]
        if any(d["disc"] == disc_no for d in rom.discs):   # duplicate dump of the same disc: keep the first
            continue
        rom.discs.append(disc)
        rom.discs.sort(key=lambda d: d["disc"])
        rom.size = sum(d["size"] for d in rom.discs)
        rom.path = rom.discs[0]["path"]
    return list(roms.values())


# ---------- rotation planner ----------
def card_ids(cfg) -> list[str]:
    return sorted(cfg["cards"], key=lambda c: (0, int(c), "") if str(c).isdigit() else (1, 0, str(c)))


def card_budget(cfg, card: dict) -> int:
    return max(0, int(float(card.get("capacity_gb", 0)) * 1024**3) - int(cfg["reserve_mb"]) * 1024**2)


def game_score(rom: Rom, state: dict, now: float) -> float:
    """Higher = more deserving of a slot. Ratings dominate, staleness breaks ties, a little jitter stays fun."""
    rating = state["ratings"].get(rom.key, 3)
    last = state["last_on_card"].get(rom.key, 0)
    days_off = min(365, max(0.0, now - last) / 86400) if last else 365
    return rating * 10 + days_off / 7.0


SCORE_HOOKS: list = []   # plugins may append fn(rom, state, now) -> float bonus (see pawtation/plugins.py)


def plan_rotation(cfg, state, roms: list[Rom], now: float | None = None) -> dict:
    """Return {card_id: [rom_key,...]}. Pins first (one favorite per card, in order), then
    greedy fill by score. Each game appears on at most one card per season."""
    now = time.time() if now is None else now
    season = len(state["history"]) + 1
    rng = random.Random(cfg["seed"] or (season * 7919))
    by_key = {r.key: r for r in roms}
    cards = cfg["cards"]
    ids = card_ids(cfg)
    plan = {c: [] for c in ids}
    free = {c: card_budget(cfg, cards[c]) for c in ids}
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
    season = (state["history"][-1].get("season", len(state["history"])) + 1) if state["history"] else 1
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
    if name.lower() in _WIN_RESERVED:
        name += "_"
    return name or "game"


def disc_filename(disc_no: int, suffix: str, multi: bool = False) -> str:
    """File name inside a game's folder: game.iso, or disc1.iso/disc2.iso for multi-disc games. Swiss pairs discs by
    their headers and prefers two names that differ only in the disc digit (docs/RESEARCH_NOTES.md A7)."""
    return (f"disc{disc_no}" if multi else "game") + suffix.lower()


def card_path(mount_p: Path, rel: str) -> Path | None:
    """Resolve a manifest-relative path, or None if it would escape the card (absolute, drive letter, '..').
    The manifest lives on removable media, so it is treated as untrusted input."""
    if not isinstance(rel, str) or not rel or "\\" in rel or ":" in rel or "//" in rel:
        return None
    parts = PurePosixPath(rel).parts
    if rel.startswith("/") or any(p in ("..", ".", "") for p in parts):
        return None
    return mount_p.joinpath(*parts)


def load_manifest(mount_p: Path) -> dict:
    m = load_json(Path(mount_p) / MANIFEST_NAME, {})
    for k in ("files", "more_files", "aux", "titles"):
        if not isinstance(m.get(k), dict):
            m[k] = {}
    return m


def _manifest_rels(manifest: dict, key: str) -> list[str]:
    rels = [manifest["files"][key]] if key in manifest["files"] else []
    more = manifest["more_files"].get(key, [])
    return rels + [r for r in more if isinstance(r, str)] if isinstance(more, list) else rels


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


def _copy_stream(src: Path, dest: Path, tick, cancel) -> int | None:
    """Copy src -> dest via dest+'.part' then rename, so a pulled card never leaves a half file under the real name.
    Returns the CRC32 of the bytes written, or None if cancelled."""
    part = dest.with_name(dest.name + ".part")
    crc = 0
    try:
        with open(src, "rb") as fi, open(part, "wb") as fo:
            while True:
                if cancel():
                    break
                chunk = fi.read(COPY_CHUNK)
                if not chunk:
                    fo.flush(); os.fsync(fo.fileno())
                    break
                fo.write(chunk)
                crc = zlib.crc32(chunk, crc)
                tick(len(chunk))
            else:  # pragma: no cover
                pass
        if cancel():
            part.unlink(missing_ok=True) if sys.version_info >= (3, 8) else part.unlink()
            return None
        os.replace(part, dest)
        return crc
    except BaseException:
        try: part.unlink()
        except OSError: pass
        raise


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
    if target.is_file() or target.is_symlink():
        target.unlink()
    parent = target.parent
    while parent not in stop_at and parent != mount_p and mount_p in parent.parents:   # tidy now-empty folders we made
        try: parent.rmdir()
        except OSError: break
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
    Returns {"removed","copied","kept","errors","warnings","cancelled","bytes_copied"}."""
    card_id = str(card_id)
    mount_p = Path(mount)
    if not mount_p.is_dir():
        raise FileNotFoundError(f"Mount path not found: {mount}")
    progress = progress or (lambda info: None)
    cancel = cancel or (lambda: False)
    verify = cfg.get("verify_copies", False) if verify is None else verify
    sub = safe_name(str(cfg["games_subdir"]).strip("/\\")) or "games"
    games_dir = mount_p / sub
    manifest_p = mount_p / MANIFEST_NAME
    manifest = load_manifest(mount_p)
    by_key = {r.key: r for r in roms}
    want = {k: by_key[k] for k in keys if k in by_key}
    report = {"removed": [], "copied": [], "kept": [], "errors": [], "warnings": [], "cancelled": False, "bytes_copied": 0}
    tag = "[dry] " if dry_run else ""

    for k in keys:
        if k not in by_key:
            report["warnings"].append(f"{k}: planned for this card but not found in the library (rescan?)")
    other = manifest.get("card_id")
    if other is not None and str(other) != card_id:
        msg = f"This SD card is labelled as card {other}, not card {card_id}."
        if not force:
            report["errors"].append(msg + " Nothing was changed. (Use force / --force to re-purpose it.)")
            return report
        report["warnings"].append(msg + " Re-purposing it as requested.")

    def save_manifest():
        label = cfg["cards"].get(card_id, {}).get("label", f"Card {card_id}")
        manifest.update({"card_id": card_id, "label": label, "updated": int(time.time()), "schema": 2,
                         "titles": {k: want[k].title for k in manifest["files"] if k in want}})
        save_json(manifest_p, manifest)

    # -- what should be on the card
    wanted_files: dict[str, list] = {}                          # key -> [(rel, src Path, size)]
    claimed: dict[str, str] = {}                                # folder (lowercase) -> key, FAT is case-insensitive
    for key, rom in want.items():
        folder = safe_name(rom.title)
        if claimed.setdefault(folder.lower(), key) != key:
            folder = safe_name(f"{folder[:60]} [{key[:16]}]")
        if not rom.launchable:
            report["errors"].append(f"{rom.title}: compressed image (.ciso/.gcz/.rvz). Swiss cannot start these; "
                                    "convert to .iso with Dolphin or NKit first. Skipped.")
            wanted_files[key] = []
            continue
        multi = len(rom.discs) > 1
        wanted_files[key] = [(f"{sub}/{folder}/{disc_filename(d['disc'], Path(d['path']).suffix, multi)}", Path(d["path"]), d["size"])
                             for d in rom.discs]
    wanted_aux: dict[str, tuple] = {}                           # rel -> (src Path | bytes, owner)
    for key in want:
        for rel, src in mod_files(cfg, key).items():
            wanted_aux.setdefault(rel, (src, key))
    if quips and cfg.get("export_quips", True):
        text = "\n".join(q.encode("ascii", "ignore").decode() for q in quips) + "\n"
        wanted_aux[QUIPS_REL] = (text.encode("ascii"), "pawtation")

    # -- remove what rotated out (tracked files only)
    for key in list(manifest["files"]) + [k for k in manifest["more_files"] if k not in manifest["files"]]:
        old = _manifest_rels(manifest, key)
        keep = {rel for rel, _s, _n in wanted_files.get(key, [])}
        for rel in old:
            if rel in keep:
                continue
            if card_path(mount_p, rel) is None:
                report["warnings"].append(f"ignored unsafe path in card manifest: {rel!r}")
            else:
                log(f"{tag}remove {rel}")
                progress({"phase": "remove", "title": manifest["titles"].get(key, key), "rel": rel})
                if not dry_run:
                    try:
                        _rm_tracked(mount_p, rel, {games_dir})
                    except OSError as e:
                        report["errors"].append(f"could not remove {rel}: {e}"); continue
                report["removed"].append(rel)
        if not dry_run:
            kept = [r for r in old if r in keep]
            if kept and key in want:
                manifest["files"][key] = kept[0]
                manifest["more_files"][key] = kept[1:]
                if not kept[1:]:
                    manifest["more_files"].pop(key, None)
            else:
                manifest["files"].pop(key, None); manifest["more_files"].pop(key, None)
    for rel in list(manifest["aux"]):
        if rel not in wanted_aux:
            if card_path(mount_p, rel) is None:
                report["warnings"].append(f"ignored unsafe path in card manifest: {rel!r}")
            else:
                log(f"{tag}remove {rel}")
                if not dry_run:
                    try:
                        _rm_tracked(mount_p, rel, set())
                    except OSError as e:
                        report["errors"].append(f"could not remove {rel}: {e}"); continue
                report["removed"].append(rel)
            if not dry_run:
                manifest["aux"].pop(rel, None)
    if not dry_run:
        save_manifest()

    # -- decide what needs copying
    todo = []                                                   # (key, rel, src, size, title)
    for key, files in wanted_files.items():
        tracked = set(_manifest_rels(manifest, key))
        for rel, src, size in files:
            dest = card_path(mount_p, rel)
            try:
                same = rel in tracked and dest.is_file() and dest.stat().st_size == size
            except OSError:
                same = False
            if same:
                report["kept"].append(rel)
            elif dest.exists() and rel not in tracked:
                report["errors"].append(f"{rel} already exists on the card and was not put there by Pawtation; "
                                        f"left untouched ({want[key].title} skipped)")
            else:
                todo.append((key, rel, src, size, want[key].title))
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
    for key, rel, src, size, title in todo:
        if cancel():
            report["cancelled"] = True; break
        dest = card_path(mount_p, rel)
        log(f"{tag}copy {title} -> {rel}")
        if dry_run:
            report["copied"].append(rel); continue
        try:
            if shutil.disk_usage(mount_p).free - size < reserve:
                report["errors"].append(f"not enough space for {title}"); continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            done = [0]

            def tick(n, _rel=rel, _title=title, _size=size, _base=all_done, _done=done):
                _done[0] += n
                progress({"phase": "copy", "title": _title, "rel": _rel, "file_done": _done[0], "file_total": _size,
                          "all_done": _base + _done[0], "all_total": all_total})

            crc = _copy_stream(src, dest, tick, cancel)
            if crc is None:
                report["cancelled"] = True; break
            if verify:
                progress({"phase": "verify", "title": title, "rel": rel, "file_done": size, "file_total": size,
                          "all_done": all_done + size, "all_total": all_total})
                back = file_crc32(dest, cancel)
                if back is None:
                    report["cancelled"] = True
                elif back != crc:
                    dest.unlink()
                    report["errors"].append(f"verification FAILED for {title} (card may be failing); copy removed"); continue
        except OSError as e:
            report["errors"].append(f"could not copy {title}: {e}"); continue
        all_done += size
        report["bytes_copied"] += size
        rels = [r for r in _manifest_rels(manifest, key) if r != rel] + [rel]
        order = [r for r, _s, _n in wanted_files[key] if r in rels]
        manifest["files"][key] = order[0]
        manifest["more_files"][key] = order[1:]
        if not order[1:]:
            manifest["more_files"].pop(key, None)
        save_manifest()                                         # after every file: a pulled card stays consistent
        report["copied"].append(rel)
        if report["cancelled"]:
            break

    # -- small extras (mods, quips)
    for rel, (src, owner) in wanted_aux.items():
        if report["cancelled"]:
            break
        dest = card_path(mount_p, rel)
        if dest is None or rel == MANIFEST_NAME or rel.split("/")[0].lower() == sub.lower():
            report["warnings"].append(f"mod file skipped (not allowed there): {rel}"); continue
        try:
            data = src if isinstance(src, bytes) else src.read_bytes()
            if dest.exists() and rel not in manifest["aux"]:
                report["warnings"].append(f"{rel} already exists on the card and is not ours; left untouched"); continue
            if dest.is_file() and dest.read_bytes() == data:
                report["kept"].append(rel); continue
            log(f"{tag}copy extra ({owner}) -> {rel}")
            if not dry_run:
                dest.parent.mkdir(parents=True, exist_ok=True)
                part = dest.with_name(dest.name + ".part")
                part.write_bytes(data); os.replace(part, dest)
                manifest["aux"][rel] = owner
            report["copied"].append(rel)
        except OSError as e:
            report["errors"].append(f"could not copy extra {rel}: {e}")

    if not dry_run:
        save_manifest()
    progress({"phase": "done", "all_done": all_done, "all_total": all_total})
    return report


def fmt_gb(n: int) -> str:
    return f"{n / 1024**3:.2f} GB"


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


def resolve_mount(cfg, card_id: str, explicit: str | None = None) -> str | None:
    """--mount wins, then config, then a mounted card whose manifest carries this id."""
    return explicit or cfg["cards"].get(str(card_id), {}).get("mount") or find_cards().get(str(card_id))


def card_contents(mount: str) -> dict:
    """What Pawtation believes is on a card: {"card_id","label","updated","titles":{key:title}} (empty if unmanaged)."""
    m = load_manifest(Path(mount))
    return {"card_id": m.get("card_id"), "label": m.get("label"), "updated": m.get("updated"),
            "titles": {k: m["titles"].get(k, k) for k in m["files"]}}


# ---------- boot card (Action Replay SD Media Launcher) ----------
BOOT_MAX_BYTES = int(2.1 * 1024**3)   # AR SD Media Launcher: standard SD only, 2 GB max (not SDHC/SDXC)


def prepare_boot_card(mount: str, swiss_dol: str, dry_run=True, log=print) -> dict:
    """Copy a user-supplied Swiss .dol to <mount>/autoexec.dol so the Action Replay SD Media Launcher auto-starts it.
    We never download Swiss; pass the DOL from an official release. Warns if the card looks bigger than 2 GB.
    An existing autoexec.dol is kept as autoexec.dol.bak (one generation) so a bad build can be rolled back."""
    m, d = Path(mount), Path(swiss_dol)
    if not m.is_dir():
        raise FileNotFoundError(f"Mount path not found: {mount}")
    if not d.is_file() or d.suffix.lower() != ".dol":
        raise FileNotFoundError(f"Swiss DOL not found (need a .dol file): {swiss_dol}")
    warn = []
    if shutil.disk_usage(m).total > BOOT_MAX_BYTES:
        warn.append("Card is larger than 2 GB: the Action Replay SD Media Launcher likely won't read it (SDHC/SDXC unsupported).")
    if (m / MANIFEST_NAME).exists():
        warn.append("This looks like one of your GAME cards (it has a Pawtation manifest), not the boot card.")
    target = m / "autoexec.dol"
    log(f"{tag_dry(dry_run)}copy {d.name} -> {target}")
    if not dry_run:
        if target.is_file() and target.read_bytes() != d.read_bytes():
            shutil.copyfile(target, m / "autoexec.dol.bak")
        shutil.copyfile(d, target)
    return {"target": str(target), "warnings": warn}


def tag_dry(dry_run: bool) -> str:
    return "[dry] " if dry_run else ""
