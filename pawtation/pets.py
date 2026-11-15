"""The chat characters. Rule-based, offline, deterministic-ish. No LLM needed.

Who the characters are comes from data/cast.json (pawtation/cast.py); what they say comes from data/pets.json and
data/scenes.json. Nothing here names a character: code relies on roles (main / guest / cameo) and on who is home.

Extend by editing data/pets.json (content), by adding an intent to `PetBrain.reply` (behavior), or from a
plugin with `api.chat(pattern, fn)` (see pawtation/plugins.py). Intents are tried top to bottom; first hit wins.

Content tiers: data/pets.json and packs rated "all" are always in play. data/afterdark/ and packs rated
"afterdark" are added only while `afterdark.is_unlocked(state)`; lists are appended, never replaced.
`card_quips()` uses the "all" tier only, whatever the lock says.
"""
from __future__ import annotations

import datetime
import random
import re
import time

from . import afterdark, cast
from .core import DATA_DIR, load_json, norm

PETS = load_json(DATA_DIR / "pets.json", {})
CHARS = PETS["characters"] if isinstance(PETS.get("characters"), dict) else {}
NAMES = cast.mains()       # ids of the main characters, read once at import (kept for older callers)
CHAT_HOOKS: list = []      # [(compiled regex, fn(brain, match, ctx) -> str | None)] added by plugins

# Said when data/pets.json has nothing for a character in a bucket (or is missing altogether).
GENERIC = {
    "greeting": ["Hi. Good to see you."],
    "idle": ["Just keeping the GameCube company."],
    "rotation_due": ["The cards are due for a fresh rotation."],
    "rotated": ["New rotation planned. Fresh games all round."],
    "synced": ["Card {card} is ready."],
    "ranked": ["Noted: {game}."],
    "study_break": ["Short break: water, a stretch, then back to it."],
    "arrive": ["I'm back."],
    "leave": ["Heading out for a bit."],
    "absent": ["{name} is out right now."],
}
EVENT_BUCKETS = {"rotated": "rotated", "synced": "synced", "due": "rotation_due", "arrive": "arrive", "leave": "leave"}
ANSWER_WEIGHT = {"main": 3, "guest": 2, "cameo": 1}     # who answers when the message names nobody

RX_AFTERDARK = re.compile(r"\bafter[ -]?dark\b|\b18 ?\+|\bnsfw\b")
RX_WHO_HOME = re.compile(r"\bwho(?:'s|s| is| are)? (?:all )?(?:at )?(?:home|here|around)\b|"
                         r"\b(?:anyone|anybody) (?:else )?(?:at )?(?:home|here|around)\b|"
                         r"\bwho(?:'s| is) (?:out|away|missing)\b|\broll call\b")
RX_EVERYONE = re.compile(r"^(?:everyone|everybody|all (?:three|of you|together)|the (?:whole )?gang)[.!]*$|"
                         r"\b(?:get|gather|bring|invite|call|round up|assemble)\b.*"
                         r"\b(?:everyone|everybody|every one|them all|all (?:three|of them|of you)|the (?:whole )?gang)\b|"
                         r"\b(?:everyone|everybody) (?:together|over|here|home)\b")
RX_INVITE = re.compile(r"\binvite\b|\b(?:call|bring|ask|get)\b.*\b(?:over|back|home|round)\b|"
                       r"\bcome (?:over|back|home|in|here|by|round)\b")
RX_SEND_OUT = re.compile(r"\b(?:send|kick|shoo)\b.*\b(?:out|away|off|home|outside)\b|"
                         r"\b(?:go|head|step|pop) (?:out|away|outside|off|home)\b|\bgo for a walk\b|\bshoo\b")
RX_WHERE_WHO = re.compile(r"\bwhere(?:'s| is| are| did)\b")
RX_SCENE = re.compile(r"\bhang(?:ing)? out\b|\bhangout\b|\bscenes?\b|\bmeet ?ups?\b|\bbanter\b")


