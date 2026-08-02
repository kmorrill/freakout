"""Decode Arturia's Collage USB/protobuf transport used by MiniFreak V.

The public API is derived from passive traffic and serialized protobuf file
descriptors embedded in the installed MiniFreak V binary. No Arturia source or
generated protobuf code is copied into this project.
"""

from __future__ import annotations

import base64
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Iterator

from google.protobuf import descriptor_pb2, descriptor_pool, json_format
from google.protobuf.message import DecodeError, Message
from google.protobuf.message_factory import GetMessageClass


COLLAGE_PACKAGE = "Arturia.Collage.Protobuf"
COLLAGE_DESCRIPTOR_NAMES = (
    "collage_message_control_resource.proto",
    "collage_message_control_system_common.proto",
    "collage_message_control_system_command.proto",
    "collage_message_control_system_status.proto",
    "collage_message_control_system.proto",
    "collage_message_control.proto",
    "collage_message_data_application.proto",
    "collage_message_data_parameter.proto",
    "collage_message_data.proto",
    "collage_message_security.proto",
    "collage_message_test_chunk.proto",
    "collage_message_test.proto",
    "collage.proto",
)

FRAME_RESPONSE = 0x10
FRAME_REQUEST = 0x11
FRAME_FLOW = 0x12
FRAME_SESSION = 0x13
FRAME_TYPES = frozenset((FRAME_RESPONSE, FRAME_REQUEST, FRAME_FLOW, FRAME_SESSION))


class CollageError(RuntimeError):
    pass


def _read_varint(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(10):
        if offset >= len(data):
            raise CollageError("truncated protobuf varint")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, offset
        shift += 7
    raise CollageError("invalid protobuf varint")


def _descriptor_end(data: bytes, offset: int) -> int:
    """Find the end of one serialized FileDescriptorProto in a Mach-O image."""
    valid_fields = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 14}
    position = offset
    while position < len(data):
        field_start = position
        key, position = _read_varint(data, position)
        field_number = key >> 3
        wire_type = key & 0x07
        if field_number not in valid_fields or wire_type in {3, 4, 6, 7}:
            return field_start
        if wire_type == 0:
            _, position = _read_varint(data, position)
        elif wire_type == 1:
            position += 8
        elif wire_type == 2:
            size, position = _read_varint(data, position)
            position += size
        elif wire_type == 5:
            position += 4
        if position > len(data):
            raise CollageError("truncated serialized protobuf descriptor")
    return position


def extract_collage_descriptors(
    binary: str | Path,
) -> list[descriptor_pb2.FileDescriptorProto]:
    """Extract Collage schemas from an installed MiniFreak V Mach-O binary."""
    data = Path(binary).read_bytes()
    descriptors: list[descriptor_pb2.FileDescriptorProto] = []
    for name in COLLAGE_DESCRIPTOR_NAMES:
        encoded_name = name.encode("utf-8")
        if len(encoded_name) >= 0x80:
            raise CollageError(f"descriptor name is unexpectedly long: {name}")
        marker = bytes((0x0A, len(encoded_name))) + encoded_name
        search_from = 0
        found: descriptor_pb2.FileDescriptorProto | None = None
        while True:
            start = data.find(marker, search_from)
            if start < 0:
                break
            search_from = start + 1
            try:
                end = _descriptor_end(data, start)
                candidate = descriptor_pb2.FileDescriptorProto.FromString(
                    data[start:end]
                )
            except (CollageError, DecodeError):
                continue
            if candidate.name == name and candidate.package == COLLAGE_PACKAGE:
                found = candidate
                break
        if found is None:
            raise CollageError(f"Collage descriptor not found: {name}")
        descriptors.append(found)
    return descriptors


