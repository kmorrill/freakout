from pathlib import Path
from zipfile import ZipFile

from minifreak_patch.microfreak_wavetable_bank import (
    MicroFreakWavetableBankDocument,
)
from minifreak_patch.wavetable import MICROFREAK_PCM_BYTES, MicroFreakWavetable


def test_wavetable_bank_directory_and_mfwbz_round_trip(tmp_path: Path):
    source = tmp_path / "01-Waves-A"
    source.mkdir()
    tables = {
        "01-Waves-A1.mfw": MicroFreakWavetable(
            "One", bytes(MICROFREAK_PCM_BYTES), version_tag="209", p3=1
        ),
        "16-Waves-A16.mfw": MicroFreakWavetable(
            "Sixteen", bytes([1]) * MICROFREAK_PCM_BYTES, version_tag="134", p3=1
        ),
    }
    for filename, table in tables.items():
        (source / filename).write_bytes(table.to_mfw())

    bank = MicroFreakWavetableBankDocument.from_mcc_directory(source).model_copy(
        update={"project_name": "Waves", "bank_directory": "01-Waves-A"}
    )
    archive_path = tmp_path / "Waves.mfwbz"
    archive_path.write_bytes(bank.to_mfwbz())
    with ZipFile(archive_path) as archive:
        assert archive.namelist() == [
            "Waves/",
            "Waves/01-Waves-A/",
            "Waves/01-Waves-A/01-Waves-A1.mfw",
            "Waves/01-Waves-A/16-Waves-A16.mfw",
        ]

    restored = MicroFreakWavetableBankDocument.from_mfwbz(archive_path)
    assert restored.model_dump() == bank.model_dump()
    output = tmp_path / "restored"
    restored.write_mcc_directory(output)
    for filename, table in tables.items():
        assert (output / filename).read_bytes() == table.to_mfw()
