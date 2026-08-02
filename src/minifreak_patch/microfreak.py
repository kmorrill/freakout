"""Lossless MicroFreak plain preset archive support.

The archive is a Boost.Serialization text object containing a short header
and a signed-byte payload. Named parameter decoding is intentionally kept
separate from raw preservation.
"""

from __future__ import annotations

import base64
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from minifreak_patch.parser import ParseError, Tokenizer
from minifreak_patch.schema import (
    DeviceModel,
    MicroFreakArchiveData,
    MicroFreakOscillatorEngineData,
    MicroFreakPatchData,
    MicroFreakParameterEvidence,
    MicroFreakSequenceData,
    MicroFreakSequenceAutomationDestination,
    MicroFreakSequencePattern,
    MicroFreakSequenceStep,
    MicroFreakStructuredParameter,
    PatchDocument,
    PatchMetadata,
    decode_microfreak_characteristics,
)
from minifreak_patch.zipwriter import create_zip


MICROFREAK_PRESET_TAG = "174"
MICROFREAK_BANK_PRESET_TAG = "134"
MICROFREAK_PRESET_PAYLOAD_SIZE = 4672
MICROFREAK_CATEGORIES = {
    0: "Bass",
    1: "Brass",
    2: "Keys",
    3: "Lead",
    4: "Organ",
    5: "Pad",
    6: "Percussion",
    7: "Sequence",
    8: "SFX",
    9: "Strings",
    10: "Template",
    11: "Vocoder",
}


