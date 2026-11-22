"""Design tokens for Pawtation: colours, type, spacing, radii, motion, sprite sizes.

Standard library only and no tkinter import, so the CLI, the tests and the GUI can all use it.
``data/theme.json`` is the copy people edit; ``FALLBACK`` below is a built-in copy of the same
document, so a missing or broken file never stops the app (``load`` repairs what it can and never
raises).  ``docs/DESIGN_SYSTEM.md`` explains every role and which widget uses it.

    from pawtation import theme
    c = theme.load("dark")            # {"bg": "#17122b", "primary": "#ff4fa3", ...}
    t = theme.tokens()                # type / space / radius / motion / sprite / keyline / ...
    theme.contrast(c["ink"], c["bg"]) # WCAG ratio
    python3 -m pawtation.theme        # prints the contrast audit for every theme
"""
from __future__ import annotations

import copy
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

VERSION = 1
# Standalone on purpose (no pawtation imports): the same rule as pawtation/paths.py, inline. In the packaged .exe the
# shipped files live in the folder PyInstaller unpacks to (sys._MEIPASS).
_BUNDLE = (Path(sys._MEIPASS) if getattr(sys, "frozen", False) and getattr(sys, "_MEIPASS", None)
           else Path(__file__).resolve().parent.parent)
THEME_PATH = _BUNDLE / "data" / "theme.json"

# ---------------------------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------------------------

#: The semantic colour roles docs/SPEC_V2.md section 6 requires of every theme.
SPEC_ROLES: Tuple[str, ...] = (
    "bg", "surface", "surface_alt", "stage", "ink", "ink_muted", "line",
    "primary", "primary_ink", "primary_soft", "accent", "accent_ink", "accent_soft",
    "success", "warning", "danger", "focus", "selection", "selection_ink",
    "nova", "iggy", "duskie",
)

#: Roles this design system adds (each is explained in docs/DESIGN_SYSTEM.md, "Added roles").
EXTRA_ROLES: Tuple[str, ...] = (
    "line_soft",                                     # decorative dividers (no contrast promise)
    "header", "header_ink",                          # the app header band
    "primary_hover", "primary_active", "primary_text",
    "accent_hover", "accent_active", "accent_text",
    "gold", "gold_ink", "gold_soft", "gold_text",    # stars, highlights, "rotation due"
    "success_soft", "warning_soft", "danger_soft",
    "danger_ink", "danger_hover", "danger_active",   # the danger button
    "disabled", "disabled_ink",
    "stage_floor", "stage_glow",
    "keyline", "shadow",                             # sticker die-cut edge and the drawn hard shadow
    "nova_ink", "iggy_ink", "duskie_ink",            # lettering on a character's name tag
    "cameo", "cameo_ink",                            # name tag for any character without its own role
)

ROLES: Tuple[str, ...] = SPEC_ROLES + EXTRA_ROLES

# ---------------------------------------------------------------------------------------------
# Built-in copy of data/theme.json (tests/test_theme.py keeps the two identical)
# ---------------------------------------------------------------------------------------------

