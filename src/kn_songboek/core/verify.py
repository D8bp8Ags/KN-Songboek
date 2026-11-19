"""Careful copying into the library: every file is checked, and the result is said, not kept quiet.

Used when a card or a diskette is kept in the library (cards.archive_card, floppy.archive_floppy). Three
checks per file, each counted so the app can say what it did:

  1. read twice   the second read goes past the computer's memory (read_from_card), so a weak spot on an
                  old diskette or card that gives other bytes each time is noticed
  2. unpacked     song files are unpacked; KN6000 files carry a checksum (adler32) that must match,
                  KN7000 files have none, so for them this only says they can be read to the end
  3. read back    what was written in the library is read back and compared byte for byte

A file whose three reads all differ stops the copy (the library keeps what it had); one that read
differently once, with two of three reads the same, is copied and said in orange. A song file that
does not unpack is copied as it is and said in orange: it may have been like that on the card already.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from ..formats import container
from ..formats.inf import FILE_TYPES
from .errors import KN7Error, Text


@dataclass
class CopyCheck:
    files: int = 0                       # files copied
    read_twice: int = 0                  # check 1: the same both times
    unpacked: int = 0                    # check 2: song files that unpacked (with checksum or to the end)
    checksum: int = 0                    #   of which with a checksum that matched (KN6000)
    song_files: int = 0                  #   song files seen
    read_back: int = 0                   # check 3: identical in the library
    not_unpacked: List[str] = field(default_factory=list)   # copied as they are; said in orange
    unstable: List[str] = field(default_factory=list)       # read differently once; 2 of 3 reads agreed

    @property
    def ok(self) -> bool:
        return not self.not_unpacked and not self.unstable


def _read_past_cache(storage, path: str) -> bytes:
    return getattr(storage, "read_from_card", storage.read)(path)


def read_checked(storage, path: str, check: CopyCheck) -> bytes:
    """Read a file twice and make sure both reads agree. When they do not, one more read decides; a
    file that keeps changing stops the copy."""
    first = storage.read(path)
    second = _read_past_cache(storage, path)
    if first != second:                                 # one more read decides; said in orange
        third = _read_past_cache(storage, path)
        if third != first and third != second:
            raise KN7Error(Text("read_unstable", "{path} reads differently every time; the card or "
                                "diskette may be damaged. Nothing was changed in the library.", path=path))
        check.unstable.append(path)
        first = third
    else:
        check.read_twice += 1
    _unpack(path, first, check)
    return first


def _unpack(path: str, data: bytes, check: CopyCheck) -> None:
    ext = os.path.splitext(path)[1].upper().strip(".")
    if ext not in FILE_TYPES:
        return
    check.song_files += 1
    try:
        got = container.parse(data, ext)
    except Exception:                                   # unreadable or another model: copied as it is
        check.not_unpacked.append(path)
        return
    check.unpacked += 1
    if got.kind in ("ID", "K1"):                        # deflate with adler32: checked in inflate_part
        check.checksum += 1


def write_checked(target, path: str, data: bytes, check: CopyCheck) -> None:
    """Write into the library and read it back, past the computer's memory."""
    target.write(path, data)
    if _read_past_cache(target, path) != data:
        raise KN7Error(Text("library_read_back", "{path} did not read back correctly in the library. "
                            "Nothing was changed in the library.", path=path))
    check.read_back += 1
    check.files += 1
