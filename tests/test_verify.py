"""Checked copying into the library (core/verify.py): every check is counted and said."""
import os
import tempfile
import unittest

from kn_songboek.core import CardSession, KN7Error, cards, floppy, verify
from kn_songboek.formats import container
from kn_songboek.storage import DirectoryStorage
from kn_songboek.storage.memory import MemoryStorage

from test_floppy import make_diskette
from test_library import add


def build_id(payload):
    """A KN6000 one-part container ('I KD', raw deflate + adler32)."""
    import struct
    import zlib
    c = zlib.compressobj(6, zlib.DEFLATED, -15)
    return (b"I KD" + struct.pack(">HH", 1, 0) + struct.pack("<II", 0, len(payload)) + c.compress(payload) + c.flush()
            + struct.pack(">I", zlib.adler32(payload)))


class Flaky(MemoryStorage):
    """A card whose file X.SQT reads differently on some reads (a weak spot)."""

    def __init__(self, files, answers):
        super().__init__(files)
        self.answers = list(answers)

    def read_from_card(self, path):
        if path.upper().endswith("X.SQT") and self.answers:
            return self.answers.pop(0)
        return self.read(path)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = os.path.join(self.tmp.name, "lib")

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_card_is_read_twice_unpacked_and_read_back(self):
        card = os.path.join(self.tmp.name, "card")
        s = CardSession.create(DirectoryStorage(card))
        add(s, 1, "WALTZ", 90)
        add(s, 2, "ROCK", 140, recorded=True)
        s.save()
        check = verify.CopyCheck()
        folder = cards.archive_card(DirectoryStorage(card), self.lib, "Kaart A", check=check)
        n = sum(len(f) for _, _, f in os.walk(folder))
        self.assertEqual((check.files, check.read_twice, check.read_back), (n, n, n))
        self.assertEqual(check.song_files, 4)                 # 2 SQT + 2 PMT
        self.assertEqual((check.unpacked, check.checksum), (4, 0))   # KN7000 files: no checksum
        self.assertTrue(check.ok)

    def test_a_diskette_is_checked_with_its_checksums(self):
        disk = os.path.join(self.tmp.name, "disk")
        make_diskette(disk)
        for n in os.listdir(disk):                         # pack the PMT files like a KN6000 diskette
            if n.endswith(".PMT"):
                p = os.path.join(disk, n)
                with open(p, "rb") as fh:
                    payload = container.parse(fh.read(), "PMT").parts[0]
                with open(p, "wb") as fh:
                    fh.write(build_id(payload))
        check = verify.CopyCheck()
        floppy.archive_floppy(disk, self.lib, "Reeks 1", check=check)
        self.assertEqual((check.files, check.read_twice, check.read_back), (10, 10, 10))
        self.assertEqual(check.song_files, 10)
        self.assertEqual(check.unpacked, 10)
        self.assertEqual(check.checksum, 2)                   # the two KN6000 PMT files
        self.assertTrue(check.ok)

    def test_a_damaged_song_file_is_copied_and_said(self):
        disk = os.path.join(self.tmp.name, "disk")
        make_diskette(disk)
        p = os.path.join(disk, "01TRAX1_.PMT")
        with open(p, "rb") as fh:
            data = fh.read()
        with open(p, "wb") as fh:
            bad = bytearray(build_id(b"x" * 100))
            bad[-1] ^= 0xFF                               # a KN6000 file whose checksum does not match
            fh.write(bytes(bad))
        check = verify.CopyCheck()
        folder = floppy.archive_floppy(disk, self.lib, "Reeks 1", check=check)
        self.assertEqual(check.not_unpacked, ["01TRAX1_.PMT"])
        self.assertFalse(check.ok)
        with open(os.path.join(folder, floppy.ORIGINALS, "01TRAX1_.PMT"), "rb") as fh:
            self.assertEqual(fh.read(), bytes(bad))       # kept as it was
        self.assertNotEqual(data, b"")

    def test_a_file_that_read_differently_once_is_said(self):
        good, bad = b"same bytes", b"other bytes"
        src = Flaky({"X.SQT": good}, [bad, good])          # 2nd read differs, the 3rd agrees with the 1st
        check = verify.CopyCheck()
        self.assertEqual(verify.read_checked(src, "X.SQT", check), good)
        self.assertEqual((check.read_twice, check.unstable), (0, ["X.SQT"]))
        with self.assertRaises(KN7Error) as e:            # three different answers: stop
            verify.read_checked(Flaky({"X.SQT": good}, [bad, b"third"]), "X.SQT", verify.CopyCheck())
        self.assertEqual(e.exception.key, "read_unstable")

    def test_a_failed_check_leaves_no_half_copy(self):
        card = os.path.join(self.tmp.name, "card")
        s = CardSession.create(DirectoryStorage(card))
        add(s, 1, "WALTZ", 90)
        s.save()

        class Broken(DirectoryStorage):
            def read_from_card(self, path):
                return os.urandom(8)
        with self.assertRaises(KN7Error):
            cards.archive_card(Broken(card), self.lib, "Kaart A")
        self.assertEqual(os.listdir(self.lib), [])

    def test_the_app_says_every_check(self):
        from kn_songboek.gui.presenter import MainPresenter
        errors = []

        class View:
            def show_error(self, text):
                errors.append(text)
        p = MainPresenter.__new__(MainPresenter)
        p.lang, p.view = "nl", View()
        c = verify.CopyCheck(files=10, read_twice=10, unpacked=10, checksum=2, song_files=10, read_back=10)
        self.assertEqual(p.check_text(c).split("\n"), [
            "✓ Gelezen: 10 bestanden, elk twee keer, steeds hetzelfde",
            "✓ Uitgepakt: 10 songbestanden, waarvan 2 met een controlegetal dat klopt",
            "✓ Teruggelezen in de bibliotheek: 10 bestanden, byte voor byte gelijk"])
        self.assertEqual(errors, [])
        c.not_unpacked = ["01TRAX1_.LSW"]
        self.assertIn("⚠ 1 songbestand(en) konden niet worden uitgepakt.", p.check_text(c))
        self.assertIn("01TRAX1_.LSW", errors[0])


