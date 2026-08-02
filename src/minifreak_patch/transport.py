"""Discovery and guarded device transport adapters.

The initial backend delegates MicroFreak USB SysEx transport to the installed
``elektroid-cli`` executable. This keeps the GPL implementation out of this
MIT library while providing a proven interoperability path with explicit
backup and readback.
"""

from __future__ import annotations

import re
import hashlib
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from minifreak_patch.microfreak import MICROFREAK_PRESET_PAYLOAD_SIZE, MicroFreakPreset
from minifreak_patch.schema import DeviceModel
from minifreak_patch.wavetable import MicroFreakWavetable


class TransportError(RuntimeError):
    pass


class WriteDisabledError(TransportError):
    pass


@dataclass
class DeviceEndpoint:
    transport_id: int
    input_name: str
    output_name: str
    device: DeviceModel
    firmware: str | None = None
    connector: str | None = None
    filesystems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "transport_id": self.transport_id,
            "input_name": self.input_name,
            "output_name": self.output_name,
            "device": self.device.value,
            "firmware": self.firmware,
            "connector": self.connector,
            "filesystems": self.filesystems,
        }


@dataclass
class DeviceItem:
    slot: int
    name: str
    size: int | None = None
    category: str | None = None


@dataclass(frozen=True)
class WavetableWriteReport:
    slot: int
    backup_path: str
    before_sha256: str
    readback_sha256: str
    restored_sha256: str
    write_verified: bool
    restore_verified: bool


@dataclass(frozen=True)
class PresetWriteReport:
    slot: int
    backup_path: str
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool


@dataclass(frozen=True)
class WavetableUploadReport:
    slot: int
    backup_path: str
    before_empty: bool
    before_sha256: str
    target_sha256: str
    readback_sha256: str
    exact_readback: bool


RunCommand = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=True,
        capture_output=True,
        text=True,
    )


