"""Independent MicroFreak preset and wavetable transport over Arturia SysEx.

The framing and transaction below were verified against a passive MIDI Control
Center 1.23.0 capture on MicroFreak firmware 5.0.0.36. Guarded preset and
wavetable writes have fresh backup, exact readback, and automatic restoration;
the Elektroid adapter remains available as a compatibility backend.
"""

from __future__ import annotations

import time
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from minifreak_patch.microfreak import (
    MICROFREAK_PRESET_PAYLOAD_SIZE,
    MicroFreakPreset,
)
from minifreak_patch.microfreak_live_map import (
    MICROFREAK_STRUCTURED_LIVE_EVIDENCE,
    MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE,
    MICROFREAK_STRUCTURED_LIVE_WORDS,
)
from minifreak_patch.microfreak_global_specs import (
    MICROFREAK_GLOBAL_VALUE_SPECS,
    decode_microfreak_global,
)
from minifreak_patch.wavetable import MICROFREAK_PCM_BYTES, MicroFreakWavetable


ARTURIA_MICROFREAK_PREFIX = bytes((0x00, 0x20, 0x6B, 0x07, 0x01))
PRESET_HEADER_LENGTH = 0x23
PRESET_PART_LENGTH = 0x20
PRESET_PARTS = MICROFREAK_PRESET_PAYLOAD_SIZE // PRESET_PART_LENGTH
INITIALIZER_TEMPLATE_BANK = 4
INITIALIZER_TEMPLATE_PROGRAM = 0
WAVE_PACKET_MIDI_BYTES = 32
SAMPLE_SLOTS = 128
SAMPLE_HEADER_RAW_BYTES = 28
SAMPLE_PART_BYTES = 4096
SAMPLE_PACKETS_PER_PART = 147
SAMPLE_MAX_SECONDS = 24
SAMPLE_RATE_HZ = 32_000
SAMPLE_MAX_BYTES = SAMPLE_MAX_SECONDS * SAMPLE_RATE_HZ * 2
SAMPLE_TOTAL_CAPACITY_MS = 209_920
SAMPLE_MEMORY_CAPACITY_BYTES = SAMPLE_TOTAL_CAPACITY_MS * 64
LIVE_PARAMETER_GROUPS = 24
LIVE_PARAMETER_WORDS_PER_GROUP = 16
LIVE_PARAMETER_WORDS = LIVE_PARAMETER_GROUPS * LIVE_PARAMETER_WORDS_PER_GROUP
MICROFREAK_OSCILLATOR_ENGINE_SCALE_MAX = 22
MICROFREAK_STATUS_RECORD_SELECTORS = (0, 1, 2, 3, 4, 5, 7)
MICROFREAK_OSCILLATOR_ENGINE_NAMES = {
    1: "BasicWaves",
    2: "SuperWave",
    3: "Wavetable",
    4: "Harmo",
    5: "KarplusStr",
    6: "V.Analog",
    7: "Waveshaper",
    8: "Two Op. FM",
    9: "Formant",
    10: "Chords",
    11: "Speech",
    12: "Modal",
    13: "Noise",
    14: "Vocoder",
    15: "Bass",
    16: "SawX",
    17: "Harm",
    18: "WaveUser",
    19: "Sample",
    20: "Scan Grains",
    21: "Cloud Grains",
    22: "Hit Grains",
}

