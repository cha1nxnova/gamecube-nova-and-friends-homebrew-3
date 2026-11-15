"""The cast: who exists (data/cast.json), who is home right now (state["scene"]) and the scenes they play
(data/scenes.json, plus After Dark and packs/). Contracts: docs/SPEC_V2.md sections 1, 2 and 4.

Rules this module keeps:
- No character id is hard-coded in logic; code relies on roles (main / guest / cameo) only. The single exception
  is BUILTIN_CAST, the fallback used when data/cast.json is missing or unusable.
- Nothing here raises on bad data. A damaged cast / scenes / pack / state file degrades to defaults.
- Everything that depends on time or chance takes `now` / `rng`, so tests never patch the clock.
  `now` may be a datetime, a POSIX timestamp or None (= the real clock).
- After Dark content (data/afterdark/, packs rated "afterdark") is read from disk only when a caller passes
  unlocked=True; callers get that flag from `afterdark.is_unlocked(state)`.
"""
from __future__ import annotations

import datetime
import math
import random
import re
import string
import time

from .core import DATA_DIR, ROOT, load_json

# Tests point these somewhere else and call reload().
CAST_PATH = DATA_DIR / "cast.json"
SCENES_PATH = DATA_DIR / "scenes.json"
AFTERDARK_DIR = DATA_DIR / "afterdark"          # pets.json + scenes.json, loaded only when unlocked
PACKS_DIR = ROOT / "packs"                      # packs/<name>/{pack.json, pets.json, scenes.json, sprites/}

ROLES = ("main", "guest", "cameo")
RATINGS = ("all", "afterdark")
EVENT_WHENS = ("arrive", "leave", "rotated", "synced", "due")   # moments that never fall back to an "any" scene
CAMEO_GROUP = "cameo"                           # presence key: the usual group plus one random cameo
MAX_HOLD_MINUTES = 24 * 60                      # no group, manual or drawn, lasts longer than a day

BUILTIN_CAST = {
    "version": 1,
    "characters": {
        "nova": {"name": "Nova", "species": "serval", "pronouns": "he/him", "role": "main", "aliases": ["nova"],
                 "color": "#2b2d42", "accent": "#f52fd2"},
        "iggy": {"name": "Iggy", "species": "fennec fox", "pronouns": "any/all", "role": "main", "aliases": ["iggy"],
                 "color": "#d2b48c", "accent": "#7582b5"}},
    "presence": {"groups": {"iggy+nova": 70, "nova": 15, "iggy": 15}, "min_minutes": 20, "max_minutes": 90},
}

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_CACHE: dict = {}


# ---------- small helpers ----------
def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _text(x) -> str:
    return " ".join(x.split()) if isinstance(x, str) else ""


def _ts(now) -> float:
    """POSIX seconds from a datetime, a number or None (the real clock)."""
    if isinstance(now, datetime.datetime):
        try:
            return now.timestamp()
        except (OverflowError, OSError, ValueError):
            return time.time()
    return float(now) if _num(now) else time.time()


def _dt(now) -> datetime.datetime:
    """Local datetime from a datetime, a number or None (the real clock)."""
    if isinstance(now, datetime.datetime):
        return now
    if _num(now):
        try:
            return datetime.datetime.fromtimestamp(now)
        except (OverflowError, OSError, ValueError):
            pass
    return datetime.datetime.now()


def fill(line, context=None) -> str:
    """Format a content line. An unknown {placeholder} or a stray brace must never crash the app."""
    try:
        return str(line).format(**(context if isinstance(context, dict) else {}))
    except Exception:
        return str(line)


def _placeholders(line: str) -> set:
    try:
        return {re.split(r"[.\[]", f, maxsplit=1)[0] for _, f, _, _ in string.Formatter().parse(line) if f}
    except ValueError:                           # stray brace: fill() will print the line as written
        return set()


