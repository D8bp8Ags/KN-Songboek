"""What is inside a song's other files: panel memories (PMT), composer styles (CMP), sound arranger
pads (MSP), sound edit (TM) and the home page picture (HMP). Read only; names and a few settings.

Layouts as seen on a real card (2026-11-15, 315 KN7000 and 43 KN6000 songs, all read this way);
independent implementation, see docs/nl/reference/songbestanden.md.

  PMT  (payload after the J KD container)
       +0x00  "JK \\0" (KN6000: "IK \\0"), +0x0C "P" ...
       +0x10  3 banks, each: 16-char bank name, then 8 panel memories
              KN7000: memory 0x750 bytes (bank 0x3A90, payload 0xAFC0)
              KN6000: memory 0x700 bytes (bank 0x3810, payload 0xA840)
       memory: tag/length blocks ending in FF; 0x40 = name (16 chars), 0x42 = rhythm and tempo
               (u16le at +8 of the block's data), the same blocks as a song's panel memory in SQT
  CMP  "TCMP", 0x70-byte header, then 3 styles of 0x80 bytes: name (16 bytes, 13 chars used) and
       4 variation names (16 bytes each), +0x50 20 variation numbers; then 60 variation records
  MSP  "TPAD", 0x70-byte header, 5 banks of 0x30 bytes (16-char name, 6 pads of 3 bytes: number,
       kind, 0x10 = user pad), then 18 user pads of 0x60 bytes starting with a 16-char name
  TM   "KN7000 SOUND RAM" (KN6000: "KN6000 ..."), then 40 sounds of 0x2C8 bytes starting with a
       16-char name, then the user drum kit (16-char name)
  HMP  stored ('JK \\0'): a 0x18C-byte record and a 160x100 BMP. No HMP on the real card yet, so
       only the BMP is taken out (found by its "BM" header); not tested on a real file.
"""
from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from . import panelsettings


class FormatError(ValueError):
    pass


def _text(b: bytes) -> str:
    return b.split(b"\0", 1)[0].decode("latin-1").strip()


def _is_text(b: bytes) -> bool:
    return all(32 <= x < 127 or x == 0 for x in b)


# ---------------------------------------------------------------- panel memory blocks
def blocks(data: bytes, off: int, end: Optional[int] = None) -> Iterator[Tuple[int, bytes]]:
    """(tag, data) of the tag/length blocks at off, up to the FF end mark."""
    end = len(data) if end is None else end
    while off + 2 <= end:
        tag, n = data[off], data[off + 1]
        if tag == 0xFF:
            return
        if off + 2 + n > end:
            raise FormatError("panel memory block 0x%02x at 0x%x runs past the end" % (tag, off))
        yield tag, data[off + 2:off + 2 + n]
        off += 2 + n


def block_tempo(payload: bytes) -> Optional[int]:
    """Tempo from a 0x42 block, or None when it is not a believable tempo."""
    if len(payload) < 10:
        return None
    bpm = struct.unpack_from("<H", payload, 8)[0]
    return bpm if 20 <= bpm <= 300 else None


@dataclass
class PartSound:
    """The sound on one keyboard part: blocks 0x10 RIGHT 1, 0x11 RIGHT 2, 0x12 LEFT are 72-byte part
    records starting {program, bank LSB, bank MSB, volume} (layout from public
    documentation; checked against the names of 358 songs)."""
    part: str                      # "R1", "R2", "L"
    program: int                   # 0..127
    lsb: int
    msb: int
    volume: int                    # 0..127


PARTS = {0x10: "R1", 0x11: "R2", 0x12: "L"}

