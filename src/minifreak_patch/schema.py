"""Device-neutral JSON documents and capability declarations."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


SCHEMA_VERSION = "arturia-freak-patch/1"

MICROFREAK_CHARACTERISTICS = (
    "Acid",
    "Aggressive",
    "Ambient",
    "Bizarre",
    "Bright",
    "Complex",
    "Dark",
    "Digital",
    "Ensemble",
    "Funky",
    "Hard",
    "Long",
    "Noise",
    "Quiet",
    "Short",
    "Simple",
    "Soft",
    "Soundtrack",
)


def decode_microfreak_characteristics(bits: str) -> list[str]:
    if len(bits) != 18 or any(char not in "01" for char in bits):
        raise ValueError("MicroFreak characteristics_bits must be 18 binary characters")
    return [
        name
        for index, name in enumerate(MICROFREAK_CHARACTERISTICS)
        if bits[-1 - index] == "1"
    ]


def encode_microfreak_characteristics(names: list[str]) -> str:
    unknown = sorted(set(names) - set(MICROFREAK_CHARACTERISTICS))
    if unknown:
        raise ValueError(f"unknown MicroFreak characteristics: {unknown!r}")
    if len(names) != len(set(names)):
        raise ValueError("MicroFreak characteristics must not contain duplicates")
    enabled = set(names)
    return "".join(
        "1" if name in enabled else "0"
        for name in reversed(MICROFREAK_CHARACTERISTICS)
    )


class DeviceModel(str, Enum):
    MINIFREAK = "minifreak"
    MICROFREAK = "microfreak"


class SupportLevel(str, Enum):
    VERIFIED = "verified"
    GUARDED = "guarded"
    PARTIAL = "partial"
    RESEARCH = "research"
    UNSUPPORTED = "unsupported"


class Capability(BaseModel):
    level: SupportLevel
    note: str


class PatchMetadata(BaseModel):
    name: str
    author: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    subtype: Optional[str] = None
    firmware: Optional[str] = None
    source_slot: Optional[int] = None


class MiniFreakPatchData(BaseModel):
    """MiniFreak-only state.

    ``parameters`` is the lossless normalized key/value representation from
    an exported .mnfx file. ``recipe`` is optional compact editing intent.
    """

    pack: str = "User"
    original_author: str = "Unknown"
    timestamp: Optional[int] = None
    metadata: dict[str, str] = Field(default_factory=dict)
    parameters: dict[str, float] = Field(default_factory=dict)
    recipe: Optional[dict[str, Any]] = None
    hardware: Optional["MiniFreakHardwareData"] = None


class MiniFreakHardwareParameter(BaseModel):
    status: str
    value_type: str
    value: float | int | str | bool | None = None
    name: Optional[str] = None
    raw_value: Optional[int] = None
    byte_offset: Optional[int] = None
    session_parameter_id: Optional[int] = None
    live_session_write: Optional[bool] = None
    encoding: Optional[str] = None
    mnfx_name: Optional[str] = None
    mnfx_encoding: Optional[str] = None
    corpus_presets: Optional[int] = None
    corpus_distinct_values: Optional[int] = None


class MiniFreakHardwareData(BaseModel):
    """Lossless state read from the MiniFreak Collage USB transport."""

    transport: Literal["arturia-collage-usb"] = "arturia-collage-usb"
    resource_location: str
    resource_name_base64: str
    raw_payload_base64: str
    transport_parameters: dict[str, MiniFreakHardwareParameter] = Field(
        default_factory=dict
    )
    decoded_parameter_support: SupportLevel = SupportLevel.RESEARCH


class MicroFreakArchiveData(BaseModel):
    version_tag: str = "174"
    characteristics_bits: str = Field(
        default="000000000000000000", pattern=r"^[01]{18}$"
    )
    characteristics: list[str] = Field(default_factory=list)
    category_id: int = Field(ge=0, le=255)
    init: int = Field(default=0, ge=0, le=255)
    p1: int = Field(default=0, ge=0, le=255)

    @model_validator(mode="before")
    @classmethod
    def populate_characteristics(cls, data: Any) -> Any:
        if isinstance(data, dict) and "characteristics" not in data:
            data = dict(data)
            data["characteristics"] = decode_microfreak_characteristics(
                data.get("characteristics_bits", "000000000000000000")
            )
        return data

    @model_validator(mode="after")
    def validate_characteristics(self) -> "MicroFreakArchiveData":
        expected = encode_microfreak_characteristics(self.characteristics)
        if expected != self.characteristics_bits:
            raise ValueError(
                "MicroFreak characteristics and characteristics_bits disagree"
            )
        return self


class MicroFreakStructuredParameter(BaseModel):
    """One field named inside the firmware's packed preset serialization."""

    group: str
    name: str
    metadata: int = Field(ge=0, le=255)
    raw_u16: int = Field(ge=0, le=65535)
    raw_s16: int = Field(ge=-32768, le=32767)
    interpreted_value: float | int | None = None
    value_label: str | None = None
    value_kind: str | None = None
    value_minimum: float | int | None = None
    value_maximum: float | int | None = None
    packed_byte_offsets: list[int]
    status: str = "firmware_tagged_payload_observed_fw5"
    encoding: str = "tagged_metadata_plus_uint16_le"
    role: Literal[
        "patch_parameter",
        "ui_action_placeholder_candidate",
        "legacy_panel_state_candidate",
    ] = "patch_parameter"
    role_evidence: str | None = None


