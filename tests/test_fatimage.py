import os
import shutil
import struct
import subprocess
import tempfile
import unittest

from kn_songboek.core import CardSession
from kn_songboek.storage import open_storage
from kn_songboek.storage.fatimage import FatError, FatImageStorage
from kn_songboek.storage.memory import MemoryStorage


def make_image(path, mb=16, mbr=False):
    """A blank FAT16 volume built by hand (so the tests need no mkfs), optionally inside an MBR."""
    bps, spc, reserved, nfats, root_entries = 512, 4, 4, 2, 512
    total = mb * 2048
    clusters = total // spc
    fatsz = (clusters * 2 + bps - 1) // bps
    bs = bytearray(512)
    bs[0:3] = b"\xeb\x3c\x90"
    bs[3:11] = b"SONGBOEK"
    struct.pack_into("<HBHBHHBHHHII", bs, 11, bps, spc, reserved, nfats, root_entries,
                     total if total < 65536 else 0, 0xF8, fatsz, 63, 255, 0, total if total >= 65536 else 0)
    bs[36:39] = b"\x80\x00\x29"
    bs[43:54] = b"NO NAME    "
    bs[54:62] = b"FAT16   "
    bs[510:512] = b"\x55\xaa"
    fat = bytearray(fatsz * bps)
    fat[0:4] = b"\xf8\xff\xff\xff"
    vol = bytes(bs) + bytes((reserved - 1) * bps) + bytes(fat) * nfats + bytes(root_entries * 32)
    pre = b""
    if mbr:
        m = bytearray(2048 * 512)
        struct.pack_into("<B3sB3sII", m, 446, 0, b"\0\0\0", 0x06, b"\0\0\0", 2048, total)
        m[510:512] = b"\x55\xaa"
        pre = bytes(m)
    with open(path, "wb") as fh:
        fh.write(pre + vol)
        fh.truncate(len(pre) + total * bps)


class FatImageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.img = os.path.join(self.tmp.name, "card.img")

    def tearDown(self):
        self.tmp.cleanup()

    def roundtrip(self, mbr):
        make_image(self.img, mbr=mbr)
        st = FatImageStorage(self.img)
        self.assertEqual(st.fat_type, 16)
        data = os.urandom(70000)
        st.write("PRIVATE/TECHNICS/KN7000/TFLD001/01001KN7.SQT", data)
        for i in range(60):                                  # more than one directory cluster
            st.write("PRIVATE/TECHNICS/KN7000/TFLD002/%02d002KN7.PMT" % i, bytes([i]) * i)
        st.move("PRIVATE/TECHNICS/KN7000/TFLD001/01001KN7.SQT", "PRIVATE/TECHNICS/KN7000/TFLD003/01003KN7.SQT")
        st.remove("PRIVATE/TECHNICS/KN7000/TFLD002/05002KN7.PMT")
        st.close()
        st = open_storage(self.img)
        self.assertIsInstance(st, FatImageStorage)
        self.assertEqual(st.read("private/technics/kn7000/tfld003/01003kn7.sqt"), data)
        self.assertFalse(st.exists("PRIVATE/TECHNICS/KN7000/TFLD001/01001KN7.SQT"))
        self.assertEqual(len(st.listdir("PRIVATE/TECHNICS/KN7000/TFLD002")), 59)
        self.assertEqual(st.read("PRIVATE/TECHNICS/KN7000/TFLD002/07002KN7.PMT"), bytes([7]) * 7)
        self.assertTrue(st.isdir("PRIVATE/TECHNICS"))
        free = st.free_bytes()
        st.write("PRIVATE/TECHNICS/KN7000/TFLD003/01003KN7.SQT", b"small")    # overwrite frees clusters
        self.assertGreater(st.free_bytes(), free)
        st.close()
        if shutil.which("fsck.fat") and not mbr:
            r = subprocess.run(["fsck.fat", "-n", self.img], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_superfloppy(self):
        self.roundtrip(False)

    def test_mbr_partition(self):
        self.roundtrip(True)

    def test_card_session_on_image(self):
        make_image(self.img)
        st = FatImageStorage(self.img)
        s = CardSession.create(st)
        s.import_song(MemoryStorage({"x.SQT": b"seq" * 1000}), {"SQT": "x.SQT"}, "IMAGE SONG", 4)
        s.save()
        s.move_song(4, 1, 9)
        s.save()
        st.close()
        s = CardSession.open(FatImageStorage(self.img))
        self.assertEqual(s.song(9, 1).name, "IMAGE SONG")
        self.assertEqual(s.validate(), [])

    def test_rejects_long_names_and_read_only(self):
        make_image(self.img)
        st = FatImageStorage(self.img)
        with self.assertRaises(FatError):
            st.write("PRIVATE/a long name.txt", b"x")
        st.close()
        ro = FatImageStorage(self.img, read_only=True)
        self.assertFalse(ro.writable())
        with self.assertRaises(FatError):
            ro.write("X.TXT", b"x")
        ro.close()

    def test_not_an_image(self):
        with open(self.img, "wb") as fh:
            fh.write(b"\0" * 4096)
        with self.assertRaises(FatError):
            FatImageStorage(self.img)

    @unittest.skipUnless(shutil.which("mkfs.fat") and shutil.which("mcopy"), "dosfstools/mtools not installed")
    def test_against_mkfs_and_mtools(self):
        for fat, mb in ((12, 4), (32, 300)):
            img = os.path.join(self.tmp.name, "f%d.img" % fat)
            with open(img, "wb") as fh:
                fh.truncate(mb << 20)
            subprocess.run(["mkfs.fat", "-F", str(fat), img], check=True, capture_output=True)
            subprocess.run(["mmd", "-i", img, "::Some Long Folder"], check=True)
            src = os.path.join(self.tmp.name, "src.bin")
            with open(src, "wb") as fh:
                fh.write(os.urandom(9000))
            subprocess.run(["mcopy", "-i", img, src, "::Some Long Folder/A long file name.bin"], check=True)
            st = FatImageStorage(img)
            self.assertEqual(st.fat_type, fat)
            with open(src, "rb") as fh:
                self.assertEqual(st.read("some long folder/a long file name.bin"), fh.read())
            st.write("SOMELO~1/NEW.DAT", b"n" * 5000)
            st.close()
            out = subprocess.run(["mcopy", "-i", img, "::Some Long Folder/NEW.DAT", "-"], capture_output=True).stdout
            self.assertEqual(out, b"n" * 5000)
            r = subprocess.run(["fsck.fat", "-n", img], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout)


class CliOnImageTests(unittest.TestCase):
    def test_cli_works_on_an_image(self):
        import io
        from contextlib import redirect_stdout
        from kn_songboek.cli.main import main
        with tempfile.TemporaryDirectory() as tmp:
            img = os.path.join(tmp, "card.img")
            make_image(img)
            def run(*a):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    code = main(["--backup-dir", os.path.join(tmp, "bk")] + list(a))
                return code, buf.getvalue()
            self.assertEqual(run("format", img)[0], 0)
            self.assertEqual(run("rename-folder", img, "2", "IMAGE")[0], 0)
            self.assertEqual(run("backups", img)[0], 0)
            code, out = run("ls", img, "--all")
            self.assertIn("IMAGE", out)
            self.assertEqual(run("restore", img, "1")[0], 0)
            self.assertEqual(run("check", img)[0], 0)