# ---------- the cast file ----------
def _clean_characters(raw) -> dict:
    out: dict = {}
    for cid, c in raw.items() if isinstance(raw, dict) else []:
        if not (isinstance(cid, str) and isinstance(c, dict)):
            continue
        cid = cid.strip().lower()
        if not _ID.match(cid) or cid == CAMEO_GROUP or cid in out:
            continue
        name = _text(c.get("name")) or cid.title()
        seen, aliases = set(), []
        for a in [cid, name] + (c["aliases"] if isinstance(c.get("aliases"), list) else []):
            a = _text(a).lower()
            if a and a not in seen:
                seen.add(a); aliases.append(a)
        role = c.get("role") if isinstance(c.get("role"), str) and c.get("role") in ROLES else "cameo"
        out[cid] = {"name": name, "species": _text(c.get("species")), "pronouns": _text(c.get("pronouns")), "role": role,
                    "aliases": aliases,
                    "color": c["color"] if isinstance(c.get("color"), str) and _HEX.match(c["color"]) else "",
                    "accent": c["accent"] if isinstance(c.get("accent"), str) and _HEX.match(c["accent"]) else ""}
    return out


def _default_groups(chars: dict) -> dict:
    """Role-based odds for a cast file that gives none: the mains mostly together, a guest now and then."""
    mains = [i for i, c in chars.items() if c["role"] == "main"]
    guests = [i for i, c in chars.items() if c["role"] == "guest"]
    groups = {group_key(mains): 58.0}
    if len(mains) > 1:
        for m in mains:
            groups[group_key([m])] = 9.0
    for g in guests:
        groups[group_key(mains + [g])] = 10.0
        if len(mains) > 1:
            for m in mains:
                groups[group_key([m, g])] = 5.0
    if any(c["role"] == "cameo" for c in chars.values()):
        groups[CAMEO_GROUP] = 4.0
    return groups


def _clean_presence(raw, chars: dict) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    groups: dict = {}
    for key, w in raw["groups"].items() if isinstance(raw.get("groups"), dict) else []:
        if not (isinstance(key, str) and _num(w) and w > 0):
            continue
        if key.strip().lower() == CAMEO_GROUP:
            if any(c["role"] == "cameo" for c in chars.values()):
                groups[CAMEO_GROUP] = groups.get(CAMEO_GROUP, 0.0) + float(w)
            continue
        ids = [p.strip().lower() for p in key.split("+")]
        if any(i not in chars or chars[i]["role"] == "cameo" for i in ids):
            continue                                            # unknown member, or a cameo outside the cameo slot
        if not any(chars[i]["role"] == "main" for i in ids):
            continue                                            # random presence always keeps a main at home
        k = group_key(ids)
        groups[k] = groups.get(k, 0.0) + float(w)
    if not any(k != CAMEO_GROUP for k in groups):
        cameo = groups.get(CAMEO_GROUP)
        groups = _default_groups(chars)
        if cameo:
            groups[CAMEO_GROUP] = cameo
    lo = raw.get("min_minutes") if _num(raw.get("min_minutes")) and raw["min_minutes"] > 0 else 20
    hi = raw.get("max_minutes") if _num(raw.get("max_minutes")) and raw["max_minutes"] > 0 else 90
    lo, hi = sorted((min(lo, MAX_HOLD_MINUTES), min(hi, MAX_HOLD_MINUTES)))
    return {"groups": groups, "min_minutes": lo, "max_minutes": hi}


def load_cast() -> dict:
    """The validated cast: {"version", "characters": {id: {name, species, pronouns, role, aliases, color, accent}},
    "presence": {"groups": {group key: weight}, "min_minutes", "max_minutes"}}. Cached; treat it as read-only.
    A missing or unusable data/cast.json (no main character) falls back to BUILTIN_CAST."""
    if _CACHE.get("cast") is None:
        raw = load_json(CAST_PATH, {})
        chars = _clean_characters(raw.get("characters"))
        if not any(c["role"] == "main" for c in chars.values()):
            raw, chars = BUILTIN_CAST, _clean_characters(BUILTIN_CAST["characters"])
        _CACHE["cast"] = {"version": 1, "characters": chars, "presence": _clean_presence(raw.get("presence"), chars)}
    return _CACHE["cast"]


