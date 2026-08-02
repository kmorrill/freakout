"""Command-line interface for minifreak-patch.

Commands:
    build   — Build a preset from a JSON recipe file
    bundle  — Bundle multiple .mnfx presets into a single bank
    show    — Display a preset summary
    dump    — Dump preset parameters as JSON
    diff    — Compare two presets
"""

from __future__ import annotations

import base64
import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import click

from minifreak_patch.collage import (
    CollageCodec,
    extract_retrieved_resources,
    patch_document_from_capture,
    patch_document_from_resource,
    summarize_capture,
)
from minifreak_patch.constants import (
    ASSIGNABLE_COLS, HARDWIRED_COLS, HARDWIRED_DEST_NAMES, MOD_DEST_NONE,
    ModSource,
    decode_mod_dest, mod_dest_description, mod_dest_label,
)
from minifreak_patch.preset import MiniFreakPreset, sanitize_default_base
from minifreak_patch.recipe import load_recipe
from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.microfreak_bank import MicroFreakBankDocument
from minifreak_patch.microfreak_wavetable_bank import (
    MicroFreakWavetableBankDocument,
)
from minifreak_patch.microfreak_midi import (
    MICROFREAK_GLOBAL_CODES,
    MICROFREAK_LIVE_WORD_SEMANTICS,
    MICROFREAK_OSCILLATOR_ENGINE_NAMES,
    MICROFREAK_STATUS_RECORD_SELECTORS,
    MicroFreakMidiTransport,
    infer_oscillator_engine_index,
)
from minifreak_patch.microfreak_live_map import (
    MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED,
    MICROFREAK_STRUCTURED_GLOBAL_COUNTERPARTS,
    MICROFREAK_STRUCTURED_LIVE_AMBIGUOUS,
    MICROFREAK_STRUCTURED_NO_LIVE_TABLE_CC_EFFECT,
    MICROFREAK_STRUCTURED_LIVE_WORDS,
)
from minifreak_patch.microfreak_global_specs import (
    MICROFREAK_GLOBAL_VALUE_SPECS,
    decode_microfreak_global,
)
from minifreak_patch.microfreak_probe import analyze_microfreak_cc_sentinel
from minifreak_patch.microfreak_payload import (
    MICROFREAK_PARAMETER_SPECS,
    decode_microfreak_parameters,
    set_microfreak_parameter,
)
from minifreak_patch.microfreak_structured import (
    STRUCTURED_ROLE_EVIDENCE,
    parse_structured_fields,
    set_structured_raw_u16,
    set_structured_value,
    structured_field_role,
)
from minifreak_patch.microfreak_structured_probe import (
    build_structured_sentinel_preset,
)
from minifreak_patch.microfreak_sequence import (
    SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES,
    analyze_sequence_payloads,
    parse_sequence_patterns,
    set_sequence_automation,
    set_sequence_automation_destination,
    set_sequence_note,
    set_sequence_note_status,
    set_sequence_velocity,
)
from minifreak_patch.live import (
    LiveControlError,
    MICROFREAK_SENTINEL_VALUES,
    controls_for,
    list_output_ports,
    send_control,
    send_control_batch,
    trigger_note,
)
from minifreak_patch.minifreak_usb import (
    MiniFreakUsbTransport,
    find_arturia_binary,
)
from minifreak_patch.minifreak_payload import (
    VERIFIED_PARAMETERS,
    update_document_parameter,
)
from minifreak_patch.schema import (
    DeviceModel,
    MICROFREAK_CHARACTERISTICS,
    MicroFreakLiveTableDocument,
    MicroFreakLiveWordData,
    PatchDocument,
    capabilities_for,
    encode_microfreak_characteristics,
)
from minifreak_patch.sentinel import (
    CONTINUOUS_CORE_PARAMETERS,
    analyze_named_preset_corpus,
    analyze_named_preset_corpus_exact,
    analyze_sentinel_experiment,
    collect_named_preset_corpus,
    generate_sentinel_experiment,
)
from minifreak_patch.transport import (
    DeviceEndpoint,
    DirectTransportDiscovery,
    ElektroidTransport,
    TransportError,
)
from minifreak_patch.wavetable import (
    MicroFreakWavetable,
    validate_minifreak_raw,
)
from minifreak_patch.zipwriter import create_zip


def _find_default_base() -> Optional[Path]:
    """Locate the default base preset relative to the package."""
    # Walk up from this file to find the repo root presets/ dir
    here = Path(__file__).resolve().parent
    for ancestor in [here, here.parent, here.parent.parent]:
        candidate = ancestor / "presets" / "minifreak-default-base.mnfx"
        if candidate.exists():
            return candidate
    return None


@click.group()
def main():
    """Freakout — JSON patch tools for Arturia MiniFreak and MicroFreak."""


# ── build ─────────────────────────────────────────────────────────────────

@main.command()
@click.argument("recipe_path", type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True,
              type=click.Path(), help="Output .mnfx file path.")
@click.option("--base", "base_path", type=click.Path(exists=True),
              default=None, help="Base preset file (default: built-in safe base).")
@click.option("--raw", is_flag=True, default=False,
              help="Output raw text instead of ZIP (for debugging).")
def build(recipe_path: str, output_path: str, base_path: Optional[str],
          raw: bool):
    """Build a preset from a JSON recipe file."""
    # Load base
    if base_path:
        base = MiniFreakPreset.from_file(base_path)
    else:
        default_base = _find_default_base()
        if default_base is None:
            click.echo("Error: no base preset found. Use --base to specify one.",
                       err=True)
            sys.exit(1)
        base = MiniFreakPreset.from_file(default_base)

    base = sanitize_default_base(base)

    # Load and build recipe
    recipe = load_recipe(recipe_path)
    preset = recipe.build(base)

    # Write output
    out = Path(output_path)
    if raw:
        out.write_text(preset.to_mnfx())
    else:
        preset.name = recipe.name
        preset.write_zip(out)

    # Summary
    click.echo(f"Built: {preset.name}")
    if preset.description:
        click.echo(f"  {preset.description}")
    if preset.preset_type or preset.subtype:
        click.echo(f"  Type: {preset.preset_type or '-'} / {preset.subtype or '-'}")
    osc1 = preset.get_osc1_engine()
    osc2 = preset.get_osc2_engine()
    if osc1:
        click.echo(f"  Osc1: {osc1.label}")
    if osc2:
        click.echo(f"  Osc2: {osc2.label}")
    for slot in (1, 2, 3):
        algo = preset.get_fx_algorithm(slot)
        enabled = preset.get_param(f"FX{slot}_Enable")
        if algo and enabled and enabled > 0.5:
            opt1 = preset.get_fx_opt1_label(slot)
            opt_str = f" ({opt1})" if opt1 else ""
            click.echo(f"  FX{slot}: {algo.label}{opt_str}")
    click.echo(f"  Params: {len(preset.params)}")
    click.echo(f"  Output: {out}")


# ── bundle ────────────────────────────────────────────────────────────────

@main.command()
@click.argument("presets", nargs=-1, required=True,
                type=click.Path(exists=True))
@click.option("-o", "--output", "output_path", required=True,
              type=click.Path(), help="Output bank .mnfx file path.")
@click.option("--pack", default="UserPresets",
              help="Pack name (folder name in the bank).")
def bundle(presets: tuple[str, ...], output_path: str, pack: str):
    """Bundle multiple .mnfx presets into a single bank."""
    entries: list[tuple[str, bytes]] = []

    for p in presets:
        try:
            preset = MiniFreakPreset.from_file(p)
        except Exception as e:
            click.echo(f"  ! skipping {p}: {e}", err=True)
            continue

        # Ensure exported format
        import time as _time
        if preset.timestamp is None:
            preset.timestamp = int(_time.time())
        if preset.firmware_version is None:
            preset.firmware_version = "4.0.2.6369"

        safe_name = preset.name.replace(" ", "_")
        path = f"MiniFreak/User/{pack}/{safe_name}"
        content = preset.to_mnfx().encode("utf-8")
        entries.append((path, content))
        click.echo(f"  + {preset.name} ({p})")

    if not entries:
        click.echo("Error: no presets could be loaded.", err=True)
        sys.exit(1)

    zip_bytes = create_zip(entries)
    Path(output_path).write_bytes(zip_bytes)

    click.echo(f"\nBundled {len(entries)} presets into: {output_path}")
    click.echo(f"Pack name: {pack}")


# ── show ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("file", type=click.Path(exists=True))
def show(file: str):
    """Display a preset summary."""
    preset = MiniFreakPreset.from_file(file)

    click.echo(f"Preset: {preset.name}")
    click.echo(f"Pack:   {preset.pack}")
    click.echo(f"Author: {preset.author}")
    click.echo(f"Type:   {preset.preset_type or '-'}")
    click.echo(f"Sub:    {preset.subtype or '-'}")
    if preset.description:
        click.echo(f"Desc:   {preset.description}")
    if preset.timestamp:
        click.echo(f"Time:   {preset.timestamp} (Unix)")
    if preset.firmware_version:
        click.echo(f"FW:     {preset.firmware_version}")
    for k, v in sorted(preset.metadata.items()):
        click.echo(f"  {k}={v}")
    click.echo(f"Params: {len(preset.params)}")

    # Sound
    click.echo("\n--- Sound ---")
    osc1 = preset.get_osc1_engine()
    osc2 = preset.get_osc2_engine()
    click.echo(f"  Osc1: {osc1.label if osc1 else '?'}")
    click.echo(f"  Osc2: {osc2.label if osc2 else '?'}")
    click.echo(f"  Osc1 Vol: {preset.get_param('Osc1_Volume'):.3f}")
    click.echo(f"  Osc2 Vol: {preset.get_param('Osc2_Volume'):.3f}")

    filt = preset.get_filter_mode()
    cutoff = preset.get_param("Vcf_Cutoff")
    reso = preset.get_param("Vcf_Resonance")
    click.echo(
        f"  Filter: {filt.label if filt else '?'}, "
        f"cutoff={cutoff:.3f}, reso={reso:.3f}"
    )
    click.echo(f"  Filter Env: {preset.get_param('Vcf_EnvAmount'):.3f}")

    # FX
    click.echo("\n--- FX ---")
    for slot in (1, 2, 3):
        algo = preset.get_fx_algorithm(slot)
        enabled = preset.get_param(f"FX{slot}_Enable")
        state = "ON" if enabled and enabled > 0.5 else "OFF"
        p1 = preset.get_param(f"FX{slot}_Param1") or 0.0
        p2 = preset.get_param(f"FX{slot}_Param2") or 0.0
        p3 = preset.get_param(f"FX{slot}_Param3") or 0.0
        click.echo(
            f"  FX{slot}: {algo.label if algo else '?'} {state} "
            f"(p1={p1:.3f}, p2={p2:.3f}, p3={p3:.3f})"
        )

    # Envelope
    click.echo("\n--- Envelope ---")
    for param in ("Attack", "Decay", "Sustain", "Release"):
        v = preset.get_param(f"Env_{param}")
        click.echo(f"  {param}: {v:.3f}" if v is not None else f"  {param}: -")

    # LFOs
    click.echo("\n--- LFOs ---")
    for lfo in (1, 2):
        wave = preset.get_lfo_waveform(lfo)
        rate = preset.get_param(f"LFO{lfo}_Rate")
        sync_en = preset.get_param(f"LFO{lfo}_SyncEn")
        sync_str = " [sync]" if sync_en and sync_en > 0.5 else ""
        click.echo(
            f"  LFO{lfo}: {wave.label if wave else '?'} "
            f"rate={rate:.3f}{sync_str}"
        )

    # Voice
    click.echo("\n--- Voice ---")
    note_mode = preset.get_note_mode()
    click.echo(f"  Note Mode: {note_mode.label if note_mode else '?'}")
    click.echo(f"  Glide: {preset.get_param('Gen_Glide'):.3f}")

    # Mod Matrix
    click.echo("\n--- Mod Matrix ---")
    _show_mod_matrix(preset)


