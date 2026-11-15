"""The Hidden World: a private compartment inside After Dark for the owner's own packs (docs/SPEC_V2.md section 9).

It ships empty and is inert until `python -m pawtation hw-setup` stores two salted PBKDF2-HMAC-SHA256 hashes in
state["hw"]: one for an 8-character reveal code (letters and digits) and one for a 10-digit passcode. The code and
the passcode themselves are never stored, logged, printed or kept in a reference by this module.

While After Dark is unlocked, typing the code into chat (check_code) brings up a bare passcode prompt; the right
passcode (try_open) opens the section for this process only. Packs whose pack.json says "rating": "hidden" are
read from disk only while it is open (packs(), and pawtation/cast.py asks is_open()). close() locks it again;
nothing about being open is ever saved, so every launch needs the code and the passcode again.

This hides, it does not protect: the source code and the state file show that the feature exists.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import re
import secrets
import time

from . import afterdark

ITERATIONS = 200000          # PBKDF2 rounds for new records; tests may lower it. Each record keeps its own count.
MIN_ITERATIONS = 1           # a stored count below this (or not a number) makes the record unusable
SALT_BYTES = 16
FREE_TRIES = 5               # wrong passcodes before the doubling wait starts
BASE_WAIT = 60               # seconds after the 5th wrong passcode; doubles with each further one
MAX_DOUBLINGS = 20           # caps the wait (about two years) so the arithmetic stays sane

_CODE = re.compile(r"^[A-Za-z0-9]{8}$")
_PASS = re.compile(r"^[0-9]{10}$")
_HEXRX = re.compile(r"^[0-9a-f]+$")

_OPEN = False                # process-wide; never saved

MSG_SET = "Saved."
MSG_CLEARED = "Cleared."
MSG_BAD_CODE = "The code must be exactly 8 letters or digits."
MSG_BAD_PASS = "The passcode must be exactly 10 digits."
MSG_MISMATCH = "The two entries did not match. Nothing was saved."


# ---------- records ----------
def _num(x) -> bool:
    try:
        return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
    except OverflowError:
        return False


def _hash(secret: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("ascii"), salt, iterations)


def _record(secret: str) -> dict:
    salt = secrets.token_bytes(SALT_BYTES)
    n = int(ITERATIONS)
    return {"salt": salt.hex(), "hash": _hash(secret, salt, n).hex(), "iter": n}


def _clean_record(rec):
    if not isinstance(rec, dict):
        return None
    salt, digest, n = rec.get("salt"), rec.get("hash"), rec.get("iter")
    if not (isinstance(salt, str) and isinstance(digest, str) and _HEXRX.match(salt) and _HEXRX.match(digest)
            and len(salt) == 2 * SALT_BYTES and len(digest) == 64):
        return None
    if not (isinstance(n, int) and not isinstance(n, bool) and n >= MIN_ITERATIONS):
        return None
    return {"salt": salt, "hash": digest, "iter": n}


def _matches(secret: str, rec: dict) -> bool:
    try:
        got = _hash(secret, bytes.fromhex(rec["salt"]), rec["iter"])
        return hmac.compare_digest(got, bytes.fromhex(rec["hash"]))
    except (ValueError, KeyError, TypeError, UnicodeError, OverflowError):
        return False


def clean_state(value):
    """state["hw"] in its one legal shape, or None (= not configured) for anything missing or damaged."""
    if not isinstance(value, dict):
        return None
    code, passcode = _clean_record(value.get("code")), _clean_record(value.get("pass"))
    if not (code and passcode):
        return None
    fails = value.get("fails")
    fails = fails if isinstance(fails, int) and not isinstance(fails, bool) and fails >= 0 else 0
    wait = value.get("wait_until")
    wait = float(wait) if _num(wait) and wait > 0 else 0
    return {"v": 1, "code": code, "pass": passcode, "fails": fails, "wait_until": wait}


def _hw(state):
    return clean_state(state.get("hw")) if isinstance(state, dict) else None


def is_configured(state) -> bool:
    return _hw(state) is not None


# ---------- setup ----------
def valid_code(text) -> bool:
    return isinstance(text, str) and bool(_CODE.match(text))


def valid_passcode(text) -> bool:
    return isinstance(text, str) and bool(_PASS.match(text))


def setup(state: dict, code, passcode) -> tuple:
    """Store salted hashes of a new code and passcode (replacing any earlier ones; the throttle starts fresh).
    Returns (ok, message); the message never contains either secret."""
    if not isinstance(state, dict):
        return False, "No state to save into."
    if not valid_code(code):
        return False, MSG_BAD_CODE
    if not valid_passcode(passcode):
        return False, MSG_BAD_PASS
    state["hw"] = {"v": 1, "code": _record(code), "pass": _record(passcode), "fails": 0, "wait_until": 0}
    return True, MSG_SET


def clear(state) -> None:
    """Remove the stored hashes (the feature becomes inert again) and lock the section in this process."""
    if isinstance(state, dict):
        state.pop("hw", None)
    close()


# ---------- reveal and open ----------
def check_code(state, text) -> bool:
    """Is `text` the reveal code? False unless the feature is configured, After Dark is unlocked and `text` is
    8 letters or digits. Constant-time comparison of the PBKDF2 hashes; never changes `state`."""
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not valid_code(text):
        return False
    hw = _hw(state)
    if hw is None or not afterdark.is_unlocked(state):
        return False
    return _matches(text, hw["code"])


def try_open(state, passcode, now=None) -> bool:
    """Open the section if `passcode` is right. While a wait is running every attempt is refused without even
    being hashed. A right passcode resets the count; from the 5th wrong one in a row the wait is
    60 * 2 ** (fails - 5) seconds. Updates state["hw"] in place: the caller saves the state."""
    global _OPEN
    hw = _hw(state)
    if hw is None or not afterdark.is_unlocked(state):
        return False
    now = float(now) if _num(now) else time.time()
    if now < hw["wait_until"]:
        return False
    ok = isinstance(passcode, str) and valid_passcode(passcode.strip()) and _matches(passcode.strip(), hw["pass"])
    if ok:
        hw["fails"], hw["wait_until"] = 0, 0
    else:
        hw["fails"] += 1
        if hw["fails"] >= FREE_TRIES:
            hw["wait_until"] = now + BASE_WAIT * 2 ** min(hw["fails"] - FREE_TRIES, MAX_DOUBLINGS)
    state["hw"] = hw
    if ok:
        _OPEN = True
        _refresh()
    return ok


def is_open() -> bool:
    return _OPEN


def close() -> None:
    """Lock the section in this process and drop everything the engine read from its packs."""
    global _OPEN
    was = _OPEN
    _OPEN = False
    if was:
        _refresh()


def _refresh() -> None:
    from . import cast                     # imported here: cast asks this module whether the section is open
    cast.reload()


def packs() -> list:
    """[{"name", "rating": "hidden", "path"}] for every pack folder whose pack.json says "rating": "hidden",
    sorted by folder. Always empty (and nothing is read from disk) unless the section is open."""
    if not _OPEN:
        return []
    from . import cast
    from .core import load_json
    try:
        folders = sorted(p for p in cast.PACKS_DIR.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))
    except OSError:
        return []
    out = []
    for folder in folders:
        meta = load_json(folder / "pack.json", {})
        if isinstance(meta, dict) and meta.get("rating") == "hidden":
            name = meta.get("name")
            name = " ".join(name.split()) if isinstance(name, str) and name.strip() else folder.name
            out.append({"name": name, "rating": "hidden", "path": folder})
    return out


GALLERY_EXTS = (".png", ".gif")


def gallery(pack_path) -> list:
    """The PNG and GIF files in a hidden pack's gallery/ folder, sorted by name. Empty unless open."""
    if not _OPEN:
        return []
    try:
        return sorted(p for p in (pack_path / "gallery").iterdir()
                      if p.is_file() and p.suffix.lower() in GALLERY_EXTS and not p.name.startswith("."))
    except (OSError, TypeError, AttributeError):
        return []
