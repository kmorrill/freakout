#!/usr/bin/env python3
"""Recover MicroFreak global subcommand names from MIDI Control Center.

This is a version-pinned, read-only clean-room research helper.  It does not
launch MIDI Control Center, contact a device, or copy Arturia assets.  Instead
it emulates only the simple constant writes made by one static initializer and
decodes the resulting libc++ short-string objects.

The analyzed binary is proprietary and must not be committed.  The tool fails
closed unless its SHA-256 matches the documented MIDI Control Center build.
Capstone is a research-only dependency::

    python3 -m pip install capstone
    python3 tools/analyze_mcc_microfreak_commands.py \
      "/Applications/Arturia/MIDI Control Center.app/Contents/MacOS/MIDI Control Center"
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import re
import struct
from dataclasses import dataclass
from pathlib import Path


EXPECTED_SHA256 = "9e75f7db046f939fc81f16f5243b0ed6bed4f5649c95145f3ab6adbb182a1f59"
MACHO_MAGIC_64 = 0xFEEDFACF
LC_SEGMENT_64 = 0x19
IMAGE_BASE = 0x100000000
INITIALIZER_START = IMAGE_BASE + 0x4CD000
INITIALIZER_END = IMAGE_BASE + 0x4CE300
TABLE_START = 0x10163CA00
TABLE_END = 0x10163D300
STRING_OBJECT_SIZE = 24
FIRST_SUBCOMMAND = 0x20
CAPTURE_BASE_RE = re.compile(r"^capture-loaded .* image-base=(0x[0-9a-fA-F]+)$")
CAPTURE_TRACE_RE = re.compile(
    r"^trace timestamp=(\d+) op=0x([0-9a-fA-F]{2}) frames=(.*)$"
)
CAPTURE_OUT_RE = re.compile(r"^out timestamp=(\d+) data=([0-9a-fA-F]+)$")


@dataclass(frozen=True)
class MachOSegment:
    name: str
    vmaddr: int
    vmsize: int
    fileoff: int
    filesize: int


@dataclass(frozen=True)
class NormalizedTrace:
    timestamp: int
    operation: int
    return_sites: tuple[int, ...]


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_macho_segments(data: bytes) -> list[MachOSegment]:
    if len(data) < 32 or struct.unpack_from("<I", data)[0] != MACHO_MAGIC_64:
        raise ValueError("expected a little-endian 64-bit Mach-O executable")
    command_count = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    segments: list[MachOSegment] = []
    for _ in range(command_count):
        if offset + 8 > len(data):
            raise ValueError("truncated Mach-O load commands")
        command, size = struct.unpack_from("<II", data, offset)
        if size < 8 or offset + size > len(data):
            raise ValueError("invalid Mach-O load command size")
        if command == LC_SEGMENT_64:
            if size < 72:
                raise ValueError("truncated LC_SEGMENT_64 command")
            raw_name = data[offset + 8 : offset + 24]
            name = raw_name.split(b"\0", 1)[0].decode("ascii", "replace")
            vmaddr, vmsize, fileoff, filesize = struct.unpack_from(
                "<QQQQ", data, offset + 24
            )
            segments.append(MachOSegment(name, vmaddr, vmsize, fileoff, filesize))
        offset += size
    return segments


def vma_to_file_offset(address: int, segments: list[MachOSegment]) -> int:
    for segment in segments:
        if segment.vmaddr <= address < segment.vmaddr + segment.filesize:
            return segment.fileoff + address - segment.vmaddr
    raise ValueError(f"VMA {address:#x} is not backed by file data")


def normalize_runtime_address(address: int, runtime_base: int) -> int:
    """Translate one ASLR-slid runtime address to the static image VMA."""
    if runtime_base < IMAGE_BASE:
        raise ValueError("runtime image base precedes the linked image base")
    return address - (runtime_base - IMAGE_BASE)


def parse_normalized_traces(
    lines: list[str], segments: list[MachOSegment]
) -> list[NormalizedTrace]:
    """Recover host-only return sites from passive capture backtraces.

    Frames outside a Mach-O segment in the fingerprinted main executable are
    deliberately discarded. This excludes the capture shim, CoreMIDI, and
    system frameworks without relying on their version-specific load bases.
    """
    runtime_bases = {
        int(match.group(1), 16)
        for line in lines
        if (match := CAPTURE_BASE_RE.match(line))
    }
    if not runtime_bases:
        raise ValueError("capture does not contain a runtime image base")
    if len(runtime_bases) != 1:
        raise ValueError("capture contains conflicting runtime image bases")
    runtime_base = runtime_bases.pop()

    def in_host_image(address: int) -> bool:
        return any(
            segment.vmaddr <= address < segment.vmaddr + segment.vmsize
            for segment in segments
        )

    traces: list[NormalizedTrace] = []
    for line in lines:
        match = CAPTURE_TRACE_RE.match(line)
        if match is None:
            continue
        operation = int(match.group(2), 16)
        raw_frames = tuple(
            int(value, 16) for value in match.group(3).split(",") if value
        )
        host_frames = tuple(
            normalized
            for frame in raw_frames
            if in_host_image(
                normalized := normalize_runtime_address(frame, runtime_base)
            )
        )
        if not host_frames:
            raise ValueError(
                f"operation 0x{operation:02x} trace has no main-image frames"
            )
        traces.append(NormalizedTrace(int(match.group(1)), operation, host_frames))
    if not traces:
        raise ValueError("capture does not contain any call-stack traces")
    return traces


def parse_normalized_call_stacks(
    lines: list[str], segments: list[MachOSegment]
) -> dict[int, Counter[tuple[int, ...]]]:
    """Group normalized passive traces by operation and return-site stack."""
    stacks: dict[int, Counter[tuple[int, ...]]] = {}
    for trace in parse_normalized_traces(lines, segments):
        stacks.setdefault(trace.operation, Counter())[trace.return_sites] += 1
    return stacks


def parse_outbound_payloads(lines: list[str]) -> dict[int, tuple[int, bytes]]:
    """Index captured Arturia SysEx operations and payloads by timestamp."""
    packets: dict[int, tuple[int, bytes]] = {}
    for line in lines:
        match = CAPTURE_OUT_RE.match(line)
        if match is None:
            continue
        raw = bytes.fromhex(match.group(2))
        if (
            len(raw) < 10
            or raw[:6] != bytes.fromhex("f000206b0701")
            or raw[-1] != 0xF7
        ):
            continue
        declared_length = raw[7]
        payload = raw[9:-1]
        if declared_length != len(payload):
            raise ValueError(
                f"capture timestamp {match.group(1)} has mismatched payload length"
            )
        packets[int(match.group(1))] = (raw[8], payload)
    return packets


def call_stack_report(
    lines: list[str], segments: list[MachOSegment]
) -> dict[str, object]:
    traces = parse_normalized_traces(lines, segments)
    outbound = parse_outbound_payloads(lines)
    stacks: dict[int, Counter[tuple[int, ...]]] = {}
    payloads: dict[tuple[int, tuple[int, ...]], list[bytes]] = {}
    unmatched: Counter[int] = Counter()
    for trace in traces:
        stacks.setdefault(trace.operation, Counter())[trace.return_sites] += 1
        packet = outbound.get(trace.timestamp)
        if packet is None:
            unmatched[trace.operation] += 1
            continue
        operation, payload = packet
        if operation != trace.operation:
            raise ValueError(
                f"trace operation 0x{trace.operation:02x} does not match "
                f"outbound operation 0x{operation:02x} at {trace.timestamp}"
            )
        payloads.setdefault((trace.operation, trace.return_sites), []).append(payload)

    def payload_shapes(operation: int, stack: tuple[int, ...]) -> list[dict[str, object]]:
        grouped: dict[tuple[int, int | None], list[bytes]] = {}
        for payload in payloads.get((operation, stack), []):
            grouped.setdefault(
                (len(payload), payload[-1] if payload else None), []
            ).append(payload)
        return [
            {
                "payload_length": length,
                "final_byte": None if final_byte is None else f"0x{final_byte:02X}",
                "count": len(items),
                "distinct_payloads": len(set(items)),
            }
            for (length, final_byte), items in sorted(
                grouped.items(), key=lambda item: (item[0][0], item[0][1] or -1)
            )
        ]

    return {
        f"0x{operation:02X}": {
            "trace_count": sum(counts.values()),
            "unmatched_trace_count": unmatched[operation],
            "unique_stacks": [
                {
                    "count": count,
                    "return_sites": [f"0x{address:X}" for address in stack],
                    "payload_shapes": payload_shapes(operation, stack),
                }
                for stack, count in counts.most_common()
            ],
        }
        for operation, counts in sorted(stacks.items())
    }


def decode_libcxx_short_strings(
    memory: bytes, *, first_code: int = FIRST_SUBCOMMAND
) -> dict[int, str]:
    if len(memory) % STRING_OBJECT_SIZE:
        raise ValueError("libc++ string table size is not a multiple of 24")
    output: dict[int, str] = {}
    for index in range(len(memory) // STRING_OBJECT_SIZE):
        item = memory[index * STRING_OBJECT_SIZE : (index + 1) * STRING_OBJECT_SIZE]
        if item[0] & 1:
            raise ValueError(f"entry {index} uses unsupported long-string storage")
        length = item[0] >> 1
        if length > STRING_OBJECT_SIZE - 2:
            raise ValueError(f"entry {index} has invalid short-string length {length}")
        output[first_code + index] = item[1 : 1 + length].decode("utf-8")
    return output


def _canonical_register(name: str) -> str:
    if name.startswith("xmm"):
        return name
    aliases = {
        "eax": "rax", "ax": "rax", "al": "rax", "ah": "rax",
        "ebx": "rbx", "bx": "rbx", "bl": "rbx", "bh": "rbx",
        "ecx": "rcx", "cx": "rcx", "cl": "rcx", "ch": "rcx",
        "edx": "rdx", "dx": "rdx", "dl": "rdx", "dh": "rdx",
        "esi": "rsi", "si": "rsi", "sil": "rsi",
        "edi": "rdi", "di": "rdi", "dil": "rdi",
        "ebp": "rbp", "bp": "rbp", "bpl": "rbp",
        "esp": "rsp", "sp": "rsp", "spl": "rsp",
    }
    if name in aliases:
        return aliases[name]
    if name.startswith("r") and name[-1:] in {"d", "w", "b"} and name[1:-1].isdigit():
        return name[:-1]
    return name


def recover_subcommands(data: bytes) -> dict[int, str]:
    digest = sha256_bytes(data)
    if digest != EXPECTED_SHA256:
        raise ValueError(
            "unsupported MIDI Control Center executable: "
            f"SHA-256 {digest}; expected {EXPECTED_SHA256}"
        )
    try:
        from capstone import CS_ARCH_X86, CS_MODE_64, Cs
        from capstone.x86 import X86_OP_IMM, X86_OP_MEM, X86_OP_REG, X86_REG_RIP
    except ImportError as error:  # pragma: no cover - environment guidance
        raise RuntimeError("install the research dependency with: pip install capstone") from error

    segments = parse_macho_segments(data)
    code_start = vma_to_file_offset(INITIALIZER_START, segments)
    code_end = vma_to_file_offset(INITIALIZER_END - 1, segments) + 1
    table = bytearray(TABLE_END - TABLE_START)
    registers: dict[str, int | bytes | None] = {}

    def read_vma(address: int, size: int) -> bytes:
        offset = vma_to_file_offset(address, segments)
        return data[offset : offset + size]

    def operand_value(operand, instruction):
        if operand.type == X86_OP_IMM:
            return operand.imm
        if operand.type == X86_OP_REG:
            return registers.get(_canonical_register(instruction.reg_name(operand.reg)))
        if (
            operand.type == X86_OP_MEM
            and operand.mem.base == X86_REG_RIP
            and operand.mem.index == 0
        ):
            address = instruction.address + instruction.size + operand.mem.disp
            return read_vma(address, operand.size)
        return None

    def write_table(address: int, size: int, value: int | bytes | None) -> None:
        if not (TABLE_START <= address and address + size <= TABLE_END):
            return
        if value is None:
            raise ValueError(f"unresolved initializer value for table VMA {address:#x}")
        if isinstance(value, int):
            mask = (1 << (size * 8)) - 1
            value = (value & mask).to_bytes(size, "little")
        table[address - TABLE_START : address - TABLE_START + size] = value[:size]

    disassembler = Cs(CS_ARCH_X86, CS_MODE_64)
    disassembler.detail = True
    disassembler.skipdata = True
    supported_moves = {"mov", "movabs", "movups", "movaps", "movdqa", "movdqu"}
    for instruction in disassembler.disasm(
        data[code_start:code_end], INITIALIZER_START
    ):
        operands = instruction.operands
        if instruction.mnemonic in supported_moves and len(operands) == 2:
            value = operand_value(operands[1], instruction)
            destination = operands[0]
            if destination.type == X86_OP_REG:
                registers[_canonical_register(instruction.reg_name(destination.reg))] = value
            elif (
                destination.type == X86_OP_MEM
                and destination.mem.base == X86_REG_RIP
                and destination.mem.index == 0
            ):
                address = instruction.address + instruction.size + destination.mem.disp
                write_table(address, destination.size, value)
        elif (
            instruction.mnemonic in {"xorps", "pxor"}
            and len(operands) == 2
            and operands[0].type == X86_OP_REG
            and operands[1].type == X86_OP_REG
            and operands[0].reg == operands[1].reg
        ):
            registers[_canonical_register(instruction.reg_name(operands[0].reg))] = bytes(
                operands[0].size
            )

    result = decode_libcxx_short_strings(table)
    if len(result) != 96 or result.get(0x20) != "kOptMidiChannelIn":
        raise ValueError("initializer recovery did not produce the expected table shape")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--capture",
        type=Path,
        help="normalize passive capture call stacks instead of recovering names",
    )
    arguments = parser.parse_args()
    data = arguments.executable.read_bytes()
    digest = sha256_bytes(data)
    if digest != EXPECTED_SHA256:
        raise ValueError(
            "unsupported MIDI Control Center executable: "
            f"SHA-256 {digest}; expected {EXPECTED_SHA256}"
        )
    if arguments.capture is not None:
        report = call_stack_report(
            arguments.capture.read_text().splitlines(), parse_macho_segments(data)
        )
        if arguments.json:
            print(json.dumps(report, indent=2))
        else:
            for operation, details in report.items():
                print(f"{operation} traces={details['trace_count']}")
                for stack in details["unique_stacks"]:
                    sites = ",".join(stack["return_sites"])
                    print(f"  count={stack['count']} return-sites={sites}")
        return 0
    commands = recover_subcommands(data)
    if arguments.json:
        print(json.dumps({f"0x{code:02X}": name for code, name in commands.items()}, indent=2))
    else:
        for code, name in commands.items():
            print(f"0x{code:02X} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
