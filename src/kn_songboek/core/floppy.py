"""KN6000/KN7000 music floppies: read the sets on a diskette and keep them in the library as a card.

A music floppy is a plain PC diskette (FAT12, 1.44 MB) with the files in its root and no index file.
Each saved set is a group of files `<nn><name6>.<EXT>`: nn is the number on the disk, name6 the name the
player typed (padded with "_"), EXT one of the song file types the SD card knows too (AST CMP EFC LSW PMT
SQT TM ...). So a set maps onto one SD song, and a diskette onto a card with its sets in folder 01.

The library copy is a normal card folder (KN7000MN.INF + TFLD001), so everything that works on a card
works on a diskette too. The diskette's own files are kept unchanged next to it in DISKETTE/, so nothing
is lost while it is not yet known how every KN6000 file behaves on the KN7000's SD card.
"""
from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from . import verify

from ..formats.inf import FILE_TYPES
from ..storage import DirectoryStorage
from ..storage.base import Storage
from .errors import KN7Error, Text
from .session import CardSession, check_name

Progress = Callable[[int, int, str], None]
ORIGINALS = "DISKETTE"                   # the diskette's own files, unchanged, inside the library copy
_SET = re.compile(r"^(\d\d)(.{1,6})\.([A-Z]{2,3})$", re.IGNORECASE)


@dataclass
class FloppySet:
    number: int                          # the nn in the file names
    name: str                            # as typed on the keyboard, "_" padding removed
    files: Dict[str, str] = field(default_factory=dict)      # EXT -> file name on the diskette


def sets(storage: Storage) -> List[FloppySet]:
    """The saved sets in the root of a diskette, in disk order."""
    found: Dict[str, FloppySet] = {}
    for n in storage.listdir(""):
        m = _SET.match(n)
        if not m or m.group(3).upper() not in FILE_TYPES or storage.isdir(n):
            continue
        key = (m.group(1) + m.group(2)).upper()
        s = found.get(key)
        if s is None:
            raw = m.group(2).upper().rstrip("_").replace("_", " ").strip()
            s = found[key] = FloppySet(int(m.group(1)), _plain(raw) or "SET %s" % m.group(1))
        s.files[m.group(3).upper()] = n
    return sorted(found.values(), key=lambda s: (s.number, s.name))


def _plain(name: str) -> str:
    out = "".join(c if " " <= c <= "~" else "?" for c in name)[:16]
    try:
        check_name(out)
    except KN7Error:
        return ""
    return out


def fingerprint(storage: Storage) -> List[tuple]:
    """(file name, size) of every set file: the same diskette gives the same list."""
    return sorted((n.upper(), storage.size(n)) for st in sets(storage) for n in st.files.values())


def find_copy(storage: Storage, where: str) -> Optional[str]:
    """The library folder under `where` that holds this very diskette already, if any."""
    mine = fingerprint(storage)
    if not mine or not os.path.isdir(where):
        return None
    for n in sorted(os.listdir(where)):
        keep = os.path.join(where, n, ORIGINALS)
        if os.path.isdir(keep) and fingerprint(DirectoryStorage(keep)) == mine:
            return os.path.join(where, n)
    return None


def free_name(where: str, name: str) -> str:
    """name, or "name 2", "name 3"... when that is taken in the library already."""
    name = name.strip() or "Diskette"
    n, out = 1, name
    while os.path.exists(os.path.join(where, out)):
        n += 1
        out = "%s %d" % (name, n)
    return out


def is_floppy(path: str) -> bool:
    """A folder (a mounted diskette or a copy of one) with KN6000/KN7000 sets in its root."""
    if not os.path.isdir(path) or os.path.isdir(os.path.join(path, "PRIVATE")):
        return False
    try:
        return bool(sets(DirectoryStorage(path)))
    except OSError:
        return False


def archive_floppy(path: str, library: str, name: str, replace: bool = False,
                   progress: Optional[Progress] = None, check: Optional[verify.CopyCheck] = None) -> str:
    """Copy a diskette into library/name as a card: every set a song in folder 01 (named after the
    diskette). Returns the library folder. The diskette is only read; every file is checked on the way
    (core/verify.py) and what was checked goes into check, for the app to say."""
    check = check if check is not None else verify.CopyCheck()
    from .cards import safe_name
    src = DirectoryStorage(path)
    found = sets(src)
    if not found:
        raise KN7Error(Text("no_sets", "{path} holds no KN6000/KN7000 sets", path=path))
    if len(found) > 20 * 99:
        raise KN7Error(Text("too_many_sets", "too many sets on {path}", path=path))
    folder = os.path.join(library, safe_name(name))
    if os.path.exists(folder) and not replace:
        raise KN7Error(Text("name_in_library", "there is already a card called {name} in the library", name=name))
    part = folder + ".part"
    if os.path.exists(part):
        shutil.rmtree(part)
    os.makedirs(part)
    # the diskette is slow: read every file (checked) into the originals folder, then build from there
    try:
        names = [n for s in found for n in s.files.values()]
        keep = os.path.join(part, ORIGINALS)
        os.makedirs(keep)
        originals = DirectoryStorage(keep)
        for i, n in enumerate(names):
            if progress:
                progress(i, len(names), n)
            verify.write_checked(originals, n, verify.read_checked(src, n, check), check)
        card = CardSession.create(DirectoryStorage(part))
        label = _plain(name) or "DISKETTE"
        for i, s in enumerate(found):
            f, so = divmod(i, 20)
            if so == 0:
                card.rename_folder(f + 1, label if f == 0 else _plain("%s %d" % (label[:13], f + 1)) or label)
            card.import_song(originals, dict(s.files), s.name, f + 1)
        card.save(backup=False)
    except BaseException:                               # a failed check: no half copy left behind
        shutil.rmtree(part, ignore_errors=True)
        raise
    if os.path.exists(folder):
        trash = folder + ".old"
        if os.path.exists(trash):
            shutil.rmtree(trash)
        os.replace(folder, trash)
        os.replace(part, folder)
        shutil.rmtree(trash)
    else:
        os.replace(part, folder)
    return folder
