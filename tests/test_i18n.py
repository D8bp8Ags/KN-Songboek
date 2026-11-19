"""Every text has a Dutch and an English version, and both fill in the same values."""
import re
import unittest

from kn_songboek.gui.i18n import TEXTS


class TextTests(unittest.TestCase):
    def test_both_languages_with_the_same_fields(self):
        for key, (nl, en) in TEXTS.items():
            with self.subTest(key=key):
                self.assertTrue(nl and en, "empty text")
                self.assertEqual(set(re.findall(r"\{(\w+)", nl)), set(re.findall(r"\{(\w+)", en)))
