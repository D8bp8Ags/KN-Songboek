"""Cards that are in the computer, and moving whole cards between a card and the library (ADR-0008).

- find_cards():      the SD cards (and other drives) that are mounted now, each classified as a KN7000
                     card, an empty card or something else.
- archive_card():    copy a card into the library under the name on its label; replacing an earlier
                     copy first zips that copy into the back-ups.
- match_library():   which library copy a card is, judged by its songs (no index, no marker file).
- new_card():        an empty card in memory to compose a new card in.
- write_card():      put a composed card on a real card (old KN7000 data is backed up and replaced).
- eject():           unmount a card so it can be pulled out (macOS; elsewhere a no-op).

Card detection looks in the platform's mount folders; $KN_SONGBOEK_VOLUMES (folders separated by os.pathsep)
replaces them, for tests.
"""
from __future__ import annotations

import os
import plistlib
import shutil
import string
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from . import verify

from ..formats import layout
from ..storage import windows
from ..storage import DirectoryStorage
from ..storage.base import Storage
from ..storage.memory import MemoryStorage
from .backup import IGNORED, make_backup, walk
from .errors import KN7Error, Text
from .session import CardSession

Progress = Callable[[int, int, str], None]

KN7000, EMPTY, OTHER, FLOPPY = "kn7000", "empty", "other", "floppy"
SD_SOUND_DIR = "SD_SOUND"
# what an operating system puts on a fresh card by itself
_SYSTEM_NAMES = IGNORED | {".SPOTLIGHT-V100", ".FSEVENTSD", ".TRASHES", ".TEMPORARYITEMS",
                           "SYSTEM VOLUME INFORMATION", "$RECYCLE.BIN", "RECYCLER", "._.TRASHES",
                           ".METADATA_NEVER_INDEX"}


@dataclass
class CardInfo:
    path: str
    name: str                  # volume name as the computer shows it
    kind: str                  # KN7000, EMPTY, OTHER or FLOPPY (a KN6000/KN7000 music diskette)
    songs: int = 0             # used songs, for a KN7000 card; sets, for a diskette
    free: Optional[int] = None
    total: Optional[int] = None
    writable: bool = True      # False: locked SD card (switch on LOCK) or write-protected diskette


# ---------------------------------------------------------------------------- detection
def volume_roots() -> List[str]:
    env = os.environ.get("KN_SONGBOEK_VOLUMES")
    if env is not None:
        return [p for p in env.split(os.pathsep) if p]
    if sys.platform == "darwin":
        return ["/Volumes"]
    if sys.platform.startswith("win"):
        return []                                       # drive letters, see _mounted()
    user = os.environ.get("USER", "")
    return ["/media/" + user, "/run/media/" + user, "/media"]


def _mounted() -> List[str]:
    out: List[str] = []
    if sys.platform.startswith("win") and "KN_SONGBOEK_VOLUMES" not in os.environ:
        windows.no_error_dialogs()                      # an empty floppy drive: no "no disk" box
        for letter in string.ascii_uppercase:           # A:/B: = diskette drive; C: = Windows itself
            p = letter + ":\\"
            if letter != "C" and os.path.isdir(p):
                out.append(p)
        return out
    for root in volume_roots():
        try:
            names = sorted(os.listdir(root), key=str.lower)
        except OSError:
            continue
        for n in names:
            p = os.path.join(root, n)
            if n.startswith(".") or not os.path.isdir(p) or p in out:
                continue
            if os.path.realpath(p) == os.path.realpath(os.sep):   # macOS boot disk link
                continue
            out.append(p)
    return out


def _visible(path: str) -> List[str]:
    try:
        return [n for n in os.listdir(path) if n.upper() not in _SYSTEM_NAMES and not n.startswith("._")]
    except OSError:
        return []


def classify(path: str) -> CardInfo:
    name = windows.display_name(path)
    st = DirectoryStorage(path)
    free = st.free_bytes()
    w = st.writable()
    try:
        total: Optional[int] = shutil.disk_usage(path).total
    except OSError:
        total = None
    if st.exists(layout.INF_PATH) or st.exists(layout.BAK_PATH):
        try:
            songs = sum(1 for _ in CardSession.open(st).db.iter_songs())
        except KN7Error:
            songs = 0
        return CardInfo(path, name, KN7000, songs, free, total, w)
    from . import floppy
    found = floppy.sets(st) if not st.isdir("PRIVATE") else []
    if found:
        return CardInfo(path, name, FLOPPY, len(found), free, total, w)
    visible = _visible(path)
    if not visible or visible == ["PRIVATE"] and not _visible(os.path.join(path, "PRIVATE")):
        return CardInfo(path, name, EMPTY, 0, free, total, w)
    return CardInfo(path, name, OTHER, 0, free, total, w)


