import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from kn_songboek.cli.main import main
from kn_songboek.core import CardSession
from kn_songboek.storage import DirectoryStorage
from kn_songboek.storage.memory import MemoryStorage


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        s = CardSession.create(DirectoryStorage(self.root))
        src = MemoryStorage({"a.SQT": b"1", "a.PMT": b"2"})
        s.import_song(src, {"SQT": "a.SQT", "PMT": "a.PMT"}, "MY WAY", 3)
        s.save()

    def tearDown(self):
        self.tmp.cleanup()

    def test_ls_json(self):
        code, out = run("ls", self.root, "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)[0]["songs"][0]["name"], "MY WAY")

    def test_dry_run_writes_nothing(self):
        code, out = run("move", self.root, "3", "1", "7", "--dry-run")
        self.assertIn("move PRIVATE/TECHNICS/KN7000/TFLD003/01003KN7.SQT", out)
        self.assertTrue(os.path.exists(os.path.join(self.root, "PRIVATE/TECHNICS/KN7000/TFLD003/01003KN7.SQT")))

    def test_move_and_check(self):
        self.assertEqual(run("move", self.root, "3", "1", "7")[0], 0)
        self.assertEqual(run("check", self.root)[0], 0)
        self.assertTrue(os.path.exists(os.path.join(self.root, "PRIVATE/TECHNICS/KN7000/TFLD007/01007KN7.PMT")))

    def test_duplicates_and_dedupe(self):
        self.assertEqual(run("copy", self.root, "3", "1", "8", "--no-backup")[0], 0)
        code, out = run("duplicates", self.root)
        self.assertIn("2 identical copies: 3/1, 8/1", out)
        self.assertEqual(run("dedupe", self.root, "8/1", "--song-list", "1", "--no-backup")[0], 0)
        code, out = run("duplicates", self.root)
        self.assertIn("no songs stored more than once", out)
        s = CardSession.open(DirectoryStorage(self.root))
        self.assertEqual(s.playlists()[0], [(8, 1)])
        self.assertFalse(s.db.song(2, 0).used)
        self.assertEqual(run("dedupe", self.root, "8/1", "--no-backup")[0], 1)

    def test_error_exit_code(self):
        self.assertEqual(run("delete", self.root, "3", "9")[0], 2)


class CliListsTests(unittest.TestCase):
    def test_favorite_songlist_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            a, b = os.path.join(tmp, "a"), os.path.join(tmp, "b")
            for root, f in ((a, 3), (b, 8)):
                s = CardSession.create(DirectoryStorage(root))
                s.import_song(MemoryStorage({"x.SQT": b"1"}), {"SQT": "x.SQT"}, "SONG%d" % f, f)
                s.save()
            self.assertEqual(run("rename-bank", a, "1", "Avond", "--no-backup")[0], 0)
            self.assertEqual(run("set-favorite", a, "1", "2", "3/1", "--no-backup")[0], 0)
            self.assertEqual(run("songlist", a, "2", "3/1", "--no-backup")[0], 0)
            self.assertEqual(run("import", a, b, "8", "1", "3", "--no-backup")[0], 0)
            code, out = run("favorites", a)
            self.assertIn("Avond", out)
            self.assertIn("3/1", out)
            self.assertIn("list 2: 3/1", out)
            self.assertIn("SONG8", run("ls", a)[1])