FALLBACK: Dict[str, Any] = {
    "version": VERSION,
    "about": "Pawtation design tokens. docs/DESIGN_SYSTEM.md explains every role. Colours are "
             "#rrggbb. pawtation/theme.py holds a built-in copy and repairs anything missing here.",
    "default": "light",
    "labels": {"light": "Blush", "dark": "Cosmic"},
    "themes": {
        "light": {
            "bg": "#fff5fa",
            "surface": "#ffffff",
            "surface_alt": "#ffe9f3",
            "stage": "#ffe4f0",
            "ink": "#1b1c30",
            "ink_muted": "#625a78",
            "line": "#e2358d",
            "primary": "#ff3d9a",
            "primary_ink": "#1b1c30",
            "primary_soft": "#ffd6e9",
            "accent": "#3d8fe0",
            "accent_ink": "#1b1c30",
            "accent_soft": "#dcecfc",
            "success": "#0f7b5b",
            "warning": "#8f5600",
            "danger": "#b8162f",
            "focus": "#d916c0",
            "selection": "#ff5fad",
            "selection_ink": "#1b1c30",
            "nova": "#2b2d42",
            "iggy": "#5a6699",
            "duskie": "#fec349",
            "line_soft": "#ffc4de",
            "header": "#ff3d9a",
            "header_ink": "#1b1c30",
            "primary_hover": "#ff62ae",
            "primary_active": "#f43a92",
            "primary_text": "#c2136e",
            "accent_hover": "#62a6ea",
            "accent_active": "#3a8adc",
            "accent_text": "#1b62b0",
            "gold": "#f7bd45",
            "gold_ink": "#1b1c30",
            "gold_soft": "#ffefc9",
            "gold_text": "#8a5a00",
            "success_soft": "#e0f6ea",
            "warning_soft": "#ffefc9",
            "danger_soft": "#ffe1e3",
            "danger_ink": "#ffffff",
            "danger_hover": "#cb2b43",
            "danger_active": "#9f1127",
            "disabled": "#f3e6ee",
            "disabled_ink": "#978da6",
            "stage_floor": "#ffa9cf",
            "stage_glow": "#ffbfdb",
            "keyline": "#ffffff",
            "shadow": "#f4b6d3",
            "nova_ink": "#ff6fdc",
            "iggy_ink": "#ffffff",
            "duskie_ink": "#1b1c30",
            "cameo": "#e9e3f4",
            "cameo_ink": "#1b1c30",
        },
        "dark": {
            "bg": "#17122b",
            "surface": "#241d40",
            "surface_alt": "#322855",
            "stage": "#110c24",
            "ink": "#f1eff8",
            "ink_muted": "#b9b0d2",
            "line": "#d14f98",
            "primary": "#ff4fa3",
            "primary_ink": "#1b1c30",
            "primary_soft": "#4a2050",
            "accent": "#5fa9f2",
            "accent_ink": "#1b1c30",
            "accent_soft": "#1c3358",
            "success": "#62e0b4",
            "warning": "#ffcf6b",
            "danger": "#ff8266",
            "focus": "#ff8cf0",
            "selection": "#ff4fa3",
            "selection_ink": "#1b1c30",
            "nova": "#ff6fdc",
            "iggy": "#5a6699",
            "duskie": "#ffd37c",
            "line_soft": "#4b3b6e",
            "header": "#ff4fa3",
            "header_ink": "#1b1c30",
            "primary_hover": "#ff78b9",
            "primary_active": "#f04499",
            "primary_text": "#ff85c0",
            "accent_hover": "#84bff7",
            "accent_active": "#4a97e6",
            "accent_text": "#8cc8ff",
            "gold": "#ffc94d",
            "gold_ink": "#1b1c30",
            "gold_soft": "#3d3122",
            "gold_text": "#ffd166",
            "success_soft": "#153828",
            "warning_soft": "#3d3122",
            "danger_soft": "#47202a",
            "danger_ink": "#1b1c30",
            "danger_hover": "#ff9b84",
            "danger_active": "#f2714f",
            "disabled": "#2b2547",
            "disabled_ink": "#81789c",
            "stage_floor": "#2e2440",
            "stage_glow": "#4a1c58",
            "keyline": "#f1eff8",
            "shadow": "#0a0717",
            "nova_ink": "#1b1c30",
            "iggy_ink": "#ffffff",
            "duskie_ink": "#1b1c30",
            "cameo": "#3a3060",
            "cameo_ink": "#f1eff8",
        },
    },
    "type": {
        "unit": "px",
        "families": {
            "display": ["Fredoka", "Baloo 2", "Nunito", "Quicksand", "Varela Round", "M PLUS Rounded 1c",
                        "Arial Rounded MT Bold", "Hiragino Maru Gothic ProN", "Chalkboard SE", "Ubuntu",
                        "Trebuchet MS", "Cantarell", "Avenir Next", "Verdana", "DejaVu Sans", "Helvetica Neue",
                        "Arial"],
            "body": ["Nunito", "Varela Round", "M PLUS Rounded 1c", "Ubuntu", "Cantarell", "Avenir Next",
                     "Trebuchet MS", "Verdana", "Noto Sans", "DejaVu Sans", "Helvetica Neue", "Segoe UI",
                     "Liberation Sans", "Arial"],
            "mono": ["JetBrains Mono", "Cascadia Mono", "Cascadia Code", "SF Mono", "Menlo", "Consolas",
                     "DejaVu Sans Mono", "Ubuntu Mono", "Liberation Mono", "Courier New"],
        },
        "scale": {
            "display": {"family": "display", "px": 26, "weight": "bold"},
            "title": {"family": "display", "px": 20, "weight": "bold"},
            "heading": {"family": "display", "px": 16, "weight": "bold"},
            "body": {"family": "body", "px": 14, "weight": "normal"},
            "body_strong": {"family": "body", "px": 14, "weight": "bold"},
            "small": {"family": "body", "px": 12, "weight": "normal"},
            "tag": {"family": "body", "px": 12, "weight": "bold"},
            "mono": {"family": "mono", "px": 13, "weight": "normal"},
        },
        "leading": 1.4,
    },
    "space": [0, 2, 4, 8, 12, 16, 24, 32, 48],
    "radius": {"none": 0, "sm": 6, "md": 10, "lg": 16, "pill": 999},
    "size": {"header": 64, "control": 36, "control_sm": 28, "control_lg": 44, "row": 30, "chip": 30,
             "progress": 22, "meter": 12, "star": 22, "hit_min": 28, "stage": 292, "stage_compact": 188},
    "layout": {"window_min": [960, 640], "window_default": [1120, 780], "side_panel": 448, "gutter": 18},
    "keyline": {"hair": 1, "control": 2, "card": 2, "sticker": 3, "focus": 3, "focus_gap": 2},
    "elevation": {"flat": [0, 0], "card": [3, 3], "raised": [4, 5], "dialog": [6, 7]},
    "motion": {
        "fast": 90,
        "base": 160,
        "slow": 280,
        "sparkle": 900,
        "stripe": 700,
        "sprite_fps_max": 12,
        "blink_min": 2800,
        "blink_max": 6500,
        "bubble_hold": 6000,
        "toast_hold": 4500,
        "reduced": {"fast": 0, "base": 0, "slow": 0, "sparkle": 0, "stripe": 0, "sprite_fps_max": 0},
    },
    "sprite": {"stage": 192, "stage_compact": 96, "cameo": 96, "dialog": 96, "empty_state": 192,
               "overlap": 24, "gap_compact": 16, "pad": 16, "baseline": 0.92},
}

