import json
import re
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "data" / "catalog.json"
IMPORT = ROOT / "scripts" / "import_ids.py"

ALLOWED_TAGS = {"furry", "furry-adjacent", "cats-and-dogs", "cat-adjacent", "cozy", "cute", "racing", "party",
                "horror", "spooky", "rpg", "sports", "fighting", "platformer", "adventure", "action", "scifi",
                "co-op", "weird", "arcade", "fox", "dragon", "bongos", "top5", "link-guest"}

ORIGINAL_KEYS = """paper-mario-ttyd soulcalibur-ii mario-kart-double-dash chibi-robo super-smash-bros-melee wind-waker
f-zero-gx pikmin pikmin-2 animal-crossing super-mario-sunshine pokemon-colosseum pokemon-xd metroid-prime
metroid-prime-2 kirby-air-ride luigis-mansion star-fox-adventures star-fox-assault sonic-adventure-2-battle
sonic-heroes sonic-adventure-dx sonic-mega-collection sonic-riders donkey-kong-jungle-beat donkey-konga
super-monkey-ball super-monkey-ball-2 mario-party-4 mario-party-5 mario-party-6 mario-party-7
mario-golf-toadstool-tour mario-power-tennis mario-superstar-baseball super-mario-strikers
fire-emblem-path-of-radiance zelda-four-swords-adventures zelda-collectors-edition resident-evil-4 resident-evil
resident-evil-zero eternal-darkness viewtiful-joe viewtiful-joe-2 killer7 tales-of-symphonia
skies-of-arcadia-legends baten-kaitos baten-kaitos-origins phantasy-star-online-1-2 pac-man-world-2
billy-hatcher beyond-good-and-evil prince-of-persia-sands-of-time tak-and-the-power-of-juju spyro-a-heros-tail
crash-nitro-kart crash-wrath-of-cortex ty-the-tasmanian-tiger ty-2-bush-rescue rayman-3
harvest-moon-a-wonderful-life harvest-moon-magical-melody wario-world warioware-mega-party-games
pokemon-channel tony-hawks-underground burnout-2 ssx-3 rogue-squadron-ii rogue-squadron-iii lego-star-wars
ikaruga timesplitters-2 def-jam-fight-for-ny custom-robo cubivore odama""".split()


