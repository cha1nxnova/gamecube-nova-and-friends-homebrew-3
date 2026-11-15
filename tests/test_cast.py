"""Cast engine tests (docs/SPEC_V2.md sections 1-4): the cast file, presence, meetups, scenes, packs, the After Dark
lock, the cast-driven PetBrain and the new CLI commands.

Everything runs against a temp cast / scenes / After Dark / packs tree and controlled pets content, so these tests do
not depend on the shipped prose (the writer may change every line). Nothing here touches a real config or state."""
import datetime
import itertools
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from pawtation import afterdark, cast, core, pets
from pawtation.core import Catalog

ROOT = Path(__file__).resolve().parent.parent
SENTINEL = "ZZAFTERDARKZZ"                       # every After Dark fixture line carries this; it must never leak
PACK_ALL = "PACKALLOK"                           # ...and every line of the "all"-rated fixture pack carries this

CAST = {"version": 1,
        "characters": {
            "nova": {"name": "Nova", "species": "serval", "pronouns": "he/him", "role": "main",
                     "aliases": ["nova", "serval", "cat", "kitty"], "color": "#2b2d42", "accent": "#f52fd2"},
            "iggy": {"name": "Iggy", "species": "fennec fox", "pronouns": "any/all", "role": "main",
                     "aliases": ["iggy", "fennec", "fox", "pup", "puppy"], "color": "#d2b48c", "accent": "#7582b5"},
            "duskie": {"name": "Duskie", "species": "golden jackal", "pronouns": "he/him", "role": "guest",
                       "aliases": ["duskie", "dusk", "jackal"], "color": "#ffd37c", "accent": "#79bff0"},
            "mochi": {"name": "Mochi", "species": "cat", "pronouns": "she/her", "role": "cameo", "aliases": ["mochi"]},
            "biscuit": {"name": "Biscuit", "species": "dog", "pronouns": "he/him", "role": "cameo", "aliases": ["biscuit"]}},
        "presence": {"groups": {"nova+iggy": 58, "nova": 9, "iggy": 9, "duskie+iggy+nova": 10,
                                "duskie+nova": 5, "duskie+iggy": 5, "cameo": 4},
                     "min_minutes": 20, "max_minutes": 90}}
IDS = list(CAST["characters"])
REGULARS = ["nova", "iggy", "duskie"]
GROUPS = [sorted(c) for n in (1, 2, 3) for c in itertools.combinations(REGULARS, n)]          # the seven meetups
WALK_ONS = [["biscuit", "iggy", "nova"], ["iggy", "mochi", "nova"]]
BUCKETS = ["greeting", "idle", "rotation_due", "rotated", "synced", "ranked", "study_break", "arrive", "leave", "absent"]
WHENS = ["any", "arrive", "leave", "rotated", "synced", "due", "night", "morning"]
NOON = datetime.datetime(2026, 11, 15, 12, 0)
NIGHT = datetime.datetime(2026, 11, 15, 23, 30)
MORNING = datetime.datetime(2026, 11, 16, 7, 0)
GAMES = [{"key": "pikmin-2", "title": "Pikmin 2", "tags": ["cozy"]}, {"key": "chibi-robo", "title": "Chibi-Robo!", "tags": []},
         {"key": "star-fox-adventures", "title": "Star Fox Adventures", "tags": []}]


def name_of(cid):
    return CAST["characters"][cid]["name"]


def ok_pets():
    """All-rated content for the fixture cast. Every line says who it belongs to and which bucket it came from."""
    per = lambda b, ids=IDS: {i: [f"{b} line {n} from {i}" + (" {card}" if b == "synced" else " {game}" if b == "ranked"
                                                               else " about {name}" if b == "absent" else "")
                                  for n in (1, 2)] for i in ids}
    doc = {b: per(b) for b in BUCKETS}
    doc.update({
        "title": "FIXTURE",
        "characters": {i: {"name": name_of(i), "art": [f"[{i}]"], "art_happy": [f"[{i}^]"], "art_sleep": [f"[{i}z]"]} for i in IDS},
        "jokes": [[name_of(i), f"joke from {i}"] for i in IDS],
        "fortunes": [[name_of(i), f"fortune from {i}"] for i in IDS],
        "activities": {"fetch": dict({"verb": "Fetch", "needs": "energy", "affection": 1, "energy": -2}, **per("fetch")),
                       "nap": dict({"verb": "Nap", "needs": "none", "affection": 1, "energy": 3}, **per("nap"))},
        "game_quips": {"pikmin-2": {i: f"pikmin quip from {i}" for i in IDS}},
        "tag_quips": {"cozy": {i: f"cozy {{game}} from {i}" for i in IDS}},
        "state_of_collection": {k: [f"{k} one", f"{k} two"] for k in ("empty", "few", "many")},
    })
    return doc


def ok_scenes():
    """Two "any" scenes for each of the seven groups, plus moment scenes for the usual pair and the trio."""
    out = []
    for g in GROUPS:
        key = "+".join(g)
        for n in (1, 2):
            out.append({"id": f"any-{key}-{n}", "who": g, "when": "any", "rating": "all", "weight": 1,
                        "lines": [[g[0], f"any scene {n} for {key}"], ["*", "a stage direction"]]})
    pair, trio = ["iggy", "nova"], ["duskie", "iggy", "nova"]
    out += [
        {"id": "rotated-pair", "who": pair, "when": "rotated", "rating": "all", "lines": [["nova", "rotated scene"], ["iggy", "yes"]]},
        {"id": "synced-pair", "who": pair, "when": "synced", "rating": "all", "lines": [["iggy", "synced scene card {card}"]]},
        {"id": "night-pair", "who": pair, "when": "night", "rating": "all", "lines": [["nova", "night scene"]]},
        {"id": "arrive-duskie", "who": trio, "when": "arrive", "rating": "all", "lines": [["duskie", "arrive scene"]]},
        {"id": "leave-duskie", "who": trio, "when": "leave", "rating": "all", "about": ["duskie"], "lines": [["duskie", "leave scene"]]},
        {"id": "arrive-nova", "who": pair, "when": "arrive", "rating": "all", "about": ["nova"], "lines": [["nova", "nova arrive scene"]]},
        {"id": "game-pikmin", "who": pair, "when": "game:pikmin-2", "rating": "all", "lines": [["nova", "scene about {game}"]]},
    ]
    return out


def spicy_pets(tag=SENTINEL):
    """After Dark content in every place the engine could possibly read a line from."""
    per = lambda: {i: [f"{tag} line {n} from {i}" for n in (1, 2)] for i in IDS}
    doc = {b: per() for b in BUCKETS}
    doc.update({
        "title": tag,
        "characters": {i: {"name": f"{tag}{i}", "art": [tag], "art_happy": [tag], "art_sleep": [tag]} for i in IDS + ["ghost"]},
        "jokes": [[name_of(i), f"{tag} joke"] for i in IDS] + [[i, f"{tag} joke by id"] for i in IDS],
        "fortunes": [[name_of(i), f"{tag} fortune"] for i in IDS],
        "activities": {"fetch": per(), "nap": per(),
                       tag.lower(): dict({"verb": tag, "needs": "none", "affection": 1, "energy": 0}, **per())},
        "game_quips": {"pikmin-2": {i: [f"{tag} quip a", f"{tag} quip b"] for i in IDS},
                       "chibi-robo": {i: f"{tag} quip" for i in IDS}},
        "tag_quips": {"cozy": {i: f"{tag} {{game}}" for i in IDS}},
        "state_of_collection": {k: [f"{tag} {k}"] for k in ("empty", "few", "many")},
    })
    return doc


def spicy_scenes(tag=SENTINEL, rating="afterdark"):
    out = []
    for g in GROUPS + WALK_ONS:
        for when in WHENS + ["game:pikmin-2", "tag:cozy"]:
            scene = {"id": f"{tag}-{'+'.join(g)}-{when}", "who": g, "when": when, "weight": 50,
                     "lines": [[g[0], f"{tag} scene"], ["*", f"{tag} stage"]]}
            if rating is not None:
                scene["rating"] = rating
            out.append(scene)
    return out