# ---------------------------------------------------------------------------------------------
# Contrast pairs the GUI is allowed to rely on.  (foreground role, background role, minimum, use)
# 4.5 = body text, 3.0 = large text, control boundaries, focus rings and other UI graphics.
# ---------------------------------------------------------------------------------------------

PAIRS: Tuple[Tuple[str, str, float, str], ...] = (
    # body text
    ("ink", "bg", 4.5, "text on the window"),
    ("ink", "surface", 4.5, "text on cards, the table, fields, speech bubbles"),
    ("ink", "surface_alt", 4.5, "text on table headings, striped rows, chips"),
    ("ink", "stage", 4.5, "text drawn straight on the stage"),
    ("ink", "stage_floor", 4.5, "text drawn on the stage floor"),
    ("ink", "primary_soft", 4.5, "text on soft pink fills (hover rows, troughs, ghost hover)"),
    ("ink", "accent_soft", 4.5, "text on secondary buttons and info toasts"),
    ("ink", "gold_soft", 4.5, "text on the rotation-due banner and highlights"),
    ("ink", "success_soft", 4.5, "text on success toasts"),
    ("ink", "warning_soft", 4.5, "text on warning toasts"),
    ("ink", "danger_soft", 4.5, "text on error toasts"),
    ("ink_muted", "bg", 4.5, "captions and the status line"),
    ("ink_muted", "surface", 4.5, "captions on cards, placeholder text"),
    ("ink_muted", "surface_alt", 4.5, "captions on striped rows and chips"),
    # text on bright fills
    ("primary_ink", "primary", 4.5, "primary button label"),
    ("primary_ink", "primary_hover", 4.5, "primary button label, hover"),
    ("primary_ink", "primary_active", 4.5, "primary button label, pressed"),
    ("header_ink", "header", 4.5, "title and outline buttons on the header band"),
    ("header_ink", "keyline", 4.5, "timer pill (a white sticker) on the header band"),
    ("accent_ink", "accent", 4.5, "label on a filled blue control"),
    ("accent_ink", "accent_hover", 4.5, "label on a filled blue control, hover"),
    ("accent_ink", "accent_active", 4.5, "label on a filled blue control, pressed"),
    ("selection_ink", "selection", 4.5, "selected table row, selected text"),
    ("gold_ink", "gold", 4.5, "label on a gold badge"),
    ("danger_ink", "danger", 4.5, "danger button label"),
    ("danger_ink", "danger_hover", 4.5, "danger button label, hover"),
    ("danger_ink", "danger_active", 4.5, "danger button label, pressed"),
    # coloured text
    ("primary_text", "bg", 4.5, "pink text and pinned rows on the window"),
    ("primary_text", "surface", 4.5, "pink text and pinned rows on cards and the table"),
    ("primary_text", "surface_alt", 4.5, "pinned rows on striped rows"),
    ("accent_text", "bg", 4.5, "links"),
    ("accent_text", "surface", 4.5, "links on cards"),
    ("accent_text", "surface_alt", 4.5, "links on striped rows"),
    ("accent_text", "accent_soft", 4.5, "info toast heading, secondary button label"),
    ("gold_text", "bg", 4.5, "star glyphs as text"),
    ("gold_text", "surface", 4.5, "star glyphs as text in the table"),
    ("gold_text", "surface_alt", 4.5, "star glyphs as text on striped rows"),
    ("gold_text", "gold_soft", 4.5, "rotation-due heading"),
    ("success", "bg", 4.5, "success text"),
    ("success", "surface", 4.5, "success text on cards"),
    ("success", "success_soft", 4.5, "success toast heading"),
    ("warning", "bg", 4.5, "warning text"),
    ("warning", "surface", 4.5, "warning text on cards"),
    ("warning", "warning_soft", 4.5, "warning toast heading"),
    ("danger", "bg", 4.5, "error text"),
    ("danger", "surface", 4.5, "error text on cards"),
    ("danger", "danger_soft", 4.5, "error toast heading"),
    # character name tags
    ("nova_ink", "nova", 4.5, "Nova's name tag"),
    ("iggy_ink", "iggy", 4.5, "Iggy's name tag"),
    ("duskie_ink", "duskie", 4.5, "Duskie's name tag"),
    ("cameo_ink", "cameo", 4.5, "name tag of a cameo or a new character"),
    # control boundaries, focus rings, graphics
    ("primary", "bg", 3.0, "pink fills and keylines on the window"),
    ("primary", "surface", 3.0, "pink fills and keylines on cards"),
    ("accent", "bg", 3.0, "blue fills and keylines on the window"),
    ("accent", "surface", 3.0, "blue fills and keylines on cards"),
    ("line", "bg", 3.0, "control borders on the window"),
    ("line", "surface", 3.0, "control borders on cards"),
    ("line", "surface_alt", 3.0, "control borders on chips and headings"),
    ("line", "stage", 3.0, "speech-bubble and chip borders on the stage"),
    ("focus", "bg", 3.0, "focus ring on the window"),
    ("focus", "surface", 3.0, "focus ring on cards"),
    ("focus", "surface_alt", 3.0, "focus ring on chips and headings"),
    ("focus", "stage", 3.0, "focus ring on the stage"),
    ("primary_ink", "primary", 3.0, "focus ring drawn on a pink fill"),
    ("gold_text", "surface", 3.0, "outline of a gold star"),
)