@dataclass(frozen=True)
class CollageFrame:
    direction: str
    frame_type: int
    declared_length: int
    channel: int
    payload: bytes
    raw: bytes
    timestamp: float | None = None

    @classmethod
    def from_bytes(
        cls,
        raw: bytes,
        *,
        direction: str = "unknown",
        timestamp: float | None = None,
    ) -> "CollageFrame":
        if len(raw) < 5:
            raise CollageError("Collage frame must be at least five bytes")
        if raw[0] not in FRAME_TYPES:
            raise CollageError(f"unknown Collage frame type 0x{raw[0]:02x}")
        declared_length = int.from_bytes(raw[1:4], "little")
        expected = 5 + declared_length
        if len(raw) != expected:
            raise CollageError(
                f"Collage frame length mismatch: header={declared_length}, "
                f"actual={len(raw) - 5}"
            )
        return cls(
            direction=direction,
            frame_type=raw[0],
            declared_length=declared_length,
            channel=raw[4],
            payload=raw[5:],
            raw=raw,
            timestamp=timestamp,
        )

    @property
    def kind(self) -> str:
        return {
            FRAME_RESPONSE: "response",
            FRAME_REQUEST: "request",
            FRAME_FLOW: "flow",
            FRAME_SESSION: "session",
        }[self.frame_type]


class CollageStreamDecoder:
    """Reassemble Collage frames split across 64-byte USB bulk packets."""

    def __init__(self, *, max_frame_size: int = 16 * 1024 * 1024) -> None:
        self.max_frame_size = max_frame_size
        self._buffers: dict[str, bytearray] = {}

    def feed(
        self,
        direction: str,
        data: bytes,
        *,
        timestamp: float | None = None,
    ) -> list[CollageFrame]:
        buffer = self._buffers.setdefault(direction, bytearray())
        buffer.extend(data)
        frames: list[CollageFrame] = []
        while len(buffer) >= 5:
            if buffer[0] not in FRAME_TYPES:
                raise CollageError(
                    f"Collage stream lost framing at 0x{buffer[0]:02x}"
                )
            length = int.from_bytes(buffer[1:4], "little")
            if length > self.max_frame_size:
                raise CollageError(f"Collage frame is implausibly large: {length}")
            total = 5 + length
            if len(buffer) < total:
                break
            raw = bytes(buffer[:total])
            del buffer[:total]
            frames.append(
                CollageFrame.from_bytes(
                    raw, direction=direction, timestamp=timestamp
                )
            )
        return frames


class CollageCodec:
    def __init__(
        self, descriptors: Iterable[descriptor_pb2.FileDescriptorProto]
    ) -> None:
        pending = {descriptor.name: descriptor for descriptor in descriptors}
        self.pool = descriptor_pool.DescriptorPool()
        while pending:
            progress = False
            for name, descriptor in list(pending.items()):
                try:
                    self.pool.Add(descriptor)
                except TypeError:
                    continue
                del pending[name]
                progress = True
            if not progress:
                raise CollageError(
                    "could not resolve Collage descriptor dependencies: "
                    + ", ".join(sorted(pending))
                )
        top_descriptor = self.pool.FindMessageTypeByName(f"{COLLAGE_PACKAGE}.Top")
        self.top_class = GetMessageClass(top_descriptor)

    @classmethod
    def from_arturia_binary(cls, binary: str | Path) -> "CollageCodec":
        return cls(extract_collage_descriptors(binary))

    def decode(self, frame: CollageFrame) -> Message | None:
        if frame.frame_type not in {FRAME_REQUEST, FRAME_RESPONSE}:
            return None
        candidates = [frame.payload]
        # Captured requests carry one transport terminator after the protobuf.
        if frame.frame_type == FRAME_REQUEST and frame.payload:
            candidates.insert(0, frame.payload[:-1])
        for payload in candidates:
            try:
                message = self.top_class.FromString(payload)
            except DecodeError:
                continue
            if message.ListFields():
                return message
        return None

    @staticmethod
    def to_dict(message: Message) -> dict[str, Any]:
        return json_format.MessageToDict(
            message,
            preserving_proto_field_name=True,
            use_integers_for_enums=False,
        )

    @staticmethod
    def operation(message: Message) -> str:
        parts: list[str] = []
        current: Message | None = message
        while current is not None:
            descriptor = current.DESCRIPTOR
            oneof = descriptor.oneofs_by_name.get("content")
            if oneof is None:
                break
            selected = current.WhichOneof("content")
            if selected is None:
                break
            parts.append(selected)
            field = descriptor.fields_by_name[selected]
            if field.message_type is None:
                break
            current = getattr(current, selected)
        return ".".join(parts) or "top"


_CAPTURE_KIND = re.compile(r"\bkind=(bulk-(?:in|out))\b")
_CAPTURE_DATA = re.compile(r"\bdata=([0-9a-fA-F]*)")


