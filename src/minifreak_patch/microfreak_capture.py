"""Read-only analysis of passive MicroFreak CoreMIDI capture logs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from minifreak_patch.microfreak_midi import MicroFreakSysex, decode_sysex


@dataclass(frozen=True)
class CapturedMicroFreakMessage:
    direction: str
    message: MicroFreakSysex


def parse_capture_lines(lines: Iterable[str]) -> list[CapturedMicroFreakMessage]:
    """Decode MicroFreak messages while ignoring identity and unrelated MIDI."""
    decoded: list[CapturedMicroFreakMessage] = []
    for line in lines:
        fields = line.split(maxsplit=1)
        marker = " data="
        if len(fields) != 2 or fields[0] not in {"in", "out"} or marker not in line:
            continue
        try:
            message = decode_sysex(bytes.fromhex(line.split(marker, 1)[1]))
        except (ValueError, RuntimeError):
            continue
        decoded.append(CapturedMicroFreakMessage(fields[0], message))
    return decoded


def summarize_capture(
    messages: Iterable[CapturedMicroFreakMessage],
) -> dict[str, object]:
    """Return transport-family counts and the current-buffer evidence boundary."""
    captured = list(messages)
    operation_counts = Counter(
        (entry.direction, entry.message.operation) for entry in captured
    )

    def count(direction: str, operation: int, predicate=lambda payload: True) -> int:
        return sum(
            entry.direction == direction
            and entry.message.operation == operation
            and predicate(entry.message.payload)
            for entry in captured
        )

    preset_header_queries = count(
        "out", 0x19, lambda payload: len(payload) == 3 and payload[2] == 0
    )
    preset_body_starts = count(
        "out", 0x19, lambda payload: len(payload) == 3 and payload[2] == 1
    )
    wavetable_header_starts = count("out", 0x57)
    wavetable_part_starts = count("out", 0x55)
    sample_starts = count("out", 0x5B)
    inventory_cycles = (
        preset_header_queries // 512
        if preset_header_queries
        and preset_header_queries % 512 == 0
        and wavetable_header_starts == preset_header_queries // 32
        and wavetable_part_starts == preset_header_queries // 8
        and sample_starts == preset_header_queries // 4
        else 0
    )
    summary = {
        "microfreak_messages": len(captured),
        "operation_counts": {
            f"{direction}:0x{operation:02x}": operation_counts[(direction, operation)]
            for direction, operation in sorted(operation_counts)
        },
        "global_queries": count("out", 0x43),
        "preset_header_queries": preset_header_queries,
        "preset_header_replies": count(
            "in", 0x52, lambda payload: len(payload) == 35
        ),
        "preset_body_starts": preset_body_starts,
        "wavetable_header_starts": wavetable_header_starts,
        "wavetable_part_starts": wavetable_part_starts,
        "sample_starts": sample_starts,
        "continuation_requests": count("out", 0x18),
        "data_start_replies": count("in", 0x15),
        "data_part_replies": count("in", 0x16),
        "data_final_replies": count("in", 0x17),
        # This conclusion is deliberately narrow: it describes only what is
        # visible in the supplied capture, not every command the firmware may
        # implement.
        "observed_current_buffer_request": False,
        "complete_startup_inventory_cycles": inventory_cycles,
        "startup_inventory_shape": "full" if inventory_cycles else "other",
    }
    return summary
