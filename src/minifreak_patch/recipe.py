"""JSON recipe models and build pipeline for MiniFreak presets.

A recipe is a compact JSON file (~50-100 fields) that describes a preset's
sound design intent. The build() method expands it against a base preset
(~2485 parameters) to produce a complete MiniFreakPreset.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from minifreak_patch.constants import (
    ASSIGNABLE_COLS, HARDWIRED_COLS, MOD_DEST_NONE,
    ArpMode, ArpOct, CycEnvMode, CycEnvRetrigSrc, CycEnvStageOrder,
    FilterMode, FxAlgorithm, LfoRetrigMode, LfoRateSync, LfoSyncFilter,
    LfoWaveform, ModCluster, ModSource, NoteMode, Osc1Engine, Osc2Engine,
    PolyAlloc, PolySteal, RetrigMode, SeqMode, SeqTimeDiv,
    TuneModQuantize, UnisonCount, UnisonMode, VeloAtMode,
    DEST_PITCH1, DEST_PITCH2, DEST_OSC1_WAVE, DEST_OSC1_TIMBRE, DEST_CUTOFF,
    encode_mod_dest, fx_opt1_from_name, mod_dest_from_name, parse_note_name,
)
from minifreak_patch.preset import MiniFreakPreset

import copy


# ── Pydantic Models ────────────────────────────────────────────────────────

class VoiceConfig(BaseModel):
    mode: Optional[str] = None
    glide: Optional[float] = None
    unison_voices: Optional[int] = None
    unison_mode: Optional[str] = None
    alloc: Optional[str] = None
    steal: Optional[str] = None
    retrig: Optional[str] = None
    legato: Optional[bool] = None


class OscConfig(BaseModel):
    engine: Optional[str] = None
    wave: Optional[float] = None
    timbre: Optional[float] = None
    shape: Optional[float] = None
    volume: Optional[float] = None
    tune: Optional[float] = None
    fine_tune: Optional[float] = None
    mod_quantize: Optional[str] = None


class FilterConfig(BaseModel):
    mode: Optional[str] = None
    cutoff: Optional[float] = None
    resonance: Optional[float] = None
    env_amount: Optional[float] = None


class EnvelopeConfig(BaseModel):
    attack: Optional[float] = None
    decay: Optional[float] = None
    sustain: Optional[float] = None
    release: Optional[float] = None
    attack_curve: Optional[float] = None
    decay_curve: Optional[float] = None
    release_curve: Optional[float] = None


class LfoConfig(BaseModel):
    rate: Optional[float] = None
    wave: Optional[str] = None
    sync: Optional[bool] = None
    rate_sync: Optional[str] = None
    retrig: Optional[str] = None
    sync_filter: Optional[str] = None


class CyclingEnvConfig(BaseModel):
    rise: Optional[float] = None
    fall: Optional[float] = None
    hold: Optional[float] = None
    mode: Optional[str] = None
    stage_order: Optional[str] = None
    retrig: Optional[str] = None
    rise_curve: Optional[float] = None
    fall_curve: Optional[float] = None


class FxConfig(BaseModel):
    algo: str
    opt1: Optional[str] = None
    time: Optional[float] = None
    intensity: Optional[float] = None
    amount: Optional[float] = None


class ModRoute(BaseModel):
    src: str
    dest: str
    amount: str


class MacroDest(BaseModel):
    dest: str
    amount: str


class MacroConfig(BaseModel):
    dests: list[MacroDest] = Field(default_factory=list)


class MacrosConfig(BaseModel):
    macro1: Optional[MacroConfig] = None
    macro2: Optional[MacroConfig] = None


class StepConfig(BaseModel):
    step: int
    notes: list[str] = Field(default_factory=list)
    vel: Optional[int] = None
    gate: Optional[float] = None
    mods: list[float] = Field(default_factory=list)


class ArpConfig(BaseModel):
    mode: Optional[str] = None
    octaves: Optional[int] = None
    gate: Optional[float] = None
    spice: Optional[float] = None


class SequenceConfig(BaseModel):
    mode: Optional[str] = None
    length: Optional[int] = None
    tempo: Optional[float] = None
    time_div: Optional[str] = None
    swing: Optional[float] = None
    gate: Optional[float] = None
    lane_dests: list[str] = Field(default_factory=list)
    steps: list[StepConfig] = Field(default_factory=list)


class Recipe(BaseModel):
    name: str
    description: Optional[str] = None
    type: Optional[str] = Field(None, alias="type")
    subtype: Optional[str] = None
    author: Optional[str] = None
    voice: Optional[VoiceConfig] = None
    osc1: Optional[OscConfig] = None
    osc2: Optional[OscConfig] = None
    filter: Optional[FilterConfig] = None
    envelope: Optional[EnvelopeConfig] = None
    lfo1: Optional[LfoConfig] = None
    lfo2: Optional[LfoConfig] = None
    cycling_env: Optional[CyclingEnvConfig] = None
    fx: Optional[list[Optional[FxConfig]]] = None
    mod: Optional[list[ModRoute]] = None
    macros: Optional[MacrosConfig] = None
    sequence: Optional[SequenceConfig] = None
    arp: Optional[ArpConfig] = None
    volume: Optional[float] = None
    velo_at: Optional[str] = None
    raw_params: Optional[dict[str, float]] = None

    model_config = {"populate_by_name": True}

    # ── Build ──────────────────────────────────────────────────────────

    def build(self, base: MiniFreakPreset) -> MiniFreakPreset:
        """Build a complete preset by applying this recipe to a base preset."""
        preset = copy.deepcopy(base)

        # 1. Apply defaults for sections this recipe defines
        self._apply_defaults(preset)

        # 2. Metadata
        preset.name = self.name
        if self.description is not None:
            preset.description = self.description
        if self.type is not None:
            preset.preset_type = self.type
        if self.subtype is not None:
            preset.subtype = self.subtype
        if self.author is not None:
            preset.author = self.author
        if self.volume is not None:
            preset.set_param("Preset_Volume", self.volume)

        # 3. Voice
        if self.voice is not None:
            self._apply_voice(preset, self.voice)

        # 4. Oscillators
        if self.osc1 is not None:
            self._apply_osc(preset, 1, self.osc1)
        if self.osc2 is not None:
            self._apply_osc(preset, 2, self.osc2)

        # 5. Filter
        if self.filter is not None:
            f = self.filter
            if f.mode is not None:
                m = FilterMode.from_name(f.mode)
                if m is None:
                    raise ValueError(f"unknown filter mode: {f.mode!r}")
                preset.set_filter_mode(m)
            if f.cutoff is not None:
                preset.set_param("Vcf_Cutoff", f.cutoff)
            if f.resonance is not None:
                preset.set_param("Vcf_Resonance", f.resonance)
            if f.env_amount is not None:
                preset.set_param("Vcf_EnvAmount", f.env_amount)

        # 6. Envelope
        if self.envelope is not None:
            e = self.envelope
            if e.attack is not None:
                preset.set_param("Env_Attack", e.attack)
            if e.decay is not None:
                preset.set_param("Env_Decay", e.decay)
            if e.sustain is not None:
                preset.set_param("Env_Sustain", e.sustain)
            if e.release is not None:
                preset.set_param("Env_Release", e.release)
            if e.attack_curve is not None:
                preset.set_param("Env_AttackCurve", e.attack_curve)
            if e.decay_curve is not None:
                preset.set_param("Env_DecayCurve", e.decay_curve)
            if e.release_curve is not None:
                preset.set_param("Env_ReleaseCurve", e.release_curve)

        # 7. LFOs
        if self.lfo1 is not None:
            self._apply_lfo(preset, 1, self.lfo1)
        if self.lfo2 is not None:
            self._apply_lfo(preset, 2, self.lfo2)

        # 8. Cycling Envelope
        if self.cycling_env is not None:
            ce = self.cycling_env
            if ce.rise is not None:
                preset.set_param("CycEnv_Rise", ce.rise)
            if ce.fall is not None:
                preset.set_param("CycEnv_Fall", ce.fall)
            if ce.hold is not None:
                preset.set_param("CycEnv_Hold", ce.hold)
            if ce.mode is not None:
                m = CycEnvMode.from_name(ce.mode)
                if m is None:
                    raise ValueError(f"unknown cycling env mode: {ce.mode!r}")
                preset.set_cycenv_mode(m)
            if ce.stage_order is not None:
                o = CycEnvStageOrder.from_name(ce.stage_order)
                if o is None:
                    raise ValueError(f"unknown stage order: {ce.stage_order!r}")
                preset.set_cycenv_stage_order(o)
            if ce.retrig is not None:
                r = CycEnvRetrigSrc.from_name(ce.retrig)
                if r is None:
                    raise ValueError(f"unknown cycenv retrig source: {ce.retrig!r}")
                preset.set_cycenv_retrig_src(r)
            if ce.rise_curve is not None:
                preset.set_param("CycEnv_RiseCurve", ce.rise_curve)
            if ce.fall_curve is not None:
                preset.set_param("CycEnv_FallCurve", ce.fall_curve)

        # 9. FX
        if self.fx is not None:
            for i, fx_slot in enumerate(self.fx[:3]):
                slot = i + 1
                if fx_slot is not None:
                    self._apply_fx(preset, slot, fx_slot)
                else:
                    preset.set_param(f"FX{slot}_Enable", 0.0)

        # 10. Mod Matrix
        if self.mod is not None:
            self._apply_mod_matrix(preset, self.mod)

        # 11. Macros
        if self.macros is not None:
            preset.clear_macros()
            if self.macros.macro1 is not None:
                self._apply_macro(preset, 1, self.macros.macro1)
            if self.macros.macro2 is not None:
                self._apply_macro(preset, 2, self.macros.macro2)

        # 12. Sequence
        if self.sequence is not None:
            self._apply_sequence(preset, self.sequence)

        # 13. Arpeggiator
        if self.arp is not None:
            self._apply_arp(preset, self.arp)
            # Auto-set Seq_Mode to Arp unless sequence.mode explicitly overrides
            seq_mode = (self.sequence.mode.lower()
                        if self.sequence and self.sequence.mode else None)
            if seq_mode not in ("off", "seq"):
                preset.set_seq_mode(SeqMode.ARP)

        # 14. Velocity/Aftertouch
        if self.velo_at is not None:
            m = VeloAtMode.from_name(self.velo_at)
            if m is None:
                raise ValueError(f"unknown velo/at mode: {self.velo_at!r}")
            preset.set_velo_at_mode(m)

        # 15. Raw parameter overrides (LAST)
        if self.raw_params is not None:
            for name, value in self.raw_params.items():
                preset.set_param(name, value)

        return preset

    # ── Apply Helpers ──────────────────────────────────────────────────

    def _apply_defaults(self, preset: MiniFreakPreset) -> None:
        """Reset commonly-inherited params for sections this recipe defines."""
        # Volume always gets a default
        preset.set_param("Preset_Volume", 0.8)

        if self.osc1 is not None:
            preset.set_param("Osc1_CoarseTune", 0.5)
            preset.set_param("Osc1_FineTune", 0.5)

        if self.osc2 is not None:
            preset.set_param("Osc2_CoarseTune", 0.5)
            preset.set_param("Osc2_FineTune", 0.5)

        if self.arp is not None:
            preset.set_param("Arp_Gate", 0.5)
            preset.set_param("Arp_Spice", 0.0)

        if self.sequence is not None:
            preset.set_param("Seq_Autom_Dest_0", MOD_DEST_NONE)
            preset.set_param("Seq_Autom_Dest_1", MOD_DEST_NONE)
            preset.set_param("Seq_Autom_Dest_2", MOD_DEST_NONE)
            preset.set_param("Seq_Autom_Dest_Last", MOD_DEST_NONE)

    def _apply_voice(self, preset: MiniFreakPreset, v: VoiceConfig) -> None:
        if v.mode is not None:
            m = NoteMode.from_name(v.mode)
            if m is None:
                raise ValueError(f"unknown voice mode: {v.mode!r}")
            preset.set_note_mode(m)
        if v.glide is not None:
            preset.set_param("Gen_Glide", v.glide)
        if v.unison_voices is not None:
            c = UnisonCount.from_name(str(v.unison_voices))
            if c is None:
                raise ValueError(f"invalid unison count: {v.unison_voices}")
            preset.set_unison_count(c)
        if v.unison_mode is not None:
            m = UnisonMode.from_name(v.unison_mode)
            if m is None:
                raise ValueError(f"unknown unison mode: {v.unison_mode!r}")
            preset.set_unison_mode(m)
        if v.alloc is not None:
            a = PolyAlloc.from_name(v.alloc)
            if a is None:
                raise ValueError(f"unknown poly alloc: {v.alloc!r}")
            preset.set_poly_alloc(a)
        if v.steal is not None:
            s = PolySteal.from_name(v.steal)
            if s is None:
                raise ValueError(f"unknown poly steal: {v.steal!r}")
            preset.set_poly_steal(s)
        if v.retrig is not None:
            r = RetrigMode.from_name(v.retrig)
            if r is None:
                raise ValueError(f"unknown retrig mode: {v.retrig!r}")
            preset.set_retrig_mode(r)
        if v.legato is not None:
            preset.set_param("Gen_LegatoMode", 1.0 if v.legato else 0.0)

    def _apply_osc(self, preset: MiniFreakPreset, osc_num: int,
                   osc: OscConfig) -> None:
        prefix = f"Osc{osc_num}"
        if osc.engine is not None:
            if osc_num == 1:
                e = Osc1Engine.from_name(osc.engine)
                if e is None:
                    raise ValueError(f"unknown Osc1 engine: {osc.engine!r}")
                preset.set_osc1_engine(e)
            else:
                e = Osc2Engine.from_name(osc.engine)
                if e is None:
                    raise ValueError(f"unknown Osc2 engine: {osc.engine!r}")
                preset.set_osc2_engine(e)
        if osc.wave is not None:
            preset.set_param(f"{prefix}_Param1", osc.wave)
        if osc.timbre is not None:
            preset.set_param(f"{prefix}_Param2", osc.timbre)
        if osc.shape is not None:
            preset.set_param(f"{prefix}_Param3", osc.shape)
        if osc.volume is not None:
            preset.set_param(f"{prefix}_Volume", osc.volume)
        if osc.tune is not None:
            preset.set_param(f"{prefix}_CoarseTune", osc.tune)
        if osc.fine_tune is not None:
            preset.set_param(f"{prefix}_FineTune", osc.fine_tune)
        if osc.mod_quantize is not None:
            q = TuneModQuantize.from_name(osc.mod_quantize)
            if q is None:
                raise ValueError(f"unknown quantize mode: {osc.mod_quantize!r}")
            preset.set_tune_mod_quantize(osc_num, q)

    def _apply_lfo(self, preset: MiniFreakPreset, lfo_num: int,
                   lfo: LfoConfig) -> None:
        if lfo.rate is not None:
            preset.set_param(f"LFO{lfo_num}_Rate", lfo.rate)
        if lfo.wave is not None:
            w = LfoWaveform.from_name(lfo.wave)
            if w is None:
                raise ValueError(f"unknown LFO waveform: {lfo.wave!r}")
            preset.set_lfo_waveform(lfo_num, w)
        if lfo.sync is not None:
            preset.set_param(f"LFO{lfo_num}_SyncEn",
                             1.0 if lfo.sync else 0.0)
        if lfo.rate_sync is not None:
            d = LfoRateSync.from_name(lfo.rate_sync)
            if d is None:
                raise ValueError(f"unknown LFO rate sync: {lfo.rate_sync!r}")
            preset.set_lfo_rate_sync(lfo_num, d)
        if lfo.retrig is not None:
            r = LfoRetrigMode.from_name(lfo.retrig)
            if r is None:
                raise ValueError(f"unknown LFO retrig mode: {lfo.retrig!r}")
            preset.set_lfo_retrig(lfo_num, r)
        if lfo.sync_filter is not None:
            f = LfoSyncFilter.from_name(lfo.sync_filter)
            if f is None:
                raise ValueError(f"unknown LFO sync filter: {lfo.sync_filter!r}")
            preset.set_lfo_sync_filter(lfo_num, f)

    def _apply_fx(self, preset: MiniFreakPreset, slot: int,
                  fx: FxConfig) -> None:
        algo = FxAlgorithm.from_name(fx.algo)
        if algo is None:
            raise ValueError(f"unknown FX algorithm: {fx.algo!r}")
        preset.set_fx_algorithm(slot, algo)
        preset.set_param(f"FX{slot}_Enable", 1.0)

        if fx.opt1 is not None:
            opt1_val = fx_opt1_from_name(algo, fx.opt1)
            if opt1_val is None:
                raise ValueError(
                    f"unknown Opt1 '{fx.opt1}' for {algo.label}")
            preset.set_param(f"FX{slot}_Opt1", opt1_val)
        if fx.time is not None:
            preset.set_param(f"FX{slot}_Param1", fx.time)
        if fx.intensity is not None:
            preset.set_param(f"FX{slot}_Param2", fx.intensity)
        if fx.amount is not None:
            preset.set_param(f"FX{slot}_Param3", fx.amount)

    def _apply_mod_matrix(self, preset: MiniFreakPreset,
                          routes: list[ModRoute]) -> None:
        preset.clear_mod_matrix()

        # Collect unique assignable destinations
        assignable_dests: list[tuple[ModCluster, int]] = []
        for route in routes:
            dest = mod_dest_from_name(route.dest)
            if dest is None:
                raise ValueError(f"unknown mod destination: {route.dest!r}")
            if not _is_hardwired_dest(dest) and dest not in assignable_dests:
                assignable_dests.append(dest)

        if len(assignable_dests) > ASSIGNABLE_COLS:
            raise ValueError(
                f"too many assignable mod destinations: {len(assignable_dests)} "
                f"(max {ASSIGNABLE_COLS})"
            )

        # Set up assignable column destinations
        for i, (cluster, offset) in enumerate(assignable_dests):
            preset.set_mod_dest(i, cluster, offset)

        # Apply each route
        for route in routes:
            source = ModSource.from_name(route.src)
            if source is None:
                raise ValueError(f"unknown mod source: {route.src!r}")
            dest = mod_dest_from_name(route.dest)
            if dest is None:
                raise ValueError(f"unknown mod destination: {route.dest!r}")
            amount = parse_mod_amount(route.amount)

            hw_col = _hardwired_col_for_dest(dest)
            if hw_col is not None:
                col = hw_col
            else:
                col = assignable_dests.index(dest) + HARDWIRED_COLS
            preset.set_mod_amount(source, col, amount)

    def _apply_macro(self, preset: MiniFreakPreset, macro_id: int,
                     config: MacroConfig) -> None:
        if len(config.dests) > 4:
            raise ValueError(
                f"macro {macro_id} has {len(config.dests)} destinations (max 4)"
            )
        for slot, dest_config in enumerate(config.dests):
            dest = mod_dest_from_name(dest_config.dest)
            if dest is None:
                raise ValueError(
                    f"unknown macro destination: {dest_config.dest!r}")
            cluster, offset = dest
            amount = parse_mod_amount(dest_config.amount)
            preset.set_macro_dest(macro_id, slot, cluster, offset)
            preset.set_macro_amount(macro_id, slot, amount)

    def _apply_sequence(self, preset: MiniFreakPreset,
                        seq: SequenceConfig) -> None:
        if seq.mode is not None:
            m = SeqMode.from_name(seq.mode)
            if m is None:
                raise ValueError(f"unknown seq mode: {seq.mode!r}")
            preset.set_seq_mode(m)
        if seq.tempo is not None:
            preset.set_tempo_bpm(seq.tempo)
        if seq.time_div is not None:
            d = SeqTimeDiv.from_name(seq.time_div)
            if d is None:
                raise ValueError(f"unknown time division: {seq.time_div!r}")
            preset.set_seq_time_div(d)
        if seq.swing is not None:
            preset.set_seq_swing(seq.swing)
        if seq.gate is not None:
            preset.set_seq_gate(seq.gate)

        # Mod lane destinations
        if seq.lane_dests:
            if len(seq.lane_dests) > 4:
                raise ValueError(
                    f"too many lane destinations: {len(seq.lane_dests)} (max 4)"
                )
            dest_params = [
                "Seq_Autom_Dest_0", "Seq_Autom_Dest_1",
                "Seq_Autom_Dest_2", "Seq_Autom_Dest_Last",
            ]
            for i, dest_name in enumerate(seq.lane_dests):
                dest = mod_dest_from_name(dest_name)
                if dest is None:
                    raise ValueError(
                        f"unknown lane destination: {dest_name!r}")
                cluster, offset = dest
                preset.set_param(dest_params[i],
                                 encode_mod_dest(cluster, offset))

        # Clear existing sequence data
        preset.clear_sequence()

        # Determine length
        if seq.length is not None:
            length = seq.length
        elif seq.steps:
            length = max(s.step for s in seq.steps) + 1
        else:
            length = 16
        preset.set_seq_length(length)

        # Write step data
        for step_cfg in seq.steps:
            if step_cfg.step >= 64:
                raise ValueError(f"step {step_cfg.step} out of range (max 63)")
            step = step_cfg.step

            preset.set_step_state(step, True)

            # Notes (up to 6 voices)
            for voice, note_name in enumerate(step_cfg.notes[:6]):
                midi = parse_note_name(note_name)
                if midi is None:
                    raise ValueError(f"invalid note name: {note_name!r}")
                preset.set_step_pitch(step, voice, midi)

            # Velocity (applied to all voices)
            if step_cfg.vel is not None:
                for voice in range(min(len(step_cfg.notes), 6)):
                    preset.set_step_velocity(step, voice, step_cfg.vel)

            # Gate
            if step_cfg.gate is not None:
                preset.set_step_gate(step, step_cfg.gate)

            # Mod lanes
            if step_cfg.mods:
                preset.set_step_mod_state(step, True)
                for lane, value in enumerate(step_cfg.mods[:4]):
                    preset.set_step_mod(step, lane, value)

    def _apply_arp(self, preset: MiniFreakPreset, arp: ArpConfig) -> None:
        if arp.mode is not None:
            m = ArpMode.from_name(arp.mode)
            if m is None:
                raise ValueError(f"unknown arp mode: {arp.mode!r}")
            preset.set_arp_mode(m)
        if arp.octaves is not None:
            o = ArpOct.from_name(str(arp.octaves))
            if o is None:
                raise ValueError(f"invalid arp octave range: {arp.octaves}")
            preset.set_arp_oct(o)
        if arp.gate is not None:
            preset.set_param("Arp_Gate", arp.gate)
        if arp.spice is not None:
            preset.set_param("Arp_Spice", arp.spice)


# ── Helper Functions ───────────────────────────────────────────────────────

def _is_hardwired_dest(dest: tuple[ModCluster, int]) -> bool:
    return _hardwired_col_for_dest(dest) is not None


def _hardwired_col_for_dest(dest: tuple[ModCluster, int]) -> Optional[int]:
    """Get the hardwired column index (0-3) for a destination, if hardwired.

    Col 0 = Pitch 1+2, Col 1 = Osc1 Wave, Col 2 = Osc1 Timbre, Col 3 = Cutoff.
    """
    if dest == DEST_PITCH1 or dest == DEST_PITCH2:
        return 0
    if dest == DEST_OSC1_WAVE:
        return 1
    if dest == DEST_OSC1_TIMBRE:
        return 2
    if dest == DEST_CUTOFF:
        return 3
    return None


def parse_mod_amount(s: str) -> float:
    """Parse a mod amount percentage string to bipolar float.

    "+30%" -> 0.65, "-20%" -> 0.4, "0%" -> 0.5
    """
    s = s.strip()
    if not s.endswith("%"):
        raise ValueError(f"mod amount must end with '%': {s!r}")
    try:
        pct = float(s[:-1])
    except ValueError:
        raise ValueError(f"invalid mod amount: {s!r}")
    if not (-100.0 <= pct <= 100.0):
        raise ValueError(f"mod amount out of range: {pct}%")
    return 0.5 + pct / 200.0


def load_recipe(path: str | Path) -> Recipe:
    """Load a recipe from a JSON file."""
    text = Path(path).read_text()
    data = json.loads(text)
    return Recipe.model_validate(data)
