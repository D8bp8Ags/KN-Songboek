"""The SD_SOUND folder on the card: SD_SOUND.TKM and SD_SOUND.PLM.

Seen on one real card (2026-11-15); what the entries point at is not confirmed yet, because that
card has no MIDI files. Read only.

  TKM  16 records of 0x200 bytes: "S4" 00 00 00 01 00 03, then a 16-char name ("________________"
       for an empty one); on the card the names look like disk names ("020165GM", "020160XG").
  PLM  "S1SD-SOUND" 00 10 ..., at 0x24 "S2" 00 00, then u16 big-endian entries until 0000:
       0x80nn and 0xC0nn (kind in the top two bits, number in the rest).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import List, Tuple

TKM_RECORD = 0x200


class FormatError(ValueError):
    pass


@dataclass
class SDSound:
    names: List[str] = field(default_factory=list)          # TKM, 16 entries ("" = empty)
    order: List[Tuple[str, int]] = field(default_factory=list)  # PLM: ("A"|"B", number)


def read_tkm(data: bytes) -> List[str]:
    out = []
    for o in range(0, len(data) - TKM_RECORD + 1, TKM_RECORD):
        if data[o:o + 2] != b"S4":
            raise FormatError("SD_SOUND.TKM record at 0x%x does not start with S4" % o)
        name = data[o + 8:o + 24].split(b"\0", 1)[0].decode("latin-1").rstrip()
        out.append("" if set(name) <= {"_"} else name)
    return out


def read_plm(data: bytes) -> List[Tuple[str, int]]:
    if not data.startswith(b"S1SD-SOUND") or data[0x24:0x26] != b"S2":
        raise FormatError("not an SD_SOUND.PLM file")
    out = []
    for o in range(0x28, len(data) - 1, 2):
        v, = struct.unpack_from(">H", data, o)
        if v == 0:
            break
        kind = {0x8000: "A", 0xC000: "B"}.get(v & 0xC000)
        if kind is None:
            raise FormatError("unknown SD_SOUND.PLM entry %04x at 0x%x" % (v, o))
        out.append((kind, v & 0x3FFF))
    return out


def read(storage, folder: str = "SD_SOUND") -> SDSound:
    """What the card's SD_SOUND folder holds; empty when it is not there."""
    out = SDSound()
    tkm, plm = folder + "/SD_SOUND.TKM", folder + "/SD_SOUND.PLM"
    if storage.exists(tkm):
        out.names = read_tkm(storage.read(tkm))
    if storage.exists(plm):
        out.order = read_plm(storage.read(plm))
    return out


def midi_files(storage, folder: str = "SD_SOUND") -> List[str]:
    """Paths of the MIDI files under SD_SOUND (one level of subfolders deep)."""
    out = []
    for name in storage.listdir(folder):
        p = folder + "/" + name
        if name.upper().endswith((".MID", ".KAR")):
            out.append(p)
        elif storage.isdir(p):
            out += [p + "/" + n for n in storage.listdir(p) if n.upper().endswith((".MID", ".KAR"))]
    return sorted(out)
