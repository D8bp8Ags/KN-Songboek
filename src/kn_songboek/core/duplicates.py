"""Find songs that are stored more than once on a card.

Many owners organise by copying a song into several folders. Every copy is a separate set of
files: it costs space and one of the 20 slots, and an edit on the keyboard changes only that copy.
A favourite or a song list points at one song instead. This module finds the copies so a front end
can offer to keep one and point favourites and song lists at it (CardSession.merge_duplicates).

Two kinds of group:
  * identical: every file of the songs has the same bytes (and the same set of file types);
  * same_name: same name, but the files differ (probably edited later): shown only, never merged.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from ..formats import layout

Slot = Tuple[int, int]               # 1-based (folder, song)


@dataclass
class DuplicateGroup:
    kind: str                        # "identical" | "same_name"
    name: str
    slots: List[Slot] = field(default_factory=list)
    bytes_each: int = 0              # card space one copy takes (identical groups)

    @property
    def saving(self) -> int:
        """Bytes freed when all but one copy are removed."""
        return self.bytes_each * (len(self.slots) - 1) if self.kind == "identical" else 0


def _fingerprint(storage, paths: Dict[str, str]) -> Optional[Tuple[Tuple[str, str], ...]]:
    out = []
    for ext in sorted(paths):
        p = paths[ext]
        if not storage.exists(p):
            return None              # a missing file: let `check` / `repair` deal with it
        out.append((ext, hashlib.sha1(storage.read(p)).hexdigest()))
    return tuple(out)


def find_duplicates(session, progress: Callable[[int, int, str], None] = None) -> List[DuplicateGroup]:
    """Groups of songs that occur more than once, identical groups first, then by name.
    Reads every song file once, so it reflects the card as saved (save or undo changes first)."""
    db, st = session.db, session.storage
    songs = list(db.iter_songs())
    by_print: Dict[tuple, List[Tuple[Slot, str, int]]] = {}
    by_name: Dict[str, List[Tuple[Slot, tuple]]] = {}
    for i, (fi, si, s) in enumerate(songs):
        if progress:
            progress(i, len(songs), s.name)
        paths = layout.song_paths(fi, si, s)
        fp = _fingerprint(st, paths)
        slot = (fi + 1, si + 1)
        if fp is not None:
            size = sum(st.size(p) for p in paths.values())
            by_print.setdefault(fp, []).append((slot, s.name, size))
        if s.name.strip():
            by_name.setdefault(s.name.strip().upper(), []).append((slot, fp))
    groups = []
    for members in by_print.values():
        if len(members) > 1:
            groups.append(DuplicateGroup("identical", members[0][1], [m[0] for m in members], members[0][2]))
    for members in by_name.values():
        if len(members) > 1 and len({fp for _, fp in members}) > 1:     # same name, different content
            slots = [slot for slot, _ in members]
            groups.append(DuplicateGroup("same_name", db.song(slots[0][0] - 1, slots[0][1] - 1).name, slots))
    groups.sort(key=lambda g: (g.kind != "identical", g.name.upper(), g.slots))
    return groups