# The General MIDI programs. KN7000 sounds in bank MSB 32 follow this grouping (a Technics sound is a
# variation of it, picked by the LSB), so the GM name says what kind of sound it is, not its exact name.
GM_NAMES = """Acoustic Grand Piano|Bright Acoustic Piano|Electric Grand Piano|Honky-tonk Piano|Electric Piano 1|Electric Piano 2|Harpsichord|Clavinet|Celesta|Glockenspiel|Music Box|Vibraphone|Marimba|Xylophone|Tubular Bells|Dulcimer|Drawbar Organ|Percussive Organ|Rock Organ|Church Organ|Reed Organ|Accordion|Harmonica|Tango Accordion|Nylon Guitar|Steel Guitar|Jazz Guitar|Clean Guitar|Muted Guitar|Overdriven Guitar|Distortion Guitar|Guitar Harmonics|Acoustic Bass|Finger Bass|Pick Bass|Fretless Bass|Slap Bass 1|Slap Bass 2|Synth Bass 1|Synth Bass 2|Violin|Viola|Cello|Contrabass|Tremolo Strings|Pizzicato Strings|Orchestral Harp|Timpani|String Ensemble 1|String Ensemble 2|Synth Strings 1|Synth Strings 2|Choir Aahs|Voice Oohs|Synth Voice|Orchestra Hit|Trumpet|Trombone|Tuba|Muted Trumpet|French Horn|Brass Section|Synth Brass 1|Synth Brass 2|Soprano Sax|Alto Sax|Tenor Sax|Baritone Sax|Oboe|English Horn|Bassoon|Clarinet|Piccolo|Flute|Recorder|Pan Flute|Blown Bottle|Shakuhachi|Whistle|Ocarina|Square Lead|Sawtooth Lead|Calliope Lead|Chiff Lead|Charang Lead|Voice Lead|Fifths Lead|Bass + Lead|New Age Pad|Warm Pad|Polysynth Pad|Choir Pad|Bowed Pad|Metallic Pad|Halo Pad|Sweep Pad|Rain|Soundtrack|Crystal|Atmosphere|Brightness|Goblins|Echoes|Sci-fi|Sitar|Banjo|Shamisen|Koto|Kalimba|Bagpipe|Fiddle|Shanai|Tinkle Bell|Agogo|Steel Drums|Woodblock|Taiko Drum|Melodic Tom|Synth Drum|Reverse Cymbal|Guitar Fret Noise|Breath Noise|Seashore|Bird Tweet|Telephone Ring|Helicopter|Applause|Gunshot""".split("|")
DRAWBAR_MSB = 34               # the drawbar organ (memories named "Drawbars/Perc" use it)
GM_MSB = 32


def sound_kind(s: PartSound) -> str:
    """"Flute", "Drawbar organ (drawbars)", or "" when the bank is not one we can name."""
    if s.msb == GM_MSB:
        return GM_NAMES[s.program]
    if s.msb == DRAWBAR_MSB:
        return "Drawbars"
    return ""


@dataclass
class PanelMemory:
    number: int                    # 1..8
    name: str
    tempo: Optional[int] = None
    chord: Optional[int] = None    # chord mode, CHORD_MODES (block 0x42, data +3 low 4 bits); 0 = not set
    sounds: List[PartSound] = field(default_factory=list)       # RIGHT 1, RIGHT 2, LEFT
    rhythm: Optional[int] = None   # 24-bit rhythm number (block 0x42, data +0..2; formats/rhythm.py)
    settings: List[dict] = field(default_factory=list)          # everything else: panelsettings.settings


@dataclass
class PanelBank:
    number: int                    # 1..3 (a diskette's full set: more), the order in the file
    name: str
    memories: List[PanelMemory] = field(default_factory=list)
    label: str = ""                # as the keyboard calls it: A, B, C, then 1..10 (bank_label)


PMT_MEMORY = {0xAFC0: 0x750, 0xA840: 0x700}        # payload size -> memory size (one SD song: 3 banks)
SONG_BANKS = 3


