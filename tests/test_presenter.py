import csv
import os
import tempfile
import unittest
from unittest import mock

from kn_songboek.core import backup

from helpers import card_with_songs, gui_test
from kn_songboek.core import CardSession
from kn_songboek.gui.presenter import MainPresenter


class FakeView:
    def __init__(self):
        self.folders, self.songs, self.search_mode = [], [], False
        self.status, self.space, self.errors, self.title, self.actions = "", "", [], "", None
        self.history = ([], [])
        self.answer = True
        self.choice = None
        self.retranslated = 0

    def show_folders(self, rows, current): self.folders, self.current = rows, current
    def show_songs(self, rows, search_mode): self.songs, self.search_mode = rows, search_mode
    def show_history(self, done, undone): self.history = (done, undone)
    def show_status(self, text): self.status = text
    def show_space(self, text): self.space = text
    def show_error(self, text): self.errors.append(text)
    def set_title(self, text): self.title = text
    def set_actions(self, actions): self.actions = actions
    def confirm(self, text): return self.answer
    def retranslate(self): self.retranslated += 1
    def show_favorites(self, banks, bank, items): self.fav = (banks, bank, items)
    def show_song_list(self, n, rows): self.songlist = (n, rows)
    def show_other(self, title, folders, current, songs): self.other = (title, folders, current, songs)
    def show_library(self, title, cards, rows): self.library = (title, cards, rows)
    def choose(self, text, options): self.choices = options; return self.choice
    def show_header(self, name, text, used, total): self.header = (name, text, used, total)
    def notify(self, text): self.notes = getattr(self, "notes", []) + [text]
    def show_done(self, text, other=""): self.done = text
    def show_page(self, page): self.page = page
    def ask_text(self, text, default=""): return getattr(self, "text_answer", default)


class PresenterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st, s = card_with_songs({1: ["A", "B"], 3: ["C"]})
        self.st.capacity = 10_000_000
        self.view = FakeView()
        self.p = MainPresenter(self.view, opener=lambda path: CardSession.open(self.st), backup_dir=self.tmp.name)
        self.p.open_card("card")

    def tearDown(self):
        self.tmp.cleanup()

    def names(self):
        return [(r.song, r.name) for r in self.view.songs if r.used]

    def test_open_shows_99_folders_and_20_slots(self):
        self.assertEqual(len(self.view.folders), 99)
        self.assertEqual(self.view.current, 1)
        self.assertEqual(len(self.view.songs), 20)
        self.assertEqual(self.names(), [(1, "A"), (2, "B")])
        self.assertIn("3 songs", self.view.status)
        self.assertFalse(self.view.actions.save)
        self.assertIn("MB vrij", self.view.space)

    def test_song_info_for_the_panel(self):
        self.p.set_favorite(1, (1, 2))
        self.p.add_to_song_list([(1, 2)])
        name, rows = self.p.song_info((1, 2))
        info = dict(rows)
        self.assertEqual(name, "B")
        self.assertEqual(info["Plaats"], "map 01 (geen naam), nr 2")
        self.assertEqual(info["Favorieten"], "bank 1 knop 1")
        self.assertEqual(info["Songlijsten"], "1")
        self.assertIsNone(self.p.song_info((1, 5)))

    def test_header_names_the_card_and_counts(self):
        name, text, used, total = self.view.header
        self.assertEqual((name, used, total), ("card", 3, 1980))
        self.assertTrue(text.startswith("3 songs in 2 mappen"))

    def test_rename_inline_validation_and_undo_redo(self):
        self.assertTrue(self.p.rename_song(1, 1, "AA"))
        self.assertEqual(self.names()[0], (1, "AA"))
        self.assertTrue(self.view.title.endswith("*"))
        self.assertFalse(self.p.rename_song(1, 1, "X" * 17))          # too long
        self.assertFalse(self.p.rename_song(1, 1, "Café"))            # not plain ASCII
        self.assertEqual(len(self.view.errors), 2)
        self.assertIn("16 tekens", self.view.errors[0])               # in the user's language
        self.assertIn("é", self.view.errors[1])
        self.p.undo()
        self.assertEqual(self.names()[0], (1, "A"))
        self.assertEqual(self.view.history, ([], ["song 1/1 hernoemd"]))
        self.p.redo()
        self.assertEqual(self.names()[0], (1, "AA"))

    def test_drag_reorder_and_drop_on_folder(self):
        self.p.drop_on_slot((1, 1), (1, 2))          # swap within folder
        self.assertEqual(self.names(), [(1, "B"), (2, "A")])
        self.p.drop_on_slot((1, 1), (1, 7))          # onto an empty slot
        self.assertEqual(self.names(), [(2, "A"), (7, "B")])
        self.assertEqual(self.p.move_songs([(1, 2), (1, 7)], 3), 2)
        self.p.select_folder(3)
        self.assertEqual(self.names(), [(1, "C"), (2, "A"), (3, "B")])

    def test_after_a_move_the_songs_are_chosen_where_they_landed(self):
        """Copy to a new folder: the new folder is shown and the copies are chosen there (the old row
        numbers used to stay chosen in the new folder)."""
        chosen = []
        self.view.select_slots = lambda slots: chosen.append(list(slots))
        f = self.p.new_folder("NIEUW")
        self.assertEqual(self.p.move_songs([(1, 1), (1, 2)], f, copy=True), 2)
        self.assertEqual(chosen[-1], [(f, 1), (f, 2)])
        self.p.select_folder(1)
        self.p.move_songs([(1, 1)], f)                  # moved away from the folder shown: nothing chosen
        self.assertEqual(chosen[-1], [])

    def test_delete_many_without_question_but_with_undo(self):
        self.view.answer = False                        # no "are you sure?": the message offers undo
        self.assertEqual(self.p.delete_songs([(1, 1), (1, 2), (1, 9)]), 2)
        self.assertEqual(self.names(), [])
        self.assertEqual(self.view.notes[-1], "2 song(s) verwijderd")
        self.assertEqual(self.p.delete_songs([(1, 1)], confirm=True), 0)

    def test_remove_several_folders_at_once(self):
        self.p.rename_folder(3, "FEEST")
        self.view.answer = False                        # "Nee": nothing happens
        self.assertEqual(self.p.delete_folders([1, 3]), 0)
        self.view.answer = True
        self.assertEqual(self.p.delete_folders([3, 1, 5]), 3)        # 5 is empty already: fine
        db = self.p.session.db
        self.assertFalse(any(x.used for f in (0, 2) for x in db.folders[f].songs))
        self.assertEqual(db.folders[2].name, "")
        self.assertEqual(self.view.notes[-1], "3 map(pen) weggehaald, 3 song(s) verwijderd")
        self.assertEqual(self.p.delete_folders([5]), 0)               # nothing in it: no question
        self.p.undo()
        self.assertEqual(self.p.session.db.folders[2].name, "FEEST")  # one undo step brings all back
        self.assertEqual(self.names(), [(1, "A"), (2, "B")])

    def test_search_and_history_jump(self):
        self.p.set_search("c")
        self.assertTrue(self.view.search_mode)
        self.assertEqual([(r.folder, r.name) for r in self.view.songs], [(3, "C")])
        self.p.set_search("")
        self.p.rename_song(1, 1, "X")
        self.p.rename_song(1, 2, "Y")
        self.p.undo_to(0)
        self.assertEqual(self.view.history[0], [])
        self.p.undo_to(2)
        self.assertEqual(len(self.view.history[0]), 2)

    def test_save_makes_backup_and_restore_brings_it_back(self):
        self.p.rename_song(1, 1, "NEW")
        steps = []
        self.assertTrue(self.p.save(progress=lambda i, n, t: steps.append(t)))
        self.assertIn("back-up", self.view.status)
        rows = self.p.backup_rows()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].label.startswith("Vandaag "))
        self.assertTrue(rows[0].this_card)
        self.assertTrue(rows[0].group.endswith("(deze kaart)"))
        self.assertEqual(self.p.backup_contents(rows[0].path), [("01  (geen naam)  (2)", ["A", "B"]),
                                                                ("03  (geen naam)  (1)", ["C"])])
        self.assertTrue(self.p.restore(rows[0].path))
        self.assertEqual(self.names()[0], (1, "A"))       # back-up was taken before the rename
        self.assertIn("weer zoals hij was", self.view.done)

    def test_backups_of_every_card_this_one_first(self):
        other, _ = card_with_songs({1: ["X", "Y", "Z"]})
        backup.make_backup(other, self.tmp.name, label="NO_NAME")          # another card, same name
        backup.make_backup(self.st, self.tmp.name, label="NO_NAME")
        backup.make_backup(other, self.tmp.name, label="Kaart A-bibliotheek")
        rows = self.p.backup_rows()
        self.assertEqual([(r.group, r.this_card, r.library) for r in rows],
                         [("NO_NAME  (deze kaart)", True, False), ("NO_NAME", False, False),
                          ("Kaart A  (oude versie in de bibliotheek)", False, True)])
        self.view.answer = False                                            # "not this card: sure?" no
        self.assertFalse(self.p.restore(rows[1].path))
        self.assertIsNotNone(self.p.make_backup_now())
        self.assertEqual(len([r for r in self.p.backup_rows() if r.this_card]), 2)

    def test_backup_as_new_card_and_into_the_library(self):
        other, _ = card_with_songs({2: ["X", "Y"]})
        z = backup.make_backup(other, self.tmp.name, label="oud")
        self.assertTrue(self.p.restore_as_new_card(z))
        self.assertTrue(self.p.composing)
        self.assertEqual([(f.folder, f.used) for f in self.view.folders if f.used], [(2, 2)])
        lib = os.path.join(self.tmp.name, "lib")
        self.p.library_path = lib
        self.view.text_answer = "Oude kaart"
        folder = self.p.restore_to_library(z)
        self.assertEqual(folder, os.path.join(lib, "Oude kaart"))
        self.assertEqual([c.label for c in self.p.library.cards], ["Oude kaart"])
        self.view.answer = False                                            # replace it? no
        self.assertIsNone(self.p.restore_to_library(z))

    def test_when_text(self):
        import datetime
        day = datetime.date(2026, 11, 15)
        self.assertEqual(self.p.when_text("2026-11-15T14:32:10", day), "Vandaag 14:32")
        self.assertEqual(self.p.when_text("2026-11-14T09:05:00", day), "Gisteren 09:05")
        self.assertEqual(self.p.when_text("2026-11-03T20:00:00", day), "3 november 2026 20:00")

    def test_export_and_language(self):
        path = os.path.join(self.tmp.name, "list.csv")
        self.p.export_csv(path)
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.DictReader(fh, delimiter=";"))
        self.assertEqual([r["Naam"] for r in rows], ["A", "B", "C"])
        self.assertEqual(list(rows[0]), ["Map", "Mapnaam", "Nr", "Naam"])
        self.assertIn(">C</td>", self.p.song_list_html())
        # chosen columns, one folder, details read from the song files (odd files leave them empty)
        self.p.export_csv(path, ["song", "name", "tempo", "chord", "files"], folder=1)
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(rows[0], ["Nr", "Naam", "Bestanden"])      # empty columns left out, as in print
        self.assertTrue(all(len(r) == 3 for r in rows))
        # the same list as printed: an empty folder with a name is there too, as a row of its own
        self.p.rename_folder(5, "LEEG")
        self.p.export_csv(path, ["folder", "folder_name", "song", "name"])
        with open(path, encoding="utf-8-sig") as fh:
            rows = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(rows[-1], ["05", "LEEG", "", ""])
        self.p.export_csv(path, ["folder", "folder_name", "song", "name"], skip_empty=True)
        with open(path, encoding="utf-8-sig") as fh:
            self.assertNotIn("LEEG", fh.read())
        self.p.undo()
        html = self.p.song_list_html(["song", "name", "tempo"], page_per_folder=True)
        self.assertNotIn("Tempo", html)                     # no song has a tempo: the empty column is left out
        self.assertEqual(html.count("page-break-before"), 1)                # folder 3 starts a new page
        self.assertNotIn("<h3", html)                       # Map and Mapnaam not ticked: no folder heading
        html = self.p.song_list_html(["folder", "song", "name"])
        self.assertIn("<h3>01</h3>", html)                  # only the number: the name was not ticked
        # A to Z: one table, name first, Map as a column so you see where a song is
        html = self.p.song_list_html(["folder", "song", "name"], by_name=True, title="Bruiloft")
        self.assertIn("<h2>Bruiloft</h2>", html)
        self.assertNotIn("<h3", html)
        self.assertLess(html.index(">A</td>"), html.index(">B</td>"))
        self.assertLess(html.index(">B</td>"), html.index(">C</td>"))
        self.assertNotIn("<h2", self.p.song_list_html(title=""))             # no title asked for
        self.p.export_csv(path, ["name", "folder"], by_name=True)
        with open(path, encoding="utf-8-sig") as fh:
            self.assertEqual([r[0] for r in csv.reader(fh, delimiter=";")][1:], ["A", "B", "C"])
        import datetime
        self.assertEqual(self.p.today_text(datetime.date(2026, 11, 18)), "18 november 2026")
        heads = self.p._tables([], [("", [{"song": "01", "name": "A", "tempo": "90", "files": ""}])],
                               ["song", "name", "tempo", "files"], self.p.export_labels, ())
        self.assertIn(">Tempo</th>", heads)
        self.assertNotIn("Bestanden", heads)                # nothing in it anywhere: left out
        self.assertIn("white-space: nowrap\">Tempo", heads)                # headings never break a word
        # columns fitted to the page: nothing is cut while it fits, the widest gives way first
        rows = [{"song": "01", "name": "A", "rhythm": "8 Beat Rock Ballad", "banks": "A: Een heel lange naam"}]
        cols, heads = ["song", "name", "rhythm", "banks"], ["Nr", "Naam", "Ritme", "Banks"]
        self.assertEqual(self.p._fit(rows, cols, heads, 80), {})
        cut = self.p._fit(rows, cols, heads, 40)
        self.assertEqual(set(cut), {"rhythm", "banks"})
        self.assertGreaterEqual(cut["rhythm"], 6)
        self.assertIsNone(self.p._fit(rows, cols, heads, 10))            # cannot fit at all
        html = self.p._folder_table(rows, cols, heads, {"rhythm": 11}, one_line=True)
        self.assertIn(">8 Beat Roc…</td>", html)
        self.assertNotIn("Ingespeeld", "".join(self.p.export_labels(["recorded"], short=True)))
        # the biggest letters where everything fits; fewer columns: more room, nothing cut
        fit = [(11.0, 30), (9.5, 200)]
        html = self.p.song_list_html(["song", "name"], fit=fit)
        self.assertEqual(self.p.list_font, 11.0)
        self.assertNotIn("…", html)
        self.assertTrue(self.p.list_title().startswith("Songlijst "))
        self.p.volume_roots = lambda: [os.path.dirname(os.path.abspath("card"))]
        self.p.card_path = os.path.abspath("card")
        self.assertIn("SD-kaart", self.p.export_source())                   # on a drive: the card in the reader
        self.p.session.db.folders[4].name = "LEEG"                         # a named folder without songs
        self.assertIn("LEEG", self.p.song_list_html(["folder", "folder_name", "name"]))
        self.assertNotIn("LEEG", self.p.song_list_html(["folder", "folder_name", "name"], skip_empty=True))
        from types import SimpleNamespace as NS
        bank = NS(name="", memories=[NS(name="Wals"), NS(name="Wals"), NS(name="Intro"), NS(name="")])
        self.assertEqual(self.p._bank_title(bank), "Wals")                 # no bank name: most buttons' name
        self.assertEqual(self.p._bank_title(NS(name="JAZZ", memories=[])), "JAZZ")
        self.assertEqual(dict(self.p.EXPORT_FIELDS)["banks"], "exp_banks")   # every bank, not only A
        self.p.set_language("en")
        self.assertEqual(self.view.retranslated, 1)
        self.assertIn("MB free", self.view.space)

    def test_duplicates_find_and_merge(self):
        self.p.move_songs([(1, 1)], 5, copy=True)                 # helper songs all have the same files
        self.assertIsNone(self.p.find_duplicates())               # unsaved changes first
        self.p.save()
        rows = self.p.find_duplicates()
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0].identical)
        self.assertEqual(rows[0].slots, ((1, 1), (1, 2), (3, 1), (5, 1)))
        self.assertIn("3", self.view.status)
        self.p.add_to_song_list([(5, 1)])
        self.assertTrue(self.p.merge_duplicates((1, 1), rows[0].slots, song_list=2))
        self.assertEqual(self.names(), [(1, "A")])
        self.assertEqual(self.p.session.playlists()[0], [(1, 1)])
        self.assertEqual(self.p.session.playlists()[1], [(1, 1)])
        self.p.undo()
        self.assertEqual(self.names(), [(1, "A"), (2, "B")])

    def test_full_folder_error_goes_to_view(self):
        for n in range(17):
            self.p.session.import_song(self.st, {"SQT": "PRIVATE/TECHNICS/KN7000/KN7000MN.INF"}, "F%d" % n, 3)
        self.assertEqual(self.p.move_songs([(1, 1), (1, 2)], 3), 2)
        self.assertEqual(self.p.move_songs([(3, 1)], 3, copy=True), 0)
        self.assertTrue(self.view.errors and "is vol" in self.view.errors[-1])


