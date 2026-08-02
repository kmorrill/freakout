import base64
import unittest

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_payload import (
    MICROFREAK_PARAMETER_SPECS,
    decode_microfreak_parameters,
    set_microfreak_parameter,
)


class MicroFreakPayloadTests(unittest.TestCase):
    def test_all_evidence_labelled_parameters_decode(self):
        payload = bytes(4672)
        decoded = decode_microfreak_parameters(payload)
        self.assertEqual(set(decoded), set(MICROFREAK_PARAMETER_SPECS))
        self.assertEqual(
            decoded["filter.cutoff"].status,
            "hardware_raw_rw_fw5_semantics_unconfirmed",
        )
        self.assertEqual(
            decoded["filter.resonance"].status,
            "published_stable_layout_observed_fw5",
        )
        self.assertNotIn("envelope.attack", decoded)

    def test_continuous_setter_changes_only_three_published_bytes(self):
        payload = bytes((index % 128 for index in range(4672)))
        changed = set_microfreak_parameter(payload, "filter.cutoff", 0.5)
        spec = MICROFREAK_PARAMETER_SPECS["filter.cutoff"]
        differences = {
            index for index, (left, right) in enumerate(zip(payload, changed)) if left != right
        }
        self.assertLessEqual(
            differences,
            {spec.msb_offset, spec.lsb_offset, spec.flag_offset},
        )
        decoded = decode_microfreak_parameters(changed)["filter.cutoff"]
        self.assertEqual(decoded.raw_value, round(0.5 * 32767))

    def test_document_carries_values_and_per_field_evidence(self):
        preset = MicroFreakPreset("Fixture", 2, 0, 16, bytes(4672))
        document = preset.to_document(1)
        self.assertIn("filter.cutoff", document.microfreak.decoded_parameters)
        evidence = document.microfreak.parameter_evidence["filter.cutoff"]
        self.assertEqual(evidence.encoding, "unsigned_15bit_normalized")

    def test_manual_decoded_only_edit_is_rejected(self):
        preset = MicroFreakPreset("Fixture", 2, 0, 16, bytes(4672))
        document = preset.to_document(1)
        document.microfreak.decoded_parameters["filter.cutoff"] = 0.5
        with self.assertRaisesRegex(ValueError, "set-microfreak-json"):
            MicroFreakPreset.from_document(document)


if __name__ == "__main__":
    unittest.main()
