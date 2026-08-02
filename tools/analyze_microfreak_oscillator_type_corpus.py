#!/usr/bin/env python3
"""Verify saved VCO.Type against the MicroFreak live oscillator word."""

from __future__ import annotations

import argparse
import base64
from collections import Counter, defaultdict
import json
from pathlib import Path

from minifreak_patch.microfreak import MICROFREAK_PRESET_PAYLOAD_SIZE
from minifreak_patch.microfreak_midi import (
    MICROFREAK_OSCILLATOR_ENGINE_NAMES,
    infer_oscillator_engine_index,
)
from minifreak_patch.microfreak_structured import (
    interpret_structured_field,
    parse_structured_fields,
)


def analyze_oscillator_type_corpus(document: dict[str, object]) -> dict[str, object]:
    rows = document.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("oscillator-type corpus requires at least one row")

    engines: dict[int, list[dict[str, object]]] = defaultdict(list)
    mismatches = []
    off_grid = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("oscillator-type corpus rows must be objects")
        try:
            payload = base64.b64decode(str(row["payload_base64"]), validate=True)
            live_word = int(row["live_word_0000"])
            slot = int(row["slot"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("row requires slot, live_word_0000, and payload_base64") from exc
        if len(payload) != MICROFREAK_PRESET_PAYLOAD_SIZE:
            raise ValueError(
                f"slot {slot} payload must be {MICROFREAK_PRESET_PAYLOAD_SIZE} bytes"
            )
        field = parse_structured_fields(payload).get("VCO.Type")
        if field is None:
            raise ValueError(f"slot {slot} has no firmware-tagged VCO.Type field")
        live_engine = infer_oscillator_engine_index(live_word)
        if live_engine is None:
            off_grid.append({"slot": slot, "live_word_0000": live_word})
            continue
        saved_engine = int(interpret_structured_field(field).value)
        if saved_engine != live_engine:
            mismatches.append(
                {
                    "slot": slot,
                    "saved_engine_index": saved_engine,
                    "live_engine_index": live_engine,
                }
            )
        engines[live_engine].append(
            {
                "slot": slot,
                "name": str(row.get("name", "")),
                "live_word": live_word,
                "metadata": field.metadata,
                "raw_u16": field.raw_u16,
                "legacy": int(row.get("saved_legacy_osc_type", -1)),
            }
        )

    engine_report = {}
    for engine, entries in sorted(engines.items()):
        engine_report[str(engine)] = {
            "name": MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(engine),
            "preset_count": len(entries),
            "live_word_0000": sorted({int(item["live_word"]) for item in entries}),
            "vco_type_metadata": dict(
                sorted(Counter(int(item["metadata"]) for item in entries).items())
            ),
            "vco_type_raw_u16": dict(
                sorted(Counter(int(item["raw_u16"]) for item in entries).items())
            ),
            "legacy_byte_values": dict(
                sorted(Counter(int(item["legacy"]) for item in entries).items())
            ),
            "examples": [
                {"slot": item["slot"], "name": item["name"]}
                for item in entries[:3]
            ],
        }

    return {
        "schema_version": "microfreak-oscillator-type-analysis/1",
        "preset_count": len(rows),
        "restoration_verified": not document.get("final_live_differences"),
        "engine_count": len(engines),
        "engine_indices": sorted(engines),
        "all_live_words_on_normalized_grid": not off_grid,
        "all_saved_vco_types_match_live_engine": not mismatches and not off_grid,
        "off_grid_live_words": off_grid,
        "mismatches": mismatches,
        "engines": engine_report,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = analyze_oscillator_type_corpus(json.loads(args.corpus.read_text()))
    if args.as_json:
        print(json.dumps(report, indent=2))
        return
    print(
        f"{report['preset_count']} presets; {report['engine_count']} engines; "
        f"saved/live match={report['all_saved_vco_types_match_live_engine']}; "
        f"restored={report['restoration_verified']}"
    )
    for engine, evidence in report["engines"].items():
        print(
            f"engine {engine}: {evidence['preset_count']} presets; "
            f"live={evidence['live_word_0000']}; "
            f"metadata={evidence['vco_type_metadata']}"
        )


if __name__ == "__main__":
    main()
