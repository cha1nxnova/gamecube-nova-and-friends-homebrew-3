"""Read the GameCube disc header (game ID, disc number, internal title) out of disc image containers.

Supported: plain .iso/.gcm, .ciso (Dolphin/Swiss "CISO"), .gcz (Dolphin compressed), .rvz/.wia.
Only the first few hundred bytes of the disc are ever decoded; nothing is written, nothing is unpacked to disk.
Layouts follow Dolphin's DiscIO sources (see docs/RESEARCH_NOTES.md for citations).

Add a container: write `_read_xxx(f) -> bytes | None` returning the first HEADER_LEN bytes of the *disc*,
then register its extension in READERS. Everything else (scan, planner, sync) picks it up automatically.
"""
from __future__ import annotations

import re
import struct
import zlib
from pathlib import Path

HEADER_LEN = 0x60            # ID (6) + disc no + version + ... + magic @0x1C + internal name @0x20 (0x40 bytes)
GC_MAGIC = 0xC2339F3D        # big-endian word at 0x1C on every retail GameCube disc

CISO_HEADER_SIZE = 0x8000
GCZ_MAGIC = 0xB10BC001
WIA_DISC_HEADER_OFFSET = 0x58   # WIA/RVZ header 1 is 0x48 bytes; header 2 has 0x10 bytes before the disc-header copy


def _read_plain(f):
    return f.read(HEADER_LEN)


def _read_ciso(f):
    head = f.read(8)
    if len(head) < 8 or head[:4] != b"CISO":
        return None
    block_map_first = f.read(1)
    if block_map_first != b"\x01":           # block 0 not stored: no disc header to read
        return None
    f.seek(CISO_HEADER_SIZE)                  # stored blocks follow the 0x8000-byte header in order
    return f.read(HEADER_LEN)


def _read_gcz(f):
    head = f.read(32)
    if len(head) < 32:
        return None
    magic, _sub, _csize, _dsize, block_size, num_blocks = struct.unpack("<IIQQII", head)
    if magic != GCZ_MAGIC or num_blocks == 0 or block_size < HEADER_LEN:
        return None
    ptrs = f.read(16 if num_blocks > 1 else 8)
    first = struct.unpack("<Q", ptrs[:8])[0]
    data_start = 32 + num_blocks * 12         # u64 pointer + u32 hash per block
    stored_raw = bool(first >> 63)
    first &= (1 << 63) - 1
    f.seek(data_start + first)
    if stored_raw:
        return f.read(HEADER_LEN)
    if num_blocks > 1:
        nxt = struct.unpack("<Q", ptrs[8:16])[0] & ((1 << 63) - 1)
        comp_len = max(0, nxt - first)
    else:
        comp_len = 1 << 20
    blob = f.read(min(comp_len, 1 << 20))
    try:
        return zlib.decompressobj().decompress(blob, HEADER_LEN)
    except zlib.error:
        return None


def _read_wia(f):
    if f.read(4) not in (b"WIA\x01", b"RVZ\x01"):
        return None
    f.seek(WIA_DISC_HEADER_OFFSET)
    return f.read(HEADER_LEN)


READERS = {".iso": _read_plain, ".gcm": _read_plain, ".ciso": _read_ciso, ".gcz": _read_gcz,
           ".rvz": _read_wia, ".wia": _read_wia}


def parse_header(head: bytes | None) -> dict | None:
    """Decode raw disc-header bytes. Returns None unless the first 6 bytes look like a game ID."""
    if not head or len(head) < 0x40:
        return None
    code = head[:6].decode("ascii", "ignore")
    if not re.fullmatch(r"[A-Z0-9]{6}", code):
        return None
    title = head[0x20:0x60].split(b"\0")[0].decode("ascii", "ignore").strip()
    return {"code6": code, "disc": head[6] + 1, "version": head[7], "title": title,
            "magic_ok": struct.unpack(">I", head[0x1C:0x20])[0] == GC_MAGIC}


def read_header(path) -> dict | None:
    """{"code6","disc" (1-based),"version","title","magic_ok"} or None if unreadable/unknown container."""
    path = Path(path)
    reader = READERS.get(path.suffix.lower())
    if not reader:
        return None
    try:
        with open(path, "rb") as f:
            return parse_header(reader(f))
    except (OSError, struct.error):
        return None


_DISC_IN_NAME = re.compile(r"(?:dis[ck]|cd)[\s_\-]*([1-9])\b", re.I)


def disc_from_filename(name: str) -> int:
    """'Game (Disc 2).iso' -> 2. Defaults to 1. Used when a header cannot be read."""
    m = _DISC_IN_NAME.search(Path(name).stem)
    return int(m.group(1)) if m else 1
