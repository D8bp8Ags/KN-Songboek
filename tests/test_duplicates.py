import unittest

from kn_songboek.core import CardSession
from kn_songboek.core.duplicates import find_duplicates
from kn_songboek.formats import layout
from kn_songboek.storage.memory import MemoryStorage


def card():
    st = MemoryStorage()
    s = CardSession.create(st)
    a = MemoryStorage({"x.SQT": b"song a", "x.PMT": b"pmt a"})
    b = MemoryStorage({"x.SQT": b"song b", "x.PMT": b"pmt b"})
    b2 = MemoryStorage({"x.SQT": b"song b EDITED", "x.PMT": b"pmt b"})
    files = {"SQT": "x.SQT", "PMT": "x.PMT"}
    s.import_song(a, files, "ALPHA", 1)        # 1/1
    s.import_song(a, files, "ALPHA", 5)        # 5/1  identical copy
    s.import_song(a, files, "ALPHA COPY", 9)   # 9/1  identical, other name
    s.import_song(b, files, "BETA", 1)         # 1/2
    s.import_song(b2, files, "BETA", 2)        # 2/1  same name, edited
    s.save()
    return st, CardSession.open(st)


class DuplicateTests(unittest.TestCase):
    def test_find(self):
        _, s = card()
        groups = find_duplicates(s)
        self.assertEqual([(g.kind, g.slots) for g in groups],
                         [("identical", [(1, 1), (5, 1), (9, 1)]), ("same_name", [(1, 2), (2, 1)])])
        self.assertEqual(groups[0].saving, 2 * len(b"song a" + b"pmt a"))
        self.assertEqual(groups[1].saving, 0)

    def test_merge_redirects_lists_and_removes_files(self):
        st, s = card()
        s.set_favorite(1, 1, (5, 1))
        s.set_song_list(1, [(1, 1), (5, 1), (1, 2)])
        s.save()
        s = CardSession.open(st)
        self.assertEqual(s.merge_duplicates((1, 1), [(5, 1), (9, 1)], song_list=2), 2)
        self.assertEqual(s.favorites()[0][1][0][1:], (0, 0))          # decoded 0-based
        self.assertEqual(s.playlists()[0], [(1, 1), (1, 2)])      # no double entry
        self.assertEqual(s.playlists()[1], [(1, 1)])
        self.assertEqual(s.history(), ["merge 2 copies into 1/1"])
        s.save()
        s = CardSession.open(st)
        self.assertFalse(s.db.song(4, 0).used)
        self.assertFalse(st.exists("PRIVATE/TECHNICS/KN7000/TFLD005/01005KN7.SQT"))
        self.assertTrue(st.exists(layout.song_paths(0, 0, s.db.song(0, 0))["SQT"]))
        self.assertEqual(find_duplicates(s)[0].kind, "same_name")

    def test_undo(self):
        _, s = card()
        s.merge_duplicates((5, 1), [(1, 1)])
        s.undo()
        self.assertTrue(s.db.song(0, 0).used)
        self.assertEqual(s.pending, [])
