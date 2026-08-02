"""Build collision-resistant multi-field MicroFreak sentinel presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_structured import (
    interpret_structured_field,
    parse_structured_fields,
    set_structured_raw_u16,
    set_structured_value,
)


@dataclass(frozen=True)
class StructuredSentinelEdit:
    name: str
    before_value: float | int
    target_value: float | int
    before_raw_u16: int
    target_raw_u16: int
    value_kind: str


def build_structured_sentinel_preset(
    preset: MicroFreakPreset,
    values: Mapping[str, float | int | Mapping[str, int]],
) -> tuple[MicroFreakPreset, tuple[StructuredSentinelEdit, ...]]:
    """Apply distinct interpreted or explicit-raw sentinels to one preset."""

    if not values:
        raise ValueError("structured sentinel map cannot be empty")
    payload = preset.payload
    edits: list[StructuredSentinelEdit] = []
    for name, target_spec in values.items():
        before_fields = parse_structured_fields(payload)
        try:
            before_field = before_fields[name]
        except KeyError as exc:
            raise ValueError(f"preset has no structured field {name!r}") from exc
        before = interpret_structured_field(before_field)
        if isinstance(target_spec, Mapping):
            if set(target_spec) != {"raw_u16"}:
                raise ValueError(
                    f"raw structured sentinel {name} must contain only raw_u16"
                )
            target_value = target_spec["raw_u16"]
            if isinstance(target_value, bool) or not isinstance(target_value, int):
                raise ValueError(f"raw structured sentinel {name} must be an integer")
            changed_payload = set_structured_raw_u16(payload, name, target_value)
            target_kind = "raw_u16"
        else:
            target_value = target_spec
            changed_payload = set_structured_value(payload, name, target_value)
            target_kind = interpret_structured_field(
                parse_structured_fields(changed_payload)[name]
            ).kind
        target_field = parse_structured_fields(changed_payload)[name]
        target = interpret_structured_field(target_field)
        if target_field.raw_u16 == before_field.raw_u16:
            raise ValueError(
                f"structured sentinel {name} does not change the saved raw value"
            )
        edits.append(
            StructuredSentinelEdit(
                name=name,
                before_value=before.value,
                target_value=(
                    target_field.raw_u16 if target_kind == "raw_u16" else target.value
                ),
                before_raw_u16=before_field.raw_u16,
                target_raw_u16=target_field.raw_u16,
                value_kind=target_kind,
            )
        )
        payload = changed_payload
    return (
        MicroFreakPreset(
            name=preset.name,
            category_id=preset.category_id,
            init=preset.init,
            p1=preset.p1,
            payload=payload,
            version_tag=preset.version_tag,
            characteristics_bits=preset.characteristics_bits,
        ),
        tuple(edits),
    )