def find_cards() -> List[CardInfo]:
    """Every mounted drive, KN7000 cards first, then empty ones, then the rest."""
    order = {KN7000: 0, FLOPPY: 1, EMPTY: 2, OTHER: 3}
    cards = [classify(p) for p in _mounted()]
    cards.sort(key=lambda c: (order[c.kind], c.name.lower()))
    return cards


# ---------------------------------------------------------------------------- library
def default_library() -> str:
    return os.path.join(os.path.expanduser("~"), "Documents", "KN7000 Bibliotheek")


def safe_name(name: str) -> str:
    """A folder name from what the user typed (the label on the card)."""
    bad = '<>:"/\\|?*'
    out = "".join("_" if c in bad or ord(c) < 32 else c for c in name).strip().strip(".")
    if not out:
        raise KN7Error(Text("no_name", "give the card a name"))
    if out.split(".")[0].upper() in _WINDOWS_RESERVED:  # names Windows keeps for itself (CON, AUX, ...)
        out += "_"
    return out


_WINDOWS_RESERVED = {"CON", "PRN", "AUX", "NUL"} | {"COM%d" % i for i in range(1, 10)} | {"LPT%d" % i for i in range(1, 10)}


def _copy_tree(src: Storage, dst: str, roots: List[str], progress: Optional[Progress],
               check: Optional[verify.CopyCheck] = None) -> int:
    """Copy every file under roots, each one checked (core/verify.py); the counts go into check."""
    check = check if check is not None else verify.CopyCheck()
    files: List[str] = []
    for r in roots:
        if src.isdir(r):
            files += walk(src, r)
    target = DirectoryStorage(dst)
    for i, p in enumerate(files):
        if progress:
            progress(i, len(files), p)
        verify.write_checked(target, p, verify.read_checked(src, p, check), check)
    return len(files)


def archive_card(card: Storage, library: str, name: str, replace: bool = False,
                 progress: Optional[Progress] = None, backup_dir: Optional[str] = None,
                 check: Optional[verify.CopyCheck] = None) -> str:
    """Copy the card's KN7000 data (and SD_SOUND) into library/name. Returns the folder. Every file is
    checked on the way (core/verify.py); what was checked goes into check, for the app to say.

    If that folder exists, replace must be True; the old copy is zipped into the back-ups first, and
    swapped out only after the new copy is complete."""
    if not card.exists(layout.INF_PATH) and not card.exists(layout.BAK_PATH):
        raise KN7Error(Text("not_kn7000", "{card} is not a KN7000 card", card=card.describe()))
    folder = os.path.join(library, safe_name(name))
    if os.path.exists(folder) and not replace:
        raise KN7Error(Text("name_in_library", "there is already a card called {name} in the library", name=name))
    os.makedirs(library, exist_ok=True)
    part = folder + ".part"
    if os.path.exists(part):
        shutil.rmtree(part)
    try:
        _copy_tree(card, part, [layout.KN7_DIR, SD_SOUND_DIR], progress, check)
    except BaseException:                               # a failed check: no half copy left behind
        shutil.rmtree(part, ignore_errors=True)
        raise
    if os.path.exists(folder):
        old = DirectoryStorage(folder)
        if old.exists(layout.INF_PATH):
            make_backup(old, backup_dir, label=os.path.basename(folder) + "-bibliotheek")
        trash = folder + ".old"
        if os.path.exists(trash):
            shutil.rmtree(trash)
        os.replace(folder, trash)
        os.replace(part, folder)
        shutil.rmtree(trash)
    else:
        os.replace(part, folder)
    return folder


def _song_keys(storage: Storage) -> Counter:
    """(name, types, sizes) of every song: what a copy of the same card has too."""
    keys: Counter = Counter()
    try:
        db = CardSession.open(storage).db
    except KN7Error:
        return keys
    for fi, si, s in db.iter_songs():
        sizes = []
        for ext, p in sorted(layout.song_paths(fi, si, s).items()):
            try:
                sizes.append((ext, storage.size(p)))
            except (OSError, KeyError):
                sizes.append((ext, -1))
        keys[(s.name, tuple(sizes))] += 1
    return keys


def match_library(card: Storage, library: str, minimum: float = 0.5) -> List[Tuple[str, str, float]]:
    """Library copies that look like this card: (label, path, share of songs in common), best first.

    Only folder copies are considered (an image file is not updated in place)."""
    from .library import find_cards as library_cards
    mine = _song_keys(card)
    if not mine or not os.path.isdir(library):
        return []
    out = []
    for label, path in library_cards(library):
        if not os.path.isdir(path):
            continue
        theirs = _song_keys(DirectoryStorage(path))
        if not theirs:
            continue
        common = sum((mine & theirs).values())
        score = common / max(sum(mine.values()), sum(theirs.values()))
        if score >= minimum:
            out.append((label, path, score))
    out.sort(key=lambda x: -x[2])
    return out


