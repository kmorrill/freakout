import pytest

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_midi import pack_8bit_midi
from minifreak_patch.microfreak_structured import parse_structured_fields
from minifreak_patch.microfreak_structured_probe import (
    build_structured_sentinel_preset,
)


def fixture_payload() -> bytes:
    prefix = (
        b"#VCO" + b"DTypec" + bytes((12, 0xFF, 0x5F))
        + b"FParam1c" + bytes((0xEE, 0xA0, 0x1A))
        + b"@#VCF" + b"FCutoffc" + bytes((0, 0xDA, 0x3C))
        + b"@ \xff"
    )
    return pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])


def test_builds_multiple_interpreted_sentinels_without_changing_header():
    source = MicroFreakPreset("Fixture", 2, 0, 16, fixture_payload())
    target, edits = build_structured_sentinel_preset(
        source, {"VCO.Type": 3, "VCF.Cutoff": 0.5}
    )
    assert (target.name, target.category_id, target.p1) == ("Fixture", 2, 16)
    assert [edit.name for edit in edits] == ["VCO.Type", "VCF.Cutoff"]
    fields = parse_structured_fields(target.payload)
    assert fields["VCO.Type"].raw_u16 == round(3 * 32767 / 12)
    assert fields["VCF.Cutoff"].raw_u16 == round(0.5 * 32767)


def test_rejects_noop_and_missing_sentinels():
    source = MicroFreakPreset("Fixture", 2, 0, 16, fixture_payload())
    with pytest.raises(ValueError, match="does not change"):
        build_structured_sentinel_preset(source, {"VCO.Type": 9})
    with pytest.raises(ValueError, match="has no structured field"):
        build_structured_sentinel_preset(source, {"Kbd.Hold": 1})


def test_builds_distinct_raw_sentinels_for_raw_only_fields():
    prefix = (
        b"#Gen"
        + b"GChOffs1c" + bytes((247, 0x00, 0x40))
        + b"GChOffs2c" + bytes((247, 0x00, 0x40))
        + b"GChOffs3c" + bytes((247, 0x00, 0x40))
        + b"@ \xff"
    )
    payload = pack_8bit_midi((prefix + bytes((0xFF,)) * 4088)[:4088])
    source = MicroFreakPreset("Chord", 0, 0, 16, payload)
    target, edits = build_structured_sentinel_preset(
        source,
        {
            "Gen.ChOffs1": {"raw_u16": 12000},
            "Gen.ChOffs2": {"raw_u16": 20000},
            "Gen.ChOffs3": {"raw_u16": 28000},
        },
    )
    fields = parse_structured_fields(target.payload)
    assert [fields[f"Gen.ChOffs{index}"].raw_u16 for index in range(1, 4)] == [
        12000,
        20000,
        28000,
    ]
    assert [edit.value_kind for edit in edits] == ["raw_u16"] * 3
