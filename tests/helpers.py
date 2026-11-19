import importlib.util
import os
import unittest

from kn_songboek.core import CardSession
from kn_songboek.storage.memory import MemoryStorage


def card_with_songs(names_by_folder):
    """{folder(1-based): [names]} -> (storage, session) with every song saved as SQT+PMT+LSW."""
    st = MemoryStorage()
    s = CardSession.create(st)
    src = MemoryStorage({"x.SQT": b"sqt", "x.PMT": b"pmt", "x.LSW": b"lsw"})
    for folder, names in names_by_folder.items():
        for n in names:
            s.import_song(src, {"SQT": "x.SQT", "PMT": "x.PMT", "LSW": "x.LSW"}, n, folder)
    s.save()
    return st, CardSession.open(st)


# GUI tests need PySide6; tools/check.py --fast (or a Python without PySide6) skips them.
gui_test = unittest.skipUnless(importlib.util.find_spec("PySide6") is not None
                               and not os.environ.get("KN_SONGBOEK_NO_GUI_TESTS"), "PySide6 not available")
