import unittest
from functools import reduce
from operator import xor

from minifreak_patch.collage import CollageError
from minifreak_patch.minifreak_payload import (
    MINIFREAK_HARDWARE_PRESET_SIZE,
    checksum_is_valid,
    decode_verified_parameters,
    set_verified_parameter,
    with_updated_checksum,
)


class MiniFreakPayloadTests(unittest.TestCase):
    def fixture(self):
        return with_updated_checksum(bytes(MINIFREAK_HARDWARE_PRESET_SIZE))

    def test_checksum_makes_the_whole_payload_xor_ff(self):
        payload = self.fixture()
        self.assertTrue(checksum_is_valid(payload))
        self.assertEqual(reduce(xor, payload, 0), 0xFF)

    def test_verified_parameter_edit_updates_raw_and_checksum(self):
        payload = set_verified_parameter(self.fixture(), "filter.cutoff", 0.5)
        decoded = decode_verified_parameters(payload)["filter.cutoff"]
        self.assertEqual(decoded["raw_value"], round(0.5 * 32767))
        self.assertAlmostEqual(decoded["value"], 0.5, places=4)
        self.assertTrue(checksum_is_valid(payload))

    def test_bipolar_parameter_accepts_negative_values(self):
        payload = set_verified_parameter(
            self.fixture(), "filter.env_amount", -0.25
        )
        decoded = decode_verified_parameters(payload)["filter.env_amount"]
        self.assertLess(decoded["raw_value"], 0)

    def test_rejects_unknown_and_out_of_range_edits(self):
        with self.assertRaises(CollageError):
            set_verified_parameter(self.fixture(), "oscillator.magic", 0.5)
        with self.assertRaises(CollageError):
            set_verified_parameter(self.fixture(), "filter.resonance", 2.0)


if __name__ == "__main__":
    unittest.main()
