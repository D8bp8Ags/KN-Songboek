import unittest

from helpers import card_with_songs
from kn_songboek.core import CardSession, NoDatabase, SlotError
from kn_songboek.formats import layout
from kn_songboek.storage.memory import MemoryStorage


class SessionTests(unittest.TestCase):
    def test_open_and_list(self):
        st, s = card_with_songs({1: ["MY WAY", "AUTUMN LEAVES"], 5: ["VOLARE"]})
        f = s.folders()
        self.assertEqual([x.folder for x in f], [1, 5])
        self.assertEqual(f[0].songs[1].name, "AUTUMN LEAVES")
        self.assertIn("PRIVATE/TECHNICS/KN7000/TFLD001/02001KN7.SQT", f[0].songs[1].files)
        self.assertEqual(s.validate(), [])

    def test_nothing_changes_before_save(self):
        st, s = card_with_songs({1: ["MY WAY"]})
        before = dict(st.files)
        s.move_song(1, 1, 3)
        s.rename_folder(3, "SINATRA")
        self.assertEqual(st.files, before)
        self.assertEqual(len(s.pending), 3)
        s.save()
        self.assertFalse(st.exists(layout.folder_dir(0) + "/01001KN7.SQT"))
        self.assertTrue(st.exists(layout.folder_dir(2) + "/01003KN7.SQT"))
        self.assertEqual(CardSession.open(st).validate(), [])

    def test_copy_of_a_song_moved_in_the_same_draft(self):
        """Move a song, then copy it (before saving): the space check and the save follow the plan
        (this crashed: the size was read from where the song is no longer going to be)."""
        st, s = card_with_songs({1: ["MY WAY", "VOLARE"]})
        s.move_song(1, 1, 2)
        s.move_song(2, 1, 3, None, True)                       # copy the song that is not in folder 2 yet
        self.assertEqual(s.bytes_needed(), 9)                  # the copy: sqt + pmt + lsw
        s.save()
        c = CardSession.open(st)
        self.assertEqual([[x.name for x in f.songs] for f in c.folders()], [["VOLARE"], ["MY WAY"], ["MY WAY"]])
        self.assertEqual(c.validate(), [])

    def test_undo(self):
        st, s = card_with_songs({1: ["MY WAY"]})
        s.rename_song(1, 1, "X")
        s.delete_song(1, 1)
        self.assertEqual(s.undo(), "delete 1/1")
        self.assertEqual(s.song(1, 1).name, "X")
        self.assertEqual(s.pending, [])
        s.undo()
        self.assertEqual(s.song(1, 1).name, "MY WAY")
        self.assertFalse(s.dirty)

    def test_favorites_follow_move_and_delete(self):
        st, s = card_with_songs({1: ["A", "B"]})
        s.db.favorites[0].items[0] = (1 << 8) | 2
        s.db.set_playlist(0, [(0, 1)])
        s.move_song(1, 2, 7)
        self.assertEqual(s.db.favorites[0].items[0], (7 << 8) | 1)
        self.assertEqual(s.db.playlist(0), [(6, 0)])
        s.delete_song(7, 1)
        self.assertEqual(s.db.favorites[0].items[0], 0)
        self.assertEqual(s.db.playlist(0), [])

    def test_swap(self):
        st, s = card_with_songs({2: ["A", "B"]})
        st.write(layout.folder_dir(1) + "/01002KN7.SQT", b"song A")
        s.swap_songs(2, 1, 2)
        s.save()
        s2 = CardSession.open(st)
        self.assertEqual([x.name for x in s2.folders()[0].songs], ["B", "A"])
        self.assertEqual(st.read(layout.folder_dir(1) + "/02002KN7.SQT"), b"song A")
        self.assertEqual(s2.validate(), [])

    def test_merge(self):
        _, a = card_with_songs({1: ["A"]})
        _, b = card_with_songs({1: ["B", "C"], 2: ["D"]})
        done = a.merge_from(b)
        self.assertEqual(done, [(1, 1, 1, 2), (1, 2, 1, 3), (2, 1, 2, 1)])
        a.save()
        self.assertEqual(a.validate(), [])

    def test_errors(self):
        st, s = card_with_songs({1: ["A"]})
        with self.assertRaises(SlotError):
            s.rename_song(1, 2, "x")
        with self.assertRaises(SlotError):
            s.move_song(1, 1, 100)
        with self.assertRaises(NoDatabase):
            CardSession.open(MemoryStorage())

    def test_bak_fallback(self):
        st, s = card_with_songs({1: ["A"]})
        s.rename_song(1, 1, "B")
        s.save()
        self.assertEqual(st.read(layout.BAK_PATH), st.read(layout.INF_PATH))
        st.write(layout.INF_PATH, b"broken")
        s2 = CardSession.open(st)
        self.assertEqual(s2.loaded_from, layout.BAK_PATH)
        self.assertEqual(s2.song(1, 1).name, "B")

    def test_validate_reports_missing_and_stray(self):
        st, s = card_with_songs({1: ["A"]})
        st.remove(layout.folder_dir(0) + "/01001KN7.PMT")
        st.write(layout.folder_dir(0) + "/JUNK.BIN", b"")
        msgs = [str(i) for i in s.validate()]
        self.assertTrue(any("missing file 01001KN7.PMT" in m for m in msgs))
        self.assertTrue(any("JUNK.BIN" in m for m in msgs))