def reload() -> dict:
    """Forget everything cached (cast, scenes, packs) and read the files again. For tests and a 'reload' button."""
    _CACHE.clear()
    return load_cast()


def characters() -> dict:
    return load_cast()["characters"]


def character(cid) -> dict:
    """One character's entry, or {} for an unknown id."""
    c = characters().get(cid) if isinstance(cid, str) else None
    return c if c else {}


def ids(*roles) -> list:
    """Character ids in cast.json order; pass roles to filter: ids("main"), ids("main", "guest")."""
    return [i for i, c in characters().items() if not roles or c["role"] in roles]


def mains() -> list:
    return ids("main")


def guests() -> list:
    return ids("guest")


def cameos() -> list:
    return ids("cameo")


def regulars() -> list:
    """Everyone who is not a cameo (mains, then guests): the characters with stats and meetups."""
    return mains() + guests()


def role(cid) -> str:
    return character(cid).get("role", "")


def name(cid) -> str:
    """Display name; an unknown id is title-cased rather than refused."""
    return character(cid).get("name") or (str(cid).title() if isinstance(cid, str) else "?")


def names(who, joiner: str = "and") -> str:
    """'Nova', 'Nova and Iggy', 'Nova, Iggy and Duskie'."""
    labels = [name(i) for i in order(who)]
    if len(labels) < 2:
        return "".join(labels)
    return ", ".join(labels[:-1]) + f" {joiner} " + labels[-1]


def order(who) -> list:
    """Known ids from `who`, de-duplicated, in cast.json order (mains first if the file lists them first)."""
    if isinstance(who, str):
        who = who.split("+")
    try:
        wanted = {i for i in who if isinstance(i, str)}
    except TypeError:
        return []
    return [i for i in characters() if i in wanted]


def group_key(who) -> str:
    """Participant ids sorted alphabetically and joined with '+': group_key(["nova", "duskie"]) == "duskie+nova"."""
    if isinstance(who, str):
        who = who.split("+")
    try:
        return "+".join(sorted({i.strip().lower() for i in who if isinstance(i, str) and i.strip()}))
    except TypeError:
        return ""


def resolve(token) -> str | None:
    """An id, display name or alias (any case) -> id. None if nobody answers to it."""
    t = _text(token).lower()
    if not t:
        return None
    chars = characters()
    if t in chars:
        return t
    for cid, c in chars.items():
        if t in c["aliases"]:
            return cid
    return None


def find(text, strict: bool = False) -> list:
    """Ids of the characters a sentence names, in order of first mention. Whole words only ('cat' is not in
    'catalog'). strict=True matches ids and display names only, not the looser aliases such as a species."""
    low = text.lower() if isinstance(text, str) else ""
    hits = []
    for cid, c in characters().items():
        words = [cid, c["name"].lower()] if strict else c["aliases"]
        at = [m.start() for w in words for m in [re.search(rf"(?<![a-z0-9]){re.escape(w)}(?![a-z0-9])", low)] if m]
        if at:
            hits.append((min(at), cid))
    return [cid for _, cid in sorted(hits)]


# ---------- presence: who is home ----------
def default_group() -> list:
    """The usual group: the heaviest presence group made only of mains (in the shipped cast, the two mascots)."""
    cast = load_cast()
    chars, best = cast["characters"], None
    for key, w in cast["presence"]["groups"].items():
        members = key.split("+")
        if key != CAMEO_GROUP and all(chars[i]["role"] == "main" for i in members):
            if best is None or (w, len(members)) > best[0]:
                best = ((w, len(members)), members)
    return sorted(best[1] if best else mains())


def clean_scene_state(value) -> dict:
    """state["scene"] in its one legal shape; anything else becomes the empty default (nobody stored yet)."""
    who, until, manual = [], 0, False
    if isinstance(value, dict):
        if isinstance(value.get("who"), list):
            who = sorted({i for i in value["who"] if isinstance(i, str)})
        if _num(value.get("until")):
            until = value["until"]
        manual = value.get("manual") is True
    return {"who": who, "until": until, "manual": manual}


