"""The delete key: Del and the Mac 'delete' (Backspace) delete songs in the song table, but clear a
favourite or a song-list row when those have the focus, and still edit text in the search box."""
import os
import tempfile
import unittest

from helpers import card_with_songs, gui_test


@gui_test
class DeleteKeyTests(unittest.TestCase):
    def test_keys(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        app = QApplication.instance() or QApplication([])
        st, s = card_with_songs({1: ["A", "B", "C"]})
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            w.confirm = lambda text: True
            w.show()
            w.activateWindow()
            app.processEvents()
            for key, row in ((Qt.Key_Backspace, 0), (Qt.Key_Delete, 1)):
                w.songs.selectRow(row)
                w.songs.setFocus()
                QTest.keyClick(w.songs, key)
                app.processEvents()
                self.assertFalse(s.db.song(0, row).used, key)
            s.set_favorite(1, 1, (1, 3))
            s.set_song_list(1, [(1, 3)])
            w.presenter.refresh()
            w.lists_dock.show()
            w.fav_table.setCurrentCell(0, 0)
            w.fav_table.setFocus()
            QTest.keyClick(w.fav_table, Qt.Key_Delete)
            self.assertIsNone(s.favorites()[0][1][0])
            w.song_list.setCurrentRow(0)
            w.song_list.setFocus()
            QTest.keyClick(w.song_list, Qt.Key_Backspace)
            self.assertEqual(s.playlists()[0], [])
            w.search.setFocus()
            w.search.setText("ab")
            QTest.keyClick(w.search, Qt.Key_Backspace)
            self.assertEqual(w.search.text(), "a")
            self.assertTrue(s.db.song(0, 2).used)
            s._undo.clear()
            w.close()


if __name__ == "__main__":
    unittest.main()
