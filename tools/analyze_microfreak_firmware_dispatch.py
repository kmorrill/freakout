#!/usr/bin/env python3
"""Locate likely MicroFreak SysEx dispatch code in an official .mff image.

This is a static, read-only research helper.  It extracts the main Cortex-M
image in memory, disassembles Thumb instructions, and finds compact regions
that compare against several already observed MIDI Control Center operation
bytes.  Nearby immediate comparisons are reported as candidate operations;
they are evidence for focused review, not automatically promoted protocol
facts.

MicroFreak 5 firmware is not one flat ``file offset = VMA - base`` image.
Known executable routines have been observed in overlapping stored views, in
particular at the direct offset, ``+0x8000``, and ``+0x14000``.  Use repeated
``--file-shift`` arguments to analyze those views independently.  The tool
never merges instructions or candidate regions across views.

Capstone is intentionally a research-only dependency::

    python3 -m pip install capstone
    python3 tools/analyze_microfreak_firmware_dispatch.py firmware.mff
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from collections import deque


DEFAULT_KNOWN_OPERATIONS = (0x15, 0x16, 0x17, 0x18, 0x19, 0x52, 0x54, 0x56)
DEFAULT_BYTE_ANCHORS = {
    "arturia_microfreak_prefix": bytes.fromhex("00 20 6b 07"),
}
FW5_MAIN_SHA256 = "bfffd66e89bda4ca9b6e36bdc832703c177b82bed7015a1cf7dcb7e5f1493c14"
BULK_DISPATCH_FIRST_OPERATION = 0x15
BULK_DISPATCH_LAST_OPERATION = 0x5D
BULK_DISPATCH_TABLE_ADDRESS = 0x0805ED20
BULK_DISPATCH_DEFAULT_TARGET = 0x0805EE60
BULK_OPERATION_ROLES = {
    0x15: "transfer_start_or_flow_control",
    0x16: "data_packet",
    0x17: "final_data_packet",
    0x18: "ack_or_next_packet_request",
    0x19: "saved_preset_read_start",
    0x52: "preset_header_reply_or_write_start",
    0x54: "wavetable_part_write_start",
    0x55: "wavetable_part_read_start",
    0x56: "wavetable_header_write_or_reset",
    0x57: "wavetable_header_read",
    0x58: "sample_body_write_block",
    0x59: "sample_body_read_block",
    0x5A: "sample_header_write_or_reset",
    0x5B: "sample_header_read_or_object_select",
    0x5C: "sample_slot_swap",
    0x5D: "sample_upload_allocation_or_preflight",
}
CONTROL_DISPATCH_FIRST_OPERATION = 0x1C
CONTROL_DISPATCH_LAST_OPERATION = 0x53
CONTROL_DISPATCH_TABLE_ADDRESS = 0x0805AFA0
CONTROL_DISPATCH_DEFAULT_TARGET = 0x0805B060
CONTROL_INCOMING_HANDLER_ADDRESS = 0x08046F74
CONTROL_OPERATION_ROLES = {
    0x1C: "device_control_session_enable",
    0x1D: "device_control_session_disable",
    0x40: "live_grouped_u16_write_or_reply",
    0x41: "live_grouped_u16_read",
    0x42: "global_setting_write",
    0x43: "global_setting_read",
    0x47: "sample_storage_statistics_read",
    0x49: "maintenance_subcommand",
    0x4C: "two_byte_runtime_control_candidate",
    0x53: "bounded_debug_console_command_input",
}
MAINTENANCE_SUBCOMMAND_TABLE_ADDRESS = 0x0805B0F8
MAINTENANCE_SUBCOMMAND_COUNT = 10
MAINTENANCE_TARGET_STORED_VIEW_FILE_SHIFT = 0x14000
MAINTENANCE_MINIMUM_OPERATION_PAYLOAD_BYTES = 2
MAINTENANCE_SUBCOMMAND_BYTE_OFFSET = 0
MAINTENANCE_VALUE_BYTE_OFFSET = 1
OP49_STATE_RECORD_FLAG_BITS = (0x40, 0x20, 0x10, 0x08, 0x04, 0x02)
OP49_STATE_RECORD_ROUTES = {
    0x00: "enqueue_internal_route_0",
    0x01: "enqueue_internal_route_1",
    0x02: "enqueue_internal_route_2",
    0x7D: "invoke_control_handler",
    0x7F: "invoke_control_handler_and_enqueue",
}
OP49_STATE_RECORD_KIND_ROLES = {
    0x00: "indexed_control_update_candidate",
    0x02: "live_synth_parameter_update_hardware_verified",
    0x07: "global_bit_enable",
    0x08: "global_bit_clear_all",
    0x09: "global_bit_set_all",
    0x0A: "matrix_or_routing_update_candidate",
    0x13: "six_byte_status_reply_request",
    0x18: "runtime_action_candidate",
    0x1E: "three_state_runtime_mode",
}
MAINTENANCE_SUBCOMMAND_METADATA = {
    0: {
        "role": "hidden_global_selector_2_enable_and_runtime_event_candidate",
        "evidence_status": "static_structure_confirmed_external_meaning_candidate",
        "payload_shape": "subcommand_u8_reserved_u8",
        "runtime_event_object_ram_address": 0x200035A4,
        "runtime_event_helper_address": 0x0803B21C,
    },
    1: {
        "role": "hidden_global_selector_2_disable_candidate",
        "evidence_status": "static_structure_confirmed_external_meaning_candidate",
        "payload_shape": "subcommand_u8_reserved_u8",
    },
    2: {
        "role": "hidden_global_selector_0x13_write",
        "evidence_status": "static_control_flow_and_read_target_confirmed_external_meaning_unknown",
        "payload_shape": "subcommand_u8_value_u8",
        "value_payload_byte_offset": MAINTENANCE_VALUE_BYTE_OFFSET,
    },
    3: {
        "role": "hidden_global_selector_0x14_write",
        "evidence_status": "static_control_flow_and_read_target_confirmed_external_meaning_unknown",
        "payload_shape": "subcommand_u8_value_u8",
        "value_payload_byte_offset": MAINTENANCE_VALUE_BYTE_OFFSET,
    },
    4: {
        "role": "no_op_unimplemented",
        "evidence_status": "static_control_flow_confirmed",
        "payload_shape": "subcommand_u8_reserved_u8",
    },
    5: {
        "role": "no_op_unimplemented",
        "evidence_status": "static_control_flow_confirmed",
        "payload_shape": "subcommand_u8_reserved_u8",
    },
    6: {
        "role": "packed_six_byte_state_record_apply",
        "evidence_status": "static_payload_and_control_flow_confirmed_semantics_unknown",
        "payload_shape": "subcommand_u8_scope_u8_then_flag_packed_six_bytes",
        "minimum_operation_payload_bytes": 9,
        "record_routes": OP49_STATE_RECORD_ROUTES,
        "record_layout": {
            "byte_0": "source_high_nibble_and_header_low_nibble",
            "byte_1": "dispatch_kind",
            "bytes_2_3": "kind_specific_big_endian_address_for_kinds_0_and_2",
            "bytes_4_5": "kind_specific_big_endian_value_for_kinds_0_and_2",
        },
        "record_kind_roles": OP49_STATE_RECORD_KIND_ROLES,
    },
    7: {
        "role": "diagnostic_bitmask_read",
        "evidence_status": "static_reply_shape_confirmed_bit_meanings_partial",
        "payload_shape": "subcommand_u8_reserved_u8",
        "reply": "operation_48_seven_byte_diagnostic_record",
    },
    8: {
        "role": "active_parameter_runtime_pointer_rebind_and_reinitialize",
        "evidence_status": "static_mutation_and_source_object_confirmed_external_trigger_meaning_candidate",
        "payload_shape": "subcommand_u8_reserved_u8",
        "source_active_parameter_object_ram_address": 0x2001C898,
        "final_helper_calls": [0x0802C928, 0x0803DF60],
        "active_sequence_object_direct_reference": False,
        "resolved_call_graph_reaches_active_sequence_accessor": False,
    },
    9: {
        "role": "sample_memory_defragment",
        "evidence_status": "public_flow_correlated_and_static_control_flow_confirmed",
        "payload_shape": "09_7f_00_in_public_implementation",
    },
}
STORAGE_STATISTIC_SELECTOR_ROLES = {
    0x0A: "allocated_sample_space",
    0x0B: "trailing_contiguous_space_candidate",
    0x0C: "fragmentation_or_reclaimable_pages_candidate",
}
DEBUG_COMMAND_TABLE_ADDRESS = 0x08073CD8
DEBUG_COMMAND_TABLE_COUNT = 14
DEBUG_COMMAND_STORED_VIEW_FILE_SHIFT = 0x14000
DEBUG_COMMAND_HANDLER_ADDRESS = 0x0805B072
DEBUG_COMMAND_MAX_BYTES = 43
RUNTIME_CONTROL_TABLE_ADDRESS = 0x08073D64
RUNTIME_CONTROL_TABLE_COUNT = 4
RUNTIME_CONTROL_HANDLER_ADDRESS = 0x0805B12E
RUNTIME_CONTROL_BOOLEAN_THRESHOLD = 0x40
# The local Ghidra project loads the header-stripped main image at its linked
# 0x08020000 base.  Raw offsets below are therefore ``address - 0x08020000``;
# offsets in the packaged member are 0x40 bytes larger because of its header.
PRESET_SERIALIZER_LINKED_ADDRESS = 0x08068A68
PRESET_SERIALIZER_RAW_FILE_OFFSET = 0x48A68
PRESET_SLOT_WRITER_LINKED_ADDRESS = 0x08059238
PRESET_SLOT_WRITER_RAW_FILE_OFFSET = 0x39238
PRESET_SLOT_READER_LINKED_ADDRESS = 0x080594D4
PRESET_SLOT_READER_RAW_FILE_OFFSET = 0x394D4
PRESET_TAGGED_PARSER_LINKED_ADDRESS = 0x08068E08
PRESET_TAGGED_PARSER_RAW_FILE_OFFSET = 0x48E08
PRESET_SEQUENCE_SERIALIZER_LINKED_ADDRESS = 0x0803C4BC
PRESET_SEQUENCE_SERIALIZER_RAW_FILE_OFFSET = 0x1C4BC
PRESET_FLASH_SLOT_BASE = 0x81
PRESET_FLASH_SLOT_BYTES = 0x1000
PRESET_SEQUENCE_BYTES = 0x824
PRESET_SERIALIZER_CALLERS_LINKED = (0x0805053C, 0x08052644)
PRESET_SERIALIZER_CALLERS_RAW_FILE_OFFSETS = (0x3053C, 0x32644)
ACTIVE_SEQUENCE_OBJECT_RAM_ADDRESS = 0x20000EEC
ACTIVE_SEQUENCE_POINTER_LITERAL_OCCURRENCES = 20
ACTIVE_SEQUENCE_DIRECT_KNOWN_SYSEX_HANDLER_REFERENCES = 0
OPERATION_19_REACHABLE_FUNCTION_COUNT = 16
ACTIVE_SEQUENCE_ACCESSOR_FUNCTIONS = (
    0x080275D8,
    0x0803879C,
    0x0804FD4C,
    0x08050C4C,
    0x08051F60,
    0x0805247C,
    0x08065270,
    0x08066090,
    0x0806628C,
    0x08068830,
    0x08068A68,
    0x08069644,
)
IMMEDIATE_RE = re.compile(r"#(?:0x([0-9a-fA-F]+)|(\d+))")


@dataclass(frozen=True)
class Instruction:
    address: int
    file_offset: int
    mnemonic: str
    operands: str
    immediate: int | None


@dataclass(frozen=True)
class Candidate:
    file_shift: int
    start_address: int
    end_address: int
    known_operations: list[int]
    nearby_immediates: list[int]
    instructions: list[Instruction]


@dataclass(frozen=True)
class LiteralReference:
    address: int
    file_offset: int
    mnemonic: str
    operands: str


@dataclass(frozen=True)
class AnchorObservation:
    name: str
    bytes_hex: str
    file_offset: int
    linked_address: int
    literal_references: list[LiteralReference]


@dataclass(frozen=True)
class BulkDispatchEntry:
    operation: int
    target_address: int
    implemented: bool


@dataclass(frozen=True)
class FunctionPointerEntry:
    index: int
    pointer: int
    target_address: int
    thumb: bool


@dataclass(frozen=True)
class DebugCommandEntry:
    index: int
    name_pointer: int
    name: str


def decode_flag_packed_six_byte_record(payload: bytes) -> bytes:
    """Decode operation-49/6's flag byte plus six MIDI-clean record bytes."""

    if len(payload) != 7 or any(value > 0x7F for value in payload):
        raise ValueError("packed six-byte record must be seven 7-bit bytes")
    flags = payload[0]
    return bytes(
        value | (0x80 if flags & bit else 0)
        for bit, value in zip(OP49_STATE_RECORD_FLAG_BITS, payload[1:])
    )


