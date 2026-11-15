"""The shipped lines: data/pets.json and data/afterdark/pets.json (schema: docs/SPEC_V2.md section 2 and 8, voices:
docs/CHARACTERS.md). Reads the real files; never touches a config or state file."""
import json
import random
import re
import string
import unittest
from pathlib import Path

from pawtation import cast, pets
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent
DATA = json.loads((ROOT / "data" / "pets.json").read_text(encoding="utf-8"))
AFTERDARK = json.loads((ROOT / "data" / "afterdark" / "pets.json").read_text(encoding="utf-8"))
CAST = json.loads((ROOT / "data" / "cast.json").read_text(encoding="utf-8"))["characters"]
CAMEOS = [i for i, c in CAST.items() if c["role"] == "cameo"]
NEW_CAMEOS = ["pickle", "vesper", "tuft", "hazel", "sprout", "stilts", "flurry", "refills"]
V1 = ["mochi", "biscuit"]

BUCKETS = ["greeting", "idle", "rotation_due", "rotated", "synced", "ranked", "study_break", "arrive", "leave", "absent"]
CAMEO_BUCKETS = ["greeting", "idle", "arrive", "leave"]
# Allowed placeholders, derived from the real call sites:
#   greeting / idle / rotated / study_break / arrive / leave: say() / duo() / presence_lines() pass nothing
#   rotation_due: cli passes nothing (gui passes days=0, which a line may ignore) -> none
#   synced: event("synced", card=cid) in cli.py, say(.., "synced", card=cid) in gui.py -> {card}
#   ranked: duo("ranked", game=title) -> {game}
#   absent: say(speaker, "absent", name=<display name of whoever is out>) -> {name}
#   game_quips / tag_quips: PetBrain._quip formats with game=title -> {game}
#   jokes, fortunes, activities, state_of_collection: never formatted -> none
ALLOWED = {"greeting": set(), "idle": set(), "rotation_due": set(), "rotated": set(), "study_break": set(),
           "arrive": set(), "leave": set(), "synced": {"card"}, "ranked": {"game"}, "absent": {"name"},
           "game_quips": {"game"}, "tag_quips": {"game"}, "jokes": set(), "fortunes": set(), "activities": set()}
DUMMY = {"card": "SD1", "game": "Test Game", "name": "Duskie"}
TAGS = ("furry furry-adjacent cats-and-dogs cat-adjacent cozy cute racing party horror spooky rpg sports fighting "
        "platformer adventure action scifi co-op weird arcade fox dragon bongos top5 link-guest").split()
TOP5 = ["paper-mario-ttyd", "animal-crossing", "soulcalibur-ii", "mario-kart-double-dash", "chibi-robo"]
ACTIVITY_NUMBERS = {"pet": ("none", 1, 0), "treat": ("none", 2, 1), "play": ("energy", 1, -2), "nap": ("none", 1, 3),
                    "fetch": ("energy", 1, -2), "laser": ("energy", 1, -3), "groom": ("none", 2, 1)}


def placeholders(line):
    return {f for _, f, _, _ in string.Formatter().parse(line) if f is not None}


def strings(o, skip_art=True):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k.startswith("_") or (skip_art and k.startswith("art")):
                continue
            yield from strings(v, skip_art)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v, skip_art)


def bucket_lines(doc, bucket):
    """Every format-able line in a bucket of a pets.json-shaped doc."""
    b = doc.get(bucket)
    if bucket in ("jokes", "fortunes"):
        return [t for _, t in b or []]
    if bucket == "activities":
        return [t for a in (b or {}).values() for k, v in a.items() if isinstance(v, list) for t in v]
    if bucket in ("game_quips", "tag_quips"):
        return [t for per in (b or {}).values() for v in per.values() for t in ([v] if isinstance(v, str) else v)]
    return [t for v in (b or {}).values() for t in v]


def lines_by(doc, cid):
    """Everything one character says in a pets.json-shaped doc (buckets, jokes, activities, quips)."""
    out = []
    for b in BUCKETS:
        out += doc.get(b, {}).get(cid, [])
    out += [t for who, t in doc.get("jokes", []) + doc.get("fortunes", []) if cast.resolve(who) == cid]
    for a in doc.get("activities", {}).values():
        out += a.get(cid, [])
    for b in ("game_quips", "tag_quips"):
        for per in doc.get(b, {}).values():
            v = per.get(cid)
            out += [v] if isinstance(v, str) else v or []
    return out


class Fresh(unittest.TestCase):
    def setUp(self):
        cast.reload()
        self.addCleanup(cast.reload)


