"""The task-oriented flow (ADR-0008): start screen, put on card, keep in library."""
import os
import tempfile
import unittest

from helpers import gui_test
from kn_songboek.core import CardSession
from kn_songboek.core import cards
from kn_songboek.gui.presenter import MainPresenter
from kn_songboek.storage import DirectoryStorage
from test_library import add
from test_presenter import FakeView


class TaskView(FakeView):
    def __init__(self):
        super().__init__()
        self.page, self.done, self.asks, self.answers, self.texts = None, [], [], [], []
        self.others, self.again = [], False
        self.folder = None

    def ask(self, text, buttons):
        self.asks.append(text)
        return self.answers.pop(0) if self.answers else None

    def ask_text(self, text, default=""):
        return self.texts.pop(0) if self.texts else None

    def show_page(self, page): self.page = page
    def show_done(self, text, other=""): self.done.append(text); self.others.append(other); return self.again
    def pick_folder(self, text): return self.folder


class TaskTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.vol = os.path.join(t, "Volumes")
        self.card = os.path.join(self.vol, "KN7000")
        s = CardSession.create(DirectoryStorage(self.card))
        add(s, 1, "WALTZ", 90)
        add(s, 2, "ROCK", 140)
        s.save()
        self.empty = os.path.join(self.vol, "LEEG")
        os.makedirs(self.empty)
        self.library = os.path.join(t, "Bibliotheek")
        self.view = TaskView()
        self.p = MainPresenter(self.view, backup_dir=os.path.join(t, "backups"))
        self.p.find_cards = lambda: [cards.classify(os.path.join(self.vol, n)) for n in sorted(os.listdir(self.vol))]
        self.ejected = []
        self.p.eject = lambda path: self.ejected.append(path) or True
        self.p.is_drive = lambda path: True

    def tearDown(self):
        self.tmp.cleanup()

    def test_organize_finds_the_card_and_puts_changes_on_it(self):
        self.assertTrue(self.p.start_organize())
        self.assertEqual(self.view.page, "organize")
        self.assertEqual(self.p.card_path, self.card)
        self.p.rename_song(1, 1, "WALS")
        self.assertEqual(self.view.actions.pending, 1)
        self.assertTrue(self.p.put_on_card())
        self.assertEqual(self.view.done, ["Klaar. Alles staat op de kaart."])     # not a mounted volume here
        self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(0, 0).name, "WALS")
        self.assertFalse(self.view.actions.pending)

    def test_a_card_that_does_not_eject_is_said_so(self):
        from unittest import mock
        from kn_songboek.storage import windows
        self.p.eject = lambda path: False                        # in use, or the system said no
        with mock.patch.object(windows, "is_drive_root", return_value=True):
            self.p._done(self.card)
        self.assertIn("Werp hem eerst", self.view.done[-1])
        self.p.eject = lambda path: True
        self.assertTrue(self.p.start_organize())
        with mock.patch.object(windows, "is_drive_root", return_value=True):
            self.p._done(self.card)
        self.assertTrue(self.view.done[-1].startswith("Klaar. Je kunt de kaart eruit halen."))
        self.assertEqual((self.view.page, self.p.session), ("start", None))    # the card is out: not shown

    def test_locked_card_is_shown_said_and_waited_for(self):
        from unittest import mock
        from kn_songboek.storage import DirectoryStorage as DS
        locked = {"on": True}
        with mock.patch.object(DS, "writable", lambda st: not locked["on"]):
            self.assertIn("schrijfbeveiligd", self.p.card_text(cards.classify(self.card)))
            self.view.show_locked = lambda text: self.view.asks.append(text)
            self.assertTrue(self.p.start_organize())
            self.assertIn("LOCK", self.view.asks[-1])              # a bar says so straight away
            self.p.rename_song(1, 1, "WALS")
            self.view.answers = [None]                              # stop: nothing written
            self.assertFalse(self.p.put_on_card())
            self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(0, 0).name, "WALTZ")

            def unlock(text, buttons):
                self.view.asks.append(text)
                locked["on"] = False                                # the user slid the switch up
                return 0
            self.view.ask = unlock
            self.assertTrue(self.p.put_on_card())
        self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(0, 0).name, "WALS")

    def test_organize_without_card_asks_again_or_for_a_folder(self):
        os.rename(self.card, os.path.join(self.tmp.name, "elders"))
        self.view.answers = [None]
        self.assertFalse(self.p.start_organize())
        self.assertIn("geen kaart", self.view.asks[0])
        self.view.answers = [1]
        self.view.folder = os.path.join(self.tmp.name, "elders")
        self.assertTrue(self.p.start_organize())

    def test_no_card_says_an_empty_card_is_in_but_never_names_other_disks(self):
        os.rename(self.card, os.path.join(self.tmp.name, "elders"))
        other = os.path.join(self.vol, "Data")               # an external drive: not a card
        os.makedirs(other)
        with open(os.path.join(other, "notes.txt"), "w") as fh:
            fh.write("x")
        self.view.answers = [None]
        self.assertFalse(self.p.start_organize())
        self.assertIn("Wat er nu wel in zit: LEEG (lege kaart)", self.view.asks[0])
        self.assertNotIn("Data", self.view.asks[0])

    def test_leave_with_changes_asks(self):
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        self.view.answers = [None]                      # cancel: stay
        self.assertFalse(self.p.leave())
        self.assertEqual(self.view.page, "organize")
        self.view.answers = [1]                         # throw away
        self.assertTrue(self.p.leave())
        self.assertEqual(self.view.page, "start")
        self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(0, 0).name, "WALTZ")

    def test_compose_and_put_on_an_empty_card(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.assertTrue(self.p.open_library(self.library))
        self.view.choice = 0                            # "Leeg beginnen"
        self.assertTrue(self.p.start_compose())
        self.assertEqual(self.view.choices[0], "Leeg beginnen")
        self.assertEqual(self.view.page, "compose")
        self.assertTrue(self.view.actions.composing)
        self.assertEqual(self.p.import_from_library([0, 1], 5), 2)
        self.assertIn("2 songs", self.view.space)
        panel = self.p.song_panel((5, 1))                         # not on a card yet: read from the library
        self.assertNotIn("ontbreekt", [size for _, size in panel["files"]])
        name, rows = self.p.song_info((5, 1))
        self.assertEqual(dict(rows).get("Gemaakt op"), "KN7000")
        # two cards in the computer: the user is asked which; pick the empty one
        self.view.choice = [c.kind for c in self.p.find_cards()].index(cards.EMPTY)
        self.assertTrue(self.p.put_on_card())
        self.assertEqual(self.p.card_path, self.empty)
        self.assertEqual(sorted(x.name for _, _, x in CardSession.open(DirectoryStorage(self.empty)).db.iter_songs()),
                         ["ROCK", "WALTZ"])
        self.assertEqual(self.view.page, "organize")
        self.assertFalse(self.p.composing)
        self.assertEqual(self.p.card_name(), "LEEG")                  # not named: the card keeps its name

    def test_no_sd_card_keep_it_in_the_library_and_make_the_card_later(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 0
        self.p.start_compose()
        self.p.import_from_library([0, 1], 5)
        self.p.find_cards = lambda: []                  # no SD card at hand
        self.view.answers = [2]                         # In de bibliotheek bewaren…
        self.view.texts = ["Bruiloft"]
        self.assertTrue(self.p.put_on_card())
        self.assertIn("Bewaard in de bibliotheek als Bruiloft", self.view.done[-1])
        self.assertEqual(self.view.page, "start")
        self.assertIsNone(self.p.session)
        self.assertIn("Bruiloft", [c.label for c in self.p.library.cards])
        kept = next(c for c in self.p.library.cards if c.label == "Bruiloft")
        self.assertEqual(sorted(x.name for _, _, x in kept.session.db.iter_songs()), ["ROCK", "WALTZ"])
        # later: start from it, as with any kept card
        self.view.choice = 1 + [c.label for c in self.p.library.cards].index("Bruiloft")
        self.assertTrue(self.p.start_compose())
        self.assertEqual(sum(1 for _ in self.p.session.db.iter_songs()), 2)

    def test_compose_onto_a_used_card_warns(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 0
        self.p.start_compose()
        self.p.import_from_library([0], 1)
        self.view.choice = [c.kind for c in self.p.find_cards()].index(cards.KN7000)
        self.view.answer = False
        self.assertFalse(self.p.put_on_card())
        self.assertEqual(sum(1 for _ in CardSession.open(DirectoryStorage(self.card)).db.iter_songs()), 2)
        self.view.answer = True
        self.assertTrue(self.p.put_on_card())
        self.assertEqual(sum(1 for _ in CardSession.open(DirectoryStorage(self.card)).db.iter_songs()), 1)

    def test_compose_from_a_kept_card_then_keep_the_new_one(self):
        s = CardSession.open(DirectoryStorage(self.card))
        s.rename_folder(2, "ROCK")
        s.set_song_list(1, [(2, 1), (1, 1)])
        s.set_favorite(1, 3, (1, 1))
        s.save(backup=False)
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 1                            # "Beginnen met Kaart A"
        self.assertTrue(self.p.start_compose())
        new = self.p.session
        self.assertEqual([(f, so, x.name) for f, so, x in [(fi + 1, si + 1, x) for fi, si, x in new.db.iter_songs()]],
                         [(1, 1, "WALTZ"), (2, 1, "ROCK")])
        self.assertEqual(new.db.folders[1].name, "ROCK")
        self.assertGreater(self.view.actions.pending, 0)              # Op kaart zetten works straight away
        self.assertIsNone(self.p.check_card())                         # not on a card yet: nothing to check
        self.assertFalse(self.p.repair())
        self.assertEqual(new.playlists()[0], [(2, 1), (1, 1)])
        self.assertEqual(new.favorites()[0][1][2][1:], (0, 0))
        self.assertFalse(new.history())                 # the starting point, nothing to undo
        new.rename_song(1, 1, "WALS")
        # put it on the empty card, and keep it in the library under a new name
        self.view.texts = ["kaart b/2026"]             # click on "Nieuwe kaart": name it
        self.assertTrue(self.p.name_new_card())
        self.assertEqual(self.p.card_name(), "KAART B2026")
        renamed = []
        self.p.rename_volume = lambda path, name: renamed.append((path, name)) or path
        asked = []
        ask_text = self.view.ask_text
        self.view.ask_text = lambda text, default="": asked.append(default) or ask_text(text, default)
        self.view.choice = [c.kind for c in self.p.find_cards()].index(cards.EMPTY)
        self.view.texts = ["Kaart B"]
        self.view.again = True                          # "Nog een kaart met dezelfde songs"
        self.assertTrue(self.p.put_on_card())
        self.assertEqual(self.view.others[-1], "Nog een kaart met dezelfde songs")
        self.assertTrue(self.p.composing)               # the next card starts from Kaart B, ready to put on
        self.assertEqual(self.view.page, "compose")
        self.assertEqual(self.p.session.db.song(0, 0).name, "WALS")
        self.assertGreater(self.view.actions.pending, 0)
        self.assertEqual(renamed, [(self.empty, "KAART B2026")])      # the SD card gets the name
        self.assertEqual(asked, ["KAART B2026"])                       # and it is suggested for the library
        self.assertEqual([c.label for c in self.p.library.cards], ["Kaart A", "Kaart B"])
        self.assertEqual(CardSession.open(DirectoryStorage(os.path.join(self.library, "Kaart B"))).db.song(0, 0).name,
                         "WALS")

    def test_no_extra_button_when_the_new_card_is_not_kept(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 1
        self.assertTrue(self.p.start_compose())
        self.view.choice = [c.kind for c in self.p.find_cards()].index(cards.EMPTY)
        self.view.answer = False                        # "Ook bewaren in de bibliotheek?" no
        self.view.again = True
        self.assertTrue(self.p.put_on_card())
        self.assertEqual(self.view.others[-1], "")
        self.assertFalse(self.p.composing)

    def test_compose_empty_refuses(self):
        self.p.start_compose()
        self.assertFalse(self.p.put_on_card())
        self.assertTrue(self.view.errors)

    def test_archive_names_then_offers_update(self):
        self.view.texts = ["Kaart bruiloften"]
        folder = self.p.start_archive(self.library)
        self.assertEqual(os.path.basename(folder), "Kaart bruiloften")
        self.assertIn("bruiloften", self.view.done[-1])
        self.view.answers = [0]                         # "Kopie vervangen"
        self.assertEqual(self.p.start_archive(self.library), folder)
        self.assertIn("Kaart bruiloften", self.view.asks[-1])

    def test_keep_a_row_of_diskettes(self):
        import shutil
        from test_floppy import make_diskette
        disk = os.path.join(self.vol, "DISKETTE  2")
        make_diskette(disk)
        self.view.choice = 0                                        # card and diskette in: which one?
        self.view.texts = ["Reeks 1", "Reeks 2"]
        self.view.answers = [0, 0, 1]       # next diskette (not in yet), look again (it is), then Klaar
        swapped = []

        def swap(path):                                             # ejected; the next one comes in later
            self.ejected.append(path)
            if path == disk:
                shutil.rmtree(path)
            return True

        def ask(text, buttons):
            self.view.asks.append(text)
            if len(self.view.asks) == 2 and not swapped:            # the user puts the next diskette in
                swapped.append(make_diskette(os.path.join(self.vol, "DISKETTE  3"), names=("BIGBND",)))
            return self.view.answers.pop(0)
        self.view.ask = ask
        self.p.eject = swap
        folder = self.p.start_archive(self.library)
        self.assertEqual(self.view.choices, ["DISKETTE  2 (diskette, 2 sets)", "KN7000 (KN7000-kaart, 2 songs)"])
        self.assertEqual(folder, os.path.join(self.library, "Diskettes", "Reeks 2"))
        self.assertEqual(self.ejected, [disk, os.path.join(self.vol, "DISKETTE  3")])   # each one ejected
        self.assertIn("Diskette 1 staat in de bibliotheek", self.view.asks[0])
        self.assertIn("nog geen diskette", self.view.asks[1])
        self.assertIn("Diskette 2 staat in de bibliotheek", self.view.asks[2])
        self.assertIn("2 diskette(s)", self.view.done[-1])
        self.assertTrue(self.p.open_library(self.library))
        self.assertEqual([c.label for c in self.p.library.cards], ["Diskettes/Reeks 1", "Diskettes/Reeks 2"])

    def test_unzipped_folder_is_kept_like_a_diskette(self):
        """A download (unzipped into a folder) is chosen with 'Zelf een map kiezen': kept like a
        diskette, but nothing is ejected and no next diskette is asked for."""
        from test_floppy import make_diskette
        folder = os.path.join(self.tmp.name, "download")
        make_diskette(folder)
        self.p.is_drive = lambda path: False
        self.view.texts = ["Download 1"]
        made = self.p.start_archive(self.library, folder)
        self.assertEqual(made, os.path.join(self.library, "Diskettes", "Download 1"))
        self.assertEqual(self.ejected, [])
        self.assertEqual(self.view.asks, [])

    def test_diskettes_all_called_the_same_are_never_overwritten(self):
        from test_floppy import make_diskette
        disk = os.path.join(self.vol, "DISKETTE  2")
        os.rename(self.card, os.path.join(self.tmp.name, "weg"))   # only the diskette in
        make_diskette(disk)
        self.view.confirm = lambda text: False                       # no next diskette
        self.view.ask_text = lambda text, default="": default        # take the suggestion
        first = self.p.start_archive(self.library)
        self.assertEqual(os.path.basename(first), "Diskette")
        # the same diskette again: recognised by its files, skip leaves it alone
        self.view.answers = [0]
        self.assertEqual(self.p.start_archive(self.library), first)
        self.assertIn("staat al in de bibliotheek", self.view.asks[-2])
        # another diskette with the same volume name: a free name, nothing replaced
        import shutil
        shutil.rmtree(disk)
        make_diskette(disk, names=("BIGBND",))
        second = self.p.start_archive(self.library)
        self.assertEqual(os.path.basename(second), "Diskette 2")
        texts = iter(["Diskette", "Reeks 3"])                       # a taken name is refused
        self.view.ask_text = lambda text, default="": next(texts)
        shutil.rmtree(disk)
        make_diskette(disk, names=("PARTY_",))
        third = self.p.start_archive(self.library)
        self.assertEqual(os.path.basename(third), "Reeks 3")
        self.assertIn("andere diskette", self.view.errors[-1])
        from kn_songboek.core import CardSession as CS
        self.assertEqual([s.name for _, _, s in CS.open(DirectoryStorage(first)).db.iter_songs()], ["TRAX1", "1FINGR"])

    def test_archive_with_several_matching_copies_asks_which(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart B")
        self.view.choice = 1                            # the second copy
        self.view.answer = False                        # "Weet je het zeker?" no: nothing happens
        self.assertIsNone(self.p.start_archive(self.library))
        self.view.answer = True
        folder = self.p.start_archive(self.library)
        self.assertEqual(os.path.basename(folder), "Kaart B")
        self.assertEqual(self.view.choices, ["Kaart A  ·  dezelfde songs", "Kaart B  ·  dezelfde songs",
                                             "Als nieuwe kaart bewaren"])
        self.assertEqual(self.view.asks, [])            # not the yes/no question for one copy

    def test_library_shows_card_and_folder(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        rows = {r.name: r.cards for r in self.p.library_rows()}
        self.assertEqual(rows, {"ROCK": "Kaart A (map 2)", "WALTZ": "Kaart A (map 1)"})


@gui_test
class StartScreenGuiTest(unittest.TestCase):
    def test_start_screen_and_pages(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            self.assertEqual(w.pages.currentIndex(), 0)
            self.assertEqual(len(w.task_buttons), 3)
            self.assertTrue(w.task_buttons["task_compose"].text().startswith("Nieuwe kaart samenstellen"))
            # each task its own colour (blue, green, orange) and a line about the library only when there is one
            self.assertEqual([b.property("task") for b in w.task_buttons.values()], ["1", "2", "3"])
            self.assertTrue(w.library_line.isHidden())
            self.assertFalse(w.dock.isVisible() or w.lists_dock.isVisible())
            card = os.path.join(t, "kaart")
            s = CardSession.create(DirectoryStorage(card))
            add(s, 1, "WALTZ", 90)
            s.save()
            w.open_path(card)
            self.assertEqual(w.pages.currentIndex(), 1)
            self.assertFalse(w.tip.isHidden())                  # first time: a tip
            w.tip_ok.click()
            self.assertTrue(w.tip.isHidden())
            self.assertEqual(w.settings.value("tip_seen_organize"), "1")
            from kn_songboek.gui.qt_app import HelpDialog, manual_chapters
            self.assertIn("## 7.", manual_chapters("x\n## 1. A\ny\n## 7. B\nz", [7]))
            self.assertNotIn("## 1.", manual_chapters("x\n## 1. A\ny\n## 7. B\nz", [7]))
            self.assertIn("ordenen", HelpDialog(w, "organize").view.toPlainText())
            self.assertTrue(w.library_panel.isHidden())
            self.assertTrue(w.draft.isHidden())
            w.presenter.rename_song(1, 1, "WALS")
            self.assertFalse(w.draft.isHidden())
            self.assertEqual(w.draft_text.text(), "1 wijziging(en) nog niet op de kaart")
            w.presenter.undo()
            self.assertTrue(w.draft.isHidden())
            self.assertTrue(w.go_start())
            self.assertEqual(w.pages.currentIndex(), 0)
            w.settings.setValue("last_library", t)
            w.presenter.start_compose()
            self.assertEqual(w.pages.currentIndex(), 1)
            self.assertFalse(w.library_panel.isHidden())
            self.assertFalse(w.draft.isHidden())
            self.assertEqual(w.draft_text.text(), "Nieuwe kaart: nog leeg")
            self.assertFalse(w.put_button.isEnabled())
            w.presenter.leave()
            w.close()


@gui_test
class BackgroundWorkTest(unittest.TestCase):
    """Long work runs on a worker thread; the window keeps processing events meanwhile."""

    def test_run_busy(self):
        import threading
        import time
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            ticks, threads = [], []
            timer = QTimer()
            timer.timeout.connect(lambda: ticks.append(1))
            timer.start(10)

            def job(progress):
                threads.append(threading.current_thread() is not threading.main_thread())
                for i in range(5):
                    progress(i, 5, "stap")
                    time.sleep(0.05)
                return 42
            self.assertEqual(w.run_busy("bezig", job), 42)
            timer.stop()
            self.assertEqual(threads, [True])
            self.assertGreater(len(ticks), 3)               # the event loop kept running
            with self.assertRaises(ValueError):
                w.run_busy("bezig", lambda p: int("x"))
            # a save through the presenter: worker thread, view refreshed afterwards on the GUI thread
            card = os.path.join(t, "kaart")
            s = CardSession.create(DirectoryStorage(card))
            add(s, 1, "WALTZ", 90)
            s.save()
            w.open_path(card)
            w.presenter.rename_song(1, 1, "WALS")
            self.assertFalse(w.draft.isHidden())
            w.presenter.backup_dir = os.path.join(t, "backups")
            w.show_done = lambda text: None
            self.assertTrue(w.presenter.put_on_card())
            self.assertTrue(w.draft.isHidden())
            self.assertEqual(w.songs.item(0, 2).text(), "WALS")
            w.close()


@gui_test
class FlowGuiTest(unittest.TestCase):
    """'Op kaart zetten' of a new card in the step window: which card, warning, write, 'Klaar'."""

    def test_closing_the_step_window_cancels_without_an_error(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication, QDialog
        from kn_songboek.gui.qt_app import MainWindow
        from kn_songboek.gui.dialogs import FlowDialog
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            f = FlowDialog(w, "x", [("step_find", "1"), ("step_done", "2")])
            f.show()
            f.reject()                                   # Esc / close button: QDialog.done(int) is not ours
            self.assertEqual(f.result(), QDialog.Rejected)
            self.assertIs(FlowDialog.done, QDialog.done)             # never overridden with another meaning
            w.close()

    def test_the_step_window_knows_the_no_card_question_with_lines_added(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            w.presenter.find_cards = lambda: []
            tr = w.presenter.t
            for key in ("no_kn7000_card", "no_card_or_floppy", "no_target_card"):
                head, _, rest = tr(key).partition("\n\n")
                text = head + "\n\n" + tr("other_cards_in", names="LEEG") + "\n\n" + rest
                self.assertIsNotNone(w._card_poll(text), key)       # waits for the card: step 1, not "Naam"
            w.close()

    def test_put_new_card_in_steps(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, QTimer
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            vol = os.path.join(t, "Volumes")
            s = CardSession.create(DirectoryStorage(os.path.join(vol, "OUD")))
            add(s, 1, "OLD", 90)
            s.save()
            os.makedirs(os.path.join(vol, "LEEG"))
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            w.presenter.find_cards = lambda: [cards.classify(os.path.join(vol, n)) for n in sorted(os.listdir(vol))]
            w.presenter.eject = lambda path: True
            w.presenter.backup_dir = os.path.join(t, "backups")
            w.settings.setValue("last_library", t)
            w.presenter.start_compose()
            w.presenter._offer_keep = lambda path, name="": None     # "ook bewaren?" is tested in TaskTests
            add(w.presenter.session, 1, "NIEUW", 100)
            seen = []

            def click():                                  # answer whatever the step window shows now
                f = w.flow
                if f is None or f._loop is None:
                    return
                seen.append([b.state for b in f.badges] + [f.step_note.text()])
                buttons = [b for b in f.body.findChildren(type(w.put_button)) if b.isVisible()]
                texts = [b.text() for b in buttons]
                for want in ("LEEG", "Klaar", "Doorgaan"):
                    for b, text in zip(buttons, texts):
                        if want in text:
                            b.click()
                            return
            timer = QTimer()
            timer.timeout.connect(click)
            timer.start(20)
            w._put_on_card()
            timer.stop()
            self.assertIsNone(w.flow)
            self.assertEqual(w.presenter.card_path, os.path.join(vol, "LEEG"))
            self.assertFalse(w.presenter.composing)
            self.assertEqual(seen[0], ["now", "todo", "todo", "Stap 1 van 3"])    # first: which card
            self.assertEqual(seen[-1], ["done", "done", "now", "Stap 3 van 3"])   # last: ticked, at 'Klaar'
            w.close()

    def test_while_writing_the_parts_are_ticked_off_and_the_card_must_stay_in(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            card = os.path.join(t, "KAART")
            s = CardSession.create(DirectoryStorage(card))
            add(s, 1, "OLD", 90)
            s.save()
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            p = w.presenter
            p.backup_dir = os.path.join(t, "backups")
            self.assertTrue(p.open_card(card))
            p.rename_song(1, 1, "NIEUW")
            seen = []
            p.view = w
            from kn_songboek.gui.dialogs import FlowDialog
            w.flow = FlowDialog(w, "x", [("step_write", "Op kaart zetten"), ("step_done", "Klaar")])
            real = w.flow.progress

            def watch(i, n, text):                         # what the list shows at each new part (GUI thread)
                real(i, n, text)
                if i < 0:
                    hold = w.flow.hold.text() if w.flow.hold is not None else ""
                    seen.append([lab.text()[0] for lab in w.flow.phase_labels] + [hold])
            w.flow.progress = watch
            p.eject = lambda path: False
            p._done = lambda path: None
            self.assertTrue(p.put_on_card())
            # space, back-up, write, verify: each one '●' in turn, the ones before it ticked
            self.assertEqual([x[:4] for x in seen], [["●", "○", "○", "○"], ["✓", "●", "○", "○"],
                                                     ["✓", "✓", "●", "○"], ["✓", "✓", "✓", "●"]])
            self.assertTrue(all(x[4] == "Haal de kaart er nog niet uit." for x in seen))
            self.assertEqual([b.state for b in w.flow.badges], ["now", "todo"])
            w.flow.hide()
            w.flow = None
            w.close()

    def test_card_acting_up_and_back_ups_open_a_step_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            card = os.path.join(t, "KAART")
            s = CardSession.create(DirectoryStorage(card))
            add(s, 1, "OLD", 90)
            s.save()
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            w.presenter.backup_dir = os.path.join(t, "backups")
            self.assertTrue(w.presenter.open_card(card))
            titles = []

            def finish(text, other=""):                      # the 'Klaar' of the step window
                titles.append((w.flow.windowTitle(), [b.state for b in w.flow.badges], text))
                return False
            from kn_songboek.gui import dialogs
            real = dialogs.FlowDialog.finish
            dialogs.FlowDialog.finish = lambda self, text, other="": finish(text, other)
            try:
                w.acts["check_card"].trigger()
            finally:
                dialogs.FlowDialog.finish = real
            self.assertEqual(titles[0][0], "Kaart doet raar?")
            self.assertIn("in orde", titles[0][2])
            self.assertIsNone(w.flow)
            w.close()


if __name__ == "__main__":
    unittest.main()


class PracticeCardTests(unittest.TestCase):
    """"Eerst oefenen": a made-up computer with its own card reader, library and back-ups. The three
    tasks go exactly as they do for real; nothing touches a real card or the real library."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.view = TaskView()
        self.view.answer = True
        self.p = MainPresenter(self.view, backup_dir=os.path.join(self.tmp.name, "backups"))
        self.real_find = self.p.find_cards

    def tearDown(self):
        self.tmp.cleanup()

    def test_organize_as_for_real_then_the_card_comes_out(self):
        from kn_songboek.core import practice
        p, view = self.p, self.view
        self.assertTrue(p.start_practice())
        self.assertTrue(p.practice)
        self.assertEqual(view.page, "start")
        self.assertIn("zonder dat er iets met je echte kaarten gebeurt", view.done[-1])
        self.assertIsNotNone(p.library)                       # the practice library, with one kept card
        self.assertEqual([c.label for c in p.library.cards], [practice.KEPT_CARD])
        self.assertTrue(p.start_organize())                    # the same task, the same code
        self.assertEqual(p.card_name(), practice.SONGS_CARD)
        self.assertEqual(sum(1 for _ in p.session.db.iter_songs()), 9)
        p.rename_song(1, 1, "MIJN FEEST")
        self.assertTrue(p.put_on_card())
        self.assertIn("Je kunt de kaart eruit halen", view.done[-1])
        self.assertEqual(p.world.in_reader(), [])             # taken out: on the shelf
        self.assertEqual(p.world.on_shelf(), [practice.SONGS_CARD])
        self.assertEqual(view.page, "start")
        self.assertTrue(os.listdir(p.world.backups))          # a back-up, as for real (of the practice card)
        self.assertFalse(os.path.exists(os.path.join(self.tmp.name, "backups")))
        self.assertTrue(p.stop_practice())
        self.assertFalse(p.practice)
        self.assertIs(p.find_cards, self.real_find)
        self.assertEqual(p.backup_dir, os.path.join(self.tmp.name, "backups"))

    def test_no_card_in_the_reader_asks_as_for_real_and_swaps_with_a_click(self):
        from kn_songboek.core import practice
        p, view = self.p, self.view
        p.start_practice()
        p.world.insert(None)                                   # an empty SD card in: no KN7000 card
        view.answers = [1, 0]                                  # Kaart wisselen…, then Opnieuw zoeken
        view.choice = 0                                        # the songs card off the shelf
        self.assertTrue(p.start_organize())
        self.assertEqual(p.card_name(), practice.SONGS_CARD)
        self.assertEqual(p.world.on_shelf(), [])             # the empty card is not kept on the shelf
        self.assertIn("klik je op de knop Kaart wisselen", view.asks[0])          # practising: how a card goes in
        self.assertIn("Wat er nu wel in zit: SD-KAART (lege kaart)", view.asks[0])   # not a riddle

    def test_swapping_empty_cards_does_not_make_the_list_longer(self):
        from kn_songboek.core import practice
        p = self.p
        p.start_practice()
        for _ in range(4):                                     # a new, empty card in, again and again
            self.assertEqual(p.world.insert(None), "SD-KAART")
        p.world.insert(practice.SONGS_CARD)
        self.assertEqual(p.world.on_shelf(), [])
        self.assertEqual(p.world.in_reader(), [practice.SONGS_CARD])

    def test_compose_from_the_kept_card_and_keep_it(self):
        from kn_songboek.core import practice
        p, view = self.p, self.view
        p.start_practice()
        view.choice = 1                                        # Beginnen met the kept card
        self.assertTrue(p.start_compose())
        self.assertTrue(p.composing)
        p.world.insert(None)                                   # a new, empty SD card in the reader
        view.texts = ["Mijn set"]                              # kept in the library as "Mijn set"
        self.assertTrue(p.put_on_card())
        self.assertIn("Mijn set", [c.label for c in p.library.cards])
        self.assertEqual(p.world.in_reader(), [])
        self.assertEqual(p.world.on_shelf(), [practice.SONGS_CARD, "SD-KAART"])

    def test_archive_into_the_practice_library(self):
        p, view = self.p, self.view
        p.start_practice()
        view.texts = ["Oefenkaart bewaard"]
        folder = p.start_archive(p.world.library)
        self.assertEqual(os.path.dirname(folder), p.world.library)

    def test_a_folder_that_is_not_a_practice_world_is_never_replaced(self):
        from kn_songboek.core import practice
        with tempfile.TemporaryDirectory() as t:
            mine = os.path.join(t, "oefenen")
            os.makedirs(mine)
            with open(os.path.join(mine, "brief.txt"), "w") as fh:
                fh.write("van mij")
            w = practice.PracticeWorld.make(mine)
            self.assertEqual(w.root, mine + " 2")
            self.assertTrue(os.path.exists(os.path.join(mine, "brief.txt")))
            again = practice.PracticeWorld.make(w.root)       # its own world: fresh again
            self.assertEqual(again.root, w.root)
