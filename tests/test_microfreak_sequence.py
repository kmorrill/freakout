import unittest

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_midi import pack_8bit_midi, unpack_8bit_midi
from minifreak_patch.microfreak_sequence import (
    KNOWN_EMPTY_NOTE_BYTES,
    SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES,
    SEQUENCE_NOTE_STATUS_BY_CODE,
    SEQUENCE_OFFSETS,
    analyze_sequence_payloads,
    parse_sequence_patterns,
    set_sequence_automation,
    set_sequence_automation_destination,
    set_sequence_note,
    set_sequence_note_status,
    set_sequence_velocity,
)


def sequence_fixture() -> bytes:
    unpacked = bytearray((0xFF,) * 4088)
    for offset in SEQUENCE_OFFSETS.values():
        for step in range(64):
            position = offset + step * 16
            unpacked[position : position + 16] = bytes(
                (60, 0xFF, 0xFF, 0xFF, 100, 100, 100, 100, *([0] * 8))
            )
    return pack_8bit_midi(bytes(unpacked))


class MicroFreakSequenceTests(unittest.TestCase):
    def test_parses_two_fixed_64_step_patterns(self):
        patterns = parse_sequence_patterns(sequence_fixture())
        self.assertEqual(set(patterns), {"A", "B"})
        self.assertEqual(len(patterns["A"].steps), 64)
        self.assertEqual(patterns["A"].steps[0].notes, (60, None, None, None))
        self.assertEqual(patterns["A"].steps[0].velocities, (100,) * 4)
        self.assertEqual(patterns["A"].steps[0].automation_values, (0,) * 4)
        self.assertEqual(patterns["A"].steps[0].automation_mask, 0)
        self.assertEqual(patterns["A"].steps[0].note_event_code, 0)
        self.assertEqual(patterns["A"].steps[0].note_status, "rest")
        self.assertEqual(patterns["A"].steps[0].reserved_bytes, (0, 0))
        self.assertEqual(patterns["A"].steps[0].unclassified_bytes, (0,) * 8)
        self.assertEqual(
            patterns["A"].automation_destination_addresses, (None,) * 4
        )
        self.assertEqual(patterns["A"].trailer_bytes, (0xFF,) * 18)

    def test_note_setter_changes_one_unpacked_byte(self):
        payload = sequence_fixture()
        changed = set_sequence_note(payload, "B", 64, 4, 127)
        before = unpack_8bit_midi(payload)
        after = unpack_8bit_midi(changed)
        differences = [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]]
        self.assertEqual(differences, [SEQUENCE_OFFSETS["B"] + 63 * 16 + 3])

    def test_json_note_edit_rebuilds_payload_and_preserves_unknown_bytes(self):
        preset = MicroFreakPreset("Seq", 7, 0, 16, sequence_fixture())
        document = preset.to_document()
        original = document.microfreak.sequence_patterns.pattern_a.steps[4]
        original.notes[2] = 72
        rebuilt = MicroFreakPreset.from_document(document)
        step = parse_sequence_patterns(rebuilt.payload)["A"].steps[4]
        self.assertEqual(step.notes[2], 72)
        self.assertEqual(step.unclassified_bytes, tuple(original.unclassified_bytes))

    def test_json_automation_edit_rebuilds_value_and_mask(self):
        preset = MicroFreakPreset("Seq", 7, 0, 16, sequence_fixture())
        document = preset.to_document()
        step = document.microfreak.sequence_patterns.pattern_a.steps[0]
        step.automation_values[1] = 73
        step.automation_mask |= 0b0010
        rebuilt = MicroFreakPreset.from_document(document)
        parsed = parse_sequence_patterns(rebuilt.payload)["A"].steps[0]
        self.assertEqual(parsed.automation_values[1], 73)
        self.assertEqual(parsed.automation_mask, 0b0010)

    def test_velocity_setter_changes_one_unpacked_byte(self):
        payload = sequence_fixture()
        changed = set_sequence_velocity(payload, "A", 2, 3, 91)
        before = unpack_8bit_midi(payload)
        after = unpack_8bit_midi(changed)
        self.assertEqual(
            [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]],
            [SEQUENCE_OFFSETS["A"] + 16 + 6],
        )

    def test_automation_setter_updates_value_and_presence_mask(self):
        payload = sequence_fixture()
        changed = set_sequence_automation(payload, "B", 3, 4, 0)
        offset = SEQUENCE_OFFSETS["B"] + 2 * 16
        raw = unpack_8bit_midi(changed)
        self.assertEqual(raw[offset + 11], 0)
        self.assertEqual(raw[offset + 13], 0b1000)
        cleared = unpack_8bit_midi(
            set_sequence_automation(changed, "B", 3, 4, None)
        )
        self.assertEqual(cleared[offset + 11], 0)
        self.assertEqual(cleared[offset + 13], 0)

    def test_automation_destination_is_little_endian_live_address(self):
        payload = sequence_fixture()
        changed = set_sequence_automation_destination(payload, "A", 3, 0x0602)
        before = unpack_8bit_midi(payload)
        after = unpack_8bit_midi(changed)
        offset = SEQUENCE_OFFSETS["A"] + 64 * 16 + 4
        self.assertEqual(after[offset : offset + 2], bytes((0x02, 0x06)))
        self.assertEqual(
            [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]],
            [offset, offset + 1],
        )
        parsed = parse_sequence_patterns(changed)["A"]
        self.assertEqual(
            parsed.automation_destination_addresses,
            (None, None, 0x0602, None),
        )
        self.assertIn(0x0602, SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES)
        with self.assertRaisesRegex(ValueError, "hardware-observed"):
            set_sequence_automation_destination(payload, "A", 1, 0x0700)

    def test_json_automation_destination_rebuilds_trailer_losslessly(self):
        preset = MicroFreakPreset("Seq", 7, 0, 16, sequence_fixture())
        document = preset.to_document()
        destination = (
            document.microfreak.sequence_patterns.pattern_b.automation_destinations[0]
        )
        destination.live_address = 0x0101
        destination.parameter = "filter.cutoff"
        rebuilt = MicroFreakPreset.from_document(document)
        parsed = parse_sequence_patterns(rebuilt.payload)["B"]
        self.assertEqual(
            parsed.automation_destination_addresses,
            (0x0101, None, None, None),
        )
        roundtrip = rebuilt.to_document()
        projected = (
            roundtrip.microfreak.sequence_patterns.pattern_b.automation_destinations[0]
        )
        self.assertEqual(projected.live_address, 0x0101)
        self.assertEqual(projected.parameter, "filter.cutoff")

    def test_note_status_setter_changes_only_hardware_status_byte(self):
        payload = sequence_fixture()
        changed = set_sequence_note_status(payload, "A", 3, "tie")
        before = unpack_8bit_midi(payload)
        after = unpack_8bit_midi(changed)
        offset = SEQUENCE_OFFSETS["A"] + 2 * 16 + 12
        self.assertEqual(
            [i for i, pair in enumerate(zip(before, after)) if pair[0] != pair[1]],
            [offset],
        )
        step = parse_sequence_patterns(changed)["A"].steps[2]
        self.assertEqual(step.note_event_code, 2)
        self.assertEqual(step.note_status, "tie")
        self.assertEqual(
            SEQUENCE_NOTE_STATUS_BY_CODE,
            {0: "rest", 1: "trigger", 2: "tie"},
        )

    def test_json_note_status_projection_is_editable(self):
        preset = MicroFreakPreset("Seq", 7, 0, 16, sequence_fixture())
        document = preset.to_document()
        step = document.microfreak.sequence_patterns.pattern_b.steps[7]
        step.note_status = "trigger"
        rebuilt = MicroFreakPreset.from_document(document)
        parsed = parse_sequence_patterns(rebuilt.payload)["B"].steps[7]
        self.assertEqual(parsed.note_event_code, 1)
        self.assertEqual(parsed.note_status, "trigger")

    def test_legacy_fb_empty_notes_parse_and_round_trip_losslessly(self):
        unpacked = bytearray(unpack_8bit_midi(sequence_fixture()))
        for offset in SEQUENCE_OFFSETS.values():
            for step in range(64):
                unpacked[offset + step * 16 : offset + step * 16 + 4] = b"\xfb" * 4
        payload = pack_8bit_midi(bytes(unpacked))
        patterns = parse_sequence_patterns(payload)
        self.assertIsNone(patterns["A"].steps[0].notes[0])
        preset = MicroFreakPreset("LegacySeq", 7, 0, 16, payload)
        self.assertEqual(MicroFreakPreset.from_document(preset.to_document()).payload, payload)

    def test_clear_uses_the_patterns_existing_empty_sentinel(self):
        unpacked = bytearray(unpack_8bit_midi(sequence_fixture()))
        offset = SEQUENCE_OFFSETS["A"]
        for step in range(64):
            unpacked[offset + step * 16 : offset + step * 16 + 4] = b"\xfb" * 4
        unpacked[offset] = 60
        changed = set_sequence_note(pack_8bit_midi(bytes(unpacked)), "A", 1, 1, None)
        self.assertEqual(unpack_8bit_midi(changed)[offset], 0xFB)
        self.assertEqual(KNOWN_EMPTY_NOTE_BYTES, {0xFB, 0xFF})

    def test_all_high_byte_note_tokens_are_lossless_and_explicit(self):
        unpacked = bytearray(unpack_8bit_midi(sequence_fixture()))
        offset = SEQUENCE_OFFSETS["A"]
        unpacked[offset : offset + 4] = bytes((0xE7, 0xF6, 0xFA, 0xFD))
        payload = pack_8bit_midi(bytes(unpacked))
        step = parse_sequence_patterns(payload)["A"].steps[0]
        self.assertEqual(step.notes, (None, None, None, None))
        self.assertEqual(step.note_bytes, (0xE7, 0xF6, 0xFA, 0xFD))
        preset = MicroFreakPreset("Tokens", 7, 0, 16, payload)
        self.assertEqual(MicroFreakPreset.from_document(preset.to_document()).payload, payload)

    def test_corpus_analyzer_reports_velocity_and_automation_domains(self):
        report = analyze_sequence_payloads([sequence_fixture()])
        self.assertEqual(report["fixed_size_payloads"], 1)
        self.assertEqual(report["payloads_with_note_projection"], 1)
        self.assertEqual(report["step_records"], 128)
        candidates = report["candidate_fields"]
        self.assertTrue(candidates["velocities"]["all_values_midi_7bit"])
        lane = candidates["automation_lanes"][0]
        self.assertEqual(lane["record_offset"], 8)
        self.assertEqual(lane["presence_mask_offset"], 13)
        self.assertEqual(lane["presence_mask_bit"], 0)
        self.assertEqual(
            candidates["note_event_code"]["code_meanings"],
            {0: "rest", 1: "trigger", 2: "tie"},
        )
        destinations = candidates["automation_destinations"]
        self.assertEqual(destinations["counts"], {"unused": 8})
        self.assertEqual(
            destinations["encoding"],
            "four_little_endian_operation41_addresses_ffff_unused",
        )
        self.assertEqual(candidates["pattern_trailer"]["size"], 18)
        self.assertEqual(
            candidates["pattern_trailer"]["remaining_raw_offsets"],
            list(range(8, 18)),
        )


if __name__ == "__main__":
    unittest.main()
