from dataclasses import dataclass

import pytest

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_current import overlay_current_parameter_object
from minifreak_patch.microfreak_midi import pack_8bit_midi
from minifreak_patch.microfreak_structured import (
    parse_structured_fields,
    set_structured_raw_u16,
)


@dataclass(frozen=True)
class Field:
    name: str
    raw_u16: int
    aliases_match: bool = True


def _preset() -> MicroFreakPreset:
    prefix = (
        b"#VCO" + b"DTypec" + bytes((22, 0x00, 0x40))
        + b"@#VCF" + b"FCutoffc" + bytes((0, 0xDA, 0x3C))
        + b"@ \xff"
    )
    unpacked = (prefix + bytes((0xFF,)) * 4088)[:4088]
    return MicroFreakPreset("Test", 0, 0, 0x33, pack_8bit_midi(unpacked))


def test_current_overlay_applies_named_word_and_preserves_all_other_bytes():
    base = _preset()
    fields = parse_structured_fields(base.payload)
    name = "VCF.Cutoff"
    target = fields[name].raw_u16 ^ 0x0123
    expected = set_structured_raw_u16(base.payload, name, target)

    report = overlay_current_parameter_object(
        base,
        base_slot=320,
        live_fields=[Field(name, target)],
        oscillator_runtime_raw_u16=0xFFFF,  # deliberately off the 0..22 grid
    )

    assert report.preset.payload == expected
    assert report.current_parameter_fields_applied == (name,)
    assert report.oscillator_engine_applied is False
    assert report.live_fields_missing_from_base == ()


def test_current_overlay_rejects_alias_disagreement():
    base = _preset()
    with pytest.raises(ValueError, match="mismatched live aliases"):
        overlay_current_parameter_object(
            base,
            base_slot=1,
            live_fields=[Field("VCF.Cutoff", 123, aliases_match=False)],
            oscillator_runtime_raw_u16=0,
        )
