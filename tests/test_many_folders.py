"""Several folders at once: move them together on the card, copy them together from the library."""
import os
import tempfile
import unittest

from helpers import card_with_songs, gui_test
from kn_songboek.core import CardSession, SlotError
from kn_songboek.formats import layout


def first_names(s, n=8):
    return [s.db.folders[f].songs[0].name if s.db.folders[f].songs[0].used else "" for f in range(n)]


class InsertFoldersTests(unittest.TestCase):
    def setUp(self):
        self.st, self.s = card_with_songs({1: ["A"], 2: ["B"], 3: ["C"], 4: ["D"], 5: ["E"], 6: ["F"]})
        self.s.rename_folder(5, "VIJF")
        self.s.set_favorite(1, 1, (5, 1))
        self.s.set_song_list(1, [(2, 1), (5, 1), (6, 1)])
        self.s.save()
        self.s = CardSession.open(self.st)

    def test_move_up_as_block(self):
        self.assertEqual(self.s.insert_folders([5, 2], 1), [1, 2])     # B and E in front of A, in order
        self.assertEqual(len(self.s.history()), 1)
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(first_names(s), ["B", "E", "A", "C", "D", "F", "", ""])
        self.assertEqual(s.db.folders[1].name, "VIJF")
        self.assertEqual(s.favorites()[0][1][0], ("song", 1, 0))
        self.assertEqual(s.playlists()[0], [(1, 1), (2, 1), (6, 1)])
        self.assertEqual(s.validate(), [])

    def test_move_down_as_block(self):
        self.assertEqual(self.s.insert_folders([1, 3], 6), [4, 5])     # A and C between E and F
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(first_names(s), ["B", "D", "E", "A", "C", "F", "", ""])
        self.assertEqual(s.db.folders[2].name, "VIJF")
        self.assertEqual(s.validate(), [])
        self.assertEqual(len(self.st.listdir(layout.folder_dir(3))), 3)

    def test_gaps_close_around_block_and_undo(self):
        before = self.s.db.to_bytes()
        self.assertEqual(self.s.insert_folders([2, 4], 7), [5, 6])     # to the end of the folders in use
        self.assertEqual(first_names(self.s), ["A", "C", "E", "F", "B", "D", "", ""])
        self.s.undo()
        self.assertEqual(self.s.db.to_bytes(), before)
        self.assertEqual(self.s.pending, [])

    def test_already_there_does_nothing(self):
        self.assertEqual(self.s.insert_folders([2, 3], 2), [2, 3])
        self.assertEqual(self.s.insert_folders([2, 3], 4), [2, 3])
        self.assertFalse(self.s.dirty)
        with self.assertRaises(SlotError):
            self.s.insert_folders([1, 2], 101)


class ImportFoldersTests(unittest.TestCase):
    def setUp(self):
        _, self.src = card_with_songs({2: ["A", "B"], 5: ["C"], 7: ["D"]})
        self.src.rename_folder(5, "BRUILOFT")

    def test_into_first_empty_folders_in_one_step(self):
        _, dst = card_with_songs({1: ["X"], 3: ["Y"]})
        r = dst.import_folders(self.src, [5, 2, 7])
        self.assertEqual([(x["from"], x["folder"], x["copied"]) for x in r], [(5, 2, 1), (2, 4, 2), (7, 5, 1)])
        self.assertEqual(dst.db.folders[1].name, "BRUILOFT")
        self.assertEqual([x.name for x in dst.db.folders[3].songs[:2]], ["A", "B"])
        self.assertEqual(len(dst.history()), 1)
        dst.undo()
        self.assertFalse(any(x.used for x in dst.db.folders[1].songs))

    def test_from_a_chosen_empty_folder(self):
        _, dst = card_with_songs({1: ["X"], 3: ["Y"]})
        r = dst.import_folders(self.src, [2, 5], start=10)
        self.assertEqual([x["folder"] for x in r], [10, 11])
        r = dst.import_folders(self.src, [7], start=3)                 # 3 is in use: first empty one
        self.assertEqual(r[0]["folder"], 2)

    def test_all_or_nothing(self):
        _, dst = card_with_songs({f: ["X"] for f in range(1, 99)})
        with self.assertRaises(SlotError):
            dst.import_folders(self.src, [2, 5])
        self.assertEqual(dst.history(), [])
        with self.assertRaises(SlotError):
            dst.import_folders(self.src, [3])                          # empty in the source