def describe_six_byte_state_record(record: bytes) -> dict[str, int | str]:
    """Describe the statically confirmed common fields of one internal record."""

    if len(record) != 6:
        raise ValueError("internal state record must contain exactly six bytes")
    return {
        "raw_hex": record.hex(),
        "source_nibble": record[0] >> 4,
        "header_nibble": record[0] & 0x0F,
        "kind": record[1],
        "kind_role": OP49_STATE_RECORD_KIND_ROLES.get(record[1], "unknown"),
        "address_be": int.from_bytes(record[2:4], "big"),
        "value_be": int.from_bytes(record[4:6], "big"),
    }


def decode_thumb_tbh_table(
    image: bytes,
    *,
    table_address: int,
    first_operation: int,
    last_operation: int,
    default_target: int,
    base: int,
    header_size: int,
    file_shift: int = 0,
) -> list[BulkDispatchEntry]:
    """Decode a Thumb ``TBH [pc, index, LSL #1]`` operation table.

    A TBH entry is an unsigned halfword offset measured in halfwords from the
    aligned PC value.  At the firmware-5 dispatcher the aligned PC is also the
    first byte of the table.
    """

    if last_operation < first_operation:
        raise ValueError("last operation must not precede first operation")
    table_offset = file_offset_for_address(
        table_address,
        base=base,
        header_size=header_size,
        file_shift=file_shift,
    )
    count = last_operation - first_operation + 1
    end = table_offset + count * 2
    if table_offset < 0 or end > len(image):
        raise ValueError("TBH dispatch table falls outside the selected firmware view")
    entries = []
    for index in range(count):
        halfword_offset = struct.unpack_from("<H", image, table_offset + index * 2)[0]
        target = table_address + halfword_offset * 2
        entries.append(
            BulkDispatchEntry(
                operation=first_operation + index,
                target_address=target,
                implemented=target != default_target,
            )
        )
    return entries


