"""CardSession: open a card, edit the database in memory, then apply everything in one go.

Design (docs/nl/explanation/architectuur.md):
  * every edit is a small command that changes an in-memory copy of the database and appends the
    file operations it needs to a pending plan; nothing on the card changes until save();
  * undo() restores the database snapshot taken before the last command and drops its file ops;
  * save() runs the plan in order, then writes the database the way the instrument does
    (old INF kept as BAK while writing, new INF read back, then BAK = second copy);
  * front ends subscribe to change notifications (on_change) instead of polling.
Numbers in the public API are 1-based (folder 1..99, song 1..20), as on the keyboard.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from ..formats import layout
from ..formats.inf import (FILE_TYPES, INFError, MusicDatabase, N_FOLDERS, N_PLAYLISTS, N_SONGS,
                           PLAYLIST_LEN, FavoriteBank, Song)
from ..storage.base import Storage
from .errors import InvalidName, KN7Error, NoDatabase, NothingToUndo, SlotError, Text
from .views import FolderView, Issue, SongView

log = logging.getLogger("kn_songboek")


@dataclass(frozen=True)
class FileOp:
    kind: str                         # 'move' | 'copy' | 'delete' | 'import'
    src: str
    dst: str = ""
    src_storage: Optional[Storage] = None   # for 'import': another card or a folder
    name: str = ""                    # for 'import': the song's name when it came in (to see a rename)

    def __str__(self) -> str:
        return "%s %s%s" % (self.kind, self.src, " -> " + self.dst if self.dst else "")


def check_name(name: str) -> None:
    """Names are at most 16 characters. Only plain ASCII is allowed for now: that is all a real card
    showed (2026-11-15) and which other characters the keyboard can show is not yet known."""
    if len(name) > 16:
        raise InvalidName("'%s' is %d characters; the keyboard allows 16" % (name, len(name)), name)
    bad = sorted({c for c in name if not " " <= c <= "~"})
    if bad:
        raise InvalidName("'%s' contains %s; only plain letters, digits and punctuation are allowed"
                          % (name, " ".join(repr(c) for c in bad)), name, "".join(bad))


class PlannedStorage:
    """Read-only look at a card with the pending file operations applied: a song that is imported or
    moved but not saved yet is read from where it is now. Everything else goes to the card itself."""

    def __init__(self, base: Storage, pending: List["FileOp"]):
        self.base = base
        self.map: Dict[str, Optional[Tuple[Storage, str]]] = {}
        for op in pending:
            self.add(op)

    def add(self, op: "FileOp") -> None:
        """One more step of the plan."""
        if op.kind == "import":
            self.map[op.dst.upper()] = (op.src_storage, op.src)
        elif op.kind in ("move", "copy"):
            self.map[op.dst.upper()] = self._where(op.src)
            if op.kind == "move":
                self.map[op.src.upper()] = None
        elif op.kind == "delete":
            self.map[op.src.upper()] = None

    def _where(self, path: str) -> Optional[Tuple[Storage, str]]:
        return self.map.get(path.upper(), (self.base, path)) if path.upper() in self.map else (self.base, path)

    def exists(self, path: str) -> bool:
        w = self._where(path)
        return w is not None and w[0].exists(w[1])

    def size(self, path: str) -> int:
        w = self._where(path)
        if w is None:
            raise KeyError(path)
        return w[0].size(w[1])

    def read(self, path: str) -> bytes:
        w = self._where(path)
        if w is None:
            raise KeyError(path)
        return w[0].read(w[1])

    def __getattr__(self, name):
        return getattr(self.base, name)


_NO_FAVS: Dict[str, object] = {"carried": 0, "banks": [], "left": 0}


def _idx(folder: int, song: Optional[int] = None) -> Tuple[int, Optional[int]]:
    if not 1 <= folder <= N_FOLDERS:
        raise SlotError(Text("folder_range", "folder {n} is out of range 1..{max}", n=folder, max=N_FOLDERS))
    if song is not None and not 1 <= song <= N_SONGS:
        raise SlotError(Text("song_range", "song {n} is out of range 1..{max}", n=song, max=N_SONGS))
    return folder - 1, (song - 1 if song is not None else None)


class CardSession:
    def __init__(self, storage: Storage, db: MusicDatabase, loaded_from: str):
        self.storage = storage
        self.db = db
        self.loaded_from = loaded_from
        self.pending: List[FileOp] = []
        self.checked_songs = 0            # songs found complete on the card after the last save
        self.missing_after: List[str] = []    # song files the database names but the card lacks, after it
        self.verified = 0                 # files read back and found right after the last save
        self._undo: List[Tuple[bytes, int, str]] = []
        self._redo: List[Tuple[bytes, List[FileOp], str]] = []
        self._listeners: List[Callable[[str], None]] = []

    # ------------------------------------------------------------------ open / create
    @classmethod
    def open(cls, storage: Storage) -> "CardSession":
        errors, missing = [], 0
        for path in (layout.INF_PATH, layout.BAK_PATH):
            try:
                return cls(storage, MusicDatabase.from_bytes(storage.read(path)), path)
            except (OSError, KeyError, INFError) as e:
                errors.append("%s: %s" % (path, e))
                missing += isinstance(e, (KeyError, FileNotFoundError))
        if missing == 2:                 # not a card at all (another folder): said differently from a damaged one
            raise NoDatabase(Text("no_card_here", "{card} holds no KN7000 card", card=storage.describe()))
        raise NoDatabase(Text("no_database", "no usable music database on {card} ({detail})", card=storage.describe(), detail="; ".join(errors)))

    @classmethod
    def create(cls, storage: Storage) -> "CardSession":
        s = cls(storage, MusicDatabase.new(), layout.INF_PATH)
        s.save(backup=False)
        return s

    # ------------------------------------------------------------------ notifications
    def on_change(self, callback: Callable[[str], None]) -> None:
        self._listeners.append(callback)

    def _changed(self, what: str) -> None:
        for cb in self._listeners:
            cb(what)

    @property
    def dirty(self) -> bool:
        return bool(self._undo)

    # ------------------------------------------------------------------ queries
    def _song_view(self, fi: int, si: int, s: Song) -> SongView:
        return SongView(fi + 1, si + 1, s.name, s.extensions, sorted(layout.song_paths(fi, si, s).values()))

    def folders(self, include_empty: bool = False) -> List[FolderView]:
        out = []
        for fi, f in enumerate(self.db.folders):
            songs = [self._song_view(fi, si, s) for si, s in enumerate(f.songs) if s.used]
            if songs or f.name or include_empty:
                out.append(FolderView(fi + 1, f.name, songs))
        return out

    def renamed_songs(self) -> Dict[Tuple[int, int], str]:
        """(folder, song) -> the name the song had before, for every song whose name was changed since the
        card was opened or last saved. The song is followed through the pending file operations, so a
        song that was renamed and then moved still says what it was called. A song brought in from
        elsewhere compares with the name it came in with; a song changed back is not listed."""
        base = MusicDatabase.from_bytes(self._undo[0][0]) if self._undo else self.db
        was = {}                                         # card path at the last save -> name then
        for fi, si, x in base.iter_songs():
            for p in layout.song_paths(fi, si, x).values():
                was[p.upper()] = x.name
        origin: Dict[str, Optional[str]] = {}            # path now -> the name it started with
        for op in self.pending:
            src = op.src.upper()
            if op.kind == "import":
                origin[op.dst.upper()] = op.name or None
            elif op.kind in ("move", "copy"):
                origin[op.dst.upper()] = origin[src] if src in origin else was.get(src)
                if op.kind == "move":
                    origin[src] = None
            elif op.kind == "delete":
                origin[src] = None
        out = {}
        for fi, si, x in self.db.iter_songs():
            paths = list(layout.song_paths(fi, si, x).values())
            if not paths:
                continue
            p = paths[0].upper()
            old = origin[p] if p in origin else was.get(p)
            if old is not None and old != x.name:
                out[(fi + 1, si + 1)] = old
        return out

    def song(self, folder: int, song: int) -> SongView:
        fi, si = _idx(folder, song)
        return self._song_view(fi, si, self.db.song(fi, si))

    def search(self, text: str) -> List[SongView]:
        t = text.upper()
        return [self._song_view(fi, si, s) for fi, si, s in self.db.iter_songs() if t in s.name.upper()]

    def favorites(self) -> List[Tuple[str, List[Optional[Tuple[str, int, int]]]]]:
        return [(b.name, [FavoriteBank.decode_item(v) for v in b.items]) for b in self.db.favorites]

    def playlists(self) -> List[List[Tuple[int, int]]]:
        return [[(f + 1, s + 1) for f, s in self.db.playlist(n)] for n in range(3)]

    # ------------------------------------------------------------------ favourites and song lists
    def rename_favorite_bank(self, bank: int, name: str) -> None:
        b = self._bank(bank)
        check_name(name)
        self._begin(Text("rename_fav_bank", "rename favourite bank {bank}", bank=bank))
        b.name = name
        self._changed("favorites")

    def set_favorite(self, bank: int, pos: int, slot: Optional[Tuple[int, int]]) -> None:
        """Put a song (1-based folder, song) on favourite button pos (1..9) of a bank, or clear it."""
        b = self._bank(bank)
        if not 1 <= pos <= len(b.items):
            raise SlotError(Text("fav_range", "favourite position {n} is out of range 1..{max}", n=pos, max=len(b.items)))
        value = 0
        if slot is not None:
            fi, si = _idx(*slot)
            if not self.db.song(fi, si).used:
                raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=slot[0], song=slot[1]))
            value = FavoriteBank.encode_song(fi, si)
        self._begin(Text("favourite", "favourite {bank}.{pos}", bank=bank, pos=pos) if slot
                    else Text("clear_favourite", "clear favourite {bank}.{pos}", bank=bank, pos=pos))
        b.items[pos - 1] = value
        self._changed("favorites")

    def set_song_list(self, n: int, slots: List[Tuple[int, int]]) -> None:
        """Replace song list n (1..3) with up to 20 songs (1-based folder, song)."""
        if not 1 <= n <= N_PLAYLISTS:
            raise SlotError(Text("list_range", "song list {n} is out of range 1..{max}", n=n, max=N_PLAYLISTS))
        if len(slots) > PLAYLIST_LEN:
            raise SlotError(Text("list_long", "a song list holds at most {max} songs", max=PLAYLIST_LEN))
        items = []
        for slot in slots:
            fi, si = _idx(*slot)
            if not self.db.song(fi, si).used:
                raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=slot[0], song=slot[1]))
            items.append((fi, si))
        self._begin(Text("song_list", "song list {n}", n=n))
        self.db.set_playlist(n - 1, items)
        self._changed("lists")

    def _bank(self, bank: int) -> FavoriteBank:
        if not 1 <= bank <= len(self.db.favorites):
            raise SlotError(Text("fav_bank_range", "favourite bank {n} is out of range 1..{max}", n=bank, max=len(self.db.favorites)))
        return self.db.favorites[bank - 1]

    def import_from(self, other: "CardSession", folder: int, song: int, to_folder: int,
                    to_song: Optional[int] = None) -> int:
        """Copy one song from another card (or a copy of one) into this card."""
        fi, si = _idx(folder, song)
        src = other.db.song(fi, si)
        if not src.used:
            raise SlotError(Text("song_empty_on", "folder {folder} song {song} is empty on {card}", folder=folder, song=song, card=other.storage.describe()))
        return self.import_song(other.storage, layout.song_paths(fi, si, src), src.name, to_folder, to_song)

    def song_details(self, folder: int, song: int) -> Dict[str, object]:
        """Files with their sizes and, if there is an SQT, the sequencer songs in it."""
        from ..formats import container, sqt
        from ..formats.rhythm import song_rhythm
        fi, si = _idx(folder, song)
        s = self.db.song(fi, si)
        if not s.used:
            raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=folder, song=song))
        st = self.planned()                 # songs moved or imported but not saved yet are read where they are
        files = {}
        for ext, p in layout.song_paths(fi, si, s).items():
            files[ext] = {"path": p, "bytes": st.size(p) if st.exists(p) else None}
        out: Dict[str, object] = {"folder": folder, "song": song, "name": s.name, "files": files, "sequencer": []}
        if "SQT" in files and files["SQT"]["bytes"]:
            try:
                parts = container.parse(st.read(files["SQT"]["path"]), "SQT").parts
                cmp = files.get("CMP", {}).get("path") if files.get("CMP", {}).get("bytes") else None
                for q in sqt.read_songs(parts[0], parts[1] if len(parts) > 1 else b""):
                    r = song_rhythm(q.rhythm_id, st, cmp)
                    out["sequencer"].append({
                        "index": q.index, "name": q.name, "model": q.model, "tempo": q.tempo,
                        "rhythm": r.label if r else None, "meter": r.meter if r else None,
                        "beats": q.beats, "notes": q.notes,
                        "tracks": [{"track": t.number, "events": t.events, "notes": t.notes,
                                    "complete": t.complete} for t in q.tracks if t.events]})
            except Exception as e:          # report, never fail a listing on one odd file
                out["sequencer_error"] = str(e)
        out.update(self._song_contents(files, st))
        return out

    def set_titles(self, folder: int, song: int) -> List[str]:
        """The songs a diskette's full set holds panel memories for ("Annie's Song", ...); empty for an
        ordinary song or when the PMT cannot be read."""
        from ..formats import songdata
        raw = self._pmt_file(folder, song)
        try:
            return songdata.pmt_set_titles(raw) if raw else []
        except Exception:                   # an odd file never stops the info
            return []

    def chord_mode(self, folder: int, song: int) -> Optional[int]:
        """The chord mode most of the song's panel memories use (songdata.CHORD_MODES), or None."""
        from ..formats import songdata
        return songdata.chord_mode(self.panel_banks(folder, song))

    def panel_banks(self, folder: int, song: int) -> list:
        """The song's panel memory banks (songdata.PanelBank: A, B, C and, when saved with ALL, 1-10);
        empty when there is no PMT or it cannot be read."""
        from ..formats import container, songdata
        raw = self._pmt_file(folder, song)
        try:
            return songdata.read_pmt(container.parse(raw, "PMT").parts[0]) if raw else []
        except Exception:                   # an odd file never stops the info
            return []

    def _pmt_file(self, folder: int, song: int) -> Optional[bytes]:
        fi, si = _idx(folder, song)
        s = self.db.song(fi, si)
        p = layout.song_paths(fi, si, s).get("PMT") if s.used else None
        st = self.planned()
        return st.read(p) if p is not None and st.exists(p) else None

    def _song_contents(self, files: Dict[str, dict], st: "Storage") -> Dict[str, object]:
        """Panel memories, composer styles, pads, sounds and home page picture, as far as readable.
        A part that cannot be read is left out and its error put under "errors"."""
        from dataclasses import asdict
        from ..formats import container, songdata
        out: Dict[str, object] = {}
        errors: Dict[str, str] = {}
        readers = {"PMT": ("panel_memories", lambda d: [asdict(b) for b in songdata.read_pmt(d)]),
                   "CMP": ("styles", lambda d: [asdict(x) for x in songdata.read_cmp(d)]),
                   "MSP": ("pads", lambda d: asdict(songdata.read_msp(d))),
                   "TM": ("sounds", lambda d: asdict(songdata.read_tm(d)))}
        for ext, (key, read) in readers.items():
            f = files.get(ext)
            if not f or not f["bytes"]:
                continue
            try:
                out[key] = read(container.parse(st.read(f["path"]), ext).parts[0])
            except Exception as e:          # an odd file never stops the details
                errors[ext] = e.args[0] if e.args and hasattr(e.args[0], "key") else str(e)   # keep a Text
        f = files.get("HMP")
        if f and f["bytes"]:
            try:
                h = songdata.read_hmp(st.read(f["path"]))
                out["home_page"] = {"width": h.width, "height": h.height, "bmp_bytes": len(h.bmp)}
            except Exception as e:
                errors["HMP"] = str(e)
        if errors:
            out["errors"] = errors
        return out

    def home_page_bmp(self, folder: int, song: int) -> Optional[bytes]:
        """The home page picture of a song as a .bmp file, or None if it has none."""
        from ..formats import songdata
        fi, si = _idx(folder, song)
        p = layout.song_paths(fi, si, self.db.song(fi, si)).get("HMP")
        st = self.planned()
        if p is None or not st.exists(p):
            return None
        return songdata.read_hmp(st.read(p)).bmp

    def planned(self) -> "PlannedStorage":
        """The card as it will be after saving, for reading songs before they are saved."""
        return PlannedStorage(self.storage, self.pending)

    def sd_sound(self) -> Dict[str, object]:
        """The SD_SOUND folder: the names in SD_SOUND.TKM, the order in SD_SOUND.PLM, MIDI files."""
        from ..formats import sdsound
        s = sdsound.read(self.storage)
        return {"names": s.names, "order": s.order, "midi": sdsound.midi_files(self.storage)}

    def validate(self) -> List[Issue]:
        """Database against the files on the card (pending operations not yet applied)."""
        issues: List[Issue] = []
        claimed = set()
        for fi, si, s in self.db.iter_songs():
            for p in layout.song_paths(fi, si, s).values():
                claimed.add(p.upper())
                if not self.storage.exists(p):
                    issues.append(Issue("error", Text("missing_file", "missing file {name}", name=p.rsplit("/", 1)[1]), fi + 1, si + 1))
        for fi in range(N_FOLDERS):
            d = layout.folder_dir(fi)
            for name in self.storage.listdir(d):
                if (d + "/" + name).upper() not in claimed:
                    issues.append(Issue("warning", Text("stray_file", "file {name} is not in the database", name=name), fi + 1))
        for b, (_name, items) in enumerate(self.favorites()):
            for it in items:
                if it and it[0] == "song" and not self.db.song(it[1], it[2]).used:
                    issues.append(Issue("warning", Text("fav_empty", "favourite bank {bank} points to an empty slot", bank=b + 1),
                                        it[1] + 1, it[2] + 1))
        return issues

    def stray_files(self) -> List[str]:
        """Files in the song folders that no song in the database uses (left behind by another program,
        or by a copy that went wrong). They do no harm, but a song moved onto that slot later would find
        a stray file in its way. Pending operations are taken into account."""
        claimed = {p.upper() for fi, si, s in self.db.iter_songs() for p in layout.song_paths(fi, si, s).values()}
        gone = {op.src.upper() for op in self.pending if op.kind in ("move", "delete")}
        made = {op.dst.upper() for op in self.pending if op.kind in ("move", "copy", "import")}
        found = []
        for fi in range(N_FOLDERS):
            d = layout.folder_dir(fi)
            for name in self.storage.listdir(d):
                path = d + "/" + name
                if path.upper() not in claimed and path.upper() not in gone and path.upper() not in made:
                    found.append(path)
        return found

    def remove_stray_files(self, paths: List[str]) -> None:
        """Plan the removal of stray files (one step, undoable; done on save, after the backup)."""
        if not paths:
            return
        self._begin(Text("remove_stray", "remove {n} stray file(s)", n=len(paths)))
        for p in paths:
            self.pending.append(FileOp("delete", p))
        self._changed("stray")

    # ------------------------------------------------------------------ command plumbing
    def _begin(self, label: str) -> None:
        self._undo.append((self.db.to_bytes(), len(self.pending), label))
        self._redo.clear()

    def undo(self) -> str:
        if not self._undo:
            raise NothingToUndo(Text("nothing_to_undo", "nothing to undo"))
        data, n_ops, label = self._undo.pop()
        self._redo.append((self.db.to_bytes(), self.pending[n_ops:], label))
        self.db = MusicDatabase.from_bytes(data)
        del self.pending[n_ops:]
        self._changed("undo")
        return label

    def redo(self) -> str:
        if not self._redo:
            raise NothingToUndo(Text("nothing_to_redo", "nothing to redo"))
        data, ops, label = self._redo.pop()
        self._undo.append((self.db.to_bytes(), len(self.pending), label))
        self.db = MusicDatabase.from_bytes(data)
        self.pending.extend(ops)
        self._changed("redo")
        return label

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def redo_history(self) -> List[str]:
        return [label for _, _, label in reversed(self._redo)]

    def history(self) -> List[str]:
        return [label for _, _, label in self._undo]

    # ------------------------------------------------------------------ edits
    def rename_song(self, folder: int, song: int, name: str) -> None:
        fi, si = _idx(folder, song)
        if not self.db.song(fi, si).used:
            raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=folder, song=song))
        check_name(name)
        self._begin(Text("rename_song", "rename song {folder}/{song}", folder=folder, song=song))
        self.db.song(fi, si).name = name
        self._changed("song")

    def rename_folder(self, folder: int, name: str) -> None:
        fi, _ = _idx(folder)
        check_name(name)
        self._begin(Text("rename_folder", "rename folder {folder}", folder=folder))
        self.db.folders[fi].name = name
        self._changed("folder")

    def delete_song(self, folder: int, song: int) -> None:
        fi, si = _idx(folder, song)
        s = self.db.song(fi, si)
        if not s.used:
            raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=folder, song=song))
        self._begin(Text("delete", "delete {folder}/{song}", folder=folder, song=song))
        for p in layout.song_paths(fi, si, s).values():
            self.pending.append(FileOp("delete", p))
        self.db.folders[fi].songs[si] = Song()
        self.db.purge_slot(fi, si)
        self._changed("song")

    def delete_folders(self, folders: List[int]) -> int:
        """Empty these folders: all their songs go and they lose their names. One step to undo, one
        change notice (a song at a time made a full card of folders take long). Gives the songs deleted."""
        idx = [_idx(f)[0] for f in sorted(set(folders))]
        if not any(self.db.folders[fi].name or any(x.used for x in self.db.folders[fi].songs) for fi in idx):
            return 0
        self._begin(Text("delete_folders", "empty {n} folder(s)", n=len(idx)))
        n = 0
        for fi in idx:
            for si, x in enumerate(self.db.folders[fi].songs):
                if not x.used:
                    continue
                for path in layout.song_paths(fi, si, x).values():
                    self.pending.append(FileOp("delete", path))
                self.db.folders[fi].songs[si] = Song()
                self.db.purge_slot(fi, si)
                n += 1
            self.db.folders[fi].name = ""
        self._changed("folder")
        return n

    def _target(self, dfi: int, dsi: Optional[int]) -> int:
        if dsi is None:
            dsi = self.db.free_slot(dfi)
            if dsi is None:
                raise SlotError(Text("folder_full", "folder {n} is full (20 songs)", n=dfi + 1))
        elif self.db.song(dfi, dsi).used:
            raise SlotError(Text("song_in_use", "folder {folder} song {song} is in use", folder=dfi + 1, song=dsi + 1))
        return dsi

    def move_song(self, folder: int, song: int, to_folder: int, to_song: Optional[int] = None,
                  copy: bool = False) -> int:
        """Move (or copy) a song; returns the 1-based destination song number. Files get the
        destination's default names, so the result is valid whatever the source base was."""
        fi, si = _idx(folder, song)
        dfi, dsi = _idx(to_folder, to_song)
        src = self.db.song(fi, si)
        if not src.used:
            raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=folder, song=song))
        dsi = self._target(dfi, dsi)
        self._begin(Text("copy" if copy else "move", ("copy" if copy else "move") + " {folder}/{song} -> {to_folder}/{to_song}",
                         folder=folder, song=song, to_folder=to_folder, to_song=dsi + 1))
        dst = Song(src.name, layout.default_base(dfi), src.types)
        for ext, p in layout.song_paths(fi, si, src).items():
            self.pending.append(FileOp("copy" if copy else "move", p, layout.song_path(dfi, dsi, dst, ext)))
        self.db.folders[dfi].songs[dsi] = dst
        if not copy:
            self.db.folders[fi].songs[si] = Song()
            self.db.retarget_slot(fi, si, dfi, dsi)
        self._changed("song")
        return dsi + 1

    def swap_songs(self, folder: int, a: int, b: int) -> None:
        """Swap two slots in one folder (sorting / reordering)."""
        fi, ai = _idx(folder, a)
        _, bi = _idx(folder, b)
        sa, sb = self.db.song(fi, ai), self.db.song(fi, bi)
        self._begin(Text("swap", "swap {folder}/{a} <-> {folder}/{b}", folder=folder, a=a, b=b))
        na, nb = Song(sb.name, layout.default_base(fi), sb.types), Song(sa.name, layout.default_base(fi), sa.types)
        tmp = layout.folder_dir(fi) + "/~SWAP%02d" % (ai + 1)
        for ext, p in layout.song_paths(fi, ai, sa).items():
            self.pending.append(FileOp("move", p, tmp + "." + ext))
        for ext, p in layout.song_paths(fi, bi, sb).items():
            self.pending.append(FileOp("move", p, layout.song_path(fi, ai, na, ext)))
        for ext in sa.extensions:
            self.pending.append(FileOp("move", tmp + "." + ext, layout.song_path(fi, bi, nb, ext)))
        self.db.folders[fi].songs[ai], self.db.folders[fi].songs[bi] = na, nb
        self.db.retarget_slot(fi, ai, fi, 0xFE)
        self.db.retarget_slot(fi, bi, fi, ai)
        self.db.retarget_slot(fi, 0xFE, fi, bi)
        self._changed("song")

    def reorder_songs(self, folder: int, songs: List[int], to: int) -> List[int]:
        """Move several songs of one folder together to another place in that folder, as one undo
        step. They keep their order and land as a block: moving up, the block starts at slot `to`;
        moving down, it ends there. The other slots (empty ones too) keep their order around it.
        Favourites and song lists follow. Returns the new 1-based slot numbers of the songs."""
        fi, _ = _idx(folder)
        picked = sorted({_idx(folder, x)[1] for x in songs})
        _, ti = _idx(folder, to)
        if not picked or any(not self.db.song(fi, x).used for x in picked):
            raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=folder,
                                 song=next((x + 1 for x in picked if not self.db.song(fi, x).used), to)))
        rest = [x for x in range(N_SONGS) if x not in picked]
        if ti < picked[0]:                            # moving up: the block starts at `to`
            at = sum(1 for x in rest if x < ti)
        else:                                         # moving down: the block ends at `to`
            at = sum(1 for x in rest if x <= ti)
        order = rest[:at] + picked + rest[at:]        # new slot i holds old slot order[i]
        mapping = {old: new for new, old in enumerate(order) if old != new}
        if not mapping:
            return [x + 1 for x in picked]
        self._begin(Text("reorder", "move {n} songs in folder {folder} to {to}", n=len(picked), folder=folder, to=to))
        old = {si: self.db.song(fi, si) for si in mapping}
        d = layout.folder_dir(fi)
        for si, song in old.items():                  # 1: every file that moves to a temporary name
            if song.used:
                for ext, p in layout.song_paths(fi, si, song).items():
                    self.pending.append(FileOp("move", p, "%s/~O%02d.%s" % (d, si + 1, ext)))
        for si, song in old.items():                  # 2: temporary name -> its new slot
            t = mapping[si]
            new = Song(song.name, layout.default_base(fi), song.types) if song.used else Song()
            for ext in new.extensions if song.used else ():
                self.pending.append(FileOp("move", "%s/~O%02d.%s" % (d, si + 1, ext), layout.song_path(fi, t, new, ext)))
            self.db.folders[fi].songs[t] = new
        self._remap_refs({(fi, si): (fi, t) for si, t in mapping.items()})
        self._changed("song")
        return [mapping.get(x, x) + 1 for x in picked]

    def move_folder(self, folder: int, to_folder: int) -> None:
        """Put a whole folder (name and 20 slots) on another folder number, as one undo step.
        If that folder is in use, the two change places. Favourites and song lists follow."""
        a, _ = _idx(folder)
        b, _ = _idx(to_folder)
        if a == b:
            return
        self._begin(Text("move_folder", "move folder {folder} -> {to}", folder=folder, to=to_folder))
        self._permute_folders({a: b, b: a})
        self._changed("song")

    def insert_folder(self, folder: int, before: int) -> int:
        """Put a folder between two others: it lands just before folder `before` (100 = after the
        last) and the folders in between shift one place, as one undo step. Returns its new number."""
        a, _ = _idx(folder)
        if not 1 <= before <= N_FOLDERS + 1:
            raise SlotError(Text("folder_range", "folder {n} is out of range 1..{max}", n=before, max=N_FOLDERS + 1))
        p = before - 1
        new = p - 1 if a < p else p                    # where folder a ends up
        if new == a:
            return folder
        if a < new:                                   # moving down: a+1..new shift up one place
            mapping = {f: f - 1 for f in range(a + 1, new + 1)}
        else:                                         # moving up: new..a-1 shift down one place
            mapping = {f: f + 1 for f in range(new, a)}
        mapping[a] = new
        self._begin(Text("insert_folder", "insert folder {folder} before {before}", folder=folder, before=before))
        self._permute_folders(mapping)
        self._changed("song")
        return new + 1

    def insert_folders(self, folders: List[int], before: int) -> List[int]:
        """Put several folders together between two others, as one undo step: they land as a block,
        in their own order, just before folder `before` (100 = after the last); the other folders keep
        their order around it (like reordering a playlist). Favourites and song lists follow.
        Returns the new 1-based numbers of the folders, in their order."""
        picked = sorted({_idx(f)[0] for f in folders})
        if not 1 <= before <= N_FOLDERS + 1:
            raise SlotError(Text("folder_range", "folder {n} is out of range 1..{max}", n=before, max=N_FOLDERS + 1))
        if not picked:
            return []
        p = before - 1
        rest = [f for f in range(N_FOLDERS) if f not in picked]
        at = sum(1 for f in rest if f < p)
        order = rest[:at] + picked + rest[at:]        # new number i holds old folder order[i]
        mapping = {old: new for new, old in enumerate(order) if old != new}
        landed = [order.index(f) + 1 for f in picked]
        if not mapping:
            return landed
        self._begin(Text("insert_folders", "move {n} folders to {to}", n=len(picked), to=landed[0]))
        self._permute_folders(mapping)
        self._changed("song")
        return landed

    def _permute_folders(self, mapping: Dict[int, int]) -> None:
        """Give folders new numbers (0-based old -> new, a permutation of the same set): names,
        songs (files renamed via temporary names), favourites and song lists."""
        old = {f: self.db.folders[f] for f in mapping}
        for f, x in old.items():                      # 1: every file to a temporary name
            for si, song in enumerate(x.songs):
                if song.used:
                    for ext, p in layout.song_paths(f, si, song).items():
                        self.pending.append(FileOp("move", p, "%s/~R%02d%02d.%s" % (layout.folder_dir(f), f + 1, si + 1, ext)))
        for f, x in old.items():                      # 2: temporary name -> final place
            t = mapping[f]
            songs = [Song(y.name, layout.default_base(t), y.types) if y.used else Song() for y in x.songs]
            for si, y in enumerate(songs):
                if y.used:
                    for ext in y.extensions:
                        self.pending.append(FileOp("move", "%s/~R%02d%02d.%s" % (layout.folder_dir(f), f + 1, si + 1, ext),
                                                   layout.song_path(t, si, y, ext)))
            x.songs = songs
        for f, x in old.items():
            self.db.folders[mapping[f]] = x
        self._remap_refs({(f, si): (t, si) for f, t in mapping.items() for si in range(N_SONGS)})

    def _remap_refs(self, remap: Dict[Tuple[int, int], Tuple[int, int]]) -> None:
        """Point favourites and song lists at new (0-based) slots, all at once."""
        for bank in self.db.favorites:
            items = []
            for v in bank.items:
                it = FavoriteBank.decode_item(v)
                if it and it[0] == "song" and (it[1], it[2]) in remap:
                    v = FavoriteBank.encode_song(*remap[(it[1], it[2])])
                items.append(v)
            bank.items = items
        for n in range(N_PLAYLISTS):
            self.db.set_playlist(n, [remap.get(x, x) for x in self.db.playlist(n)])

    def import_song(self, source: Storage, files: Dict[str, str], name: str, folder: int,
                    song: Optional[int] = None) -> int:
        """Add a song from files in another storage (another card, a folder, an export)."""
        dfi, dsi = _idx(folder, song)
        dsi = self._target(dfi, dsi)
        self._begin(Text("import", "import {name} -> {folder}/{song}", name=name, folder=folder, song=dsi + 1))
        self._import(source, files, name, dfi, dsi)
        self._changed("song")
        return dsi + 1

    def _import(self, source: Storage, files: Dict[str, str], name: str, dfi: int, dsi: int) -> None:
        mask = 0
        for ext in files:
            mask |= 1 << FILE_TYPES.index(ext.upper().strip(". "))
        entry = Song(name[:16], layout.default_base(dfi), mask)
        for ext, p in files.items():
            self.pending.append(FileOp("import", p, layout.song_path(dfi, dsi, entry, ext.upper().strip(". ")),
                                       source, entry.name))
        self.db.folders[dfi].songs[dsi] = entry

    def import_song_list(self, source: "CardSession", list_no: int, to_list: Optional[int] = None,
                         folder: Optional[int] = None, folder_name: Optional[str] = None,
                         reuse: bool = False) -> Dict[str, object]:
        """Copy song list list_no (1..3) of another card onto this card, as one undo step.
        The songs go into one folder in list order (default: the first empty one, named folder_name),
        so the folder is a set list too (many players use folders that way). With reuse, songs that
        are already on this card with identical files are not copied again. Song list to_list
        (default: the first empty one) then holds the songs in the original order.
        Returns {"list", "folder", "copied", "reused"}."""
        if not 1 <= list_no <= N_PLAYLISTS:
            raise SlotError(Text("list_range", "song list {n} is out of range 1..{max}", n=list_no, max=N_PLAYLISTS))
        items = source.playlists()[list_no - 1]
        if not items:
            raise SlotError(Text("list_empty_on", "song list {n} of {card} is empty", n=list_no, card=source.storage.describe()))
        to_list = self._list_to_fill(to_list)
        if folder_name is not None:
            check_name(folder_name)
        plan = self._reuse_plan(source, items) if reuse else [(None, (f, so)) for f, so in items]
        to_copy = [p for p in plan if p[0] is None]
        dfi, free_slots = self._folder_for(folder, len(to_copy)) if to_copy else (None, [])

        self._begin(Text("copy_list", "copy song list {n} -> list {to}", n=list_no, to=to_list))
        result_slots = []
        slots = iter(free_slots)
        for here, (f, so) in plan:
            if here is None:
                src = source.db.song(f - 1, so - 1)
                dsi = next(slots)
                self._import(source.storage, layout.song_paths(f - 1, so - 1, src), src.name, dfi, dsi)
                here = (dfi, dsi)
            result_slots.append(here)
        if dfi is not None and folder_name and not self.db.folders[dfi].name:
            self.db.folders[dfi].name = folder_name
        self.db.set_playlist(to_list - 1, result_slots)
        self._changed("song")
        return {"list": to_list, "folder": dfi + 1 if dfi is not None else None,
                "copied": len(to_copy), "reused": len(plan) - len(to_copy)}

    def _list_to_fill(self, to_list: Optional[int]) -> int:
        """The song list (1..3) to fill: the one asked for, or the first empty one."""
        if to_list is None:
            free = [n for n, pl in enumerate(self.playlists(), 1) if not pl]
            if not free:
                raise SlotError(Text("lists_full", "all {n} song lists on this card are in use; choose one to replace", n=N_PLAYLISTS))
            return free[0]
        if not 1 <= to_list <= N_PLAYLISTS:
            raise SlotError(Text("list_range", "song list {n} is out of range 1..{max}", n=to_list, max=N_PLAYLISTS))
        return to_list

    def _songs_here(self):
        """The songs on this card, to find one that is already here: those on the card by their file
        sizes ({sorted (ext, size)}: [slots]), and those still to be imported in this session by
        where they come from ({frozenset (storage id, path)}: slot)."""
        saved = {op.dst.upper() for op in self.pending}
        pending_src = {op.dst.upper(): (id(op.src_storage), op.src.upper()) for op in self.pending if op.kind == "import"}
        here: Dict[tuple, List[Tuple[int, int]]] = {}
        incoming: Dict[frozenset, Tuple[int, int]] = {}
        for fi, si, s in self.db.iter_songs():
            paths = layout.song_paths(fi, si, s)
            if any(p.upper() in saved or not self.storage.exists(p) for p in paths.values()):
                srcs = [pending_src.get(p.upper()) for p in paths.values()]
                if all(srcs):
                    incoming[frozenset(srcs)] = (fi, si)
                continue                              # not on the card yet, cannot compare bytes
            here.setdefault(tuple(sorted((e, self.storage.size(p)) for e, p in paths.items())), []).append((fi, si))
        return here, incoming

    def _reuse_plan(self, source: "CardSession", items) -> List[Tuple[Optional[Tuple[int, int]], Tuple[int, int]]]:
        """For each song of the list: (the 0-based slot of the identical song already here, or None to
        copy it; its 1-based source slot). Sizes first, the bytes only when the sizes match."""
        from . import duplicates
        here, incoming = self._songs_here()
        plan: List[Tuple[Optional[Tuple[int, int]], Tuple[int, int]]] = []
        for f, so in items:
            spaths = layout.song_paths(f - 1, so - 1, source.db.song(f - 1, so - 1))
            found = incoming.get(frozenset((id(source.storage), p.upper()) for p in spaths.values()))
            key = tuple(sorted((e, source.storage.size(p)) for e, p in spaths.items()))
            if found is None and key in here:
                fp = duplicates._fingerprint(source.storage, spaths)
                found = next((slot for slot in here[key] if fp is not None and duplicates._fingerprint(
                    self.storage, layout.song_paths(slot[0], slot[1], self.db.song(*slot))) == fp), None)
            plan.append((found, (f, so)))
        return plan

    def _folder_for(self, folder: Optional[int], need: int) -> Tuple[int, List[int]]:
        """The 0-based folder that takes need songs (the one asked for, or the first empty one) and
        its free places."""
        if folder is None:
            dfi = next((fi for fi, fo in enumerate(self.db.folders)
                        if not fo.name and not any(x.used for x in fo.songs)), None)
            if dfi is None:
                raise SlotError(Text("no_empty_folder_for", "no empty folder left for {n} song(s)", n=need))
        else:
            dfi, _ = _idx(folder)
        free_slots = [si for si, x in enumerate(self.db.folders[dfi].songs) if not x.used]
        if len(free_slots) < need:
            raise SlotError(Text("folder_room", "folder {n} has {free} free place(s), {need} needed", n=dfi + 1, free=len(free_slots), need=need))
        return dfi, free_slots

    def merge_duplicates(self, keep: Tuple[int, int], copies: List[Tuple[int, int]],
                         song_list: Optional[int] = None) -> int:
        """Keep one song and delete its copies, as one undo step. Favourites and song lists that
        pointed at a copy now point at the kept song. With song_list (1..3) the kept song is also
        added to that list if it is not in it yet. Returns the number of copies removed.
        The caller decides which songs are copies (core.duplicates.find_duplicates)."""
        kfi, ksi = _idx(*keep)
        copies = [tuple(c) for c in copies if tuple(c) != tuple(keep)]
        for c in [keep] + copies:
            fi, si = _idx(*c)
            if not self.db.song(fi, si).used:
                raise SlotError(Text("song_empty", "folder {folder} song {song} is empty", folder=c[0], song=c[1]))
        if song_list is not None:
            self._check_room_in_list(song_list, (kfi, ksi), {(c[0] - 1, c[1] - 1) for c in copies})
        self._begin(Text("merge", "merge {n} copies into {folder}/{song}", n=len(copies), folder=keep[0], song=keep[1]))
        for c in copies:
            fi, si = c[0] - 1, c[1] - 1
            for p in layout.song_paths(fi, si, self.db.song(fi, si)).values():
                self.pending.append(FileOp("delete", p))
            self.db.folders[fi].songs[si] = Song()
            self.db.retarget_slot(fi, si, kfi, ksi)
        self._once_in_each_list((kfi, ksi))
        if song_list is not None:
            items = self.db.playlist(song_list - 1)
            if (kfi, ksi) not in items and len(items) < PLAYLIST_LEN:
                self.db.set_playlist(song_list - 1, items + [(kfi, ksi)])
        self._changed("song")
        return len(copies)

    def _check_room_in_list(self, song_list: int, kept: Tuple[int, int], gone: set) -> None:
        """Song list song_list (1..3) can take the kept song: it is in it already, it takes the place
        of a copy, or there is room."""
        if not 1 <= song_list <= N_PLAYLISTS:
            raise SlotError(Text("list_range", "song list {n} is out of range 1..{max}", n=song_list, max=N_PLAYLISTS))
        items = self.db.playlist(song_list - 1)
        if kept not in items and not any(p in gone for p in items) and len(items) >= PLAYLIST_LEN:
            raise SlotError(Text("list_full", "song list {n} is full ({max} songs)", n=song_list, max=PLAYLIST_LEN))

    def _once_in_each_list(self, slot: Tuple[int, int]) -> None:
        """After merging, a list may hold the kept song twice: keep its first place only."""
        for n in range(N_PLAYLISTS):
            seen, items = set(), []
            for p in self.db.playlist(n):
                if p == slot and p in seen:
                    continue
                seen.add(p)
                items.append(p)
            self.db.set_playlist(n, items)

    def import_folder(self, source: "CardSession", folder: int, to_folder: Optional[int] = None,
                      favorites: bool = True) -> Dict[str, object]:
        """Copy a whole folder of another card (songs on the same places, and its name) into an empty
        folder of this card (default: the first empty one), as one undo step. Its songs' favourite
        buttons come along where there is room (see _carry_favorites; result key "favorites")."""
        sfi, songs = self._source_folder(source, folder)
        if to_folder is None:
            dfi = next(iter(self._empty_folders()), None)
            if dfi is None:
                raise SlotError(Text("no_empty_folder", "no empty folder left on this card"))
        else:
            dfi, _ = _idx(to_folder)
            if any(x.used for x in self.db.folders[dfi].songs):
                raise SlotError(Text("folder_not_empty", "folder {n} is not empty", n=dfi + 1))
        self._begin(Text("copy_folder", "copy folder {folder} -> {to}", folder=folder, to=dfi + 1))
        name = self._copy_folder_in(source, sfi, songs, dfi)
        favs = self._carry_favorites(source, {(sfi, si): (dfi, si) for si, _ in songs}) if favorites else dict(_NO_FAVS)
        self._changed("song")
        return {"folder": dfi + 1, "copied": len(songs), "name": name, "favorites": favs}

    def import_folders(self, source: "CardSession", folders: List[int], start: Optional[int] = None) -> List[Dict[str, object]]:
        """Copy several whole folders of another card at once, as one undo step: each into an empty
        folder of this card, in their order. They fill the empty folders from `start` on (when that
        one is empty), then the first empty ones. Nothing happens unless all of them fit. Their
        favourite buttons come along as with import_folder; every result carries the same "favorites"."""
        picked = [(f, *self._source_folder(source, f)) for f in dict.fromkeys(folders)]
        empty = self._empty_folders()
        if start is not None and _idx(start)[0] in empty:
            s0 = _idx(start)[0]
            empty = [f for f in empty if f >= s0] + [f for f in empty if f < s0]
        if len(empty) < len(picked):
            raise SlotError(Text("too_few_empty_folders", "{n} folders do not fit: {free} empty folders left",
                                 n=len(picked), free=len(empty)))
        if not picked:
            return []
        self._begin(Text("copy_folders", "copy {n} folders", n=len(picked)))
        out, moved = [], {}
        for (folder, sfi, songs), dfi in zip(picked, empty):
            name = self._copy_folder_in(source, sfi, songs, dfi)
            moved.update({(sfi, si): (dfi, si) for si, _ in songs})
            out.append({"from": folder, "folder": dfi + 1, "copied": len(songs), "name": name})
        favs = self._carry_favorites(source, moved)
        for x in out:
            x["favorites"] = favs
        self._changed("song")
        return out

    def _carry_favorites(self, source: "CardSession", moved: Dict[Tuple[int, int], Tuple[int, int]]) -> Dict[str, object]:
        """Put the favourite buttons of copied songs on this card too. moved: 0-based slot on source ->
        0-based slot here. A favourite button of this card is never overwritten.

        The songs of one source bank stay together, on the same button numbers, in the first bank
        here that has those buttons free and suits it: the same bank number (with the same name, or
        still unused), another bank with the same name, or else an unused bank (no name, no buttons),
        which then gets the source bank's name. When no bank suits, those favourites stay behind and
        are counted in "left". Returns {"carried": n, "banks": [1-based banks here], "left": n}."""
        carried, left, banks = 0, 0, []
        for sb, src in enumerate(source.db.favorites):
            group = {}
            for pos, v in enumerate(src.items):
                it = FavoriteBank.decode_item(v)
                if it and it[0] == "song" and (it[1], it[2]) in moved:
                    group[pos] = FavoriteBank.encode_song(*moved[(it[1], it[2])])
            if not group:
                continue

            def free(b: FavoriteBank, group=group) -> bool:
                return all(b.items[pos] == 0 for pos in group)

            def unused(b: FavoriteBank) -> bool:
                return not b.name and not any(b.items)
            mine = self.db.favorites
            here = mine[sb] if sb < len(mine) and free(mine[sb]) and (mine[sb].name == src.name or unused(mine[sb])) else None
            if here is None and src.name:
                here = next((b for b in mine if b.name == src.name and free(b)), None)
            if here is None:
                here = next((b for b in mine if unused(b)), None)
            if here is None:
                left += len(group)
                continue
            for pos, v in group.items():
                here.items[pos] = v
            if not here.name:
                here.name = src.name
            carried += len(group)
            n = mine.index(here) + 1
            if n not in banks:
                banks.append(n)
        return {"carried": carried, "banks": sorted(banks), "left": left}

    def _empty_folders(self) -> List[int]:
        """0-based numbers of the folders without a name and without songs."""
        return [fi for fi, fo in enumerate(self.db.folders) if not fo.name and not any(x.used for x in fo.songs)]

    def _source_folder(self, source: "CardSession", folder: int):
        sfi, _ = _idx(folder)
        songs = [(si, x) for si, x in enumerate(source.db.folders[sfi].songs) if x.used]
        if not songs:
            raise SlotError(Text("folder_empty_on", "folder {n} of {card} is empty", n=folder, card=source.storage.describe()))
        return sfi, songs

    def _copy_folder_in(self, source: "CardSession", sfi: int, songs, dfi: int) -> str:
        for si, x in songs:
            self._import(source.storage, layout.song_paths(sfi, si, x), x.name, dfi, si)
        name = source.db.folders[sfi].name
        if name:
            self.db.folders[dfi].name = name
        return name

    def merge_from(self, other: "CardSession", folder_map: Optional[Dict[int, int]] = None) -> List[Tuple[int, int, int, int]]:
        """Copy every song of another card into free slots (same folder number unless remapped).
        Returns (src folder, src song, dst folder, dst song) tuples, 1-based."""
        done = []
        for f in other.folders():
            dst_folder = (folder_map or {}).get(f.folder, f.folder)
            if f.name and not self.db.folders[dst_folder - 1].name:
                self.rename_folder(dst_folder, f.name)
            for s in f.songs:
                src_entry = other.db.song(s.folder - 1, s.song - 1)
                files = layout.song_paths(s.folder - 1, s.song - 1, src_entry)
                n = self.import_song(other.storage, files, s.name, dst_folder)
                done.append((s.folder, s.song, dst_folder, n))
        return done

    # ------------------------------------------------------------------ save
    def bytes_needed(self) -> int:
        """Extra card space the pending plan needs (copies and imports; moves and deletes are free)."""
        n = 0
        plan = PlannedStorage(self.storage, [])         # the card as it is at each step of the plan:
        for op in self.pending:                         # a copy of a song moved or imported earlier in it
            if op.kind == "copy":                       # is read from where it is at that moment
                n += plan.size(op.src)
            elif op.kind == "import":
                n += op.src_storage.size(op.src)
            plan.add(op)
        return n

    def preflight(self) -> None:
        """Refuse to start a save that cannot finish: read-only card or too little space."""
        if not self.storage.writable():
            raise KN7Error(Text("locked", "{card} is write-protected (is the lock switch on the SD card down?)", card=self.storage.describe()))
        free = self.storage.free_bytes()
        need = self.bytes_needed() + 2 * 0xD620     # room for a new INF and BAK while writing
        if free is not None and need > free:
            raise KN7Error(Text("no_space", "not enough space on {card}: {need} KB needed, {free} KB free",
                                card=self.storage.describe(), need=(need + 1023) // 1024, free=free // 1024))

    def _expected_files(self) -> Dict[str, Optional[str]]:
        """Run the plan on paper, before anything changes: for every path it touches, the SHA-1 of what
        must be there after the save, or None when the path must be gone. Each source file is read once,
        as it is now; a swap through a temporary name works out because the plan is followed in order."""
        import hashlib
        state: Dict[str, Optional[str]] = {}

        def now(path: str) -> Optional[str]:
            if path not in state:
                state[path] = hashlib.sha1(self.storage.read(path)).hexdigest() if self.storage.exists(path) else None
            return state[path]
        for op in self.pending:
            if op.kind == "move":
                h = now(op.src)
                state[op.dst], state[op.src] = h, None
            elif op.kind == "copy":
                state[op.dst] = now(op.src)
            elif op.kind == "delete":
                state[op.src] = None
            elif op.kind == "import" and op.src_storage is not None:
                state[op.dst] = hashlib.sha1(op.src_storage.read(op.src)).hexdigest()
        return state

    def _verify_files(self, expected: Dict[str, Optional[str]]) -> int:
        """After a save: read every touched file back and compare it with what the plan said, byte for
        byte (by SHA-1). Returns how many files were checked; raises when one differs."""
        import hashlib
        read = getattr(self.storage, "read_from_card", self.storage.read)   # past the computer's cache
        wrong = []
        for path, h in expected.items():
            there = self.storage.exists(path)
            if h is None:
                if there:
                    wrong.append(path)
            elif not there or hashlib.sha1(read(path)).hexdigest() != h:
                wrong.append(path)
        log.info("  verified %d file(s), %d wrong", len(expected), len(wrong))
        if wrong:
            raise KN7Error(Text("verify_failed", "after saving, {n} file(s) on the card are not what they should be "
                                "({paths}); the back-up made before saving still has the old card",
                                n=len(wrong), paths=", ".join(wrong[:5])))
        return len(expected)

    def unfinished_save(self) -> Optional[Dict[str, str]]:
        """When a save was cut off (card pulled out, computer off), our note is still on the card:
        {'started': ISO time, 'backup': back-up zip made just before, or ''}. None if all is well."""
        if not self.storage.exists(layout.JOB_PATH):
            return None
        info = {"started": "", "backup": ""}
        try:
            for line in self.storage.read(layout.JOB_PATH).decode("utf-8", "replace").splitlines():
                key, _sep, value = line.partition(" ")
                if key in info:
                    info[key] = value.strip()
        except OSError:
            pass
        return info

    def forget_unfinished_save(self) -> None:
        if self.storage.exists(layout.JOB_PATH):
            self.storage.remove(layout.JOB_PATH)

    def _write_job(self, backup_zip: str) -> None:
        import datetime as _dt
        lines = ["KN Songboek save in progress; if this file is still here, that save did not finish",
                 "started " + _dt.datetime.now().replace(microsecond=0).isoformat(),
                 "backup " + (backup_zip or "")]
        lines += ["op " + str(op) for op in self.pending]
        self.storage.write(layout.JOB_PATH, ("\n".join(lines) + "\n").encode("utf-8"))

    def check_songs(self) -> List[str]:
        """Every file the database names, looked for on the card: the paths that are missing."""
        return [p for fi, si, s in self.db.iter_songs() for p in layout.song_paths(fi, si, s).values()
                if not self.storage.exists(p)]

    def save(self, backup: bool = True, progress: Callable[[int, int, str], None] = None,
             backup_zip: str = "", phase: Optional[Callable[[str], None]] = None) -> int:
        """Apply the pending file operations, then write the database. Returns the number of
        file operations performed. While it runs a note (layout.JOB_PATH) is on the card, so a save
        that is cut off is noticed the next time the card is opened. phase("write") and
        phase("verify") say where it is, for the step window's list."""
        self.preflight()
        if phase:
            phase("write")
        total = len(self.pending)
        log.info("save to %s: %d file operation(s)", self.storage.describe(), total)
        expected = self._expected_files()               # what every touched file must hold afterwards
        self._write_job(backup_zip)
        for i, op in enumerate(self.pending):
            if progress:
                progress(i, total, str(op))
            log.info("  %s", op)
            if op.kind == "move":
                self.storage.move(op.src, op.dst)
            elif op.kind == "copy":
                self.storage.copy(op.src, op.dst)
            elif op.kind == "delete":
                if self.storage.exists(op.src):
                    self.storage.remove(op.src)
            elif op.kind == "import":
                self.storage.write(op.dst, op.src_storage.read(op.src))
        # As the instrument does (func_48562464): keep the old INF as BAK while writing, write the
        # new INF, read it back, then make BAK an identical second copy.
        if backup and self.storage.exists(layout.INF_PATH):
            self.storage.copy(layout.INF_PATH, layout.BAK_PATH)
        self.db.rebuild_alpha_index()
        data = self.db.to_bytes()
        self.storage.write(layout.INF_PATH, data)
        if phase:
            phase("verify")
        read = getattr(self.storage, "read_from_card", self.storage.read)
        if read(layout.INF_PATH) != data:
            raise KN7Error(Text("read_back", "the database did not read back correctly; KN7000MN.BAK still holds the old one"))
        if backup:
            self.storage.write(layout.BAK_PATH, data)
        log.info("  database written (%d songs)", sum(1 for _ in self.db.iter_songs()))
        self.verified = self._verify_files(expected)
        # the whole card once more: the database as it is on the card names only files that are there
        self.missing_after = self.check_songs()
        self.checked_songs = sum(1 for _ in self.db.iter_songs())
        self.forget_unfinished_save()
        log.info("  card checked: %d songs, %d file(s) missing", self.checked_songs, len(self.missing_after))
        self.pending.clear()
        self._undo.clear()
        self._redo.clear()
        self.loaded_from = layout.INF_PATH
        self._changed("saved")
        return total