@gui_test
class ManyFoldersGuiTests(unittest.TestCase):
    def test_drag_several_folders_in_the_list(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import warnings
        warnings.simplefilter("ignore", DeprecationWarning)
        from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QSettings, Qt
        from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MIME_FOLDER, MainWindow
        QApplication.instance() or QApplication([])
        st, s = card_with_songs({1: ["A"], 2: ["B"], 3: ["C"], 4: ["D"]})
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            f = w.folders
            w.show()
            f.item(0).setSelected(True)
            f.item(2).setSelected(True)
            f.setCurrentItem(f.item(2), f.selectionModel().SelectionFlag.Select)
            self.assertEqual(f.chosen_folders(), [1, 3])

            m = QMimeData()
            m.setData(MIME_FOLDER, QByteArray(b"1;3"))

            def at(row, where):
                r = f.visualItemRect(f.item(row))
                return QPoint(r.center().x(), {"top": r.top() + 1, "mid": r.center().y(), "bottom": r.bottom()}[where])

            f.dragEnterEvent(QDragEnterEvent(at(0, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            f.set_show_empty(True)
            f.dragMoveEvent(QDragMoveEvent(at(6, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f.drop_rect()[0], "line")             # several: never "into an empty folder"
            self.assertIn("2 mappen", w.statusBar().currentMessage())
            f.dragMoveEvent(QDragMoveEvent(at(3, "bottom"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f._insert_before, 5)
            f.dropEvent(QDropEvent(QPointF(at(3, "bottom")), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(first_names(s, 4), ["B", "D", "A", "C"])
            self.assertEqual(w.presenter.folder, 3)
            self.assertEqual(f.chosen_folders(), [3, 4])                # they stay chosen where they landed
            self.assertIn("2 mappen staan nu op 3 t/m 4", w.statusBar().currentMessage())
            self.assertEqual(len(s.history()), 1)
            self.assertFalse(w.presenter.insert_folders([3, 4], 4))     # already there
            s._undo.clear()
            w.close()

    def test_library_copies_several_folders(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QPoint, QPointF, QSettings, Qt
        from PySide6.QtGui import QDragEnterEvent, QDragMoveEvent, QDropEvent
        from PySide6.QtWidgets import QApplication
        from kn_songboek.core import CardSession as CS
        from kn_songboek.gui.qt_app import MainWindow
        from kn_songboek.gui.widgets import MIME_LIB_FOLDERS
        from kn_songboek.storage import DirectoryStorage
        from test_library import add
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "lib")
            a = CS.create(DirectoryStorage(os.path.join(root, "Kaart Bruiloft")))
            add(a, 3, "ONE", 100)
            add(a, 3, "TWO", 110)
            add(a, 4, "THREE", 120)
            add(a, 6, "FOUR", 120)
            a.rename_folder(3, "FEEST")
            a.save()
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.confirm = lambda text: True
            self.assertTrue(w.open_library(root))
            self.assertTrue(w.presenter.new_card(os.path.join(tmp, "Nieuw")))
            lp = w.library_panel
            lp.card.setCurrentIndex(lp.card.findData("Kaart Bruiloft"))
            self.assertEqual([lp.part.itemData(i) for i in range(lp.part.count())],
                             [None, "folder:3", "folder:4", "folder:6"])
            lp.parts.setCurrentRow(1)
            lp.parts.item(3).setSelected(True)
            lp.parts.item(0).setSelected(True)                           # "Alle songs" does not count
            self.assertEqual(lp.parts.chosen_folders(), [3, 6])
            self.assertEqual(lp.copy_part.text(), "2 hele mappen toevoegen aan je kaart")
            lp.copy_part.click()
            s = w.presenter.session
            self.assertEqual(s.db.folders[0].name, "FEEST")
            self.assertEqual([x.name for x in s.db.folders[0].songs[:2]], ["ONE", "TWO"])
            self.assertEqual(s.db.folders[1].songs[0].name, "FOUR")
            self.assertEqual(len(s.history()), 1)
            self.assertIn("2 mappen gekopieerd", w.statusBar().currentMessage())
            # dragged onto an empty folder of the card: they start there
            from PySide6.QtCore import QByteArray, QMimeData
            md = QMimeData()
            md.setData(MIME_LIB_FOLDERS, QByteArray("Kaart Bruiloft\n4;6".encode()))
            f = w.folders
            f.set_show_empty(True)
            r = f.visualItemRect(f.item(9))
            pt = QPoint(r.center().x(), r.center().y())
            f.dragEnterEvent(QDragEnterEvent(pt, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
            f.dragMoveEvent(QDragMoveEvent(pt, Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
            self.assertIn("te beginnen bij 10", w.statusBar().currentMessage())
            w.show_error = lambda text: self.fail(text)
            r = f.visualItemRect(f.item(9))                                  # the list may have scrolled
            pt = QPoint(r.center().x(), r.center().y())
            f.dropEvent(QDropEvent(QPointF(pt), Qt.CopyAction, md, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(s.db.folders[9].songs[0].name, "THREE")
            self.assertEqual(s.db.folders[10].songs[0].name, "FOUR")       # same song twice is fine
            self.assertEqual(w.folders.chosen_folders(), [10, 11])
            s._undo.clear()
            w.presenter.library.close()
            w.close()


if __name__ == "__main__":
    unittest.main()
