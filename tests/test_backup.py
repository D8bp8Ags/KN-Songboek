import datetime as dt
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

from kn_songboek.cli.main import main
from kn_songboek.core import CardSession, KN7Error
from kn_songboek.core import backup as bk
from kn_songboek.formats import layout
from kn_songboek.storage import DirectoryStorage
from kn_songboek.storage.memory import MemoryStorage

from helpers import card_with_songs


def run(*argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(argv))
    return code, buf.getvalue()


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_backup_and_restore_roundtrip(self):
        st, s = card_with_songs({1: ["A", "B"]})
        st.write(".DS_Store", b"x")
        z = bk.make_backup(st, self.dir, label="card")
        before = dict(st.files)
        s.delete_song(1, 1)
        s.move_song(1, 2, 5)
        s.save()
        self.assertNotEqual(st.files, before)
        bk.restore(st, z)
        self.assertEqual(st.files, before)

    def test_prune_keeps_newest(self):
        st, _ = card_with_songs({1: ["A"]})
        for i in range(4):
            bk.make_backup(st, self.dir, keep=2, label="c", now=dt.datetime(2026, 1, 1, 12, 0, i))
        items = bk.list_backups(os.path.join(self.dir, "c"))
        self.assertEqual([b.created[-2:] for b in items], ["03", "02"])
        self.assertEqual(items[0].songs, 1)

    def test_prune_leaves_another_card_with_the_same_name_alone(self):
        a, _ = card_with_songs({1: ["A", "B"]})
        b, _ = card_with_songs({1: ["X", "Y"]})
        bk.make_backup(b, self.dir, keep=2, label="NO_NAME", now=dt.datetime(2026, 1, 1, 11, 0, 0))
        for i in range(4):
            bk.make_backup(a, self.dir, keep=2, label="NO_NAME", now=dt.datetime(2026, 1, 1, 12, 0, i))
        items = bk.list_backups(os.path.join(self.dir, "NO_NAME"))
        self.assertEqual([b.created[-5:] for b in items], ["00:03", "00:02", "00:00"])  # card b's survives
        self.assertEqual(bk.contents(items[2].path), [(1, "", ["X", "Y"])])
        self.assertEqual(sorted(bk.as_storage(items[0].path).files), sorted(a.files))

    def test_list_all_and_library_backups(self):
        st, _ = card_with_songs({1: ["A"]})
        bk.make_backup(st, self.dir, label="Kaart", now=dt.datetime(2026, 1, 1))
        bk.make_backup(st, self.dir, label="Kaart-bibliotheek", now=dt.datetime(2026, 1, 2))
        items = bk.list_all(self.dir)
        self.assertEqual([(b.card_name, b.library) for b in items], [("Kaart", True), ("Kaart", False)])

    def test_restore_rejects_foreign_zip(self):
        import zipfile
        bad = os.path.join(self.dir, "x.zip")
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../evil", b"")
        with self.assertRaises(KN7Error):
            bk.restore(MemoryStorage(), bad)

    def test_preflight_write_protect_and_space(self):
        st, s = card_with_songs({1: ["A"]})
        st.read_only = True
        s.rename_song(1, 1, "B")
        with self.assertRaisesRegex(KN7Error, "write-protected"):
            s.save()
        st.read_only = False
        st.capacity = sum(len(v) for v in st.files.values()) + 10
        s.move_song(1, 1, 2, copy=True)
        with self.assertRaisesRegex(KN7Error, "not enough space"):
            s.save()

    def test_cli_backs_up_before_writing_and_logs(self):
        root = os.path.join(self.dir, "SDCARD")
        s = CardSession.create(DirectoryStorage(root))
        s.import_song(MemoryStorage({"a.SQT": b"1"}), {"SQT": "a.SQT"}, "MY WAY", 3)
        s.save()
        log = os.path.join(self.dir, "kn7.log")
        bdir = os.path.join(self.dir, "b")
        code, out = run("--log", log, "--backup-dir", bdir, "move", root, "3", "1", "7")
        self.assertEqual(code, 0, out)
        self.assertIn("back-up:", out)
        self.assertIn("move %s/TFLD003/01003KN7.SQT" % layout.KN7_DIR, open(log).read())
        code, out = run("--backup-dir", bdir, "backups", root)
        self.assertIn("1 songs", out)
        code, out = run("--backup-dir", bdir, "restore", root, "1", "--no-backup")
        self.assertEqual(code, 0, out)
        self.assertTrue(os.path.exists(os.path.join(root, layout.KN7_DIR, "TFLD003/01003KN7.SQT")))
        self.assertFalse(os.path.exists(os.path.join(root, layout.KN7_DIR, "TFLD007/01007KN7.SQT")))
        code, out = run("info", root)
        self.assertIn("songs      1 in", out)