def read_pmt(payload: bytes) -> List[PanelBank]:
    """The banks of a panel memory file: 3 for one SD song; a diskette's full set has more (13 on the
    Top Trax disks) in the same layout."""
    mem = PMT_MEMORY.get(len(payload))
    if mem is None and payload[:1] in (b"J", b"I"):
        m = 0x750 if payload[:1] == b"J" else 0x700
        if len(payload) > 0x10 and (len(payload) - 0x10) % (0x10 + 8 * m) == 0:
            mem = m
    if mem is None or payload[1:4] != b"K \0":
        raise FormatError("not a panel memory file (%d bytes)" % len(payload))
    stride = 0x10 + 8 * mem
    banks = []
    for b in range((len(payload) - 0x10) // stride):
        base = 0x10 + b * stride
        bank = PanelBank(b + 1, _text(payload[base:base + 16]), label=bank_label(b + 1))
        for m in range(8):
            o = base + 0x10 + m * mem
            pm = PanelMemory(m + 1, "")
            found = {}
            for tag, data in blocks(payload, o, o + mem):
                found[tag] = data
                if tag == 0x40:
                    pm.name = _text(data[:16])
                elif tag == 0x42:
                    pm.tempo = block_tempo(data)
                    pm.chord = data[3] & 0x0F if len(data) > 3 else None
                    pm.rhythm = data[0] | data[1] << 8 | data[2] << 16 if len(data) > 2 else None
                elif tag in PARTS and len(data) >= 4:
                    pm.sounds.append(PartSound(PARTS[tag], data[0] & 0x7F, data[1], data[2], data[3] & 0x7F))
            pm.settings = panelsettings.settings(found)
            bank.memories.append(pm)
        banks.append(bank)
    return banks


def bank_label(number: int) -> str:
    """The keyboard's name for the bank at this place in the file (1-based): A, B, C, then 1 to 10.
    Every model has A, B and C; the KN6000/KN7000 add 1-10. "3 BANK" saves only A, B and C."""
    return "ABC"[number - 1] if number <= SONG_BANKS else str(number - SONG_BANKS)


CHORD_MODES = {1: "one finger", 2: "fingered", 3: "pianist"}


def chord_counts(banks: List[PanelBank]) -> Dict[int, int]:
    """How many panel memories use each chord mode (CHORD_MODES); one song can mix them."""
    count: Dict[int, int] = {}
    for b in banks:
        for m in b.memories:
            if m.chord in CHORD_MODES:
                count[m.chord] = count.get(m.chord, 0) + 1
    return count


def chord_mode(banks: List[PanelBank]) -> Optional[int]:
    """The chord mode most panel memories use (CHORD_MODES), or None when none sets one. The diskettes
    come in pairs that differ only in this: TRAX1 (fingered) and 1FINGR (one finger)."""
    count = chord_counts(banks)
    return max(count, key=lambda k: count[k]) if count else None


_NUMBERED = re.compile(r"^(.*?\S)\s*\d+$")


def set_titles(banks: List[PanelBank]) -> List[str]:
    """The songs in a diskette's full set: memories named "Annie`s Song 1".."4" are one song,
    "Annie's Song". Empty for one SD song's own 3 banks (those are that song's settings)."""
    if len(banks) <= SONG_BANKS:
        return []
    count: Dict[str, int] = {}
    for b in banks:
        for m in b.memories:
            found = _NUMBERED.match(m.name.strip())
            if found:
                t = " ".join(found.group(1).replace("`", "'").split())
                count[t] = count.get(t, 0) + 1
    return [t for t, n in count.items() if n >= 2]


def pmt_set_titles(raw: bytes) -> List[str]:
    """set_titles() of a PMT file as stored; one SD song's file is seen from its header and not unpacked."""
    from . import container
    if len(raw) < 16 or struct.unpack_from("<I", raw, 12)[0] in PMT_MEMORY:
        return []
    return set_titles(read_pmt(container.parse(raw, "PMT").parts[0]))


# ---------------------------------------------------------------- composer styles
@dataclass
class Style:
    number: int                    # 1..3
    name: str
    variations: List[str] = field(default_factory=list)


def read_cmp(payload: bytes) -> List[Style]:
    if payload[:4] != b"TCMP" or len(payload) < 0x70 + 3 * 0x80:
        raise FormatError("not a composer file")
    out = []
    for k in range(3):
        r = payload[0x70 + k * 0x80:0xF0 + k * 0x80]
        if not _is_text(r[:0x50]):
            raise FormatError("composer style %d has no readable name" % (k + 1))
        out.append(Style(k + 1, _text(r[:16]), [_text(r[16 * j:16 * j + 16]) for j in range(1, 5)]))
    return out


# ---------------------------------------------------------------- sound arranger pads
@dataclass
class Pad:
    number: int                    # 1..6 in its bank
    user: Optional[int]            # 1..18: the user pad it plays, None for a built-in pad
    builtin: Optional[Tuple[int, int]] = None   # (number, kind) of a built-in pad
    name: str = ""                 # known for user pads


@dataclass
class PadBank:
    number: int                    # 1..5
    name: str
    pads: List[Pad] = field(default_factory=list)


@dataclass
class PadFile:
    banks: List[PadBank]
    user_pads: List[str]           # names of the 18 user pads


def read_msp(payload: bytes) -> PadFile:
    if payload[:4] != b"TPAD" or len(payload) < 0x160 + 18 * 0x60:
        raise FormatError("not a pad file")
    users = []
    for k in range(18):
        o = 0x160 + k * 0x60
        users.append(_text(payload[o:o + 16]) if _is_text(payload[o:o + 16]) else "")
    banks = []
    for b in range(5):
        o = 0x70 + b * 0x30
        bank = PadBank(b + 1, _text(payload[o:o + 16]))
        for p in range(6):
            x, y, flag = payload[o + 16 + 3 * p:o + 19 + 3 * p]
            if flag & 0x10:
                u = x * 6 + y
                bank.pads.append(Pad(p + 1, u + 1, None, users[u] if u < 18 else ""))
            else:
                bank.pads.append(Pad(p + 1, None, (x, y)))
        banks.append(bank)
    return PadFile(banks, users)


# ---------------------------------------------------------------- sound edit
@dataclass
class SoundFile:
    model: str                     # "KN7000" / "KN6000"
    sounds: List[str]              # 40 names
    drum_kit: str


def read_tm(payload: bytes) -> SoundFile:
    if payload[:2] != b"KN" or payload[6:16] != b" SOUND RAM" or len(payload) < 0x10 + 41 * 0x2C8:
        raise FormatError("not a sound file")
    sounds = []
    for k in range(40):
        o = 0x10 + k * 0x2C8
        sounds.append(_text(payload[o:o + 16]))
    o = 0x10 + 40 * 0x2C8
    return SoundFile(_text(payload[:6]), sounds, _text(payload[o:o + 16]))


# ---------------------------------------------------------------- home page
@dataclass
class HomePage:
    record: bytes
    bmp: bytes                     # a complete .bmp file
    width: int
    height: int


def read_hmp(data: bytes) -> HomePage:
    """Take the picture out of a home page file (the stored 'JK \\0' container or its payload)."""
    i = data.find(b"BM", 0x10)
    while i >= 0:
        if i + 26 <= len(data):
            size, = struct.unpack_from("<I", data, i + 2)
            hdr, = struct.unpack_from("<I", data, i + 14)
            if hdr in (12, 40, 108, 124) and 26 < size <= len(data) - i:
                if hdr == 12:
                    w, h = struct.unpack_from("<HH", data, i + 18)
                else:
                    w, h = struct.unpack_from("<ii", data, i + 18)
                return HomePage(bytes(data[:i]), bytes(data[i:i + size]), w, abs(h))
        i = data.find(b"BM", i + 1)
    raise FormatError("no picture found in the home page file")