if __name__ == "__main__":
    unittest.main()


class DamagedInLibraryTests(unittest.TestCase):
    def test_a_damaged_song_is_orange_and_asked_before_it_goes_on_a_card(self):
        from kn_songboek.core.library import Library
        from kn_songboek.gui.presenter import MainPresenter
        with tempfile.TemporaryDirectory() as tmp:
            disk = os.path.join(tmp, "disk")
            make_diskette(disk)
            bad = bytearray(build_id(b"x" * 100))
            bad[-1] ^= 0xFF                                # checksum wrong
            with open(os.path.join(disk, "01TRAX1_.PMT"), "wb") as fh:
                fh.write(bytes(bad))
            lib_dir = os.path.join(tmp, "lib")
            floppy.archive_floppy(disk, os.path.join(lib_dir, "Diskettes"), "Reeks 1")
            lib = Library.open(lib_dir)
            asked = []

            class View:
                def __init__(self):
                    self.answer = False

                def confirm(self, text):
                    asked.append(text)
                    return self.answer

                def __getattr__(self, name):
                    return lambda *a, **k: None
            p = MainPresenter.__new__(MainPresenter)
            p.library, p.lib_filter, p.lang, p.view = lib, {}, "nl", View()
            p._notify = lambda text: None
            p.session = CardSession.create(DirectoryStorage(os.path.join(tmp, "card")))
            lib.fill_details()
            rows = {r.name.split("  ·")[0]: r for r in p.library_rows()}
            self.assertEqual(rows["TRAX1"].damaged, ("PMT",))
            self.assertEqual(rows["1FINGR"].damaged, ())
            self.assertEqual(p.import_from_library([rows["TRAX1"].index], 1), 0)     # "no": nothing happens
            self.assertIn("TRAX1 (PMT)", asked[0])
            self.assertEqual(list(p.session.db.iter_songs()), [])
            p.view.answer = True
            self.assertEqual(p.import_from_library([rows["TRAX1"].index], 1), 1)     # "yes": as it is
            self.assertEqual(p.import_from_library([rows["1FINGR"].index], 1), 1)    # a good song: no question
            self.assertEqual(len(asked), 2)
            lib.close()
