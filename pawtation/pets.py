"""Chat pets: Mochi (cat) and Biscuit (dog). Rule-based, offline, deterministic-ish. No LLM needed.

Extend by editing data/pets.json (content), by adding an intent to `PetBrain.INTENTS` (behavior), or from a
plugin with `api.chat(pattern, fn)` (see pawtation/plugins.py). Intents are tried top to bottom; first hit wins.
"""
from __future__ import annotations

import random
import re
import time

from .core import DATA_DIR, load_json, norm

PETS = load_json(DATA_DIR / "pets.json", {})
CHARS = PETS.get("characters", {})
NAMES = ("mochi", "biscuit")
CHAT_HOOKS: list = []      # [(compiled regex, fn(brain, match, ctx) -> str | None)] added by plugins


def _char(pet: str) -> dict:
    c = CHARS.get(pet) if isinstance(CHARS, dict) else None
    return c if isinstance(c, dict) else {}


def other(pet: str) -> str:
    return "biscuit" if pet == "mochi" else "mochi"


def _fill(line: str, **fmt) -> str:
    """Format a content line; an unknown {placeholder} or stray brace in pets.json must never crash the app."""
    try:
        return str(line).format(**fmt)
    except Exception:
        return str(line)


def _strs(x) -> list:
    return [s for s in x if isinstance(s, str) and s] if isinstance(x, list) else []


def _bucket(name: str) -> dict:
    b = PETS.get(name)
    return b if isinstance(b, dict) else {}


def _pairs(name: str) -> list:
    """[[who, text], ...] buckets, with malformed rows dropped."""
    b = PETS.get(name)
    return [(r[0], r[1]) for r in b if isinstance(r, (list, tuple)) and len(r) == 2
            and all(isinstance(x, str) for x in r)] if isinstance(b, list) else []


