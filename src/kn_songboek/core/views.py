"""Read-only data handed to front ends. Numbers are 1-based, as on the keyboard's screen."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class SongView:
    folder: int            # 1..99
    song: int              # 1..20
    name: str
    types: List[str]
    files: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class FolderView:
    folder: int
    name: str
    songs: List[SongView]

    @property
    def used(self) -> int:
        return len(self.songs)


@dataclass(frozen=True)
class Issue:
    severity: str          # 'error' | 'warning'
    message: str
    folder: Optional[int] = None
    song: Optional[int] = None

    def __str__(self) -> str:
        where = ""
        if self.folder is not None:
            where = "TFLD%03d" % self.folder + (" song %02d" % self.song if self.song else "") + ": "
        return "%s: %s%s" % (self.severity, where, self.message)