class MicroFreakOscillatorEngineData(BaseModel):
    """Named engine plus the saved layout boundary that contains it."""

    index: int = Field(ge=1, le=22)
    name: str
    saved_layout_max_index: int = Field(ge=1, le=127)
    saved_layout_family: Literal["historical", "firmware_5_sample_capable"]
    can_select_all_firmware_5_engines: bool
    automatic_layout_migration: SupportLevel = SupportLevel.UNSUPPORTED
    evidence: str = "hardware_saved_live_320_plus_cc22_and_v5_saved_write"


class MicroFreakSequenceStep(BaseModel):
    """One lossless step with corpus-supported note and automation fields."""

    notes: list[Optional[int]] = Field(min_length=4, max_length=4)
    note_bytes: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    velocities: Optional[list[int]] = Field(default=None, min_length=4, max_length=4)
    automation_values: Optional[list[int]] = Field(
        default=None, min_length=4, max_length=4
    )
    automation_mask: Optional[int] = Field(default=None, ge=0, le=15)
    note_event_code: Optional[int] = Field(default=None, ge=0, le=255)
    note_status: Optional[Literal["rest", "trigger", "tie"]] = None
    reserved_bytes: Optional[list[int]] = Field(
        default=None, min_length=2, max_length=2
    )
    unclassified_bytes: list[int] = Field(min_length=8, max_length=12)

    @model_validator(mode="after")
    def validate_byte_ranges(self) -> "MicroFreakSequenceStep":
        if any(note is not None and not 0 <= note <= 127 for note in self.notes):
            raise ValueError("MicroFreak sequence notes must be 0..127 or null")
        if self.note_bytes is not None and any(
            not 0 <= value <= 255 for value in self.note_bytes
        ):
            raise ValueError("MicroFreak raw sequence note bytes must be 0..255")
        if self.velocities is not None and any(
            not 0 <= value <= 127 for value in self.velocities
        ):
            raise ValueError("MicroFreak sequence velocities must be 0..127")
        if self.automation_values is not None and any(
            not 0 <= value <= 255 for value in self.automation_values
        ):
            raise ValueError("MicroFreak sequence automation values must be 0..255")
        if self.reserved_bytes is not None and any(
            not 0 <= value <= 255 for value in self.reserved_bytes
        ):
            raise ValueError("MicroFreak reserved sequence bytes must be 0..255")
        if any(not 0 <= value <= 255 for value in self.unclassified_bytes):
            raise ValueError("MicroFreak unclassified sequence bytes must be 0..255")
        return self


class MicroFreakSequencePattern(BaseModel):
    unpacked_offset: int
    steps: list[MicroFreakSequenceStep] = Field(min_length=64, max_length=64)
    automation_destinations: Optional[
        list["MicroFreakSequenceAutomationDestination"]
    ] = Field(default=None, min_length=4, max_length=4)
    trailer_bytes: Optional[list[int]] = Field(
        default=None, min_length=18, max_length=18
    )

    @model_validator(mode="after")
    def validate_trailer(self) -> "MicroFreakSequencePattern":
        if self.trailer_bytes is not None and any(
            not 0 <= value <= 255 for value in self.trailer_bytes
        ):
            raise ValueError("MicroFreak sequence trailer bytes must be 0..255")
        if self.automation_destinations is not None and [
            item.lane for item in self.automation_destinations
        ] != [1, 2, 3, 4]:
            raise ValueError("MicroFreak sequence automation lanes must be ordered 1..4")
        return self


