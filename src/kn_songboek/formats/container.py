"""The KN7000 file containers ('J KD', 'J K\\1', 'JK \\0') and the 'J KD' LZSS codec.

Format as found in public KN7000 documentation and the KN7000 program; this is an independent
implementation of that description.

  'J KD'  .CMP .PMT .MSP .TM        one part:  +4 u16be version=1, +6 u16be flags,
                                             +8 u32le 0, +0xC u32le size, +0x10 LZSS stream
          .SQT .LSW                 two parts: +8 u32le size1, +0xC size2, +0x10 csize1,
                                             +0x14 csize2, +0x18 stream1 stream2
  'JK D'  .EFC                      same layout and LZSS as one-part 'J KD' (seen on a real card)
  'I KD' / 'IK D'  KN6000 songs     same headers as 'J KD' / 'JK D', each part raw deflate + adler32
  'J K\\1' .AST .CST                 +4 u32le inflated size; .AST stream at +0x10, .CST at +0x30;
                                     raw deflate (zlib 1.0.4, no 2-byte header) + adler32 (BE)
  'JK \\0' .HMP .FAV .MD             stored

LZSS: flag byte, 8 items low bit first, 1 = literal; a reference is lo, hi with ring position
lo | (hi >> 3) << 8 (13 bits, absolute) and length (hi & 7) + 3; ring of 8192 bytes filled with 0,
first write at 0x1FF6; no end marker (the header gives the size).
"""
from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from collections import OrderedDict
from typing import List

from . import lzss_tree
from .text import Text

# Signatures of KN5000 song files (seen 2026-11-16 in style downloads): an older model whose files are
# laid out otherwise; we do not read them, and whether a KN7000 loads them is not known.
KN5000_MAGIC = (b"HK \0", b"H\0K\0", b"KN50")


class OtherModelError(ValueError):
    """A song file of another keyboard model that we cannot read."""

N, F, THRESHOLD = 0x2000, 10, 2
TWO_PART = {"SQT", "LSW"}


def lzss_decode(c: bytes, n: int) -> bytes:
    """Unpack Technics LZSS (a 0x2000-byte ring that starts as zeros, written from N - F on).

    Instead of a ring the output itself is the window, behind N zero bytes that stand for the ring's
    start: ring position pos then holds the byte d places back, d = (N - F + written - pos) mod N (0
    meaning N). A copy that does not overlap what it writes is one slice, which is what makes this
    several times faster than copying byte by byte through a ring."""
    buf = bytearray(N)                       # the ring's starting zeros; output follows from index N
    end = N + n
    i, size = 0, len(c)
    mask, back = N - 1, N - F
    while len(buf) < end and i < size:
        flags = c[i]
        i += 1
        for bit in range(8):
            if len(buf) >= end or i >= size:
                break
            if flags >> bit & 1:
                buf.append(c[i])
                i += 1
            else:
                lo, hi = c[i], c[i + 1]
                i += 2
                length = (hi & 7) + THRESHOLD + 1
                d = (back + len(buf) - N - (lo | (hi >> 3) << 8)) & mask or N
                start = len(buf) - d
                if d >= length:
                    buf += buf[start:start + length]
                else:                        # overlapping run: repeats the last d bytes
                    for k in range(length):
                        buf.append(buf[start + k])
    if len(buf) < end:
        raise ValueError("LZSS stream ended after %d of %d bytes" % (len(buf) - N, n))
    return bytes(buf[N:end])


def lzss_encode(data: bytes) -> bytes:
    """Compress like Technics does: byte-identical to the keyboard's own files (formats/lzss_tree.py,
    checked against every 'J KD' file on a real card)."""
    return lzss_tree.encode(data)


def inflate_part(d: bytes, off: int):
    return _inflate(d, off)[0]


def _inflate(d: bytes, off: int):
    """(payload, offset just after its adler32) of the raw deflate stream at off."""
    o = zlib.decompressobj(-15)
    p = o.decompress(d[off:])
    if not o.eof:
        raise ValueError("deflate stream at 0x%x does not end" % off)
    end = len(d) - len(o.unused_data)
    adler = struct.unpack(">I", d[end:end + 4])[0] if end + 4 <= len(d) else None
    if adler is not None and adler != zlib.adler32(p):
        raise ValueError("adler32 mismatch after stream at 0x%x" % off)
    return p, end + 4


