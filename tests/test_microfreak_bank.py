from pathlib import Path
from zipfile import ZipFile

import pytest

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_bank import MicroFreakBankDocument


def make_preset(name: str, payload: bytes) -> MicroFreakPreset:
    return MicroFreakPreset(
        name=name,
        category_id=0,
        init=0,
        p1=0,
        payload=payload,
    )


def make_bank_preset(name: str, payload: bytes) -> MicroFreakPreset:
    preset = make_preset(name, payload)
    preset.version_tag = "134"
    return preset


def test_mcc_directory_json_round_trip(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    presets = {
        "01-Project-A1.mbp": make_bank_preset("One", bytes(4672)),
        "512-Project-A512.mbp": make_bank_preset("Init", b""),
    }
    for filename, preset in presets.items():
        (source / filename).write_bytes(preset.to_bytes())

    bank = MicroFreakBankDocument.from_mcc_directory(source)
    assert [item.slot for item in bank.slots] == [1, 512]
    assert bank.occupied_count == 1
    assert bank.project_name == tmp_path.name
    assert bank.bank_directory == "source"

    restored = MicroFreakBankDocument.model_validate_json(
        bank.model_dump_json(exclude_none=True)
    )
    output = tmp_path / "output"
    restored.write_mcc_directory(output)

    for filename, preset in presets.items():
        assert (output / filename).read_bytes() == preset.to_bytes()


def test_bank_rejects_duplicate_slots(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    preset = make_preset("One", b"")
    (source / "1-A.mbp").write_bytes(preset.to_bytes())
    (source / "01-B.mbp").write_bytes(preset.to_bytes())

    with pytest.raises(ValueError, match="duplicate slot"):
        MicroFreakBankDocument.from_mcc_directory(source)


def test_bank_rejects_unmapped_mbp_filename(tmp_path: Path):
    (tmp_path / "preset.mbp").write_bytes(make_preset("One", b"").to_bytes())
    with pytest.raises(ValueError, match="determine slot"):
        MicroFreakBankDocument.from_mcc_directory(tmp_path)


def test_mfprojz_round_trip_preserves_topology_and_preset_bytes(tmp_path: Path):
    preset = make_bank_preset("One", bytes(4672))
    source = tmp_path / "source"
    source.mkdir()
    filename = "01-Freaky sounds-A1.mbp"
    (source / filename).write_bytes(preset.to_bytes())
    bank = MicroFreakBankDocument.from_mcc_directory(source).model_copy(
        update={
            "project_name": "Freaky sounds",
            "bank_directory": "01-Freaky sounds-A",
        }
    )

    archive_path = tmp_path / "bank.mfprojz"
    archive_path.write_bytes(bank.to_mfprojz())
    with ZipFile(archive_path) as archive:
        assert archive.namelist() == [
            "Freaky sounds/",
            "Freaky sounds/01-Freaky sounds-A/",
            "Freaky sounds/01-Freaky sounds-A/01-Freaky sounds-A1.mbp",
        ]
        assert archive.read(archive.namelist()[-1]) == preset.to_bytes()

    restored = MicroFreakBankDocument.from_mfprojz(archive_path)
    assert restored.project_name == "Freaky sounds"
    assert restored.bank_directory == "01-Freaky sounds-A"
    assert restored.slots[0].patch == bank.slots[0].patch


def test_slot_prefix_does_not_require_separator(tmp_path: Path):
    (tmp_path / "100Hypnoscillator-A6.mbp").write_bytes(
        make_bank_preset("One", bytes(4672)).to_bytes()
    )
    bank = MicroFreakBankDocument.from_mcc_directory(tmp_path)
    assert bank.slots[0].slot == 100


def test_slot_prefix_can_be_concatenated_with_date(tmp_path: Path):
    (tmp_path / "10600122021 17h55-A26.mbp").write_bytes(
        make_bank_preset("One", bytes(4672)).to_bytes()
    )
    bank = MicroFreakBankDocument.from_mcc_directory(tmp_path)
    assert bank.slots[0].slot == 106
