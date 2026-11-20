"""Favourite buttons come along when whole folders are copied onto a card, without overwriting any."""
import os
import tempfile
import unittest

from helpers import card_with_songs
from kn_songboek.core import CardSession, cards


def fav(s, bank):
    return s.favorites()[bank - 1]


class CarryFavoritesTests(unittest.TestCase):
    def setUp(self):
        _, self.src = card_with_songs({2: ["A", "B"], 5: ["C"], 7: ["D"]})
        self.src.rename_favorite_bank(3, "BALLADS")
        self.src.set_favorite(3, 1, (2, 2))         # B on bank 3 button 1
        self.src.set_favorite(3, 4, (5, 1))         # C on bank 3 button 4
        self.src.set_favorite(3, 9, (7, 1))         # D: its folder is not copied
        self.src.set_favorite(1, 2, (2, 1))         # A on bank 1 button 2 (bank without a name)

    def test_same_bank_and_button_on_an_empty_card(self):
        _, dst = card_with_songs({1: ["X"]})
        r = dst.import_folder(self.src, 2)
        self.assertEqual(r["folder"], 2)
        self.assertEqual(r["favorites"], {"carried": 2, "banks": [1, 3], "left": 0})
        self.assertEqual(fav(dst, 3)[0], "BALLADS")
        self.assertEqual(fav(dst, 3)[1][0], ("song", 1, 1))
        self.assertEqual(fav(dst, 3)[1][3], None)   # C was not copied
        self.assertEqual(fav(dst, 1)[1][1], ("song", 1, 0))
        self.assertEqual(len(dst.history()), 1)     # one undo step, favourites included
        dst.undo()
        self.assertEqual(fav(dst, 3), ("", [None] * 9))

    def test_points_at_the_new_folder(self):
        _, dst = card_with_songs({1: ["X"], 2: ["Y"]})
        r = dst.import_folders(self.src, [5, 2])
        self.assertEqual([x["folder"] for x in r], [3, 4])
        self.assertEqual(r[0]["favorites"]["carried"], 3)
        b = fav(dst, 3)[1]
        self.assertEqual((b[0], b[3]), (("song", 3, 1), ("song", 2, 0)))   # B in folder 4, C in folder 3
        dst.save()
        again = CardSession.open(dst.storage)
        self.assertEqual(fav(again, 3)[1][0], ("song", 3, 1))
        self.assertEqual(again.validate(), [])

    def test_never_overwrites_and_moves_to_a_free_bank(self):
        _, dst = card_with_songs({1: ["X", "Y"]})
        dst.rename_favorite_bank(3, "ROCK")          # bank 3 is the player's own: other name
        dst.set_favorite(1, 2, (1, 1))               # bank 1 button 2 is taken
        r = dst.import_folder(self.src, 2)
        self.assertEqual(fav(dst, 3)[0], "ROCK")
        self.assertEqual(fav(dst, 3)[1], [None] * 9)
        self.assertEqual(fav(dst, 1)[1][1], ("song", 0, 0))                # X stays on bank 1 button 2
        # bank 1's A and bank 3's B each go to the first unused bank, on the same button
        self.assertEqual(r["favorites"], {"carried": 2, "banks": [2, 4], "left": 0})
        self.assertEqual(fav(dst, 2)[1][1], ("song", 1, 0))
        self.assertEqual(fav(dst, 4), ("BALLADS", [("song", 1, 1)] + [None] * 8))

    def test_bank_with_the_same_name_elsewhere(self):
        _, dst = card_with_songs({1: ["X"]})
        dst.rename_favorite_bank(3, "ROCK")
        dst.rename_favorite_bank(10, "BALLADS")
        dst.set_favorite(10, 5, (1, 1))
        dst.import_folder(self.src, 2)
        self.assertEqual(fav(dst, 10)[1][0], ("song", 1, 1))
        self.assertEqual(fav(dst, 10)[1][4], ("song", 0, 0))

    def test_all_banks_full_leaves_them_behind(self):
        _, dst = card_with_songs({1: ["X"]})
        for b in range(1, 41):
            dst.rename_favorite_bank(b, "BANK %d" % b)
        before = dst.favorites()
        r = dst.import_folder(self.src, 2)
        self.assertEqual(r["favorites"], {"carried": 0, "banks": [], "left": 2})
        self.assertEqual(dst.favorites(), before)
        self.assertTrue(dst.db.folders[1].songs[0].used)                   # the songs did come

    def test_without_favorites(self):
        _, dst = card_with_songs({1: ["X"]})
        r = dst.import_folder(self.src, 2, favorites=False)
        self.assertEqual(r["favorites"]["carried"], 0)
        self.assertEqual(fav(dst, 3), ("", [None] * 9))

    def test_copy_of_a_whole_card_keeps_every_bank_as_it_is(self):
        s = cards.new_card_from(self.src)
        self.assertEqual(s.favorites(), self.src.favorites())


class PresenterTexts(unittest.TestCase):
    def test_toast_and_window_say_what_happened(self):
        from test_presenter import FakeView
        from kn_songboek.gui.presenter import MainPresenter
        from kn_songboek.storage import DirectoryStorage
        from test_library import add
        with tempfile.TemporaryDirectory() as tmp:
            root = os.path.join(tmp, "lib")
            a = CardSession.create(DirectoryStorage(os.path.join(root, "Kaart Bruiloft")))
            add(a, 3, "ONE", 100)
            add(a, 3, "TWO", 110)
            a.set_favorite(2, 1, (3, 1))
            a.set_favorite(2, 2, (3, 2))
            a.save()
            view = FakeView()
            asked = []
            view.ask = lambda text, buttons: asked.append(text) or 0
            p = MainPresenter(view, backup_dir=os.path.join(tmp, "bk"))
            p.open_library(root)
            self.assertTrue(p.new_card(os.path.join(tmp, "new")))
            self.assertTrue(p.copy_library_part("Kaart Bruiloft", ("folder", 3)))
            self.assertIn("Ook 2 favorieten gingen mee (favorietenbank 2)", view.notes[-1])
            self.assertEqual(asked, [])
            for b in range(1, 41):
                p.session.rename_favorite_bank(b, "VOL")
            self.assertTrue(p.copy_library_folders("Kaart Bruiloft", [3]))
            self.assertNotIn("favoriet", view.notes[-1])
            self.assertIn("2 favorieten konden niet mee", asked[0])
            self.assertIn("niets van je eigen favorieten overschreven", asked[0])
            p.library.close()


if __name__ == "__main__":
    unittest.main()
