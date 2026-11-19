import random
import unittest

from kn_songboek.formats import container


class FastDecodeTests(unittest.TestCase):
    def test_round_trip_on_many_kinds_of_data(self):
        random.seed(7)
        for n in (0, 1, 17, 300, 9000, 20000):
            for data in (bytes(random.getrandbits(8) for _ in range(n)),
                         bytes(random.choice(b"ab\0 ") for _ in range(n)),     # long overlapping runs
                         (b"KN7000 registration " * 1200)[:n], bytes(n)):     # zeros: refs into the ring's start
                self.assertEqual(container.lzss_decode(container.lzss_encode(data), len(data)), data)

    def test_parse_is_kept_and_hands_out_copies(self):
        raw = container.build_kd(b"PMT payload" * 100)
        a = container.parse(raw, "PMT")
        a.parts[0] = b"changed by a caller"
        self.assertEqual(container.parse(raw, "PMT").parts[0], b"PMT payload" * 100)

    def test_a_short_stream_still_fails(self):
        with self.assertRaises(ValueError):
            container.lzss_decode(b"\xff" + b"x" * 8, 20)


class OtherModelTests(unittest.TestCase):
    def test_kn5000_file_is_named(self):
        from kn_songboek.formats import container
        for magic in container.KN5000_MAGIC:
            with self.assertRaises(container.OtherModelError) as cm:
                container.parse(magic + bytes(60), "PMT")
            self.assertEqual(cm.exception.args[0].key, "kn5000_file")
