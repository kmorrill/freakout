"""Verified fields in the 3,328-byte MiniFreak hardware preset payload."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import reduce
from operator import xor

from minifreak_patch.collage import CollageError
from minifreak_patch.minifreak_corpus_map import CORPUS_EXACT_PARAMETERS


MINIFREAK_HARDWARE_PRESET_SIZE = 3328
MINIFREAK_CHECKSUM_OFFSET = 4


@dataclass(frozen=True)
class VerifiedParameter:
    name: str
    offset: int
    session_parameter_id: int | None
    minimum: float
    maximum: float
    mnfx_name: str
    mnfx_encoding: str
    corpus_distinct_values: int | None = None


VERIFIED_PARAMETERS = {
    "oscillator1.coarse_tune": VerifiedParameter(
        "Oscillator 1 Coarse Tune", 130, 0x01, -1.0, 1.0,
        "Osc1_CoarseTune", "normalized_bipolar_s16"
    ),
    "oscillator1.param1": VerifiedParameter(
        "Oscillator 1 Parameter 1", 136, 0x04, 0.0, 1.0,
        "Osc1_Param1", "unit_s16"
    ),
    "oscillator1.param2": VerifiedParameter(
        "Oscillator 1 Parameter 2", 138, 0x05, 0.0, 1.0,
        "Osc1_Param2", "unit_s16"
    ),
    "oscillator1.param3": VerifiedParameter(
        "Oscillator 1 Parameter 3", 140, 0x06, 0.0, 1.0,
        "Osc1_Param3", "unit_s16"
    ),
    "oscillator1.volume": VerifiedParameter(
        "Oscillator 1 Volume", 148, 0x0A, 0.0, 1.0,
        "Osc1_Volume", "unit_s16"
    ),
    "oscillator2.coarse_tune": VerifiedParameter(
        "Oscillator 2 Coarse Tune", 150, 0x0B, -1.0, 1.0,
        "Osc2_CoarseTune", "normalized_bipolar_s16"
    ),
    "oscillator2.fine_tune": VerifiedParameter(
        "Oscillator 2 Fine Tune", 152, 0x0C, -1.0, 1.0,
        "Osc2_FineTune", "normalized_bipolar_s16"
    ),
    "oscillator2.param1": VerifiedParameter(
        "Oscillator 2 Parameter 1", 156, 0x0E, 0.0, 1.0,
        "Osc2_Param1", "unit_s16"
    ),
    "oscillator2.param2": VerifiedParameter(
        "Oscillator 2 Parameter 2", 158, 0x0F, 0.0, 1.0,
        "Osc2_Param2", "unit_s16"
    ),
    "oscillator2.param3": VerifiedParameter(
        "Oscillator 2 Parameter 3", 160, 0x10, 0.0, 1.0,
        "Osc2_Param3", "unit_s16"
    ),
    "oscillator2.volume": VerifiedParameter(
        "Oscillator 2 Volume", 168, 0x14, 0.0, 1.0,
        "Osc2_Volume", "unit_s16"
    ),
    "oscillator.glide": VerifiedParameter(
        "Glide", 170, 0x15, 0.0, 1.0, "Osc_Glide", "unit_s16"
    ),
    "oscillator.bend_range": VerifiedParameter(
        "Pitch Bend Range", 174, 0x17, 0.0, 1.0,
        "Osc_BendRange", "unit_s16"
    ),
    "filter.cutoff": VerifiedParameter(
        "Filter Cutoff", 178, 0x19, 0.0, 1.0,
        "Vcf_Cutoff", "unit_s16"
    ),
    "filter.resonance": VerifiedParameter(
        "Filter Resonance", 180, 0x1A, 0.0, 1.0,
        "Vcf_Resonance", "unit_s16"
    ),
    "filter.env_amount": VerifiedParameter(
        "Filter Envelope Amount", 182, 0x1B, -1.0, 1.0,
        "Vcf_EnvAmount", "normalized_bipolar_s16"
    ),
    "envelope.attack": VerifiedParameter(
        "Envelope Attack", 186, 0x1D, 0.0, 1.0,
        "Env_Attack", "unit_s16"
    ),
    "envelope.decay": VerifiedParameter(
        "Envelope Decay", 188, 0x1E, 0.0, 1.0,
        "Env_Decay", "unit_s16"
    ),
    "envelope.sustain": VerifiedParameter(
        "Envelope Sustain", 190, 0x1F, 0.0, 1.0,
        "Env_Sustain", "unit_s16"
    ),
    "envelope.release": VerifiedParameter(
        "Envelope Release", 192, 0x20, 0.0, 1.0,
        "Env_Release", "unit_s16"
    ),
    "cycling_envelope.rise": VerifiedParameter(
        "Cycling Envelope Rise", 206, 0x27, 0.0, 1.0,
        "CycEnv_Rise", "unit_s16"
    ),
    "cycling_envelope.fall": VerifiedParameter(
        "Cycling Envelope Fall", 208, 0x28, 0.0, 1.0,
        "CycEnv_Fall", "unit_s16"
    ),
    "cycling_envelope.hold": VerifiedParameter(
        "Cycling Envelope Hold", 210, 0x29, 0.0, 1.0,
        "CycEnv_Hold", "unit_s16"
    ),
    "cycling_envelope.rise_curve": VerifiedParameter(
        "Cycling Envelope Rise Curve", 212, 0x2A, 0.0, 1.0,
        "CycEnv_RiseCurve", "unit_s16"
    ),
    "cycling_envelope.fall_curve": VerifiedParameter(
        "Cycling Envelope Fall Curve", 214, 0x2B, 0.0, 1.0,
        "CycEnv_FallCurve", "unit_s16"
    ),
    "lfo1.rate": VerifiedParameter(
        "LFO 1 Rate", 224, 0x30, 0.0, 1.0,
        "LFO1_Rate", "unit_s16"
    ),
    "lfo2.rate": VerifiedParameter(
        "LFO 2 Rate", 238, 0x37, 0.0, 1.0,
        "LFO2_Rate", "unit_s16"
    ),
    "voice.unison_spread": VerifiedParameter(
        "Unison Spread", 292, 0x52, 0.0, 1.0,
        "Gen_UnisonSpread", "unit_s16"
    ),
    "cycling_envelope.mode": VerifiedParameter(
        "Cycling Envelope Mode", 204, 0x26, 0.0, 1.0,
        "CycEnv_Mode", "unit_s16"
    ),
    "cycling_envelope.retrigger_source": VerifiedParameter(
        "Cycling Envelope Retrigger Source", 220, 0x2E, 0.0, 1.0,
        "CycEnv_RetrigSrc", "unit_s16"
    ),
    "lfo1.wave": VerifiedParameter(
        "LFO 1 Wave", 222, 0x2F, 0.0, 1.0,
        "LFO1_Wave", "unit_s16"
    ),
    "lfo1.synced_rate": VerifiedParameter(
        "LFO 1 Synced Rate", 226, 0x31, 0.0, 1.0,
        "LFO1_RateSync", "unit_s16"
    ),
    "lfo1.retrigger": VerifiedParameter(
        "LFO 1 Retrigger", 234, 0x35, 0.0, 1.0,
        "LFO1_Retrig", "unit_s16"
    ),
    "lfo2.wave": VerifiedParameter(
        "LFO 2 Wave", 236, 0x36, 0.0, 1.0,
        "LFO2_Wave", "unit_s16"
    ),
    "lfo2.synced_rate": VerifiedParameter(
        "LFO 2 Synced Rate", 240, 0x38, 0.0, 1.0,
        "LFO2_RateSync", "unit_s16"
    ),
    "lfo2.retrigger": VerifiedParameter(
        "LFO 2 Retrigger", 248, 0x3C, 0.0, 1.0,
        "LFO2_Retrig", "unit_s16"
    ),
    "macro1.value": VerifiedParameter(
        "Macro 1 Value", 250, 0x3D, 0.0, 1.0,
        "Macro1_Value", "unit_s16"
    ),
    "macro2.value": VerifiedParameter(
        "Macro 2 Value", 252, 0x3E, 0.0, 1.0,
        "Macro2_Value", "unit_s16"
    ),
    "voice.note_mode": VerifiedParameter(
        "Voice Note Mode", 286, 0x4F, 0.0, 1.0,
        "Gen_NoteMode", "unit_s16"
    ),
    "voice.unison_count": VerifiedParameter(
        "Unison Voice Count", 294, 0x53, 0.0, 1.0,
        "Gen_UnisonCount", "unit_s16"
    ),
    "keyboard.source": VerifiedParameter(
        "Keyboard Source", 534, 0xCB, 0.0, 1.0,
        "Kbd_Src", "unit_s16"
    ),
    "modulation.wheel": VerifiedParameter(
        "Modulation Wheel", 622, 0xF7, 0.0, 1.0,
        "Mod_Wheel", "unit_s16"
    ),
    "keyboard.octave": VerifiedParameter(
        "Keyboard Octave", 626, 0xF9, 0.0, 1.0,
        "Kbd_Octave", "unit_s16"
    ),
    "keyboard.chord_length": VerifiedParameter(
        "Chord Length", 660, 0x10A, 0.0, 1.0,
        "Kbd_Chord_Length", "unit_s16"
    ),
    "keyboard.chord_offset_0": VerifiedParameter(
        "Chord Offset 1", 666, 0x10D, -1.0, 1.0,
        "Kbd_Chord_Offset_0", "normalized_bipolar_s16"
    ),
    "fx1.param1": VerifiedParameter(
        "FX 1 Parameter 1", 564, 0xDA, 0.0, 1.0,
        "FX1_Param1", "unit_s16"
    ),
    "fx1.param2": VerifiedParameter(
        "FX 1 Parameter 2", 566, 0xDB, 0.0, 1.0,
        "FX1_Param2", "unit_s16"
    ),
    "fx1.param3": VerifiedParameter(
        "FX 1 Parameter 3", 568, 0xDC, 0.0, 1.0,
        "FX1_Param3", "unit_s16"
    ),
    "fx1.option1": VerifiedParameter(
        "FX 1 Option 1", 570, 0xDD, 0.0, 1.0,
        "FX1_Opt1", "unit_s16"
    ),
    "fx1.option2": VerifiedParameter(
        "FX 1 Option 2", 572, 0xDE, 0.0, 1.0,
        "FX1_Opt2", "unit_s16"
    ),
    "fx1.option3": VerifiedParameter(
        "FX 1 Option 3", 574, 0xDF, 0.0, 1.0,
        "FX1_Opt3", "unit_s16"
    ),
    "fx2.param1": VerifiedParameter(
        "FX 2 Parameter 1", 582, 0xE3, 0.0, 1.0,
        "FX2_Param1", "unit_s16"
    ),
    "fx2.param2": VerifiedParameter(
        "FX 2 Parameter 2", 584, 0xE4, 0.0, 1.0,
        "FX2_Param2", "unit_s16"
    ),
    "fx2.param3": VerifiedParameter(
        "FX 2 Parameter 3", 586, 0xE5, 0.0, 1.0,
        "FX2_Param3", "unit_s16"
    ),
    "fx2.option1": VerifiedParameter(
        "FX 2 Option 1", 588, 0xE6, 0.0, 1.0,
        "FX2_Opt1", "unit_s16"
    ),
    "fx3.param1": VerifiedParameter(
        "FX 3 Parameter 1", 600, 0xEC, 0.0, 1.0,
        "FX3_Param1", "unit_s16"
    ),
    "fx3.param2": VerifiedParameter(
        "FX 3 Parameter 2", 602, 0xED, 0.0, 1.0,
        "FX3_Param2", "unit_s16"
    ),
    "fx3.param3": VerifiedParameter(
        "FX 3 Parameter 3", 604, 0xEE, 0.0, 1.0,
        "FX3_Param3", "unit_s16"
    ),
    "fx3.option1": VerifiedParameter(
        "FX 3 Option 1", 606, 0xEF, 0.0, 1.0,
        "FX3_Opt1", "unit_s16"
    ),
    "sequencer.time_division": VerifiedParameter(
        "Sequencer Time Division", 694, 0x11B, 0.0, 1.0,
        "Seq_TimeDiv", "unit_s16"
    ),
    "sequencer.gate": VerifiedParameter(
        "Sequencer Gate", 696, 0x11C, 0.0, 1.0,
        "Seq_Gate", "unit_s16"
    ),
    "sequencer.length": VerifiedParameter(
        "Sequencer Length", 700, 0x11E, 0.0, 1.0,
        "Seq_Length", "unit_s16"
    ),
    "sequencer.automation_set_0": VerifiedParameter(
        "Sequencer Automation Set 1", 710, 0x123, 0.0, 1.0,
        "Seq_Autom_Set_0", "unit_s16"
    ),
    "sequencer.automation_set_1": VerifiedParameter(
        "Sequencer Automation Set 2", 712, 0x124, 0.0, 1.0,
        "Seq_Autom_Set_1", "unit_s16"
    ),
    "sequencer.automation_set_2": VerifiedParameter(
        "Sequencer Automation Set 3", 714, 0x125, 0.0, 1.0,
        "Seq_Autom_Set_2", "unit_s16"
    ),
    "arpeggiator.mode": VerifiedParameter(
        "Arpeggiator Mode", 734, 0x12F, 0.0, 1.0,
        "Arp_Mode", "unit_s16"
    ),
    "arpeggiator.octaves": VerifiedParameter(
        "Arpeggiator Octaves", 736, 0x130, 0.0, 1.0,
        "Arp_Oct", "unit_s16"
    ),
}

_existing_mnfx_names = {spec.mnfx_name for spec in VERIFIED_PARAMETERS.values()}
_CORPUS_EXACT_KEYS: set[str] = set()
for _mnfx_name, (_offset, _encoding, _distinct) in CORPUS_EXACT_PARAMETERS.items():
    if _mnfx_name in _existing_mnfx_names:
        continue
    _key = f"mnfx.{_mnfx_name}"
    _minimum = -1.0 if _encoding == "normalized_bipolar_s16" else 0.0
    VERIFIED_PARAMETERS[_key] = VerifiedParameter(
        _mnfx_name,
        _offset,
        None,
        _minimum,
        1.0,
        _mnfx_name,
        _encoding,
        _distinct,
    )
    _CORPUS_EXACT_KEYS.add(_key)

# These offsets are independently supported by the matched .mnfx/device corpus,
# but two hardware batches (arbitrary sentinels and known-valid corpus values)
# showed that the corresponding live parameter-message IDs do not write them.
# Keep them available for full-payload decoding without exposing them as live
# session writes.
CORPUS_ONLY_PARAMETER_KEYS = frozenset({
    "arpeggiator.mode",
    "arpeggiator.octaves",
    "fx1.option1",
    "fx1.option2",
    "fx1.option3",
    "fx1.param1",
    "fx1.param2",
    "fx1.param3",
    "fx2.option1",
    "fx2.param1",
    "fx2.param2",
    "fx2.param3",
    "fx3.option1",
    "fx3.param1",
    "fx3.param2",
    "fx3.param3",
    "keyboard.chord_length",
    "keyboard.chord_offset_0",
    "keyboard.octave",
    "keyboard.source",
    "modulation.wheel",
    "sequencer.automation_set_0",
    "sequencer.automation_set_1",
    "sequencer.automation_set_2",
    "sequencer.gate",
    "sequencer.length",
    "sequencer.time_division",
}) | frozenset(_CORPUS_EXACT_KEYS)

LIVE_SESSION_PARAMETERS = {
    key: spec
    for key, spec in VERIFIED_PARAMETERS.items()
    if key not in CORPUS_ONLY_PARAMETER_KEYS
}


def payload_checksum(payload: bytes) -> int:
    """Return byte 4: the complement of the XOR of all other bytes."""
    if len(payload) != MINIFREAK_HARDWARE_PRESET_SIZE:
        raise CollageError(
            f"MiniFreak hardware preset must be {MINIFREAK_HARDWARE_PRESET_SIZE} bytes"
        )
    return 0xFF ^ reduce(
        xor,
        payload[:MINIFREAK_CHECKSUM_OFFSET]
        + payload[MINIFREAK_CHECKSUM_OFFSET + 1 :],
        0,
    )


def checksum_is_valid(payload: bytes) -> bool:
    return payload_checksum(payload) == payload[MINIFREAK_CHECKSUM_OFFSET]


def with_updated_checksum(payload: bytes) -> bytes:
    result = bytearray(payload)
    result[MINIFREAK_CHECKSUM_OFFSET] = payload_checksum(payload)
    return bytes(result)


def decode_verified_parameters(payload: bytes) -> dict[str, dict[str, object]]:
    if not checksum_is_valid(payload):
        raise CollageError("MiniFreak hardware preset checksum is invalid")
    decoded: dict[str, dict[str, object]] = {}
    for key, spec in VERIFIED_PARAMETERS.items():
        raw = int.from_bytes(payload[spec.offset : spec.offset + 2], "little", signed=True)
        decoded[key] = {
            "status": (
                "corpus_48_exact" if key in _CORPUS_EXACT_KEYS else "verified"
            ),
            "value_type": "normalized_float",
            "value": raw / 32767.0,
            "name": spec.name,
            "raw_value": raw,
            "byte_offset": spec.offset,
            "session_parameter_id": spec.session_parameter_id,
            "live_session_write": key in LIVE_SESSION_PARAMETERS,
            "encoding": "signed-16-le / 32767",
            "mnfx_name": spec.mnfx_name,
            "mnfx_encoding": spec.mnfx_encoding,
            "corpus_presets": 48 if spec.corpus_distinct_values is not None else None,
            "corpus_distinct_values": spec.corpus_distinct_values,
        }
    return decoded


def set_verified_parameter(payload: bytes, key: str, value: float) -> bytes:
    try:
        spec = VERIFIED_PARAMETERS[key]
    except KeyError as exc:
        raise CollageError(
            f"unsupported MiniFreak hardware parameter {key!r}; verified: "
            + ", ".join(VERIFIED_PARAMETERS)
        ) from exc
    if not spec.minimum <= value <= spec.maximum:
        raise CollageError(
            f"{key} must be between {spec.minimum:g} and {spec.maximum:g}"
        )
    if not checksum_is_valid(payload):
        raise CollageError("MiniFreak hardware preset checksum is invalid")
    result = bytearray(payload)
    raw = round(value * 32767.0)
    result[spec.offset : spec.offset + 2] = raw.to_bytes(2, "little", signed=True)
    return with_updated_checksum(bytes(result))


def update_document_parameter(document, key: str, value: float):
    """Update one verified MiniFreak field in a shared JSON document."""
    from minifreak_patch.schema import MiniFreakHardwareParameter

    if document.minifreak is None or document.minifreak.hardware is None:
        raise CollageError("MiniFreak hardware JSON with raw payload is required")
    hardware = document.minifreak.hardware
    payload = base64.b64decode(hardware.raw_payload_base64)
    updated = set_verified_parameter(payload, key, value)
    hardware.raw_payload_base64 = base64.b64encode(updated).decode("ascii")
    hardware.transport_parameters = {
        name: MiniFreakHardwareParameter.model_validate(parameter)
        for name, parameter in decode_verified_parameters(updated).items()
    }
    return document
