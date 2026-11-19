"""Oefenen ("Eerst oefenen?"): a made-up computer with a card reader, a library and back-ups of its own,
so the three tasks go exactly as they do for real (same code, same screens), without touching a real
card or the real library.

It lives in the app's own data folder (next to the back-ups), never on an SD card, and starts fresh
each time. Only invented song and folder names are used.

    oefenen/
      Kaartlezer/     the cards "in the computer" (find_cards looks here; eject takes them out)
      Kast/           the cards that are out of the computer (taken out, or not put in yet)
      Bibliotheek/    the practice library, with one kept card in it
      Back-ups/       the practice back-ups
"""
from __future__ import annotations

import os
import shutil
import struct
from typing import List, Optional

from . import cards
from ..formats import container
from ..storage import DirectoryStorage
from ..storage.memory import MemoryStorage
from .backup import default_backup_dir
from .session import CardSession

MARK = "OEFENEN.TXT"             # only a folder with this file in it is ever replaced by a fresh one

SONGS_CARD = "OEFENKAART"        # the card with songs that is in the reader at the start
FOLDERS = {
    1: ("FEEST", [("HET IS FEEST", 128), ("POLONAISE", 120), ("LAATSTE RONDE", 132)]),
    2: ("WALSEN", [("AVONDWALS", 90), ("KERMISWALS", 96)]),
    3: ("LATIN", [("SAMBA ZON", 100), ("RUMBA ROOD", 104), ("CHA CHA", 112)]),
    5: ("OEFENEN", [("PROBEER MIJ", 110)]),
}


KEPT_CARD = "Oefenkaart van vorig jaar"     # in the practice library: songs to make a new card from
KEPT_FOLDERS = {
    1: ("DANSEN", [("TANGO NACHT", 118), ("FOXTROT", 124), ("QUICKSTEP", 200)]),
    2: ("ROCK", [("ROCK RONDE", 140), ("TWIST", 150)]),
    4: ("RUSTIG", [("SLAAPLIEDJE", 70), ("AVONDROOD", 80)]),
}


def practice_dir(backup_dir: str = "") -> str:
    base = os.path.dirname(os.path.normpath(backup_dir or default_backup_dir()))
    return os.path.join(base, "oefenen")


def _name16(s: str) -> bytes:
    return s.encode("latin-1").ljust(16, b" ")


def _song_file(tempo: int) -> bytes:
    """A song record as the keyboard writes it, with its tempo, and no recorded tracks."""
    r = bytearray(0x8E0)
    r[0:7] = b"ZZZZ\x01\x01\x0d"
    for t in range(16):
        struct.pack_into("<BH", r, 0xD0 + 3 * t, 0, 0xFFFF)
    r[0x100:0x110] = b"_" * 16
    pm = bytes([0x42, 14]) + bytes([0x5A, 0, 0, 0x10, 0, 0, 0, 0, tempo, 0, 0, 0, 0, 0]) + b"\xff\xff"
    r[0x140:0x140 + len(pm)] = pm
    return container.build_kd2(bytes(r), b"")


def _memory_file(name: str, tempo: int) -> bytes:
    """Panel memories: 3 banks of 8 buttons, all with the song's tempo."""
    mem = 0x750
    d = bytearray(0x10 + 3 * (0x10 + 8 * mem))
    d[0:4] = b"JK \0"
    d[0x0C:0x10] = b"P\x07\x18\x00"
    for b in range(3):
        base = 0x10 + b * (0x10 + 8 * mem)
        d[base:base + 16] = _name16("Bank %d" % (b + 1))
        for m in range(8):
            o = base + 0x10 + m * mem
            blk = bytes([0x40, 18]) + _name16(("%s %d" % (name[:13], m + 1))[:16]) + b"\0\0"
            blk += bytes([0x42, 14, 0x14, 4, 0, 0x12, 0, 0, 0, 0]) + struct.pack("<H", tempo) + bytes(4)
            blk += b"\xff\xff"
            d[o:o + len(blk)] = blk
    return container.build_kd(bytes(d))


def make_practice_card(path: str, folders=None) -> str:
    """A practice card with invented songs in path (a new folder)."""
    s = CardSession.create(DirectoryStorage(path))
    src = MemoryStorage()
    for folder, (fname, songs) in (folders or FOLDERS).items():
        s.rename_folder(folder, fname)
        for k, (name, tempo) in enumerate(songs):
            key = "%d_%d" % (folder, k)              # own files per song: they are copied at save time
            src.write(key + ".SQT", _song_file(tempo))
            src.write(key + ".PMT", _memory_file(name, tempo))
            s.import_song(src, {"SQT": key + ".SQT", "PMT": key + ".PMT"}, name, folder)
    s.set_favorite(1, 1, (1, 1))
    s.set_song_list(1, [(1, 1), (2, 1)])
    s.save(backup=False)
    return path