class TestPetsContent(Fresh):
    def test_main_buckets_have_real_volume(self):
        for b in BUCKETS:
            for cid, least in (("nova", 10), ("iggy", 10), ("duskie", 6)):
                self.assertGreaterEqual(len(DATA[b][cid]), least, (b, cid))
                self.assertEqual(len(set(DATA[b][cid])), len(DATA[b][cid]), (b, cid))     # no duplicates
        for b in ("greeting", "idle", "rotation_due", "rotated", "synced", "ranked", "study_break"):
            for cid in V1:
                self.assertTrue(DATA[b][cid], (b, cid))                                       # version-1 lines kept

    def test_cameo_lines(self):
        self.assertEqual(sorted(NEW_CAMEOS + V1), sorted(CAMEOS))
        for cid in CAMEOS:
            for b in CAMEO_BUCKETS:
                self.assertGreaterEqual(len(DATA[b].get(cid, [])), 4 if cid in NEW_CAMEOS else 3, (b, cid))
        tellers = [cast.resolve(who) for who, _ in DATA["jokes"]]
        for cid in NEW_CAMEOS:
            self.assertGreaterEqual(tellers.count(cid), 2, cid)
        for line in lines_by(DATA, "pickle"):
            self.assertNotIn("!", line)                                                       # flat work dread
        for line in lines_by(DATA, "refills"):
            self.assertRegex(line, r"^[A-Z][a-z]+\.$")                                        # one word, full stop

    def test_line_length_and_ascii(self):
        for doc in (DATA, AFTERDARK):
            for s in strings(doc):
                self.assertLessEqual(len(s), 140, s)
                self.assertTrue(s.isascii(), s)

    def test_placeholders_match_the_call_sites(self):
        for doc in (DATA, AFTERDARK):
            for bucket, allowed in ALLOWED.items():
                for line in bucket_lines(doc, bucket):
                    self.assertLessEqual(placeholders(line), allowed, (bucket, line))
                    line.format(**DUMMY)
        for line in DATA["absent"]["nova"] + DATA["absent"]["iggy"] + DATA["absent"]["duskie"]:
            self.assertIn("{name}", line)
        for line in DATA["synced"]["nova"] + DATA["synced"]["iggy"] + DATA["synced"]["duskie"]:
            self.assertIn("{card}", line)

    def test_jokes_and_fortunes(self):
        speakers = {c["name"] for c in cast.characters().values()}
        count = lambda rows, name: sum(1 for who, _ in rows if who == name)
        for who, _ in DATA["jokes"] + DATA["fortunes"]:
            self.assertIn(who, speakers)
        for name, jokes, fortunes in (("Nova", 30, 12), ("Iggy", 25, 12), ("Duskie", 12, 6)):
            self.assertGreaterEqual(count(DATA["jokes"], name), jokes, name)
            self.assertGreaterEqual(count(DATA["fortunes"], name), fortunes, name)
        for name in ("Mochi", "Biscuit"):
            self.assertGreaterEqual(count(DATA["jokes"], name), 20)                            # version-1 jokes kept
        texts = [t for _, t in DATA["jokes"]]
        self.assertEqual(len(texts), len(set(texts)))

    def test_activities_through_petbrain(self):
        acts = DATA["activities"]
        for name, (needs, aff, energy) in ACTIVITY_NUMBERS.items():
            self.assertEqual((acts[name]["needs"], acts[name]["affection"], acts[name]["energy"]), (needs, aff, energy), name)
            for cid in V1:
                self.assertTrue(acts[name][cid], (name, cid))
        self.assertIn("cook", acts); self.assertIn("tea", acts)
        for name, a in acts.items():
            for k in ("verb", "needs", "affection", "energy"):
                self.assertIn(k, a, name)
            for cid in cast.regulars():
                self.assertGreaterEqual(len(a.get(cid, [])), 4, (name, cid))
                state = {"pets": {cid: {"affection": 5, "energy": 10}}, "ratings": {}, "last_on_card": {}}
                brain = pets.PetBrain(state, Catalog(), random.Random(7))
                said = brain.activity(cid, name)
                prefix = cast.name(cid) + ": "
                self.assertTrue(said.startswith(prefix), (name, cid, said))
                self.assertIn(said[len(prefix):], a[cid])

    def test_game_and_tag_quips(self):
        keys = {g["key"] for g in Catalog().games}
        for k in TOP5:
            for cid in ("nova", "iggy", "duskie", "mochi", "biscuit"):
                self.assertTrue(DATA["game_quips"][k].get(cid), (k, cid))
        both = [k for k, v in DATA["game_quips"].items() if v.get("nova") and v.get("iggy")]
        self.assertGreaterEqual(len(both), 25)
        for k, v in DATA["game_quips"].items():
            self.assertIn(k, keys)
            self.assertIn("mochi", v); self.assertIn("biscuit", v)
        for t in TAGS:
            for cid in ("nova", "iggy", "mochi", "biscuit"):
                self.assertTrue(DATA["tag_quips"][t].get(cid), (t, cid))

    def test_ascii_art(self):
        for cid, c in DATA["characters"].items():
            moods = [c[m] for m in ("art", "art_happy", "art_sleep")]
            for art in moods:
                self.assertEqual(len(art), len(moods[0]), cid)
                self.assertLessEqual(len(art), 6, cid)
                for row in art:
                    self.assertTrue(row.isascii() and len(row) <= 22, (cid, row))
        art = {cid: "\n".join(DATA["characters"][cid]["art"]) for cid in ("nova", "iggy", "duskie")}
        self.assertIn(".-.", art["nova"])                                                     # tall rounded ears
        self.assertIn("(o-o)", art["iggy"])                                                   # round glasses
        self.assertEqual(len(set(art.values())), 3)

    def test_house_voice_rules(self):
        everything = "\n".join(strings(DATA))
        self.assertLessEqual(everything.count(":3"), 5)                                      # not the other app's Nova
        self.assertLessEqual(everything.count("toxoplasmosis"), 2)

    def test_afterdark_lines(self):
        for b in ("idle", "greeting", "arrive"):
            for cid in ("nova", "iggy", "duskie"):
                self.assertGreaterEqual(len(AFTERDARK[b][cid]), 6, (b, cid))
        self.assertGreaterEqual(len(AFTERDARK["jokes"]), 10)
        adults = {"nova", "iggy", "duskie"}
        for key, b in AFTERDARK.items():
            if isinstance(b, dict):
                self.assertLessEqual(set(b), adults, key)                                     # the three adults only
        for who, _ in AFTERDARK["jokes"]:
            self.assertIn(cast.resolve(who), adults)


if __name__ == "__main__":
    unittest.main()
