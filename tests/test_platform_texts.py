"""Mac and Windows each see only their own keys and names: in the app's texts and in the manual (?-button)."""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
MANUAL = os.path.join(HERE, "..", "docs", "nl", "handleiding.md")
MANUAL_EN = os.path.join(HERE, "..", "docs", "en", "manual.md")

try:
    from kn_songboek.gui.widgets import manual_for_this_computer
    HAVE_QT = True
except ImportError:                                   # pragma: no cover
    HAVE_QT = False


class TextTests(unittest.TestCase):
    def test_a_text_with_a_windows_version(self):
        from kn_songboek.gui import i18n
        old = i18n.WINDOWS
        try:
            i18n.WINDOWS = False
            self.assertIn("Option", i18n.tr("nl", "drop_copy", folder=3))
            self.assertEqual(i18n.tr("nl", "btn_show_folder"), "Toon in Finder")
            i18n.WINDOWS = True
            self.assertIn("Alt", i18n.tr("nl", "drop_copy", folder=3))
            self.assertNotIn("Option", i18n.tr("nl", "drop_copy", folder=3))
            self.assertEqual(i18n.tr("nl", "btn_show_folder"), "Toon in Verkenner")
        finally:
            i18n.WINDOWS = old

    def test_no_text_names_both_computers(self):
        from kn_songboek.gui.i18n import TEXTS
        for key, (nl, en) in TEXTS.items():
            for text in (nl, en):
                self.assertFalse("Option/Alt" in text or "Cmd/Ctrl" in text or "Finder of" in text, key)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class ManualTests(unittest.TestCase):
    def setUp(self):
        with open(MANUAL, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_windows_sees_windows_keys_only(self):
        w = manual_for_this_computer(self.text, True)
        self.assertNotIn("<!--", w)
        self.assertNotIn("Cmd", w)
        self.assertNotIn("Finder", w)
        self.assertIn("Ctrl+Y", w)
        self.assertNotIn("geschreven voor de Mac", w)

    def test_mac_sees_mac_keys_only(self):
        m = manual_for_this_computer(self.text, False)
        self.assertNotIn("<!--", m)
        self.assertNotIn("Ctrl", m)
        self.assertIn("Shift+Cmd+Z", m)
        self.assertNotIn("Windows", m)


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class EnglishManualTests(unittest.TestCase):
    """The app in English shows the English manual, with the same chapters as the Dutch one."""

    def setUp(self):
        with open(MANUAL_EN, encoding="utf-8") as fh:
            self.text = fh.read()

    def test_windows_sees_windows_names_in_english(self):
        w = manual_for_this_computer(self.text, True, "en")
        self.assertNotIn("<!--", w)
        self.assertNotIn("Cmd", w)
        self.assertNotIn("Finder", w)
        self.assertIn("File Explorer", w)
        self.assertIn("Recycle Bin", w)
        self.assertNotIn("Verkenner", w)

    def test_mac_sees_mac_keys_only(self):
        m = manual_for_this_computer(self.text, False, "en")
        self.assertNotIn("Ctrl", m)
        self.assertIn("Shift+Cmd+Z", m)

    def test_same_chapters_and_pictures_as_the_dutch_manual(self):
        import re
        with open(MANUAL, encoding="utf-8") as fh:
            nl = fh.read()
        for pattern in (r"^## (\d+)\.", r"\]\((img/[^)]+)\)"):          # chapters, then pictures
            self.assertEqual(re.findall(pattern, self.text, re.M), re.findall(pattern, nl, re.M))

    def test_the_help_window_follows_the_language(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        import tempfile
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        from kn_songboek.gui.dialogs import HelpDialog
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as t:
            w = MainWindow(QSettings(os.path.join(t, "s.ini"), QSettings.IniFormat))
            w.presenter.set_language("en")
            self.assertIn("Getting started", HelpDialog(w, "start").text)
            w.presenter.set_language("nl")
            self.assertIn("Beginnen", HelpDialog(w, "start").text)
            w.close()


if __name__ == "__main__":
    unittest.main()
