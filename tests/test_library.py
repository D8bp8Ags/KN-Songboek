import os
import struct
import tempfile
import unittest

from kn_songboek.core import CardSession
from kn_songboek.core.library import Library, copy_into, find_cards
from kn_songboek.formats import container
from kn_songboek.storage import DirectoryStorage
from kn_songboek.storage.fatimage import FatImageStorage
from kn_songboek.storage.memory import MemoryStorage
from test_fatimage import make_image


def sqt_file(tempo, recorded):
    r = bytearray(0x8E0)
    r[0:7] = b"ZZZZ\x01\x01\x0d"
    for t in range(16):
        struct.pack_into("<BH", r, 0xD0 + 3 * t, 0, 1 if (recorded and t == 0) else 0xFFFF)
    r[0x100:0x110] = b"_" * 16
    pm = bytes([0x42, 14]) + bytes([0x5A, 0, 0, 0x10, 0, 0, 0, 0, tempo, 0, 0, 0, 0, 0]) + b"\xff\xff"
    r[0x140:0x140 + len(pm)] = pm
    cell = bytes([0]) + struct.pack("<HH", 0, 0xFFFF) + (b"\x00\x90\x3c\x64\x30\x00\x82").ljust(251, b"\x81")
    return container.build_kd2(bytes(r), cell if recorded else b"")


def add(session, folder, name, tempo, recorded=False, extra=b""):
    src = MemoryStorage({"x.SQT": sqt_file(tempo, recorded), "x.PMT": b"pmt" + extra})
    session.import_song(src, {"SQT": "x.SQT", "PMT": "x.PMT"}, name, folder)


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = os.path.join(self.tmp.name, "Bibliotheek")
        a = CardSession.create(DirectoryStorage(os.path.join(self.root, "Kaart 01")))
        add(a, 1, "WALTZ", 90)
        add(a, 1, "ROCK", 140, recorded=True)
        a.save()
        b = CardSession.create(DirectoryStorage(os.path.join(self.root, "Oud", "Kaart 1998")))
        add(b, 4, "WALTZ COPY", 90)                     # identical files, other name
        add(b, 4, "WALTZ", 90, extra=b"edited")         # same name, other content
        b.save()
        os.makedirs(os.path.join(self.root, "Leeg"))
        img = os.path.join(self.root, "piet.img")
        make_image(img)
        st = FatImageStorage(img)
        c = CardSession.create(st)
        add(c, 2, "ROCK", 140, recorded=True)
        c.save()
        st.close()
        with open(os.path.join(self.root, "kapot.img"), "wb") as fh:
            fh.write(b"not an image")

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_cards(self):
        self.assertEqual([lbl for lbl, _ in find_cards(self.root)],
                         ["Kaart 01", "kapot.img", "Oud/Kaart 1998", "piet.img"])

    def test_open_groups_identical_songs(self):
        lib = Library.open(self.root)
        self.assertEqual([c.label for c in lib.cards], ["Kaart 01", "Oud/Kaart 1998", "piet.img"])
        self.assertEqual([p.path for p in lib.problems], ["kapot.img"])
        self.assertEqual(lib.copies, 5)
        rows = [(s.name, s.cards) for s in lib.songs]
        self.assertEqual(rows, [("ROCK", ["Kaart 01", "piet.img"]),
                                ("WALTZ", ["Kaart 01", "Oud/Kaart 1998"]),
                                ("WALTZ", ["Oud/Kaart 1998"])])
        lib.close()

    def test_details_and_search(self):
        lib = Library.open(self.root)
        self.assertEqual(len(lib.search(recorded=True)), 0)          # details not read yet
        lib.fill_details()
        rock = lib.search("roc")[0]
        self.assertEqual((rock.tempo, rock.recorded), (140, True))
        self.assertEqual([s.name for s in lib.search(recorded=False)], ["WALTZ", "WALTZ"])
        self.assertEqual(len(lib.search(tempo_min=100)), 1)
        self.assertEqual(len(lib.search(card="Oud/Kaart 1998")), 2)
        self.assertEqual(len(lib.search("copy")), 1)                 # matches another copy's name
        lib.close()

    def test_compose_new_card(self):
        lib = Library.open(self.root)
        new = CardSession.create(DirectoryStorage(os.path.join(self.tmp.name, "Nieuw")))
        for s in lib.songs:
            copy_into(new, s, 1)
        new.save()
        lib.close()
        again = CardSession.open(DirectoryStorage(os.path.join(self.tmp.name, "Nieuw")))
        self.assertEqual([x.name for x in again.folders()[0].songs], ["ROCK", "WALTZ", "WALTZ"])
        self.assertEqual(again.validate(), [])
        self.assertEqual(Library.open(self.root).copies, 5)          # library untouched


class LibraryCliTests(LibraryTests):
    def run_cli(self, *argv):
        import io
        from contextlib import redirect_stdout
        from kn_songboek.cli.main import main
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--backup-dir", os.path.join(self.tmp.name, "bk")] + list(argv))
        return code, buf.getvalue()

    def test_cli(self):
        code, out = self.run_cli("library", "ls", self.root)
        self.assertEqual(code, 0)
        self.assertIn("ROCK", out)
        self.assertIn("3 song(s), 3 card(s); skipped: kapot.img", out)
        code, out = self.run_cli("library", "search", self.root, "--recorded", "--tempo", "130-150", "--json")
        import json
        rows = json.loads(out)
        self.assertEqual([(r["name"], r["tempo"]) for r in rows], [("ROCK", 140)])
        target = os.path.join(self.tmp.name, "Nieuw")
        CardSession.create(DirectoryStorage(target))
        code, out = self.run_cli("library", "copy", self.root, target, "7", "Oud/Kaart 1998:4/2", "piet.img:2/1")
        self.assertEqual(code, 0, out)
        self.assertEqual([x.name for x in CardSession.open(DirectoryStorage(target)).folders()[0].songs], ["WALTZ", "ROCK"])
        self.assertEqual(self.run_cli("library", "copy", self.root, target, "7", "Kaart 01:9/9")[0], 2)
        code, out = self.run_cli("library", "copy-folder", self.root, target, "Kaart 01:1")
        self.assertEqual(code, 0, out)
        self.assertIn("copied to folder 1 (2 songs)", out)
        s = CardSession.open(DirectoryStorage(target))
        s.set_song_list(1, [(1, 2), (1, 1)])
        s.save()
        code, out = self.run_cli("library", "copy-list", target, target, "x:1")
        self.assertEqual(code, 2)                                   # target is not a library card label