def _free_name(path: str) -> str:
    n = 2
    while os.path.exists("%s %d" % (path, n)):
        n += 1
    return "%s %d" % (path, n)


class PracticeWorld:
    """The made-up computer. find_cards, eject and volume_roots stand in for core/cards' own, so the
    app's code runs unchanged on it."""

    def __init__(self, root: str):
        self.root = root
        self.reader = os.path.join(root, "Kaartlezer")
        self.shelf = os.path.join(root, "Kast")
        self.library = os.path.join(root, "Bibliotheek")
        self.backups = os.path.join(root, "Back-ups")

    @classmethod
    def make(cls, root: str) -> "PracticeWorld":
        """A fresh world in root (an earlier one there is replaced; any other folder is left alone and
        a new one is made next to it)."""
        if os.path.exists(root):
            if os.path.isfile(os.path.join(root, MARK)):
                shutil.rmtree(root)
            else:
                root = _free_name(root)
        w = cls(root)
        for d in (w.reader, w.shelf, w.library, w.backups):
            os.makedirs(d)
        make_practice_card(os.path.join(w.reader, SONGS_CARD))
        make_practice_card(os.path.join(w.library, KEPT_CARD), KEPT_FOLDERS)
        with open(os.path.join(root, MARK), "w", encoding="utf-8") as fh:
            fh.write("Oefenen met KN Songboek. Begint elke keer opnieuw; hier staat niets van een echte kaart.\n")
        return w

    @staticmethod
    def _dirs(path: str) -> List[str]:
        return sorted(os.path.join(path, n) for n in os.listdir(path)
                      if not n.startswith(".") and os.path.isdir(os.path.join(path, n)))

    def find_cards(self) -> List[cards.CardInfo]:
        order = {cards.KN7000: 0, cards.FLOPPY: 1, cards.EMPTY: 2, cards.OTHER: 3}
        return sorted((cards.classify(p) for p in self._dirs(self.reader)), key=lambda c: (order[c.kind], c.name.lower()))

    def volume_roots(self) -> List[str]:
        return [self.reader]

    def eject(self, path: str) -> bool:
        """Take the card out of the reader: it goes to the shelf. An empty card is not kept there (a new,
        empty one can always be put in), so the list of cards to choose from only shows cards with songs."""
        if os.path.normpath(os.path.dirname(os.path.normpath(path))) != os.path.normpath(self.reader):
            return False
        if cards.classify(path).kind == cards.EMPTY:
            shutil.rmtree(path)                  # inside this practice world only (path is in its reader)
            return True
        dst = os.path.join(self.shelf, os.path.basename(os.path.normpath(path)))
        os.replace(path, _free_name(dst) if os.path.exists(dst) else dst)
        return True

    def in_reader(self) -> List[str]:
        return [os.path.basename(p) for p in self._dirs(self.reader)]

    def on_shelf(self) -> List[str]:
        return [os.path.basename(p) for p in self._dirs(self.shelf)]

    def insert(self, name: Optional[str]) -> str:
        """Put a card in the reader, as the player does by hand: the card on the shelf with this name,
        or (None) a new, empty SD card. The card that was in comes out first. Returns its name."""
        for p in self._dirs(self.reader):
            self.eject(p)
        if name is None:
            name, n = "SD-KAART", 1
            while os.path.exists(os.path.join(self.shelf, name)):    # a written card with that name is out
                n += 1
                name = "SD-KAART %d" % n
            path = os.path.join(self.reader, name)
            os.makedirs(path)
        else:
            path = os.path.join(self.reader, name)
            os.replace(os.path.join(self.shelf, name), path)
        return os.path.basename(path)

    def rename_volume(self, path: str, name: str) -> Optional[str]:
        """The new card gets its name, as an SD card's label does."""
        name = cards.volume_name(name)
        if not name:
            return None
        if os.path.basename(os.path.normpath(path)) == name:
            return path
        dst = os.path.join(os.path.dirname(os.path.normpath(path)), name)
        if os.path.exists(dst) or os.path.exists(os.path.join(self.shelf, name)):
            return None
        os.replace(path, dst)
        return dst