class ElektroidTransport:
    def __init__(
        self,
        executable: str = "elektroid-cli",
        runner: RunCommand | None = None,
    ) -> None:
        self.executable = executable
        self.runner = runner or _default_runner

    @property
    def available(self) -> bool:
        return self.runner is not _default_runner or shutil.which(self.executable) is not None

    def _run(self, *args: str) -> subprocess.CompletedProcess[str]:
        if not self.available:
            raise TransportError(
                "elektroid-cli is not installed; install Elektroid for USB transport"
            )
        try:
            return self.runner((self.executable, *args))
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or str(exc)).strip()
            raise TransportError(detail) from exc

    def discover(self) -> list[DeviceEndpoint]:
        listing = self._run("ld").stdout
        candidates = self._parse_candidates(listing)
        return [self._inspect(*candidate) for candidate in candidates]

    def resolve(self, transport_id: int) -> DeviceEndpoint:
        """Resolve one endpoint without probing every other connected device."""
        listing = self._run("ld").stdout
        for candidate in self._parse_candidates(listing):
            if candidate[0] == transport_id:
                return self._inspect(*candidate)
        raise TransportError(f"Freak transport {transport_id} was not found")

    @staticmethod
    def _parse_candidates(listing: str) -> list[tuple[int, str, str]]:
        candidates: list[tuple[int, str, str]] = []
        for line in listing.splitlines():
            match = re.match(r"^(\d+): id: (.*?); name: (.*)$", line.strip())
            if not match:
                continue
            transport_id = int(match.group(1))
            identity = match.group(2)
            if " :: " in identity:
                input_name, output_name = identity.split(" :: ", 1)
            else:
                input_name = output_name = match.group(3)
            if input_name != output_name:
                continue
            lowered = input_name.lower()
            if "microfreak" not in lowered and "minifreak" not in lowered:
                continue
            candidates.append((transport_id, input_name, output_name))
        return candidates

    def _inspect(
        self, transport_id: int, input_name: str, output_name: str
    ) -> DeviceEndpoint:
        info = self._run("info", str(transport_id)).stdout
        fields: dict[str, str] = {}
        for line in info.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                fields[key.strip()] = value.strip()
        reported_name = fields.get("Device name", input_name).lower()
        connector = fields.get("Connector name")
        if "microfreak" in reported_name or connector == "microfreak":
            device = DeviceModel.MICROFREAK
        elif "minifreak" in input_name.lower():
            device = DeviceModel.MINIFREAK
        else:
            raise TransportError(f"transport {transport_id} is not a Freak device")
        filesystems = [
            item.strip()
            for item in fields.get("Filesystems", "").split(",")
            if item.strip()
        ]
        return DeviceEndpoint(
            transport_id=transport_id,
            input_name=input_name,
            output_name=output_name,
            device=device,
            firmware=fields.get("Device version"),
            connector=connector,
            filesystems=filesystems,
        )

    def list_presets(self, endpoint: DeviceEndpoint) -> list[DeviceItem]:
        self._require_microfreak(endpoint)
        output = self._run(
            "microfreak:preset:ls", f"{endpoint.transport_id}:/"
        ).stdout
        items: list[DeviceItem] = []
        pattern = re.compile(
            r"^F\s+(\d+)\s+(.+?)\s+\[\s*category=(.*?)\s*\]$"
        )
        for line in output.splitlines():
            match = pattern.match(line.strip())
            if match:
                items.append(
                    DeviceItem(
                        slot=int(match.group(1)),
                        name=match.group(2).strip(),
                        category=match.group(3).strip(),
                    )
                )
        return items

    def read_preset(self, endpoint: DeviceEndpoint, slot: int) -> MicroFreakPreset:
        self._require_microfreak(endpoint)
        if not 1 <= slot <= 512:
            raise ValueError("MicroFreak preset slot must be 1..512")
        with tempfile.TemporaryDirectory(prefix="freak-patch-") as temp:
            self._run(
                "microfreak:ppreset:dl",
                f"{endpoint.transport_id}:/{slot}",
                temp,
            )
            files = list(Path(temp).glob("*.mfp"))
            if len(files) != 1:
                raise TransportError("preset download did not produce one .mfp file")
            return MicroFreakPreset.from_file(files[0])

    def list_wavetables(self, endpoint: DeviceEndpoint) -> list[DeviceItem]:
        self._require_microfreak(endpoint)
        output = self._run(
            "microfreak:wavetable:ls", f"{endpoint.transport_id}:/"
        ).stdout
        items: list[DeviceItem] = []
        pattern = re.compile(r"^F\s+(.+?)\s+(\d+)\s*(.*)$")
        for line in output.splitlines():
            match = pattern.match(line.strip())
            if not match:
                continue
            size_text, slot_text, name = match.groups()
            size = 0 if size_text == "0B" else 16_384 if size_text == "16KiB" else None
            items.append(DeviceItem(slot=int(slot_text), name=name.strip(), size=size))
        return items

    def read_wavetable(
        self, endpoint: DeviceEndpoint, slot: int
    ) -> MicroFreakWavetable:
        self._require_microfreak(endpoint)
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        with tempfile.TemporaryDirectory(prefix="freak-table-") as temp:
            self._run(
                "microfreak:pwavetable:dl",
                f"{endpoint.transport_id}:/{slot}",
                temp,
            )
            files = list(Path(temp).glob("*.mfw"))
            if len(files) != 1:
                raise TransportError("wavetable download did not produce one .mfw file")
            return MicroFreakWavetable.from_mfw(files[0].read_bytes())

    def _upload_bytes(
        self,
        endpoint: DeviceEndpoint,
        slot: int,
        data: bytes,
        *,
        filesystem: str,
        suffix: str,
    ) -> None:
        with tempfile.TemporaryDirectory(prefix="freak-upload-") as temp:
            target = Path(temp) / f"target{suffix}"
            target.write_bytes(data)
            self._run(
                f"microfreak:{filesystem}:ul",
                str(target),
                f"{endpoint.transport_id}:/{slot}",
            )

    def write_preset(
        self,
        endpoint: DeviceEndpoint,
        slot: int,
        preset: MicroFreakPreset,
        backup_path: str | Path,
    ) -> PresetWriteReport:
        """Write one lossless MicroFreak preset with guarded restoration."""
        self._require_microfreak(endpoint)
        if not 1 <= slot <= 512:
            raise ValueError("MicroFreak preset slot must be 1..512")
        before = self.read_preset(endpoint, slot)
        if self.read_preset(endpoint, slot) != before:
            raise TransportError("MicroFreak preset changed during preflight")
        if len(before.payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise TransportError(
                f"MicroFreak preset slot {slot} is an empty Init slot; "
                "writing is refused because its empty state cannot be restored by upload"
            )
        if len(preset.payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise ValueError("an uploadable MicroFreak preset requires a full payload")
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = before.to_bytes()
        target_bytes = preset.to_bytes()
        backup.write_bytes(before_bytes)

        def restore() -> bool:
            self._upload_bytes(
                endpoint,
                slot,
                before_bytes,
                filesystem="ppreset",
                suffix=".mfp",
            )
            return self.read_preset(endpoint, slot) == before

        try:
            self._upload_bytes(
                endpoint,
                slot,
                target_bytes,
                filesystem="ppreset",
                suffix=".mfp",
            )
            readback = self.read_preset(endpoint, slot)
        except Exception as exc:
            if not restore():
                raise TransportError(
                    f"MicroFreak preset write and restoration failed; backup: {backup}"
                ) from exc
            raise TransportError(
                f"MicroFreak preset write failed; restoration verified; backup: {backup}"
            ) from exc
        if readback != preset:
            if not restore():
                raise TransportError(
                    f"MicroFreak preset readback and restoration failed; backup: {backup}"
                )
            raise TransportError(
                f"MicroFreak preset readback differed; restoration verified; backup: {backup}"
            )
        return PresetWriteReport(
            slot=slot,
            backup_path=str(backup),
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            target_sha256=hashlib.sha256(target_bytes).hexdigest(),
            readback_sha256=hashlib.sha256(readback.to_bytes()).hexdigest(),
            exact_readback=True,
        )

    def verify_wavetable_write_transport(
        self,
        endpoint: DeviceEndpoint,
        slot: int,
        backup_path: str | Path,
    ) -> WavetableWriteReport:
        """Write the freshly read table back, verify it, and restore it again.

        This is a same-content transport probe, not a general upload API. It
        always creates an explicit backup and performs a final restore/readback.
        """
        self._require_microfreak(endpoint)
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        before = self.read_wavetable(endpoint, slot)
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        backup.write_bytes(before.to_mfw())
        before_hash = hashlib.sha256(before.pcm16le).hexdigest()

        readback_hash = ""
        restored_hash = ""
        write_verified = False
        restore_verified = False
        write_error: Exception | None = None
        try:
            self._run(
                "microfreak:pwavetable:ul",
                str(backup),
                f"{endpoint.transport_id}:/{slot}",
            )
            readback = self.read_wavetable(endpoint, slot)
            readback_hash = hashlib.sha256(readback.pcm16le).hexdigest()
            write_verified = (
                readback.name == before.name and readback.pcm16le == before.pcm16le
            )
            if not write_verified:
                write_error = TransportError(
                    "same-content wavetable write did not match its readback"
                )
        except Exception as exc:
            write_error = exc
        finally:
            # Restore even after an upload timeout or mismatched readback.
            self._run(
                "microfreak:pwavetable:ul",
                str(backup),
                f"{endpoint.transport_id}:/{slot}",
            )
            restored = self.read_wavetable(endpoint, slot)
            restored_hash = hashlib.sha256(restored.pcm16le).hexdigest()
            restore_verified = (
                restored.name == before.name and restored.pcm16le == before.pcm16le
            )
        if not restore_verified:
            raise TransportError(
                f"MicroFreak wavetable restore could not be verified; backup: {backup}"
            )
        if write_error is not None:
            raise TransportError(
                f"wavetable transport probe failed but restoration verified: {write_error}"
            ) from write_error
        return WavetableWriteReport(
            slot=slot,
            backup_path=str(backup),
            before_sha256=before_hash,
            readback_sha256=readback_hash,
            restored_sha256=restored_hash,
            write_verified=write_verified,
            restore_verified=restore_verified,
        )

    def write_wavetable(
        self,
        endpoint: DeviceEndpoint,
        slot: int,
        table: MicroFreakWavetable,
        backup_path: str | Path,
    ) -> WavetableUploadReport:
        """Upload an arbitrary table with exact readback and rollback."""
        self._require_microfreak(endpoint)
        if not 1 <= slot <= 16:
            raise ValueError("MicroFreak wavetable slot must be 1..16")
        listing = {item.slot: item for item in self.list_wavetables(endpoint)}
        if slot not in listing:
            raise TransportError(f"MicroFreak wavetable slot {slot} was not listed")
        before_empty = listing[slot].size == 0
        before = None if before_empty else self.read_wavetable(endpoint, slot)
        if before is not None and self.read_wavetable(endpoint, slot) != before:
            raise TransportError("MicroFreak wavetable changed during preflight")
        backup = Path(backup_path)
        backup.parent.mkdir(parents=True, exist_ok=True)
        before_bytes = b"" if before is None else before.to_mfw()
        target_bytes = table.to_mfw()
        backup.write_bytes(before_bytes)

        def restore() -> bool:
            if before is None:
                self._run(
                    "microfreak:wavetable:rm",
                    f"{endpoint.transport_id}:/{slot}",
                )
                state = {item.slot: item for item in self.list_wavetables(endpoint)}
                return slot in state and state[slot].size == 0
            self._upload_bytes(
                endpoint,
                slot,
                before_bytes,
                filesystem="pwavetable",
                suffix=".mfw",
            )
            return self.read_wavetable(endpoint, slot) == before

        try:
            self._upload_bytes(
                endpoint,
                slot,
                target_bytes,
                filesystem="pwavetable",
                suffix=".mfw",
            )
            readback = self.read_wavetable(endpoint, slot)
        except Exception as exc:
            if not restore():
                raise TransportError(
                    f"MicroFreak wavetable upload and restoration failed; backup: {backup}"
                ) from exc
            raise TransportError(
                f"MicroFreak wavetable upload failed; restoration verified; backup: {backup}"
            ) from exc
        if readback != table:
            if not restore():
                raise TransportError(
                    f"MicroFreak wavetable readback and restoration failed; backup: {backup}"
                )
            raise TransportError(
                f"MicroFreak wavetable readback differed; restoration verified; backup: {backup}"
            )
        return WavetableUploadReport(
            slot=slot,
            backup_path=str(backup),
            before_empty=before_empty,
            before_sha256=hashlib.sha256(before_bytes).hexdigest(),
            target_sha256=hashlib.sha256(target_bytes).hexdigest(),
            readback_sha256=hashlib.sha256(readback.to_mfw()).hexdigest(),
            exact_readback=True,
        )

    @staticmethod
    def _require_microfreak(endpoint: DeviceEndpoint) -> None:
        if endpoint.device != DeviceModel.MICROFREAK:
            raise TransportError(
                "direct MiniFreak preset transport is still under research"
            )
