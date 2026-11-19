"""What differs on Windows, tested here by pretending (the real calls only run on Windows itself)."""
import os
import unittest
from unittest import mock

from kn_songboek.core import backup, cards
from kn_songboek.storage import windows
from kn_songboek.storage.memory import MemoryStorage


class WindowsTests(unittest.TestCase):
    def test_drive_roots(self):
        for p in ("E:\\", "E:", "e:/"):
            self.assertTrue(windows.is_drive_root(p))
        for p in ("E:\\KN7000", "/Volumes/KN7000", "C:\\Users\\a", ""):
            self.assertFalse(windows.is_drive_root(p))

    def test_a_drive_is_called_by_its_label(self):
        with mock.patch.object(windows, "drive_label", return_value="KN7000"):
            self.assertEqual(windows.display_name("E:\\"), "KN7000 (E:)")
        with mock.patch.object(windows, "drive_label", return_value=""):
            self.assertEqual(windows.display_name("E:\\"), "E:")
        self.assertEqual(windows.display_name("/Volumes/KN7000"), "KN7000")

    def test_backup_folder_uses_the_label_not_the_letter(self):
        st = MemoryStorage()
        st.describe = lambda: "E:\\"
        with mock.patch.object(windows, "drive_label", return_value="BRUILOFT"):
            self.assertEqual(backup.card_label(st), "BRUILOFT")

    def test_names_windows_keeps_for_itself(self):
        self.assertEqual(cards.safe_name("CON"), "CON_")
        self.assertEqual(cards.safe_name("aux.2"), "aux.2_")
        self.assertEqual(cards.safe_name("Kaart: 1?"), "Kaart_ 1_")
        self.assertEqual(cards.safe_name("CONCERT"), "CONCERT")

    def test_drive_letters_with_the_floppy_and_without_windows_itself(self):
        seen = []
        with mock.patch.object(cards.sys, "platform", "win32"), \
                mock.patch.dict(os.environ, {}, clear=False), \
                mock.patch.object(cards.os.path, "isdir", side_effect=lambda p: seen.append(p) or p in ("A:\\", "C:\\", "E:\\")), \
                mock.patch.object(windows, "no_error_dialogs") as quiet:
            os.environ.pop("KN_SONGBOEK_VOLUMES", None)
            self.assertEqual(cards._mounted(), ["A:\\", "E:\\"])
            quiet.assert_called_once()
        self.assertNotIn("C:\\", seen)

    def test_nothing_happens_elsewhere(self):
        if windows.WINDOWS:
            self.skipTest("on Windows itself")
        self.assertEqual(windows.drive_label("E:\\"), "")
        self.assertFalse(windows.set_drive_label("E:\\", "X"))
        self.assertFalse(windows.eject_drive("E:\\"))
        self.assertFalse(windows.show_in_explorer("/tmp"))
        windows.no_error_dialogs()


if __name__ == "__main__":
    unittest.main()


class TrashTests(unittest.TestCase):
    def test_never_deletes_when_the_bin_says_no(self):
        import tempfile
        from unittest import mock
        from kn_songboek.storage import trash
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "Kaart")
            os.mkdir(d)
            with mock.patch.object(trash, "_run", return_value=False), \
                 mock.patch.object(trash, "_mac", return_value=False):
                self.assertFalse(trash.move_to_trash(d))
            self.assertTrue(os.path.isdir(d))
            self.assertFalse(trash.move_to_trash(os.path.join(tmp, "nope")))
