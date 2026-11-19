import unittest

from kn_songboek.core import CardSession
from kn_songboek.core import repair
from kn_songboek.formats import layout
from kn_songboek.formats.inf import MusicDatabase

from helpers import card_with_songs


class RepairTests(unittest.TestCase):
    def test_clean_card_needs_nothing(self):
        st, _ = card_with_songs({1: ["A", "B"], 4: ["C"]})
        _, rep = repair.rebuild(st)
        self.assertTrue(rep.nothing_to_do, rep)

    def test_interrupted_move_is_repaired(self):
        st, s = card_with_songs({1: ["A", "B"]})
        st.write(layout.KN7_DIR + "/TFLD002/~SWAP01.SQT", b"junk")
        # files moved by hand to folder 3, database not updated
        for ext, p in layout.song_paths(0, 1, s.db.song(0, 1)).items():
            st.move(p, layout.KN7_DIR + "/TFLD003/01003KN7." + ext)
        db, rep = repair.rebuild(st)
        self.assertEqual(rep.removed, [(1, 2, "B")])
        self.assertEqual(rep.added, [(3, 1, "SONG 003-01")])
        self.assertTrue(any("~SWAP01" in p for p in rep.unknown_files))
        s2 = CardSession(st, db, "repair")
        s2.save()
        self.assertEqual([i for i in CardSession.open(st).validate() if i.severity == "error"], [])

    def test_lost_database_rebuilt_with_placeholder_names(self):
        st, s = card_with_songs({2: ["A"]})
        st.remove(layout.INF_PATH)
        st.remove(layout.BAK_PATH)
        db, rep = repair.rebuild(st)
        self.assertEqual(rep.added, [(2, 1, "SONG 002-01")])
        self.assertTrue(db.song(1, 0).used)
        self.assertIsInstance(db, MusicDatabase)
