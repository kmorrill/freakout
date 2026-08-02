"""Parse the self-describing named prefix of a MicroFreak preset payload.

Preset transfers contain 8-to-7-bit MIDI packing. After unpacking, firmware 5
stores groups as ``@#XYZ`` and fields as ``(0x40 + name length), name, 'c',
metadata, uint16-le``. The remaining sequence body is intentionally preserved
but not interpreted here.
"""

from __future__ import annotations

from dataclasses import dataclass

from minifreak_patch.microfreak import MICROFREAK_PRESET_PAYLOAD_SIZE
from minifreak_patch.microfreak_live_map import MICROFREAK_STRUCTURED_LIVE_WORDS
from minifreak_patch.microfreak_midi import pack_8bit_midi, unpack_8bit_midi


STRUCTURED_FIELD_STATUS = "firmware_tagged_payload_observed_fw5"
STRUCTURED_UI_ACTION_PLACEHOLDER_CANDIDATES = frozenset(
    {
        "Mat.MatBtn",
        "Mat.MatEnc",
        "Sys.PrsetBt",
        "Sys.PrsetID",
        "Sys.Save",
        "Sys.Utility",
    }
)
STRUCTURED_LEGACY_PANEL_STATE_CANDIDATES = frozenset({"Gen.Panel"})
STRUCTURED_ROLE_EVIDENCE = (
    "all_320_saved_values_zero_no_operation41_mapping_name_and_group_semantics"
)

MICROFREAK_DESTINATION_LABELS: dict[int, str] = {0x0000: "VCO.Type"}
for _destination_name, _destination_addresses in (
    MICROFREAK_STRUCTURED_LIVE_WORDS.items()
):
    for _destination_address in _destination_addresses:
        MICROFREAK_DESTINATION_LABELS.setdefault(
            _destination_address, _destination_name
        )


def structured_field_role(key: str) -> tuple[str, str | None]:
    if key in STRUCTURED_UI_ACTION_PLACEHOLDER_CANDIDATES:
        return "ui_action_placeholder_candidate", STRUCTURED_ROLE_EVIDENCE
    if key in STRUCTURED_LEGACY_PANEL_STATE_CANDIDATES:
        return "legacy_panel_state_candidate", STRUCTURED_ROLE_EVIDENCE
    return "patch_parameter", None


@dataclass(frozen=True)
class MicroFreakStructuredField:
    key: str
    group: str
    name: str
    metadata: int
    raw_u16: int
    raw_s16: int
    unpacked_metadata_offset: int
    unpacked_value_offset: int
    packed_metadata_offsets: tuple[int, ...]
    packed_byte_offsets: tuple[int, ...]


@dataclass(frozen=True)
class MicroFreakStructuredValue:
    value: float | int
    kind: str
    minimum: float | int
    maximum: float | int
    label: str | None = None


_BIPOLAR_GROUPS = {f"Co{index}" for index in range(1, 8)}
_BIPOLAR_NAMES = {"EG1", "EG2", "LFO", "Xpr", "Key"}
_NORMALIZED_TAGS = {
    "VCO.Param1", "VCO.Param2", "VCO.Param3",
    "VCF.Cutoff", "VCF.Reso",
    "EG1.RiseLvl", "EG1.RiseSlp", "EG1.FallLvl", "EG1.Hold",
    "EG1.FallSlp", "EG1.Amount", "Kbd.Glide",
    "Arp.Rate", "Arp.Spice", "Arp.Dice", "LFO.Rate",
    "EG2.Attack", "EG2.DecRel", "EG2.Sustain",
    "Gen.Volume", "Gen.UniSprd",
}
_METADATA_INTEGER_OFFSETS = {
    # Hardware playback plus the complete saved corpus establish the UI
    # domains: metadata stores the span, while the pattern trailer mirrors the
    # displayed value with these minimum offsets.
    "Seq.Length": 4,
    "Seq.GateLen": 10,
}


def _packed_offset(unpacked_offset: int) -> int:
    block, index = divmod(unpacked_offset, 7)
    return block * 8 + 1 + index


