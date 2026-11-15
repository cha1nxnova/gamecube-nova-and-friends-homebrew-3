#!/usr/bin/env python3
"""Build the committed art from its sources.  Dev-time only; the app never runs this.

    python3 art/build.py                 # every rig under art/rigs/ -> assets/sprites/
    python3 art/build.py --only nova     # just one character (repeatable: --only nova iggy)
    python3 art/build.py --contact       # also write art/out/contact_<id>.png for a visual check
    python3 art/build.py --check         # no rendering: report whether assets/ match the rigs
    python3 art/build.py --renders       # also run the low-poly renderer (art/lowpoly), if present

What it does, for each character it builds:

1. imports ``art/rigs/<id>.py`` and validates its API (``lib2d.validate_rig``),
2. calls ``draw(pose)`` for every frame of every animation, plus the portrait,
3. rasterises all of them in one go (headless Chromium, or a fallback: see ``lib2d/raster.py``) to
   ``assets/sprites/<id>/<size>/<anim>_<nn>.png`` for sizes 96 and 192, and ``<id>/512/portrait_00.png``,
4. losslessly re-compresses the PNGs when Pillow is installed,
5. deletes PNGs of frames that no longer exist in the rig.

It then ALWAYS regenerates ``assets/sprites/manifest.json`` from the rigs and what is really on disk, so a rig
added later only needs a rebuild.  Output is deterministic: no timestamps, sorted keys, fixed frame order;
the same rig on the same rasteriser gives the same bytes.

Hand-made art: put a file called ``HANDMADE`` in ``assets/sprites/<id>/`` and this script will never render
into or delete from that folder; the manifest entry is then built from the PNGs it finds there.
See docs/ART_PIPELINE.md.
"""
from __future__ import annotations

import argparse
import base64
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

ART = Path(__file__).resolve().parent
ROOT = ART.parent
if str(ART) not in sys.path:
    sys.path.insert(0, str(ART))

from lib2d import raster                 # noqa: E402  (after the sys.path tweak)
from lib2d.poses import validate_rig     # noqa: E402

RIGS = ART / "rigs"
OUT = ART / "out"
SPRITES = ROOT / "assets" / "sprites"
CAST_JSON = ROOT / "data" / "cast.json"

SIZES = (96, 192)          # the animated sprite sizes in the manifest
PORTRAIT_SIZE = 512
MANIFEST_VERSION = 1
FRAME_RE = re.compile(r"^([a-z0-9_]+)_(\d\d)\.png$")
DEFAULT_FPS = 8
LOOPING_BY_DEFAULT = ("idle", "talk", "sleep")


# ------------------------------------------------------------------ rigs

def rig_paths(rigs_dir: Path = RIGS) -> List[Path]:
    """Every rig module, sorted by name (files starting with an underscore are helpers, not rigs)."""
    if not rigs_dir.is_dir():
        return []
    return sorted(p for p in rigs_dir.glob("*.py") if not p.name.startswith("_"))


