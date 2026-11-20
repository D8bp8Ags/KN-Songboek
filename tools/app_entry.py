"""Start of the built app (tools/build_app.py): the window, as `kn-songboek` does.

`--self-test` (used by the GitHub build) opens the main window and the manual and stops: exit code 0 when the
packed app has everything it needs, 1 when not. `--self-test --screenshot FILE` also saves a picture of the
window, to see how it looks on that system."""
import sys


def self_test(argv) -> int:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    from kn_songboek.gui.dialogs import HelpDialog
    from kn_songboek.gui.qt_app import MainWindow
    app = QApplication(argv[:1])
    win = MainWindow()
    win.resize(1280, 800)
    win.show()
    for _ in range(20):
        app.processEvents()
    if "--screenshot" in argv:
        out = argv[argv.index("--screenshot") + 1]
        loop_done = []
        QTimer.singleShot(1500, lambda: loop_done.append(win.grab().save(out)))
        while not loop_done:
            app.processEvents()
        print("self-test: screenshot %s" % ("saved" if loop_done[0] else "FAILED"), flush=True)
    manual = HelpDialog(win, "start")
    ok = bool(manual.text)
    print("self-test: window ok, manual %s" % ("ok" if ok else "MISSING"), flush=True)
    return 0 if ok else 1


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        sys.exit(self_test(sys.argv))
    from kn_songboek.gui.qt_app import main
    sys.exit(main())
