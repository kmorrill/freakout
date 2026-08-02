"""Coded bulk experiments for mapping MiniFreak .mnfx parameters to USB state."""

from __future__ import annotations

import base64
import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from minifreak_patch.collage import iter_capture_frames
from minifreak_patch.minifreak_payload import MINIFREAK_HARDWARE_PRESET_SIZE
from minifreak_patch.preset import MiniFreakPreset


SENTINEL_SCHEMA = "arturia-minifreak-sentinel/1"

# Continuous parameters with stable 0..1 .mnfx representations. Discrete
# engines, modes, switches, modulation destinations, and sequencer arrays are
# deliberately assigned to later family-specific codebooks.
CONTINUOUS_CORE_PARAMETERS = (
    "Osc1_CoarseTune",
    "Osc1_FineTune",
    "Osc1_Param1",
    "Osc1_Param2",
    "Osc1_Param3",
    "Osc1_Volume",
    "Osc2_CoarseTune",
    "Osc2_FineTune",
    "Osc2_Param1",
    "Osc2_Param2",
    "Osc2_Param3",
    "Osc2_Volume",
    "Osc_BendRange",
    "Osc_Glide",
    "Osc_Mixer_NonLinearity",
    "Vcf_Cutoff",
    "Vcf_Resonance",
    "Vcf_EnvAmount",
    "Env_Attack",
    "Env_AttackCurve",
    "Env_Decay",
    "Env_DecayCurve",
    "Env_Sustain",
    "Env_Release",
    "Env_ReleaseCurve",
    "CycEnv_Rise",
    "CycEnv_RiseCurve",
    "CycEnv_Hold",
    "CycEnv_Fall",
    "CycEnv_FallCurve",
    "LFO1_Rate",
    "LFO2_Rate",
    "Gen_UnisonSpread",
    "Kbd_Chord_Strum",
)


def _sentinel_raw(index: int, shot: int) -> int:
    """Return a deterministic, unique, non-extreme positive s16 code."""
    if shot == 0:
        return 4096 + ((index * 379 + 123) % 24576)
    if shot == 1:
        return 4096 + ((index * 997 + 7919) % 24576)
    raise ValueError("the first sentinel codebook contains exactly two shots")