def iter_capture_frames(path: str | Path) -> Iterator[CollageFrame]:
    decoder = CollageStreamDecoder()
    with Path(path).open() as capture:
        yield from _iter_capture_lines(capture, decoder)


def _iter_capture_lines(
    lines: Iterable[str], decoder: CollageStreamDecoder
) -> Iterator[CollageFrame]:
    for line in lines:
        kind_match = _CAPTURE_KIND.search(line)
        data_match = _CAPTURE_DATA.search(line)
        if kind_match is None or data_match is None or not data_match.group(1):
            continue
        try:
            timestamp = float(line.split(" ", 1)[0])
        except ValueError:
            timestamp = None
        data = bytes.fromhex(data_match.group(1))
        yield from decoder.feed(
            kind_match.group(1), data, timestamp=timestamp
        )


def _decode_bytes_field(value: str) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
        return raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return value


@dataclass
class CollageCaptureSummary:
    frames: Counter[str] = field(default_factory=Counter)
    operations: Counter[str] = field(default_factory=Counter)
    decoded_messages: int = 0
    parameters: dict[int, dict[str, Any]] = field(default_factory=dict)
    resources: list[dict[str, Any]] = field(default_factory=list)
    retrieved_resources: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frames": dict(sorted(self.frames.items())),
            "decoded_messages": self.decoded_messages,
            "operations": dict(sorted(self.operations.items())),
            "parameters": {
                str(key): value for key, value in sorted(self.parameters.items())
            },
            "resources": self.resources,
            "retrieved_resources": self.retrieved_resources,
        }


@dataclass(frozen=True)
class RetrievedResource:
    message_id: int
    name: bytes
    location: str
    data: bytes
    total_size: int
    complete: bool

    def to_dict(self, *, include_content: bool = True) -> dict[str, Any]:
        try:
            name_text: str | None = self.name.decode("utf-8")
        except UnicodeDecodeError:
            name_text = None
        result: dict[str, Any] = {
            "message_id": self.message_id,
            "name_base64": base64.b64encode(self.name).decode("ascii"),
            "name_utf8": name_text,
            "location": self.location,
            "total_size": self.total_size,
            "complete": self.complete,
            "sha256": hashlib.sha256(self.data).hexdigest(),
        }
        if include_content:
            result["content_base64"] = base64.b64encode(self.data).decode("ascii")
        return result


def extract_retrieved_resources(
    path: str | Path, codec: CollageCodec
) -> list[RetrievedResource]:
    states: dict[int, dict[str, Any]] = {}
    for frame in iter_capture_frames(path):
        message = codec.decode(frame)
        if message is None:
            continue
        operation = codec.operation(message)
        message_id = int(message.message_id)
        if operation == "control.resource.request.retrieve":
            request = message.control.resource.request.retrieve
            field = request.DESCRIPTOR.fields_by_name["location"]
            location = field.enum_type.values_by_number[int(request.location)].name
            states[message_id] = {
                "name": bytes(request.name),
                "location": location,
                "total_size": 0,
                "chunks": {},
            }
        elif operation == "control.resource.response.retrieve":
            response = message.control.resource.response.retrieve
            state = states.setdefault(
                message_id,
                {"name": b"", "location": "unknown", "total_size": 0, "chunks": {}},
            )
            state["total_size"] = max(
                int(state["total_size"]), int(response.total_size)
            )
            state["chunks"][int(response.offset)] = bytes(response.content)

    resources: list[RetrievedResource] = []
    for message_id, state in sorted(states.items()):
        total_size = int(state["total_size"])
        if total_size <= 0:
            continue
        data = bytearray(total_size)
        covered = bytearray(total_size)
        for offset, content in state["chunks"].items():
            end = min(total_size, offset + len(content))
            data[offset:end] = content[: end - offset]
            covered[offset:end] = b"\x01" * (end - offset)
        resources.append(
            RetrievedResource(
                message_id=message_id,
                name=state["name"],
                location=state["location"],
                data=bytes(data),
                total_size=total_size,
                complete=all(covered),
            )
        )
    return resources