@dataclass
class Container:
    kind: str                     # 'KD' (LZSS), 'ID' (KN6000 deflate), 'K1', 'RAW'
    magic: bytes
    header: bytes
    parts: List[bytes] = field(default_factory=list)


_CACHE: "OrderedDict[tuple, Container]" = OrderedDict()
_CACHE_SIZE = 64


def parse(data: bytes, ext: str) -> Container:
    """The parts of a song file, unpacked. The last 64 files are kept (by their exact bytes), so
    clicking back and forth through songs, or reading one song for several things, unpacks it once."""
    ext = ext.upper().strip(". ")
    key = (ext, len(data), zlib.crc32(data), data[:32])
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return Container(hit.kind, hit.magic, hit.header, list(hit.parts))
    got = _parse(data, ext)
    _CACHE[key] = got
    if len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)
    return Container(got.kind, got.magic, got.header, list(got.parts))


def _parse(data: bytes, ext: str) -> Container:
    m = data[:4]
    if m in KN5000_MAGIC:
        raise OtherModelError(Text("kn5000_file", "KN5000 file: the app cannot read it, and it may not work on "
                                   "a KN7000"))
    # EFC files on a real card use the magic "JK D"; the payload is the same LZSS stream (2026-11-15)
    if m in (b"J KD", b"JK D") and len(data) >= 0x10:
        if ext in TWO_PART:
            s1, s2, c1, c2 = struct.unpack_from("<4I", data, 8)
            p1 = lzss_decode(data[0x18:0x18 + c1], s1) if s1 else b""
            p2 = lzss_decode(data[0x18 + c1:0x18 + c1 + c2], s2) if s2 else b""
            return Container("KD", m, bytes(data[:0x18]), [p1, p2])
        size = struct.unpack_from("<I", data, 0xC)[0]
        return Container("KD", m, bytes(data[:0x10]), [lzss_decode(data[0x10:], size)])
    # KN6000 songs ('I KD' / 'IK D'): same headers, but each part is raw deflate + adler32.
    # The KN7000 plays them; 43 songs on the user's card are like this (2026-11-15).
    if m in (b"I KD", b"IK D") and len(data) >= 0x10:
        if ext in TWO_PART:
            s1, s2, c1, c2 = struct.unpack_from("<4I", data, 8)
            # part 2 starts right after part 1's stream and adler32; on the KN6000 diskettes that is 2
            # bytes before 0x18 + csize1 (seen in every LSW of the user's diskettes, 2026-11-17)
            p1, after = _inflate(data, 0x18) if s1 else (b"", 0x18)
            p2 = inflate_part(data, after) if s2 else b""
            return Container("ID", m, bytes(data[:0x18]), [p1, p2])
        return Container("ID", m, bytes(data[:0x10]), [inflate_part(data, 0x10)])
    if m == b"J K\x01":
        start = 0x30 if ext == "CST" else 0x10
        return Container("K1", m, bytes(data[:start]), [inflate_part(data, start)])
    return Container("RAW", m, b"", [bytes(data)])


def build_kd(payload: bytes, flags: int = 0, magic: bytes = b"J KD") -> bytes:
    """A one-part container (CMP, PMT, MSP, TM; EFC with magic 'JK D')."""
    stream = lzss_encode(payload)
    return magic + struct.pack(">HH", 1, flags) + struct.pack("<II", 0, len(payload)) + stream


def build_kd2(p1: bytes, p2: bytes, flags: int = 0) -> bytes:
    """A two-part container (SQT, LSW)."""
    s1, s2 = lzss_encode(p1) if p1 else b"", lzss_encode(p2) if p2 else b""
    return (b"J KD" + struct.pack(">HH", 1, flags)
            + struct.pack("<4I", len(p1), len(p2), len(s1), len(s2)) + s1 + s2)


# ---- song file (.SQT part 1) headline fields, from the public format description ----
SQT_RECORD = 0x8E0


def sqt_song_records(p1: bytes):
    """Yield (index, record bytes) for each 0x8E0-byte KN7000 song record in SQT part 1."""
    for i in range(len(p1) // SQT_RECORD):
        rec = p1[i * SQT_RECORD:(i + 1) * SQT_RECORD]
        if rec[:4] == b"ZZZZ":
            yield i, rec