def _stored(state):
    """(who or None, until, manual) from state["scene"]. `who` is None unless it names at least one known,
    non-cameo character (a cameo is never home alone)."""
    sc = clean_scene_state(state.get("scene") if isinstance(state, dict) else None)
    chars = characters()
    who = [i for i in sc["who"] if i in chars]
    if not any(chars[i]["role"] != "cameo" for i in who):
        return None, 0.0, False
    return who, float(sc["until"]), sc["manual"]


def _store(state, who, until: float, manual: bool) -> None:
    if isinstance(state, dict):
        state["scene"] = {"who": sorted(who), "until": until, "manual": bool(manual)}


def _change(old, new) -> dict:
    return {"who": sorted(new), "arrived": order([i for i in new if i not in old]),
            "left": order([i for i in old if i not in new]), "changed": set(old) != set(new)}


def present(state, now=None) -> list:
    """Ids of who is home, sorted (so group_key(present(...)) is just '+'.join). Never mutates `state`.
    An expired group stays home until step() moves it; with nothing stored, the usual group is home.
    (`now` is accepted so every presence call has the same shape; expiry is step()'s business.)"""
    who, _until, _manual = _stored(state)
    return who if who else default_group()


def is_manual(state) -> bool:
    return bool(_stored(state)[2])


def remaining(state, now=None) -> float:
    """Seconds until step() will draw a new group (0 when it is due)."""
    who, until, _manual = _stored(state)
    left = until - _ts(now) if who else 0.0
    return left if 0 < left <= MAX_HOLD_MINUTES * 60 + 60 else 0.0


def _draw(rng) -> list:
    cast = load_cast()
    groups = cast["presence"]["groups"]
    keys = list(groups)
    key = rng.choices(keys, weights=[groups[k] for k in keys], k=1)[0]
    if key == CAMEO_GROUP:
        who = default_group()
        walk_ons = cameos()
        if walk_ons:
            who.append(rng.choice(walk_ons))
    else:
        who = key.split("+")
    if not any(role(i) == "main" for i in who):                 # cannot happen with a validated cast; cheap to keep
        who.append(rng.choice(mains()))
    return sorted(set(who))


def step(state, now=None, rng=None) -> dict:
    """Advance presence. While the current group has time left this is a no-op; once it has expired (or nothing
    is stored) a new group is drawn by the presence weights and stored in state["scene"].
    Returns {"who": [...], "arrived": [...], "left": [...], "changed": bool}."""
    rng = rng or random
    ts = _ts(now)
    old = present(state)
    if remaining(state, ts) > 0:
        return {"who": old, "arrived": [], "left": [], "changed": False}
    new = _draw(rng)
    p = load_cast()["presence"]
    _store(state, new, ts + rng.uniform(p["min_minutes"], p["max_minutes"]) * 60, False)
    return _change(old, new)


def shuffle(state, now=None, rng=None) -> dict:
    """Draw a new random group right now, even if the current one has time left. Same result shape as step()."""
    old = present(state)
    if isinstance(state, dict):
        state["scene"] = clean_scene_state(None)
    return _change(old, step(state, now, rng)["who"])


def gather(state, who, minutes=None, now=None) -> dict:
    """Set who is home by hand: any non-empty set of non-cameo characters (ids, names or aliases; anything
    unknown is ignored). The group lasts `minutes` (default: presence max_minutes), then presence is random again.
    Returns step()'s shape plus "error": "" on success, or a message (and nothing changed) if nobody was named."""
    if isinstance(who, str):
        who = re.split(r"[+,\s]+", who)
    try:
        wanted = order([resolve(i) for i in who])
    except TypeError:
        wanted = []
    wanted = [i for i in wanted if role(i) != "cameo"]
    old = present(state)
    if not wanted:
        return {"who": old, "arrived": [], "left": [], "changed": False,
                "error": f"Nobody to gather. Name at least one of: {names(regulars(), 'or')}."}
    hold = minutes if _num(minutes) and minutes > 0 else load_cast()["presence"]["max_minutes"]
    _store(state, wanted, _ts(now) + min(hold, MAX_HOLD_MINUTES) * 60, True)
    return dict(_change(old, wanted), error="")