class Fixture(unittest.TestCase):
    """A private data tree: cast.json, scenes.json, afterdark/, packs/ and pets content, all under a temp dir."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.data = self.tmp / "data"; (self.data / "afterdark").mkdir(parents=True)
        self.packs = self.tmp / "packs"; self.packs.mkdir()
        paths = (cast.CAST_PATH, cast.SCENES_PATH, cast.AFTERDARK_DIR, cast.PACKS_DIR)
        keep = json.dumps(pets.PETS)

        def restore():
            cast.CAST_PATH, cast.SCENES_PATH, cast.AFTERDARK_DIR, cast.PACKS_DIR = paths
            cast.reload()
            pets.PETS.clear(); pets.PETS.update(json.loads(keep))
        self.addCleanup(restore)
        cast.CAST_PATH, cast.SCENES_PATH = self.data / "cast.json", self.data / "scenes.json"
        cast.AFTERDARK_DIR, cast.PACKS_DIR = self.data / "afterdark", self.packs
        self.put(cast.CAST_PATH, CAST)
        self.put(cast.SCENES_PATH, {"version": 1, "scenes": ok_scenes()})
        pets.PETS.clear(); pets.PETS.update(ok_pets())
        cast.reload()
        self.cat = Catalog(GAMES)
        self.roms = [core.Rom(path=f"{g['key']}.iso", size=1, code6=None, internal_title=None, key=g["key"], title=g["title"],
                              in_catalog=True, tags=g["tags"]) for g in GAMES]
        self.state = {"history": [{"ts": 1, "season": 1, "plan": {"1": ["pikmin-2"], "2": []}}]}

    def put(self, path, obj):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
        cast.reload()

    def pack(self, name, meta=None, scenes=None, lines=None):
        d = self.packs / name; d.mkdir(parents=True, exist_ok=True)
        if meta is not None:
            self.put(d / "pack.json", meta)
        if scenes is not None:
            self.put(d / "scenes.json", {"version": 1, "scenes": scenes})
        if lines is not None:
            self.put(d / "pets.json", lines)
        cast.reload()

    def add_afterdark(self):
        """After Dark content everywhere it could hide: the built-in tier, packs, and mislabelled spots."""
        self.put(cast.AFTERDARK_DIR / "pets.json", spicy_pets())
        self.put(cast.AFTERDARK_DIR / "scenes.json", {"version": 1, "scenes": spicy_scenes(rating="all")})   # mislabelled on purpose
        self.pack("spicy", {"name": "Spicy", "rating": "afterdark"}, spicy_scenes(), spicy_pets())
        self.pack("no-pack-json", None, spicy_scenes(rating="all"), spicy_pets())                 # no rating at all: fail closed
        self.pack("odd-rating", {"name": "Odd", "rating": "mature"}, spicy_scenes(rating="all"), spicy_pets())
        self.pack("list-rating", {"rating": ["all"]}, spicy_scenes(rating=None), spicy_pets())
        self.pack("broken-json", "{not json", spicy_scenes(rating="all"), spicy_pets())
        self.pack("cozy", {"name": "Cozy", "rating": "all"},                                      # an honest all-rated pack...
                  [{"id": "pack-all", "who": ["iggy", "nova"], "when": "any", "rating": "all", "weight": 1,
                    "lines": [["nova", f"{PACK_ALL} scene"]]}] + spicy_scenes(),                 # ...with afterdark scenes inside
                  {"idle": {"nova": [f"{PACK_ALL} idle"]}, "jokes": [["Nova", f"{PACK_ALL} joke"]]})
        self.put(cast.SCENES_PATH, {"version": 1, "scenes": ok_scenes() + spicy_scenes() + spicy_scenes(rating="weird")})

    def brain(self, seed=1, clock=NOON, state=None):
        return pets.PetBrain(self.state if state is None else state, self.cat, random.Random(seed), clock=lambda: clock)

    def home(self, who, state=None, manual=True):
        (self.state if state is None else state)["scene"] = {"who": sorted(who), "until": NOON.timestamp() + 3600, "manual": manual}


# ---------------------------------------------------------------------------------------------------------- cast file
class CastFile(Fixture):
    def test_roles_keys_and_names(self):
        self.assertEqual((cast.mains(), cast.guests(), cast.cameos()), (["nova", "iggy"], ["duskie"], ["mochi", "biscuit"]))
        self.assertEqual(cast.regulars(), REGULARS)
        self.assertEqual(cast.ids(), IDS); self.assertEqual(cast.ids("guest", "cameo"), ["duskie", "mochi", "biscuit"])
        self.assertEqual(cast.group_key(["nova", "duskie", "iggy", "nova"]), "duskie+iggy+nova")
        self.assertEqual(cast.group_key("nova+iggy"), "iggy+nova")
        self.assertEqual(cast.group_key(None), ""); self.assertEqual(cast.group_key([1, None, "Nova "]), "nova")
        self.assertEqual(cast.order(["duskie", "ghost", 7, "nova", "nova"]), ["nova", "duskie"])
        self.assertEqual((cast.name("iggy"), cast.name("ghost"), cast.role("duskie"), cast.role("ghost")), ("Iggy", "Ghost", "guest", ""))
        self.assertEqual(cast.names(["duskie", "nova", "iggy"]), "Nova, Iggy and Duskie")
        self.assertEqual((cast.names(["iggy"]), cast.names([]), cast.names(["nova", "iggy"], "or")), ("Iggy", "", "Nova or Iggy"))
        self.assertEqual(cast.default_group(), ["iggy", "nova"])
        self.assertEqual(cast.load_cast()["presence"]["groups"]["iggy+nova"], 58)             # "nova+iggy" was normalised
        self.assertEqual(pets.NAMES, cast.mains())                                            # the old module attribute

    def test_resolve_and_find(self):
        self.assertEqual([cast.resolve(x) for x in ("NOVA", " Duskie ", "jackal", "puppy", "ghost", "", None, 5)],
                         ["nova", "duskie", "duskie", "iggy", None, None, None, None])
        self.assertEqual(cast.find("hey duskie, is nova's cat nap over?"), ["duskie", "nova"])
        self.assertEqual(cast.find("Tell IGGY and the jackal"), ["iggy", "duskie"])
        self.assertEqual(cast.find("display the catalog, supernova puppyish duskiest"), [])   # whole words only
        self.assertEqual(cast.find("star fox adventures"), ["iggy"])
        self.assertEqual(cast.find("star fox adventures", strict=True), [])                   # species words are loose aliases
        self.assertEqual(cast.find("the fox and Nova", strict=True), ["nova"])
        self.assertEqual(cast.find(None), [])

    def test_shipped_cast_file_is_usable(self):
        shipped = json.loads((ROOT / "data" / "cast.json").read_text(encoding="utf-8"))
        self.put(cast.CAST_PATH, shipped)
        loaded = cast.load_cast()
        self.assertEqual(list(loaded["characters"]), list(shipped["characters"]))             # nothing was rejected
        self.assertTrue(cast.mains()); self.assertEqual(len(loaded["presence"]["groups"]), len(shipped["presence"]["groups"]))
        for c in loaded["characters"].values():
            self.assertIn(c["role"], cast.ROLES)

    def test_missing_or_useless_file_falls_back_to_the_builtin_pair(self):
        for raw in (None, "{not json", "[]", "7", '"x"', {}, {"characters": []}, {"characters": {"x": 5, 7: {}, "": {}}},
                    {"characters": {"solo": {"role": "guest"}}},                              # nobody is a main
                    {"characters": {"a b": {"role": "main"}, "cameo": {"role": "main"}, "x+y": {"role": "main"}}}):
            if raw is None:
                cast.CAST_PATH.unlink(); cast.reload()
            else:
                self.put(cast.CAST_PATH, raw)
            self.assertEqual(list(cast.characters()), list(cast.BUILTIN_CAST["characters"]), raw)
            self.assertEqual(len(cast.mains()), 2)
            self.assertTrue(cast.step({}, NOON, random.Random(1))["who"])

    def test_damaged_entries_are_repaired_or_dropped(self):
        self.put(cast.CAST_PATH, {"characters": {
            "Zed": {"role": "main", "name": 5, "aliases": "zed", "color": "red", "accent": ["#fff"]},
            "pal": {"role": "sidekick", "name": "  Pal \n the  Second ", "aliases": ["PAL", 3, "", "buddy", "pal"]},
            "bad id!": {"role": "main"}, "list": ["main"], "g": {"role": "guest", "pronouns": 7}},
            "presence": {"groups": {"zed": "lots", "g": 5, "zed+ghost": 5, "pal+zed": 5, "zed+g": 3, "cameo": True, 5: 5,
                                    "zed+zed": 2, "g+zed": float("inf")},
                         "min_minutes": 90, "max_minutes": 20}})
        chars = cast.characters()
        self.assertEqual(list(chars), ["zed", "pal", "g"])
        self.assertEqual((chars["zed"]["name"], chars["zed"]["color"], chars["zed"]["accent"], chars["zed"]["aliases"]), ("Zed", "", "", ["zed"]))
        self.assertEqual((chars["pal"]["role"], chars["pal"]["name"], chars["pal"]["aliases"]), ("cameo", "Pal the Second", ["pal", "pal the second", "buddy"]))
        self.assertEqual(chars["g"]["pronouns"], "")
        p = cast.load_cast()["presence"]
        self.assertEqual(p["groups"], {"g+zed": 3.0, "zed": 2.0})                           # only groups with a main, no cameos
        self.assertEqual((p["min_minutes"], p["max_minutes"]), (20, 90))                      # swapped back into order

    def test_presence_defaults_come_from_roles(self):
        for presence in (None, [], {"groups": []}, {"groups": {"ghost": 5, "duskie": 5}}, {"groups": {"nova": -1, "iggy": 0}},
                         {"min_minutes": "x", "max_minutes": None}):
            self.put(cast.CAST_PATH, dict(CAST, presence=presence))
            p = cast.load_cast()["presence"]
            self.assertEqual(p["groups"], {"iggy+nova": 58.0, "nova": 9.0, "iggy": 9.0, "duskie+iggy+nova": 10.0,
                                           "duskie+nova": 5.0, "duskie+iggy": 5.0, "cameo": 4.0}, presence)
            self.assertEqual((p["min_minutes"], p["max_minutes"]), (20, 90))
        only_mains = {k: v for k, v in CAST["characters"].items() if v["role"] == "main"}
        self.put(cast.CAST_PATH, {"characters": only_mains, "presence": {"groups": {"cameo": 5}}})
        self.assertNotIn("cameo", cast.load_cast()["presence"]["groups"])                     # no cameos, so no cameo slot

    def test_a_new_character_is_one_entry(self):
        extra = json.loads(json.dumps(CAST))
        extra["characters"]["pip"] = {"name": "Pip", "role": "guest", "aliases": ["pip"]}
        extra["presence"]["groups"]["nova+pip"] = 50
        self.put(cast.CAST_PATH, extra)
        self.assertEqual(cast.guests(), ["duskie", "pip"])
        state = {}
        b = self.brain(state=state)
        self.assertEqual(state["pets"]["pip"], {"affection": 5, "energy": 5})
        self.assertEqual(cast.gather(state, ["pip"], now=NOON)["who"], ["pip"])
        self.assertTrue(b.reply("hello pip").startswith("Pip:"))                             # generic line, no content needed


# ----------------------------------------------------------------------------------------------------------- presence
class Presence(Fixture):
    def test_present_never_mutates_and_defaults_to_the_usual_group(self):
        for state in ({}, {"scene": None}, {"scene": {"who": [], "until": 0, "manual": False}}):
            before = json.dumps(state)
            self.assertEqual(cast.present(state, NOON), ["iggy", "nova"])
            self.assertEqual(json.dumps(state), before)
        state = {"scene": {"who": ["nova", "duskie"], "until": 5.0, "manual": True}}
        before = json.dumps(state)
        self.assertEqual(cast.present(state, NOON), ["duskie", "nova"])                       # expired, but only step() moves anyone
        self.assertEqual(cast.present(state), ["duskie", "nova"]); self.assertEqual(json.dumps(state), before)
        self.assertEqual(cast.remaining(state, NOON), 0.0)

    def test_step_only_draws_when_the_group_has_expired(self):
        rng, state = random.Random(5), {}
        first = cast.step(state, NOON, rng)
        self.assertEqual(sorted(first), ["arrived", "changed", "left", "who"])
        sc = dict(state["scene"])
        self.assertEqual((sc["who"], sc["manual"]), (first["who"], False))
        self.assertTrue(20 * 60 <= sc["until"] - NOON.timestamp() <= 90 * 60)
        for minutes in (0, 1, 19):                                                            # still inside the shortest stay
            again = cast.step(state, NOON + datetime.timedelta(minutes=minutes), rng)
            self.assertEqual(again, {"who": first["who"], "arrived": [], "left": [], "changed": False})
            self.assertEqual(state["scene"], sc)
        later = cast.step(state, sc["until"] + 1, rng)                                        # a plain timestamp works too
        self.assertGreater(state["scene"]["until"], sc["until"])
        self.assertEqual(later["changed"], set(later["who"]) != set(first["who"]))
        self.assertEqual(sorted(later["who"]), sorted(set(first["who"]) - set(later["left"]) | set(later["arrived"])))

    def test_presence_weights_over_many_draws(self):
        rng, state, t = random.Random(2026), {}, 1_800_000_000.0
        n, seen, groups, stays = 20000, Counter(), Counter(), []
        for _ in range(n):
            who = cast.step(state, t, rng)["who"]
            self.assertTrue(set(who) & {"nova", "iggy"}, who)                                 # at least one main, always
            if set(who) & {"mochi", "biscuit"}:
                self.assertEqual(len(who), 3); self.assertTrue({"nova", "iggy"} <= set(who))  # a cameo joins the usual pair
            self.assertEqual(who, sorted(who))
            seen.update(who); groups[cast.group_key(who)] += 1
            stays.append(state["scene"]["until"] - t)
            t = state["scene"]["until"] + 1                                                   # jump past the stay: next call redraws
        share = {i: seen[i] / n for i in IDS}
        self.assertGreater(share["nova"], 0.82); self.assertGreater(share["iggy"], 0.82)      # expected 0.86 each
        self.assertTrue(0.16 < share["duskie"] < 0.24, share)                                 # expected 0.20
        self.assertTrue(0.012 < share["mochi"] < 0.03 and 0.012 < share["biscuit"] < 0.03, share)   # expected 0.02 each
        self.assertGreater(min(share["nova"], share["iggy"]), 3 * share["duskie"])            # mains far more than the guest
        self.assertGreater(share["duskie"], 5 * max(share["mochi"], share["biscuit"]))        # guest far more than any cameo
        self.assertTrue(0.55 < groups["iggy+nova"] / n < 0.61, groups)                        # expected 0.58
        self.assertEqual(set(groups) - {"iggy+nova", "nova", "iggy", "duskie+iggy+nova", "duskie+nova", "duskie+iggy",
                                        "iggy+mochi+nova", "biscuit+iggy+nova"}, set())
        self.assertTrue(20 * 60 <= min(stays) and max(stays) <= 90 * 60)
        self.assertEqual(state["scene"]["manual"], False)

    def test_gather_every_single_pair_and_trio(self):
        self.assertEqual(len(GROUPS), 7)
        for group in GROUPS:
            state = {}
            r = cast.gather(state, group, now=NOON)
            self.assertEqual((r["error"], r["who"]), ("", group))
            self.assertEqual(state["scene"], {"who": group, "until": NOON.timestamp() + 90 * 60, "manual": True})
            self.assertEqual(cast.present(state, NOON), group)
            self.assertTrue(cast.is_manual(state))
            self.assertEqual(r["arrived"], [i for i in REGULARS if i in group and i not in ("nova", "iggy")])
            self.assertEqual(r["left"], [i for i in ("nova", "iggy") if i not in group])
            self.assertEqual(r["changed"], group != ["iggy", "nova"])
            self.assertEqual(cast.step(state, NOON + datetime.timedelta(minutes=89), random.Random(1))["who"], group)

    def test_gather_validation(self):
        state = {"scene": {"who": ["nova"], "until": NOON.timestamp() + 60, "manual": False}}
        before = json.dumps(state)
        for nobody in ([], None, 5, "", ["ghost"], ["mochi", "biscuit"], [None, 3, ""], "ghost"):   # cameos cannot be gathered
            r = cast.gather(state, nobody, now=NOON)
            self.assertTrue(r["error"], nobody); self.assertIn("Duskie", r["error"])
            self.assertEqual((r["who"], r["changed"], r["arrived"], r["left"]), (["nova"], False, [], []))
            self.assertEqual(json.dumps(state), before)
        r = cast.gather(state, ["ghost", "JACKAL", 7, "mochi", "Nova", "nova"], minutes=30, now=NOON)   # unknown ids are ignored
        self.assertEqual((r["error"], r["who"], r["arrived"]), ("", ["duskie", "nova"], ["duskie"]))
        self.assertEqual(state["scene"]["until"], NOON.timestamp() + 30 * 60)
        self.assertEqual(cast.gather(state, "iggy duskie", now=NOON)["who"], ["duskie", "iggy"])
        for minutes in (-5, 0, "long", None, float("nan"), True):                             # nonsense -> the default stay
            cast.gather(state, ["nova"], minutes=minutes, now=NOON)
            self.assertEqual(state["scene"]["until"], NOON.timestamp() + 90 * 60, minutes)
        cast.gather(state, ["nova"], minutes=10 ** 9, now=NOON)
        self.assertEqual(state["scene"]["until"], NOON.timestamp() + cast.MAX_HOLD_MINUTES * 60)

    def test_manual_group_expires_back_to_random(self):
        rng, state = random.Random(3), {}
        cast.gather(state, ["duskie"], minutes=30, now=NOON)                                  # the guest alone: allowed by hand
        for minutes in (0, 15, 29.9):
            r = cast.step(state, NOON + datetime.timedelta(minutes=minutes), rng)
            self.assertEqual((r["who"], r["changed"], state["scene"]["manual"]), (["duskie"], False, True))
        r = cast.step(state, NOON + datetime.timedelta(minutes=30.1), rng)
        self.assertEqual(state["scene"]["manual"], False)
        self.assertTrue(set(r["who"]) & {"nova", "iggy"}); self.assertTrue(r["changed"])
        self.assertEqual(r["left"], [] if "duskie" in r["who"] else ["duskie"])
        self.assertEqual(sorted(r["arrived"]), sorted(set(r["who"]) - {"duskie"}))

    def test_shuffle_redraws_now(self):
        rng, state = random.Random(1), {}
        cast.gather(state, ["duskie"], now=NOON)
        r = cast.shuffle(state, NOON, rng)
        self.assertTrue(set(r["who"]) & {"nova", "iggy"}); self.assertFalse(state["scene"]["manual"])
        self.assertEqual(r["left"], [] if "duskie" in r["who"] else ["duskie"])
        self.assertGreater(cast.remaining(state, NOON), 0)

    def test_damaged_scene_state(self):
        far = NOON.timestamp() + 600
        for scene, expect in ((5, None), ([], None), ("nova", None), ({"who": "nova"}, None), ({"who": {"nova": 1}}, None),
                              ({"who": [1, None, ["nova"]], "until": far}, None), ({"who": ["ghost"], "until": far}, None),
                              ({"who": ["mochi", "biscuit"], "until": far}, None),            # cameos are never home alone
                              ({"who": ["nova", "ghost", 4, "nova"], "until": far}, ["nova"]),
                              ({"who": ["duskie"], "until": far, "manual": "yes"}, ["duskie"]),
                              ({"who": ["mochi", "iggy"], "until": far}, ["iggy", "mochi"])):
            state = {"scene": scene}
            self.assertEqual(cast.present(state, NOON), expect or ["iggy", "nova"], scene)
            r = cast.step(state, NOON, random.Random(1))
            self.assertEqual(r["who"] == expect, expect is not None, scene)                   # usable -> kept; otherwise redrawn
            self.assertTrue(set(cast.present(state, NOON)) & set(REGULARS))
            self.assertEqual(cast.clean_scene_state(scene)["manual"], False)
        for until in ("soon", None, float("nan"), float("inf"), [1], NOON.timestamp() + 10 * 365 * 86400, -5):
            state = {"scene": {"who": ["duskie", "nova"], "until": until, "manual": True}}    # a broken / runaway clock value
            self.assertEqual(cast.remaining(state, NOON), 0.0, until)
            cast.step(state, NOON, random.Random(2))
            self.assertFalse(state["scene"]["manual"]); self.assertTrue(0 < cast.remaining(state, NOON) <= 90 * 60)
        for state in (None, [], "x", 5):                                                      # not even a dict
            self.assertEqual(cast.present(state), ["iggy", "nova"])
            self.assertTrue(cast.step(state, NOON, random.Random(1))["who"])
            self.assertEqual(cast.gather(state, ["nova"])["who"], ["nova"])

    def test_load_state_defaults_and_repairs(self):
        home = self.tmp / "home"; home.mkdir()
        old = core.STATE_PATH
        core.STATE_PATH = home / "state.json"
        self.addCleanup(setattr, core, "STATE_PATH", old)
        st = core.load_state()                                                                # no file at all
        self.assertEqual(st["pets"], {i: {"affection": 5, "energy": 5} for i in REGULARS})   # every non-cameo; no cameo entries
        self.assertEqual((st["scene"], st["afterdark"]), ({"who": [], "until": 0, "manual": False}, {"unlocked": False}))
        core.STATE_PATH.write_text(json.dumps({
            "pets": {"mochi": {"affection": 9, "energy": 1}, "biscuit": "old", "nova": {"affection": "x"}, "iggy": {"affection": 7, "energy": 2}},
            "scene": {"who": ["nova", 5, "duskie", "nova"], "until": "later", "manual": 1}, "afterdark": {"unlocked": "yes"}}))
        st = core.load_state()
        self.assertEqual(st["pets"], {"mochi": {"affection": 9, "energy": 1}, "biscuit": "old",   # v1 entries are left alone
                                      "nova": {"affection": 5, "energy": 5}, "iggy": {"affection": 7, "energy": 2},
                                      "duskie": {"affection": 5, "energy": 5}})
        self.assertEqual(st["scene"], {"who": ["duskie", "nova"], "until": 0, "manual": False})
        self.assertEqual(st["afterdark"], {"unlocked": False})
        for junk in ({"scene": 7, "afterdark": [True], "pets": 3}, {"scene": [], "afterdark": "unlocked"},
                     {"afterdark": {"unlocked": True}}, {"afterdark": {"unlocked": True, "confirmed_on": "sometime"}},
                     {"afterdark": {"unlocked": 1, "confirmed_on": "2026-01-01"}}):
            core.STATE_PATH.write_text(json.dumps(junk))
            st = core.load_state()
            self.assertEqual((st["scene"]["who"], st["afterdark"]), ([], {"unlocked": False}), junk)
            self.assertTrue(self.brain(state=st).reply("hi"))
        core.STATE_PATH.write_text(json.dumps({"afterdark": {"unlocked": True, "confirmed_on": "2026-11-15", "extra": 1}}))
        self.assertEqual(core.load_state()["afterdark"], {"unlocked": True, "confirmed_on": "2026-11-15"})


# ------------------------------------------------------------------------------------------------------------- scenes
class Scenes(Fixture):
    def pick(self, who, when="any", seed=0, **kw):
        kw.setdefault("unlocked", False)
        return cast.pick_scene(who, when, rng=random.Random(seed), **kw)

    def test_scene_matches_exactly_who_is_present(self):
        for group in GROUPS:
            ids = {self.pick(group, seed=s)["id"] for s in range(40)}
            key = "+".join(group)
            self.assertEqual(ids, {f"any-{key}-1", f"any-{key}-2"}, group)
            scene = self.pick(list(reversed(group)))
            self.assertEqual((scene["who"], scene["key"], scene["rating"]), (group, key, "all"))
        self.assertEqual(self.pick("nova+iggy")["key"], "iggy+nova")                         # a group key works as `who`
        for nobody in ([], None, ["ghost"], 5, [None]):
            self.assertIsNone(self.pick(nobody))
        self.put(cast.SCENES_PATH, {"scenes": [s for s in ok_scenes() if s["who"] != ["duskie"]]})
        self.assertIsNone(self.pick(["duskie"]))                                              # no borrowing from other groups

    def test_when_prefers_the_moment_then_any_but_events_are_strict(self):
        pair, trio = ["iggy", "nova"], ["duskie", "iggy", "nova"]
        for seed in range(20):
            self.assertEqual(self.pick(pair, "night", seed)["id"], "night-pair")
            self.assertEqual(self.pick(pair, "rotated", seed)["id"], "rotated-pair")
            self.assertEqual(self.pick(pair, "synced", seed, context={"card": "3"})["id"], "synced-pair")
            self.assertEqual(self.pick(pair, " NIGHT ", seed)["id"], "night-pair")
            self.assertTrue(self.pick(pair, "morning", seed)["id"].startswith("any-"))       # no morning scene: the any pool
            self.assertTrue(self.pick(trio, "night", seed)["id"].startswith("any-"))
            self.assertTrue(self.pick(pair, "tag:nothing", seed)["id"].startswith("any-"))
            self.assertTrue(self.pick(pair, None, seed)["id"].startswith("any-"))
            self.assertTrue(self.pick(pair, 7, seed)["id"].startswith("any-"))
        for when in cast.EVENT_WHENS:                                                         # never an unrelated "any" scene
            self.assertIsNone(self.pick(["nova"], when), when)
        self.assertIsNone(self.pick(trio, "rotated")); self.assertIsNone(self.pick(pair, "due"))
        self.assertEqual(cast.time_when(NIGHT), "night"); self.assertEqual(cast.time_when(MORNING), "morning")
        self.assertEqual(cast.time_when(NOON), "any"); self.assertEqual(cast.time_when(NOON.timestamp()), "any")
        hours = {h: cast.time_when(datetime.datetime(2026, 1, 1, h, 0)) for h in range(24)}
        self.assertEqual([h for h, w in hours.items() if w == "night"], [0, 1, 2, 3, 4, 22, 23])   # 22:00-05:00 local
        self.assertEqual([h for h, w in hours.items() if w == "morning"], [5, 6, 7, 8, 9, 10])

    def test_placeholders_need_their_context(self):
        pair = ["iggy", "nova"]
        self.assertIsNone(self.pick(pair, "synced"))                                          # {card} unknown: never shown raw
        self.assertIsNone(self.pick(pair, "synced", context={"game": "x"}))
        scene = self.pick(pair, "synced", context={"card": "B"})
        self.assertEqual(scene["needs"], ["card"])
        self.assertEqual(cast.play(scene, {"card": "B"}), ["Iggy: synced scene card B"])
        self.assertEqual(cast.play(self.pick(pair, "game:pikmin-2", context={"game": "Pikmin 2"}), {"game": "Pikmin 2"}),
                         ["Nova: scene about Pikmin 2"])
        self.assertTrue(self.pick(pair, "game:pikmin-2")["id"].startswith("any-"))            # without the title: fall back

    def test_arrive_and_leave_scenes_are_about_who_moved(self):
        pair, trio = ["iggy", "nova"], ["duskie", "iggy", "nova"]
        ctx = lambda *who: {"movers": list(who)}
        self.assertEqual(self.pick(trio, "arrive", context=ctx("duskie"))["id"], "arrive-duskie")   # default: the non-mains
        self.assertEqual(self.pick(trio, "arrive", context=ctx("duskie"))["about"], ["duskie"])
        self.assertIsNone(self.pick(trio, "arrive", context=ctx("nova")))                     # Nova came home: not that scene
        self.assertIsNone(self.pick(trio, "arrive", context=ctx("duskie", "nova")))
        self.assertEqual(self.pick(trio, "leave", context=ctx("duskie"))["id"], "leave-duskie")
        self.assertIsNone(self.pick(trio, "leave", context=ctx("iggy")))
        self.assertEqual(self.pick(pair, "arrive", context=ctx("nova"))["id"], "arrive-nova")       # explicit "about"
        self.assertIsNone(self.pick(pair, "arrive", context=ctx("iggy")))
        self.assertEqual(self.pick(trio, "arrive")["id"], "arrive-duskie")                    # no movers given: any arrive scene

    def test_rating_weight_and_avoid(self):
        pair = ["iggy", "nova"]
        extra = [{"id": "ad", "who": pair, "when": "any", "rating": "afterdark", "weight": 500, "lines": [["nova", SENTINEL]]},
                 {"id": "odd", "who": pair, "when": "any", "rating": "R", "weight": 500, "lines": [["nova", SENTINEL]]},
                 {"id": "heavy", "who": ["duskie"], "when": "any", "rating": "all", "weight": 18, "lines": [["duskie", "heavy"]]}]
        self.put(cast.SCENES_PATH, {"scenes": ok_scenes() + extra})
        locked = Counter(self.pick(pair, seed=s)["id"] for s in range(300))
        self.assertEqual(set(locked), {"any-iggy+nova-1", "any-iggy+nova-2"})
        for flag in (1, "yes", [True], None, 0):                                              # only a real True unlocks
            self.assertNotIn(self.pick(pair, seed=3, unlocked=flag)["rating"], ("afterdark",))
        self.assertTrue(all(s["rating"] == "all" for s in cast.all_scenes()))
        self.assertEqual({s["id"]: s["rating"] for s in cast.all_scenes(True) if s["id"] in ("ad", "odd")},
                         {"ad": "afterdark", "odd": "afterdark"})                             # an unknown rating is not "all"
        opened = Counter(self.pick(pair, seed=s, unlocked=True)["id"] for s in range(300))
        self.assertGreater(opened["ad"] + opened["odd"], 280)                                 # weight 500 + 500 against 1 + 1
        solo = Counter(self.pick(["duskie"], seed=s)["id"] for s in range(2000))
        self.assertTrue(0.86 < solo["heavy"] / 2000 < 0.94, solo)                             # 18 of 20
        for seed in range(30):
            self.assertEqual(self.pick(["nova"], seed=seed, avoid="any-nova-1")["id"], "any-nova-2")
            self.assertEqual(self.pick(pair, "night", seed, avoid="night-pair")["id"], "night-pair")   # the only choice stays

    def test_a_cameo_walk_on_does_not_silence_the_others(self):
        scene = self.pick(["biscuit", "iggy", "nova"])
        self.assertEqual(scene["key"], "iggy+nova")
        mine = {"id": "with-biscuit", "who": ["biscuit", "nova", "iggy"], "when": "any", "rating": "all",
                "lines": [["biscuit", "BORK"], ["nova", "Hello, neighbour."]]}
        self.put(cast.SCENES_PATH, {"scenes": ok_scenes() + [mine]})
        self.assertEqual(self.pick(["biscuit", "iggy", "nova"])["id"], "with-biscuit")        # an exact scene wins
        self.assertEqual(cast.play(self.pick(["biscuit", "iggy", "nova"])), ["Biscuit: BORK", "Nova: Hello, neighbour."])

    def test_play_and_script(self):
        scene = {"who": ["iggy", "nova"], "lines": [["nova", "Card {card}, {game}."], ["*", "A pause."], ["iggy", "{unknown} {"],
                                                    ["ghost", "boo"], "junk", ["nova"], ["nova", 5], None]}
        self.assertEqual(cast.play(scene, {"card": "A", "game": "Pikmin"}),
                         ["Nova: Card A, Pikmin.", "(A pause.)", "Iggy: {unknown} {", "Ghost: boo"])
        self.assertEqual(cast.script(scene, {"card": "A", "game": "Pikmin"})[:2], [("nova", "Card A, Pikmin."), ("*", "A pause.")])
        self.assertEqual(cast.play(scene)[0], "Nova: Card {card}, {game}.")                  # missing context: printed as written
        for junk in (None, 5, "x", [], {}, {"lines": 5}, {"lines": {"a": 1}}):
            self.assertEqual(cast.play(junk), []); self.assertEqual(cast.script(junk, 7), [])

    def test_malformed_scene_files(self):
        good = {"id": "good", "who": ["nova"], "when": "any", "rating": "all", "lines": [["nova", "fine"]]}
        for raw in ("{not json", "7", '"x"', "null", {}, {"scenes": 5}, {"scenes": {"a": 1}}, {"scenes": [None, 5, "x", [], {}]}):
            self.put(cast.SCENES_PATH, raw)
            self.assertEqual(cast.all_scenes(), [], raw); self.assertIsNone(self.pick(["nova"]))
            self.assertTrue(self.brain().scene()); self.assertTrue(self.brain().reply("hang out"))   # falls back to idle lines
        cast.SCENES_PATH.unlink(); cast.reload()
        self.assertEqual(cast.all_scenes(True), [])
        bad = [dict(good, id="who-missing", who=None), dict(good, id="who-empty", who=[]), dict(good, id="who-unknown", who=["nova", "ghost"]),
               dict(good, id="who-int", who=[1]), dict(good, id="when-int", when=5), dict(good, id="when-empty", when="  "),
               dict(good, id="no-lines", lines=[]), dict(good, id="lines-junk", lines="hello"),
               dict(good, id="stranger", lines=[["iggy", "not in who"]]), dict(good, id="blank", lines=[["nova", "   "]]),
               dict(good, id="nested", lines=[[["nova"], "x"]])]
        odd = [dict(good, id="str-who", who="nova"), dict(good, id=7, weight="heavy"), dict(good, id="neg", weight=-3),
               dict(good, id="mixed", lines=[["nova", "kept"], ["iggy", "dropped"], ["*", "kept too"], ["NOVA ", " spaced  out "], 5]),
               dict(good, id="about-junk", about=[5, "ghost"], when="arrive"), dict(good, id="no-rating", rating=None)]
        del odd[-1]["rating"]
        self.put(cast.SCENES_PATH, [good] + bad + odd)                                        # a bare list is accepted too
        got = {s["id"]: s for s in cast.all_scenes(True)}
        self.assertEqual(sorted(got), sorted(["good", "str-who", "builtin#13", "neg", "mixed", "about-junk", "no-rating"]))
        self.assertEqual((got["builtin#13"]["weight"], got["neg"]["weight"]), (1.0, 1.0))
        self.assertEqual(got["mixed"]["lines"], [["nova", "kept"], ["*", "kept too"], ["nova", "spaced out"]])
        self.assertEqual((got["about-junk"]["about"], got["no-rating"]["rating"], got["str-who"]["who"]), (["nova"], "all", ["nova"]))
        for _ in range(50):
            self.assertTrue(cast.play(self.pick(["nova"], seed=_)))


# -------------------------------------------------------------------------------------------------------------- packs
class Packs(Fixture):
    def test_all_rated_pack_loads_when_locked_and_afterdark_pack_does_not(self):
        self.pack("cozy", {"name": "Cozy Pack", "rating": "all"},
                  [{"id": "pack-all", "who": ["duskie"], "when": "any", "rating": "all", "weight": 500, "lines": [["duskie", f"{PACK_ALL} scene"]]}],
                  {"idle": {"duskie": [f"{PACK_ALL} idle"]}, "jokes": [["Duskie", f"{PACK_ALL} joke"]],
                   "game_quips": {"chibi-robo": {"duskie": f"{PACK_ALL} quip"}}})
        self.pack("spicy", {"name": "Spicy", "rating": "afterdark"},
                  [{"id": "pack-ad", "who": ["duskie"], "when": "any", "rating": "all", "weight": 500, "lines": [["duskie", f"{SENTINEL} scene"]]}],
                  {"idle": {"duskie": [f"{SENTINEL} idle"]}})
        (self.packs / "README.md").write_text("not a pack"); (self.packs / "_off").mkdir(); (self.packs / ".hidden").mkdir()
        self.put(self.packs / "_off" / "scenes.json", [{"who": ["duskie"], "lines": [["duskie", "disabled pack"]]}])
        self.assertEqual([(p["name"], p["rating"]) for p in cast.packs()], [("Cozy Pack", "all")])
        self.assertEqual([(p["name"], p["rating"]) for p in cast.packs(True)], [("Cozy Pack", "all"), ("Spicy", "afterdark")])
        self.assertEqual(cast.packs(True)[0]["path"], self.packs / "cozy")
        ids = [s["id"] for s in cast.all_scenes()]
        self.assertIn("pack-all", ids); self.assertNotIn("pack-ad", ids)
        self.assertEqual(len(ids), len(ok_scenes()) + 1)                                      # appended, nothing replaced
        self.assertEqual([s["source"] for s in cast.all_scenes() if s["id"] == "pack-all"], ["pack:cozy"])
        self.assertEqual({s["id"]: s["rating"] for s in cast.all_scenes(True) if s["id"].startswith("pack-")},
                         {"pack-all": "all", "pack-ad": "afterdark"})                         # the pack's rating overrides the label
        self.assertEqual(len(cast.extra_pets()), 1); self.assertEqual(len(cast.extra_pets(True)), 2)
        self.home(["duskie"])
        b = self.brain()
        said = {b.say("duskie", "idle") for _ in range(200)}
        self.assertEqual(said, {"Duskie: idle line 1 from duskie", "Duskie: idle line 2 from duskie", f"Duskie: {PACK_ALL} idle"})
        self.assertIn(f"Duskie: {PACK_ALL} joke", {b.joke() for _ in range(100)})
        self.assertIn(f"Duskie: {PACK_ALL} scene", {l for _ in range(20) for l in b.scene("any")})
        cards = b.card_quips(["chibi-robo"], limit=100)
        self.assertIn(f"Duskie: {PACK_ALL} quip", cards); self.assertIn(f"Duskie: {PACK_ALL} joke", cards)   # all-rated: fine on a card
        everything = said | {b.joke() for _ in range(200)} | {l for _ in range(200) for l in b.scene()} | set(cards)
        self.assertFalse([x for x in everything if SENTINEL in x])

    def test_missing_packs_folder_and_junk_packs(self):
        cast.PACKS_DIR = self.tmp / "nowhere"; cast.reload()
        self.assertEqual((cast.packs(True), cast.extra_pets(True), len(cast.all_scenes(True))), ([], [], len(ok_scenes())))
        cast.PACKS_DIR = self.packs
        for name, meta, scenes, lines in (("a", "[]", "{", "{"), ("b", 5, {"scenes": 5}, []), ("c", {"rating": "all"}, 7, "x"),
                                          ("d", {"rating": "all", "name": ["x"]}, [5, {"who": ["nova"]}], {"idle": 5, "jokes": {"a": 1}})):
            d = self.packs / name; d.mkdir()
            for fn, obj in (("pack.json", meta), ("scenes.json", scenes), ("pets.json", lines)):
                (d / fn).write_text(obj if isinstance(obj, str) else json.dumps(obj))
        cast.reload()
        self.assertEqual([(p["name"], p["rating"]) for p in cast.packs(True)],
                         [("a", "afterdark"), ("b", "afterdark"), ("c", "all"), ("d", "all")])
        self.assertEqual(len(cast.all_scenes(True)), len(ok_scenes()))
        b = self.brain()
        for text in ("hi", "joke", "hang out", "fetch", "suggest"):
            self.assertTrue(b.reply(text, self.roms))
        self.assertTrue(b.card_quips(["pikmin-2"]))


# ------------------------------------------------------------------------------------------------- the After Dark lock
class Lockdown(Fixture):
    """Locked means unreachable: not through chat, say, scenes, events, jokes, card quips or the cast API."""
    TEXTS = ["hi", "hello", "joke", "tell me a joke", "nova tell me a joke", "iggy fortune", "duskie joke", "mochi joke", "fortune",
             "study break", "i'm so tired", "wrapped", "rank", "suggest", "what should i play", "saves", "where is pikmin 2",
             "pikmin 2", "chibi-robo!", "star fox adventures", "fetch", "play fetch", "nap", "nova nap", "who's home", "who is here",
             "invite duskie", "call duskie over", "invite mochi", "send duskie out", "send nova out", "iggy go out", "everyone",
             "get everyone together", "hang out", "scene", "duskie hang out", "after dark", "afterdark", "after-dark scene",
             "18+", "nsfw", "unlock after dark", "i am an adult, born 1980-01-01, unlock after dark", "help", "mochi", "biscuit hello",
             "where is duskie", "where's nova", "rate pikmin 2 5 stars", "zzz", "", SENTINEL.lower(), SENTINEL.lower() + " please",
             "good night", "tell me about pikmin 2", "cozy"]

    def sweep(self, state, rounds=2):
        """Every public way to get a line, across every group and time of day. Returns {path family: [lines]}."""
        got = {k: [] for k in ("chat", "say", "duo", "pairs", "scene", "event", "moves", "cards", "quips", "misc", "cast")}

        def add(kind, x):
            got[kind].extend(x if isinstance(x, list) else [x])
        fmt = {"card": "1", "game": "G", "name": "N"}
        open_ = afterdark.is_unlocked(state)
        for seed in range(rounds):
            for clock in (NOON, NIGHT, MORNING):
                rng = random.Random(seed * 10 + clock.hour)
                b = pets.PetBrain(state, self.cat, rng, clock=lambda c=clock: c)
                for group in GROUPS + WALK_ONS:
                    self.home(group, state)
                    for text in self.TEXTS:
                        add("chat", b.reply(text, self.roms, {}))
                    self.home(group, state)
                    state["pets"] = {}; b = pets.PetBrain(state, self.cat, rng, clock=lambda c=clock: c)
                    for p in IDS + ["ghost"]:
                        for bucket in BUCKETS + ["nope"]:
                            add("say", b.say(p, bucket, **fmt))
                        add("pairs", [b.joke(p), b.fortune(p), b.joke(), b.fortune(), b.study_break(p)])
                        add("misc", [b.activity(p, "fetch"), b.activity(p, "nap"), b.activity(p, SENTINEL.lower()),
                                     b.art(p), b.art(p, "art_happy"), b.name(p), b.mood(p)])
                        add("quips", [b.game_quip(p, k) or "" for k in ("pikmin-2", "chibi-robo", "star-fox-adventures", "nope")])
                    for bucket in BUCKETS:
                        add("duo", b.duo(bucket, **fmt))
                    for when in WHENS + ["game:pikmin-2", "tag:cozy", "bogus", None]:
                        add("event", b.event(when, card="1", game="G"))
                        add("scene", b.scene(when, card="1", game="G"))
                        for flag in (open_, False, 0, None):
                            s = cast.pick_scene(group, when, unlocked=flag, rng=rng, context={"card": "1", "game": "G"})
                            add("cast", cast.play(s, {"card": "1", "game": "G"}) if s else [])
                    add("scene", b.scene()); add("event", b.due_nag())
                    add("misc", [b.collection(self.roms), b.collection([]), b.suggest(self.roms), b.suggest([]), b.ranking(self.roms),
                                 b.wrapped(self.roms), b.help(), b.save_report({}), b.save_report(None), b.home_line(), b.whos_home(),
                                 b.afterdark_info(), json.dumps(b.activities()), json.dumps(b.home())])
                    add("misc", [x for item in got["misc"][-14:] if isinstance(item, list) for x in item])
                    add("cards", b.card_quips(["pikmin-2", "chibi-robo", "star-fox-adventures", "nope"], limit=1000))
                    for other in GROUPS:                                                      # every possible move in and out
                        self.home(group, state)
                        add("moves", b.presence_lines(cast.gather(state, other, now=clock)))
                    self.home(group, state)
                    add("moves", b.invite(["duskie"])); add("moves", b.send_out(["duskie"])); add("moves", b.everyone())
                    add("moves", b.presence_lines(cast.shuffle(state, clock, rng)))
        add("cast", [json.dumps(cast.all_scenes(open_)), json.dumps(cast.extra_pets(open_)), json.dumps(cast.all_scenes()),
                     json.dumps(cast.extra_pets()), json.dumps(cast.all_scenes(1)), json.dumps(cast.extra_pets("yes")),
                     json.dumps([p["name"] for p in cast.packs(open_)]), json.dumps(pets._layers(open_)), json.dumps(pets._layers())])
        return {k: [x for x in v if isinstance(x, str)] for k, v in got.items()}

    def leaks(self, got):
        return {k: [x for x in v if SENTINEL in x or SENTINEL.lower() in x][:3] for k, v in got.items()
                if any(SENTINEL in x or SENTINEL.lower() in x for x in v)}

    def test_locked_state_can_never_surface_afterdark_content(self):
        self.add_afterdark()
        self.assertGreater(len(cast.all_scenes(True)), 500)                                   # the fixture really is in place
        for scene in ({"unlocked": False}, None):
            state = dict(self.state) if scene is None else dict(self.state, afterdark=scene)
            got = self.sweep(state)
            calls = sum(len(v) for v in got.values())
            self.assertGreater(calls, 20000, "the sweep must stay a brute-force hunt")
            self.assertEqual(self.leaks(got), {})
            self.assertTrue(any(PACK_ALL in x for x in got["chat"]))                          # the all-rated pack did load
            self.assertTrue(any(PACK_ALL in x for x in got["scene"])); self.assertTrue(any(PACK_ALL in x for x in got["cards"]))
            self.assertNotIn(SENTINEL, json.dumps(state)); self.assertFalse(afterdark.is_unlocked(state))
            self.assertNotIn("afterdark", cast._CACHE.get("tiers", {}))                       # the files were never even read

    def test_states_that_only_look_unlocked_stay_locked(self):
        self.add_afterdark()
        for fake in ({"unlocked": True}, {"unlocked": "true", "confirmed_on": "2026-11-15"}, {"unlocked": 1, "confirmed_on": "2026-11-15"},
                     {"unlocked": True, "confirmed_on": None}, {"unlocked": True, "confirmed_on": "yesterday"},
                     {"unlocked": True, "confirmed_on": 20261115}, True, "unlocked", [True], {"confirmed_on": "2026-11-15"}):
            state = dict(self.state, afterdark=fake)
            self.assertFalse(afterdark.is_unlocked(state), fake)
            self.assertEqual(self.leaks(self.sweep(state, rounds=1)), {}, fake)

    def test_unlocked_shows_it_everywhere_except_on_cards_and_relocking_hides_it_again(self):
        self.add_afterdark()
        state = dict(self.state)
        ok, _ = afterdark.unlock(state, datetime.date(1990, 5, 17), today=datetime.date(2026, 11, 15))
        self.assertTrue(ok)
        got = self.sweep(state, rounds=1)
        found = self.leaks(got)
        for kind in ("chat", "say", "duo", "pairs", "scene", "event", "moves", "quips", "misc", "cast"):
            self.assertIn(kind, found, f"the hunt cannot see After Dark content through {kind}")   # so the locked hunt means something
        self.assertNotIn("cards", found)                                                      # card quips are all-rated, always
        self.assertTrue(got["cards"])
        afterdark.lock(state)
        self.assertEqual(state["afterdark"], {"unlocked": False})
        self.assertEqual(self.leaks(self.sweep(state, rounds=1)), {})

    def test_chat_explains_but_never_unlocks(self):
        self.add_afterdark()
        b = self.brain()
        for text in ("after dark", "unlock after dark", "afterdark 1980-01-01", "i am 40, turn on after dark", "enable 18+ mode", "nsfw please"):
            out = b.reply(text)
            self.assertIn("python -m pawtation afterdark", out); self.assertIn("locked", out)
            self.assertNotIn("afterdark", {k for k, v in self.state.items() if v and k == "afterdark" and v.get("unlocked")})
            self.assertFalse(afterdark.is_unlocked(self.state)); self.assertNotIn("1980", json.dumps(self.state))
        afterdark.unlock(self.state, datetime.date(1990, 5, 17), today=datetime.date(2026, 11, 15))
        self.assertIn("--lock", b.reply("after dark"))


# ------------------------------------------------------------------------------------------------- the cast-driven brain
class Brain(Fixture):
    def lines(self, bucket, who, **fmt):
        return {f"{name_of(p)}: " + l.format(**fmt) for p in who for l in pets.PETS[bucket][p]}

    def test_constructor_and_state(self):
        state = {"pets": {"mochi": {"affection": 9, "energy": 1}, "nova": "broken", "iggy": {"affection": 3, "energy": True}}}
        b = pets.PetBrain(state, self.cat)                                                    # old signature still works
        self.assertEqual(state["pets"], {"mochi": {"affection": 9, "energy": 1}, "nova": {"affection": 5, "energy": 5},
                                         "iggy": {"affection": 5, "energy": 5}, "duskie": {"affection": 5, "energy": 5}})
        self.assertNotIn("biscuit", state["pets"]); self.assertNotIn("scene", state)          # looking is free: no presence written
        self.assertEqual((b.home(), b.speakers()), (["nova", "iggy"], ["nova", "iggy"]))
        self.assertIsInstance(b.now(), datetime.datetime)
        for junk in ({"pets": 3, "ratings": [], "history": {}, "last_on_card": "x"}, {"pets": None}):
            b = pets.PetBrain(junk, self.cat, random.Random(1), clock=lambda: 1 / 0)          # a broken clock is survivable
            self.assertIsInstance(b.now(), datetime.datetime)
            for text in ("hi", "suggest", "rank", "wrapped", "fetch", "where is pikmin 2", "hang out"):
                self.assertTrue(b.reply(text, self.roms))
        self.assertEqual(pets.other("nova"), "iggy"); self.assertEqual(pets.other("iggy"), "nova")

    def test_duo_is_one_line_from_each_character_who_is_home(self):
        b = self.brain()
        for group in GROUPS:
            self.home(group)
            for bucket in ("idle", "rotated", "greeting", "study_break"):
                out = b.duo(bucket)
                self.assertEqual([l.split(":")[0] for l in out], [name_of(p) for p in cast.order(group)], (group, bucket))
                self.assertTrue(set(out) <= self.lines(bucket, group))
            self.assertTrue(set(b.duo("synced", card="7")) <= self.lines("synced", group, card="7"))
        self.home(["biscuit", "iggy", "nova"])
        self.assertEqual([l.split(":")[0] for l in b.duo("greeting")], ["Nova", "Iggy", "Biscuit"])   # cameos say hello...
        self.assertEqual([l.split(":")[0] for l in b.duo("arrive")], ["Nova", "Iggy", "Biscuit"])
        for bucket in ("idle", "rotated", "rotation_due", "synced", "ranked", "study_break", "leave"):
            self.assertEqual([l.split(":")[0] for l in b.duo(bucket, card="1", game="G")], ["Nova", "Iggy"], bucket)   # ...and nothing else
        del pets.PETS["greeting"]["biscuit"]
        self.assertEqual([l.split(":")[0] for l in b.duo("greeting")], ["Nova", "Iggy"])      # a cameo with no line stays quiet
        self.assertEqual(b.say("biscuit", "greeting"), "Biscuit: Hi. Good to see you.")       # say() itself is unchanged

    def test_jokes_and_fortunes_come_from_whoever_is_home(self):
        b = self.brain()
        for group in GROUPS + WALK_ONS:
            self.home(group)
            for fn, word in ((b.joke, "joke"), (b.fortune, "fortune")):
                told = {fn() for _ in range(120)}
                self.assertEqual(told, {f"{name_of(p)}: {word} from {p}" for p in group}, group)
                for p in group:
                    self.assertEqual(fn(p), f"{name_of(p)}: {word} from {p}")                 # a named teller tells their own
        self.home(["duskie"])
        pets.PETS["jokes"] = [r for r in pets.PETS["jokes"] if r[0] != "Duskie"] + [["Stranger", "not in the cast"], ["nova", "joke by id"]]
        self.assertEqual({b.joke() for _ in range(80)}, {"Nova: joke from nova", "Nova: joke by id", "Iggy: joke from iggy"})   # fallback: any main
        self.assertEqual({b.reply("duskie tell me a joke").split(":")[0] for _ in range(40)}, {"Nova", "Iggy"})
        pets.PETS["jokes"] = [["Mochi", "cameo only"]]; pets.PETS["fortunes"] = "broken"
        self.assertTrue(b.joke().startswith("Duskie: ")); self.assertTrue(b.fortune().startswith("Duskie: "))   # nothing usable: a stock line
        self.assertNotIn("cameo only", b.joke())

    def test_event_plays_a_scene_or_falls_back_to_bucket_lines(self):
        b = self.brain()
        self.home(["iggy", "nova"])
        self.assertEqual(b.event("rotated"), ["Nova: rotated scene", "Iggy: yes"])
        self.assertEqual(b.event("synced", card="B"), ["Iggy: synced scene card B"])
        due = b.event("due")                                                                  # no "due" scene: rotation_due lines
        self.assertEqual(len(due), 2); self.assertTrue(set(due) <= self.lines("rotation_due", ["nova", "iggy"]))
        self.assertTrue(set(b.due_nag()) <= self.lines("rotation_due", ["nova", "iggy"]))
        self.home(["duskie", "nova"])                                                         # no scenes for this pair's events
        self.assertTrue(set(b.event("rotated")) <= self.lines("rotated", ["nova", "duskie"]))
        self.assertTrue(set(b.event("synced", card="B")) <= self.lines("synced", ["nova", "duskie"], card="B"))
        self.assertEqual(len(b.event("synced", card="B")), 2)
        self.assertEqual((b.event("bogus"), b.event(None), b.event(5), b.event("night")), ([], [], [], []))
        self.assertEqual(b.event("synced", who="x", when="y", card="1"), [])                  # clashing keywords: contained
        self.home(["iggy", "nova"])
        self.assertEqual(b.event("synced"), ["Nova: synced line 1 from nova {card}"][:0] or b.event("synced"))   # never raises
        self.assertEqual(len(b.event("synced")), 2)

    def test_scene_follows_the_clock_and_never_repeats_back_to_back(self):
        self.home(["iggy", "nova"])
        night = Counter(l for s in range(60) for l in self.brain(s, NIGHT).scene())
        self.assertTrue(night["Nova: night scene"]); self.assertTrue(night["Nova: any scene 1 for iggy+nova"])   # about half and half
        day = Counter(l for s in range(60) for l in self.brain(s, NOON).scene())
        self.assertFalse(day["Nova: night scene"])
        self.assertEqual(self.brain().scene("night"), ["Nova: night scene"])
        b = self.brain()
        firsts = [b.scene("any")[0] for _ in range(20)]
        self.assertTrue(all(a != c for a, c in zip(firsts, firsts[1:])), firsts)              # two scenes: they alternate
        self.assertEqual(b.scene("game:pikmin-2", game="Pikmin 2"), ["Nova: scene about Pikmin 2"])
        self.put(cast.SCENES_PATH, {"scenes": []})
        self.assertTrue(set(b.scene()) <= self.lines("idle", ["nova", "iggy"]))               # no scenes at all: idle lines

    def test_presence_lines(self):
        b = self.brain()
        self.home(["iggy", "nova"])
        self.assertEqual(b.presence_lines(cast.gather(self.state, REGULARS, now=NOON)), ["Duskie: arrive scene"])
        self.assertEqual(b.presence_lines(cast.gather(self.state, ["iggy", "nova"], now=NOON)), ["Duskie: leave scene"])
        out = b.presence_lines(cast.gather(self.state, ["duskie", "nova"], now=NOON))         # a swap: goodbye first, then hello
        self.assertEqual([l.split(":")[0] for l in out], ["Iggy", "Duskie"])
        self.assertIn(out[0], self.lines("leave", ["iggy"])); self.assertIn(out[1], self.lines("arrive", ["duskie"]))
        out = b.presence_lines(cast.gather(self.state, ["iggy"], now=NOON))
        self.assertEqual([l.split(":")[0] for l in out], ["Nova", "Duskie", "Iggy"])
        self.assertEqual(b.presence_lines(cast.gather(self.state, ["iggy", "nova"], now=NOON)), ["Nova: nova arrive scene"])
        self.assertEqual(b.presence_lines(cast.gather(self.state, ["iggy", "nova"], now=NOON)), [])   # nobody moved
        walk_on = {"who": ["biscuit", "iggy", "nova"], "arrived": ["biscuit"], "left": [], "changed": True}
        self.assertIn(b.presence_lines(walk_on)[0], self.lines("arrive", ["biscuit"]))
        del pets.PETS["arrive"]["biscuit"]
        self.assertEqual(b.presence_lines(walk_on), [])                                       # a cameo without a line slips in quietly
        for junk in (None, 5, [], {}, {"who": 5, "arrived": "nova", "left": {"a": 1}}, {"arrived": ["ghost"], "left": [None]}):
            self.assertEqual(b.presence_lines(junk), [])

    def test_card_quips_use_the_cast_and_nothing_else(self):
        self.home(["duskie"])                                                                 # who is home does not matter for a card
        q = self.brain().card_quips(["pikmin-2", "star-fox-adventures"], limit=100)
        self.assertEqual(q[:3], [f"{name_of(p)}: pikmin quip from {p}" for p in REGULARS])    # non-cameo characters only
        self.assertEqual(sum("joke from" in x for x in q), 5); self.assertEqual(sum("fortune from" in x for x in q), 5)
        jokes = [x for x in q if "joke from" in x]
        self.assertEqual({x.split(":")[0] for x in jokes[:3]}, {"Nova", "Iggy", "Duskie"})    # the main cast first, cameos fill up
        self.assertTrue(all("\n" not in x for x in q)); self.assertEqual(len(self.brain().card_quips(["pikmin-2"], limit=2)), 2)
        for junk in (None, 5, [["x"]], [{}], [None, 5]):
            self.assertIsInstance(self.brain().card_quips(junk), list)

    def test_activity_and_stats_follow_the_cast(self):
        b = self.brain()
        self.assertEqual(sorted(b.activities()), ["fetch", "nap"])
        self.assertIn(b.activity("duskie", "fetch"), self.lines("fetch", ["duskie"]) if False else
                      {f"Duskie: fetch line {n} from duskie" for n in (1, 2)})
        self.assertEqual(self.state["pets"]["duskie"], {"affection": 6, "energy": 3})
        b.activity("duskie", "fetch"); self.assertIn("sleepy", b.activity("duskie", "fetch"))
        self.assertEqual(b.mood("duskie"), "sleep"); self.assertEqual(b.mood("ghost"), "art")
        self.assertIn("don't know", b.activity("nova", "juggle")); self.assertIn("don't know", b.activity("nova", None))
        del pets.PETS["activities"]["nap"]["iggy"]
        self.assertEqual(b.activity("iggy", "nap"), "Iggy: That was nice.")                   # no line for this character yet
        self.assertEqual(b.art("nova"), "[nova]"); self.assertEqual(b.art("nova", "art_sleep"), "[novaz]")
        self.assertEqual(b.art("ghost"), "")


# --------------------------------------------------------------------------------------------------------------- chat
class ChatIntents(Fixture):
    def test_whos_home(self):
        b = self.brain()
        for text in ("who's home", "who is home?", "who is here", "whos home", "anyone home?", "who’s around", "roll call"):
            out = b.reply(text)
            self.assertRegex(out, r"^(Nova: It's me and Iggy|Iggy: It's me and Nova) right now\. Duskie is out\.$", text)
        self.assertEqual(b.reply("nova, who's home?"), "Nova: It's me and Iggy right now. Duskie is out.")
        self.home(["duskie"])
        self.assertEqual(b.reply("who is here"), "Duskie: Just me right now. Nova and Iggy are out.")
        self.home(REGULARS)
        self.assertEqual(b.reply("iggy who is home"), "Iggy: It's me, Nova and Duskie right now.")
        self.assertEqual(b.home_line(), "Home right now: Nova, Iggy and Duskie.")
        self.home(["iggy"]); self.assertEqual(b.home_line(), "Home right now: Iggy. Out: Nova and Duskie.")

    def test_invite(self):
        b = self.brain()
        for text in ("invite duskie", "call duskie over", "duskie come over", "bring the jackal over", "ask Duskie round"):
            self.home(["iggy", "nova"])
            self.assertEqual(b.reply(text), "Duskie: arrive scene", text)
            self.assertEqual(self.state["scene"]["who"], ["duskie", "iggy", "nova"])
            self.assertEqual((self.state["scene"]["manual"], self.state["scene"]["until"]), (True, NOON.timestamp() + 90 * 60))
        self.assertEqual(b.reply("invite duskie"), "Duskie: Already here.")
        self.home(["nova"])
        out = b.reply("invite iggy and duskie").split("\n")
        self.assertEqual([l.split(":")[0] for l in out], ["Iggy", "Duskie"]); self.assertEqual(b.home(), REGULARS)
        self.home(["iggy", "nova"])
        self.assertIn("Invite who? Nova, Iggy or Duskie.", b.reply("invite"))
        self.assertIn("Mochi drops by when Mochi feels like it", b.reply("invite mochi"))     # cameos cannot be summoned
        self.assertEqual(b.home(), ["nova", "iggy"])

    def test_send_out_keeps_a_main_at_home(self):
        b = self.brain()
        self.home(REGULARS)
        self.assertEqual(b.reply("send duskie out"), "Duskie: leave scene")
        self.assertEqual(b.home(), ["nova", "iggy"])
        self.assertIn(b.reply("send nova out"), {f"Nova: leave line {n} from nova" for n in (1, 2)})
        self.assertEqual(b.home(), ["iggy"])
        self.assertEqual(b.reply("send iggy out"), "Iggy: Somebody has to mind the GameCube. I'm staying put.")
        self.assertEqual(b.home(), ["iggy"])                                                  # the last main stays
        self.assertIn(b.reply("send nova out"), {f"Iggy: absent line {n} from iggy about Nova" for n in (1, 2)})   # already out
        self.home(["duskie", "nova"])
        self.assertTrue(b.reply("nova go out").startswith("Nova: Somebody has to mind")); self.assertEqual(b.home(), ["nova", "duskie"])
        self.home(REGULARS)
        self.assertTrue(b.reply("send nova and iggy out").startswith("Nova: Somebody has to mind")); self.assertEqual(b.home(), REGULARS)
        self.assertEqual([l.split(":")[0] for l in b.reply("iggy and duskie, go for a walk").split("\n")], ["Iggy", "Duskie"])
        self.assertEqual(b.home(), ["nova"])
        self.home(["duskie"])                                                                 # a hand-made guest-only group
        self.assertTrue(b.reply("send duskie out").startswith("Duskie: Somebody has to mind")); self.assertEqual(b.home(), ["duskie"])
        self.home(["biscuit", "iggy", "nova"])
        self.assertIn(b.reply("send biscuit out"), {f"Biscuit: leave line {n} from biscuit" for n in (1, 2)})
        self.assertEqual(b.home(), ["nova", "iggy"])
        self.assertTrue(set(b.reply("send it out").split("\n")) <= {f"{name_of(p)}: idle line {n} from {p}" for p in IDS for n in (1, 2)})

    def test_everyone(self):
        b = self.brain()
        for text in ("everyone", "Everybody!", "get everyone together", "invite everyone", "call them all over", "the whole gang"):
            self.home(["nova"])
            out = b.reply(text).split("\n")
            self.assertEqual([l.split(":")[0] for l in out], ["Iggy", "Duskie"], text); self.assertEqual(b.home(), REGULARS, text)
        self.assertRegex(b.reply("everyone"), r"^(Nova|Iggy|Duskie): Everyone's already here\.$")
        self.home(["iggy", "nova"])
        self.assertIn("idle line", b.reply("hello everyone"))                                 # a greeting, not a summons... (idle or greeting)
        self.assertEqual(b.home(), ["nova", "iggy"])
        self.assertIn("card 1", b.reply("where is pikmin 2, everyone?", self.roms)); self.assertEqual(b.home(), ["nova", "iggy"])

    def test_hang_out_plays_a_scene_for_the_present_set(self):
        b = self.brain()
        for group in GROUPS:
            self.home(group)
            key = "+".join(group)
            for text in ("hang out", "scene", "let's hang out", "play a scene", "banter"):
                out = b.reply(text).split("\n")
                self.assertRegex(out[0], rf"^{name_of(group[0])}: any scene [12] for {re.escape(key)}$", (group, text))
                self.assertEqual(out[1], "(a stage direction)")

    def test_named_character_answers_if_home_else_an_absent_line(self):
        b = self.brain()
        self.home(["iggy", "nova"])
        for _ in range(20):
            self.assertTrue(b.reply("nova, hello").startswith("Nova: greeting line"))
            self.assertTrue(b.reply("hey pup").startswith("Iggy: greeting line"))             # aliases pick the answerer too
            self.assertRegex(b.reply("duskie, hello"), r"^(Nova|Iggy): absent line [12] from (nova|iggy) about Duskie$")
            self.assertRegex(b.reply("duskie tell me a joke"), r"^(Nova|Iggy): absent line . from \w+ about Duskie$")
            self.assertRegex(b.reply("where is duskie?"), r"^(Nova|Iggy): absent line . from \w+ about Duskie$")
            self.assertRegex(b.reply("nova, where's duskie"), r"^Nova: absent line . from nova about Duskie$")
            self.assertRegex(b.reply("biscuit play fetch"), r"^(Nova|Iggy): absent line . from \w+ about Biscuit$")   # v1 pets are cameos now
            self.assertRegex(b.reply("hi"), r"^(Nova|Iggy): greeting line")
        self.assertNotIn("biscuit", self.state["pets"])                                       # ...and no activity happened
        self.assertEqual(b.reply("where's nova?"), "Nova: Right here.")
        self.assertEqual(b.reply("nova and duskie, hello").split(":")[0], "Nova")             # someone named is home: they answer
        self.home(["duskie", "nova"])
        self.assertEqual(b.reply("duskie tell me a joke"), "Duskie: joke from duskie")
        self.assertRegex(b.reply("iggy?"), r"^(Nova|Duskie): absent line . from \w+ about Iggy$")
        for _ in range(30):                                                                   # a species word in a game title is not a summons
            self.assertRegex(b.reply("star fox adventures", self.roms), r"^(Nova|Duskie): Ooh, Star Fox Adventures\.$")
            self.assertRegex(b.reply("where is star fox adventures", self.roms), r"^(Nova|Duskie): Star Fox Adventures is resting")
            self.assertRegex(b.reply("fox joke"), r"^(Nova|Duskie): joke from")
        self.assertIn("several", b.reply("rate star 5", [self.roms[2], core.Rom("b.iso", 1, None, None, "star-b", "Star B", False)]))

    def test_who_answers_is_weighted_by_role(self):
        self.home(["duskie", "iggy", "mochi", "nova"])
        b = self.brain(seed=4)
        n = 6000
        who = Counter(b.reply("zzz").split(":")[0] for _ in range(n))
        self.assertEqual(set(who), {"Nova", "Iggy", "Duskie", "Mochi"})
        self.assertTrue(who["Nova"] > who["Duskie"] > who["Mochi"] and who["Iggy"] > who["Duskie"], who)   # 3 : 3 : 2 : 1
        self.assertTrue(0.29 < who["Nova"] / n < 0.38 and 0.18 < who["Duskie"] / n < 0.27 and 0.08 < who["Mochi"] / n < 0.15, who)

    def test_old_intents_still_work_with_the_cast(self):
        b = self.brain()
        self.assertIn("card 1", b.reply("where is pikmin 2?", self.roms))
        self.assertEqual(b.reply("iggy, pikmin 2", self.roms), "Iggy: pikmin quip from iggy")
        out = b.reply("rate pikmin 2 5 stars", self.roms).split("\n")
        self.assertEqual((self.state["ratings"], [l.split(":")[0] for l in out]), ({"pikmin-2": 5}, ["Nova", "Iggy"]))
        self.assertIn("Pikmin 2", b.reply("rank", self.roms)); self.assertIn("WRAPPED", b.reply("wrapped", self.roms))
        wrapped = b.reply("wrapped", self.roms).split("\n")[-3:]
        self.assertEqual([l.split(":")[0] for l in wrapped], ["Nova", "Iggy", "Duskie"])
        self.assertTrue(b.reply("iggy play fetch").startswith("Iggy: fetch line")); self.assertEqual(self.state["pets"]["iggy"]["energy"], 3)
        pick = b.reply("what should i play", self.roms).split("\n")
        self.assertTrue(pick[0].startswith("Tonight's pick:")); self.assertEqual([l.split(":")[0] for l in pick[1:]], ["Nova", "Iggy"])
        helped = b.reply("help")
        for word in ("fetch", "nap", "who's home", "invite", "hang out", "Nova, Iggy or Duskie"):
            self.assertIn(word, helped)
        self.assertRegex(b.reply("saves", self.roms, {}), r"^(Nova|Iggy): No saves")
        self.assertRegex(b.reply("i'm so tired"), r"^(Nova|Iggy): study_break line")
        self.assertEqual(b.reply("nova i'm so tired").split(":")[0], "Nova")

    def test_plugin_hooks_still_get_first_refusal(self):
        seen = []
        hooks = [(re.compile(r"\bboop\b"), lambda brain, m, ctx: seen.append(ctx) or brain._line(ctx["pet"], "Boop.")),
                 (re.compile(r"\bbang\b"), lambda brain, m, ctx: 1 / 0), (re.compile(r"\bnothing\b"), lambda brain, m, ctx: None)]
        keep = list(pets.CHAT_HOOKS)
        self.addCleanup(lambda: pets.CHAT_HOOKS.__setitem__(slice(None), keep))
        pets.CHAT_HOOKS[:] = hooks
        b = self.brain()
        self.assertEqual(b.reply("iggy boop"), "Iggy: Boop.")
        self.assertEqual({k: seen[0][k] for k in ("pet", "text", "roms", "saves")}, {"pet": "iggy", "text": "iggy boop", "roms": [], "saves": None})
        self.assertEqual((seen[0]["home"], seen[0]["named"]), (["nova", "iggy"], ["iggy"]))
        self.assertEqual(b.reply("invite duskie boop"), b.reply("boop").split(":")[0] + ": Boop.")   # hooks beat the new intents
        self.assertRegex(b.reply("bang"), r"^(Nova|Iggy): A plugin tripped over its own tail \(ZeroDivisionError")
        self.assertRegex(b.reply("nothing hi"), r"^(Nova|Iggy): greeting line")


# --------------------------------------------------------------------------------------------------------- robustness
class Robustness(Fixture):
    TEXTS = ["hi", "hello nova", "joke", "fortune", "fetch", "nap", "zzz", "suggest", "rank", "wrapped", "saves", "help", "pikmin 2",
             "where is pikmin 2", "rate pikmin 2 4 stars", "who's home", "invite duskie", "send duskie out", "send nova out", "everyone",
             "hang out", "scene", "duskie hello", "mochi", "after dark", "study break", ""]

    def drive(self, state=None):
        state = {} if state is None else state
        b = pets.PetBrain(state, self.cat, random.Random(9), clock=lambda: NIGHT)
        for text in self.TEXTS:
            self.assertTrue(b.reply(text, self.roms, {}), text)
        for when in WHENS + ["bogus", None]:
            self.assertIsInstance(b.event(when, card="1"), list); self.assertTrue(b.scene(when, card="1"))
        self.assertIsInstance(b.card_quips(["pikmin-2", "chibi-robo"]), list)
        for p in cast.ids() + ["ghost"]:
            for bucket in BUCKETS:
                self.assertTrue(b.say(p, bucket, card="1", game="G", name="N"))
            self.assertTrue(b.joke(p)); self.assertTrue(b.fortune(p)); self.assertTrue(b.activity(p, "fetch"))
            b.art(p); b.mood(p); b.game_quip(p, "pikmin-2")
        self.assertTrue(b.collection([])); self.assertTrue(b.collection(self.roms)); self.assertTrue(b.home_line())
        self.assertTrue(cast.step(state, NIGHT, random.Random(1))["who"])
        self.assertIsInstance(b.presence_lines(cast.shuffle(state, NIGHT, random.Random(2))), list)
        return b

    def test_no_shape_of_pets_content_can_crash(self):
        shapes = [{}, {"characters": 5, "greeting": 7, "idle": [], "jokes": {}, "fortunes": 3, "activities": [], "game_quips": 1,
                       "tag_quips": "x", "state_of_collection": [], "absent": None, "arrive": "x", "leave": 0, "title": 5},
                  {"characters": {"nova": 5, "iggy": {"name": 7, "art": "x", "art_happy": [1]}}, "greeting": {"nova": 5, "iggy": [None, 3]},
                   "idle": {"nova": ["{", "}", "{0}", "{x.y}", "{game[", "{name!z}", "{:>9999999999}"], "iggy": {"a": 1}},
                   "absent": {"nova": ["{nope}"], "iggy": ["{name.__class__}"]}, "jokes": [["Nova"], ["Nova", 5], [5, "x"], "x", None, ["Nova", "ok", "extra"]],
                   "fortunes": [[["Nova"], "x"]], "activities": {"fetch": {"needs": "energy", "affection": "lots", "energy": None, "nova": "x"},
                                                                 "nap": 5, 7: {}, "bad(": {"nova": ["x"]}},
                   "game_quips": {"pikmin-2": {"nova": 5, "iggy": [5, None], "duskie": {"a": 1}}, "chibi-robo": "x"},
                   "tag_quips": {"cozy": ["x"]}, "state_of_collection": {"empty": 5, "few": [5], "many": "x"}},
                  {"synced": {"nova": ["{card.x} {game} {days} {pet}"]}, "ranked": {"iggy": ["{}"]}, "rotated": {"nova": [""]},
                   "activities": {"fetch": {"verb": 5, "needs": ["energy"], "affection": True, "energy": float("nan")}}}]
        for shape in shapes:
            pets.PETS.clear(); pets.PETS.update(shape)
            for state in ({}, {"pets": {"nova": {"affection": "x", "energy": None}, "iggy": 5}, "ratings": {"pikmin-2": "five"},
                               "history": [5, {"plan": 5}, {"plan": {"1": 5}}], "last_on_card": {"pikmin-2": "x"}}):
                self.drive(state)

    def test_no_shape_of_cast_scenes_or_state_can_crash(self):
        casts = [None, "{", [], {"characters": 5}, {"characters": {"a": {"role": "main"}}},                    # one main, nothing else
                 {"characters": {"a": {"role": "main", "aliases": ["hi", "joke", "(", "a.b", "everyone"]},      # hostile aliases
                                 "b": {"role": "cameo", "name": "B: the\nsecond"}}, "presence": {"groups": {"cameo": 1}}},
                 {"characters": {str(i): {"role": r} for i, r in enumerate(["main", "guest", "cameo", "main", "guest", "nope"])},
                  "presence": {"groups": {"0+1+3+4": 1, "cameo": 1e308, "3": 1e-300}, "min_minutes": 1e-9, "max_minutes": 1e12}}]
        scenes = [None, "{", {"scenes": [{"who": ["a"], "lines": [["a", "{x} {"], ["*", "{}"]]},
                                         {"who": ["0", "3"], "when": "rotated", "weight": 1e308, "lines": [["0", "x"]]},
                                         {"who": ["a", "b"], "when": "arrive", "about": "b", "lines": [["b", "{card}"]]}]}]
        states = [{}, {"scene": {"who": ["a", "b", "0", "3", 5], "until": 1e18, "manual": True}, "afterdark": {"unlocked": True},
                       "pets": [], "ratings": 5, "history": "x", "last_on_card": None}]
        for c in casts:
            for s in scenes:
                for obj, path in ((c, cast.CAST_PATH), (s, cast.SCENES_PATH)):
                    if obj is None and path.exists():
                        path.unlink()
                    elif obj is not None:
                        path.write_text(obj if isinstance(obj, str) else json.dumps(obj), encoding="utf-8")
                cast.reload()
                self.assertTrue(cast.mains())
                for state in states:
                    b = self.drive(json.loads(json.dumps(state)))
                    self.assertTrue(set(b.home()) & set(cast.regulars()))

    def test_everything_missing_falls_back_to_the_builtin_pair_with_stock_lines(self):
        for p in (cast.CAST_PATH, cast.SCENES_PATH):
            p.unlink()
        cast.reload(); pets.PETS.clear()
        b = self.drive()
        self.home(["iggy", "nova"], b.state)
        self.assertEqual(cast.ids(), ["nova", "iggy"])
        self.assertEqual(b.duo("greeting"), ["Nova: Hi. Good to see you.", "Iggy: Hi. Good to see you."])
        self.assertEqual(b.event("synced", card="2"), ["Nova: Card 2 is ready.", "Iggy: Card 2 is ready."])
        self.assertEqual(b.say("nova", "absent", name="Iggy"), "Nova: Iggy is out right now.")
        self.assertEqual(b.say("nova", "no-such-bucket"), "Nova: ...")
        self.assertEqual(b.reply("hang out").split("\n"), ["Nova: Just keeping the GameCube company.", "Iggy: Just keeping the GameCube company."])
        self.assertRegex(b.reply("joke"), r"^(Nova|Iggy): I had a joke")
        self.assertEqual(b.card_quips(["pikmin-2"]), [])


# ---------------------------------------------------------------------------------------------------------------- CLI
class CastCli(unittest.TestCase):
    """End to end through `python -m pawtation`, against the shipped data files, with PAWTATION_HOME in a temp dir."""

    def setUp(self):
        self.home = Path(tempfile.mkdtemp())
        self.names = {c["name"] for c in json.loads((ROOT / "data" / "cast.json").read_text(encoding="utf-8"))["characters"].values()}

    def run_cli(self, *args, stdin=None):
        env = dict(os.environ, PAWTATION_HOME=str(self.home), PYTHONPATH=str(ROOT))
        r = subprocess.run([sys.executable, "-m", "pawtation", *args], cwd=str(ROOT), env=env, input=stdin,
                           capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr

    def state(self):
        return json.loads((self.home / "state.json").read_text(encoding="utf-8"))

    def spoken(self, out):
        """Lines of the form "Name: text" or "(stage direction)"."""
        return [l for l in out.splitlines() if l.split(":")[0] in self.names or (l.startswith("(") and l.endswith(")"))]

    def test_cast_command(self):
        code, out = self.run_cli("cast"); self.assertEqual(code, 0, out)
        self.assertIn("Home right now:", out); self.assertNotIn("Traceback", out)
        for name in self.names:
            self.assertIn(name, out)                                                          # the roster lists everyone
        first = self.state()["scene"]
        self.assertTrue(first["who"]); self.assertFalse(first["manual"])
        code, out = self.run_cli("cast"); self.assertEqual(code, 0, out)
        self.assertEqual(self.state()["scene"], first)                                        # still inside the stay: nobody moved
        code, out = self.run_cli("cast", "--gather", "nova", "duskie"); self.assertEqual(code, 0, out)
        self.assertEqual((self.state()["scene"]["who"], self.state()["scene"]["manual"]), (["duskie", "nova"], True))
        self.assertIn("Home right now: Nova and Duskie. Out: Iggy.", out); self.assertIn("meetup", out)
        code, out = self.run_cli("cast", "--gather", "Iggy", "--minutes", "5"); self.assertEqual(code, 0, out)
        sc = self.state()["scene"]
        self.assertEqual(sc["who"], ["iggy"]); self.assertTrue(0 < sc["until"] - datetime.datetime.now().timestamp() <= 300)
        code, out = self.run_cli("cast", "--gather", "nobody", "mochi"); self.assertEqual(code, 1, out)
        self.assertIn("Nobody to gather", out); self.assertEqual(self.state()["scene"]["who"], ["iggy"])
        code, out = self.run_cli("cast", "--everyone"); self.assertEqual(code, 0, out)
        self.assertEqual(self.state()["scene"]["who"], ["duskie", "iggy", "nova"])
        self.assertTrue(self.spoken(out), out)                                                # somebody said hello on the way in
        code, out = self.run_cli("cast", "--random"); self.assertEqual(code, 0, out)
        sc = self.state()["scene"]
        self.assertFalse(sc["manual"]); self.assertTrue({"nova", "iggy"} & set(sc["who"]))
        code, out = self.run_cli("cast", "--random", "--everyone"); self.assertEqual(code, 2)   # argparse: pick one
        self.assertNotIn("Traceback", out)

    def test_scene_command(self):
        for group in (["nova"], ["nova", "iggy"], ["nova", "iggy", "duskie"], ["duskie"]):
            self.assertEqual(self.run_cli("cast", "--gather", *group)[0], 0)
            code, out = self.run_cli("scene"); self.assertEqual(code, 0, out)
            self.assertNotIn("Traceback", out); self.assertIn("Home right now:", out)
            lines = self.spoken(out)
            self.assertTrue(lines, out)
            speakers = {l.split(":")[0].lower() for l in lines if not l.startswith("(")}
            self.assertTrue(speakers <= set(group), (group, out))                             # only who is home speaks
        for when in ("rotated", "night", "due", "nonsense"):
            code, out = self.run_cli("scene", "--when", when); self.assertEqual(code, 0, out)
            self.assertTrue(self.spoken(out), out); self.assertNotIn("Traceback", out)

    def test_chat_session(self):
        script = ("who is home\ninvite duskie\nhang out\nduskie tell me a joke\nsend duskie out\neveryone\nscene\n"
                  "send nova out\nsend iggy out\nafter dark\nhelp\n\nquit\n")
        self.assertEqual(self.run_cli("cast", "--gather", "nova", "iggy")[0], 0)
        code, out = self.run_cli("chat", stdin=script); self.assertEqual(code, 0, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("Home right now: Nova and Iggy. Out: Duskie.", out)
        self.assertIn("Duskie:", out)                                                         # he came over and spoke
        self.assertIn("staying put", out)                                                     # the last main refused to leave
        self.assertIn("python -m pawtation afterdark", out)
        st = self.state()
        self.assertEqual(st["scene"]["who"], ["iggy"]); self.assertTrue(st["scene"]["manual"])
        self.assertEqual(st["afterdark"], {"unlocked": False})
        self.assertEqual(sorted(st["pets"]), ["duskie", "iggy", "nova"])
        (self.home / "state.json").write_text(json.dumps({"scene": {"who": ["duskie"], "until": 12, "manual": True}, "pets": 5}))
        code, out = self.run_cli("chat", stdin="hello\nwho's home\n"); self.assertEqual(code, 0, out)   # an expired meetup + EOF
        self.assertNotIn("Traceback", out); self.assertFalse(self.state()["scene"]["manual"])

    def test_events_from_other_commands_survive_any_presence(self):
        (self.home / "state.json").write_text("{broken")
        for cmd in (["status"], ["cast"], ["scene"], ["wrapped"], ["saves"]):
            code, out = self.run_cli(*cmd)
            self.assertEqual(code, 0, f"{cmd}: {out}"); self.assertNotIn("Traceback", out)


if __name__ == "__main__":
    unittest.main()