def generate_sentinel_experiment(
    base_path: str | Path,
    output_dir: str | Path,
    *,
    parameters: Iterable[str] = CONTINUOUS_CORE_PARAMETERS,
    limit: int | None = None,
) -> Path:
    """Create two coded .mnfx presets and a machine-readable manifest."""
    base_path = Path(base_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = MiniFreakPreset.from_file(base_path)
    selected = list(parameters)
    if limit is not None:
        selected = selected[:limit]
    if not selected:
        raise ValueError("at least one sentinel parameter is required")
    missing = [name for name in selected if name not in base.params]
    if missing:
        raise ValueError("base preset lacks parameters: " + ", ".join(missing))

    entries: list[dict[str, Any]] = []
    variants = [copy.deepcopy(base), copy.deepcopy(base)]
    for shot, variant in enumerate(variants):
        variant.name = f"Sntl{shot + 1:02d}"
        variant.pack = "Sentinel"

    for index, name in enumerate(selected):
        baseline = float(base.params[name])
        codes: list[dict[str, float | int]] = []
        baseline_raw = round(baseline * 32767.0)
        for shot, variant in enumerate(variants):
            raw = _sentinel_raw(index, shot)
            if raw == baseline_raw:
                raw += 1
            value = raw / 32767.0
            variant.set_param(name, value)
            codes.append({"value": value, "raw_s16": raw})
        entries.append(
            {
                "index": index,
                "name": name,
                "baseline": baseline,
                "codes": codes,
            }
        )

    shots: list[dict[str, str]] = []
    for shot, variant in enumerate(variants):
        label = chr(ord("A") + shot)
        filename = f"sentinel-{label.lower()}.mnfx"
        variant.write_zip(output_dir / filename)
        shots.append({"label": label, "preset": filename})

    manifest = {
        "schema_version": SENTINEL_SCHEMA,
        "family": "continuous-core",
        "base_file": base_path.name,
        "base_sha256": hashlib.sha256(base_path.read_bytes()).hexdigest(),
        "shots": shots,
        "parameters": entries,
        "instructions": {
            "order": ["baseline", "A", "baseline", "B", "baseline"],
            "restore_requirement": "final hardware payload must equal baseline exactly",
        },
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def hardware_payload_from_json(path: str | Path) -> bytes:
    document = json.loads(Path(path).read_text())
    try:
        encoded = document["minifreak"]["hardware"]["raw_payload_base64"]
    except (KeyError, TypeError) as exc:
        raise ValueError("MiniFreak lossless hardware JSON is required") from exc
    payload = base64.b64decode(encoded, validate=True)
    if len(payload) != MINIFREAK_HARDWARE_PRESET_SIZE:
        raise ValueError("MiniFreak hardware payload must be 3,328 bytes")
    return payload


def decode_session_delta(payload: bytes) -> tuple[int, int] | None:
    """Decode the observed frame-0x13 parameter delta payload."""
    if len(payload) < 12 or payload[:5] != b"\x00\x00\x03\x01\x10":
        return None
    position = 5
    identifier = 0
    shift = 0
    while position < len(payload):
        byte = payload[position]
        position += 1
        identifier |= (byte & 0x7F) << shift
        if byte < 0x80:
            break
        shift += 7
        if shift > 28:
            return None
    if payload[position : position + 3] != b"\x10\x00\x00":
        return None
    position += 3
    if len(payload) != position + 3 or payload[-1] != 0x38:
        return None
    value = int.from_bytes(payload[position : position + 2], "little", signed=True)
    return identifier, value


def session_values_from_capture(path: str | Path) -> dict[int, list[int]]:
    values: dict[int, list[int]] = {}
    for frame in iter_capture_frames(path):
        if frame.kind != "session" or frame.direction != "bulk-out":
            continue
        decoded = decode_session_delta(frame.payload)
        if decoded is None:
            continue
        identifier, value = decoded
        values.setdefault(identifier, []).append(value)
    return values


def analyze_sentinel_experiment(
    manifest_path: str | Path,
    baseline_json: str | Path,
    shot_a_json: str | Path,
    shot_b_json: str | Path,
    *,
    capture_a: str | Path | None = None,
    capture_b: str | Path | None = None,
    tolerance: int = 2,
) -> dict[str, Any]:
    """Correlate sentinel code pairs with buffer offsets and session IDs."""
    manifest = json.loads(Path(manifest_path).read_text())
    if manifest.get("schema_version") != SENTINEL_SCHEMA:
        raise ValueError("unsupported sentinel manifest")
    baseline = hardware_payload_from_json(baseline_json)
    shots = [
        hardware_payload_from_json(shot_a_json),
        hardware_payload_from_json(shot_b_json),
    ]
    session_shots = [
        session_values_from_capture(capture_a) if capture_a else {},
        session_values_from_capture(capture_b) if capture_b else {},
    ]

    changed_bytes = [
        [index for index, value in enumerate(payload) if value != baseline[index]]
        for payload in shots
    ]
    results: list[dict[str, Any]] = []
    for parameter in manifest["parameters"]:
        expected = [int(code["raw_s16"]) for code in parameter["codes"]]
        offsets: list[int] = []
        for offset in range(0, len(baseline) - 1, 2):
            observed = [
                int.from_bytes(payload[offset : offset + 2], "little", signed=True)
                for payload in shots
            ]
            if all(abs(a - b) <= tolerance for a, b in zip(observed, expected)):
                offsets.append(offset)

        session_ids: list[int] = []
        if capture_a and capture_b:
            for identifier in set(session_shots[0]) & set(session_shots[1]):
                if any(
                    abs(value - expected[0]) <= tolerance
                    for value in session_shots[0][identifier]
                ) and any(
                    abs(value - expected[1]) <= tolerance
                    for value in session_shots[1][identifier]
                ):
                    session_ids.append(identifier)
        results.append(
            {
                "name": parameter["name"],
                "expected_raw_s16": expected,
                "buffer_offset_candidates": offsets,
                "session_parameter_id_candidates": sorted(session_ids),
                "status": (
                    "unique"
                    if len(offsets) == 1 and (not capture_a or len(session_ids) == 1)
                    else "ambiguous"
                ),
            }
        )

    return {
        "schema_version": SENTINEL_SCHEMA,
        "family": manifest["family"],
        "baseline_sha256": hashlib.sha256(baseline).hexdigest(),
        "shot_sha256": [hashlib.sha256(payload).hexdigest() for payload in shots],
        "changed_byte_counts": [len(items) for items in changed_bytes],
        "session_delta_counts": [
            sum(len(values) for values in shot.values()) for shot in session_shots
        ],
        "results": results,
    }


def collect_named_preset_corpus(
    transport: Any,
    mnfx_dir: str | Path,
    output_dir: str | Path,
    *,
    scan_slots: int = 512,
    max_matches: int = 64,
) -> Path:
    """Pair uniquely named .mnfx exports with matching connected-device slots."""
    mnfx_dir = Path(mnfx_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    by_name: dict[str, list[Path]] = {}
    for path in mnfx_dir.glob("*.mnfx"):
        try:
            preset = MiniFreakPreset.from_file(path)
        except Exception:
            continue
        by_name.setdefault(preset.name, []).append(path.resolve())
    unique = {name: paths[0] for name, paths in by_name.items() if len(paths) == 1}
    entries: list[dict[str, Any]] = []
    for slot in range(1, min(scan_slots, 512) + 1):
        metadata = transport.read_preset_metadata(slot)
        name = metadata.data[8:22].split(b"\0", 1)[0].decode("utf-8", "replace")
        source = unique.get(name)
        if source is None:
            continue
        resource = transport.read_saved_preset(slot)
        payload_name = resource.data[8:22].split(b"\0", 1)[0].decode(
            "utf-8", "replace"
        )
        if payload_name != name:
            continue
        payload_file = f"slot-{slot:03d}.bin"
        (output_dir / payload_file).write_bytes(resource.data)
        entries.append(
            {
                "device_slot": slot,
                "name": name,
                "mnfx_path": str(source),
                "payload_file": payload_file,
                "payload_sha256": hashlib.sha256(resource.data).hexdigest(),
            }
        )
        if len(entries) >= max_matches:
            break
    if not entries:
        raise ValueError("no uniquely named .mnfx exports match connected slots")
    manifest = {
        "schema_version": SENTINEL_SCHEMA,
        "family": "natural-preset-corpus",
        "mnfx_directory": str(mnfx_dir.resolve()),
        "entries": entries,
    }
    manifest_path = output_dir / "corpus.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest_path


def _encoded_value(value: float, encoding: str) -> int | None:
    if encoding == "unit_s16":
        raw = round(value * 32767.0)
        return raw if -32768 <= raw <= 32767 else None
    if encoding == "normalized_bipolar_s16":
        raw = round((value * 2.0 - 1.0) * 32767.0)
        return raw if -32768 <= raw <= 32767 else None
    if encoding == "normalized_u16":
        raw = round(value * 65535.0)
        return raw if 0 <= raw <= 65535 else None
    raise ValueError(f"unknown corpus encoding {encoding}")


def analyze_named_preset_corpus(
    manifest_path: str | Path,
    *,
    parameters: Iterable[str] = CONTINUOUS_CORE_PARAMETERS,
    tolerance: int = 2,
    top: int = 5,
) -> dict[str, Any]:
    """Score .mnfx-to-buffer offset candidates across many natural presets."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != SENTINEL_SCHEMA:
        raise ValueError("unsupported corpus manifest")
    root = manifest_path.parent
    samples: list[tuple[MiniFreakPreset, bytes, dict[str, Any]]] = []
    for entry in manifest["entries"]:
        preset = MiniFreakPreset.from_file(entry["mnfx_path"])
        payload = (root / entry["payload_file"]).read_bytes()
        if len(payload) != MINIFREAK_HARDWARE_PRESET_SIZE:
            raise ValueError(f"invalid corpus payload: {entry['payload_file']}")
        samples.append((preset, payload, entry))

    encodings = ("unit_s16", "normalized_bipolar_s16", "normalized_u16")
    results: list[dict[str, Any]] = []
    for name in parameters:
        candidates: list[dict[str, Any]] = []
        for encoding in encodings:
            usable: list[tuple[int, bytes]] = []
            distinct: set[int] = set()
            for preset, payload, _entry in samples:
                if name not in preset.params:
                    continue
                expected = _encoded_value(float(preset.params[name]), encoding)
                if expected is None:
                    continue
                usable.append((expected, payload))
                distinct.add(expected)
            if len(usable) < 4 or len(distinct) < 4:
                continue
            for offset in range(0, MINIFREAK_HARDWARE_PRESET_SIZE - 1, 2):
                matches = 0
                absolute_error = 0
                for expected, payload in usable:
                    signed = encoding != "normalized_u16"
                    observed = int.from_bytes(
                        payload[offset : offset + 2], "little", signed=signed
                    )
                    error = abs(observed - expected)
                    absolute_error += error
                    if error <= tolerance:
                        matches += 1
                if matches:
                    candidates.append(
                        {
                            "offset": offset,
                            "encoding": encoding,
                            "matches": matches,
                            "samples": len(usable),
                            "match_ratio": matches / len(usable),
                            "mean_absolute_error": absolute_error / len(usable),
                        }
                    )
        candidates.sort(
            key=lambda item: (
                -item["match_ratio"],
                -item["matches"],
                item["mean_absolute_error"],
                item["offset"],
            )
        )
        best = candidates[:top]
        results.append(
            {
                "name": name,
                "candidates": best,
                "status": (
                    "unique"
                    if best
                    and best[0]["match_ratio"] >= 0.9
                    and (
                        len(best) == 1
                        or best[1]["match_ratio"] < best[0]["match_ratio"]
                    )
                    else "unresolved"
                ),
            }
        )
    return {
        "schema_version": SENTINEL_SCHEMA,
        "family": "natural-preset-corpus",
        "sample_count": len(samples),
        "results": results,
    }


def analyze_named_preset_corpus_exact(
    manifest_path: str | Path,
) -> dict[str, Any]:
    """Hash exact corpus signatures to map every common .mnfx parameter."""
    manifest_path = Path(manifest_path)
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema_version") != SENTINEL_SCHEMA:
        raise ValueError("unsupported corpus manifest")
    root = manifest_path.parent
    samples: list[tuple[MiniFreakPreset, bytes]] = []
    for entry in manifest["entries"]:
        preset = MiniFreakPreset.from_file(entry["mnfx_path"])
        payload = (root / entry["payload_file"]).read_bytes()
        if len(payload) != MINIFREAK_HARDWARE_PRESET_SIZE:
            raise ValueError(f"invalid corpus payload: {entry['payload_file']}")
        samples.append((preset, payload))
    if not samples:
        raise ValueError("corpus is empty")

    common = set(samples[0][0].params)
    for preset, _payload in samples[1:]:
        common &= set(preset.params)

    signed_signatures: dict[tuple[int, ...], list[int]] = {}
    unsigned_signatures: dict[tuple[int, ...], list[int]] = {}
    for offset in range(0, MINIFREAK_HARDWARE_PRESET_SIZE - 1, 2):
        signed = tuple(
            int.from_bytes(payload[offset : offset + 2], "little", signed=True)
            for _preset, payload in samples
        )
        unsigned = tuple(
            int.from_bytes(payload[offset : offset + 2], "little", signed=False)
            for _preset, payload in samples
        )
        signed_signatures.setdefault(signed, []).append(offset)
        unsigned_signatures.setdefault(unsigned, []).append(offset)

    results: list[dict[str, Any]] = []
    for name in sorted(common):
        values = [float(preset.params[name]) for preset, _payload in samples]
        candidates: list[dict[str, Any]] = []
        for encoding in ("unit_s16", "normalized_bipolar_s16", "normalized_u16"):
            expected = [_encoded_value(value, encoding) for value in values]
            if any(value is None for value in expected):
                continue
            signature = tuple(int(value) for value in expected if value is not None)
            if len(set(signature)) < 4:
                continue
            index = (
                unsigned_signatures
                if encoding == "normalized_u16"
                else signed_signatures
            )
            for offset in index.get(signature, []):
                candidates.append({"offset": offset, "encoding": encoding})
        results.append(
            {
                "name": name,
                "distinct_values": len(set(values)),
                "candidates": candidates,
                "status": "unique" if len(candidates) == 1 else "unresolved",
            }
        )
    unique = [result for result in results if result["status"] == "unique"]
    return {
        "schema_version": SENTINEL_SCHEMA,
        "family": "natural-preset-corpus-exact-all",
        "sample_count": len(samples),
        "common_parameter_count": len(common),
        "unique_mapping_count": len(unique),
        "results": results,
    }
