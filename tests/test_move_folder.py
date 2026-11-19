"""Dragging a whole folder onto another folder number (CardSession.move_folder)."""
import os
import tempfile
import unittest

from helpers import card_with_songs, gui_test
from kn_songboek.core import CardSession
from kn_songboek.formats import layout


def files(st, folder):
    return sorted(st.listdir(layout.folder_dir(folder - 1)))


class MoveFolderTests(unittest.TestCase):
    def setUp(self):
        self.st, self.s = card_with_songs({1: ["A1", "A2"], 2: ["B1"]})
        self.s.rename_folder(1, "ZOMERAVOND")
        self.s.set_favorite(1, 1, (1, 2))
        self.s.set_song_list(1, [(1, 1), (2, 1)])
        self.s.save()
        self.s = CardSession.open(self.st)

    def test_move_to_empty_folder(self):
        self.s.move_folder(1, 20)
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(s.db.folders[19].name, "ZOMERAVOND")
        self.assertEqual([x.name for x in s.db.folders[19].songs[:2]], ["A1", "A2"])
        self.assertFalse(any(x.used for x in s.db.folders[0].songs))
        self.assertEqual(s.db.folders[0].name, "")
        self.assertEqual(files(self.st, 1), [])
        self.assertEqual(len(files(self.st, 20)), 6)
        self.assertEqual(s.favorites()[0][1][0], ("song", 19, 1))
        self.assertEqual(s.playlists()[0], [(20, 1), (2, 1)])
        self.assertEqual(s.validate(), [])

    def test_swap_with_folder_in_use(self):
        self.s.move_folder(1, 2)
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(s.db.folders[0].songs[0].name, "B1")
        self.assertEqual(s.db.folders[1].name, "ZOMERAVOND")
        self.assertEqual([x.name for x in s.db.folders[1].songs[:2]], ["A1", "A2"])
        self.assertEqual(s.playlists()[0], [(2, 1), (1, 1)])
        self.assertEqual(s.favorites()[0][1][0], ("song", 1, 1))
        self.assertEqual(s.validate(), [])
        self.assertEqual(self.st.read(layout.song_paths(0, 0, s.db.song(0, 0))["SQT"]), b"sqt")

    def test_undo(self):
        before = self.s.db.to_bytes()
        self.s.move_folder(1, 20)
        self.s.undo()
        self.assertEqual(self.s.db.to_bytes(), before)
        self.assertEqual(self.s.pending, [])

    def test_same_folder_does_nothing(self):
        self.s.move_folder(3, 3)
        self.assertFalse(self.s.dirty)


class InsertFolderTests(unittest.TestCase):
    def setUp(self):
        self.st, self.s = card_with_songs({1: ["A"], 2: ["B"], 3: ["C"], 4: ["D"], 5: ["E"]})
        self.s.set_favorite(1, 1, (5, 1))
        self.s.set_song_list(1, [(2, 1), (5, 1)])
        self.s.rename_folder(5, "LAATSTE")
        self.s.save()
        self.s = CardSession.open(self.st)

    def names(self, s, n=6):
        return [s.db.folders[f].songs[0].name if s.db.folders[f].songs[0].used else "" for f in range(n)]

    def test_move_up_between(self):
        self.assertEqual(self.s.insert_folder(5, 2), 2)          # E between A and B
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(self.names(s), ["A", "E", "B", "C", "D", ""])
        self.assertEqual(s.db.folders[1].name, "LAATSTE")
        self.assertEqual(s.favorites()[0][1][0], ("song", 1, 0))
        self.assertEqual(s.playlists()[0], [(3, 1), (2, 1)])
        self.assertEqual(s.validate(), [])

    def test_move_down_between(self):
        self.assertEqual(self.s.insert_folder(1, 4), 3)          # A between C and D
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(self.names(s), ["B", "C", "A", "D", "E", ""])
        self.assertEqual(s.playlists()[0], [(1, 1), (5, 1)])
        self.assertEqual(s.validate(), [])
        self.assertEqual(len(files(self.st, 3)), 3)

    def test_no_change_and_undo(self):
        self.assertEqual(self.s.insert_folder(2, 2), 2)
        self.assertEqual(self.s.insert_folder(2, 3), 2)
        self.assertFalse(self.s.dirty)
        before = self.s.db.to_bytes()
        self.s.insert_folder(5, 1)
        self.s.undo()
        self.assertEqual(self.s.db.to_bytes(), before)
        self.assertEqual(self.s.pending, [])

    def test_after_last(self):
        self.assertEqual(self.s.insert_folder(1, 100), 99)
        self.s.save()
        s = CardSession.open(self.st)
        self.assertEqual(s.db.folders[98].songs[0].name, "A")
        self.assertEqual(self.names(s, 5), ["B", "C", "D", "E", ""])


