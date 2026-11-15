import json
import random
import string
import unittest
from pathlib import Path

from pawtation import cast, pets
from pawtation.core import Catalog

DATA = json.loads((Path(__file__).resolve().parent.parent / "data" / "pets.json").read_text(encoding="utf-8"))

PER_PET = ["greeting", "rotation_due", "rotated", "synced", "ranked", "idle", "study_break"]
# Allowed placeholders per bucket, derived from the call sites (pets.py, cli.py, gui.py):
#   greeting/rotated/idle/rotation_due/study_break: say()/duo() called with no kwargs -> none
#   synced: say(..., card=cid) in gui.py -> {card}
#   ranked: duo("ranked", game=title) / say("mochi","ranked",game=...) -> {game}
#   tag_quips: formatted with game=title in PetBrain.game_quip -> {game}
#   game_quips, activities, jokes, fortunes: never formatted -> none
ALLOWED = {"greeting": set(), "rotation_due": set(), "rotated": set(), "idle": set(), "study_break": set(),
           "synced": {"card"}, "ranked": {"game"}, "tag_quips": {"game"},
           "game_quips": set(), "activities": set(), "jokes": set(), "fortunes": set()}
DUMMY = {"card": "SD1", "game": "Test Game", "days": 3, "pet": "Mochi", "other": "Biscuit"}
TAGS = ("furry furry-adjacent cats-and-dogs cat-adjacent cozy cute racing party horror spooky rpg sports fighting "
        "platformer adventure action scifi co-op weird arcade fox dragon bongos top5 link-guest").split()
TOP5 = ["paper-mario-ttyd", "animal-crossing", "soulcalibur-ii", "mario-kart-double-dash", "chibi-robo"]


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if k.startswith("art"):
                continue
            yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def lines_of(bucket):
    """Yield every format-able line in a bucket."""
    b = DATA[bucket]
    if bucket in ("jokes", "fortunes"):
        for who, text in b:
            yield text
    elif bucket == "activities":
        for a in b.values():
            for pet in ("mochi", "biscuit"):
                yield from a[pet]
    elif bucket in ("game_quips", "tag_quips"):
        for v in b.values():
            yield v["mochi"]
            yield v["biscuit"]
    else:
        for pet in ("mochi", "biscuit"):
            yield from b[pet]


class TestPetsContent(unittest.TestCase):
    def test_buckets(self):
        for b in PER_PET:
            for pet in ("mochi", "biscuit"):
                self.assertTrue(DATA[b][pet], (b, pet))
        for b in ("jokes", "fortunes", "activities", "game_quips", "tag_quips"):
            self.assertTrue(DATA[b], b)

    def test_line_length(self):
        for s in strings({k: v for k, v in DATA.items() if k not in ("characters", "_comment")}):
            self.assertLessEqual(len(s), 140, s)

    def test_placeholders(self):
        for bucket, allowed in ALLOWED.items():
            for line in lines_of(bucket):
                names = {f for _, f, _, _ in string.Formatter().parse(line) if f is not None}
                self.assertLessEqual(names, allowed, (bucket, line))
                line.format(**DUMMY)

    def test_fortunes_and_jokes(self):
        self.assertGreaterEqual(len(DATA["jokes"]), 48)
        self.assertGreaterEqual(len(DATA["fortunes"]), 20)
        speakers = {c["name"] for c in cast.characters().values()}          # display names from data/cast.json
        for who, _ in DATA["jokes"] + DATA["fortunes"]:
            self.assertIn(who, speakers)
        for pet in ("mochi", "biscuit"):
            self.assertGreaterEqual(len(DATA["study_break"][pet]), 6)

    def test_activities(self):
        brain = pets.PetBrain({"pets": {}, "ratings": {}, "last_on_card": {}}, Catalog(), random.Random(1))
        for name in ("fetch", "laser", "groom", "pet", "treat", "play", "nap"):
            self.assertIn(name, DATA["activities"])
        for name, a in DATA["activities"].items():
            for k in ("verb", "needs", "affection", "energy"):
                self.assertIn(k, a, name)
            for pet, prefix in (("mochi", "Mochi:"), ("biscuit", "Biscuit:")):
                self.assertTrue(a[pet], (name, pet))
                brain.state["pets"][pet] = {"affection": 5, "energy": 10}
                self.assertTrue(brain.activity(pet, name).startswith(prefix), (name, pet))

    def test_quips(self):
        keys = {g["key"] for g in Catalog().games}
        for k in TOP5:
            for pet in ("mochi", "biscuit"):
                self.assertTrue(DATA["game_quips"][k][pet])
        for k, v in DATA["game_quips"].items():
            self.assertIn(k, keys)
            self.assertIn("mochi", v)
            self.assertIn("biscuit", v)
        for t in TAGS:
            for pet in ("mochi", "biscuit"):
                self.assertTrue(DATA["tag_quips"][t][pet], (t, pet))

    def test_art_moods(self):
        for pet, c in DATA["characters"].items():
            for mood in ("art_happy", "art_sleep"):
                self.assertEqual(len(c[mood]), len(c["art"]), (pet, mood))
                self.assertTrue(all(len(x) <= 20 and x.isascii() for x in c[mood]))


if __name__ == "__main__":
    unittest.main()