# ---------- content access (every shape is checked: a damaged file must never crash the app) ----------
def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _strs(x) -> list:
    return [s for s in x if isinstance(s, str) and s] if isinstance(x, list) else []


def _fill(line: str, **fmt) -> str:
    """Format a content line; an unknown {placeholder} or stray brace in pets.json must never crash the app."""
    return cast.fill(line, fmt)


def _layers(unlocked: bool = False) -> list:
    """Content documents, base first: data/pets.json, then whatever cast.extra_pets() allows at this rating."""
    return [PETS] + [d for d in cast.extra_pets(unlocked is True) if isinstance(d, dict)]


def _lines(layers, bucket: str, pet: str) -> list:
    """Every line a character has in a per-character bucket ({"greeting": {"<id>": [...]}})."""
    out = []
    for doc in layers:
        b = doc.get(bucket)
        if isinstance(b, dict):
            out += _strs(b.get(pet))
    return out


def _rows(layers, bucket: str) -> list:
    """[[who, text], ...] buckets (jokes, fortunes), with malformed rows dropped."""
    out = []
    for doc in layers:
        b = doc.get(bucket)
        if isinstance(b, list):
            out += [(r[0], r[1]) for r in b if isinstance(r, (list, tuple)) and len(r) == 2
                    and all(isinstance(x, str) and x for x in r)]
    return out


def _options(layers, bucket: str, key: str, pet: str) -> list:
    """game_quips[key][id] / tag_quips[tag][id]: one line or a list of alternatives."""
    out = []
    for doc in layers:
        b = doc.get(bucket)
        per = b.get(key) if isinstance(b, dict) and isinstance(key, str) else None
        v = per.get(pet) if isinstance(per, dict) else None
        out += [v] if isinstance(v, str) and v else _strs(v)
    return out


def _activities(layers) -> dict:
    """name -> settings dict (the first document that defines the activity wins; later ones only add lines)."""
    out: dict = {}
    for doc in layers:
        b = doc.get("activities")
        for name, act in b.items() if isinstance(b, dict) else []:
            if isinstance(name, str) and isinstance(act, dict) and name not in out:
                out[name] = act
    return out


def _activity_lines(layers, name: str, pet: str) -> list:
    out = []
    for doc in layers:
        b = doc.get("activities")
        act = b.get(name) if isinstance(b, dict) else None
        if isinstance(act, dict):
            out += _strs(act.get(pet))
    return out


def _char(pet: str) -> dict:
    """A character's pets.json entry (name, vibe, ASCII art); packs rated "all" may add characters."""
    for doc in _layers(False):
        chars = doc.get("characters")
        c = chars.get(pet) if isinstance(chars, dict) and isinstance(pet, str) else None
        if isinstance(c, dict):
            return c
    return {}


def other(pet: str) -> str:
    """Another main character (kept for older callers that assumed exactly two)."""
    rest = [p for p in cast.mains() if p != pet]
    return rest[0] if rest else pet


