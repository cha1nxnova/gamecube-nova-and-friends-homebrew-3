"""The shipped scenes: data/scenes.json (all ages) and data/afterdark/scenes.json (opt-in 18+ tier), plus content-wide
checks over every shipped line. Schema: docs/SPEC_V2.md sections 2, 4 and 8; voices: docs/CHARACTERS.md.
Reads the real files; never touches a config or state file."""
import itertools
import json
import random
import re
import string
import unittest
from collections import Counter
from pathlib import Path

from pawtation import cast
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SCENES = json.loads((DATA / "scenes.json").read_text(encoding="utf-8"))["scenes"]
AD_SCENES = json.loads((DATA / "afterdark" / "scenes.json").read_text(encoding="utf-8"))["scenes"]
PETS = json.loads((DATA / "pets.json").read_text(encoding="utf-8"))
AD_PETS = json.loads((DATA / "afterdark" / "pets.json").read_text(encoding="utf-8"))
CAST = json.loads((DATA / "cast.json").read_text(encoding="utf-8"))["characters"]
CAMEOS = {i for i, c in CAST.items() if c["role"] == "cameo"}
NEW_CAMEOS = ["pickle", "vesper", "tuft", "hazel", "sprout", "stilts", "flurry", "refills"]
REGULARS = ["nova", "iggy", "duskie"]
GROUPS = ["+".join(sorted(c)) for n in (1, 2, 3) for c in itertools.combinations(REGULARS, n)]
MINIMUMS = {"iggy+nova": 45, "duskie+iggy+nova": 24, "duskie+nova": 16, "duskie+iggy": 16, "nova": 10, "iggy": 10,
            "duskie": 6}
PLAIN_WHENS = {"any", "arrive", "leave", "rotated", "synced", "due", "night", "morning"}
TOP5 = ["paper-mario-ttyd", "animal-crossing", "soulcalibur-ii", "mario-kart-double-dash", "chibi-robo"]
SPATCHCOCK = "No, I'm not going to 'spatchcock' you, so stop asking."
ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# Pet names aimed at the player (docs/CHARACTERS.md "Standing rules"). Kept deliberately simple: none of these words
# appears anywhere in shipped content, so no sentence-level judgement is needed. Character-to-character teasing uses
# other words ("pup", "menace"); if a future line genuinely needs one of these between characters, rephrase it.
PET_NAMES = re.compile(r"\b(sweetie|sweetheart|honey|darling|babe|baby|cutie|sugar|good (?:boy|girl)|dearest|my dear)\b",
                       re.I)
# A cheap tripwire for explicit language, applied to ALL tiers (After Dark ships innuendo only; SPEC section 4 and 8).
# Exceptions, by exact text: a character talking about himself, not to the player (Biscuit's version-1 lines).
PET_NAME_OK = {"Do you think the GameCube has a good boy mode? It does now: me.", "I'm a fluffy cloud!! A good boy cloud!!"}
EXPLICIT = re.compile(r"\b(sex\w*|naked|nude\w*|porn\w*|orgasm\w*|genital\w*|penis|vagina\w*|breasts?|nipples?|erotic\w*|"
                      r"horny|aroused|arousal|fuck\w*|cum|thrust\w*|moan\w*|undress\w*|strip(?:s|ped|ping)?|lingerie|"
                      r"crotch|groin|bulge|kink\w*|fetish\w*)\b", re.I)


def strings(o):
    if isinstance(o, str):
        yield o
    elif isinstance(o, dict):
        for k, v in o.items():
            if not k.startswith("_") and not k.startswith("art"):
                yield from strings(v)
    elif isinstance(o, list):
        for v in o:
            yield from strings(v)


def all_text():
    """Every shipped line, all tiers."""
    return (list(strings(PETS)) + list(strings(AD_PETS)) + [t for s in SCENES + AD_SCENES for _, t in s["lines"]])


def placeholders(line):
    return {f for _, f, _, _ in string.Formatter().parse(line) if f is not None}


class Fresh(unittest.TestCase):
    def setUp(self):
        cast.reload()
        self.addCleanup(cast.reload)
        self.cat = Catalog()
        self.tags = {t for g in self.cat.games for t in g.get("tags", [])}


