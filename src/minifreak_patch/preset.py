"""MiniFreak preset representation and serialization."""

from __future__ import annotations

import copy
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from minifreak_patch.constants import (
    ASSIGNABLE_COLS, HARDWIRED_COLS, MOD_DEST_NONE,
    ArpMode, ArpOct, CycEnvMode, CycEnvRetrigSrc, CycEnvStageOrder,
    FilterMode, FxAlgorithm, LfoRetrigMode, LfoRateSync, LfoSyncFilter,
    LfoWaveform, ModCluster, ModSource, NoteMode, PolyAlloc, PolySteal,
    RetrigMode, SeqMode, SeqTimeDiv, TuneModQuantize, UnisonCount,
    UnisonMode, VeloAtMode,
    encode_mod_dest, fx_opt1_label,
)
from minifreak_patch.parser import (
    PresetHeader, extract_mnfx_text, parse_header, parse_parameters,
)
from minifreak_patch.zipwriter import create_zip


@dataclass
class ParamDiff:
    name: str
    value_a: Optional[float]
    value_b: Optional[float]


@dataclass
class MiniFreakPreset:
    """A parsed MiniFreak preset."""

    name: str = "Init"
    pack: str = "User"
    author: str = "User"
    original_author: str = "Unknown"
    description: str = ""
    timestamp: Optional[int] = None
    firmware_version: Optional[str] = None
    preset_type: Optional[str] = None
    subtype: Optional[str] = None
    metadata: dict[str, str] = field(default_factory=dict)
    params: dict[str, float] = field(default_factory=dict)

    # ── Loading ────────────────────────────────────────────────────────

    @classmethod
    def from_bytes(cls, data: bytes) -> "MiniFreakPreset":
        text = extract_mnfx_text(data)
        return cls.from_text(text)

    @classmethod
    def from_text(cls, text: str) -> "MiniFreakPreset":
        header, params_offset = parse_header(text)
        params_list = (
            parse_parameters(text[params_offset:], header.param_count)
            if header.param_count > 0
            else []
        )

        preset_type = None
        subtype = None
        metadata: dict[str, str] = {}

        for key, value in header.metadata:
            if key == "Type":
                preset_type = value
            elif key == "Subtype":
                subtype = value
            else:
                metadata[key] = value

        return cls(
            name=header.name,
            pack=header.pack,
            author=header.author,
            original_author=header.original_author,
            description=header.description,
            timestamp=header.timestamp,
            firmware_version=header.firmware_version,
            preset_type=preset_type,
            subtype=subtype,
            metadata=metadata,
            params=dict(params_list),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> "MiniFreakPreset":
        data = Path(path).read_bytes()
        return cls.from_bytes(data)

    # ── Serialization ──────────────────────────────────────────────────

    def to_mnfx(self) -> str:
        """Serialize the preset to Boost.Serialization text archive format."""
        parts: list[str] = []

        # Archive header
        parts.append("22 serialization::archive 10 0 7 0 7 ")

        # Preset name
        _write_lstr(parts, self.name)
        parts.append(" ")

        # Pack
        _write_lstr(parts, self.pack)
        parts.append(" ")

        # Class info marker + author
        parts.append("66 ")
        _write_lstr(parts, self.author)
        parts.append(" ")

        # Original author
        _write_lstr(parts, self.original_author)
        parts.append(" ")

        # Export vs factory format
        if self.timestamp is not None and self.firmware_version is not None:
            # Exported format
            parts.append("0 0 0 0 0 1 ")
            _write_lstr(parts, self.description)
            parts.append(f" {self.timestamp} ")
            _write_lstr(parts, self.firmware_version)
            parts.append(" 0 0 0 0 0 0 0 0 0 0 ")
        else:
            # Factory format
            parts.append("0 0 0 0 0 0 ")
            _write_lstr(parts, self.description)
            parts.append("  0 0  0 0 0 0 -1 0 0 0  0 0 ")

        # Build metadata list (Type and Subtype included)
        all_metadata: list[tuple[str, str]] = []
        for k, v in sorted(self.metadata.items()):
            all_metadata.append((k, v))
        if self.subtype is not None:
            all_metadata.append(("Subtype", self.subtype))
        if self.preset_type is not None:
            all_metadata.append(("Type", self.preset_type))

        parts.append(f"{len(all_metadata)} 0 0 0 ")
        for key, value in all_metadata:
            _write_lstr(parts, key)
            parts.append(" ")
            _write_lstr(parts, value)
            parts.append(" ")

        # Trailing header
        parts.append("0 0 0 7 0 0 0 0 0 0 ")

        # Parameter count
        parts.append(f"{len(self.params)} 0 0 0 ")

        # Parameters (sorted by name for deterministic output)
        for name in sorted(self.params):
            value = self.params[name]
            _write_lstr(parts, name)
            parts.append(" ")
            # Integer format for whole numbers, float otherwise
            if value == int(value) and -(2**63) <= value < 2**63:
                parts.append(f"{int(value)} ")
            else:
                parts.append(f"{value} ")

        # End marker
        parts.append("0 0\n")

        return "".join(parts)

    def to_zip(self) -> bytes:
        """Export preset as a ZIP 1.0 archive for MiniFreak V import."""
        preset = copy.deepcopy(self)
        if preset.timestamp is None:
            preset.timestamp = int(time.time())
        if preset.firmware_version is None:
            preset.firmware_version = "4.0.2.6369"

        mnfx_content = preset.to_mnfx().encode("utf-8")
        path = f"MiniFreak/User/{preset.pack}/{preset.name}"
        return create_zip([(path, mnfx_content)])

    def write_zip(self, path: str | Path) -> None:
        """Write preset as a ZIP file to disk."""
        Path(path).write_bytes(self.to_zip())

    def to_document(self, recipe: dict | None = None):
        """Convert this preset to the shared lossless JSON document."""
        from minifreak_patch.schema import (
            DeviceModel,
            MiniFreakPatchData,
            PatchDocument,
            PatchMetadata,
        )

        return PatchDocument(
            device=DeviceModel.MINIFREAK,
            metadata=PatchMetadata(
                name=self.name,
                author=self.author,
                description=self.description or None,
                category=self.preset_type,
                subtype=self.subtype,
                firmware=self.firmware_version,
            ),
            minifreak=MiniFreakPatchData(
                pack=self.pack,
                original_author=self.original_author,
                timestamp=self.timestamp,
                metadata=dict(self.metadata),
                parameters=dict(self.params),
                recipe=recipe,
            ),
        )

    @classmethod
    def from_document(cls, document):
        """Build a MiniFreak preset from the shared JSON document."""
        from minifreak_patch.schema import DeviceModel

        if document.device != DeviceModel.MINIFREAK or document.minifreak is None:
            raise ValueError("not a MiniFreak patch document")
        block = document.minifreak
        return cls(
            name=document.metadata.name,
            pack=block.pack,
            author=document.metadata.author or "User",
            original_author=block.original_author,
            description=document.metadata.description or "",
            timestamp=block.timestamp,
            firmware_version=document.metadata.firmware,
            preset_type=document.metadata.category,
            subtype=document.metadata.subtype,
            metadata=dict(block.metadata),
            params=dict(block.parameters),
        )

    # ── Parameter Access ───────────────────────────────────────────────

    def get_param(self, name: str) -> Optional[float]:
        return self.params.get(name)

    def set_param(self, name: str, value: float) -> None:
        self.params[name] = value

    def params_with_prefix(self, prefix: str) -> list[tuple[str, float]]:
        return [(k, v) for k, v in self.params.items() if k.startswith(prefix)]

    # ── Typed Getters/Setters ──────────────────────────────────────────

    def set_osc1_engine(self, engine: Osc1Engine) -> None:
        from minifreak_patch.constants import Osc1Engine as _  # noqa: already imported
        self.set_param("Osc1_Type", engine.to_value())

    def get_osc1_engine(self) -> Optional[Osc1Engine]:
        from minifreak_patch.constants import Osc1Engine
        v = self.get_param("Osc1_Type")
        return Osc1Engine.from_value(v) if v is not None else None

    def set_osc2_engine(self, engine: Osc2Engine) -> None:
        from minifreak_patch.constants import Osc2Engine as _  # noqa
        self.set_param("Osc2_Type", engine.to_value())

    def get_osc2_engine(self) -> Optional[Osc2Engine]:
        from minifreak_patch.constants import Osc2Engine
        v = self.get_param("Osc2_Type")
        return Osc2Engine.from_value(v) if v is not None else None

    def set_fx_algorithm(self, slot: int, algo: FxAlgorithm) -> None:
        self.set_param(f"FX{slot}_Type", algo.to_value())

    def get_fx_algorithm(self, slot: int) -> Optional[FxAlgorithm]:
        v = self.get_param(f"FX{slot}_Type")
        return FxAlgorithm.from_value(v) if v is not None else None

    def get_fx_opt1_label(self, slot: int) -> Optional[str]:
        algo = self.get_fx_algorithm(slot)
        if algo is None:
            return None
        v = self.get_param(f"FX{slot}_Opt1")
        return fx_opt1_label(algo, v) if v is not None else None

    def set_filter_mode(self, mode: FilterMode) -> None:
        self.set_param("Vcf_Type", mode.to_value())

    def get_filter_mode(self) -> Optional[FilterMode]:
        v = self.get_param("Vcf_Type")
        return FilterMode.from_value(v) if v is not None else None

    def set_lfo_waveform(self, lfo: int, wave: LfoWaveform) -> None:
        self.set_param(f"LFO{lfo}_Wave", wave.to_value())

    def get_lfo_waveform(self, lfo: int) -> Optional[LfoWaveform]:
        v = self.get_param(f"LFO{lfo}_Wave")
        return LfoWaveform.from_value(v) if v is not None else None

    def set_tune_mod_quantize(self, osc: int, q: TuneModQuantize) -> None:
        self.set_param(f"Osc{osc}_TuneModQuantize", q.to_value())

    def set_note_mode(self, mode: NoteMode) -> None:
        self.set_param("Gen_NoteMode", mode.to_value())

    def get_note_mode(self) -> Optional[NoteMode]:
        v = self.get_param("Gen_NoteMode")
        return NoteMode.from_value(v) if v is not None else None

    def set_unison_count(self, count: UnisonCount) -> None:
        self.set_param("Gen_UnisonCount", count.to_value())

    def set_poly_alloc(self, mode: PolyAlloc) -> None:
        self.set_param("Gen_PolyAlloc", mode.to_value())

    def set_poly_steal(self, mode: PolySteal) -> None:
        self.set_param("Gen_PolySteal", mode.to_value())

    def set_unison_mode(self, mode: UnisonMode) -> None:
        self.set_param("Gen_UnisonMode", mode.to_value())

    def set_retrig_mode(self, mode: RetrigMode) -> None:
        self.set_param("Gen_RetrigMode", mode.to_value())

    def set_seq_mode(self, mode: SeqMode) -> None:
        self.set_param("Seq_Mode", mode.to_value())

    def get_seq_mode(self) -> Optional[SeqMode]:
        v = self.get_param("Seq_Mode")
        return SeqMode.from_value(v) if v is not None else None

    def set_arp_mode(self, mode: ArpMode) -> None:
        self.set_param("Arp_Mode", mode.to_value())

    def set_arp_oct(self, oct: ArpOct) -> None:
        self.set_param("Arp_Oct", oct.to_value())

    def set_cycenv_mode(self, mode: CycEnvMode) -> None:
        self.set_param("CycEnv_Mode", mode.to_value())

    def set_cycenv_retrig_src(self, src: CycEnvRetrigSrc) -> None:
        self.set_param("CycEnv_RetrigSrc", src.to_value())

    def set_cycenv_stage_order(self, order: CycEnvStageOrder) -> None:
        self.set_param("CycEnv_StageOrder", order.to_value())

    def set_lfo_retrig(self, lfo: int, mode: LfoRetrigMode) -> None:
        self.set_param(f"LFO{lfo}_Retrig", mode.to_value())

    def set_lfo_rate_sync(self, lfo: int, div: LfoRateSync) -> None:
        self.set_param(f"LFO{lfo}_RateSync", div.to_value())

    def set_lfo_sync_filter(self, lfo: int, filt: LfoSyncFilter) -> None:
        self.set_param(f"LFO{lfo}_SyncFilter", filt.to_value())

    def set_velo_at_mode(self, mode: VeloAtMode) -> None:
        self.set_param("Mx_VeloAt", mode.to_value())

    # ── Mod Matrix Helpers ─────────────────────────────────────────────

    def set_mod_dest(self, col: int, cluster: ModCluster, offset: int) -> None:
        """Set an assignable mod matrix destination column (col 0-8)."""
        name = f"Mx_ColId_{col}" if col < 8 else "Mx_ColId_Last"
        self.set_param(name, encode_mod_dest(cluster, offset))

    def set_mod_amount(self, source: ModSource, col: int, amount: float) -> None:
        """Set a mod matrix amount.

        For hardwired destinations (col 0-3) uses Mx_Dot_*.
        For assignable destinations (col 4-12) uses Mx_AssignDot_*.
        Amount is bipolar: 0.5=center, 0.0=-100%, 1.0=+100%.
        """
        row = source.value
        if col < HARDWIRED_COLS:
            idx = row * HARDWIRED_COLS + col
            name = f"Mx_Dot_{idx}" if idx < 27 else "Mx_Dot_Last"
        else:
            assign_col = col - HARDWIRED_COLS
            idx = row * ASSIGNABLE_COLS + assign_col
            name = f"Mx_AssignDot_{idx}" if idx < 62 else "Mx_AssignDot_Last"
        self.set_param(name, amount)

    def clear_mod_matrix(self) -> None:
        """Clear the entire mod matrix."""
        for i in range(27):
            self.set_param(f"Mx_Dot_{i}", 0.5)
        self.set_param("Mx_Dot_Last", 0.5)

        for i in range(62):
            self.set_param(f"Mx_AssignDot_{i}", 0.5)
        self.set_param("Mx_AssignDot_Last", 0.5)

        for i in range(8):
            self.set_param(f"Mx_ColId_{i}", MOD_DEST_NONE)
        self.set_param("Mx_ColId_Last", MOD_DEST_NONE)

    def set_macro_dest(self, macro_id: int, slot: int,
                       cluster: ModCluster, offset: int) -> None:
        name = (f"Macro{macro_id}_Dest_{slot}" if slot < 3
                else f"Macro{macro_id}_Dest_Last")
        self.set_param(name, encode_mod_dest(cluster, offset))

    def set_macro_amount(self, macro_id: int, slot: int, amount: float) -> None:
        name = (f"Macro{macro_id}_Amount_{slot}" if slot < 3
                else f"Macro{macro_id}_Amount_Last")
        self.set_param(name, amount)

    def clear_macros(self) -> None:
        """Clear both macros."""
        for macro_id in (1, 2):
            for slot in range(3):
                self.set_param(f"Macro{macro_id}_Dest_{slot}", MOD_DEST_NONE)
                self.set_param(f"Macro{macro_id}_Amount_{slot}", 0.5)
            self.set_param(f"Macro{macro_id}_Dest_Last", MOD_DEST_NONE)
            self.set_param(f"Macro{macro_id}_Amount_Last", 0.5)
            self.set_param(f"Macro{macro_id}_Value", 0.5)

    # ── Sequence Helpers ───────────────────────────────────────────────

    def set_step_pitch(self, step: int, voice: int, midi_note: int) -> None:
        self.set_param(f"Pitch_S{step}_I{voice}", midi_note / 128.0)

    def clear_step_pitch(self, step: int, voice: int) -> None:
        self.set_param(f"Pitch_S{step}_I{voice}", 1.0)

    def set_step_velocity(self, step: int, voice: int, velocity: int) -> None:
        self.set_param(f"Velo_S{step}_I{voice}", velocity / 127.0)

    def set_step_length(self, step: int, voice: int, length: float) -> None:
        self.set_param(f"Length_S{step}_I{voice}", length / 127.0)

    def set_step_state(self, step: int, active: bool) -> None:
        self.set_param(f"StepState_S{step}", 1.0 if active else 0.0)

    def set_step_gate(self, step: int, gate: float) -> None:
        self.set_param(f"Gate_S{step}", gate)

    def set_step_mod(self, step: int, lane: int, value: float) -> None:
        self.set_param(f"Mod_S{step}_I{lane}", value)

    def set_step_mod_state(self, step: int, active: bool) -> None:
        self.set_param(f"ModState_S{step}", 1.0 if active else 0.0)

    def set_tempo_bpm(self, bpm: float) -> None:
        self.set_param("Tempo", (bpm - 30.0) / 210.0)

    def set_seq_time_div(self, div: SeqTimeDiv) -> None:
        self.set_param("Seq_TimeDiv", div.to_value())

    def set_seq_gate(self, gate: float) -> None:
        self.set_param("Seq_Gate", gate)

    def set_seq_swing(self, swing: float) -> None:
        self.set_param("Seq_Swing", swing)

    def set_seq_length(self, length: int) -> None:
        """Set sequence length (1-64 steps)."""
        length = max(1, min(64, length))
        self.set_param("Seq_Length", (length - 1) / 63.0)

    def clear_sequence(self) -> None:
        """Clear the entire sequence (64 steps x 6 voices)."""
        for step in range(64):
            self.set_step_state(step, False)
            self.set_step_gate(step, 0.5)
            self.set_step_mod_state(step, False)
            for voice in range(6):
                self.clear_step_pitch(step, voice)
                self.set_step_velocity(step, voice, 100)
                self.set_step_length(step, voice, 0.0)
            for lane in range(4):
                self.set_step_mod(step, lane, 0.5)

    # ── Diff ───────────────────────────────────────────────────────────

    def diff(self, other: "MiniFreakPreset") -> list[ParamDiff]:
        """Compare with another preset, returning differing parameters."""
        diffs: list[ParamDiff] = []

        for name, val_a in self.params.items():
            val_b = other.params.get(name)
            if val_b is None:
                diffs.append(ParamDiff(name, val_a, None))
            elif abs(val_a - val_b) > 1e-10:
                diffs.append(ParamDiff(name, val_a, val_b))

        for name, val_b in other.params.items():
            if name not in self.params:
                diffs.append(ParamDiff(name, None, val_b))

        diffs.sort(key=lambda d: d.name)
        return diffs


def _write_lstr(parts: list[str], s: str) -> None:
    """Append a length-prefixed string to the parts list."""
    parts.append(f"{len(s)} {s}")


# ── Sanitize Default Base ──────────────────────────────────────────────────

def sanitize_default_base(preset: MiniFreakPreset) -> MiniFreakPreset:
    """Reset a base preset to neutral defaults for recipe building.

    This clears the mod matrix, macros, sequence, and sets all
    sound parameters to safe starting values.
    """
    p = copy.deepcopy(preset)

    p.clear_mod_matrix()
    p.clear_macros()
    p.clear_sequence()

    # Seq mode off
    p.set_seq_mode(SeqMode.OFF)

    # Voice: Poly, no glide, no legato
    p.set_note_mode(NoteMode.POLY)
    p.set_param("Gen_Glide", 0.0)
    p.set_param("Gen_LegatoMode", 0.0)

    # Osc1: BasicWaves, centered params, volume 0.8
    p.set_param("Osc1_Type", 0.0)
    for param in ("Osc1_Wave", "Osc1_Timbre", "Osc1_Shape",
                   "Osc1_CoarseTune", "Osc1_FineTune"):
        p.set_param(param, 0.5)
    p.set_param("Osc1_Volume", 0.8)

    # Osc2: BasicWaves, centered params, volume 0.0 (silent)
    p.set_param("Osc2_Type", 0.0)
    for param in ("Osc2_Wave", "Osc2_Timbre", "Osc2_Shape",
                   "Osc2_CoarseTune", "Osc2_FineTune"):
        p.set_param(param, 0.5)
    p.set_param("Osc2_Volume", 0.0)

    # Filter: LPF, open cutoff, no resonance, no env amount
    p.set_filter_mode(FilterMode.LOW_PASS)
    p.set_param("Vcf_Cutoff", 0.8)
    p.set_param("Vcf_Resonance", 0.0)
    p.set_param("Vcf_EnvAmount", 0.0)

    # Envelope: quick attack, moderate decay/release, full sustain
    p.set_param("Env_Attack", 0.0)
    p.set_param("Env_Decay", 0.3)
    p.set_param("Env_Sustain", 1.0)
    p.set_param("Env_Release", 0.3)

    # FX: all disabled
    for slot in (1, 2, 3):
        p.set_param(f"FX{slot}_Enable", 0.0)
        p.set_param(f"FX{slot}_Type", 0.0)
        for sub in ("Opt1", "Time", "Intensity", "Amount"):
            p.set_param(f"FX{slot}_{sub}", 0.5)

    # Volume
    p.set_param("Preset_Volume", 0.8)

    # Seq automation destinations → none
    for lane in range(4):
        for sfx in ("Dest", "Set", "Smooth", "Val"):
            name = (f"Seq_Automation{sfx}_{lane}" if lane < 3
                    else f"Seq_Automation{sfx}_Last")
            if sfx == "Dest":
                p.set_param(name, MOD_DEST_NONE)
            else:
                p.set_param(name, 0.0)

    # Seq params
    p.set_seq_time_div(SeqTimeDiv.SIXTEENTH)
    p.set_seq_gate(0.5)
    p.set_seq_swing(0.0)

    return p
