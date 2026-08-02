#!/usr/bin/env python3
"""Compare Arturia's installed MiniFreak V UI with a lossless MNFX preset.

This is a static, read-only audit.  It expands the simple ``<for>`` loops used
by Arturia's screen XML, resolves local string constants, inventories every
``param=`` reference, and separates interactive controls from display-only
parameter consumers.  The JSON report is intended to be checked into research
artifacts or diffed after an Arturia software update.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from minifreak_patch.minifreak_payload import VERIFIED_PARAMETERS  # noqa: E402
from minifreak_patch.preset import MiniFreakPreset  # noqa: E402


DEFAULT_RESOURCES = Path("/Library/Arturia/MiniFreak V/resources")
PATCH_SCREEN_FILES = {"screens/synth.xml", "screens/sequencer.xml"}
INTERACTIVE_TAGS = {
    "adsrenvelope",
    "button",
    "buttoncontrolled",
    "circularbutton",
    "combobox",
    "imageslider",
    "lfo-shaper",
    "minifreak_modulationroll",
    "mnf_dest_chooser",
    "pianoroll",
    "softbar",
    "softknob",
    "syncedtimeruler",
    "textslider",
    "velocityroll",
}
_SUBSTITUTION = re.compile(r"\$\{([^${}]*)\}")


def _parse_xml(path: Path) -> ET.Element:
    """Parse Arturia XML, tolerating its application-specific tag prefixes."""

    text = path.read_text(errors="replace")
    try:
        return ET.fromstring(text)
    except ET.ParseError as error:
        if "unbound prefix" not in str(error):
            raise
        text = re.sub(r"(<\/?)([A-Za-z_]\w*):", r"\1\2_", text)
        text = re.sub(r"(\s)([A-Za-z_]\w*):([A-Za-z_]\w*\s*=)", r"\1\2_\3", text)
        return ET.fromstring(text)


def _discover_ui_files(resources: Path) -> tuple[list[Path], list[str]]:
    pending = [resources / "MiniFreak V_gui.xml"]
    discovered: set[Path] = set()
    missing: set[str] = set()
    while pending:
        path = pending.pop()
        if path in discovered:
            continue
        discovered.add(path)
        root = _parse_xml(path)
        for element in root.iter():
            if element.tag not in {"xmlfile", "xmlfile_component"}:
                continue
            filename = element.attrib.get("filename")
            if not filename or "${" in filename:
                continue
            included = resources / filename
            if included.exists():
                pending.append(included)
            else:
                missing.add(filename)
    return sorted(discovered), sorted(missing)


def _safe_number(expression: str, names: dict[str, str]) -> int:
    """Evaluate the integer arithmetic used by Arturia's XML loop bounds."""

    for name, value in sorted(names.items(), key=lambda item: -len(item[0])):
        expression = re.sub(rf"\b{re.escape(name)}\b", value, expression)
    node = ast.parse(expression, mode="eval")

    def visit(current: ast.AST) -> int:
        if isinstance(current, ast.Expression):
            return visit(current.body)
        if isinstance(current, ast.Constant) and isinstance(current.value, (int, float)):
            return int(current.value)
        if isinstance(current, ast.UnaryOp) and isinstance(
            current.op, (ast.UAdd, ast.USub)
        ):
            value = visit(current.operand)
            return value if isinstance(current.op, ast.UAdd) else -value
        if isinstance(current, ast.BinOp) and isinstance(
            current.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv)
        ):
            left, right = visit(current.left), visit(current.right)
            if isinstance(current.op, ast.Add):
                return left + right
            if isinstance(current.op, ast.Sub):
                return left - right
            if isinstance(current.op, ast.Mult):
                return left * right
            return left // right
        raise ValueError(f"unsupported expression: {expression}")

    return visit(node)


def _resolve(value: str, env: dict[str, str], constants: dict[str, str]) -> str:
    merged = {**constants, **env}
    previous = None
    while value != previous:
        previous = value
        value = _SUBSTITUTION.sub(lambda match: merged.get(match.group(1), match.group(0)), value)
        if value in merged:
            value = merged[value]
    return value


