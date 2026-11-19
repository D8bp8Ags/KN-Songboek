"""Checks against a copy of a real card. Skipped unless KN_SONGBOEK_REAL_CARD points at one.

The card itself is private and is never committed: point the variable at a local copy, e.g.
    KN_SONGBOEK_REAL_CARD=/pad/naar/kaartkopie python -m pytest
"""
import os
import unittest

from kn_songboek.formats import layout
from kn_songboek.formats.inf import MusicDatabase

CARD = os.environ.get("KN_SONGBOEK_REAL_CARD")


@unittest.skipUnless(CARD, "set KN_SONGBOEK_REAL_CARD to a copy of a real card")
class RealCardTests(unittest.TestCase):
    def _db(self, name):
        with open(os.path.join(CARD, layout.KN7_DIR, name), "rb") as fh:
            return fh.read()

    def test_roundtrip_and_alpha_index(self):
        for name in ("KN7000MN.INF", "KN7000MN.BAK"):
            raw = self._db(name)
            db = MusicDatabase.from_bytes(raw)
            self.assertEqual(db.to_bytes(), raw, name)
            db.rebuild_alpha_index()
            self.assertEqual(db.to_bytes(), raw, name + ": rebuilt alphabetical index differs")

    def test_every_listed_file_exists_and_nothing_else(self):
        db = MusicDatabase.from_bytes(self._db("KN7000MN.INF"))
        root = os.path.join(CARD, layout.KN7_DIR)
        actual = {(d, f.upper()) for d in os.listdir(root) if d.startswith("TFLD")
                  for f in os.listdir(os.path.join(root, d))}
        expected = {tuple(p.upper().split("/")[-2:]) for fi, si, s in db.iter_songs()
                    for p in layout.song_paths(fi, si, s).values()}
        self.assertEqual(expected - actual, set())
        self.assertEqual(actual - expected, set())


@unittest.skipUnless(CARD, "set KN_SONGBOEK_REAL_CARD to a copy of a real card")
class RealCardContentsTests(unittest.TestCase):
    def test_every_song_contents_reads(self):
        from kn_songboek.core import CardSession
        from kn_songboek.storage import open_storage
        s = CardSession.open(open_storage(CARD, read_only=True))
        for fi, si, _ in s.db.iter_songs():
            d = s.song_details(fi + 1, si + 1)
            self.assertNotIn("errors", d, "%d/%d" % (fi + 1, si + 1))
            for key in ("panel_memories", "styles", "pads", "sounds"):
                self.assertIn(key, d, "%d/%d" % (fi + 1, si + 1))


@unittest.skipUnless(CARD, "set KN_SONGBOEK_REAL_CARD to a copy of a real card")
class RealCardEncoderTests(unittest.TestCase):
    def test_rebuilt_files_are_byte_identical(self):
        """Unpack and pack again: the same bytes as Technics wrote (every 4th song, to stay quick;
        KN_SONGBOEK_REAL_CARD_ALL=1 checks them all)."""
        import struct

        from kn_songboek.core import CardSession
        from kn_songboek.formats import container
        from kn_songboek.storage import open_storage
        st = open_storage(CARD, read_only=True)
        s = CardSession.open(st)
        songs = list(s.db.iter_songs())
        if not os.environ.get("KN_SONGBOEK_REAL_CARD_ALL"):
            songs = songs[::4]
        checked = 0
        for fi, si, song in songs:
            for ext, p in layout.song_paths(fi, si, song).items():
                raw = st.read(p)
                if raw[:4] not in (b"J KD", b"JK D"):
                    continue
                flags = struct.unpack_from(">H", raw, 6)[0]
                parts = container.parse(raw, ext).parts
                if ext in container.TWO_PART:
                    again = container.build_kd2(parts[0], parts[1], flags)
                else:
                    again = container.build_kd(parts[0], flags, raw[:4])
                self.assertEqual(again, raw, "%d/%d %s" % (fi + 1, si + 1, ext))
                checked += 1
        self.assertGreater(checked, 0)
