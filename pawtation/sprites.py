"""Runtime sprite loader (standard library only; never imports tkinter).

Reads ``assets/sprites/manifest.json`` and ``assets/renders/manifest.json``.  Every function returns an empty
result (``[]``, ``{}``, ``None``, ``False``) instead of raising when a manifest or file is missing or corrupt.
Tests can patch :data:`ASSETS` or pass ``root=``.  See docs/ART_PIPELINE.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .paths import BUNDLE

ASSETS = BUNDLE / "assets"
#: pseudo-character holding decorations (sparkle, heart, ...); not listed by characters()
PROPS = "props"


def _root(root: Optional[Path]) -> Path:
    return Path(root) if root is not None else Path(ASSETS)


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError):
        return None


def load_manifest(root: Optional[Path] = None) -> Dict[str, Any]:
    """The sprite manifest as a dict with at least ``characters`` (dict) and ``sizes`` (list); else empty."""
    data = _read(_root(root) / "sprites" / "manifest.json")
    if not isinstance(data, dict) or not isinstance(data.get("characters"), dict):
        return {}
    chars = {k: v for k, v in data["characters"].items()
             if isinstance(k, str) and isinstance(v, dict) and isinstance(v.get("anims"), dict)}
    sizes = [s for s in data.get("sizes", []) if isinstance(s, int) and not isinstance(s, bool)]
    return {"version": data.get("version", 1), "sizes": sizes, "characters": chars}


def _anim(char: str, anim: str, root: Optional[Path]) -> Optional[Dict[str, Any]]:
    c = load_manifest(root).get("characters", {}).get(char)
    a = c["anims"].get(anim) if c else None
    if isinstance(a, dict) and isinstance(a.get("frames"), list):
        return a
    return None


def has(char: str, root: Optional[Path] = None) -> bool:
    """True when the manifest lists at least one animation for ``char``."""
    c = load_manifest(root).get("characters", {}).get(char)
    return bool(c and c["anims"])


def characters(root: Optional[Path] = None) -> List[str]:
    """Sorted ids of characters with sprites (the ``props`` pseudo-character is not included)."""
    return sorted(k for k, v in load_manifest(root).get("characters", {}).items()
                  if v["anims"] and k != PROPS)


def available_sizes(root: Optional[Path] = None) -> List[int]:
    """Sprite sizes (px) the manifest declares, ascending."""
    return sorted(set(load_manifest(root).get("sizes", [])))


def anim_info(char: str, anim: str, root: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """``{"fps", "loop", "count"}`` for one animation, or None if it does not exist."""
    a = _anim(char, anim, root)
    count = sum(1 for f in a["frames"] if isinstance(f, str)) if a else 0
    if not count:
        return None
    fps = a.get("fps")
    fps = int(fps) if isinstance(fps, (int, float)) and not isinstance(fps, bool) and fps > 0 else 8
    return {"fps": fps, "loop": bool(a.get("loop", False)), "count": count}


def _pack_override(rel: str, char: str, size: int, pack_dirs: Sequence[Any]) -> Optional[Path]:
    name = Path(rel).name
    for pd in pack_dirs:
        p = Path(pd) / "sprites" / char / str(size) / name
        if p.is_file():
            return p
    return None


def frames(char: str, anim: str, size: int, pack_dirs: Sequence[Any] = (),
           root: Optional[Path] = None) -> List[Path]:
    """Existing PNG paths for the animation at ``size``, in order.

    For each frame, ``<pack>/sprites/<char>/<size>/<anim>_<nn>.png`` from the first pack in ``pack_dirs`` that
    has it wins over the built-in file.  Frames whose file is missing are skipped; any problem -> ``[]``.
    """
    a = _anim(char, anim, root)
    if a is None:
        return []
    base = _root(root) / "sprites"
    out: List[Path] = []
    for rel in a["frames"]:
        if not isinstance(rel, str):
            continue
        over = _pack_override(rel, char, size, pack_dirs)
        if over is not None:
            out.append(over)
            continue
        p = base / rel.replace("{size}", str(int(size)))
        if p.is_file():
            out.append(p)
    return out


# ------------------------------------------------------------------ low-poly renders

def _renders(root: Optional[Path]) -> Dict[str, Any]:
    data = _read(_root(root) / "renders" / "manifest.json")
    r = data.get("renders") if isinstance(data, dict) else None
    return r if isinstance(r, dict) else {}


def render(name: str, root: Optional[Path] = None) -> Optional[Path]:
    """Path of a still render (``file``), or of the first frame of a frame strip; None if absent."""
    e = _renders(root).get(name)
    if not isinstance(e, dict):
        return None
    rel = e.get("file")
    if not isinstance(rel, str) and isinstance(e.get("frames"), list) and e["frames"]:
        rel = e["frames"][0]
    if not isinstance(rel, str):
        return None
    p = _root(root) / "renders" / rel
    return p if p.is_file() else None


def render_frames(name: str, root: Optional[Path] = None) -> Tuple[List[Path], int]:
    """``(existing frame paths, fps)`` of an animated render; a still gives one frame; unknown -> ``([], 0)``."""
    e = _renders(root).get(name)
    if not isinstance(e, dict):
        return [], 0
    fps = e.get("fps")
    fps = int(fps) if isinstance(fps, (int, float)) and not isinstance(fps, bool) and fps > 0 else 12
    rels = e.get("frames") if isinstance(e.get("frames"), list) else [e.get("file")]
    base = _root(root) / "renders"
    out = [base / r for r in rels if isinstance(r, str) and (base / r).is_file()]
    return out, (fps if out else 0)