# ---------- scenes, After Dark and packs ----------
def _clean_scene(raw, source: str, index: int, force_afterdark: bool):
    if not isinstance(raw, dict):
        return None
    chars = characters()
    who = raw.get("who")
    if isinstance(who, str):
        who = who.split("+")
    if not isinstance(who, list) or not who or not all(isinstance(i, str) and i.strip().lower() in chars for i in who):
        return None
    who = sorted({i.strip().lower() for i in who})
    when = raw.get("when", "any")
    if not (isinstance(when, str) and when.strip()):
        return None
    lines = []
    for row in raw["lines"] if isinstance(raw.get("lines"), list) else []:
        if (isinstance(row, (list, tuple)) and len(row) == 2 and isinstance(row[0], str) and _text(row[1])
                and (row[0] == "*" or row[0].strip().lower() in who)):
            lines.append([row[0].strip().lower(), _text(row[1])])
    if not lines:
        return None
    rating = "all" if raw.get("rating", "all") == "all" and not force_afterdark else "afterdark"   # fail closed
    about = raw.get("about")
    if isinstance(about, str):
        about = [about]
    about = sorted({i for i in about if isinstance(i, str) and i in who}) if isinstance(about, list) else []
    if not about:                                               # who an arrive/leave scene is about, by default
        about = [i for i in who if chars[i]["role"] != "main"] or list(who)
    return {"id": _text(raw.get("id")) or f"{source}#{index}", "who": who, "key": "+".join(who), "when": when.strip().lower(),
            "rating": rating, "weight": float(raw["weight"]) if _num(raw.get("weight")) and raw["weight"] > 0 else 1.0,
            "lines": lines, "about": about, "source": source,
            "needs": sorted(set().union(*[_placeholders(t) for _, t in lines]))}


def _scenes_file(path, source: str, force_afterdark: bool) -> list:
    raw = load_json(path, None)
    rows = raw.get("scenes") if isinstance(raw, dict) else raw
    out = []
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        scene = _clean_scene(row, source, i, force_afterdark)
        if scene:
            out.append(scene)
    return out


