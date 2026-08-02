#!/usr/bin/env python3
"""Correlate saved-preset parameter values with operation-41 live words."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path


def _exact_affine_relation(xs: list[int], ys: list[int]) -> dict[str, int] | None:
    pairs = sorted(set(zip(xs, ys)))
    if len({x for x, _ in pairs}) < 3 or len({y for _, y in pairs}) < 2:
        return None
    first = pairs[0]
    second = next((pair for pair in pairs[1:] if pair[0] != first[0]), None)
    if second is None:
        return None
    scale = Fraction(second[1] - first[1], second[0] - first[0])
    offset = Fraction(first[1]) - scale * first[0]
    if any(Fraction(y) != scale * x + offset for x, y in pairs):
        return None
    return {
        "scale_numerator": scale.numerator,
        "scale_denominator": scale.denominator,
        "offset_numerator": offset.numerator,
        "offset_denominator": offset.denominator,
    }


def _analyze_namespace(
    rows: list[dict[str, object]], namespace: str, live_addresses: list[str]
) -> dict[str, object]:
    fields = sorted(
        {
            field
            for row in rows
            for field in (
                row.get(namespace, {})
                if isinstance(row.get(namespace), dict)
                else {}
            )
        }
    )
    result = {}
    for field in fields:
        selected = [
            row
            for row in rows
            if isinstance(row.get(namespace), dict)
            and field in row[namespace]
        ]
        values = [int(row[namespace][field]) for row in selected]
        word_vectors = {
            address: [int(row["live_words"][address]) for row in selected]
            for address in live_addresses
        }
        exact = [
            address
            for address, vector in word_vectors.items()
            if len(set(values)) >= 2 and vector == values
        ]
        deterministic = []
        affine = {}
        for address, vector in word_vectors.items():
            mapping: dict[int, set[int]] = {}
            for saved, live in zip(values, vector):
                mapping.setdefault(saved, set()).add(live)
            if (
                len(mapping) >= 3
                and len(set(vector)) >= 2
                and all(len(outputs) == 1 for outputs in mapping.values())
            ):
                deterministic.append(address)
            relation = _exact_affine_relation(values, vector)
            if relation is not None:
                affine[address] = relation
        result[field] = {
            "preset_count": len(selected),
            "unique_saved_values": len(set(values)),
            "exact_live_addresses": exact,
            "deterministic_live_addresses": deterministic,
            "exact_affine_live_addresses": affine,
        }
    return result


def correlate_saved_live_corpus(document: dict[str, object]) -> dict[str, object]:
    rows = document.get("rows")
    if not isinstance(rows, list) or len(rows) < 2:
        raise ValueError("saved/live corpus requires at least two rows")
    first = rows[0]
    if not isinstance(first, dict):
        raise ValueError("saved/live corpus rows must be objects")
    parameters = first.get("parameters")
    live_words = first.get("live_words")
    if not isinstance(parameters, dict) or not isinstance(live_words, dict):
        raise ValueError("each row requires parameters and live_words objects")

    typed_rows = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("saved/live corpus rows must be objects")
        row_parameters = row.get("parameters")
        row_words = row.get("live_words")
        if not isinstance(row_parameters, dict) or not isinstance(row_words, dict):
            raise ValueError("each row requires parameters and live_words objects")
        typed_rows.append(row)

    addresses = list(live_words)
    canonical = _analyze_namespace(typed_rows, "parameters", addresses)
    structured = _analyze_namespace(
        typed_rows, "structured_parameters", addresses
    )

    return {
        "schema_version": "microfreak-saved-live-correlation/1",
        "preset_count": len(rows),
        "restoration_verified": not document.get("final_live_differences"),
        "parameters": canonical,
        "structured_parameters": structured,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    report = correlate_saved_live_corpus(json.loads(args.corpus.read_text()))
    if args.as_json:
        print(json.dumps(report, indent=2))
        return
    for namespace in ("parameters", "structured_parameters"):
        for parameter, evidence in report[namespace].items():
            addresses = ", ".join(evidence["exact_live_addresses"]) or "none"
            print(
                f"{namespace}:{parameter}: {evidence['unique_saved_values']} "
                f"unique values; exact live addresses: {addresses}"
            )


if __name__ == "__main__":
    main()
