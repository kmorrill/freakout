import unittest

from minifreak_patch.microfreak_midi import pack_8bit_midi, unpack_8bit_midi
from minifreak_patch.microfreak_structured import (
    interpret_structured_field,
    parse_structured_fields,
    set_structured_raw_u16,
    set_structured_value,
    structured_field_role,
)
from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_payload import (
    OSCILLATOR_TYPE_HARDWARE_STATUS,
    decode_microfreak_parameters,
    set_microfreak_parameter,
)


def fixture_payload() -> bytes:
    prefix = (
        b"#VCO" + b"DTypec" + bytes((12, 0xFF, 0x5F))
        + b"FParam1c" + bytes((0xEE, 0xA0, 0x1A))
        + b"@#VCF" + b"FCutoffc" + bytes((0, 0xDA, 0x3C))
        + b"@ \xff"
    )
    unpacked = (prefix + bytes((0xFF,)) * 4088)[:4088]
    return pack_8bit_midi(unpacked)


class MicroFreakStructuredTests(unittest.TestCase):
    def test_parses_named_groups_without_fixed_offsets(self):
        payload = fixture_payload()
        fields = parse_structured_fields(payload)
        self.assertEqual(set(fields), {"VCO.Type", "VCO.Param1", "VCF.Cutoff"})
        self.assertEqual(fields["VCO.Type"].metadata, 12)
        self.assertEqual(fields["VCO.Type"].raw_u16, 0x5FFF)
        self.assertEqual(fields["VCF.Cutoff"].raw_u16, 0x3CDA)

    def test_raw_edit_round_trips_and_changes_only_value(self):
        payload = fixture_payload()
        before_unpacked = unpack_8bit_midi(payload)
        changed = set_structured_raw_u16(payload, "VCF.Cutoff", 0x1234)
        after_unpacked = unpack_8bit_midi(changed)
        differences = [
            index for index, pair in enumerate(zip(before_unpacked, after_unpacked))
            if pair[0] != pair[1]
        ]
        field = parse_structured_fields(changed)["VCF.Cutoff"]
        self.assertEqual(field.raw_u16, 0x1234)
        self.assertEqual(
            differences,
            [field.unpacked_value_offset, field.unpacked_value_offset + 1],
        )

    def test_pack_unpack_is_exact(self):
        payload = fixture_payload()
        self.assertEqual(pack_8bit_midi(unpack_8bit_midi(payload)), payload)

    def test_document_exposes_firmware_tagged_fields(self):
        document = MicroFreakPreset("Fixture", 2, 0, 16, fixture_payload()).to_document()
        field = document.microfreak.structured_parameters["VCF.Cutoff"]
        self.assertEqual(field.raw_u16, 0x3CDA)
        self.assertEqual(field.status, "firmware_tagged_payload_observed_fw5")
        self.assertEqual(field.value_kind, "unsigned_normalized")
        engine = document.microfreak.oscillator_engine
        self.assertEqual(engine.index, 9)
        self.assertEqual(engine.name, "Formant")
        self.assertEqual(engine.saved_layout_max_index, 12)
        self.assertEqual(engine.saved_layout_family, "historical")
        self.assertFalse(engine.can_select_all_firmware_5_engines)

    def test_metadata_scaled_and_normalized_interpretation(self):
        fields = parse_structured_fields(fixture_payload())
        osc_type = interpret_structured_field(fields["VCO.Type"])
        self.assertEqual(osc_type.kind, "metadata_scaled_integer")
        self.assertEqual(osc_type.value, 9)
        cutoff = interpret_structured_field(fields["VCF.Cutoff"])
        self.assertEqual(cutoff.kind, "unsigned_normalized")
        self.assertAlmostEqual(cutoff.value, 0x3CDA / 32767)

    def test_interpreted_setter_uses_per_preset_metadata(self):
        payload = fixture_payload()
        changed = set_structured_value(payload, "VCO.Type", 3)
        field = parse_structured_fields(changed)["VCO.Type"]
        self.assertEqual(field.raw_u16, round(3 * 32767 / 12))
        self.assertEqual(interpret_structured_field(field).value, 3)

        changed = set_structured_value(payload, "VCF.Cutoff", 0.5)
        self.assertEqual(
            parse_structured_fields(changed)["VCF.Cutoff"].raw_u16,
            round(0.5 * 32767),
        )

    def test_canonical_oscillator_type_uses_tagged_field_not_legacy_byte(self):
        payload = fixture_payload()
        decoded = decode_microfreak_parameters(payload)["osc.type"]
        self.assertEqual(decoded.value, 9)
        self.assertEqual(decoded.raw_value, 0x5FFF)
        self.assertEqual(decoded.status, OSCILLATOR_TYPE_HARDWARE_STATUS)
        self.assertEqual(decoded.byte_offsets, (8, 12, 13, 14))
        self.assertEqual(
            decoded.evidence_encoding, "VCO.Type_metadata_scaled_integer"
        )

        changed = set_microfreak_parameter(payload, "osc.type", 3)
        self.assertEqual(
            interpret_structured_field(parse_structured_fields(changed)["VCO.Type"]).value,
            3,
        )
        with self.assertRaisesRegex(ValueError, "automatic layout migration"):
            set_microfreak_parameter(payload, "osc.type", 18)

    def test_raw_only_field_rejects_interpreted_edit(self):
        prefix = b"#Sys" + b"GPrsetIDc" + bytes((0, 1, 0)) + b"@ \xff"
        payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
        with self.assertRaisesRegex(ValueError, "ui_action_placeholder_candidate"):
            set_structured_value(payload, "Sys.PrsetID", 2)
        document = MicroFreakPreset("Fixture", 2, 0, 16, payload).to_document()
        field = document.microfreak.structured_parameters["Sys.PrsetID"]
        self.assertEqual(field.role, "ui_action_placeholder_candidate")
        self.assertIn("all_320", field.role_evidence)

    def test_legacy_panel_candidate_rejects_bounded_interpreted_edit(self):
        prefix = b"#Gen" + b"EPanelc" + bytes((1, 0, 0)) + b"@ \xff"
        payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
        field = parse_structured_fields(payload)["Gen.Panel"]
        self.assertEqual(interpret_structured_field(field).kind, "metadata_scaled_integer")
        with self.assertRaisesRegex(ValueError, "legacy_panel_state_candidate"):
            set_structured_value(payload, "Gen.Panel", 1)
        changed = set_structured_raw_u16(payload, "Gen.Panel", 32767)
        self.assertEqual(parse_structured_fields(changed)["Gen.Panel"].raw_u16, 32767)

    def test_firmware_f7_chord_offset_encoding_is_bounded_and_editable(self):
        prefix = (
            b"#Gen"
            + b"GChOffs1c" + bytes((0xF7, 0x00, 0x40))
            + b"GChOffs2c" + bytes((0xF7, 0x80, 0x7F))
            + b"GChOffs3c" + bytes((0xF7, 0x00, 0x00))
            + b"@ \xff"
        )
        payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
        fields = parse_structured_fields(payload)
        self.assertEqual(interpret_structured_field(fields["Gen.ChOffs1"]).value, 0)
        self.assertEqual(interpret_structured_field(fields["Gen.ChOffs2"]).value, 127)
        self.assertEqual(interpret_structured_field(fields["Gen.ChOffs3"]).value, -128)
        self.assertEqual(
            interpret_structured_field(fields["Gen.ChOffs1"]).kind,
            "signed_offset_shift7",
        )
        changed = set_structured_value(payload, "Gen.ChOffs1", -35)
        changed_field = parse_structured_fields(changed)["Gen.ChOffs1"]
        self.assertEqual(changed_field.raw_u16, 0x2E80)
        self.assertEqual(interpret_structured_field(changed_field).value, -35)
        with self.assertRaisesRegex(ValueError, "-128..127"):
            set_structured_value(payload, "Gen.ChOffs1", 128)

    def test_sequence_ui_offsets_and_trailer_mirrors_are_synchronized(self):
        prefix = (
            b"#Seq"
            + b"FLengthc" + bytes((60, 0xFF, 0x7F))
            + b"GGateLenc" + bytes((80, 0x00, 0x40))
            + b"@ \xff"
        )
        payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
        fields = parse_structured_fields(payload)
        length = interpret_structured_field(fields["Seq.Length"])
        gate = interpret_structured_field(fields["Seq.GateLen"])
        self.assertEqual(
            (length.value, length.minimum, length.maximum, length.kind),
            (64, 4, 64, "metadata_scaled_offset_integer"),
        )
        self.assertEqual(
            (gate.value, gate.minimum, gate.maximum, gate.kind),
            (50, 10, 90, "metadata_scaled_offset_integer"),
        )
        changed = set_structured_value(payload, "Seq.Length", 4)
        changed = set_structured_value(changed, "Seq.GateLen", 10)
        changed_fields = parse_structured_fields(changed)
        self.assertEqual(changed_fields["Seq.Length"].raw_u16, 0)
        self.assertEqual(changed_fields["Seq.GateLen"].raw_u16, 0)
        unpacked = unpack_8bit_midi(changed)
        for offset in (1980, 3022):
            trailer = offset + 64 * 16
            self.assertEqual(unpacked[trailer + 8 : trailer + 10], bytes((10, 4)))

    def test_matrix_assign_decodes_and_validates_live_destination_id(self):
        prefix = b"#Mat" + b"GAssign1c" + bytes((0, 0x01, 0x01)) + b"@ \xff"
        payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
        field = parse_structured_fields(payload)["Mat.Assign1"]
        value = interpret_structured_field(field)
        self.assertEqual(value.kind, "live_destination_id")
        self.assertEqual(value.value, 0x0101)
        self.assertEqual(value.label, "VCF.Cutoff")
        changed = set_structured_value(payload, "Mat.Assign1", 0x0705)
        changed_value = interpret_structured_field(
            parse_structured_fields(changed)["Mat.Assign1"]
        )
        self.assertEqual(changed_value.label, "Gen.UniSprd")
        with self.assertRaisesRegex(ValueError, "not a mapped live parameter"):
            set_structured_value(payload, "Mat.Assign1", 0x170F)

    def test_constant_field_roles_remain_candidates_not_claimed_facts(self):
        self.assertEqual(
            structured_field_role("Gen.Panel")[0],
            "legacy_panel_state_candidate",
        )
        self.assertEqual(
            structured_field_role("Mat.MatEnc")[0],
            "ui_action_placeholder_candidate",
        )
        self.assertEqual(structured_field_role("VCF.Cutoff"), ("patch_parameter", None))

    def test_manual_interpreted_only_edit_is_rejected(self):
        document = MicroFreakPreset("Fixture", 2, 0, 16, fixture_payload()).to_document()
        document.microfreak.structured_parameters[
            "VCF.Cutoff"
        ].interpreted_value = 0.5
        with self.assertRaisesRegex(ValueError, "set-microfreak-structured-value"):
            MicroFreakPreset.from_document(document)


if __name__ == "__main__":
    unittest.main()
