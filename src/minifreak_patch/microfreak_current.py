"""Evidence-qualified MicroFreak current-parameter overlay.

Operation 41 exposes the complete 384-word active parameter object, but not
the active sequence/header regions.  This module overlays every
hardware-correlated current structured field onto a caller-supplied saved
preset while retaining the saved regions that have no current-buffer read.
The result is useful and lossless for the regions it claims, without being
misrepresented as a complete unsaved-current dump.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable, Protocol

from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_midi import infer_oscillator_engine_index
from minifreak_patch.microfreak_structured import (
    parse_structured_fields,
    set_structured_raw_u16,
    set_structured_value,
)


class LiveStructuredFieldLike(Protocol):
    name: str
    raw_u16: int
    aliases_match: bool


@dataclass(frozen=True)
class MicroFreakCurrentOverlayReport:
    preset: MicroFreakPreset
    base_slot: int
    current_parameter_fields_applied: tuple[str, ...]
    live_fields_missing_from_base: tuple[str, ...]
    oscillator_engine_index: int | None
    oscillator_engine_applied: bool
    exact_payload_match_to_base: bool


def overlay_current_parameter_object(
    base_preset: MicroFreakPreset,
    *,
    base_slot: int,
    live_fields: Iterable[LiveStructuredFieldLike],
    oscillator_runtime_raw_u16: int,
) -> MicroFreakCurrentOverlayReport:
    """Overlay verified current words onto one complete saved-slot payload.

    ``base_slot`` is provenance, not a device-selected-slot assertion. The
    caller is responsible for choosing the saved slot whose header and
    sequence should supply the regions absent from operation 41.
    """

    if not 1 <= base_slot <= 512:
        raise ValueError("MicroFreak current-overlay base slot must be 1..512")
    if not base_preset.payload:
        raise ValueError("MicroFreak current-overlay base slot must be occupied")
    if not 0 <= oscillator_runtime_raw_u16 <= 0xFFFF:
        raise ValueError("MicroFreak oscillator runtime word must be 0..65535")

    payload = base_preset.payload
    base_fields = parse_structured_fields(payload)
    applied: list[str] = []
    missing: list[str] = []
    seen: set[str] = set()
    for field in live_fields:
        if field.name in seen:
            raise ValueError(f"duplicate current structured field {field.name!r}")
        seen.add(field.name)
        if not field.aliases_match:
            raise ValueError(
                f"current structured field {field.name!r} has mismatched live aliases"
            )
        if field.name not in base_fields:
            missing.append(field.name)
            continue
        payload = set_structured_raw_u16(payload, field.name, field.raw_u16)
        applied.append(field.name)

    engine_index = infer_oscillator_engine_index(oscillator_runtime_raw_u16)
    engine_applied = engine_index is not None and "VCO.Type" in base_fields
    if engine_applied:
        payload = set_structured_value(payload, "VCO.Type", engine_index)
        applied.append("VCO.Type")

    current = replace(base_preset, payload=payload)
    return MicroFreakCurrentOverlayReport(
        preset=current,
        base_slot=base_slot,
        current_parameter_fields_applied=tuple(applied),
        live_fields_missing_from_base=tuple(sorted(missing)),
        oscillator_engine_index=engine_index,
        oscillator_engine_applied=engine_applied,
        exact_payload_match_to_base=payload == base_preset.payload,
    )
