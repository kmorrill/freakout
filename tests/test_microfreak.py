import base64
import zipfile
from io import BytesIO
import unittest

from minifreak_patch.microfreak import (
    MICROFREAK_PRESET_PAYLOAD_SIZE,
    MicroFreakObject,
    MicroFreakPreset,
)


class MicroFreakTests(unittest.TestCase):
    def test_object_text_round_trip_preserves_signed_bytes(self):
        source = MicroFreakObject(
            version_tag="TEST",
            name="A Name",
            p0=2,
            p3=0,
            p5=16,
            payload=bytes([0, 1, 127, 128, 255]),
            characteristics_bits="000000000000101100",
        )
        restored = MicroFreakObject.from_bytes(source.to_bytes())
        self.assertEqual(restored, source)

    def test_preset_json_round_trip_is_lossless(self):
        payload = bytes((index * 17) & 0xFF
                        for index in range(MICROFREAK_PRESET_PAYLOAD_SIZE))
        source = MicroFreakPreset(
            name="JSON Test",
            category_id=2,
            init=0,
            p1=16,
            payload=payload,
        )
        document = source.to_document(source_slot=12)
        self.assertEqual(document.metadata.source_slot, 12)
        self.assertEqual(
            base64.b64decode(document.microfreak.raw_payload_base64), payload
        )
        restored = MicroFreakPreset.from_document(document)
        self.assertEqual(restored, source)

    def test_mfpz_has_official_single_entry_and_round_trips(self):
        source = MicroFreakPreset("Zip Test", 2, 0, 16, bytes(4672))
        zipped = source.to_zip()
        with zipfile.ZipFile(BytesIO(zipped)) as archive:
            self.assertEqual(archive.namelist(), ["0_preset"])
            self.assertEqual(archive.read("0_preset"), source.to_bytes())
        self.assertEqual(MicroFreakPreset.from_bytes(zipped), source)

    def test_bank_object_variant_round_trips_exactly(self):
        source = (
            b"22 serialization::archive 10 0 4 3 134 4 Init 128 0 0 18 "
            b"000000000000101100 1 0 51 0\n"
        )
        preset = MicroFreakPreset.from_bytes(source)
        self.assertEqual(preset.version_tag, "134")
        self.assertEqual(preset.category_id, 128)
        self.assertEqual(preset.characteristics_bits, "000000000000101100")
        self.assertEqual(preset.to_bytes(), source)

    def test_archive_tag_is_opaque_and_preserved(self):
        source = MicroFreakPreset(
            "Dev", 3, 0, 16, bytes(4672), version_tag="DEVBUILD"
        )
        self.assertEqual(MicroFreakPreset.from_bytes(source.to_bytes()), source)

    def test_empty_bank_slot_can_preserve_long_project_label(self):
        source = MicroFreakPreset(
            "Solidtrax Back To The 80s V2_2-A384",
            0,
            1,
            51,
            b"",
            version_tag="1844",
        )
        restored = MicroFreakPreset.from_document(source.to_document())
        self.assertEqual(restored.to_bytes(), source.to_bytes())


if __name__ == "__main__":
    unittest.main()
