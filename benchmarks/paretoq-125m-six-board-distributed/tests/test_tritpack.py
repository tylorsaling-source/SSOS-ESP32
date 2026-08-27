import itertools
import unittest

from tools.tritpack import pack_trits, unpack_trits


class TritPackTests(unittest.TestCase):
    def test_all_five_trit_combinations(self) -> None:
        for values in itertools.product((-1, 0, 1), repeat=5):
            payload, count = pack_trits(values)
            self.assertEqual(count, 5)
            self.assertEqual(len(payload), 1)
            self.assertEqual(unpack_trits(payload, count), list(values))

    def test_partial_final_byte(self) -> None:
        values = [-1, 0, 1, 1, 0, -1, 1]
        payload, count = pack_trits(values)
        self.assertEqual(len(payload), 2)
        self.assertEqual(unpack_trits(payload, count), values)

    def test_invalid_input(self) -> None:
        with self.assertRaises(ValueError):
            pack_trits([2])
        with self.assertRaises(ValueError):
            unpack_trits(bytes([243]), 5)


if __name__ == "__main__":
    unittest.main()
