"""The song library: every card in one folder, read live, no database or index (ADR-0007).

    Library/
    ├── Kaart 01/              a copy of a card (has PRIVATE/TECHNICS/KN7000/KN7000MN.INF)
    ├── Oud/Kaart 1998/        nested up to MAX_DEPTH levels
    └── piet.img               a card image

Opening reads each card's own database (fast). A diskette's set holds the panel memories of many
songs (the Top Trax disks: 20); their titles are read at once for diskettes kept in the library and
on demand for other cards, so a search finds "Annie's Song" inside TRAX1. Songs whose files are byte-identical are shown once
with all the cards they are on. Tempo and "recorded or not" come from the SQT file and are read on
demand (details / fill_details), so a front end can show the list first and fill those in after.
Nothing is ever written to the library.
"""
from __future__ import annotations

import hashlib
import os
from collections import Counter
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..formats import container, layout, songdata, sqt
from ..formats.rhythm import song_rhythm
from ..storage import DirectoryStorage, FatImageStorage
from ..storage.base import Storage
from .errors import KN7Error, Text
from .floppy import ORIGINALS
from .session import CardSession

MAX_DEPTH = 3
IMAGE_EXTENSIONS = (".img", ".dmg", ".bin", ".ima")
Progress = Callable[[int, int, str], None]


def file_digest(data: bytes) -> bytes:
    return hashlib.sha1(data).digest()


@dataclass
class LibraryCard:
    label: str                     # path relative to the library, e.g. "Oud/Kaart 1998"
    path: str
    session: CardSession

    @property
    def storage(self) -> Storage:
        return self.session.storage


@dataclass
class LibraryCopy:
    """One song on one card."""
    card: LibraryCard
    folder: int                    # 1-based
    song: int                      # 1-based
    name: str
    extensions: Tuple[str, ...]

    @property
    def paths(self) -> Dict[str, str]:
        return layout.song_paths(self.folder - 1, self.song - 1, self.card.session.db.song(self.folder - 1, self.song - 1))

    @property
    def where(self) -> str:
        return "%s  %02d/%02d" % (self.card.label, self.folder, self.song)


@dataclass
class LibrarySong:
    """A song as the library shows it: identical copies on several cards are one entry."""
    name: str
    copies: List[LibraryCopy] = field(default_factory=list)
    tempo: Optional[int] = None
    meter: Optional[str] = None        # time signature from the song's rhythm, e.g. "3/4"
    recorded: Optional[bool] = None    # None until details() has read the SQT
    size: int = 0                      # bytes of one copy
    checked: bool = False              # details() has run
    titles: List[str] = field(default_factory=list)   # songs in a diskette's full set ("Annie's Song", ...)
    damaged: List[str] = field(default_factory=list)   # files that do not unpack (known once details() ran)

    @property
    def cards(self) -> List[str]:
        out: List[str] = []
        for c in self.copies:
            if c.card.label not in out:
                out.append(c.card.label)
        return out

    @property
    def extensions(self) -> Tuple[str, ...]:
        return self.copies[0].extensions

    def matching_titles(self, text: str) -> List[str]:
        """The titles inside this set that contain text (` and ' count as the same)."""
        t = text.strip().upper().replace("`", "'")
        return [x for x in self.titles if t and t in x.upper()]


@dataclass
class LibraryProblem:
    path: str
    message: str


def _is_card_dir(path: str) -> bool:
    return DirectoryStorage(path).exists(layout.INF_PATH)


def find_cards(root: str) -> List[Tuple[str, str]]:
    """(label, path) of every card under root: folders holding a KN7000 database, and image files."""
    root = os.path.abspath(root)
    out: List[Tuple[str, str]] = []

    def walk(path: str, depth: int) -> None:
        try:
            names = sorted(os.listdir(path), key=str.lower)
        except OSError:
            return
        for n in names:
            if n.startswith("."):
                continue
            p = os.path.join(path, n)
            label = os.path.relpath(p, root).replace(os.sep, "/")
            if os.path.isdir(p):
                if _is_card_dir(p):
                    out.append((label, p))
                elif depth < MAX_DEPTH:
                    walk(p, depth + 1)
            elif n.lower().endswith(IMAGE_EXTENSIONS):
                out.append((label, p))
    if _is_card_dir(root):
        out.append((os.path.basename(root), root))
    else:
        walk(root, 1)
    return out


