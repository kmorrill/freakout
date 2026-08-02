import unittest

from pydantic import ValidationError

from minifreak_patch.preset import MiniFreakPreset
from minifreak_patch.schema import (
    DeviceModel,
    MicroFreakLiveTableDocument,
    MicroFreakLiveWordData,
    PatchDocument,
    PatchMetadata,
    SupportLevel,
    capabilities_for,
    decode_microfreak_characteristics,
    encode_microfreak_characteristics,
)


class PatchSchemaTests(unittest.TestCase):
    def test_capabilities_demarcate_active_and_saved_reads(self):
        mini = capabilities_for(DeviceModel.MINIFREAK)
        micro = capabilities_for(DeviceModel.MICROFREAK)
        self.assertEqual(mini["patch.device.active_read"].level, SupportLevel.VERIFIED)
        self.assertEqual(micro["patch.device.active_read"].level, SupportLevel.PARTIAL)
        self.assertEqual(
            micro["patch.device.active_sequence_behavioral_read"].level,
            SupportLevel.PARTIAL,
        )
        self.assertEqual(
            micro["patch.device.active_word_read"].level, SupportLevel.VERIFIED
        )
        self.assertEqual(
            micro["patch.device.active_write"].level, SupportLevel.GUARDED
        )
        self.assertEqual(
            micro["patch.device.active_word_write"].level, SupportLevel.GUARDED
        )
        self.assertEqual(micro["patch.device.saved_read"].level, SupportLevel.VERIFIED)
        self.assertEqual(
            micro["patch.device.init_template_read"].level, SupportLevel.VERIFIED
        )
        self.assertEqual(micro["global.device.read"].level, SupportLevel.VERIFIED)
        self.assertEqual(micro["global.device.write"].level, SupportLevel.GUARDED)

    def test_microfreak_live_table_document_validates_grouped_addresses(self):
        document = MicroFreakLiveTableDocument(
            start_ordinal=16,
            word_count=1,
            complete_table=False,
            words=[
                MicroFreakLiveWordData(
                    address=0x0100,
                    group=1,
                    word=0,
                    raw_u16=0x8000,
                    raw_s16=-32768,
                    raw_payload_hex="1001000000",
                )
            ],
        )
        self.assertEqual(document.schema_version, "arturia-microfreak-live-table/1")
        with self.assertRaises(ValidationError):
            MicroFreakLiveWordData(
                address=0x0101,
                group=1,
                word=0,
                raw_u16=1,
                raw_s16=1,
                raw_payload_hex="0001000001",
            )

    def test_minifreak_round_trip_through_document(self):
        source = MiniFreakPreset(
            name="Test Patch",
            pack="User",
            author="Tester",
            firmware_version="4.0.2.6369",
            preset_type="Keys",
            params={"Osc1_Type": 0.0, "Vcf_Cutoff": 0.75},
        )
        document = source.to_document()
        restored = MiniFreakPreset.from_document(document)
        self.assertEqual(restored.name, source.name)
        self.assertEqual(restored.params, source.params)
        self.assertEqual(restored.firmware_version, source.firmware_version)

    def test_device_block_is_required(self):
        with self.assertRaises(ValidationError):
            PatchDocument(
                device=DeviceModel.MICROFREAK,
                metadata=PatchMetadata(name="Missing block"),
            )

    def test_microfreak_characteristic_bit_order(self):
        self.assertEqual(
            decode_microfreak_characteristics("010000000000100000"),
            ["Complex", "Soft"],
        )
        self.assertEqual(
            encode_microfreak_characteristics(["Ambient", "Soft", "Soundtrack"]),
            "110000000000000100",
        )


if __name__ == "__main__":
    unittest.main()
