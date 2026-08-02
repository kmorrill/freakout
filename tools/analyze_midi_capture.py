#!/usr/bin/env python3
"""Summarize Arturia MicroFreak transactions in a passive capture log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from minifreak_patch.microfreak_capture import parse_capture_lines, summarize_capture


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("capture")
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    messages = parse_capture_lines(Path(args.capture).read_text().splitlines())
    summary = summarize_capture(messages)
    if args.as_json:
        print(json.dumps(summary, indent=2, sort_keys=True))
        return
    print(f"MicroFreak messages: {summary['microfreak_messages']}")
    print(
        "Operations: "
        + ", ".join(
            f"{key}={value}"
            for key, value in summary["operation_counts"].items()
        )
    )
    for key in (
        "global_queries",
        "preset_header_queries",
        "preset_header_replies",
        "preset_body_starts",
        "wavetable_header_starts",
        "wavetable_part_starts",
        "sample_starts",
        "continuation_requests",
        "data_start_replies",
        "data_part_replies",
        "data_final_replies",
        "complete_startup_inventory_cycles",
    ):
        print(f"{key.replace('_', ' ').title()}: {summary[key]}")
    print(
        "Observed current/edit-buffer request: "
        + ("yes" if summary["observed_current_buffer_request"] else "no")
    )


if __name__ == "__main__":
    main()