def _show_mod_matrix(preset: MiniFreakPreset) -> None:
    """Display the mod matrix state."""
    # Show column destinations
    total_cols = HARDWIRED_COLS + ASSIGNABLE_COLS
    col_descs: list[str] = []
    for col in range(total_cols):
        if col < HARDWIRED_COLS:
            col_descs.append(HARDWIRED_DEST_NAMES[col])
        else:
            assign_idx = col - HARDWIRED_COLS
            param = (f"Mx_ColId_{assign_idx}" if assign_idx < 8
                     else "Mx_ColId_Last")
            val = preset.get_param(param)
            if val is None or abs(val - MOD_DEST_NONE) < 1e-6:
                col_descs.append("(none)")
            else:
                dest = decode_mod_dest(val)
                if dest:
                    col_descs.append(mod_dest_description(*dest))
                else:
                    col_descs.append(f"?({val:.6f})")

    # Show non-zero routings
    has_routes = False
    for source in ModSource:
        for col in range(total_cols):
            row = source.value
            if col < HARDWIRED_COLS:
                idx = row * HARDWIRED_COLS + col
                param = f"Mx_Dot_{idx}" if idx < 27 else "Mx_Dot_Last"
            else:
                assign_col = col - HARDWIRED_COLS
                idx = row * ASSIGNABLE_COLS + assign_col
                param = (f"Mx_AssignDot_{idx}" if idx < 62
                         else "Mx_AssignDot_Last")

            val = preset.get_param(param)
            if val is not None and abs(val - 0.5) > 0.001:
                pct = (val - 0.5) * 200
                sign = "+" if pct >= 0 else ""
                click.echo(
                    f"  {source.label} -> {col_descs[col]} {sign}{pct:.0f}%"
                )
                has_routes = True

    if not has_routes:
        click.echo("  (empty)")


# ── dump ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--prefix", default=None,
              help="Filter parameters by name prefix (e.g., 'Osc1_').")
def dump(file: str, prefix: Optional[str]):
    """Dump preset parameters as JSON."""
    preset = MiniFreakPreset.from_file(file)

    if prefix:
        data = {k: v for k, v in sorted(preset.params.items())
                if k.startswith(prefix)}
    else:
        data = {
            "name": preset.name,
            "pack": preset.pack,
            "author": preset.author,
            "type": preset.preset_type,
            "subtype": preset.subtype,
            "description": preset.description,
            "params": dict(sorted(preset.params.items())),
        }

    click.echo(json.dumps(data, indent=2))


# ── diff ──────────────────────────────────────────────────────────────────

@main.command()
@click.argument("file_a", type=click.Path(exists=True))
@click.argument("file_b", type=click.Path(exists=True))
@click.option("--prefix", default=None,
              help="Filter diffs by parameter prefix.")
def diff(file_a: str, file_b: str, prefix: Optional[str]):
    """Compare two presets and show differences."""
    a = MiniFreakPreset.from_file(file_a)
    b = MiniFreakPreset.from_file(file_b)

    click.echo(f"A: {a.name} ({file_a})")
    click.echo(f"B: {b.name} ({file_b})")
    click.echo()

    if a.preset_type != b.preset_type:
        click.echo(f"Type:    {a.preset_type or '-'} -> {b.preset_type or '-'}")
    if a.subtype != b.subtype:
        click.echo(f"Subtype: {a.subtype or '-'} -> {b.subtype or '-'}")

    diffs = a.diff(b)
    if prefix:
        diffs = [d for d in diffs if d.name.startswith(prefix)]

    suffix = f" (prefix: {prefix})" if prefix else ""
    click.echo(f"\n{len(diffs)} parameter differences{suffix}:")
    click.echo()

    for d in diffs:
        va = f"{d.value_a:.6f}" if d.value_a is not None else "-"
        vb = f"{d.value_b:.6f}" if d.value_b is not None else "-"
        click.echo(f"  {d.name:<30s}  {va} -> {vb}")


# ── shared JSON ───────────────────────────────────────────────────────────

