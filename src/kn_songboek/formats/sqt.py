"""Sequencer songs (.SQT): song records, tracks and events. Read-only for now.

Own implementation from the public format description and measurements
on a real card (2026-11-15); no code copied (ADR-0004).

Part 1 (after LZSS, see container.py) holds song records of 0x8E0 bytes (KN7000):
    +0x00  "ZZZZ"
    +0x04  u8   1 = song in use
    +0x05  u8,u8  model signature 01 0D (KN7000); 01 0A = KN6000 (records of 0x870 bytes)
    +0xD0  16 x {u8 flags, u16le first cell}   track directory, cell numbers 1-based, 0xFFFF = empty
    +0x100 16   song name ("________________" when never named)
    +0x140 the song's panel memory: tag/length blocks ending in FF FF; tag 0x42 holds the rhythm
           and the tempo as u16le at payload +8 (checked on a real card)
Part 2 holds 256-byte cells: u8 flags, u16le previous cell (0 = none), u16le next cell
(0xFFFF = last), 251 bytes of events. A track is the chain of cells from its first cell.

Events: 0x81 = beat (no tick byte), 0x82 = end of track; every other event is a tick byte
(0..95 within the beat) followed by a status byte and its data:
    0x80 tempo (+2: bpm in two 7-bit halves, low first: 3B 01 = 59 + 128 = 187)   0x84 bar   0x85/0x86 rhythm start/stop (+0)   other 0x8n (+2)
    0x9n note (+4: key, velocity, duration ticks, duration beats)
    0xAn part parameter (+6)  0xBn controller (+3)  0xCn program (+3)  0xDn pressure (+1)
    0xEn pitch bend (+2)      0xF1/F2/F3 parameter events (+5/+6/+7)
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .rhythm import panel_rhythm_id

RECORD = {b"\x01\x0d": 0x8E0, b"\x01\x0a": 0x870}
CELL = 256
N_TRACKS = 16
TICKS_PER_BEAT = 96

_LEN_HIGH = {0x9: 4, 0xA: 6, 0xB: 3, 0xC: 3, 0xD: 1, 0xE: 2}
_LEN_F = {0xF1: 5, 0xF2: 6, 0xF3: 7}
_LEN_8 = {0x80: 2, 0x84: 0, 0x85: 0, 0x86: 0}


class SQTError(ValueError):
    pass


@dataclass
class Track:
    number: int                    # 1..16
    cells: int = 0
    events: int = 0
    notes: int = 0
    beats: int = 0
    complete: bool = False         # reached 0x82
    tempo: Optional[int] = None    # first tempo event on this track


@dataclass
class SQTSong:
    index: int                     # 1..10 inside the file
    name: str
    model: str                     # "KN7000" / "KN6000"
    tracks: List[Track] = field(default_factory=list)
    panel_tempo: Optional[int] = None   # tempo set in the song's panel memory
    rhythm_id: Optional[int] = None     # 24-bit rhythm in the panel memory (formats/rhythm.py)


    @property
    def has_events(self) -> bool:
        return any(t.events for t in self.tracks)

    @property
    def tempo(self) -> Optional[int]:
        """The tempo the song plays at: its first tempo event if recorded, else the panel tempo."""
        return next((t.tempo for t in self.tracks if t.tempo), None) or self.panel_tempo

    @property
    def beats(self) -> int:
        return max((t.beats for t in self.tracks), default=0)

    @property
    def notes(self) -> int:
        return sum(t.notes for t in self.tracks)


def event_length(status: int) -> Optional[int]:
    if status in _LEN_F:
        return _LEN_F[status]
    if status in _LEN_8:
        return _LEN_8[status]
    hi = status >> 4
    if hi == 0x8:
        return 2
    if hi == 0xB and status != 0xB0:
        return None                # 0xB1..0xBF are not events
    return _LEN_HIGH.get(hi)


def _chain(cells: bytes, first: int) -> List[bytes]:
    out, seen, n = [], set(), first
    while n not in (0, 0xFFFF) and n not in seen:
        seen.add(n)
        off = (n - 1) * CELL
        if off + CELL > len(cells):
            raise SQTError("track points at cell %d, file has %d" % (n, len(cells) // CELL))
        cell = cells[off:off + CELL]
        out.append(cell[5:])
        n = struct.unpack_from("<H", cell, 3)[0]
    return out


def parse_track(number: int, data: bytes, cells: int) -> Track:
    t = Track(number, cells)
    i = 0
    while i < len(data):
        b = data[i]
        if b == 0x81:
            t.beats += 1
            i += 1
            continue
        if b == 0x82:
            t.complete = True
            break
        if b >= 0x80 or i + 1 >= len(data):
            break                  # unknown layout: stop counting, report incomplete
        status = data[i + 1]
        n = event_length(status)
        if n is None:
            break
        if status == 0x80 and t.tempo is None and i + 3 < len(data):
            t.tempo = data[i + 2] | (data[i + 3] << 7)
        if status >> 4 == 0x9:
            t.notes += 1
        t.events += 1
        i += 2 + n
    return t


def panel_tempo(record: bytes) -> Optional[int]:
    """The tempo set in a song record's panel memory (tag 0x42), or None if not found / out of range."""
    off = 0x140
    while off + 2 <= len(record):
        tag, n = record[off], record[off + 1]
        if tag == 0xFF:
            break
        if tag == 0x42 and n >= 10:
            bpm = struct.unpack_from("<H", record, off + 2 + 8)[0]
            return bpm if 20 <= bpm <= 300 else None
        off += 2 + n
    return None


def read_songs(part1: bytes, part2: bytes = b"") -> List[SQTSong]:
    """All songs in use in an SQT file (both parts already unpacked)."""
    if part1[:4] != b"ZZZZ":
        raise SQTError("not an SQT song record")
    size = RECORD.get(part1[5:7])
    if size is None:
        raise SQTError("unknown SQT model signature %s" % part1[5:7].hex())
    model = "KN7000" if size == 0x8E0 else "KN6000"
    songs = []
    for i in range(len(part1) // size):
        r = part1[i * size:(i + 1) * size]
        if r[:4] != b"ZZZZ" or r[4] != 1:
            continue
        name = r[0x100:0x110].split(b"\0")[0].decode("latin-1").rstrip()
        song = SQTSong(i + 1, "" if set(name) <= {"_"} else name, model, panel_tempo=panel_tempo(r),
                       rhythm_id=panel_rhythm_id(r))
        for tn in range(N_TRACKS):
            first = struct.unpack_from("<H", r, 0xD0 + 3 * tn + 1)[0]
            if first == 0xFFFF:
                continue
            chain = _chain(part2, first)
            song.tracks.append(parse_track(tn + 1, b"".join(chain), len(chain)))
        songs.append(song)
    return songs


def summary(songs: List[SQTSong]) -> Dict[str, object]:
    return {"songs": len(songs), "with_events": sum(1 for s in songs if s.has_events),
            "notes": sum(s.notes for s in songs)}
