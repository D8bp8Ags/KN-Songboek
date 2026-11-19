"""Make the screenshots for the manuals from made-up demo cards, with the app in that language.

    QT_QPA_PLATFORM=offscreen python tools/make_screenshots.py [nl|en] [OUTPUT_DIR]
        no language: both, into docs/nl/img (handleiding.md) and docs/en/img (manual.md)

Only invented song and folder names are used: real card contents never go into the repository.
"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(ROOT, "src"), os.path.join(ROOT, "tests")]

from PySide6.QtCore import QSettings, Qt, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from kn_songboek.core import CardSession  # noqa: E402
from kn_songboek.formats import container  # noqa: E402
from kn_songboek.storage import DirectoryStorage  # noqa: E402
from kn_songboek.storage.memory import MemoryStorage  # noqa: E402
from test_library import sqt_file  # noqa: E402
from test_songdata import make_cmp, make_msp, make_pmt, make_tm  # noqa: E402

FOLDERS = {
    "nl": {
        1: ("FEEST", ["HET IS FEEST", "DANSEN", "POLONAISE", "LAATSTE RONDE"]),
        2: ("WALSEN", ["WEENSE WALS", "AVONDWALS", "KERMISWALS"]),
        3: ("LATIN", ["SAMBA ZON", "RUMBA ROOD", "CHA CHA"]),
        4: ("ROCK", ["ROCK 1", "ROCK 2"]),
        5: ("SCHLAGER", ["ZOMERLIED", "BERGLIED"]),
    },
    "en": {
        1: ("PARTY", ["PARTY TIME", "DANCING", "CONGA LINE", "LAST ORDERS"]),
        2: ("WALTZES", ["VIENNA WALTZ", "EVENING WALTZ", "FAIR WALTZ"]),
        3: ("LATIN", ["SAMBA SUN", "RUMBA RED", "CHA CHA"]),
        4: ("ROCK", ["ROCK 1", "ROCK 2"]),
        5: ("POP", ["SUMMER SONG", "MOUNTAIN SONG"]),
    },
}
# the second library card, the renamed song and folder, and the songs put on the new card
WORDS = {
    "nl": dict(lib="Bibliotheek", card="Kaart", new=("NIEUW", ["HET IS FEEST", "NIEUW LIED"]),
               calm=("RUSTIG", ["SLOWFOX", "AVONDWALS"]), renamed="DANSEN!", wedding="BRUILOFT",
               chosen=("HET IS FEEST", "AVONDWALS", "SLOWFOX")),
    "en": dict(lib="Library", card="Card", new=("NEW", ["PARTY TIME", "NEW SONG"]),
               calm=("QUIET", ["SLOW FOX", "EVENING WALTZ"]), renamed="DANCING!", wedding="WEDDING",
               chosen=("PARTY TIME", "EVENING WALTZ", "SLOW FOX")),
}


def demo_card(path, folders, tempo=120):
    s = CardSession.create(DirectoryStorage(path))
    src = MemoryStorage({"x.SQT": sqt_file(tempo, True), "x.PMT": container.build_kd(make_pmt()),
                         "x.CMP": container.build_kd(make_cmp()), "x.MSP": container.build_kd(make_msp()),
                         "x.TM": container.build_kd(make_tm())})
    files = {"SQT": "x.SQT", "PMT": "x.PMT", "CMP": "x.CMP", "MSP": "x.MSP", "TM": "x.TM", "LSW": "x.LSW"}
    for f, (name, songs) in folders.items():
        s.rename_folder(f, name)
        for n in songs:
            src.write(n + ".LSW", n.encode())       # every demo song different, so none are grouped
            s.import_song(src, dict(files, LSW=n + ".LSW"), n, f)
    s.set_favorite(1, 1, (1, 1))
    s.set_favorite(1, 2, (2, 1))
    s.set_song_list(1, [x for x in [(1, 1), (2, 2), (3, 1)] if x[0] in folders and x[1] <= len(folders[x[0]][1])])
    s.save(backup=False)


def shot(widget, out, name):
    win = widget.window()
    if hasattr(win, "toast"):
        win.toast.hide()                                   # no "Ongedaan maken" message in the pictures
    QApplication.processEvents()
    pm = widget.grab()
    pm.save(os.path.join(out, name))
    print("wrote", name)


def main(out, lang="nl"):
    os.makedirs(out, exist_ok=True)
    os.environ["KN_SONGBOEK_BACKUP_DIR"] = tempfile.mkdtemp()
    app = QApplication.instance() or QApplication([])
    from kn_songboek.gui.qt_app import MainWindow
    folders, words = FOLDERS[lang], WORDS[lang]
    tmp = tempfile.mkdtemp()
    lib = os.path.join(tmp, words["lib"])
    old, new = words["card"] + " 2019", words["card"] + " 2023"
    demo_card(os.path.join(lib, old), folders)
    demo_card(os.path.join(lib, new), {1: words["new"], 2: words["calm"]}, 96)
    card = os.path.join(tmp, "SD-kaart" if lang == "nl" else "SD card")
    demo_card(card, folders)

    settings = QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat)
    settings.setValue("language", lang)
    w = MainWindow(settings)
    t = w.presenter.t
    for page in ("organize", "compose"):
        w.settings.setValue("tip_seen_" + page, "1")       # the first-time tips are left out
    w.confirm = lambda text: True
    w.choose = lambda text, options: 0                     # "Leeg beginnen"
    w.presenter._offer_keep = lambda path, suggest="": None            # no "ook bewaren?" in the pictures
    w.resize(1280, 760)
    w.show()
    shot(w, out, "1-start.png")

    w.open_path(card)                                      # "Kaart bekijken en ordenen"
    w.folders.setCurrentRow(0)
    w.songs.selectRow(1)
    shot(w, out, "3-kaart.png")

    f = w.folders
    f._dragging_folder = True
    f._show_drop(f.item(1), 3, Qt.MoveAction)              # a folder dragged between 02 and 03
    shot(w, out, "4-map-slepen.png")
    f._peek(True)                                          # while dragging the empty folders show
    f._show_drop(f.item(7), None, Qt.MoveAction)           # onto an empty folder
    shot(f, out, "4b-map-op-lege-map.png")
    f._clear_drop()
    f._peek(False)

    w.lists_dock.show()
    w.lists_dock.raise_()
    shot(w, out, "5-favorieten.png")
    w.lists_dock.hide()


    w.presenter.rename_song(1, 2, words["renamed"])
    shot(w, out, "7-wijziging.png")
    w.presenter.undo()
    w.go_start()

    w.settings.setValue("last_library", lib)               # "Nieuwe kaart samenstellen"
    w.presenter.start_compose()
    w.presenter.fill_library_details(batch=1000)
    w.presenter.rename_folder(1, words["wedding"])
    rows = w.presenter.library_rows()
    w.presenter.import_from_library([r.index for r in rows if r.name.split("  ·")[0] in words["chosen"]], 1)
    w.presenter.select_folder(1)
    w.folders.setCurrentRow(0)
    shot(w, out, "2-bibliotheek.png")
    lp = w.library_panel                                   # one card chosen: its folders, like on the keyboard
    lp.card.setCurrentIndex(lp.card.findData(old))
    lp.parts.setCurrentRow(1)
    shot(w, out, "2b-bibliotheek-kaart.png")
    lp.card.setCurrentIndex(0)
    from kn_songboek.core import cards
    from kn_songboek.gui.qt_app import MoreDialog
    vol = os.path.join(tmp, "Volumes")                     # "Op kaart zetten" in steps
    demo_card(os.path.join(vol, "KN7000"), folders)
    os.makedirs(os.path.join(vol, "NO NAME"))
    w.presenter.find_cards = lambda: [cards.classify(os.path.join(vol, n)) for n in sorted(os.listdir(vol))]
    w.presenter.eject = lambda path: True
    del w.choose                                           # "Leeg beginnen" above; now the step window asks
    taken = []

    def step():
        fl = w.flow
        if fl is None or fl._loop is None:
            return
        buttons = [b for b in fl.body.findChildren(type(w.put_button)) if b.isVisible()]
        if any("NO NAME" in b.text() for b in buttons) and "9" not in taken:
            taken.append("9")
            shot(fl, out, "9-welke-kaart.png")
        if fl.finish_button is not None and fl.finish_button.isVisible() and "8" not in taken:
            taken.append("8")
            shot(fl, out, "8-klaar.png")
        for want in ("NO NAME", t("btn_done"), t("btn_continue")):
            for b in buttons:
                if want in b.text():
                    b.click()
                    return
    from kn_songboek.gui.dialogs import FlowDialog
    real_progress = FlowDialog.progress

    def busy(self, i, n, text):                           # the list of parts, half way: "8a-bezig.png"
        real_progress(self, i, n, text)
        if i < 0 and n == 1 and "8a" not in taken:
            taken.append("8a")
            real_progress(self, 45, 100, "")
            self.bar.repaint()
            shot(self, out, "8a-bezig.png")
    FlowDialog.progress = busy
    timer = QTimer()
    timer.timeout.connect(step)
    timer.start(50)
    w._put_on_card()
    timer.stop()
    FlowDialog.progress = real_progress

    from kn_songboek.gui.qt_app import BackupsDialog
    w.open_path(card)
    from kn_songboek.core import backup as bk
    bk.make_backup(w.presenter.session.storage, w.presenter.backup_dir)
    bk.make_backup(DirectoryStorage(os.path.join(lib, new)), w.presenter.backup_dir,
                   label=new + "-" + words["lib"].lower())
    bd = BackupsDialog(w)
    bd.show()
    shot(bd, out, "11-back-ups.png")
    bd.close()

    more = MoreDialog(w)
    more.show()
    shot(more, out, "10-meer.png")
    more.close()
    w.presenter.session._undo.clear()
    QTimer.singleShot(0, app.quit)
    w.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    langs = [args.pop(0)] if args and args[0] in FOLDERS else list(FOLDERS)
    for lang in langs:
        main(args[0] if args else os.path.join(ROOT, "docs", lang, "img"), lang)
