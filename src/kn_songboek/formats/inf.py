"""KN7000MN.INF -- the Technics SX-KN7000 SD-card music database ("SDDIR INF").

Layout recovered from the KN7000 main program (build 941) by static analysis of the program.  The instrument keeps the whole file mirrored in battery SRAM at 0x50083D72
and writes it back verbatim (0xD620 bytes) after every SD change.  All integers are
little-endian (MN10300 CPU).

    offset  size     contents
    0x0000  0x10     signature "KN7000 SDDIR INF"
    0x0010  99*0x1F0 folder records (TFLD001 .. TFLD099)
                       +0x00 name[16]           folder name, space padded
                       +0x10 20 * song entry (0x18 bytes each)
                               +0x00 name[16]   song name, space padded
                               +0x10 base[6]    file base name, e.g. "001KN7" (empty = default)
                               +0x16 u16 types  bit i set = file with extension FILE_TYPES[i] exists
    0xBFE0  0x78     song lists (playlists): 3 lists * 20 * (u8 folder, u8 song), 0-based,
                     0xFF 0xFF ends a list (func_485614F6 insert, func_4856169B purge)
    0xC058  40*0x22  favourites banks: name[16] + u16 items[9]
                       item 0 = empty; (folder+1) << 8 | (song+1) = Technics song;
                       0x8000 | n = entry n of the SD-SOUND (SMF) list
    0xC5A8  0x100    u16 first_index[128]: first position in the alphabetical list of a name
                     starting with character c (0xFFFF = none); slots 126/127 are reused for
                     the 0x8B / 0x8D character groups
    0xC6A8  1980*2   alphabetical list: (u8 folder, u8 song) for all 99*20 slots
    0xD620           end of file
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple

SIGNATURE = b"KN7000 SDDIR INF"
FILE_SIZE = 0xD620
N_FOLDERS = 99
N_SONGS = 20
NAME_LEN = 16
BASE_LEN = 6
SONG_SIZE = 0x18
FOLDER_SIZE = NAME_LEN + N_SONGS * SONG_SIZE  # 0x1F0
OFF_FOLDERS = 0x10
OFF_BROWSE = OFF_FOLDERS + N_FOLDERS * FOLDER_SIZE  # 0xBFE0
N_PLAYLISTS = 3
PLAYLIST_LEN = 20
BROWSE_SIZE = N_PLAYLISTS * PLAYLIST_LEN * 2  # 0x78
OFF_FAV = OFF_BROWSE + BROWSE_SIZE  # 0xC058
N_FAV_BANKS = 40
FAV_ITEMS = 9
FAV_SIZE = NAME_LEN + 2 * FAV_ITEMS  # 0x22
OFF_ALPHA_FIRST = OFF_FAV + N_FAV_BANKS * FAV_SIZE  # 0xC5A8
OFF_ALPHA_LIST = OFF_ALPHA_FIRST + 0x100  # 0xC6A8
N_SLOTS = N_FOLDERS * N_SONGS  # 1980

assert OFF_ALPHA_LIST + N_SLOTS * 2 == FILE_SIZE

# Bit i of a song's type mask <-> file extension i (table at program 0x4852F882).
FILE_TYPES = ("LSW", "PMT", "SQT", "CMP", "TM", "MSP", "EFC",
              "MD", "FAV", "HMP", "AST", "SQF", "SEQ", "ACT")
FILE_TYPE_INFO = {
    "LSW": "current panel + per-rhythm sound links (J KD, 2 parts)",
    "PMT": "panel memory banks (J KD)",
    "SQT": "sequencer song(s) (J KD, 2 parts)",
    "CMP": "composer / custom styles, TCMP container (J KD)",
    "TM": "sound edit / custom sounds (J KD, same writer as PMT)",
    "MSP": "music stylist pads, TPAD container (J KD)",
    "EFC": "effect memory (J KD, same writer as PMT)",
    "MD": "music database settings (stored, JK \\0)",
    "FAV": "favourites (stored, JK \\0)",
    "HMP": "home page: 0x18C record + 160x100 BMP (stored)",
    "AST": "custom data / all custom styles (J K\\1, deflate)",
    "SQF": "never written by the KN7000 save routines (import only)",
    "SEQ": "never written by the KN7000 save routines (import only)",
    "ACT": "presentation (FEATURE.PRE) action script, text",
}

ENCODING = "latin-1"


def _name(raw: bytes) -> str:
    return raw.split(b"\0", 1)[0].decode(ENCODING).rstrip(" ")


def _pad(s: str, n: int, fill: bytes = b" ") -> bytes:
    b = s.encode(ENCODING, errors="replace")[:n]
    return b + fill * (n - len(b))


@dataclass
class Song:
    name: str = ""
    base: str = ""          # 6-char file base; "" means the instrument's default
    types: int = 0          # bit mask over FILE_TYPES
    raw_name: bytes = b""   # original bytes, kept so untouched entries round-trip exactly
    raw_base: bytes = b""

    @property
    def used(self) -> bool:
        return self.types != 0

    @property
    def extensions(self) -> List[str]:
        return [ext for i, ext in enumerate(FILE_TYPES) if self.types >> i & 1]

    def to_bytes(self) -> bytes:
        name = self.raw_name if self.raw_name and _name(self.raw_name) == self.name else _pad(self.name, NAME_LEN)
        base = self.raw_base if self.raw_base and _name(self.raw_base) == self.base else _pad(self.base, BASE_LEN, b"\0")
        return name + base + struct.pack("<H", self.types & 0x3FFF)

    @classmethod
    def from_bytes(cls, b: bytes) -> "Song":
        rn, rb = bytes(b[:16]), bytes(b[16:22])
        return cls(_name(rn), _name(rb), struct.unpack_from("<H", b, 22)[0], rn, rb)


@dataclass
class Folder:
    name: str = ""
    songs: List[Song] = field(default_factory=lambda: [Song() for _ in range(N_SONGS)])
    raw_name: bytes = b""

    def to_bytes(self) -> bytes:
        name = self.raw_name if self.raw_name and _name(self.raw_name) == self.name else _pad(self.name, NAME_LEN)
        return name + b"".join(s.to_bytes() for s in self.songs)


@dataclass
class FavoriteBank:
    name: str = ""
    items: List[int] = field(default_factory=lambda: [0] * FAV_ITEMS)
    raw_name: bytes = b""

    def to_bytes(self) -> bytes:
        name = self.raw_name if self.raw_name and _name(self.raw_name) == self.name else _pad(self.name, NAME_LEN)
        return name + struct.pack("<9H", *self.items)

    @staticmethod
    def decode_item(v: int) -> Optional[Tuple[str, int, int]]:
        """-> ('song', folder, song) 0-based, ('smf', index, 0), or None."""
        if v == 0:
            return None
        if v & 0x8000:
            return ("smf", v & 0x7FFF, 0)
        return ("song", (v >> 8) - 1, (v & 0xFF) - 1)

    @staticmethod
    def encode_song(folder: int, song: int) -> int:
        return (folder + 1) << 8 | (song + 1)


class INFError(ValueError):
    pass


@dataclass
class MusicDatabase:
    folders: List[Folder]
    browse: bytes
    favorites: List[FavoriteBank]
    alpha_first: List[int]
    alpha_list: List[Tuple[int, int]]

    # ---------------------------------------------------------------- load / save
    @classmethod
    def new(cls) -> "MusicDatabase":
        db = cls([Folder() for _ in range(N_FOLDERS)], b"\xFF" * BROWSE_SIZE,
                 [FavoriteBank() for _ in range(N_FAV_BANKS)], [0xFFFF] * 128, [])
        db.rebuild_alpha_index()
        return db

    @classmethod
    def from_bytes(cls, d: bytes) -> "MusicDatabase":
        if len(d) < FILE_SIZE:
            raise INFError("file is %d bytes, expected %d" % (len(d), FILE_SIZE))
        if d[:16] != SIGNATURE:
            raise INFError("bad signature %r" % d[:16])
        folders = []
        for f in range(N_FOLDERS):
            o = OFF_FOLDERS + f * FOLDER_SIZE
            raw = bytes(d[o:o + NAME_LEN])
            songs = [Song.from_bytes(d[o + NAME_LEN + s * SONG_SIZE:o + NAME_LEN + (s + 1) * SONG_SIZE])
                     for s in range(N_SONGS)]
            folders.append(Folder(_name(raw), songs, raw))
        favs = []
        for i in range(N_FAV_BANKS):
            o = OFF_FAV + i * FAV_SIZE
            raw = bytes(d[o:o + NAME_LEN])
            favs.append(FavoriteBank(_name(raw), list(struct.unpack_from("<9H", d, o + NAME_LEN)), raw))
        first = list(struct.unpack_from("<128H", d, OFF_ALPHA_FIRST))
        alpha = [(d[OFF_ALPHA_LIST + 2 * i], d[OFF_ALPHA_LIST + 2 * i + 1]) for i in range(N_SLOTS)]
        return cls(folders, bytes(d[OFF_BROWSE:OFF_BROWSE + BROWSE_SIZE]), favs, first, alpha)

    @classmethod
    def load(cls, path) -> "MusicDatabase":
        with open(path, "rb") as fh:
            return cls.from_bytes(fh.read())

    def to_bytes(self) -> bytes:
        out = bytearray(SIGNATURE)
        for f in self.folders:
            out += f.to_bytes()
        out += self.browse
        for b in self.favorites:
            out += b.to_bytes()
        out += struct.pack("<128H", *self.alpha_first)
        alpha = list(self.alpha_list) + [(0xFF, 0xFF)] * (N_SLOTS - len(self.alpha_list))
        for af, asl in alpha[:N_SLOTS]:
            out += bytes((af, asl))
        assert len(out) == FILE_SIZE, hex(len(out))
        return bytes(out)

    def save(self, path) -> None:
        with open(path, "wb") as fh:
            fh.write(self.to_bytes())

    # ---------------------------------------------------------------- playlists
    def playlist(self, n: int) -> List[Tuple[int, int]]:
        """Song list n (0..2) as 0-based (folder, song) pairs."""
        out = []
        for i in range(PLAYLIST_LEN):
            f, s = self.browse[(n * PLAYLIST_LEN + i) * 2], self.browse[(n * PLAYLIST_LEN + i) * 2 + 1]
            if f == 0xFF or s == 0xFF:
                break
            out.append((f, s))
        return out

    def set_playlist(self, n: int, items: List[Tuple[int, int]]) -> None:
        if len(items) > PLAYLIST_LEN:
            raise ValueError("a song list holds at most %d songs" % PLAYLIST_LEN)
        b = bytearray(self.browse)
        flat = [x for p in items for x in p] + [0xFF] * (2 * (PLAYLIST_LEN - len(items)))
        b[n * PLAYLIST_LEN * 2:(n + 1) * PLAYLIST_LEN * 2] = bytes(flat)
        self.browse = bytes(b)

    def purge_slot(self, folder: int, song: int) -> None:
        """Remove every reference to a slot (favourites and song lists), as the instrument does
        when a song is deleted."""
        v = FavoriteBank.encode_song(folder, song)
        for bank in self.favorites:
            bank.items = [0 if x == v else x for x in bank.items]
        for n in range(N_PLAYLISTS):
            self.set_playlist(n, [p for p in self.playlist(n) if p != (folder, song)])

    def retarget_slot(self, f0: int, s0: int, f1: int, s1: int) -> None:
        v0, v1 = FavoriteBank.encode_song(f0, s0), FavoriteBank.encode_song(f1, s1)
        for bank in self.favorites:
            bank.items = [v1 if x == v0 else x for x in bank.items]
        for n in range(N_PLAYLISTS):
            self.set_playlist(n, [(f1, s1) if p == (f0, s0) else p for p in self.playlist(n)])

    def copy(self) -> "MusicDatabase":
        return MusicDatabase.from_bytes(self.to_bytes())

    # ---------------------------------------------------------------- queries
    def iter_songs(self, used_only: bool = True) -> Iterator[Tuple[int, int, Song]]:
        for fi, f in enumerate(self.folders):
            for si, s in enumerate(f.songs):
                if s.used or not used_only:
                    yield fi, si, s

    def song(self, folder: int, song: int) -> Song:
        return self.folders[folder].songs[song]

    def free_slot(self, folder: int) -> Optional[int]:
        for si, s in enumerate(self.folders[folder].songs):
            if not s.used:
                return si
        return None

    # ---------------------------------------------------------------- index
    def rebuild_alpha_index(self) -> None:
        """Rebuild the alphabetical list the way the program does before every save
        (func_48561785 + func_48561960): all 1980 slots sorted by their 16-byte name with leading
        spaces skipped, then a first-index table by first character.  The firmware uses an
        unstable qsort, so equal names may come out in another order than on the instrument."""
        recs = []
        for fi, f in enumerate(self.folders):
            for si, s in enumerate(f.songs):
                raw = s.to_bytes()[:NAME_LEN]
                key = raw.lstrip(b" ") or b" "
                # signed-char compare as on the MN10300 (extb): bytes >= 0x80 sort first
                recs.append((bytes((c - 256 if c >= 0x80 else c) + 128 for c in key), fi, si, key[0], s.used))
        recs.sort(key=lambda r: r[0])
        first = [0xFFFF] * 128
        prev = None
        for i, (_, _fi, _si, c, used) in enumerate(recs):
            if not used:
                continue
            if c != prev:
                if 0 < c < 0x80:
                    first[c] = i
                elif c == 0x8B:
                    first[126] = i
                elif c == 0x8D:
                    first[127] = i
                prev = c
        first[0] = 0  # the program clears entry 0 after building the table
        self.alpha_first = first
        # Unused slots keep their sorted position but are written as 0xFF 0xFF; with plain names
        # they sort first, so on a real card the used songs fill the tail of the 1980-entry list
        # and first_index points at absolute positions (checked against a real card, 2026-11-15).
        self.alpha_list = [(fi, si) if used else (0xFF, 0xFF) for _, fi, si, _, used in recs]
