import struct
import unittest
import zlib

from kn_songboek.formats import container as c


class ContainerKindTests(unittest.TestCase):
    def test_jk_d_is_lzss_like_j_kd(self):
        payload = b"IK\x00\x00     Room1      " * 20
        kd = c.build_kd(payload)
        k = c.parse(b"JK D" + kd[4:], "EFC")
        self.assertEqual((k.kind, k.parts), ("KD", [payload]))

    def test_kn6000_i_kd_is_deflate(self):
        payload = b"KN6000 SOUND RAM" * 50
        co = zlib.compressobj(6, zlib.DEFLATED, -15)
        stream = co.compress(payload) + co.flush() + struct.pack(">I", zlib.adler32(payload))
        data = b"I KD" + struct.pack(">HH", 1, 0) + struct.pack("<II", 0, len(payload)) + stream
        k = c.parse(data, "TM")
        self.assertEqual((k.kind, k.parts), ("ID", [payload]))

    def test_kn6000_two_parts_follow_each_other(self):
        """A KN6000 diskette's LSW: part 2 starts right after part 1's adler32, 2 bytes before
        0x18 + csize1 (csize1 counts 2 bytes more than the stream and its checksum)."""
        p1, p2 = b"first part " * 40, b"second part " * 90

        def pack(p):
            co = zlib.compressobj(6, zlib.DEFLATED, -15)
            return co.compress(p) + co.flush() + struct.pack(">I", zlib.adler32(p))
        s1, s2 = pack(p1), pack(p2)
        data = (b"I KD" + struct.pack(">HH", 1, 0) + struct.pack("<4I", len(p1), len(p2), len(s1) + 2, len(s2) + 2)
                + s1 + s2)
        k = c.parse(data, "LSW")
        self.assertEqual((k.kind, k.parts), ("ID", [p1, p2]))
        data = (b"I KD" + struct.pack(">HH", 1, 0) + struct.pack("<4I", len(p1), len(p2), len(s1), len(s2)) + s1 + s2)
        self.assertEqual(c.parse(data, "SQT").parts, [p1, p2])          # sizes that add up exactly: the same