class Schema(Fresh):
    def test_every_scene(self):
        ids = Counter(s["id"] for s in SCENES + AD_SCENES)
        self.assertEqual([i for i, n in ids.items() if n > 1], [])
        for s in SCENES + AD_SCENES:
            sid = s["id"]
            self.assertRegex(sid, ID)
            self.assertLessEqual(set(s), {"id", "who", "when", "rating", "weight", "lines", "about"}, sid)
            self.assertEqual(s["who"], sorted(set(s["who"])), sid)
            self.assertTrue(s["who"] and set(s["who"]) <= set(CAST), sid)
            self.assertTrue(set(s["who"]) - CAMEOS, sid)                                     # a cameo is never alone
            self.assertIn(s["rating"], ("all", "afterdark"), sid)
            self.assertTrue(isinstance(s.get("weight", 1), (int, float)) and s.get("weight", 1) > 0, sid)
            self.assertLessEqual(set(s.get("about", [])), set(s["who"]), sid)
            when = s["when"]
            if when.startswith("game:"):
                self.assertIn(when[5:], self.cat.by_key, sid)
            elif when.startswith("tag:"):
                self.assertIn(when[4:], self.tags, sid)
            else:
                self.assertIn(when, PLAIN_WHENS, sid)
            allowed = {"card"} if when == "synced" else {"game"} if when.startswith(("game:", "tag:")) else set()
            self.assertTrue(2 <= len(s["lines"]) <= 6, sid)
            for who, text in s["lines"]:
                self.assertTrue(who == "*" or who in s["who"], (sid, who))
                self.assertTrue(text and len(text) <= 140 and text.isascii(), (sid, text))
                self.assertLessEqual(placeholders(text), allowed, (sid, text))
                text.format(card="SD1", game="Test Game")
                if who == "*":
                    self.assertLessEqual(len(text), 90, (sid, text))                          # short stage directions
            self.assertTrue(any(w != "*" for w, _ in s["lines"]), sid)

    def test_engine_reads_every_scene(self):
        got = {s["id"]: s for s in cast.all_scenes(unlocked=True)}
        for s in SCENES + AD_SCENES:
            self.assertIn(s["id"], got)
            self.assertEqual(len(cast.play(got[s["id"]], {"card": "SD1", "game": "Test Game"})), len(s["lines"]))

    def test_ratings_stay_in_their_tier(self):
        self.assertEqual({s["rating"] for s in SCENES}, {"all"})
        self.assertEqual({s["rating"] for s in AD_SCENES}, {"afterdark"})
        self.assertTrue(all(s["rating"] == "all" for s in cast.all_scenes(unlocked=False)))


class Volume(Fresh):
    def test_group_minimums_and_any_pool(self):
        groups = Counter("+".join(s["who"]) for s in SCENES)
        for g, least in MINIMUMS.items():
            self.assertGreaterEqual(groups[g], least, g)
        anys = Counter("+".join(s["who"]) for s in SCENES if s["when"] == "any")
        for g in GROUPS:
            self.assertGreaterEqual(anys[g], 3, g)

    def test_moments_are_covered(self):
        whens = Counter((s["key"], s["when"]) for s in cast.all_scenes())
        for when in ("rotated", "synced", "due", "night", "morning"):
            self.assertTrue(whens[("iggy+nova", when)], when)
            self.assertTrue(whens[("duskie+iggy+nova", when)], when)
        for key in TOP5:
            self.assertTrue(any(w == f"game:{key}" for _, w in whens), key)
            self.assertTrue(whens[("iggy+nova", f"game:{key}")], key)
        for tag in ("cozy", "horror", "racing", "party", "rpg"):
            self.assertTrue(whens[("iggy+nova", f"tag:{tag}")], tag)

    def test_every_arrival_and_departure_has_a_scene(self):
        """For every regular group: a scene for each member walking in (said with the others there) and heading out."""
        scenes = [s for s in cast.all_scenes() if not set(s["who"]) & CAMEOS]
        for g in GROUPS:
            members = g.split("+")
            for m in members:
                for when in ("arrive", "leave"):
                    picked = cast.pick_scene(members, when, rng=random.Random(1), context={"movers": [m]})
                    self.assertIsNotNone(picked, (g, m, when))
                    self.assertEqual((picked["key"], picked["about"]), (g, [m]))
        self.assertTrue(scenes)

    def test_pick_scene_finds_something_for_every_group(self):
        for g in GROUPS:
            for when in ("any", "night", "morning"):
                self.assertIsNotNone(cast.pick_scene(g.split("+"), when, rng=random.Random(3)), (g, when))