@main.command("to-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
def to_json(input_path: str, output_path: str):
    """Convert a .mnfx, .mfp, or .mfpz patch to shared JSON."""
    suffix = Path(input_path).suffix.lower()
    if suffix == ".mnfx":
        document = MiniFreakPreset.from_file(input_path).to_document()
    elif suffix in {".mfp", ".mfpz", ".mbp"}:
        document = MicroFreakPreset.from_file(input_path).to_document()
    else:
        raise click.ClickException(f"unsupported patch extension: {suffix}")
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Wrote {document.device.value} JSON: {output_path}")


@main.command("from-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
def from_json(input_path: str, output_path: str):
    """Convert shared JSON back to a device patch file."""
    document = PatchDocument.model_validate_json(Path(input_path).read_text())
    if document.device == DeviceModel.MINIFREAK:
        preset = MiniFreakPreset.from_document(document)
        if Path(output_path).suffix.lower() == ".mnfx":
            preset.write_zip(output_path)
        else:
            Path(output_path).write_text(preset.to_mnfx())
    else:
        preset = MicroFreakPreset.from_document(document)
        if Path(output_path).suffix.lower() == ".mfpz":
            Path(output_path).write_bytes(preset.to_zip())
        else:
            Path(output_path).write_bytes(preset.to_bytes())
    click.echo(f"Wrote {document.device.value} patch: {output_path}")


@main.command("microfreak-bank-to-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
def microfreak_bank_to_json(input_path: str, output_path: str):
    """Convert an .mfprojz or MCC .mbp directory to lossless bank JSON."""
    source = Path(input_path)
    bank = (
        MicroFreakBankDocument.from_mcc_directory(source)
        if source.is_dir()
        else MicroFreakBankDocument.from_mfprojz(source)
    )
    Path(output_path).write_text(
        bank.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Wrote {len(bank.slots)} MicroFreak slots "
        f"({bank.occupied_count} occupied): {output_path}"
    )


@main.command("microfreak-bank-from-json")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_path", type=click.Path())
def microfreak_bank_from_json(input_path: str, output_path: str):
    """Restore bank JSON to an .mfprojz or MCC .mbp directory."""
    bank = MicroFreakBankDocument.model_validate_json(Path(input_path).read_text())
    output = Path(output_path)
    if output.suffix.lower() == ".mfprojz":
        output.write_bytes(bank.to_mfprojz())
    else:
        bank.write_mcc_directory(output)
    click.echo(f"Wrote {len(bank.slots)} MicroFreak slots: {output_path}")


@main.command("set-microfreak-characteristics")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_path", type=click.Path())
@click.argument(
    "characteristics",
    nargs=-1,
    type=click.Choice(MICROFREAK_CHARACTERISTICS, case_sensitive=False),
)
def set_microfreak_characteristics_command(
    input_path: str,
    output_path: str,
    characteristics: tuple[str, ...],
):
    """Set named MicroFreak characteristics in a patch JSON document."""
    document = PatchDocument.model_validate_json(Path(input_path).read_text())
    if document.device != DeviceModel.MICROFREAK or document.microfreak is None:
        raise click.ClickException("not a MicroFreak patch JSON document")
    canonical = [
        next(
            name
            for name in MICROFREAK_CHARACTERISTICS
            if name.lower() == supplied.lower()
        )
        for supplied in characteristics
    ]
    bits = encode_microfreak_characteristics(canonical)
    document.microfreak.archive.characteristics = canonical
    document.microfreak.archive.characteristics_bits = bits
    document = PatchDocument.model_validate(document.model_dump())
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Wrote MicroFreak characteristics {canonical!r}: {output_path}"
    )


@main.command("microfreak-wavetable-bank-to-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
def microfreak_wavetable_bank_to_json(input_path: str, output_path: str):
    """Convert an .mfwbz or MCC .mfw directory to lossless bank JSON."""
    source = Path(input_path)
    bank = (
        MicroFreakWavetableBankDocument.from_mcc_directory(source)
        if source.is_dir()
        else MicroFreakWavetableBankDocument.from_mfwbz(source)
    )
    Path(output_path).write_text(bank.model_dump_json(indent=2) + "\n")
    click.echo(f"Wrote {len(bank.slots)} MicroFreak wavetables: {output_path}")


@main.command("microfreak-wavetable-bank-from-json")
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("output_path", type=click.Path())
def microfreak_wavetable_bank_from_json(input_path: str, output_path: str):
    """Restore wavetable-bank JSON to .mfwbz or an MCC .mfw directory."""
    bank = MicroFreakWavetableBankDocument.model_validate_json(
        Path(input_path).read_text()
    )
    output = Path(output_path)
    if output.suffix.lower() == ".mfwbz":
        output.write_bytes(bank.to_mfwbz())
    else:
        bank.write_mcc_directory(output)
    click.echo(f"Wrote {len(bank.slots)} MicroFreak wavetables: {output_path}")


# ── capabilities and transport ────────────────────────────────────────────

@main.command("capabilities")
@click.argument("device", required=False,
                type=click.Choice([item.value for item in DeviceModel]))
@click.option("--json", "json_output", is_flag=True)
def capabilities_command(device: str | None, json_output: bool):
    """Show explicitly supported operations for one or both devices."""
    devices = [DeviceModel(device)] if device else list(DeviceModel)
    result = {
        item.value: {
            name: capability.model_dump(mode="json")
            for name, capability in capabilities_for(item).items()
        }
        for item in devices
    }
    if json_output:
        click.echo(json.dumps(result, indent=2))
        return
    for item in devices:
        click.echo(item.value)
        for name, capability in capabilities_for(item).items():
            click.echo(f"  {name:<28} {capability.level.value:<11} {capability.note}")


@main.command("json-schema")
def json_schema_command():
    """Print the versioned shared patch JSON Schema."""
    click.echo(json.dumps(PatchDocument.model_json_schema(), indent=2))


@main.command("devices")
@click.option("--json", "json_output", is_flag=True)
@click.option(
    "--backend",
    type=click.Choice(("direct", "elektroid")),
    default="direct",
    show_default=True,
    help="Use independent bounded discovery or Elektroid compatibility discovery.",
)
def devices_command(json_output: bool, backend: str):
    """Discover Freak patch transports without changing either device."""
    try:
        endpoints = (
            DirectTransportDiscovery().discover()
            if backend == "direct"
            else ElektroidTransport().discover()
        )
    except TransportError as exc:
        raise click.ClickException(str(exc)) from exc
    if json_output:
        click.echo(json.dumps([item.to_dict() for item in endpoints], indent=2))
        return
    if not endpoints:
        click.echo("No Freak devices found.")
    for item in endpoints:
        click.echo(
            f"{item.transport_id}: {item.device.value} "
            f"backend={item.backend} connector={item.connector or '?'} "
            f"firmware={item.firmware or 'not probed'}"
        )


@main.group("live")
def live_group():
    """Change the active sound using documented MIDI CC messages."""


@live_group.command("ports")
def live_ports():
    """List MIDI outputs. This does not contact or change a device."""
    try:
        ports = list_output_ports()
    except LiveControlError as exc:
        raise click.ClickException(str(exc)) from exc
    for port in ports:
        click.echo(port)


@live_group.command("controls")
@click.argument("device", type=click.Choice([item.value for item in DeviceModel]))
@click.option("--json", "json_output", is_flag=True)
def live_controls(device: str, json_output: bool):
    """List the documented live controls for a device."""
    entries = controls_for(DeviceModel(device))
    data = {
        name: {"cc": item.cc, "minimum": item.minimum, "maximum": item.maximum}
        for name, item in entries.items()
    }
    if json_output:
        click.echo(json.dumps(data, indent=2))
        return
    for name, item in data.items():
        click.echo(
            f"{name:<24} CC {item['cc']:>3}  "
            f"{item['minimum']}..{item['maximum']}"
        )


@live_group.command("note")
@click.argument("device", type=click.Choice([item.value for item in DeviceModel]))
@click.argument("note", type=click.IntRange(0, 127), default=60)
@click.option("--velocity", type=click.IntRange(1, 127), default=80, show_default=True)
@click.option("--duration", type=click.FloatRange(min=0), default=0.5, show_default=True)
@click.option("--channel", type=click.IntRange(1, 16), default=1, show_default=True)
@click.option("--port", default=None, help="Exact MIDI output name.")
def live_note(
    device: str,
    note: int,
    velocity: int,
    duration: float,
    channel: int,
    port: str | None,
):
    """Play one bounded test note; this does not save or edit a preset."""
    try:
        selected = trigger_note(
            DeviceModel(device),
            note,
            velocity=velocity,
            duration_seconds=duration,
            channel=channel,
            port=port,
        )
    except LiveControlError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        f"Played MIDI note {note} on channel {channel} through {selected}; "
        "note-off sent, preset unchanged"
    )


@live_group.command("set")
@click.argument("device", type=click.Choice([item.value for item in DeviceModel]))
@click.argument("parameter")
@click.argument("value", type=int)
@click.option("--channel", type=click.IntRange(1, 16), default=1, show_default=True)
@click.option("--all-channels", is_flag=True)
@click.option("--port", default=None, help="Exact MIDI output name.")
def live_set(
    device: str,
    parameter: str,
    value: int,
    channel: int,
    all_channels: bool,
    port: str | None,
):
    """Send one live value; it is not saved and cannot be read back over CC."""
    try:
        channels = list(range(1, 17)) if all_channels else [channel]
        selected = ""
        control = None
        for selected_channel in channels:
            selected, control = send_control(
                DeviceModel(device),
                parameter,
                value,
                channel=selected_channel,
                port=port,
            )
    except LiveControlError as exc:
        raise click.ClickException(str(exc)) from exc
    assert control is not None
    click.echo(
        f"Sent {device} {parameter}={value} (CC {control.cc}) to {selected}; "
        f"{len(channels)} channel(s), active sound only, not saved"
    )


@live_group.command("microfreak-sentinel")
@click.argument("output_path", type=click.Path())
@click.option("--channel", type=click.IntRange(1, 16), default=1, show_default=True)
@click.option(
    "--all-channels",
    is_flag=True,
    help="Send identical sentinels on channels 1..16 to resolve receive-channel uncertainty.",
)
@click.option("--port", default=None, help="Exact MIDI output name.")
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def live_microfreak_sentinel(
    output_path: str,
    channel: int,
    all_channels: bool,
    port: str | None,
    i_understand_this_changes_live_buffer: bool,
):
    """Send one collision-resistant CC batch and save its experiment plan."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this changes the active MicroFreak sound; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    try:
        channels = list(range(1, 17)) if all_channels else [channel]
        selected = ""
        sent = []
        for selected_channel in channels:
            selected, sent = send_control_batch(
                DeviceModel.MICROFREAK,
                MICROFREAK_SENTINEL_VALUES,
                channel=selected_channel,
                port=port,
            )
    except LiveControlError as exc:
        raise click.ClickException(str(exc)) from exc
    plan = {
        "schema_version": "microfreak-cc-sentinel/1",
        "device": "microfreak",
        "transport": "documented_midi_cc_live_buffer",
        "port": selected,
        "channel": channel if not all_channels else None,
        "channels": channels,
        "saved": False,
        "warning": (
            "Values are live only. Select the intended occupied test slot before "
            "sending; a physical Save is required before preset-byte correlation."
        ),
        "values": {
            name: {"cc": control.cc, "value": value}
            for name, control, value in sent
        },
    }
    Path(output_path).write_text(json.dumps(plan, indent=2) + "\n")
    click.echo(
        f"Sent {len(sent)} distinct MicroFreak CC sentinels on "
        f"{len(channels)} channel(s) to {selected}; "
        f"plan -> {output_path}. Live buffer only; nothing was saved."
    )


@live_group.command("analyze-microfreak-sentinel")
@click.argument("before_path", type=click.Path(exists=True))
@click.argument("after_path", type=click.Path(exists=True))
@click.argument("plan_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
@click.option(
    "--normalization-control",
    type=click.Path(exists=True),
    default=None,
    help="Same baseline physically saved without sentinels.",
)
def live_analyze_microfreak_sentinel(
    before_path: str,
    after_path: str,
    plan_path: str,
    output_path: str,
    normalization_control: str | None,
):
    """Resolve MicroFreak payload-layout candidates from one saved CC batch."""
    try:
        before_doc = PatchDocument.model_validate_json(Path(before_path).read_text())
        after_doc = PatchDocument.model_validate_json(Path(after_path).read_text())
        if before_doc.device != DeviceModel.MICROFREAK:
            raise ValueError("before document is not a MicroFreak patch")
        if after_doc.device != DeviceModel.MICROFREAK:
            raise ValueError("after document is not a MicroFreak patch")
        plan = json.loads(Path(plan_path).read_text())
        if plan.get("schema_version") != "microfreak-cc-sentinel/1":
            raise ValueError("unsupported or missing sentinel plan schema_version")
        expected = {
            key: int(entry["value"])
            for key, entry in plan.get("values", {}).items()
        }
        control_payload = None
        if normalization_control:
            control_doc = PatchDocument.model_validate_json(
                Path(normalization_control).read_text()
            )
            if control_doc.device != DeviceModel.MICROFREAK:
                raise ValueError("normalization control is not a MicroFreak patch")
            control_payload = MicroFreakPreset.from_document(control_doc).payload
        report = analyze_microfreak_cc_sentinel(
            MicroFreakPreset.from_document(before_doc).payload,
            MicroFreakPreset.from_document(after_doc).payload,
            expected,
            normalization_control=control_payload,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    click.echo(
        f"Sentinel analysis: layout={report['resolved_layout'] or 'inconclusive'} "
        f"changed_bytes={report['total_changed_bytes']} -> {output_path}"
    )


def _endpoint(transport: ElektroidTransport, transport_id: int) -> DeviceEndpoint:
    try:
        return transport.resolve(transport_id)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc


@main.command("pull")
@click.argument("transport_id", type=int)
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("output_path", type=click.Path())
def pull_command(transport_id: int, slot: int, output_path: str):
    """Read a saved patch from a connected device into shared JSON."""
    transport = ElektroidTransport()
    endpoint = _endpoint(transport, transport_id)
    if endpoint.device != DeviceModel.MICROFREAK:
        raise click.ClickException(
            "direct MiniFreak patch reads are not decoded yet; export .mnfx via MiniFreak V"
        )
    preset = transport.read_preset(endpoint, slot)
    document = preset.to_document(source_slot=slot)
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Read MicroFreak slot {slot}: {preset.name} -> {output_path}")


@main.command("pull-microfreak-direct")
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def pull_microfreak_direct_command(slot: int, output_path: str, port: str | None):
    """Read one MicroFreak preset without Elektroid or an Arturia application."""
    try:
        preset = MicroFreakMidiTransport(port_name=port).read_preset(slot)
        document = preset.to_document(source_slot=slot)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Direct-read MicroFreak slot {slot}: {preset.name} -> {output_path}")


@main.command("pull-microfreak-init-direct")
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def pull_microfreak_init_direct_command(output_path: str, port: str | None):
    """Read firmware 5's reserved Init template into editable shared JSON."""
    try:
        preset = MicroFreakMidiTransport(port_name=port).read_initializer_template()
        document = preset.to_document()
        document.shared["device_source"] = {
            "kind": "firmware_initializer_template",
            "transport": "arturia-microfreak-sysex",
            "bank": 4,
            "program": 0,
            "tracks_active_buffer": False,
        }
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Direct-read MicroFreak firmware Init template -> {output_path}")


@main.command("pull-microfreak-wavetable-direct")
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def pull_microfreak_wavetable_direct_command(
    slot: int, output_path: str, port: str | None
):
    """Read one MicroFreak wavetable without Elektroid or Arturia apps."""
    try:
        table = MicroFreakMidiTransport(port_name=port).read_wavetable(slot)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        json.dumps(table.to_document().to_dict(), indent=2) + "\n"
    )
    click.echo(
        f"Direct-read MicroFreak wavetable {slot}: {table.name} -> {output_path}"
    )


@main.command("push-microfreak-wavetable-direct")
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-writes", is_flag=True)
def push_microfreak_wavetable_direct_command(
    slot: int,
    input_path: str,
    backup_path: str,
    port: str | None,
    i_understand_this_writes: bool,
):
    """Guarded wavetable upload without Elektroid or Arturia apps."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this replaces a MicroFreak wavetable slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        source = Path(input_path)
        if source.suffix.lower() in {".mfw", ".mfwz"}:
            table = MicroFreakWavetable.from_mfw(source.read_bytes())
        else:
            table = MicroFreakWavetable.from_document(json.loads(source.read_text()))
        report = MicroFreakMidiTransport(port_name=port).write_wavetable(
            slot, table, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@main.command("clear-microfreak-wavetable-direct")
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-clears", is_flag=True)
def clear_microfreak_wavetable_direct_command(
    slot: int,
    backup_path: str,
    port: str | None,
    i_understand_this_clears: bool,
):
    """Clear one MicroFreak wavetable slot after making an exact backup."""
    if not i_understand_this_clears:
        raise click.ClickException(
            "this clears a MicroFreak wavetable slot; add "
            "--i-understand-this-clears to proceed"
        )
    try:
        report = MicroFreakMidiTransport(port_name=port).clear_wavetable(
            slot, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@main.command("set-microfreak-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("parameter", type=click.Choice(tuple(MICROFREAK_PARAMETER_SPECS)))
@click.argument("value", type=float)
@click.argument("output_path", type=click.Path())
def set_microfreak_json_command(
    input_path: str, parameter: str, value: float, output_path: str
):
    """Offline-edit one evidence-labelled MicroFreak payload field."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        target_value: float | int = value
        if MICROFREAK_PARAMETER_SPECS[parameter].value_type == "integer":
            if not value.is_integer():
                raise ValueError(f"{parameter} requires an integer value")
            target_value = int(value)
        preset.payload = set_microfreak_parameter(
            preset.payload, parameter, target_value
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Set MicroFreak {parameter}={target_value} -> {output_path}")


@main.command("set-microfreak-structured-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("parameter")
@click.argument("raw_u16", type=click.IntRange(0, 65535))
@click.argument("output_path", type=click.Path())
def set_microfreak_structured_json_command(
    input_path: str, parameter: str, raw_u16: int, output_path: str
):
    """Offline-edit one firmware-tagged MicroFreak field by exact raw value."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_structured_raw_u16(preset.payload, parameter, raw_u16)
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Set MicroFreak {parameter} raw_u16={raw_u16} -> {output_path}")


@main.command("set-microfreak-structured-value")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("parameter")
@click.argument("value", type=float)
@click.argument("output_path", type=click.Path())
def set_microfreak_structured_value_command(
    input_path: str, parameter: str, value: float, output_path: str
):
    """Offline-edit one interpreted firmware-tagged MicroFreak value."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_structured_value(preset.payload, parameter, value)
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    result = updated.microfreak.structured_parameters[parameter]
    click.echo(
        f"Set MicroFreak {parameter}={result.interpreted_value} "
        f"({result.value_kind}, raw_u16={result.raw_u16}) -> {output_path}"
    )


@main.command("set-microfreak-sequence-note")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("pattern", type=click.Choice(("A", "B"), case_sensitive=False))
@click.argument("step", type=click.IntRange(1, 64))
@click.argument("voice", type=click.IntRange(1, 4))
@click.argument("note")
@click.argument("output_path", type=click.Path())
def set_microfreak_sequence_note_command(
    input_path: str,
    pattern: str,
    step: int,
    voice: int,
    note: str,
    output_path: str,
):
    """Offline-edit one Sequence A/B note slot; use 'clear' for an empty slot."""
    try:
        note_value = None if note.lower() in {"clear", "none", "null"} else int(note)
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_sequence_note(
            preset.payload, pattern, step, voice, note_value
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    rendered_note = "clear" if note_value is None else str(note_value)
    click.echo(
        f"Set MicroFreak Sequence {pattern.upper()} step {step} voice {voice} "
        f"note={rendered_note} -> {output_path}"
    )


@main.command("set-microfreak-sequence-velocity")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("pattern", type=click.Choice(("A", "B"), case_sensitive=False))
@click.argument("step", type=click.IntRange(1, 64))
@click.argument("voice", type=click.IntRange(1, 4))
@click.argument("velocity", type=click.IntRange(0, 127))
@click.argument("output_path", type=click.Path())
def set_microfreak_sequence_velocity_command(
    input_path: str,
    pattern: str,
    step: int,
    voice: int,
    velocity: int,
    output_path: str,
):
    """Offline-edit one Sequence A/B note velocity."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_sequence_velocity(
            preset.payload, pattern, step, voice, velocity
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Set MicroFreak Sequence {pattern.upper()} step {step} voice {voice} "
        f"velocity={velocity} -> {output_path}"
    )


@main.command("set-microfreak-sequence-status")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("pattern", type=click.Choice(("A", "B"), case_sensitive=False))
@click.argument("step", type=click.IntRange(1, 64))
@click.argument("status", type=click.Choice(("rest", "trigger", "tie")))
@click.argument("output_path", type=click.Path())
def set_microfreak_sequence_status_command(
    input_path: str,
    pattern: str,
    step: int,
    status: str,
    output_path: str,
):
    """Offline-edit one Sequence A/B rest, trigger, or tie status."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_sequence_note_status(
            preset.payload, pattern, step, status
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Set MicroFreak Sequence {pattern.upper()} step {step} "
        f"status={status} -> {output_path}"
    )


@main.command("set-microfreak-sequence-automation")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("pattern", type=click.Choice(("A", "B"), case_sensitive=False))
@click.argument("step", type=click.IntRange(1, 64))
@click.argument("lane", type=click.IntRange(1, 4))
@click.argument("value")
@click.argument("output_path", type=click.Path())
def set_microfreak_sequence_automation_command(
    input_path: str,
    pattern: str,
    step: int,
    lane: int,
    value: str,
    output_path: str,
):
    """Offline-edit one sequence automation lane; use 'clear' to unset it."""
    try:
        automation_value = (
            None if value.lower() in {"clear", "none", "null"} else int(value)
        )
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_sequence_automation(
            preset.payload, pattern, step, lane, automation_value
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    rendered = "clear" if automation_value is None else str(automation_value)
    click.echo(
        f"Set MicroFreak Sequence {pattern.upper()} step {step} lane {lane} "
        f"automation={rendered} -> {output_path}"
    )


@main.command("set-microfreak-sequence-destination")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("pattern", type=click.Choice(("A", "B"), case_sensitive=False))
@click.argument("lane", type=click.IntRange(1, 4))
@click.argument("destination")
@click.argument("output_path", type=click.Path())
def set_microfreak_sequence_destination_command(
    input_path: str,
    pattern: str,
    lane: int,
    destination: str,
    output_path: str,
):
    """Set a lane destination by mapped name/hex address, or clear it."""

    try:
        normalized = destination.lower()
        if normalized in {"clear", "none", "null"}:
            live_address = None
        else:
            candidates = [
                address
                for address in SEQUENCE_AUTOMATION_DESTINATION_ADDRESSES
                if MICROFREAK_LIVE_WORD_SEMANTICS.get(address, {}).get("parameter")
                == destination
            ]
            if len(candidates) == 1:
                live_address = candidates[0]
            elif len(candidates) > 1:
                raise ValueError(
                    f"{destination!r} has multiple observed destination aliases; "
                    + ", ".join(f"{address:04x}" for address in sorted(candidates))
                )
            else:
                live_address = int(normalized.removeprefix("0x"), 16)
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        preset.payload = set_sequence_automation_destination(
            preset.payload, pattern, lane, live_address
        )
        updated = preset.to_document(source_slot=document.metadata.source_slot)
        updated.metadata = document.metadata
        updated.shared = document.shared
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        updated.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    rendered = (
        "clear"
        if live_address is None
        else f"{live_address:04x} "
        f"({MICROFREAK_LIVE_WORD_SEMANTICS[live_address]['parameter']})"
    )
    click.echo(
        f"Set MicroFreak Sequence {pattern.upper()} lane {lane} "
        f"destination={rendered} -> {output_path}"
    )


@main.command("microfreak-status-records-direct")
@click.argument("output_path", type=click.Path())
@click.option(
    "--selector",
    "selectors",
    type=click.Choice(tuple(str(item) for item in MICROFREAK_STATUS_RECORD_SELECTORS)),
    multiple=True,
    help="Firmware-backed read-only selector; repeat to restrict the capture.",
)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_status_records_direct_command(
    output_path: str, selectors: tuple[str, ...], port: str | None
):
    """Capture raw kind-0x13 replies and verify live/global state is exact."""

    selected = (
        tuple(int(selector) for selector in selectors)
        if selectors
        else MICROFREAK_STATUS_RECORD_SELECTORS
    )
    try:
        report = MicroFreakMidiTransport(
            port_name=port
        ).capture_status_state_record_replies(selected)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    document = {
        "schema_version": "microfreak-status-record-capture/1",
        "device": "microfreak",
        "transport": "arturia-microfreak-sysex-49-6-kind-13",
        "evidence": "firmware_static_read_only_plus_raw_hardware_capture",
        "selectors": list(selected),
        "replies": [asdict(reply) for reply in report.replies],
        "state_verification": {
            "live_table_exact": report.live_table_exact,
            "changed_live_addresses": [
                f"{address:04x}" for address in report.changed_live_addresses
            ],
            "global_settings_exact": report.global_settings_exact,
            "changed_global_settings": [
                {"name": name, "before": before, "after": after}
                for name, before, after in report.changed_global_settings
            ],
        },
    }
    Path(output_path).write_text(json.dumps(document, indent=2) + "\n")
    if not report.live_table_exact or not report.global_settings_exact:
        raise click.ClickException(
            f"status capture changed device state; raw report retained: {output_path}"
        )
    click.echo(
        f"Captured {len(report.replies)} MicroFreak status replies with exact "
        f"live/global state -> {output_path}"
    )


@main.command("microfreak-globals-direct")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_globals_direct_command(port: str | None):
    """Read all MIDI Control Center-visible MicroFreak global settings."""
    try:
        settings = MicroFreakMidiTransport(port_name=port).read_global_settings()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(settings, indent=2))


@main.command("microfreak-globals-json-direct")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_globals_json_direct_command(port: str | None):
    """Read globals with audited labels/domains and explicit raw-only gaps."""
    try:
        settings = MicroFreakMidiTransport(port_name=port).read_global_settings()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rows = {
        name: {
            "code": MICROFREAK_GLOBAL_CODES[name],
            **decode_microfreak_global(name, value),
        }
        for name, value in settings.items()
    }
    click.echo(
        json.dumps(
            {
                "schema_version": "microfreak-globals/1",
                "device": "microfreak",
                "setting_count": len(rows),
                "audited_domain_count": len(MICROFREAK_GLOBAL_VALUE_SPECS),
                "raw_only_count": len(rows) - len(MICROFREAK_GLOBAL_VALUE_SPECS),
                "settings": rows,
            },
            indent=2,
        )
    )


@main.command("microfreak-sequence-playback-direct")
@click.argument("output_path", type=click.Path())
@click.option(
    "--source-slot",
    type=click.IntRange(1, 512),
    default=None,
    help="Optionally select a saved sequence preset before capture.",
)
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    default=None,
    help="Required with --source-slot; recalled and verified afterward.",
)
@click.option("--clocks", type=click.IntRange(1, 8192), default=192, show_default=True)
@click.option(
    "--live-snapshot-every",
    type=click.IntRange(1, 8192),
    default=None,
    help="Read operation-41 live words every N clocks (maximum 128 snapshots).",
)
@click.option(
    "--live-field",
    "live_fields",
    multiple=True,
    type=click.Choice(tuple(sorted(MICROFREAK_STRUCTURED_LIVE_WORDS))),
    help="Limit snapshots to a mapped field and every alias; repeat as needed.",
)
@click.option(
    "--clock-interval",
    type=click.FloatRange(min=0.001, max=0.1),
    default=0.01,
    show_default=True,
    help="Seconds between MIDI Clock messages.",
)
@click.option("--trigger-note", type=click.IntRange(0, 127), default=60)
@click.option("--velocity", type=click.IntRange(1, 127), default=80)
@click.option("--channel", type=click.IntRange(1, 16), default=1)
@click.option("--backup-dir", type=click.Path(), default="backups")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-temporarily-changes-clock-source", is_flag=True)
def microfreak_sequence_playback_direct_command(
    output_path: str,
    source_slot: int | None,
    recovery_slot: int | None,
    clocks: int,
    live_snapshot_every: int | None,
    live_fields: tuple[str, ...],
    clock_interval: float,
    trigger_note: int,
    velocity: int,
    channel: int,
    backup_dir: str,
    port: str | None,
    i_understand_this_temporarily_changes_clock_source: bool,
):
    """Behaviorally observe an active sequence through outgoing USB MIDI."""

    if not i_understand_this_temporarily_changes_clock_source:
        raise click.ClickException(
            "this temporarily changes Clock Source and starts the sequencer; add "
            "--i-understand-this-temporarily-changes-clock-source to proceed"
        )
    if source_slot is not None and recovery_slot is None:
        raise click.ClickException("--recovery-slot is required with --source-slot")
    if source_slot is None and recovery_slot is not None:
        raise click.ClickException("--recovery-slot requires --source-slot")
    if live_fields and live_snapshot_every is None:
        raise click.ClickException("--live-field requires --live-snapshot-every")

    import time as _time

    transport = MicroFreakMidiTransport(port_name=port)
    stamp = f"{_time.time_ns()}"
    backup_root = Path(backup_dir)
    before_backup = backup_root / f"microfreak-clock-before-{stamp}.json"
    usb_backup = backup_root / f"microfreak-clock-usb-{stamp}.json"
    baseline = None
    final = None
    clock_before = None
    events = None
    live_snapshots = None
    experiment_error: Exception | None = None
    restoration_error: Exception | None = None
    try:
        baseline = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
        clock_before = transport.read_global_settings()["clock.source"]
        if source_slot is not None:
            transport.select_preset(source_slot)
            transport.sleep(0.3)
        if clock_before != 1:
            report = transport.write_global_setting(
                "clock.source", 1, before_backup
            )
            if not report.exact_readback:
                raise RuntimeError("Clock Source USB readback was not exact")
        if live_snapshot_every is None:
            events = transport.capture_sequence_playback_events(
                clock_count=clocks,
                clock_interval_seconds=clock_interval,
                trigger_note=trigger_note,
                velocity=velocity,
                channel=channel,
            )
        else:
            trace = transport.capture_sequence_live_trace(
                clock_count=clocks,
                snapshot_every_clocks=live_snapshot_every,
                clock_interval_seconds=clock_interval,
                trigger_note=trigger_note,
                velocity=velocity,
                channel=channel,
                snapshot_addresses=tuple(
                    address
                    for field_name in dict.fromkeys(live_fields)
                    for address in MICROFREAK_STRUCTURED_LIVE_WORDS[field_name]
                )
                or None,
            )
            events = trace.events
            live_snapshots = trace.snapshots
    except Exception as exc:
        experiment_error = exc
    finally:
        try:
            if source_slot is not None:
                assert recovery_slot is not None
                transport.select_preset(recovery_slot)
                transport.sleep(0.3)
            if clock_before is not None:
                current_clock = transport.read_global_settings()["clock.source"]
                if current_clock != clock_before:
                    report = transport.write_global_setting(
                        "clock.source", clock_before, usb_backup
                    )
                    if not report.exact_readback:
                        raise RuntimeError("Clock Source restoration was not exact")
            if baseline is not None:
                final = {
                    word.index: word.raw_u16
                    for word in transport.read_live_parameter_words()
                }
        except Exception as exc:
            restoration_error = exc

    final_differences = (
        []
        if baseline is None or final is None
        else [address for address in baseline if baseline[address] != final[address]]
    )
    if restoration_error is not None or final_differences:
        details = restoration_error or (
            "live differences "
            + ", ".join(f"0x{address:04x}" for address in final_differences)
        )
        raise click.ClickException(
            f"sequence playback restoration failed: {details}; "
            f"clock backups: {before_backup}, {usb_backup}"
        )
    if experiment_error is not None:
        raise click.ClickException(
            f"sequence playback capture failed after verified restoration: "
            f"{experiment_error}"
        )
    assert events is not None and clock_before is not None

    rows = [event.__dict__ for event in events]
    event_counts: dict[str, int] = {}
    for event in events:
        event_counts[event.message_type] = event_counts.get(event.message_type, 0) + 1
    musical_types = {
        "note_on",
        "note_off",
        "control_change",
        "pitchwheel",
        "aftertouch",
        "polytouch",
    }
    structured_by_address: dict[int, list[str]] = {}
    for field_name, addresses in MICROFREAK_STRUCTURED_LIVE_WORDS.items():
        for address in addresses:
            structured_by_address.setdefault(address, []).append(field_name)
    live_snapshot_rows = []
    if live_snapshots is not None:
        live_baseline = {
            word.index: word.raw_u16 for word in live_snapshots[0].words
        }
        for snapshot in live_snapshots:
            values = {word.index: word.raw_u16 for word in snapshot.words}
            changes = []
            for address, before_value in live_baseline.items():
                after_value = values[address]
                if before_value == after_value:
                    continue
                changes.append(
                    {
                        "address": f"{address:04x}",
                        "before_raw_u16": before_value,
                        "after_raw_u16": after_value,
                        "midi_semantic": MICROFREAK_LIVE_WORD_SEMANTICS.get(
                            address
                        ),
                        "structured_fields": structured_by_address.get(address, []),
                    }
                )
            live_snapshot_rows.append(
                {
                    "clock_sent": snapshot.clock_sent,
                    "changed_from_clock_zero": changes,
                    "words": {
                        f"{address:04x}": value
                        for address, value in values.items()
                    },
                }
            )
    document = {
        "schema_version": "microfreak-sequence-playback/1",
        "device": "microfreak",
        "capture_kind": "behavioral_partial_current_pattern",
        "evidence_status": "hardware_usb_midi_output_observed",
        "source_slot": source_slot,
        "recovery_slot": recovery_slot,
        "clock_count": clocks,
        "clock_interval_seconds": clock_interval,
        "trigger": {
            "note": trigger_note,
            "velocity": velocity,
            "channel": channel,
        },
        "clock_source_before": clock_before,
        "clock_source_restored": True,
        "live_table_restored": True,
        "event_counts": event_counts,
        "events": rows,
        "musical_events": [
            row for row in rows if row["message_type"] in musical_types
        ],
        "live_trace": None
        if live_snapshots is None
        else {
            "snapshot_every_clocks": live_snapshot_every,
            "snapshot_count": len(live_snapshots),
            "operation": 41,
            "fields": list(dict.fromkeys(live_fields)),
            "word_count_per_snapshot": len(live_snapshots[0].words),
            "clock_paused_during_snapshot": True,
            "snapshots": live_snapshot_rows,
        },
        "boundaries": {
            "selected_pattern_only": True,
            "lossless_sequence_dump": False,
            "audio_required": False,
            "panel_input_required": False,
        },
    }
    Path(output_path).write_text(json.dumps(document, indent=2) + "\n")
    click.echo(
        f"Captured {len(events)} MicroFreak playback events; "
        + (
            f"sampled {len(live_snapshots)} operation-41 snapshots; "
            if live_snapshots is not None
            else ""
        )
        + f"clock and live table restored exactly -> {output_path}"
    )


@main.command("microfreak-global-codes-direct")
@click.argument("codes", nargs=-1, type=click.IntRange(0, 127), required=True)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_global_codes_direct_command(codes: tuple[int, ...], port: str | None):
    """Read raw operation-43 selectors without changing the MicroFreak."""
    try:
        settings = MicroFreakMidiTransport(port_name=port).read_global_codes(codes)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps({f"0x{code:02x}": value for code, value in settings.items()}, indent=2)
    )


@main.command("microfreak-global-write-probe")
@click.argument("name", type=click.Choice(sorted(MICROFREAK_GLOBAL_CODES)))
@click.argument("target", type=click.IntRange(0, 127))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot recalled if the inverse global write leaves live changes.",
)
@click.option("--i-understand-this-changes-device-setting", is_flag=True)
def microfreak_global_write_probe_command(
    name: str,
    target: int,
    port: str | None,
    recovery_slot: int,
    i_understand_this_changes_device_setting: bool,
):
    """Reversibly prove one operation-42 global-setting write."""
    if not i_understand_this_changes_device_setting:
        raise click.ClickException(
            "this temporarily changes a MicroFreak device setting; add "
            "--i-understand-this-changes-device-setting to proceed"
        )
    try:
        report = MicroFreakMidiTransport(port_name=port).probe_global_setting_write(
            name, target, recovery_slot
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                **report.__dict__,
                "code_hex": f"0x{report.code:02x}",
                "changes": [
                    {
                        **change.__dict__,
                        "address": f"0x{change.index:04x}",
                    }
                    for change in report.changes
                ],
                "changed_after_restore_addresses": [
                    f"0x{address:04x}"
                    for address in report.changed_after_restore_addresses
                ],
            },
            indent=2,
        )
    )