class MicroFreakSequenceAutomationDestination(BaseModel):
    """One automation lane's saved operation-41 destination address."""

    lane: int = Field(ge=1, le=4)
    live_address: Optional[int] = Field(default=None, ge=0, le=0x170F)
    parameter: Optional[str] = None
    evidence: str = (
        "hardware_playback_cc_plus_operation41_motivseq_and_320_preset_corpus"
    )

    @model_validator(mode="after")
    def validate_live_address_shape(self) -> "MicroFreakSequenceAutomationDestination":
        if self.live_address is not None and (
            self.live_address >> 8 >= 24 or self.live_address & 0xFF >= 16
        ):
            raise ValueError("MicroFreak sequence destination is not a live-word address")
        return self


class MicroFreakSequenceData(BaseModel):
    layout: str = "microfreak-fw5-two-patterns-64x16/1"
    evidence: str = "fixed_offsets_observed_across_five_fw5_tagged_layouts"
    pattern_a: MicroFreakSequencePattern
    pattern_b: MicroFreakSequencePattern


class MicroFreakPatchData(BaseModel):
    """MicroFreak-only state.

    The raw payload is retained for byte-perfect editing and round trips.
    Named fields are intentionally separate and may only contain values whose
    offsets and encodings have been verified.
    """

    archive: MicroFreakArchiveData
    decoded_parameters: dict[str, float | int | str | bool] = Field(
        default_factory=dict
    )
    parameter_evidence: dict[str, "MicroFreakParameterEvidence"] = Field(
        default_factory=dict
    )
    structured_parameters: dict[str, MicroFreakStructuredParameter] = Field(
        default_factory=dict
    )
    oscillator_engine: Optional[MicroFreakOscillatorEngineData] = None
    sequence_patterns: Optional[MicroFreakSequenceData] = None
    raw_payload_base64: str
    decoded_parameter_support: SupportLevel = SupportLevel.PARTIAL


class MicroFreakParameterEvidence(BaseModel):
    status: str
    value_type: str
    raw_value: int
    byte_offsets: list[int]
    flag_mask: Optional[int] = None
    encoding: str


class MicroFreakLiveWordData(BaseModel):
    """One operation-41 word from the active MicroFreak synth object."""

    address: int = Field(ge=0, le=0x170F)
    group: int = Field(ge=0, le=23)
    word: int = Field(ge=0, le=15)
    raw_u16: int = Field(ge=0, le=65535)
    raw_s16: int = Field(ge=-32768, le=32767)
    raw_payload_hex: str = Field(pattern=r"^[0-9a-f]{10}$")
    parameter: Optional[str] = None
    relationship: Optional[Literal["direct", "alias", "dependent"]] = None
    evidence: Optional[str] = None

    @model_validator(mode="after")
    def validate_address_and_signed_value(self) -> "MicroFreakLiveWordData":
        if self.address != (self.group << 8) | self.word:
            raise ValueError("MicroFreak live address must equal group << 8 | word")
        expected_signed = (
            self.raw_u16 - 0x10000 if self.raw_u16 & 0x8000 else self.raw_u16
        )
        if self.raw_s16 != expected_signed:
            raise ValueError("MicroFreak live raw_s16 disagrees with raw_u16")
        if (self.parameter is None) != (self.relationship is None):
            raise ValueError(
                "MicroFreak live parameter and relationship must appear together"
            )
        return self


