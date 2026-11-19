"""Presenter for the main window (Model-View-Presenter).

The view (Qt or anything else) only shows what the presenter gives it and forwards user actions.
All decisions live here, so they can be tested without a display (tests/test_presenter.py).
Numbers are 1-based, as on the keyboard.
"""
from __future__ import annotations

import csv
import hashlib
import datetime as _dt
import os
import zipfile
from dataclasses import dataclass
from html import escape
from types import SimpleNamespace
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple

from ..core import CardSession, KN7Error
from ..core.errors import InvalidName
from ..core import backup, duplicates, repair
from ..core import cards, verify
from ..core import library as lb
from ..formats import layout
from ..storage import DirectoryStorage, open_storage, trash, windows
from .i18n import has_key, size_text, tr
from .presenter_song import FAIL, SongDetails

Slot = Tuple[int, int]          # (folder, song)


@dataclass(frozen=True)
class FolderRow:
    folder: int
    name: str
    used: int


@dataclass(frozen=True)
class SongRow:
    folder: int
    song: int
    name: str                   # "" for an empty slot
    types: str
    used: bool


@dataclass(frozen=True)
class Actions:
    card: bool = False          # a card is open
    save: bool = False
    undo: bool = False
    redo: bool = False
    undo_text: str = ""
    redo_text: str = ""
    pending: int = 0            # changes not on the card yet (the yellow bar)
    composing: bool = False     # a new card in memory, not on a card yet


@dataclass(frozen=True)
class BackupRow:
    path: str
    label: str                  # "Vandaag 14:32  ·  120 songs"
    group: str = ""             # "KN7000  (deze kaart)": the card it was taken of
    this_card: bool = False     # looks like the open card (half its songs or more in common)
    library: bool = False       # an old library copy, kept when it was replaced


@dataclass(frozen=True)
class DuplicateRow:
    identical: bool             # True: same files, can be merged; False: same name, different content
    name: str
    slots: Tuple[Slot, ...]
    labels: Tuple[str, ...]     # "03/01  folder name" per copy
    saving: str                 # space freed by keeping one ("" when not identical)


@dataclass(frozen=True)
class LibraryRow:
    index: int                  # position in Library.songs, used for dragging
    name: str
    tempo: str
    recorded: str
    cards: str                  # "Kaart 01, Kaart 07"
    where: str                  # one line per copy, for the tooltip
    types: str
    meter: str = ""             # "4/4", "3/4"; "" when unknown
    slot: str = ""              # number in the folder ("01".."20") or song list, when one is shown
    inside: Tuple[str, ...] = ()  # songs in a diskette's full set ("Annie's Song", ...)
    damaged: Tuple[str, ...] = ()  # files that do not unpack: shown in orange, asked before use


class MainView(Protocol):
    def show_folders(self, rows: List[FolderRow], current: int) -> None: ...
    def show_songs(self, rows: List[SongRow], search_mode: bool) -> None: ...
    def show_history(self, done: List[str], undone: List[str]) -> None: ...
    def show_status(self, text: str) -> None: ...
    def show_space(self, text: str) -> None: ...
    def show_error(self, text: str) -> None: ...
    def set_title(self, text: str) -> None: ...
    def set_actions(self, actions: Actions) -> None: ...
    def confirm(self, text: str) -> bool: ...
    def retranslate(self) -> None: ...
    def show_favorites(self, banks: List[str], bank: int, items: List[str]) -> None: ...
    def show_song_list(self, n: int, rows: List[Tuple[Slot, str]]) -> None: ...
    def show_other(self, title: str, folders: List[FolderRow], current: int, songs: List[SongRow]) -> None: ...
    def show_library(self, title: str, cards: List[str], rows: List[LibraryRow]) -> None: ...
    def choose(self, text: str, options: List[str]) -> Optional[int]: ...
    def ask(self, text: str, buttons: List[str]) -> Optional[int]: ...        # None = cancelled
    def ask_text(self, text: str, default: str = "") -> Optional[str]: ...
    def show_page(self, page: str) -> None: ...                             # "start", "organize", "compose"
    def show_header(self, name: str, text: str, used: int, total: int) -> None: ...   # card name + fullness meter
    def notify(self, text: str) -> None: ...            # "DANSEN verplaatst naar map 3" with an undo button
    def show_done(self, text: str, other: str = "") -> bool: ...           # True: the other button was chosen
    def pick_folder(self, text: str) -> Optional[str]: ...