class FavoritesAndListsTests(unittest.TestCase):
    def test_favorites_follow_moves_and_undo(self):
        st, s = card_with_songs({1: ["A", "B"]})
        s.rename_favorite_bank(1, "Avond")
        s.set_favorite(1, 3, (1, 2))
        self.assertEqual(s.favorites()[0], ("Avond", [None, None, ("song", 0, 1)] + [None] * 6))
        s.move_song(1, 2, 4)
        self.assertEqual(s.favorites()[0][1][2], ("song", 3, 0))
        s.undo()
        s.undo()
        self.assertEqual(s.favorites()[0][1][2], None)
        with self.assertRaises(SlotError):
            s.set_favorite(1, 1, (5, 5))
        with self.assertRaises(SlotError):
            s.set_favorite(41, 1, None)

    def test_song_lists(self):
        st, s = card_with_songs({1: ["A", "B"], 2: ["C"]})
        s.set_song_list(2, [(2, 1), (1, 1)])
        s.save()
        s2 = CardSession.open(st)
        self.assertEqual(s2.playlists()[1], [(2, 1), (1, 1)])
        s2.delete_song(1, 1)
        self.assertEqual(s2.playlists()[1], [(2, 1)])
        with self.assertRaises(SlotError):
            s2.set_song_list(1, [(1, 1)] * 21)

    def test_import_from_other_card(self):
        _, other = card_with_songs({5: ["X"]})
        st, s = card_with_songs({1: ["A"]})
        n = s.import_from(other, 5, 1, 1)
        self.assertEqual(n, 2)
        s.save()
        self.assertEqual(st.read(layout.folder_dir(0) + "/02001KN7.SQT"), b"sqt")


class ReorderTests(unittest.TestCase):
    def test_several_songs_move_as_a_block_and_the_rest_shifts(self):
        from kn_songboek.storage.memory import MemoryStorage
        st = MemoryStorage()
        s = CardSession.create(st)
        names = ["A", "B", "C", "D", "E", "F"]
        for n in names:
            s.import_song(MemoryStorage({"x.SQT": n.encode()}), {"SQT": "x.SQT"}, n, 1)
        s.save(backup=False)
        s.set_song_list(1, [(1, 4), (1, 1)])                 # D, A
        self.assertEqual(s.reorder_songs(1, [3, 4, 5], 1), [1, 2, 3])          # C D E to the top
        self.assertEqual([x.name for x in s.db.folders[0].songs[:6]], ["C", "D", "E", "A", "B", "F"])
        self.assertEqual(s.playlists()[0], [(1, 2), (1, 4)])                    # the list still says D, A
        s.save(backup=False)
        s = CardSession.open(st)
        self.assertEqual(s.validate(), [])
        from kn_songboek.formats import layout
        for si in range(6):
            song = s.db.song(0, si)
            self.assertEqual(st.read(layout.song_paths(0, si, song)["SQT"]), song.name.encode())
        self.assertEqual(s.reorder_songs(1, [1, 2], 5), [4, 5])                  # moving down: the block ends there
        self.assertEqual([x.name for x in s.db.folders[0].songs[:6]], ["E", "A", "B", "C", "D", "F"])
        s.undo()
        self.assertEqual([x.name for x in s.db.folders[0].songs[:6]], ["C", "D", "E", "A", "B", "F"])
        self.assertEqual(s.reorder_songs(1, [2, 3], 2), [2, 3])                  # already there: nothing
        with self.assertRaises(SlotError):
            s.reorder_songs(1, [1, 9], 3)                                         # 9 is empty