@main.command("set-microfreak-global-direct")
@click.argument("name", type=click.Choice(sorted(MICROFREAK_GLOBAL_VALUE_SPECS)))
@click.argument("target", type=click.IntRange(0, 127))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-changes-device-setting", is_flag=True)
def set_microfreak_global_direct_command(
    name: str,
    target: int,
    backup_path: str,
    port: str | None,
    i_understand_this_changes_device_setting: bool,
):
    """Set one audited global value with backup and exact readback."""
    if not i_understand_this_changes_device_setting:
        raise click.ClickException(
            "this changes a persistent MicroFreak device setting; add "
            "--i-understand-this-changes-device-setting to proceed"
        )
    try:
        report = MicroFreakMidiTransport(port_name=port).write_global_setting(
            name, target, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {**report.__dict__, "code_hex": f"0x{report.code:02x}"}, indent=2
        )
    )


@main.command("microfreak-samples-direct")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--occupied-only", is_flag=True, help="Omit empty sample slots.")
def microfreak_samples_direct_command(port: str | None, occupied_only: bool):
    """Read the 128-slot MicroFreak sample directory without changing it."""
    try:
        headers = MicroFreakMidiTransport(port_name=port).read_sample_inventory()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rows = [header.__dict__ for header in headers]
    if occupied_only:
        rows = [row for row in rows if not row["empty"]]
    click.echo(
        json.dumps(
            {
                "schema_version": "microfreak-sample-inventory/1",
                "device": "microfreak",
                "slots": rows,
            },
            indent=2,
        )
    )