def decode_fw5_bulk_dispatch(
    image: bytes, *, base: int = 0x08020000, header_size: int = 0x40
) -> list[BulkDispatchEntry]:
    """Decode the version-pinned firmware-5 bulk object-transfer dispatcher."""

    digest = hashlib.sha256(image).hexdigest()
    if digest != FW5_MAIN_SHA256:
        raise ValueError(
            "bulk dispatcher addresses are pinned to MicroFreak FW5 main image "
            f"{FW5_MAIN_SHA256}; received {digest}"
        )
    return decode_thumb_tbh_table(
        image,
        table_address=BULK_DISPATCH_TABLE_ADDRESS,
        first_operation=BULK_DISPATCH_FIRST_OPERATION,
        last_operation=BULK_DISPATCH_LAST_OPERATION,
        default_target=BULK_DISPATCH_DEFAULT_TARGET,
        base=base,
        header_size=header_size,
    )


def decode_fw5_control_dispatch(
    image: bytes, *, base: int = 0x08020000, header_size: int = 0x40
) -> list[BulkDispatchEntry]:
    """Decode the firmware-5 global/storage/device-control dispatcher."""

    digest = hashlib.sha256(image).hexdigest()
    if digest != FW5_MAIN_SHA256:
        raise ValueError(
            "control dispatcher addresses are pinned to MicroFreak FW5 main image "
            f"{FW5_MAIN_SHA256}; received {digest}"
        )
    return decode_thumb_tbh_table(
        image,
        table_address=CONTROL_DISPATCH_TABLE_ADDRESS,
        first_operation=CONTROL_DISPATCH_FIRST_OPERATION,
        last_operation=CONTROL_DISPATCH_LAST_OPERATION,
        default_target=CONTROL_DISPATCH_DEFAULT_TARGET,
        base=base,
        header_size=header_size,
    )


