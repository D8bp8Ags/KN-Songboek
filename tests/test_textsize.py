"""Weergave › Lettergrootte reaches every part of the app (gui/style.py): letters of every widget kind,
sizes in style sheets, and fixed sizes in the code (style.px)."""
import os
import re
import tempfile
import unittest

try:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSettings
    from PySide6.QtWidgets import QApplication, QWidget
    HAVE_QT = True
except ImportError:                                   # pragma: no cover
    HAVE_QT = False

HERE = os.path.dirname(os.path.abspath(__file__))
GUI = os.path.join(HERE, "..", "src", "kn_songboek", "gui")


@unittest.skipUnless(HAVE_QT, "PySide6 not installed")
class TextSizeTests(unittest.TestCase):
    def setUp(self):
        from kn_songboek.gui import style
        self.style = style
        self.app = QApplication.instance() or QApplication([])
        style.apply(self.app)

    def tearDown(self):
        self.style.set_text_size("normal")
        self.style._fonts(self.app)
        self.style._restyle(self.app)

    def test_every_widget_kind_gets_the_size(self):
        st = self.style
        for name, size in (("normal", 15), ("xlarge", 20)):
            st.set_text_size(name)
            st._fonts(self.app)
            for cls in st.FONT_CLASSES:
                self.assertEqual(self.app.font(cls).pointSizeF(), size, (name, cls))

    def test_system_resetting_the_letters_is_undone(self):
        """macOS puts its own smaller letters back on lists, labels and buttons right after the start and on
        light/dark, and tells the windows (not the app): the sizes come back."""
        from PySide6.QtCore import QCoreApplication, QEvent
        from PySide6.QtGui import QFont
        st = self.style
        st.set_text_size("xlarge")
        st._fonts(self.app)
        st.apply(self.app)
        w = QWidget()
        small = QFont(self.app.font())
        small.setPointSizeF(11)
        for cls in ("QAbstractItemView", "QLabel", "QPushButton"):
            self.app.setFont(small, cls)
        QCoreApplication.sendEvent(w, QEvent(QEvent.ThemeChange))
        for _ in range(3):
            QCoreApplication.processEvents()
        for cls in ("QAbstractItemView", "QLabel", "QPushButton"):
            self.assertEqual(self.app.font(cls).pointSizeF(), 20, cls)
        w.deleteLater()

    def test_style_sheets_grow(self):
        st = self.style
        st.set_text_size("xlarge")
        self.assertEqual(st.sheet("QPushButton { padding: 10px 20px; border: 1px solid red; }"),
                         "QPushButton { padding: 13px 26px; border: 1px solid red; }")
        st.set_text_size("normal")
        self.assertEqual(st.sheet("min-height: 100px"), "min-height: 100px")

    def test_whole_window_follows(self):
        """At Heel groot no widget in the window or a dialog keeps small letters."""
        from kn_songboek.gui import dialogs
        from kn_songboek.gui.qt_app import MainWindow
        st = self.style
        st.set_text_size("xlarge")
        st._fonts(self.app)
        st._restyle(self.app)
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            tops = [w, dialogs.MoreDialog(w), dialogs.HelpDialog(w, "organize"), dialogs.AboutDialog(w)]
            for top in tops:
                for ch in [top] + top.findChildren(QWidget):
                    f = ch.font()                       # a size from a style sheet is in pixels (Reg Bank buttons: 13)
                    size, least = (f.pointSizeF(), 20) if f.pointSizeF() > 0 else (f.pixelSize(), st.px(13))
                    self.assertGreaterEqual(size, least, (type(top).__name__, ch.metaObject().className(), ch.objectName()))
            for top in tops[1:]:
                top.deleteLater()
            w.close()

    def test_no_fixed_sizes_in_code(self):
        """Sizes in the code go through style.px or style.sheet, so they grow with the letters."""
        call = re.compile(r"\.(resize|setMinimumSize|setFixedSize|setMinimumWidth|setMinimumHeight|setFixedWidth|"
                          r"setFixedHeight|setMaximumWidth|setMaximumHeight|setSizes)\(([^)]*)\)")
        sheet = re.compile(r"setStyleSheet\((?!style\.sheet)[^)]*\d\dpx")
        bad = []
        for fn in sorted(os.listdir(GUI)):
            if not fn.endswith(".py") or fn == "style.py":
                continue
            with open(os.path.join(GUI, fn), encoding="utf-8") as fh:
                for n, line in enumerate(fh, 1):
                    m = call.search(line)
                    if m and re.search(r"(?<![\w.(])\d{2,}(?![\w.])", m.group(2).replace("style.px(", "(")):
                        bad.append("%s:%d %s" % (fn, n, line.strip()))
                    if sheet.search(line):
                        bad.append("%s:%d %s" % (fn, n, line.strip()))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