class PetBrain:
    def __init__(self, state: dict, catalog, rng: random.Random | None = None):
        self.state, self.catalog = state, catalog
        self.rng = rng or random.Random()
        state.setdefault("ratings", {}); state.setdefault("last_on_card", {}); state.setdefault("history", [])
        pets = state.setdefault("pets", {})
        for p in NAMES:
            pets.setdefault(p, {"affection": 5, "energy": 5})

    # ---- helpers
    def say(self, pet: str, bucket: str, **fmt) -> str:
        lines = _strs(_bucket(bucket).get(pet)) or ["..."]
        return self._line(pet, _fill(self.rng.choice(lines), **fmt))

    def _line(self, pet, text):
        return f"{_char(pet).get('name') or pet.title()}: {text}"

    def art(self, pet: str, mood: str = "art") -> str:
        return "\n".join(_strs(_char(pet).get(mood)) or _strs(_char(pet).get("art")))

    def duo(self, bucket: str, **fmt) -> list[str]:
        return [self.say("mochi", bucket, **fmt), self.say("biscuit", bucket, **fmt)]

    def _pair(self, bucket: str, fallback: str) -> str:
        """Buckets shaped [[who, text], ...] (jokes, fortunes)."""
        items = _pairs(bucket)
        if not items:
            return fallback
        who, text = self.rng.choice(items)
        return f"{who}: {text}"

    def _title(self, key: str) -> str:
        return self.catalog.by_key.get(key, {}).get("title", key)

    # ---- features
    def joke(self) -> str:
        return self._pair("jokes", "Mochi: I had a joke. I napped on it.")

    def fortune(self) -> str:
        return self._pair("fortunes", "Biscuit: Today is a GOOD day!! I checked!!")

    def study_break(self) -> str:
        return self.say(self.rng.choice(NAMES), "study_break")

    def due_nag(self) -> list[str]:
        return self.duo("rotation_due")

    def collection(self, roms) -> list[str]:
        """Both pets comment on the size of the library (pets.json -> state_of_collection: empty/few/many)."""
        bucket = "empty" if not roms else "few" if len(roms) < 15 else "many"
        lines = _strs(_bucket("state_of_collection").get(bucket)) or ["...", "..."]
        return [self._line(p, lines[i % len(lines)]) for i, p in enumerate(NAMES)]

    def activity(self, pet: str, name: str) -> str:
        act = _bucket("activities").get(name)
        if not isinstance(act, dict):
            return self._line(pet, "I don't know that trick yet.")
        s = self.state["pets"].setdefault(pet, {"affection": 5, "energy": 5})
        if act.get("needs") == "energy" and s["energy"] < 2:
            return self._line(pet, "Too sleepy for that. Try a nap or a treat?")
        num = lambda k: act.get(k) if isinstance(act.get(k), (int, float)) else 0
        s["affection"] = max(0, min(20, s["affection"] + num("affection")))
        s["energy"] = max(0, min(10, s["energy"] + num("energy")))
        return self._line(pet, self.rng.choice(_strs(act.get(pet)) or ["..."]))

    def mood(self, pet: str) -> str:
        s = self.state["pets"].get(pet, {})
        return "sleep" if s.get("energy", 5) < 2 else "happy" if s.get("affection", 5) >= 12 else "art"

    def game_quip(self, pet: str, key: str) -> str | None:
        g = self.catalog.by_key.get(key)
        per_game = _bucket("game_quips").get(key)
        q = per_game.get(pet) if isinstance(per_game, dict) else None
        if isinstance(q, str) and q:
            return self._line(pet, _fill(q, game=g["title"] if g else key))
        for tag in (g or {}).get("tags", []):
            per_tag = _bucket("tag_quips").get(tag)
            t = per_tag.get(pet) if isinstance(per_tag, dict) else None
            if isinstance(t, str) and t:
                return self._line(pet, _fill(t, game=g["title"]))
        return None

    def card_quips(self, keys, limit: int = 40) -> list[str]:
        """Plain one-line quips about the games on a card, for /pawtation/quips.txt (a future on-console companion).
        Never raises: a quip problem must not get in the way of a sync."""
        try:
            return self._card_quips(keys, limit)
        except Exception:
            return []

    def _card_quips(self, keys, limit):
        out = []
        for key in keys:
            for pet in NAMES:
                q = self.game_quip(pet, key)
                if q:
                    out.append(q)
        for bucket in ("jokes", "fortunes"):
            items = _pairs(bucket)
            self.rng.shuffle(items)
            out += [f"{who}: {text}" for who, text in items[:10]]
        seen, uniq = set(), []
        for line in out:
            line = " ".join(line.split())
            if line not in seen:
                seen.add(line); uniq.append(line)
        return uniq[:limit]

    def suggest(self, roms, now=None) -> str:
        """Pick a game: rating-weighted, slightly favors stale/unplayed. Both pets weigh in."""
        if not roms:
            return "\n".join(self.collection(roms))
        w = []
        for r in roms:
            rating = self.state["ratings"].get(r.key, 3)
            last = self.state["last_on_card"].get(r.key, 0)
            w.append(max(0.5, rating + (1.5 if not last else 0)))
        pick = self.rng.choices(roms, weights=w, k=1)[0]
        a = self.game_quip("mochi", pick.key) or f"Mochi: I'd nap through {pick.title}. Then play it."
        b = self.game_quip("biscuit", pick.key) or f"Biscuit: {pick.title}!! I pick {pick.title}!!"
        where = self.where(pick.key)
        return "\n".join([f"Tonight's pick: {pick.title}" + (f" (it's on card {where})" if where else " (not on a card this season)"), a, b])

    def where(self, key: str) -> str | None:
        hist = self.state.get("history") or []
        if hist:
            for cid, keys in hist[-1]["plan"].items():
                if key in keys:
                    return cid
        return None

    def ranking(self, roms) -> str:
        rated = [(self.state["ratings"][r.key], r.title) for r in roms if self.state["ratings"].get(r.key)]
        if not rated:
            return "Mochi: Nothing rated yet. Tell me: 'rate paper mario 5'."
        rated.sort(key=lambda t: (-t[0], t[1].lower()))
        rows = [f"{'*' * s}{'.' * (5 - s)}  {t}" for s, t in rated[:10]]
        return "Top of the Cat/Dog Charts\n" + "\n".join(rows)

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

    def rate(self, query: str, stars: int, roms) -> str:
        hits = self.find_games(query, roms)
        if not hits:
            return "Mochi: I couldn't find that game in your library."
        if len(hits) > 1:
            names = ", ".join(r.title for r in hits[:5]) + ("..." if len(hits) > 5 else "")
            return f"Mochi: That could be several games ({names}). Be more specific and I'll write it down."
        r = hits[0]
        self.state["ratings"][r.key] = max(1, min(5, int(stars)))
        return "\n".join(self.duo("ranked", game=r.title))

    def save_report(self, saves: dict | None) -> str:
        """Honest save summary: what the save file itself says (its comment text), never invented progress."""
        if not saves:
            return ("Mochi: No saves to sniff. Export .gci files from your memory card and set saves_dir in config.json.")
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
        pet = self.rng.choice(NAMES)
        tail = "I peeked. I didn't scratch anything." if pet == "mochi" else "I sniffed ALL of them!! Didn't chew any!!"
        return "Freshest saves:\n" + "\n".join(rows) + "\n" + self._line(pet, tail)

    def wrapped(self, roms) -> str:
        """Season recap ("Mochi's Wrapped"): what the rotation history and your ratings say. Facts only."""
        hist = self.state.get("history") or []
        if not hist:
            return "Mochi: No seasons yet. Plan a rotation and I'll start keeping notes."
        counts: dict[str, int] = {}
        for h in hist:
            for keys in h.get("plan", {}).values():
                for k in keys:
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
        a, b = self.state["pets"]["mochi"], self.state["pets"]["biscuit"]
        out.append(f"Mochi: Affection {a['affection']}/20. I have decided to allow this to continue.")
        out.append(f"Biscuit: Affection {b['affection']}/20!! BEST SEASON EVER!! (I say that every season!!)")
        return "\n".join(out)

    def help(self) -> str:
        acts = ", ".join(_bucket("activities"))
        return ("Things you can say: joke, fortune, suggest, rank, rate <game> <1-5>, where is <game>, saves, wrapped, "
                f"study break, {acts}. Add 'mochi' or 'biscuit' to pick who answers.")

    # ---- chat dispatcher
    def _who(self, t: str) -> str:
        if re.search(r"\b(biscuit|dog|doggo|puppy|pup|bork|woof)\b", t):
            return "biscuit"
        if re.search(r"\b(mochi|cat|kitty|kitten|meow|mew|purr)\b", t):
            return "mochi"
        return self.rng.choice(NAMES)

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
        t = " ".join(text.lower().split())
        pet = self._who(t)
        ctx = {"roms": roms, "saves": saves, "pet": pet, "text": text}
        for rx, fn in CHAT_HOOKS:                                   # plugins get first refusal
            m = rx.search(t)
            if m:
                try:
                    out = fn(self, m, ctx)
                except Exception as e:                              # a broken plugin must not kill the chat
                    out = f"Mochi: A plugin hissed at me ({type(e).__name__}: {e})."
                if out:
                    return out
        m = re.match(r"(?:please )?rate\s+(.+?)\s+([1-5])(?:\s*(?:stars?|/5))?$", t)
        if m:
            whole = norm(m.group(1) + m.group(2))                   # "rate pikmin 2": a title ending in a digit, no stars yet
            named = [r for r in roms if norm(r.title) == whole]
            if named and not re.search(r"(stars?|/5)$", t):
                return self._line("mochi", f"How many stars for {named[0].title}? Say: rate {named[0].title.lower()} 4")
            return self.rate(m.group(1), int(m.group(2)), roms)
        if re.search(r"\b(help|commands|what can you do)\b", t):
            return self.help()
        if re.search(r"\b(jokes?|puns?|make me laugh)\b|\bfunny\b", t):
            return self.joke()
        if re.search(r"\b(fortune|horoscope|cookie)\b", t):
            return self.fortune()
        if re.search(r"\b(study|studying|exam|tired|stressed|break|rotation is hard|rounds)\b", t):
            return self.study_break()
        if re.search(r"\b(wrapped|recap|season stats)\b", t):
            return self.wrapped(roms)
        if re.search(r"\b(rank|ranking|rankings|charts|top (games|ten|10|5|five))\b", t):
            return self.ranking(roms)
        if re.search(r"\b(suggest|recommend|bored|pick (one|a game|something))\b|what should i play", t):
            return self.suggest(roms)
        if re.search(r"\b(saves?|progress|memory card)\b", t):
            return self.save_report(saves)
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
        acts = [n for n in _bucket("activities") if re.search(rf"\b{re.escape(n)}(s|ies|ing)?\b", t)]
        if acts:
            return self.activity(pet, acts[-1])                     # "play fetch" -> fetch (later = more specific)
        if re.search(r"\b(hello|hi|hey|heya|howdy|sup|yo|good (morning|evening|night))\b", t):
            return self.say(pet, "greeting")
        return self.say(pet, "idle")
