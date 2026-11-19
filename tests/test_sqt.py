import struct
import unittest

from kn_songboek.formats import sqt


def record(name=b"MY SONG", tracks=None):
    r = bytearray(0x8E0)
    r[0:7] = b"ZZZZ\x01\x01\x0d"
    for t in range(16):
        struct.pack_into("<BH", r, 0xD0 + 3 * t, 0, (tracks or {}).get(t, 0xFFFF))
    r[0x100:0x110] = name.ljust(16, b" ")
    return bytes(r)


def cell(prev, nxt, data):
    return bytes([0]) + struct.pack("<HH", prev, nxt) + data.ljust(251, b"\x81")[:251]


class SqtTests(unittest.TestCase):
    def test_track_over_two_cells(self):
        ev1 = b"\x00\x80\x78\x00" + b"\x00\x90\x3c\x64\x30\x00" + b"\x81" + b"\x10\x90\x3e\x64\x00\x01"
        ev1 = ev1 + b"\x81" * (251 - len(ev1))          # beats fill the first cell
        ev2 = b"\x05\x85" + b"\x00\xb0\x00\x07\x64" + b"\x82"
        part1 = record(tracks={0: 1}) + b"ZZZZ\x00" + bytes(0x8E0 - 5)
        part2 = cell(0, 2, ev1) + cell(1, 0xFFFF, ev2)
        songs = sqt.read_songs(part1, part2)
        self.assertEqual(len(songs), 1)
        s = songs[0]
        self.assertEqual((s.name, s.model, s.tempo, s.notes), ("MY SONG", "KN7000", 120, 2))
        t = s.tracks[0]
        self.assertEqual((t.number, t.cells, t.events, t.complete), (1, 2, 5, True))
        self.assertEqual(t.beats, 251 - 17 + 1)

    def test_settings_only_song_and_default_name(self):
        s = sqt.read_songs(record(name=b"_" * 16))[0]
        self.assertEqual((s.name, s.tracks, s.has_events), ("", [], False))

    def test_bad_pointer_is_reported(self):
        with self.assertRaises(sqt.SQTError):
            sqt.read_songs(record(tracks={0: 5}), cell(0, 0xFFFF, b"\x82"))


class TempoTests(unittest.TestCase):
    def test_event_tempo_uses_two_7bit_halves(self):
        part1 = record(tracks={0: 1})
        part2 = cell(0, 0xFFFF, b"\x00\x80\x3b\x01\x82")      # 59 + 128 = 187, as on a real card
        self.assertEqual(sqt.read_songs(part1, part2)[0].tempo, 187)

    def test_panel_tempo(self):
        r = bytearray(record())
        pm = bytes([0x40, 2, 0, 0, 0x42, 14]) + bytes([0x5A, 0, 0, 0x10, 0, 0, 0, 0, 96, 0, 0, 0, 0, 0]) + b"\xff\xff"
        r[0x140:0x140 + len(pm)] = pm
        s = sqt.read_songs(bytes(r))[0]
        self.assertEqual((s.panel_tempo, s.tempo, s.has_events), (96, 96, False))
        self.assertIsNone(sqt.panel_tempo(record()))
