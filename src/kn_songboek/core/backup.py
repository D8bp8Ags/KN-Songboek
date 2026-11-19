"""Back-ups of a card's music data as dated zip files, kept on the computer (not on the card).

A back-up holds everything under PRIVATE/TECHNICS/KN7000 (database, BAK and all song folders), so a
restore puts the card back exactly as it was. The keyboard's own KN7000MN.BAK is no history: after a
save it is a copy of the new database (see docs/nl/reference/kn7000mn-inf.md).
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sys
import zipfile
from collections import Counter
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..formats import layout
from ..formats.inf import MusicDatabase
from ..storage import windows
from ..storage.base import Storage
from ..storage.memory import MemoryStorage
from .errors import KN7Error, Text

IGNORED = {".DS_STORE", "THUMBS.DB", "DESKTOP.INI"}
_STAMP = "%Y%m%d-%H%M%S"
LIBRARY_SUFFIX = "-bibliotheek"     # back-ups of a library copy made before it was replaced (cards.archive_card)
SAME_CARD = 0.5                     # share of songs in common from which two back-ups are of the same card


def default_backup_dir() -> str:
    """$KN_SONGBOEK_BACKUP_DIR, else the platform's per-user data folder + KN Songboek/backups."""
    env = os.environ.get("KN_SONGBOEK_BACKUP_DIR")
    if env:
        return env
    home = os.path.expanduser("~")
    if sys.platform == "darwin":
        base = os.path.join(home, "Library", "Application Support")
    elif sys.platform.startswith("win"):
        base = os.environ.get("APPDATA", home)
    else:
        base = os.environ.get("XDG_DATA_HOME", os.path.join(home, ".local", "share"))
    return os.path.join(base, "KN Songboek", "backups")


def card_label(storage: Storage) -> str:
    """A file-name-safe name for the card, from its folder or volume name."""
    where = storage.describe()
    name = windows.drive_label(where) or os.path.basename(where.rstrip("/\\")) or "card"   # E:\ -> its label
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "card"


@dataclass(frozen=True)
class BackupInfo:
    path: str
    created: str          # ISO time from the file name
    files: int
    songs: int            # used songs in the database inside the zip, -1 if unreadable
    label: str = ""       # the folder it is in: the card's name (several cards can share one, e.g. NO NAME)

    @property
    def library(self) -> bool:
        """A back-up of a library copy rather than of an SD card."""
        return self.label.endswith(LIBRARY_SUFFIX)

    @property
    def card_name(self) -> str:
        return self.label[:-len(LIBRARY_SUFFIX)] if self.library else self.label


def walk(storage: Storage, root: str = layout.KN7_DIR) -> List[str]:
    """All file paths below root (card paths), skipping OS litter."""
    out: List[str] = []
    for name in storage.listdir(root):
        if name.upper() in IGNORED or name.upper().endswith(".TMP"):
            continue
        p = root + "/" + name
        if storage.isdir(p):
            out.extend(walk(storage, p))
        else:
            out.append(p)
    return out


def make_backup(storage: Storage, backup_dir: Optional[str] = None, keep: int = 10,
                label: Optional[str] = None, now: Optional[_dt.datetime] = None,
                progress: Callable[[int, int, str], None] = None) -> str:
    """Zip PRIVATE/TECHNICS/KN7000 into backup_dir/<label>/<label>-<stamp>.zip; prune to `keep`."""
    backup_dir = backup_dir or default_backup_dir()
    label = label or card_label(storage)
    folder = os.path.join(backup_dir, label)
    os.makedirs(folder, exist_ok=True)
    stamp = (now or _dt.datetime.now()).strftime(_STAMP)
    target = os.path.join(folder, "%s-%s.zip" % (label, stamp))
    n = 1
    while os.path.exists(target):
        n += 1
        target = os.path.join(folder, "%s-%s-%d.zip" % (label, stamp, n))
    files = walk(storage)
    tmp = target + ".part"
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for i, p in enumerate(files):
            if progress:
                progress(i, len(files), p)
            z.writestr(p, storage.read(p))
    os.replace(tmp, target)
    if keep > 0:
        prune(folder, target, keep)
    return target


def prune(folder: str, newest: str, keep: int) -> List[str]:
    """Remove all but the `keep` newest back-ups of the same card as `newest`. Two different cards with
    the same name (NO NAME, KN7000) share a folder: back-ups of the other card are never removed."""
    mine = song_names(newest)
    same = [b for b in list_backups(folder) if b.path == newest or similarity(mine, song_names(b.path)) >= SAME_CARD]
    gone = []
    for old in same[keep:]:
        os.remove(old.path)
        gone.append(old.path)
    return gone


