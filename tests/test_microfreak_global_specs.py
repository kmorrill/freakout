from minifreak_patch.microfreak_global_specs import (
    MICROFREAK_GLOBAL_VALUE_SPECS,
    decode_microfreak_global,
)
from minifreak_patch.microfreak_midi import MICROFREAK_GLOBAL_CODES


def test_audited_domains_cover_all_43_named_globals():
    assert len(MICROFREAK_GLOBAL_CODES) == 43
    assert len(MICROFREAK_GLOBAL_VALUE_SPECS) == 43
    assert set(MICROFREAK_GLOBAL_VALUE_SPECS) == set(MICROFREAK_GLOBAL_CODES)


def test_irregular_and_generated_domains_preserve_wire_values():
    assert MICROFREAK_GLOBAL_VALUE_SPECS["midi.channel_in"].label(127) == "All"
    assert MICROFREAK_GLOBAL_VALUE_SPECS["midi.output_destination"].allowed_values == (
        0, 1, 4, 5
    )
    assert MICROFREAK_GLOBAL_VALUE_SPECS["keyboard.root_note"].label(1) == "C#"
    assert MICROFREAK_GLOBAL_VALUE_SPECS["tuning.master"].label(64) == "0 cents"
    assert MICROFREAK_GLOBAL_VALUE_SPECS["microphone.gain"].label(72) == "Auto Gain"
    assert MICROFREAK_GLOBAL_VALUE_SPECS["microphone.noise_gate"].label(31) == "-90 dB"


def test_firmware_clamps_supply_missing_domains_without_guessing_units():
    decoded = decode_microfreak_global("midi.automation_out", 1)
    assert decoded["value_domain_status"] == "firmware_5_global_setter_clamp_static"
    assert decoded["allowed_values"] == [0, 1]
    assert MICROFREAK_GLOBAL_VALUE_SPECS["device.id"].allowed_values == tuple(
        range(127)
    )
    assert MICROFREAK_GLOBAL_VALUE_SPECS["device.id"].label(126) == "126"
    assert MICROFREAK_GLOBAL_VALUE_SPECS[
        "keyboard.aftertouch_offset"
    ].allowed_values == tuple(range(101))
    assert MICROFREAK_GLOBAL_VALUE_SPECS[
        "midi.channel_in_lower"
    ].allowed_values == (*range(16), 126)
    assert MICROFREAK_GLOBAL_VALUE_SPECS["midi.channel_in_lower"].label(126) == "None"
