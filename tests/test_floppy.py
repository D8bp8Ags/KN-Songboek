import os
import tempfile
import unittest

from kn_songboek.core import CardSession, KN7Error, floppy
from kn_songboek.core.library import Library
from kn_songboek.formats import container
from kn_songboek.storage import DirectoryStorage

from test_library import sqt_file
from test_songdata import make_cmp, make_pmt, make_tm


def make_diskette(path, names=("TRAX1_", "1FINGR")):
    """A music floppy as the keyboard writes it: <nn><name6>.<EXT> in the root, no index."""
    os.makedirs(path, exist_ok=True)
    for i, n in enumerate(names, 1):
        for ext, data in (("SQT", sqt_file(120, False)), ("PMT", container.build_kd(make_pmt(True, songs=["Annie`s Song", "Big Band"]))),
                          ("CMP", container.build_kd(make_cmp())), ("TM", container.build_kd(make_tm())),
                          ("LSW", n.encode())):
            with open(os.path.join(path, "%02d%s.%s" % (i, n, ext)), "wb") as fh:
                fh.write(data)
    with open(os.path.join(path, "README.TXT"), "w") as fh:          # other files are left alone
        fh.write("x")


class FloppyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.disk = os.path.join(self.tmp.name, "DISKETTE  2")
        self.lib = os.path.join(self.tmp.name, "lib")
        make_diskette(self.disk)

    def tearDown(self):
        self.tmp.cleanup()

    def test_sets_on_a_diskette(self):
        found = floppy.sets(DirectoryStorage(self.disk))
        self.assertEqual([(s.number, s.name, sorted(s.files)) for s in found],
                         [(1, "TRAX1", ["CMP", "LSW", "PMT", "SQT", "TM"]),
                          (2, "1FINGR", ["CMP", "LSW", "PMT", "SQT", "TM"])])
        self.assertTrue(floppy.is_floppy(self.disk))
        self.assertFalse(floppy.is_floppy(self.lib))

    def test_archive_makes_a_library_card_and_keeps_the_originals(self):
        before = sorted(os.listdir(self.disk))
        folder = floppy.archive_floppy(self.disk, os.path.join(self.lib, "Diskettes"), "Reeks 1")
        self.assertEqual(sorted(os.listdir(self.disk)), before)                 # only read
        card = CardSession.open(DirectoryStorage(folder))
        self.assertEqual([(f, so, s.name) for f, so, s in card.db.iter_songs()], [(0, 0, "TRAX1"), (0, 1, "1FINGR")])
        self.assertEqual(card.db.folders[0].name, "Reeks 1")
        self.assertEqual(card.validate(), [])
        self.assertEqual(len(os.listdir(os.path.join(folder, floppy.ORIGINALS))), 10)
        lib = Library.open(self.lib)
        self.assertEqual([c.label for c in lib.cards], ["Diskettes/Reeks 1"])
        self.assertEqual(sorted(s.name for s in lib.songs), ["1FINGR", "TRAX1"])
        self.assertEqual(sorted(s.name for s in lib.search(source="floppy")), ["1FINGR", "TRAX1"])   # filter
        self.assertEqual(lib.search(source="card"), [])
        with self.assertRaises(KN7Error):                                       # name taken
            floppy.archive_floppy(self.disk, os.path.join(self.lib, "Diskettes"), "Reeks 1")
        floppy.archive_floppy(self.disk, os.path.join(self.lib, "Diskettes"), "Reeks 1", replace=True)

    def test_songs_inside_a_set_are_shown_and_found(self):
        from kn_songboek.gui.presenter import MainPresenter
        floppy.archive_floppy(self.disk, os.path.join(self.lib, "Diskettes"), "Reeks 1")
        lib = Library.open(self.lib)
        self.assertEqual([s.titles for s in lib.songs], [["Annie's Song", "Big Band"]] * 2)
        self.assertEqual(sorted(s.name for s in lib.search("annie`s")), ["1FINGR", "TRAX1"])
        self.assertEqual(lib.search("cocktail"), [])
        p = MainPresenter.__new__(MainPresenter)
        p.library, p.lib_filter, p.lang = lib, {"text": "big"}, "nl"
        rows = p.library_rows()
        self.assertEqual(sorted(r.name for r in rows), ["1FINGR  ·  met Big Band", "TRAX1  ·  met Big Band"])
        self.assertEqual(rows[0].inside, ("Annie's Song", "Big Band"))
        p.lib_filter = {}
        self.assertIn("TRAX1  ·  set met 2 songs", [r.name for r in p.library_rows()])
        card = CardSession.open(DirectoryStorage(os.path.join(self.lib, "Diskettes", "Reeks 1")))
        self.assertEqual(card.set_titles(1, 1), ["Annie's Song", "Big Band"])
        self.assertEqual(card.chord_mode(1, 1), 2)
        p.session = card
        info = dict(p.song_info((1, 1))[1])
        self.assertEqual([k for k in info if k.startswith("Reg Bank")],
                         ["Reg Bank A", "Reg Bank B", "Reg Bank C", "Reg Bank 1"])
        self.assertIn("8 van de 8 knoppen", info["Reg Bank 1"])
        self.assertEqual(info["Opgeslagen met"], "ALL (alle 4 Reg Banks)")
        # song list: each song of a set on its own line, with the set it comes from
        rows = p.export_rows(["folder", "song", "name", "set"])
        self.assertEqual([(r["name"], r["set"]) for r in rows],
                         [("TRAX1", ""), ("Annie's Song", "TRAX1"), ("Big Band", "TRAX1"),
                          ("1FINGR", ""), ("Annie's Song", "1FINGR"), ("Big Band", "1FINGR")])
        self.assertEqual(rows[1]["song"], "01")                            # where it is: the set's place
        lib_rows = p.library_export_rows(["name", "set"], by_name=True)
        self.assertEqual([(r["name"], r["set"]) for r in lib_rows][:2], [("1FINGR", ""), ("Annie's Song", "1FINGR")])
        self.assertTrue(all(r["where"] for r in lib_rows))
        html = p._tables([], [("", rows)], ["song", "name", "set"], p.export_labels, ())
        self.assertIn(">Uit set</th>", html)
        self.assertEqual(info["Akkoorden"], "zelf spelen (fingered)")
        from kn_songboek.formats import songdata
        pmt = bytearray(make_pmt())             # one SD song, saved with 3 BANK; bank C left empty
        pmt[0x10 + 2 * (0x10 + 8 * 0x750) + 0x10:] = bytes(len(pmt) - (0x10 + 2 * (0x10 + 8 * 0x750) + 0x10))
        self.assertEqual(p._bank_rows(songdata.read_pmt(bytes(pmt))),
                         [("Opgeslagen met", "3 BANK (alleen Reg Bank A, B en C)"),
                          ("Reg Bank A", "Bank 1, 8 van de 8 knoppen"), ("Reg Bank B", "Bank 2, 8 van de 8 knoppen"),
                          ("Reg Bank C", "leeg")])

    def test_empty_disk_is_refused(self):
        empty = os.path.join(self.tmp.name, "leeg")
        os.makedirs(empty)
        with self.assertRaises(KN7Error):
            floppy.archive_floppy(empty, self.lib, "x")