def _packed_offsets(unpacked_offsets: tuple[int, ...]) -> tuple[int, ...]:
    offsets: set[int] = set()
    for unpacked_offset in unpacked_offsets:
        block = unpacked_offset // 7
        offsets.add(block * 8)  # high-bit bitmap for this seven-byte block
        offsets.add(_packed_offset(unpacked_offset))
    return tuple(sorted(offsets))


def parse_structured_fields(payload: bytes) -> dict[str, MicroFreakStructuredField]:
    if len(payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
        return {}
    unpacked = unpack_8bit_midi(payload)
    fields: dict[str, MicroFreakStructuredField] = {}
    position = 0
    group: str | None = None

    while position < len(unpacked):
        if position == 0 and unpacked[position] == 0x23:
            group_bytes = unpacked[position + 1 : position + 4]
            position += 4
        elif unpacked[position : position + 2] == b"@#":
            group_bytes = unpacked[position + 2 : position + 5]
            position += 5
        else:
            group_bytes = b""
        if group_bytes:
            if len(group_bytes) != 3 or not all(0x20 <= item < 0x7F for item in group_bytes):
                break
            group = group_bytes.decode("ascii")
            continue

        name_length = unpacked[position] - 0x40
        end = position + 1 + name_length
        if not group or not 1 <= name_length <= 31 or end + 4 > len(unpacked):
            break
        name_bytes = unpacked[position + 1 : end]
        if unpacked[end] != 0x63 or not all(0x20 <= item < 0x7F for item in name_bytes):
            break
        name = name_bytes.decode("ascii")
        metadata = unpacked[end + 1]
        metadata_offset = end + 1
        value_offset = end + 2
        raw_u16 = int.from_bytes(unpacked[value_offset : value_offset + 2], "little")
        raw_s16 = raw_u16 if raw_u16 < 0x8000 else raw_u16 - 0x10000
        key = f"{group}.{name}"
        if key in fields:
            raise ValueError(f"duplicate MicroFreak structured field {key}")
        fields[key] = MicroFreakStructuredField(
            key=key,
            group=group,
            name=name,
            metadata=metadata,
            raw_u16=raw_u16,
            raw_s16=raw_s16,
            unpacked_metadata_offset=metadata_offset,
            unpacked_value_offset=value_offset,
            packed_metadata_offsets=_packed_offsets((metadata_offset,)),
            packed_byte_offsets=_packed_offsets((value_offset, value_offset + 1)),
        )
        position = value_offset + 2
    return fields


def interpret_structured_field(
    field: MicroFreakStructuredField,
) -> MicroFreakStructuredValue:
    """Interpret only ranges established by tags and per-preset metadata."""
    if field.group in _BIPOLAR_GROUPS and field.name in _BIPOLAR_NAMES:
        value = max(-1.0, min(1.0, field.raw_s16 / 32767.0))
        return MicroFreakStructuredValue(value, "bipolar_normalized", -1.0, 1.0)
    if field.metadata == 0xF7 and field.raw_u16 <= 0x7FFF:
        value = (field.raw_u16 - 0x4000) >> 7
        return MicroFreakStructuredValue(
            value, "signed_offset_shift7", -128, 127
        )
    if field.key in {"Mat.Assign1", "Mat.Assign2", "Mat.Assign3"}:
        label = MICROFREAK_DESTINATION_LABELS.get(field.raw_u16)
        if label is not None:
            return MicroFreakStructuredValue(
                field.raw_u16,
                "live_destination_id",
                0,
                0x170F,
                label,
            )
    if 1 <= field.metadata <= 127:
        offset = _METADATA_INTEGER_OFFSETS.get(field.key, 0)
        value = round(field.raw_u16 * field.metadata / 32767.0) + offset
        return MicroFreakStructuredValue(
            value,
            "metadata_scaled_offset_integer"
            if offset
            else "metadata_scaled_integer",
            offset,
            field.metadata + offset,
        )
    if field.key in _NORMALIZED_TAGS:
        value = max(0.0, min(1.0, field.raw_u16 / 32767.0))
        return MicroFreakStructuredValue(value, "unsigned_normalized", 0.0, 1.0)
    return MicroFreakStructuredValue(field.raw_u16, "raw_u16", 0, 65535)


def set_structured_raw_u16(payload: bytes, key: str, raw_u16: int) -> bytes:
    if isinstance(raw_u16, bool) or not isinstance(raw_u16, int):
        raise ValueError("MicroFreak structured raw value must be an integer")
    if not 0 <= raw_u16 <= 0xFFFF:
        raise ValueError("MicroFreak structured raw value must be 0..65535")
    fields = parse_structured_fields(payload)
    try:
        field = fields[key]
    except KeyError as exc:
        raise ValueError(f"unknown MicroFreak structured field {key!r}") from exc
    unpacked = bytearray(unpack_8bit_midi(payload))
    unpacked[field.unpacked_value_offset : field.unpacked_value_offset + 2] = (
        raw_u16.to_bytes(2, "little")
    )
    return pack_8bit_midi(bytes(unpacked))


def set_structured_value(payload: bytes, key: str, value: float | int) -> bytes:
    fields = parse_structured_fields(payload)
    try:
        field = fields[key]
    except KeyError as exc:
        raise ValueError(f"unknown MicroFreak structured field {key!r}") from exc
    role, _ = structured_field_role(key)
    if role != "patch_parameter":
        raise ValueError(
            f"{key} is classified as {role}, not a proven patch parameter; "
            "use the explicit raw research editor only if that distinction is intended"
        )
    interpreted = interpret_structured_field(field)
    if interpreted.kind in {
        "metadata_scaled_integer",
        "metadata_scaled_offset_integer",
    }:
        if isinstance(value, bool) or int(value) != value:
            raise ValueError(f"{key} requires an integer")
        integer = int(value)
        if not int(interpreted.minimum) <= integer <= int(interpreted.maximum):
            raise ValueError(
                f"{key} must be {int(interpreted.minimum)}..{int(interpreted.maximum)}"
            )
        offset = int(interpreted.minimum)
        raw = round((integer - offset) * 32767 / field.metadata)
    elif interpreted.kind == "signed_offset_shift7":
        if isinstance(value, bool) or int(value) != value:
            raise ValueError(f"{key} requires an integer")
        integer = int(value)
        if not -128 <= integer <= 127:
            raise ValueError(f"{key} must be -128..127")
        raw = 0x4000 + (integer << 7)
    elif interpreted.kind == "live_destination_id":
        if isinstance(value, bool) or int(value) != value:
            raise ValueError(f"{key} requires an integer destination ID")
        raw = int(value)
        if raw not in MICROFREAK_DESTINATION_LABELS:
            raise ValueError(
                f"{key} destination 0x{raw:04x} is not a mapped live parameter"
            )
    elif interpreted.kind == "unsigned_normalized":
        numeric = float(value)
        if not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{key} must be normalized from 0.0 to 1.0")
        raw = round(numeric * 32767)
    elif interpreted.kind == "bipolar_normalized":
        numeric = float(value)
        if not -1.0 <= numeric <= 1.0:
            raise ValueError(f"{key} must be normalized from -1.0 to 1.0")
        raw = round(numeric * 32767) & 0xFFFF
    else:
        raise ValueError(
            f"{key} has raw-only semantics; use set-microfreak-structured-json"
        )
    changed = set_structured_raw_u16(payload, key, raw)
    if key in {"Seq.Length", "Seq.GateLen"}:
        from minifreak_patch.microfreak_sequence import (
            SEQUENCE_OFFSETS,
            SEQUENCE_STEP_COUNT,
            SEQUENCE_STEP_SIZE,
        )

        trailer_byte = 9 if key == "Seq.Length" else 8
        unpacked = bytearray(unpack_8bit_midi(changed))
        for pattern_offset in SEQUENCE_OFFSETS.values():
            unpacked[
                pattern_offset
                + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE
                + trailer_byte
            ] = integer
        changed = pack_8bit_midi(bytes(unpacked))
    return changed
