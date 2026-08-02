"""Lossless MicroFreak project-bank JSON interchange.

MIDI Control Center stores a synchronized MicroFreak project as 512 plain
``.mbp`` preset objects. Exported ``.mfprojz`` projects are ZIP files with one
project directory, one bank directory, and the same numbered objects.
"""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path
from pathlib import PurePosixPath

from pydantic import BaseModel, Field, model_validator

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.schema import DeviceModel, PatchDocument


MICROFREAK_BANK_SCHEMA_VERSION = "microfreak-bank/1"
MICROFREAK_BANK_SLOT_COUNT = 512
_SLOT_FILENAME = re.compile(r"^(\d+).*\.mbp$", re.IGNORECASE)


def _slot_from_filename(filename: str) -> int:
    match = _SLOT_FILENAME.match(filename)
    if match is None:
        raise ValueError(f"cannot determine slot from {filename!r}")
    digits = match.group(1)
    # Old MCC projects sometimes concatenate the slot and a date without a
    # separator (for example slot 106 as ``10600122021...``). Slot numbers are
    # naturally one, two, or three digits, with leading zero only for 01..09.
    if len(digits) >= 3 and 100 <= int(digits[:3]) <= MICROFREAK_BANK_SLOT_COUNT:
        return int(digits[:3])
    if len(digits) >= 2 and 10 <= int(digits[:2]) <= 99:
        return int(digits[:2])
    if len(digits) >= 2 and digits[0] == "0" and 1 <= int(digits[:2]) <= 9:
        return int(digits[:2])
    return int(digits[0])


class MicroFreakBankSlot(BaseModel):
    slot: int = Field(ge=1, le=MICROFREAK_BANK_SLOT_COUNT)
    filename: str
    patch: PatchDocument

    @model_validator(mode="after")
    def validate_slot(self) -> "MicroFreakBankSlot":
        if Path(self.filename).name != self.filename:
            raise ValueError("MicroFreak bank filenames must not contain a path")
        if not self.filename.lower().endswith(".mbp"):
            raise ValueError("MicroFreak bank filenames must end in .mbp")
        if self.patch.device != DeviceModel.MICROFREAK:
            raise ValueError("MicroFreak bank slots require MicroFreak patches")
        return self


class MicroFreakBankDocument(BaseModel):
    schema_version: str = MICROFREAK_BANK_SCHEMA_VERSION
    device: DeviceModel = DeviceModel.MICROFREAK
    project_name: str | None = None
    bank_directory: str | None = None
    slots: list[MicroFreakBankSlot]

    @model_validator(mode="after")
    def validate_bank(self) -> "MicroFreakBankDocument":
        if self.schema_version != MICROFREAK_BANK_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported MicroFreak bank schema {self.schema_version!r}"
            )
        if self.device != DeviceModel.MICROFREAK:
            raise ValueError("MicroFreak bank documents require device=microfreak")
        for label, value in (
            ("project_name", self.project_name),
            ("bank_directory", self.bank_directory),
        ):
            if value is not None and (
                not value or PurePosixPath(value).name != value or value in {".", ".."}
            ):
                raise ValueError(f"MicroFreak {label} must be one path component")
        slot_numbers = [item.slot for item in self.slots]
        if len(slot_numbers) != len(set(slot_numbers)):
            raise ValueError("MicroFreak bank contains duplicate slot numbers")
        return self

    @classmethod
    def from_mcc_directory(cls, directory: str | Path) -> "MicroFreakBankDocument":
        root = Path(directory)
        slots: list[MicroFreakBankSlot] = []
        for path in root.iterdir():
            if not path.is_file() or path.suffix.lower() != ".mbp":
                continue
            slot = _slot_from_filename(path.name)
            preset = MicroFreakPreset.from_file(path)
            slots.append(
                MicroFreakBankSlot(
                    slot=slot,
                    filename=path.name,
                    patch=preset.to_document(source_slot=slot),
                )
            )
        slots.sort(key=lambda item: item.slot)
        return cls(
            project_name=root.parent.name,
            bank_directory=root.name,
            slots=slots,
        )

    @classmethod
    def from_mfprojz(cls, path: str | Path) -> "MicroFreakBankDocument":
        with zipfile.ZipFile(path) as archive:
            members = [
                info
                for info in archive.infolist()
                if info.filename.lower().endswith(".mbp")
                and "__MACOSX" not in PurePosixPath(info.filename).parts
            ]
            if not members:
                raise ValueError("MicroFreak project contains no .mbp presets")
            parents = {PurePosixPath(info.filename).parent for info in members}
            if len(parents) != 1:
                raise ValueError("MicroFreak project must contain one preset bank")
            parent = parents.pop()
            if len(parent.parts) != 2:
                raise ValueError(
                    "MicroFreak project presets must be project/bank/file.mbp"
                )
            slots: list[MicroFreakBankSlot] = []
            for info in members:
                filename = PurePosixPath(info.filename).name
                slot = _slot_from_filename(filename)
                preset = MicroFreakPreset.from_bytes(archive.read(info))
                slots.append(
                    MicroFreakBankSlot(
                        slot=slot,
                        filename=filename,
                        patch=preset.to_document(source_slot=slot),
                    )
                )
        slots.sort(key=lambda item: item.slot)
        return cls(
            project_name=parent.parts[0],
            bank_directory=parent.parts[1],
            slots=slots,
        )

    def write_mcc_directory(self, directory: str | Path) -> None:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        for item in self.slots:
            preset = MicroFreakPreset.from_document(item.patch)
            (root / item.filename).write_bytes(preset.to_bytes())

    def to_mfprojz(self) -> bytes:
        project_name = self.project_name or "MicroFreak Project"
        bank_directory = self.bank_directory or f"01-{project_name}-A"
        # Revalidate defaults and caller edits before constructing archive paths.
        validated = self.model_copy(
            update={
                "project_name": project_name,
                "bank_directory": bank_directory,
            }
        )
        type(self).model_validate(validated.model_dump())

        output = BytesIO()
        with zipfile.ZipFile(output, "w") as archive:
            for directory in (
                f"{project_name}/",
                f"{project_name}/{bank_directory}/",
            ):
                info = zipfile.ZipInfo(directory)
                info.create_system = 0
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, b"")
            for item in sorted(self.slots, key=lambda slot: slot.slot):
                preset = MicroFreakPreset.from_document(item.patch)
                member = f"{project_name}/{bank_directory}/{item.filename}"
                info = zipfile.ZipInfo(member)
                info.create_system = 0
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, preset.to_bytes(), compresslevel=6)
        return output.getvalue()

    @property
    def occupied_count(self) -> int:
        return sum(
            bool(item.patch.microfreak.raw_payload_base64) for item in self.slots
        )