class ListsAndSecondCardTests(unittest.TestCase):
    names = PresenterTests.names
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st, _ = card_with_songs({1: ["A", "B"], 3: ["C"]})
        self.ost, _ = card_with_songs({9: ["OTHER1", "OTHER2"]})
        self.view = FakeView()
        cards = {"card": self.st, "other": self.ost}
        self.p = MainPresenter(self.view, opener=lambda path: CardSession.open(cards[path]), backup_dir=self.tmp.name)
        self.p.open_card("card")

    def tearDown(self):
        self.tmp.cleanup()

    def test_favorites_editor(self):
        self.assertEqual(len(self.view.fav[0]), 40)
        self.assertTrue(self.p.set_favorite(4, (3, 1)))
        self.assertEqual(self.view.fav[2][3], "C  ·  map 03, nr 1")
        self.assertTrue(self.p.rename_bank("Zaterdag"))
        self.assertEqual(self.view.fav[0][0], "01  Zaterdag")
        self.assertFalse(self.p.set_favorite(1, (5, 5)))
        self.p.select_bank(2)
        self.assertEqual(self.view.fav[2], [""] * 9)

    def test_song_list_editor(self):
        self.p.select_song_list(2)
        self.p.add_to_song_list([(1, 2), (3, 1)])
        self.p.add_to_song_list([(1, 1)], at=0)
        self.assertEqual([r[0] for r in self.view.songlist[1]], [(1, 1), (1, 2), (3, 1)])
        self.p.move_in_song_list(2, 0)
        self.assertEqual([r[0] for r in self.view.songlist[1]], [(3, 1), (1, 1), (1, 2)])
        self.p.remove_from_song_list([1])
        self.assertEqual([r[0] for r in self.view.songlist[1]], [(3, 1), (1, 2)])
        self.p.undo()
        self.assertEqual(len(self.view.songlist[1]), 3)

    def test_second_card_drag_in(self):
        self.assertTrue(self.p.open_other("other"))
        self.assertEqual(self.view.other[2], 9)
        self.assertEqual([s.name for s in self.view.other[3] if s.used], ["OTHER1", "OTHER2"])
        self.assertEqual(self.p.import_from_other([(9, 1), (9, 2)], 1), 2)
        self.assertEqual(self.names(), [(1, "A"), (2, "B"), (3, "OTHER1"), (4, "OTHER2")])
        self.assertTrue(self.p.save())
        self.assertEqual(CardSession.open(self.st).song(1, 3).name, "OTHER1")
        self.p.close_other()
        self.assertEqual(self.view.other[1], [])