def norm(s):
    s = s.lower().replace("&", "and")
    s = re.sub(r"\[.*?\]|\(.*?\)", " ", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def load(path=CATALOG):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def collisions(games):
    """Informational: (A, B) where norm(A) is a strict substring of norm(B), len(norm(A)) >= 8
    (the length at which Catalog.match's containment fallback kicks in)."""
    names = [(g["title"], norm(g["title"])) for g in games]
    out = []
    for ta, na in names:
        if len(na) < 8:
            continue
        for tb, nb in names:
            if na != nb and na in nb:
                out.append((ta, tb))
    return out


class CatalogData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = load()
        cls.games = cls.cat["games"]

    def test_shape(self):
        self.assertEqual(len(ORIGINAL_KEYS), 79)
        for g in self.games:
            self.assertTrue(g.get("key"), g)
            self.assertTrue(g.get("title"), g)
            self.assertIsInstance(g.get("year", 0), int)

    def test_keys_unique(self):
        keys = [g["key"] for g in self.games]
        self.assertEqual(len(keys), len(set(keys)))

    def test_code4(self):
        codes = [g["code4"] for g in self.games if g.get("code4")]
        self.assertEqual(len(codes), len(set(codes)))
        for c in codes:
            self.assertRegex(c, r"^[A-Z0-9]{4}$")
            self.assertEqual(len(c), 4)

    def test_original_keys_present(self):
        have = {g["key"] for g in self.games}
        for k in ORIGINAL_KEYS:
            self.assertIn(k, have)
        for k in ("paper-mario-ttyd", "animal-crossing", "soulcalibur-ii", "mario-kart-double-dash", "chibi-robo"):
            self.assertIn(k, have)

    def test_not_gamecube(self):
        self.assertNotIn("katamari-damacy", {g["key"] for g in self.games})

    def test_size(self):
        self.assertGreaterEqual(len(self.games), 300)

    def test_tags_in_vocabulary(self):
        for g in self.games:
            for t in g.get("tags", []):
                self.assertIn(t, ALLOWED_TAGS, g["key"])

    def test_norm_titles_unique(self):
        seen = {}
        for g in self.games:
            n = norm(g["title"])
            self.assertNotIn(n, seen, f"{g['key']} duplicates {seen.get(n)}")
            seen[n] = g["key"]

    def test_lookalike_titles_resolve_to_the_right_game(self):
        """Titles that contain another title ('Viewtiful Joe 2' vs 'Viewtiful Joe') must each match themselves,
        both as an exact file name and in dump-set style with a region tag."""
        from pawtation.core import Catalog
        cat = Catalog()
        pairs = collisions(self.games)
        self.assertGreater(len(pairs), 10)
        for a, b in pairs:
            for title in (a, b):
                want = cat.by_name[norm(title)]["key"]
                for fn in (f"{title}.iso", f"{title} (USA) (Rev 1).iso"):
                    got = cat.match(None, fn.replace(":", " -").replace("/", "-"))
                    self.assertEqual(got and got["key"], want, fn)


class ImportIds(unittest.TestCase):
    ID_FILE = (
        "GALE01 = Super Smash Bros. Melee\n"          # existing, already has code4 (same)
        "GLTE99 = Luigi's Mansion Totally Fake\n"     # unknown -> add
        "GRSE01 = Some Fake Game\n"                   # code4 owned by soulcalibur-ii -> conflict
        "RSPE01 = Wii Sports\n"                       # not GameCube-looking
        "GMPD01 = Not NTSC-U\n"                       # 4th char D -> ignored
        "not a line\n"
    )

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.cat = self.dir / "catalog.json"
        self.cat.write_text(json.dumps({"games": [
            {"key": "a", "title": "Alpha Game", "year": 2001, "developer": "", "genres": [], "tags": [], "aliases": []},
            {"key": "b", "title": "Beta Game", "year": 2002, "developer": "", "genres": [], "tags": [],
             "aliases": [], "code4": "GBBE"},
            {"key": "c", "title": "Gamma Game", "year": 2002, "developer": "", "genres": [], "tags": [],
             "aliases": [], "code4": "GCCE"},
        ]}), encoding="utf-8")
        self.ids = self.dir / "ids.txt"
        self.ids.write_text(
            "GAAE01 = Alpha Game\nGBXE01 = Beta Game\nGDDE01 = Delta Game\nGEEE01 = Epsilon Game\n"
            "GEFE02 = Epsilon Game\nRXXE01 = Wii Thing\nGZZP01 = PAL Thing\nGCCE01 = Other Game\n",
            encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-I", str(IMPORT), str(self.ids), "--catalog", str(self.cat), *args],
                              capture_output=True, text=True, check=True).stdout

    def test_dry_run_changes_nothing(self):
        before = self.cat.read_bytes()
        out = self.run_cli()
        self.assertEqual(before, self.cat.read_bytes())
        self.assertIn("dry-run", out)
        self.assertIn("set code4   a = GAAE", out)
        self.assertIn("CONFLICT", out)

    def test_apply(self):
        self.run_cli("--apply")
        games = {g["key"]: g for g in load(self.cat)["games"]}
        self.assertEqual(games["a"]["code4"], "GAAE")
        self.assertEqual(games["b"]["code4"], "GBBE")          # differing code4 never overwritten
        self.assertEqual(games["c"]["code4"], "GCCE")
        added = [g for g in games.values() if g["title"] == "Delta Game"]
        self.assertEqual(len(added), 1)
        self.assertEqual((added[0]["code4"], added[0]["year"], added[0]["tags"]), ("GDDE", 0, []))
        self.assertFalse([g for g in games.values() if g["title"] in ("Wii Thing", "PAL Thing", "Other Game")])
        self.assertFalse([g for g in games.values() if g["title"] == "Epsilon Game"])   # same title, two codes
        self.assertEqual(len(games), 4)


if __name__ == "__main__":
    unittest.main()
