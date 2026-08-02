"""Lossless MicroFreak wavetable-bank JSON and `.mfwbz` containers."""

from __future__ import annotations

import re
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import BaseModel, Field, model_validator

from minifreak_patch.schema import DeviceModel
from minifreak_patch.wavetable import MicroFreakWavetable


MICROFREAK_WAVETABLE_BANK_SCHEMA_VERSION = "microfreak-wavetable-bank/1"
MICROFREAK_WAVETABLE_SLOT_COUNT = 16
_WAVETABLE_SLOT_FILENAME = re.compile(r"^(\d{1,2}).*\.mfw$", re.IGNORECASE)


def _slot_from_filename(filename: str) -> int:
    match = _WAVETABLE_SLOT_FILENAME.match(filename)
    if match is None:
        raise ValueError(f"cannot determine wavetable slot from {filename!r}")
    return int(match.group(1))


class MicroFreakWavetableBankSlot(BaseModel):
    slot: int = Field(ge=1, le=MICROFREAK_WAVETABLE_SLOT_COUNT)
    filename: str
    wavetable: dict[str, Any]

    @model_validator(mode="after")
    def validate_slot(self) -> "MicroFreakWavetableBankSlot":
        if Path(self.filename).name != self.filename:
            raise ValueError("MicroFreak wavetable filenames must not contain a path")
        if not self.filename.lower().endswith(".mfw"):
            raise ValueError("MicroFreak wavetable filenames must end in .mfw")
        MicroFreakWavetable.from_document(self.wavetable)
        return self


class MicroFreakWavetableBankDocument(BaseModel):
    schema_version: str = MICROFREAK_WAVETABLE_BANK_SCHEMA_VERSION
    device: DeviceModel = DeviceModel.MICROFREAK
    project_name: str | None = None
    bank_directory: str | None = None
    slots: list[MicroFreakWavetableBankSlot]

    @model_validator(mode="after")
    def validate_bank(self) -> "MicroFreakWavetableBankDocument":
        if self.schema_version != MICROFREAK_WAVETABLE_BANK_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported wavetable-bank schema {self.schema_version!r}"
            )
        if self.device != DeviceModel.MICROFREAK:
            raise ValueError("MicroFreak wavetable banks require device=microfreak")
        for label, value in (
            ("project_name", self.project_name),
            ("bank_directory", self.bank_directory),
        ):
            if value is not None and (
                not value or PurePosixPath(value).name != value or value in {".", ".."}
            ):
                raise ValueError(f"MicroFreak {label} must be one path component")
        numbers = [item.slot for item in self.slots]
        if len(numbers) != len(set(numbers)):
            raise ValueError("MicroFreak wavetable bank contains duplicate slots")
        return self

    @classmethod
    def from_mcc_directory(
        cls, directory: str | Path
    ) -> "MicroFreakWavetableBankDocument":
        root = Path(directory)
        slots = []
        for path in root.iterdir():
            if not path.is_file() or path.suffix.lower() != ".mfw":
                continue
            slot = _slot_from_filename(path.name)
            table = MicroFreakWavetable.from_mfw(path.read_bytes())
            slots.append(
                MicroFreakWavetableBankSlot(
                    slot=slot,
                    filename=path.name,
                    wavetable=table.to_document().to_dict(),
                )
            )
        slots.sort(key=lambda item: item.slot)
        return cls(
            project_name=root.parent.name,
            bank_directory=root.name,
            slots=slots,
        )

    @classmethod
    def from_mfwbz(cls, path: str | Path) -> "MicroFreakWavetableBankDocument":
        with zipfile.ZipFile(path) as archive:
            members = [
                info
                for info in archive.infolist()
                if info.filename.lower().endswith(".mfw")
                and "__MACOSX" not in PurePosixPath(info.filename).parts
            ]
            if not members:
                raise ValueError("MicroFreak wavetable bank contains no .mfw tables")
            parents = {PurePosixPath(info.filename).parent for info in members}
            if len(parents) != 1:
                raise ValueError("MicroFreak wavetable archive must contain one bank")
            parent = parents.pop()
            if len(parent.parts) != 2:
                raise ValueError(
                    "MicroFreak wavetable members must be project/bank/file.mfw"
                )
            slots = []
            for info in members:
                filename = PurePosixPath(info.filename).name
                table = MicroFreakWavetable.from_mfw(archive.read(info))
                slots.append(
                    MicroFreakWavetableBankSlot(
                        slot=_slot_from_filename(filename),
                        filename=filename,
                        wavetable=table.to_document().to_dict(),
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
            table = MicroFreakWavetable.from_document(item.wavetable)
            (root / item.filename).write_bytes(table.to_mfw())

    def to_mfwbz(self) -> bytes:
        project_name = self.project_name or "MicroFreak Wavetables"
        bank_directory = self.bank_directory or f"01-{project_name}-A"
        validated = self.model_copy(
            update={"project_name": project_name, "bank_directory": bank_directory}
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
            for item in sorted(self.slots, key=lambda value: value.slot):
                table = MicroFreakWavetable.from_document(item.wavetable)
                member = f"{project_name}/{bank_directory}/{item.filename}"
                info = zipfile.ZipInfo(member)
                info.create_system = 0
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, table.to_mfw(), compresslevel=6)
        return output.getvalue()