def _pack_dirs() -> list:
    """[(folder, name, rating)] for every pack folder. A pack is rated "all" only if its pack.json says exactly
    that; a missing, unreadable or odd pack.json makes it an After Dark pack (fail closed)."""
    if "packs" not in _CACHE:
        found = []
        try:
            folders = sorted(p for p in PACKS_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
        except OSError:
            folders = []
        for folder in folders:
            meta = load_json(folder / "pack.json", {})
            rating = "all" if meta.get("rating") == "all" else "afterdark"
            found.append((folder, _text(meta.get("name")) or folder.name, rating))
        _CACHE["packs"] = found
    return _CACHE["packs"]


def _tier(rating: str) -> dict:
    """Everything one rating tier adds, read on first use: {"scenes": [...], "pets": [pets.json-shaped dicts]}.
    The "afterdark" tier is only ever asked for by a caller that passed unlocked=True."""
    cached = _CACHE.setdefault("tiers", {})
    if rating not in cached:
        after = rating == "afterdark"
        scenes, pets = [], []
        if after:
            scenes += _scenes_file(AFTERDARK_DIR / "scenes.json", "afterdark", True)
            pets.append(load_json(AFTERDARK_DIR / "pets.json", {}))
        else:
            scenes += _scenes_file(SCENES_PATH, "builtin", False)
        for folder, _name, pack_rating in _pack_dirs():
            if pack_rating == rating:
                scenes += _scenes_file(folder / "scenes.json", f"pack:{folder.name}", after)
                pets.append(load_json(folder / "pets.json", {}))
        cached[rating] = {"scenes": scenes, "pets": [p for p in pets if p]}
    return cached[rating]


def all_scenes(unlocked: bool = False) -> list:
    """Every usable scene: data/scenes.json and packs rated "all", plus (only when unlocked) data/afterdark and
    packs rated "afterdark". Sources are appended, never replaced. Each scene is the validated dict
    {id, who, key, when, rating, weight, lines, about, source, needs}; treat them as read-only."""
    unlocked = unlocked is True
    scenes = [s for s in _tier("all")["scenes"] if unlocked or s["rating"] == "all"]
    return scenes + (_tier("afterdark")["scenes"] if unlocked else [])


def extra_pets(unlocked: bool = False) -> list:
    """pets.json-shaped dicts whose lists are appended to data/pets.json: packs rated "all", plus (only when
    unlocked) data/afterdark/pets.json and packs rated "afterdark". Unvalidated: pawtation/pets.py checks shapes."""
    return _tier("all")["pets"] + (_tier("afterdark")["pets"] if unlocked is True else [])


def packs(unlocked: bool = False) -> list:
    """Packs whose content is in play: [{"name", "rating", "path"}] (for the sprite loader and `doctor`)."""
    return [{"name": n, "rating": r, "path": folder} for folder, n, r in _pack_dirs() if r == "all" or unlocked is True]


def time_when(now=None) -> str:
    """The time-of-day moment for scenes: "night" (22:00-05:00 local), "morning" (05:00-11:00), else "any"."""
    hour = _dt(now).hour
    return "night" if hour >= 22 or hour < 5 else "morning" if hour < 11 else "any"


def _about_ok(scene: dict, when: str, movers) -> bool:
    """An arrive/leave scene fits a presence change only if it is about exactly the characters who moved."""
    if when not in ("arrive", "leave") or not isinstance(movers, (list, tuple, set)):
        return True
    return set(scene["about"]) == {i for i in movers if isinstance(i, str)}


def pick_scene(who, when="any", *, unlocked: bool = False, rng=None, context=None, avoid=None):
    """A scene for exactly the set `who` at the moment `when`, or None.

    Scenes whose `when` equals the moment are preferred. If there are none, "any" scenes are the fallback pool,
    except for the event moments (EVENT_WHENS), which return None so the caller can use per-character lines.
    A walk-on cameo does not silence the others: with no scene for the full set, the non-cameo set is tried.
    `context` supplies placeholder values ({game}, {card}); a scene that needs one the context lacks is skipped.
    For "arrive" / "leave", context["movers"] (who arrived / left) must equal the scene's `about`.
    `avoid` is a scene id to skip while there is another choice (no immediate repeats)."""
    rng = rng or random
    ctx = context if isinstance(context, dict) else {}
    when = when.strip().lower() if isinstance(when, str) and when.strip() else "any"
    there = order(who)
    if not there:
        return None
    keys = [group_key(there)]
    core_set = [i for i in there if role(i) != "cameo"]
    if core_set and len(core_set) != len(there):
        keys.append(group_key(core_set))
    scenes = all_scenes(unlocked)
    for key in keys:
        pool = [s for s in scenes if s["key"] == key and all(n in ctx for n in s["needs"])]
        hits = [s for s in pool if s["when"] == when and _about_ok(s, when, ctx.get("movers"))]
        if not hits and when not in EVENT_WHENS:
            hits = [s for s in pool if s["when"] == "any"]
        if hits:
            if avoid is not None and len(hits) > 1:
                hits = [s for s in hits if s["id"] != avoid] or hits
            return rng.choices(hits, weights=[s["weight"] for s in hits], k=1)[0]
    return None


def script(scene, context=None) -> list:
    """[(speaker id or "*", formatted text), ...] for a scene. A malformed scene yields what can be read."""
    rows = scene.get("lines") if isinstance(scene, dict) else None
    out = []
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, (list, tuple)) and len(row) == 2 and all(isinstance(x, str) for x in row):
            out.append((row[0], fill(row[1], context)))
    return out


def play(scene, context=None) -> list:
    """A scene as display lines: "Name: text", and stage directions ("*") as "(text)"."""
    return [f"({text})" if who == "*" else f"{name(who)}: {text}" for who, text in script(scene, context)]