def decode_function_pointer_table(
    image: bytes,
    *,
    table_address: int,
    count: int,
    base: int,
    header_size: int,
    file_shift: int = 0,
) -> list[FunctionPointerEntry]:
    """Decode a little-endian table of absolute ARM/Thumb function pointers."""

    if count < 0:
        raise ValueError("function pointer count must not be negative")
    table_offset = file_offset_for_address(
        table_address,
        base=base,
        header_size=header_size,
        file_shift=file_shift,
    )
    end = table_offset + count * 4
    if table_offset < 0 or end > len(image):
        raise ValueError("function pointer table falls outside the selected firmware view")
    entries = []
    for index in range(count):
        pointer = struct.unpack_from("<I", image, table_offset + index * 4)[0]
        entries.append(
            FunctionPointerEntry(
                index=index,
                pointer=pointer,
                target_address=pointer & ~1,
                thumb=bool(pointer & 1),
            )
        )
    return entries


def decode_fw5_maintenance_subcommands(
    image: bytes, *, base: int = 0x08020000, header_size: int = 0x40
) -> list[FunctionPointerEntry]:
    """Decode operation-49's ten-entry maintenance subcommand table."""

    digest = hashlib.sha256(image).hexdigest()
    if digest != FW5_MAIN_SHA256:
        raise ValueError(
            "maintenance table addresses are pinned to MicroFreak FW5 main image "
            f"{FW5_MAIN_SHA256}; received {digest}"
        )
    return decode_function_pointer_table(
        image,
        table_address=MAINTENANCE_SUBCOMMAND_TABLE_ADDRESS,
        count=MAINTENANCE_SUBCOMMAND_COUNT,
        base=base,
        header_size=header_size,
    )


def decode_debug_command_table(
    image: bytes,
    *,
    table_address: int,
    count: int,
    base: int,
    header_size: int,
    file_shift: int,
) -> list[DebugCommandEntry]:
    """Decode operation-53's pointer/index debug-command records."""

    table_offset = file_offset_for_address(
        table_address,
        base=base,
        header_size=header_size,
        file_shift=file_shift,
    )
    if table_offset < 0 or table_offset + count * 8 > len(image):
        raise ValueError("debug command table falls outside the selected firmware view")
    entries = []
    for index in range(count):
        name_pointer, command_index = struct.unpack_from(
            "<Ii", image, table_offset + index * 8
        )
        if command_index != index:
            raise ValueError(
                f"debug command record {index} has unexpected index {command_index}"
            )
        name_offset = file_offset_for_address(
            name_pointer,
            base=base,
            header_size=header_size,
            file_shift=file_shift,
        )
        if not 0 <= name_offset < len(image):
            raise ValueError(f"debug command {index} name falls outside firmware")
        terminator = image.find(b"\x00", name_offset, min(len(image), name_offset + 64))
        if terminator < 0:
            raise ValueError(f"debug command {index} name is not terminated")
        try:
            name = image[name_offset:terminator].decode("ascii")
        except UnicodeDecodeError as exc:
            raise ValueError(f"debug command {index} name is not ASCII") from exc
        entries.append(
            DebugCommandEntry(index=index, name_pointer=name_pointer, name=name)
        )
    return entries


def decode_fw5_debug_commands(
    image: bytes, *, base: int = 0x08020000, header_size: int = 0x40
) -> list[DebugCommandEntry]:
    """Decode the pinned firmware-5 operation-53 debug command table."""

    digest = hashlib.sha256(image).hexdigest()
    if digest != FW5_MAIN_SHA256:
        raise ValueError(
            "debug command table addresses are pinned to MicroFreak FW5 main "
            f"image {FW5_MAIN_SHA256}; received {digest}"
        )
    return decode_debug_command_table(
        image,
        table_address=DEBUG_COMMAND_TABLE_ADDRESS,
        count=DEBUG_COMMAND_TABLE_COUNT,
        base=base,
        header_size=header_size,
        file_shift=DEBUG_COMMAND_STORED_VIEW_FILE_SHIFT,
    )


def decode_fw5_runtime_controls(
    image: bytes, *, base: int = 0x08020000, header_size: int = 0x40
) -> list[DebugCommandEntry]:
    """Decode operation-4C's four sync runtime-control selectors."""

    digest = hashlib.sha256(image).hexdigest()
    if digest != FW5_MAIN_SHA256:
        raise ValueError(
            "runtime control table addresses are pinned to MicroFreak FW5 main "
            f"image {FW5_MAIN_SHA256}; received {digest}"
        )
    return decode_debug_command_table(
        image,
        table_address=RUNTIME_CONTROL_TABLE_ADDRESS,
        count=RUNTIME_CONTROL_TABLE_COUNT,
        base=base,
        header_size=header_size,
        file_shift=DEBUG_COMMAND_STORED_VIEW_FILE_SHIFT,
    )


def parse_int(value: str) -> int:
    return int(value, 0)


def read_main_image(path: Path) -> tuple[str, bytes]:
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name.startswith("nanowave_main") and name.endswith(".bin")
        ]
        if len(names) != 1:
            raise ValueError(f"expected one nanowave_main image, found {names!r}")
        return names[0], archive.read(names[0])