# Hardware-correlated in one 20-CC sentinel batch against firmware 5. The
# active table returned to an exact 384-word baseline after preset recall.
# Repeated addresses with the same value are engine aliases. Oscillator type
# instead updates one packed word plus three derived signed-state words.
MICROFREAK_LIVE_WORD_SEMANTICS: dict[int, dict[str, str]] = {
    0x0000: {"parameter": "osc.type", "relationship": "dependent"},
    0x0001: {"parameter": "osc.wave", "relationship": "direct"},
    0x0003: {"parameter": "osc.timbre", "relationship": "direct"},
    0x0005: {"parameter": "osc.shape", "relationship": "direct"},
    0x000B: {"parameter": "envelope.attack", "relationship": "alias"},
    0x000C: {"parameter": "envelope.decay", "relationship": "alias"},
    0x000D: {"parameter": "envelope.sustain", "relationship": "alias"},
    0x000F: {"parameter": "filter.env_amount", "relationship": "alias"},
    0x0101: {"parameter": "filter.cutoff", "relationship": "alias"},
    0x0102: {"parameter": "filter.resonance", "relationship": "alias"},
    0x0104: {"parameter": "cycling_env.rise", "relationship": "alias"},
    0x0105: {
        "parameter": "cycling_env.rise_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
    0x0106: {"parameter": "cycling_env.fall", "relationship": "alias"},
    0x0107: {"parameter": "cycling_env.hold", "relationship": "alias"},
    0x0108: {
        "parameter": "cycling_env.fall_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
    0x0109: {"parameter": "cycling_env.amount", "relationship": "alias"},
    0x010A: {"parameter": "glide", "relationship": "alias"},
    0x0201: {"parameter": "cycling_env.rise", "relationship": "alias"},
    0x0202: {
        "parameter": "cycling_env.rise_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
    0x0203: {"parameter": "cycling_env.fall", "relationship": "alias"},
    0x0204: {"parameter": "cycling_env.hold", "relationship": "alias"},
    0x0205: {
        "parameter": "cycling_env.fall_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
    0x0206: {"parameter": "cycling_env.amount", "relationship": "alias"},
    0x0207: {"parameter": "glide", "relationship": "alias"},
    0x0300: {"parameter": "glide", "relationship": "alias"},
    0x030A: {"parameter": "arp.rate_sync", "relationship": "alias"},
    0x030B: {"parameter": "arp.rate_free", "relationship": "alias"},
    0x030E: {"parameter": "spice", "relationship": "alias"},
    0x0402: {"parameter": "arp.rate_sync", "relationship": "alias"},
    0x0403: {"parameter": "arp.rate_free", "relationship": "alias"},
    0x0406: {"parameter": "spice", "relationship": "alias"},
    0x040B: {"parameter": "lfo.rate_sync", "relationship": "alias"},
    0x040C: {"parameter": "lfo.rate_free", "relationship": "alias"},
    0x0501: {"parameter": "lfo.rate_sync", "relationship": "alias"},
    0x0502: {"parameter": "lfo.rate_free", "relationship": "alias"},
    0x0601: {"parameter": "envelope.attack", "relationship": "alias"},
    0x0602: {"parameter": "envelope.decay", "relationship": "alias"},
    0x0603: {"parameter": "envelope.sustain", "relationship": "alias"},
    0x0605: {"parameter": "filter.env_amount", "relationship": "alias"},
    0x0B0D: {"parameter": "osc.type", "relationship": "dependent"},
    0x0C07: {"parameter": "osc.type", "relationship": "dependent"},
    0x0D01: {"parameter": "osc.type", "relationship": "dependent"},
    0x0F0E: {"parameter": "filter.cutoff", "relationship": "alias"},
    0x0F0F: {"parameter": "filter.resonance", "relationship": "alias"},
    0x1008: {"parameter": "filter.cutoff", "relationship": "alias"},
    0x1009: {"parameter": "filter.resonance", "relationship": "alias"},
    0x100B: {"parameter": "cycling_env.rise", "relationship": "alias"},
    0x100C: {
        "parameter": "cycling_env.rise_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
    0x100D: {"parameter": "cycling_env.fall", "relationship": "alias"},
    0x100E: {"parameter": "cycling_env.hold", "relationship": "alias"},
    0x100F: {
        "parameter": "cycling_env.fall_shape",
        "relationship": "alias",
        "evidence": "saved_live_13_preset_exact_match_restore",
    },
}

# Promote the diversity-optimized saved/live corpus without replacing the
# earlier CC-derived canonical labels. Every address below matched its tagged
# raw_u16 vector exactly across 40 selected presets and survived exact recovery.
for _field_name, _field_addresses in MICROFREAK_STRUCTURED_LIVE_WORDS.items():
    for _ordinal, _field_address in enumerate(_field_addresses):
        MICROFREAK_LIVE_WORD_SEMANTICS.setdefault(
            _field_address,
            {
                "parameter": f"structured.{_field_name}",
                "relationship": "direct" if _ordinal == 0 else "alias",
                "evidence": MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE.get(
                    _field_name, MICROFREAK_STRUCTURED_LIVE_EVIDENCE
                ),
            },
        )

MICROFREAK_GLOBAL_CODES = {
    "midi.channel_in": 0x20,
    "midi.channel_out": 0x21,
    "midi.automation_in": 0x22,
    "midi.automation_out": 0x23,
    "midi.output_destination": 0x25,
    "midi.local_control": 0x26,
    "control.pause_exit_mode": 0x29,
    "midi.program_change_enable": 0x2A,
    "midi.arp_seq_notes_out": 0x2B,
    "midi.thru": 0x3B,
    "midi.knob_send_cc": 0x24,
    "midi.merge": 0x3C,
    "clock.source": 0x2E,
    "device.id": 0x2F,
    "midi.automation_14bit": 0x30,
    "clock.sync_port_timing": 0x31,
    "clock.sync_port_start": 0x32,
    "clock.global_tempo": 0x3D,
    "cv.pitch_format": 0x38,
    "cv.gate_format": 0x39,
    "cv.press_range": 0x3A,
    "cv.zero_volt_reference": 0x36,
    "cv.one_volt_reference": 0x37,
    "control.knob_catch": 0x2D,
    "control.click_to_load": 0x3E,
    "control.help_screen": 0x40,
    "control.osc_knob_speed": 0x4C,
    "control.octave_led_blink": 0x4D,
    "tuning.master": 0x42,
    "memory.protection": 0x3F,
    "keyboard.sensitivity": 0x41,
    "keyboard.aftertouch_curve": 0x27,
    "keyboard.velocity_curve": 0x28,
    "keyboard.aftertouch_compensation": 0x33,
    "keyboard.aftertouch_offset": 0x34,
    "midi.channel_in_lower": 0x35,
    "keyboard.relative_bend": 0x44,
    "keyboard.scale": 0x45,
    "keyboard.root_note": 0x46,
    "microphone.gain": 0x47,
    "microphone.noise_gate": 0x49,
    "microphone.detect": 0x4A,
    "midi.usb_to_din": 0x43,
}
WAVE_PACKET_RAW_BYTES = 28
WAVE_PACKETS_PER_PART = 147
WAVE_PART_BYTES = 4096
WAVE_PARTS = MICROFREAK_PCM_BYTES // WAVE_PART_BYTES


class MicroFreakMidiError(RuntimeError):
    pass


def infer_oscillator_engine_index(raw_u16: int) -> int | None:
    """Decode the observed normalized oscillator-engine live word.

    Hardware corpus values lie exactly (within integer rounding) on a 0..22
    normalized scale. Returning ``None`` for any off-grid word keeps the
    relationship evidence-labelled instead of silently coercing an unknown
    runtime representation.
    """

    if not 0 <= raw_u16 <= 0x7FFF:
        return None
    candidate = round(raw_u16 * MICROFREAK_OSCILLATOR_ENGINE_SCALE_MAX / 0x7FFF)
    expected = round(candidate * 0x7FFF / MICROFREAK_OSCILLATOR_ENGINE_SCALE_MAX)
    return candidate if abs(raw_u16 - expected) <= 1 else None


@dataclass(frozen=True)
class MicroFreakSysex:
    sequence: int
    operation: int
    payload: bytes


@dataclass(frozen=True)
class DirectPresetWriteReport:
    slot: int
    backup_path: str
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool
    target_archive_sha256: str
    readback_archive_sha256: str
    archive_wrapper_normalized: bool


@dataclass(frozen=True)
class DirectWavetableHeader:
    slot: int
    name: str
    empty: bool


@dataclass(frozen=True)
class DirectSampleHeader:
    """One lossless MicroFreak sample-directory entry."""

    slot: int
    device_id: int
    name: str
    address: int
    size_bytes: int
    checksum: int
    empty: bool
    raw_header_hex: str


@dataclass(frozen=True)
class DirectSample:
    """One lossless device sample body with its directory metadata."""

    header: DirectSampleHeader
    audio_bytes: bytes


@dataclass(frozen=True)
class DirectSampleWriteReport:
    """Guarded sample upload report with exact body readback."""

    slot: int
    backup_path: str
    before_empty: bool
    before_name: str
    before_sha256: str
    target_name: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool


@dataclass(frozen=True)
class DirectSampleClearReport:
    """Verified sample clear with a lossless local recovery artifact."""

    slot: int
    backup_path: str
    before_name: str
    before_sha256: str
    empty_verified: bool


@dataclass(frozen=True)
class DirectSampleStorageStats:
    """Read-only operation-47/48 sample-memory statistics."""

    used_milliseconds: int
    free_milliseconds: int
    estimated_free_bytes: int
    capacity_bytes: int
    raw_payload_hex: str


@dataclass(frozen=True)
class DirectStatusRecordReply:
    """One raw operation-48 reply to a firmware-backed kind-0x13 request."""

    selector: int
    request_sequence: int
    raw_sysex_hex: str
    raw_length: int
    prefix_hex: str
    reply_sequence: int | None
    declared_length: int | None
    operation: int | None
    payload_hex: str
    declared_length_matches: bool
    unpacked_record_hex: str | None
    record_kind: int | None
    record_selector: int | None
    value_u16: int | None
    value_u32: int | None


@dataclass(frozen=True)
class DirectStatusRecordCaptureReport:
    """Read-only status replies plus before/after patch/global invariants."""

    replies: tuple[DirectStatusRecordReply, ...]
    live_table_exact: bool
    changed_live_addresses: tuple[int, ...]
    global_settings_exact: bool
    changed_global_settings: tuple[tuple[str, int, int], ...]


@dataclass(frozen=True)
class DirectLiveParameterWord:
    """One read-only word from the live parameter-table transport."""

    index: int
    raw_u16: int
    signed_i16: int
    raw_payload_hex: str


@dataclass(frozen=True)
class DirectLiveStructuredField:
    """One named structured field projected from the complete live table."""

    name: str
    raw_u16: int
    signed_i16: int
    addresses: tuple[int, ...]
    alias_values: tuple[int, ...]
    aliases_match: bool
    evidence: str


@dataclass(frozen=True)
class DirectLiveParameterWriteProbeReport:
    """Reversible live-word write experiment with complete-table verification."""

    index: int
    parameter: str | None
    before_raw_u16: int
    target_raw_u16: int
    readback_raw_u16: int
    restored_raw_u16: int
    target_verified: bool
    restore_verified: bool
    restoration_method: str
    recovery_slot: int
    changed_after_addresses: tuple[int, ...]
    changed_after_restore_addresses: tuple[int, ...]


@dataclass(frozen=True)
class DirectLiveTableChange:
    """One word changed during a reversible live-table experiment."""

    index: int
    before_raw_u16: int
    after_raw_u16: int
    restored_raw_u16: int


@dataclass(frozen=True)
class DirectLiveCcProbeReport:
    """Reversible MIDI-CC versus complete-live-table experiment."""

    parameter: str
    cc: int
    target_value: int
    restore_value: int
    target_effect_observed: bool
    restore_verified: bool
    restoration_method: str
    recovery_slot: int
    changes: tuple[DirectLiveTableChange, ...]
    changed_after_restore_addresses: tuple[int, ...]


@dataclass(frozen=True)
class DirectGlobalWriteProbeReport:
    """Verified global-setting write/readback/restore experiment."""

    name: str
    code: int
    before_value: int
    target_value: int
    readback_value: int
    restored_value: int
    target_verified: bool
    restore_verified: bool
    restoration_method: str
    recovery_slot: int
    changes: tuple[DirectLiveTableChange, ...]
    changed_after_restore_addresses: tuple[int, ...]


@dataclass(frozen=True)
class DirectGlobalWriteReport:
    """Domain-checked global write with preflight backup and readback."""

    name: str
    code: int
    backup_path: str
    before_value: int
    target_value: int
    readback_value: int
    exact_readback: bool


@dataclass(frozen=True)
class DirectSequencePlaybackEvent:
    """One device-originated MIDI event observed during host-clock playback."""

    clock_sent: int
    elapsed_seconds: float
    message_type: str
    channel: int | None
    note: int | None
    velocity: int | None
    control: int | None
    value: int | None
    pitch: int | None
    data: tuple[int, ...]
    host_echo_candidate: bool


@dataclass(frozen=True)
class DirectSequenceLiveSnapshot:
    """Selected operation-41 words sampled at one external-clock boundary."""

    clock_sent: int
    words: tuple[DirectLiveParameterWord, ...]


@dataclass(frozen=True)
class DirectSequenceLiveTrace:
    """Outgoing MIDI plus complete live-state snapshots from one playback."""

    events: tuple[DirectSequencePlaybackEvent, ...]
    snapshots: tuple[DirectSequenceLiveSnapshot, ...]


@dataclass(frozen=True)
class DirectWavetableWriteReport:
    slot: int
    backup_path: str
    before_empty: bool
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool


@dataclass(frozen=True)
class DirectWavetableClearReport:
    slot: int
    backup_path: str
    before_sha256: str
    empty_verified: bool


def encode_sysex(sequence: int, operation: int, payload: bytes = b"") -> bytes:
    if not 0 <= sequence <= 0x7F:
        raise ValueError("MicroFreak sequence must be 0..127")
    if len(payload) > 0x7F or any(value > 0x7F for value in payload):
        raise ValueError("MicroFreak MIDI SysEx payload must be 7-bit clean")
    return bytes(
        (0xF0, *ARTURIA_MICROFREAK_PREFIX, sequence, len(payload), operation)
    ) + payload + bytes((0xF7,))


def decode_sysex(data: bytes | Iterable[int]) -> MicroFreakSysex:
    raw = bytes(data)
    if raw[:1] == b"\xF0" and raw[-1:] == b"\xF7":
        raw = raw[1:-1]
    if len(raw) < 8 or raw[:5] != ARTURIA_MICROFREAK_PREFIX:
        raise MicroFreakMidiError("not an Arturia MicroFreak SysEx message")
    sequence, declared_length, operation = raw[5:8]
    payload = raw[8:]
    if declared_length != len(payload):
        raise MicroFreakMidiError(
            f"MicroFreak SysEx declared {declared_length} payload bytes, "
            f"received {len(payload)}"
        )
    return MicroFreakSysex(sequence, operation, payload)


def decode_control_word_payload(payload: bytes | Iterable[int]) -> tuple[int, int]:
    """Decode operation-40's flag-packed big-endian index/value pair."""

    raw = bytes(payload)
    if len(raw) != 5 or any(value > 0x7F for value in raw):
        raise MicroFreakMidiError("operation-40 payload must be five 7-bit bytes")
    flags = raw[0]
    index = ((raw[1] | (0x80 if flags & 0x40 else 0)) << 8) | (
        raw[2] | (0x80 if flags & 0x20 else 0)
    )
    value = ((raw[3] | (0x80 if flags & 0x10 else 0)) << 8) | (
        raw[4] | (0x80 if flags & 0x08 else 0)
    )
    return index, value


def encode_control_index_payload(index: int) -> bytes:
    """Encode operation-41's flag-packed 16-bit table index."""

    if not 0 <= index <= 0xFFFF:
        raise ValueError("control-table index must be 0..65535")
    high, low = index >> 8, index & 0xFF
    flags = (0x40 if high & 0x80 else 0) | (0x20 if low & 0x80 else 0)
    return bytes((flags, high & 0x7F, low & 0x7F))


def encode_control_word_payload(index: int, value: int) -> bytes:
    """Encode the flag-packed shape used by operation-40 replies."""

    if not 0 <= index <= 0xFFFF:
        raise ValueError("control-table index must be 0..65535")
    if not 0 <= value <= 0xFFFF:
        raise ValueError("control-table value must be 0..65535")
    index_high, index_low = index >> 8, index & 0xFF
    value_high, value_low = value >> 8, value & 0xFF
    flags = 0
    parts = (index_high, index_low, value_high, value_low)
    for bit, part in zip((0x40, 0x20, 0x10, 0x08), parts):
        if part & 0x80:
            flags |= bit
    return bytes((flags, *(part & 0x7F for part in parts)))


def encode_control_word_request_payload(index: int, value: int) -> bytes:
    """Encode the device's asymmetric operation-40 write request.

    Firmware reads the four address/value bytes directly and does not apply
    the reply flag byte. Consequently each byte must already be 7-bit clean;
    reply packing is not a valid inverse for writes.
    """

    if not 0 <= index <= 0xFFFF:
        raise ValueError("control-table index must be 0..65535")
    if not 0 <= value <= 0xFFFF:
        raise ValueError("control-table value must be 0..65535")
    parts = (index >> 8, index & 0xFF, value >> 8, value & 0xFF)
    if any(part > 0x7F for part in parts):
        raise ValueError(
            "operation-40 write address/value bytes must each be 7-bit clean"
        )
    return bytes((0, *parts))


def pack_six_byte_state_record(record: bytes | Iterable[int]) -> bytes:
    """Pack one six-byte internal record behind its operation-49 flag byte."""

    raw = bytes(record)
    if len(raw) != 6:
        raise ValueError("MicroFreak internal state record must be six bytes")
    flags = 0
    for bit, value in zip((0x40, 0x20, 0x10, 0x08, 0x04, 0x02), raw):
        if value & 0x80:
            flags |= bit
    return bytes((flags, *(value & 0x7F for value in raw)))


def unpack_six_byte_state_record(data: bytes | Iterable[int]) -> bytes:
    """Unpack the flag byte plus six MIDI-clean bytes into one raw record."""

    packed = bytes(data)
    if len(packed) != 7 or any(value > 0x7F for value in packed):
        raise ValueError("packed MicroFreak state record must be seven 7-bit bytes")
    flags = packed[0]
    return bytes(
        value | (0x80 if flags & bit else 0)
        for bit, value in zip(
            (0x40, 0x20, 0x10, 0x08, 0x04, 0x02), packed[1:]
        )
    )


def encode_status_state_record_request(selector: int) -> bytes:
    """Encode the statically read-only kind-0x13 status selector request."""

    if selector not in MICROFREAK_STATUS_RECORD_SELECTORS:
        choices = ", ".join(str(item) for item in MICROFREAK_STATUS_RECORD_SELECTORS)
        raise ValueError(f"status selector must be one of: {choices}")
    record = bytes((0xF5, 0x13, selector, 0, 0, 0))
    return bytes((0x06, 0x7D)) + pack_six_byte_state_record(record)


def encode_live_parameter_state_record_request(index: int, value: int) -> bytes:
    """Encode the statically derived operation-49/6 direct live-setter request."""

    if not 0 <= index <= 0xFFFF:
        raise ValueError("control-table index must be 0..65535")
    if not 0 <= value <= 0x7FFF:
        raise ValueError("internal-record live target must be 0..32767")
    scaled = value << 1
    record = bytes(
        (0xF5, 0x02, index >> 8, index & 0xFF, scaled >> 8, scaled & 0xFF)
    )
    return bytes((0x06, 0x7D)) + pack_six_byte_state_record(record)


def unpack_8bit_midi(data: bytes) -> bytes:
    """Decode Arturia's 8-to-7-bit MIDI packing (32 bytes to 28 bytes)."""
    if len(data) % 8:
        raise ValueError("packed MIDI data length must be a multiple of 8")
    output = bytearray()
    for offset in range(0, len(data), 8):
        high_bits = data[offset]
        for index in range(7):
            output.append(data[offset + index + 1] | ((high_bits & 1) << 7))
            high_bits >>= 1
    return bytes(output)


def pack_8bit_midi(data: bytes) -> bytes:
    """Encode 8-bit data into Arturia's 7-bit-clean MIDI representation."""
    if len(data) % 7:
        raise ValueError("raw MIDI packing input length must be a multiple of 7")
    output = bytearray()
    for offset in range(0, len(data), 7):
        high_bits = 0
        low = bytearray()
        for index, value in enumerate(data[offset : offset + 7]):
            high_bits |= ((value >> 7) & 1) << index
            low.append(value & 0x7F)
        output.append(high_bits)
        output.extend(low)
    return bytes(output)


def microfreak_sample_checksum(audio_bytes: bytes) -> int:
    """Return the firmware-compatible little-endian 16-bit sample checksum."""

    if len(audio_bytes) % 2:
        raise ValueError("MicroFreak sample PCM must contain complete 16-bit samples")
    return sum(
        int.from_bytes(audio_bytes[offset : offset + 2], "little")
        for offset in range(0, len(audio_bytes), 2)
    ) & 0xFFFF


class MicroFreakMidiTransport:
    """Direct one-preset reader using paired CoreMIDI input/output ports."""

    def __init__(
        self,
        *,
        port_name: str | None = None,
        midi_backend: Any | None = None,
        timeout: float = 2.0,
        sleep_fn: Any = time.sleep,
    ) -> None:
        self.port_name = port_name
        self.midi = midi_backend or self._load_mido()
        self.timeout = timeout
        self.sleep = sleep_fn
        self.sequence = 0

    @staticmethod
    def _load_mido() -> Any:
        try:
            import mido
        except ImportError as exc:  # pragma: no cover - installation error
            raise MicroFreakMidiError(
                "direct MicroFreak MIDI requires mido and python-rtmidi"
            ) from exc
        return mido

    def resolve_port(self) -> str:
        inputs = list(self.midi.get_input_names())
        outputs = list(self.midi.get_output_names())
        if self.port_name is not None:
            if self.port_name not in inputs or self.port_name not in outputs:
                raise MicroFreakMidiError(
                    f"MicroFreak port must exist as input and output: {self.port_name}"
                )
            return self.port_name
        matches = sorted(
            set(inputs).intersection(outputs),
            key=lambda name: ("arturia" not in name.lower(), name),
        )
        matches = [name for name in matches if "microfreak" in name.lower()]
        if len(matches) != 1:
            raise MicroFreakMidiError(
                "expected exactly one paired MicroFreak MIDI port; found: "
                + (", ".join(matches) if matches else "none")
            )
        return matches[0]

    def _next_request(self, operation: int, payload: bytes = b"") -> Any:
        raw = encode_sysex(self.sequence, operation, payload)
        self.sequence = (self.sequence + 1) & 0x7F
        return self.midi.Message("sysex", data=raw[1:-1])

    def _receive(self, input_port: Any) -> MicroFreakSysex:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = input_port.poll()
            if message is None:
                self.sleep(0.001)
                continue
            if getattr(message, "type", None) != "sysex":
                continue
            try:
                return decode_sysex(message.data)
            except MicroFreakMidiError:
                continue
        raise MicroFreakMidiError("timed out waiting for a MicroFreak SysEx reply")

    def _exchange(
        self,
        input_port: Any,
        output_port: Any,
        operation: int,
        payload: bytes,
        expected_operation: int,
        expected_length: int,
    ) -> bytes:
        request_sequence = self.sequence
        output_port.send(self._next_request(operation, payload))
        response = self._receive(input_port)
        if response.sequence != request_sequence:
            raise MicroFreakMidiError(
                f"expected MicroFreak sequence 0x{request_sequence:02x}, "
                f"received 0x{response.sequence:02x}"
            )
        if response.operation != expected_operation:
            raise MicroFreakMidiError(
                f"expected MicroFreak operation 0x{expected_operation:02x}, "
                f"received 0x{response.operation:02x}"
            )
        if len(response.payload) != expected_length:
            raise MicroFreakMidiError(
                f"expected {expected_length} response bytes, "
                f"received {len(response.payload)}"
            )
        return response.payload

    @staticmethod
    def _decode_global_reply(data: bytes | Iterable[int], code: int) -> int:
        raw = bytes(data)
        if raw and raw[0] == 0xF0:
            raw = raw[1:]
        if raw and raw[-1] == 0xF7:
            raw = raw[:-1]
        if (
            len(raw) != 10
            or raw[:5] != bytes.fromhex("00206b077f")
            or raw[6:9] != bytes((0x02, 0x42, code))
        ):
            raise MicroFreakMidiError(
                f"invalid MicroFreak global reply for code 0x{code:02x}"
            )
        return raw[9]

    @staticmethod
    def _decode_alt_reply(
        data: bytes | Iterable[int], operation: int, expected_length: int
    ) -> bytes:
        """Decode a device-originated ``07 7F`` control-family reply."""

        raw = bytes(data)
        if raw and raw[0] == 0xF0:
            raw = raw[1:]
        if raw and raw[-1] == 0xF7:
            raw = raw[:-1]
        if (
            len(raw) != 8 + expected_length
            or raw[:5] != bytes.fromhex("00206b077f")
            or raw[6] != expected_length
            or raw[7] != operation
        ):
            raise MicroFreakMidiError(
                f"invalid MicroFreak alternate reply for operation 0x{operation:02x}"
            )
        return raw[8:]

    def read_global_codes(self, codes: Iterable[int]) -> dict[int, int]:
        """Read selected raw operation-43 selectors without changing device state."""

        selected = tuple(dict.fromkeys(codes))
        if not selected:
            raise ValueError("at least one MicroFreak global code is required")
        if any(not 0 <= code <= 0x7F for code in selected):
            raise ValueError("MicroFreak global codes must be 0..127")
        port_name = self.resolve_port()
        self.sequence = 0
        result: dict[int, int] = {}
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            for code in selected:
                output_port.send(self._next_request(0x43, bytes((code,))))
                response = self._receive_raw_sysex(input_port)
                result[code] = self._decode_global_reply(response, code)
        return result

    def read_global_settings(self) -> dict[str, int]:
        """Read all 43 named firmware-5 global subcommands confirmed on hardware."""

        raw = self.read_global_codes(MICROFREAK_GLOBAL_CODES.values())
        return {name: raw[code] for name, code in MICROFREAK_GLOBAL_CODES.items()}

    def _write_global_code(self, code: int, value: int) -> None:
        """Send operation 42's two-byte setter; callers must verify via 43."""

        if not 0 <= code <= 0x7F or not 0 <= value <= 0x7F:
            raise ValueError("MicroFreak global code and value must be 0..127")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_output(port_name) as output_port:
            output_port.send(self._next_request(0x42, bytes((code, value))))

    def probe_global_setting_write(
        self, name: str, target_value: int, recovery_slot: int
    ) -> DirectGlobalWriteProbeReport:
        """Temporarily write one named global and verify exact restoration.

        Operation 42 does not acknowledge writes, so operation 43 readback is
        mandatory after both target and inverse writes. The active 384-word
        synth table is also compared to expose global-to-patch side effects.
        """

        try:
            code = MICROFREAK_GLOBAL_CODES[name]
        except KeyError as exc:
            choices = ", ".join(sorted(MICROFREAK_GLOBAL_CODES))
            raise ValueError(f"unknown MicroFreak global {name!r}; supported: {choices}") from exc
        if not 0 <= target_value <= 127:
            raise ValueError("MicroFreak global target must be 0..127")
        if not 1 <= recovery_slot <= 512:
            raise ValueError("MicroFreak recovery slot must be 1..512")

        before_value: int | None = None
        baseline: list[DirectLiveParameterWord] | None = None
        changed: list[DirectLiveParameterWord] | None = None
        restored: list[DirectLiveParameterWord] | None = None
        readback_value: int | None = None
        restored_value: int | None = None
        restoration_method = "operation_42_inverse"
        try:
            before_value = self.read_global_codes((code,))[code]
            baseline = self.read_live_parameter_words()
            self._write_global_code(code, target_value)
            self.sleep(0.1)
            readback_value = self.read_global_codes((code,))[code]
            changed = self.read_live_parameter_words()
            self._write_global_code(code, before_value)
            self.sleep(0.1)
            restored_value = self.read_global_codes((code,))[code]
            restored = self.read_live_parameter_words()
        except Exception:
            if before_value is not None:
                try:
                    self._write_global_code(code, before_value)
                    self.sleep(0.1)
                finally:
                    if baseline is not None:
                        self.select_preset(recovery_slot)
                        self.sleep(0.2)
            raise

        assert baseline is not None and changed is not None and restored is not None
        assert before_value is not None and readback_value is not None
        assert restored_value is not None
        before_by_index = {word.index: word for word in baseline}
        changed_by_index = {word.index: word for word in changed}
        restored_by_index = {word.index: word for word in restored}
        restore_differences = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != restored_by_index[address].raw_u16
        )
        if restore_differences:
            restoration_method = "operation_42_inverse_plus_saved_slot_recall"
            self.select_preset(recovery_slot)
            self.sleep(0.2)
            restored = self.read_live_parameter_words()
            restored_by_index = {word.index: word for word in restored}
            restore_differences = tuple(
                address
                for address in before_by_index
                if before_by_index[address].raw_u16
                != restored_by_index[address].raw_u16
            )

        changes = tuple(
            DirectLiveTableChange(
                index=address,
                before_raw_u16=before_by_index[address].raw_u16,
                after_raw_u16=changed_by_index[address].raw_u16,
                restored_raw_u16=restored_by_index[address].raw_u16,
            )
            for address in before_by_index
            if before_by_index[address].raw_u16
            != changed_by_index[address].raw_u16
        )
        report = DirectGlobalWriteProbeReport(
            name=name,
            code=code,
            before_value=before_value,
            target_value=target_value,
            readback_value=readback_value,
            restored_value=restored_value,
            target_verified=readback_value == target_value,
            restore_verified=(
                restored_value == before_value and not restore_differences
            ),
            restoration_method=restoration_method,
            recovery_slot=recovery_slot,
            changes=changes,
            changed_after_restore_addresses=restore_differences,
        )
        if not report.target_verified or not report.restore_verified:
            raise MicroFreakMidiError(
                "guarded global-setting probe failed verification: "
                f"target_verified={report.target_verified}, "
                f"restored_value={restored_value}, expected={before_value}, "
                f"live_differences={[f'0x{x:04x}' for x in restore_differences]}"
            )
        return report

    def write_global_setting(
        self, name: str, target_value: int, backup_path: str | Path
    ) -> DirectGlobalWriteReport:
        """Persist one audited global value and verify operation-43 readback.

        A JSON backup is written before mutation. Settings without an audited
        value domain are refused; the raw probe remains the explicit research
        path for those fields. Failed readback triggers an inverse write and
        independently verifies restoration before the error is returned.
        """

        try:
            code = MICROFREAK_GLOBAL_CODES[name]
        except KeyError as exc:
            choices = ", ".join(sorted(MICROFREAK_GLOBAL_CODES))
            raise ValueError(f"unknown MicroFreak global {name!r}; supported: {choices}") from exc
        spec = MICROFREAK_GLOBAL_VALUE_SPECS.get(name)
        if spec is None:
            raise ValueError(
                f"{name} has no audited value domain; use the reversible raw probe"
            )
        if target_value not in spec.allowed_values:
            allowed = ", ".join(str(value) for value in spec.allowed_values)
            raise ValueError(f"{name} target must be one of: {allowed}")

        before_reads = (
            self.read_global_codes((code,))[code],
            self.read_global_codes((code,))[code],
        )
        if before_reads[0] != before_reads[1]:
            raise MicroFreakMidiError(
                f"unstable {name} preflight: {before_reads[0]} then {before_reads[1]}"
            )
        before_value = before_reads[0]
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_text(
            json.dumps(
                {
                    "schema_version": "microfreak-global-backup/1",
                    "device": "microfreak",
                    "name": name,
                    "code": code,
                    "before": decode_microfreak_global(name, before_value),
                    "target": decode_microfreak_global(name, target_value),
                },
                indent=2,
            )
            + "\n"
        )

        self._write_global_code(code, target_value)
        self.sleep(0.1)
        readback_value = self.read_global_codes((code,))[code]
        if readback_value != target_value:
            self._write_global_code(code, before_value)
            self.sleep(0.1)
            restored = self.read_global_codes((code,))[code]
            if restored != before_value:
                raise MicroFreakMidiError(
                    f"{name} target readback failed ({readback_value}) and "
                    f"automatic restore failed ({restored}, expected {before_value})"
                )
            raise MicroFreakMidiError(
                f"{name} target readback failed ({readback_value}, expected "
                f"{target_value}); original {before_value} restored exactly"
            )
        return DirectGlobalWriteReport(
            name=name,
            code=code,
            backup_path=str(backup),
            before_value=before_value,
            target_value=target_value,
            readback_value=readback_value,
            exact_readback=True,
        )

    def _receive_raw_sysex(
        self, input_port: Any, on_non_sysex: Any | None = None
    ) -> bytes:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            message = input_port.poll()
            if message is None:
                self.sleep(0.001)
                continue
            if getattr(message, "type", None) == "sysex":
                return bytes(message.data)
            if on_non_sysex is not None:
                on_non_sysex(message)
        raise MicroFreakMidiError("timed out waiting for a MicroFreak SysEx reply")

    def read_preset(self, slot: int) -> MicroFreakPreset:
        if not 1 <= slot <= 512:
            raise ValueError("MicroFreak preset slot must be 1..512")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            return self._read_preset_open(input_port, output_port, slot)

    def select_preset(self, slot: int) -> tuple[int, int]:
        """Select a saved preset using MIDI bank-select and program-change.

        This changes only the active live patch. It does not write preset
        storage, and standard MIDI provides no acknowledgement to verify the
        resulting selection.
        """
        if not 1 <= slot <= 512:
            raise ValueError("MicroFreak preset slot must be 1..512")
        zero_based = slot - 1
        bank, program = divmod(zero_based, 128)
        port_name = self.resolve_port()
        with self.midi.open_output(port_name) as output_port:
            output_port.send(
                self.midi.Message(
                    "control_change", channel=0, control=0, value=bank
                )
            )
            output_port.send(
                self.midi.Message("program_change", channel=0, program=program)
            )
        return bank, program

    @staticmethod
    def _sequence_playback_event(
        message: Any,
        *,
        clock_sent: int,
        started_at: float,
    ) -> DirectSequencePlaybackEvent:
        data = tuple(int(value) for value in getattr(message, "data", ()))
        return DirectSequencePlaybackEvent(
            clock_sent=clock_sent,
            elapsed_seconds=max(0.0, time.monotonic() - started_at),
            message_type=str(getattr(message, "type", "unknown")),
            channel=getattr(message, "channel", None),
            note=getattr(message, "note", None),
            velocity=getattr(message, "velocity", None),
            control=getattr(message, "control", None),
            value=getattr(message, "value", None),
            pitch=getattr(message, "pitch", None),
            data=data,
            host_echo_candidate=getattr(message, "type", None)
            in {"clock", "start", "stop"},
        )

    def capture_sequence_playback_events(
        self,
        *,
        clock_count: int = 192,
        clock_interval_seconds: float = 0.01,
        settle_seconds: float = 0.2,
        trigger_note: int = 60,
        velocity: int = 80,
        channel: int = 1,
    ) -> tuple[DirectSequencePlaybackEvent, ...]:
        """Observe the active pattern through the device's own MIDI output.

        The caller must put Clock Source in USB mode and ensure the desired
        sequence is enabled. This method performs no preset or global write;
        it sends Start, Clock, one held transposition note, then always sends
        Note Off and Stop. The higher-level CLI provides clock backup/restore
        and complete live-table recovery checks.
        """

        if not 1 <= clock_count <= 8192:
            raise ValueError("MicroFreak playback clock count must be 1..8192")
        if clock_interval_seconds < 0 or settle_seconds < 0:
            raise ValueError("MicroFreak playback delays cannot be negative")
        if not 0 <= trigger_note <= 127:
            raise ValueError("MicroFreak playback trigger note must be 0..127")
        if not 1 <= velocity <= 127:
            raise ValueError("MicroFreak playback velocity must be 1..127")
        if not 1 <= channel <= 16:
            raise ValueError("MicroFreak playback channel must be 1..16")

        port_name = self.resolve_port()
        events: list[DirectSequencePlaybackEvent] = []
        started_at = time.monotonic()
        clock_sent = 0

        def drain(input_port: Any) -> None:
            while True:
                message = input_port.poll()
                if message is None:
                    return
                events.append(
                    self._sequence_playback_event(
                        message,
                        clock_sent=clock_sent,
                        started_at=started_at,
                    )
                )

        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            drain(input_port)
            output_port.send(self.midi.Message("start"))
            output_port.send(
                self.midi.Message(
                    "note_on",
                    channel=channel - 1,
                    note=trigger_note,
                    velocity=velocity,
                )
            )
            try:
                for clock_sent in range(1, clock_count + 1):
                    output_port.send(self.midi.Message("clock"))
                    self.sleep(clock_interval_seconds)
                    drain(input_port)
                self.sleep(settle_seconds)
                drain(input_port)
            finally:
                output_port.send(
                    self.midi.Message(
                        "note_off",
                        channel=channel - 1,
                        note=trigger_note,
                        velocity=0,
                    )
                )
                output_port.send(self.midi.Message("stop"))
                self.sleep(settle_seconds)
                drain(input_port)
        return tuple(events)

    def capture_sequence_live_trace(
        self,
        *,
        clock_count: int = 192,
        snapshot_every_clocks: int = 6,
        clock_interval_seconds: float = 0.01,
        settle_seconds: float = 0.2,
        trigger_note: int = 60,
        velocity: int = 80,
        channel: int = 1,
        snapshot_addresses: Iterable[int] | None = None,
    ) -> DirectSequenceLiveTrace:
        """Sample operation-41 live words while externally clocking a sequence.

        External clock is deliberately paused for each operation-41 snapshot,
        so every table is associated with an exact number of clocks sent. MIDI
        events encountered before or during the SysEx reads are retained. The
        caller remains responsible for selecting/recovering a preset and for
        backing up and restoring Clock Source; the CLI supplies those guards.
        """

        if not 1 <= clock_count <= 8192:
            raise ValueError("MicroFreak playback clock count must be 1..8192")
        if not 1 <= snapshot_every_clocks <= clock_count:
            raise ValueError(
                "sequence live snapshot interval must be 1..clock_count"
            )
        snapshot_count = (clock_count + snapshot_every_clocks - 1) // snapshot_every_clocks
        if snapshot_count > 128:
            raise ValueError("sequence live trace is limited to 128 snapshots")
        if clock_interval_seconds < 0 or settle_seconds < 0:
            raise ValueError("MicroFreak playback delays cannot be negative")
        if not 0 <= trigger_note <= 127:
            raise ValueError("MicroFreak playback trigger note must be 0..127")
        if not 1 <= velocity <= 127:
            raise ValueError("MicroFreak playback velocity must be 1..127")
        if not 1 <= channel <= 16:
            raise ValueError("MicroFreak playback channel must be 1..16")
        if snapshot_addresses is None:
            addresses = tuple(
                (group << 8) | word
                for group in range(LIVE_PARAMETER_GROUPS)
                for word in range(LIVE_PARAMETER_WORDS_PER_GROUP)
            )
        else:
            addresses = tuple(dict.fromkeys(snapshot_addresses))
            if not addresses:
                raise ValueError("sequence live trace needs at least one address")
            invalid = [
                address
                for address in addresses
                if not isinstance(address, int)
                or not 0 <= address <= 0xFFFF
                or address >> 8 >= LIVE_PARAMETER_GROUPS
                or address & 0xFF >= LIVE_PARAMETER_WORDS_PER_GROUP
            ]
            if invalid:
                raise ValueError(
                    "invalid operation-41 live address: "
                    + ", ".join(
                        f"0x{address:04x}" if isinstance(address, int) else repr(address)
                        for address in invalid
                    )
                )

        port_name = self.resolve_port()
        self.sequence = 0
        events: list[DirectSequencePlaybackEvent] = []
        snapshots: list[DirectSequenceLiveSnapshot] = []
        started_at = time.monotonic()
        clock_sent = 0

        def record(message: Any) -> None:
            events.append(
                self._sequence_playback_event(
                    message,
                    clock_sent=clock_sent,
                    started_at=started_at,
                )
            )

        def drain(input_port: Any) -> None:
            while True:
                message = input_port.poll()
                if message is None:
                    return
                if getattr(message, "type", None) != "sysex":
                    record(message)

        def read_snapshot(
            input_port: Any, output_port: Any
        ) -> tuple[DirectLiveParameterWord, ...]:
            return tuple(
                self._read_live_parameter_word_session(
                    input_port,
                    output_port,
                    address,
                    on_non_sysex=record,
                )
                for address in addresses
            )

        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            output_port.send(self._next_request(0x1C))
            self.sleep(0.05)
            try:
                snapshots.append(
                    DirectSequenceLiveSnapshot(
                        clock_sent=0,
                        words=read_snapshot(input_port, output_port),
                    )
                )
                output_port.send(self.midi.Message("start"))
                output_port.send(
                    self.midi.Message(
                        "note_on",
                        channel=channel - 1,
                        note=trigger_note,
                        velocity=velocity,
                    )
                )
                try:
                    for clock_sent in range(1, clock_count + 1):
                        output_port.send(self.midi.Message("clock"))
                        self.sleep(clock_interval_seconds)
                        drain(input_port)
                        if (
                            clock_sent % snapshot_every_clocks == 0
                            or clock_sent == clock_count
                        ):
                            snapshots.append(
                                DirectSequenceLiveSnapshot(
                                    clock_sent=clock_sent,
                                    words=read_snapshot(input_port, output_port),
                                )
                            )
                    self.sleep(settle_seconds)
                    drain(input_port)
                finally:
                    output_port.send(
                        self.midi.Message(
                            "note_off",
                            channel=channel - 1,
                            note=trigger_note,
                            velocity=0,
                        )
                    )
                    output_port.send(self.midi.Message("stop"))
                    self.sleep(settle_seconds)
                    drain(input_port)
            finally:
                output_port.send(self._next_request(0x1D))
        return DirectSequenceLiveTrace(tuple(events), tuple(snapshots))

    def read_preset_bank(self) -> list[tuple[int, MicroFreakPreset]]:
        """Read all 512 slots while keeping one paired MIDI connection open."""
        port_name = self.resolve_port()
        self.sequence = 0
        result = []
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            for slot in range(1, 513):
                result.append((slot, self._read_preset_open(input_port, output_port, slot)))
        return result

    def read_initializer_template(self) -> MicroFreakPreset:
        """Read the firmware-owned Init pseudo-slot at bank 4/program 0.

        Firmware 5.0.0.36 returns a normal 35-byte header and full 4,672-byte
        body at this address even though saved storage ends at bank 3. A
        bounded live-CC experiment confirmed that the bytes do not track the
        active edit buffer. This is therefore exposed as an editable template,
        not as current-patch state.
        """
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            header = self._exchange(
                input_port,
                output_port,
                0x19,
                bytes((INITIALIZER_TEMPLATE_BANK, INITIALIZER_TEMPLATE_PROGRAM, 0)),
                0x52,
                PRESET_HEADER_LENGTH,
            )
            if header[:2] != bytes(
                (INITIALIZER_TEMPLATE_BANK, INITIALIZER_TEMPLATE_PROGRAM)
            ):
                raise MicroFreakMidiError(
                    "MicroFreak Init pseudo-slot did not echo bank 4/program 0"
                )
            self._exchange(
                input_port,
                output_port,
                0x19,
                bytes((INITIALIZER_TEMPLATE_BANK, INITIALIZER_TEMPLATE_PROGRAM, 1)),
                0x15,
                0,
            )
            payload = b"".join(
                self._exchange(
                    input_port,
                    output_port,
                    0x18,
                    b"\x00",
                    0x17 if index == PRESET_PARTS - 1 else 0x16,
                    PRESET_PART_LENGTH,
                )
                for index in range(PRESET_PARTS)
            )
        return MicroFreakPreset(
            name=header[12:26].split(b"\x00", 1)[0].decode(
                "utf-8", errors="replace"
            ),
            category_id=header[10],
            init=1 if header[3] & 0x08 else 0,
            p1=header[11],
            payload=payload,
        )

    def _read_sample_header_session(
        self, input_port: Any, output_port: Any, slot: int
    ) -> DirectSampleHeader:
        zero_based = slot - 1
        self._exchange(
            input_port, output_port, 0x5B, bytes((zero_based, 0, 0)), 0x15, 0
        )
        packed = self._exchange(
            input_port,
            output_port,
            0x18,
            b"\x00",
            0x16,
            WAVE_PACKET_MIDI_BYTES,
        )
        header = unpack_8bit_midi(packed)
        if len(header) != SAMPLE_HEADER_RAW_BYTES:
            raise MicroFreakMidiError(
                f"expected {SAMPLE_HEADER_RAW_BYTES} sample header bytes, "
                f"received {len(header)}"
            )
        name = header[10:23].split(b"\x00", 1)[0].decode(
            "utf-8", errors="replace"
        )
        size_bytes = int.from_bytes(header[4:8], "little")
        return DirectSampleHeader(
            slot=slot,
            device_id=header[23],
            name=name,
            address=int.from_bytes(header[0:4], "little"),
            size_bytes=size_bytes,
            checksum=int.from_bytes(header[8:10], "little"),
            empty=size_bytes == 0,
            raw_header_hex=header.hex(),
        )

    def read_sample_header(self, slot: int) -> DirectSampleHeader:
        """Read one sample-directory entry without reading or changing audio."""
        if not 1 <= slot <= SAMPLE_SLOTS:
            raise ValueError(f"MicroFreak sample slot must be 1..{SAMPLE_SLOTS}")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            return self._read_sample_header_session(input_port, output_port, slot)

    def read_sample_inventory(self) -> list[DirectSampleHeader]:
        """Read all 128 sample headers over one paired MIDI connection."""
        port_name = self.resolve_port()
        self.sequence = 0
        result = []
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            for slot in range(1, SAMPLE_SLOTS + 1):
                result.append(
                    self._read_sample_header_session(input_port, output_port, slot)
                )
        return result

    def read_sample_storage_stats(self) -> DirectSampleStorageStats:
        """Read the firmware's sample-memory utilization counters."""

        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            output_port.send(self._next_request(0x1C))
            self.sleep(0.05)
            try:
                output_port.send(self._next_request(0x47, b"\x0a"))
                payload = self._decode_alt_reply(
                    self._receive_raw_sysex(input_port), 0x48, 9
                )
            finally:
                output_port.send(self._next_request(0x1D))
        lsb = payload[6] | (0x80 if payload[2] & 0x08 else 0)
        msb = payload[7] | (0x80 if payload[2] & 0x04 else 0)
        used_ms = ((msb << 8) | lsb) << 2
        free_ms = max(0, SAMPLE_TOTAL_CAPACITY_MS - used_ms)
        return DirectSampleStorageStats(
            used_milliseconds=used_ms,
            free_milliseconds=free_ms,
            estimated_free_bytes=free_ms * 64,
            capacity_bytes=SAMPLE_MEMORY_CAPACITY_BYTES,
            raw_payload_hex=payload.hex(),
        )

    @staticmethod
    def _inspect_status_record_reply(
        selector: int, request_sequence: int, raw_reply: bytes
    ) -> DirectStatusRecordReply:
        """Describe a raw reply without requiring either known wire framing."""

        raw = bytes(raw_reply)
        if raw[:1] == b"\xF0":
            raw = raw[1:]
        if raw[-1:] == b"\xF7":
            raw = raw[:-1]
        prefix = raw[:5]
        reply_sequence = raw[5] if len(raw) > 5 else None
        declared_length = raw[6] if len(raw) > 6 else None
        operation = raw[7] if len(raw) > 7 else None
        payload = raw[8:] if len(raw) > 8 else b""
        length_matches = declared_length is not None and declared_length == len(payload)
        unpacked_record: bytes | None = None
        if (
            prefix == bytes.fromhex("00 20 6b 07 7f")
            and operation == 0x48
            and length_matches
            and len(payload) == 9
            and payload[:2] == bytes((0x06, 0x7D))
        ):
            try:
                unpacked_record = unpack_six_byte_state_record(payload[2:])
            except ValueError:
                pass
        record_kind = None
        record_selector = None
        value_u16 = None
        value_u32 = None
        if unpacked_record is not None and unpacked_record[0] == 0xFF:
            record_kind = unpacked_record[1]
            if record_kind == 0x19 and unpacked_record[3] == 0:
                record_selector = unpacked_record[2]
                value_u16 = int.from_bytes(unpacked_record[4:6], "big")
            elif record_kind in (0x1B, 0x1C, 0x1D):
                value_u32 = int.from_bytes(unpacked_record[2:6], "big")
        return DirectStatusRecordReply(
            selector=selector,
            request_sequence=request_sequence,
            raw_sysex_hex=raw.hex(),
            raw_length=len(raw),
            prefix_hex=prefix.hex(),
            reply_sequence=reply_sequence,
            declared_length=declared_length,
            operation=operation,
            payload_hex=payload.hex(),
            declared_length_matches=length_matches,
            unpacked_record_hex=(
                unpacked_record.hex() if unpacked_record is not None else None
            ),
            record_kind=record_kind,
            record_selector=record_selector,
            value_u16=value_u16,
            value_u32=value_u32,
        )

    def capture_status_state_record_replies(
        self,
        selectors: Iterable[int] = MICROFREAK_STATUS_RECORD_SELECTORS,
    ) -> DirectStatusRecordCaptureReport:
        """Capture kind-0x13 replies and prove patch/global state stayed exact.

        Firmware analysis classifies these seven selectors as getters. The raw
        wire reply is retained before applying the likely seven-byte packed
        record interpretation that explains the earlier six-byte decoder
        rejection.
        """

        selected = tuple(dict.fromkeys(selectors))
        if not selected:
            raise ValueError("at least one MicroFreak status selector is required")
        invalid = [
            selector
            for selector in selected
            if selector not in MICROFREAK_STATUS_RECORD_SELECTORS
        ]
        if invalid:
            raise ValueError(f"unsupported MicroFreak status selectors: {invalid}")

        globals_before = self.read_global_settings()
        port_name = self.resolve_port()
        self.sequence = 0
        baseline: list[DirectLiveParameterWord] = []
        after: list[DirectLiveParameterWord] = []
        replies: list[DirectStatusRecordReply] = []
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            output_port.send(self._next_request(0x1C))
            self.sleep(0.05)
            try:
                baseline = self._read_live_parameter_table_session(
                    input_port, output_port
                )
                for selector in selected:
                    request_sequence = self.sequence
                    request = encode_status_state_record_request(selector)
                    output_port.send(self._next_request(0x49, request))
                    raw_reply = self._receive_raw_sysex(input_port)
                    replies.append(
                        self._inspect_status_record_reply(
                            selector, request_sequence, raw_reply
                        )
                    )
                after = self._read_live_parameter_table_session(
                    input_port, output_port
                )
            finally:
                output_port.send(self._next_request(0x1D))

        globals_after = self.read_global_settings()
        before_by_index = {word.index: word.raw_u16 for word in baseline}
        after_by_index = {word.index: word.raw_u16 for word in after}
        changed_live = tuple(
            index
            for index in before_by_index
            if before_by_index[index] != after_by_index.get(index)
        )
        changed_globals = tuple(
            (name, globals_before[name], globals_after[name])
            for name in globals_before
            if globals_before[name] != globals_after.get(name)
        )
        return DirectStatusRecordCaptureReport(
            replies=tuple(replies),
            live_table_exact=not changed_live,
            changed_live_addresses=changed_live,
            global_settings_exact=not changed_globals,
            changed_global_settings=changed_globals,
        )

    def _read_live_parameter_word_session(
        self,
        input_port: Any,
        output_port: Any,
        index: int,
        on_non_sysex: Any | None = None,
    ) -> DirectLiveParameterWord:
        output_port.send(self._next_request(0x41, encode_control_index_payload(index)))
        payload = self._decode_alt_reply(
            self._receive_raw_sysex(input_port, on_non_sysex), 0x40, 5
        )
        returned_index, value = decode_control_word_payload(payload)
        if returned_index != index:
            raise MicroFreakMidiError(
                f"requested live parameter 0x{index:04x}, received "
                f"0x{returned_index:04x}"
            )
        return DirectLiveParameterWord(
            index=index,
            raw_u16=value,
            signed_i16=value - 0x10000 if value & 0x8000 else value,
            raw_payload_hex=payload.hex(),
        )

    def _read_live_parameter_table_session(
        self,
        input_port: Any,
        output_port: Any,
        on_non_sysex: Any | None = None,
    ) -> list[DirectLiveParameterWord]:
        return [
            self._read_live_parameter_word_session(
                input_port,
                output_port,
                (group << 8) | word,
                on_non_sysex,
            )
            for group in range(LIVE_PARAMETER_GROUPS)
            for word in range(LIVE_PARAMETER_WORDS_PER_GROUP)
        ]

    def read_live_parameter_words(
        self, start: int = 0, count: int = LIVE_PARAMETER_WORDS
    ) -> list[DirectLiveParameterWord]:
        """Read a bounded range of the firmware's 24 by 16 active-word table.

        This is a read-only operation. The 384-word bound comes from the
        firmware object's 24-entry pointer table and its 16-bit-per-group
        validity masks; hardware replies are still checked index by index.
        """

        if not 0 <= start < LIVE_PARAMETER_WORDS:
            raise ValueError(
                f"live parameter ordinal start must be 0..{LIVE_PARAMETER_WORDS - 1}"
            )
        if not 1 <= count <= LIVE_PARAMETER_WORDS - start:
            raise ValueError(
                f"live parameter count must be 1..{LIVE_PARAMETER_WORDS - start}"
            )
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            output_port.send(self._next_request(0x1C))
            self.sleep(0.05)
            try:
                return [
                    self._read_live_parameter_word_session(
                        input_port,
                        output_port,
                        ((ordinal // LIVE_PARAMETER_WORDS_PER_GROUP) << 8)
                        | (ordinal % LIVE_PARAMETER_WORDS_PER_GROUP),
                    )
                    for ordinal in range(start, start + count)
                ]
            finally:
                output_port.send(self._next_request(0x1D))

    def probe_live_control_change(
        self,
        parameter: str,
        cc: int,
        target_value: int,
        restore_value: int,
        recovery_slot: int,
        *,
        channel: int = 1,
    ) -> DirectLiveCcProbeReport:
        """Send one CC and compare the complete active table before/after.

        The caller supplies the intended inverse CC value. If that does not
        reproduce the baseline exactly, the explicitly supplied saved preset
        is recalled and compared against the same 384-word baseline. This
        never sends a store/save operation.
        """

        if not parameter:
            raise ValueError("MIDI CC probe parameter name cannot be empty")
        if not 0 <= cc <= 127:
            raise ValueError("MIDI CC number must be 0..127")
        if not 0 <= target_value <= 127 or not 0 <= restore_value <= 127:
            raise ValueError("MIDI CC target and restore values must be 0..127")
        if not 1 <= channel <= 16:
            raise ValueError("MIDI channel must be 1..16")
        if not 1 <= recovery_slot <= 512:
            raise ValueError("MicroFreak recovery slot must be 1..512")

        port_name = self.resolve_port()
        self.sequence = 0
        baseline: list[DirectLiveParameterWord] | None = None
        changed: list[DirectLiveParameterWord] | None = None
        restored: list[DirectLiveParameterWord] | None = None
        restoration_method = "inverse_midi_cc"
        try:
            with self.midi.open_input(port_name) as input_port, self.midi.open_output(
                port_name
            ) as output_port:
                while input_port.poll() is not None:
                    pass
                output_port.send(self._next_request(0x1C))
                self.sleep(0.05)
                try:
                    baseline = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    output_port.send(
                        self.midi.Message(
                            "control_change",
                            channel=channel - 1,
                            control=cc,
                            value=target_value,
                        )
                    )
                    self.sleep(0.05)
                    changed = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    output_port.send(
                        self.midi.Message(
                            "control_change",
                            channel=channel - 1,
                            control=cc,
                            value=restore_value,
                        )
                    )
                    self.sleep(0.05)
                    restored = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                finally:
                    output_port.send(self._next_request(0x1D))
        except Exception:
            if baseline is not None:
                self.select_preset(recovery_slot)
                self.sleep(0.2)
            raise

        assert baseline is not None and changed is not None and restored is not None
        before_by_index = {word.index: word for word in baseline}
        changed_by_index = {word.index: word for word in changed}
        restored_by_index = {word.index: word for word in restored}
        restore_differences = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != restored_by_index[address].raw_u16
        )
        if restore_differences:
            restoration_method = "saved_slot_recall"
            self.select_preset(recovery_slot)
            self.sleep(0.2)
            restored = self.read_live_parameter_words()
            restored_by_index = {word.index: word for word in restored}
            restore_differences = tuple(
                address
                for address in before_by_index
                if before_by_index[address].raw_u16
                != restored_by_index[address].raw_u16
            )

        changes = tuple(
            DirectLiveTableChange(
                index=address,
                before_raw_u16=before_by_index[address].raw_u16,
                after_raw_u16=changed_by_index[address].raw_u16,
                restored_raw_u16=restored_by_index[address].raw_u16,
            )
            for address in before_by_index
            if before_by_index[address].raw_u16
            != changed_by_index[address].raw_u16
        )
        report = DirectLiveCcProbeReport(
            parameter=parameter,
            cc=cc,
            target_value=target_value,
            restore_value=restore_value,
            target_effect_observed=bool(changes),
            restore_verified=not restore_differences,
            restoration_method=restoration_method,
            recovery_slot=recovery_slot,
            changes=changes,
            changed_after_restore_addresses=restore_differences,
        )
        if not report.restore_verified:
            raise MicroFreakMidiError(
                "guarded MIDI-CC probe failed exact recovery: "
                f"differences={[f'0x{x:04x}' for x in restore_differences]}"
            )
        return report

    def probe_live_parameter_word_write(
        self, index: int, target_raw_u16: int, recovery_slot: int
    ) -> DirectLiveParameterWriteProbeReport:
        """Write one live word, read the whole table, and restore exactly.

        This never stores a preset. It is intentionally limited to addresses
        already correlated with documented MIDI CC behavior. The complete
        384-word table is compared after both the target and restoration so a
        setter side effect or alias is visible rather than silently ignored.
        """

        semantic = MICROFREAK_LIVE_WORD_SEMANTICS.get(index)
        if semantic is None:
            raise ValueError(
                f"live parameter address 0x{index:04x} is not hardware-correlated"
            )
        if not 0 <= target_raw_u16 <= 0x7FFF:
            raise ValueError("guarded live target must be 0..32767")
        if not 1 <= recovery_slot <= 512:
            raise ValueError("MicroFreak recovery slot must be 1..512")
        target_payload = encode_control_word_request_payload(index, target_raw_u16)

        port_name = self.resolve_port()
        self.sequence = 0
        baseline: list[DirectLiveParameterWord] | None = None
        changed: list[DirectLiveParameterWord] | None = None
        restored: list[DirectLiveParameterWord] | None = None
        restoration_method = "operation_40"
        try:
            with self.midi.open_input(port_name) as input_port, self.midi.open_output(
                port_name
            ) as output_port:
                while input_port.poll() is not None:
                    pass
                output_port.send(self._next_request(0x1C))
                self.sleep(0.05)
                try:
                    baseline = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    before_by_index = {word.index: word for word in baseline}
                    output_port.send(self._next_request(0x40, target_payload))
                    self.sleep(0.05)
                    changed = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    try:
                        restore_payload = encode_control_word_request_payload(
                            index, before_by_index[index].raw_u16
                        )
                    except ValueError:
                        restore_payload = None
                    if restore_payload is not None:
                        output_port.send(self._next_request(0x40, restore_payload))
                        self.sleep(0.05)
                        restored = self._read_live_parameter_table_session(
                            input_port, output_port
                        )
                finally:
                    output_port.send(self._next_request(0x1D))
        except Exception:
            if baseline is not None:
                self.select_preset(recovery_slot)
                self.sleep(0.2)
            raise

        assert baseline is not None and changed is not None
        before_by_index = {word.index: word for word in baseline}
        changed_by_index = {word.index: word for word in changed}
        if restored is not None:
            operation_40_restored = {word.index: word for word in restored}
            operation_40_restore_differences = tuple(
                address
                for address in before_by_index
                if before_by_index[address].raw_u16
                != operation_40_restored[address].raw_u16
            )
        else:
            operation_40_restore_differences = tuple(before_by_index)
        if operation_40_restore_differences:
            restoration_method = "saved_slot_recall"
            self.select_preset(recovery_slot)
            self.sleep(0.2)
            restored = self.read_live_parameter_words()

        assert restored is not None
        restored_by_index = {word.index: word for word in restored}
        changed_addresses = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != changed_by_index[address].raw_u16
        )
        restore_differences = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != restored_by_index[address].raw_u16
        )
        report = DirectLiveParameterWriteProbeReport(
            index=index,
            parameter=semantic["parameter"],
            before_raw_u16=before_by_index[index].raw_u16,
            target_raw_u16=target_raw_u16,
            readback_raw_u16=changed_by_index[index].raw_u16,
            restored_raw_u16=restored_by_index[index].raw_u16,
            target_verified=changed_by_index[index].raw_u16 == target_raw_u16,
            restore_verified=not restore_differences,
            restoration_method=restoration_method,
            recovery_slot=recovery_slot,
            changed_after_addresses=changed_addresses,
            changed_after_restore_addresses=restore_differences,
        )
        if not report.target_verified or not report.restore_verified:
            raise MicroFreakMidiError(
                "guarded operation-40 probe failed verification: "
                f"target_verified={report.target_verified}, "
                f"restore_verified={report.restore_verified}, "
                f"restore_differences={[f'0x{x:04x}' for x in restore_differences]}"
            )
        return report

    def probe_live_parameter_state_record_write(
        self, index: int, target_raw_u16: int, recovery_slot: int
    ) -> DirectLiveParameterWriteProbeReport:
        """Probe operation-49/6 kind 2 with full-table readback and restore."""

        semantic = MICROFREAK_LIVE_WORD_SEMANTICS.get(index)
        if semantic is None:
            raise ValueError(
                f"live parameter address 0x{index:04x} is not hardware-correlated"
            )
        if not 0 <= target_raw_u16 <= 0x7FFF:
            raise ValueError("guarded live target must be 0..32767")
        if not 1 <= recovery_slot <= 512:
            raise ValueError("MicroFreak recovery slot must be 1..512")
        target_payload = encode_live_parameter_state_record_request(
            index, target_raw_u16
        )

        port_name = self.resolve_port()
        self.sequence = 0
        baseline: list[DirectLiveParameterWord] | None = None
        changed: list[DirectLiveParameterWord] | None = None
        restored: list[DirectLiveParameterWord] | None = None
        restoration_method = "operation_49_internal_record"
        try:
            with self.midi.open_input(port_name) as input_port, self.midi.open_output(
                port_name
            ) as output_port:
                while input_port.poll() is not None:
                    pass
                output_port.send(self._next_request(0x1C))
                self.sleep(0.05)
                try:
                    baseline = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    before_by_index = {word.index: word for word in baseline}
                    output_port.send(self._next_request(0x49, target_payload))
                    self.sleep(0.05)
                    changed = self._read_live_parameter_table_session(
                        input_port, output_port
                    )
                    before_value = before_by_index[index].raw_u16
                    if before_value <= 0x7FFF:
                        restore_payload = encode_live_parameter_state_record_request(
                            index, before_value
                        )
                        output_port.send(self._next_request(0x49, restore_payload))
                        self.sleep(0.05)
                        restored = self._read_live_parameter_table_session(
                            input_port, output_port
                        )
                finally:
                    output_port.send(self._next_request(0x1D))
        except Exception:
            if baseline is not None:
                self.select_preset(recovery_slot)
                self.sleep(0.2)
            raise

        assert baseline is not None and changed is not None
        before_by_index = {word.index: word for word in baseline}
        changed_by_index = {word.index: word for word in changed}
        if restored is not None:
            candidate_restored = {word.index: word for word in restored}
            candidate_differences = tuple(
                address
                for address in before_by_index
                if before_by_index[address].raw_u16
                != candidate_restored[address].raw_u16
            )
        else:
            candidate_differences = tuple(before_by_index)
        if candidate_differences:
            restoration_method = "saved_slot_recall"
            self.select_preset(recovery_slot)
            self.sleep(0.2)
            restored = self.read_live_parameter_words()

        assert restored is not None
        restored_by_index = {word.index: word for word in restored}
        changed_addresses = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != changed_by_index[address].raw_u16
        )
        restore_differences = tuple(
            address
            for address in before_by_index
            if before_by_index[address].raw_u16
            != restored_by_index[address].raw_u16
        )
        report = DirectLiveParameterWriteProbeReport(
            index=index,
            parameter=semantic["parameter"],
            before_raw_u16=before_by_index[index].raw_u16,
            target_raw_u16=target_raw_u16,
            readback_raw_u16=changed_by_index[index].raw_u16,
            restored_raw_u16=restored_by_index[index].raw_u16,
            target_verified=changed_by_index[index].raw_u16 == target_raw_u16,
            restore_verified=not restore_differences,
            restoration_method=restoration_method,
            recovery_slot=recovery_slot,
            changed_after_addresses=changed_addresses,
            changed_after_restore_addresses=restore_differences,
        )
        if not report.target_verified or not report.restore_verified:
            raise MicroFreakMidiError(
                "guarded operation-49/6 probe failed verification: "
                f"target_verified={report.target_verified}, "
                f"restore_verified={report.restore_verified}, "
                f"restore_differences={[f'0x{x:04x}' for x in restore_differences]}"
            )
        return report

    def read_live_parameter_word(self, index: int) -> DirectLiveParameterWord:
        """Read one group/slot-addressed word (0x0000 through 0x170f)."""

        group, word = index >> 8, index & 0xFF
        if not (
            0 <= group < LIVE_PARAMETER_GROUPS
            and 0 <= word < LIVE_PARAMETER_WORDS_PER_GROUP
        ):
            raise ValueError(
                "live parameter address must have group 0x00..0x17 and "
                "word 0x00..0x0f"
            )
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            output_port.send(self._next_request(0x1C))
            self.sleep(0.05)
            try:
                return self._read_live_parameter_word_session(
                    input_port, output_port, index
                )
            finally:
                output_port.send(self._next_request(0x1D))

    def read_live_structured_fields(self) -> list[DirectLiveStructuredField]:
        """Read all hardware-correlated tagged fields in one live-table pass."""

        fields, _ = self.read_live_structured_snapshot()
        return fields

    def read_live_structured_snapshot(
        self,
    ) -> tuple[list[DirectLiveStructuredField], DirectLiveParameterWord]:
        """Read named current fields and oscillator type in one 384-word pass."""

        words = {word.index: word for word in self.read_live_parameter_words()}
        result = []
        for name, addresses in MICROFREAK_STRUCTURED_LIVE_WORDS.items():
            values = tuple(words[address].raw_u16 for address in addresses)
            raw = values[0]
            result.append(
                DirectLiveStructuredField(
                    name=name,
                    raw_u16=raw,
                    signed_i16=raw - 0x10000 if raw & 0x8000 else raw,
                    addresses=addresses,
                    alias_values=values,
                    aliases_match=len(set(values)) == 1,
                    evidence=MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE.get(
                        name, MICROFREAK_STRUCTURED_LIVE_EVIDENCE
                    ),
                )
            )
        return result, words[0x0000]

    def read_sample(self, slot: int) -> DirectSample:
        """Read one sample body through the firmware's sequential block stream.

        Operation 5B selects the sample and resets its stream. Operation 59
        then exposes successive 4 KiB blocks; each block uses the same
        operation-18 packet pull as a wavetable part. The last block is
        truncated to the exact byte length stored in the directory header.
        This path sends no write, erase, allocation, or finalize operation.
        """
        if not 1 <= slot <= SAMPLE_SLOTS:
            raise ValueError(f"MicroFreak sample slot must be 1..{SAMPLE_SLOTS}")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            header = self._read_sample_header_session(
                input_port, output_port, slot
            )
            if header.empty:
                raise MicroFreakMidiError(f"MicroFreak sample slot {slot} is empty")
            output = bytearray()
            zero_based = slot - 1
            part_count = (header.size_bytes + SAMPLE_PART_BYTES - 1) // SAMPLE_PART_BYTES
            for part in range(part_count):
                self._exchange(
                    input_port,
                    output_port,
                    0x59,
                    bytes((zero_based, part)),
                    0x15,
                    0,
                )
                for packet in range(WAVE_PACKETS_PER_PART):
                    packed = self._exchange(
                        input_port,
                        output_port,
                        0x18,
                        b"\x00",
                        0x17 if packet == WAVE_PACKETS_PER_PART - 1 else 0x16,
                        WAVE_PACKET_MIDI_BYTES,
                    )
                    raw = unpack_8bit_midi(packed)
                    output.extend(raw[:8] if packet == 146 else raw)
                    self.sleep(0.005)
        return DirectSample(header=header, audio_bytes=bytes(output[: header.size_bytes]))

    @staticmethod
    def _sample_name_bytes(name: str) -> bytes:
        try:
            encoded = name.encode("ascii")
        except UnicodeEncodeError as exc:
            raise ValueError("MicroFreak sample names must be ASCII") from exc
        alphabet = set(b" ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")
        if not encoded or len(encoded) > 12:
            raise ValueError("MicroFreak sample names must contain 1..12 bytes")
        if any(value not in alphabet for value in encoded):
            raise ValueError(
                "MicroFreak sample names may use letters, digits, space, '.', '_', and '-'"
            )
        return encoded

    @classmethod
    def _sample_header_bytes(
        cls, slot: int, name: str, audio_bytes: bytes, *, empty: bool = False
    ) -> bytes:
        if not 1 <= slot <= SAMPLE_SLOTS:
            raise ValueError(f"MicroFreak sample slot must be 1..{SAMPLE_SLOTS}")
        if empty:
            encoded_name = b""
            audio_bytes = b""
        else:
            encoded_name = cls._sample_name_bytes(name)
            if not audio_bytes or len(audio_bytes) > SAMPLE_MAX_BYTES:
                raise ValueError(
                    f"MicroFreak sample PCM must contain 2..{SAMPLE_MAX_BYTES} bytes"
                )
            if len(audio_bytes) % 2:
                raise ValueError(
                    "MicroFreak sample PCM must contain complete 16-bit samples"
                )
        header = bytearray(SAMPLE_HEADER_RAW_BYTES)
        header[4:8] = len(audio_bytes).to_bytes(4, "little")
        header[8:10] = microfreak_sample_checksum(audio_bytes).to_bytes(2, "little")
        header[10 : 10 + len(encoded_name)] = encoded_name
        header[23] = slot - 1
        return bytes(header)

    @staticmethod
    def _sample_wire_state(sample: DirectSample) -> bytes:
        name = sample.header.name.encode("ascii")
        return (
            len(name).to_bytes(1, "little")
            + name
            + sample.header.size_bytes.to_bytes(4, "little")
            + sample.header.checksum.to_bytes(2, "little")
            + sample.audio_bytes
        )

    def _reset_sample_header_session(
        self,
        input_port: Any,
        output_port: Any,
        slot: int,
        header: bytes,
    ) -> None:
        zero_based = slot - 1
        self._exchange(
            input_port,
            output_port,
            0x5A,
            bytes((zero_based, 0, 0)),
            0x18,
            0,
        )
        self.sleep(0.005)
        self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
        self.sleep(0.005)
        self._exchange(
            input_port,
            output_port,
            0x17,
            pack_8bit_midi(header),
            0x18,
            0,
        )
        self.sleep(0.005)

    def _upload_sample_parts_session(
        self,
        input_port: Any,
        output_port: Any,
        slot: int,
        audio_bytes: bytes,
    ) -> None:
        zero_based = slot - 1
        part_count = (len(audio_bytes) + SAMPLE_PART_BYTES - 1) // SAMPLE_PART_BYTES
        for part in range(part_count):
            self._exchange(
                input_port,
                output_port,
                0x58,
                bytes((zero_based, 0, 1)),
                0x18,
                0,
            )
            self.sleep(0.005)
            self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
            self.sleep(0.005)
            part_data = audio_bytes[
                part * SAMPLE_PART_BYTES : (part + 1) * SAMPLE_PART_BYTES
            ].ljust(SAMPLE_PART_BYTES, b"\x00")
            for packet in range(SAMPLE_PACKETS_PER_PART):
                if packet == SAMPLE_PACKETS_PER_PART - 1:
                    raw = part_data[packet * 28 : packet * 28 + 8] + bytes(20)
                    operation = 0x17
                else:
                    raw = part_data[packet * 28 : (packet + 1) * 28]
                    operation = 0x16
                self._exchange(
                    input_port,
                    output_port,
                    operation,
                    pack_8bit_midi(raw),
                    0x18,
                    0,
                )
                self.sleep(0.005)

    def _upload_sample(self, slot: int, name: str, audio_bytes: bytes) -> None:
        header = self._sample_header_bytes(slot, name, audio_bytes)
        zero_based = slot - 1
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            # Allocation negotiation observed in MIDI Control Center and the
            # public Elektroid connector. The second reply is unsolicited.
            self._exchange(
                input_port,
                output_port,
                0x5D,
                bytes((zero_based, 0, 0)),
                0x18,
                0,
            )
            self.sleep(0.005)
            self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
            self.sleep(0.005)
            accepted = self._exchange(
                input_port,
                output_port,
                0x17,
                pack_8bit_midi(header),
                0x16,
                1,
            )
            if accepted != b"\x01":
                raise MicroFreakMidiError(
                    "MicroFreak refused sample allocation (insufficient contiguous space)"
                )
            allocation_complete = self._receive(input_port)
            if allocation_complete.operation != 0x18 or allocation_complete.payload:
                raise MicroFreakMidiError(
                    "unexpected MicroFreak sample-allocation completion reply"
                )
            self.sleep(0.005)

            self._reset_sample_header_session(
                input_port, output_port, slot, header
            )
            self._upload_sample_parts_session(
                input_port, output_port, slot, audio_bytes
            )

            # The official/public flow performs one post-upload stream pass.
            # Its bytes are not trusted as verification; the independent
            # operation-59 reader below performs the exact readback.
            self._exchange(
                input_port,
                output_port,
                0x5B,
                bytes((zero_based, 0, 1)),
                0x15,
                0,
            )
            for packet in range(SAMPLE_PACKETS_PER_PART):
                self._exchange(
                    input_port,
                    output_port,
                    0x18,
                    b"\x00",
                    0x17 if packet == SAMPLE_PACKETS_PER_PART - 1 else 0x16,
                    WAVE_PACKET_MIDI_BYTES,
                )
                self.sleep(0.005)
        self.sleep(0.03)

    def _clear_sample(self, slot: int) -> None:
        header = self._sample_header_bytes(slot, "", b"", empty=True)
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            while input_port.poll() is not None:
                pass
            self._reset_sample_header_session(
                input_port, output_port, slot, header
            )
        self.sleep(0.03)

    def write_sample(
        self,
        slot: int,
        name: str,
        audio_bytes: bytes,
        backup_path: str | Path,
    ) -> DirectSampleWriteReport:
        """Guarded raw PCM16LE upload with exact body readback and rollback."""

        target_header_bytes = self._sample_header_bytes(slot, name, audio_bytes)
        target = DirectSample(
            header=DirectSampleHeader(
                slot=slot,
                device_id=slot - 1,
                name=name,
                address=0,
                size_bytes=len(audio_bytes),
                checksum=microfreak_sample_checksum(audio_bytes),
                empty=False,
                raw_header_hex=target_header_bytes.hex(),
            ),
            audio_bytes=audio_bytes,
        )
        before_header = self.read_sample_header(slot)
        stable_header = self.read_sample_header(slot)
        if stable_header != before_header:
            raise MicroFreakMidiError("MicroFreak sample header changed during preflight")
        before = None if before_header.empty else self.read_sample(slot)
        if before is not None and self.read_sample(slot) != before:
            raise MicroFreakMidiError("MicroFreak sample changed during preflight")

        required_bytes = (
            (len(audio_bytes) + SAMPLE_PART_BYTES - 1) // SAMPLE_PART_BYTES
        ) * SAMPLE_PART_BYTES
        stats = self.read_sample_storage_stats()
        if stats.estimated_free_bytes < required_bytes:
            raise MicroFreakMidiError(
                "MicroFreak does not report enough free sample memory for a guarded upload"
            )

        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = bytes.fromhex(before_header.raw_header_hex) + (
            b"" if before is None else before.audio_bytes
        )
        backup.write_bytes(before_bytes)
        target_wire = self._sample_wire_state(target)

        def restore() -> bool:
            if before is None:
                self._clear_sample(slot)
                return self.read_sample_header(slot).empty
            self._upload_sample(
                slot, before.header.name, before.audio_bytes
            )
            return self._sample_wire_state(self.read_sample(slot)) == self._sample_wire_state(before)

        try:
            self._upload_sample(slot, name, audio_bytes)
            readback = self.read_sample(slot)
        except Exception as exc:
            if not restore():
                raise MicroFreakMidiError(
                    f"direct sample upload and restoration failed; backup: {backup}"
                ) from exc
            raise MicroFreakMidiError(
                f"direct sample upload failed; restoration verified; backup: {backup}"
            ) from exc

        readback_wire = self._sample_wire_state(readback)
        if readback_wire != target_wire:
            if not restore():
                raise MicroFreakMidiError(
                    f"direct sample readback and restoration failed; backup: {backup}"
                )
            raise MicroFreakMidiError(
                f"direct sample readback differed; restoration verified; backup: {backup}"
            )
        return DirectSampleWriteReport(
            slot=slot,
            backup_path=str(backup),
            before_empty=before is None,
            before_name=before_header.name,
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            target_name=name,
            target_sha256=hashlib.sha256(target_wire).hexdigest(),
            readback_sha256=hashlib.sha256(readback_wire).hexdigest(),
            exact_readback=True,
        )

    def clear_sample(
        self, slot: int, backup_path: str | Path
    ) -> DirectSampleClearReport:
        """Clear one occupied sample after saving a lossless recovery artifact."""

        before = self.read_sample(slot)
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = bytes.fromhex(before.header.raw_header_hex) + before.audio_bytes
        backup.write_bytes(before_bytes)
        before_wire = self._sample_wire_state(before)
        try:
            self._clear_sample(slot)
            empty = self.read_sample_header(slot).empty
        except Exception as exc:
            self._upload_sample(slot, before.header.name, before.audio_bytes)
            if self._sample_wire_state(self.read_sample(slot)) != before_wire:
                raise MicroFreakMidiError(
                    f"direct sample clear and restoration failed; backup: {backup}"
                ) from exc
            raise MicroFreakMidiError(
                f"direct sample clear failed; restoration verified; backup: {backup}"
            ) from exc
        if not empty:
            self._upload_sample(slot, before.header.name, before.audio_bytes)
            if self._sample_wire_state(self.read_sample(slot)) != before_wire:
                raise MicroFreakMidiError(
                    f"direct sample clear verification and restoration failed; backup: {backup}"
                )
            raise MicroFreakMidiError(
                f"direct sample slot did not clear; restoration verified; backup: {backup}"
            )
        return DirectSampleClearReport(
            slot=slot,
            backup_path=str(backup),
            before_name=before.header.name,
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            empty_verified=True,
        )

    def _read_preset_open(
        self, input_port: Any, output_port: Any, slot: int
    ) -> MicroFreakPreset:
        zero_based = slot - 1
        bank, program = divmod(zero_based, 128)
        header = self._exchange(
                input_port,
                output_port,
                0x19,
                bytes((bank, program, 0)),
                0x52,
                PRESET_HEADER_LENGTH,
            )
        name = header[12:26].split(b"\x00", 1)[0].decode(
            "utf-8", errors="replace"
        )
        category_id = header[10]
        init = 1 if header[3] & 0x08 else 0
        p1 = header[11]
        if init:
            payload = b""
        else:
            self._exchange(
                    input_port,
                    output_port,
                    0x19,
                    bytes((bank, program, 1)),
                    0x15,
                    0,
                )
            parts = []
            for index in range(PRESET_PARTS):
                parts.append(
                    self._exchange(
                            input_port,
                            output_port,
                            0x18,
                            b"\x00",
                            0x17 if index == PRESET_PARTS - 1 else 0x16,
                            PRESET_PART_LENGTH,
                    )
                )
            payload = b"".join(parts)
        return MicroFreakPreset(
            name=name,
            category_id=category_id,
            init=init,
            p1=p1,
            payload=payload,
        )

    @staticmethod
    def _preset_header(slot: int, preset: MicroFreakPreset) -> bytes:
        preset.validate()
        if len(preset.payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise ValueError("direct MicroFreak upload requires a full preset payload")
        zero_based = slot - 1
        bank, program = divmod(zero_based, 128)
        header = bytearray(PRESET_HEADER_LENGTH)
        header[0] = bank
        header[1] = program
        header[3] = 0
        header[8] = program
        header[10] = preset.category_id
        header[11] = preset.p1
        encoded_name = preset.name.encode("utf-8")
        header[12 : 12 + len(encoded_name)] = encoded_name
        return bytes(header)

    def _upload_preset(self, slot: int, preset: MicroFreakPreset) -> None:
        if not 1 <= slot <= 512:
            raise ValueError("MicroFreak preset slot must be 1..512")
        zero_based = slot - 1
        bank, program = divmod(zero_based, 128)
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            self._exchange(
                input_port,
                output_port,
                0x52,
                self._preset_header(slot, preset),
                0x18,
                0,
            )
            self.sleep(0.005)
            self._exchange(
                input_port,
                output_port,
                0x52,
                bytes((bank, program, 1)),
                0x18,
                0,
            )
            self.sleep(0.005)
            self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
            self.sleep(0.005)
            for index in range(PRESET_PARTS):
                part = preset.payload[
                    index * PRESET_PART_LENGTH : (index + 1) * PRESET_PART_LENGTH
                ]
                self._exchange(
                    input_port,
                    output_port,
                    0x17 if index == PRESET_PARTS - 1 else 0x16,
                    part,
                    0x18,
                    0,
                )
                self.sleep(0.005)
        self.sleep(0.03)

    @staticmethod
    def _preset_wire_state(preset: MicroFreakPreset) -> bytes:
        """Return only fields represented by operation-52 header/body data."""

        name = preset.name.encode("utf-8")
        return (
            len(name).to_bytes(2, "big")
            + name
            + bytes((preset.category_id, preset.p1))
            + preset.payload
        )

    def write_preset(
        self,
        slot: int,
        preset: MicroFreakPreset,
        backup_path: str | Path,
    ) -> DirectPresetWriteReport:
        """Guarded independent saved-preset upload with exact rollback."""
        before = self.read_preset(slot)
        if self.read_preset(slot) != before:
            raise MicroFreakMidiError("MicroFreak preset changed during preflight")
        if len(before.payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise MicroFreakMidiError(
                f"MicroFreak preset slot {slot} is an empty Init slot; "
                "its empty state cannot be restored by upload"
            )
        preset.validate()
        if preset.init != 0:
            raise ValueError("direct MicroFreak upload requires an occupied preset")
        if len(preset.payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise ValueError("direct MicroFreak upload requires a full preset payload")
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = before.to_bytes()
        target_bytes = preset.to_bytes()
        backup.write_bytes(before_bytes)

        def restore() -> bool:
            self._upload_preset(slot, before)
            return self.read_preset(slot) == before

        try:
            self._upload_preset(slot, preset)
            readback = self.read_preset(slot)
        except Exception as exc:
            if not restore():
                raise MicroFreakMidiError(
                    f"direct MicroFreak write and restoration failed; backup: {backup}"
                ) from exc
            raise MicroFreakMidiError(
                f"direct MicroFreak write failed; restoration verified; backup: {backup}"
            ) from exc
        target_wire = self._preset_wire_state(preset)
        readback_wire = self._preset_wire_state(readback)
        if readback_wire != target_wire:
            failed_readback = backup.with_name(
                f"{backup.name}.failed-readback.mfp"
            )
            failed_readback.write_bytes(readback.to_bytes())
            if not restore():
                raise MicroFreakMidiError(
                    "direct MicroFreak readback and restoration failed; "
                    f"backup: {backup}; failed readback: {failed_readback}"
                )
            raise MicroFreakMidiError(
                "direct MicroFreak readback differed; restoration verified; "
                f"backup: {backup}; failed readback: {failed_readback}"
            )
        return DirectPresetWriteReport(
            slot=slot,
            backup_path=str(backup),
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            target_sha256=hashlib.sha256(target_wire).hexdigest(),
            readback_sha256=hashlib.sha256(readback_wire).hexdigest(),
            exact_readback=True,
            target_archive_sha256=hashlib.sha256(target_bytes).hexdigest(),
            readback_archive_sha256=hashlib.sha256(readback.to_bytes()).hexdigest(),
            archive_wrapper_normalized=readback.version_tag != preset.version_tag,
        )

    def _read_wavetable_header_session(
        self, input_port: Any, output_port: Any, slot: int
    ) -> DirectWavetableHeader:
        zero_based = slot - 1
        self._exchange(
            input_port,
            output_port,
            0x57,
            bytes((zero_based, 0, 0)),
            0x15,
            0,
        )
        packed = self._exchange(
            input_port, output_port, 0x18, b"\x01", 0x16, WAVE_PACKET_MIDI_BYTES
        )
        header = unpack_8bit_midi(packed)
        name = header[12:28].split(b"\x00", 1)[0].decode(
            "utf-8", errors="replace"
        )
        return DirectWavetableHeader(
            slot=slot,
            name=name,
            empty=bool(header[3] & 0x08),
        )

    def read_wavetable_header(self, slot: int) -> DirectWavetableHeader:
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            return self._read_wavetable_header_session(
                input_port, output_port, slot
            )

    def read_wavetable(self, slot: int) -> MicroFreakWavetable:
        """Read one user wavetable through independent CoreMIDI SysEx."""
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            header = self._read_wavetable_header_session(
                input_port, output_port, slot
            )
            if header.empty:
                raise MicroFreakMidiError(
                    f"MicroFreak wavetable slot {slot} is empty"
                )
            output = bytearray()
            zero_based = slot - 1
            for part in range(WAVE_PARTS):
                self._exchange(
                    input_port,
                    output_port,
                    0x55,
                    bytes((zero_based, part, 0)),
                    0x15,
                    0,
                )
                for packet in range(WAVE_PACKETS_PER_PART):
                    packed = self._exchange(
                        input_port,
                        output_port,
                        0x18,
                        b"\x00",
                        0x17 if packet == WAVE_PACKETS_PER_PART - 1 else 0x16,
                        WAVE_PACKET_MIDI_BYTES,
                    )
                    raw = unpack_8bit_midi(packed)
                    output.extend(raw[:8] if packet == 146 else raw)
                    self.sleep(0.005)
        if len(output) != MICROFREAK_PCM_BYTES:
            raise MicroFreakMidiError(
                f"expected {MICROFREAK_PCM_BYTES} wavetable bytes, "
                f"received {len(output)}"
            )
        return MicroFreakWavetable(name=header.name, pcm16le=bytes(output))

    @staticmethod
    def _wavetable_header_bytes(
        slot: int, name: str, *, empty: bool = False
    ) -> bytes:
        encoded_name = name.encode("utf-8")
        if len(encoded_name) > 15:
            raise ValueError("MicroFreak wavetable names are at most 15 bytes")
        zero_based = slot - 1
        header = bytearray(28)
        header[0] = zero_based
        header[3] = 0x08 if empty else 0
        header[8] = zero_based
        header[10] = 1
        header[11] = 1
        header[12 : 12 + len(encoded_name)] = encoded_name
        return bytes(header)

    def _set_wavetable_entry_session(
        self,
        input_port: Any,
        output_port: Any,
        slot: int,
        name: str,
        *,
        empty: bool = False,
    ) -> None:
        zero_based = slot - 1
        self._exchange(
            input_port,
            output_port,
            0x56,
            bytes((zero_based, 0, 0)),
            0x18,
            0,
        )
        self.sleep(0.005)
        self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
        self.sleep(0.005)
        header = self._wavetable_header_bytes(slot, name, empty=empty)
        self._exchange(
            input_port,
            output_port,
            0x16,
            pack_8bit_midi(header),
            0x18,
            0,
        )
        self.sleep(0.005)
        self._exchange(
            input_port, output_port, 0x17, bytes(8), 0x18, 0
        )
        self.sleep(0.005)

    def _upload_wavetable_parts_session(
        self,
        input_port: Any,
        output_port: Any,
        slot: int,
        pcm16le: bytes,
    ) -> None:
        if len(pcm16le) != MICROFREAK_PCM_BYTES:
            raise ValueError(
                f"MicroFreak wavetable must be {MICROFREAK_PCM_BYTES} bytes"
            )
        zero_based = slot - 1
        for part in range(WAVE_PARTS):
            self._exchange(
                input_port,
                output_port,
                0x54,
                bytes((zero_based, part, 1)),
                0x18,
                0,
            )
            self.sleep(0.005)
            self._exchange(input_port, output_port, 0x15, b"", 0x18, 0)
            self.sleep(0.005)
            part_data = pcm16le[part * WAVE_PART_BYTES : (part + 1) * WAVE_PART_BYTES]
            for packet in range(WAVE_PACKETS_PER_PART):
                if packet == 146:
                    raw = part_data[packet * 28 : packet * 28 + 8] + bytes(20)
                    operation = 0x17
                else:
                    raw = part_data[packet * 28 : (packet + 1) * 28]
                    operation = 0x16
                self._exchange(
                    input_port,
                    output_port,
                    operation,
                    pack_8bit_midi(raw),
                    0x18,
                    0,
                )
                self.sleep(0.005)

    def _upload_wavetable(self, slot: int, table: MicroFreakWavetable) -> None:
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            self._set_wavetable_entry_session(
                input_port, output_port, slot, table.name
            )
            self._upload_wavetable_parts_session(
                input_port, output_port, slot, table.pcm16le
            )
        self.sleep(0.03)

    def _clear_wavetable(self, slot: int) -> None:
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        port_name = self.resolve_port()
        self.sequence = 0
        with self.midi.open_input(port_name) as input_port, self.midi.open_output(
            port_name
        ) as output_port:
            self._set_wavetable_entry_session(
                input_port, output_port, slot, "", empty=True
            )
            self._upload_wavetable_parts_session(
                input_port, output_port, slot, bytes(MICROFREAK_PCM_BYTES)
            )
        self.sleep(0.03)

    def write_wavetable(
        self,
        slot: int,
        table: MicroFreakWavetable,
        backup_path: str | Path,
    ) -> DirectWavetableWriteReport:
        """Guarded independent wavetable upload with exact rollback."""
        header = self.read_wavetable_header(slot)
        before = None if header.empty else self.read_wavetable(slot)
        if before is not None and self.read_wavetable(slot) != before:
            raise MicroFreakMidiError("MicroFreak wavetable changed during preflight")
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = b"" if before is None else before.to_mfw()
        target_bytes = table.to_mfw()
        backup.write_bytes(before_bytes)

        def restore() -> bool:
            if before is None:
                self._clear_wavetable(slot)
                return self.read_wavetable_header(slot).empty
            self._upload_wavetable(slot, before)
            return self.read_wavetable(slot) == before

        try:
            self._upload_wavetable(slot, table)
            readback = self.read_wavetable(slot)
        except Exception as exc:
            if not restore():
                raise MicroFreakMidiError(
                    f"direct wavetable write and restoration failed; backup: {backup}"
                ) from exc
            raise MicroFreakMidiError(
                f"direct wavetable write failed; restoration verified; backup: {backup}"
            ) from exc
        if readback != table:
            if not restore():
                raise MicroFreakMidiError(
                    f"direct wavetable readback and restoration failed; backup: {backup}"
                )
            raise MicroFreakMidiError(
                f"direct wavetable readback differed; restoration verified; backup: {backup}"
            )
        return DirectWavetableWriteReport(
            slot=slot,
            backup_path=str(backup),
            before_empty=before is None,
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            target_sha256=hashlib.sha256(target_bytes).hexdigest(),
            readback_sha256=hashlib.sha256(readback.to_mfw()).hexdigest(),
            exact_readback=True,
        )

    def clear_wavetable(
        self, slot: int, backup_path: str | Path
    ) -> DirectWavetableClearReport:
        """Clear one occupied table after creating an exact recoverable backup."""
        header = self.read_wavetable_header(slot)
        if header.empty:
            raise MicroFreakMidiError(f"MicroFreak wavetable slot {slot} is already empty")
        before = self.read_wavetable(slot)
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = before.to_mfw()
        backup.write_bytes(before_bytes)
        try:
            self._clear_wavetable(slot)
            empty = self.read_wavetable_header(slot).empty
        except Exception as exc:
            self._upload_wavetable(slot, before)
            if self.read_wavetable(slot) != before:
                raise MicroFreakMidiError(
                    f"direct wavetable clear and restoration failed; backup: {backup}"
                ) from exc
            raise MicroFreakMidiError(
                f"direct wavetable clear failed; restoration verified; backup: {backup}"
            ) from exc
        if not empty:
            self._upload_wavetable(slot, before)
            if self.read_wavetable(slot) != before:
                raise MicroFreakMidiError(
                    f"direct wavetable clear verification and restoration failed; backup: {backup}"
                )
            raise MicroFreakMidiError(
                f"direct wavetable slot did not clear; restoration verified; backup: {backup}"
            )
        return DirectWavetableClearReport(
            slot=slot,
            backup_path=str(backup),
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            empty_verified=True,
        )