@main.command("microfreak-sample-storage-direct")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_sample_storage_direct_command(port: str | None):
    """Read MicroFreak sample-memory utilization without changing it."""
    try:
        stats = MicroFreakMidiTransport(port_name=port).read_sample_storage_stats()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "schema_version": "microfreak-sample-storage/1",
                "device": "microfreak",
                **stats.__dict__,
            },
            indent=2,
        )
    )


@main.command("microfreak-live-word-direct")
@click.argument("index", type=click.IntRange(0, 0x170F))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_live_word_direct_command(index: int, port: str | None):
    """Read one bounded word from the active MicroFreak parameter table."""
    try:
        word = MicroFreakMidiTransport(port_name=port).read_live_parameter_word(index)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(word.__dict__, indent=2))


@main.command("microfreak-live-table-direct")
@click.option("--start", type=click.IntRange(0, 383), default=0, show_default=True)
@click.option("--count", type=click.IntRange(1, 384), default=384, show_default=True)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_live_table_direct_command(
    start: int, count: int, port: str | None
):
    """Read a range of the active MicroFreak 24-by-16 word table."""
    try:
        words = MicroFreakMidiTransport(port_name=port).read_live_parameter_words(
            start, count
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    document_words = []
    for word in words:
        semantic = MICROFREAK_LIVE_WORD_SEMANTICS.get(word.index)
        document_words.append(
            MicroFreakLiveWordData(
                address=word.index,
                group=word.index >> 8,
                word=word.index & 0xFF,
                raw_u16=word.raw_u16,
                raw_s16=word.signed_i16,
                raw_payload_hex=word.raw_payload_hex,
                parameter=semantic["parameter"] if semantic else None,
                relationship=semantic["relationship"] if semantic else None,
                evidence=(
                    semantic.get("evidence", "hardware_cc_sentinel_exact_restore")
                    if semantic
                    else None
                ),
            )
        )
    document = MicroFreakLiveTableDocument(
        start_ordinal=start,
        word_count=len(document_words),
        complete_table=start == 0 and len(document_words) == 384,
        words=document_words,
    )
    click.echo(document.model_dump_json(indent=2))


@main.command("microfreak-live-structured-direct")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_live_structured_direct_command(port: str | None):
    """Read named current MicroFreak fields in one complete live-table pass."""
    transport = MicroFreakMidiTransport(port_name=port)
    try:
        fields, oscillator = transport.read_live_structured_snapshot()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    engine_index = infer_oscillator_engine_index(oscillator.raw_u16)
    rows = [
        {
            "name": "VCO.Type",
            "raw_u16": oscillator.raw_u16,
            "signed_i16": oscillator.signed_i16,
            "addresses": [0],
            "alias_values": [oscillator.raw_u16],
            "aliases_match": True,
            "engine_index": engine_index,
            "engine_name": MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(engine_index),
            "encoding": "runtime_engine_index_normalized_to_22",
            "evidence": "hardware_saved_live_320_plus_cc9_all_22",
        },
        *[
            {
                **field.__dict__,
                "addresses": [f"0x{address:04x}" for address in field.addresses],
                "alias_values": list(field.alias_values),
            }
            for field in fields
        ],
    ]
    click.echo(
        json.dumps(
            {
                "schema_version": "microfreak-live-structured/2",
                "device": "microfreak",
                "read_only": True,
                "complete_live_word_count": 384,
                "mapped_field_count": len(rows),
                "all_aliases_match": all(row["aliases_match"] for row in rows),
                "fields": rows,
                "unresolved": {
                    "mutually_confounded_in_saved_corpus": list(
                        MICROFREAK_STRUCTURED_LIVE_AMBIGUOUS
                    ),
                    "nonvarying_in_320_preset_corpus": list(
                        MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED
                    ),
                    "sequence_body": "not_present_in_384_word_live_table",
                },
                "constant_role_candidates": {
                    name: {
                        "role": structured_field_role(name)[0],
                        "evidence": STRUCTURED_ROLE_EVIDENCE,
                        "live_address": None,
                    }
                    for name in MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED
                },
                "transport_boundaries": {
                    "saved_field_mapped_despite_documented_cc_no_effect": list(
                        MICROFREAK_STRUCTURED_NO_LIVE_TABLE_CC_EFFECT
                    ),
                    "separate_named_global_counterpart": (
                        MICROFREAK_STRUCTURED_GLOBAL_COUNTERPARTS
                    ),
                },
            },
            indent=2,
        )
    )


@main.command("microfreak-current-overlay-json-direct")
@click.argument("base_slot", type=click.IntRange(1, 512))
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_current_overlay_json_direct_command(
    base_slot: int, output_path: str, port: str | None
):
    """Capture current mapped parameters over a complete saved-slot base."""

    from minifreak_patch.microfreak_current import overlay_current_parameter_object

    transport = MicroFreakMidiTransport(port_name=port)
    try:
        base = transport.read_preset(base_slot)
        fields, oscillator = transport.read_live_structured_snapshot()
        report = overlay_current_parameter_object(
            base,
            base_slot=base_slot,
            live_fields=fields,
            oscillator_runtime_raw_u16=oscillator.raw_u16,
        )
        document = report.preset.to_document(source_slot=base_slot)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    artifact = {
        "schema_version": "microfreak-current-overlay/1",
        "device": "microfreak",
        "capture": {
            "active_transport": "operation_41_complete_384_word_table",
            "base_saved_slot": base_slot,
            "base_slot_selection_is_assumed_not_device_read": True,
            "mapped_current_field_count": len(fields) + 1,
            "current_parameter_fields_applied": list(
                report.current_parameter_fields_applied
            ),
            "current_parameter_field_count": len(
                report.current_parameter_fields_applied
            ),
            "live_fields_missing_from_base": [
                {
                    "name": field.name,
                    "raw_u16": field.raw_u16,
                    "signed_i16": field.signed_i16,
                    "addresses": [f"0x{address:04x}" for address in field.addresses],
                    "alias_values": list(field.alias_values),
                    "aliases_match": field.aliases_match,
                }
                for field in fields
                if field.name in report.live_fields_missing_from_base
            ],
            "oscillator_engine_index": report.oscillator_engine_index,
            "oscillator_engine_applied": report.oscillator_engine_applied,
            "exact_payload_match_to_base": report.exact_payload_match_to_base,
            "regions_from_current_read": [
                f"{len(fields) + 1} mapped named parameter fields",
            ],
            "regions_preserved_from_saved_base_not_current_read": [
                "preset header and characteristics",
                "Sequence A and Sequence B 0x824-byte body",
                "six raw-only internal or UI-action tags",
                "unmapped metadata and reserved bytes",
            ],
            "completeness": "partial_current_complete_saved_base",
        },
        "patch": document.model_dump(mode="json", exclude_none=True),
    }
    Path(output_path).write_text(json.dumps(artifact, indent=2) + "\n")
    click.echo(
        f"Captured {len(fields) + 1} mapped current MicroFreak fields; applied "
        f"{len(report.current_parameter_fields_applied)} to saved slot "
        f"{base_slot}'s compatible tagged layout -> {output_path}"
    )


@main.command("microfreak-live-word-write-probe")
@click.argument("index", type=click.IntRange(0, 0x170F))
@click.argument("target", type=click.IntRange(0, 0x7FFF))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot to recall automatically if verification fails.",
)
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def microfreak_live_word_write_probe_command(
    index: int,
    target: int,
    port: str | None,
    recovery_slot: int,
    i_understand_this_changes_live_buffer: bool,
):
    """Reversibly probe operation 40 and verify the entire live table."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this temporarily changes the active MicroFreak sound; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    try:
        report = transport.probe_live_parameter_word_write(
            index, target, recovery_slot
        )
    except Exception as exc:
        recovery = ""
        try:
            transport.select_preset(recovery_slot)
            recovery = f"; recovery slot {recovery_slot} recall sent"
        except Exception as recovery_exc:
            recovery = f"; recovery recall also failed: {recovery_exc}"
        raise click.ClickException(f"{exc}{recovery}") from exc
    click.echo(
        json.dumps(
            {
                **report.__dict__,
                "changed_after_addresses": [
                    f"0x{address:04x}" for address in report.changed_after_addresses
                ],
                "changed_after_restore_addresses": [
                    f"0x{address:04x}"
                    for address in report.changed_after_restore_addresses
                ],
            },
            indent=2,
        )
    )


@main.command("microfreak-live-cc-probe")
@click.argument("parameter", type=click.Choice(sorted(controls_for(DeviceModel.MICROFREAK))))
@click.argument("target", type=click.IntRange(0, 127))
@click.argument("restore", type=click.IntRange(0, 127))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot recalled automatically if the inverse CC is not exact.",
)
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def microfreak_live_cc_probe_command(
    parameter: str,
    target: int,
    restore: int,
    port: str | None,
    recovery_slot: int,
    i_understand_this_changes_live_buffer: bool,
):
    """Correlate one documented CC with the complete active-word table."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this temporarily changes the active MicroFreak sound; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    control = controls_for(DeviceModel.MICROFREAK)[parameter]
    if not control.minimum <= target <= control.maximum:
        raise click.ClickException(
            f"{parameter} target must be {control.minimum}..{control.maximum}"
        )
    if not control.minimum <= restore <= control.maximum:
        raise click.ClickException(
            f"{parameter} restore must be {control.minimum}..{control.maximum}"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    try:
        report = transport.probe_live_control_change(
            parameter,
            control.cc,
            target,
            restore,
            recovery_slot,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                **report.__dict__,
                "changes": [
                    {
                        **change.__dict__,
                        "address": f"0x{change.index:04x}",
                    }
                    for change in report.changes
                ],
                "changed_after_restore_addresses": [
                    f"0x{address:04x}"
                    for address in report.changed_after_restore_addresses
                ],
            },
            indent=2,
        )
    )


