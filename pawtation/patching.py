"""Mod bench: apply a patch to a COPY of one of your own disc images (or any file). The original is never modified.

Built in (pure Python): BPS (.bps, checksummed, any size) and IPS (.ips, offsets below 16 MB, so mostly for small
files such as an extracted main.dol). xdelta/VCDIFF (.xdelta, .vcdiff) is handed to an `xdelta3` program if one is
installed. Patches come from you; Pawtation ships none and downloads none.

Add a format: write `apply_xxx(src: Path, patch: Path, out: Path) -> dict` and register it in FORMATS.
"""
from __future__ import annotations

import mmap
import os
import shutil
import subprocess
import zlib
from pathlib import Path


class PatchError(Exception):
    pass


MAX_OUTPUT = 16 * 1024**3      # far above any GameCube image (1.46 GB); stops a bad patch from filling the disk


def crc32_file(path: Path) -> int:
    crc = 0
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 << 20), b""):
            crc = zlib.crc32(chunk, crc)
    return crc


# ---------- BPS ----------
def _varint(buf, pos: int) -> tuple[int, int]:
    data, shift = 0, 1
    while True:
        if pos >= len(buf):
            raise PatchError("BPS patch is truncated")
        x = buf[pos]; pos += 1
        data += (x & 0x7F) * shift
        if x & 0x80:
            return data, pos
        shift <<= 7
        data += shift


