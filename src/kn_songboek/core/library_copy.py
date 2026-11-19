"""A copy of the whole library on a USB stick or an external disk, so the kept cards and diskettes are
not only on one computer.

copy_library(library, target) makes (or brings up to date) target/<library's folder name>:
  - a file that is not there yet, or differs in size or date, is copied and read back byte for byte
    (past the computer's memory, as in core/verify.py);
  - a file that is already there with the same size and date is left as it is, and counted;
  - a file in the copy that is no longer in the library is never removed (nothing is cleaned up by
    itself); it is counted, so the app can say so.
Nothing is kept about earlier copies: every run looks at the files themselves.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .errors import KN7Error, Text

Progress = Callable[[int, int, str], None]
SAME_TIME = 2.0                  # FAT/exFAT sticks keep times to 2 seconds


@dataclass
class LibraryCopy:
    folder: str = ""                                   # the copy: target/<library name>
    copied: int = 0                                    # new or changed, read back and the same
    same: int = 0                                      # already there with the same size and date
    extra: List[str] = field(default_factory=list)     # in the copy only (no longer in the library)
    size: int = 0                                      # bytes copied


def _files(root: str) -> List[str]:
    out = []
    for d, dirs, names in os.walk(root):
        dirs[:] = sorted(x for x in dirs if not x.startswith("."))
        for n in sorted(names):
            if not n.startswith("."):
                out.append(os.path.relpath(os.path.join(d, n), root))
    return out


def _same(a: str, b: str) -> bool:
    try:
        sa, sb = os.stat(a), os.stat(b)
    except OSError:
        return False
    return sa.st_size == sb.st_size and abs(sa.st_mtime - sb.st_mtime) <= SAME_TIME


def _read_past_cache(path: str) -> bytes:
    from ..storage import DirectoryStorage
    d, n = os.path.split(path)
    return DirectoryStorage(d).read_from_card(n)


def copy_library(library: str, target: str, progress: Optional[Progress] = None) -> LibraryCopy:
    library, target = os.path.abspath(library), os.path.abspath(target)
    if os.path.normcase(target + os.sep).startswith(os.path.normcase(library + os.sep)):
        raise KN7Error(Text("copy_inside_library", "the copy cannot go inside the library itself ({path})",
                            path=target))
    rep = LibraryCopy(folder=os.path.join(target, os.path.basename(library.rstrip(os.sep)) or "Bibliotheek"))
    files = _files(library)
    todo = [f for f in files if not _same(os.path.join(library, f), os.path.join(rep.folder, f))]
    rep.same = len(files) - len(todo)
    need = sum(os.path.getsize(os.path.join(library, f)) for f in todo)
    try:
        free = shutil.disk_usage(target).free
    except OSError:
        free = None
    if free is not None and need > free:
        raise KN7Error(Text("copy_no_space", "not enough room on {path}: {need} MB needed, {free} MB free",
                            path=target, need=need // 2**20 + 1, free=free // 2**20))
    for i, f in enumerate(todo):
        if progress:
            progress(i, len(todo), f)
        src, dst = os.path.join(library, f), os.path.join(rep.folder, f)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(src, "rb") as fh:
            data = fh.read()
        part = dst + ".part"
        with open(part, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        if _read_past_cache(part) != data:
            os.remove(part)
            raise KN7Error(Text("copy_read_back", "{path} did not read back correctly on the copy", path=dst))
        os.replace(part, dst)
        try:
            shutil.copystat(src, dst)                  # same date: the next copy can see it is the same
        except OSError:                                # some sticks keep no rights: then only the date
            os.utime(dst, (os.path.getatime(src), os.path.getmtime(src)))
        rep.copied += 1
        rep.size += len(data)
    if progress:
        progress(len(todo), len(todo), "")
    known = {os.path.normcase(f) for f in files}
    rep.extra = [f for f in _files(rep.folder) if os.path.normcase(f) not in known] if os.path.isdir(rep.folder) else []
    return rep
