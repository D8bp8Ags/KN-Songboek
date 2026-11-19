"""A copy of the whole library on a USB stick (core/library_copy.py): checked, and said."""
import os
import tempfile
import time
import unittest

from kn_songboek.core import KN7Error, library_copy


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class LibraryCopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.lib = os.path.join(self.tmp.name, "KN7000 Bibliotheek")
        self.stick = os.path.join(self.tmp.name, "STICK")
        os.makedirs(self.stick)
        write(os.path.join(self.lib, "Kaart A", "PRIVATE", "X.SQT"), b"a" * 100)
        write(os.path.join(self.lib, "Diskettes", "Reeks 1", "01.PMT"), b"b" * 50)

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_copy_then_only_what_changed(self):
        rep = library_copy.copy_library(self.lib, self.stick)
        self.assertEqual(rep.folder, os.path.join(self.stick, "KN7000 Bibliotheek"))
        self.assertEqual((rep.copied, rep.same, rep.extra, rep.size), (2, 0, [], 150))
        with open(os.path.join(rep.folder, "Kaart A", "PRIVATE", "X.SQT"), "rb") as fh:
            self.assertEqual(fh.read(), b"a" * 100)
        rep = library_copy.copy_library(self.lib, self.stick)
        self.assertEqual((rep.copied, rep.same), (0, 2))
        time.sleep(0.01)
        write(os.path.join(self.lib, "Kaart A", "PRIVATE", "X.SQT"), b"c" * 101)     # changed in the library
        os.remove(os.path.join(self.lib, "Diskettes", "Reeks 1", "01.PMT"))         # gone from the library
        rep = library_copy.copy_library(self.lib, self.stick)
        self.assertEqual((rep.copied, rep.same), (1, 0))
        self.assertEqual(rep.extra, [os.path.join("Diskettes", "Reeks 1", "01.PMT")])   # never removed
        self.assertTrue(os.path.exists(os.path.join(rep.folder, "Diskettes", "Reeks 1", "01.PMT")))

    def test_not_inside_the_library(self):
        with self.assertRaises(KN7Error) as e:
            library_copy.copy_library(self.lib, os.path.join(self.lib, "Kaart A"))
        self.assertEqual(e.exception.key, "copy_inside_library")

    def test_a_copy_that_reads_back_wrong_stops(self):
        from unittest import mock
        with mock.patch.object(library_copy, "_read_past_cache", return_value=b"other"):
            with self.assertRaises(KN7Error) as e:
                library_copy.copy_library(self.lib, self.stick)
        self.assertEqual(e.exception.key, "copy_read_back")

    def test_the_app_says_what_it_did(self):
        from kn_songboek.gui.presenter import MainPresenter
        from test_presenter import FakeView
        view = FakeView()
        p = MainPresenter(view, backup_dir=self.tmp.name)
        self.assertIsNone(p.copy_library(self.stick))
        self.assertIn("nog geen bibliotheek", view.errors[-1])
        p.library, p.library_path = object(), self.lib
        self.assertTrue(p.copy_library(self.stick))
        self.assertIn("✓ Gekopieerd: 2 bestanden", view.done)
        self.assertIn("byte voor byte gelijk", view.done)
        p.copy_library(self.stick)
        self.assertIn("✓ Al gelijk op de kopie: 2 bestanden", view.done)


if __name__ == "__main__":
    unittest.main()