@unittest.skipUnless(__import__("importlib").util.find_spec("PySide6"), "PySide6 not installed")
@gui_test
class QtSmokeTest(unittest.TestCase):
    def test_window_builds_and_shows_card(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import ExportDialog, MainWindow, export_pdf
        from kn_songboek.gui.dialogs import FolderPickerDialog
        app = QApplication.instance() or QApplication([])  # noqa: F841
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            st, s = card_with_songs({2: ["X"]})
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            self.assertEqual(w.folders.count(), 100)               # 99 folders + "lege mappen" row
            self.assertTrue(w.folders.item(0).isHidden())          # empty folders are folded away
            self.assertFalse(w.folders.item(1).isHidden())
            self.assertEqual(w.folders.toggle_item.text(), "▸ 98 lege mappen")
            w.folders.set_show_empty(True)
            self.assertFalse(w.folders.item(0).isHidden())
            w.folders.set_show_empty(False)
            self.assertEqual(w.presenter.new_folder("NIEUW"), 1)    # first unused folder
            self.assertFalse(w.folders.item(0).isHidden())
            self.assertFalse(w.empty_hint.isHidden())
            h = w.acts["history"]                                   # menu item with a tick: on, and off again
            h.trigger()
            self.assertTrue(h.isChecked() and not w.dock.isHidden())
            h.trigger()
            self.assertTrue(not h.isChecked() and w.dock.isHidden())
            w.dock.show()                                           # the tick follows the panel
            self.assertTrue(h.isChecked())
            w.dock.hide()
            w._undo()                                               # undo offers "Opnieuw" at the bottom
            self.assertTrue(w.redo_button.isEnabled())
            self.assertEqual(w.toast.undo.text(), "Opnieuw")
            w.toast.undo.click()                                    # redo: the new folder is back
            self.assertEqual(w.toast.undo.text(), "Ongedaan maken")
            self.assertFalse(w.redo_button.isEnabled())
            w.presenter.undo()
            w.presenter.select_folder(2)
            self.assertEqual(w.songs.rowCount(), 20)
            self.assertEqual(w.songs.item(0, 2).text(), "X")
            w.songs.item(0, 2).setText("Y")                 # inline edit
            self.assertEqual(s.db.song(1, 0).name, "Y")
            w.songs.selectRow(0)
            self.assertEqual(w.selected_slots(), [(2, 1)])
            self.assertFalse(w.action_bar.isHidden())               # buttons instead of dragging
            self.assertEqual([n for n, _ in w.presenter.folder_choices(2)], [0])   # no other folder in use: only "new"
            pick = FolderPickerDialog(w, "x", w.presenter.folder_choices())         # a table: Map, Naam, Songs, Nog vrij
            self.assertEqual([pick.list.topLevelItem(0).text(c) for c in range(4)], ["02", "(geen naam)", "1", "19"])
            self.assertEqual(pick.folder(), 2)
            pdf = os.path.join(tmp, "l.pdf")
            export_pdf(w.presenter.song_list_html(), pdf)
            self.assertGreater(os.path.getsize(pdf), 500)
            export_pdf(w.presenter.song_list_html(), pdf, date="18 november 2026", pages="Pagina {n} van {total}",
                       big=True, pt=8.0)
            self.assertGreater(os.path.getsize(pdf), 500)
            # dark mode: the app's text is white, the paper's text must stay black
            from PySide6.QtGui import QColor, QImage, QPalette, QPainter, QTextDocument
            from PySide6.QtCore import QSizeF
            from kn_songboek.gui.qt_app import draw_page
            app = QApplication.instance()
            old = app.palette()
            dark = QPalette(old)
            dark.setColor(QPalette.Text, QColor("white"))
            dark.setColor(QPalette.WindowText, QColor("white"))
            app.setPalette(dark)
            try:
                doc = QTextDocument()
                doc.setHtml(w.presenter.song_list_html())
                doc.setPageSize(QSizeF(400, 600))
                img = QImage(400, 600, QImage.Format_RGB32)
                img.fill(QColor("white"))
                painter = QPainter(img)
                draw_page(painter, doc, 0, QSizeF(400, 600))
                painter.end()
                dark_px = sum(1 for x in range(0, 400, 2) for y in range(0, 600, 2)
                              if QColor(img.pixel(x, y)).lightness() < 100)
                self.assertGreater(dark_px, 20)
            finally:
                app.setPalette(old)
            dlg = ExportDialog(w, "pdf")
            self.assertTrue(dlg.page.isEnabled())
            dlg.by_name.setChecked(True)                    # A to Z: "new page per folder" means nothing
            self.assertFalse(dlg.page.isEnabled())
            c = dlg.choice()
            self.assertTrue(c["by_name"] and c["date"] and c["pages"] and not c["page"] and not c["landscape"])
            self.assertEqual(c["source"], "card")
            self.assertTrue(c["title"].startswith("Songlijst"))
            dlg.remember(w.settings)
            self.assertEqual(ExportDialog(w, "csv").by_name.isChecked(), True)    # remembered
            csv = ExportDialog(w, "csv")                    # same window, CSV picked: layout options off
            self.assertTrue(csv.as_csv.isChecked() and not csv.title.isEnabled())
            csv.as_pdf.setChecked(True)
            self.assertTrue(csv.title.isEnabled() and csv.choice()["format"] == "pdf")
            w.settings.setValue("export/order", "folder")
            w.presenter.set_favorite(2, (2, 1))
            self.assertEqual(w.fav_table.item(1, 0).text(), "Y  ·  map 02, nr 1")
            w.presenter.add_to_song_list([(2, 1)])
            self.assertEqual(w.song_list.count(), 1)
            _, other = card_with_songs({4: ["Z"]})
            w.presenter._opener = lambda p: other
            w.presenter.open_other("o")
            self.assertEqual(w.other_songs.item(0, 1).text(), "Z")
            w.presenter.import_from_other([(4, 1)], 2)
            self.assertEqual(w.songs.item(1, 2).text(), "Z")
            item = w.folders.item(4)
            w.folders._show_drop(item, None, Qt.MoveAction)
            self.assertIn("05", w.statusBar().currentMessage())
            self.assertEqual(w.folders.drop_rect()[0], "box")
            w.folders._clear_drop()
            self.assertIsNone(w.folders.drop_rect())
            from kn_songboek.gui.qt_app import DuplicatesDialog
            w.presenter.save()
            dlg = DuplicatesDialog(w, w.presenter.find_duplicates())
            self.assertEqual(dlg.tree.topLevelItemCount(), 1)
            dlg.tree.setCurrentItem(dlg.tree.topLevelItem(0).child(0))
            self.assertTrue(dlg.keep_btn.isEnabled())
            w.confirm = lambda text: True
            dlg._keep()
            self.assertEqual(dlg.tree.topLevelItemCount(), 0)
            w.presenter.set_language("en")
            self.assertEqual(w.acts["save"].text(), "Put on card")
            self.assertEqual(w.tabs.tabText(1), "Song lists")
            s._undo.clear()
            w.close()

    def test_backups_dialog_and_folder_list_width(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import BackupsDialog, MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["KN_SONGBOEK_BACKUP_DIR"] = os.path.join(tmp, "bk")
            try:
                card = os.path.join(tmp, "SD")
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools"))
                from make_screenshots import demo_card
                demo_card(card, {1: ("LANGE MAPNAAM 12", ["A", "B"]), 2: ("ROCK", ["C"])})
                w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
                w.resize(1000, 700)
                w.show()
                w.open_path(card)
                fm = w.folders.fontMetrics()
                self.assertGreater(w.folders.minimumWidth(), fm.horizontalAdvance("01  LANGE MAPNAAM 12  (2)"))
                QApplication.processEvents()
                w.split.setSizes([10, 900, 200])
                self.assertGreaterEqual(w.split.sizes()[0], w.folders.minimumWidth())
                h = w.split.handle(1)
                self.assertIn("Dubbelklik", h.toolTip())
                w.split.setSizes([600, 200, 230])
                h.mouseDoubleClickEvent(None)                                     # back to the usual widths
                self.assertLess(w.split.sizes()[0], 400)
                from kn_songboek.gui.qt_app import AboutDialog
                self.assertIn("Versie", " ".join(lab.text() for lab in AboutDialog(w).findChildren(type(w.page_title))))
                import kn_songboek
                with mock.patch.object(kn_songboek, "__url__", ""):
                    self.assertIsNone(AboutDialog(w).findChild(type(w.page_title), "about_link"))   # no URL: no link
                with mock.patch.object(kn_songboek, "__url__", "https://example.org/kn_songboek"):
                    link = AboutDialog(w).findChild(type(w.page_title), "about_link")
                    self.assertIn("https://example.org/kn_songboek", link.text())
                    self.assertTrue(link.openExternalLinks())
                self.assertEqual(w.menus["help"].actions()[-1].text(), "Over KN Songboek")
                dlg = BackupsDialog(w)
                self.assertFalse(dlg.here_btn.isEnabled())                     # no back-ups yet
                w.show_done = lambda text: None
                w.presenter.make_backup_now()
                dlg = BackupsDialog(w)
                self.assertTrue(dlg.path().endswith(".zip"))
                self.assertTrue(dlg.here_btn.isEnabled())
                self.assertEqual(dlg.contents.topLevelItem(0).text(0), "01  LANGE MAPNAAM 12  (2)")
                w.close()
            finally:
                del os.environ["KN_SONGBOEK_BACKUP_DIR"]

    def test_name_fields_stop_at_16_plain_characters(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QLineEdit, QStyleOptionViewItem, QWidget
        from kn_songboek.gui.qt_app import EmptySlotDelegate, name_field
        QApplication.instance() or QApplication([])
        e = name_field(QLineEdit())
        e.insert("X" * 25)
        self.assertEqual(e.text(), "X" * 16)
        e.clear()
        e.insert("Café")
        self.assertEqual(e.text(), "")                                # é refused, so nothing typed
        e.insert("CAFE 2")
        self.assertEqual(e.text(), "CAFE 2")
        from PySide6.QtGui import QStandardItemModel
        m = QStandardItemModel(1, 1)
        host = QWidget()
        delegate = EmptySlotDelegate(host)
        ed = delegate.createEditor(host, QStyleOptionViewItem(), m.index(0, 0))
        self.assertEqual(ed.maxLength(), 16)

    def test_columns_can_be_resized_and_are_kept(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication, QHeaderView
        from kn_songboek.gui.qt_app import MainWindow
        from test_library import LibraryTests
        QApplication.instance() or QApplication([])
        fx = LibraryTests("test_find_cards")
        fx.setUp()
        try:
            ini = os.path.join(fx.tmp.name, "s.ini")
            w = MainWindow(QSettings(ini, QSettings.IniFormat))
            w.confirm = lambda text: True
            self.assertTrue(w.open_library(fx.root))
            for tb in (w.songs, w.library_panel.table):
                h = tb.horizontalHeader()
                self.assertTrue(all(h.sectionResizeMode(c) == QHeaderView.Interactive for c in range(h.count())))
            h = w.library_panel.table.horizontalHeader()
            from test_presenter import card_with_songs as cws
            _, s = cws({1: ["wieringen_______"] * 20})
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            self.assertLess(w.minimumSizeHint().width(), 1200)          # fits a laptop screen, panels can move
            h.resizeSection(1, 123)                                    # the user drags the edge
            w.library_panel.recorded.setChecked(True)                  # the list is filled again
            self.assertEqual(h.sectionSize(1), 123)
            w.close()
            w2 = MainWindow(QSettings(ini, QSettings.IniFormat))
            w2._restore_columns()
            self.assertEqual(w2.library_panel.table.horizontalHeader().sectionSize(1), 123)
        finally:
            fx.tearDown()

    def test_waiting_for_the_next_diskette(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.core import cards
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            inside = [True]                                     # the last diskette did not come out
            w.presenter.find_cards = lambda: [cards.CardInfo("/x", "DISKETTE", cards.FLOPPY, 2)] if inside[0] else []
            w.presenter.waiting_for = (cards.FLOPPY,)
            poll = w._card_poll("✓ Diskette 1 staat in de bibliotheek…")
            self.assertFalse(poll())                            # still the old one: wait
            inside[0] = False
            self.assertFalse(poll())
            inside[0] = True                                    # the next one is in: go on
            self.assertTrue(poll())
            w.presenter.waiting_for = ()
            self.assertIsNone(w._card_poll("iets anders"))

    def test_shift_click_in_the_library_folder_list_keeps_the_range(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings, Qt
        from PySide6.QtTest import QTest
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        from test_library import LibraryTests
        QApplication.instance() or QApplication([])
        fx = LibraryTests("test_find_cards")
        fx.setUp()
        try:
            w = MainWindow(QSettings(os.path.join(fx.tmp.name, "s.ini"), QSettings.IniFormat))
            w.confirm = lambda text: True
            self.assertTrue(w.open_library(fx.root))
            w.show()
            lp = w.library_panel
            w.presenter.library_parts = lambda card: [(("folder", i), "%02d" % i) for i in range(1, 40)]
            lp.card.setCurrentIndex(lp.card.findData("Kaart 01"))
            lst = lp.parts

            def click(r, mod=Qt.NoModifier):
                QTest.mouseClick(lst.viewport(), Qt.LeftButton, mod, lst.visualItemRect(lst.item(r)).center())
                return sorted(lst.row(i) for i in lst.selectedItems())
            self.assertEqual(click(1), [1])
            self.assertEqual(click(20, Qt.ShiftModifier), list(range(1, 21)))     # 01 up to 20, not "Alle songs"
            self.assertNotIn(5, click(5, Qt.ControlModifier))                    # Cmd-click takes one out
            self.assertEqual(len(lst.selectedItems()), 19)
            w.close()
        finally:
            fx.tearDown()

    def test_text_size_rebuilds_the_window_and_keeps_the_work(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui import style
        from kn_songboek.gui.qt_app import MainWindow
        from test_library import LibraryTests
        QApplication.instance() or QApplication([])
        fx = LibraryTests("test_find_cards")
        fx.setUp()
        try:
            w = MainWindow(QSettings(os.path.join(fx.tmp.name, "s.ini"), QSettings.IniFormat))
            w.confirm = lambda text: True
            self.assertTrue(w.open_library(fx.root))
            self.assertTrue(w.presenter.new_card(os.path.join(fx.tmp.name, "Nieuw")))
            w.confirm = lambda text: self.fail("no question when the window is rebuilt")
            p = w.presenter
            self.assertTrue(p.rename_folder(2, "FEEST"))
            w.size_acts["large"].trigger()                     # Weergave › Lettergrootte › Groot
            new = p.view
            self.assertIsNot(new, w)
            self.assertIs(new.presenter, p)
            self.assertEqual(style.TEXT_SIZES["large"], style._scale)
            self.assertTrue(p.session.dirty)                    # the change is still there, not saved
            self.assertIn("FEEST", [new.folders.item(i).text() for i in range(new.folders.count())][1])
            self.assertEqual(new.library_panel.table.rowCount(), 3)
            self.assertTrue(new.size_acts["large"].isChecked())
            new._rebuilt = True                                 # close without the question
            new.close()
        finally:
            from kn_songboek.gui import style as st
            st.set_text_size("normal")
            fx.tearDown()

    def test_library_panel(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MIME_LIB, FolderList, MainWindow
        from test_library import LibraryTests
        QApplication.instance() or QApplication([])
        fx = LibraryTests("test_find_cards")
        fx.setUp()
        try:
            w = MainWindow(QSettings(os.path.join(fx.tmp.name, "s.ini"), QSettings.IniFormat))
            w.confirm = lambda text: True
            self.assertEqual(w.card_stack.currentIndex(), 0)            # welcome page
            self.assertTrue(w.lang_acts["nl"].isChecked() and not w.lang_acts["en"].isChecked())
            self.assertTrue(w.open_library(fx.root))
            while w.presenter.fill_library_details():
                pass
            from kn_songboek.gui.qt_app import ExportDialog
            self.assertTrue(w.acts["export_pdf"].isEnabled())           # no card open: the library can be listed
            dlg = ExportDialog(w, "pdf")
            self.assertTrue(dlg.from_lib.isChecked() and dlg.library_chosen())
            self.assertFalse(dlg.boxes["rhythm"].isEnabled())           # the library cannot read the rhythm
            self.assertTrue(dlg.boxes["tempo"].isEnabled())
            self.assertEqual(dlg.title.text(), "Songlijst bibliotheek")
            self.assertEqual(dlg.choice()["source"], "library")
            tb = w.library_panel.table
            self.assertEqual(tb.rowCount(), 3)
            self.assertEqual(tb.item(0, 0).text(), "ROCK")
            with mock.patch.object(QApplication, "focusWidget", return_value=tb):   # Cmd+A in the library
                w._select_all()
            self.assertEqual(len(tb.selectionModel().selectedRows()), 3)
            self.assertEqual(w.selected_slots(), [])                    # not the card's songs
            tb.clearSelection()
            self.assertEqual(tb.item(0, 1).data(0), 140)
            w.library_panel.recorded.setChecked(True)
            self.assertEqual(tb.rowCount(), 1)
            w.library_panel.recorded.setChecked(False)
            self.assertTrue(w.presenter.new_card(os.path.join(fx.tmp.name, "Nieuw")))
            self.assertEqual(w.card_stack.currentIndex(), 1)
            tb.selectRow(0)
            md = tb.mimeData([])
            self.assertTrue(md.hasFormat(MIME_LIB))

            class Ev:
                def mimeData(self): return md
                def modifiers(self): return 0
            from PySide6.QtCore import Qt
            self.assertEqual(FolderList.drop_action(Ev()), Qt.CopyAction)
            self.assertEqual(w.presenter.import_from_library([tb.item(0, 0).data(Qt.UserRole)], 3), 1)
            w.presenter.select_folder(3)
            self.assertEqual(w.songs.item(0, 2).text(), "ROCK")
            lp = w.library_panel
            self.assertTrue(lp.card_row.isHidden())                  # "Alle kaarten": nothing about one card
            self.assertTrue(lp.copy_part.isHidden())
            lp.card.setCurrentIndex(lp.card.findData("Kaart 01"))
            self.assertFalse(lp.card_row.isHidden())
            self.assertTrue(lp.copy_part.isVisible() or not w.isVisible())
            self.assertEqual(lp.part.itemData(1), "folder:1")
            self.assertEqual(lp.parts.count(), lp.part.count())     # the folders as a list, like the keyboard
            lp.parts.setCurrentRow(1)
            self.assertEqual(lp.part.currentIndex(), 1)
            self.assertEqual([tb.item(r, 0).text() for r in range(tb.rowCount())], ["WALTZ  ·  2 versies", "ROCK"])
            self.assertEqual([tb.verticalHeaderItem(r).text() for r in range(tb.rowCount())], ["01", "02"])
            self.assertFalse(lp.copy_part.isHidden())
            self.assertEqual(lp.copy_part.text(), "Hele map 01 (geen naam) toevoegen aan je kaart")
            lp.copy_part.click()
            self.assertEqual(w.presenter.folder, 1)
            self.assertEqual([w.songs.item(r, 2).text() for r in range(2)], ["WALTZ", "ROCK"])
            w.presenter.session._undo.clear()
            w.presenter.library.close()
            w.close()
        finally:
            fx.tearDown()

    def test_drag_to_a_folder_copies_by_default_and_moves_with_modifier(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MIME, MIME_OTHER, FolderList, SongTable, _encode, wants_move
        QApplication.instance() or QApplication([])

        class Ev:
            def __init__(self, mime, mods):
                self._m, self._mods = mime, mods
            def mimeData(self): return self._m
            def modifiers(self): return self._mods

        own = _encode([(1, 1)])
        self.assertFalse(wants_move(Qt.NoModifier))
        self.assertTrue(wants_move(Qt.AltModifier))
        self.assertEqual(FolderList.drop_action(Ev(own, Qt.NoModifier)), Qt.CopyAction)
        self.assertEqual(FolderList.drop_action(Ev(own, Qt.AltModifier)), Qt.MoveAction)
        self.assertEqual(FolderList.drop_action(Ev(own, Qt.ControlModifier)), Qt.MoveAction)
        self.assertEqual(SongTable.drop_action(Ev(own, Qt.AltModifier)), Qt.MoveAction)
        other = _encode([(1, 1)])
        other.setData(MIME_OTHER, other.data(MIME))
        other.removeFormat(MIME)
        self.assertEqual(FolderList.drop_action(Ev(other, Qt.NoModifier)), Qt.CopyAction)


class LibraryPresenterTests(unittest.TestCase):
    def setUp(self):
        from test_library import LibraryTests
        self.fixture = LibraryTests("test_find_cards")
        self.fixture.setUp()
        self.root = self.fixture.root
        self.view = FakeView()
        self.p = MainPresenter(self.view, backup_dir=self.fixture.tmp.name)

    def tearDown(self):
        if self.p.library:
            self.p.library.close()
        self.fixture.tearDown()

    def test_library_flow(self):
        self.assertTrue(self.p.open_library(self.root))
        title, cards, rows = self.view.library
        self.assertIn("3 kaart(en), 3 songs", title)
        self.assertEqual(cards, ["Kaart 01", "Oud/Kaart 1998", "piet.img"])
        self.assertIn("kapot.img", self.view.status)
        self.assertEqual(rows[0].tempo, "…")
        while self.p.fill_library_details(batch=1):
            pass
        rows = self.view.library[2]
        self.assertEqual([(r.name, r.tempo, r.recorded) for r in rows],
                         [("ROCK", "140", "ja"), ("WALTZ  ·  2 versies", "90", ""), ("WALTZ  ·  2 versies", "90", "")])
        waltz = [r for r in rows if r.name.startswith("WALTZ")]       # each says where the other one is
        self.assertIn("Andere versie(s) met dezelfde naam", waltz[0].where)
        self.assertIn(waltz[1].where.split("\n")[0], waltz[0].where)
        self.p.set_library_filter(recorded=True)
        self.assertEqual([r.name for r in self.view.library[2]], ["ROCK"])
        self.p.set_library_filter(card="Oud/Kaart 1998", tempo_min=80, tempo_max=100)
        self.assertEqual(len(self.view.library[2]), 2)
        new = os.path.join(self.fixture.tmp.name, "Nieuwe kaart")
        self.view.answer = True
        self.assertTrue(self.p.new_card(new))
        self.assertEqual(self.p.import_from_library([0, 1], 5), 2)
        self.assertEqual([(r.song, r.name) for r in self.view.songs if r.used], [])   # folder 1 shown
        self.p.select_folder(5)
        self.assertEqual([(r.song, r.name) for r in self.view.songs if r.used], [(1, "ROCK"), (2, "WALTZ")])
        self.assertTrue(self.p.save())
        self.p.session.storage.free_bytes = lambda: 10
        self.assertEqual(self.p.import_from_library([2], 5), 0)
        self.assertIn("ruimte", self.view.errors[-1])

    def test_export_says_which_card_the_list_is_made_of(self):
        self.assertTrue(self.p.open_library(self.root))
        lib = self.p.library.cards[0]
        self.p.open_card(lib.path)
        self.assertEqual(self.p.export_source(), 'Uit: Kaart "%s" uit de bibliotheek (de kopie op de computer)'
                         % lib.label)
        self.assertEqual(self.p.list_title(), "Songlijst " + lib.label)
        self.view.answer = True
        self.assertTrue(self.p.new_card(os.path.join(self.fixture.tmp.name, "Nieuw")))
        self.assertEqual(self.p.export_source(), 'Uit: De kaart in de map "Nieuw" op de computer')
        self.view.choice = 0                                # a new, empty card
        self.assertTrue(self.p.start_compose())
        self.assertIn("nieuwe kaart", self.p.export_source())
        self.assertTrue(self.p.open_library(self.root))

    def test_the_whole_library_as_a_song_list(self):
        self.assertTrue(self.p.open_library(self.root))
        lib = self.p.library
        self.assertIn("De hele bibliotheek (3 kaarten en diskettes, 3 songs)", self.p.library_export_text())
        # A to Z: one row per song, with every place it is on
        rows = self.p.library_export_rows(["name", "tempo"], by_name=True)
        self.assertEqual([r["name"] for r in rows], sorted((x.name for x in lib.songs), key=str.casefold))
        waltz = [r for r in rows if r["name"] == "WALTZ"]
        self.assertTrue(all(" map " in r["where"] and " nr " in r["where"] for r in rows))
        self.assertEqual(rows[0]["tempo"], "140")                         # read from the song
        self.assertTrue(waltz)
        # card by card: every copy, under its card
        rows = self.p.library_export_rows(["folder", "song", "name"])
        self.assertEqual(len(rows), sum(len(x.copies) for x in lib.songs))
        self.assertEqual([r["card"] for r in rows], sorted((r["card"] for r in rows),
                                                            key=[c.label for c in lib.cards].index))
        html = self.p.library_list_html(["folder", "song", "name"], page_per_card=True, title="Alles")
        self.assertIn("<h2>Alles</h2>", html)
        for c in lib.cards:
            if any(x.card is c for s in lib.songs for x in s.copies):
                self.assertIn(">%s</h2>" % c.label, html)
        self.assertIn("page-break-before", html)
        html = self.p.library_list_html(["name", "tempo", "rhythm"], by_name=True)
        self.assertIn(">Staat op</th>", html)
        self.assertNotIn("Ritme", html)                                   # the library cannot read that
        path = os.path.join(self.fixture.tmp.name, "lib.csv")
        self.assertTrue(self.p.export_library_csv(path, ["folder", "name"]))
        with open(path, encoding="utf-8-sig") as fh:
            got = list(csv.reader(fh, delimiter=";"))
        self.assertEqual(got[0], ["Kaart", "Map", "Naam"])
        # only what the filter shows
        self.assertFalse(self.p.library_filtered())
        self.p.set_library_filter(text="ROCK")
        self.assertTrue(self.p.library_filtered())
        self.assertEqual([r["name"] for r in self.p.library_export_rows(["name"], True, filtered=True)], ["ROCK"])
        self.assertIn("1 songs", self.p.library_export_text(True))

    def test_the_new_filters(self):
        self.assertTrue(self.p.open_library(self.root))
        while self.p.fill_library_details(batch=5):
            pass
        names = lambda: sorted(r.name.split("  ·")[0] for r in self.view.library[2])   # noqa: E731
        self.assertEqual(self.p.library_meters(), sorted({x.meter for x in self.p.library.songs if x.meter}))
        meter = self.p.library.songs[0].meter
        if meter:
            self.p.set_library_filter(meter=meter)
            self.assertTrue(all(x.meter == meter for x in self.p.library.songs
                                if x.name in names()))
        self.p.set_library_filter(spread="more")
        more = names()
        self.p.set_library_filter(spread="one")
        self.assertEqual(sorted(more + names()), sorted(x.name for x in self.p.library.songs))
        self.p.set_library_filter(source="floppy")
        self.assertEqual(names(), [])                                  # no diskettes in this library
        self.p.set_library_filter(source="card")
        self.assertEqual(len(names()), len(self.p.library.songs))
        self.p.set_library_filter(damaged=True)
        self.assertEqual(names(), [])
        # not on my card yet: what is put on the open card disappears from the list
        self.view.answer = True
        self.assertTrue(self.p.new_card(os.path.join(self.fixture.tmp.name, "Nieuwe kaart")))
        rock = next(i for i, x in enumerate(self.p.library.songs) if x.name == "ROCK")
        self.p.set_library_filter(not_on_card=True)
        self.assertIn("ROCK", names())
        self.assertEqual(self.p.import_from_library([rock], 5), 1)
        self.p.set_library_filter(not_on_card=True)
        self.assertNotIn("ROCK", names())
        self.p.rename_song(5, 1, "ANDERE NAAM")                        # another name: still the same song
        self.p.set_library_filter(not_on_card=True)
        self.assertNotIn("ROCK", names())
        self.assertTrue(self.p.save())                                  # also once it is on the card
        self.p.set_library_filter(not_on_card=True)
        self.assertNotIn("ROCK", names())

    def test_bad_library_path(self):
        self.assertFalse(self.p.open_library(os.path.join(self.root, "nope")))
        self.assertTrue(self.view.errors)


    def test_remove_a_card_from_the_library_goes_to_the_bin(self):
        from unittest import mock
        from kn_songboek.storage import trash
        self.assertTrue(self.p.open_library(self.root))
        old = os.path.join(self.root, "Oud", "Kaart 1998")
        self.view.answer = False                        # "no": nothing happens
        self.assertFalse(self.p.remove_library_card("Oud/Kaart 1998"))
        self.assertTrue(os.path.isdir(old))
        self.view.answer = True
        moved = []
        with mock.patch.object(trash, "move_to_trash", side_effect=lambda path: moved.append(path) or False):
            self.assertFalse(self.p.remove_library_card("Oud/Kaart 1998"))
        self.assertEqual(moved, [old])
        self.assertTrue(os.path.isdir(old))             # the bin said no: still there, and said so
        self.assertIn("Prullenbak", self.view.errors[-1])
        self.assertIn("Oud/Kaart 1998", self.view.library[1])
        bin_dir = os.path.join(self.fixture.tmp.name, "bin")
        gone = lambda path: __import__("shutil").move(path, bin_dir) or True   # noqa: E731
        with mock.patch.object(trash, "move_to_trash", side_effect=gone):
            self.assertTrue(self.p.remove_library_card("Oud/Kaart 1998"))
        self.assertEqual(self.view.library[1], ["Kaart 01", "piet.img"])
        self.assertIn("Prullenbak", self.view.status)
        self.assertTrue(os.path.isdir(bin_dir))         # moved, not deleted

    def test_a_library_card_the_new_card_still_uses_stays(self):
        self.assertTrue(self.p.open_library(self.root))
        self.view.answer = True
        self.assertTrue(self.p.new_card(os.path.join(self.fixture.tmp.name, "Nieuwe kaart")))
        rows = self.p.library_rows()
        rock = next(r.index for r in rows if r.name == "ROCK")
        self.assertEqual(self.p.import_from_library([rock], 5), 1)
        label = self.p.library.songs[rock].copies[0].card.label
        path = self.p._library_card_path(label)
        self.assertFalse(self.p.remove_library_card(label))     # the song is copied only when saving
        self.assertIn("gebruikt nog songs uit", self.view.errors[-1])
        self.assertFalse(self.p.rename_library_card(label))
        self.assertTrue(os.path.exists(path))
        self.assertTrue(self.p.save())                           # saved: now it may go
        self.view.ask_text = lambda text, default="": "Kaart nieuw"
        self.assertTrue(self.p.rename_library_card(label))
        self.assertIn("Kaart nieuw", self.view.library[1] if "/" not in label else
                      [c.split("/")[-1] for c in self.view.library[1]])

    def test_renaming_the_chosen_library_card_keeps_it_chosen(self):
        self.assertTrue(self.p.open_library(self.root))
        label = self.p.library.cards[0].label
        self.p.set_library_filter(card=label, part=("folder", 1))
        self.view.ask_text = lambda text, default="": "Andere naam"
        started = []
        self.view.fill_library_details_later = lambda: started.append(1)
        self.assertTrue(self.p.rename_library_card(label))
        self.assertTrue(started)                                         # tempo and time read again, not "…"
        new = self.p.lib_filter["card"]
        self.assertTrue(new.endswith("Andere naam"))                   # not back to all cards
        self.assertEqual(self.p.lib_filter["part"], ("folder", 1))
        self.assertTrue(self.p.library_rows())

    def test_rename_a_library_card(self):
        self.assertTrue(self.p.open_library(self.root))
        old = os.path.join(self.root, "Kaart 01")
        self.view.ask_text = lambda text, default="": None                      # cancelled
        self.assertFalse(self.p.rename_library_card("Kaart 01"))
        self.view.ask_text = lambda text, default="": "piet"                     # piet.img is a file: no clash
        self.assertTrue(self.p.rename_library_card("Kaart 01"))
        self.assertFalse(os.path.exists(old))
        self.assertEqual(self.view.library[1], ["Oud/Kaart 1998", "piet", "piet.img"])
        self.assertIn("heet nu piet", self.view.status)
        self.view.ask_text = lambda text, default="": "Oud"                      # taken
        self.assertFalse(self.p.rename_library_card("piet"))
        self.assertIn("al iets met de naam Oud", self.view.errors[-1])
        self.view.ask_text = lambda text, default="": "Nieuw 2"                  # an image keeps its extension
        self.assertTrue(self.p.rename_library_card("piet.img"))
        self.assertIn("Nieuw 2.img", self.view.library[1])

    def test_only_cards_inside_the_library_can_be_removed(self):
        self.assertTrue(self.p.open_library(self.root))
        self.view.answer = True
        self.assertFalse(self.p.remove_library_card("bestaat niet"))
        self.p.library.cards[0].path = self.fixture.tmp.name     # outside the library: refused
        self.assertFalse(self.p.remove_library_card("Kaart 01"))
        self.assertTrue(os.path.isdir(self.fixture.tmp.name))


class PlainErrorTests(unittest.TestCase):
    """Errors say what happened and what to do, in plain words; technical details come last."""

    def test_a_library_chosen_as_card_is_offered_as_library(self):
        from test_library import LibraryTests
        fx = LibraryTests("test_find_cards")
        fx.setUp()
        try:
            view = FakeView()
            asked = []
            view.ask = lambda text, buttons: asked.append(text) or 0
            p = MainPresenter(view, backup_dir=fx.tmp.name)
            self.assertFalse(p.open_card(fx.root))
            self.assertIn("bibliotheek met bewaarde kaarten", asked[0])
            self.assertIsNotNone(p.library)                       # "yes": the library is open
            self.assertIn("Nieuwe kaart samenstellen", view.done)
            self.assertEqual(view.errors, [])
            p.library.close()
        finally:
            fx.tearDown()

    def test_an_empty_folder_and_a_damaged_card_are_said_differently(self):
        with tempfile.TemporaryDirectory() as tmp:
            view = FakeView()
            p = MainPresenter(view, backup_dir=tmp)
            self.assertFalse(p.open_card(tmp))
            self.assertIn("Hier staat geen KN7000-kaart", view.errors[-1])
            os.makedirs(os.path.join(tmp, "PRIVATE", "TECHNICS", "KN7000"))
            from kn_songboek.formats import layout
            with open(os.path.join(tmp, *layout.INF_PATH.split("/")), "wb") as fh:
                fh.write(b"rubbish")
            self.assertFalse(p.open_card(tmp))
            self.assertIn("inhoudsopgave van de kaart is beschadigd", view.errors[-1])
            self.assertIn("Voor als je hulp vraagt", view.errors[-1])

    def test_card_check_is_said_in_words(self):
        st, s = card_with_songs({1: ["A"]})
        del st.files[next(p for p in st.files if p.upper().endswith(".SQT"))]
        st.write("PRIVATE/TECHNICS/KN7000/TFLD001/ZZ.SQT", b"x")
        view = FakeView()
        view.ask = lambda text, buttons: None                  # "later" on the notices when it opens
        p = MainPresenter(view, opener=lambda path: CardSession.open(st), backup_dir=tempfile.mkdtemp())
        p.open_card("card")
        text = "\n".join(p.check())
        self.assertIn("Map 1, song 1: het bestand", text)
        self.assertIn("speelt niet", text)
        self.assertIn("hoort bij geen enkele song", text)
        self.assertNotIn("database", text)

    def test_no_database_word_left_for_the_player(self):
        from kn_songboek.gui import i18n
        for key, (nl, _en) in i18n.TEXTS.items():
            if key not in ("title", "file_MD"):
                self.assertNotIn("atabase", nl, key)


class LibraryListTests(unittest.TestCase):
    def test_copy_song_list_and_folder_from_library(self):
        from kn_songboek.storage import DirectoryStorage
        from test_library import add
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "lib")
            a = CardSession.create(DirectoryStorage(os.path.join(root, "Kaart Bruiloft")))
            add(a, 3, "ONE", 100)
            add(a, 3, "TWO", 110)
            add(a, 4, "THREE", 120)
            a.rename_folder(3, "FEEST")
            a.set_song_list(1, [(4, 1), (3, 1)])
            a.save()
            view = FakeView()
            p = MainPresenter(view, backup_dir=os.path.join(tmp, "bk"))
            p.open_library(root)
            parts = p.library_parts("Kaart Bruiloft")
            self.assertEqual([k for k, _ in parts], [("folder", 3), ("folder", 4), ("list", 1)])
            self.assertEqual(parts[0][1], "03  FEEST  (2)")
            p.set_library_filter(card="Kaart Bruiloft", part=("list", 1))
            self.assertEqual([r.name for r in view.library[2]], ["THREE", "ONE"])
            p.set_library_filter(card="Kaart Bruiloft", part=("folder", 3))
            self.assertEqual([r.name for r in view.library[2]], ["ONE", "TWO"])
            self.assertTrue(p.new_card(os.path.join(tmp, "new")))
            self.assertTrue(p.copy_library_part("Kaart Bruiloft", ("list", 1)))
            self.assertEqual(p.session.playlists()[0], [(1, 1), (1, 2)])
            self.assertEqual(p.session.db.folders[0].name, "KAART BRUILOFT")
            self.assertIn("2 song(s) gekopieerd", view.status)
            self.assertTrue(p.copy_library_part("Kaart Bruiloft", ("folder", 3)))
            self.assertEqual(p.folder, 2)
            self.assertEqual(p.session.db.folders[1].name, "FEEST")
            self.assertEqual([(r.song, r.name) for r in view.songs if r.used], [(1, "ONE"), (2, "TWO")])
            self.assertEqual(len(p.session.history()), 2)
            p.copy_library_part("Kaart Bruiloft", ("list", 1))
            p.copy_library_part("Kaart Bruiloft", ("list", 1))
            view.choice = None
            self.assertFalse(p.copy_library_part("Kaart Bruiloft", ("list", 1)))   # all lists used, cancelled
            self.assertTrue(view.choices[0].startswith("Songlijst 1 vervangen"))
            view.choice = 0
            self.assertTrue(p.copy_library_part("Kaart Bruiloft", ("list", 1)))
            self.assertTrue(p.save())
            p.library.close()


class LanguageTests(unittest.TestCase):
    def test_every_core_message_and_step_has_both_languages(self):
        """Every Text key raised or recorded in core has a Dutch and an English text, so no English
        message reaches a Dutch user (and the other way round)."""
        import glob
        import re
        from kn_songboek.gui.i18n import TEXTS
        keys = set()
        for f in glob.glob(os.path.join(os.path.dirname(__file__), "..", "src", "kn_songboek", "core", "*.py")):
            src = open(f, encoding="utf-8").read()
            keys |= set(re.findall(r'Text\("(\w+)"', src)) | ({"copy", "move"} if "Text(\"copy\" if copy" in src else set())
            self.assertEqual(re.findall(r'raise (?!InvalidName)\w+\("', src), [], f)   # no bare English message in core
            # (InvalidName carries name and bad characters; the presenter words it itself)
        self.assertGreater(len(keys), 40)
        missing = sorted(k for k in keys if "err." + k not in TEXTS and "step." + k not in TEXTS and "issue." + k not in TEXTS)
        self.assertEqual(missing, [])
        for k in keys:
            for nl, en in [TEXTS[x] for x in ("err." + k, "step." + k, "issue." + k) if x in TEXTS]:
                self.assertTrue(nl and en and nl != en, k)

    def test_errors_and_steps_are_said_in_the_users_language(self):
        from kn_songboek.core.errors import SlotError, Text
        p = MainPresenter.__new__(MainPresenter)
        p.lang = "nl"
        e = SlotError(Text("folder_full", "folder {n} is full (20 songs)", n=3))
        self.assertEqual(p.error_text(e), "Map 3 is vol (20 songs).")
        self.assertIn("Voor als je hulp vraagt: raw", p.error_text(SlotError("raw")))
        import errno
        self.assertIn("schrijfbeveiligd", p.os_error_text(OSError(errno.EROFS, "Read-only file system", "/x")))
        p.lang = "en"
        self.assertEqual(p.error_text(e), "Folder 3 is full (20 songs).")
        self.assertEqual(p.step_text(Text("rename_folder", "rename folder {folder}", folder=2)), "renamed folder 2")


class InfoPanelTests(unittest.TestCase):
    @staticmethod
    def _panel():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication, QWidget
        from kn_songboek.gui.qt_app import InfoPanel
        QApplication.instance() or QApplication([])

        def mem(n, name):
            return {"number": n, "name": name, "tempo": 120, "rhythm": "8 Beat Rock", "chord": "fingered",
                    "sounds": [("R1", "Rechterhand 1", "Flute", 100)] if name else []}

        class P:
            session = object()
            calls = []
            def t(self, key, **kw): return key + (repr(sorted(kw.items())) if kw else "")
            def song_panel(self, slot):
                self.calls.append(slot)
                return {"banks": [{"label": "A", "name": "", "used": 8,
                                   "memories": [mem(i + 1, "Zeeman %d" % (i + 1)) for i in range(8)]},
                                  {"label": "B", "name": "Polka", "used": 1,
                                   "memories": [mem(1, "Polka 1"), dict(mem(2, ""), filled=True, tempo=98)]
                                   + [mem(i + 3, "") for i in range(6)]},
                                  {"label": "C", "name": "", "used": 0, "memories": [mem(i + 1, "") for i in range(8)]}],
                        "saved": "3 BANK", "recording": [], "styles": [(1, "MY WALTZ", ["Waltz 1"])],
                        "pads": [], "own_sounds": [], "drum_kit": "", "has_sounds": False, "bmp": b"",
                        "files": [("PMT", "1 KB")], "errors": []}

        tmp = tempfile.mkdtemp()
        win = QWidget()
        win.settings = QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat)
        win.presenter = P()
        return InfoPanel(win), win

    def test_details_fill_in_after_the_click(self):
        panel, win = self._panel()
        panel.show_info(("Song", [("Tempo", "120")]), (1, 1))
        self.assertTrue(panel.sections["banks"]["box"].isHidden())      # not yet: arrowing stays quick
        panel._load_details()
        self.assertEqual(win.presenter.calls, [(1, 1)])
        self.assertFalse(panel.sections["banks"]["box"].isHidden())
        self.assertFalse(panel.sections["styles"]["box"].isHidden())
        self.assertTrue(panel.sections["recording"]["box"].isHidden())   # nothing recorded: no heading
        self.assertEqual([b.text() for b in panel.bank_buttons], ["A", "B", "C"])
        self.assertTrue(panel.bank_buttons[2].property("empty"))
        self.assertIn("Zeeman 1", panel.mem_buttons[0].text())
        self.assertIn("Flute", panel.detail.text())
        panel._choose_bank(1)
        panel._choose_button(0)
        self.assertIn("Polka 1", panel.detail.text())
        self.assertFalse(panel.mem_buttons[1].property("empty"))         # no name, but it has settings
        self.assertIn("panel_no_name", panel.mem_buttons[1].text())
        self.assertTrue(panel.mem_buttons[2].property("empty"))
        panel._choose_button(1)
        self.assertIn("98", panel.detail.text())
        panel.show_info(None)
        self.assertTrue(panel.sections["banks"]["box"].isHidden())

    def test_list_view_shows_every_bank_and_choices_are_remembered(self):
        panel, win = self._panel()
        panel.show_info(("Song", []), (1, 1))
        panel._load_details()
        panel._set_view("list")
        self.assertTrue(panel.pad_grid.isHidden())
        text = panel.bank_list.text()
        for name in ("Zeeman 1", "Zeeman 8", "Polka 1"):
            self.assertIn(name, text)
        panel.sections["styles"]["head"].setChecked(False)              # fold "Composer-stijlen"
        from kn_songboek.gui.qt_app import InfoPanel
        again = InfoPanel(win)
        self.assertEqual(again.view, "list")
        self.assertIn("styles", again.closed)
        self.assertFalse(again.sections["styles"]["head"].isChecked())


class StrayNoticeTests(unittest.TestCase):
    def setUp(self):
        from kn_songboek.formats import layout
        self.tmp = tempfile.TemporaryDirectory()
        self.st, s = card_with_songs({1: ["A"]})
        s.save()
        self.st.capacity = 10_000_000
        self.st.write(layout.folder_dir(0) + "/SONG009.SQT", b"x")
        self.view = FakeView()
        self.view.asked = []
        self.p = MainPresenter(self.view, opener=lambda path: CardSession.open(self.st), backup_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def open_answering(self, answer):
        self.view.ask = lambda text, buttons: (self.view.asked.append(text), answer)[1]
        self.p.open_card("card")

    def test_keep_leaves_everything(self):
        self.open_answering(1)
        self.assertEqual(len(self.view.asked), 1)
        self.assertIn("TFLD001/SONG009.SQT", self.view.asked[0])
        self.assertFalse(self.p.session.dirty)

    def test_clean_up_is_a_planned_step(self):
        self.open_answering(0)
        self.assertTrue(self.p.session.dirty)
        self.assertEqual(self.p.session.stray_files(), [])
        self.assertIn("opgeruimd", self.view.status)


class CardCheckOnOpenTests(unittest.TestCase):
    def setUp(self):
        from kn_songboek.formats import layout
        self.layout = layout
        self.tmp = tempfile.TemporaryDirectory()
        self.st, s = card_with_songs({1: ["A", "B"]})
        s.save()
        self.st.capacity = 10_000_000
        self.view = FakeView()
        self.view.asked = []
        self.p = MainPresenter(self.view, opener=lambda path: CardSession.open(self.st), backup_dir=self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def open_answering(self, answer):
        self.view.ask = lambda text, buttons: (self.view.asked.append((text, buttons)), answer)[1]
        self.p.open_card("card")

    def test_unfinished_save_is_reported_and_can_wait(self):
        self.st.write(self.layout.JOB_PATH, b"started 2026-11-16T14:00:00\nbackup \n")
        self.open_answering(1)                                  # no back-up: [repair, later]
        text, buttons = self.view.asked[0]
        self.assertIn("niet afgemaakt", text)
        self.assertEqual(len(buttons), 2)
        self.assertTrue(self.st.exists(self.layout.JOB_PATH))   # "Later" changes nothing

    def test_missing_files_offer_repair(self):
        e = CardSession.open(self.st).db.song(0, 1)
        for p in self.layout.song_paths(0, 1, e).values():
            self.st.remove(p)
        self.open_answering(None)
        self.assertIn("niet op staan", self.view.asked[0][0])

    def test_saved_message_says_the_card_was_checked(self):
        self.open_answering(None)
        self.assertEqual(self.view.asked, [])
        self.p.session.rename_song(1, 1, "Nieuw")
        self.assertTrue(self.p.save())
        self.assertIn("hele kaart nagekeken", self.view.status)
