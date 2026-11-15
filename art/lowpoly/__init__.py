"""Papercraft low-poly renders: a pure-Python flat-shaded software renderer and the models it draws.

Dev-time only (the app never imports this package; it reads the PNGs under ``assets/renders``).
Standard library only. See ``docs/ART_LOWPOLY.md``.

    python3 art/lowpoly/build.py [--only nova] [--frames N]
"""

__all__ = ["mesh", "render", "png", "pipeline"]
