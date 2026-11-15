"""PROPS: not a character but a set of single-frame stickers (decorations and objects) in the house style.

Same rig API as a character (``CHAR_ID``, ``HEIGHT``, ``ANIMS``, ``draw(pose)``), so it goes through the same
build and lands in the same manifest as ``props``.  ``REQUIRED = {}`` tells ``validate_rig`` that no standard
animations are needed, and ``PORTRAIT = False`` skips the 512 px still.  Every prop is a plain, generic object:
no logos, no brand marks.  A pose is just ``{"prop": "<name>"}``.
"""
from __future__ import annotations

from lib2d import (anim, blob, circle, clip, detail, ellipse, g, heart, line, mix, outlined, path, polyline,
                   rect, rotate, sparkle, sticker, zzz)

CHAR_ID = "props"
HEIGHT = 0.8
REQUIRED = {}
PORTRAIT = False

INK = "#2b2d42"
CREAM = "#fff3d6"
TOAST = "#e9a85a"
TOAST_D = "#c98233"
CRUST = "#b4691f"
CHEESE = "#ffd23f"
CHEESE_D = "#f0b21c"
MUG = "#7fc8c2"
MUG_D = "#4fa59f"
TEA = "#b5651d"
SILVER = "#dfe3ee"
SILVER_D = "#aeb4c8"
VIOLET = "#8b6fd6"
GOLD = "#f2c14e"
CARD = "#3c6fd8"
CARD_D = "#2b52a8"
MEM = "#59b86b"
MEM_D = "#3a8b4b"
W = 6.0

NAMES = ("sparkle", "heart", "zzz", "grilled_cheese", "tea_mug", "disc", "sd_card", "memory_card")
ANIMS = {n: anim([{"prop": n}], fps=1, loop=False) for n in NAMES}


def _sparkle():
    return [sparkle(256, 256, 190, fill="#fff6a8", ink=INK, width=8, pinch=0.2),
            sparkle(372, 150, 52, fill="#ffffff", ink=INK, width=6)]


def _heart():
    return [heart(256, 262, 165, fill="#ff4fa3", ink=INK, width=8),
            detail(ellipse(180, 190, 30, 16, rot=-35, fill="#ffffff", opacity=0.55))]


def _zzz():
    return [zzz(110, 390, size=90, fill="#ffffff", ink=INK, count=3)]


def _grilled_cheese():
    slice_top = rect(110, 120, 292, 150, 44, fill=TOAST, transform=rotate(-8, 256, 256))
    slice_bot = rect(110, 230, 292, 150, 44, fill=TOAST_D, transform=rotate(-8, 256, 256))
    melt = path("M120 262 C150 300 170 250 200 292 C230 330 250 262 290 300 C320 335 350 270 392 296 "
                "L398 240 L116 240 Z", fill=CHEESE, transform=rotate(-8, 256, 256))
    drip = path("M214 292 C216 340 238 346 240 316 C242 300 236 292 232 288 Z", fill=CHEESE_D,
                transform=rotate(-8, 256, 256))
    return [outlined(slice_bot, melt, drip, slice_top, ink=INK, width=W),
            detail(rect(132, 146, 248, 14, 7, fill=mix(TOAST, "#ffffff", 0.4), opacity=0.7,
                        transform=rotate(-8, 256, 256)),
                   line(150, 200, 360, 190, stroke=CRUST, stroke_width=8, opacity=0.5)),
            sparkle(390, 118, 28, fill="#ffffff", ink=INK, width=5)]


def _tea_mug():
    body = path("M150 190 L150 380 Q150 420 190 420 L300 420 Q340 420 340 380 L340 190 Z", fill=MUG)
    handle = path("M338 230 Q420 230 420 300 Q420 360 332 360", fill="none", stroke=MUG_D, stroke_width=26)
    rim = ellipse(245, 190, 95, 26, fill=TEA)
    steam = [polyline([(205, 140), (190, 105), (218, 80), (204, 46)], stroke="#ffffff", stroke_width=14),
             polyline([(275, 140), (260, 108), (288, 84), (274, 54)], stroke="#ffffff", stroke_width=14)]
    return [outlined(body, handle, rim, ink=INK, width=W),
            detail(rect(170, 230, 26, 150, 13, fill="#ffffff", opacity=0.4),
                   ellipse(245, 192, 74, 15, fill=mix(TEA, "#ffffff", 0.25)),
                   circle(245, 322, 30, fill="#ffffff", opacity=0.55)),
            *steam]


def _disc():
    cx, cy = 256, 262
    return [outlined(circle(cx, cy, 190, fill=SILVER), ink=INK, width=W),
            detail(circle(cx, cy, 150, fill=VIOLET), circle(cx, cy, 104, fill=SILVER_D),
                   path("M256 262 L256 72 A190 190 0 0 1 395 130 Z", fill="#ffffff", opacity=0.25),
                   circle(cx, cy, 60, fill=SILVER), circle(cx, cy, 26, fill="#ffffff", stroke=INK, stroke_width=5)),
            sparkle(404, 120, 30, fill="#ffffff", ink=INK, width=5)]


def _sd_card():
    body = path("M170 70 L320 70 L376 126 L376 442 Q376 458 360 458 L170 458 Q154 458 154 442 L154 86 Q154 70 170 70 Z",
                fill=CARD)
    pins = [rect(176 + i * 36, 78, 22, 70, 5, fill=GOLD, stroke=None) for i in range(5)]
    return [outlined(body, ink=INK, width=W),
            detail(*pins, rect(182, 220, 164, 190, 14, fill="#ffffff"),
                   line(204, 270, 324, 270, stroke=CARD_D, stroke_width=12),
                   line(204, 310, 296, 310, stroke=CARD_D, stroke_width=12),
                   rect(160, 438, 210, 10, 5, fill=CARD_D, opacity=0.5))]


def _memory_card():
    body = path("M120 120 L392 120 Q420 120 420 148 L420 360 Q420 392 388 392 L150 392 Q120 392 120 362 Z",
                fill=MEM)
    notch = path("M392 120 L420 148 L420 120 Z", fill=MEM_D)
    pins = [rect(168 + i * 38, 126, 22, 56, 5, fill=GOLD, stroke=None) for i in range(6)]
    return [outlined(body, ink=INK, width=W),
            detail(notch, *pins, rect(150, 218, 212, 130, 18, fill="#ffffff"),
                   circle(256, 283, 36, fill=mix(MEM, "#ffffff", 0.35)),
                   circle(256, 283, 14, fill=MEM_D))]


_DRAW = {"sparkle": _sparkle, "heart": _heart, "zzz": _zzz, "grilled_cheese": _grilled_cheese,
         "tea_mug": _tea_mug, "disc": _disc, "sd_card": _sd_card, "memory_card": _memory_card}


def draw(pose) -> str:
    """One prop sticker: ``pose["prop"]`` picks it (default sparkle)."""
    return sticker(*_DRAW.get(pose.get("prop", "sparkle"), _sparkle)(), ink=INK)