class Cameos(Fresh):
    def test_new_cameo_walk_ons(self):
        for cid in NEW_CAMEOS:
            mine = [s for s in SCENES if cid in s["who"]]
            self.assertTrue(2 <= len(mine) <= 3, cid)
            for s in mine:
                others = set(s["who"]) - {cid}
                self.assertTrue(others and others <= {"nova", "iggy"}, s["id"])              # cameos visit the usual pair
                self.assertTrue(any(w == cid for w, _ in s["lines"]), s["id"])
            self.assertTrue(any(s["when"] == "arrive" for s in mine), cid)
        for s in SCENES:
            for who, text in s["lines"]:
                if who == "pickle":
                    self.assertNotIn("!", text)
                if who == "refills":
                    self.assertRegex(text, r"^[A-Z][a-z]+\.$")
        vesper = [s for s in SCENES if "vesper" in s["who"]]
        self.assertTrue(all(s["when"] in ("night", "arrive") for s in vesper))
        self.assertGreaterEqual(sum(s["when"] == "night" for s in vesper), 2)

    def test_a_visiting_cameo_gets_its_scene(self):
        for cid in NEW_CAMEOS:
            visit = ["iggy", "nova", cid]
            picked = cast.pick_scene(visit, "arrive", rng=random.Random(2), context={"movers": [cid]})
            self.assertIsNotNone(picked, cid)
            self.assertIn(cid, picked["who"])

    def test_no_cameo_in_afterdark(self):
        """No cameo as a participant, speaker, bucket key or joke teller, and no cameo named in the text. Ids are
        checked structurally ("refills" is also pharmacy shop-talk); display names are matched case-sensitively."""
        for s in AD_SCENES:
            self.assertFalse(set(s["who"]) & CAMEOS, s["id"])
            self.assertFalse({w for w, _ in s["lines"]} & CAMEOS, s["id"])
        for key, b in AD_PETS.items():
            if isinstance(b, dict):
                self.assertFalse(set(b) & CAMEOS, key)
            for per in (b.values() if isinstance(b, dict) else []):
                if isinstance(per, dict):
                    self.assertFalse(set(per) & CAMEOS, key)
        for who, _ in AD_PETS.get("jokes", []) + AD_PETS.get("fortunes", []):
            self.assertNotIn(cast.resolve(who), CAMEOS)
        text = "\n".join(list(strings(AD_PETS)) + [t for s in AD_SCENES for _, t in s["lines"]])
        for cid in CAMEOS:
            self.assertIsNone(re.search(rf"\b{re.escape(CAST[cid]['name'])}\b", text), cid)


class Afterdark(Fresh):
    def test_volume_and_spread(self):
        groups = Counter("+".join(s["who"]) for s in AD_SCENES)
        self.assertGreaterEqual(len(AD_SCENES), 36)
        self.assertGreaterEqual(groups["iggy+nova"], 15)
        for g in ("duskie+iggy+nova", "duskie+nova", "duskie+iggy"):
            self.assertGreaterEqual(groups[g], 5, g)
        self.assertLessEqual(set(groups), {"iggy+nova", "duskie+iggy+nova", "duskie+nova", "duskie+iggy"})


class ContentRules(Fresh):
    def test_spatchcock_exactly_once(self):
        hits = [(s["id"], s["who"], who) for s in SCENES + AD_SCENES for who, t in s["lines"] if t == SPATCHCOCK]
        self.assertEqual(len(hits), 1)
        self.assertEqual((hits[0][1], hits[0][2]), (["iggy", "nova"], "iggy"))
        self.assertEqual(sum(t.count("spatchcock") for t in all_text()), 1)

    def test_no_pet_names_for_the_player(self):
        for t in all_text():
            if t not in PET_NAME_OK:
                self.assertIsNone(PET_NAMES.search(t), t)

    def test_no_explicit_language_in_any_tier(self):
        for t in all_text():
            self.assertIsNone(EXPLICIT.search(t), t)


if __name__ == "__main__":
    unittest.main()