def first_immediate(operands: str) -> int | None:
    match = IMMEDIATE_RE.search(operands)
    if not match:
        return None
    return int(match.group(1), 16) if match.group(1) else int(match.group(2), 10)


def file_offset_for_address(
    address: int, *, base: int, header_size: int, file_shift: int
) -> int:
    """Map one linked address into one explicitly selected stored view."""

    return header_size + address - base + file_shift


def find_byte_offsets(image: bytes, needle: bytes) -> list[int]:
    if not needle:
        raise ValueError("byte anchor must not be empty")
    offsets: list[int] = []
    start = 0
    while True:
        offset = image.find(needle, start)
        if offset < 0:
            return offsets
        offsets.append(offset)
        start = offset + 1


def find_thumb_literal_references(
    image: bytes,
    *,
    target_addresses: set[int],
    base: int,
    header_size: int,
    file_shift: int,
) -> dict[int, list[LiteralReference]]:
    """Find exact PC-relative literal loads in one stored code view.

    This deliberately scans every halfword because an anchor can belong to a
    callback that is not reachable from the package's vector table.  Results
    remain static candidates until the surrounding routine matches behavior.
    """

    try:
        from capstone import CS_ARCH_ARM, CS_MODE_LITTLE_ENDIAN, CS_MODE_THUMB, Cs
        from capstone.arm import ARM_OP_MEM, ARM_REG_PC
    except ImportError as error:  # pragma: no cover - environment guidance
        raise RuntimeError("install the research dependency with: pip install capstone") from error

    references: dict[int, list[LiteralReference]] = {
        address: [] for address in target_addresses
    }
    if not target_addresses:
        return references

    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)
    disassembler.detail = True
    for file_offset in range(header_size, len(image) - 3, 2):
        address = base + file_offset - header_size - file_shift
        item = next(
            disassembler.disasm(
                image[file_offset : file_offset + 4], address, count=1
            ),
            None,
        )
        if item is None or not item.mnemonic.startswith("ldr"):
            continue
        for operand in item.operands:
            if operand.type != ARM_OP_MEM or operand.mem.base != ARM_REG_PC:
                continue
            literal_address = ((address + 4) & ~3) + operand.mem.disp
            if literal_address in references:
                references[literal_address].append(
                    LiteralReference(
                        address=address,
                        file_offset=file_offset,
                        mnemonic=item.mnemonic,
                        operands=item.op_str,
                    )
                )
    return references


def scan_byte_anchors(
    image: bytes,
    *,
    anchors: dict[str, bytes],
    base: int,
    header_size: int,
    file_shift: int,
) -> list[AnchorObservation]:
    pending: list[tuple[str, bytes, int, int]] = []
    for name, needle in anchors.items():
        for file_offset in find_byte_offsets(image, needle):
            linked_address = base + file_offset - header_size - file_shift
            pending.append((name, needle, file_offset, linked_address))

    references = find_thumb_literal_references(
        image,
        target_addresses={item[3] for item in pending},
        base=base,
        header_size=header_size,
        file_shift=file_shift,
    )
    return [
        AnchorObservation(
            name=name,
            bytes_hex=needle.hex(),
            file_offset=file_offset,
            linked_address=linked_address,
            literal_references=references[linked_address],
        )
        for name, needle, file_offset, linked_address in pending
    ]


def disassemble_reachable(
    image: bytes, *, base: int, header_size: int, file_shift: int = 0
) -> list[Instruction]:
    try:
        from capstone import CS_ARCH_ARM, CS_MODE_LITTLE_ENDIAN, CS_MODE_THUMB, Cs
    except ImportError as error:  # pragma: no cover - environment guidance
        raise RuntimeError("install the research dependency with: pip install capstone") from error

    if len(image) <= header_size + 8:
        raise ValueError("firmware image is too short")

    disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB | CS_MODE_LITTLE_ENDIAN)

    def in_image(address: int) -> bool:
        offset = file_offset_for_address(
            address,
            base=base,
            header_size=header_size,
            file_shift=file_shift,
        )
        return base <= address and header_size <= offset < len(image)

    def decode_one(address: int):
        offset = file_offset_for_address(
            address,
            base=base,
            header_size=header_size,
            file_shift=file_shift,
        )
        if offset < header_size or offset >= len(image):
            return None
        item = next(
            disassembler.disasm(image[offset : offset + 4], address, count=1),
            None,
        )
        return (offset, item) if item is not None else None

    # The image's first word is an initial stack pointer; subsequent vector
    # words are Thumb handler pointers. RTOS tasks and protocol callbacks are
    # also commonly installed through aligned pointer tables, so seed every
    # aligned word that is a valid in-image Thumb address. Random data almost
    # never falls in this narrow flash range, while this reaches code that a
    # direct-call-only traversal misses.
    seeds: set[int] = set()
    for offset in range(header_size + 4, len(image) - 3, 4):
        pointer = struct.unpack_from("<I", image, offset)[0]
        target = pointer & ~1
        if pointer & 1 and in_image(target):
            seeds.add(target)

    queue: deque[int] = deque(sorted(seeds))
    visited: set[int] = set()
    decoded: dict[int, Instruction] = {}

    while queue:
        address = queue.popleft() & ~1
        while in_image(address) and address not in visited:
            decoded_item = decode_one(address)
            if decoded_item is None:
                break
            file_offset, item = decoded_item
            if item.size not in (2, 4):
                break
            visited.add(address)
            comparison = (
                first_immediate(item.op_str) if item.mnemonic.startswith("cmp") else None
            )
            decoded[address] = Instruction(
                address=address,
                file_offset=file_offset,
                mnemonic=item.mnemonic,
                operands=item.op_str,
                immediate=comparison,
            )

            mnemonic = item.mnemonic
            target = first_immediate(item.op_str)
            next_address = address + item.size

            if mnemonic in {"bl", "blx"}:
                if target is not None and in_image(target & ~1):
                    queue.append(target & ~1)
            elif mnemonic in {"cbz", "cbnz"}:
                if target is not None and in_image(target & ~1):
                    queue.append(target & ~1)
            elif (
                mnemonic.startswith("b")
                and mnemonic not in {"bx", "bl", "blx"}
                and item.op_str.startswith("#")
            ):
                if target is not None and in_image(target & ~1):
                    queue.append(target & ~1)
                if mnemonic in {"b", "b.w"}:
                    break

            if (
                mnemonic in {"bx", "tbb", "tbh"}
                or (mnemonic == "pop" and "pc" in item.op_str)
                or (mnemonic in {"ldr", "mov"} and item.op_str.startswith("pc,"))
            ):
                break
            address = next_address

    return [decoded[address] for address in sorted(decoded)]


