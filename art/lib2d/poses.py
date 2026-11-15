"""The pose / animation model.

A **pose** is a plain dict of parameters that a rig's ``draw(pose)`` understands; missing keys take the rig's
defaults, so a pose only lists what differs from the neutral stand.  An **animation** is::

    {"fps": 6, "loop": True, "frames": [pose, pose, ...]}

and a rig module exposes ``ANIMS = {"idle": {...}, "blink": {...}, ...}``.  The helpers here build frame lists
without hand-writing every dict.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence

from .geom import ease, lerp

__all__ = ["pose", "tween", "cycle", "hold", "anim", "REQUIRED_ANIMS", "CAMEO_ANIMS", "validate_rig"]

Pose = Dict[str, Any]

#: animations every main / guest character must have (SPEC_V2 section 5), with the allowed frame counts
REQUIRED_ANIMS = {
    "idle": (4, 8), "blink": (2, 3), "talk": (2, 4), "happy": (4, 6), "sleep": (2, 4), "wave": (4, 6),
    "look_left": (1, 1), "look_right": (1, 1), "special": (4, 8),
}
#: cameo characters only need these
CAMEO_ANIMS = {"idle": (2, 8), "talk": (2, 4)}


def pose(base: Optional[Pose] = None, **changes: Any) -> Pose:
    """A new pose: ``base`` (not modified) with ``changes`` on top."""
    out = dict(base or {})
    out.update(changes)
    return out


def _mix(a: Any, b: Any, t: float) -> Any:
    if isinstance(a, bool) or isinstance(b, bool):
        return a if t < 0.5 else b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return lerp(float(a), float(b), t)
    if (isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)) and len(a) == len(b)
            and all(isinstance(v, (int, float)) for v in list(a) + list(b))):
        return tuple(lerp(float(x), float(y), t) for x, y in zip(a, b))
    return a if t < 0.5 else b


def tween(a: Pose, b: Pose, n: int, easing: bool = True, defaults: Optional[Pose] = None) -> List[Pose]:
    """``n`` poses from ``a`` to ``b`` inclusive.

    Numbers (and tuples of numbers) are interpolated; everything else (eye state, mouth shape, props) switches
    from ``a``'s value to ``b``'s halfway through.  A key present in only one pose is interpolated against
    ``defaults[key]`` when given, otherwise it simply appears in the frames nearer to the pose that has it.
    """
    if n <= 1:
        return [dict(b)]
    out = []
    keys = list(a.keys()) + [k for k in b.keys() if k not in a]
    for i in range(n):
        t = i / float(n - 1)
        if easing:
            t = ease(t)
        p: Pose = {}
        for k in keys:
            va = a.get(k, (defaults or {}).get(k))
            vb = b.get(k, (defaults or {}).get(k))
            if va is None and vb is None:
                continue
            if va is None:
                if t >= 0.5:
                    p[k] = vb
            elif vb is None:
                if t < 0.5:
                    p[k] = va
            else:
                p[k] = _mix(va, vb, t)
        out.append(p)
    return out


def cycle(i: int, n: int, amp: float = 1.0, phase: float = 0.0) -> float:
    """``amp * sin`` of frame ``i`` in a seamless ``n``-frame loop (``phase`` in turns, 0.25 = start at peak)."""
    return amp * math.sin(2.0 * math.pi * (i / float(n) + phase))


def hold(p: Pose, n: int) -> List[Pose]:
    """The same pose ``n`` times (a pause)."""
    return [dict(p) for _ in range(n)]


def anim(frames: Sequence[Pose], fps: int = 8, loop: bool = True) -> Dict[str, Any]:
    """Bundle frames into the animation dict a rig's ``ANIMS`` holds."""
    return {"fps": int(fps), "loop": bool(loop), "frames": [dict(f) for f in frames]}


def validate_rig(mod: Any, cameo: bool = False) -> List[str]:
    """Problems with a rig module's public API, as human-readable strings (empty list = fine).

    Used by ``art/build.py`` before rendering and by ``tests/test_sprites.py``.
    """
    problems: List[str] = []
    cid = getattr(mod, "CHAR_ID", None)
    if not isinstance(cid, str) or not cid or cid != cid.lower() or not cid.replace("_", "").isalnum():
        problems.append("CHAR_ID must be a lowercase id string")
    h = getattr(mod, "HEIGHT", None)
    if not isinstance(h, (int, float)) or not (0.2 <= float(h) <= 1.0):
        problems.append("HEIGHT must be a number in 0.2..1.0 (Nova = 1.0)")
    if not callable(getattr(mod, "draw", None)):
        problems.append("draw(pose) is missing")
    anims = getattr(mod, "ANIMS", None)
    if not isinstance(anims, dict) or not anims:
        problems.append("ANIMS must be a non-empty dict")
        return problems
    for name, a in anims.items():
        if not isinstance(name, str) or not name.replace("_", "").isalnum() or name != name.lower():
            problems.append("animation name %r must be lowercase letters, digits, underscores" % (name,))
        if not isinstance(a, dict) or not isinstance(a.get("frames"), list) or not a["frames"]:
            problems.append("%s: needs a non-empty 'frames' list" % name)
            continue
        if not isinstance(a.get("fps"), int) or not (1 <= a["fps"] <= 30):
            problems.append("%s: fps must be an int in 1..30" % name)
        if not isinstance(a.get("loop"), bool):
            problems.append("%s: loop must be a bool" % name)
        if len(a["frames"]) > 100:
            problems.append("%s: more than 100 frames" % name)
        if not all(isinstance(f, dict) for f in a["frames"]):
            problems.append("%s: every frame must be a pose dict" % name)
    override = getattr(mod, "REQUIRED", None)       # optional: a rig may state its own requirements
    if isinstance(override, dict):
        need = override                              # e.g. REQUIRED = {} for the props pseudo-character
    else:
        need = CAMEO_ANIMS if cameo else REQUIRED_ANIMS
    for name, (lo, hi) in need.items():
        if name not in anims:
            problems.append("required animation %r is missing" % name)
        elif isinstance(anims[name], dict) and isinstance(anims[name].get("frames"), list):
            n = len(anims[name]["frames"])
            if not (lo <= n <= hi):
                problems.append("%s: %d frames, expected %d..%d" % (name, n, lo, hi))
    return problems
