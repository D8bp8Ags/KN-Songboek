import collections
import os
import struct
import unittest

from kn_songboek.core import CardSession
from kn_songboek.formats import container, rhythm, sqt
from kn_songboek.formats.rhythm_table import INDEX, STYLES
from kn_songboek.storage.memory import MemoryStorage


def panel(rhythm_id, tempo=120):
    payload = struct.pack("<HB", rhythm_id & 0xFFFF, rhythm_id >> 16) + bytes(5) + bytes([tempo]) + bytes(5)
    return bytes([0x40, 2, 0, 0, 0x42, len(payload)]) + payload + b"\xff\xff"


def song_record(rhythm_id):
    r = bytearray(0x8E0)
    r[0:7] = b"ZZZZ\x01\x01\x0d"
    for t in range(16):
        struct.pack_into("<BH", r, 0xD0 + 3 * t, 0, 0xFFFF)
    r[0x100:0x110] = b"MY SONG".ljust(16)
    pm = panel(rhythm_id)
    r[0x140:0x140 + len(pm)] = pm
    return bytes(r)


def tcmp(beats_by_style):
    """A TCMP container whose style s plays VARIATION 1 = variation record 20*s with the given beats."""
    c = bytearray(0x3670)
    c[0:4] = b"TCMP"
    for s, beats in enumerate(beats_by_style):
        rec = 0x70 + s * 0x80
        c[rec:rec + 13] = (b"MEMSTYLE %d" % (s + 1)).ljust(13)
        c[rec + 0x50:rec + 0x64] = bytes(range(20 * s, 20 * s + 20))
        var = 0x1F0 + 20 * s * 0xE0
        c[var + 0x10], c[var + 0x11] = 3, beats - 1
    return bytes(c)


class BuiltinTests(unittest.TestCase):
    def test_table_shape(self):
        self.assertEqual(len(INDEX), 2048)
        self.assertTrue(all(i < len(STYLES) for i in INDEX))
        self.assertEqual({b for _, b in STYLES}, {3, 4})
        self.assertEqual(sum(1 for _, b in STYLES if b == 3), 15)

    def test_known_ids(self):
        self.assertEqual(rhythm.builtin(0x20D), ("Waltz", 3))
        self.assertEqual(rhythm.builtin(0x556), ("60s Pop Idol", 4))
        self.assertEqual(rhythm.builtin(0x10D), ("Waltz", 3))       # an alias of 0x20D
        self.assertIsNone(rhythm.builtin(0x1000))

    def test_decode_builtin(self):
        r = rhythm.decode(0x00020D)
        self.assertEqual((r.source, r.label, r.beats, r.meter), (rhythm.SOURCE_BUILTIN, "Waltz", 3, "3/4"))
        self.assertEqual(rhythm.decode(0x05A).meter, "4/4")

    def test_meter_in_name_wins(self):
        self.assertEqual(rhythm.decode(0x004).label, "Polka 2/4")
        self.assertEqual(rhythm.decode(0x004).meter, "2/4")
        self.assertEqual(rhythm.decode(0x402).meter, "6/8")      # USA March 6/8, a 4-beat pattern


class MemoryAndCustomTests(unittest.TestCase):
    def test_memory_style_reads_the_cmp(self):
        cmp = tcmp([4, 3, 4])
        r = rhythm.decode(0x100001, cmp)
        self.assertEqual((r.source, r.number, r.label, r.meter), (rhythm.SOURCE_MEMORY, 1, "MEMSTYLE 2", "3/4"))
        self.assertEqual(rhythm.decode(0x100002, cmp).meter, "4/4")

    def test_memory_without_cmp_is_unknown(self):
        r = rhythm.decode(0x100000)
        self.assertEqual((r.label, r.meter), ("Composer memory 1", None))

    def test_custom_is_not_on_the_card(self):
        r = rhythm.decode(0x200004)
        self.assertEqual((r.source, r.label, r.meter), (rhythm.SOURCE_CUSTOM, "Custom 5", None))


class SongTests(unittest.TestCase):
    def test_panel_rhythm_id(self):
        s = sqt.read_songs(song_record(0x10020D & 0x0FFFFF))[0]
        self.assertEqual(s.rhythm_id, 0x20D)
        self.assertIsNone(rhythm.panel_rhythm_id(bytes(0x8E0)))

    def test_song_details_show_meter_from_cmp(self):
        sqt_file = container.build_kd2(song_record(0x100001), b"")
        cmp_file = container.build_kd(tcmp([4, 3, 4]))
        src = MemoryStorage({"x.SQT": sqt_file, "x.CMP": cmp_file, "x.PMT": b"pmt"})
        st = MemoryStorage()
        s = CardSession.create(st)
        s.import_song(src, {"SQT": "x.SQT", "CMP": "x.CMP", "PMT": "x.PMT"}, "WALS", 1)
        s.save()
        d = CardSession.open(st).song_details(1, 1)
        q = d["sequencer"][0]
        self.assertEqual((q["rhythm"], q["meter"]), ("MEMSTYLE 2", "3/4"))


@unittest.skipUnless(os.environ.get("KN_SONGBOEK_REAL_CARD"), "set KN_SONGBOEK_REAL_CARD to a copy of a real card")
class RealCardMeterTests(unittest.TestCase):
    def test_every_song_has_a_rhythm_and_known_meters_are_sane(self):
        from kn_songboek.storage import DirectoryStorage
        s = CardSession.open(DirectoryStorage(os.environ["KN_SONGBOEK_REAL_CARD"]))
        seen = collections.Counter()
        for fi, si, _ in s.db.iter_songs():
            d = s.song_details(fi + 1, si + 1)
            for q in d["sequencer"]:
                if q["model"] != "KN7000":
                    continue
                self.assertIsNotNone(q["rhythm"], (fi + 1, si + 1))
                seen[q["meter"]] += 1
                self.assertIn(q["meter"], (None, "2/2", "2/4", "3/4", "4/4", "6/8"), (fi + 1, si + 1))
        self.assertGreater(seen["4/4"], 0, seen)


if __name__ == "__main__":
    unittest.main()