@dataclass
class MicroFreakObject:
    version_tag: str
    name: str
    p0: int
    p3: int
    p5: int
    payload: bytes
    characteristics_bits: str = "000000000000000000"

    @classmethod
    def from_bytes(cls, data: bytes) -> "MicroFreakObject":
        if data.startswith(b"PK"):
            with zipfile.ZipFile(BytesIO(data)) as archive:
                names = archive.namelist()
                if len(names) != 1:
                    raise ParseError("expected one object in MicroFreak ZIP")
                data = archive.read(names[0])
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError("MicroFreak object is not UTF-8 text") from exc
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> "MicroFreakObject":
        tok = Tokenizer(text)
        if tok.read_length_prefixed_string() != "serialization::archive":
            raise ParseError("invalid MicroFreak archive magic")
        if tok.read_int() != 10 or tok.read_int() != 0 or tok.read_int() != 4:
            raise ParseError("unsupported MicroFreak archive header")
        version_tag = tok.read_length_prefixed_string()
        name = tok.read_length_prefixed_string()
        p0 = tok.read_int()
        if tok.read_int() != 0 or tok.read_int() != 0:
            raise ParseError("unsupported MicroFreak object flags")
        characteristics_bits = tok.read_length_prefixed_string()
        if len(characteristics_bits) != 18 or any(
            char not in "01" for char in characteristics_bits
        ):
            raise ParseError("invalid MicroFreak characteristics bits")
        p3 = tok.read_int()
        if tok.read_int() != 0:
            raise ParseError("unsupported MicroFreak object flag")
        p5 = tok.read_int()
        size = tok.read_int()
        signed = [tok.read_int() for _ in range(size)]
        if any(value < -128 or value > 127 for value in signed):
            raise ParseError("MicroFreak payload contains a non-byte value")
        return cls(
            version_tag=version_tag,
            name=name,
            p0=p0,
            p3=p3,
            p5=p5,
            payload=bytes(value & 0xFF for value in signed),
            characteristics_bits=characteristics_bits,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "MicroFreakObject":
        return cls.from_bytes(Path(path).read_bytes())

    def to_text(self) -> str:
        values = " ".join(str(value if value < 128 else value - 256)
                          for value in self.payload)
        payload_values = f" {values}" if values else ""
        return (
            "22 serialization::archive 10 0 4 "
            f"{len(self.version_tag)} {self.version_tag} "
            f"{len(self.name)} {self.name} "
            f"{self.p0} 0 0 18 {self.characteristics_bits} "
            f"{self.p3} 0 {self.p5} {len(self.payload)}{payload_values}\n"
        )

    def to_bytes(self) -> bytes:
        return self.to_text().encode("utf-8")


@dataclass
class MicroFreakPreset:
    name: str
    category_id: int
    init: int
    p1: int
    payload: bytes
    version_tag: str = MICROFREAK_PRESET_TAG
    characteristics_bits: str = "000000000000000000"

    @classmethod
    def from_bytes(cls, data: bytes) -> "MicroFreakPreset":
        obj = MicroFreakObject.from_bytes(data)
        if not obj.version_tag:
            raise ParseError("MicroFreak archive tag is empty")
        if len(obj.payload) not in (0, MICROFREAK_PRESET_PAYLOAD_SIZE):
            raise ParseError(
                f"unexpected MicroFreak preset payload size {len(obj.payload)}"
            )
        return cls(
            name=obj.name,
            category_id=obj.p0,
            init=obj.p3,
            p1=obj.p5,
            payload=obj.payload,
            version_tag=obj.version_tag,
            characteristics_bits=obj.characteristics_bits,
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "MicroFreakPreset":
        return cls.from_bytes(Path(path).read_bytes())

    def to_bytes(self) -> bytes:
        self.validate()
        return MicroFreakObject(
            version_tag=self.version_tag,
            name=self.name,
            p0=self.category_id,
            p3=self.init,
            p5=self.p1,
            payload=self.payload,
            characteristics_bits=self.characteristics_bits,
        ).to_bytes()

    def to_zip(self) -> bytes:
        """Serialize the official one-entry .mfpz preset container."""
        return create_zip([("0_preset", self.to_bytes())])

    def validate(self) -> None:
        if not self.version_tag or len(self.version_tag.encode("utf-8")) > 64:
            raise ValueError("MicroFreak archive tag must be 1..64 UTF-8 bytes")
        name_size = len(self.name.encode("utf-8"))
        if self.payload and name_size > 14:
            raise ValueError("occupied MicroFreak preset names are at most 14 bytes")
        if not self.payload and name_size > 255:
            raise ValueError("empty MicroFreak bank labels are at most 255 bytes")
        if len(self.characteristics_bits) != 18 or any(
            char not in "01" for char in self.characteristics_bits
        ):
            raise ValueError(
                "MicroFreak characteristics_bits must be 18 binary characters"
            )
        if not 0 <= self.category_id <= 255:
            raise ValueError("MicroFreak category_id must be 0..255")
        if not 0 <= self.init <= 255 or not 0 <= self.p1 <= 255:
            raise ValueError("MicroFreak archive flags must be 0..255")
        if len(self.payload) not in (0, MICROFREAK_PRESET_PAYLOAD_SIZE):
            raise ValueError(
                f"MicroFreak preset payload must be 0 or "
                f"{MICROFREAK_PRESET_PAYLOAD_SIZE} bytes"
            )

    def to_document(self, source_slot: int | None = None) -> PatchDocument:
        decoded_parameters = {}
        parameter_evidence = {}
        structured_parameters = {}
        oscillator_engine = None
        sequence_patterns = None
        if self.payload:
            from minifreak_patch.microfreak_payload import (
                decode_microfreak_parameters,
            )

            for key, decoded in decode_microfreak_parameters(self.payload).items():
                spec = decoded.spec
                if decoded.byte_offsets is not None:
                    offsets = list(decoded.byte_offsets)
                else:
                    offsets = [spec.lsb_offset]
                    if spec.msb_offset is not None:
                        offsets.append(spec.msb_offset)
                    if spec.flag_offset is not None:
                        offsets.append(spec.flag_offset)
                decoded_parameters[key] = decoded.value
                parameter_evidence[key] = MicroFreakParameterEvidence(
                    status=decoded.status,
                    value_type=spec.value_type,
                    raw_value=decoded.raw_value,
                    byte_offsets=sorted(set(offsets)),
                    flag_mask=spec.flag_mask,
                    encoding=decoded.evidence_encoding or spec.encoding,
                )
            from minifreak_patch.microfreak_structured import (
                interpret_structured_field,
                parse_structured_fields,
                structured_field_role,
            )

            parsed_structured = parse_structured_fields(self.payload)
            for key, field in parsed_structured.items():
                interpreted = interpret_structured_field(field)
                role, role_evidence = structured_field_role(key)
                structured_parameters[key] = MicroFreakStructuredParameter(
                    group=field.group,
                    name=field.name,
                    metadata=field.metadata,
                    raw_u16=field.raw_u16,
                    raw_s16=field.raw_s16,
                    interpreted_value=interpreted.value,
                    value_label=interpreted.label,
                    value_kind=interpreted.kind,
                    value_minimum=interpreted.minimum,
                    value_maximum=interpreted.maximum,
                    packed_byte_offsets=list(field.packed_byte_offsets),
                    role=role,
                    role_evidence=role_evidence,
                )
            type_field = parsed_structured.get("VCO.Type")
            if type_field is not None:
                from minifreak_patch.microfreak_midi import (
                    MICROFREAK_OSCILLATOR_ENGINE_NAMES,
                )

                engine_index = int(interpret_structured_field(type_field).value)
                sample_capable = (
                    type_field.metadata >= 22
                    and "VCO.SmpIdx" in parsed_structured
                    and "Gen.SmpHash" in parsed_structured
                )
                oscillator_engine = MicroFreakOscillatorEngineData(
                    index=engine_index,
                    name=MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(
                        engine_index, f"Unknown {engine_index}"
                    ),
                    saved_layout_max_index=type_field.metadata,
                    saved_layout_family=(
                        "firmware_5_sample_capable"
                        if sample_capable
                        else "historical"
                    ),
                    can_select_all_firmware_5_engines=sample_capable,
                )
            from minifreak_patch.microfreak_sequence import (
                SEQUENCE_EVIDENCE,
                SEQUENCE_LAYOUT,
                parse_sequence_patterns,
            )

            patterns = parse_sequence_patterns(self.payload)
            if patterns:
                from minifreak_patch.microfreak_midi import (
                    MICROFREAK_LIVE_WORD_SEMANTICS,
                )

                def project_pattern(name: str) -> MicroFreakSequencePattern:
                    pattern = patterns[name]
                    return MicroFreakSequencePattern(
                        unpacked_offset=pattern.unpacked_offset,
                        automation_destinations=[
                            MicroFreakSequenceAutomationDestination(
                                lane=lane,
                                live_address=address,
                                parameter=(
                                    MICROFREAK_LIVE_WORD_SEMANTICS.get(address, {}).get(
                                        "parameter"
                                    )
                                    if address is not None
                                    else None
                                ),
                            )
                            for lane, address in enumerate(
                                pattern.automation_destination_addresses, start=1
                            )
                        ],
                        trailer_bytes=list(pattern.trailer_bytes),
                        steps=[
                            MicroFreakSequenceStep(
                                notes=list(step.notes),
                                note_bytes=list(step.note_bytes),
                                velocities=list(step.velocities),
                                automation_values=list(step.automation_values),
                                automation_mask=step.automation_mask,
                                note_event_code=step.note_event_code,
                                note_status=step.note_status,
                                reserved_bytes=list(step.reserved_bytes),
                                unclassified_bytes=list(step.unclassified_bytes),
                            )
                            for step in pattern.steps
                        ],
                    )

                sequence_patterns = MicroFreakSequenceData(
                    layout=SEQUENCE_LAYOUT,
                    evidence=SEQUENCE_EVIDENCE,
                    pattern_a=project_pattern("A"),
                    pattern_b=project_pattern("B"),
                )
        return PatchDocument(
            device=DeviceModel.MICROFREAK,
            metadata=PatchMetadata(
                name=self.name,
                category=MICROFREAK_CATEGORIES.get(self.category_id & 0x7F),
                source_slot=source_slot,
            ),
            microfreak=MicroFreakPatchData(
                archive=MicroFreakArchiveData(
                    version_tag=self.version_tag,
                    category_id=self.category_id,
                    init=self.init,
                    p1=self.p1,
                    characteristics_bits=self.characteristics_bits,
                    characteristics=decode_microfreak_characteristics(
                        self.characteristics_bits
                    ),
                ),
                decoded_parameters=decoded_parameters,
                parameter_evidence=parameter_evidence,
                structured_parameters=structured_parameters,
                oscillator_engine=oscillator_engine,
                sequence_patterns=sequence_patterns,
                raw_payload_base64=base64.b64encode(self.payload).decode("ascii"),
            ),
        )

    @classmethod
    def from_document(cls, document: PatchDocument) -> "MicroFreakPreset":
        if document.device != DeviceModel.MICROFREAK or document.microfreak is None:
            raise ValueError("not a MicroFreak patch document")
        block = document.microfreak
        payload = base64.b64decode(block.raw_payload_base64, validate=True)
        if payload and block.sequence_patterns is not None:
            from minifreak_patch.microfreak_sequence import apply_sequence_patterns

            payload = apply_sequence_patterns(payload, block.sequence_patterns)
        if payload and block.decoded_parameters:
            from minifreak_patch.microfreak_payload import decode_microfreak_parameters

            actual = {
                key: value.value
                for key, value in decode_microfreak_parameters(payload).items()
            }
            for key, expected in block.decoded_parameters.items():
                if key in actual and abs(float(expected) - float(actual[key])) > 1e-9:
                    raise ValueError(
                        f"decoded MicroFreak parameter {key!r} does not match the "
                        "lossless payload; use set-microfreak-json"
                    )
        if payload and block.structured_parameters:
            from minifreak_patch.microfreak_structured import (
                interpret_structured_field,
                parse_structured_fields,
            )

            actual_structured = parse_structured_fields(payload)
            for key, expected in block.structured_parameters.items():
                actual_field = actual_structured.get(key)
                if actual_field is None or actual_field.raw_u16 != expected.raw_u16:
                    raise ValueError(
                        f"structured MicroFreak parameter {key!r} does not match "
                        "the lossless payload; use set-microfreak-structured-json"
                    )
                if expected.interpreted_value is not None:
                    actual_value = interpret_structured_field(actual_field).value
                    legacy_sequence_offset = {
                        "Seq.Length": 4,
                        "Seq.GateLen": 10,
                    }.get(key)
                    legacy_offset_match = (
                        legacy_sequence_offset is not None
                        and expected.value_kind == "metadata_scaled_integer"
                        and abs(
                            float(actual_value)
                            - legacy_sequence_offset
                            - float(expected.interpreted_value)
                        )
                        <= 1e-9
                    )
                    if (
                        abs(float(actual_value) - float(expected.interpreted_value))
                        > 1e-9
                        and not legacy_offset_match
                    ):
                        raise ValueError(
                            f"interpreted MicroFreak parameter {key!r} does not "
                            "match the lossless payload; use "
                            "set-microfreak-structured-value"
                        )
        if payload and block.oscillator_engine is not None:
            from minifreak_patch.microfreak_midi import (
                MICROFREAK_OSCILLATOR_ENGINE_NAMES,
            )
            from minifreak_patch.microfreak_structured import (
                interpret_structured_field,
                parse_structured_fields,
            )

            fields = parse_structured_fields(payload)
            type_field = fields.get("VCO.Type")
            if type_field is None:
                raise ValueError("oscillator_engine requires tagged VCO.Type")
            index = int(interpret_structured_field(type_field).value)
            sample_capable = (
                type_field.metadata >= 22
                and "VCO.SmpIdx" in fields
                and "Gen.SmpHash" in fields
            )
            family = (
                "firmware_5_sample_capable" if sample_capable else "historical"
            )
            expected = block.oscillator_engine
            if (
                expected.index != index
                or expected.name
                != MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(index, f"Unknown {index}")
                or expected.saved_layout_max_index != type_field.metadata
                or expected.can_select_all_firmware_5_engines != sample_capable
                or expected.saved_layout_family != family
            ):
                raise ValueError(
                    "oscillator_engine summary does not match the lossless payload; "
                    "use set-microfreak-json"
                )
        preset = cls(
            name=document.metadata.name,
            category_id=block.archive.category_id,
            init=block.archive.init,
            p1=block.archive.p1,
            payload=payload,
            version_tag=block.archive.version_tag,
            characteristics_bits=block.archive.characteristics_bits,
        )
        preset.validate()
        return preset
