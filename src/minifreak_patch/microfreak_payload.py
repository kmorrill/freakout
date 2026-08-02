"""Evidence-labelled named fields in the 4,672-byte MicroFreak payload.

These locations were published by the archived MicroFreak Reader and are
unchanged between its FW1 and FW2 tables. They are useful and exactly
reversible, but remain ``published_stable_layout_observed_fw5`` until a
controlled hardware sound/UI probe verifies each semantic label on current
firmware. Fields whose published locations shifted between FW1 and FW2 are
deliberately excluded from editing and handled by the sentinel probe.
"""

from __future__ import annotations

from dataclasses import dataclass

from minifreak_patch.microfreak import MICROFREAK_PRESET_PAYLOAD_SIZE


EVIDENCE_STATUS = "published_stable_layout_observed_fw5"
HARDWARE_RAW_RW_STATUS = "hardware_raw_rw_fw5_semantics_unconfirmed"
HARDWARE_RAW_RW_KEYS = {"filter.cutoff"}
OSCILLATOR_TYPE_HARDWARE_STATUS = (
    "hardware_saved_live_320_preset_exact_correlation_fw5"
)


@dataclass(frozen=True)
class MicroFreakParameterSpec:
    key: str
    value_type: str
    msb_offset: int | None
    lsb_offset: int
    flag_offset: int | None = None
    flag_mask: int | None = None
    encoding: str = "unsigned_15bit_normalized"


@dataclass(frozen=True)
class DecodedMicroFreakParameter:
    value: float | int
    raw_value: int
    status: str
    spec: MicroFreakParameterSpec
    byte_offsets: tuple[int, ...] | None = None
    evidence_encoding: str | None = None


def _offset(row: int, column: int) -> int:
    return row * 32 + column


def _continuous(
    key: str,
    msb: tuple[int, int],
    lsb: tuple[int, int],
    flag: tuple[int, int],
    mask: int,
) -> MicroFreakParameterSpec:
    return MicroFreakParameterSpec(
        key=key,
        value_type="normalized_float",
        msb_offset=_offset(*msb),
        lsb_offset=_offset(*lsb),
        flag_offset=_offset(*flag),
        flag_mask=mask,
    )


# Clean-room transcription of public row/column protocol facts that are stable
# in both published layouts. Shifted arp, LFO, and envelope entries and the
# internally inconsistent arp-swing entry are intentionally omitted pending a
# current-firmware saved-sentinel comparison.
MICROFREAK_PARAMETER_SPECS = {
    spec.key: spec
    for spec in (
        MicroFreakParameterSpec(
            "osc.type",
            "integer",
            None,
            _offset(0, 14),
            encoding="firmware_tagged_metadata_scaled_integer",
        ),
        _continuous("osc.wave", (0, 27), (0, 26), (0, 24), 0x02),
        _continuous("osc.timbre", (1, 7), (1, 6), (1, 0), 0x20),
        _continuous("osc.shape", (1, 20), (1, 19), (1, 16), 0x04),
        _continuous("filter.cutoff", (2, 30), (2, 29), (2, 24), 0x10),
        _continuous("filter.resonance", (3, 9), (3, 7), (3, 0), 0x40),
        _continuous("cycling_env.rise", (4, 6), (4, 5), (4, 0), 0x10),
        _continuous("cycling_env.rise_shape", (4, 20), (4, 19), (4, 16), 0x04),
        _continuous("cycling_env.fall", (5, 2), (5, 1), (5, 0), 0x01),
        _continuous("cycling_env.hold", (5, 12), (5, 11), (5, 8), 0x04),
        _continuous("cycling_env.fall_shape", (5, 26), (5, 25), (5, 24), 0x01),
        _continuous("cycling_env.amount", (6, 6), (6, 5), (6, 0), 0x10),
        _continuous("glide", (6, 23), (6, 22), (6, 16), 0x20),
    )
}


