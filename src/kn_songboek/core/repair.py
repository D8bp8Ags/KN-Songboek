"""Rebuild the music database from the song files on the card.

Use after an interrupted save, a card edited by hand on a computer, or a lost KN7000MN.INF.
The keyboard does something similar when it finds no usable database (func_4855F2F2/F56A).

Song files of KN7000 songs do not carry the song name (checked on a real card, 2026-11-15), so names
come from, in this order: the previous database (INF or BAK) where the same slot still has the same
files; the KN6000 name field in LSW (+0x26) or PMT (+0x13) for 'I KD' songs; otherwise "SONG fff-ss".
Folder names, favourites and song lists are kept from the previous database; favourites and list
entries that point at a slot that no longer holds a song are cleared.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..formats import container, layout
from ..formats.inf import FILE_TYPES, INFError, MusicDatabase, N_FOLDERS, N_SONGS, Song
from ..storage.base import Storage

_FILE = re.compile(r"^(\d\d)(.{6})\.([A-Z]{2,3})$")


@dataclass
class RepairReport:
    added: List[Tuple[int, int, str]] = field(default_factory=list)      # 1-based folder, song, name
    removed: List[Tuple[int, int, str]] = field(default_factory=list)
    changed: List[Tuple[int, int, str]] = field(default_factory=list)    # file types differ
    unknown_files: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)                   # two bases in one slot

    @property
    def nothing_to_do(self) -> bool:
        return not (self.added or self.removed or self.changed)


def _previous(storage: Storage) -> Optional[MusicDatabase]:
    for p in (layout.INF_PATH, layout.BAK_PATH):
        try:
            return MusicDatabase.from_bytes(storage.read(p))
        except (OSError, KeyError, INFError):
            continue
    return None


def _kn6000_name(storage: Storage, files: Dict[str, str]) -> str:
    for ext, off in (("LSW", 0x26), ("PMT", 0x13)):
        p = files.get(ext)
        if not p:
            continue
        try:
            data = storage.read(p)
            parts = container.parse(data, ext).parts
        except Exception:
            continue
        raw = parts[0] if parts else b""
        if (ext == "LSW" and raw[:2] == b"ZZ") or (ext == "PMT" and raw[:3] == b"IK "):
            name = raw[off:off + 16].split(b"\x00")[0].decode("latin-1").strip()
            if name:
                return name
    return ""


def scan(storage: Storage) -> Tuple[Dict[Tuple[int, int], Tuple[str, Dict[str, str]]], RepairReport]:
    """(0-based folder, song) -> (base, {ext: card path}) for every song file group on the card."""
    found: Dict[Tuple[int, int], Tuple[str, Dict[str, str]]] = {}
    rep = RepairReport()
    for d in storage.listdir(layout.KN7_DIR):
        m = re.match(r"^TFLD(\d{3})$", d.upper())
        if not m or not 1 <= int(m.group(1)) <= N_FOLDERS:
            continue
        fi = int(m.group(1)) - 1
        for name in storage.listdir(layout.KN7_DIR + "/" + d):
            path = layout.KN7_DIR + "/" + d + "/" + name
            fm = _FILE.match(name.upper())
            if not fm or fm.group(3) not in [e.strip() for e in FILE_TYPES] or not 1 <= int(fm.group(1)) <= N_SONGS:
                if name.upper() not in (".DS_STORE", "THUMBS.DB"):
                    rep.unknown_files.append(path)
                continue
            si, base, ext = int(fm.group(1)) - 1, fm.group(2), fm.group(3)
            if (fi, si) in found and found[(fi, si)][0] != base:
                rep.conflicts.append("%s: also %s" % (path, found[(fi, si)][0]))
                continue
            found.setdefault((fi, si), (base, {}))[1][ext] = path
    return found, rep


def rebuild(storage: Storage, previous: Optional[MusicDatabase] = None) -> Tuple[MusicDatabase, RepairReport]:
    prev = previous if previous is not None else _previous(storage)
    db = prev.copy() if prev is not None else MusicDatabase.new()
    found, rep = scan(storage)
    exts = [e.strip() for e in FILE_TYPES]
    for fi in range(N_FOLDERS):
        for si in range(N_SONGS):
            old = prev.song(fi, si) if prev is not None else Song()
            hit = found.get((fi, si))
            if hit is None:
                if old.used:
                    rep.removed.append((fi + 1, si + 1, old.name))
                    db.folders[fi].songs[si] = Song()
                    db.purge_slot(fi, si)
                continue
            base, files = hit
            types = 0
            for ext in files:
                types |= 1 << exts.index(ext)
            same_base = old.used and (old.base or layout.default_base(fi)).upper() == base.upper()
            if same_base:
                if old.types != types:
                    rep.changed.append((fi + 1, si + 1, old.name))
                    new = Song(old.name, old.base, types, old.raw_name, old.raw_base)
                    db.folders[fi].songs[si] = new
                continue
            name = _kn6000_name(storage, files) or "SONG %03d-%02d" % (fi + 1, si + 1)
            if old.used:
                rep.removed.append((fi + 1, si + 1, old.name))
                db.purge_slot(fi, si)
            db.folders[fi].songs[si] = Song(name[:16], base, types)
            rep.added.append((fi + 1, si + 1, name[:16]))
    return db, rep