_HEX6 = re.compile(r"^#[0-9a-fA-F]{6}$")
_HEX3 = re.compile(r"^#[0-9a-fA-F]{3}$")


# ---------------------------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------------------------

def is_hex(value: Any) -> bool:
    """True for a ``#rrggbb`` string (the only colour form theme files may use)."""
    return isinstance(value, str) and bool(_HEX6.match(value))


def rgb(color: str) -> Tuple[int, int, int]:
    """``#rrggbb`` (or the ``#rgb`` shorthand) -> (r, g, b) in 0..255.  Raises ValueError otherwise."""
    if isinstance(color, str):
        text = color.strip()
        if _HEX3.match(text):
            text = "#" + "".join(ch * 2 for ch in text[1:])
        if _HEX6.match(text):
            return int(text[1:3], 16), int(text[3:5], 16), int(text[5:7], 16)
    raise ValueError("not a #rrggbb colour: %r" % (color,))


def to_hex(r: float, g: float, b: float) -> str:
    """(r, g, b) in 0..255 (clamped, rounded) -> ``#rrggbb``."""
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in (r, g, b))


def luminance(color: str) -> float:
    """WCAG 2 relative luminance, 0.0 (black) .. 1.0 (white)."""
    def lin(v: int) -> float:
        s = v / 255.0
        return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb(color)
    return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)