# ---------------------------------------------------------------------------- composing
def new_card() -> CardSession:
    """An empty card in memory. Songs are imported into it as usual; write_card() puts it on a card."""
    return CardSession.create(MemoryStorage())


def new_card_from(source: CardSession) -> CardSession:
    """A new card in memory that starts as a copy of another card (a library copy): every folder on its
    own number with its name, the song lists and the favourites. Nothing is undoable yet: it is the
    starting point, like an empty new card."""
    s = new_card()
    for fi, fo in enumerate(source.db.folders):
        if any(x.used for x in fo.songs):
            s.import_folder(source, fi + 1, fi + 1)
        elif fo.name:
            s.rename_folder(fi + 1, fo.name)
    for n in range(3):
        s.db.set_playlist(n, list(source.db.playlist(n)))
    for mine, theirs in zip(s.db.favorites, source.db.favorites):
        mine.name = theirs.name
        mine.items[:] = theirs.items
    s._undo.clear()
    s._redo.clear()
    return s


def write_card(session: CardSession, target: Storage, progress: Optional[Progress] = None,
               backup_dir: Optional[str] = None, phase: Optional[Callable[[str], None]] = None) -> Optional[str]:
    """Put a card composed with new_card() on target. Returns the back-up of what was there, if anything.

    First the space is checked (nothing is touched when it does not fit); then the KN7000 folder on
    target is backed up and removed; the composed plan (imports from the library, and any moves or
    deletes after them) is then carried out on target. Other files on the card (SD_SOUND, the user's
    own files) are left alone. phase("space"), "backup", "write", "verify" say where it is."""
    if not isinstance(session.storage, MemoryStorage) or session.storage.listdir(layout.KN7_DIR) != ["KN7000MN.INF"]:
        raise KN7Error(Text("not_composed", "only a card made with 'new card' can be written this way"))
    if not target.writable():
        raise KN7Error(Text("locked", "{card} is write-protected (is the lock switch on the SD card down?)", card=target.describe()))
    if phase:
        phase("space")
    backup = None
    old = walk(target) if target.isdir(layout.KN7_DIR) else []
    free = target.free_bytes()
    if free is not None:
        free += sum(target.size(p) for p in old)
        need = session.bytes_needed() + 2 * 0xD620
        if need > free:
            raise KN7Error(Text("no_space", "not enough space on {card}: {need} KB needed, {free} KB free",
                                card=target.describe(), need=(need + 1023) // 1024, free=free // 1024))
    if old:
        if phase:
            phase("backup")
        backup = make_backup(target, backup_dir)
    for p in old:
        target.remove(p)
    session.storage = target
    session.save(backup=True, progress=progress, phase=phase)
    return backup


VOLUME_MAX = 11                 # an SD card's name (FAT volume label)
_FAT_BAD = '"*+,./:;<=>?[\\]|'


def volume_name(text: str) -> str:
    """What an SD card can be called (a FAT volume label): at most 11 plain characters, capitals."""
    out = "".join(c for c in text.upper() if " " <= c <= "~" and c not in _FAT_BAD)
    return out.strip()[:VOLUME_MAX].strip()


def _disk_info(what: str) -> dict:
    r = subprocess.run(["diskutil", "info", "-plist", what], capture_output=True, timeout=30)
    return plistlib.loads(r.stdout) if r.returncode == 0 else {}


def rename_volume(path: str, name: str) -> Optional[str]:
    """Give the card in path the name on its label (macOS and Windows). Returns where it is mounted now,
    or None if it could not be renamed (other systems, or the system said no)."""
    name = volume_name(name)
    if windows.WINDOWS and name:
        return path if windows.set_drive_label(path, name) else None
    if sys.platform != "darwin" or not name:
        return None
    if os.path.basename(os.path.normpath(path)) == name:
        return path
    try:
        dev = _disk_info(path).get("DeviceIdentifier")
        if not dev:
            return None
        r = subprocess.run(["diskutil", "rename", dev, name], capture_output=True, timeout=60)
        if r.returncode != 0:
            return None
        return _disk_info(dev).get("MountPoint") or None
    except (OSError, subprocess.SubprocessError, plistlib.InvalidFileException, ValueError):
        return None


def eject(path: str) -> bool:
    """Unmount the card so it can be pulled out. True if done (macOS and Windows; else False)."""
    if windows.WINDOWS:
        return windows.eject_drive(path)
    if sys.platform != "darwin" or not os.path.ismount(path):    # never the disk a plain folder is on
        return False
    try:
        r = subprocess.run(["diskutil", "eject", path], capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0
