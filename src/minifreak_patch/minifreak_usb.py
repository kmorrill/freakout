"""Independent MiniFreak Collage USB transport.

Only the vendor interface (interface 0, endpoints 0x04/0x83) is claimed, so
CoreMIDI can continue to own the separate MIDI interface. Reads are public;
live writes are limited to independently verified session parameters and use
exact readback plus automatic restoration on failure. Saved-preset writes and
remove operations are intentionally absent from this module.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from minifreak_patch.collage import (
    CollageCodec,
    CollageError,
    CollageFrame,
    CollageStreamDecoder,
    FRAME_REQUEST,
    RetrievedResource,
)
from minifreak_patch.minifreak_payload import (
    LIVE_SESSION_PARAMETERS,
    MINIFREAK_CHECKSUM_OFFSET,
    MINIFREAK_HARDWARE_PRESET_SIZE,
    VERIFIED_PARAMETERS,
    checksum_is_valid,
    decode_verified_parameters,
    set_verified_parameter,
    with_updated_checksum,
)


MINIFREAK_USB_VENDOR_ID = 0x1C75
MINIFREAK_USB_PRODUCT_ID = 0x0602
MINIFREAK_COLLAGE_INTERFACE = 0
MINIFREAK_COLLAGE_OUT = 0x04
MINIFREAK_COLLAGE_IN = 0x83

DEFAULT_ARTURIA_BINARIES = (
    Path(
        "/Library/Audio/Plug-Ins/VST3/MiniFreak V.vst3/Contents/MacOS/MiniFreak V"
    ),
    Path("/Applications/Arturia/MiniFreak V.app/Contents/MacOS/MiniFreak V"),
)


def find_arturia_binary() -> Path:
    """Find the installed binary that contains the Collage protobuf schema."""
    for candidate in DEFAULT_ARTURIA_BINARIES:
        if candidate.is_file():
            return candidate
    raise CollageError(
        "MiniFreak V is required for its installed Collage schema; pass "
        "--arturia-binary if it is installed in a nonstandard location"
    )


def _request_frame(message: Any) -> bytes:
    # Requests observed on the wire carry one 0x38 transport terminator after
    # the serialized Top message. It is not part of the protobuf document.
    payload = message.SerializeToString() + b"\x38"
    return (
        bytes((FRAME_REQUEST,))
        + len(payload).to_bytes(3, "little")
        + b"\x00"
        + payload
    )


def _subscription_request(codec: CollageCodec) -> bytes:
    message = codec.top_class()
    identifier = message.data.request.parameter_subscribe.ids.add()
    identifier.mask = 0xFFFFFFFF
    return _request_frame(message)


def _resource_request(
    codec: CollageCodec,
    *,
    name: bytes,
    location: int,
    message_id: int = 1,
    chunk_size: int = 211,
) -> bytes:
    message = codec.top_class()
    message.message_id = message_id
    request = message.control.resource.request.retrieve
    request.name = name
    request.location = location
    request.size = chunk_size
    request.options = 1  # RESOURCE_OPTION_FAST
    return _request_frame(message)


def _resource_remove_frame(
    codec: CollageCodec,
    *,
    name: bytes,
    location: int,
    message_id: int = 1,
) -> bytes:
    message = codec.top_class()
    message.message_id = message_id
    request = message.control.resource.request.remove
    request.name = name
    request.location = location
    return _request_frame(message)


def _resource_store_frames(
    codec: CollageCodec,
    *,
    content: bytes,
    name: bytes = b"\xff\xff",
    location: int = 3,
    message_id: int = 1,
    chunk_size: int = 203,
) -> Iterator[bytes]:
    """Encode the official activating resource-store sequence.

    MiniFreak V uses a fresh incrementing Collage message ID for every chunk
    and the device acknowledges the final ID. Reusing one ID for the whole
    resource is accepted by the device but leaves the active buffer unchanged.
    """
    if not content:
        raise ValueError("MiniFreak resource content cannot be empty")
    if chunk_size <= 0:
        raise ValueError("MiniFreak resource chunk size must be positive")
    for offset in range(0, len(content), chunk_size):
        message = codec.top_class()
        message.message_id = message_id + offset // chunk_size
        request = message.control.resource.request.store
        request.name = name
        request.location = location
        request.is_start_of_resource = offset == 0
        request.content = content[offset : offset + chunk_size]
        request.total_size = len(content)
        yield _request_frame(message)


def _session_parameter_frame(parameter_id: int, raw_value: int) -> bytes:
    """Encode the verified one-parameter live-session frame."""
    if not 0 <= parameter_id <= 0x3FFF:
        raise ValueError("MiniFreak session parameter id must fit two-byte varint")
    if not -0x8000 <= raw_value <= 0x7FFF:
        raise ValueError("MiniFreak session parameter value must fit signed 16-bit")
    encoded_id = bytearray()
    remaining = parameter_id
    while True:
        byte = remaining & 0x7F
        remaining >>= 7
        encoded_id.append(byte | (0x80 if remaining else 0))
        if not remaining:
            break
    payload = (
        b"\x00\x00\x03\x01\x10"
        + bytes(encoded_id)
        + b"\x10\x00\x00"
        + raw_value.to_bytes(2, "little", signed=True)
        + b"\x38"
    )
    return bytes((0x13,)) + len(payload).to_bytes(3, "little") + b"\x00" + payload


@dataclass(frozen=True)
class MiniFreakActiveEditReport:
    parameter: str
    requested_value: float
    backup_path: Path
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool
    restored: bool = False
    restore_sha256: str | None = None


@dataclass(frozen=True)
class MiniFreakActiveBatchReport:
    parameters: dict[str, float]
    backup_path: Path
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool
    transport: str = "session-delta"
    restored: bool = False
    restore_sha256: str | None = None


@dataclass(frozen=True)
class MiniFreakSessionMapReport:
    backup_path: Path
    before_sha256: str
    changed_sha256: str
    restored_sha256: str
    exact_restore: bool
    unexplained_changed_bytes: int
    mappings: dict[str, dict[str, int | bool | str | None]]


@dataclass(frozen=True)
class MiniFreakSavedWriteReport:
    slot: int
    parameters: dict[str, float]
    backup_path: Path
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool


class MiniFreakUsbTransport:
    """Access MiniFreak resources without launching MiniFreak V."""

    def __init__(
        self,
        codec: CollageCodec,
        *,
        usb_core: Any | None = None,
        usb_util: Any | None = None,
    ) -> None:
        self.codec = codec
        if usb_core is None or usb_util is None:
            try:
                import usb.core as imported_core
                import usb.util as imported_util
            except ImportError as exc:  # pragma: no cover - installation error
                raise CollageError("direct MiniFreak reads require pyusb") from exc
            usb_core = imported_core
            usb_util = imported_util
        self.usb_core = usb_core
        self.usb_util = usb_util

    def _find(self) -> Any:
        device = self.usb_core.find(
            idVendor=MINIFREAK_USB_VENDOR_ID,
            idProduct=MINIFREAK_USB_PRODUCT_ID,
        )
        if device is None:
            raise CollageError("connected MiniFreak USB device was not found")
        return device

    def read_current_preset(self, *, timeout: float = 10.0) -> RetrievedResource:
        return self._read_resource(
            name=b"\xff\xff",
            location=3,
            location_name="RESOURCE_LOCATION_PRESET",
            timeout=timeout,
        )

    def read_saved_preset(
        self, slot: int, *, timeout: float = 10.0
    ) -> RetrievedResource:
        if not 1 <= slot <= 512:
            raise ValueError("MiniFreak preset slot must be 1..512")
        return self._read_resource(
            name=(slot - 1).to_bytes(2, "little"),
            location=3,
            location_name="RESOURCE_LOCATION_PRESET",
            timeout=timeout,
        )

    def read_preset_metadata(
        self, slot: int, *, timeout: float = 5.0
    ) -> RetrievedResource:
        if not 1 <= slot <= 512:
            raise ValueError("MiniFreak preset slot must be 1..512")
        return self._read_resource(
            name=(slot - 1).to_bytes(2, "little"),
            location=6,
            location_name="RESOURCE_LOCATION_METADATA",
            chunk_size=128,
            timeout=timeout,
        )

    def verify_active_parameter_transport(
        self,
        key: str,
        value: float,
        backup_path: str | Path,
        *,
        timeout: float = 10.0,
    ) -> MiniFreakActiveEditReport:
        """Apply one verified live field, prove exact readback, then restore."""
        if key not in LIVE_SESSION_PARAMETERS:
            raise CollageError(f"{key} is payload-mapped but not live-session writable")
        before = self.read_current_preset(timeout=timeout)
        stable = self.read_current_preset(timeout=timeout)
        if before.data != stable.data:
            raise CollageError(
                "MiniFreak current buffer changed during preflight; refusing write"
            )
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.data)
        target = set_verified_parameter(before.data, key, value)
        if target == before.data:
            raise CollageError("probe value must differ from the current value")
        spec = VERIFIED_PARAMETERS[key]
        target_raw = int.from_bytes(
            target[spec.offset : spec.offset + 2], "little", signed=True
        )
        before_raw = int.from_bytes(
            before.data[spec.offset : spec.offset + 2], "little", signed=True
        )
        after_data = b""
        restored_data = b""
        try:
            self._send_session_parameter(
                spec.session_parameter_id, target_raw, timeout=timeout
            )
            after_data = self.read_current_preset(timeout=timeout).data
        finally:
            self._send_session_parameter(
                spec.session_parameter_id, before_raw, timeout=timeout
            )
            restored_data = self.read_current_preset(timeout=timeout).data
        if restored_data != before.data:
            raise CollageError(
                "MiniFreak active buffer restore could not be verified; "
                f"raw backup: {backup}"
            )
        if after_data != target:
            raise CollageError(
                "MiniFreak active parameter write did not match expected payload; "
                f"restore verified; raw backup: {backup}"
            )
        return MiniFreakActiveEditReport(
            parameter=key,
            requested_value=value,
            backup_path=backup,
            before_sha256=hashlib.sha256(before.data).hexdigest(),
            target_sha256=hashlib.sha256(target).hexdigest(),
            readback_sha256=hashlib.sha256(after_data).hexdigest(),
            exact_readback=True,
            restored=True,
            restore_sha256=hashlib.sha256(restored_data).hexdigest(),
        )

    def write_active_parameter(
        self,
        key: str,
        value: float,
        backup_path: str | Path,
        *,
        timeout: float = 10.0,
    ) -> MiniFreakActiveEditReport:
        """Write one verified live field; restore automatically on mismatch."""
        if key not in LIVE_SESSION_PARAMETERS:
            raise CollageError(f"{key} is payload-mapped but not live-session writable")
        before = self.read_current_preset(timeout=timeout)
        stable = self.read_current_preset(timeout=timeout)
        if before.data != stable.data:
            raise CollageError(
                "MiniFreak current buffer changed during preflight; refusing write"
            )
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.data)
        target = set_verified_parameter(before.data, key, value)
        spec = VERIFIED_PARAMETERS[key]
        target_raw = int.from_bytes(
            target[spec.offset : spec.offset + 2], "little", signed=True
        )
        self._send_session_parameter(
            spec.session_parameter_id, target_raw, timeout=timeout
        )
        after = self.read_current_preset(timeout=timeout).data
        if after != target:
            before_raw = int.from_bytes(
                before.data[spec.offset : spec.offset + 2], "little", signed=True
            )
            self._send_session_parameter(
                spec.session_parameter_id, before_raw, timeout=timeout
            )
            restored = self.read_current_preset(timeout=timeout).data
            if restored != before.data:
                raise CollageError(
                    "MiniFreak write and automatic restore both failed; "
                    f"raw backup: {backup}"
                )
            raise CollageError(
                "MiniFreak write did not match expected payload; restore verified; "
                f"raw backup: {backup}"
            )
        return MiniFreakActiveEditReport(
            parameter=key,
            requested_value=value,
            backup_path=backup,
            before_sha256=hashlib.sha256(before.data).hexdigest(),
            target_sha256=hashlib.sha256(target).hexdigest(),
            readback_sha256=hashlib.sha256(after).hexdigest(),
            exact_readback=True,
        )

    def write_active_payload(
        self,
        target: bytes,
        backup_path: str | Path,
        *,
        timeout: float = 10.0,
    ) -> MiniFreakActiveBatchReport:
        """Apply all supported differences from a lossless hardware JSON payload.

        The target must differ from the connected edit buffer only at fields
        whose payload offsets have been hardware-verified. Live-session fields
        use compact deltas; corpus-only fields use the official activating
        resource-store sequence. Other byte differences are rejected before a
        device write occurs.
        """
        before = self.read_current_preset(timeout=timeout)
        stable = self.read_current_preset(timeout=timeout)
        if before.data != stable.data:
            raise CollageError(
                "MiniFreak current buffer changed during preflight; refusing write"
            )
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.data)

        if len(target) != MINIFREAK_HARDWARE_PRESET_SIZE:
            raise CollageError(
                f"MiniFreak target payload must be {MINIFREAK_HARDWARE_PRESET_SIZE} bytes"
            )
        if not checksum_is_valid(target):
            raise CollageError("MiniFreak target payload checksum is invalid")

        expected = before.data
        changed: dict[str, tuple[int, int, float]] = {}
        for key, spec in VERIFIED_PARAMETERS.items():
            target_raw = int.from_bytes(
                target[spec.offset : spec.offset + 2], "little", signed=True
            )
            before_raw = int.from_bytes(
                before.data[spec.offset : spec.offset + 2], "little", signed=True
            )
            if target_raw == before_raw:
                continue
            value = target_raw / 32767.0
            if not spec.minimum <= value <= spec.maximum:
                raise CollageError(
                    f"target {key} raw value {target_raw} is outside its verified range"
                )
            expected = set_verified_parameter(expected, key, value)
            changed[key] = (before_raw, target_raw, value)

        if expected != target:
            raise CollageError(
                "MiniFreak target contains unsupported byte changes; only "
                + ", ".join(VERIFIED_PARAMETERS)
                + " may be pushed live"
            )
        if not changed:
            raise CollageError("MiniFreak target has no supported live changes")

        if any(key not in LIVE_SESSION_PARAMETERS for key in changed):
            def restore_resource() -> bytes:
                acknowledged = self._store_current_preset(
                    before.data, timeout=timeout
                )
                restored_data = self.read_current_preset(timeout=timeout).data
                if not acknowledged:
                    raise CollageError(
                        "MiniFreak resource restore was not acknowledged"
                    )
                return restored_data

            try:
                acknowledged = self._store_current_preset(target, timeout=timeout)
                after = self.read_current_preset(timeout=timeout).data
            except Exception as exc:
                restored = restore_resource()
                if restored != before.data:
                    raise CollageError(
                        "MiniFreak resource write failed and exact restoration "
                        f"also failed; raw backup: {backup}"
                    ) from exc
                raise CollageError(
                    "MiniFreak resource write failed; exact restoration verified; "
                    f"raw backup: {backup}"
                ) from exc
            if not acknowledged or after != target:
                restored = restore_resource()
                if restored != before.data:
                    raise CollageError(
                        "MiniFreak resource readback differed and exact restoration "
                        f"failed; raw backup: {backup}"
                    )
                raise CollageError(
                    "MiniFreak resource readback differed; exact restoration "
                    f"verified; raw backup: {backup}"
                )
            return MiniFreakActiveBatchReport(
                parameters={
                    key: value for key, (_a, _b, value) in changed.items()
                },
                backup_path=backup,
                before_sha256=hashlib.sha256(before.data).hexdigest(),
                target_sha256=hashlib.sha256(target).hexdigest(),
                readback_sha256=hashlib.sha256(after).hexdigest(),
                exact_readback=True,
                transport="resource-store",
            )

        def restore() -> bytes:
            for key, (before_raw, _target_raw, _value) in reversed(changed.items()):
                self._send_session_parameter(
                    VERIFIED_PARAMETERS[key].session_parameter_id,
                    before_raw,
                    timeout=timeout,
                )
            return self.read_current_preset(timeout=timeout).data

        try:
            for key, (_before_raw, target_raw, _value) in changed.items():
                self._send_session_parameter(
                    VERIFIED_PARAMETERS[key].session_parameter_id,
                    target_raw,
                    timeout=timeout,
                )
            after = self.read_current_preset(timeout=timeout).data
        except Exception as exc:
            restored = restore()
            if restored != before.data:
                raise CollageError(
                    "MiniFreak live JSON write failed and exact restoration also "
                    f"failed; raw backup: {backup}"
                ) from exc
            raise CollageError(
                "MiniFreak live JSON write failed; exact restoration verified; "
                f"raw backup: {backup}"
            ) from exc

        if after != target:
            restored = restore()
            if restored != before.data:
                raise CollageError(
                    "MiniFreak live JSON readback differed and exact restoration "
                    f"failed; raw backup: {backup}"
                )
            raise CollageError(
                "MiniFreak live JSON readback differed; exact restoration verified; "
                f"raw backup: {backup}"
            )

        return MiniFreakActiveBatchReport(
            parameters={key: value for key, (_a, _b, value) in changed.items()},
            backup_path=backup,
            before_sha256=hashlib.sha256(before.data).hexdigest(),
            target_sha256=hashlib.sha256(target).hexdigest(),
            readback_sha256=hashlib.sha256(after).hexdigest(),
            exact_readback=True,
        )

    def write_saved_payload(
        self,
        slot: int,
        target: bytes,
        backup_path: str | Path,
        *,
        timeout: float = 10.0,
    ) -> MiniFreakSavedWriteReport:
        """Write mapped JSON changes to an occupied saved slot safely.

        Empty slots are refused because firmware 4.0.1 returns an I/O error for
        resource removal, so their exact empty state cannot yet be restored.
        """
        before = self.read_saved_preset(slot, timeout=timeout)
        stable = self.read_saved_preset(slot, timeout=timeout)
        if before.data != stable.data:
            raise CollageError(
                f"MiniFreak slot {slot} changed during preflight; refusing write"
            )
        if before.data[3] != 0x41:
            raise CollageError(
                f"MiniFreak slot {slot} is empty; empty-slot writes remain disabled"
            )
        expected_header = (slot - 1).to_bytes(2, "little")
        if before.data[:2] != expected_header:
            raise CollageError(f"MiniFreak slot {slot} has an unexpected header")
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.data)

        if len(target) != MINIFREAK_HARDWARE_PRESET_SIZE:
            raise CollageError(
                f"MiniFreak target payload must be {MINIFREAK_HARDWARE_PRESET_SIZE} bytes"
            )
        if not checksum_is_valid(target):
            raise CollageError("MiniFreak target payload checksum is invalid")
        if target[:2] != expected_header or target[3] != 0x41:
            raise CollageError("MiniFreak saved target does not belong to this slot")

        expected = before.data
        changed: dict[str, tuple[int, int, float]] = {}
        for key, spec in VERIFIED_PARAMETERS.items():
            target_raw = int.from_bytes(
                target[spec.offset : spec.offset + 2], "little", signed=True
            )
            before_raw = int.from_bytes(
                before.data[spec.offset : spec.offset + 2], "little", signed=True
            )
            if target_raw == before_raw:
                continue
            value = target_raw / 32767.0
            if not spec.minimum <= value <= spec.maximum:
                raise CollageError(
                    f"target {key} raw value {target_raw} is outside its verified range"
                )
            expected = set_verified_parameter(expected, key, value)
            changed[key] = (before_raw, target_raw, value)
        if expected != target:
            raise CollageError(
                "MiniFreak saved target contains unsupported byte changes"
            )
        if not changed:
            raise CollageError("MiniFreak saved target has no supported changes")

        def restore() -> bytes:
            acknowledged = self._store_saved_preset(
                slot, before.data, timeout=timeout
            )
            restored = self.read_saved_preset(slot, timeout=timeout).data
            if not acknowledged:
                raise CollageError("MiniFreak saved-slot restore was not acknowledged")
            return restored

        try:
            acknowledged = self._store_saved_preset(slot, target, timeout=timeout)
            after = self.read_saved_preset(slot, timeout=timeout).data
        except Exception as exc:
            restored = restore()
            if restored != before.data:
                raise CollageError(
                    "MiniFreak saved-slot write failed and exact restoration also "
                    f"failed; raw backup: {backup}"
                ) from exc
            raise CollageError(
                "MiniFreak saved-slot write failed; exact restoration verified; "
                f"raw backup: {backup}"
            ) from exc
        if not acknowledged or after != target:
            restored = restore()
            if restored != before.data:
                raise CollageError(
                    "MiniFreak saved-slot readback differed and exact restoration "
                    f"failed; raw backup: {backup}"
                )
            raise CollageError(
                "MiniFreak saved-slot readback differed; exact restoration verified; "
                f"raw backup: {backup}"
            )
        return MiniFreakSavedWriteReport(
            slot=slot,
            parameters={key: value for key, (_a, _b, value) in changed.items()},
            backup_path=backup,
            before_sha256=hashlib.sha256(before.data).hexdigest(),
            target_sha256=hashlib.sha256(target).hexdigest(),
            readback_sha256=hashlib.sha256(after).hexdigest(),
            exact_readback=True,
        )

    def verify_session_parameter_map(
        self,
        keys: list[str] | tuple[str, ...],
        backup_path: str | Path,
        *,
        timeout: float = 10.0,
    ) -> MiniFreakSessionMapReport:
        """Map many session IDs in one coded shot and restore exactly.

        Each ID receives a unique raw sentinel absent from the baseline. The
        resulting buffer locates every actual offset independently of the
        proposed mapping, allowing restoration with the value that truly
        occupied that offset before the experiment.
        """
        if not keys:
            raise ValueError("at least one MiniFreak session key is required")
        unknown = [key for key in keys if key not in VERIFIED_PARAMETERS]
        if unknown:
            raise CollageError("unknown MiniFreak session keys: " + ", ".join(unknown))
        without_session_ids = [
            key
            for key in keys
            if VERIFIED_PARAMETERS[key].session_parameter_id is None
        ]
        if without_session_ids:
            raise CollageError(
                "MiniFreak fields have payload mappings but no session-ID candidate: "
                + ", ".join(without_session_ids)
            )
        before = self.read_current_preset(timeout=timeout)
        stable = self.read_current_preset(timeout=timeout)
        if before.data != stable.data:
            raise CollageError(
                "MiniFreak current buffer changed during preflight; refusing probe"
            )
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.data)

        occupied = {
            int.from_bytes(before.data[offset : offset + 2], "little", signed=True)
            for offset in range(128, len(before.data) - 1, 2)
        }
        sentinels: dict[str, int] = {}
        used: set[int] = set()
        for index, key in enumerate(keys):
            spec = VERIFIED_PARAMETERS[key]
            candidate = 4096 + ((index * 733 + 271) % 23000)
            while candidate in occupied or candidate in used:
                candidate += 1
                if candidate > 30000:
                    candidate = 4096
            value = candidate / 32767.0
            if not spec.minimum <= value <= spec.maximum:
                raise CollageError(f"could not choose a safe sentinel for {key}")
            sentinels[key] = candidate
            used.add(candidate)

        after = b""
        actual_offsets: dict[str, int] = {}
        probe_error: Exception | None = None
        try:
            for key in keys:
                spec = VERIFIED_PARAMETERS[key]
                self._send_session_parameter(
                    spec.session_parameter_id, sentinels[key], timeout=timeout
                )
            after = self.read_current_preset(timeout=timeout).data
            for key, sentinel in sentinels.items():
                offsets = [
                    offset
                    for offset in range(128, len(after) - 1, 2)
                    if int.from_bytes(
                        after[offset : offset + 2], "little", signed=True
                    )
                    == sentinel
                ]
                if len(offsets) == 1:
                    actual_offsets[key] = offsets[0]
            changed_indices = {
                index
                for index, value in enumerate(after)
                if value != before.data[index]
            }
            allowed_indices = {MINIFREAK_CHECKSUM_OFFSET}
            for key in keys:
                offset = VERIFIED_PARAMETERS[key].offset
                allowed_indices.update((offset, offset + 1))
            unexplained = changed_indices - allowed_indices
            if unexplained:
                raise CollageError(
                    "bulk session probe changed bytes outside proposed parameter offsets: "
                    + ", ".join(str(index) for index in sorted(unexplained))
                )
        except Exception as exc:
            probe_error = exc
        finally:
            for key in reversed(keys):
                spec = VERIFIED_PARAMETERS[key]
                offset = actual_offsets.get(key, spec.offset)
                original = int.from_bytes(
                    before.data[offset : offset + 2], "little", signed=True
                )
                self._send_session_parameter(
                    spec.session_parameter_id, original, timeout=timeout
                )
            restored = self.read_current_preset(timeout=timeout).data

        if restored != before.data:
            raise CollageError(
                "MiniFreak bulk session probe did not restore exactly; "
                f"raw backup: {backup}"
            ) from probe_error
        if probe_error is not None:
            raise CollageError(
                "MiniFreak bulk session probe failed; exact restoration verified; "
                f"raw backup: {backup}; detail: {probe_error}"
            ) from probe_error
        mappings: dict[str, dict[str, int | bool | str | None]] = {}
        for key in keys:
            spec = VERIFIED_PARAMETERS[key]
            before_raw = int.from_bytes(
                before.data[spec.offset : spec.offset + 2], "little", signed=True
            )
            after_raw = int.from_bytes(
                after[spec.offset : spec.offset + 2], "little", signed=True
            )
            observed_offset = actual_offsets.get(key)
            if observed_offset == spec.offset:
                behavior = "exact"
            elif after_raw != before_raw:
                behavior = "quantized_or_clamped"
                observed_offset = spec.offset
            else:
                behavior = "no_change"
            mapping_verified = observed_offset == spec.offset
            mappings[key] = {
                "session_parameter_id": spec.session_parameter_id,
                "expected_offset": spec.offset,
                "observed_offset": observed_offset,
                "before_raw": before_raw,
                "requested_sentinel_raw": sentinels[key],
                "observed_raw": after_raw,
                "write_behavior": behavior,
                "formula_verified": mapping_verified
                and spec.offset == 128 + 2 * spec.session_parameter_id,
                "expected_mapping_verified": mapping_verified,
            }
        return MiniFreakSessionMapReport(
            backup_path=backup,
            before_sha256=hashlib.sha256(before.data).hexdigest(),
            changed_sha256=hashlib.sha256(after).hexdigest(),
            restored_sha256=hashlib.sha256(restored).hexdigest(),
            exact_restore=True,
            unexplained_changed_bytes=0,
            mappings=mappings,
        )

    def _send_session_parameter(
        self, parameter_id: int, raw_value: int, *, timeout: float
    ) -> None:
        device = self._find()
        decoder = CollageStreamDecoder()
        flow_out = 0x80

        def receive(timeout_ms: int = 100) -> None:
            nonlocal flow_out
            try:
                packet = bytes(
                    device.read(MINIFREAK_COLLAGE_IN, 1024, timeout=timeout_ms)
                )
            except self.usb_core.USBTimeoutError:
                return
            for frame in decoder.feed("bulk-in", packet):
                if frame.kind == "flow":
                    flow_out = 0xC0 if frame.channel & 0x40 else 0x80

        def send(raw: bytes) -> None:
            written = int(device.write(MINIFREAK_COLLAGE_OUT, raw, timeout=1000))
            if written != len(raw):
                raise CollageError(
                    f"short MiniFreak USB write: {written} of {len(raw)} bytes"
                )
            receive()

        self.usb_util.claim_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        try:
            for _ in range(12):
                send(bytes((0x12, 0, 0, 0, flow_out)))
            send(_session_parameter_frame(parameter_id, raw_value))
            for _ in range(12):
                send(bytes((0x12, 0, 0, 0, flow_out)))
        finally:
            self.usb_util.release_interface(device, MINIFREAK_COLLAGE_INTERFACE)

    def _store_current_preset(self, content: bytes, *, timeout: float) -> bool:
        """Store and activate one complete current-preset resource."""
        return self._store_preset_resource(
            content, name=b"\xff\xff", timeout=timeout
        )

    def _store_saved_preset(
        self, slot: int, content: bytes, *, timeout: float
    ) -> bool:
        if not 1 <= slot <= 512:
            raise ValueError("MiniFreak preset slot must be 1..512")
        return self._store_preset_resource(
            content, name=(slot - 1).to_bytes(2, "little"), timeout=timeout
        )

    def _store_preset_resource(
        self, content: bytes, *, name: bytes, timeout: float
    ) -> bool:
        """Store one active or saved preset using MiniFreak V framing."""
        device = self._find()
        decoder = CollageStreamDecoder()
        flow_out = 0x80
        chunk_size = 203
        expected_id = 1 + (len(content) - 1) // chunk_size
        acknowledged = False

        def receive(timeout_ms: int = 1000) -> None:
            nonlocal flow_out, acknowledged
            try:
                packet = bytes(
                    device.read(MINIFREAK_COLLAGE_IN, 1024, timeout=timeout_ms)
                )
            except self.usb_core.USBTimeoutError:
                return
            for frame in decoder.feed("bulk-in", packet):
                if frame.kind == "flow":
                    flow_out = 0xC0 if frame.channel & 0x40 else 0x80
                    continue
                message = self.codec.decode(frame)
                if (
                    message is not None
                    and int(message.message_id) == expected_id
                    and self.codec.operation(message)
                    == "control.resource.response.store"
                ):
                    acknowledged = True

        def send(raw: bytes) -> None:
            written = int(device.write(MINIFREAK_COLLAGE_OUT, raw, timeout=1000))
            if written != len(raw):
                raise CollageError(
                    f"short MiniFreak USB write: {written} of {len(raw)} bytes"
                )
            receive()

        def poll() -> None:
            send(bytes((0x12, 0, 0, 0, flow_out)))

        self.usb_util.claim_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        try:
            for _ in range(12):
                poll()
            send(_subscription_request(self.codec))
            for _ in range(12):
                poll()
            for frame in _resource_store_frames(
                self.codec,
                content=content,
                name=name,
                message_id=1,
                chunk_size=chunk_size,
            ):
                send(frame)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and not acknowledged:
                poll()
        finally:
            self.usb_util.release_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        return acknowledged

    def _remove_saved_preset(
        self, slot: int, *, timeout: float, location: int = 3
    ) -> bool:
        """Remove one saved preset resource; used for exact empty-slot restore."""
        if not 1 <= slot <= 512:
            raise ValueError("MiniFreak preset slot must be 1..512")
        device = self._find()
        decoder = CollageStreamDecoder()
        flow_out = 0x80
        acknowledged = False
        remove_result: int | None = None

        def receive(timeout_ms: int = 1000) -> None:
            nonlocal flow_out, acknowledged, remove_result
            try:
                packet = bytes(
                    device.read(MINIFREAK_COLLAGE_IN, 1024, timeout=timeout_ms)
                )
            except self.usb_core.USBTimeoutError:
                return
            for frame in decoder.feed("bulk-in", packet):
                if frame.kind == "flow":
                    flow_out = 0xC0 if frame.channel & 0x40 else 0x80
                    continue
                message = self.codec.decode(frame)
                if (
                    message is not None
                    and int(message.message_id) == 1
                    and self.codec.operation(message)
                    == "control.resource.response.remove"
                ):
                    remove_result = int(message.control.resource.response.result)
                    acknowledged = remove_result == 0

        def send(raw: bytes) -> None:
            written = int(device.write(MINIFREAK_COLLAGE_OUT, raw, timeout=1000))
            if written != len(raw):
                raise CollageError(
                    f"short MiniFreak USB write: {written} of {len(raw)} bytes"
                )
            receive()

        def poll() -> None:
            send(bytes((0x12, 0, 0, 0, flow_out)))

        self.usb_util.claim_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        try:
            for _ in range(12):
                poll()
            send(_subscription_request(self.codec))
            for _ in range(12):
                poll()
            send(
                _resource_remove_frame(
                    self.codec,
                    name=(slot - 1).to_bytes(2, "little"),
                    location=location,
                )
            )
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline and remove_result is None:
                poll()
        finally:
            self.usb_util.release_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        if remove_result not in (None, 0):
            raise CollageError(
                f"MiniFreak resource remove failed with result {remove_result}"
            )
        return acknowledged

    def _read_resource(
        self,
        *,
        name: bytes,
        location: int,
        location_name: str,
        chunk_size: int = 211,
        timeout: float,
    ) -> RetrievedResource:
        device = self._find()
        decoder = CollageStreamDecoder()
        flow_out = 0x80
        chunks: dict[int, bytes] = {}
        total_size = 0
        expected_id = 1

        def receive(timeout_ms: int = 1000) -> list[CollageFrame]:
            nonlocal flow_out, total_size
            try:
                packet = bytes(
                    device.read(MINIFREAK_COLLAGE_IN, 1024, timeout=timeout_ms)
                )
            except self.usb_core.USBTimeoutError:
                return []
            frames = decoder.feed("bulk-in", packet)
            for frame in frames:
                if frame.kind == "flow":
                    flow_out = 0xC0 if frame.channel & 0x40 else 0x80
                    continue
                message = self.codec.decode(frame)
                if (
                    message is not None
                    and int(message.message_id) == expected_id
                    and self.codec.operation(message)
                    == "control.resource.response.retrieve"
                ):
                    response = message.control.resource.response.retrieve
                    chunks[int(response.offset)] = bytes(response.content)
                    total_size = max(total_size, int(response.total_size))
            return frames

        def send(raw: bytes) -> None:
            written = int(
                device.write(MINIFREAK_COLLAGE_OUT, raw, timeout=1000)
            )
            if written != len(raw):
                raise CollageError(
                    f"short MiniFreak USB write: {written} of {len(raw)} bytes"
                )
            receive()

        def poll() -> None:
            raw = bytes((0x12, 0, 0, 0, flow_out))
            send(raw)

        self.usb_util.claim_interface(device, MINIFREAK_COLLAGE_INTERFACE)
        try:
            # The official client continuously exchanges these zero-payload
            # flow frames. A short warm-up establishes its credit state.
            for _ in range(12):
                poll()
            send(_subscription_request(self.codec))
            for _ in range(12):
                poll()
            send(
                _resource_request(
                    self.codec,
                    name=name,
                    location=location,
                    message_id=expected_id,
                    chunk_size=chunk_size,
                )
            )

            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if total_size and sum(map(len, chunks.values())) >= total_size:
                    break
                poll()
        finally:
            self.usb_util.release_interface(device, MINIFREAK_COLLAGE_INTERFACE)

        if total_size <= 0:
            raise CollageError(
                f"MiniFreak returned no {location_name.lower()} resource for {name.hex()}"
            )
        data = bytearray(total_size)
        covered = bytearray(total_size)
        for offset, content in chunks.items():
            end = min(total_size, offset + len(content))
            data[offset:end] = content[: end - offset]
            covered[offset:end] = b"\x01" * (end - offset)
        if not all(covered):
            missing = covered.count(0)
            raise CollageError(
                f"MiniFreak preset read incomplete: {missing} of {total_size} bytes missing"
            )
        return RetrievedResource(
            message_id=expected_id,
            name=name,
            location=location_name,
            data=bytes(data),
            total_size=total_size,
            complete=True,
        )