def _screen_references(
    path: Path,
    resources: Path,
    shared_constants: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    root = _parse_xml(path)
    relative_source = str(path.relative_to(resources))
    constants = dict(shared_constants or {})
    constants.update({
        element.attrib["name"]: element.attrib["value"]
        for element in root.findall("./constants/*")
        if "name" in element.attrib and "value" in element.attrib
    })
    references: list[dict[str, Any]] = []

    def walk(element: ET.Element, env: dict[str, str]) -> None:
        if element.tag == "for":
            variable = element.attrib.get("src", "")
            try:
                start = _safe_number(_resolve(element.attrib["from"], env, constants), constants)
                stop = _safe_number(_resolve(element.attrib["to"], env, constants), constants)
            except (KeyError, SyntaxError, ValueError, ZeroDivisionError):
                # Retain unresolved template references once; they remain visible
                # in the report instead of silently disappearing.
                for child in element:
                    walk(child, env)
                return
            if abs(stop - start) > 512:
                raise ValueError(f"refusing oversized XML loop {start}..{stop} in {path}")
            for index in range(start, stop + 1):
                nested = dict(env)
                nested[variable] = str(index)
                for child in element:
                    walk(child, nested)
            return

        if "param" in element.attrib:
            parameter = _resolve(element.attrib["param"], env, constants)
            references.append(
                {
                    "parameter": parameter,
                    "source": relative_source,
                    "patch_surface": relative_source in PATCH_SCREEN_FILES,
                    "element": element.tag,
                    "title": _resolve(element.attrib.get("title", ""), env, constants),
                    "interactive": (
                        element.tag in INTERACTIVE_TAGS
                        and element.attrib.get("intercept-mouse", "1") != "0"
                    ),
                }
            )
        for child in element:
            walk(child, env)

    walk(root, {})
    return references


def _parameter_definitions(resources: Path) -> dict[str, list[dict[str, Any]]]:
    """Load the main definition and its directly declared parameter includes."""

    main = resources / "MiniFreak V.xml"
    root = _parse_xml(main)
    definitions: dict[str, list[dict[str, Any]]] = defaultdict(list)

    def add_params(
        parent: ET.Element, source: Path, section: str, prefix: str = ""
    ) -> None:
        for element in parent:
            if element.tag == "block":
                block_name = element.attrib.get("name", "")
                try:
                    count = int(element.attrib.get("nbblock", "1"))
                except ValueError:
                    count = 1
                for index in range(1, count + 1):
                    add_params(
                        element, source, section, f"{prefix}{block_name}{index}_"
                    )
                continue
            if element.tag != "param":
                add_params(element, source, section, prefix)
                continue
            name = element.attrib.get("name")
            if name:
                definitions[f"{prefix}{name}"].append(
                    {
                        "source": str(source),
                        "section": section,
                        "display_name": element.attrib.get("display_name"),
                        "description": element.attrib.get("text_desc"),
                        "transmitted_to_processor": element.attrib.get(
                            "transmittedtoprocessor", "1"
                        )
                        != "0",
                        "not_set_modified": element.attrib.get("notsetmodified") == "1",
                        "saved_in_preferences": element.attrib.get("savedinpreffile") == "1",
                        "attributes": dict(element.attrib),
                        "inline_items": [dict(item.attrib) for item in element.findall("./item")],
                        "item_list_references": [
                            item.attrib.get("name")
                            for item in element.findall("./item_list")
                            if item.attrib.get("name")
                        ],
                    }
                )

    for section in ("vst", "internal"):
        container = root.find(section)
        if container is None:
            continue
        # Direct params only; included file params are added with inherited section.
        add_params(container, main, section)
        for include in container.findall("./xmlfile_parameters"):
            filename = include.attrib.get("filename")
            if not filename:
                continue
            include_path = resources / filename
            if include_path.exists():
                add_params(_parse_xml(include_path), include_path, section)
    return definitions


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_fingerprint(
    resources: Path,
    mnfx: Path,
    ui_files: list[Path],
    definitions: dict[str, list[dict[str, Any]]],
) -> str:
    """Hash every installed or repository source that drives the audit."""
    definition_files = {
        Path(item["source"])
        for entries in definitions.values()
        for item in entries
    }
    hardware_map = REPO_ROOT / "src/minifreak_patch/minifreak_payload.py"
    sources = set(ui_files) | definition_files | {mnfx, hardware_map}
    digest = hashlib.sha256()
    for path in sorted(sources, key=lambda item: str(item)):
        try:
            label = f"arturia:{path.relative_to(resources)}"
        except ValueError:
            try:
                label = f"repo:{path.relative_to(REPO_ROOT)}"
            except ValueError:
                label = f"external:{path.name}"
        digest.update(label.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def build_report(resources: Path, mnfx: Path) -> dict[str, Any]:
    preset = MiniFreakPreset.from_file(mnfx)
    mnfx_names = set(preset.params)
    hardware_names = {item.mnfx_name for item in VERIFIED_PARAMETERS.values()}
    definitions = _parameter_definitions(resources)
    ui_files, missing_ui_includes = _discover_ui_files(resources)
    source_fingerprint = _source_fingerprint(
        resources, mnfx, ui_files, definitions
    )
    gui_root = _parse_xml(resources / "MiniFreak V_gui.xml")
    shared_constants = {
        element.attrib["name"]: element.attrib["value"]
        for path in ui_files
        for element in _parse_xml(path).findall("./constants/*")
        if "name" in element.attrib and "value" in element.attrib
    }
    shared_constants.update({
        element.attrib["name"]: element.attrib["value"]
        for element in gui_root.findall("./constants/*")
        if "name" in element.attrib and "value" in element.attrib
    })
    references = [
        reference
        for path in ui_files
        for reference in _screen_references(path, resources, shared_constants)
    ]

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for reference in references:
        grouped[reference["parameter"]].append(reference)

    parameters: dict[str, dict[str, Any]] = {}
    for name in sorted(set(grouped) | mnfx_names | set(definitions)):
        refs = grouped.get(name, [])
        defs = definitions.get(name, [])
        interactive = any(ref["interactive"] for ref in refs)
        patch_surface_interactive = any(
            ref["interactive"] and ref["patch_surface"] for ref in refs
        )
        in_mnfx = name in mnfx_names
        if in_mnfx and patch_surface_interactive:
            classification = "interactive_patch"
        elif in_mnfx and refs:
            classification = "referenced_patch"
        elif in_mnfx:
            classification = "serialized_not_directly_referenced"
        elif patch_surface_interactive and any(
            item["saved_in_preferences"] for item in defs
        ):
            classification = "interactive_preference"
        elif patch_surface_interactive and defs and all(
            not item["transmitted_to_processor"] or item["not_set_modified"]
            for item in defs
        ):
            classification = "ui_runtime_helper"
        elif patch_surface_interactive:
            classification = "patch_surface_unresolved"
        elif refs:
            classification = "application_shell"
        else:
            classification = "defined_not_serialized_or_referenced"
        parameters[name] = {
            "classification": classification,
            "in_baseline_mnfx": in_mnfx,
            "hardware_mapped": name in hardware_names,
            "interactive": interactive,
            "patch_surface_interactive": patch_surface_interactive,
            "definitions": defs,
            "ui_references": refs,
        }

    class_counts = Counter(item["classification"] for item in parameters.values())
    interactive_names = {
        name for name, item in parameters.items() if item["patch_surface_interactive"]
    }
    unresolved_templates = sorted(name for name in grouped if "${" in name)
    unresolved_patch_templates = sorted(
        name
        for name in unresolved_templates
        if any(ref["patch_surface"] for ref in grouped[name])
    )
    return {
        "schema_version": "minifreak-ui-mnfx-audit/1",
        "inputs": {
            "arturia_resources": str(resources),
            "arturia_instrument_version": _parse_xml(
                resources / "MiniFreak V.xml"
            ).attrib.get("instrument_version_generated"),
            "mnfx": str(mnfx),
            "mnfx_firmware": preset.firmware_version,
            "mnfx_sha256": _sha256(mnfx),
            "hardware_map_sha256": _sha256(
                REPO_ROOT / "src/minifreak_patch/minifreak_payload.py"
            ),
            "source_fingerprint_sha256": source_fingerprint,
            "ui_files_scanned": [str(path.relative_to(resources)) for path in ui_files],
            "missing_conditional_ui_includes": missing_ui_includes,
        },
        "summary": {
            "baseline_mnfx_parameters": len(mnfx_names),
            "official_parameter_definitions": len(definitions),
            "distinct_ui_parameter_references": len(grouped),
            "distinct_patch_surface_interactive_parameters": len(interactive_names),
            "distinct_all_ui_interactive_parameters": len(
                {name for name, item in parameters.items() if item["interactive"]}
            ),
            "interactive_parameters_in_mnfx": len(interactive_names & mnfx_names),
            "interactive_parameters_not_in_mnfx": len(interactive_names - mnfx_names),
            "mnfx_parameters_with_hardware_mapping": len(mnfx_names & hardware_names),
            "unresolved_ui_templates": len(unresolved_templates),
            "unresolved_patch_surface_templates": len(unresolved_patch_templates),
            "classification_counts": dict(sorted(class_counts.items())),
        },
        "unresolved_ui_templates": unresolved_templates,
        "parameters": parameters,
    }


def audit_passes(report: dict[str, Any]) -> bool:
    summary = report["summary"]
    return (
        summary["unresolved_patch_surface_templates"] == 0
        and summary["classification_counts"].get("patch_surface_unresolved", 0)
        == 0
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resources", type=Path, default=DEFAULT_RESOURCES)
    parser.add_argument(
        "--mnfx",
        type=Path,
        default=REPO_ROOT / "presets/minifreak-default-base.mnfx",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit nonzero if any installed patch-surface control is unresolved",
    )
    args = parser.parse_args()
    report = build_report(args.resources, args.mnfx)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
    print(json.dumps(report["summary"], indent=2), file=sys.stderr)
    if args.check and not audit_passes(report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
