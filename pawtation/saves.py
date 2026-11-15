"""Read GameCube memory-card save exports (.gci) to know which games have saves and how recently touched.

Honest scope: a .gci directory header reliably gives game code, filename, last-modified time and size in
blocks. It does NOT tell you story progress. Real progress needs a per-game parser; register one in
PROGRESS_PARSERS (code4 -> function(bytes) -> str). Block count is used as a rough "how big is the save" hint.
"""
from __future__ import annotations

import struct
import time
from pathlib import Path

GC_EPOCH = 946684800  # 2000-01-01 UTC


HEADER = 0x40          # the memory-card directory entry that starts every .gci
BLOCK = 0x2000
PREFIX = {".gci": 0, ".gcs": 0x110}   # .gcs = GameShark wrapper: 0x110 extra bytes before the same .gci layout


def _text(b: bytes) -> str:
    b = b.split(b"\0")[0]
    for enc in ("ascii", "shift_jis"):
        try:
            return b.decode(enc).strip()
        except UnicodeDecodeError:
            pass
    return b.decode("ascii", "ignore").strip()


def parse_gci(path: Path) -> dict | None:
    """Header facts + the save's own two-line description ("comment"), which many games fill with honest progress
    text (file name, play time, chapter). Returns None if the file does not look like a save export."""
    path = Path(path)
    skip = PREFIX.get(path.suffix.lower())
    if skip is None:
        return None
    try:
        raw = path.read_bytes()[skip:]
    except OSError:
        return None
    if len(raw) < HEADER:
        return None
    code4 = raw[0:4].decode("ascii", "ignore")
    if not code4.isalnum() or len(code4) != 4:
        return None
    maker = raw[4:6].decode("ascii", "ignore")
    name = _text(raw[8:0x28])
    modtime = struct.unpack(">I", raw[0x28:0x2C])[0]
    blocks = struct.unpack(">H", raw[0x38:0x3A])[0]
    comment_at = struct.unpack(">I", raw[0x3C:0x40])[0]
    info = {"code4": code4, "maker": maker, "file": name, "blocks": blocks,
            "modified": GC_EPOCH + modtime, "path": str(path), "comment": []}
    data = raw[HEADER:]
    if comment_at != 0xFFFFFFFF and comment_at + 64 <= len(data):
        info["comment"] = [_text(data[comment_at:comment_at + 32]), _text(data[comment_at + 32:comment_at + 64])]
    parser = PROGRESS_PARSERS.get(code4)
    if parser:
        try:
            out = parser(raw)
            if out:
                info["progress"] = str(out)
        except Exception:        # never let a bad parser break the app
            pass
    return info


def scan_saves(folder: str) -> dict[str, dict]:
    """code4 -> most recently modified save info."""
    out: dict[str, dict] = {}
    if not folder or not Path(folder).is_dir():
        return out
    for p in sorted(Path(folder).rglob("*")):
        if p.suffix.lower() not in PREFIX or not p.is_file():
            continue
        info = parse_gci(p)
        if info and (info["code4"] not in out or info["modified"] > out[info["code4"]]["modified"]):
            out[info["code4"]] = info
    return out


def days_since(ts: float) -> int:
    return max(0, int((time.time() - ts) / 86400))


# Per-game progress parsers: code4 -> fn(raw_gci_bytes) -> str. EMPTY ON PURPOSE: none ship until a save layout is
# documented or checked against your own sample saves (see docs/MODDING.md "progress parsers"). Drop one in a
# plugin with `api.progress_parser("G8ME", fn)` - raw[0x40:] is the save data, raw[:0x40] the header above.
PROGRESS_PARSERS: dict = {}