def summarize_capture(
    path: str | Path, codec: CollageCodec
) -> CollageCaptureSummary:
    summary = CollageCaptureSummary()
    for frame in iter_capture_frames(path):
        summary.frames[f"{frame.direction}.{frame.kind}"] += 1
        message = codec.decode(frame)
        if message is None:
            continue
        summary.decoded_messages += 1
        operation = codec.operation(message)
        summary.operations[operation] += 1
        document = codec.to_dict(message)

        if operation.startswith("data."):
            data_kind, action = operation.split(".")[1:3]
            action_data = document["data"][data_kind].get(action, {})
            for parameter in action_data.get("parameters", []):
                identifier = parameter.get("id", {}).get("single")
                if identifier is None:
                    continue
                value_block = parameter.get("value", {})
                value_type, value = (
                    next(iter(value_block.items()))
                    if value_block
                    else ("unset", None)
                )
                summary.parameters[int(identifier)] = {
                    "status": parameter.get("status", "unknown"),
                    "value_type": value_type,
                    "value": value,
                    "source": operation,
                }

        if operation.startswith("control.resource."):
            control_kind, action = operation.split(".")[2:4]
            action_data = document["control"]["resource"][control_kind].get(
                action, {}
            )
            resource = {"operation": operation, **action_data}
            if isinstance(resource.get("name"), str):
                resource["name"] = _decode_bytes_field(resource["name"])
            if "content" in resource:
                content = resource.pop("content")
                resource["content_bytes"] = len(base64.b64decode(content))
            summary.resources.append(resource)
    summary.retrieved_resources = [
        resource.to_dict() for resource in extract_retrieved_resources(path, codec)
    ]
    return summary


def _fixed_text(payload: bytes, start: int, end: int) -> str | None:
    text = payload[start:end].split(b"\x00", 1)[0]
    if not text:
        return None
    try:
        return text.decode("utf-8")
    except UnicodeDecodeError:
        return None


def patch_document_from_resource(
    resource: RetrievedResource,
    *,
    parameters: dict[int, dict[str, Any]] | None = None,
) -> "PatchDocument":
    """Build shared JSON from one complete current MiniFreak resource."""
    from minifreak_patch.schema import (
        DeviceModel,
        MiniFreakHardwareData,
        MiniFreakHardwareParameter,
        MiniFreakPatchData,
        PatchDocument,
        PatchMetadata,
    )
    from minifreak_patch.minifreak_payload import decode_verified_parameters

    if resource.location != "RESOURCE_LOCATION_PRESET" or not resource.complete:
        raise CollageError("a complete MiniFreak preset resource is required")
    payload = resource.data
    if len(payload) < 128:
        raise CollageError("MiniFreak preset resource is unexpectedly short")
    transport_parameters = {
        str(identifier): MiniFreakHardwareParameter.model_validate(value)
        for identifier, value in (parameters or {}).items()
    }
    transport_parameters.update(
        {
            key: MiniFreakHardwareParameter.model_validate(value)
            for key, value in decode_verified_parameters(payload).items()
        }
    )
    name = _fixed_text(payload, 8, 22) or "Unknown"
    author = _fixed_text(payload, 22, 36)
    pack = _fixed_text(payload, 38, 59) or "User"
    description = _fixed_text(payload, 59, 128)
    return PatchDocument(
        device=DeviceModel.MINIFREAK,
        metadata=PatchMetadata(
            name=name,
            author=author,
            description=description,
        ),
        minifreak=MiniFreakPatchData(
            pack=pack,
            parameters={},
            hardware=MiniFreakHardwareData(
                resource_location=resource.location,
                resource_name_base64=base64.b64encode(resource.name).decode("ascii"),
                raw_payload_base64=base64.b64encode(payload).decode("ascii"),
                transport_parameters=transport_parameters,
            ),
        ),
    )


def patch_document_from_capture(
    path: str | Path, codec: CollageCodec
) -> "PatchDocument":
    """Build lossless shared JSON for the current MiniFreak preset resource."""
    resources = [
        resource
        for resource in extract_retrieved_resources(path, codec)
        if resource.location == "RESOURCE_LOCATION_PRESET" and resource.complete
    ]
    if not resources:
        raise CollageError("capture contains no complete MiniFreak preset resource")
    summary = summarize_capture(path, codec)
    return patch_document_from_resource(
        resources[-1], parameters=summary.parameters
    )
