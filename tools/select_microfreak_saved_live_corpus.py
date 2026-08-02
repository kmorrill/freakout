#!/usr/bin/env python3
"""Choose a compact saved-preset corpus with broad structured-value diversity."""

from __future__ import annotations

import argparse
import base64
import json
from collections import defaultdict
from pathlib import Path

from minifreak_patch.microfreak_structured import parse_structured_fields


def _decode_rows(document: dict[str, object]) -> list[dict[str, object]]:
    rows = document.get("rows")
    if not isinstance(rows, list):
        raise ValueError("oscillator corpus requires a rows list")
    decoded = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("oscillator corpus rows must be objects")
        payload_text = row.get("payload_base64")
        if not isinstance(payload_text, str):
            raise ValueError("each row requires payload_base64")
        fields = parse_structured_fields(base64.b64decode(payload_text))
        decoded.append(
            {
                "slot": int(row["slot"]),
                "name": str(row.get("name", "")),
                "values": {name: field.raw_u16 for name, field in fields.items()},
                "metadata": {name: field.metadata for name, field in fields.items()},
            }
        )
    return decoded


def select_diverse_rows(
    rows: list[dict[str, object]],
    count: int,
    *,
    include_slots: tuple[int, ...] = (),
    value_cap: int = 8,
) -> list[dict[str, object]]:
    if not 1 <= count <= len(rows):
        raise ValueError("selection count must be within the available rows")
    by_slot = {int(row["slot"]): row for row in rows}
    missing = [slot for slot in include_slots if slot not in by_slot]
    if missing:
        raise ValueError(f"included slots are absent from the corpus: {missing}")

    universe: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for row in rows:
        values = row["values"]
        metadata = row["metadata"]
        assert isinstance(values, dict) and isinstance(metadata, dict)
        for field, value in values.items():
            universe[field].add((int(metadata[field]), int(value)))

    selected = []
    selected_slots = set()
    observed: dict[str, set[tuple[int, int]]] = defaultdict(set)

    def add(row: dict[str, object]) -> None:
        slot = int(row["slot"])
        if slot in selected_slots:
            return
        selected.append(row)
        selected_slots.add(slot)
        values = row["values"]
        metadata = row["metadata"]
        assert isinstance(values, dict) and isinstance(metadata, dict)
        for field, value in values.items():
            observed[field].add((int(metadata[field]), int(value)))

    for slot in dict.fromkeys(include_slots):
        add(by_slot[slot])

    while len(selected) < count:
        best = None
        best_score = -1.0
        for row in rows:
            if int(row["slot"]) in selected_slots:
                continue
            values = row["values"]
            metadata = row["metadata"]
            assert isinstance(values, dict) and isinstance(metadata, dict)
            score = 0.0
            for field, value in values.items():
                token = (int(metadata[field]), int(value))
                target = min(value_cap, len(universe[field]))
                if token not in observed[field] and len(observed[field]) < target:
                    # Rare/low-cardinality fields matter as much as continuous
                    # fields; normalize each incremental value by its target.
                    score += 1.0 / max(1, target)
            # Stable tie-break favors lower slots for reproducibility.
            if score > best_score or (
                score == best_score
                and best is not None
                and int(row["slot"]) < int(best["slot"])
            ):
                best = row
                best_score = score
        assert best is not None
        add(best)
    return selected


def build_report(
    document: dict[str, object],
    count: int,
    *,
    include_slots: tuple[int, ...] = (),
    value_cap: int = 8,
) -> dict[str, object]:
    rows = _decode_rows(document)
    selected = select_diverse_rows(
        rows, count, include_slots=include_slots, value_cap=value_cap
    )
    all_values: dict[str, set[tuple[int, int]]] = defaultdict(set)
    selected_values: dict[str, set[tuple[int, int]]] = defaultdict(set)
    for row, destination in (
        *((row, all_values) for row in rows),
        *((row, selected_values) for row in selected),
    ):
        values = row["values"]
        metadata = row["metadata"]
        assert isinstance(values, dict) and isinstance(metadata, dict)
        for field, value in values.items():
            destination[field].add((int(metadata[field]), int(value)))
    return {
        "schema_version": "microfreak-saved-live-selection/1",
        "source_preset_count": len(rows),
        "selected_count": len(selected),
        "value_cap": value_cap,
        "included_slots": list(include_slots),
        "selected_slots": [int(row["slot"]) for row in selected],
        "selected_presets": [
            {"slot": int(row["slot"]), "name": str(row["name"])}
            for row in selected
        ],
        "field_diversity": {
            field: {
                "selected_unique_metadata_value_pairs": len(selected_values[field]),
                "corpus_unique_metadata_value_pairs": len(all_values[field]),
                "target_unique_pairs": min(value_cap, len(all_values[field])),
            }
            for field in sorted(all_values)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--count", type=int, default=24)
    parser.add_argument("--include-slot", type=int, action="append", default=[])
    parser.add_argument("--value-cap", type=int, default=8)
    args = parser.parse_args()
    report = build_report(
        json.loads(args.corpus.read_text()),
        args.count,
        include_slots=tuple(args.include_slot),
        value_cap=args.value_cap,
    )
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(" ".join(str(slot) for slot in report["selected_slots"]))


if __name__ == "__main__":
    main()
