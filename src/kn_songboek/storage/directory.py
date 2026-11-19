"""A card that is a folder on the computer: the mounted SD card itself, or a copy of it."""
from __future__ import annotations

import os
import shutil
import sys
from typing import Dict, List, Optional


def _fsync(path: str) -> None:
    """Make sure what is written to path is on the card itself, not only in the computer's memory.
    A folder is synced too (that is where a new name or a removed file is kept); a system that cannot
    sync a folder (Windows) simply skips it."""
    try:
        # Windows can only flush a file opened for writing (and cannot open a folder at all)
        fd = os.open(path, os.O_RDWR if sys.platform.startswith("win") and os.path.isfile(path) else os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


class DirectoryStorage:
    def __init__(self, root: str):
        self.root = os.path.abspath(root)
        self._names: Dict[str, Dict[str, str]] = {}     # folder -> {UPPER: real name}

    # FAT is case-insensitive; macOS/Linux mounts or copies may not be. Folder listings are cached
    # (listing a folder per path component was most of the time of opening a library) and the
    # cache is dropped on every change this object makes.
    def _listing(self, folder: str) -> Dict[str, str]:
        names = self._names.get(folder)
        if names is None:
            try:
                names = {e.upper(): e for e in os.listdir(folder)}
            except OSError:
                names = {}
            self._names[folder] = names
        return names

    def _changed(self) -> None:
        self._names.clear()

    def _real(self, path: str) -> str:
        p = self.root
        for part in [x for x in path.split("/") if x]:
            p = os.path.join(p, self._listing(p).get(part.upper(), part))
        return p

    def read(self, path: str) -> bytes:
        with open(self._real(path), "rb") as fh:
            return fh.read()

    def read_from_card(self, path: str) -> bytes:
        """Read past the computer's memory, from the card itself where the system allows it (macOS:
        F_NOCACHE; Linux: drop the cached pages first). Used to check a save; elsewhere a plain read."""
        with open(self._real(path), "rb") as fh:
            fd = fh.fileno()
            try:
                if sys.platform == "darwin":
                    import fcntl
                    fcntl.fcntl(fd, getattr(fcntl, "F_NOCACHE", 48), 1)
                elif hasattr(os, "posix_fadvise"):
                    os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
            except OSError:
                pass
            return fh.read()

    def write(self, path: str, data: bytes) -> None:
        self._changed()
        real = self._real(path)
        os.makedirs(os.path.dirname(real), exist_ok=True)
        tmp = real + ".tmp"
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, real)
        _fsync(os.path.dirname(real))
        self._changed()

    def exists(self, path: str) -> bool:
        return os.path.exists(self._real(path))

    def listdir(self, path: str) -> List[str]:
        real = self._real(path)
        return sorted(os.listdir(real)) if os.path.isdir(real) else []

    def move(self, src: str, dst: str) -> None:
        self._changed()
        d = self._real(dst)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        s = self._real(src)
        shutil.move(s, d)
        _fsync(d)
        _fsync(os.path.dirname(d))
        _fsync(os.path.dirname(s))
        self._changed()

    def copy(self, src: str, dst: str) -> None:
        self._changed()
        d = self._real(dst)
        os.makedirs(os.path.dirname(d), exist_ok=True)
        shutil.copyfile(self._real(src), d)
        _fsync(d)
        _fsync(os.path.dirname(d))
        self._changed()

    def remove(self, path: str) -> None:
        self._changed()
        real = self._real(path)
        os.remove(real)
        _fsync(os.path.dirname(real))
        self._changed()

    def describe(self) -> str:
        return self.root

    def isdir(self, path: str) -> bool:
        return os.path.isdir(self._real(path))

    def size(self, path: str) -> int:
        return os.path.getsize(self._real(path))

    def _usage(self):
        p = self.root
        while not os.path.exists(p) and os.path.dirname(p) != p:
            p = os.path.dirname(p)
        try:
            return shutil.disk_usage(p)
        except OSError:
            return None

    def free_bytes(self) -> Optional[int]:
        u = self._usage()
        return u.free if u else None

    def total_bytes(self) -> Optional[int]:
        u = self._usage()
        return u.total if u else None

    def writable(self) -> bool:
        # A locked SD card mounts read-only, which os.access reports.
        p = self.root
        while not os.path.exists(p) and os.path.dirname(p) != p:
            p = os.path.dirname(p)          # a card folder that is about to be created
        return os.access(p, os.W_OK)