@gui_test
class MoveFolderGuiTests(unittest.TestCase):
    def test_presenter_and_drop(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import warnings
        warnings.simplefilter("ignore", DeprecationWarning)
        from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QSettings, Qt
        from PySide6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDragMoveEvent, QDropEvent
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MIME_FOLDER, MainWindow
        QApplication.instance() or QApplication([])
        st, s = card_with_songs({1: ["A1"], 2: ["B1"]})
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            self.assertTrue(w.presenter.move_folder(1, 20))
            self.assertEqual(w.presenter.folder, 20)
            self.assertEqual(w.songs.item(0, 2).text(), "A1")
            self.assertIn("20", w.statusBar().currentMessage())
            self.assertTrue(w.presenter.move_folder(20, 2))
            self.assertIn("geruild", w.statusBar().currentMessage())
            self.assertEqual(s.db.folders[19].songs[0].name, "B1")
            f = w.folders
            w.show()

            def mime(n):
                m = QMimeData()
                m.setData(MIME_FOLDER, QByteArray(str(n).encode()))
                return m

            def at(row, where):
                r = f.visualItemRect(f.item(row))
                return QPoint(r.center().x(), {"top": r.top() + 1, "mid": r.center().y(), "bottom": r.bottom()}[where])

            m = mime(2)
            f.dragEnterEvent(QDragEnterEvent(at(1, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            f.dragMoveEvent(QDragMoveEvent(at(4, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f.drop_rect()[0], "box")
            self.assertIn("lege map 05", w.statusBar().currentMessage())
            f.dragMoveEvent(QDragMoveEvent(at(5, "top"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual((f.drop_rect()[0], f._insert_before), ("line", 6))
            f.dragMoveEvent(QDragMoveEvent(at(5, "bottom"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f._insert_before, 7)
            f.grab()                                           # paints the line
            f.dragMoveEvent(QDragMoveEvent(at(19, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f._insert_before, 21)             # folder 20 is in use: never a swap
            f.dragMoveEvent(QDragMoveEvent(at(19, "top"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertEqual(f._insert_before, 20)
            f.dragLeaveEvent(QDragLeaveEvent())
            self.assertIsNone(f.drop_rect())
            f.dragEnterEvent(QDragEnterEvent(at(1, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            f.dragMoveEvent(QDragMoveEvent(at(6, "mid"), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            f.dropEvent(QDropEvent(QPointF(at(6, "mid")), Qt.MoveAction, m, Qt.LeftButton, Qt.NoModifier))
            self.assertIsNone(f.drop_rect())                   # nothing stays marked after a drop
            self.assertEqual(s.db.folders[6].songs[0].name, "A1")
            self.assertTrue(all(f.item(i).data(Qt.BackgroundRole) is None for i in range(f.count())))
            s.move_folder(7, 2)
            self.assertTrue(w.presenter.insert_folder(20, 2))  # 20 (B1) between 01 and 02 (A1)
            self.assertEqual(s.db.folders[1].songs[0].name, "B1")
            self.assertEqual(s.db.folders[2].songs[0].name, "A1")
            self.assertEqual(w.presenter.folder, 2)
            self.assertTrue(w.presenter.insert_folder(3, 1))   # A1 in front of 01
            self.assertEqual(w.presenter.folder, 1)
            s._undo.clear()
            w.close()


if __name__ == "__main__":
    unittest.main()
