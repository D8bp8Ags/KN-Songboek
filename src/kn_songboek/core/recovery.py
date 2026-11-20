"""Crash recovery: the changes that are not on the card yet, kept on the computer while they are made.

The app works on a draft: every change stays in memory until Op kaart zetten. If the app stops
unexpectedly (a crash, a power cut, the computer restarts), that draft would be lost. So while there
are unsaved changes, a copy of the draft is written to the app's own data folder after every change
(never to the card). When the changes are put on the card or thrown away, the copy is removed. A copy
that is still there when the app starts is a draft from a session that stopped unexpectedly, and the
app offers to bring it back.

One draft is one folder under drafts_dir() with:
  * draft.json: which card (or a new card), the steps (for undo) and the planned file operations;
  * blobs/: the card database after each step (zlib) and songs that only lived in memory (a song
    split from a set, a song from a back-up), named by their SHA-256.
Songs imported from a folder (the library, another card) are not copied: draft.json says where they are,
with their size and time, and bringing the draft back checks they are still the same.
A draft for an opened card remembers the card's database as it was; it is only brought back on that
same card, unchanged (otherwise the planned moves would be about other files).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import os
import shutil
import zlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from ..formats.inf import MusicDatabase
from ..formats.text import Text
from ..storage.directory import DirectoryStorage
from ..storage.memory import MemoryStorage
from .backup import default_backup_dir
from .errors import KN7Error
from .session import CardSession, FileOp

log = logging.getLogger("kn_songboek")

VERSION = 1
DRAFT_FILE = "draft.json"
ORGANIZE, COMPOSE = "organize", "compose"


def drafts_dir(backup_dir: Optional[str] = None) -> str:
    """$KN_SONGBOEK_DRAFT_DIR, else next to the back-ups in the per-user data folder: .../KN Songboek/concept."""
    env = os.environ.get("KN_SONGBOEK_DRAFT_DIR")
    if env and not backup_dir:
        return env
    base = os.path.dirname(os.path.normpath(backup_dir or default_backup_dir()))
    return os.path.join(base, "concept")


class RecoveryError(KN7Error):
    """The draft cannot be brought back (the card or the library changed since)."""


@dataclass
class DraftInfo:
    """What the start question tells about a draft that was left behind."""
    path: str                      # its folder
    kind: str                      # ORGANIZE or COMPOSE
    card_path: str                 # the opened card ("" for a new card)
    card_name: str                 # what the top bar called it
    compose_name: str
    saved: str                     # ISO time of the last change
    steps: int                     # changes that can be undone
    songs: int                     # songs on the card in the draft
    data: dict = field(repr=False, default_factory=dict)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _label_out(label) -> dict:
    if isinstance(label, Text):
        return {"key": label.key, "text": str(label), "values": label.values}
    return {"text": str(label)}


def _label_in(d: dict):
    if d.get("key"):
        t = str.__new__(Text, d.get("text", ""))      # the English as it was, with its key for translation
        t.key, t.values = d["key"], dict(d.get("values") or {})
        return t
    return d.get("text", "")


class DraftKeeper:
    """Writes the draft of one open session to its own folder; one per app window.

    save() is cheap enough to call after every change: blobs that are already there are not written
    again, and nothing is written when nothing changed."""

    def __init__(self, root: str):
        self.root = root
        self.folder = ""                       # this window's draft, "" while there is none
        self._last: Optional[Tuple] = None
        self._base: Optional[Tuple[CardSession, str, str]] = None   # (session, loaded_from, sha of it)
        self._refs: Dict[Tuple[int, str], dict] = {}                # import sources already looked at
        self._shas: Dict[int, Optional[Tuple[bytes, str]]] = {}

    # ------------------------------------------------------------------ writing
    def save(self, s: CardSession, kind: str, card_path: str = "", card_name: str = "",
             compose_name: str = "") -> bool:
        """Write the draft of s (only what changed). Returns True when something was written."""
        db = s.db.to_bytes()
        shas = {id(d): self._shas.get(id(d)) for d, _, _ in s._undo}     # the steps' snapshots never change
        for d, _, _ in s._undo:
            if shas[id(d)] is None or shas[id(d)][0] is not d:
                shas[id(d)] = (d, _sha(d))
        self._shas = shas
        undo = [(shas[id(d)][1], n, lab) for d, n, lab in s._undo]
        key = (id(s), kind, card_path, compose_name, _sha(db), tuple((h, n) for h, n, _ in undo), len(s.pending),
               tuple(id(op) for op in s.pending))
        if key == self._last and self.folder and os.path.isdir(self.folder):
            return False
        if not self.folder or not os.path.isdir(self.folder):
            stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            self.folder = _free(os.path.join(self.root, "%s-%d" % (stamp, os.getpid())))
            os.makedirs(os.path.join(self.folder, "blobs"))
        blobs = os.path.join(self.folder, "blobs")
        used = set()

        def blob(data: bytes, packed: bool = False) -> str:
            h = _sha(data)
            used.add(h)
            p = os.path.join(blobs, h)
            if not os.path.exists(p):
                _write(p, zlib.compress(data, 6) if packed else data)
            return h

        doc = {"version": VERSION, "kind": kind, "card_path": card_path, "card_name": card_name,
               "compose_name": compose_name, "saved": _dt.datetime.now().isoformat(timespec="seconds"),
               "songs": sum(1 for _ in s.db.iter_songs())}
        if kind == ORGANIZE:
            if self._base is None or self._base[0] is not s:
                raw = s.storage.read(s.loaded_from)          # only read: the card itself is never written here
                self._base = (s, s.loaded_from, _sha(raw))
            doc["loaded_from"], doc["base"] = self._base[1], self._base[2]
        doc["db"] = blob(db, True)
        doc["undo"] = []
        for (d, n, lab), (h, _, _) in zip(s._undo, undo):
            blob(d, True)
            doc["undo"].append({"db": h, "ops": n, "label": _label_out(lab)})
        doc["ops"] = [self._op(op, blob) for op in s.pending]
        _write(os.path.join(self.folder, DRAFT_FILE), json.dumps(doc, indent=1, default=str).encode("utf-8"))
        for name in os.listdir(blobs):                       # blobs no step needs any more
            if name not in used:
                try:
                    os.remove(os.path.join(blobs, name))
                except OSError:
                    pass
        self._last = key
        return True

    def _op(self, op: FileOp, blob) -> dict:
        d = {"kind": op.kind, "src": op.src, "dst": op.dst}
        if op.kind != "import":
            return d
        if op.name:
            d["name"] = op.name
        st = op.src_storage
        k = (id(st), op.src.upper())
        ref = self._refs.get(k)
        if ref is None:
            if isinstance(st, DirectoryStorage):
                real = st._real(op.src)
                info = os.stat(real)
                ref = {"dir": st.root, "size": info.st_size, "mtime": info.st_mtime_ns}
            else:                                            # only in memory: keep the song itself
                ref = {"blob": blob(st.read(op.src))}
            self._refs[k] = ref
        elif "blob" in ref:
            blob(st.read(op.src))                        # mark it as still used (already on disk)
        d["from"] = ref
        return d

    def clear(self) -> None:
        """The changes are on the card, or thrown away: no draft any more."""
        if self.folder:
            shutil.rmtree(self.folder, ignore_errors=True)
        self.folder, self._last, self._base = "", None, None
        self._refs.clear()


# ---------------------------------------------------------------------- finding and bringing back
def left_behind(root: str, mine: str = "") -> List[DraftInfo]:
    """Drafts from sessions that stopped unexpectedly, newest first (not this window's own)."""
    out = []
    try:
        names = sorted(os.listdir(root), reverse=True)
    except OSError:
        return []
    for name in names:
        path = os.path.join(root, name)
        if os.path.normpath(path) == os.path.normpath(mine or "-"):
            continue
        try:
            with open(os.path.join(path, DRAFT_FILE), "rb") as fh:
                d = json.loads(fh.read().decode("utf-8"))
        except (OSError, ValueError):
            continue                     # half written (it stopped while writing the first one): skip
        if d.get("version") != VERSION:
            continue
        out.append(DraftInfo(path, d.get("kind", ""), d.get("card_path", ""), d.get("card_name", ""),
                             d.get("compose_name", ""), d.get("saved", ""), len(d.get("undo", [])),
                             int(d.get("songs", 0)), d))
    return out


def discard(info: DraftInfo) -> None:
    shutil.rmtree(info.path, ignore_errors=True)


def _read_blob(info: DraftInfo, h: str, packed: bool = False) -> bytes:
    with open(os.path.join(info.path, "blobs", h), "rb") as fh:
        data = fh.read()
    return zlib.decompress(data) if packed else data


def same_card(info: DraftInfo, s: CardSession) -> bool:
    """Is s the card the draft was made on, unchanged since?"""
    d = info.data
    try:
        return s.loaded_from == d.get("loaded_from") and _sha(s.storage.read(s.loaded_from)) == d.get("base")
    except (OSError, KeyError):
        return False


def apply(info: DraftInfo, s: CardSession) -> None:
    """Put the draft into a freshly opened session s (the same card, or a new empty card)."""
    d = info.data
    if d.get("kind") == ORGANIZE and not same_card(info, s):
        raise RecoveryError(Text("draft_card_changed", "the card was changed since; the draft no longer fits it"))
    sources: Dict[str, DirectoryStorage] = {}
    memory = MemoryStorage()
    ops, missing = [], []
    try:
        for o in d.get("ops", []):
            src_storage = None
            ref = o.get("from")
            if o["kind"] == "import":
                if ref is None:
                    raise KeyError(o["src"])          # caught below: the draft is damaged
                if "blob" in ref:
                    memory.write(o["src"], _read_blob(info, ref["blob"]))
                    src_storage = memory
                else:
                    st = sources.setdefault(ref["dir"], DirectoryStorage(ref["dir"]))
                    try:
                        real = st._real(o["src"])
                        stat = os.stat(real)
                        same = stat.st_size == ref["size"] and stat.st_mtime_ns == ref["mtime"]
                    except OSError:
                        same = False
                    if not same:
                        missing.append(os.path.join(ref["dir"], o["src"]))
                    src_storage = st
            ops.append(FileOp(o["kind"], o["src"], o.get("dst", ""), src_storage, o.get("name", "")))
        db = MusicDatabase.from_bytes(_read_blob(info, d["db"], True))
        undo = [(_read_blob(info, u["db"], True), int(u["ops"]), _label_in(u["label"])) for u in d.get("undo", [])]
    except (OSError, KeyError, ValueError, zlib.error) as e:
        raise RecoveryError(Text("draft_damaged", "the draft could not be read ({detail})", detail=str(e))) from e
    if missing:
        raise RecoveryError(Text("draft_library_changed",
                                 "{n} song file(s) the draft needs were changed or removed since, e.g. {first}",
                                 n=len(missing), first=missing[0]))
    s.db = db
    s.pending = ops
    s._undo = undo
    s._redo = []
    s._changed("all")


def _write(path: str, data: bytes) -> None:
    tmp = path + ".tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _free(path: str) -> str:
    n, p = 1, path
    while os.path.exists(p):
        n += 1
        p = "%s-%d" % (path, n)
    return p