def list_backups(folder: str) -> List[BackupInfo]:
    """Back-ups in one card's folder, newest first."""
    out = []
    if not os.path.isdir(folder):
        return out
    for name in os.listdir(folder):
        if not name.lower().endswith(".zip"):
            continue
        m = re.search(r"(\d{8}-\d{6})(?:-\d+)?\.zip$", name)
        created = _dt.datetime.strptime(m.group(1), _STAMP).isoformat() if m else ""
        path = os.path.join(folder, name)
        try:
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
                try:
                    db = MusicDatabase.from_bytes(z.read(_find(names, layout.INF_PATH)))
                    songs = sum(1 for _ in db.iter_songs())
                except Exception:
                    songs = -1
        except zipfile.BadZipFile:
            continue
        out.append(BackupInfo(path, created, len(names), songs, os.path.basename(os.path.normpath(folder))))
    out.sort(key=lambda b: (b.created, b.path), reverse=True)
    return out


def list_all(backup_dir: Optional[str] = None) -> List[BackupInfo]:
    """Back-ups of every card (and every replaced library copy), newest first."""
    backup_dir = backup_dir or default_backup_dir()
    out: List[BackupInfo] = []
    if os.path.isdir(backup_dir):
        for name in sorted(os.listdir(backup_dir)):
            p = os.path.join(backup_dir, name)
            if os.path.isdir(p) and not name.startswith("."):
                out.extend(list_backups(p))
    out.sort(key=lambda b: (b.created, b.path), reverse=True)
    return out


def database(zip_path: str) -> MusicDatabase:
    """The card's database as it was in the back-up."""
    with zipfile.ZipFile(zip_path) as z:
        return MusicDatabase.from_bytes(z.read(_find(z.namelist(), layout.INF_PATH)))


def contents(zip_path: str) -> List[Tuple[int, str, List[str]]]:
    """(folder number, folder name, song names) of every folder with songs in the back-up."""
    db = database(zip_path)
    return [(fi + 1, fo.name, [x.name for x in fo.songs if x.used])
            for fi, fo in enumerate(db.folders) if any(x.used for x in fo.songs)]


def song_names(zip_path: str) -> Counter:
    try:
        return Counter(s.name for _, _, s in database(zip_path).iter_songs())
    except (KeyError, zipfile.BadZipFile, OSError, KN7Error, ValueError):
        return Counter()


def card_song_names(storage: Storage) -> Counter:
    try:
        return Counter(s.name for _, _, s in MusicDatabase.from_bytes(storage.read(layout.INF_PATH)).iter_songs())
    except (KeyError, OSError, KN7Error, ValueError):
        return Counter()


def similarity(a: Counter, b: Counter) -> float:
    """Share of songs two cards have in common (by name): 1.0 the same, 0 nothing alike."""
    if not a or not b:
        return 1.0 if not a and not b else 0.0
    return sum((a & b).values()) / max(sum(a.values()), sum(b.values()))


def as_storage(zip_path: str) -> MemoryStorage:
    """The back-up as a card in memory, to look at or to put somewhere else (another card, the library)."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        _check_zip(names, zip_path)
        return MemoryStorage({n: z.read(n) for n in names if not n.endswith("/")})


def _find(names: List[str], path: str) -> str:
    for n in names:
        if n.upper() == path.upper():
            return n
    raise KeyError(path)


def restore_plan(storage: Storage, zip_path: str) -> List[str]:
    """What restore() would do, as 'write X' / 'delete Y' lines."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
    _check_zip(names, zip_path)
    keep = {n.upper() for n in names}
    plan = ["write " + n for n in names]
    plan += ["delete " + p for p in walk(storage) if p.upper() not in keep]
    return plan


def restore(storage: Storage, zip_path: str, progress: Callable[[int, int, str], None] = None) -> int:
    """Put the card's KN7000 folder back to the state in the zip. Files that are not in the back-up
    are deleted, so take a back-up of the current state first (the CLI does). Returns #operations."""
    if not storage.writable():
        raise KN7Error(Text("locked", "{card} is write-protected (is the lock switch on the SD card down?)", card=storage.describe()))
    plan = restore_plan(storage, zip_path)
    with zipfile.ZipFile(zip_path) as z:
        # database last, so an interrupted restore leaves the old database pointing at files
        # that are mostly still there rather than a new database without its files
        names = sorted(z.namelist(), key=lambda n: n.upper() in (layout.INF_PATH.upper(), layout.BAK_PATH.upper()))
        deletes = [line[7:] for line in plan if line.startswith("delete ")]
        total = len(names) + len(deletes)
        for i, p in enumerate(deletes):
            if progress:
                progress(i, total, "delete " + p)
            storage.remove(p)
        for i, n in enumerate(names, len(deletes)):
            if progress:
                progress(i, total, "write " + n)
            storage.write(n, z.read(n))
    return total


def _check_zip(names: List[str], zip_path: str) -> None:
    prefix = layout.KN7_DIR.upper() + "/"
    bad = [n for n in names if not n.upper().startswith(prefix) or ".." in n.split("/")]
    if bad:
        raise KN7Error(Text("not_backup", "{path} is not a KN Songboek back-up (unexpected entry {entry})", path=zip_path, entry=bad[0]))
    _find(names, layout.INF_PATH)
