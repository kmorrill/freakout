import unittest
import zipfile
from io import BytesIO

from minifreak_patch.wavetable import (
    MICROFREAK_PCM_BYTES,
    MicroFreakWavetable,
)


class WavetableTests(unittest.TestCase):
    def test_microfreak_archive_round_trip(self):
        pcm = bytes((index * 13) & 0xFF for index in range(MICROFREAK_PCM_BYTES))
        source = MicroFreakWavetable(name="Test Table", pcm16le=pcm)
        restored = MicroFreakWavetable.from_mfw(source.to_mfw())
        self.assertEqual(restored, source)

    def test_microfreak_mfwz_container(self):
        source = MicroFreakWavetable(
            name="Zip Table", pcm16le=bytes(MICROFREAK_PCM_BYTES)
        )
        zipped = source.to_mfwz()
        with zipfile.ZipFile(BytesIO(zipped)) as archive:
            self.assertEqual(archive.namelist(), ["0_sample"])
            self.assertEqual(archive.read("0_sample"), source.to_mfw())
        self.assertEqual(MicroFreakWavetable.from_mfw(zipped), source)

    def test_microfreak_library_archive_fields_are_lossless(self):
        source = MicroFreakWavetable(
            name="Factory",
            pcm16le=bytes(MICROFREAK_PCM_BYTES),
            version_tag="209",
            p3=1,
        )
        restored = MicroFreakWavetable.from_document(source.to_document().to_dict())
        self.assertEqual(restored, source)
        self.assertEqual(restored.to_mfw(), source.to_mfw())

    def test_microfreak_size_is_strict(self):
        with self.assertRaises(ValueError):
            MicroFreakWavetable(name="Bad", pcm16le=b"short")


if __name__ == "__main__":
    unittest.main()