class PetBrain:
    def __init__(self, state: dict, catalog, rng: random.Random | None = None, clock=None):
        """`clock` is a callable returning a datetime (default: datetime.datetime.now); tests pass a fixed one."""
        self.state, self.catalog = state, catalog
        self.rng = rng or random.Random()
        self.clock = clock or datetime.datetime.now
        self._last_scene = None
        for key, kind in (("ratings", dict), ("last_on_card", dict), ("history", list), ("pets", dict)):
            if not isinstance(state.get(key), kind):
                state[key] = kind()
        for p in cast.regulars():                                   # v1 entries (mochi, biscuit) are left alone
            self._stats(p)

    # ---- helpers
    def now(self) -> datetime.datetime:
        try:
            t = self.clock()
        except Exception:
            t = None
        return t if isinstance(t, datetime.datetime) else datetime.datetime.now()

    def unlocked(self) -> bool:
        return afterdark.is_unlocked(self.state)

    def _content(self) -> list:
        return _layers(self.unlocked())

    def _stats(self, pet: str) -> dict:
        pets = self.state["pets"] if isinstance(self.state.get("pets"), dict) else self.state.setdefault("pets", {})
        if not isinstance(pets, dict):
            pets = self.state["pets"] = {}
        s = pets.get(pet)
        if not (isinstance(s, dict) and _num(s.get("affection")) and _num(s.get("energy"))):
            s = pets[pet] = {"affection": 5, "energy": 5}
        return s

    def name(self, pet: str) -> str:
        n = _char(pet).get("name")
        return n if isinstance(n, str) and n else cast.name(pet)

    def home(self) -> list:
        """Ids of who is home right now, in cast order."""
        return cast.order(cast.present(self.state))

    def speakers(self) -> list:
        """The non-cameo characters who are home (never empty)."""
        return [p for p in self.home() if cast.role(p) != "cameo"] or cast.mains()

    def _anyone(self, home=None) -> str:
        home = home or self.home()
        return self.rng.choices(home, weights=[ANSWER_WEIGHT.get(cast.role(p), 1) for p in home], k=1)[0]

    def say(self, pet: str, bucket: str, **fmt) -> str:
        lines = _lines(self._content(), bucket, pet) or GENERIC.get(bucket) or ["..."]
        return self._line(pet, _fill(self.rng.choice(lines), **fmt))

    def _line(self, pet, text):
        return f"{self.name(pet)}: {text}"

    def art(self, pet: str, mood: str = "art") -> str:
        return "\n".join(_strs(_char(pet).get(mood)) or _strs(_char(pet).get("art")))

    def duo(self, bucket: str, **fmt) -> list[str]:
        """One line from each character who is home. Cameos join in only to say hello."""
        who = self.home()
        if bucket in ("greeting", "arrive"):
            content = self._content()
            who = [p for p in who if cast.role(p) != "cameo" or _lines(content, bucket, p)]
        else:
            who = [p for p in who if cast.role(p) != "cameo"]
        return [self.say(p, bucket, **fmt) for p in who or cast.mains()]

    def _pair(self, bucket: str, fallback: str, pet: str | None = None) -> str:
        """Buckets shaped [[who, text], ...] (jokes, fortunes): only speakers who are home get to tell one."""
        by: dict = {}
        for who, text in _rows(self._content(), bucket):
            cid = cast.resolve(who)
            if cid:
                by.setdefault(cid, []).append(text)
        home = self.home()
        tellers = [pet] if pet in home and by.get(pet) else [p for p in home if by.get(p)]
        tellers = tellers or [p for p in cast.mains() if by.get(p)]
        if not tellers:
            return self._line(pet if pet in home else self._anyone(home), fallback)
        pool = [(p, text) for p in tellers for text in by[p]]
        who, text = self.rng.choice(pool)
        return self._line(who, text)

    def _title(self, key: str) -> str:
        return self.catalog.by_key.get(key, {}).get("title", key)

    # ---- features
    def joke(self, pet: str | None = None) -> str:
        return self._pair("jokes", "I had a joke. It got away.", pet)

    def fortune(self, pet: str | None = None) -> str:
        return self._pair("fortunes", "Today looks like a good day for a game.", pet)

    def study_break(self, pet: str | None = None) -> str:
        return self.say(pet or self.rng.choice(self.speakers()), "study_break")

    def due_nag(self) -> list[str]:
        return self.event("due")

    def collection(self, roms) -> list[str]:
        """Whoever is home comments on the size of the library (pets.json -> state_of_collection: empty/few/many)."""
        bucket = "empty" if not roms else "few" if len(roms) < 15 else "many"
        lines = []
        for doc in self._content():
            b = doc.get("state_of_collection")
            lines += _strs(b.get(bucket)) if isinstance(b, dict) else []
        lines = lines or ["...", "..."]
        return [self._line(p, lines[i % len(lines)]) for i, p in enumerate(self.speakers())]

    def activities(self) -> dict:
        """name -> settings ({verb, needs, affection, energy, ...}) for every activity in play."""
        return _activities(self._content())

    def activity(self, pet: str, name: str) -> str:
        content = self._content()
        act = _activities(content).get(name) if isinstance(name, str) else None
        if not isinstance(act, dict):
            return self._line(pet, "I don't know that trick yet.")
        s = self._stats(pet)
        if act.get("needs") == "energy" and s["energy"] < 2:
            return self._line(pet, "Too sleepy for that. Try a nap or a treat?")
        num = lambda k: act.get(k) if _num(act.get(k)) else 0
        s["affection"] = max(0, min(20, s["affection"] + num("affection")))
        s["energy"] = max(0, min(10, s["energy"] + num("energy")))
        return self._line(pet, self.rng.choice(_activity_lines(content, name, pet) or ["That was nice."]))

    def mood(self, pet: str) -> str:
        pets = self.state.get("pets")
        s = pets.get(pet) if isinstance(pets, dict) else None
        s = s if isinstance(s, dict) else {}
        energy = s.get("energy") if _num(s.get("energy")) else 5
        affection = s.get("affection") if _num(s.get("affection")) else 5
        return "sleep" if energy < 2 else "happy" if affection >= 12 else "art"

    def _quip(self, layers, pet: str, key: str) -> str | None:
        g = self.catalog.by_key.get(key)
        title = g["title"] if g else key
        pick = lambda opts: opts[0] if len(opts) == 1 else self.rng.choice(opts)
        opts = _options(layers, "game_quips", key, pet)
        if opts:
            return self._line(pet, _fill(pick(opts), game=title))
        for tag in (g or {}).get("tags", []):
            opts = _options(layers, "tag_quips", tag, pet)
            if opts:
                return self._line(pet, _fill(pick(opts), game=title))
        return None

    def game_quip(self, pet: str, key: str) -> str | None:
        return self._quip(self._content(), pet, key)

    def card_quips(self, keys, limit: int = 40) -> list[str]:
        """Plain one-line quips about the games on a card, for /pawtation/quips.txt (a future on-console companion).
        Always "all"-rated content, even while After Dark is unlocked: a card can end up in anyone's console.
        Never raises: a quip problem must not get in the way of a sync."""
        try:
            return self._card_quips(keys, limit)
        except Exception:
            return []

    def _card_quips(self, keys, limit):
        layers = _layers(False)                                     # never the After Dark tier
        out = []
        for key in keys:
            for pet in cast.regulars():
                q = self._quip(layers, pet, key)
                if q:
                    out.append(q)
        for bucket in ("jokes", "fortunes"):
            items = [(cid, text) for who, text in _rows(layers, bucket) for cid in [cast.resolve(who)] if cid]
            self.rng.shuffle(items)
            items.sort(key=lambda it: cast.role(it[0]) == "cameo")  # stable: the main cast first, cameos fill up
            out += [self._line(cid, text) for cid, text in items[:10]]
        seen, uniq = set(), []
        for line in out:
            line = " ".join(line.split())
            if line not in seen:
                seen.add(line); uniq.append(line)
        return uniq[:limit]

    def suggest(self, roms, now=None) -> str:
        """Pick a game: rating-weighted, slightly favors stale/unplayed. Everyone who is home weighs in."""
        if not roms:
            return "\n".join(self.collection(roms))
        w = []
        for r in roms:
            rating = self.state["ratings"].get(r.key, 3)
            last = self.state["last_on_card"].get(r.key, 0)
            w.append(max(0.5, (rating if _num(rating) else 3) + (1.5 if not last else 0)))
        pick = self.rng.choices(roms, weights=w, k=1)[0]
        where = self.where(pick.key)
        out = [f"Tonight's pick: {pick.title}" + (f" (it's on card {where})" if where else " (not on a card this season)")]
        for p in self.speakers():
            out.append(self.game_quip(p, pick.key) or self._line(p, f"{pick.title}. I'd play that tonight."))
        return "\n".join(out)

    def where(self, key: str) -> str | None:
        hist = self.state.get("history") or []
        last = hist[-1] if isinstance(hist, list) and hist else None
        plan = last.get("plan") if isinstance(last, dict) else None
        for cid, keys in plan.items() if isinstance(plan, dict) else []:
            if isinstance(keys, (list, tuple)) and key in keys:
                return cid
        return None

    def ranking(self, roms, pet: str | None = None) -> str:
        ratings = self.state["ratings"]
        rated = [(ratings[r.key], r.title) for r in roms if _num(ratings.get(r.key)) and 1 <= ratings[r.key] <= 5]
        if not rated:
            return self._line(pet or self._anyone(), "Nothing rated yet. Tell me: 'rate paper mario 5'.")
        rated.sort(key=lambda t: (-t[0], t[1].lower()))
        rows = [f"{'*' * int(s)}{'.' * (5 - int(s))}  {t}" for s, t in rated[:10]]
        return "Top of the Household Charts\n" + "\n".join(rows)

    def find_games(self, query: str, roms) -> list:
        """Library games a human probably means by `query`: exact key/title first, else every title containing it."""
        q = norm(query)
        if not q:
            return []
        exact = [r for r in roms if q in (norm(r.title), r.key.replace("-", ""))]
        if exact:
            return exact
        aliases = {r.key: [norm(a) for a in self.catalog.by_key.get(r.key, {}).get("aliases", [])] for r in roms}
        return [r for r in roms if q in norm(r.title) or any(q in a for a in aliases[r.key])]

    def rate(self, query: str, stars: int, roms, pet: str | None = None) -> str:
        hits = self.find_games(query, roms)
        if not hits:
            return self._line(pet or self._anyone(), "I couldn't find that game in your library.")
        if len(hits) > 1:
            names = ", ".join(r.title for r in hits[:5]) + ("..." if len(hits) > 5 else "")
            return self._line(pet or self._anyone(),
                              f"That could be several games ({names}). Be more specific and I'll write it down.")
        r = hits[0]
        self.state["ratings"][r.key] = max(1, min(5, int(stars)))
        return "\n".join(self.duo("ranked", game=r.title))

    def save_report(self, saves: dict | None, pet: str | None = None) -> str:
        """Honest save summary: what the save file itself says (its comment text), never invented progress."""
        pet = pet or self._anyone()
        if not saves:
            return self._line(pet, "No saves to look at. Export .gci files from your memory card and set saves_dir "
                                   "in config.json.")
        newest = sorted(saves.values(), key=lambda s: -s.get("modified", 0))[:5]
        rows = []
        for s in newest:
            g = self.catalog.by_code4.get(s.get("code4"))
            title = g["title"] if g else (s.get("comment") or [s.get("file", "?")])[0] or s.get("file", "?")
            bits = [f"{s.get('blocks', '?')} blocks", time.strftime("%Y-%m-%d", time.gmtime(s.get("modified", 0)))]
            if s.get("progress"):
                bits.append(str(s["progress"]))
            elif s.get("comment") and any(s["comment"]):
                bits.append('says: "' + " / ".join(c for c in s["comment"] if c) + '"')
            rows.append(f"  {title}: " + ", ".join(bits))
        return "Freshest saves:\n" + "\n".join(rows) + "\n" + self._line(pet, "I looked. I didn't change a thing.")

    def wrapped(self, roms, pet: str | None = None) -> str:
        """Season recap: what the rotation history and your ratings say. Facts only."""
        hist = [h for h in self.state.get("history") or [] if isinstance(h, dict) and isinstance(h.get("plan"), dict)]
        if not hist:
            return self._line(pet or self._anyone(), "No seasons yet. Plan a rotation and I'll start keeping notes.")
        counts: dict[str, int] = {}
        for h in hist:
            for keys in h["plan"].values():
                for k in keys if isinstance(keys, (list, tuple)) else []:
                    if isinstance(k, str):
                        counts[k] = counts.get(k, 0) + 1
        titles = {r.key: r.title for r in roms}
        name = lambda k: titles.get(k) or self._title(k)
        regulars = sorted(counts, key=lambda k: (-counts[k], name(k)))[:5]
        never = [r.title for r in roms if r.key not in counts]
        five = [name(k) for k, v in self.state["ratings"].items() if v == 5]
        out = [f"PAWTATION WRAPPED  -  {len(hist)} season(s), {len(counts)} different games rotated",
               "Most-rotated: " + ", ".join(f"{name(k)} (x{counts[k]})" for k in regulars)]
        if five:
            out.append("Five-star club: " + ", ".join(sorted(five)[:8]))
        if never:
            out.append(f"Still waiting for a turn: {len(never)} game(s), e.g. " + ", ".join(never[:4]))
        for p in cast.regulars():
            out.append(self._line(p, f"Affection {self._stats(p)['affection']}/20. Same time next season."))
        return "\n".join(out)

    def help(self) -> str:
        acts = ", ".join(self.activities())
        return ("Things you can say: joke, fortune, suggest, rank, rate <game> <1-5>, where is <game>, saves, wrapped, "
                f"study break, {acts}. Company: who's home, invite <name>, send <name> out, everyone, hang out. "
                f"Add a name ({cast.names(cast.regulars(), 'or')}) to pick who answers.")

    # ---- who is home, meetups, scenes
    def home_line(self) -> str:
        """A plain status line: who is home and which regulars are out."""
        home = self.home()
        out = [p for p in cast.regulars() if p not in home]
        return f"Home right now: {cast.names(home)}." + (f" Out: {cast.names(out)}." if out else "")

    def whos_home(self, pet: str | None = None) -> str:
        home = self.home()
        pet = pet if pet in home else self._anyone(home)
        others = [p for p in home if p != pet]
        out = [p for p in cast.regulars() if p not in home]
        labels = ["me"] + [self.name(p) for p in others]
        text = f"It's {', '.join(labels[:-1])} and {labels[-1]} right now." if others else "Just me right now."
        if out:
            text += f" {cast.names(out)} {'is' if len(out) == 1 else 'are'} out."
        return self._line(pet, text)

    def _absent(self, speaker: str, who: str) -> str:
        return self.say(speaker, "absent", name=self.name(who))

    def invite(self, who, minutes=None) -> list[str]:
        """Bring the named non-cameo characters home, alongside whoever is already there."""
        home = self.home()
        asked = cast.order(who)
        wanted = [p for p in asked if cast.role(p) != "cameo"]
        if not wanted:
            if asked:                                               # a cameo: walk-ons cannot be summoned
                return [self._line(self._anyone(home), f"{self.name(asked[0])} drops by when {self.name(asked[0])} "
                                                       "feels like it. No summoning the neighbours.")]
            return [self._line(self._anyone(home), f"Invite who? {cast.names(cast.regulars(), 'or')}.")]
        if all(p in home for p in wanted):
            return [self._line(wanted[0], "Already here.")]
        change = cast.gather(self.state, self.speakers() + wanted, minutes, self.now())
        return self.presence_lines(change) or [self.home_line()]

    def send_out(self, who) -> list[str]:
        """Send the named characters out. At least one main always stays home."""
        home = self.home()
        asked = cast.order(who)
        going = [p for p in asked if p in home]
        if not going:
            return [self._absent(self._anyone(home), asked[0])] if asked else [self.home_line()]
        staying = [p for p in home if p not in going and cast.role(p) != "cameo"]
        if not any(cast.role(p) == "main" for p in staying):
            keeper = next((p for p in going if cast.role(p) == "main"), going[0])
            return [self._line(keeper, "Somebody has to mind the GameCube. I'm staying put.")]
        change = cast.gather(self.state, staying, None, self.now())
        return self.presence_lines(change) or [self.home_line()]

    def everyone(self) -> list[str]:
        """Get every non-cameo character together."""
        change = cast.gather(self.state, cast.regulars(), None, self.now())
        return self.presence_lines(change) or [self._line(self._anyone(), "Everyone's already here.")]

    def _scene_lines(self, who, when: str, **context) -> list[str]:
        scene = cast.pick_scene(who, when, unlocked=self.unlocked(), rng=self.rng, context=context,
                                avoid=self._last_scene)
        if not scene:
            return []
        self._last_scene = scene["id"]
        return cast.play(scene, context)

    def scene(self, when: str | None = None, **context) -> list[str]:
        """Play a scene for whoever is home. `when` defaults to the time of day (night / morning) about half the
        time and "any" otherwise. With no scene for this group, everyone says an idle line instead."""
        if when is None:
            when = cast.time_when(self.now())
            if when != "any" and self.rng.random() < 0.5:
                when = "any"
        return self._scene_lines(self.home(), when, **context) or self.duo("idle")

    def event(self, when: str, **context) -> list[str]:
        """Lines for something that just happened: "rotated", "synced" (card=...), "due", "arrive", "leave".
        A scene written for that moment and the present group wins; otherwise each character who is home says
        a line from the matching bucket (rotated / synced / rotation_due / arrive / leave).
        Never raises: a missing line must not make a finished sync look like a failure."""
        try:
            lines = self._scene_lines(self.home(), when, **context)
            if lines:
                return lines
            bucket = EVENT_BUCKETS.get(when) if isinstance(when, str) else None
            return self.duo(bucket, **context) if bucket else []
        except Exception:
            return []

    def presence_lines(self, change) -> list[str]:
        """What to show for a result of cast.step() / cast.gather(): goodbyes from whoever left, then hellos from
        whoever arrived (a matching leave / arrive scene if there is one, else one line each). [] if nobody moved."""
        try:
            return self._presence_lines(change)
        except Exception:
            return []

    def _presence_lines(self, change) -> list[str]:
        if not isinstance(change, dict):
            return []
        who, arrived, left = (cast.order(change.get(k) or []) for k in ("who", "arrived", "left"))
        content = self._content()
        speaks = lambda p, bucket: cast.role(p) != "cameo" or _lines(content, bucket, p)
        out = []
        if left:
            before = cast.order([p for p in who if p not in arrived] + left)
            out += (self._scene_lines(before, "leave", movers=left)
                    or [self.say(p, "leave") for p in left if speaks(p, "leave")])
        if arrived:
            out += (self._scene_lines(who, "arrive", movers=arrived)
                    or [self.say(p, "arrive") for p in arrived if speaks(p, "arrive")])
        return out

    def afterdark_info(self) -> str:
        """Chat can explain After Dark; it can never unlock it."""
        if self.unlocked():
            return "After Dark is on. To turn it off again: python -m pawtation afterdark --lock"
        return ("After Dark is an opt-in 18+ tier, and it is locked. It cannot be unlocked from chat: run "
                "`python -m pawtation afterdark` (or use the app's After Dark setting) and confirm your date of "
                "birth once.")

    # ---- chat dispatcher
    def _mentioned(self, t: str, roms, loose: bool = False):
        """The library game named in a sentence, longest title first so 'Pikmin 2' beats 'Pikmin'."""
        nt = norm(t)
        for r in sorted(roms, key=lambda r: -len(norm(r.title))):
            n = norm(r.title)
            if len(n) > 5 and n in nt:
                return r
        if not loose or len(nt) < 4:                                # partial names only when the user asked about a game
            return None
        hits = self.find_games(re.sub(r"\b(where|is|are|the|on|which|card|what|about|tell|me)\b", " ", t), roms)
        return hits[0] if len(hits) == 1 else None

    def reply(self, text: str, roms=None, saves=None) -> str:
        roms = roms or []
        t = " ".join(str(text).lower().replace("’", "'").split())
        home = self.home()
        named = cast.find(t)                                        # everyone the message names, by any alias
        direct = cast.find(t, strict=True)                          # ...by id or display name only
        here = [p for p in named if p in home]
        asked = here[0] if here else None                           # the home character the user picked, if any
        pet = asked or self._anyone(home)
        ctx = {"roms": roms, "saves": saves, "pet": pet, "text": text, "home": home, "named": named}
        for rx, fn in CHAT_HOOKS:                                   # plugins get first refusal
            m = rx.search(t)
            if m:
                try:
                    out = fn(self, m, ctx)
                except Exception as e:                              # a broken plugin must not kill the chat
                    out = self._line(pet, f"A plugin tripped over its own tail ({type(e).__name__}: {e}).")
                if out:
                    return out
        m = re.match(r"(?:please )?rate\s+(.+?)\s+([1-5])(?:\s*(?:stars?|/5))?$", t)
        if m:
            whole = norm(m.group(1) + m.group(2))                   # "rate pikmin 2": a title ending in a digit, no stars yet
            titled = [r for r in roms if norm(r.title) == whole]
            if titled and not re.search(r"(stars?|/5)$", t):
                return self._line(pet, f"How many stars for {titled[0].title}? Say: rate {titled[0].title.lower()} 4")
            return self.rate(m.group(1), int(m.group(2)), roms, pet)
        if re.search(r"\b(help|commands|what can you do)\b", t):
            return self.help()
        if RX_AFTERDARK.search(t):
            return self.afterdark_info()
        if RX_WHO_HOME.search(t):
            return self.whos_home(asked)
        if RX_EVERYONE.search(t):
            return "\n".join(self.everyone())
        if RX_INVITE.search(t) and (named or re.search(r"\binvite\b", t)):
            return "\n".join(self.invite(named))
        if named and RX_SEND_OUT.search(t):
            return "\n".join(self.send_out(named))
        away = [p for p in direct if p not in home]
        if direct and RX_WHERE_WHO.search(t) and not self._mentioned(t, roms):
            return self._absent(pet, away[0]) if away else self._line(direct[0], "Right here.")
        if away and not here:                                       # the message is for someone who is out
            return self._absent(pet, away[0])
        if RX_SCENE.search(t):
            return "\n".join(self.scene())
        if re.search(r"\b(jokes?|puns?|make me laugh)\b|\bfunny\b", t):
            return self.joke(asked)
        if re.search(r"\b(fortune|horoscope|cookie)\b", t):
            return self.fortune(asked)
        if re.search(r"\b(study|studying|exam|tired|stressed|break|rotation is hard|rounds)\b", t):
            return self.study_break(asked)
        if re.search(r"\b(wrapped|recap|season stats)\b", t):
            return self.wrapped(roms, pet)
        if re.search(r"\b(rank|ranking|rankings|charts|top (games|ten|10|5|five))\b", t):
            return self.ranking(roms, pet)
        if re.search(r"\b(suggest|recommend|bored|pick (one|a game|something))\b|what should i play", t):
            return self.suggest(roms)
        if re.search(r"\b(saves?|progress|memory card)\b", t):
            return self.save_report(saves, pet)
        m = re.search(r"\b(?:where(?:'s| is)|which card (?:has|is))\s+(.+?)\??$", t)
        if m:
            r = self._mentioned(m.group(1), roms, loose=True)
            if not r:
                return self._line(pet, "I looked under every cushion. That one's not in the library.")
            c = self.where(r.key)
            return self._line(pet, f"{r.title} is on card {c}." if c else f"{r.title} is resting this season. Not on any card.")
        r = self._mentioned(t, roms)                                # a game by name beats small talk
        if r:
            return self.game_quip(pet, r.key) or self._line(pet, f"Ooh, {r.title}.")
        acts = [n for n in self.activities() if re.search(rf"\b{re.escape(n)}(s|ies|ing)?\b", t)]
        if acts:
            return self.activity(pet, acts[-1])                     # "play fetch" -> fetch (later = more specific)
        if re.search(r"\b(hello|hi|hey|heya|howdy|sup|yo|good (morning|evening|night))\b", t):
            return self.say(pet, "greeting")
        return self.say(pet, "idle")
