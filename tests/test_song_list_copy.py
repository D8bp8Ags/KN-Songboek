import unittest

from kn_songboek.core import CardSession, SlotError
from kn_songboek.storage.memory import MemoryStorage


def song(content):
    return MemoryStorage({"x.SQT": content, "x.PMT": b"pmt" + content}), {"SQT": "x.SQT", "PMT": "x.PMT"}


def card(songs, lists=None):
    st = MemoryStorage()
    s = CardSession.create(st)
    for folder, name, content in songs:
        src, files = song(content)
        s.import_song(src, files, name, folder)
    for n, slots in (lists or {}).items():
        s.set_song_list(n, slots)
    s.save()
    return st, CardSession.open(st)


class SongListCopyTests(unittest.TestCase):
    def setUp(self):
        _, self.src = card([(2, "A", b"a"), (2, "B", b"b"), (7, "C", b"c")], {2: [(7, 1), (2, 1), (2, 2)]})

    def test_copy_reuses_identical_and_keeps_order(self):
        st, dst = card([(1, "B HERE", b"b"), (1, "OTHER", b"x")], {1: [(1, 2)]})
        r = dst.import_song_list(self.src, 2, folder_name="BRUILOFT", reuse=True)
        self.assertEqual(r, {"list": 2, "folder": 2, "copied": 2, "reused": 1})
        self.assertEqual(dst.playlists()[1], [(2, 1), (2, 2), (1, 1)])      # C, A, then the B already here
        self.assertEqual(dst.db.folders[1].name, "BRUILOFT")
        self.assertEqual(dst.history(), ["copy song list 2 -> list 2"])
        dst.save()
        again = CardSession.open(st)
        self.assertEqual([x.name for x in again.folders()[1].songs], ["C", "A"])
        self.assertEqual(again.validate(), [])
        dst.undo() if dst.dirty else None

    def test_undo_is_one_step(self):
        _, dst = card([])
        dst.import_song_list(self.src, 2)
        dst.undo()
        self.assertEqual(dst.pending, [])
        self.assertEqual(dst.playlists(), [[], [], []])

    def test_errors(self):
        _, dst = card([], {1: [], 2: [], 3: []})
        with self.assertRaises(SlotError):
            dst.import_song_list(self.src, 1)                       # empty source list
        _, full = card([(1, "X", b"x")], {1: [(1, 1)], 2: [(1, 1)], 3: [(1, 1)]})
        with self.assertRaises(SlotError):
            full.import_song_list(self.src, 2)                      # no free list
        r = full.import_song_list(self.src, 2, to_list=3, folder=1)
        self.assertEqual((r["list"], r["folder"]), (3, 1))
        self.assertEqual(full.playlists()[2], [(1, 2), (1, 3), (1, 4)])

    def test_default_copies_everything_in_list_order(self):
        _, dst = card([(1, "B HERE", b"b")])
        r = dst.import_song_list(self.src, 2)
        self.assertEqual((r["copied"], r["reused"], r["folder"]), (3, 0, 2))
        self.assertEqual([x.name for x in dst.folders()[1].songs], ["C", "A", "B"])
        self.assertEqual(dst.playlists()[0], [(2, 1), (2, 2), (2, 3)])

    def test_copy_folder(self):
        self.src.rename_folder(2, "ZATERDAG")
        _, dst = card([(1, "X", b"x")])
        r = dst.import_folder(self.src, 2)
        self.assertEqual(r, {"folder": 2, "copied": 2, "name": "ZATERDAG",
                             "favorites": {"carried": 0, "banks": [], "left": 0}})
        self.assertEqual([(x.song, x.name) for x in dst.folders()[1].songs], [(1, "A"), (2, "B")])
        self.assertEqual(dst.db.folders[1].name, "ZATERDAG")
        self.assertEqual(len(dst.history()), 1)
        with self.assertRaises(SlotError):
            dst.import_folder(self.src, 2, to_folder=1)              # not empty