class Library:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self.cards: List[LibraryCard] = []
        self.songs: List[LibrarySong] = []
        self.problems: List[LibraryProblem] = []
        self._fingerprints: Dict[int, str] = {}

    # ------------------------------------------------------------------ opening
    @classmethod
    def open(cls, root: str, progress: Optional[Progress] = None) -> "Library":
        if not os.path.isdir(root):
            raise KN7Error(Text("not_folder", "{path} is not a folder", path=root))
        lib = cls(root)
        found = find_cards(root)
        for i, (label, path) in enumerate(found):
            if progress:
                progress(i, len(found), label)
            try:
                st = FatImageStorage(path, read_only=True) if os.path.isfile(path) else DirectoryStorage(path)
                lib.cards.append(LibraryCard(label, path, CardSession.open(st)))
            except (KN7Error, OSError) as e:
                lib.problems.append(LibraryProblem(label, str(e)))
        lib._collect()
        return lib

    def _collect(self) -> None:
        """Group the songs of all cards; identical files (same types, sizes, then bytes) -> one entry."""
        by_size: Dict[tuple, List[Tuple[LibraryCopy, int]]] = {}
        for card in self.cards:
            for fi, si, s in card.session.db.iter_songs():
                c = LibraryCopy(card, fi + 1, si + 1, s.name, tuple(s.extensions))
                try:
                    sizes = tuple((ext, card.storage.size(p)) for ext, p in sorted(c.paths.items()))
                except (OSError, KeyError):
                    sizes = ("missing", id(c))                  # never grouped
                by_size.setdefault(sizes, []).append((c, sum(x[1] for x in sizes if isinstance(x, tuple))))
        songs: List[LibrarySong] = []
        for members in by_size.values():
            if len(members) == 1:
                groups = [members]
            else:                                               # same sizes: compare the bytes
                by_hash: Dict[str, List[Tuple[LibraryCopy, int]]] = {}
                for c, size in members:
                    by_hash.setdefault(self._fingerprint(c), []).append((c, size))
                groups = list(by_hash.values())
            for g in groups:
                copies = [c for c, _ in g]
                name = Counter(c.name for c in copies).most_common(1)[0][0]
                songs.append(LibrarySong(name, copies, size=g[0][1]))
        songs.sort(key=lambda s: (s.name.upper(), s.cards))
        self.songs = songs
        floppies = {id(c) for c in self.cards if self.is_floppy(c)}
        for s in songs:
            if any(id(c.card) in floppies for c in s.copies):
                self._read_titles(s)

    @staticmethod
    def _read_titles(song: LibrarySong) -> None:
        """The song titles in a diskette set's panel memories (first readable copy)."""
        for c in song.copies:
            p = c.paths.get("PMT")
            if p is None:
                return
            try:
                song.titles = songdata.pmt_set_titles(c.card.storage.read(p))
                return
            except Exception:                                   # an odd file never stops the library
                continue

    @staticmethod
    def _fingerprint(c: LibraryCopy) -> str:
        h = hashlib.sha1()
        try:
            for ext, p in sorted(c.paths.items()):              # per file a digest: the open card is
                h.update(ext.encode())                          # compared the same way (file_digest)
                h.update(file_digest(c.card.storage.read(p)))
        except (OSError, KeyError):
            return "unreadable:%s" % c.where
        return h.hexdigest()

    # ------------------------------------------------------------------ details
    def details(self, song: LibrarySong) -> LibrarySong:
        """Read tempo, time signature and 'recorded or not' from the song's SQT (first readable copy)."""
        if song.checked:
            return song
        song.checked = True
        if not song.titles:
            self._read_titles(song)
        song.damaged = self._damaged(song.copies[0]) if song.copies else []
        for c in song.copies:
            p = c.paths.get("SQT")
            if p is None:
                song.recorded = False
                return song
            try:
                parts = container.parse(c.card.storage.read(p), "SQT").parts
                found = sqt.read_songs(parts[0], parts[1] if len(parts) > 1 else b"")
            except Exception:                                   # an odd file never stops the library
                continue
            song.recorded = any(q.has_events for q in found)
            song.tempo = next((q.tempo for q in found if q.tempo), None)
            rid = next((q.rhythm_id for q in found if q.rhythm_id is not None), None)
            r = song_rhythm(rid, c.card.storage, c.paths.get("CMP"))
            song.meter = r.meter if r else None
            return song
        return song

    @staticmethod
    def _damaged(c: LibraryCopy) -> List[str]:
        """The song's files that cannot be read or unpacked (KN6000 files: checksum wrong), by type (PMT).
        The copies of a song are identical, so one copy says it for all."""
        bad = []
        for ext, p in sorted(c.paths.items()):
            try:
                container.parse(c.card.storage.read(p), ext)
            except Exception:                                   # unreadable, cut short, checksum wrong
                bad.append(ext)
        return bad

    def fill_details(self, progress: Optional[Progress] = None) -> None:
        for i, s in enumerate(self.songs):
            if progress:
                progress(i, len(self.songs), s.name)
            self.details(s)

    # ------------------------------------------------------------------ queries
    def is_floppy(self, card: LibraryCard) -> bool:
        """A diskette kept in the library (its original files are kept next to it)."""
        return card.storage.isdir(ORIGINALS)

    def fingerprint(self, song: LibrarySong) -> str:
        """The song's files (types and bytes) as one value; read once, then remembered."""
        fp = self._fingerprints.get(id(song))
        if fp is None:
            fp = self._fingerprints[id(song)] = self._fingerprint(song.copies[0])
        return fp

    def search(self, text: str = "", card: Optional[str] = None, recorded: Optional[bool] = None,
               tempo_min: Optional[int] = None, tempo_max: Optional[int] = None, meter: Optional[str] = None,
               spread: Optional[str] = None, source: Optional[str] = None,
               damaged: Optional[bool] = None) -> List[LibrarySong]:
        """Filter the songs. Tempo, time signature, recorded and damaged only match songs whose details
        are known. spread: "one" (on one kept card only) or "more" (on more than one); source: "card"
        (SD cards) or "floppy" (diskettes)."""
        t = text.strip().upper()
        floppies = {id(c) for c in self.cards if self.is_floppy(c)} if source else set()
        out = []
        for s in self.songs:
            if meter is not None and s.meter != meter:
                continue
            if spread == "one" and len(s.cards) != 1 or spread == "more" and len(s.cards) < 2:
                continue
            if source is not None and not any((id(c.card) in floppies) == (source == "floppy") for c in s.copies):
                continue
            if damaged is not None and (not s.checked or bool(s.damaged) is not damaged):
                continue
            if t and t not in s.name.upper() and not any(t in c.name.upper() for c in s.copies) \
                    and not s.matching_titles(text):
                continue
            if card is not None and card not in s.cards:
                continue
            if recorded is not None and s.recorded is not recorded:
                continue
            if tempo_min is not None and (s.tempo is None or s.tempo < tempo_min):
                continue
            if tempo_max is not None and (s.tempo is None or s.tempo > tempo_max):
                continue
            out.append(s)
        return out

    @property
    def copies(self) -> int:
        return sum(len(s.copies) for s in self.songs)

    def close(self) -> None:
        for c in self.cards:
            close = getattr(c.storage, "close", None)
            if close:
                close()


def copy_into(target: CardSession, song: LibrarySong, folder: int, slot: Optional[int] = None) -> int:
    """Put a library song on a card being composed (one undo step). Returns the 1-based slot."""
    c = song.copies[0]
    return target.import_song(c.card.storage, c.paths, song.name, folder, slot)
