"""The rhythm a song uses and its time signature (maatsoort).

A song does not store a time signature. Its panel memory (SQT record +0x140, block 0x42, see
``formats/sqt.py``) holds the selected rhythm as a 24-bit number, little-endian at payload +0..2:

    bits 20-22  source: 0 = built-in, 1 = MEMORY (COMPOSER MEMORY, the song's own .CMP),
                2 = CUSTOM (the keyboard's 20 CUSTOM styles in its internal flash)
    built-in    the low 12 bits are a style-ID; ``rhythm_table.INDEX`` folds it to a style
    MEMORY      the low bits are the style number 0-2 in the song's TCMP (.CMP) container
    CUSTOM      the low bits are the CUSTOM slot 0-19; that style is not on the SD card

Every variation of a style records its beats in a bar (beats - 1 in the low 3 bits of its meter
byte); all 20 variations of a built-in style agree. The keyboard counts only beats: of the 220
built-in rhythms it can select, 15 have 3 beats (the waltzes) and the rest 4. "Polka 2/4" and
"USA March 6/8" are 4-beat patterns too; for those the meter in the name is shown, else beats/4.
"""
from __future__ import annotations

from .text import Text            # English, with a key so a front end can translate it

import re
import struct
from dataclasses import dataclass
from typing import Optional

from .rhythm_table import INDEX, STYLES

SOURCE_BUILTIN, SOURCE_MEMORY, SOURCE_CUSTOM = 0, 1, 2
SOURCE_NAMES = {SOURCE_BUILTIN: "ingebouwd", SOURCE_MEMORY: "composer memory", SOURCE_CUSTOM: "custom"}

# TCMP (.CMP, COMPOSER MEMORY): 0x70-byte header, 3 style records of 0x80, 60 variation records of 0xE0
TCMP_STYLES = 0x70
TCMP_STYLE_SIZE = 0x80
TCMP_VARS = TCMP_STYLES + 3 * TCMP_STYLE_SIZE
TCMP_VAR_SIZE = 0xE0

_NAMED_METER = re.compile(r"\b([2-9]/[248])\b")


@dataclass(frozen=True)
class Rhythm:
    rhythm_id: int
    source: int
    number: int                    # built-in style-ID, MEMORY style 0-2 or CUSTOM slot 0-19
    name: Optional[str] = None
    beats: Optional[int] = None    # beats in a bar; None when not known from the card

    @property
    def meter(self) -> Optional[str]:
        """'3/4', '4/4' ... or None when unknown; a meter in the name ('Polka 2/4') wins."""
        m = _NAMED_METER.search(self.name or "")
        if m:
            return m.group(1)
        return "%d/4" % self.beats if self.beats else None

    @property
    def label(self) -> str:
        """Short text for the user, e.g. 'Waltz' or 'Composer memory 2' or 'Custom 5'."""
        if self.name:
            return self.name
        if self.source == SOURCE_MEMORY:
            return Text("rhythm_memory", "Composer memory {n}", n=self.number + 1)
        if self.source == SOURCE_CUSTOM:
            return Text("rhythm_custom", "Custom {n}", n=self.number + 1)
        return Text("rhythm_number", "Rhythm 0x{n:03X}", n=self.number)


def builtin(style_id: int) -> Optional[tuple]:
    """(name, beats) of a built-in style-ID, or None when the ID is outside the index."""
    if style_id > 0xFFF:
        return None
    return STYLES[INDEX[((style_id & 0xF00) >> 1) | (style_id & 0x7F)]]


def tcmp_style(cmp: bytes, style: int) -> Optional[tuple]:
    """(name, beats) of style 0-2 in an unpacked TCMP container, from its VARIATION 1."""
    if cmp[:4] != b"TCMP" or not 0 <= style < 3:
        return None
    rec = TCMP_STYLES + style * TCMP_STYLE_SIZE
    if len(cmp) < rec + TCMP_STYLE_SIZE:
        return None
    name = cmp[rec:rec + 13].split(b"\0")[0].decode("latin-1").strip() or None
    var = cmp[rec + 0x50]
    off = TCMP_VARS + var * TCMP_VAR_SIZE
    if var >= 60 or len(cmp) < off + 0x12:
        return name, None
    return name, (cmp[off + 0x11] & 7) + 1


def decode(rhythm_id: int, cmp: Optional[bytes] = None) -> Rhythm:
    """Interpret a 24-bit rhythm number; ``cmp`` is the song's unpacked .CMP for MEMORY styles."""
    source, number = (rhythm_id >> 20) & 7, rhythm_id & 0xFFFFF
    name = beats = None
    if source == SOURCE_BUILTIN:
        hit = builtin(number)
        if hit:
            name, beats = hit
    elif source == SOURCE_MEMORY and cmp is not None:
        hit = tcmp_style(cmp, number)
        if hit:
            name, beats = hit
    return Rhythm(rhythm_id, source, number, name, beats)


def panel_rhythm_id(record: bytes, start: int = 0x140) -> Optional[int]:
    """The 24-bit rhythm number in a panel memory (block 0x42, payload +0..2), or None."""
    off = start
    while off + 2 <= len(record):
        tag, n = record[off], record[off + 1]
        if tag == 0xFF:
            break
        if tag == 0x42 and n >= 3 and off + 5 <= len(record):
            lo, hi = struct.unpack_from("<HB", record, off + 2)
            return lo | hi << 16
        off += 2 + n
    return None


def song_rhythm(rhythm_id: Optional[int], storage=None, cmp_path: Optional[str] = None) -> Optional[Rhythm]:
    """``decode`` for a song on a card: reads the song's .CMP only when the rhythm is a MEMORY style."""
    if rhythm_id is None:
        return None
    cmp = None
    if (rhythm_id >> 20) & 7 == SOURCE_MEMORY and storage is not None and cmp_path:
        from . import container
        try:
            cmp = container.parse(storage.read(cmp_path), "CMP").parts[0]
        except Exception:               # an unreadable .CMP only costs the meter
            cmp = None
    return decode(rhythm_id, cmp)