@main.command("microfreak-live-record-write-probe")
@click.argument("index", type=click.IntRange(0, 0x170F))
@click.argument("target", type=click.IntRange(0, 0x7FFF))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot to recall automatically if verification fails.",
)
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def microfreak_live_record_write_probe_command(
    index: int,
    target: int,
    port: str | None,
    recovery_slot: int,
    i_understand_this_changes_live_buffer: bool,
):
    """Reversibly probe operation 49/6 and verify the entire live table."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this temporarily changes the active MicroFreak sound; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    try:
        report = transport.probe_live_parameter_state_record_write(
            index, target, recovery_slot
        )
    except Exception as exc:
        recovery = ""
        try:
            transport.select_preset(recovery_slot)
            recovery = f"; recovery slot {recovery_slot} recall sent"
        except Exception as recovery_exc:
            recovery = f"; recovery recall also failed: {recovery_exc}"
        raise click.ClickException(f"{exc}{recovery}") from exc
    click.echo(
        json.dumps(
            {
                **report.__dict__,
                "changed_after_addresses": [
                    f"0x{address:04x}" for address in report.changed_after_addresses
                ],
                "changed_after_restore_addresses": [
                    f"0x{address:04x}"
                    for address in report.changed_after_restore_addresses
                ],
            },
            indent=2,
        )
    )


@main.command("microfreak-sample-download-direct")
@click.argument("slot", type=click.IntRange(1, 128))
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def microfreak_sample_download_direct_command(
    slot: int, output_path: str, port: str | None
):
    """Losslessly download one MicroFreak sample body without changing it."""
    try:
        sample = MicroFreakMidiTransport(port_name=port).read_sample(slot)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_bytes(sample.audio_bytes)
    digest = hashlib.sha256(sample.audio_bytes).hexdigest()
    click.echo(
        f"Direct-read MicroFreak sample {slot}: {sample.header.name} "
        f"({len(sample.audio_bytes)} bytes, sha256={digest}) -> {output_path}"
    )


@main.command("push-microfreak-sample-direct")
@click.argument("slot", type=click.IntRange(1, 128))
@click.argument("input_path", type=click.Path(exists=True, dir_okay=False))
@click.argument("backup_path", type=click.Path())
@click.option("--name", required=True, help="ASCII sample name, at most 12 bytes.")
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-writes", is_flag=True)
def push_microfreak_sample_direct_command(
    slot: int,
    input_path: str,
    backup_path: str,
    name: str,
    port: str | None,
    i_understand_this_writes: bool,
):
    """Guardedly upload raw mono 32 kHz PCM16LE and verify exact readback."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this writes MicroFreak sample storage; add "
            "--i-understand-this-writes to proceed"
        )
    audio_bytes = Path(input_path).read_bytes()
    try:
        report = MicroFreakMidiTransport(port_name=port).write_sample(
            slot, name, audio_bytes, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@main.command("clear-microfreak-sample-direct")
@click.argument("slot", type=click.IntRange(1, 128))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-writes", is_flag=True)
def clear_microfreak_sample_direct_command(
    slot: int,
    backup_path: str,
    port: str | None,
    i_understand_this_writes: bool,
):
    """Clear one sample only after a complete body backup."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this clears one MicroFreak sample slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        report = MicroFreakMidiTransport(port_name=port).clear_sample(
            slot, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@main.command("collect-microfreak-structure-direct")
@click.argument("output_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
def collect_microfreak_structure_direct_command(output_path: str, port: str | None):
    """Read all slots and inventory firmware-tagged preset fields."""
    transport = MicroFreakMidiTransport(port_name=port)
    slots = []
    field_counts: dict[str, int] = {}
    metadata_values: dict[str, set[int]] = {}
    sequence_payloads = []
    occupied = 0
    try:
        for slot, preset in transport.read_preset_bank():
            if not preset.payload:
                continue
            occupied += 1
            sequence_payloads.append(preset.payload)
            fields = parse_structured_fields(preset.payload)
            patterns = parse_sequence_patterns(preset.payload)
            keys = list(fields)
            slots.append({
                "slot": slot,
                "name": preset.name,
                "category_id": preset.category_id,
                "field_count": len(keys),
                "fields": keys,
                "sequence_context": {
                    key: field.raw_u16
                    for key, field in fields.items()
                    if key.startswith("Seq.") or key.startswith("Arp.")
                },
                "sequence_patterns": {
                    name: {
                        "automation_destination_addresses": [
                            None if address is None else f"{address:04x}"
                            for address in pattern.automation_destination_addresses
                        ],
                        "trailer_bytes": list(pattern.trailer_bytes),
                    }
                    for name, pattern in patterns.items()
                },
            })
            for key, field in fields.items():
                field_counts[key] = field_counts.get(key, 0) + 1
                metadata_values.setdefault(key, set()).add(field.metadata)
            if occupied % 32 == 0:
                click.echo(f"Read {occupied} occupied presets through slot {slot}...", err=True)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    report = {
        "schema_version": "microfreak-structured-corpus/2",
        "slots_scanned": 512,
        "occupied_presets": occupied,
        "distinct_fields": len(field_counts),
        "field_counts": dict(sorted(field_counts.items())),
        "metadata_values": {
            key: sorted(values) for key, values in sorted(metadata_values.items())
        },
        "presets": slots,
        "sequence_corpus": analyze_sequence_payloads(sequence_payloads),
    }
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    click.echo(
        f"Inventoried {occupied} occupied presets and {len(field_counts)} "
        f"distinct tagged fields -> {output_path}"
    )


@main.command("collect-microfreak-saved-live-direct")
@click.argument("output_path", type=click.Path())
@click.option(
    "--slot",
    "slots",
    multiple=True,
    type=click.IntRange(1, 512),
    default=tuple(range(1, 13)),
    show_default=True,
    help="Saved slot to correlate; repeat for multiple presets.",
)
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot selected after collection and verified against baseline.",
)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def collect_microfreak_saved_live_direct_command(
    output_path: str,
    slots: tuple[int, ...],
    recovery_slot: int,
    port: str | None,
    i_understand_this_changes_live_buffer: bool,
):
    """Pair saved fields with selected live tables, then restore exactly."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this selects saved presets and replaces the active buffer; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    baseline = None
    rows = []
    collection_error: Exception | None = None
    final = None
    restore_error: Exception | None = None
    try:
        baseline = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
        for slot in dict.fromkeys(slots):
            preset = transport.read_preset(slot)
            if not preset.payload:
                raise ValueError(
                    f"slot {slot} ({preset.name!r}) has no saved preset payload"
                )
            transport.select_preset(slot)
            transport.sleep(0.25)
            live_words = {
                word.index: word.raw_u16
                for word in transport.read_live_parameter_words()
            }
            try:
                parameters = decode_microfreak_parameters(preset.payload)
                structured = parse_structured_fields(preset.payload)
            except Exception as exc:
                raise ValueError(
                    f"slot {slot} ({preset.name!r}) parameter decode failed: {exc}"
                ) from exc
            rows.append(
                {
                    "slot": slot,
                    "name": preset.name,
                    "parameters": {
                        name: item.raw_value for name, item in parameters.items()
                    },
                    "structured_parameters": {
                        name: item.raw_u16 for name, item in structured.items()
                    },
                    "structured_metadata": {
                        name: item.metadata for name, item in structured.items()
                    },
                    "live_words": {
                        f"{address:04x}": value
                        for address, value in live_words.items()
                    },
                }
            )
    except Exception as exc:
        collection_error = exc
    finally:
        try:
            transport.select_preset(recovery_slot)
            transport.sleep(0.4)
            final = {
                word.index: word.raw_u16
                for word in transport.read_live_parameter_words()
            }
        except Exception as exc:
            restore_error = exc

    if restore_error is not None:
        raise click.ClickException(
            f"saved/live collection recovery failed: {restore_error}"
        ) from restore_error
    assert baseline is not None and final is not None
    differences = [
        f"{address:04x}"
        for address in baseline
        if baseline[address] != final[address]
    ]
    if differences:
        raise click.ClickException(
            "recovery slot did not restore the baseline live table; "
            f"differences={differences}"
        )
    if collection_error is not None:
        raise click.ClickException(
            f"saved/live collection failed after exact recovery: {collection_error}"
        ) from collection_error

    report = {
        "schema_version": "microfreak-saved-live-corpus/1",
        "rows": rows,
        "restored_slot": recovery_slot,
        "final_live_differences": [],
    }
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    click.echo(
        f"Correlated {len(rows)} saved presets with complete live tables and "
        f"restored slot {recovery_slot} exactly -> {output_path}"
    )


@main.command("collect-microfreak-oscillator-types-direct")
@click.argument("output_path", type=click.Path())
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot selected after collection and verified against baseline.",
)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def collect_microfreak_oscillator_types_direct_command(
    output_path: str,
    recovery_slot: int,
    port: str | None,
    i_understand_this_changes_live_buffer: bool,
):
    """Correlate every saved preset with the live oscillator-engine word."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this selects every occupied saved preset and replaces the active "
            "buffer; add --i-understand-this-changes-live-buffer to proceed"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    baseline = None
    rows = []
    collection_error: Exception | None = None
    final = None
    restore_error: Exception | None = None
    try:
        baseline = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
        bank = transport.read_preset_bank()
        occupied = [(slot, preset) for slot, preset in bank if preset.payload]
        for ordinal, (slot, preset) in enumerate(occupied, start=1):
            transport.select_preset(slot)
            transport.sleep(0.15)
            live_word = transport.read_live_parameter_word(0x0000)
            saved_type = decode_microfreak_parameters(preset.payload)[
                "osc.type"
            ].raw_value
            rows.append(
                {
                    "slot": slot,
                    "name": preset.name,
                    "category_id": preset.category_id,
                    "saved_legacy_osc_type": saved_type,
                    "live_word_0000": live_word.raw_u16,
                    "inferred_engine_index": infer_oscillator_engine_index(
                        live_word.raw_u16
                    ),
                    "inferred_engine_name": MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(
                        infer_oscillator_engine_index(live_word.raw_u16)
                    ),
                    "payload_base64": base64.b64encode(preset.payload).decode(
                        "ascii"
                    ),
                }
            )
            if ordinal % 32 == 0:
                click.echo(
                    f"Correlated {ordinal}/{len(occupied)} occupied presets...",
                    err=True,
                )
    except Exception as exc:
        collection_error = exc
    finally:
        try:
            transport.select_preset(recovery_slot)
            transport.sleep(0.4)
            final = {
                word.index: word.raw_u16
                for word in transport.read_live_parameter_words()
            }
        except Exception as exc:
            restore_error = exc

    if restore_error is not None:
        raise click.ClickException(
            f"oscillator-type collection recovery failed: {restore_error}"
        ) from restore_error
    assert baseline is not None and final is not None
    differences = [
        f"{address:04x}"
        for address in baseline
        if baseline[address] != final[address]
    ]
    if differences:
        raise click.ClickException(
            "recovery slot did not restore the baseline live table; "
            f"differences={differences}"
        )
    if collection_error is not None:
        raise click.ClickException(
            "oscillator-type collection failed after exact recovery: "
            f"{collection_error}"
        ) from collection_error

    report = {
        "schema_version": "microfreak-oscillator-type-corpus/1",
        "rows": rows,
        "restored_slot": recovery_slot,
        "final_live_differences": [],
    }
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    click.echo(
        f"Correlated {len(rows)} occupied presets with oscillator live state "
        f"and restored slot {recovery_slot} exactly -> {output_path}"
    )


@main.command("collect-microfreak-oscillator-cc-direct")
@click.argument("output_path", type=click.Path())
@click.option(
    "--recovery-slot",
    type=click.IntRange(1, 512),
    required=True,
    help="Saved slot selected after the sweep and verified against baseline.",
)
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def collect_microfreak_oscillator_cc_direct_command(
    output_path: str,
    recovery_slot: int,
    port: str | None,
    i_understand_this_changes_live_buffer: bool,
):
    """Map every documented oscillator Type CC value to live word 0000."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "this sweeps oscillator Type across the active sound; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    transport = MicroFreakMidiTransport(port_name=port)
    baseline = None
    rows = []
    collection_error: Exception | None = None
    final = None
    restore_error: Exception | None = None
    try:
        baseline = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
        selected_port = transport.resolve_port()
        control = controls_for(DeviceModel.MICROFREAK)["osc.type"]
        for value in range(control.minimum, control.maximum + 1):
            send_control(
                DeviceModel.MICROFREAK,
                "osc.type",
                value,
                port=selected_port,
            )
            transport.sleep(0.03)
            live_word = transport.read_live_parameter_word(0x0000)
            engine = infer_oscillator_engine_index(live_word.raw_u16)
            rows.append(
                {
                    "cc": control.cc,
                    "cc_value": value,
                    "live_word_0000": live_word.raw_u16,
                    "inferred_engine_index": engine,
                    "inferred_engine_name": MICROFREAK_OSCILLATOR_ENGINE_NAMES.get(
                        engine
                    ),
                }
            )
    except Exception as exc:
        collection_error = exc
    finally:
        try:
            transport.select_preset(recovery_slot)
            transport.sleep(0.4)
            final = {
                word.index: word.raw_u16
                for word in transport.read_live_parameter_words()
            }
        except Exception as exc:
            restore_error = exc

    if restore_error is not None:
        raise click.ClickException(
            f"oscillator CC sweep recovery failed: {restore_error}"
        ) from restore_error
    assert baseline is not None and final is not None
    differences = [
        f"{address:04x}"
        for address in baseline
        if baseline[address] != final[address]
    ]
    if differences:
        raise click.ClickException(
            "recovery slot did not restore the baseline live table; "
            f"differences={differences}"
        )
    if collection_error is not None:
        raise click.ClickException(
            f"oscillator CC sweep failed after exact recovery: {collection_error}"
        ) from collection_error

    ranges = []
    for row in rows:
        if not ranges or ranges[-1]["engine_index"] != row["inferred_engine_index"]:
            ranges.append(
                {
                    "engine_index": row["inferred_engine_index"],
                    "engine_name": row["inferred_engine_name"],
                    "cc_value_min": row["cc_value"],
                    "cc_value_max": row["cc_value"],
                    "live_word_0000": row["live_word_0000"],
                }
            )
        else:
            ranges[-1]["cc_value_max"] = row["cc_value"]

    report = {
        "schema_version": "microfreak-oscillator-cc-sweep/1",
        "rows": rows,
        "ranges": ranges,
        "restored_slot": recovery_slot,
        "final_live_differences": [],
    }
    Path(output_path).write_text(json.dumps(report, indent=2) + "\n")
    click.echo(
        f"Mapped {len(rows)} Type CC values to {len(ranges)} live ranges and "
        f"restored slot {recovery_slot} exactly -> {output_path}"
    )


