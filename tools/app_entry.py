"""Start of the built app (tools/build_app.py): the window, as `kn-songboek` does.

`--self-test` (used by the GitHub build) opens the main window and the manual and stops: exit code 0 when the
packed app has everything it needs, 1 when not."""
import sys


def self_test() -> int:
    from PySide6.QtWidgets import QApplication

    from kn_songboek.gui.dialogs import HelpDialog
    from kn_songboek.gui.qt_app import MainWindow
    app = QApplication(sys.argv[:1])
    win = MainWindow()
    win.show()
    app.processEvents()
    manual = HelpDialog(win, "start")
    ok = bool(manual.text)
    print("self-test: window ok, manual %s" % ("ok" if ok else "MISSING"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    from kn_songboek.gui.qt_app import main
    sys.exit(main())
