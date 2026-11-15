"""Minimal PNG codec (zlib + struct): 8-bit RGBA out, 8-bit RGB/RGBA in.

    encode_png(width, height, rgba) -> bytes
    write_png(path, width, height, rgba) -> int      (bytes written)
    decode_png(data) -> (width, height, bytearray)   (always RGBA, straight alpha)
    read_png(path) -> (width, height, bytearray)
    png_info(data) -> dict                           (IHDR fields, no pixel decoding)

``rgba`` is ``width * height * 4`` bytes, rows top to bottom, straight (non-premultiplied) alpha.
"""
from __future__ import annotations

import struct
import zlib

SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


def _filtered(rgba: bytes, width: int, height: int, ftype: int) -> bytes:
    """Scanlines with one PNG filter type for the whole image: 0 None, 1 Sub, 2 Up."""
    stride = width * 4
    out = bytearray()
    prev = bytes(stride)
    for y in range(height):
        row = bytes(rgba[y * stride:(y + 1) * stride])
        out.append(ftype)
        if ftype == 0:
            out += row
        elif ftype == 1:
            out += row[:4]
            out += bytes([(a - b) & 255 for a, b in zip(row[4:], row)])
        else:
            out += bytes([(a - b) & 255 for a, b in zip(row, prev)])
        prev = row
    return bytes(out)


def encode_png(width: int, height: int, rgba, level: int = 9) -> bytes:
    """Encode straight-alpha RGBA bytes as a PNG file image (colour type 6, 8 bits, no interlace).

    Tries the None, Sub and Up filters and keeps the smallest result; the choice is deterministic.
    """
    if width <= 0 or height <= 0:
        raise ValueError("image must be at least 1x1")
    if len(rgba) != width * height * 4:
        raise ValueError("rgba must be width*height*4 bytes (got %d, want %d)" % (len(rgba), width * height * 4))
    best = None
    for ftype in (0, 1, 2):
        packed = zlib.compress(_filtered(rgba, width, height, ftype), level)
        if best is None or len(packed) < len(best):
            best = packed
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return SIGNATURE + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", best) + _chunk(b"IEND", b"")


def write_png(path, width: int, height: int, rgba, level: int = 9) -> int:
    data = encode_png(width, height, rgba, level)
    with open(str(path), "wb") as fh:
        fh.write(data)
    return len(data)


def _chunks(data: bytes):
    if data[:8] != SIGNATURE:
        raise ValueError("not a PNG file (bad signature)")
    pos = 8
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError("truncated PNG chunk header")
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        crc = data[pos + 8 + length:pos + 12 + length]
        if len(body) != length or len(crc) != 4:
            raise ValueError("truncated PNG chunk %r" % tag)
        if struct.unpack(">I", crc)[0] != (zlib.crc32(tag + body) & 0xFFFFFFFF):
            raise ValueError("bad CRC in PNG chunk %r" % tag)
        yield tag, body
        pos += 12 + length
        if tag == b"IEND":
            return
    raise ValueError("PNG has no IEND chunk")


def png_info(data: bytes) -> dict:
    """IHDR of a PNG: width, height, bit_depth, color_type, interlace, has_alpha. Checks every CRC."""
    info = None
    for tag, body in _chunks(data):
        if tag == b"IHDR":
            w, h, depth, ctype, _comp, _filt, interlace = struct.unpack(">IIBBBBB", body)
            info = {"width": w, "height": h, "bit_depth": depth, "color_type": ctype,
                    "interlace": interlace, "has_alpha": ctype in (4, 6)}
    if info is None:
        raise ValueError("PNG has no IHDR chunk")
    return info


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def decode_png(data: bytes):
    """Decode an 8-bit, non-interlaced RGB or RGBA PNG to ``(width, height, rgba bytearray)``."""
    info = None
    idat = bytearray()
    for tag, body in _chunks(data):
        if tag == b"IHDR":
            info = struct.unpack(">IIBBBBB", body)
        elif tag == b"IDAT":
            idat += body
    if info is None:
        raise ValueError("PNG has no IHDR chunk")
    width, height, depth, ctype, _comp, _filt, interlace = info
    if depth != 8 or ctype not in (2, 6) or interlace != 0:
        raise ValueError("only 8-bit non-interlaced RGB/RGBA PNGs are supported")
    bpp = 4 if ctype == 6 else 3
    stride = width * bpp
    raw = zlib.decompress(bytes(idat))
    if len(raw) != (stride + 1) * height:
        raise ValueError("PNG pixel data has the wrong length")
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _y in range(height):
        ftype = raw[pos]
        row = bytearray(raw[pos + 1:pos + 1 + stride])
        pos += stride + 1
        if ftype == 1:
            for i in range(bpp, stride):
                row[i] = (row[i] + row[i - bpp]) & 255
        elif ftype == 2:
            for i in range(stride):
                row[i] = (row[i] + prev[i]) & 255
        elif ftype == 3:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + ((left + prev[i]) >> 1)) & 255
        elif ftype == 4:
            for i in range(stride):
                left = row[i - bpp] if i >= bpp else 0
                up_left = prev[i - bpp] if i >= bpp else 0
                row[i] = (row[i] + _paeth(left, prev[i], up_left)) & 255
        elif ftype != 0:
            raise ValueError("unknown PNG filter type %d" % ftype)
        if bpp == 4:
            out += row
        else:
            for i in range(0, stride, 3):
                out += row[i:i + 3]
                out.append(255)
        prev = row
    return width, height, out


def read_png(path):
    with open(str(path), "rb") as fh:
        return decode_png(fh.read())