class MicroFreakLiveTableDocument(BaseModel):
    """Lossless JSON snapshot of a bounded active-word table range."""

    schema_version: Literal["arturia-microfreak-live-table/1"] = (
        "arturia-microfreak-live-table/1"
    )
    device: Literal["microfreak"] = "microfreak"
    transport: Literal["arturia-microfreak-sysex-41"] = (
        "arturia-microfreak-sysex-41"
    )
    start_ordinal: int = Field(ge=0, le=383)
    word_count: int = Field(ge=1, le=384)
    complete_table: bool
    groups: Literal[24] = 24
    words_per_group: Literal[16] = 16
    named_parameter_support: SupportLevel = SupportLevel.PARTIAL
    live_write_support: SupportLevel = SupportLevel.GUARDED
    words: list[MicroFreakLiveWordData] = Field(min_length=1, max_length=384)

    @model_validator(mode="after")
    def validate_range(self) -> "MicroFreakLiveTableDocument":
        if self.word_count != len(self.words):
            raise ValueError("MicroFreak live word_count disagrees with words")
        if self.start_ordinal + self.word_count > 384:
            raise ValueError("MicroFreak live range exceeds the 384-word table")
        if self.complete_table != (
            self.start_ordinal == 0 and self.word_count == 384
        ):
            raise ValueError("MicroFreak complete_table flag disagrees with range")
        expected_addresses = [
            ((ordinal // 16) << 8) | (ordinal % 16)
            for ordinal in range(
                self.start_ordinal, self.start_ordinal + self.word_count
            )
        ]
        if [word.address for word in self.words] != expected_addresses:
            raise ValueError("MicroFreak live words are not a contiguous ordinal range")
        return self


class PatchDocument(BaseModel):
    schema_version: Literal["arturia-freak-patch/1"] = SCHEMA_VERSION
    device: DeviceModel
    metadata: PatchMetadata
    shared: dict[str, Any] = Field(default_factory=dict)
    minifreak: Optional[MiniFreakPatchData] = None
    microfreak: Optional[MicroFreakPatchData] = None

    @model_validator(mode="after")
    def validate_device_block(self) -> "PatchDocument":
        if self.device == DeviceModel.MINIFREAK:
            if self.minifreak is None or self.microfreak is not None:
                raise ValueError(
                    "MiniFreak documents require only the 'minifreak' block"
                )
        elif self.device == DeviceModel.MICROFREAK:
            if self.microfreak is None or self.minifreak is not None:
                raise ValueError(
                    "MicroFreak documents require only the 'microfreak' block"
                )
        return self


DEVICE_CAPABILITIES: dict[DeviceModel, dict[str, Capability]] = {
    DeviceModel.MINIFREAK: {
        "device.discovery": Capability(
            level=SupportLevel.VERIFIED,
            note="USB MIDI endpoint and identity are auto-detected.",
        ),
        "patch.file.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Exported and factory .mnfx files parse losslessly.",
        ),
        "patch.file.write": Capability(
            level=SupportLevel.VERIFIED,
            note="JSON can be serialized to MiniFreak V-compatible .mnfx.",
        ),
        "patch.named_parameters": Capability(
            level=SupportLevel.PARTIAL,
            note="Hardware JSON exposes 158 exact corpus-mapped fields. All are active-buffer writable; 40 use session deltas and 118 use activating resource store. Full mapping is incomplete.",
        ),
        "patch.device.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent Collage USB client reads the active buffer, all 512 saved slots, and slot metadata.",
        ),
        "patch.device.active_read": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent Collage resource retrieval reads the unsaved 3,328-byte active edit buffer.",
        ),
        "patch.device.saved_read": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent Collage resource retrieval reads all 512 saved slots and 128-byte slot metadata.",
        ),
        "patch.device.write": Capability(
            level=SupportLevel.PARTIAL,
            note="Active-buffer JSON writes are available for 158 named fields with exact readback; newly promoted corpus fields use resource store.",
        ),
        "patch.device.active_write": Capability(
            level=SupportLevel.VERIFIED,
            note="Forty mapped fields use session deltas; 118 additional exact corpus-mapped fields use the independently verified activating resource-store transaction.",
        ),
        "patch.device.saved_write": Capability(
            level=SupportLevel.PARTIAL,
            note="Occupied saved slots support mapped JSON writes with backup, exact readback, and restore-on-failure. Empty-slot creation is disabled because firmware resource removal returns I/O error.",
        ),
        "patch.live.cc": Capability(
            level=SupportLevel.VERIFIED,
            note="Published MIDI CCs change the active sound without saving or readback.",
        ),
        "wavetable.file.prepare": Capability(
            level=SupportLevel.PARTIAL,
            note="MiniFreak 189x512x24-bit raw tables can be validated.",
        ),
        "wavetable.device.upload": Capability(
            level=SupportLevel.UNSUPPORTED,
            note="Firmware 4.0.1 exposes 32 factory tables but no documented user wavetable slots.",
        ),
    },
    DeviceModel.MICROFREAK: {
        "device.discovery": Capability(
            level=SupportLevel.VERIFIED,
            note="The paired CoreMIDI endpoint is auto-selected for independent preset transport; Elektroid also identifies firmware and filesystems.",
        ),
        "patch.file.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Plain .mfp/.mbp, one-preset .mfpz, and project .mfprojz archives parse losslessly.",
        ),
        "patch.file.write": Capability(
            level=SupportLevel.VERIFIED,
            note="Lossless JSON serializes to plain .mfp/.mbp and one-preset .mfpz.",
        ),
        "patch.bank.file": Capability(
            level=SupportLevel.PARTIAL,
            note="Twenty-five public .mfprojz projects with 8,832 objects round-trip through the project model. Control Center 1.23.0 accepted an extracted generated project and decoded both intended presets; archive-picker import remains a UI check.",
        ),
        "patch.named_parameters": Capability(
            level=SupportLevel.PARTIAL,
            note="A firmware-5 full-bank scan found 107 self-named structured fields and a 96-field common core without fixed offsets. All support exact raw editing; 101 have bounded metadata-scaled, normalized, bipolar, signed-offset, or live-destination JSON values. Canonical osc.type uses tagged VCO.Type: it matched all 320 connected saved presets, and a genuine 22-engine firmware-5 payload was saved and selected as Scan Grains. Historical-to-firmware-5 layout migration remains deliberately unsupported. Six internal/action fields remain raw-only.",
        ),
        "patch.sequence": Capability(
            level=SupportLevel.PARTIAL,
            note="Both 64-step patterns are lossless in JSON. Notes, velocities, four automation values/masks, and rest/trigger/tie are editable. Trailer bytes 0..7 are four editable operation-41 destinations. Hardware proved byte 8 is gate percentage; byte 9 is a non-authoritative mirror of tagged length. UI-correct 10..90 gate and 4..64 length edits synchronize both pattern mirrors. Step-final bytes and trailer bytes 10..17 stay raw.",
        ),
        "patch.device.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Saved-slot read is verified; see the explicit active/saved read capabilities for the current-buffer boundary.",
        ),
        "patch.device.active_read": Capability(
            level=SupportLevel.PARTIAL,
            note="Operation 41 reads all 384 words. A 40-preset corpus plus two bulk saved sentinels map 99 structured tags exactly; normalized oscillator type makes 100 named current fields. The qualified current-overlay JSON applies compatible live fields to a complete saved base. Host-clock playback behaviorally reads the selected pattern's outgoing notes, velocities, automation, and boundaries, but is not a lossless sequence-object dump. Seven constant legacy/UI-action candidates, active sequence bytes/header state, metadata, and other non-word state remain unresolved.",
        ),
        "patch.device.active_sequence_behavioral_read": Capability(
            level=SupportLevel.PARTIAL,
            note="The guarded USB-clock capture records the selected active pattern's device-originated Note On/Off, velocity, automation CC, and clock-relative boundaries without audio or panel input. Optional operation-41 snapshots correlate named live fields at exact clock counts; MotivSeq proved cutoff, resonance, and envelope-decay lanes. It backs up/restores Clock Source and verifies all 384 live words after recovery. Pattern selection, inactive/raw sequence bytes, and lossless current-object transfer remain unresolved.",
        ),
        "patch.device.active_word_read": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent SysEx operation 41 exports all 384 grouped live words losslessly. The corpus and sentinel probes map 99 tags to exact direct/alias words; oscillator type adds a 100th named current field through its hardware-proven normalized encoding.",
        ),
        "patch.device.active_word_write": Capability(
            level=SupportLevel.GUARDED,
            note="Operation 49/6 kind 2 is hardware-proven to write any nonnegative 15-bit target at a known live address. A cutoff probe changed all three aliases, read back exactly through operation 41, and restored the operation-40-inexpressible original through the same packed-record path with zero differences across all 384 words. Unmapped addresses and negative signed values remain disabled.",
        ),
        "patch.device.active_write": Capability(
            level=SupportLevel.GUARDED,
            note="Known live words have two guarded setters: operation 40 for MIDI-clean bytes and operation 49/6 for nonnegative 15-bit targets. VCF.Type, Kbd.Hold, Kbd.Root, Arp.Dice, Seq.XiceRst, all three chord offsets, and all three assignable destinations were written with exact alias readback and restoration. Signed modulation values, seven legacy/UI-action candidates, sequence bodies, metadata, and full-patch live writes remain incomplete.",
        ),
        "patch.device.saved_read": Capability(
            level=SupportLevel.VERIFIED,
            note="The independent CoreMIDI SysEx backend and Elektroid both read all 512 saved slots; direct and delegated slot-1 JSON matched byte-for-byte.",
        ),
        "patch.device.init_template_read": Capability(
            level=SupportLevel.VERIFIED,
            note="Firmware 5.0.0.36 exposes a stable full 4,672-byte Init template at reserved bank 4/program 0. A reversible live-CC test proved it does not track the active buffer.",
        ),
        "patch.device.select": Capability(
            level=SupportLevel.GUARDED,
            note="All 512 slots map to four MIDI banks and 128 programs. Selection is computer-controlled but standard MIDI provides no acknowledgement and replaces the unsaved active patch.",
        ),
        "patch.device.write": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent CoreMIDI and delegated saved-preset uploads use fresh backup, stable preflight, exact readback, and automatic restoration on failure.",
        ),
        "patch.device.saved_write": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent SysEx slot 320 write/read/restore is hardware-verified against the exact transmitted header and 4,672-byte payload, including a firmware-5 Sample-to-Scan-Grains JSON edit followed by exact original restoration. The non-transmitted archive version tag is normalized by hardware; empty Init slots remain refused.",
        ),
        "patch.live.cc": Capability(
            level=SupportLevel.VERIFIED,
            note="Twenty documented sound-control CCs were sent in one collision-resistant batch and correlated to operation 41. A complete CC9 sweep activated all 22 oscillator engines. The generic guarded probe independently reproduced cutoff CC23 at three live aliases; documented Hold CC64 produced no live-table change. Every experiment verified an exact 384-word recovery.",
        ),
        "global.device.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Read-only operation-43 queries return all 43 firmware-5 named globals. Twelve hidden codes were recovered from the fingerprinted MCC table and confirmed on hardware. Thirty-four decode through installed-description labels; firmware setter clamps bound the other nine without guessing unknown units.",
        ),
        "global.device.write": Capability(
            level=SupportLevel.GUARDED,
            note="Operation 42 accepts a named code/value pair but provides no acknowledgement. Root Note 0x46 and hidden Automation Out 0x23 were hardware-proven target/inverse through operation-43 readback with no active-table change. All 43 firmware-bounded domains support backup-before-write and exact target readback; labels preserve raw values when semantic units remain unknown.",
        ),
        "runtime.status.read": Capability(
            level=SupportLevel.PARTIAL,
            note="Operation 49/6 kind 0x13 exports all seven firmware-backed status selectors. Raw operation-48 frames and structural 16/32-bit values are hardware verified with exact before/after checks of all 384 live words and 43 globals; external meanings of several runtime words remain unresolved.",
        ),
        "wavetable.file.prepare": Capability(
            level=SupportLevel.VERIFIED,
            note="32 cycles x 256 samples, mono PCM16 at 32 kHz; plain .mfw and one-entry .mfwz are supported.",
        ),
        "wavetable.bank.file": Capability(
            level=SupportLevel.RESEARCH,
            note="Lossless 16-slot MCC directory JSON is verified; .mfwbz uses the observed sibling project/bank ZIP topology pending Control Center archive-picker confirmation.",
        ),
        "wavetable.device.read": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent CoreMIDI and Elektroid readers support all 16 slots; slot-1 Ney JSON matched byte-for-byte.",
        ),
        "wavetable.device.upload": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent and delegated arbitrary uploads use backup, exact readback, and rollback. Direct slot-2 upload/read/clear was hardware-verified while slot 1 remained untouched.",
        ),
        "sample.device.inventory": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent CoreMIDI reads all 128 lossless directory headers. Slot-1 Ney was stable across repeated hardware reads.",
        ),
        "sample.device.download": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent CoreMIDI sample-body download is hardware-verified. Operation 5B selects/resets the object and operation 59 streams sequential 4 KiB blocks; a 384,000-byte sample matched exactly across two complete reads.",
        ),
        "sample.device.upload": Capability(
            level=SupportLevel.VERIFIED,
            note="Independent CoreMIDI allocation, header, and body upload is guarded by a lossless header-plus-PCM backup and exact operation-59 readback. A 384,000-byte slot-2 upload matched exactly, cleared back to empty, and a final full slot-1 read retained its original SHA-256.",
        ),
    },
}


def capabilities_for(device: DeviceModel) -> dict[str, Capability]:
    return DEVICE_CAPABILITIES[device]
