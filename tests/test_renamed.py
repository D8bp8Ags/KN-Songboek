"""A renamed song shows its old name until the change is on the card (songlijst + panel rechts)."""
import os
import unittest

from helpers import card_with_songs, gui_test
from kn_songboek.core import CardSession
from kn_songboek.storage.memory import MemoryStorage


class RenamedSongs(unittest.TestCase):
    def test_rename_shows_old_name_until_saved(self):
        st, s = card_with_songs({1: ["FEEST", "WALS"]})
        self.assertEqual(s.renamed_songs(), {})
        s.rename_song(1, 1, "HET IS FEEST")
        self.assertEqual(s.renamed_songs(), {(1, 1): "FEEST"})
        s.rename_song(1, 1, "FEEST")                     # changed back: nothing to show
        self.assertEqual(s.renamed_songs(), {})
        s.rename_song(1, 1, "HET IS FEEST")
        s.save()
        self.assertEqual(s.renamed_songs(), {})

    def test_undo_takes_the_mark_away(self):
        st, s = card_with_songs({1: ["FEEST"]})
        s.rename_song(1, 1, "HET IS FEEST")
        s.undo()
        self.assertEqual(s.renamed_songs(), {})

    def test_followed_through_moves_and_swaps(self):
        st, s = card_with_songs({1: ["FEEST", "WALS", "POLKA"]})
        s.rename_song(1, 1, "HET IS FEEST")
        s.move_song(1, 1, 4)                             # another folder
        self.assertEqual(s.renamed_songs(), {(4, 1): "FEEST"})
        s.rename_song(1, 2, "WALS DER LIEFDE")
        s.swap_songs(1, 2, 3)
        self.assertEqual(s.renamed_songs(), {(4, 1): "FEEST", (1, 3): "WALS"})
        s.move_song(4, 1, 1, None, True)                 # a copy of a renamed song was renamed too
        self.assertIn("FEEST", s.renamed_songs().values())

    def test_moved_without_rename_is_not_marked(self):
        st, s = card_with_songs({1: ["FEEST", "WALS"]})
        s.swap_songs(1, 1, 2)
        s.move_song(1, 1, 7)
        self.assertEqual(s.renamed_songs(), {})

    def test_imported_song_compares_with_name_it_came_in_with(self):
        st, s = card_with_songs({1: ["FEEST"]})
        src = MemoryStorage({"x.SQT": b"sqt", "x.LSW": b"lsw"})
        s.import_song(src, {"SQT": "x.SQT", "LSW": "x.LSW"}, "NIEUW", 2)
        self.assertEqual(s.renamed_songs(), {})
        s.rename_song(2, 1, "NIEUW LIED")
        self.assertEqual(s.renamed_songs(), {(2, 1): "NIEUW"})


@gui_test
class RenamedInWindow(unittest.TestCase):
    def test_list_and_panel(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        from kn_songboek.gui.widgets import EmptySlotDelegate
        import tempfile
        QApplication.instance() or QApplication([])
        from kn_songboek.storage.directory import DirectoryStorage
        d = tempfile.mkdtemp()
        s = CardSession.create(DirectoryStorage(d))
        src = MemoryStorage({"x.SQT": b"sqt", "x.LSW": b"lsw"})
        s.import_song(src, {"SQT": "x.SQT", "LSW": "x.LSW"}, "FEEST", 1)
        s.save()
        from PySide6.QtCore import QSettings
        w = MainWindow(QSettings(os.path.join(d, "s.ini"), QSettings.IniFormat))
        self.assertTrue(w.presenter.open_card(d))
        w.presenter.rename_song(1, 1, "HET IS FEEST")
        it = w.songs.item(0, 2)
        self.assertEqual(it.text(), "HET IS FEEST")
        self.assertEqual(it.data(EmptySlotDelegate.WAS_ROLE), "(was: FEEST)")
        self.assertEqual(w.presenter.song_rows()[0].old_name, "FEEST")
        w.info.show_info(w.presenter.song_info((1, 1), banks=False), (1, 1))
        self.assertFalse(w.info.renamed.isHidden())
        self.assertEqual(w.info.renamed_old.text(), "FEEST")
        w.info.renamed_button.click()
        QApplication.processEvents()
        self.assertEqual(w.songs.item(0, 2).text(), "FEEST")
        self.assertIsNone(w.songs.item(0, 2).data(EmptySlotDelegate.WAS_ROLE))
        self.assertEqual(w.presenter.song_rows()[0].old_name, "")
        w.info.show_info(w.presenter.song_info((1, 1), banks=False), (1, 1))
        self.assertTrue(w.info.renamed.isHidden())
        w.presenter.session.undo()                       # the restore is a step of its own
        self.assertEqual(w.presenter.song_rows()[0].old_name, "FEEST")
        w.confirm = lambda *a, **k: True                # leaving with the change unsaved: fine here
        w.close()


if __name__ == "__main__":
    unittest.main()