def contrast(hex_a: str, hex_b: str) -> float:
    """WCAG 2 contrast ratio between two colours, 1.0 .. 21.0.  Order does not matter."""
    la, lb = luminance(hex_a), luminance(hex_b)
    if la < lb:
        la, lb = lb, la
    return (la + 0.05) / (lb + 0.05)


def mix(hex_a: str, hex_b: str, t: float) -> str:
    """Blend two colours: ``t=0`` gives ``hex_a``, ``t=1`` gives ``hex_b`` (clamped, sRGB channels).

    This is how the GUI gets in-between tones (a glow ring, a pressed tint) without hex literals.
    """
    try:
        t = float(t)
    except (TypeError, ValueError):
        t = 0.0
    if t != t:                                       # NaN
        t = 0.0
    t = max(0.0, min(1.0, t))
    a, b = rgb(hex_a), rgb(hex_b)
    return to_hex(*(a[i] + (b[i] - a[i]) * t for i in range(3)))


def readable(background: str, candidates: Sequence[str]) -> str:
    """The candidate colour with the highest contrast against ``background`` (first wins a tie)."""
    best, best_ratio = "", -1.0
    for cand in candidates:
        try:
            ratio = contrast(cand, background)
        except ValueError:
            continue
        if ratio > best_ratio:
            best, best_ratio = cand, ratio
    if not best:
        raise ValueError("no usable candidate colour")
    return best


# ---------------------------------------------------------------------------------------------
# Loading and repair
# ---------------------------------------------------------------------------------------------

def _note(problems: Optional[List[str]], text: str) -> None:
    if problems is not None:
        problems.append(text)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == value and value >= 0


def _repair(value: Any, fallback: Any, where: str, problems: Optional[List[str]]) -> Any:
    """``value`` if it has the same shape as ``fallback``; otherwise the fallback (recursing into dicts)."""
    if isinstance(fallback, dict):
        if not isinstance(value, dict):
            _note(problems, "%s: expected an object, using the built-in values" % where)
            return copy.deepcopy(fallback)
        out = {}
        for key, fb in fallback.items():
            if key in value:
                out[key] = _repair(value[key], fb, "%s.%s" % (where, key), problems)
            else:
                _note(problems, "%s.%s: missing, using the built-in value" % (where, key))
                out[key] = copy.deepcopy(fb)
        for key, extra in value.items():             # additions are welcome; keep them as they are
            if key not in out and isinstance(key, str):
                out[key] = copy.deepcopy(extra)
        return out
    if isinstance(fallback, list):
        want_text = bool(fallback) and isinstance(fallback[0], str)
        ok = isinstance(value, list) and len(value) > 0 and all(
            (isinstance(v, str) and v.strip()) if want_text else _is_number(v) for v in value)
        if not ok:
            _note(problems, "%s: expected a list of %s, using the built-in values"
                  % (where, "names" if want_text else "numbers"))
            return copy.deepcopy(fallback)
        return list(value)
    if isinstance(fallback, str):
        if not (isinstance(value, str) and value.strip()):
            _note(problems, "%s: expected text, using the built-in value" % where)
            return fallback
        return value
    if _is_number(fallback):
        if not _is_number(value):
            _note(problems, "%s: expected a number, using the built-in value" % where)
            return fallback
        return value
    return copy.deepcopy(fallback)


def _base_for(name: str, raw: Dict[str, Any], default: str) -> Dict[str, str]:
    """The built-in theme a (possibly custom) theme borrows missing roles from."""
    themes = FALLBACK["themes"]
    if name in themes:
        return themes[name]
    bg = raw.get("bg")
    if is_hex(bg):
        return themes["dark"] if luminance(bg) < 0.18 else themes["light"]
    return themes[default if default in themes else FALLBACK["default"]]


def _repair_theme(name: str, raw: Any, default: str, problems: Optional[List[str]]) -> Dict[str, str]:
    if not isinstance(raw, dict):
        _note(problems, "themes.%s: expected an object, using the built-in theme" % name)
        raw = {}
    base = _base_for(name, raw, default)
    out: Dict[str, str] = {}
    for role in ROLES:
        value = raw.get(role)
        if is_hex(value):
            out[role] = value.lower()
        else:
            _note(problems, "themes.%s.%s: %s, using the built-in colour"
                  % (name, role, "missing" if role not in raw else "not a #rrggbb colour"))
            out[role] = base[role]
    for role, value in raw.items():                  # extra roles: keep the valid ones
        if role in out or not isinstance(role, str):
            continue
        if is_hex(value):
            out[role] = value.lower()
        else:
            _note(problems, "themes.%s.%s: not a #rrggbb colour, ignored" % (name, role))
    return out


