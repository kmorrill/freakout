"""Analyze one batched MicroFreak CC save against published layout candidates.

The archived public reader documented two different locations for seven
controls. This module does not choose one by firmware-number guesswork. It
scores both layouts against an actual before/after payload and retains every
unexplained byte for later clean-room analysis.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from minifreak_patch.microfreak import MICROFREAK_PRESET_PAYLOAD_SIZE
from minifreak_patch.microfreak_payload import (
    MICROFREAK_PARAMETER_SPECS,
    MicroFreakParameterSpec,
)


def _offset(row: int, column: int) -> int:
    return row * 32 + column


def _continuous(
    key: str,
    msb: tuple[int, int],
    lsb: tuple[int, int],
    flag: tuple[int, int],
    mask: int,
) -> MicroFreakParameterSpec:
    return MicroFreakParameterSpec(
        key=key,
        value_type="normalized_float",
        msb_offset=_offset(*msb),
        lsb_offset=_offset(*lsb),
        flag_offset=_offset(*flag),
        flag_mask=mask,
    )


# Clean-room transcription of row/column facts from the archived public
# MicroFreak Reader. These are evidence candidates, not editable mappings.
SHIFTED_LAYOUT_SPECS: dict[str, dict[str, MicroFreakParameterSpec]] = {
    "legacy_fw1": {
        spec.key: spec
        for spec in (
            _continuous("arp.rate_sync", (9, 27), (9, 26), (9, 24), 0x02),
            _continuous("arp.rate_free", (10, 5), (10, 4), (10, 0), 0x08),
            _continuous("lfo.rate_sync", (12, 31), (12, 30), (12, 24), 0x20),
            _continuous("lfo.rate_free", (13, 10), (13, 9), (13, 8), 0x01),
            _continuous("envelope.attack", (14, 29), (14, 28), (14, 24), 0x08),
            _continuous("envelope.decay", (15, 10), (15, 9), (15, 8), 0x01),
            _continuous("envelope.sustain", (15, 23), (15, 22), (15, 16), 0x20),
        )
    },
    "fw2_plus_candidate": {
        spec.key: spec
        for spec in (
            _continuous("arp.rate_free", (10, 27), (10, 26), (10, 24), 0x02),
            _continuous("arp.rate_sync", (10, 17), (10, 15), (10, 8), 0x40),
            _continuous("lfo.rate_free", (13, 31), (13, 30), (13, 24), 0x20),
            _continuous("lfo.rate_sync", (13, 21), (13, 20), (13, 16), 0x08),
            _continuous("envelope.attack", (15, 19), (15, 18), (15, 16), 0x02),
            _continuous("envelope.decay", (15, 31), (15, 30), (15, 24), 0x20),
            _continuous("envelope.sustain", (16, 13), (16, 12), (16, 8), 0x08),
        )
    },
}


@dataclass(frozen=True)
class ProbeFieldResult:
    key: str
    expected_cc: int | None
    before_raw: int
    after_raw: int
    changed: bool
    byte_offsets: tuple[int, ...]
    changed_offsets: tuple[int, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "expected_cc": self.expected_cc,
            "before_raw": self.before_raw,
            "after_raw": self.after_raw,
            "changed": self.changed,
            "byte_offsets": list(self.byte_offsets),
            "changed_offsets": list(self.changed_offsets),
        }


def _require_payload(payload: bytes) -> None:
    if len(payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
        raise ValueError(
            f"MicroFreak sentinel analysis requires "
            f"{MICROFREAK_PRESET_PAYLOAD_SIZE} payload bytes"
        )


def _spec_offsets(spec: MicroFreakParameterSpec) -> tuple[int, ...]:
    values = [spec.lsb_offset]
    if spec.msb_offset is not None:
        values.append(spec.msb_offset)
    if spec.flag_offset is not None:
        values.append(spec.flag_offset)
    return tuple(sorted(set(values)))


def _raw_value(payload: bytes, spec: MicroFreakParameterSpec) -> int:
    if spec.encoding in {
        "unsigned_7bit",
        "firmware_tagged_metadata_scaled_integer",
    }:
        # The saved-CC sentinel probe deliberately observes the historical
        # packed byte at this location. Canonical firmware-5 oscillator edits
        # use the self-describing VCO.Type field instead.
        return payload[spec.lsb_offset] & 0x7F
    assert spec.msb_offset is not None
    assert spec.flag_offset is not None and spec.flag_mask is not None
    shift = (spec.flag_mask & -spec.flag_mask).bit_length() - 1
    low_bit = (payload[spec.flag_offset] & spec.flag_mask) >> shift
    return (
        ((payload[spec.msb_offset] & 0x7F) << 8)
        | (low_bit << 7)
        | (payload[spec.lsb_offset] & 0x7F)
    )


def _field_result(
    before: bytes,
    after: bytes,
    spec: MicroFreakParameterSpec,
    expected_values: Mapping[str, int],
) -> ProbeFieldResult:
    offsets = _spec_offsets(spec)
    before_raw = _raw_value(before, spec)
    after_raw = _raw_value(after, spec)
    return ProbeFieldResult(
        key=spec.key,
        expected_cc=expected_values.get(spec.key),
        before_raw=before_raw,
        after_raw=after_raw,
        changed=before_raw != after_raw,
        byte_offsets=offsets,
        changed_offsets=tuple(i for i in offsets if before[i] != after[i]),
    )


def analyze_microfreak_cc_sentinel(
    before: bytes,
    after: bytes,
    expected_values: Mapping[str, int],
    normalization_control: bytes | None = None,
) -> dict[str, object]:
    """Score layouts against a saved edit, optionally subtracting save churn.

    ``normalization_control`` is the result of saving the same baseline without
    sending sentinels. When supplied, field scoring and unexplained bytes use
    control-vs-sentinel rather than factory-baseline-vs-sentinel.
    """
    _require_payload(before)
    _require_payload(after)
    if normalization_control is not None:
        _require_payload(normalization_control)
    if before == after:
        raise ValueError("sentinel before and after payloads are identical")

    comparison_before = normalization_control or before
    changed_offsets = {
        index
        for index, pair in enumerate(zip(comparison_before, after))
        if pair[0] != pair[1]
    }
    normalization_offsets = (
        {
            index
            for index, pair in enumerate(zip(before, normalization_control))
            if pair[0] != pair[1]
        }
        if normalization_control is not None
        else set()
    )
    stable = {
        key: _field_result(comparison_before, after, spec, expected_values)
        for key, spec in MICROFREAK_PARAMETER_SPECS.items()
        if key in expected_values
    }
    layouts: dict[str, dict[str, object]] = {}
    stable_offsets = {
        offset for result in stable.values() for offset in result.byte_offsets
    }
    for name, specs in SHIFTED_LAYOUT_SPECS.items():
        fields = {
            key: _field_result(comparison_before, after, spec, expected_values)
            for key, spec in specs.items()
        }
        candidate_offsets = {
            offset for result in fields.values() for offset in result.byte_offsets
        }
        layouts[name] = {
            "changed_field_score": sum(result.changed for result in fields.values()),
            "field_count": len(fields),
            "fields": {key: result.to_dict() for key, result in fields.items()},
            "unexplained_changed_offsets": sorted(
                changed_offsets - stable_offsets - candidate_offsets
            ),
        }

    scores = {
        name: int(report["changed_field_score"])
        for name, report in layouts.items()
    }
    best_score = max(scores.values())
    winners = [name for name, score in scores.items() if score == best_score]
    resolved = winners[0] if len(winners) == 1 else None
    return {
        "schema_version": "microfreak-cc-sentinel-analysis/1",
        "comparison_basis": (
            "normalization_control_vs_sentinel"
            if normalization_control is not None
            else "baseline_vs_sentinel"
        ),
        "normalization_changed_bytes": len(normalization_offsets),
        "normalization_changed_offsets": sorted(normalization_offsets),
        "total_changed_bytes": len(changed_offsets),
        "changed_offsets": sorted(changed_offsets),
        "stable_fields_changed": sum(result.changed for result in stable.values()),
        "stable_field_count": len(stable),
        "stable_fields": {key: result.to_dict() for key, result in stable.items()},
        "layout_scores": scores,
        "resolved_layout": resolved,
        "resolution_status": "unique_high_score" if resolved else "inconclusive",
        "layouts": layouts,
    }