@main.command("probe-microfreak-structured-sentinels-direct")
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("values_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-writes", is_flag=True)
def probe_microfreak_structured_sentinels_direct_command(
    slot: int,
    values_path: str,
    backup_path: str,
    port: str | None,
    i_understand_this_writes: bool,
):
    """Bulk-probe tagged fields, then restore saved and active state exactly."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this temporarily replaces a saved MicroFreak preset; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        values = json.loads(Path(values_path).read_text())
    except Exception as exc:
        raise click.ClickException(f"invalid sentinel JSON: {exc}") from exc
    def valid_sentinel(value):
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return True
        return (
            isinstance(value, dict)
            and set(value) == {"raw_u16"}
            and isinstance(value["raw_u16"], int)
            and not isinstance(value["raw_u16"], bool)
            and 0 <= value["raw_u16"] <= 0xFFFF
        )

    if not isinstance(values, dict) or not all(
        isinstance(name, str) and valid_sentinel(value)
        for name, value in values.items()
    ):
        raise click.ClickException(
            "sentinel JSON must map field names to numeric interpreted values "
            "or {\"raw_u16\": 0..65535}"
        )

    transport = MicroFreakMidiTransport(port_name=port)
    original = None
    target = None
    edits = ()
    baseline = None
    changed = None
    final = None
    target_report = None
    restore_report = None
    target_written = False
    experiment_error: Exception | None = None
    restoration_error: Exception | None = None
    target_backup = Path(backup_path).with_name(
        f"{Path(backup_path).name}.sentinel-target.mfp"
    )
    try:
        original = transport.read_preset(slot)
        target, edits = build_structured_sentinel_preset(original, values)
        transport.select_preset(slot)
        transport.sleep(0.3)
        baseline = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
        target_report = transport.write_preset(slot, target, backup_path)
        target_written = True
        transport.select_preset(slot)
        transport.sleep(0.3)
        changed = {
            word.index: word.raw_u16
            for word in transport.read_live_parameter_words()
        }
    except Exception as exc:
        experiment_error = exc
    finally:
        if target_written and original is not None:
            try:
                restore_report = transport.write_preset(
                    slot, original, target_backup
                )
                transport.select_preset(slot)
                transport.sleep(0.3)
                final = {
                    word.index: word.raw_u16
                    for word in transport.read_live_parameter_words()
                }
            except Exception as exc:
                restoration_error = exc

    if restoration_error is not None:
        raise click.ClickException(
            f"structured sentinel restoration failed: {restoration_error}; "
            f"original backup: {backup_path}"
        ) from restoration_error
    if experiment_error is not None:
        recovered = target_written and final is not None
        raise click.ClickException(
            f"structured sentinel experiment failed; restored={recovered}: "
            f"{experiment_error}"
        ) from experiment_error
    assert original is not None and target is not None
    assert baseline is not None and changed is not None and final is not None
    assert target_report is not None and restore_report is not None
    final_differences = tuple(
        address for address in baseline if baseline[address] != final[address]
    )
    if final_differences:
        raise click.ClickException(
            "saved preset restored but active table differs: "
            + ", ".join(f"0x{address:04x}" for address in final_differences)
        )
    changes = [
        {
            "address": f"0x{address:04x}",
            "before_raw_u16": baseline[address],
            "target_raw_u16": changed[address],
            "restored_raw_u16": final[address],
            "semantic": MICROFREAK_LIVE_WORD_SEMANTICS.get(address),
        }
        for address in baseline
        if baseline[address] != changed[address]
    ]
    click.echo(
        json.dumps(
            {
                "schema_version": "microfreak-structured-sentinel-probe/1",
                "device": "microfreak",
                "slot": slot,
                "preset": original.name,
                "edits": [edit.__dict__ for edit in edits],
                "saved_target_exact_readback": target_report.exact_readback,
                "saved_restore_exact_readback": restore_report.exact_readback,
                "live_changes": changes,
                "live_change_count": len(changes),
                "final_live_differences": [],
                "backup_path": backup_path,
                "target_backup_path": str(target_backup),
            },
            indent=2,
        )
    )


@main.command("push-microfreak")
@click.argument("transport_id", type=int)
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option("--i-understand-this-writes", is_flag=True)
def push_microfreak_command(
    transport_id: int,
    slot: int,
    input_path: str,
    backup_path: str,
    i_understand_this_writes: bool,
):
    """Write lossless shared JSON to one MicroFreak saved-preset slot."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this replaces a saved MicroFreak slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        transport = ElektroidTransport()
        report = transport.write_preset(
            _endpoint(transport, transport_id), slot, preset, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@main.command("push-microfreak-direct")
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option(
    "--select-after-write",
    is_flag=True,
    help="Make the written slot the active live patch after exact readback.",
)
@click.option("--i-understand-this-writes", is_flag=True)
def push_microfreak_direct_command(
    slot: int,
    input_path: str,
    backup_path: str,
    port: str | None,
    select_after_write: bool,
    i_understand_this_writes: bool,
):
    """Guarded MicroFreak saved-preset write without Elektroid or Arturia apps."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this replaces a saved MicroFreak slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        preset = MicroFreakPreset.from_document(document)
        transport = MicroFreakMidiTransport(port_name=port)
        report = transport.write_preset(slot, preset, backup_path)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    result = dict(report.__dict__)
    result["selected_after_write"] = False
    if select_after_write:
        try:
            bank, program = transport.select_preset(slot)
        except Exception as exc:
            raise click.ClickException(
                f"slot {slot} was written and verified, but live selection failed: {exc}"
            ) from exc
        result.update(
            selected_after_write=True,
            midi_bank=bank,
            midi_program=program,
        )
    click.echo(json.dumps(result, indent=2))


@main.command("select-microfreak-direct")
@click.argument("slot", type=click.IntRange(1, 512))
@click.option("--port", default=None, help="Exact paired MicroFreak MIDI port.")
@click.option("--i-understand-this-changes-live-buffer", is_flag=True)
def select_microfreak_direct_command(
    slot: int,
    port: str | None,
    i_understand_this_changes_live_buffer: bool,
):
    """Select a saved MicroFreak slot without touching the hardware controls."""
    if not i_understand_this_changes_live_buffer:
        raise click.ClickException(
            "selection replaces the unsaved active patch; add "
            "--i-understand-this-changes-live-buffer to proceed"
        )
    try:
        bank, program = MicroFreakMidiTransport(port_name=port).select_preset(slot)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(
        json.dumps(
            {
                "device": "microfreak",
                "slot": slot,
                "midi_bank": bank,
                "midi_program": program,
                "selection_sent": True,
                "selection_acknowledged": False,
            },
            indent=2,
        )
    )


@main.command("pull-current")
@click.argument("output_path", type=click.Path())
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema (auto-detected by default).",
)
def pull_current_command(output_path: str, arturia_binary: str | None):
    """Read the active MiniFreak patch directly over USB into shared JSON."""
    try:
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        resource = MiniFreakUsbTransport(codec).read_current_preset()
        document = patch_document_from_resource(resource)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Read current MiniFreak patch: {document.metadata.name} -> {output_path}"
    )


@main.command("pull-minifreak")
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("output_path", type=click.Path())
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema (auto-detected by default).",
)
def pull_minifreak_command(
    slot: int, output_path: str, arturia_binary: str | None
):
    """Read one saved MiniFreak slot directly over USB into shared JSON."""
    try:
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        resource = MiniFreakUsbTransport(codec).read_saved_preset(slot)
        document = patch_document_from_resource(resource)
        document.metadata.source_slot = slot
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(
        f"Read MiniFreak slot {slot}: {document.metadata.name} -> {output_path}"
    )


@main.command("set-minifreak-json")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("parameter", type=click.Choice(tuple(VERIFIED_PARAMETERS)))
@click.argument("value", type=float)
@click.argument("output_path", type=click.Path())
def set_minifreak_json_command(
    input_path: str,
    parameter: str,
    value: float,
    output_path: str,
):
    """Offline-edit one hardware-verified field and regenerate checksum."""
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        update_document_parameter(document, parameter, value)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Set {parameter}={value:g} -> {output_path}")


# ── bulk MiniFreak mapping experiments ───────────────────────────────────

@main.group("sentinel")
def sentinel_group():
    """Generate and analyze coded bulk MiniFreak mapping experiments."""


@sentinel_group.command("generate")
@click.argument("base_mnfx", type=click.Path(exists=True))
@click.argument("output_dir", type=click.Path())
@click.option(
    "--limit",
    type=click.IntRange(1, len(CONTINUOUS_CORE_PARAMETERS)),
    default=None,
    help="Use only the first N continuous-core parameters.",
)
@click.option(
    "--parameter",
    "parameters",
    multiple=True,
    help="Explicit .mnfx parameter; repeat for a custom family.",
)
def sentinel_generate_command(
    base_mnfx: str,
    output_dir: str,
    limit: int | None,
    parameters: tuple[str, ...],
):
    """Create two coded .mnfx shots and their experiment manifest."""
    try:
        selected = parameters or CONTINUOUS_CORE_PARAMETERS
        manifest = generate_sentinel_experiment(
            base_mnfx, output_dir, parameters=selected, limit=limit
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote sentinel experiment: {manifest}")


@sentinel_group.command("analyze")
@click.argument("manifest", type=click.Path(exists=True))
@click.argument("baseline_json", type=click.Path(exists=True))
@click.argument("shot_a_json", type=click.Path(exists=True))
@click.argument("shot_b_json", type=click.Path(exists=True))
@click.option("--capture-a", type=click.Path(exists=True), default=None)
@click.option("--capture-b", type=click.Path(exists=True), default=None)
@click.option("--output", "output_path", type=click.Path(), default=None)
def sentinel_analyze_command(
    manifest: str,
    baseline_json: str,
    shot_a_json: str,
    shot_b_json: str,
    capture_a: str | None,
    capture_b: str | None,
    output_path: str | None,
):
    """Match two coded hardware reads and optional USB captures to .mnfx keys."""
    if bool(capture_a) != bool(capture_b):
        raise click.ClickException("provide both --capture-a and --capture-b")
    try:
        result = analyze_sentinel_experiment(
            manifest,
            baseline_json,
            shot_a_json,
            shot_b_json,
            capture_a=capture_a,
            capture_b=capture_b,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = json.dumps(result, indent=2) + "\n"
    if output_path:
        Path(output_path).write_text(rendered)
        click.echo(f"Wrote sentinel analysis: {output_path}")
    else:
        click.echo(rendered, nl=False)


@sentinel_group.command("collect-corpus")
@click.argument("mnfx_dir", type=click.Path(exists=True, file_okay=False))
@click.argument("output_dir", type=click.Path())
@click.option("--scan-slots", type=click.IntRange(1, 512), default=512)
@click.option("--max-matches", type=click.IntRange(1, 512), default=64)
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema.",
)
def sentinel_collect_corpus_command(
    mnfx_dir: str,
    output_dir: str,
    scan_slots: int,
    max_matches: int,
    arturia_binary: str | None,
):
    """Pair unique .mnfx names with connected MiniFreak slot payloads."""
    try:
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        manifest = collect_named_preset_corpus(
            MiniFreakUsbTransport(codec),
            mnfx_dir,
            output_dir,
            scan_slots=scan_slots,
            max_matches=max_matches,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"Wrote matched MiniFreak corpus: {manifest}")


@sentinel_group.command("analyze-corpus")
@click.argument("manifest", type=click.Path(exists=True))
@click.option(
    "--parameter",
    "parameters",
    multiple=True,
    help="Explicit .mnfx parameter; repeat to restrict the analysis.",
)
@click.option(
    "--all-parameters",
    is_flag=True,
    help="Use the exact-signature index across every common .mnfx parameter.",
)
@click.option("--output", "output_path", type=click.Path(), default=None)
def sentinel_analyze_corpus_command(
    manifest: str,
    parameters: tuple[str, ...],
    all_parameters: bool,
    output_path: str | None,
):
    """Correlate a matched natural-preset corpus with binary offsets."""
    try:
        if all_parameters:
            if parameters:
                raise ValueError("--all-parameters cannot be combined with --parameter")
            result = analyze_named_preset_corpus_exact(manifest)
        else:
            result = analyze_named_preset_corpus(
                manifest,
                parameters=parameters or CONTINUOUS_CORE_PARAMETERS,
            )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = json.dumps(result, indent=2) + "\n"
    if output_path:
        Path(output_path).write_text(rendered)
        click.echo(f"Wrote corpus analysis: {output_path}")
    else:
        click.echo(rendered, nl=False)


@sentinel_group.command("verify-session-map")
@click.argument("backup_path", type=click.Path())
@click.option(
    "--parameter",
    "parameters",
    multiple=True,
    type=click.Choice(tuple(VERIFIED_PARAMETERS)),
    help="Mapped JSON key; repeat to restrict the probe (all by default).",
)
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema.",
)
@click.option(
    "--i-understand-this-writes",
    is_flag=True,
    help="Required: briefly changes mapped live fields and restores them exactly.",
)
def sentinel_verify_session_map_command(
    backup_path: str,
    parameters: tuple[str, ...],
    arturia_binary: str | None,
    i_understand_this_writes: bool,
):
    """Verify many MiniFreak session IDs in one coded, restored shot."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this briefly changes the active MiniFreak sound; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        report = MiniFreakUsbTransport(codec).verify_session_parameter_map(
            parameters
            or tuple(
                key
                for key, spec in VERIFIED_PARAMETERS.items()
                if spec.session_parameter_id is not None
            ),
            backup_path,
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = {
        **report.__dict__,
        "backup_path": str(report.backup_path),
    }
    click.echo(json.dumps(rendered, indent=2))


@main.command("push-current")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema (auto-detected by default).",
)
@click.option(
    "--i-understand-this-writes",
    is_flag=True,
    help="Required: changes the active MiniFreak sound; it does not save a slot.",
)
def push_current_command(
    input_path: str,
    backup_path: str,
    arturia_binary: str | None,
    i_understand_this_writes: bool,
):
    """Apply hardware-verified changes from shared JSON to the active MiniFreak."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this changes the active MiniFreak sound; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        if document.device != DeviceModel.MINIFREAK:
            raise ValueError("push-current requires a MiniFreak JSON document")
        if document.minifreak is None or document.minifreak.hardware is None:
            raise ValueError(
                "push-current requires lossless hardware JSON from pull-current"
            )
        target = base64.b64decode(
            document.minifreak.hardware.raw_payload_base64, validate=True
        )
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        report = MiniFreakUsbTransport(codec).write_active_payload(
            target, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = {
        **report.__dict__,
        "backup_path": str(report.backup_path),
        "persistence": "active-buffer-only; save on the hardware to retain it",
    }
    click.echo(json.dumps(rendered, indent=2))


@main.command("push-slot")
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("slot", type=click.IntRange(1, 512))
@click.argument("backup_path", type=click.Path())
@click.option(
    "--arturia-binary",
    type=click.Path(exists=True),
    default=None,
    help="MiniFreak V binary containing the Collage schema (auto-detected by default).",
)
@click.option(
    "--i-understand-this-writes",
    is_flag=True,
    help="Required: persistently overwrites an occupied MiniFreak slot.",
)
def push_slot_command(
    input_path: str,
    slot: int,
    backup_path: str,
    arturia_binary: str | None,
    i_understand_this_writes: bool,
):
    """Write mapped JSON changes to an occupied saved MiniFreak slot."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this persistently overwrites a saved MiniFreak slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        document = PatchDocument.model_validate_json(Path(input_path).read_text())
        if document.device != DeviceModel.MINIFREAK:
            raise ValueError("push-slot requires a MiniFreak JSON document")
        if document.minifreak is None or document.minifreak.hardware is None:
            raise ValueError(
                "push-slot requires lossless hardware JSON from pull-minifreak"
            )
        target = base64.b64decode(
            document.minifreak.hardware.raw_payload_base64, validate=True
        )
        binary = Path(arturia_binary) if arturia_binary else find_arturia_binary()
        codec = CollageCodec.from_arturia_binary(binary)
        report = MiniFreakUsbTransport(codec).write_saved_payload(
            slot, target, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = {**report.__dict__, "backup_path": str(report.backup_path)}
    click.echo(json.dumps(rendered, indent=2))


# ── passive MiniFreak USB capture ─────────────────────────────────────────

@main.group("capture")
def capture_group():
    """Decode passive MiniFreak V USB captures."""


@capture_group.command("analyze")
@click.argument("capture_path", type=click.Path(exists=True))
@click.option(
    "--arturia-binary",
    required=True,
    type=click.Path(exists=True),
    help="Installed MiniFreak V executable or plug-in containing Collage schemas.",
)
@click.option("--output", "output_path", type=click.Path())
@click.option("--extract-resources", type=click.Path())
def capture_analyze(
    capture_path: str,
    arturia_binary: str,
    output_path: str | None,
    extract_resources: str | None,
):
    """Decode Collage operations and current parameter values from a log."""
    try:
        codec = CollageCodec.from_arturia_binary(arturia_binary)
        result = summarize_capture(capture_path, codec).to_dict()
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    rendered = json.dumps(result, indent=2) + "\n"
    if output_path:
        Path(output_path).write_text(rendered)
        click.echo(f"Wrote decoded Collage capture: {output_path}")
    else:
        click.echo(rendered, nl=False)
    if extract_resources:
        directory = Path(extract_resources)
        directory.mkdir(parents=True, exist_ok=True)
        for resource in extract_retrieved_resources(capture_path, codec):
            name = resource.name.hex() or "unnamed"
            destination = directory / (
                f"{resource.location.lower()}-{name}-{resource.message_id}.bin"
            )
            destination.write_bytes(resource.data)
            click.echo(f"Extracted resource: {destination}")


@capture_group.command("current-patch")
@click.argument("capture_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
@click.option(
    "--arturia-binary",
    required=True,
    type=click.Path(exists=True),
    help="Installed MiniFreak V executable or plug-in containing Collage schemas.",
)
def capture_current_patch(
    capture_path: str, output_path: str, arturia_binary: str
):
    """Convert a captured current MiniFreak preset into shared lossless JSON."""
    try:
        codec = CollageCodec.from_arturia_binary(arturia_binary)
        document = patch_document_from_capture(capture_path, codec)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    Path(output_path).write_text(
        document.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    click.echo(f"Wrote captured MiniFreak patch JSON: {output_path}")


# ── wavetable ─────────────────────────────────────────────────────────────

@main.group("wavetable")
def wavetable_group():
    """Inspect and prepare device-specific wavetables."""


@wavetable_group.command("list")
@click.argument("transport_id", type=int)
@click.option("--json", "json_output", is_flag=True)
def wavetable_list(transport_id: int, json_output: bool):
    """List MicroFreak wavetable slots without changing the device."""
    transport = ElektroidTransport()
    endpoint = _endpoint(transport, transport_id)
    items = transport.list_wavetables(endpoint)
    rows = [item.__dict__ for item in items]
    if json_output:
        click.echo(json.dumps(rows, indent=2))
    else:
        for item in items:
            click.echo(f"{item.slot:02d}  {item.size or 0:5d}  {item.name}")


@wavetable_group.command("pull")
@click.argument("transport_id", type=int)
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("output_path", type=click.Path())
def wavetable_pull(transport_id: int, slot: int, output_path: str):
    """Read a MicroFreak wavetable into a lossless JSON document."""
    transport = ElektroidTransport()
    endpoint = _endpoint(transport, transport_id)
    table = transport.read_wavetable(endpoint, slot)
    Path(output_path).write_text(json.dumps(table.to_document().to_dict(), indent=2) + "\n")
    click.echo(f"Read MicroFreak wavetable {slot}: {table.name} -> {output_path}")


@wavetable_group.command("push")
@click.argument("transport_id", type=int)
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("backup_path", type=click.Path())
@click.option("--i-understand-this-writes", is_flag=True)
def wavetable_push(
    transport_id: int,
    slot: int,
    input_path: str,
    backup_path: str,
    i_understand_this_writes: bool,
):
    """Upload a MicroFreak .mfw or lossless wavetable JSON document."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this replaces a MicroFreak wavetable slot; add "
            "--i-understand-this-writes to proceed"
        )
    try:
        source = Path(input_path)
        if source.suffix.lower() in {".mfw", ".mfwz"}:
            table = MicroFreakWavetable.from_mfw(source.read_bytes())
        else:
            table = MicroFreakWavetable.from_document(json.loads(source.read_text()))
        transport = ElektroidTransport()
        report = transport.write_wavetable(
            _endpoint(transport, transport_id), slot, table, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


@wavetable_group.command("prepare")
@click.argument("device", type=click.Choice([item.value for item in DeviceModel]))
@click.argument("input_path", type=click.Path(exists=True))
@click.argument("output_path", type=click.Path())
@click.option("--name", default=None)
def wavetable_prepare(device: str, input_path: str, output_path: str,
                      name: str | None):
    """Validate and package a wavetable offline; this does not upload it."""
    model = DeviceModel(device)
    if model == DeviceModel.MICROFREAK:
        table = MicroFreakWavetable.from_wav(input_path, name=name)
        output = Path(output_path)
        output.write_bytes(
            table.to_mfwz() if output.suffix.lower() == ".mfwz" else table.to_mfw()
        )
        click.echo(f"Prepared MicroFreak {output.suffix}: {output_path}")
    else:
        document = validate_minifreak_raw(Path(input_path).read_bytes())
        if name:
            document.name = name
        Path(output_path).write_text(json.dumps(document.to_dict(), indent=2) + "\n")
        click.echo(f"Validated MiniFreak raw wavetable: {output_path}")


@wavetable_group.command("verify-transport")
@click.argument("transport_id", type=int)
@click.argument("slot", type=click.IntRange(1, 16))
@click.argument("backup_path", type=click.Path())
@click.option(
    "--i-understand-this-writes",
    is_flag=True,
    help="Required: writes the fresh backup back to the same slot, verifies, and restores.",
)
def wavetable_verify_transport(
    transport_id: int,
    slot: int,
    backup_path: str,
    i_understand_this_writes: bool,
):
    """Probe MicroFreak upload with identical content and verified restoration."""
    if not i_understand_this_writes:
        raise click.ClickException(
            "this guarded probe performs a same-content write; add "
            "--i-understand-this-writes to proceed"
        )
    transport = ElektroidTransport()
    endpoint = _endpoint(transport, transport_id)
    try:
        report = transport.verify_wavetable_write_transport(
            endpoint, slot, backup_path
        )
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(json.dumps(report.__dict__, indent=2))


if __name__ == "__main__":
    main()