def load_document(path: Optional[Path] = None, problems: Optional[List[str]] = None) -> Dict[str, Any]:
    """The whole token document, validated and repaired.  Never raises.

    ``path`` defaults to ``THEME_PATH``.  If ``problems`` is a list, a line is appended for every
    repair made (the GUI can show them in the status line; ``python3 -m pawtation.theme --check``
    prints them).
    """
    target = Path(path) if path is not None else THEME_PATH
    raw: Any = None
    parsed = False
    try:
        with open(target, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
        parsed = True
    except FileNotFoundError:
        _note(problems, "%s: not found, using the built-in theme" % target.name)
    except (OSError, ValueError, UnicodeError, RecursionError) as exc:
        _note(problems, "%s: unreadable (%s), using the built-in theme" % (target.name, exc.__class__.__name__))
    if not isinstance(raw, dict):
        if parsed:
            _note(problems, "%s: expected an object at the top, using the built-in theme" % target.name)
        return copy.deepcopy(FALLBACK)

    doc: Dict[str, Any] = {}
    for key, fb in FALLBACK.items():
        if key in ("themes", "default", "labels", "version", "about"):
            continue
        if key in raw:
            doc[key] = _repair(raw[key], fb, key, problems)
        else:
            _note(problems, "%s: missing, using the built-in values" % key)
            doc[key] = copy.deepcopy(fb)

    raw_themes = raw.get("themes")
    if not isinstance(raw_themes, dict):
        _note(problems, "themes: missing or not an object, using the built-in themes")
        raw_themes = {}
    raw_default = raw.get("default")
    fallback_default = FALLBACK["default"]
    themes: Dict[str, Dict[str, str]] = {}
    for name in FALLBACK["themes"]:                  # the built-in themes always exist
        if name in raw_themes:
            themes[name] = _repair_theme(name, raw_themes[name], fallback_default, problems)
        else:
            _note(problems, "themes.%s: missing, using the built-in theme" % name)
            themes[name] = dict(FALLBACK["themes"][name])
    for name, value in raw_themes.items():           # custom themes ride along
        if isinstance(name, str) and name and name not in themes:
            themes[name] = _repair_theme(name, value, fallback_default, problems)
    doc["themes"] = themes

    if isinstance(raw_default, str) and raw_default in themes:
        doc["default"] = raw_default
    else:
        if "default" in raw:
            _note(problems, "default: %r is not a theme, using %r" % (raw_default, fallback_default))
        doc["default"] = fallback_default

    labels = dict(FALLBACK["labels"])
    raw_labels = raw.get("labels")
    if isinstance(raw_labels, dict):
        for name, text in raw_labels.items():
            if isinstance(name, str) and isinstance(text, str) and text.strip():
                labels[name] = text
    doc["labels"] = labels
    version = raw.get("version")
    doc["version"] = version if isinstance(version, int) and not isinstance(version, bool) else VERSION
    about = raw.get("about")
    doc["about"] = about if isinstance(about, str) else FALLBACK["about"]
    for key, value in raw.items():                   # unknown top-level sections are kept untouched
        if isinstance(key, str) and key not in doc:
            doc[key] = copy.deepcopy(value)
    return doc


def names(path: Optional[Path] = None) -> List[str]:
    """Theme names, the default one first."""
    doc = load_document(path)
    default = doc["default"]
    return [default] + [name for name in doc["themes"] if name != default]


def default_name(path: Optional[Path] = None) -> str:
    return load_document(path)["default"]


def resolve(name: Optional[str] = None, path: Optional[Path] = None) -> str:
    """The theme name ``load(name)`` will actually use (unknown or empty -> the default)."""
    doc = load_document(path)
    return name if isinstance(name, str) and name in doc["themes"] else doc["default"]


def load(name: Optional[str] = None, path: Optional[Path] = None) -> Dict[str, str]:
    """Colours of one theme as ``{role: "#rrggbb"}``.  Every role in ``ROLES`` is always present.

    ``name=None`` or an unknown name gives the default theme.  A missing or broken file gives the
    built-in copy; a broken or missing role is repaired from it.  Never raises.
    """
    doc = load_document(path)
    key = name if isinstance(name, str) and name in doc["themes"] else doc["default"]
    return dict(doc["themes"][key])


def label(name: Optional[str] = None, path: Optional[Path] = None) -> str:
    """Display name of a theme for menus ("Blush", "Cosmic"); falls back to the capitalised key."""
    doc = load_document(path)
    key = name if isinstance(name, str) and name in doc["themes"] else doc["default"]
    return doc["labels"].get(key) or key.capitalize()


def tokens(path: Optional[Path] = None) -> Dict[str, Any]:
    """Everything that is not a colour: ``type``, ``space``, ``radius``, ``size``, ``keyline``,
    ``elevation``, ``motion``, ``sprite`` (validated and repaired like the colours)."""
    doc = load_document(path)
    return {key: value for key, value in doc.items()
            if key not in ("themes", "default", "labels", "version", "about")}


def check(path: Optional[Path] = None) -> List[str]:
    """Problems found in the theme file: repairs made while loading, then contrast pairs that fail."""
    problems: List[str] = []
    doc = load_document(path, problems)
    for name, colors in doc["themes"].items():
        for fg, bg, minimum, use in PAIRS:
            ratio = contrast(colors[fg], colors[bg])
            if ratio < minimum:
                problems.append("themes.%s: %s on %s is %.2f:1, needs %.1f:1 (%s)"
                                % (name, fg, bg, ratio, minimum, use))
    return problems


def audit(colors: Dict[str, str], pairs: Optional[Iterable[Tuple[str, str, float, str]]] = None
          ) -> List[Tuple[str, str, float, float, bool, str]]:
    """Measure contrast pairs for one theme: ``[(fg, bg, ratio, minimum, passes, use), ...]``."""
    rows = []
    for fg, bg, minimum, use in (PAIRS if pairs is None else pairs):
        ratio = contrast(colors[fg], colors[bg])
        rows.append((fg, bg, ratio, minimum, ratio >= minimum, use))
    return rows


# ---------------------------------------------------------------------------------------------
# Type, motion, sprites, characters
# ---------------------------------------------------------------------------------------------

def _font_key(family: str) -> str:
    return " ".join(family.split()).casefold()


def pick_font(candidates: Iterable[str], installed: Optional[Iterable[str]], default: str = "") -> str:
    """First candidate family that is installed, spelled the way the system spells it.

    ``installed`` is whatever the toolkit reports (``tkinter.font.families()``); matching ignores case
    and extra spaces, and skips the ``@vertical`` families Windows lists.  Nothing installed, or
    ``installed`` is None/empty: returns ``default`` (``""`` = "let the toolkit choose").
    """
    have: Dict[str, str] = {}
    for family in installed or ():
        if isinstance(family, str) and family.strip() and not family.startswith("@"):
            have.setdefault(_font_key(family), family)
    for cand in candidates or ():
        if isinstance(cand, str):
            hit = have.get(_font_key(cand))
            if hit:
                return hit
    return default


def fonts(installed: Optional[Iterable[str]], path: Optional[Path] = None) -> Dict[str, str]:
    """``{"display": family, "body": family, "mono": family}`` for this machine ("" = toolkit default)."""
    families = tokens(path)["type"]["families"]
    have = list(installed or ())
    return {role: pick_font(cands, have) for role, cands in families.items() if isinstance(cands, list)}


def tk_size(px: float, ui_scale: float = 1.0) -> int:
    """A type-scale size in pixels -> the negative integer Tk reads as "this many pixels"."""
    try:
        scale = float(ui_scale)
    except (TypeError, ValueError):
        scale = 1.0
    if not scale > 0:
        scale = 1.0
    return -max(1, int(round(float(px) * scale)))


def reduce_motion_requested(cfg: Optional[Dict[str, Any]] = None,
                            environ: Optional[Dict[str, str]] = None) -> bool:
    """True when the owner asked for reduced motion: ``"gui_reduce_motion": true`` in config.json or
    ``PAWTATION_REDUCE_MOTION=1`` in the environment.  (Tk cannot read the OS setting.)"""
    env = os.environ if environ is None else environ
    if str(env.get("PAWTATION_REDUCE_MOTION", "")).strip().lower() in ("1", "true", "yes", "on"):
        return True
    return bool(cfg and cfg.get("gui_reduce_motion") is True)


def motion(reduced: bool = False, path: Optional[Path] = None) -> Dict[str, Any]:
    """Durations in milliseconds.  ``reduced=True`` applies the ``reduced`` overrides: transitions,
    sparkles, stripes and sprite animation all become 0 (= jump to the end state, hold one frame)."""
    spec = dict(tokens(path)["motion"])
    overrides = spec.pop("reduced", {})
    if reduced and isinstance(overrides, dict):
        for key, value in overrides.items():
            if _is_number(value):
                spec[key] = value
    spec["is_reduced"] = bool(reduced)
    return spec


def stage_sprite_size(stage_width: float, count: int, stage_height: Optional[float] = None,
                      path: Optional[Path] = None) -> int:
    """Sprite size (px) for ``count`` characters standing on a stage ``stage_width`` px wide:
    the large size when they fit side by side (stickers may overlap a little) and, if
    ``stage_height`` is given, the stage is tall enough for them plus a speech bubble; else the
    compact size."""
    doc = tokens(path)
    spec = doc["sprite"]
    big, small = int(spec["stage"]), int(spec["stage_compact"])
    count = max(1, int(count))
    needed = count * big - (count - 1) * spec["overlap"] + 2 * spec["pad"]
    if stage_width < needed:
        return small
    if stage_height is not None and stage_height < doc["size"]["stage"]:
        return small
    return big


def character_colors(colors: Dict[str, str], char_id: str,
                     cast_entry: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(tag fill, tag lettering) for a character, without hard-coding any character id.

    1. the theme's own ``<id>`` / ``<id>_ink`` roles when both exist;
    2. else the ``color`` from that character's ``data/cast.json`` entry, with whichever of the theme's
       inks reads best on it;
    3. else the neutral ``cameo`` / ``cameo_ink`` pair.
    """
    fill, ink = colors.get(str(char_id)), colors.get("%s_ink" % char_id)
    if is_hex(fill) and is_hex(ink):
        return fill, ink
    cast_color = cast_entry.get("color") if isinstance(cast_entry, dict) else None
    if is_hex(fill) or is_hex(cast_color):
        return _legible_tag(fill if is_hex(fill) else cast_color.lower(), colors)
    return colors["cameo"], colors["cameo_ink"]


def _legible_tag(fill: str, colors: Dict[str, str], minimum: float = 4.5) -> Tuple[str, str]:
    """A tag fill close to ``fill`` plus a brand ink (dark or light) that reads on it at ``minimum``:1.
    A mid-tone fill that neither ink can sit on is nudged lighter (dark ink) or darker (light ink)."""
    dark, light = colors["primary_ink"], colors["keyline"]
    if luminance(dark) > luminance(light):
        dark, light = light, dark
    ink = readable(fill, [dark, light])
    toward = light if ink == dark else dark
    for _ in range(24):
        if contrast(ink, fill) >= minimum:
            break
        fill = mix(fill, toward, 0.08)
    return fill, ink


# ---------------------------------------------------------------------------------------------
# python3 -m pawtation.theme
# ---------------------------------------------------------------------------------------------

def main(argv: Optional[Sequence[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--help" in args or "-h" in args:
        print("usage: python3 -m pawtation.theme [--check | --dump | --roles]\n"
              "  (no option)  contrast audit of every theme in data/theme.json\n"
              "  --check      list problems (repairs and failing pairs); exit 1 if any\n"
              "  --dump       print the built-in fallback document as JSON\n"
              "  --roles      list the colour roles")
        return 0
    if "--dump" in args:
        print(json.dumps(FALLBACK, indent=2))
        return 0
    if "--roles" in args:
        print("\n".join(ROLES))
        return 0
    if "--check" in args:
        found = check()
        print("\n".join(found) if found else "theme.json: no problems")
        return 1 if found else 0
    doc = load_document()
    for name, colors in doc["themes"].items():
        print("== %s (%s)" % (name, doc["labels"].get(name, name)))
        for fg, bg, ratio, minimum, ok, use in audit(colors):
            print("  %-13s on %-14s %5.2f  (min %.1f) %s  %s" % (fg, bg, ratio, minimum, "ok  " if ok else "FAIL", use))
    return 0


if __name__ == "__main__":                           # pragma: no cover
    sys.exit(main())
