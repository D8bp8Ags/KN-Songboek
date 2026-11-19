import random
import struct
import unittest

from kn_songboek.formats import container, layout
from kn_songboek.formats.inf import FILE_SIZE, OFF_FAV, SIGNATURE, MusicDatabase, Song


class InfTests(unittest.TestCase):
    def test_layout_constants(self):
        self.assertEqual(FILE_SIZE, 0xD620)
        self.assertEqual(OFF_FAV, 0xC058)

    def test_roundtrip_new(self):
        b = MusicDatabase.new().to_bytes()
        self.assertEqual((len(b), b[:16]), (FILE_SIZE, SIGNATURE))
        self.assertEqual(MusicDatabase.from_bytes(b).to_bytes(), b)

    def test_roundtrip_preserves_raw_bytes(self):
        b = bytearray(MusicDatabase.new().to_bytes())
        o = 0x10 + 16
        b[o:o + 16] = b"MY SONG\0garbage!"
        b[o + 16:o + 22] = b"001KN7"
        struct.pack_into("<H", b, o + 22, 0b101)
        db = MusicDatabase.from_bytes(bytes(b))
        s = db.song(0, 0)
        self.assertEqual((s.name, s.base, s.extensions), ("MY SONG", "001KN7", ["LSW", "SQT"]))
        self.assertEqual(db.to_bytes()[:0xBFE0], bytes(b[:0xBFE0]))

    def test_alpha_index(self):
        db = MusicDatabase.new()
        db.song(0, 0).name, db.song(0, 0).types = "ZEBRA", 4
        db.song(1, 3).name, db.song(1, 3).types = "  APPLE", 4
        db.rebuild_alpha_index()
        used = [p for p in db.alpha_list if p != (0xFF, 0xFF)]
        self.assertEqual(used, [(1, 3), (0, 0)])
        # unused slots sort first, so the used songs fill the tail of the list
        self.assertEqual(db.alpha_list[-2:], [(1, 3), (0, 0)])
        self.assertEqual(db.alpha_first[ord("A")], len(db.alpha_list) - 2)
        self.assertEqual(db.alpha_list[db.alpha_first[ord("A")]], (1, 3))

    def test_playlists(self):
        db = MusicDatabase.new()
        self.assertEqual(db.playlist(0), [])
        db.set_playlist(1, [(0, 0), (4, 2)])
        db2 = MusicDatabase.from_bytes(db.to_bytes())
        self.assertEqual(db2.playlist(1), [(0, 0), (4, 2)])
        db2.purge_slot(0, 0)
        self.assertEqual(db2.playlist(1), [(4, 2)])


class LayoutTests(unittest.TestCase):
    def test_paths(self):
        self.assertEqual(layout.song_path(0, 1, Song("X", "", 4), "SQT"),
                         "PRIVATE/TECHNICS/KN7000/TFLD001/02001KN7.SQT")
        self.assertEqual(layout.song_path(98, 19, Song("X", "ABCDEF", 4), "SQT"),
                         "PRIVATE/TECHNICS/KN7000/TFLD099/20ABCDEF.SQT")


class LzssTests(unittest.TestCase):
    def check(self, data):
        self.assertEqual(container.lzss_decode(container.lzss_encode(data), len(data)), data)

    def test_patterns(self):
        rnd = random.Random(1)
        for d in (b"", b"A" * 5000, bytes(rnd.randrange(256) for _ in range(3000)),
                  (b"TCMP style data " * 900) + bytes(range(256)) * 40):
            self.check(d)

    def test_kd_container(self):
        p = b"ZZZZ" + bytes(range(200)) * 30
        self.assertEqual(container.parse(container.build_kd(p), "PMT").parts, [p])
        self.assertEqual(container.parse(container.build_kd2(p, p[::-1]), "SQT").parts, [p, p[::-1]])
