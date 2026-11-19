import os
import tempfile
import unittest
from unittest import mock

from kn_songboek.core import CardSession
from kn_songboek.core import cards
from kn_songboek.core.backup import list_backups
from kn_songboek.core.errors import KN7Error
from kn_songboek.core.library import Library
from kn_songboek.formats import layout
from kn_songboek.storage import DirectoryStorage
from test_library import add


class CardsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = self.tmp.name
        self.volumes = os.path.join(t, "Volumes")
        self.card = os.path.join(self.volumes, "KN7000")
        s = CardSession.create(DirectoryStorage(self.card))
        add(s, 1, "WALTZ", 90)
        add(s, 1, "ROCK", 140, recorded=True)
        add(s, 2, "SAMBA", 100)
        s.save()
        with open(os.path.join(self.card, "PRIVATE", "TECHNICS", "KN7000", "TFLD001", ".DS_Store"), "wb"):
            pass
        os.makedirs(os.path.join(self.card, "SD_SOUND"))
        with open(os.path.join(self.card, "SD_SOUND", "SONG.MID"), "wb") as fh:
            fh.write(b"MThd")
        os.makedirs(os.path.join(self.volumes, "LEEG", ".Spotlight-V100"))
        os.makedirs(os.path.join(self.volumes, "FOTO", "DCIM"))
        self.library = os.path.join(t, "Bibliotheek")
        self.backups = os.path.join(t, "backups")
        env = mock.patch.dict(os.environ, {"KN_SONGBOEK_VOLUMES": self.volumes, "KN_SONGBOEK_BACKUP_DIR": self.backups})
        env.start()
        self.addCleanup(env.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def test_find_cards_classifies(self):
        found = [(c.name, c.kind, c.songs) for c in cards.find_cards()]
        self.assertEqual(found, [("KN7000", cards.KN7000, 3), ("LEEG", cards.EMPTY, 0), ("FOTO", cards.OTHER, 0)])

    def test_archive_and_library(self):
        folder = cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart bruiloften")
        self.assertEqual(os.path.basename(folder), "Kaart bruiloften")
        self.assertTrue(os.path.exists(os.path.join(folder, "SD_SOUND", "SONG.MID")))
        lib = Library.open(self.library)
        self.assertEqual(sorted(s.name for s in lib.songs), ["ROCK", "SAMBA", "WALTZ"])
        self.assertEqual(lib.songs[0].copies[0].where, "Kaart bruiloften  01/02")
        lib.close()
        with self.assertRaises(KN7Error):
            cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart bruiloften")

    def test_update_replaces_and_backs_up(self):
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A")
        s = CardSession.open(DirectoryStorage(self.card))
        add(s, 3, "NIEUW", 120)
        s.save(backup=False)
        match = cards.match_library(DirectoryStorage(self.card), self.library)
        self.assertEqual([(m[0], round(m[2], 2)) for m in match], [("Kaart A", 0.75)])
        cards.archive_card(DirectoryStorage(self.card), self.library, "Kaart A", replace=True)
        lib = Library.open(self.library)
        self.assertIn("NIEUW", [x.name for x in lib.songs])
        lib.close()
        self.assertEqual(len(list_backups(os.path.join(self.backups, "Kaart A-bibliotheek"))), 1)
        self.assertFalse(os.path.exists(os.path.join(self.library, "Kaart A.part")))

    def test_match_ignores_other_cards(self):
        other = CardSession.create(DirectoryStorage(os.path.join(self.library, "Ander")))
        add(other, 1, "WALTZ", 90)
        add(other, 1, "POLKA", 90)
        add(other, 1, "TANGO", 90)
        add(other, 1, "FOX", 90)
        other.save()
        self.assertEqual(cards.match_library(DirectoryStorage(self.card), self.library), [])

    def test_safe_name(self):
        self.assertEqual(cards.safe_name(" Kaart 1/2: feest "), "Kaart 1_2_ feest")
        with self.assertRaises(KN7Error):
            cards.safe_name(" . ")

    def test_write_new_card_to_empty_and_used_card(self):
        src = CardSession.open(DirectoryStorage(self.card))
        new = cards.new_card()
        for fi, si, song in src.db.iter_songs():
            new.import_song(src.storage, layout.song_paths(fi, si, song), song.name, 5)
        new.rename_folder(5, "SETLIST")
        new.move_song(5, 1, 7)
        empty = os.path.join(self.volumes, "LEEG")
        self.assertIsNone(cards.write_card(new, DirectoryStorage(empty)))
        out = CardSession.open(DirectoryStorage(empty))
        self.assertEqual([(f, s, x.name) for f, s, x in out.db.iter_songs()],
                         [(4, 1, "ROCK"), (4, 2, "SAMBA"), (6, 0, "WALTZ")])
        # onto the used card: old data backed up, replaced, SD_SOUND left alone
        new2 = cards.new_card()
        new2.import_song(out.storage, layout.song_paths(4, 1, out.db.song(4, 1)), "SAMBA", 1)
        backup = cards.write_card(new2, DirectoryStorage(self.card))
        self.assertTrue(backup and os.path.exists(backup))
        again = CardSession.open(DirectoryStorage(self.card))
        self.assertEqual([x.name for _, _, x in again.db.iter_songs()], ["SAMBA"])
        self.assertTrue(os.path.exists(os.path.join(self.card, "SD_SOUND", "SONG.MID")))

    def test_write_card_refuses_an_opened_card(self):
        with self.assertRaises(KN7Error):
            cards.write_card(CardSession.open(DirectoryStorage(self.card)), DirectoryStorage(self.volumes))

    def test_cli(self):
        import contextlib
        import io
        from kn_songboek.cli.main import main
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(main(["cards"]), 0)
            self.assertEqual(main(["library", "add", self.library, self.card, "Kaart C"]), 0)
            self.assertEqual(main(["library", "add", self.library, self.card, "--update"]), 0)
        text = out.getvalue()
        self.assertIn("KN7000 card, 3 song(s)", text)
        self.assertIn("updating Kaart C (100% of the songs in common)", text)


if __name__ == "__main__":
    unittest.main()


class VolumeNameTests(unittest.TestCase):
    def test_volume_name_fits_a_fat_label(self):
        self.assertEqual(cards.volume_name("Kaart bruiloften 2026"), "KAART BRUIL")
        self.assertEqual(cards.volume_name("  a/b:c*é  "), "ABC")
        self.assertEqual(cards.volume_name("..."), "")

    def test_rename_uses_diskutil_and_returns_the_new_place(self):
        import plistlib
        calls = []

        def run(cmd, **kw):
            calls.append(cmd)
            out = {"info": {"DeviceIdentifier": "disk4s1", "MountPoint": "/Volumes/FEEST"}}
            return mock.Mock(returncode=0, stdout=plistlib.dumps(out["info"]))
        with mock.patch.object(cards.sys, "platform", "darwin"), mock.patch.object(cards.subprocess, "run", run):
            self.assertEqual(cards.rename_volume("/Volumes/NO NAME", "feest"), "/Volumes/FEEST")
            self.assertEqual(cards.rename_volume("/Volumes/FEEST", "Feest"), "/Volumes/FEEST")   # already so
        self.assertEqual(calls[1], ["diskutil", "rename", "disk4s1", "FEEST"])
        self.assertEqual(len(calls), 3)
        with mock.patch.object(cards.sys, "platform", "linux"):
            self.assertIsNone(cards.rename_volume("/media/x", "FEEST"))