class MainPresenter(SongDetails):
    def __init__(self, view: MainView, opener: Callable[[str], CardSession] = None,
                 lang: str = "nl", backup_dir: Optional[str] = None):
        self.view = view
        self.session: Optional[CardSession] = None
        self._opener = opener or (lambda path: CardSession.open(open_storage(path)))
        self.backups = True          # zip the card's KN7000 folder before every save (core/backup.py)
        self.world = None            # practising: the made-up computer (core/practice.py), else None
        self._real: Dict[str, object] = {}          # what practising stands in for, back when it stops
        self.backup_dir = backup_dir
        self.lang = lang
        self.folder = 1
        self.query = ""
        self.card_path = ""
        self.bank = 1                # favourite bank shown in the editor
        self.list_no = 1             # song list shown in the editor
        self.other: Optional[CardSession] = None     # second card, read-only source
        self.other_folder = 1
        self.library: Optional[lb.Library] = None
        self.library_path = ""
        self.lib_filter: Dict[str, object] = {}
        self._file_digests: Dict[object, bytes] = {}    # files of the open card, by where they are read
        self._detail_pos = 0
        self.page = "start"
        self.composing = False       # session is a new card in memory (core/cards.new_card)
        self._checking = False       # the checks after opening run once, not again when they reopen
        self.find_cards: Callable[[], List[cards.CardInfo]] = cards.find_cards
        # Long work (reading a library, writing a card, back-ups) goes through runner(text, job, phases,
        # hold), where job(progress) does the work. phases: [(key, label)] the step window lists while
        # it runs (progress(-1, k, key) says phase k has started); hold: "Haal de kaart er nog niet uit".
        # The job(progress) does the work. The Qt view runs it on a worker thread so the window never hangs;
        # here (tests, no GUI) it simply runs. While it runs the session's change notifications are held
        # back and replayed afterwards, so the view is only updated from its own thread.
        self.runner: Callable[..., object] = lambda text, job, phases=(), hold="": job(None)
        self._quiet = 0
        self._missed = False
        self.eject: Callable[[str], bool] = cards.eject
        self.volume_roots: Callable[[], List[str]] = cards.volume_roots
        self.is_drive: Callable[[str], bool] = os.path.ismount     # a diskette, not a folder on the computer
        self.rename_volume: Callable[[str, str], Optional[str]] = cards.rename_volume
        self.compose_name = ""       # what the new card will be called (its volume label), "" = not chosen
        self.waiting_for: Tuple[str, ...] = ()           # card kinds the open question waits for

    def t(self, key: str, **kw) -> str:
        return tr(self.lang, key, **kw)

    @property
    def practice(self) -> bool:
        return self.world is not None

    def _busy(self, key: str, job: Callable[[Optional[Callable[[int, int, str], None]]], object],
              phases: Sequence[str] = (), hold: str = ""):
        """Run job(progress) through the view's runner (see __init__). Exceptions come back here.
        phases: the keys of the parts of the job, in order (the step window shows them as a list that
        gets ticked off; the job says where it is with _phase); hold: what must stay in the computer
        while it runs ("card", "floppy" or "stick")."""
        self._quiet += 1
        try:
            return self.runner(self.t(key), job, phases=[(k, self.t("ph_" + k)) for k in phases],
                               hold=self.t("hold_" + hold) if hold else "")
        finally:
            self._quiet -= 1
            if not self._quiet and self._missed:
                self._missed = False
                self.refresh()

    @staticmethod
    def _phase(p: Optional[Callable[[int, int, str], None]], phases: Sequence[str]) -> Callable[[str], None]:
        """phase(key): tell the step window that this part of the job has started (as progress -1)."""
        def phase(key: str) -> None:
            if p is not None and key in phases:
                p(-1, list(phases).index(key), key)
        return phase

    def _renamed_phase(self, p, phases: Sequence[str]) -> Callable[[str], None]:
        """As _phase, where the core's "write" is a new card's "write_new" (other words in the list)."""
        phase = self._phase(p, phases)
        return lambda key: phase("write_new" if key == "write" and "write_new" in phases else key)

    def _notify(self, text: str) -> None:
        """Say what an edit did, with "Ongedaan maken" next to it (instead of asking "are you sure?")."""
        self.view.show_status(text)
        self.view.notify(text)

    def _guard(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except InvalidName as e:
            self.view.show_error(self.t("name_bad_chars", name=e.name, bad=" ".join(e.bad)) if e.bad
                                 else self.t("name_too_long", name=e.name, n=len(e.name)))
        except KN7Error as e:
            self.view.show_error(self.error_text(e))
        except OSError as e:
            self.view.show_error(self.os_error_text(e))
        return FAIL

    def error_text(self, e: "KN7Error") -> str:
        """The error in the user's language: core errors carry a key (core.errors.Text); one without
        (a damaged file, read by the format code) is said in words around its technical detail."""
        if e.key and has_key("err." + e.key):
            return self.t("err." + e.key, **e.values)
        return self.t("err_other", detail=str(e))

    def os_error_text(self, e: OSError) -> str:
        import errno
        key = {errno.ENOSPC: "err_os_full", errno.EROFS: "err_os_locked", errno.EACCES: "err_os_access",
               errno.EPERM: "err_os_access", errno.ENOENT: "err_os_gone"}.get(e.errno or 0, "err_os_other")
        return self.t(key, path=e.filename or "", detail=e.strerror or str(e)).strip()

    def step_text(self, label: str) -> str:
        """An undo/redo step ("rename song 1/3") in the user's language."""
        key = getattr(label, "key", "")
        if key and has_key("step." + key):
            return self.t("step." + key, **label.values)
        return str(label)

    # -------------------------------------------------------------- rendering
    def refresh(self, _what: str = "") -> None:
        if self._quiet:                  # long work running (maybe on another thread): later
            self._missed = True
            return
        if hasattr(self.view, "show_practice"):        # the start screen says it while practising
            self.view.show_practice(self.practice_reader_text())
        s = self.session
        if s is None:
            self._show_nothing()
            return
        folders = [FolderRow(fi + 1, f.name, sum(1 for x in f.songs if x.used)) for fi, f in enumerate(s.db.folders)]
        self.view.show_folders(folders, self.folder)
        self.view.show_songs(self.song_rows(), bool(self.query))
        hist, redo = [self.step_text(x) for x in s.history()], [self.step_text(x) for x in s.redo_history()]
        self.view.show_history(hist, redo)
        # a new card can go on a card as soon as it has songs, also when it started as a copy of a
        # kept card and nothing was changed yet (then there is no history)
        pending = len(hist) if not self.composing else max(len(hist), sum(f.used for f in folders))
        self.view.set_actions(Actions(True, s.dirty or self.composing, bool(hist), bool(redo),
                                      hist[-1] if hist else "", redo[0] if redo else "",
                                      pending, self.composing))
        where = self.t("new_card_title") if self.composing else s.storage.describe()
        self.view.set_title("%s - %s%s" % (self.t("title"), where, " *" if s.dirty else ""))
        self._show_space()
        if s.dirty:
            self.view.show_status(self.t("pending", last=hist[-1]))
        self.view.show_header(*self.header())
        locked = not self.composing and not s.storage.writable()      # a bar that stays until it is unlocked
        if hasattr(self.view, "show_locked"):
            self.view.show_locked(self.t("locked_open") if locked else "")
        self._show_lists()
        self._show_other()

    def _show_nothing(self) -> None:
        self.view.show_folders([], 0)
        self.view.show_songs([], False)
        self.view.show_history([], [])
        self.view.set_actions(Actions())
        self.view.set_title(self.t("title"))
        self.view.show_space("")
        self.view.show_header("", "", 0, 0)
        self.view.show_status(self.t("no_card"))

    def _show_space(self) -> None:
        s = self.session
        if self.composing:
            self.view.show_space(self.fullness_text())
            return
        free = s.storage.free_bytes()
        if free is not None:
            self.view.show_space(self._free_text(s.storage, free))

    # -------------------------------------------------------------- tasks (ADR-0008)
    # The start screen. Each task: (key, method name). A floppy task can be added here later.
    TASKS = [("task_organize", "start_organize"), ("task_compose", "start_compose"), ("task_archive", "start_archive")]

    KEEP = "keep"                    # _pick_card: the extra choice (no card: keep it in the library instead)

    def _pick_card(self, kinds: Sequence[str], none_key: str, extra: str = ""):
        """Find the cards of the given kinds that are in the computer; ask which one if more than one.
        None if there is none (after telling the user) or the user cancelled; KEEP if extra (one more
        button when there is no card) was chosen."""
        while True:
            busy = "looking_for_floppy" if list(kinds) == [cards.FLOPPY] else \
                "looking_for_card_or_floppy" if cards.FLOPPY in kinds else "looking_for_cards"
            all_cards = self._guard(self._busy, busy, lambda _p: self.find_cards())
            found = [c for c in ([] if all_cards is FAIL else all_cards) if c.kind in kinds]
            if len(found) == 1:
                return found[0]
            if found:
                i = self.view.choose(self.t("which_card"), [self.card_text(c) for c in found])
                return None if i is None else found[i]
            # practising: the card is put in with a click (Kaart wisselen) instead of by hand, and never a
            # folder of the real computer
            text = self.t(none_key)
            # an empty SD card that is in: say so, so "no card" is not a riddle (never other disks, such as
            # an external drive: those are no cards)
            others = [c for c in ([] if all_cards is FAIL else all_cards) if c.kind == cards.EMPTY and cards.EMPTY not in kinds]
            if others:
                what = self.t("other_cards_in", names=", ".join(self.card_text(c) for c in others))
                head, _, rest = text.partition("\n\n")      # what happened, what is in it, what to do
                text = "\n\n".join(x for x in (head, what, rest) if x)
            if self.practice:
                text += "\n\n" + self.t("practice_no_card")
            a = self.view.ask(text, [self.t("btn_search_again"),
                                                 self.t("btn_practice_swap" if self.practice else "btn_choose_folder")]
                              + ([extra] if extra else []))
            if a is None:
                return None
            if a == 2:
                return self.KEEP
            if a == 1 and self.practice:
                self.swap_practice_card()
            elif a == 1:
                path = self.view.pick_folder(self.t("choose_card_folder"))
                return cards.classify(path) if path else None

    def card_text(self, c: "cards.CardInfo") -> str:
        text = self._card_text(c)
        if not c.writable and c.kind != cards.FLOPPY:    # a diskette is only read: its tab does not matter
            text += self.t("card_locked")
        return text

    def _card_text(self, c: "cards.CardInfo") -> str:
        if c.kind == cards.KN7000:
            return self.t("card_kn7000", name=c.name, n=c.songs)
        if c.kind == cards.EMPTY:
            return self.t("card_empty", name=c.name)
        if c.kind == cards.FLOPPY:
            return self.t("card_floppy", name=c.name, n=c.songs)
        return self.t("card_other", name=c.name)

    def leave(self) -> bool:
        """Back to the start screen. With changes that are not on the card: put them on, throw them
        away, or stay."""
        s = self.session
        if s is not None and (s.dirty or self.composing and any(True for _ in s.db.iter_songs())):
            a = self.view.ask(self.t("leave_unsaved", n=len(s.history())), [self.t("btn_put_on_card"), self.t("btn_discard")])
            if a is None:
                return False
            if a == 0 and not self.put_on_card():
                return False
        self.session, self.composing, self.card_path, self.query = None, False, "", ""
        self.page = "start"
        self.view.show_page("start")
        self.refresh()
        return True

    def start_organize(self, path: Optional[str] = None) -> bool:
        """Task 1: open the KN7000 card that is in the computer (or the given folder)."""
        if path is None:
            c = self._pick_card([cards.KN7000], "no_kn7000_card")
            if c is None:
                return False
            path = c.path
        if not self.open_card(path):
            return False
        self.composing = False
        self.page = "organize"
        self.view.show_page("organize")
        self.refresh()
        return True

    # -------------------------------------------------------------- practising (core/practice.py)
    _SEAMS = ("find_cards", "eject", "volume_roots", "rename_volume", "is_drive", "backup_dir")

    def start_practice(self) -> bool:
        """"Eerst oefenen": a made-up computer with a card reader, a library and back-ups of its own. The
        three tasks then go exactly as they do for real (the same code and screens); only the SD card is
        put in with a click. Nothing happens to a real card or the real library."""
        from ..core import practice
        if self.practice or self.session is not None and not self.leave():
            return False
        world = self._guard(practice.PracticeWorld.make, practice.practice_dir(self.backup_dir or ""))
        if world is FAIL:
            return False
        self._real = {k: getattr(self, k) for k in self._SEAMS}
        self._real["library_path"] = self.library_path if self.library is not None else ""
        self.find_cards, self.eject, self.volume_roots = world.find_cards, world.eject, world.volume_roots
        self.rename_volume, self.is_drive, self.backup_dir = world.rename_volume, (lambda _p: False), world.backups
        self.world = world
        self.open_library(world.library)
        self.page = "start"
        self.view.show_page("start")
        self.refresh()
        points = self.t("practice_points", card=practice.SONGS_CARD, kept=practice.KEPT_CARD).split("\n")
        if hasattr(self.view, "show_intro"):           # the GUI: a window of its own, with a heading and points
            self.view.show_intro(self.t("practice_title"), self.t("practice_intro"), points, self.t("btn_practice_begin"))
        else:
            self.view.show_done("\n".join([self.t("practice_intro")] + points))
        return True

    def stop_practice(self) -> bool:
        """Back to the real computer, card reader and library."""
        if not self.practice or not self.leave():
            return False
        real, self._real = self._real, {}
        for k in self._SEAMS:
            setattr(self, k, real[k])
        self.world, self.library = None, None
        self.library_path = ""
        if real.get("library_path"):
            self.open_library(str(real["library_path"]))
        else:
            self.view.show_library("", [], [])
        self.refresh()
        return True

    def practice_reader_text(self) -> str:
        """What is in the practice card reader now (the start screen says it while practising)."""
        if not self.practice:
            return ""
        inside = self.world.in_reader()
        return self.t("practice_in_reader", name=", ".join(inside)) if inside else self.t("practice_reader_empty")

    def swap_practice_card(self) -> bool:
        """Kaart wisselen: take the card out of the practice reader and put another one in (one taken
        out earlier, a new empty SD card, or none)."""
        if not self.practice:
            return False
        if self.session is not None and not self.leave():
            return False
        shelf = self.world.on_shelf()
        options = [self.t("practice_put_in", name=n) for n in shelf] + [self.t("practice_new_card")]
        if self.world.in_reader():
            options.append(self.t("practice_take_out"))
        a = self.view.choose(self.t("practice_swap_q"), options)
        if a is None:
            return False
        if a < len(shelf):
            ok = self._guard(self.world.insert, shelf[a])
        elif a == len(shelf):
            ok = self._guard(self.world.insert, None)
        else:
            ok = self._guard(lambda: [self.world.eject(p) for p in self.world._dirs(self.world.reader)])
        self.refresh()
        return ok is not FAIL

    def _unlocked(self, storage) -> bool:
        """A locked SD card can be read but not written. Ask to unlock it until it is, or the user
        stops (False)."""
        while not storage.writable():
            if self.view.ask(self.t("locked_write"), [self.t("btn_try_again")]) is None:
                return False
        return True

    def start_compose(self) -> bool:
        """Task 2: a new card in memory, empty or starting as a copy of a card kept in the library
        (make one card, keep it, then make the next one from it); songs come from the library."""
        base = None
        kept = list(self.library.cards) if self.library is not None else []
        if kept:
            options = [self.t("compose_start_empty")] + [self.t("compose_start_from", name=c.label) for c in kept]
            a = self.view.choose(self.t("compose_how"), options)
            if a is None:
                return False
            base = kept[a - 1] if a else None
        s = self._guard(cards.new_card_from, base.session) if base is not None else self._guard(cards.new_card)
        if s is FAIL:
            return False
        self._begin_compose(s)
        return True

    def _begin_compose(self, s: CardSession) -> None:
        self.session, self.card_path, self.query, self.folder = s, "", "", 1
        self.composing = True
        self.compose_name = ""
        s.on_change(self.refresh)
        self.page = "compose"
        self.view.show_page("compose")
        self.refresh()

    def name_new_card(self) -> bool:
        """Click on "Nieuwe kaart": the name the SD card gets when it is put on a card (and the
        suggested name in the library)."""
        if not self.composing:
            return False
        ask = getattr(self.view, "ask_volume_name", self.view.ask_text)    # the GUI limits typing to 11
        name = ask(self.t("ask_card_name"), self.compose_name)
        if name is None:
            return False
        self.compose_name = cards.volume_name(name)
        self.refresh()
        return True

    SLOTS = 99 * 20                  # what really limits a KN7000 card: 99 folders of 20 songs

    def card_name(self) -> str:
        """The name in the top bar: the SD card's name (its volume label), or "Nieuwe kaart"."""
        if self.composing or self.session is None:
            return (self.composing and self.compose_name) or self.t("new_card_name")
        return windows.display_name(self.card_path or self.session.storage.describe())

    def header(self) -> Tuple[str, str, int, int]:
        """(card name, "14 songs in 5 mappen\n28.9 GB vrij", songs, 1980) for the top bar."""
        s = self.session
        songs = sum(1 for _ in s.db.iter_songs())
        folders = sum(1 for f in s.db.folders if any(x.used for x in f.songs))
        text = self.t("header_songs_1" if songs == 1 else "header_songs", n=songs) + " " + \
            self.t("header_folders_1" if folders == 1 else "header_folders", n=folders)
        if self.composing:
            size = self._guard(s.bytes_needed)
            text += "\n" + size_text(0 if size is FAIL else size)
        else:
            free = s.storage.free_bytes()
            if free is not None:
                text += "\n" + self._free_text(s.storage, free)
        return self.card_name(), text, songs, self.SLOTS

    def fullness_text(self) -> str:
        s = self.session
        n = sum(1 for _ in s.db.iter_songs())
        size = self._guard(s.bytes_needed)
        return self.t("fullness_1" if n == 1 else "fullness", n=n, size=size_text(0 if size is FAIL else size))

    def put_on_card(self, progress: Callable[[int, int, str], None] = None, target: Optional[str] = None) -> bool:
        """The one 'save' button: back-up, write, then 'done, you can take the card out'."""
        s = self.session
        if s is None:
            return False
        if not self.composing:
            if not s.dirty:
                return True
            if not self._unlocked(s.storage) or not self.save(progress):
                return False
            self._done(self.card_path)
            return True
        if not any(True for _ in s.db.iter_songs()):
            self.view.show_error(self.t("compose_empty"))
            return False
        target = target or self._target_card()
        if target is None:
            return False
        if target == self.KEEP:
            return self.keep_for_later()
        if not self._unlocked(DirectoryStorage(target)):
            return False
        dest = DirectoryStorage(target)
        steps = ["space"] + (["backup"] if dest.isdir(layout.KN7_DIR) else []) + ["write_new", "verify"]
        res = self._guard(self._busy, "saving",
                          lambda p: cards.write_card(s, dest, p or progress, self.backup_dir,
                                                     self._renamed_phase(p, steps)), steps, "card")
        if res is FAIL:
            return False
        name = self.compose_name
        if name:                                         # the SD card gets the name chosen for it
            moved = self._guard(self.rename_volume, target, name)
            if moved and moved is not FAIL:
                target = moved
        self.composing = False
        self.card_path = target
        self.page = "organize"
        self.view.show_page("organize")
        self.refresh()
        self._offer_keep(target, name)
        self._done(target)
        return True

    def _target_card(self) -> Optional[str]:
        """The SD card a new card is written to: found, and the user agrees to what is on it now."""
        c = self._pick_card([cards.EMPTY, cards.KN7000], "no_target_card",
                            self.t("btn_keep_for_later") if self.library is not None else "")
        if c is None or c == self.KEEP:
            return c
        if c.kind == cards.OTHER and not self.view.confirm(self.t("confirm_other_target", name=c.name)):
            return None
        if c.kind == cards.KN7000 and c.songs and not self.view.confirm(self.t("confirm_replace_card", name=c.name, n=c.songs)):
            return None
        return c.path

    def keep_for_later(self) -> bool:
        """No SD card at hand: the new card goes into the library under a name of its own, as a kept card.
        Later it goes on an SD card with Nieuwe kaart samenstellen › Beginnen met <name> (one way to make a
        card from a kept one, not a second kind of draft)."""
        lib, s = self.library, self.session
        if lib is None or s is None or not self.composing:
            return False
        name = None
        while name is None:
            name = self.view.ask_text(self.t("ask_keep_name"), self.compose_name)
            if name is None:
                return False
            name = name.strip()
            if not name or os.path.exists(os.path.join(lib.root, name)):
                if name:
                    self.view.show_error(self.t("name_taken", name=name))
                name = None
        folder = os.path.join(lib.root, name)
        res = self._guard(self._busy, "archiving",
                          lambda p: cards.write_card(s, DirectoryStorage(folder), p, self.backup_dir))
        if res is FAIL:
            return False
        self.composing = False                      # it is kept now: nothing is left unsaved
        self.open_library(lib.root)
        self.leave()
        self.view.show_done(self.t("kept_for_later", name=name))
        return True

    def _offer_keep(self, path: str, suggest: str = "") -> None:
        """Right after a new card is written: keep it in the library too, so the next card can start
        from it, without putting the card in again later."""
        lib = self.library
        if lib is None or not self.view.confirm(self.t("ask_keep_new")):
            return
        name = None
        while name is None:
            name = self.view.ask_text(self.t("ask_label"), suggest)
            if name is None:
                return
            name = name.strip()
            if not name or os.path.exists(os.path.join(lib.root, name)):
                if name:
                    self.view.show_error(self.t("name_taken", name=name))
                name = None
        check = verify.CopyCheck()
        folder = self._guard(self._busy, "archiving",
                             lambda p: cards.archive_card(DirectoryStorage(path), lib.root, name, False, p,
                                                          self.backup_dir, check), hold="card")
        if folder is not FAIL:
            self.open_library(lib.root)
            self._done_extra = self.t("archived_too", name=name) + "\n" + self.check_text(check)   # said by _done
            self._kept_label = os.path.basename(folder)     # "Nog een kaart met dezelfde songs" starts from it

    def _done(self, path: str) -> None:
        on_drive = path and (windows.is_drive_root(path) or os.path.dirname(os.path.normpath(path))
                             in [os.path.normpath(r) for r in self.volume_roots()])
        extra, self._done_extra = getattr(self, "_done_extra", ""), ""     # also kept in the library: its checks
        extra = "\n\n" + extra if extra else ""
        kept, self._kept_label = getattr(self, "_kept_label", ""), ""
        # a new card that is also kept in the library: an option to make the next SD card with the same songs
        other = {"other": self.t("btn_another_card")} if kept else {}
        again = False
        if not on_drive:                              # a copy in a folder: nothing to take out
            again = self.view.show_done(self.t("done") + extra, **other)
        elif self.eject(path):
            again = self.view.show_done(self.t("done_ejected") + extra, **other)
            # the card is out of the computer now: showing it would be a card that is no longer there
            # (the next click would fail), so back to the start screen
            if self.session is not None and not self.session.dirty and self.card_path == path:
                self.leave()
        else:                                           # still in use, or the system said no
            again = self.view.show_done(self.t("done_eject_yourself")
                                        + extra, **other)
        if again and kept:
            self.another_card(kept)

    def another_card(self, label: str) -> bool:
        """"Nog een kaart met dezelfde songs": a new card that starts as a copy of the card just kept in
        the library (the same as Nieuwe kaart samenstellen › Beginnen met <label>)."""
        if self.session is not None and not self.leave():
            return False
        base = next((c for c in (self.library.cards if self.library is not None else []) if c.label == label), None)
        if base is None:
            return False
        s = self._guard(cards.new_card_from, base.session)
        if s is FAIL:
            return False
        self._begin_compose(s)
        return True

    def start_archive(self, library: str, path: Optional[str] = None,
                      progress: Callable[[int, int, str], None] = None) -> Optional[str]:
        """Task 3: copy the card or the music diskette that is in the computer into the library.
        Returns the library folder (the last one, for a row of diskettes)."""
        if path is None:
            c = self._pick_card([cards.KN7000, cards.FLOPPY], "no_card_or_floppy")
            if c is None:
                return None
        else:
            c = cards.classify(path)
        if c.kind == cards.FLOPPY:
            made = self.archive_floppies(library, c)
            return made[-1] if made else None
        path, default = c.path, c.name
        st = self._guard(open_storage, path)
        if st is FAIL:
            return None
        match = self._guard(self._busy, "looking_in_library", lambda _p: cards.match_library(st, library), hold="card")
        if match is FAIL:
            return None
        chosen = self._copy_to_update(match)
        if chosen is None:
            return None
        name, replace = chosen
        if replace and not self.view.confirm(self.t("confirm_replace_copy", name=name)):
            return None                                 # replacing a copy is big: one more "are you sure?"
        if name is None:
            chosen = self._new_copy_name(library, "" if match else default)
            if chosen is None:
                return None
            name, replace = chosen
        check = verify.CopyCheck()
        folder = self._guard(self._busy, "archiving",
                             lambda p: cards.archive_card(st, library, name, replace, p or progress, self.backup_dir,
                                                          check), hold="card")
        if folder is FAIL:
            return None
        self.view.show_done(self.t("archived", name=os.path.basename(folder)) + "\n\n" + self.check_text(check))
        return folder

    def check_text(self, check: "verify.CopyCheck") -> str:
        """Every check of a copy into the library, one line each, so nothing is checked in silence. A
        problem is also said in its own message first (orange in the app: something to look at)."""
        lines = [self.t("chk_read", n=check.read_twice)]
        if check.song_files:
            lines.append(self.t("chk_unpacked", n=check.unpacked, sum=check.checksum)
                         if check.checksum else self.t("chk_unpacked_nosum", n=check.unpacked))
        lines.append(self.t("chk_read_back", n=check.read_back))
        problems = []
        if check.unstable:
            problems.append(self.t("chk_unstable", n=len(check.unstable), files="\n".join(check.unstable)))
        if check.not_unpacked:
            problems.append(self.t("chk_not_unpacked", n=len(check.not_unpacked), files="\n".join(check.not_unpacked)))
        if problems:
            self.view.show_error("\n\n".join(problems))
            lines += ["⚠ " + x.split("\n")[0] for x in problems]
        return "\n".join(lines)

    def _copy_to_update(self, match):
        """The library copy this card is an update of: (name, True), or (None, False) for a new copy;
        None when the user cancels. match: [(label, path, score)] from cards.match_library."""
        if len(match) == 1:
            a = self.view.ask(self.t("ask_update", name=match[0][0]), [self.t("btn_update"), self.t("btn_new_name")])
            if a is None:
                return None
            return (match[0][0], True) if a == 0 else (None, False)
        if match:                                       # more copies look like this card: let the user pick one
            options = [self.t("pick_copy_same" if score >= 1 else "pick_copy_almost", name=label,
                              pct=min(99, int(score * 100))) for label, _path, score in match]
            a = self.view.choose(self.t("ask_update_which", n=len(match)), options + [self.t("btn_new_name")])
            if a is None:
                return None
            if a < len(match):
                return match[a][0], True
        return None, False

    def _new_copy_name(self, library: str, default: str):
        """Ask the name for a new library copy: (name, replace an existing folder of that name), or None."""
        while True:
            name = self.view.ask_text(self.t("ask_label"), default)
            if name is None:
                return None
            name = name.strip()
            if name and os.path.exists(os.path.join(library, name)):
                if not self.view.confirm(self.t("confirm_overwrite_copy", name=name)):
                    continue
                return name, True
            return name, False

    FLOPPY_DIR = "Diskettes"         # diskettes go together in one part of the library

    def archive_floppies(self, library: str, first: Optional["cards.CardInfo"] = None) -> List[str]:
        """Keep music diskettes in the library, one after the other. After each one it is ejected and
        one screen says it is kept and waits for the next diskette (it goes on by itself once one is
        in), until the user clicks Klaar. Returns the library folders made."""
        made: List[str] = []
        c = first
        while c is not None:
            folder = self._archive_floppy(library, c)
            if folder is None:
                break
            made.append(folder)
            checks = self.check_text(self._last_check)
            if not self.is_drive(c.path):          # a folder (an unzipped download): nothing to eject
                self.view.show_done(self.t("floppy_kept", name=os.path.basename(folder), n=c.songs) + "\n\n" + checks)
                return made
            self.eject(c.path)
            c = self._next_floppy(self.t("floppy_next", k=len(made), name=os.path.basename(folder), n=c.songs,
                                         checks=checks))
        if made:
            self.view.show_done(self.t("floppies_done", n=len(made)))
        return made

    def _next_floppy(self, text: str) -> Optional["cards.CardInfo"]:
        """Wait for the next diskette: None when the user is done."""
        while True:
            self.waiting_for = (cards.FLOPPY,)          # the window goes on by itself once one is in
            try:
                a = self.view.ask(text, [self.t("btn_search_again"), self.t("btn_floppies_done")])
            finally:
                self.waiting_for = ()
            if a != 0:
                return None
            found = self._guard(self._busy, "looking_for_floppy", lambda _p: self.find_cards())
            floppies = [x for x in ([] if found is FAIL else found) if x.kind == cards.FLOPPY]
            if floppies:
                return floppies[0]
            text = self.t("no_floppy")

    def _archive_floppy(self, library: str, c: "cards.CardInfo") -> Optional[str]:
        """One diskette into library/Diskettes. Every diskette has the same name on the computer
        ("DISKETTE 2"), so the name is never a reason to replace: the same diskette is recognised by
        its files, and a name that is taken asks for another one."""
        from ..core import floppy
        where = os.path.join(library, self.FLOPPY_DIR)
        same = self._guard(lambda: floppy.find_copy(DirectoryStorage(c.path), where))
        if same is FAIL:
            return None
        replace = False
        if same:
            a = self.view.ask(self.t("floppy_known", name=os.path.basename(same)),
                              [self.t("btn_floppy_skip"), self.t("btn_floppy_again")])
            if a is None:
                return None
            if a == 0:
                self._last_check = verify.CopyCheck()
                return same
            name: Optional[str] = os.path.basename(same)
            replace = True
        else:
            name = None
        while name is None:
            name = self.view.ask_text(self.t("ask_floppy_label"), floppy.free_name(where, ""))
            if name is None:
                return None
            name = name.strip()
            if not name:
                name = None
            elif os.path.exists(os.path.join(where, name)):
                self.view.show_error(self.t("floppy_name_taken", name=name))
                name = None
        self._last_check = check = verify.CopyCheck()
        folder = self._guard(self._busy, "reading_floppy",
                             lambda p: floppy.archive_floppy(c.path, where, name, replace, p, check),
                             hold="floppy" if self.is_drive(c.path) else "")
        return None if folder is FAIL else folder

    # -------------------------------------------------------------- favourites and song lists
    def slot_label(self, slot: Slot) -> str:
        """"HET IS FEEST  ·  map 01, nr 2": the song first, then where it is."""
        x = self.session.db.song(slot[0] - 1, slot[1] - 1)
        return self.t("slot_label", name=x.name if x.used else self.t("empty"), f=slot[0], n=slot[1])

    def _show_lists(self) -> None:
        s = self.session
        banks = ["%02d  %s" % (i, b.name) for i, b in enumerate(s.db.favorites, 1)]
        items = []
        for v in s.db.favorites[self.bank - 1].items:
            d = s.db.favorites[0].decode_item(v)
            if d is None:
                items.append("")
            elif d[0] == "smf":
                items.append("SD-SOUND #%d" % (d[1] + 1))
            else:
                items.append(self.slot_label((d[1] + 1, d[2] + 1)))
        self.view.show_favorites(banks, self.bank, items)
        rows = [((f, so), self.slot_label((f, so))) for f, so in s.playlists()[self.list_no - 1]]
        self.view.show_song_list(self.list_no, rows)

    def select_bank(self, bank: int) -> None:
        self.bank = bank
        self._show_lists()

    def select_song_list(self, n: int) -> None:
        self.list_no = n
        self._show_lists()

    def rename_bank(self, name: str) -> bool:
        return self._guard(self.session.rename_favorite_bank, self.bank, name) is not FAIL

    def set_favorite(self, pos: int, slot: Optional[Slot]) -> bool:
        return self._guard(self.session.set_favorite, self.bank, pos, slot) is not FAIL

    def add_to_song_list(self, slots: Sequence[Slot], at: Optional[int] = None) -> bool:
        cur = self.session.playlists()[self.list_no - 1]
        at = len(cur) if at is None else max(0, min(at, len(cur)))
        new = cur[:at] + [tuple(x) for x in slots] + cur[at:]
        return self._guard(self.session.set_song_list, self.list_no, new) is not FAIL

    def remove_from_song_list(self, indexes: Sequence[int]) -> bool:
        cur = self.session.playlists()[self.list_no - 1]
        new = [x for i, x in enumerate(cur) if i not in set(indexes)]
        return self._guard(self.session.set_song_list, self.list_no, new) is not FAIL

    def move_in_song_list(self, src: int, dst: int) -> bool:
        cur = self.session.playlists()[self.list_no - 1]
        if not 0 <= src < len(cur):
            return False
        item = cur.pop(src)
        cur.insert(max(0, min(dst, len(cur))), item)
        return self._guard(self.session.set_song_list, self.list_no, cur) is not FAIL

    # -------------------------------------------------------------- second card
    def open_other(self, path: str) -> bool:
        o = self._guard(self._opener, path)
        if o is FAIL:
            return False
        self.other, self.other_path = o, path
        self.other_folder = next((f.folder for f in o.folders()), 1)
        self._show_other()
        return True

    def close_other(self) -> None:
        self.other = None
        self._show_other()

    def select_other_folder(self, folder: int) -> None:
        self.other_folder = folder
        self._show_other()

    def _show_other(self) -> None:
        o = self.other
        if o is None:
            self.view.show_other("", [], 0, [])
            return
        folders = [FolderRow(fi + 1, f.name, sum(1 for x in f.songs if x.used)) for fi, f in enumerate(o.db.folders)]
        songs = [SongRow(self.other_folder, si + 1, x.name if x.used else "", " ".join(x.extensions), x.used)
                 for si, x in enumerate(o.db.folders[self.other_folder - 1].songs)]
        self.view.show_other(o.storage.describe(), folders, self.other_folder, songs)

    def import_from_other(self, slots: Sequence[Slot], to_folder: int, to_song: Optional[int] = None) -> int:
        """Copy songs from the second card into this card (drag from the right-hand panel)."""
        n = 0
        for i, (f, so) in enumerate(slots):
            dst = to_song if (to_song is not None and i == 0) else None
            if self._guard(self.session.import_from, self.other, f, so, to_folder, dst) is FAIL:
                break
            n += 1
        if n:
            self._notify(self.t("copied", n=n, f=to_folder))
        return n

    # -------------------------------------------------------------- library (ADR-0007)
    def open_library(self, path: str, progress: Callable[[int, int, str], None] = None) -> bool:
        lib = self._guard(self._busy, "loading_library", lambda p: lb.Library.open(path, p or progress))
        if lib is FAIL:
            return False
        if self.library is not None:
            self.library.close()
        self.library, self.library_path, self._detail_pos = lib, path, 0
        self.lib_filter = {}
        self.show_library()
        later = getattr(self.view, "fill_library_details_later", None)
        if later:                                       # tempo and time signature: read in the background
            later()
        msg = self.t("lib_opened", cards=len(lib.cards), songs=len(lib.songs))
        if lib.problems:
            msg += " " + self.t("lib_skipped", names=", ".join(p.path for p in lib.problems))
        self.view.show_status(msg)
        return True

    def library_title(self) -> str:
        lib = self.library
        if lib is None:
            return self.t("lib_none")
        return self.t("lib_title", name=os.path.basename(lib.root.rstrip("/\\")) or lib.root,
                      cards=len(lib.cards), songs=len(lib.songs))

    def library_rows(self) -> List[LibraryRow]:
        lib = self.library
        if lib is None:
            return []
        f = self.lib_filter
        index = {id(x): i for i, x in enumerate(lib.songs)}
        rows = []
        found = lib.search(f.get("text", ""), f.get("card"), f.get("recorded"), f.get("tempo_min"), f.get("tempo_max"),
                           f.get("meter"), f.get("spread"), f.get("source"), f.get("damaged"))
        if f.get("not_on_card") and self.session is not None:
            mine = self._card_fingerprints()
            found = [x for x in found if lib.fingerprint(x) not in mine]
        card = self._lib_card(f.get("card"))
        slots: Dict[int, str] = {}
        if card is not None and f.get("part"):
            found, slots = self._in_part_order(lib, card, f["part"], found)
        names: Dict[str, int] = {}
        same_name: Dict[str, List[lb.LibrarySong]] = {}
        for x in lib.songs:                             # same name, different song: "AVONDWALS · 2 versies"
            names[x.name] = names.get(x.name, 0) + 1
            same_name.setdefault(x.name, []).append(x)
        for x in found:
            unknown = "" if x.checked else "…"          # still being read
            rows.append(LibraryRow(index[id(x)], self._library_label(x, names, f.get("text", "")),
                                   str(x.tempo) if x.tempo else unknown,
                                   self.t("yes") if x.recorded else unknown,
                                   self._where_text(x), self._where_tip(x, same_name[x.name]), " ".join(x.extensions),
                                   x.meter or unknown, slots.get(id(x), ""), tuple(x.titles), tuple(x.damaged)))
        return rows

    @staticmethod
    def _in_part_order(lib, card, part, found):
        """The songs found that are in one folder or song list of the chosen card, in its order, and
        their numbers there ({id(song): "03"} for a folder place, "3" for a list position)."""
        keep = {id(x) for x in found}
        by_slot = {(c.folder, c.song): x for x in lib.songs for c in x.copies if c.card is card}
        if part[0] == "list":
            order = card.session.playlists()[part[1] - 1]
        else:
            order = [(part[1], si + 1) for si, x in enumerate(card.session.db.folders[part[1] - 1].songs) if x.used]
        numbered = [(sl, by_slot[sl]) for sl in order if sl in by_slot and id(by_slot[sl]) in keep]
        return ([x for _, x in numbered],
                {id(x): ("%02d" % sl[1] if part[0] == "folder" else str(i)) for i, (sl, x) in enumerate(numbered, 1)})

    def _where_tip(self, x: "lb.LibrarySong", same: List["lb.LibrarySong"]) -> str:
        """Where this song is, and where the other versions with the same name are (tooltip)."""
        tip = "\n".join(c.where for c in x.copies)
        others = [c.where for o in same if o is not x for c in o.copies]
        if others:
            tip += "\n\n" + self.t("lib_other_versions", n=len(others)) + "\n" + "\n".join(others)
        return tip

    def _library_label(self, x, names: Dict[str, int], text: str) -> str:
        label = x.name or self.t("noname")
        if names.get(x.name, 0) > 1:
            label = self.t("versions", name=label, n=names[x.name])
        hits = x.matching_titles(text) if text.strip().upper() not in x.name.upper() else []
        if hits:                                        # found inside a diskette set: say which song
            return self.t("lib_found_inside", name=label, titles=", ".join(hits))
        if x.titles:
            return self.t("lib_set_n", name=label, n=len(x.titles))
        return label

    def _where_text(self, song: "lb.LibrarySong") -> str:
        """'Kaart bruiloften (map 3)': where the physical card is, and the folder to look in."""
        parts: List[str] = []
        for label in song.cards:
            folders = sorted({c.folder for c in song.copies if c.card.label == label})
            parts.append(self.t("on_card", card=label, folders=", ".join(str(f) for f in folders)))
        return "; ".join(parts)

    def show_library(self) -> None:
        cards = [c.label for c in self.library.cards] if self.library else []
        self.view.show_library(self.library_title(), cards, self.library_rows())

    def set_library_filter(self, text: str = "", card: Optional[str] = None, recorded: Optional[bool] = None,
                           tempo_min: Optional[int] = None, tempo_max: Optional[int] = None,
                           part: Optional[Tuple[str, int]] = None, meter: Optional[str] = None,
                           spread: Optional[str] = None, source: Optional[str] = None,
                           damaged: Optional[bool] = None, not_on_card: bool = False) -> None:
        """part ("folder", n) or ("list", n) shows that folder or song list of the chosen card, in order.
        meter: a time signature; spread "one"/"more": on one kept card only / on more than one; source
        "card"/"floppy"; damaged: only the orange songs; not_on_card: hide what is on the open card already."""
        self.lib_filter = {"text": text, "card": card or None, "recorded": recorded,
                           "tempo_min": tempo_min, "tempo_max": tempo_max, "part": part if card else None,
                           "meter": meter, "spread": spread, "source": source, "damaged": damaged,
                           "not_on_card": not_on_card}
        self.show_library()

    def library_meters(self) -> List[str]:
        """The time signatures known so far in the library (they are read in the background)."""
        found = {x.meter for x in self.library.songs if x.meter} if self.library else set()
        return sorted(found, key=lambda m: (int(m.split("/")[1]), int(m.split("/")[0])) if "/" in m else (99, 0))

    def _card_fingerprints(self) -> set:
        """The songs on the open card (with its changes) as Library.fingerprint sees them. Each file is
        read once: it is remembered by where it is read from."""
        plan, out = self.session.planned(), set()
        cache = self._file_digests
        for fi, si, song in self.session.db.iter_songs():
            h = hashlib.sha1()
            try:
                for ext, p in sorted(layout.song_paths(fi, si, song).items()):
                    w = plan._where(p)
                    key = (id(w[0]), w[1].upper(), w[0].size(w[1])) if w else None
                    if key not in cache:
                        cache[key] = lb.file_digest(w[0].read(w[1]) if w else b"")
                    h.update(ext.encode())
                    h.update(cache[key])
            except (OSError, KeyError):
                continue
            out.add(h.hexdigest())
        return out

    def _lib_card(self, label: Optional[str]):
        if self.library is None or not label:
            return None
        return next((c for c in self.library.cards if c.label == label), None)

    def library_parts(self, card: Optional[str]) -> List[Tuple[Tuple[str, int], str]]:
        """The folders and song lists of one library card that hold songs: (key, label)."""
        c = self._lib_card(card)
        if c is None:
            return []
        out = []
        for fi, fo in enumerate(c.session.db.folders):
            n = sum(1 for x in fo.songs if x.used)
            if n:
                out.append((("folder", fi + 1), self.t("lib_folder_n", n=fi + 1, name=fo.name or self.t("noname"), count=n)))
        for n, pl in enumerate(c.session.playlists(), 1):
            if pl:
                out.append((("list", n), self.t("lib_list_n", n=n, count=len(pl))))
        return out

    def copy_library_part(self, card: str, part: Tuple[str, int]) -> bool:
        """Copy a whole folder or song list of a library card onto the open card, in one undo step.
        Everything is copied (duplicates are fine: a folder is often used as a set list)."""
        if part[0] == "folder":
            return self.copy_library_folder(card, part[1])
        return self.copy_library_list(card, part[1])

    def copy_library_folder(self, card: str, folder: int) -> bool:
        c, s = self._lib_card(card), self.session
        if c is None or s is None or not self._space_for(c.session, [(folder, si + 1) for si, x in
                                                                    enumerate(c.session.db.folders[folder - 1].songs) if x.used]):
            return False
        r = self._guard(s.import_folder, c.session, folder)
        if r is FAIL:
            return False
        self.folder = r["folder"]
        self.refresh()
        self._notify(self.t("folder_copied", n=folder, to=r["folder"], copied=r["copied"]))
        return True

    def copy_library_folders(self, card: str, folders: Sequence[int], start: Optional[int] = None) -> bool:
        """Copy several whole folders of a library card onto the open card at once, in one undo step:
        each into an empty folder, from `start` on when that one is empty (a drop on it)."""
        folders = list(dict.fromkeys(folders))
        if len(folders) == 1 and start is None:
            return self.copy_library_folder(card, folders[0])
        c, s = self._lib_card(card), self.session
        if c is None or s is None or not folders:
            return False
        slots = [(f, si + 1) for f in folders for si, x in enumerate(c.session.db.folders[f - 1].songs) if x.used]
        if not self._space_for(c.session, slots):
            return False
        r = self._guard(s.import_folders, c.session, folders, start)
        if r is FAIL:
            return False
        self.folder = r[0]["folder"]
        self.refresh()
        if hasattr(self.view, "select_folders"):
            self.view.select_folders([x["folder"] for x in r])
        if len(r) == 1:
            self._notify(self.t("folder_copied", n=r[0]["from"], to=r[0]["folder"], copied=r[0]["copied"]))
        else:
            self._notify(self.t("folders_copied", n=len(r), songs=sum(x["copied"] for x in r),
                                to=", ".join(str(x["folder"]) for x in r)))
        return True

    def _free_text(self, storage, free: int) -> str:
        """'893.0 MB vrij van 1.0 GB' (· schrijfbeveiligd)."""
        total = getattr(storage, "total_bytes", lambda: None)()
        key = ("free_of" if total else "free") + ("" if storage.writable() else "_ro")
        return self.t(key, size=size_text(free), total=size_text(total or 0))

    def _space_for(self, source: CardSession, slots) -> bool:
        free = self.session.storage.free_bytes()
        if free is None:
            return True
        size = 0
        for f, so in slots:
            for p in source.song(f, so).files:
                size += source.storage.size(p) if source.storage.exists(p) else 0
        need = self.session.bytes_needed() + size + 2 * 0xD620
        if need > free:
            self.view.show_error(self.t("no_space", need=size_text(need), free=size_text(free)))
            return False
        return True

    def copy_library_list(self, card: str, list_no: int) -> bool:
        """Copy a whole song list: all its songs into an empty folder, in order, plus a song list."""
        c, s = self._lib_card(card), self.session
        if c is None or s is None or not self._space_for(c.session, c.session.playlists()[list_no - 1]):
            return False
        to_list = None
        if all(s.playlists()):
            options = [self.t("replace_list", n=n, count=len(pl)) for n, pl in enumerate(s.playlists(), 1)]
            pick = self.view.choose(self.t("all_lists_used"), options)
            if pick is None:
                return False
            to_list = pick + 1
        name = "".join(ch for ch in os.path.basename(card).upper() if " " <= ch <= "~")[:16].strip() or None
        r = self._guard(s.import_song_list, c.session, list_no, to_list, None, name)
        if r is FAIL:
            return False
        self.folder = r["folder"] or self.folder
        self.refresh()
        self._notify(self.t("list_copied", n=list_no, to=r["list"], copied=r["copied"], reused=r["reused"]))
        return True

    def remove_library_card(self, label: str) -> bool:
        """Take one card (or diskette) out of the library: its folder goes to the bin, after asking.
        Only on request and never for good: it can be put back from the Trash / Recycle Bin.
        The card itself and its backups are not touched."""
        path = self._library_card_path(label)           # only something inside the library
        lib = self.library
        if path is None or lib is None:
            return False
        if self._draft_uses(path):
            self.view.show_error(self.t("lib_card_in_use", name=label))
            return False
        bin_key = "bin"                                # "Prullenbak", on Windows its own name (i18n.tr)
        if not self.view.confirm(self.t("confirm_lib_remove", name=label, bin=self.t(bin_key))):
            return False
        lib.close()                                     # a card image must not be open while it moves
        if not trash.move_to_trash(path):
            self.view.show_error(self.t("lib_remove_failed", name=label, bin=self.t(bin_key)))
            self.open_library(self.library_path)
            return False
        self.open_library(self.library_path)
        self.view.show_status(self.t("lib_removed", name=label, bin=self.t(bin_key)))
        return True

    def _draft_uses(self, path: str) -> bool:
        """The card being made still has to copy songs from this library card when it is saved."""
        if self.session is None:
            return False
        path = os.path.normcase(os.path.abspath(path))
        for op in self.session.pending:
            st = op.src_storage
            where = getattr(st, "root", None) or getattr(st, "path", None)
            if op.kind == "import" and where:
                w = os.path.normcase(os.path.abspath(where))
                if w == path or w.startswith(path + os.sep):
                    return True
        return False

    def _library_card_path(self, label: str) -> Optional[str]:
        """The path of a library card, only when it really lies inside the library."""
        c, lib = self._lib_card(label), self.library
        if c is None or lib is None:
            return None
        root = os.path.normcase(os.path.abspath(lib.root))
        path = os.path.abspath(c.path)
        if os.path.normcase(path) == root or not os.path.normcase(path).startswith(root + os.sep):
            return None
        return path

    def rename_library_card(self, label: str) -> bool:
        """Give a card (or diskette) in the library another name: its folder is renamed in place."""
        path = self._library_card_path(label)
        if path is None:
            return False
        if self._draft_uses(path):
            self.view.show_error(self.t("lib_card_in_use", name=label))
            return False
        old = os.path.basename(path)
        is_file = os.path.isfile(path)
        stem, ext = os.path.splitext(old) if is_file else (old, "")
        typed = self.view.ask_text(self.t("ask_lib_rename", name=label), stem)
        if typed is None or not typed.strip() or typed.strip() == stem:
            return False
        try:
            new = cards.safe_name(typed.strip()) + ext
        except KN7Error as e:
            self.view.show_error(self.error_text(e))
            return False
        target = os.path.join(os.path.dirname(path), new)
        if os.path.exists(target) and os.path.normcase(target) != os.path.normcase(path):
            self.view.show_error(self.t("lib_name_taken", name=new))
            return False
        self.library.close()
        try:
            os.rename(path, target)
        except OSError as e:
            self.view.show_error(self.t("lib_rename_failed", name=label, error=str(e)))
            self.open_library(self.library_path)
            return False
        new_label = os.path.relpath(target, self.library.root).replace(os.sep, "/")
        before = dict(self.lib_filter)                   # what was shown stays shown, under its new name
        self.open_library(self.library_path)
        if before:
            if before.get("card") == label:
                before["card"] = new_label
            self.set_library_filter(**before)
        self.view.show_status(self.t("lib_renamed", old=label, new=new_label))
        return True

    def fill_library_details(self, batch: int = 40) -> bool:
        """Read tempo and recording for the next batch of songs. Returns True while there is more to do;
        the view calls it from an idle timer so the list is usable at once."""
        lib = self.library
        if lib is None:
            return False
        end = min(self._detail_pos + batch, len(lib.songs))
        for s in lib.songs[self._detail_pos:end]:
            lib.details(s)
        self._detail_pos = end
        if end >= len(lib.songs):
            self.show_library()
            self.view.show_status(self.t("lib_details_done", n=len(lib.songs)))
            return False
        self.view.show_status(self.t("lib_details", i=end, n=len(lib.songs)))
        return True

    def import_from_library(self, indices: Sequence[int], to_folder: int, to_song: Optional[int] = None) -> int:
        """Put library songs on the open card (drag from the library onto a folder or slot)."""
        lib, s = self.library, self.session
        if lib is None or s is None:
            return 0
        songs = [lib.songs[i] for i in indices if 0 <= i < len(lib.songs)]
        damaged = [x for x in songs if lib.details(x).damaged]
        if damaged and not self.view.confirm(self.t("confirm_damaged", n=len(damaged), songs="\n".join(
                "%s (%s)" % (x.name, ", ".join(x.damaged)) for x in damaged))):
            return 0
        free = s.storage.free_bytes()
        if free is not None:
            need = s.bytes_needed() + sum(x.size for x in songs) + 2 * 0xD620
            if need > free:
                self.view.show_error(self.t("no_space", need=size_text(need), free=size_text(free)))
                return 0
        n = 0
        for i, x in enumerate(songs):
            dst = to_song if (to_song is not None and i == 0) else None
            if self._guard(lb.copy_into, s, x, to_folder, dst) is FAIL:
                break
            n += 1
        if n:
            self._notify(self.t("copied", n=n, f=to_folder))
        return n

    def new_card(self, path: str) -> bool:
        """Start a card in an empty folder (or on an empty SD card). An existing card is just opened."""
        if not path:
            return False
        if os.path.isdir(path) and DirectoryStorage(path).exists("PRIVATE/TECHNICS/KN7000/KN7000MN.INF"):
            return self.open_card(path)
        if not self.view.confirm(self.t("confirm_new_card", path=path)):
            return False
        if self._guard(CardSession.create, DirectoryStorage(path)) is FAIL:
            return False
        return self.open_card(path)

    def song_rows(self) -> List[SongRow]:
        s = self.session
        if s is None:
            return []
        if self.query:
            return [SongRow(v.folder, v.song, v.name, " ".join(v.types), True) for v in s.search(self.query)]
        return [SongRow(self.folder, si + 1, x.name if x.used else "", " ".join(x.extensions), x.used)
                for si, x in enumerate(s.db.folders[self.folder - 1].songs)]

    # -------------------------------------------------------------- opening and navigation
    def open_card(self, path: str) -> bool:
        if self._is_library(path):          # a common mix-up: the library folder chosen instead of a card
            if self.view.ask(self.t("is_library", path=path), [self.t("btn_use_library")]) == 0:
                opener = getattr(type(self.view), "open_library", None)       # the window also remembers it
                if (opener(self.view, path) if opener else self.open_library(path)):
                    self.view.show_done(self.t("library_chosen"))
            return False
        s = self._guard(self._opener, path)
        if s is FAIL:
            return False
        self.session, self.card_path, self.query = s, path, ""
        self.folder = next((f.folder for f in s.folders()), 1)
        s.on_change(self.refresh)
        self.refresh()
        self.view.show_status(self.t("opened_bak" if s.loaded_from == layout.BAK_PATH else "opened",
                                     n=sum(f.used for f in s.folders())))
        if not self._checking:
            self._checking = True
            try:
                self.offer_card_check()
            finally:
                self._checking = False
        return True

    @staticmethod
    def _is_library(path: str) -> bool:
        """A folder that is not a card itself but holds kept cards (a library, or its Diskettes folder)."""
        return os.path.isdir(path) and not lb._is_card_dir(path) and bool(lb.find_cards(path))

    def offer_card_check(self) -> None:
        """Right after opening, three checks, each only a notice with a choice (nothing by itself):
        a save that did not finish, song files that are missing, and files no song uses."""
        s = self.session
        if s is None or self.composing or not s.storage.writable():
            return
        job = s.unfinished_save()
        if job is not None:
            zip_path = job["backup"] if job["backup"] and os.path.exists(job["backup"]) else ""
            buttons = ([self.t("btn_job_restore")] if zip_path else []) + [self.t("btn_job_repair"),
                                                                           self.t("btn_later")]
            when = self.when_text(job["started"]) if job["started"] else "?"
            a = self.view.ask(self.t("job_found", when=when), buttons)
            if a is not None and zip_path and a == 0:
                if self.restore(zip_path):
                    self.session.forget_unfinished_save()
                return
            if a is not None and a == len(buttons) - 2:
                self.session.forget_unfinished_save()       # repair rebuilds from what is on the card
                self.repair()
            return
        missing = s.check_songs()
        if missing:
            if self.view.ask(self.t("missing_found", n=len(missing), example="/".join(missing[0].split("/")[-2:])),
                             [self.t("btn_job_repair"), self.t("btn_later")]) == 0:
                self.repair()
            return
        self.offer_stray_cleanup()

    def offer_stray_cleanup(self) -> None:
        """Files in the folders that no song uses: say so, and clean up only if the user wants
        (as a planned, undoable step). Nothing is removed by itself."""
        s = self.session
        if s is None or self.composing or not s.storage.writable():
            return
        stray = s.stray_files()
        if not stray:
            return
        example = "/".join(stray[0].split("/")[-2:])
        if self.view.ask(self.t("stray_found", n=len(stray), example=example),
                         [self.t("btn_stray_fix"), self.t("btn_stray_keep")]) == 0:
            s.remove_stray_files(stray)
            self.view.show_status(self.t("stray_planned", n=len(stray)))

    def select_folder(self, folder: int) -> None:
        self.folder, self.query = folder, ""
        self.view.show_songs(self.song_rows(), False)

    def set_search(self, text: str) -> None:
        self.query = text.strip()
        rows = self.song_rows()
        self.view.show_songs(rows, bool(self.query))
        if self.query:
            self.view.show_status(self.t("hits", n=len(rows), q=self.query))

    def set_language(self, lang: str) -> None:
        self.lang = lang
        self.view.retranslate()
        self.refresh()

    # -------------------------------------------------------------- edits
    def rename_song(self, folder: int, song: int, name: str) -> bool:
        if self._guard(self.session.rename_song, folder, song, name) is FAIL:
            self.refresh()          # put the old text back in an inline editor
            return False
        return True

    def rename_folder(self, folder: int, name: str) -> bool:
        if self._guard(self.session.rename_folder, folder, name) is FAIL:
            self.refresh()
            return False
        return True

    def folder_choices(self, exclude: int = 0) -> List[Tuple[int, List[str]]]:
        """Folders to offer in "Verplaatsen naar…" / "Kopiëren naar…": the ones in use (name or songs),
        as table cells (number, name, songs, free places). A full folder is left out.
        (0, ["", "+ Nieuwe map…", "", ""]) at the end makes a new one."""
        s = self.session
        out: List[Tuple[int, List[str]]] = []
        for fi, f in enumerate(s.db.folders):
            n = sum(1 for x in f.songs if x.used)
            if fi + 1 == exclude or not (f.name or n) or n >= len(f.songs):
                continue
            out.append((fi + 1, ["%02d" % (fi + 1), f.name or self.t("noname"), str(n), str(len(f.songs) - n)]))
        out.append((0, ["", self.t("pick_new_folder"), "", ""]))
        return out

    def new_folder(self, name: str) -> Optional[int]:
        """Give the first unused folder (no name, no songs) a name and show it. Returns its number."""
        s = self.session
        if s is None:
            return None
        free = next((fi + 1 for fi, f in enumerate(s.db.folders) if not f.name and not any(x.used for x in f.songs)), None)
        if free is None:
            self.view.show_error(self.t("no_free_folder"))
            return None
        if self._guard(s.rename_folder, free, name) is FAIL:
            return None
        self.folder, self.query = free, ""
        self.refresh()
        return free

    def delete_songs(self, slots: Sequence[Slot], confirm: bool = False) -> int:
        slots = [x for x in slots if self.session.db.song(x[0] - 1, x[1] - 1).used]
        if not slots or (confirm and not self.view.confirm(self.t("confirm_delete", n=len(slots)))):
            return 0
        n = sum(1 for f, s in slots if self._guard(self.session.delete_song, f, s) is not FAIL)
        self._notify(self.t("deleted", n=n))
        return n

    def delete_folders(self, folders: Sequence[int], confirm: bool = True) -> int:
        """Weghalen with folders chosen: their songs go and the folders lose their names, so they are
        empty again (as on a new card). One question, one undo step. Gives the number of songs."""
        if self.session is None or not folders:
            return 0
        db = self.session.db
        folders = sorted(set(folders))
        songs = sum(1 for f in folders for x in db.folders[f - 1].songs if x.used)
        if not songs and not any(db.folders[f - 1].name for f in folders):
            return 0
        names = ", ".join("%02d" % f for f in folders)
        if len(folders) > 6:
            names = "%02d … %02d" % (folders[0], folders[-1])
        if confirm and not self.view.confirm(self.t("confirm_delete_folders", n=len(folders), folders=names,
                                                    songs=songs)):
            return 0
        n = self._guard(self.session.delete_folders, folders)
        if n is FAIL:
            return 0
        self._notify(self.t("deleted_folders", n=len(folders), songs=n))
        return n

    def move_songs(self, slots: Sequence[Slot], to_folder: int, copy: bool = False) -> int:
        """Move/copy songs to the first free slots of a folder (drag onto a folder). Stops at the
        first error (e.g. the folder is full); what was done so far stays and can be undone."""
        n, landed = 0, []
        for f, s in slots:
            if f == to_folder and not copy:
                continue
            dst = self._guard(self.session.move_song, f, s, to_folder, None, copy)
            if dst is FAIL:
                break
            landed.append((to_folder, dst))
            n += 1
        if n:
            self._notify(self.t("copied" if copy else "moved", n=n, f=to_folder))
        if hasattr(self.view, "select_slots") and not self.query:
            # what is chosen afterwards are the songs themselves: where they landed when that folder is
            # shown (a new folder is), else nothing (they moved away) or still the originals (a copy)
            if self.folder == to_folder:
                self.view.select_slots(landed)
            elif not copy:
                self.view.select_slots([])
        return n

    def reorder_songs(self, slots: Sequence[Slot], dst: Slot) -> bool:
        """Drag several songs of one folder to another place in it: they move there as a block, in
        their order; the songs in between shift up or down (like the keyboard's own song order)."""
        if self.session is None or not slots or any(f != dst[0] for f, _ in slots):
            return False
        new = self._guard(self.session.reorder_songs, dst[0], [s for _, s in slots], dst[1])
        if new is FAIL:
            return False
        if hasattr(self.view, "select_slots"):
            self.view.select_slots([(dst[0], n) for n in new])
        self._notify(self.t("reordered", n=len(new), f=dst[0], a=min(new), b=max(new)))
        return True

    def move_folder(self, folder: int, to_folder: int) -> bool:
        """Drag a folder onto another number: it moves there; a folder in use there swaps places."""
        if folder == to_folder or self.session is None:
            return False
        swap = bool(self.session.db.folders[to_folder - 1].name) or any(
            x.used for x in self.session.db.folders[to_folder - 1].songs)
        old = self.folder
        self.folder, self.query = to_folder, ""
        if self._guard(self.session.move_folder, folder, to_folder) is FAIL:
            self.folder = old
            return False
        self._notify(self.t("folders_swapped" if swap else "folder_moved", a=folder, b=to_folder))
        return True

    def insert_folder(self, folder: int, before: int) -> bool:
        """Drop a folder on the line between two others: it lands there and the folders in between
        shift one place (before = the folder it goes in front of, 100 = after the last)."""
        if self.session is None:
            return False
        new = before - 1 if folder < before else before
        if new == folder:
            return False
        old = self.folder
        self.folder, self.query = new, ""
        if self._guard(self.session.insert_folder, folder, before) is FAIL:
            self.folder = old
            return False
        self._notify(self.t("folder_inserted", a=folder, b=new))
        return True

    def insert_folders(self, folders: Sequence[int], before: int) -> bool:
        """Drop several chosen folders on the line between two others: they land there together, in
        their order, and the other folders shift around them (one folder: insert_folder)."""
        folders = sorted(set(folders))
        if len(folders) == 1:
            return self.insert_folder(folders[0], before)
        if self.session is None or not folders:
            return False
        landed = self._guard(self.session.insert_folders, folders, before)
        if landed is FAIL:
            return False
        if landed == folders:                              # dropped where they already are
            return False
        self.folder, self.query = landed[0], ""
        self.refresh()
        if hasattr(self.view, "select_folders"):
            self.view.select_folders(landed)
        self._notify(self.t("folders_inserted", n=len(landed), a=landed[0], b=landed[-1]))
        return True

    def drop_on_slot(self, src: Slot, dst: Slot) -> None:
        """Drag one song onto a slot: an empty slot receives it; in the same folder an occupied
        slot swaps places (reordering); in another folder it goes to the first free slot."""
        if src == dst:
            return
        target_used = self.session.db.song(dst[0] - 1, dst[1] - 1).used
        if src[0] == dst[0] and target_used:
            self._guard(self.session.swap_songs, src[0], src[1], dst[1])
        elif not target_used:
            self._guard(self.session.move_song, src[0], src[1], dst[0], dst[1])
        else:
            self._guard(self.session.move_song, src[0], src[1], dst[0], None)

    def undo(self) -> None:
        label = self._guard(self.session.undo)
        if label is not FAIL:
            self.view.show_status(self.t("undone", what=self.step_text(label)))

    def redo(self) -> None:
        label = self._guard(self.session.redo)
        if label is not FAIL:
            self.view.show_status(self.t("redone", what=self.step_text(label)))

    def undo_to(self, n_done: int) -> None:
        """Click in the history list: undo or redo until n_done commands are applied."""
        while len(self.session.history()) > n_done:
            self.session.undo()
        while len(self.session.history()) < n_done and self.session.can_redo:
            self.session.redo()

    # -------------------------------------------------------------- saving and safety
    def save(self, progress: Callable[[int, int, str], None] = None) -> bool:
        steps = ["space"] + (["backup"] if self.backups else []) + ["write", "verify"]

        def run(p):
            phase = self._phase(p, steps)
            phase("space")
            self.session.preflight()
            phase("backup")
            zip_path = (backup.make_backup(self.session.storage, self.backup_dir, progress=p)
                        if self.backups else None)
            return self.session.save(progress=p or progress, backup_zip=zip_path or "", phase=phase), zip_path
        res = self._guard(self._busy, "saving", run, steps, "card")
        if res is FAIL:
            return False
        n, zip_path = res
        s = self.session
        text = (self.t("saved_backup", n=n, zip=zip_path, checked=s.verified) if zip_path
                else self.t("saved", n=n, checked=s.verified))
        text += " " + self.t("card_checked", songs=s.checked_songs)
        self.view.show_status(text)
        if s.missing_after:             # not caused by this save (its own files were checked above)
            self.view.show_error(self.t("missing_after", n=len(s.missing_after),
                                        example="/".join(s.missing_after[0].split("/")[-2:])))
        return True

    def check(self) -> List[str]:
        if self.composing:              # its songs are still in the library, not on a card: nothing to check
            return []
        issues = self._guard(self.session.validate)
        issues = [] if issues is FAIL else issues
        self.view.show_status(self.t("issues", n=len(issues)))
        return [self.issue_text(i) for i in issues]

    def issue_text(self, i) -> str:
        """One thing wrong on the card, in the user's words, with where it is."""
        key = "issue." + getattr(i.message, "key", "")
        what = self.t(key, **i.message.values) if has_key(key) else str(i.message)
        if i.folder is None:
            return what
        where = self.t("issue_at_song", folder=i.folder, song=i.song) if i.song else self.t("issue_at_folder", folder=i.folder)
        return "%s: %s" % (where, what)

    def repair(self) -> bool:
        if self.composing:              # rebuilding from the files would empty a card that is not written yet
            return False
        if self.session.dirty:
            self.view.show_error(self.t("unsaved_first"))
            return False
        res = self._guard(self._busy, "reading_card", lambda _p: repair.rebuild(self.session.storage), hold="card")
        if res is FAIL:
            return False
        db, rep = res
        if rep.nothing_to_do:
            self.view.show_status(self.t("repair_none"))
            return False
        if not self.view.confirm(self.t("confirm_repair", a=len(rep.added), r=len(rep.removed), c=len(rep.changed))):
            return False
        st = self.session.storage

        steps = ["space"] + (["backup"] if self.backups else []) + ["write_index", "verify"]

        def run(p):
            phase = self._phase(p, steps)
            phase("space")
            fixed = CardSession(st, db, "repair")
            fixed.preflight()
            if self.backups:
                phase("backup")
                backup.make_backup(st, self.backup_dir, progress=p)
            fixed.save(phase=lambda k: phase("write_index" if k == "write" else k))
        if self._guard(self._busy, "saving", run, steps, "card") is FAIL:
            return False
        self.open_card(self.card_path)
        self.view.show_status(self.t("repaired"))
        return True

    # -------------------------------------------------------------- duplicates
    def find_duplicates(self) -> Optional[List[DuplicateRow]]:
        """Songs stored more than once. Works on the card as saved, so changes must be saved first."""
        if self.session.dirty:
            self.view.show_error(self.t("unsaved_first"))
            return None
        groups = self._guard(self._busy, "reading_card", lambda _p: duplicates.find_duplicates(self.session))
        if groups is FAIL:
            return None
        rows = []
        for g in groups:
            labels = tuple("%02d/%02d  %s" % (f, so, self.session.db.folders[f - 1].name or self.t("noname"))
                           for f, so in g.slots)
            rows.append(DuplicateRow(g.kind == "identical", g.name, tuple(g.slots), labels,
                                     size_text(g.saving) if g.kind == "identical" else ""))
        n = sum(len(r.slots) - 1 for r in rows if r.identical)
        self.view.show_status(self.t("dups_found", n=n) if n else self.t("dups_none"))
        return rows

    def merge_duplicates(self, keep: Slot, copies: Sequence[Slot], song_list: Optional[int] = None) -> bool:
        """Keep one copy, delete the others (after saving), point favourites and song lists at it."""
        others = [c for c in copies if tuple(c) != tuple(keep)]
        if not others:
            return False
        if not self.view.confirm(self.t("confirm_merge", n=len(others), keep="%02d/%02d" % tuple(keep))):
            return False
        if self._guard(self.session.merge_duplicates, keep, others, song_list) is FAIL:
            return False
        self._notify(self.t("merged", n=len(others), keep="%02d/%02d" % tuple(keep)))
        return True

    def backup_rows(self) -> List[BackupRow]:
        """Back-ups of every card, the open card's first, then the others newest first. Two cards with
        the same name (NO NAME) are told apart by their songs, not by the name."""
        mine = None
        if self.session is not None and not self.composing:
            mine = backup.card_song_names(self.session.storage)
        groups: Dict[Tuple[str, bool], List[BackupRow]] = {}
        for b in backup.list_all(self.backup_dir):
            same = mine is not None and not b.library and backup.similarity(mine, backup.song_names(b.path)) >= backup.SAME_CARD
            key = "backup_group_library" if b.library else "backup_group_this" if same else "backup_group"
            row = BackupRow(b.path, self.t("backup_row", when=self.when_text(b.created),
                                           songs=b.songs if b.songs >= 0 else "?"),
                            self.t(key, name=b.card_name), same, b.library)
            groups.setdefault((b.label, same), []).append(row)
        ordered = sorted(groups.values(), key=lambda rows: (not rows[0].this_card, rows[0].library))
        return [r for rows in ordered for r in rows]

    def backup_contents(self, zip_path: str) -> List[Tuple[str, List[str]]]:
        """("01  FEEST  (4)", song names) for every folder with songs in the back-up."""
        try:
            folders = backup.contents(zip_path)
        except (KeyError, OSError, KN7Error, ValueError, zipfile.BadZipFile):
            return []
        return [(self.t("lib_folder_n", n=n, name=name or self.t("noname"), count=len(songs)), songs)
                for n, name, songs in folders]

    def copy_library(self, target: Optional[str] = None) -> Optional[str]:
        """"Kopie van de bibliotheek maken": the whole library onto a USB stick or an external disk
        (core/library_copy.py). A second time to the same place only copies what changed."""
        from ..core import library_copy
        root = self.library_path if self.library is not None else ""
        if not root:
            self.view.show_error(self.t("copy_no_library"))
            return None
        if target is None:
            target = self.view.pick_folder(self.t("copy_pick"))
            if not target:
                return None
        rep = self._guard(self._busy, "copying_library", lambda p: library_copy.copy_library(root, target, p), hold="stick")
        if rep is FAIL:
            return None
        def files(n: int) -> str:
            return self.t("count_file") if n == 1 else self.t("count_files", n=n)

        lines = [self.t("copy_new", n=files(rep.copied), size=size_text(rep.size)) if rep.copied else "",
                 self.t("copy_same", n=files(rep.same)) if rep.same else "",
                 self.t("copy_extra", n=files(len(rep.extra)), example=rep.extra[0]) if rep.extra else ""]
        self.view.show_done(self.t("copy_done", path=rep.folder) + "\n\n" + self.t("copy_checks")
                            + "\n" + "\n".join(x for x in lines if x))
        return rep.folder

    def make_backup_now(self) -> Optional[str]:
        """"Nu een back-up maken" for the open card."""
        if self.session is None or self.composing:
            return None
        st = self.session.storage
        path = self._guard(self._busy, "backing_up", lambda p: backup.make_backup(st, self.backup_dir, progress=p),
                           hold="card")
        if path is FAIL:
            return None
        self.view.show_done(self.t("backup_made", name=self.card_name()))
        return path

    def when_text(self, iso: str, today: Optional["_dt.date"] = None) -> str:
        """"Vandaag 14:32", "Gisteren 09:05" or "3 november 2026 14:32" for an ISO time."""
        try:
            when = _dt.datetime.fromisoformat(iso)
        except ValueError:
            return iso.replace("T", " ")
        today = today or _dt.date.today()
        clock = when.strftime("%H:%M")
        if when.date() == today:
            return self.t("today", time=clock)
        if when.date() == today - _dt.timedelta(days=1):
            return self.t("yesterday", time=clock)
        month = self.t("months").split()[when.month - 1]
        return "%d %s %d %s" % (when.day, month, when.year, clock)

    def check_card(self) -> Optional[List[str]]:
        """"Kaart doet raar?": check the card; when something is wrong, offer to repair it.
        Returns the problems found (empty: all fine), None when there is no card."""
        if self.session is None or self.composing:
            return None
        issues = self.check()
        if not issues:
            self.view.show_done(self.t("check_fine"))
            return issues
        text = self.t("check_problems", n=len(issues), list="\n".join("• " + i for i in issues[:8]))
        if self.view.ask(text, [self.t("btn_repair")]) == 0 and self.repair():
            self.view.show_done(self.t("repaired"))
        return issues

    def restore(self, zip_path: str) -> bool:
        """Put the open card back the way it was in the back-up (a back-up of now is made first)."""
        if self.session is None or self.composing:
            return False
        if self.session.dirty:
            self.view.show_error(self.t("unsaved_first"))
            return False
        when = self.when_text(self._backup_time(zip_path))
        same = backup.similarity(backup.card_song_names(self.session.storage), backup.song_names(zip_path))
        if same < backup.SAME_CARD and not self.view.confirm(self.t("confirm_restore_other", pct=round(same * 100))):
            return False
        if not self.view.confirm(self.t("confirm_restore", when=when)):
            return False
        st = self.session.storage

        steps = (["backup"] if self.backups else []) + ["restore"]

        def run(p):
            phase = self._phase(p, steps)
            if self.backups:
                phase("backup")
                backup.make_backup(st, self.backup_dir, progress=p)
            phase("restore")
            return backup.restore(st, zip_path, progress=p)
        if self._guard(self._busy, "restoring", run, steps, "card") is FAIL:
            return False
        self.open_card(self.card_path)
        self.view.show_status(self.t("restored", zip=zip_path))
        self.view.show_done(self.t("restored_done", when=when))
        return True

    def restore_as_new_card(self, zip_path: str) -> bool:
        """Start a new card from the back-up, to put it on any card (another one, an empty one)
        with Op kaart zetten, as when composing."""
        if self.session is not None and self.session.dirty and not self.composing:
            self.view.show_error(self.t("unsaved_first"))
            return False
        src = self._guard(lambda: CardSession.open(backup.as_storage(zip_path)))
        if src is FAIL:
            return False
        s = self._guard(cards.new_card_from, src)
        if s is FAIL:
            return False
        self._begin_compose(s)
        self.view.show_status(self.t("restored_as_new", when=self.when_text(self._backup_time(zip_path))))
        return True

    def restore_to_library(self, zip_path: str, card_name: str = "") -> Optional[str]:
        """Put the back-up in the library as a card (an old library copy back, or a card's old state)."""
        root = self.library.root if self.library is not None else self.library_path or cards.default_library()
        name = None
        while name is None:
            name = self.view.ask_text(self.t("ask_label"), card_name)
            if name is None:
                return None
            name = name.strip()
            if not name:
                name = None
        replace = os.path.exists(os.path.join(root, name))
        if replace and not self.view.confirm(self.t("confirm_replace_library", name=name)):
            return None
        mem = self._guard(backup.as_storage, zip_path)
        if mem is FAIL:
            return None
        check = verify.CopyCheck()
        folder = self._guard(self._busy, "archiving",
                             lambda p: cards.archive_card(mem, root, name, replace, p, self.backup_dir, check))
        if folder is FAIL:
            return None
        self.open_library(root)
        self.view.show_done(self.t("restored_library", name=name) + "\n\n" + self.check_text(check))
        return folder

    @staticmethod
    def _backup_time(zip_path: str) -> str:
        folder = os.path.dirname(zip_path)
        for b in backup.list_backups(folder):
            if os.path.normpath(b.path) == os.path.normpath(zip_path):
                return b.created
        return os.path.basename(zip_path)

    # -------------------------------------------------------------- export
    # What a song list (CSV or PDF) can hold; the first four are the plain list, the rest is read from
    # each song's files. (key, label key)
    EXPORT_FIELDS = [("folder", "col.folder"), ("folder_name", "col.folder_name"), ("song", "col.song"),
                     ("name", "col.name"), ("rhythm", "info_rhythm"), ("meter", "info_meter"),
                     ("tempo", "info_tempo"), ("recorded", "info_recorded"), ("model", "info_model"),
                     ("chord", "info_chord"), ("banks", "exp_banks"), ("inside", "info_inside"),
                     ("files", "col.types"), ("set", "exp_col_set")]
    EXPORT_DEFAULT = ("folder", "folder_name", "song", "name")
    _PLAIN = {"folder", "folder_name", "song", "name", "files"}

    def export_rows(self, fields: Sequence[str] = EXPORT_DEFAULT, folder: Optional[int] = None,
                    progress: Optional[Callable[[int, int, str], None]] = None) -> List[Dict[str, str]]:
        """One row per song ({field: text}), for all folders or one; fields from EXPORT_FIELDS."""
        s = self.session
        songs = [(f, x) for f in s.folders() if folder in (None, f.folder) for x in f.songs]
        details = any(k not in self._PLAIN for k in fields)
        rows = []
        for i, (f, x) in enumerate(songs):
            if progress and details:
                progress(i, len(songs), x.name)
            row = {"folder": "%02d" % f.folder, "folder_name": f.name, "song": "%02d" % x.song, "name": x.name,
                   "files": " ".join(x.types)}
            if details:
                row.update(self._export_details((f.folder, x.song), fields))
            out = {k: row.get(k, "") for k in fields}
            if "set" in fields:                         # a diskette set: its songs, each on its own row
                out["_titles"] = s.set_titles(f.folder, x.song)
            rows.append(out)
        return self._expand_sets(rows) if "set" in fields else rows

    @staticmethod
    def _expand_sets(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """After a diskette set's row, a row for every song in it: that song's name, and "set" = the
        set's name (where it is stays the same; what the set's files say is left empty, it is the set's)."""
        keep = ("folder", "folder_name", "song", "card", "where")
        out = []
        for r in rows:
            titles = r.pop("_titles", [])
            r.setdefault("set", "")
            out.append(r)
            for title in titles:
                out.append(dict({k: v for k, v in r.items() if k in keep}, name=title, set=r.get("name", "")))
        return out

    def _export_details(self, slot: Slot, fields: Sequence[str]) -> Dict[str, str]:
        try:
            facts = self.song_facts(slot)
        except (KN7Error, OSError, ValueError, KeyError):   # an odd song: leave its details empty
            return {}
        facts["chord"] = facts.pop("chord_short", facts.get("chord", ""))   # a list wants it short
        facts["banks"] = facts.get("banks", "").replace(" · ", ", ")
        return facts

    def _bank_title(self, bank) -> str:
        """A bank in a few words: its name, else the name most of its buttons have."""
        used = [m.name for m in bank.memories if m.name]
        return bank.name or (max(set(used), key=used.count) if used else "") or self.t("panel_no_name")

    def _export(self, fields, folder):
        details = any(k not in self._PLAIN for k in fields)
        if not details:
            return self.export_rows(fields, folder)
        return self._guard(self._busy, "exporting", lambda p: self.export_rows(fields, folder, p))

    def export_labels(self, fields: Sequence[str], short: bool = False) -> List[str]:
        """Column headings; short: the brief ones for a standing page with many columns ("Model")."""
        labels = dict(self.EXPORT_FIELDS)
        return [self.t("exp_short_" + k) if short and has_key("exp_short_" + k) else self.t(labels[k])
                for k in fields]

    def song_table(self) -> List[Dict[str, str]]:
        return self.export_rows(("folder", "folder_name", "song", "name", "files"))

    # Columns that never wrap in a printed list: short, and a broken word there is unreadable.
    _ONE_LINE = {"folder", "song", "name", "meter", "tempo", "recorded", "model", "card"}

    @staticmethod
    def sort_by_name(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """The rows A to Z on song name (case does not matter); the same name stays in folder order."""
        return sorted(rows, key=lambda r: r.get("name", "").strip().casefold())

    def today_text(self, today: Optional["_dt.date"] = None) -> str:
        """Today as "18 november 2026", for the bottom of a printed song list."""
        today = today or _dt.date.today()
        return "%d %s %d" % (today.day, self.t("months").split()[today.month - 1], today.year)

    def _open_library_card(self):
        """The library card that is open (a copy on the computer), or None (an SD card, a new card)."""
        if self.composing or self.library is None or not self.card_path:
            return None
        here = os.path.normcase(os.path.abspath(self.card_path))
        return next((c for c in self.library.cards if os.path.normcase(os.path.abspath(c.path)) == here), None)

    def export_source(self) -> str:
        """Where a song list comes from, in one line for the export window ("Uit: ...")."""
        return self.t("exp_from_line", what=self.export_source_what())

    def export_source_what(self) -> str:
        """The open card in a few words: the new card being put together, a card from the library, a
        card in a folder, or the SD card in the reader."""
        if self.composing:
            return self.t("exp_from_new", name=self.card_name())
        lib = self._open_library_card()
        if lib is not None:
            return self.t("exp_from_library", name=lib.label)
        path = self.card_path
        on_drive = path and (windows.is_drive_root(path) or os.path.dirname(os.path.normpath(path))
                             in [os.path.normpath(r) for r in self.volume_roots()])
        if path and not on_drive:                         # a card copy in some folder on the computer
            return self.t("exp_from_folder", name=os.path.basename(os.path.normpath(path)))
        return self.t("exp_from_card", name=self.card_name())

    def list_title(self) -> str:
        """The proposed title above a printed song list: "Songlijst" and the card's name."""
        lib = self._open_library_card()
        return self.t("exp_title_text", name=lib.label if lib is not None else self.card_name())

    # ------------------------------------------------------- library export
    # What a song list of the library can show: the plain columns plus what the library reads itself.
    LIB_FIELDS = {"folder", "folder_name", "song", "name", "files", "tempo", "meter", "recorded", "set"}
    _LIB_SLOW = {"tempo", "meter", "recorded"}

    def library_filtered(self) -> bool:
        """A filter or search is on in the library: then "only what you see" makes sense."""
        return any(v for v in getattr(self, "lib_filter", {}).values())

    def library_export_text(self, filtered: bool = False) -> str:
        lib = self.library
        if lib is None:
            return ""
        if filtered:
            return self.t("exp_from_lib_filtered", songs=len(self.library_rows()))
        return self.t("exp_from_lib_all", cards=len(lib.cards), songs=len(lib.songs))

    def _library_songs(self, filtered: bool) -> List["lb.LibrarySong"]:
        lib = self.library
        if lib is None:
            return []
        if not filtered:
            return list(lib.songs)
        seen, out = set(), []
        for r in self.library_rows():
            x = lib.songs[r.index]
            if id(x) not in seen:
                seen.add(id(x))
                out.append(x)
        return out

    def _where(self, c) -> str:
        return self.t("exp_where", card=c.card.label, folder="%02d" % c.folder, song="%02d" % c.song)

    def library_export_rows(self, fields: Sequence[str], by_name: bool = False, filtered: bool = False,
                            progress: Optional[Callable[[int, int, str], None]] = None) -> List[Dict[str, str]]:
        """The library as song-list rows. by_name: one row per song, with where it is ("where": every
        card, folder and number). Otherwise one row per copy, card by card (the library mirrors the
        cards), with "card"."""
        lib = self.library
        songs = self._library_songs(filtered)
        slow = any(k in self._LIB_SLOW for k in fields)
        sets = "set" in fields
        for i, x in enumerate(songs):
            if slow or sets:
                if progress:
                    progress(i, len(songs), x.name)
                if slow:
                    lib.details(x)
                elif not x.titles and not x.checked:
                    lib._read_titles(x)

        def titled(row, x):
            if sets:
                row["_titles"] = list(x.titles)
            return row

        def facts(x) -> Dict[str, str]:
            return {"tempo": str(x.tempo) if x.tempo else "", "meter": x.meter or "",
                    "recorded": self.t("yes") if x.recorded else "", "files": " ".join(x.extensions)}

        if by_name:
            rows = [titled(dict(facts(x), name=x.name, where="; ".join(self._where(c) for c in x.copies)), x)
                    for x in songs]
            return self.sort_by_name(self._expand_sets(rows) if sets else rows)
        mine = {id(c): x for x in songs for c in x.copies}
        rows = []
        for card in lib.cards:
            db = card.session.db
            copies = sorted((c for x in songs for c in x.copies if c.card is card), key=lambda c: (c.folder, c.song))
            for c in copies:
                row = dict(facts(mine[id(c)]), card=card.label, folder="%02d" % c.folder,
                           folder_name=db.folders[c.folder - 1].name, song="%02d" % c.song, name=c.name,
                           files=" ".join(c.extensions))
                rows.append(titled(row, mine[id(c)]))
        return self._expand_sets(rows) if sets else rows

    def _library_export(self, fields, by_name, filtered):
        if not any(k in self._LIB_SLOW or k == "set" for k in fields):
            return self.library_export_rows(fields, by_name, filtered)
        return self._guard(self._busy, "exporting", lambda p: self.library_export_rows(fields, by_name, filtered, p))

    def _library_cols(self, fields: Sequence[str], by_name: bool) -> List[str]:
        fields = [k for k in fields if k in self.LIB_FIELDS]
        if by_name:                                     # where it is replaces Map, Mapnaam and Nr
            return ["name", "where", *[k for k in fields if k not in ("folder", "folder_name", "song", "name")]]
        return ["card", *fields]

    def _library_labels(self, cols: Sequence[str], short: bool = False) -> List[str]:
        extra = {"card": "col.card", "where": "exp_col_where"}
        return [self.t(extra[k]) if k in extra else self.export_labels([k], short)[0] for k in cols]

    def library_list(self, fields: Sequence[str] = EXPORT_DEFAULT, by_name: bool = False,
                     filtered: bool = False, page_per_card: bool = False):
        """The library as a song list, the same for print and CSV: (sections, cols, labels, context).
        A to Z with where each song is, or card by card (per card its folders, as in the list of one
        card). A section is (heading html, rows, {context column: text}); see _list_csv."""
        rows = self._library_export(fields, by_name, filtered)
        if rows is FAIL:
            return FAIL
        if by_name:
            return [("", rows, {})], self._library_cols(fields, True), self._library_labels, []
        fields = [k for k in fields if k in self.LIB_FIELDS]
        cols = [k for k in fields if k not in ("folder", "folder_name")]
        sections = []
        for card in self.library.cards:
            mine = [r for r in rows if r["card"] == card.label]
            if not mine:
                continue
            brk = " style=\"page-break-before: always\"" if page_per_card and sections else ""
            card_head = "<h2%s>%s</h2>" % (brk, escape(card.label))
            for folder in dict.fromkeys(r["folder"] for r in mine):
                inside = [r for r in mine if r["folder"] == folder]
                head = SimpleNamespace(folder=int(folder), name=inside[0]["folder_name"])
                ctx = {"card": card.label, "folder": folder, "folder_name": head.name}
                sections.append((card_head + self._folder_heading(head, fields, ""), inside, ctx))
                card_head = ""
        context = ["card", *[k for k in ("folder", "folder_name") if k in fields]]
        return sections, cols, self._library_labels, context

    def export_library_csv(self, path: str, fields: Sequence[str] = EXPORT_DEFAULT, by_name: bool = False,
                           filtered: bool = False) -> bool:
        """The library (or what its filter shows) as CSV: the same list as printed (library_list)."""
        made = self.library_list(fields, by_name, filtered)
        return made is not FAIL and self._list_csv(path, *made)

    def library_list_html(self, fields: Sequence[str] = EXPORT_DEFAULT, by_name: bool = False,
                          filtered: bool = False, page_per_card: bool = False,
                          title: Optional[str] = None, fit: Sequence[Tuple[float, int]] = ()) -> Optional[str]:
        """The library for printing (library_list); fit: see _tables."""
        made = self.library_list(fields, by_name, filtered, page_per_card)
        if made is FAIL:
            return None
        sections, cols, labels, _context = made
        title = self.t("exp_lib_title") if title is None else title.strip()
        parts = ["<h2>%s</h2>" % escape(title)] if title else []
        return self._tables(parts, [(h, rs) for h, rs, _c in sections], cols, labels, fit)

    def song_list(self, fields: Sequence[str] = EXPORT_DEFAULT, folder: Optional[int] = None,
                  page_per_folder: bool = False, skip_empty: bool = False, by_name: bool = False):
        """The card's song list, the same for print and CSV: (sections, cols, labels, context).
        Folder by folder: per folder a section (its heading, its songs); by_name: one section with every
        song A to Z (Map and Mapnaam then are columns, so you can see where a song is). skip_empty
        leaves out folders without songs. A section is (heading html, rows, {context column: text})."""
        rows = self._export(list(dict.fromkeys(["folder", *fields])), folder)
        if rows is FAIL:
            return FAIL
        if by_name:
            cols = ["name", *[k for k in fields if k != "name"]]     # looking up a name: name first
            return [("", self.sort_by_name(rows), {})], cols, self.export_labels, []
        cols = [k for k in fields if k not in ("folder", "folder_name")]
        sections = []
        for f in self.session.folders():
            mine = [r for r in rows if r["folder"] == "%02d" % f.folder]
            if folder not in (None, f.folder):
                continue
            if not mine and folder is None and (skip_empty or not f.name):
                continue
            brk = " style=\"page-break-before: always\"" if page_per_folder and sections else ""
            ctx = {"folder": "%02d" % f.folder, "folder_name": f.name}
            sections.append((self._folder_heading(f, fields, brk), mine, ctx))
        return sections, cols, self.export_labels, [k for k in ("folder", "folder_name") if k in fields]

    def export_csv(self, path: str, fields: Sequence[str] = EXPORT_DEFAULT, folder: Optional[int] = None,
                   by_name: bool = False, skip_empty: bool = False) -> bool:
        """The song list as CSV for Excel: the same list as printed (song_list)."""
        made = self.song_list(fields, folder, False, skip_empty, by_name)
        return made is not FAIL and self._list_csv(path, *made)

    def song_list_html(self, fields: Sequence[str] = EXPORT_DEFAULT, folder: Optional[int] = None,
                       page_per_folder: bool = False, skip_empty: bool = False, by_name: bool = False,
                       title: Optional[str] = None, fit: Sequence[Tuple[float, int]] = ()) -> Optional[str]:
        """The song list for printing (song_list). title goes on top (None: the app's name, "": no
        title). fit: see _tables."""
        made = self.song_list(fields, folder, page_per_folder, skip_empty, by_name)
        if made is FAIL:
            return None
        sections, cols, labels, _context = made
        title = self.t("title") if title is None else title.strip()
        parts = ["<h2>%s</h2>" % escape(title)] if title else []
        return self._tables(parts, [(h, rs) for h, rs, _c in sections], cols, labels, fit)

    def _list_csv(self, path: str, sections, cols: List[str], labels, context: List[str]) -> bool:
        """A song list as CSV (Excel opens it right: BOM, ";"). The same columns, in the same order, as
        the printed list; what the printed list says in a heading (card, folder, folder name) is a
        column in front, since a sheet has no headings. A folder without songs that the printed list
        shows gets a row of its own."""
        cols = self._list_cols(cols, [r for _h, rs, _c in sections for r in rs])
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh, delimiter=";")
            w.writerow(labels(context + cols))
            for _head, rows, ctx in sections:
                start = [ctx.get(k, "") for k in context]
                if not rows and start:
                    w.writerow(start + [""] * len(cols))
                for r in rows:
                    w.writerow(start + [r.get(k, "") for k in cols])
        self.view.show_status(self.t("exported", path=path))
        return True

    @staticmethod
    def _list_cols(cols: List[str], every: List[Dict[str, str]]) -> List[str]:
        """The columns a list shows: "Uit set" right after the name, and a column with nothing in it
        anywhere left out (the name always stays)."""
        if "set" in cols:
            cols = [k for k in cols if k != "set"]
            cols.insert(cols.index("name") + 1 if "name" in cols else len(cols), "set")
        return [k for k in cols if k == "name" or any(r.get(k) for r in every)] if every else list(cols)

    def _tables(self, parts: List[str], sections, cols: List[str], labels, fit) -> str:
        """The list's tables: per section (heading html, rows) a table with the columns cols, the same
        columns in every table. A column with nothing in it anywhere is left out. fit: the page sizes
        to try, (letter size, characters on a line), largest first; the first one where every column
        fits on one line is used (self.list_font says which), else long texts are cut off with "…",
        widest column first, just as much as needed. Without fit, long texts may wrap."""
        every = [r for _h, rs in sections for r in rs]
        cols = self._list_cols(cols, every)
        self.list_font = None
        heads, crop = labels(cols), {}
        if fit:
            plan = None
            for pt, chars in fit:
                for short in (False, True):
                    heads = labels(cols, short)
                    crop = self._fit(every, cols, heads, chars)
                    if crop == {}:                      # everything fits as it is
                        plan = (pt, heads, crop)
                        break
                    if crop is not None and plan is None:
                        plan = (pt, heads, crop)        # the biggest letters that fit with cutting
                if plan is not None and plan[2] == {}:
                    break
            if plan is None:                            # nothing fits even cut short: smallest, cut most
                pt, chars = fit[-1]
                heads = labels(cols, True)
                plan = (pt, heads, self._fit(every, cols, heads, chars, force=True) or {})
            self.list_font, heads, crop = plan
        out = list(parts)
        for head, rows in sections:
            out.append(head)
            out.append(self._folder_table(rows, cols, heads, crop, one_line=bool(fit)))
        return "".join(out)

    # Never cut short: short already, or what a player looks for.
    _NO_CROP = {"folder", "song", "name", "meter", "tempo", "recorded", "set"}

    @staticmethod
    def _fit(rows, cols, heads, room, force: bool = False) -> Optional[Dict[str, int]]:
        """How far to cut each column so the table fits ({} = no cutting needed, None = it does not
        fit). room is the width of the page: a number of characters, or (width, measure, gap) with
        measure(text, bold) giving a text's real width and gap the room between two columns. The
        widest column gives way first, one character at a time, never below its heading or 6
        characters. force: cut to those minimums whatever happens."""
        if isinstance(room, tuple):
            avail, measure, gap = room
        else:
            avail, gap = room, 2

            def measure(text, bold=False):
                return len(text)
        values = {k: set(r.get(k, "") for r in rows) for k in cols}
        longest = {k: max([0] + [len(v) for v in values[k]]) for k in cols}
        head_w = {k: measure(h, True) for k, h in zip(cols, heads)}

        def col_width(k, n):
            return max([head_w[k]] + [measure(MainPresenter._crop(v, n)) for v in values[k]])

        chars = dict(longest)
        width = {k: col_width(k, longest[k]) for k in cols}
        floor = {k: longest[k] if k in MainPresenter._NO_CROP else min(longest[k], max(len(h), 6))
                 for k, h in zip(cols, heads)}
        while sum(width.values()) + gap * len(cols) > avail:
            can = [k for k in cols if chars[k] > floor[k]]
            if not can:
                return {k: n for k, n in chars.items() if n < longest[k]} if force else None
            k = max(can, key=lambda c: width[c])
            chars[k] -= 1
            width[k] = col_width(k, chars[k])
        return {k: n for k, n in chars.items() if n < longest[k]}

    @staticmethod
    def _folder_heading(f, fields, brk: str) -> str:
        """Map and Mapnaam as the heading, as ticked (or only the page break)."""
        head = [x for x in ("%02d" % f.folder if "folder" in fields else "",
                            escape(f.name) if "folder_name" in fields else "") if x]
        if head:
            return "<h3%s>%s</h3>" % (brk, " &nbsp; ".join(head))
        return "<div%s></div>" % brk if brk else ""

    @staticmethod
    def _crop(text: str, n: Optional[int]) -> str:
        return text if n is None or len(text) <= n else text[:n - 1].rstrip() + "…"

    @staticmethod
    def _folder_table(rows, cols, heads, crop: Optional[Dict[str, int]] = None, one_line: bool = False) -> str:
        """A table of rows with the columns cols (headings heads). crop: cut these columns to this many
        characters ("8 Beat Ro…"). one_line: no cell wraps (the columns were fitted to the page)."""
        crop = crop or {}
        out = ["<table cellspacing=0 cellpadding=3>"]
        if len(cols) > 2:                               # more than number and name: say what each column is
            out.append("<tr>%s</tr>" % "".join("<th align=left style=\"padding-right: 12px; white-space: nowrap\">"
                                               "%s</th>" % escape(h) for h in heads))
        for r in rows:
            out.append("<tr>%s</tr>" % "".join(
                "<td style=\"padding-right: 12px%s\">%s</td>"
                % ("; white-space: nowrap" if one_line or k in MainPresenter._ONE_LINE else "",
                   escape(MainPresenter._crop(r.get(k, ""), crop.get(k))))
                for k in cols))
        out.append("</table>")
        return "".join(out)
