"""Song contents (PMT, CMP, MSP, TM, HMP) and the SD_SOUND files, on made-up files with the layout
seen on a real card."""
import io
import struct
import unittest

from helpers import gui_test
from contextlib import redirect_stdout

from kn_songboek.cli.main import _runs, main
from kn_songboek.core import CardSession
from kn_songboek.formats import container, sdsound, songdata
from kn_songboek.storage.memory import MemoryStorage


def name16(s):
    return s.encode("latin-1").ljust(16, b" ")


def make_pmt(kn6000=False, tempo=120, songs=(), chord=2):
    """3 banks as for one SD song; with songs a diskette's full set: 3 general banks, then per bank
    2 songs of 4 memories ("Annie`s Song 1".."4")."""
    mem = 0x700 if kn6000 else 0x750
    label = "General %s%s" if songs else "Memory %d%d"            # a set's general banks: no numbered names
    names = [[label % ("ABC"[b] if songs else b + 1, "ABCDEFGH"[m] if songs else m + 1) for m in range(8)]
             for b in range(3)]
    for i in range(0, len(songs), 2):
        pair = list(songs[i:i + 2]) * 2
        names.append(["%s %d" % (pair[m // 4], m % 4 + 1) for m in range(8)])
    d = bytearray(0x10 + len(names) * (0x10 + 8 * mem))
    d[0:4] = b"IK \0" if kn6000 else b"JK \0"
    d[0x0C:0x10] = b"P\x07\x18\x00"
    for b in range(len(names)):
        base = 0x10 + b * (0x10 + 8 * mem)
        d[base:base + 16] = name16("Bank %d" % (b + 1))
        for m in range(8):
            o = base + 0x10 + m * mem
            blk = bytes([0x40, 18]) + name16(names[b][m]) + b"\0\0"
            blk += bytes([0x10, 72]) + bytes([73, 20, 32, 100]) + bytes(68)          # R1: Flute, volume 100
            blk += bytes([0x12, 72]) + bytes([4, 0, 16, 0xE0]) + bytes(68)          # L: a bank we cannot name
            blk += bytes([0x42, 14, 0x14, 4, 0, 0x10 | chord, 0, 0, 0, 0]) + struct.pack("<H", tempo + m) + bytes(4)
            blk += b"\xff\xff"
            d[o:o + len(blk)] = blk
    return bytes(d)


def make_cmp():
    d = bytearray(0x70 + 3 * 0x80 + 60 * 0xE0)
    d[0:4] = b"TCMP"
    d[0x30:0x70] = b" " * 0x40
    for k, (name, vs) in enumerate([("MY WALTZ", ["Waltz 1", "Waltz 2", "", ""]),
                                    ("Easy 16 Beat", ["", "", "", ""]), ("", ["", "", "", ""])]):
        o = 0x70 + k * 0x80
        d[o:o + 16] = name.encode().ljust(13, b" ") + b"\0\0\0"
        for j, v in enumerate(vs):
            d[o + 16 * (j + 1):o + 16 * (j + 2)] = v.encode().ljust(13, b" ") + b"\0\0\0"
        d[o + 0x50:o + 0x64] = bytes(range(k * 20, k * 20 + 20))
    return bytes(d)


def make_msp():
    d = bytearray(0x160 + 18 * 0x60 + 0x100)
    d[0:4] = b"TPAD"
    d[0x30:0x70] = b" " * 0x40
    banks = [(" Compile Bank 1 ", [(0x71, 2, 0)] * 5 + [(0, 1, 0x10)])] + \
            [("  User Bank %d   " % u, [(u - 1, p, 0x10) for p in range(6)]) for u in (1, 2, 3)] + \
            [(" Compile Bank 2 ", [(5, 1, 0)] * 6)]
    for b, (name, pads) in enumerate(banks):
        o = 0x70 + b * 0x30
        d[o:o + 16] = name16(name)
        for p, e in enumerate(pads):
            d[o + 16 + 3 * p:o + 19 + 3 * p] = bytes(e)
    for k in range(18):
        o = 0x160 + k * 0x60
        d[o:o + 16] = name16("Pad %d" % (k + 1))
    return bytes(d)


def make_tm(model=b"KN7000"):
    d = bytearray(47098)
    d[0:16] = model + b" SOUND RAM"
    for k in range(40):
        o = 0x10 + k * 0x2C8
        d[o:o + 16] = name16("Sound %d" % (k + 1))
    o = 0x10 + 40 * 0x2C8
    d[o:o + 16] = name16("User Kit")
    return bytes(d)


def make_bmp(w=160, h=100):
    row = (w * 3 + 3) & ~3
    pixels = bytes(row * h)
    return (b"BM" + struct.pack("<IHHI", 54 + len(pixels), 0, 0, 54)
            + struct.pack("<IiiHHIIiiII", 40, w, h, 1, 24, 0, len(pixels), 2835, 2835, 0, 0) + pixels)


def make_hmp():
    return b"JK \0" + bytes(12) + bytes(0x18C) + make_bmp()


class SongDataTests(unittest.TestCase):
    def test_pmt_kn7000_and_kn6000(self):
        for kn6000 in (False, True):
            banks = songdata.read_pmt(make_pmt(kn6000))
            self.assertEqual([b.name for b in banks], ["Bank 1", "Bank 2", "Bank 3"])
            self.assertEqual(len(banks[2].memories), 8)
            self.assertEqual(banks[1].memories[3].name, "Memory 24")
            self.assertEqual(banks[1].memories[3].tempo, 123)

    def test_full_set_from_a_diskette(self):
        for kn6000 in (True, False):
            p = make_pmt(kn6000, songs=["Annie`s Song", "Cocktail Bar", "Penny Arcade  "])
            banks = songdata.read_pmt(p)
            self.assertEqual(len(banks), 5)
            self.assertEqual(banks[3].memories[0].name, "Annie`s Song 1")
            self.assertEqual([b.label for b in banks], ["A", "B", "C", "1", "2"])
            self.assertEqual(songdata.set_titles(banks), ["Annie's Song", "Cocktail Bar", "Penny Arcade"])
            self.assertEqual(songdata.pmt_set_titles(container.build_kd(p)),
                             ["Annie's Song", "Cocktail Bar", "Penny Arcade"])
        self.assertEqual(songdata.set_titles(songdata.read_pmt(make_pmt())), [])      # one SD song: its own banks
        self.assertEqual(songdata.pmt_set_titles(container.build_kd(make_pmt())), [])

    def test_part_sounds(self):
        m = songdata.read_pmt(make_pmt())[0].memories[0]
        self.assertEqual(m.sounds, [songdata.PartSound("R1", 73, 20, 32, 100), songdata.PartSound("L", 4, 0, 16, 0x60)])
        self.assertEqual(songdata.sound_kind(m.sounds[0]), "Flute")
        self.assertEqual(songdata.sound_kind(m.sounds[1]), "")
        from kn_songboek.gui.presenter import MainPresenter
        p = MainPresenter.__new__(MainPresenter)
        p.lang = "nl"
        self.assertEqual(p._sounds_text(m.sounds), "  ·  R1 Flute, L klank bank 16/0 nr 5")

    def test_chord_mode(self):
        self.assertEqual(songdata.chord_mode(songdata.read_pmt(make_pmt())), 2)              # fingered
        self.assertEqual(songdata.chord_mode(songdata.read_pmt(make_pmt(True, chord=1))), 1)  # one finger
        self.assertIsNone(songdata.chord_mode(songdata.read_pmt(make_pmt(chord=0))))
        banks = songdata.read_pmt(make_pmt())
        banks[0].memories[0].chord = 1                                  # one button one finger, the rest fingered
        self.assertEqual(songdata.chord_counts(banks), {1: 1, 2: 23})
        from kn_songboek.gui.presenter import MainPresenter
        p = MainPresenter.__new__(MainPresenter)
        p.lang = "nl"
        self.assertEqual(p._chord_text(banks),
                         "gemengd: 1 knop één vinger (one finger), 23 knoppen zelf spelen (fingered)")
        self.assertEqual(p._chord_text(songdata.read_pmt(make_pmt())), "zelf spelen (fingered)")

    def test_pmt_rejects_other_sizes(self):
        with self.assertRaises(songdata.FormatError):
            songdata.read_pmt(make_pmt()[:-16])

    def test_pmt_through_the_container(self):
        payload = container.parse(container.build_kd(make_pmt()), "PMT").parts[0]
        self.assertEqual(songdata.read_pmt(payload)[0].memories[0].name, "Memory 11")

    def test_cmp(self):
        styles = songdata.read_cmp(make_cmp())
        self.assertEqual([s.name for s in styles], ["MY WALTZ", "Easy 16 Beat", ""])
        self.assertEqual(styles[0].variations, ["Waltz 1", "Waltz 2", "", ""])

    def test_msp(self):
        f = songdata.read_msp(make_msp())
        self.assertEqual([b.name for b in f.banks][:2], ["Compile Bank 1", "User Bank 1"])
        self.assertEqual(f.banks[0].pads[0].builtin, (0x71, 2))
        self.assertEqual(f.banks[0].pads[5].user, 2)
        self.assertEqual(f.banks[0].pads[5].name, "Pad 2")
        self.assertEqual(f.banks[3].pads[0].name, "Pad 13")      # user bank 3, pad 1

    def test_tm(self):
        for model in (b"KN7000", b"KN6000"):
            f = songdata.read_tm(make_tm(model))
            self.assertEqual(f.model, model.decode())
            self.assertEqual(len(f.sounds), 40)
            self.assertEqual(f.sounds[39], "Sound 40")
            self.assertEqual(f.drum_kit, "User Kit")

    def test_hmp(self):
        h = songdata.read_hmp(make_hmp())
        self.assertEqual((h.width, h.height), (160, 100))
        self.assertEqual(h.bmp, make_bmp())
        self.assertEqual(len(h.record), 0x10 + 0x18C)
        with self.assertRaises(songdata.FormatError):
            songdata.read_hmp(b"JK \0" + bytes(500))


def make_tkm(names):
    return b"".join(b"S4\0\0\0\x01\0\x03" + (n or "_" * 16).encode().ljust(16, b" ")[:16] + bytes(0x200 - 24)
                    for n in names)


def make_plm(entries):
    d = bytearray(2560)
    d[0:12] = b"S1SD-SOUND\0\x10"
    d[0x24:0x28] = b"S2\0\0"
    for i, v in enumerate(entries):
        struct.pack_into(">H", d, 0x28 + 2 * i, v)
    return bytes(d)


class SDSoundTests(unittest.TestCase):
    def test_tkm_and_plm(self):
        st = MemoryStorage({"SD_SOUND/SD_SOUND.TKM": make_tkm([""] + ["DISK%02d" % i for i in range(2, 17)]),
                            "SD_SOUND/SD_SOUND.PLM": make_plm([0x8010, 0x8002, 0xC011, 0xC012, 0xC013]),
                            "SD_SOUND/A.MID": b"MThd", "SD_SOUND/POP/B.MID": b"MThd"})
        s = sdsound.read(st)
        self.assertEqual(s.names[0], "")
        self.assertEqual(s.names[15], "DISK16")
        self.assertEqual(s.order, [("A", 16), ("A", 2), ("B", 17), ("B", 18), ("B", 19)])
        self.assertEqual(sdsound.midi_files(st), ["SD_SOUND/A.MID", "SD_SOUND/POP/B.MID"])

    def test_missing_folder(self):
        st = MemoryStorage()
        self.assertEqual(sdsound.read(st).names, [])
        self.assertEqual(sdsound.midi_files(st), [])

    def test_bad_files(self):
        with self.assertRaises(sdsound.FormatError):
            sdsound.read_tkm(b"XX" + bytes(0x1FE))
        with self.assertRaises(sdsound.FormatError):
            sdsound.read_plm(bytes(2560))

    def test_runs(self):
        self.assertEqual(_runs([("A", 16), ("A", 2), ("A", 5), ("A", 6), ("A", 7), ("B", 17), ("B", 18)]),
                         "A16 A2 A5-A7 B17 B18")


def card_with_contents():
    st = MemoryStorage()
    s = CardSession.create(st)
    src = MemoryStorage({"x.PMT": container.build_kd(make_pmt()), "x.CMP": container.build_kd(make_cmp()),
                         "x.MSP": container.build_kd(make_msp()), "x.TM": container.build_kd(make_tm()),
                         "x.HMP": make_hmp(), "bad.LSW": b"lsw"})
    s.import_song(src, {"PMT": "x.PMT", "CMP": "x.CMP", "MSP": "x.MSP", "TM": "x.TM", "HMP": "x.HMP",
                        "LSW": "bad.LSW"}, "SONG", 1)
    src2 = MemoryStorage({"x.PMT": container.build_kd(b"rubbish")})
    s.import_song(src2, {"PMT": "x.PMT"}, "ODD", 1)
    s.save()
    st.write("SD_SOUND/SD_SOUND.TKM", make_tkm(["X"] * 16))
    return st, CardSession.open(st)


class SessionContentsTests(unittest.TestCase):
    def setUp(self):
        self.st, self.s = card_with_contents()

    def test_song_details(self):
        d = self.s.song_details(1, 1)
        self.assertEqual(d["panel_memories"][0]["memories"][0]["name"], "Memory 11")
        self.assertEqual(d["styles"][0]["name"], "MY WALTZ")
        self.assertEqual(d["pads"]["banks"][1]["pads"][0]["name"], "Pad 1")
        self.assertEqual(d["sounds"]["drum_kit"], "User Kit")
        self.assertEqual(d["home_page"], {"width": 160, "height": 100, "bmp_bytes": len(make_bmp())})
        self.assertNotIn("errors", d)
        self.assertEqual(self.s.home_page_bmp(1, 1), make_bmp())

    def test_odd_file_is_reported_not_raised(self):
        d = self.s.song_details(1, 2)
        self.assertNotIn("panel_memories", d)
        self.assertIn("PMT", d["errors"])
        self.assertIsNone(self.s.home_page_bmp(1, 2))

    def test_sd_sound(self):
        self.assertEqual(self.s.sd_sound(), {"names": ["X"] * 16, "order": [], "midi": []})

    def test_cli(self):
        from kn_songboek.cli import main as cli
        orig = cli._open
        cli._open = lambda args: self.s
        try:
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(main(["show", "card", "1", "1"]), 0)
                self.assertEqual(main(["sdsound", "card"]), 0)
            text = out.getvalue()
        finally:
            cli._open = orig
        for want in ("panel memory bank 1: Bank 1", "Memory 11", "tempo 120", "composer style 1: MY WALTZ  (Waltz 1, Waltz 2)",
                     "pad bank 2: User Bank 1: Pad 1", "drum kit User Kit", "home page picture: 160x100",
                     "SD_SOUND.TKM"):
            self.assertIn(want, text)


@gui_test
class GuiContentsTests(unittest.TestCase):
    def test_panel_has_everything(self):
        """The info panel is the one place for what is in a song (the separate Inhoud-window is gone):
        Reg Banks, composer styles, the home page picture and what could not be read."""
        import os
        import tempfile
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        st, s = card_with_contents()
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            d = w.presenter.song_panel((1, 1))
            self.assertEqual((d["banks"][0]["label"], d["banks"][0]["name"]), ("A", "Bank 1"))
            self.assertEqual(d["styles"][0][1], "MY WALTZ")
            self.assertEqual(d["bmp"], make_bmp())
            d = w.presenter.song_panel((1, 2))
            self.assertIsNone(d["bmp"])
            self.assertIn("PMT: niet te lezen", [h for h, _ in d["errors"]])
            self.assertNotIn("contents", w.acts)

    def test_panel_facts_and_info_from_real_files(self):
        """song_panel / song_facts / song_info on a song with every kind of file (gui/presenter_song.py)."""
        import os
        import tempfile
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtCore import QSettings
        from PySide6.QtWidgets import QApplication
        from kn_songboek.gui.qt_app import MainWindow
        QApplication.instance() or QApplication([])
        st, s = card_with_contents()
        with tempfile.TemporaryDirectory() as tmp:
            w = MainWindow(QSettings(os.path.join(tmp, "s.ini"), QSettings.IniFormat))
            w.presenter._opener = lambda p: s
            w.presenter.open_card("c")
            p = w.presenter
            d = p.song_panel((1, 1))
            self.assertEqual(d["banks"][0]["label"], "A")
            self.assertTrue(d["banks"][0]["memories"][0]["filled"])
            self.assertEqual(d["styles"][0][1], "MY WALTZ")
            self.assertTrue(d["pads"] and d["has_sounds"])
            self.assertEqual(d["bmp"], make_bmp())
            self.assertIn("PMT", [e for e, _z in d["files"]])
            facts = p.song_facts((1, 1))
            self.assertEqual(set(facts), {"rhythm", "meter", "tempo", "model", "recorded", "chord", "chord_short", "banks", "inside"})
            self.assertTrue(p._export_details((1, 1), ["chord"])["chord"])     # the short words for a list
            name, rows = p.song_info((1, 1))
            self.assertTrue(name.startswith("SONG"))
            self.assertIn("Plaats", dict(rows))
            broken = p.song_panel((1, 2))                               # unreadable PMT: said, no error window
            self.assertIn("PMT: niet te lezen", [h for h, _e in broken["errors"]])


if __name__ == "__main__":
    unittest.main()


class PanelSettingsTests(unittest.TestCase):
    def test_settings_from_blocks(self):
        from kn_songboek.formats import panelsettings
        part = bytearray(72)
        part[0:4] = bytes([73, 0, 32, 100])
        part[0x0D] = 0x80 | 60                       # chorus 60, on
        part[0x1C] = 96                              # pan right 32
        blocks = {0x42: bytes([0, 0, 0, 2, 0x40, 0, 0, 0x20, 120, 0, 0, 0, 0, 0]),
                  0x44: bytes([1, 56, 66, 0xFF, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0]),
                  0x41: bytes([5, 0, 0, 1, 64, 0, 0, 0]), 0x10: bytes(part), 0x13: bytes([90, 0, 0, 0])}
        got = {(x["group"], x["key"]): x for x in panelsettings.settings(blocks)}
        self.assertEqual(got[("style", "variation")]["value"], 2)          # VARIATION 3 (0-based)
        self.assertEqual(got[("keys", "transpose")]["value"], 66)          # +2
        self.assertEqual(got[("keys", "split_point")]["value"], 56)
        self.assertTrue(got[("style", "left_hold")]["value"])
        self.assertFalse(got[("style", "techni_type")]["sure"])           # meaning of the number unknown
        self.assertEqual(got[("volumes", "acc1")]["value"], 90)
        self.assertEqual(got[("R1", "chorus")]["value"], 60)
        self.assertTrue(got[("R1", "chorus_on")]["value"])
        self.assertNotIn(("R1", "sound"), got)                               # R1 shows its sound elsewhere