def load_rig(path: Path) -> Any:
    """Import one rig file as a module (``art/`` is on sys.path so it can ``import lib2d``)."""
    spec = importlib.util.spec_from_file_location("pawtation_rig_" + path.stem, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load rig %s" % path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def cameo_ids(cast_json: Path = CAST_JSON) -> List[str]:
    """Ids whose role is "cameo" in data/cast.json (they need fewer animations).  Missing file -> none."""
    try:
        data = json.loads(cast_json.read_text(encoding="utf-8"))
        chars = data.get("characters", {})
        return sorted(k for k, v in chars.items() if isinstance(v, dict) and v.get("role") == "cameo")
    except (OSError, ValueError, AttributeError):
        return []


def load_rigs(only: Optional[Sequence[str]] = None, rigs_dir: Path = RIGS) -> Dict[str, Any]:
    """``{CHAR_ID: module}`` for every rig (or the ones named in ``only``).  Invalid rigs raise SystemExit."""
    cameos = cameo_ids()
    rigs: Dict[str, Any] = {}
    for path in rig_paths(rigs_dir):
        mod = load_rig(path)
        cid = getattr(mod, "CHAR_ID", None)
        if cid != path.stem:
            raise SystemExit("%s: CHAR_ID is %r but the file is %s.py; they must match" % (path, cid, path.stem))
        problems = validate_rig(mod, cameo=bool(getattr(mod, "CAMEO", cid in cameos)))
        if problems:
            raise SystemExit("%s is not a valid rig:\n  - %s" % (path, "\n  - ".join(problems)))
        rigs[cid] = mod
    if only:
        missing = [c for c in only if c not in rigs]
        if missing:
            raise SystemExit("no rig for: %s (have: %s)" % (", ".join(missing), ", ".join(sorted(rigs)) or "none"))
    return rigs


def frame_rel(cid: str, anim_name: str, index: int) -> str:
    """Manifest path of one frame, with the literal ``{size}`` token."""
    return "%s/{size}/%s_%02d.png" % (cid, anim_name, index)


def portrait_rel(cid: str) -> str:
    return "%s/%d/portrait_00.png" % (cid, PORTRAIT_SIZE)


def is_handmade(cid: str, sprites: Path = SPRITES) -> bool:
    return (sprites / cid / "HANDMADE").exists()


# ------------------------------------------------------------------ rendering

def frame_jobs(cid: str, mod: Any, sprites: Path = SPRITES) -> List[Dict[str, Any]]:
    """One rasteriser job per frame per size, plus the portrait."""
    jobs: List[Dict[str, Any]] = []
    for name, a in mod.ANIMS.items():
        for i, pose in enumerate(a["frames"]):
            svg = mod.draw(pose)
            for size in SIZES:
                jobs.append({"svg": svg, "size": size,
                             "png": sprites / frame_rel(cid, name, i).replace("{size}", str(size))})
    portrait = getattr(mod, "PORTRAIT", None)
    if portrait is None:
        first = next(iter(mod.ANIMS.values()))
        portrait = first["frames"][0]
    jobs.append({"svg": mod.draw(portrait), "size": PORTRAIT_SIZE, "png": sprites / portrait_rel(cid)})
    return jobs


def remove_stale(cid: str, keep: Sequence[Path], sprites: Path = SPRITES) -> List[Path]:
    """Delete generated PNGs of this character that the rig no longer produces."""
    keep_set = {Path(p).resolve() for p in keep}
    removed = []
    base = sprites / cid
    if not base.is_dir():
        return removed
    for size_dir in sorted(p for p in base.iterdir() if p.is_dir() and p.name.isdigit()):
        for png in sorted(size_dir.glob("*.png")):
            if FRAME_RE.match(png.name) and png.resolve() not in keep_set:
                png.unlink()
                removed.append(png)
        if not any(size_dir.iterdir()):
            size_dir.rmdir()
    return removed


def build_character(cid: str, mod: Any, tool: Optional[str] = None, optimise: bool = True,
                    sprites: Path = SPRITES, log: Any = print) -> Dict[str, Any]:
    """Render one character.  Returns a small report dict."""
    if is_handmade(cid, sprites):
        log("  %s: HANDMADE marker found, not rendering" % cid)
        return {"id": cid, "skipped": True}
    jobs = frame_jobs(cid, mod, sprites)
    used = raster.rasterise(jobs, tool=tool)
    pngs = [Path(j["png"]) for j in jobs]
    squeezed = raster.optimise_png(pngs) if optimise else False
    removed = remove_stale(cid, pngs, sprites)
    total = sum(p.stat().st_size for p in pngs)
    log("  %s: %d PNGs via %s%s, %.1f KB%s" % (
        cid, len(pngs), used, " + Pillow recompress" if squeezed else "", total / 1024.0,
        (", removed %d stale" % len(removed)) if removed else ""))
    return {"id": cid, "files": pngs, "bytes": total, "rasteriser": used, "optimised": squeezed}


# ------------------------------------------------------------------ manifest

def _disk_anims(cid: str, sprites: Path) -> Dict[str, int]:
    """Animations found on disk for a character: name -> frame count (complete at every size only)."""
    per_size: List[Dict[str, List[int]]] = []
    for size in SIZES:
        found: Dict[str, List[int]] = {}
        d = sprites / cid / str(size)
        if d.is_dir():
            for png in d.glob("*.png"):
                m = FRAME_RE.match(png.name)
                if m:
                    found.setdefault(m.group(1), []).append(int(m.group(2)))
        per_size.append(found)
    out: Dict[str, int] = {}
    for name, idx in per_size[0].items():
        idx = sorted(idx)
        if idx != list(range(len(idx))):
            continue                                   # gaps in the numbering: not usable
        if all(sorted(other.get(name, [])) == idx for other in per_size[1:]):
            out[name] = len(idx)
    return out


def _meta_file(cid: str, sprites: Path) -> Dict[str, Any]:
    """Optional ``assets/sprites/<id>/anims.json``: ``{"idle": {"fps": 6, "loop": true}}`` for hand-made art."""
    try:
        data = json.loads((sprites / cid / "anims.json").read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def make_manifest(rigs: Optional[Dict[str, Any]] = None, sprites: Path = SPRITES,
                  warn: Any = None) -> Dict[str, Any]:
    """The manifest for what is on disk right now.

    For a character with a rig, animations come from the rig (order, fps, loop, frame count) and are listed
    only when every frame exists at every size.  Characters without a rig, or marked HANDMADE, are described
    from the PNGs found in their folder.
    """
    rigs = load_rigs() if rigs is None else rigs
    warn = warn or (lambda msg: None)
    chars: Dict[str, Any] = {}
    ids = set(rigs)
    if sprites.is_dir():
        ids.update(p.name for p in sprites.iterdir() if p.is_dir())
    for cid in sorted(ids):
        mod = rigs.get(cid)
        entry: Dict[str, Any] = {"anims": {}}
        if mod is not None and not is_handmade(cid, sprites):
            entry["height"] = float(mod.HEIGHT)
            for name, a in mod.ANIMS.items():
                rels = [frame_rel(cid, name, i) for i in range(len(a["frames"]))]
                missing = [r for r in rels for s in SIZES
                           if not (sprites / r.replace("{size}", str(s))).is_file()]
                if missing:
                    warn("%s/%s: %d frame file(s) missing, animation left out (rebuild with --only %s)"
                         % (cid, name, len(missing), cid))
                    continue
                entry["anims"][name] = {"fps": int(a["fps"]), "loop": bool(a["loop"]), "frames": rels}
        else:
            meta = _meta_file(cid, sprites)
            if mod is not None:
                entry["height"] = float(mod.HEIGHT)
            for name, count in sorted(_disk_anims(cid, sprites).items()):
                rig_anim = (mod.ANIMS.get(name) if mod is not None else None) or {}
                m = meta.get(name) if isinstance(meta.get(name), dict) else {}
                fps = m.get("fps", rig_anim.get("fps", DEFAULT_FPS))
                loop = m.get("loop", rig_anim.get("loop", name in LOOPING_BY_DEFAULT))
                entry["anims"][name] = {"fps": int(fps), "loop": bool(loop),
                                        "frames": [frame_rel(cid, name, i) for i in range(count)]}
        if (sprites / portrait_rel(cid)).is_file():
            entry["portrait"] = portrait_rel(cid)
        if entry["anims"]:
            chars[cid] = entry
    return {"version": MANIFEST_VERSION, "sizes": list(SIZES), "characters": chars}


def manifest_text(manifest: Dict[str, Any]) -> str:
    """Stable JSON: sorted character ids, animations in rig order, one frame list per line."""
    lines = ["{", ' "version": %d,' % manifest["version"], ' "sizes": %s,' % json.dumps(manifest["sizes"]),
             ' "characters": {']
    chars = manifest["characters"]
    for ci, cid in enumerate(sorted(chars)):
        c = chars[cid]
        lines.append("  %s: {" % json.dumps(cid))
        for key in ("height", "portrait"):
            if key in c:
                lines.append("   %s: %s," % (json.dumps(key), json.dumps(c[key])))
        lines.append('   "anims": {')
        names = list(c["anims"])
        for ai, name in enumerate(names):
            a = c["anims"][name]
            lines.append("    %s: {\"fps\": %d, \"loop\": %s, \"frames\": %s}%s" % (
                json.dumps(name), a["fps"], json.dumps(a["loop"]), json.dumps(a["frames"]),
                "," if ai < len(names) - 1 else ""))
        lines.append("   }")
        lines.append("  }%s" % ("," if ci < len(chars) - 1 else ""))
    lines += [" }", "}"]
    return "\n".join(lines) + "\n"


def write_manifest(manifest: Dict[str, Any], sprites: Path = SPRITES) -> Path:
    sprites.mkdir(parents=True, exist_ok=True)
    path = sprites / "manifest.json"
    path.write_text(manifest_text(manifest), encoding="utf-8")
    return path


def check(rigs: Dict[str, Any], sprites: Path = SPRITES) -> List[str]:
    """Differences between the committed manifest and what the rigs + disk say it should be."""
    problems: List[str] = []
    want = make_manifest(rigs, sprites, warn=problems.append)
    try:
        have = json.loads((sprites / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return ["manifest.json unreadable: %s" % exc]
    if have != want:
        problems.append("assets/sprites/manifest.json is out of date: run  python3 art/build.py")
    for cid, mod in sorted(rigs.items()):
        if cid not in want["characters"] and not is_handmade(cid, sprites):
            problems.append("%s has a rig but no complete sprites: run  python3 art/build.py --only %s"
                            % (cid, cid))
    return problems


# ------------------------------------------------------------------ contact sheet

GREY = "#7d7d86"
NAVY_BG = "#16172e"


def _data_uri(png: Path) -> str:
    return "data:image/png;base64," + base64.b64encode(png.read_bytes()).decode("ascii")


def contact_sheet(cid: str, manifest: Dict[str, Any], sprites: Path = SPRITES, out_dir: Path = OUT,
                  tool: Optional[str] = None) -> Optional[Path]:
    """All frames of one character, actual pixels, on mid-grey and on dark navy -> art/out/contact_<id>.png."""
    entry = manifest["characters"].get(cid)
    if not entry:
        return None
    big, small = max(SIZES), min(SIZES)
    cols = 8
    cell, label_h, pad = big + 4, 18, 12
    blocks: List[Tuple[str, List[str]]] = []
    for name, a in entry["anims"].items():
        title = "%s  %d fps%s" % (name, a["fps"], "  loop" if a["loop"] else "")
        blocks.append((title, a["frames"]))
    # pack whole animations into rows of at most `cols` frames
    rows: List[List[Tuple[str, List[str]]]] = []
    used = cols
    for title, frames in blocks:
        n = min(len(frames), cols)
        if used + n > cols:
            rows.append([])
            used = 0
        rows[-1].append((title, frames))
        used += n
    left_w = cols * cell
    small_cols = 5
    right_w = max(PORTRAIT_SIZE + 4, small_cols * (small + 4))
    all_frames = [f for _, fr in blocks for f in fr]
    small_rows = (len(all_frames) + small_cols - 1) // small_cols
    panel_h = max(len(rows) * (cell + label_h), PORTRAIT_SIZE + 8 + label_h + small_rows * (small + 4)) + pad
    width = pad + left_w + pad + right_w + pad
    height = 2 * (panel_h + pad) + pad
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
             % (width, height, width, height)]
    for pi, (bg, fg) in enumerate(((GREY, "#ffffff"), (NAVY_BG, "#c9cbe6"))):
        y0 = pad + pi * (panel_h + pad)
        parts.append('<rect x="0" y="%d" width="%d" height="%d" fill="%s"/>' % (y0 - pad // 2, width,
                                                                            panel_h + pad, bg))
        y = y0
        for row in rows:
            x = pad
            for title, frames in row:
                parts.append('<text x="%d" y="%d" font-family="sans-serif" font-size="13" fill="%s">%s</text>'
                             % (x + 2, y + 13, fg, title))
                for f in frames[:cols]:
                    png = sprites / f.replace("{size}", str(big))
                    parts.append('<image x="%d" y="%d" width="%d" height="%d" href="%s"/>'
                                 % (x + 2, y + label_h, big, big, _data_uri(png)))
                    x += cell
            y += cell + label_h
        # right column: portrait, then every frame at the small size
        rx = pad + left_w + pad
        ry = y0
        if entry.get("portrait"):
            parts.append('<text x="%d" y="%d" font-family="sans-serif" font-size="13" fill="%s">portrait '
                         '%d px</text>' % (rx + 2, ry + 13, fg, PORTRAIT_SIZE))
            parts.append('<image x="%d" y="%d" width="%d" height="%d" href="%s"/>'
                         % (rx + 2, ry + label_h, PORTRAIT_SIZE, PORTRAIT_SIZE,
                            _data_uri(sprites / entry["portrait"])))
        ry += PORTRAIT_SIZE + 8 + label_h
        for i, f in enumerate(all_frames):
            png = sprites / f.replace("{size}", str(small))
            parts.append('<image x="%d" y="%d" width="%d" height="%d" href="%s"/>'
                         % (rx + 2 + (i % small_cols) * (small + 4), ry + (i // small_cols) * (small + 4),
                            small, small, _data_uri(png)))
    parts.append("</svg>")
    out = out_dir / ("contact_%s.png" % cid)
    raster.rasterise([{"svg": "".join(parts), "png": out, "width": width, "height": height,
                       "background": GREY}], tool=tool)
    return out


# ------------------------------------------------------------------ low-poly hook

def run_renders(only: Optional[Sequence[str]] = None) -> int:
    """``--renders``: hand over to the 3D pipeline (art/lowpoly/build.py, owned by the 3D artist)."""
    script = ART / "lowpoly" / "build.py"
    if not script.is_file():
        print("low-poly renders: art/lowpoly/build.py not found; nothing to do (see docs/ART_LOWPOLY.md)")
        return 0
    cmd = [sys.executable, str(script)]
    for cid in only or []:
        cmd += ["--only", cid]
    print("low-poly renders: " + " ".join(cmd[1:]))
    return subprocess.call(cmd)


# ------------------------------------------------------------------ command line

def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Build Pawtation's sprite art from the rigs under art/rigs/.")
    ap.add_argument("--only", nargs="+", metavar="ID", help="build just these characters")
    ap.add_argument("--contact", action="store_true", help="also write art/out/contact_<id>.png")
    ap.add_argument("--check", action="store_true", help="do not render; exit 1 if assets are out of date")
    ap.add_argument("--list", action="store_true", help="list rigs, animations and frame counts, then exit")
    ap.add_argument("--rasteriser", choices=raster.TOOLS, help="force one rasteriser instead of auto-detect")
    ap.add_argument("--no-optimise", action="store_true", help="skip the lossless Pillow recompression")
    ap.add_argument("--renders", action="store_true", help="also build the low-poly renders (art/lowpoly)")
    args = ap.parse_args(argv)

    rigs = load_rigs(args.only)
    if args.list:
        for cid, mod in sorted(rigs.items()):
            total = sum(len(a["frames"]) for a in mod.ANIMS.values())
            print("%s  height %.2f  %d frames" % (cid, mod.HEIGHT, total))
            for name, a in mod.ANIMS.items():
                print("    %-11s %2d frames  %2d fps  %s" % (name, len(a["frames"]), a["fps"],
                                                           "loop" if a["loop"] else "once"))
        return 0
    if args.check:
        problems = check(rigs)
        for msg in problems:
            print("STALE: " + msg)
        if not problems:
            print("ok: assets/sprites matches the rigs")
        return 1 if problems else 0

    todo = sorted(args.only) if args.only else sorted(rigs)
    print("rasterisers available: %s" % (", ".join(raster.available()) or "none"))
    reports = []
    try:
        for cid in todo:
            reports.append(build_character(cid, rigs[cid], tool=args.rasteriser,
                                           optimise=not args.no_optimise))
    except raster.RasteriserError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2
    manifest = make_manifest(rigs, warn=lambda m: print("warning: " + m))
    path = write_manifest(manifest)
    print("manifest: %s (%d character(s))" % (path.relative_to(ROOT), len(manifest["characters"])))
    if args.contact:
        try:
            for cid in todo:
                sheet = contact_sheet(cid, manifest, tool=args.rasteriser)
                if sheet:
                    print("contact sheet: %s" % sheet.relative_to(ROOT))
        except raster.RasteriserError as exc:
            print("error: contact sheet failed: %s" % exc, file=sys.stderr)
            return 2
    total = sum(r.get("bytes", 0) for r in reports)
    if total:
        print("total: %.1f KB in %d files" % (total / 1024.0, sum(len(r.get("files", [])) for r in reports)))
    if args.renders:
        return run_renders(args.only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