def find_candidates(
    instructions: list[Instruction],
    *,
    known_operations: set[int],
    span: int,
    minimum_known: int,
    file_shift: int = 0,
) -> list[Candidate]:
    comparisons = [item for item in instructions if item.immediate is not None]
    raw: list[tuple[int, int, set[int], set[int]]] = []
    for start, first in enumerate(comparisons):
        region = [item for item in comparisons[start:] if item.address <= first.address + span]
        immediates = {
            item.immediate
            for item in region
            if item.immediate is not None and 0 <= item.immediate <= 0x7F
        }
        hits = immediates & known_operations
        if len(hits) >= minimum_known:
            raw.append((first.address, first.address + span, hits, immediates))

    # Sliding windows around one dispatcher overlap heavily. Merge them into
    # one review region while retaining every nearby byte-sized comparison.
    merged: list[tuple[int, int, set[int], set[int]]] = []
    for start_address, end_address, hits, immediates in raw:
        if merged and start_address <= merged[-1][1]:
            old_start, old_end, old_hits, old_immediates = merged[-1]
            merged[-1] = (
                old_start,
                max(old_end, end_address),
                old_hits | hits,
                old_immediates | immediates,
            )
        else:
            merged.append(
                (start_address, end_address, set(hits), set(immediates))
            )

    candidates: list[Candidate] = []
    for start_address, end_address, hits, immediates in merged:
        region = [
            item
            for item in instructions
            if start_address <= item.address <= end_address
        ]
        candidates.append(
            Candidate(
                file_shift=file_shift,
                start_address=start_address,
                end_address=end_address,
                known_operations=sorted(hits),
                nearby_immediates=sorted(immediates),
                instructions=region,
            )
        )
    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path)
    parser.add_argument("--base", type=parse_int, default=0x08020000)
    parser.add_argument("--header-size", type=parse_int, default=0x40)
    parser.add_argument(
        "--file-shift",
        type=parse_int,
        action="append",
        dest="file_shifts",
        help=(
            "stored-file displacement from the flat VMA mapping; repeat to "
            "scan independent views (for firmware 5, try 0, 0x8000, and "
            "0x14000)"
        ),
    )
    parser.add_argument(
        "--span",
        type=parse_int,
        default=0x100,
        help="maximum address span for grouping immediate comparisons",
    )
    parser.add_argument("--minimum-known", type=int, default=3)
    parser.add_argument(
        "--known-operation",
        type=parse_int,
        action="append",
        dest="known_operations",
        help="repeat to replace the default known operation set",
    )
    parser.add_argument("--json", action="store_true", dest="json_output")
    parser.add_argument(
        "--no-anchor-scan",
        action="store_true",
        help="skip exact protocol-byte anchor and literal-reference scanning",
    )
    args = parser.parse_args()

    image_name, image = read_main_image(args.firmware)
    known = set(args.known_operations or DEFAULT_KNOWN_OPERATIONS)
    file_shifts = args.file_shifts or [0]
    if len(set(file_shifts)) != len(file_shifts):
        parser.error("--file-shift values must be unique")

    views = []
    for file_shift in file_shifts:
        instructions = disassemble_reachable(
            image,
            base=args.base,
            header_size=args.header_size,
            file_shift=file_shift,
        )
        candidates = find_candidates(
            instructions,
            known_operations=known,
            span=args.span,
            minimum_known=args.minimum_known,
            file_shift=file_shift,
        )
        anchors = (
            []
            if args.no_anchor_scan
            else scan_byte_anchors(
                image,
                anchors=DEFAULT_BYTE_ANCHORS,
                base=args.base,
                header_size=args.header_size,
                file_shift=file_shift,
            )
        )
        views.append(
            {
                "file_shift": file_shift,
                "evidence_status": "static_candidate_unconfirmed",
                "reachable_instruction_count": len(instructions),
                "candidate_count": len(candidates),
                "candidates": [asdict(item) for item in candidates],
                "anchors": [asdict(item) for item in anchors],
            }
        )

    # Only the direct view begins at the package's actual vector table.  A
    # shifted view must not relabel arbitrary bytes as an initial SP/reset pair.
    initial_sp, reset_vector = struct.unpack_from("<II", image, args.header_size)

    metadata = {
        "image": image_name,
        "image_size": len(image),
        "base_address": args.base,
        "header_size": args.header_size,
        "initial_stack_pointer": initial_sp,
        "reset_vector": reset_vector,
        "known_operations": sorted(known),
        "evidence_status": "static_candidate_unconfirmed",
        "views": views,
    }
    if hashlib.sha256(image).hexdigest() == FW5_MAIN_SHA256:
        bulk_dispatch = decode_fw5_bulk_dispatch(
            image, base=args.base, header_size=args.header_size
        )
        metadata["bulk_sysex_dispatch"] = {
            "scope": "bulk_object_transfer_only",
            "evidence_status": "static_control_flow_confirmed",
            "first_operation": BULK_DISPATCH_FIRST_OPERATION,
            "last_operation": BULK_DISPATCH_LAST_OPERATION,
            "table_address": BULK_DISPATCH_TABLE_ADDRESS,
            "default_target": BULK_DISPATCH_DEFAULT_TARGET,
            "implemented_operations": [
                item.operation for item in bulk_dispatch if item.implemented
            ],
            "entries": [
                {**asdict(item), "role": BULK_OPERATION_ROLES.get(item.operation)}
                for item in bulk_dispatch
            ],
        }
        control_dispatch = decode_fw5_control_dispatch(
            image, base=args.base, header_size=args.header_size
        )
        maintenance_subcommands = decode_fw5_maintenance_subcommands(
            image, base=args.base, header_size=args.header_size
        )
        debug_commands = decode_fw5_debug_commands(
            image, base=args.base, header_size=args.header_size
        )
        runtime_controls = decode_fw5_runtime_controls(
            image, base=args.base, header_size=args.header_size
        )
        metadata["control_sysex_dispatch"] = {
            "scope": "global_storage_and_device_control",
            "evidence_status": "static_control_flow_confirmed",
            "first_operation": CONTROL_DISPATCH_FIRST_OPERATION,
            "last_operation": CONTROL_DISPATCH_LAST_OPERATION,
            "table_address": CONTROL_DISPATCH_TABLE_ADDRESS,
            "default_target": CONTROL_DISPATCH_DEFAULT_TARGET,
            "implemented_operations": [
                item.operation for item in control_dispatch if item.implemented
            ],
            "entries": [
                {**asdict(item), "role": CONTROL_OPERATION_ROLES.get(item.operation)}
                for item in control_dispatch
            ],
            "maintenance_operation_49_subcommands": {
                "evidence_status": "static_control_flow_confirmed",
                "incoming_handler_address": CONTROL_INCOMING_HANDLER_ADDRESS,
                "minimum_operation_payload_bytes": (
                    MAINTENANCE_MINIMUM_OPERATION_PAYLOAD_BYTES
                ),
                "subcommand_payload_byte_offset": MAINTENANCE_SUBCOMMAND_BYTE_OFFSET,
                "table_address": MAINTENANCE_SUBCOMMAND_TABLE_ADDRESS,
                "target_code_stored_view_file_shift": (
                    MAINTENANCE_TARGET_STORED_VIEW_FILE_SHIFT
                ),
                "safety": "not_hardware_probed_branches_may_mutate_runtime_or_storage",
                "entries": [
                    {
                        **asdict(item),
                        **MAINTENANCE_SUBCOMMAND_METADATA[item.index],
                    }
                    for item in maintenance_subcommands
                ],
            },
            "storage_statistics_operation_47_selectors": [
                {"selector": selector, "role": role}
                for selector, role in STORAGE_STATISTIC_SELECTOR_ROLES.items()
            ],
            "debug_console_operation_53": {
                "evidence_status": "static_control_flow_confirmed",
                "handler_address": DEBUG_COMMAND_HANDLER_ADDRESS,
                "maximum_input_bytes": DEBUG_COMMAND_MAX_BYTES,
                "table_address": DEBUG_COMMAND_TABLE_ADDRESS,
                "stored_view_file_shift": DEBUG_COMMAND_STORED_VIEW_FILE_SHIFT,
                "safety": "not_hardware_probed_low_level_commands_may_mutate_or_reboot",
                "entries": [asdict(item) for item in debug_commands],
            },
            "runtime_control_operation_4c": {
                "evidence_status": "static_control_flow_confirmed",
                "handler_address": RUNTIME_CONTROL_HANDLER_ADDRESS,
                "payload_shape": "selector boolean_source",
                "boolean_rule": "false_0_through_63_true_64_through_127",
                "boolean_threshold": RUNTIME_CONTROL_BOOLEAN_THRESHOLD,
                "table_address": RUNTIME_CONTROL_TABLE_ADDRESS,
                "stored_view_file_shift": DEBUG_COMMAND_STORED_VIEW_FILE_SHIFT,
                "safety": "not_hardware_probed_no_independent_state_readback",
                "entries": [asdict(item) for item in runtime_controls],
            },
        }
        metadata["preset_storage_and_active_serialization"] = {
            "evidence_status": "static_control_flow_confirmed",
            "coordinate_note": (
                "header-stripped raw offset equals linked address minus "
                "0x08020000; packaged-member offset adds the 0x40-byte header"
            ),
            "flash_slot_address_formula": "(slot + 0x81) * 0x1000",
            "flash_slot_base": PRESET_FLASH_SLOT_BASE,
            "flash_slot_bytes": PRESET_FLASH_SLOT_BYTES,
            "saved_preset_read": {
                "linked_address": PRESET_SLOT_READER_LINKED_ADDRESS,
                "header_stripped_raw_file_offset": PRESET_SLOT_READER_RAW_FILE_OFFSET,
                "behavior": "read_exactly_4096_bytes_from_flash_slot",
                "sysex_entry": "operation_19_saved_slot_only",
            },
            "active_preset_serializer": {
                "linked_address": PRESET_SERIALIZER_LINKED_ADDRESS,
                "header_stripped_raw_file_offset": PRESET_SERIALIZER_RAW_FILE_OFFSET,
                "caller_linked_addresses": list(PRESET_SERIALIZER_CALLERS_LINKED),
                "caller_header_stripped_raw_file_offsets": list(
                    PRESET_SERIALIZER_CALLERS_RAW_FILE_OFFSETS
                ),
                "behavior": (
                    "serialize_active_header_sequences_and_tagged_parameters_"
                    "then_write_flash_slot"
                ),
                "direct_incoming_sysex_caller": False,
            },
            "sequence_serializer": {
                "linked_address": PRESET_SEQUENCE_SERIALIZER_LINKED_ADDRESS,
                "header_stripped_raw_file_offset": PRESET_SEQUENCE_SERIALIZER_RAW_FILE_OFFSET,
                "bytes": PRESET_SEQUENCE_BYTES,
            },
            "active_sequence_object": {
                "ram_address": ACTIVE_SEQUENCE_OBJECT_RAM_ADDRESS,
                "serialized_bytes": PRESET_SEQUENCE_BYTES,
                "pointer_literal_occurrences": (
                    ACTIVE_SEQUENCE_POINTER_LITERAL_OCCURRENCES
                ),
                "accessor_function_addresses": list(
                    ACTIVE_SEQUENCE_ACCESSOR_FUNCTIONS
                ),
                "direct_references_from_known_sysex_handler_ranges": (
                    ACTIVE_SEQUENCE_DIRECT_KNOWN_SYSEX_HANDLER_REFERENCES
                ),
                "operation_19_reachable_function_count": (
                    OPERATION_19_REACHABLE_FUNCTION_COUNT
                ),
                "operation_19_reaches_any_accessor": False,
                "evidence_limit": (
                    "direct-reference and statically resolved call graph only; "
                    "indirect calls remain a separate search boundary"
                ),
            },
            "tagged_parameter_parser": {
                "linked_address": PRESET_TAGGED_PARSER_LINKED_ADDRESS,
                "header_stripped_raw_file_offset": PRESET_TAGGED_PARSER_RAW_FILE_OFFSET,
                "direction": "saved_payload_to_active_object",
            },
            "flash_slot_writer": {
                "linked_address": PRESET_SLOT_WRITER_LINKED_ADDRESS,
                "header_stripped_raw_file_offset": PRESET_SLOT_WRITER_RAW_FILE_OFFSET,
                "behavior": "erase_then_write_exactly_4096_bytes_to_flash_slot",
            },
            "current_buffer_boundary": (
                "operation_19_reads_flash_only; the inverse serializer is reached "
                "by two save-workflow callers and always continues to a flash-slot "
                "write; no direct known SysEx-handler reference to the active "
                "sequence object was found"
            ),
        }
    if args.json_output:
        print(json.dumps(metadata, indent=2))
        return

    print(
        f"{image_name}: {len(image)} bytes, base=0x{args.base:08x}, "
        f"SP=0x{initial_sp:08x}, reset=0x{reset_vector:08x}"
    )
    print(f"known operation bytes: {' '.join(f'{item:02x}' for item in sorted(known))}")
    print("evidence status: static candidate; hardware/wire confirmation required")
    if "bulk_sysex_dispatch" in metadata:
        bulk = metadata["bulk_sysex_dispatch"]
        operations = " ".join(f"{item:02x}" for item in bulk["implemented_operations"])
        print(
            "bulk object-transfer dispatcher: static control-flow confirmed; "
            f"implemented operations: {operations}"
        )
    if "control_sysex_dispatch" in metadata:
        control = metadata["control_sysex_dispatch"]
        operations = " ".join(
            f"{item:02x}" for item in control["implemented_operations"]
        )
        print(
            "global/storage/device-control dispatcher: static control-flow "
            f"confirmed; implemented operations: {operations}"
        )
    for view, file_shift in zip(views, file_shifts):
        print(f"\nview file_shift={file_shift:+#x}")
        print(f"reachable instructions: {view['reachable_instruction_count']}")
        print(f"candidate regions: {view['candidate_count']}")
        for anchor in view["anchors"]:
            references = anchor["literal_references"]
            print(
                f"anchor {anchor['name']} file+0x{anchor['file_offset']:x} "
                f"=> 0x{anchor['linked_address']:08x}; "
                f"literal refs={len(references)}"
            )
            for reference in references:
                print(
                    f" @ 0x{reference['address']:08x} "
                    f"(file+0x{reference['file_offset']:x}): "
                    f"{reference['mnemonic']} {reference['operands']}"
                )
        candidates = view["candidates"]
        for index, candidate in enumerate(candidates, 1):
            print(
                f"\n[{index}] 0x{candidate['start_address']:08x}-"
                f"0x{candidate['end_address']:08x} "
                f"known={','.join(f'{item:02x}' for item in candidate['known_operations'])} "
                f"nearby={','.join(f'{item:02x}' for item in candidate['nearby_immediates'])}"
            )
            for item in candidate["instructions"]:
                if item["immediate"] is not None:
                    marker = "*" if item["immediate"] in known else "+"
                    print(
                        f" {marker} 0x{item['address']:08x} "
                        f"(file+0x{item['file_offset']:x}): "
                        f"{item['mnemonic']:<8} {item['operands']}"
                    )


if __name__ == "__main__":
    main()