def apply_bps(src: Path, patch: Path, out: Path) -> dict:
    p = Path(patch).read_bytes()
    if len(p) < 4 + 12 or p[:4] != b"BPS1":
        raise PatchError("not a BPS patch")
    want_src, want_out, want_patch = (int.from_bytes(p[len(p) - 12 + i:len(p) - 8 + i], "little") for i in (0, 4, 8))
    if zlib.crc32(p[:-4]) != want_patch:
        raise PatchError("the patch file itself is corrupt (checksum mismatch)")
    pos = 4
    src_size, pos = _varint(p, pos)
    out_size, pos = _varint(p, pos)
    meta_len, pos = _varint(p, pos)
    pos += meta_len
    end = len(p) - 12
    if out_size > MAX_OUTPUT:
        raise PatchError("this patch claims an impossibly large result; refusing")
    if Path(src).stat().st_size != src_size:
        raise PatchError(f"this patch expects a {src_size}-byte source; yours is {Path(src).stat().st_size} bytes "
                         "(wrong region/revision of the game, or a different container format?)")
    if crc32_file(src) != want_src:
        raise PatchError("source checksum does not match what the patch was made for (wrong revision or a modified dump)")
    out = Path(out)
    part = out.with_name(out.name + ".part")
    try:
        with open(src, "rb") as fs, open(part, "w+b") as fo:
            fo.truncate(out_size)
            s = mmap.mmap(fs.fileno(), 0, access=mmap.ACCESS_READ) if src_size else b""
            o = mmap.mmap(fo.fileno(), 0) if out_size else bytearray()
            try:
                opos = srel = orel = 0
                while pos < end:
                    data, pos = _varint(p, pos)
                    cmd, length = data & 3, (data >> 2) + 1
                    if opos + length > out_size:
                        raise PatchError("BPS patch writes past the end of its target")
                    if cmd == 0:                                    # SourceRead: same offset in the source
                        if opos + length > src_size:
                            raise PatchError("BPS patch reads past the end of the source")
                        o[opos:opos + length] = s[opos:opos + length]
                    elif cmd == 1:                                  # TargetRead: literal bytes from the patch
                        if pos + length > end:
                            raise PatchError("BPS patch is truncated")
                        o[opos:opos + length] = p[pos:pos + length]
                        pos += length
                    else:
                        d, pos = _varint(p, pos)
                        off = (-1 if d & 1 else 1) * (d >> 1)
                        if cmd == 2:                                # SourceCopy: relative seek in the source
                            srel += off
                            if srel < 0 or srel + length > src_size:
                                raise PatchError("BPS patch reads outside the source")
                            o[opos:opos + length] = s[srel:srel + length]
                            srel += length
                        else:                                       # TargetCopy: may overlap what it is writing (RLE)
                            orel += off
                            if orel < 0 or orel >= opos:
                                raise PatchError("BPS patch reads outside the target")
                            gap = opos - orel
                            if gap >= length:
                                o[opos:opos + length] = o[orel:orel + length]
                            else:
                                unit = bytes(o[orel:opos])
                                o[opos:opos + length] = (unit * (length // gap + 1))[:length]
                            orel += length
                    opos += length
                if opos != out_size:
                    raise PatchError("BPS patch ended early")
            finally:
                for m in (s, o):
                    if isinstance(m, mmap.mmap):
                        m.close()
        if crc32_file(part) != want_out:
            raise PatchError("patched result failed its checksum; nothing was kept")
        os.replace(part, out)
    finally:
        if part.exists():
            part.unlink()
    return {"format": "bps", "out": str(out), "size": out_size}


# ---------- IPS ----------
def apply_ips(src: Path, patch: Path, out: Path) -> dict:
    p = Path(patch).read_bytes()
    if p[:5] != b"PATCH":
        raise PatchError("not an IPS patch")
    data = bytearray(Path(src).read_bytes())
    pos, done = 5, False
    while pos + 3 <= len(p):
        if p[pos:pos + 3] == b"EOF" and len(p) - pos - 3 in (0, 3):   # the real end (an offset can also spell "EOF")
            pos += 3; done = True
            break
        off = int.from_bytes(p[pos:pos + 3], "big"); pos += 3
        if pos + 2 > len(p):
            break
        size = int.from_bytes(p[pos:pos + 2], "big"); pos += 2
        if size:
            chunk = p[pos:pos + size]; pos += size
            if len(chunk) != size:
                raise PatchError("IPS patch is truncated")
        else:
            if pos + 3 > len(p):
                raise PatchError("IPS patch is truncated")
            chunk = p[pos + 2:pos + 3] * int.from_bytes(p[pos:pos + 2], "big"); pos += 3
        if off > len(data):
            data.extend(b"\0" * (off - len(data)))
        data[off:off + len(chunk)] = chunk
    if not done:
        raise PatchError("IPS patch has no EOF marker (truncated?)")
    if len(p) - pos == 3:                                           # optional truncate extension
        del data[int.from_bytes(p[pos:pos + 3], "big"):]
    out = Path(out)
    part = out.with_name(out.name + ".part")
    try:
        part.write_bytes(data)
        os.replace(part, out)
    finally:
        if part.exists():
            part.unlink()
    return {"format": "ips", "out": str(out), "size": len(data)}


# ---------- xdelta (external tool) ----------
def apply_xdelta(src: Path, patch: Path, out: Path) -> dict:
    exe = shutil.which("xdelta3") or shutil.which("xdelta")
    if not exe:
        raise PatchError("xdelta patches need the free `xdelta3` program on your PATH (not bundled). "
                         "Install it, or ask the mod author for a .bps.")
    out = Path(out)
    part = out.with_name(out.name + ".part")
    try:
        r = subprocess.run([exe, "-d", "-f", "-s", str(src), str(patch), str(part)], capture_output=True, text=True)
        if r.returncode != 0:
            raise PatchError("xdelta3 refused the patch: " + (r.stderr.strip() or "unknown error")
                             + " (usually the wrong region/revision of the game)")
        os.replace(part, out)
    finally:
        if part.exists():
            part.unlink()
    return {"format": "xdelta", "out": str(out), "size": out.stat().st_size}


FORMATS = {".bps": apply_bps, ".ips": apply_ips, ".xdelta": apply_xdelta, ".xdelta3": apply_xdelta, ".vcdiff": apply_xdelta}


def apply_patch(src, patch, out) -> dict:
    """Write a patched copy of `src` to `out`. Refuses to overwrite the source or an existing file."""
    src, patch, out = Path(src), Path(patch), Path(out)
    fn = FORMATS.get(patch.suffix.lower())
    if not fn:
        raise PatchError(f"unknown patch type '{patch.suffix}'. Supported: " + ", ".join(sorted(FORMATS)))
    if not src.is_file():
        raise PatchError(f"source not found: {src}")
    if not patch.is_file():
        raise PatchError(f"patch not found: {patch}")
    if out.exists():
        raise PatchError(f"{out} already exists; choose another name (Pawtation never overwrites here)")
    if out.resolve() == src.resolve():
        raise PatchError("output must be a different file from the source")
    if Path(str(out) + ".part").exists():
        raise PatchError(f"{out}.part is in the way; remove it or choose another output name")
    try:
        return fn(src, patch, out)
    except (OverflowError, ValueError, MemoryError, IndexError) as e:
        raise PatchError(f"the patch is malformed ({type(e).__name__}: {e})")
