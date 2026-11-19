"""Screen tests (offscreen Qt): the start screen's task buttons, the progress line in the status bar and
folding buttons open in the info panel's Lijst."""
import os
import tempfile
import unittest

from helpers import gui_test
import test_presenter


@gui_test
class StartScreenTests(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        self.tmp = tempfile.TemporaryDirectory()
        self.w = MainWindow(QSettings(os.path.join(self.tmp.name, "s.ini"), QSettings.IniFormat))

    def tearDown(self):
        self.w.close()
        self.tmp.cleanup()

    def test_each_task_button_starts_its_task(self):
        called = []
        self.w._archive = lambda: called.append("start_archive")
        self.w.library_folder = lambda: None
        for key, method in self.w.presenter.TASKS:
            if method != "start_archive":
                setattr(self.w.presenter, method, lambda m=method: called.append(m))
            self.w.task_buttons[key].click()
        self.assertEqual(called, [m for _k, m in self.w.presenter.TASKS])

    def test_back_to_start_is_grey_on_the_start_screen(self):
        self.w.show_page("start")
        self.assertFalse(self.w.acts["start"].isEnabled())
        self.w.show_page("organize")
        self.assertTrue(self.w.acts["start"].isEnabled())

    def test_about_shows_the_backup_folder_before_the_first_backup(self):
        from unittest import mock

        from kn_songboek.gui import dialogs
        missing = os.path.join(self.tmp.name, "nog-geen-backups")
        self.w.presenter.backup_dir = missing
        dlg = dialogs.AboutDialog(self.w)
        from PySide6.QtWidgets import QPushButton
        buttons = [b for b in dlg.findChildren(QPushButton) if b.text() == self.w.presenter.t(dialogs.SHOW_FOLDER)]
        self.assertTrue(buttons)
        with mock.patch.object(dialogs, "show_in_finder") as shown:
            buttons[-1].click()
        shown.assert_called_once_with(missing)
        self.assertTrue(os.path.isdir(missing))                          # made, so Finder can show it

    def test_progress_sits_in_the_status_bar_and_does_not_move_the_page(self):
        self.w.resize(900, 600)
        self.w.show()
        top = self.w.pages.mapTo(self.w, self.w.pages.rect().topLeft()).y()
        self.w.busy_bar.start("Bezig")
        self.w.busy_bar.progress(1, 4, "")
        self.assertIs(self.w.busy_bar.parent(), self.w.statusBar())
        self.assertEqual(self.w.pages.mapTo(self.w, self.w.pages.rect().topLeft()).y(), top)
        self.assertEqual(self.w.busy_bar.pct.text(), "25%")
        self.w.busy_bar.hide()


    def test_name_column_grows_back_after_the_table_was_narrow(self):
        from PySide6.QtWidgets import QApplication
        t = self.w.songs
        h = t.horizontalHeader()
        t.setParent(None)                            # on its own, so its width is ours to set
        t.resize(200, 400)
        t.show()
        QApplication.processEvents()
        t.fit_name()
        narrow = h.sectionSize(2)
        t.resize(900, 400)
        QApplication.processEvents()
        t.fit_name()
        self.assertGreater(h.sectionSize(2), narrow)
        self.assertEqual(h.sectionSize(2), t.name_width)
        h.resizeSection(2, 44)                       # a squeezed width saved last time
        self.w._restore_columns()
        self.assertEqual(h.sectionSize(2), t.name_width)


@gui_test
class ListFoldTests(unittest.TestCase):
    def test_a_button_folds_open_beneath_itself_and_shut_again(self):
        panel, win = test_presenter.InfoPanelTests._panel()
        song_panel = win.presenter.song_panel

        def with_settings(slot):
            d = song_panel(slot)
            for m in d["banks"][0]["memories"]:
                m["basic"] = m["settings"] = [("Begeleiding", [("Variatie", "2", True)])]
            return d
        win.presenter.song_panel = with_settings
        panel.show_info(("Song", []), (1, 1))
        panel._load_details()
        panel._set_view("list")
        self.assertNotIn("Variatie", panel.bank_list.text())          # folded: quick to build
        panel._open_memory("mem:0:1")
        self.assertIn("Variatie", panel.bank_list.text())
        self.assertEqual(panel.bank_list.text().count("Variatie"), 1)  # only that button
        self.assertEqual((panel.bank, panel.button), (0, 1))          # Knoppen shows the same one
        panel._open_memory("mem:0:1")
        self.assertNotIn("Variatie", panel.bank_list.text())
        panel.show_info(("Other", []), (1, 2))                         # another song starts folded
        panel._load_details()
        self.assertEqual(panel.unfolded, set())


if __name__ == "__main__":
    unittest.main()
