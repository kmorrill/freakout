"""Firmware-5 MicroFreak sequence blocks with conservative semantics.

Across all five observed tagged preset layouts, Sequence A and Sequence B are
fixed 64 x 16-byte blocks in the 4,088-byte unpacked payload. The first four
bytes of each record are MIDI note slots. Factory payloads use either 0xfb or
0xff for empty, depending on their serialization variant. The remaining bytes
are exposed losslessly. Corpus evidence identifies bytes 8..11 as four 8-bit
automation values and byte 13 as their presence mask; byte 12 and the final
two bytes remain conservatively raw.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from minifreak_patch.microfreak_midi import pack_8bit_midi, unpack_8bit_midi


SEQUENCE_LAYOUT = "microfreak-fw5-two-patterns-64x16/1"
SEQUENCE_EVIDENCE = "fixed_offsets_observed_across_five_fw5_tagged_layouts"
SEQUENCE_STEP_COUNT = 64
SEQUENCE_STEP_SIZE = 16
SEQUENCE_OFFSETS = {"A": 1980, "B": 3022}
SEQUENCE_TRAILER_SIZE = 18
SEQUENCE_AUTOMATION_DESTINATION_EVIDENCE = (
    "hardware_playback_cc_plus_operation41_motivseq_and_320_preset_corpus"
)
# Every non-FFFF word in the connected 320-preset corpus was one of these
# already mapped operation-41 addresses. MotivSeq then proved that its first
# three words select the destinations of automation lanes 1..3 over USB MIDI.
SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES = frozenset(
    (
        0x0000,
        0x0001,
        0x0003,
        0x0005,
        0x0101,
        0x0102,
        0x0201,
        0x0203,
        0x0204,
        0x0206,
        0x0300,
        0x0501,
        0x0502,
        0x0601,
        0x0602,
        0x0603,
        0x0D01,
    )
)
KNOWN_EMPTY_NOTE_BYTES = frozenset((0xFB, 0xFF))
NON_NOTE_TOKEN_MIN = 0x80
SEQUENCE_NOTE_STATUS_BY_CODE = {0: "rest", 1: "trigger", 2: "tie"}
SEQUENCE_NOTE_CODE_BY_STATUS = {
    status: code for code, status in SEQUENCE_NOTE_STATUS_BY_CODE.items()
}
SEQUENCE_NOTE_STATUS_EVIDENCE = (
    "official_manual_status_domain_plus_hardware_midi_clock_boundary_correlation"
)


def _preferred_non_note_byte(unpacked: bytes | bytearray, offset: int) -> int:
    counts: dict[int, int] = {}
    for step in range(SEQUENCE_STEP_COUNT):
        for voice in range(4):
            value = unpacked[offset + step * SEQUENCE_STEP_SIZE + voice]
            if value >= NON_NOTE_TOKEN_MIN:
                counts[value] = counts.get(value, 0) + 1
    return max(sorted(counts), key=counts.get) if counts else 0xFF


@dataclass(frozen=True)
class MicroFreakSequenceStep:
    notes: tuple[int | None, int | None, int | None, int | None]
    note_bytes: tuple[int, int, int, int]
    velocities: tuple[int, int, int, int]
    automation_values: tuple[int, int, int, int]
    automation_mask: int
    note_event_code: int
    note_status: str | None
    reserved_bytes: tuple[int, int]
    unclassified_bytes: tuple[int, ...]
    unpacked_offset: int


@dataclass(frozen=True)
class MicroFreakSequencePattern:
    name: str
    unpacked_offset: int
    steps: tuple[MicroFreakSequenceStep, ...]
    automation_destination_addresses: tuple[
        int | None, int | None, int | None, int | None
    ]
    trailer_bytes: tuple[int, ...]


def parse_sequence_patterns(payload: bytes) -> dict[str, MicroFreakSequencePattern]:
    if len(payload) != 4672 or any(value > 0x7F for value in payload):
        return {}
    unpacked = unpack_8bit_midi(payload)
    patterns: dict[str, MicroFreakSequencePattern] = {}
    for name, pattern_offset in SEQUENCE_OFFSETS.items():
        steps = []
        for index in range(SEQUENCE_STEP_COUNT):
            offset = pattern_offset + index * SEQUENCE_STEP_SIZE
            raw = unpacked[offset : offset + SEQUENCE_STEP_SIZE]
            if len(raw) != SEQUENCE_STEP_SIZE:
                return {}
            if any(value > 127 for value in raw[4:8]):
                return {}
            notes = tuple(None if value >= NON_NOTE_TOKEN_MIN else value for value in raw[:4])
            steps.append(
                MicroFreakSequenceStep(
                    notes=notes,  # type: ignore[arg-type]
                    note_bytes=tuple(raw[:4]),  # type: ignore[arg-type]
                    velocities=tuple(raw[4:8]),  # type: ignore[arg-type]
                    automation_values=tuple(raw[8:12]),  # type: ignore[arg-type]
                    note_event_code=raw[12],
                    note_status=SEQUENCE_NOTE_STATUS_BY_CODE.get(raw[12]),
                    automation_mask=raw[13],
                    reserved_bytes=tuple(raw[14:16]),  # type: ignore[arg-type]
                    unclassified_bytes=tuple(raw[8:]),
                    unpacked_offset=offset,
                )
            )
        patterns[name] = MicroFreakSequencePattern(
            name=name,
            unpacked_offset=pattern_offset,
            steps=tuple(steps),
            automation_destination_addresses=tuple(
                None if word == 0xFFFF else word
                for word in (
                    int.from_bytes(
                        unpacked[
                            pattern_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE + lane * 2:
                            pattern_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE + lane * 2 + 2
                        ],
                        "little",
                    )
                    for lane in range(4)
                )
            ),  # type: ignore[arg-type]
            trailer_bytes=tuple(
                unpacked[
                    pattern_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE:
                    pattern_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE
                    + SEQUENCE_TRAILER_SIZE
                ]
            ),
        )
    return patterns


def apply_sequence_patterns(payload: bytes, sequence_data) -> bytes:
    """Apply a validated schema projection while retaining all other bytes."""

    if sequence_data.layout != SEQUENCE_LAYOUT:
        raise ValueError(f"unsupported MicroFreak sequence layout {sequence_data.layout!r}")
    unpacked = bytearray(unpack_8bit_midi(payload))
    supplied = {"A": sequence_data.pattern_a, "B": sequence_data.pattern_b}
    for name, pattern in supplied.items():
        expected_offset = SEQUENCE_OFFSETS[name]
        non_note_byte = _preferred_non_note_byte(unpacked, expected_offset)
        if pattern.unpacked_offset != expected_offset:
            raise ValueError(
                f"MicroFreak Sequence {name} offset must be {expected_offset}"
            )
        if len(pattern.steps) != SEQUENCE_STEP_COUNT:
            raise ValueError(f"MicroFreak Sequence {name} must have 64 steps")
        for index, step in enumerate(pattern.steps):
            if len(step.notes) != 4:
                raise ValueError("each MicroFreak sequence step must contain four notes")
            offset = expected_offset + index * SEQUENCE_STEP_SIZE
            existing = unpacked[offset : offset + 4]
            projected_note_bytes = getattr(step, "note_bytes", None)
            note_bytes = bytes(
                note
                if note is not None
                else projected_note_bytes[voice]
                if projected_note_bytes is not None
                and projected_note_bytes[voice] >= NON_NOTE_TOKEN_MIN
                else current
                if current >= NON_NOTE_TOKEN_MIN
                else non_note_byte
                for voice, (note, current) in enumerate(zip(step.notes, existing))
            )
            velocities = getattr(step, "velocities", None)
            remainder = bytes(step.unclassified_bytes)
            if velocities is None and len(remainder) == 12:
                # Backward-compatible input from the first sequence JSON
                # projection, where velocities were part of the unknown tail.
                velocity_bytes = remainder[:4]
                remainder = remainder[4:]
            elif velocities is not None and len(velocities) == 4 and len(remainder) in (8, 12):
                velocity_bytes = bytes(velocities)
                if len(remainder) == 12:
                    remainder = remainder[4:]
            else:
                raise ValueError(
                    "each MicroFreak sequence step needs four velocities and "
                    "eight unclassified bytes"
                )
            automation_values = getattr(step, "automation_values", None)
            note_event_code = getattr(step, "note_event_code", None)
            note_status = getattr(step, "note_status", None)
            automation_mask = getattr(step, "automation_mask", None)
            reserved_bytes = getattr(step, "reserved_bytes", None)
            if automation_values is not None:
                remainder = bytes(automation_values) + remainder[4:]
            if note_status is not None:
                try:
                    note_event_code = SEQUENCE_NOTE_CODE_BY_STATUS[note_status]
                except KeyError as exc:
                    raise ValueError(
                        "MicroFreak sequence note status must be rest, trigger, or tie"
                    ) from exc
            if note_event_code is not None:
                remainder = remainder[:4] + bytes((note_event_code,)) + remainder[5:]
            if automation_mask is not None:
                remainder = remainder[:5] + bytes((automation_mask,)) + remainder[6:]
            if reserved_bytes is not None:
                remainder = remainder[:6] + bytes(reserved_bytes)
            raw = note_bytes + velocity_bytes + remainder
            unpacked[offset : offset + SEQUENCE_STEP_SIZE] = raw
        trailer_offset = expected_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE
        trailer_bytes = getattr(pattern, "trailer_bytes", None)
        if trailer_bytes is not None:
            if len(trailer_bytes) != SEQUENCE_TRAILER_SIZE or any(
                not 0 <= value <= 255 for value in trailer_bytes
            ):
                raise ValueError(
                    f"MicroFreak Sequence {name} trailer must contain "
                    f"{SEQUENCE_TRAILER_SIZE} bytes"
                )
            unpacked[
                trailer_offset : trailer_offset + SEQUENCE_TRAILER_SIZE
            ] = bytes(trailer_bytes)
        destinations = getattr(pattern, "automation_destinations", None)
        if destinations is not None:
            if len(destinations) != 4:
                raise ValueError(
                    f"MicroFreak Sequence {name} needs four automation destinations"
                )
            for lane, destination in enumerate(destinations, start=1):
                if destination.lane != lane:
                    raise ValueError(
                        f"MicroFreak Sequence {name} automation destination "
                        f"lane order must be 1..4"
                    )
                address = destination.live_address
                if (
                    address is not None
                    and address not in SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES
                ):
                    raise ValueError(
                        f"MicroFreak sequence automation destination 0x{address:04x} "
                        "was not observed in the hardware preset corpus"
                    )
                if address is not None and destination.parameter is not None:
                    from minifreak_patch.microfreak_midi import (
                        MICROFREAK_LIVE_WORD_SEMANTICS,
                    )

                    expected_parameter = MICROFREAK_LIVE_WORD_SEMANTICS[address][
                        "parameter"
                    ]
                    if destination.parameter != expected_parameter:
                        raise ValueError(
                            f"MicroFreak sequence destination 0x{address:04x} is "
                            f"{expected_parameter}, not {destination.parameter}"
                        )
                unpacked[
                    trailer_offset + (lane - 1) * 2:
                    trailer_offset + lane * 2
                ] = (0xFFFF if address is None else address).to_bytes(2, "little")
    return pack_8bit_midi(bytes(unpacked))


def set_sequence_automation_destination(
    payload: bytes,
    pattern: str,
    lane: int,
    live_address: int | None,
) -> bytes:
    """Set one corpus- and playback-supported sequence lane destination."""

    pattern = pattern.upper()
    if pattern not in SEQUENCE_OFFSETS:
        raise ValueError("MicroFreak sequence pattern must be A or B")
    if not 1 <= lane <= 4:
        raise ValueError("MicroFreak sequence automation lane must be 1..4")
    if (
        live_address is not None
        and live_address not in SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES
    ):
        raise ValueError(
            "MicroFreak sequence automation destination must be a "
            "hardware-observed operation-41 address or null"
        )
    unpacked = bytearray(unpack_8bit_midi(payload))
    offset = (
        SEQUENCE_OFFSETS[pattern]
        + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE
        + (lane - 1) * 2
    )
    unpacked[offset : offset + 2] = (
        0xFFFF if live_address is None else live_address
    ).to_bytes(2, "little")
    return pack_8bit_midi(bytes(unpacked))


def set_sequence_note(
    payload: bytes,
    pattern: str,
    step: int,
    voice: int,
    note: int | None,
) -> bytes:
    pattern = pattern.upper()
    if pattern not in SEQUENCE_OFFSETS:
        raise ValueError("MicroFreak sequence pattern must be A or B")
    if not 1 <= step <= SEQUENCE_STEP_COUNT:
        raise ValueError("MicroFreak sequence step must be 1..64")
    if not 1 <= voice <= 4:
        raise ValueError("MicroFreak sequence voice must be 1..4")
    if note is not None and not 0 <= note <= 127:
        raise ValueError("MicroFreak sequence note must be 0..127 or null")
    unpacked = bytearray(unpack_8bit_midi(payload))
    pattern_offset = SEQUENCE_OFFSETS[pattern]
    offset = pattern_offset + (step - 1) * SEQUENCE_STEP_SIZE + voice - 1
    unpacked[offset] = (
        _preferred_non_note_byte(unpacked, pattern_offset) if note is None else note
    )
    return pack_8bit_midi(bytes(unpacked))


def set_sequence_velocity(
    payload: bytes,
    pattern: str,
    step: int,
    voice: int,
    velocity: int,
) -> bytes:
    pattern = pattern.upper()
    if pattern not in SEQUENCE_OFFSETS:
        raise ValueError("MicroFreak sequence pattern must be A or B")
    if not 1 <= step <= SEQUENCE_STEP_COUNT:
        raise ValueError("MicroFreak sequence step must be 1..64")
    if not 1 <= voice <= 4:
        raise ValueError("MicroFreak sequence voice must be 1..4")
    if not 0 <= velocity <= 127:
        raise ValueError("MicroFreak sequence velocity must be 0..127")
    unpacked = bytearray(unpack_8bit_midi(payload))
    offset = SEQUENCE_OFFSETS[pattern] + (step - 1) * SEQUENCE_STEP_SIZE + 4 + voice - 1
    unpacked[offset] = velocity
    return pack_8bit_midi(bytes(unpacked))


def set_sequence_automation(
    payload: bytes,
    pattern: str,
    step: int,
    lane: int,
    value: int | None,
) -> bytes:
    """Set or clear one corpus-supported 8-bit sequence automation lane."""
    pattern = pattern.upper()
    if pattern not in SEQUENCE_OFFSETS:
        raise ValueError("MicroFreak sequence pattern must be A or B")
    if not 1 <= step <= SEQUENCE_STEP_COUNT:
        raise ValueError("MicroFreak sequence step must be 1..64")
    if not 1 <= lane <= 4:
        raise ValueError("MicroFreak sequence automation lane must be 1..4")
    if value is not None and not 0 <= value <= 255:
        raise ValueError("MicroFreak sequence automation value must be 0..255 or null")
    unpacked = bytearray(unpack_8bit_midi(payload))
    base = SEQUENCE_OFFSETS[pattern] + (step - 1) * SEQUENCE_STEP_SIZE
    bit = 1 << (lane - 1)
    if value is None:
        unpacked[base + 8 + lane - 1] = 0
        unpacked[base + 13] &= ~bit
    else:
        unpacked[base + 8 + lane - 1] = value
        unpacked[base + 13] |= bit
    return pack_8bit_midi(bytes(unpacked))


def set_sequence_note_status(
    payload: bytes,
    pattern: str,
    step: int,
    status: str,
) -> bytes:
    """Set one hardware-correlated rest, trigger, or tie status byte."""

    pattern = pattern.upper()
    if pattern not in SEQUENCE_OFFSETS:
        raise ValueError("MicroFreak sequence pattern must be A or B")
    if not 1 <= step <= SEQUENCE_STEP_COUNT:
        raise ValueError("MicroFreak sequence step must be 1..64")
    normalized = status.lower()
    try:
        code = SEQUENCE_NOTE_CODE_BY_STATUS[normalized]
    except KeyError as exc:
        raise ValueError(
            "MicroFreak sequence note status must be rest, trigger, or tie"
        ) from exc
    unpacked = bytearray(unpack_8bit_midi(payload))
    offset = SEQUENCE_OFFSETS[pattern] + (step - 1) * SEQUENCE_STEP_SIZE + 12
    unpacked[offset] = code
    return pack_8bit_midi(bytes(unpacked))


def analyze_sequence_payloads(payloads: Iterable[bytes]) -> dict[str, object]:
    """Summarize the fixed step record across a lossless preset corpus."""
    records: list[bytes] = []
    trailers: list[bytes] = []
    payload_count = 0
    note_tokens: dict[str, int] = {}
    for payload in payloads:
        if len(payload) != 4672 or any(value > 0x7F for value in payload):
            continue
        payload_count += 1
        unpacked = unpack_8bit_midi(payload)
        for pattern_offset in SEQUENCE_OFFSETS.values():
            for step in range(SEQUENCE_STEP_COUNT):
                offset = pattern_offset + step * SEQUENCE_STEP_SIZE
                record = unpacked[offset : offset + SEQUENCE_STEP_SIZE]
                records.append(record)
                for value in record[:4]:
                    key = f"0x{value:02x}"
                    if value >= NON_NOTE_TOKEN_MIN:
                        note_tokens[key] = note_tokens.get(key, 0) + 1
            trailer_offset = pattern_offset + SEQUENCE_STEP_COUNT * SEQUENCE_STEP_SIZE
            trailers.append(
                unpacked[trailer_offset : trailer_offset + SEQUENCE_TRAILER_SIZE]
            )

    byte_domains = []
    for offset in range(SEQUENCE_STEP_SIZE):
        values = sorted({record[offset] for record in records})
        byte_domains.append(
            {
                "offset": offset,
                "distinct_values": len(values),
                "minimum": min(values) if values else None,
                "maximum": max(values) if values else None,
                "always_zero": values == [0],
            }
        )

    lanes = []
    for lane, offset in enumerate(range(8, 12), start=1):
        values = [record[offset] for record in records]
        bit = 1 << (lane - 1)
        distinct = sorted(set(values))
        lanes.append(
            {
                "lane": lane,
                "record_offset": offset,
                "encoding_candidate": "u8_value_with_presence_mask",
                "presence_mask_offset": 13,
                "presence_mask_bit": lane - 1,
                "distinct_values": len(distinct),
                "minimum": min(distinct) if distinct else None,
                "maximum": max(distinct) if distinct else None,
                "nonzero_records": sum(value != 0 for value in values),
                "present_records": sum(bool(record[13] & bit) for record in records),
                "present_zero_records": sum(
                    bool(record[13] & bit) and record[offset] == 0
                    for record in records
                ),
                "nonzero_without_presence_records": sum(
                    not (record[13] & bit) and record[offset] != 0
                    for record in records
                ),
            }
        )

    velocity_values = [value for record in records for value in record[4:8]]
    destination_counts: dict[str, int] = {}
    destination_by_lane: list[dict[str, int]] = [dict() for _ in range(4)]
    for trailer in trailers:
        for lane in range(4):
            word = int.from_bytes(trailer[lane * 2 : lane * 2 + 2], "little")
            key = "unused" if word == 0xFFFF else f"{word:04x}"
            destination_counts[key] = destination_counts.get(key, 0) + 1
            lane_counts = destination_by_lane[lane]
            lane_counts[key] = lane_counts.get(key, 0) + 1
    trailer_byte_domains = [
        {
            "offset": offset,
            "distinct_values": sorted({trailer[offset] for trailer in trailers}),
        }
        for offset in range(SEQUENCE_TRAILER_SIZE)
    ]
    return {
        "layout": SEQUENCE_LAYOUT,
        "fixed_size_payloads": payload_count,
        "payloads_with_note_projection": payload_count,
        "step_records": len(records),
        "non_note_token_counts": dict(sorted(note_tokens.items())),
        "byte_domains": byte_domains,
        "candidate_fields": {
            "notes": {
                "record_offsets": [0, 1, 2, 3],
                "evidence": "midi_note_domain_and_four_voice_alignment",
            },
            "velocities": {
                "record_offsets": [4, 5, 6, 7],
                "encoding_candidate": "four_u7_values",
                "all_values_midi_7bit": all(value <= 127 for value in velocity_values),
                "evidence": "four_voice_alignment_and_velocity_domain",
            },
            "automation_lanes": lanes,
            "note_event_code": {
                "record_offset": 12,
                "distinct_values": sorted({record[12] for record in records}),
                "semantic_status": "hardware_midi_output_verified",
                "code_meanings": SEQUENCE_NOTE_STATUS_BY_CODE,
                "evidence": SEQUENCE_NOTE_STATUS_EVIDENCE,
            },
            "automation_presence_mask": {
                "record_offset": 13,
                "minimum": min((record[13] for record in records), default=None),
                "maximum": max((record[13] for record in records), default=None),
                "evidence": "four_bit_alignment_with_bytes_8_through_11",
            },
            "automation_destinations": {
                "trailer_byte_offsets": list(range(8)),
                "encoding": "four_little_endian_operation41_addresses_ffff_unused",
                "counts": dict(sorted(destination_counts.items())),
                "counts_by_lane": [
                    dict(sorted(counts.items())) for counts in destination_by_lane
                ],
                "observed_supported_addresses": [
                    f"{address:04x}"
                    for address in sorted(SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES)
                ],
                "evidence": SEQUENCE_AUTOMATION_DESTINATION_EVIDENCE,
            },
            "pattern_trailer": {
                "size": SEQUENCE_TRAILER_SIZE,
                "byte_domains": trailer_byte_domains,
                "remaining_raw_offsets": list(range(8, SEQUENCE_TRAILER_SIZE)),
            },
            "reserved_bytes": {
                "record_offsets": [14, 15],
                "nonzero_records": sum(
                    record[14] != 0 or record[15] != 0 for record in records
                ),
            },
        },
    }
