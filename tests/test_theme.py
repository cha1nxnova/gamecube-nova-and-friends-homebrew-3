"""Design tokens (docs/SPEC_V2.md section 6, docs/DESIGN_SYSTEM.md): both themes are complete, every
text/background pair the GUI uses meets WCAG AA, a missing or broken theme.json falls back to the
built-in copy, and the colour / font helpers behave.  No tkinter, no display, no network."""
import ast
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from pawtation import theme

# Written out here on purpose (not imported from theme.py): loosening the module must not loosen the test.
SPEC_ROLES = [
    "bg", "surface", "surface_alt", "stage", "ink", "ink_muted", "line", "primary", "primary_ink",
    "primary_soft", "accent", "accent_ink", "accent_soft", "success", "warning", "danger", "focus",
    "selection", "selection_ink", "nova", "iggy", "duskie",
]
TEXT = 4.5      # WCAG AA, body text
UI = 3.0        # WCAG AA, large text, control boundaries, focus rings, graphics

TEXT_PAIRS = [
    ("ink", "bg"), ("ink", "surface"), ("ink", "surface_alt"), ("ink", "stage"),
    ("ink_muted", "bg"), ("ink_muted", "surface"),
    ("primary_ink", "primary"), ("accent_ink", "accent"), ("selection_ink", "selection"),
]
UI_PAIRS = [(fg, bg) for fg in ("primary", "accent", "focus", "line") for bg in ("bg", "surface")]
# How status colours are used (DESIGN_SYSTEM.md "Status"): as text on the window, on a card and on
# their own soft fill; body text on a soft fill is plain ink; the danger button carries danger_ink.
STATUS_PAIRS = [
    ("success", "bg"), ("success", "surface"), ("success", "success_soft"),
    ("warning", "bg"), ("warning", "surface"), ("warning", "warning_soft"),
    ("danger", "bg"), ("danger", "surface"), ("danger", "danger_soft"),
    ("ink", "success_soft"), ("ink", "warning_soft"), ("ink", "danger_soft"), ("ink", "accent_soft"),
    ("accent_text", "accent_soft"), ("danger_ink", "danger"),
]
BUILT_IN = ("light", "dark")


def shipped():
    with open(theme.THEME_PATH, encoding="utf-8") as handle:
        return json.load(handle)


