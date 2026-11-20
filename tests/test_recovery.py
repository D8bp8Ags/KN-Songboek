"""Crash recovery (core/recovery.py): changes not on the card yet come back after the app stopped unexpectedly.

A "crash" is simulated by throwing the presenter away without leaving or quitting, and starting a new
one on the same data folder, as the app does at its next start."""
import hashlib
import os
import tempfile
import unittest

from helpers import gui_test
from kn_songboek.core import CardSession, cards, recovery
from kn_songboek.gui.presenter import MainPresenter
from kn_songboek.storage import DirectoryStorage
from kn_songboek.storage.memory import MemoryStorage
from test_library import add
from test_tasks import TaskView


def tree(root):
    """Every file under root with its content hash: to show a card was not touched."""
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.vol = os.path.join(t, "Volumes")
        self.card = os.path.join(self.vol, "KN7000")
        s = CardSession.create(DirectoryStorage(self.card))
        add(s, 1, "WALTZ", 90)
        add(s, 1, "TANGO", 120)
        add(s, 2, "ROCK", 140)
        s.save()
        self.empty = os.path.join(self.vol, "LEEG")
        os.makedirs(self.empty)
        self.library = os.path.join(t, "Bibliotheek")
        self.drafts = os.path.join(t, "concept")
        self.p, self.view = self.start()

    def start(self):
        """The app starting (again): a new window on the same data folder."""
        view = TaskView()
        p = MainPresenter(view, backup_dir=os.path.join(self.tmp.name, "backups"), draft_dir=self.drafts)
        p.find_cards = lambda: [cards.classify(os.path.join(self.vol, n)) for n in sorted(os.listdir(self.vol))]
        p.eject = lambda path: True
        p.is_drive = lambda path: False
        return p, view

    def tearDown(self):
        self.tmp.cleanup()

    def kept(self):
        return recovery.left_behind(self.drafts)

    def names(self, s):
        return [(f + 1, n + 1, x.name) for f, n, x in s.db.iter_songs()]

    # ------------------------------------------------------------------ an opened card
    def test_changes_to_a_card_come_back_after_a_crash_and_can_be_put_on_it(self):
        before = tree(self.card)
        self.assertTrue(self.p.start_organize())
        self.assertEqual(self.kept(), [])                       # nothing changed yet: nothing kept
        self.p.rename_song(1, 1, "WALS")
        self.p.move_songs([(1, 2)], 3)
        self.p.rename_folder(3, "LATIN")
        self.assertEqual(len(self.kept()), 1)
        self.assertEqual(tree(self.card), before)               # the card itself is never written
        want = self.names(self.p.session)
        # crash: the app is gone without asking anything; it starts again
        p, view = self.start()
        view.answers = [0]                                      # "Ja, verdergaan"
        self.assertTrue(p.offer_drafts())
        self.assertIn("3 wijzigingen aan de kaart KN7000", view.asks[0])
        self.assertEqual(view.page, "organize")
        self.assertEqual(p.card_path, self.card)
        self.assertEqual(self.names(p.session), want)
        self.assertEqual(p.session.db.folders[2].name, "LATIN")
        self.assertEqual(len(p.session.history()), 3)
        self.assertIn("Je wijzigingen zijn terug", view.done[-1])
        self.assertEqual(len(self.kept()), 1)                   # only this window's own copy now
        # undo still works step by step
        p.undo()
        self.assertEqual(p.session.db.folders[2].name, "")
        p.rename_folder(3, "LATIN")
        self.assertEqual(tree(self.card), before)
        self.assertTrue(p.put_on_card())
        on_card = CardSession.open(DirectoryStorage(self.card))
        self.assertEqual(self.names(on_card), want)
        self.assertEqual(on_card.validate(), [])                 # the moved song's files moved too
        self.assertEqual(self.kept(), [])                       # on the card: nothing left to bring back

    def test_throw_away_asks_once_more_and_later_keeps_it(self):
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        p, view = self.start()
        view.answers = [None]                                   # "Later beslissen"
        self.assertFalse(p.offer_drafts())
        self.assertEqual(len(self.kept()), 1)
        self.assertIsNone(p.session)
        p, view = self.start()
        view.answer = False                                     # "Nee, weggooien", then "not sure after all"
        view.answers = [1, None]
        self.assertFalse(p.offer_drafts())
        self.assertEqual(len(view.asks), 2)                     # asked again
        self.assertEqual(len(self.kept()), 1)
        p, view = self.start()
        view.answer = True
        view.answers = [1]
        self.assertFalse(p.offer_drafts())
        self.assertEqual(self.kept(), [])
        self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(0, 0).name, "WALTZ")

    def test_card_not_in_the_computer_is_asked_for(self):
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        away = os.path.join(self.tmp.name, "in de la")
        os.rename(self.card, away)
        p, view = self.start()
        moved = []

        def ask(text, buttons):
            view.asks.append(text)
            if len(view.asks) == 1:
                return 0                                        # Ja, verdergaan
            if not moved:
                moved.append(os.rename(away, self.card))       # the user puts the card in
                return 0                                        # Opnieuw proberen
            return None
        view.ask = ask
        self.assertTrue(p.offer_drafts())
        self.assertIn("Doe eerst de SD-kaart KN7000 in de computer", view.asks[1])
        self.assertEqual(p.session.db.song(0, 0).name, "WALS")

    def test_another_or_changed_card_is_refused(self):
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        other = CardSession.open(DirectoryStorage(self.card))   # meanwhile the card was changed elsewhere
        other.rename_song(2, 1, "POP")
        other.save()
        p, view = self.start()
        view.answers = [0, None]                                # Ja, verdergaan; then Later beslissen
        self.assertFalse(p.offer_drafts())
        self.assertIn("niet dezelfde kaart", view.asks[1])
        self.assertIsNone(p.session)
        self.assertEqual(len(self.kept()), 1)                   # kept: the right card may still turn up
        self.assertEqual(CardSession.open(DirectoryStorage(self.card)).db.song(1, 0).name, "POP")

    def test_quitting_or_leaving_on_purpose_keeps_nothing(self):
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        self.view.answers = [1]                                 # leave: throw the changes away
        self.assertTrue(self.p.leave())
        self.assertEqual(self.kept(), [])
        self.p.start_organize()
        self.p.rename_song(1, 1, "WALS")
        self.p.forget_draft()                                   # Stop › "Toch afsluiten"
        self.assertEqual(self.kept(), [])
        self.p.undo()                                           # undo everything: nothing unsaved any more
        self.assertEqual(self.kept(), [])

    def test_nothing_is_kept_while_practising(self):
        self.p.start_practice()
        self.p.start_organize()
        self.p.rename_song(1, 1, "X")
        self.assertEqual(self.kept(), [])

    # ------------------------------------------------------------------ a new card
    def test_a_new_card_comes_back_with_its_songs_from_the_library(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 0                                    # Leeg beginnen
        self.assertTrue(self.p.start_compose())
        self.p.compose_name = "BRUILOFT"
        self.assertEqual(self.p.import_from_library([0, 1, 2], 5), 3)
        want = self.names(self.p.session)
        size = os.path.getsize(os.path.join(self.kept()[0].path, "draft.json"))
        self.assertLess(size, 20000)                            # the songs are pointed at, not copied
        p, view = self.start()
        p.open_library(self.library)
        view.answers = [0]
        self.assertTrue(p.offer_drafts())
        self.assertIn("Een nieuwe kaart met 3 songs", view.asks[0])
        self.assertTrue(p.composing)
        self.assertEqual(view.page, "compose")
        self.assertEqual(p.compose_name, "BRUILOFT")
        self.assertEqual(self.names(p.session), want)
        p.rename_volume = lambda path, name: None
        view.choice = [c.kind for c in p.find_cards()].index(cards.EMPTY)
        self.assertTrue(p.put_on_card())
        made = CardSession.open(DirectoryStorage(self.empty))
        self.assertEqual(self.names(made), want)
        self.assertEqual(made.validate(), [])
        self.assertEqual(self.kept(), [])

    def test_a_library_song_changed_since_is_said(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        self.p.open_library(self.library)
        self.view.choice = 0
        self.p.start_compose()
        self.p.import_from_library([0], 1)
        src = next(op for op in self.p.session.pending if op.kind == "import")
        real = src.src_storage._real(src.src)
        with open(real, "ab") as fh:                            # changed afterwards
            fh.write(b"x")
        p, view = self.start()
        view.answers = [0, None]
        self.assertFalse(p.offer_drafts())
        self.assertIn("veranderd of weg", view.asks[1])

    def test_songs_that_only_lived_in_memory_are_kept_themselves(self):
        self.p.start_organize()
        mem = MemoryStorage({"x.SQT": b"sqt!", "x.PMT": b"pmt!"})
        self.p.session.import_song(mem, {"SQT": "x.SQT", "PMT": "x.PMT"}, "UIT SET", 4)
        p, view = self.start()
        view.answers = [0]
        self.assertTrue(p.offer_drafts())
        self.assertTrue(p.put_on_card())
        on_card = CardSession.open(DirectoryStorage(self.card))
        self.assertEqual(on_card.db.song(3, 0).name, "UIT SET")
        paths = on_card.song(4, 1).files
        self.assertEqual(sorted(on_card.storage.read(x) for x in paths), [b"pmt!", b"sqt!"])

    def test_a_half_written_draft_is_skipped(self):
        os.makedirs(os.path.join(self.drafts, "kapot"))
        with open(os.path.join(self.drafts, "kapot", "draft.json"), "w") as fh:
            fh.write('{"version": 1, "kind": "org')
        self.assertEqual(self.kept(), [])
        p, view = self.start()
        self.assertFalse(p.offer_drafts())
        self.assertEqual(view.asks, [])


class DefaultPlaceTests(unittest.TestCase):
    def test_next_to_the_back_ups_and_not_used_by_tests_without_a_draft_dir(self):
        self.assertEqual(os.path.basename(recovery.drafts_dir("/x/KN Songboek/backups")), "concept")
        self.assertEqual(os.path.dirname(recovery.drafts_dir(os.path.join("x", "KN Songboek", "backups"))),
                         os.path.join("x", "KN Songboek"))
        with tempfile.TemporaryDirectory() as t:
            p = MainPresenter(TaskView(), backup_dir=t)
            self.assertIsNone(p.drafts)


@gui_test
class QuitTests(unittest.TestCase):
    def test_the_question_says_later_instead_of_cancel(self):
        from PySide6.QtWidgets import QApplication, QMessageBox
        from kn_songboek.gui.qt_app import MainWindow
        from unittest import mock
        QApplication.instance() or QApplication([])
        w = MainWindow()
        seen = []

        def exec_(box):
            seen.extend(b.text() for b in box.buttons())
            return 0
        with mock.patch.object(QMessageBox, "exec", exec_):
            self.assertIsNone(w.ask("vraag", ["Ja, verdergaan", "Nee, weggooien"], cancel="Later beslissen"))
        self.assertIn("Later beslissen", seen)
        self.assertNotIn("Annuleren", seen)
        w._rebuilt = True
        w.close()


if __name__ == "__main__":
    unittest.main()