def _require_full_payload(payload: bytes) -> None:
    if len(payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
        raise ValueError("named MicroFreak parameters require a full preset payload")


def decode_microfreak_parameters(
    payload: bytes,
) -> dict[str, DecodedMicroFreakParameter]:
    _require_full_payload(payload)
    result = {}
    for key, spec in MICROFREAK_PARAMETER_SPECS.items():
        byte_offsets = None
        evidence_encoding = None
        status = HARDWARE_RAW_RW_STATUS if key in HARDWARE_RAW_RW_KEYS else EVIDENCE_STATUS
        if spec.encoding == "firmware_tagged_metadata_scaled_integer":
            # Firmware 5 carries the authoritative engine selection in the
            # self-describing VCO.Type field. Its metadata is the maximum
            # engine index supported when that preset was written, so the raw
            # uint16 must be interpreted against the per-preset metadata.
            from minifreak_patch.microfreak_structured import (
                interpret_structured_field,
                parse_structured_fields,
            )

            field = parse_structured_fields(payload).get("VCO.Type")
            if field is not None:
                interpreted = interpret_structured_field(field)
                raw = field.raw_u16
                value = int(interpreted.value)
                byte_offsets = tuple(
                    sorted(
                        set(
                            field.packed_metadata_offsets
                            + field.packed_byte_offsets
                        )
                    )
                )
                evidence_encoding = "VCO.Type_metadata_scaled_integer"
                status = OSCILLATOR_TYPE_HARDWARE_STATUS
            else:
                # Retain read compatibility with older/non-tagged fixtures;
                # this byte is only a legacy encoded control position and is
                # not safe for firmware-5 engine editing.
                raw = payload[spec.lsb_offset] & 0x7F
                value = raw
                evidence_encoding = "legacy_unsigned_7bit_fallback"
        elif spec.encoding == "unsigned_7bit":
            raw = payload[spec.lsb_offset] & 0x7F
            value: float | int = raw
        else:
            assert spec.msb_offset is not None
            assert spec.flag_offset is not None and spec.flag_mask is not None
            shift = (spec.flag_mask & -spec.flag_mask).bit_length() - 1
            low_bit = (payload[spec.flag_offset] & spec.flag_mask) >> shift
            raw = (
                ((payload[spec.msb_offset] & 0x7F) << 8)
                | (low_bit << 7)
                | (payload[spec.lsb_offset] & 0x7F)
            )
            value = raw / 32767.0
        result[key] = DecodedMicroFreakParameter(
            value=value,
            raw_value=raw,
            status=status,
            spec=spec,
            byte_offsets=byte_offsets,
            evidence_encoding=evidence_encoding,
        )
    return result


def set_microfreak_parameter(
    payload: bytes, key: str, value: float | int
) -> bytes:
    _require_full_payload(payload)
    try:
        spec = MICROFREAK_PARAMETER_SPECS[key]
    except KeyError as exc:
        raise ValueError(f"unsupported MicroFreak parameter {key!r}") from exc
    updated = bytearray(payload)
    if spec.encoding == "firmware_tagged_metadata_scaled_integer":
        if isinstance(value, bool) or int(value) != value:
            raise ValueError(f"{key} must be an integer engine index")
        from minifreak_patch.microfreak_structured import (
            parse_structured_fields,
            set_structured_value,
        )

        target = int(value)
        field = parse_structured_fields(payload).get("VCO.Type")
        if field is None:
            raise ValueError("osc.type requires firmware-tagged VCO.Type")
        if target > field.metadata:
            raise ValueError(
                f"osc.type {target} requires a preset layout supporting at least "
                f"{target} engines; this preset's VCO.Type layout supports "
                f"0..{field.metadata}. Use a firmware-5 preset as the base; "
                "automatic layout migration is not hardware-proven."
            )
        return set_structured_value(payload, "VCO.Type", target)
    if spec.encoding == "unsigned_7bit":
        if isinstance(value, bool) or int(value) != value or not 0 <= int(value) <= 127:
            raise ValueError(f"{key} must be an integer from 0 to 127")
        updated[spec.lsb_offset] = int(value)
    else:
        numeric = float(value)
        if not 0.0 <= numeric <= 1.0:
            raise ValueError(f"{key} must be normalized from 0.0 to 1.0")
        raw = round(numeric * 32767)
        assert spec.msb_offset is not None
        assert spec.flag_offset is not None and spec.flag_mask is not None
        updated[spec.msb_offset] = (raw >> 8) & 0x7F
        updated[spec.lsb_offset] = raw & 0x7F
        shift = (spec.flag_mask & -spec.flag_mask).bit_length() - 1
        updated[spec.flag_offset] = (
            updated[spec.flag_offset] & ~spec.flag_mask
        ) | (((raw >> 7) & 1) << shift)
    return bytes(updated)
