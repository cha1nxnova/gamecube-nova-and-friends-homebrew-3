"""SVG -> PNG.  Dev-time only: the app never imports this.

Preferred rasteriser is headless Chromium through Playwright (one browser session for the whole job list, so
a full build takes seconds).  If that is not available the driver falls back, in order, to ``rsvg-convert``,
``inkscape`` and ImageMagick (``magick`` or ``convert``).  If nothing works it raises :class:`RasteriserError`
with instructions.

A job is a dict::

    {"svg": "<svg ...>...</svg>",   # markup (or "svg_path": an existing file)
     "png": Path,                   # output file
     "size": 192,                   # square output, pixels (or "width" + "height")
     "background": None}            # None = transparent, or a CSS colour such as "#7d7d86"
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = ["RasteriserError", "TOOLS", "available", "rasterise", "optimise_png"]

HERE = Path(__file__).resolve().parent
NODE_SCRIPT = HERE / "chromium_render.js"

#: preference order
TOOLS = ("chromium", "rsvg-convert", "inkscape", "magick", "convert")


class RasteriserError(RuntimeError):
    """No working rasteriser, or the chosen one failed."""


def _run(cmd: Sequence[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(list(cmd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
                          universal_newlines=True)


def _chromium_ok() -> bool:
    node = shutil.which("node")
    if not node:
        return False
    try:
        r = _run([node, "-e", "require.resolve('playwright')"], timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0


def available() -> List[str]:
    """Names of the rasterisers that look usable on this machine, best first."""
    found = []
    if _chromium_ok():
        found.append("chromium")
    for exe in ("rsvg-convert", "inkscape", "magick", "convert"):
        if shutil.which(exe):
            found.append(exe)
    return found


def _wh(job: Dict[str, Any]) -> tuple:
    return int(job.get("width") or job["size"]), int(job.get("height") or job["size"])


def _materialise(jobs: Sequence[Dict[str, Any]], tmp: Path) -> List[Dict[str, Any]]:
    """Write inline SVG to files so every tool gets a path."""
    out = []
    for i, job in enumerate(jobs):
        j = dict(job)
        if "svg_path" in j:
            j["svg"] = str(Path(j.pop("svg_path")).resolve())
        else:
            p = tmp / ("job_%04d.svg" % i)
            p.write_text(j["svg"], encoding="utf-8")
            j["svg"] = str(p)
        j["png"] = str(Path(j["png"]).resolve())
        Path(j["png"]).parent.mkdir(parents=True, exist_ok=True)
        out.append(j)
    return out


def _via_chromium(jobs: List[Dict[str, Any]], tmp: Path) -> None:
    jf = tmp / "jobs.json"
    jf.write_text(json.dumps(jobs), encoding="utf-8")
    r = _run([shutil.which("node") or "node", str(NODE_SCRIPT), str(jf)])
    if r.returncode != 0:
        raise RasteriserError("headless Chromium failed:\n" + (r.stderr or r.stdout).strip())


def _via_cli(tool: str, jobs: List[Dict[str, Any]]) -> None:
    exe = shutil.which(tool)
    if not exe:
        raise RasteriserError("%s is not installed" % tool)
    for j in jobs:
        w, h = _wh(j)
        bg = j.get("background")
        if tool == "rsvg-convert":
            cmd = [exe, "-w", str(w), "-h", str(h), "-o", j["png"]]
            if bg:
                cmd += ["-b", bg]
            cmd.append(j["svg"])
        elif tool == "inkscape":
            cmd = [exe, j["svg"], "--export-type=png", "--export-filename=" + j["png"],
                   "-w", str(w), "-h", str(h)]
            if bg:
                cmd += ["--export-background=" + bg, "--export-background-opacity=1"]
        else:  # magick / convert
            cmd = [exe, "-background", bg or "none", "-density", "%.3f" % (96.0 * w / 512.0), j["svg"],
                   "-resize", "%dx%d!" % (w, h), "-depth", "8", "PNG32:" + j["png"]]
        r = _run(cmd)
        if r.returncode != 0 or not os.path.exists(j["png"]):
            raise RasteriserError("%s failed on %s:\n%s" % (tool, j["svg"], (r.stderr or r.stdout).strip()))


def rasterise(jobs: Sequence[Dict[str, Any]], tool: Optional[str] = None) -> str:
    """Render every job; return the name of the rasteriser that did it.

    ``tool`` forces one of :data:`TOOLS`; by default the first available one is used, falling through to the
    next if it fails.
    """
    if not jobs:
        return tool or "none"
    candidates = [tool] if tool else available()
    if not candidates:
        raise RasteriserError(
            "No SVG rasteriser found. Install ONE of:\n"
            "  - Node.js + Playwright with Chromium (preferred):  npm i -g playwright && npx playwright install chromium\n"
            "  - librsvg:      rsvg-convert   (apt install librsvg2-bin / brew install librsvg)\n"
            "  - Inkscape 1.x: inkscape\n"
            "  - ImageMagick:  magick or convert (needs an SVG delegate)\n"
            "The committed PNGs under assets/sprites/ work without any of these; you only need a rasteriser "
            "to rebuild them.")
    errors = []
    with tempfile.TemporaryDirectory(prefix="pawtation-art-") as td:
        tmp = Path(td)
        ready = _materialise(jobs, tmp)
        for name in candidates:
            try:
                if name == "chromium":
                    if not _chromium_ok():
                        raise RasteriserError("node + playwright not found")
                    _via_chromium(ready, tmp)
                elif name in TOOLS:
                    _via_cli(name, ready)
                else:
                    raise RasteriserError("unknown rasteriser %r (choose from %s)" % (name, ", ".join(TOOLS)))
                return name
            except (RasteriserError, OSError, subprocess.SubprocessError) as exc:
                errors.append("%s: %s" % (name, exc))
    raise RasteriserError("Every rasteriser failed:\n  " + "\n  ".join(errors))


def optimise_png(paths: Sequence[Path]) -> bool:
    """Losslessly re-encode PNGs as 8-bit RGBA at maximum compression, if Pillow is installed.

    Returns ``False`` (and leaves the files alone) when Pillow is missing.  The pixels never change, so the
    sprites look identical either way; only the byte count differs.
    """
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return False
    for p in paths:
        with Image.open(str(p)) as im:
            rgba = im.convert("RGBA")
        rgba.save(str(p), format="PNG", optimize=True, compress_level=9)
    return True
