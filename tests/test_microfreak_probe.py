import unittest

from minifreak_patch.live import MICROFREAK_SENTINEL_VALUES
from minifreak_patch.microfreak_probe import (
    SHIFTED_LAYOUT_SPECS,
    analyze_microfreak_cc_sentinel,
)


def set_raw(payload: bytes, spec, raw: int) -> bytes:
    result = bytearray(payload)
    result[spec.msb_offset] = (raw >> 8) & 0x7F
    result[spec.lsb_offset] = raw & 0x7F
    shift = (spec.flag_mask & -spec.flag_mask).bit_length() - 1
    result[spec.flag_offset] = (
        result[spec.flag_offset] & ~spec.flag_mask
    ) | (((raw >> 7) & 1) << shift)
    return bytes(result)


class MicroFreakProbeTests(unittest.TestCase):
    def test_fw2_candidate_wins_when_all_shifted_fields_change(self):
        before = bytes(4672)
        after = before
        for index, spec in enumerate(
            SHIFTED_LAYOUT_SPECS["fw2_plus_candidate"].values(), start=1
        ):
            after = set_raw(after, spec, index * 3101)
        report = analyze_microfreak_cc_sentinel(
            before, after, MICROFREAK_SENTINEL_VALUES
        )
        self.assertEqual(report["resolved_layout"], "fw2_plus_candidate")
        self.assertEqual(report["layout_scores"]["fw2_plus_candidate"], 7)
        self.assertEqual(report["layout_scores"]["legacy_fw1"], 0)

    def test_identical_payload_is_not_treated_as_probe_evidence(self):
        with self.assertRaisesRegex(ValueError, "identical"):
            analyze_microfreak_cc_sentinel(
                bytes(4672), bytes(4672), MICROFREAK_SENTINEL_VALUES
            )

    def test_unexplained_bytes_are_preserved(self):
        before = bytes(4672)
        after = bytearray(before)
        after[4000] = 17
        report = analyze_microfreak_cc_sentinel(
            before, bytes(after), MICROFREAK_SENTINEL_VALUES
        )
        for layout in report["layouts"].values():
            self.assertIn(4000, layout["unexplained_changed_offsets"])

    def test_normalization_control_is_subtracted_before_scoring(self):
        baseline = bytes(4672)
        control = bytearray(baseline)
        control[3000] = 99
        sentinel = bytes(control)
        for index, spec in enumerate(
            SHIFTED_LAYOUT_SPECS["fw2_plus_candidate"].values(), start=1
        ):
            sentinel = set_raw(sentinel, spec, index * 3001)
        report = analyze_microfreak_cc_sentinel(
            baseline,
            sentinel,
            MICROFREAK_SENTINEL_VALUES,
            normalization_control=bytes(control),
        )
        self.assertEqual(
            report["comparison_basis"],
            "normalization_control_vs_sentinel",
        )
        self.assertEqual(report["normalization_changed_bytes"], 1)
        self.assertNotIn(3000, report["changed_offsets"])
        self.assertEqual(report["resolved_layout"], "fw2_plus_candidate")


if __name__ == "__main__":
    unittest.main()