class TempThemeFile(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory(prefix="pawtation-theme-")
        self.addCleanup(self._dir.cleanup)
        self.path = Path(self._dir.name) / "theme.json"

    def write(self, data):
        if isinstance(data, (bytes, bytearray)):
            self.path.write_bytes(data)
        elif isinstance(data, str):
            self.path.write_text(data, encoding="utf-8")
        else:
            self.path.write_text(json.dumps(data), encoding="utf-8")
        return self.path


class ShippedFile(unittest.TestCase):
    def test_spec_roles_are_all_declared(self):
        for role in SPEC_ROLES:
            self.assertIn(role, theme.SPEC_ROLES)
            self.assertIn(role, theme.ROLES)
        self.assertEqual(len(theme.ROLES), len(set(theme.ROLES)), "duplicate role names")

    def test_file_has_the_contract_shape(self):
        doc = shipped()
        self.assertEqual(doc["version"], 1)
        self.assertEqual(doc["default"], "light")
        for key in ("themes", "type", "space", "radius", "motion"):
            self.assertIn(key, doc)
        self.assertIsInstance(doc["space"], list)
        self.assertEqual(set(BUILT_IN), set(doc["themes"]))

    def test_both_themes_define_every_role_as_rrggbb(self):
        doc = shipped()
        for name in BUILT_IN:
            colors = doc["themes"][name]
            for role in list(SPEC_ROLES) + list(theme.ROLES):
                self.assertIn(role, colors, "%s is missing %s" % (name, role))
            for role, value in colors.items():
                self.assertRegex(value, r"^#[0-9a-f]{6}$", "%s.%s" % (name, role))
        self.assertEqual(set(doc["themes"]["light"]), set(doc["themes"]["dark"]),
                         "light and dark must define the same roles")

    def test_file_and_built_in_copy_are_identical(self):
        self.assertEqual(shipped(), theme.FALLBACK,
                         "data/theme.json and theme.FALLBACK drifted apart: "
                         "python3 -m pawtation.theme --dump > data/theme.json")

    def test_file_loads_without_repairs_or_failures(self):
        self.assertEqual(theme.check(), [])
        problems = []
        theme.load_document(problems=problems)
        self.assertEqual(problems, [])

    def test_load_returns_every_role(self):
        for name in BUILT_IN:
            colors = theme.load(name)
            self.assertEqual(set(colors), set(shipped()["themes"][name]))
            self.assertEqual(colors, shipped()["themes"][name])
        self.assertEqual(theme.names()[0], "light")
        self.assertEqual(sorted(theme.names()), ["dark", "light"])
        self.assertEqual(theme.load(), theme.load("light"))
        self.assertEqual(theme.default_name(), "light")

    def test_no_personal_data_in_the_file(self):
        text = theme.THEME_PATH.read_text(encoding="utf-8")
        self.assertNotIn("@", text)


class Contrast(unittest.TestCase):
    def check_pairs(self, pairs, minimum):
        for name in BUILT_IN:
            colors = theme.load(name)
            for fg, bg in pairs:
                ratio = theme.contrast(colors[fg], colors[bg])
                self.assertGreaterEqual(
                    ratio, minimum, "%s: %s %s on %s %s is %.2f:1, needs %.1f:1"
                    % (name, fg, colors[fg], bg, colors[bg], ratio, minimum))

    def test_text_pairs_meet_aa(self):
        self.check_pairs(TEXT_PAIRS, TEXT)

    def test_fills_borders_and_focus_meet_3_to_1(self):
        self.check_pairs(UI_PAIRS, UI)

    def test_status_colours_on_their_documented_backgrounds(self):
        self.check_pairs(STATUS_PAIRS, TEXT)

    def test_character_name_tags(self):
        self.check_pairs([("nova_ink", "nova"), ("iggy_ink", "iggy"), ("duskie_ink", "duskie"),
                          ("cameo_ink", "cameo")], TEXT)

    def test_bright_fill_states_keep_their_label_readable(self):
        self.check_pairs([("primary_ink", "primary_hover"), ("primary_ink", "primary_active"),
                          ("accent_ink", "accent_hover"), ("accent_ink", "accent_active"),
                          ("danger_ink", "danger_hover"), ("danger_ink", "danger_active"),
                          ("header_ink", "header"), ("header_ink", "keyline"), ("gold_ink", "gold")], TEXT)

    def test_coloured_text_roles(self):
        self.check_pairs([(fg, bg) for fg in ("primary_text", "accent_text", "gold_text")
                          for bg in ("bg", "surface", "surface_alt")], TEXT)

    def test_every_documented_pair_passes(self):
        for name in BUILT_IN:
            for fg, bg, ratio, minimum, ok, use in theme.audit(theme.load(name)):
                self.assertTrue(ok, "%s: %s on %s is %.2f:1, needs %.1f:1 (%s)" % (name, fg, bg, ratio, minimum, use))

    def test_documented_pairs_cover_the_required_ones(self):
        documented = {}
        for fg, bg, minimum, _use in theme.PAIRS:
            documented[(fg, bg)] = max(minimum, documented.get((fg, bg), 0))
            self.assertIn(fg, theme.ROLES)
            self.assertIn(bg, theme.ROLES)
            self.assertIn(minimum, (TEXT, UI))
        for pair in TEXT_PAIRS + STATUS_PAIRS:
            self.assertGreaterEqual(documented.get(pair, 0), TEXT, pair)
        for pair in UI_PAIRS:
            self.assertGreaterEqual(documented.get(pair, 0), UI, pair)

    def test_muted_and_disabled_text_are_not_the_same_thing(self):
        # disabled text is exempt from AA but must still be visible, and clearly quieter than muted text
        for name in BUILT_IN:
            c = theme.load(name)
            self.assertGreaterEqual(theme.contrast(c["disabled_ink"], c["disabled"]), 2.0)
            self.assertLess(theme.contrast(c["disabled_ink"], c["bg"]), theme.contrast(c["ink_muted"], c["bg"]))


class Brand(unittest.TestCase):
    """The owner's direction: pink-forward, starlight-blue accent, gold highlights, navy ink."""

    @staticmethod
    def hue(color):
        r, g, b = (v / 255.0 for v in theme.rgb(color))
        hi, lo = max(r, g, b), min(r, g, b)
        if hi == lo:
            return 0.0
        if hi == r:
            h = ((g - b) / (hi - lo)) % 6
        elif hi == g:
            h = (b - r) / (hi - lo) + 2
        else:
            h = (r - g) / (hi - lo) + 4
        return h * 60.0

    def test_pink_drives_the_chrome_in_both_themes(self):
        for name in BUILT_IN:
            c = theme.load(name)
            for role in ("primary", "header", "selection", "focus", "line", "primary_hover", "primary_active"):
                self.assertTrue(295 <= self.hue(c[role]) <= 345, "%s.%s %s is not pink" % (name, role, c[role]))
            self.assertTrue(200 <= self.hue(c["accent"]) <= 225, "%s accent is not starlight blue" % name)
            self.assertTrue(35 <= self.hue(c["gold"]) <= 50, "%s gold is not gold" % name)

    def test_ink_is_navy_never_pure_black(self):
        for name in BUILT_IN:
            c = theme.load(name)
            for role in ("ink", "primary_ink", "accent_ink", "selection_ink", "header_ink"):
                self.assertNotEqual(c[role], "#000000")
        self.assertEqual(theme.load("light")["ink"], "#1b1c30")
        self.assertLess(theme.luminance(theme.load("dark")["bg"]), 0.03)
        self.assertGreater(theme.luminance(theme.load("light")["bg"]), 0.85)

    def test_themes_share_the_brand_inks(self):
        light, dark = theme.load("light"), theme.load("dark")
        for role in ("primary_ink", "accent_ink", "selection_ink", "header_ink", "gold_ink"):
            self.assertEqual(light[role], dark[role], role)


class Helpers(unittest.TestCase):
    def test_contrast_known_values(self):
        self.assertAlmostEqual(theme.contrast("#000", "#fff"), 21.0, places=6)
        self.assertAlmostEqual(theme.contrast("#000000", "#ffffff"), 21.0, places=6)
        self.assertAlmostEqual(theme.contrast("#777", "#fff"), 4.48, delta=0.01)
        self.assertAlmostEqual(theme.contrast("#777777", "#FFFFFF"), 4.48, delta=0.01)
        self.assertAlmostEqual(theme.contrast("#767676", "#ffffff"), 4.54, delta=0.01)
        self.assertAlmostEqual(theme.contrast("#ff0000", "#ffffff"), 4.0, delta=0.01)

    def test_contrast_is_symmetric_and_one_for_equal_colours(self):
        self.assertEqual(theme.contrast("#ff4fa3", "#1b1c30"), theme.contrast("#1b1c30", "#ff4fa3"))
        self.assertAlmostEqual(theme.contrast("#ff4fa3", "#FF4FA3"), 1.0)

    def test_luminance_endpoints(self):
        self.assertAlmostEqual(theme.luminance("#000000"), 0.0)
        self.assertAlmostEqual(theme.luminance("#ffffff"), 1.0)

    def test_bad_colours_raise_value_error(self):
        for bad in ("pink", "#12345", "#gggggg", "", "1b1c30", None, 12, "#1b1c30ff"):
            with self.assertRaises(ValueError, msg=repr(bad)):
                theme.rgb(bad)
            self.assertFalse(theme.is_hex(bad))
        self.assertTrue(theme.is_hex("#1B1c30"))
        self.assertFalse(theme.is_hex("#fff"), "theme files must use the six-digit form")

    def test_mix(self):
        self.assertEqual(theme.mix("#000000", "#ffffff", 0), "#000000")
        self.assertEqual(theme.mix("#000000", "#ffffff", 1), "#ffffff")
        self.assertEqual(theme.mix("#000000", "#ffffff", 0.5), "#808080")
        self.assertEqual(theme.mix("#ff4fa3", "#ff4fa3", 0.3), "#ff4fa3")
        self.assertEqual(theme.mix("#000", "#FFF", 2), "#ffffff", "t is clamped")
        self.assertEqual(theme.mix("#000", "#fff", -1), "#000000", "t is clamped")
        self.assertEqual(theme.mix("#102030", "#304050", 0.25), "#182838")
        self.assertRegex(theme.mix("#ff4fa3", "#17122b", 0.37), r"^#[0-9a-f]{6}$")
        with self.assertRaises(ValueError):
            theme.mix("nope", "#ffffff", 0.5)

    def test_readable_picks_the_best_ink(self):
        self.assertEqual(theme.readable("#ffffff", ["#ffffff", "#1b1c30"]), "#1b1c30")
        self.assertEqual(theme.readable("#17122b", ["#1b1c30", "#f1eff8"]), "#f1eff8")
        with self.assertRaises(ValueError):
            theme.readable("#ffffff", ["nope"])

    def test_pick_font(self):
        installed = ["Arial", "DejaVu Sans", "nunito", "@MS Gothic", "Trebuchet MS"]
        self.assertEqual(theme.pick_font(["Fredoka", "Nunito", "Arial"], installed), "nunito")
        self.assertEqual(theme.pick_font(["Fredoka", "TREBUCHET  ms"], installed), "Trebuchet MS")
        self.assertEqual(theme.pick_font(["Fredoka", "Baloo 2"], installed), "")
        self.assertEqual(theme.pick_font(["Fredoka"], installed, default="TkDefaultFont"), "TkDefaultFont")
        self.assertEqual(theme.pick_font(["MS Gothic"], installed), "", "@vertical families never match")
        self.assertEqual(theme.pick_font(["Arial"], None), "")
        self.assertEqual(theme.pick_font(["Arial"], []), "")
        self.assertEqual(theme.pick_font(iter(["Zzz", "Arial"]), iter(installed)), "Arial")
        self.assertEqual(theme.pick_font([], installed), "")

    def test_fonts_picks_one_family_per_role(self):
        got = theme.fonts(["Verdana", "Consolas", "Arial"])
        self.assertEqual(got, {"display": "Verdana", "body": "Verdana", "mono": "Consolas"})
        self.assertEqual(theme.fonts(None), {"display": "", "body": "", "mono": ""})

    def test_tk_size_is_negative_pixels(self):
        self.assertEqual(theme.tk_size(14), -14)
        self.assertEqual(theme.tk_size(14, 1.5), -21)
        self.assertEqual(theme.tk_size(14, 0), -14)
        self.assertEqual(theme.tk_size(0.2), -1)

    def test_character_colors(self):
        for name in BUILT_IN:
            c = theme.load(name)
            self.assertEqual(theme.character_colors(c, "nova"), (c["nova"], c["nova_ink"]))
            self.assertEqual(theme.character_colors(c, "mochi"), (c["cameo"], c["cameo_ink"]))
            self.assertEqual(theme.character_colors(c, "mochi", {"name": "Mochi"}), (c["cameo"], c["cameo_ink"]))
            # a new character gets its cast.json colour, nudged until a brand ink reads on it
            for cast_color in ("#79bff0", "#808080", "#ff0000", "#2b2d42", "#ffd37c", "#7582b5", "#00a060"):
                fill, ink = theme.character_colors(c, "newcomer", {"color": cast_color})
                self.assertGreaterEqual(theme.contrast(ink, fill), TEXT, "%s %s" % (name, cast_color))
                self.assertIn(ink, (c["primary_ink"], c["keyline"]))
            fill, _ink = theme.character_colors(c, "newcomer", {"color": "#FFD37C"})
            self.assertEqual(fill, "#ffd37c", "a colour that already works is kept as it is")
            self.assertEqual(theme.character_colors(c, "newcomer", {"color": "gold"}), (c["cameo"], c["cameo_ink"]))

    def test_stage_sprite_size(self):
        self.assertEqual(theme.stage_sprite_size(448, 1), 192)
        self.assertEqual(theme.stage_sprite_size(448, 2), 192)
        self.assertEqual(theme.stage_sprite_size(448, 3), 96)
        self.assertEqual(theme.stage_sprite_size(600, 3), 192)
        self.assertEqual(theme.stage_sprite_size(200, 1), 96)
        self.assertEqual(theme.stage_sprite_size(448, 2, stage_height=200), 96)
        self.assertEqual(theme.stage_sprite_size(448, 2, stage_height=320), 192)
        self.assertEqual(theme.stage_sprite_size(448, 0), 192)

    def test_motion_and_the_reduced_motion_rule(self):
        normal, reduced = theme.motion(), theme.motion(reduced=True)
        self.assertNotIn("reduced", normal)
        self.assertFalse(normal["is_reduced"])
        self.assertTrue(reduced["is_reduced"])
        for key in ("fast", "base", "slow", "sparkle", "stripe", "sprite_fps_max"):
            self.assertGreater(normal[key], 0, key)
            self.assertEqual(reduced[key], 0, key)
        self.assertLessEqual(normal["slow"], 400, "nothing in the chrome animates for longer than 0.4 s")
        self.assertLess(normal["fast"], normal["base"])
        self.assertLess(normal["base"], normal["slow"])
        for key in ("bubble_hold", "toast_hold"):        # reading time is not motion
            self.assertEqual(normal[key], reduced[key])
            self.assertGreaterEqual(normal[key], 4000)

    def test_reduce_motion_requested(self):
        self.assertFalse(theme.reduce_motion_requested({}, {}))
        self.assertFalse(theme.reduce_motion_requested(None, {}))
        self.assertTrue(theme.reduce_motion_requested({"gui_reduce_motion": True}, {}))
        self.assertFalse(theme.reduce_motion_requested({"gui_reduce_motion": "yes"}, {}))
        self.assertTrue(theme.reduce_motion_requested({}, {"PAWTATION_REDUCE_MOTION": "1"}))
        self.assertTrue(theme.reduce_motion_requested(None, {"PAWTATION_REDUCE_MOTION": " TRUE "}))
        self.assertFalse(theme.reduce_motion_requested({}, {"PAWTATION_REDUCE_MOTION": "0"}))

    def test_label(self):
        self.assertEqual(theme.label("light"), "Blush")
        self.assertEqual(theme.label("dark"), "Cosmic")
        self.assertEqual(theme.label("no-such-theme"), "Blush")


class Tokens(unittest.TestCase):
    def test_sections_exist(self):
        tok = theme.tokens()
        for key in ("type", "space", "radius", "size", "layout", "keyline", "elevation", "motion", "sprite"):
            self.assertIn(key, tok)
        self.assertNotIn("themes", tok)

    def test_type_scale(self):
        typ = theme.tokens()["type"]
        self.assertEqual(typ["unit"], "px")
        families = typ["families"]
        self.assertEqual(set(families), {"display", "body", "mono"})
        for role, cands in families.items():
            self.assertGreaterEqual(len(cands), 6, role)
            self.assertEqual(len(cands), len({c.casefold() for c in cands}), "%s lists a family twice" % role)
        for name, spec in typ["scale"].items():
            self.assertIn(spec["family"], families, name)
            self.assertIn(spec["weight"], ("normal", "bold"), name)
            self.assertGreaterEqual(spec["px"], 12, "%s is too small to read" % name)
        self.assertGreaterEqual(typ["scale"]["body"]["px"], 14)
        self.assertGreater(typ["scale"]["display"]["px"], typ["scale"]["title"]["px"])
        self.assertGreater(typ["scale"]["title"]["px"], typ["scale"]["heading"]["px"])
        self.assertGreater(typ["scale"]["heading"]["px"], typ["scale"]["body"]["px"])

    def test_every_platform_has_a_stock_font_in_each_list(self):
        families = theme.tokens()["type"]["families"]
        stock = {
            "windows": {"Trebuchet MS", "Verdana", "Arial", "Segoe UI", "Consolas", "Courier New"},
            "macos": {"Arial Rounded MT Bold", "Avenir Next", "Helvetica Neue", "Verdana", "Arial", "Menlo", "Courier New"},
            "linux": {"DejaVu Sans", "Ubuntu", "Cantarell", "Liberation Sans", "DejaVu Sans Mono", "Liberation Mono"},
        }
        for role, cands in families.items():
            for system, have in stock.items():
                self.assertTrue(have & set(cands), "%s has no stock %s font" % (role, system))

    def test_rounded_faces_come_first_and_segoe_ui_is_not_the_look(self):
        families = theme.tokens()["type"]["families"]
        self.assertNotIn("Segoe UI", families["display"])
        body = families["body"]
        self.assertLess(body.index("Trebuchet MS"), body.index("Segoe UI"))
        self.assertIn(families["display"][0], ("Fredoka", "Baloo 2", "Nunito", "Quicksand"))
        self.assertIn("Arial Rounded MT Bold", families["display"])
        self.assertIn(theme.pick_font(families["display"], ["Segoe UI", "Arial", "Trebuchet MS", "Verdana"]),
                      ("Trebuchet MS",), "stock Windows should land on Trebuchet MS, not Segoe UI or Arial")

    def test_scales(self):
        tok = theme.tokens()
        space = tok["space"]
        self.assertEqual(space[0], 0)
        self.assertEqual(space, sorted(space))
        self.assertEqual(len(space), len(set(space)))
        radius = tok["radius"]
        self.assertEqual(radius["none"], 0)
        self.assertLess(radius["sm"], radius["md"])
        self.assertLess(radius["md"], radius["lg"])
        self.assertGreaterEqual(radius["pill"], 99)
        size = tok["size"]
        self.assertGreaterEqual(size["hit_min"], 24, "WCAG 2.2 target size (minimum)")
        for key in ("control", "control_sm", "row", "chip", "star"):
            self.assertGreaterEqual(size[key], 22, key)
        self.assertGreaterEqual(size["control_sm"], size["hit_min"])
        self.assertGreaterEqual(tok["keyline"]["focus"], 2)
        for level, offset in tok["elevation"].items():
            self.assertEqual(len(offset), 2, level)

    def test_sprite_sizes_match_the_art_contract(self):
        sprite = theme.tokens()["sprite"]
        for key in ("stage", "stage_compact", "cameo", "dialog", "empty_state"):
            self.assertIn(sprite[key], (96, 192), key)
        self.assertEqual(sprite["stage"], 192)
        self.assertEqual(sprite["stage_compact"], 96)
        self.assertAlmostEqual(sprite["baseline"], 0.92)
        size = theme.tokens()["size"]
        self.assertGreater(size["stage"], sprite["stage"], "room for a speech bubble above the sprites")
        self.assertGreater(size["stage_compact"], sprite["stage_compact"])


class FallbackAndRepair(TempThemeFile):
    def assert_is_fallback(self, path):
        problems = []
        doc = theme.load_document(path, problems)
        self.assertEqual(doc, theme.FALLBACK)
        self.assertTrue(problems, "a fallback should be reported")
        for name in BUILT_IN:
            self.assertEqual(theme.load(name, path=path), theme.FALLBACK["themes"][name])
        self.assertEqual(sorted(theme.names(path)), ["dark", "light"])

    def test_missing_file(self):
        self.assert_is_fallback(self.path)

    def test_corrupt_json(self):
        self.assert_is_fallback(self.write('{"version": 1, "themes": {"light": {"bg": "#fff5fa",'))

    def test_empty_file(self):
        self.assert_is_fallback(self.write(""))

    def test_binary_garbage(self):
        self.assert_is_fallback(self.write(b"\xff\xfe\x00\x00PNG\x89\x00garbage"))

    def test_wrong_top_level_type(self):
        for junk in ([1, 2, 3], "pink", 7, None, True):
            self.assert_is_fallback(self.write(json.dumps(junk)))

    def test_a_directory_instead_of_a_file(self):
        os.mkdir(self.path)
        self.assert_is_fallback(self.path)

    def test_empty_object_gets_every_section(self):
        doc = theme.load_document(self.write({}))
        self.assertEqual(doc, theme.FALLBACK)

    def test_missing_and_broken_roles_are_repaired(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        light = doc["themes"]["light"]
        del light["primary"]
        light["ink"] = "navy"
        light["line"] = "#12345"
        light["focus"] = 12
        light["accent"] = None
        light["danger"] = "#GGGGGG"
        light["bg"] = "#FFF0F6"                       # valid: kept, lower-cased
        light["sparkle"] = "#ABCDEF"                  # extra role: kept
        light["nonsense"] = "sparkly"                 # extra junk: dropped
        problems = []
        got = theme.load("light", path=self.write(doc))
        theme.load_document(self.path, problems)
        fb = theme.FALLBACK["themes"]["light"]
        for role in ("primary", "ink", "line", "focus", "accent", "danger"):
            self.assertEqual(got[role], fb[role], role)
            self.assertTrue(any("themes.light.%s" % role in p for p in problems), role)
        self.assertEqual(got["bg"], "#fff0f6")
        self.assertEqual(got["sparkle"], "#abcdef")
        self.assertNotIn("nonsense", got)
        for role in theme.ROLES:
            self.assertRegex(got[role], r"^#[0-9a-f]{6}$")
        self.assertEqual(theme.load("dark", path=self.path), theme.FALLBACK["themes"]["dark"])

    def test_missing_theme_is_supplied(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        del doc["themes"]["dark"]
        doc["themes"]["light"] = "not an object"
        path = self.write(doc)
        self.assertEqual(theme.load("dark", path=path), theme.FALLBACK["themes"]["dark"])
        self.assertEqual(theme.load("light", path=path), theme.FALLBACK["themes"]["light"])

    def test_themes_of_the_wrong_type(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["themes"] = ["light", "dark"]
        self.assertEqual(theme.load_document(self.write(doc))["themes"], theme.FALLBACK["themes"])

    def test_default_and_unknown_names(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["default"] = "dark"
        path = self.write(doc)
        self.assertEqual(theme.names(path), ["dark", "light"])
        self.assertEqual(theme.load(path=path), theme.FALLBACK["themes"]["dark"])
        self.assertEqual(theme.load("no-such-theme", path=path), theme.FALLBACK["themes"]["dark"])
        self.assertEqual(theme.resolve("no-such-theme", path), "dark")
        self.assertEqual(theme.resolve("light", path), "light")
        doc["default"] = "sunset"
        self.assertEqual(theme.default_name(self.write(doc)), "light")
        doc["default"] = ["light"]
        self.assertEqual(theme.default_name(self.write(doc)), "light")
        for odd in (12, None, ["dark"], {"a": 1}):
            self.assertEqual(theme.load(odd, path=path), theme.load(path=path))

    def test_custom_theme_borrows_from_the_closest_built_in(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["themes"]["midnight"] = {"bg": "#000010", "primary": "#ff00aa"}
        doc["themes"]["paper"] = {"bg": "#fffff0"}
        doc["themes"]["blank"] = {}
        doc["labels"]["midnight"] = "Midnight"
        path = self.write(doc)
        self.assertEqual(theme.names(path), ["light", "dark", "midnight", "paper", "blank"])
        midnight = theme.load("midnight", path=path)
        self.assertEqual(midnight["bg"], "#000010")
        self.assertEqual(midnight["primary"], "#ff00aa")
        self.assertEqual(midnight["ink"], theme.FALLBACK["themes"]["dark"]["ink"])
        self.assertEqual(theme.load("paper", path=path)["ink"], theme.FALLBACK["themes"]["light"]["ink"])
        self.assertEqual(theme.load("blank", path=path)["ink"], theme.FALLBACK["themes"]["light"]["ink"])
        self.assertEqual(theme.label("midnight", path), "Midnight")
        self.assertEqual(theme.label("paper", path), "Paper")
        failing = [p for p in theme.check(path) if p.startswith("themes.midnight")]
        self.assertTrue(failing, "check() should flag what was repaired or fails contrast in a custom theme")

    def test_broken_token_sections_are_repaired(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["space"] = "roomy"
        doc["radius"]["pill"] = "big"
        doc["type"]["families"]["display"] = []
        doc["type"]["families"]["body"] = ["", 3]
        doc["type"]["scale"]["body"]["px"] = -4
        doc["type"]["scale"]["title"] = None
        doc["motion"] = None
        doc["sprite"]["stage"] = True
        del doc["size"]
        doc["elevation"]["card"] = ["a", "b"]
        doc["keyline"]["focus"] = float("nan")
        problems = []
        tok = theme.tokens(self.write(json.dumps(doc)))        # allow_nan default: NaN is written as NaN
        theme.load_document(self.path, problems)
        fb = theme.FALLBACK
        self.assertEqual(tok["space"], fb["space"])
        self.assertEqual(tok["radius"]["pill"], fb["radius"]["pill"])
        self.assertEqual(tok["radius"]["md"], fb["radius"]["md"])
        self.assertEqual(tok["type"]["families"]["display"], fb["type"]["families"]["display"])
        self.assertEqual(tok["type"]["families"]["body"], fb["type"]["families"]["body"])
        self.assertEqual(tok["type"]["scale"]["body"]["px"], fb["type"]["scale"]["body"]["px"])
        self.assertEqual(tok["type"]["scale"]["title"], fb["type"]["scale"]["title"])
        self.assertEqual(tok["motion"], fb["motion"])
        self.assertEqual(tok["sprite"]["stage"], fb["sprite"]["stage"])
        self.assertEqual(tok["size"], fb["size"])
        self.assertEqual(tok["elevation"]["card"], fb["elevation"]["card"])
        self.assertEqual(tok["keyline"]["focus"], fb["keyline"]["focus"])
        self.assertGreaterEqual(len(problems), 10)
        self.assertEqual(theme.motion(True, self.path)["fast"], 0)
        self.assertEqual(theme.stage_sprite_size(448, 2, path=self.path), 192)

    def test_valid_token_overrides_and_additions_are_kept(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["space"] = [0, 3, 6, 9]
        doc["radius"]["md"] = 12
        doc["radius"]["xl"] = 28
        doc["type"]["families"]["display"] = ["Comic Sans MS", "Arial"]
        doc["mine"] = {"anything": [1, 2]}
        tok = theme.tokens(self.write(doc))
        self.assertEqual(tok["space"], [0, 3, 6, 9])
        self.assertEqual(tok["radius"]["md"], 12)
        self.assertEqual(tok["radius"]["xl"], 28)
        self.assertEqual(theme.fonts(["Arial", "Comic Sans MS"], self.path)["display"], "Comic Sans MS")
        self.assertEqual(tok["mine"], {"anything": [1, 2]})
        self.assertEqual(theme.check(self.path), [])

    def test_results_are_copies(self):
        colors = theme.load("light")
        colors["primary"] = "#000000"
        colors.clear()
        self.assertEqual(theme.load("light")["primary"], theme.FALLBACK["themes"]["light"]["primary"])
        doc = theme.load_document(self.path)                   # missing file -> fallback copy
        doc["themes"]["light"]["primary"] = "#000000"
        doc["type"]["families"]["display"].clear()
        doc["space"].append(999)
        self.assertEqual(theme.load("light", path=self.path)["primary"], theme.load("light")["primary"])
        self.assertTrue(theme.FALLBACK["type"]["families"]["display"])
        self.assertNotIn(999, theme.FALLBACK["space"])
        tok = theme.tokens()
        tok["motion"]["fast"] = 5000
        self.assertNotEqual(theme.tokens()["motion"]["fast"], 5000)

    def test_check_reports_a_failing_pair(self):
        doc = json.loads(json.dumps(theme.FALLBACK))
        doc["themes"]["light"]["ink_muted"] = "#d9c9d4"        # far too pale on a blush background
        found = theme.check(self.write(doc))
        self.assertTrue(any("ink_muted on bg" in p for p in found), found)


class CommandLine(unittest.TestCase):
    def run_main(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = theme.main(list(args))
        return code, out.getvalue()

    def test_check_passes_on_the_shipped_file(self):
        code, text = self.run_main("--check")
        self.assertEqual(code, 0, text)
        self.assertIn("no problems", text)

    def test_audit_lists_both_themes_and_no_failures(self):
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("== light", text)
        self.assertIn("== dark", text)
        self.assertNotIn("FAIL", text)

    def test_dump_is_the_built_in_copy(self):
        code, text = self.run_main("--dump")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(text), theme.FALLBACK)

    def test_help_and_roles(self):
        self.assertEqual(self.run_main("--help")[0], 0)
        code, text = self.run_main("--roles")
        self.assertEqual(text.split(), list(theme.ROLES))


class SourceRules(unittest.TestCase):
    """Runtime code is Python 3.9-compatible standard library, and theme.py never needs tkinter."""

    SOURCE = Path(theme.__file__)

    def test_parses_as_python_3_9(self):
        ast.parse(self.SOURCE.read_text(encoding="utf-8"), filename=str(self.SOURCE), feature_version=(3, 9))

    def test_imports_are_standard_library_and_not_tkinter(self):
        tree = ast.parse(self.SOURCE.read_text(encoding="utf-8"))
        allowed = {"__future__", "copy", "json", "os", "re", "sys", "pathlib", "typing"}
        seen = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                seen.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0, "theme.py must not import other pawtation modules")
                seen.add((node.module or "").split(".")[0])
        self.assertLessEqual(seen, allowed, "unexpected imports: %s" % sorted(seen - allowed))
        self.assertNotIn("tkinter", seen)

    def test_uses_postponed_annotations(self):
        self.assertIn("from __future__ import annotations", self.SOURCE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
