# MiniFreak Preset Design & Build Guide

> **Audience**: AI coding agents working with this codebase.
> **Purpose**: Everything you need to design MiniFreak presets programmatically — sound design concepts, the JSON recipe format, the Rust tooling, and the underlying .mnfx binary format.

## Quick Start

```bash
# Build a preset from a recipe JSON (uses the repo's safe default base)
cargo run --bin minifreak-tool -- build --output my-patch.mnfx recipe.json

# Bundle multiple presets into a bank for import
cargo run --bin minifreak-tool -- bundle preset1.mnfx preset2.mnfx --output bank.mnfx --pack "My Bank"

# Inspect a preset
cargo run --bin minifreak-tool -- show preset.mnfx

# Compare two presets
cargo run --bin minifreak-tool -- diff a.mnfx b.mnfx
```

**Critical rule**: Always use `minifreak-tool` to produce .mnfx files. Do NOT use shell `zip`, Python `zipfile`, or Finder compression — they produce ZIP formats that MiniFreak V rejects.

---

## 1. The MiniFreak as a Sound Design Platform

The Arturia MiniFreak is a 6-voice digital/analog hybrid synthesizer. Understanding its signal flow is essential for writing good recipes.

### Signal Flow

```
Osc1 ──┐
       ├──► Mixer ──► Analog Filter ──► Amp ──► FX1 ──► FX2 ──► FX3 ──► Output
Osc2 ──┘       │
               │
   Mod Matrix (7 sources × 13 destinations) modulates anything in the chain
```

### Oscillator Engines

Each oscillator has an **engine** (synthesis algorithm) plus 3 continuous parameters (Wave, Timbre, Shape) whose meaning changes per engine. This is the core of MiniFreak sound design — engine choice determines the fundamental character.

**Osc1 Engines (24)**:

| Engine | Character | Best For |
|--------|-----------|----------|
| BasicWaves | Classic analog waveforms (saw, square, pulse) | Bread-and-butter synth sounds |
| SuperWave | Thick detuned stacks (like JP-8000 supersaw) | Pads, trance leads, stabs |
| Harmo | Additive harmonics (like drawbar organ) | Organs, bells, evolving tones |
| Karplus | Physical modeling (plucked strings) | Plucks, mallets, metallic hits |
| VAnalog | Virtual analog with character | Warm analog-style sounds |
| Waveshaper | Distorted waveform sculpting | Aggressive, gritty textures |
| TwoOpFM | 2-operator FM synthesis | Bells, electric piano, metallic |
| Formant | Vowel/formant synthesis | Vocal textures, talking sounds |
| Speech | Speech synthesis (robotic) | Vocoded speech, robotics |
| Modal | Resonant body modeling (struck objects) | Percussion, tuned resonances |
| Noise | Filtered noise generator | Percussion, wind, textures |
| Bass | Dedicated bass engine | Sub bass, 303-style, reese |
| SawX | Extended saw variants | Cutting leads, aggressive bass |
| Harm | Harmonic oscillator variant | Bright, harmonic-rich tones |
| AudioIn | External audio as oscillator source | Processing external signals |
| Wavetable | Wavetable scanning | Evolving digital textures |
| Sample | Sample playback | One-shot or looped samples |
| CloudGrains | Granular cloud synthesis | Ambient, textural, atmospheric |
| HitGrains | Granular with percussive attack | Percussive granular textures |
| Frozen | Spectral freeze effect | Drones, frozen moments |
| Skan | Spectral scanning | Morphing spectral content |
| Particle | Particle-based synthesis | Glitchy, scattered textures |
| Lick | Physical modeling string licks | Guitar-like, stringed plucks |
| Raster | Harsh digital oscillator | Industrial, bitcrushed tones |

**Osc2-Only Engines (6 additional)**:

| Engine | Character | Best For |
|--------|-----------|----------|
| Chords | Built-in chord voicing | Instant chord stabs |
| FM/RM | Ring/frequency modulation of Osc1 | Metallic, inharmonic, clangy |
| MultiFilter | Multi-mode filter as oscillator | Self-oscillating filter tones |
| SurgeonFilter | Surgical filter precision | Precise resonant filtering |
| CombFilter | Comb filtering of Osc1 | Flanged, metallic coloring |
| PhaserFilter | Phaser-style filtering of Osc1 | Sweeping, phased textures |
| Destroy | Bitcrushing/destruction of Osc1 | Lo-fi, broken digital |

**Practical notes**:
- Osc2's filter engines process Osc1's output — they're not independent oscillators but processors
- FM/RM and Destroy also interact with Osc1 — think of them as "Osc1 modifiers"
- When using processing engines on Osc2, Osc1's engine choice matters more since it's the raw material

### The Analog Filter

A Steiner-Parker multimode filter — the only analog component in the signal path. This is where warmth and character come from.

- **Modes**: LPF (low-pass), BPF (band-pass), HPF (high-pass)
- **Cutoff** (0.0–1.0): Frequency point. 0.0 = fully closed (dark), 1.0 = fully open (bright)
- **Resonance** (0.0–1.0): Peak at cutoff frequency. High values = squealy, acid-like
- **Env Amount** (0.0–1.0): How much the amplitude envelope opens/closes the filter. High values = plucky, percussive filter sweeps

**Common patterns**:
- Acid bass: LPF, low cutoff (0.15–0.30), high resonance (0.5–0.7), high env amount (0.6–0.8)
- Bright pad: LPF, high cutoff (0.6–0.8), low resonance, moderate env amount
- Airy texture: HPF, moderate cutoff (0.4–0.6), low resonance
- Vocal quality: BPF, mid cutoff (0.35–0.55), moderate resonance (0.3–0.5)

### Envelopes

**Amp Envelope (ADSR)**: Controls volume shape. All values 0.0–1.0.
- **Attack**: Time to reach peak. 0 = instant (stabs, plucks), 0.3–0.6 = swells, pads
- **Decay**: Time from peak to sustain level. Short = percussive, long = evolving
- **Sustain**: Held level. 0 = fully percussive, 1.0 = organ-like
- **Release**: Fade after note-off. Short = tight, long = ambient tails

Also affects filter when Env Amount > 0 — the same ADSR shape modulates cutoff.

**Cycling Envelope**: A loopable envelope with Rise/Fall/Hold stages.
- **Modes**: Env (one-shot), Run (free-running), Loop (repeating)
- When looping, acts like an extra LFO with envelope shape
- Great for rhythmic filter modulation, tremolo, evolving textures

### LFOs

Two LFOs for cyclic modulation. Key parameters:
- **Rate**: Speed (0.0–1.0 for free, or sync to tempo divisions)
- **Waveform**: Sine, Triangle, Saw, Square, Sample&Hold, Slew S&H, Exp Saw, Exp Ramp, Shaper
- **Retrigger**: Free (continuous), PolyKbd, MonoKbd, LegatoKbd, One, OtherLfo, CycEnv, SeqStart
- **Sync**: Lock to tempo with 27 division options (8 bars dotted down to 1/32 triplet)

**Typical uses**:
- Vibrato: LFO → Pitch, sine wave, moderate rate
- Filter wobble: LFO → Cutoff, triangle or sine, slow rate
- Tremolo: LFO → Volume, sine, moderate rate
- Rhythmic gating: LFO → Volume, square wave, tempo-synced

### FX Slots

Three serial FX slots, each with 13 algorithm choices and per-algorithm sub-modes (Opt1):

| Algorithm | Sub-Modes (Opt1) | Time | Intensity | Amount |
|-----------|-------------------|------|-----------|--------|
| Chorus | Default, Lush, Dark, Shaded, Single | Rate | Depth | Mix |
| Phaser | Default, Default Sync, Space, Space Sync, S&H, S&H Sync | Rate | Feedback | Mix |
| Flanger | Default, Default Sync, Swept, Swept Sync | Rate | Feedback | Mix |
| Reverb | Default, Long, Hall, Echoes, Room, Dark Room | Decay | Damping | Mix |
| Delay | Digital, Digital Sync, Stereo, Stereo Sync, Ping-Pong, PP Sync, Mono, Mono Sync, Filtered, Filtered Sync, Filtered PP, Filtered PP Sync | Time | Feedback | Mix |
| Distortion | Classic, Soft Clip, Germanium, Dual Fold, Climb, Tape | Drive | Tone | Mix |
| Bit Crusher | *(continuous knob)* | Sample Rate | Bit Depth | Mix |
| 3-Band EQ | *(continuous knob)* | Low | Mid | High |
| Peak EQ | Low Shelf, Bell, High Shelf | Frequency | Q | Gain |
| Multi Comp | *(continuous knob)* | Threshold | Ratio | Makeup |
| Super Unison | Classic, Ravey, Soli, Slow, Slow Trig, Wide Trig, Mono Trig, Wavy | Voices | Detune | Mix |
| Vocoder Self | Clean, Vintage, Narrow, Gated | Band Count | Decay | Mix |
| Vocoder Ext | Clean, Vintage, Narrow, Gated | Band Count | Decay | Mix |

**FX slot strategy**: Order matters since they're in series.
- Distortion before reverb = ambient grit
- Reverb before delay = washy echoes
- Chorus/Phaser for width, then reverb for space, then delay for rhythm

### Mod Matrix

The mod matrix is the MiniFreak's most powerful feature for creating movement and expression. It connects modulation sources to parameter destinations.

**7 Sources** (rows):
1. **CycEnv** — Cycling envelope output
2. **Envelope** — Amp ADSR envelope output
3. **LFO1** — First LFO
4. **LFO2** — Second LFO
5. **Velocity/Aftertouch** — Performance input (configurable: Velocity, Aftertouch, or Velo+AT)
6. **Wheel** — Mod wheel (CC 1)
7. **Keyboard** — Keyboard tracking (pitch-to-modulation)

**13 Destinations per source** (columns):
- 4 **hardwired** (always connected): Pitch 1+2, Osc1 Wave, Osc1 Timbre, Cutoff
- 9 **assignable** (routable to any parameter)

**Amounts**: Bipolar, specified as percentage strings: "+50%", "-30%", "0%" (no modulation)

**Routable destinations** (91 synth params + 9 FX params):
- Oscillator: type, wave, timbre, shape, volume, sub, tune, fine tune
- Filter: cutoff, resonance, env amount, mode
- Amp: attack, decay, sustain, release, curves, volume
- LFO1/2: rate, wave, phase
- CycEnv: rise, fall, hold
- Voice: glide, vibrato rate/depth, unison spread
- FX1-3: time, intensity, amount, opt1
- Macros: macro1 value, macro2 value
- **Meta-mod**: Modulate the amount of other mod matrix entries

**Macros**: Two assignable macro knobs (CC 117, CC 118), each with up to 4 parameter destinations and individual amounts. Great for performance-oriented "super knobs."

### Voice Modes

- **Mono**: Single voice, all 6 oscillators stacked. Fattest sound.
- **Unison**: Multiple voices playing same note (2/3/4/6 voices). Thick detuned stacks.
- **Poly**: True polyphony up to 6 voices. Chords, pads.
- **Para** (Paraphonic): Multiple notes share one filter. Compromise between mono thickness and poly harmony.

Sub-modes: UniPoly and UniPara combine unison with polyphonic voicing.

### Sequencer & Arpeggiator

**Sequencer**: Up to 64 steps, each with:
- Up to 6 pitches (polyphonic sequencing)
- Velocity, gate length
- 4 automation lanes (mod destinations with per-step values)

**Arpeggiator**: 7 modes (Up, Down, Up/Down, Random, Pattern, Order, Poly), 1-4 octave range, gate and spice controls.

---

## 2. The JSON Recipe Format

Recipes are the primary way to define presets programmatically. A recipe is a compact JSON object (~50–100 fields) that gets expanded against a base preset (~2485 parameters) to produce a complete .mnfx file.

### Minimal Recipe

```json
{
  "name": "My Patch",
  "osc1": { "engine": "SuperWave" },
  "filter": { "cutoff": 0.5 }
}
```

Everything not specified inherits from the base preset. This is the key design principle — you only declare what you want to change.

### Full Recipe Schema

```json
{
  "name": "Patch Name (required, max ~20 chars)",

  "voice": {
    "mode": "Mono|Unison|Poly|Para",
    "glide": 0.0,
    "unison_voices": 4,
    "unison_mode": "Unison|Uni Poly|Uni Para",
    "alloc": "Cycle|Reassign|Reset",
    "steal": "Oldest|Lowest|None",
    "retrig": "Env Reset|Env Continue",
    "legato": true
  },

  "osc1": {
    "engine": "BasicWaves",
    "wave": 0.5,
    "timbre": 0.5,
    "shape": 0.0,
    "volume": 1.0,
    "tune": 0.5,
    "fine_tune": 0.5,
    "sub": 0.0,
    "mod_quantize": "Continuous|Chromatic|Octaves|Fifths|Minor|Major|PhrygianDom|Minor9th|Major9th|MinorPenta|MajorPenta"
  },

  "osc2": {
    "engine": "BasicWaves",
    "wave": 0.5,
    "timbre": 0.5,
    "shape": 0.0,
    "volume": 1.0,
    "tune": 0.5,
    "fine_tune": 0.5
  },

  "filter": {
    "mode": "LPF|BPF|HPF",
    "cutoff": 0.5,
    "resonance": 0.0,
    "env_amount": 0.0
  },

  "envelope": {
    "attack": 0.0,
    "decay": 0.5,
    "sustain": 0.7,
    "release": 0.3,
    "attack_curve": 0.5,
    "decay_curve": 0.5,
    "release_curve": 0.5
  },

  "lfo1": {
    "rate": 0.5,
    "wave": "Sine|Triangle|Saw|Square|Sample And Hold|Slew SH|Exp Saw|Exp Ramp|Shaper",
    "sync": false,
    "rate_sync": "1/4",
    "retrig": "Free|Poly Kbd|Mono Kbd|Legato Kbd|One|Other LFO|CycEnv|Seq Start",
    "sync_filter": "All|Straight|Triplet|Dotted|Free"
  },

  "lfo2": { "...same as lfo1..." },

  "cycling_env": {
    "rise": 0.3,
    "fall": 0.3,
    "hold": 0.0,
    "mode": "Env|Run|Loop",
    "stage_order": "Rise Hold Fall|Rise Fall Hold|Hold Rise Fall",
    "retrig": "Poly Kbd|Mono Kbd|Legato Kbd|LFO1|LFO2",
    "rise_curve": 0.5,
    "fall_curve": 0.5
  },

  "fx": [
    { "algo": "Chorus", "opt1": "Lush", "time": 0.5, "intensity": 0.5, "amount": 0.5 },
    { "algo": "Reverb", "opt1": "Hall", "time": 0.6, "intensity": 0.3, "amount": 0.4 },
    { "algo": "Delay", "opt1": "Stereo Sync", "time": 0.5, "intensity": 0.3, "amount": 0.3 }
  ],

  "mod": [
    { "src": "LFO1", "dest": "Cutoff", "amount": "+30%" },
    { "src": "Envelope", "dest": "Osc1 Wave", "amount": "-20%" },
    { "src": "Wheel", "dest": "FX1 Amount", "amount": "+50%" }
  ],

  "macros": {
    "macro1": {
      "name": "SWEEP",
      "dests": [
        { "dest": "Cutoff", "amount": "+60%" },
        { "dest": "Resonance", "amount": "+30%" }
      ]
    },
    "macro2": {
      "name": "SPACE",
      "dests": [
        { "dest": "FX2 Amount", "amount": "+80%" },
        { "dest": "FX3 Amount", "amount": "+50%" }
      ]
    }
  },

  "velo_at": "Velocity|Aftertouch|VeloPlusAt",

  "arp": {
    "mode": "Up|Down|Up/Down|Random|Pattern|Order|Poly",
    "octaves": 2,
    "gate": 0.5,
    "spice": 0.0
  },

  "sequence": {
    "mode": "Seq",
    "length": 16,
    "tempo": 120,
    "time_div": "1/16",
    "swing": 0.5,
    "gate": 0.5,
    "lane_dests": ["Cutoff", "FX1 Intensity", "Osc1 Wave", "Osc2 Timbre"],
    "steps": [
      { "step": 0, "notes": ["C3"], "vel": 100, "gate": 0.6, "mods": [0.3, 0.5] },
      { "step": 1, "notes": ["C3"], "vel": 80 },
      { "step": 4, "notes": ["Eb3", "G3"], "vel": 110, "gate": 0.8 }
    ]
  },

  "raw_params": {
    "SomeParamName": 0.42
  }
}
```

### Key Format Rules

1. **All values are 0.0–1.0 floats** unless they're enum strings or note names
2. **Engine/algorithm names are case-insensitive** and accept common variants (e.g., "superwave", "SuperWave", "Multi Filter")
3. **Mod amounts are percentage strings**: "+50%", "-100%", "0%". Internally mapped to bipolar floats (0.0 = -100%, 0.5 = center, 1.0 = +100%)
4. **Sequence steps are 0-indexed** (step 0 = first step, step 15 = last step of 16)
5. **Notes are string names** like "C4", "Eb3", "F#2" (C4 = MIDI 60). Up to 6 notes per step for polyphonic sequencing
6. **Velocity field is `vel`** (0–127), gate length field is `gate` (0.0–1.0)
7. **Mod lane values field is `mods`** (array of up to 4 floats, matching `lane_dests` order)
8. **Omitted fields inherit from base preset** — only specify what you want to change
9. **`raw_params`** is an escape hatch for any parameter by its raw name. Applied last, overrides everything
10. **Tempo formula**: Internal value = (BPM - 30) / 210. Range: 30–240 BPM
11. **Opt1 sub-modes** are per-algorithm. Check the FX table above for valid options per algorithm
12. **Max 4 macro destinations** per macro knob
13. **Max 4 automation lanes** in the sequencer
14. **FX array is positional** — 3 elements, position = slot. Use `null` for unused slots
15. **Unison voices** and **arp octaves** use raw numbers (2/3/4/6 and 1/2/3/4)

### Mod Destination Names

When specifying `dest` in mod routes, macros, or sequencer lanes, use these names:

**Oscillator**: `Osc1 Type`, `Osc1 Wave`, `Osc1 Timbre`, `Osc1 Shape`, `Osc1 Volume`, `Osc1 Sub`, `Osc1 Tune`, `Osc1 Fine Tune` (same pattern for Osc2)

**Filter**: `Cutoff`, `Resonance`, `Filter Env Amount`, `Filter Mode`

**Amp/Envelope**: `Attack`, `Decay`, `Sustain`, `Release`, `Amp Volume`, `Attack Curve`, `Decay Curve`, `Release Curve`

**LFO**: `LFO1 Rate`, `LFO1 Wave`, `LFO1 Phase`, `LFO2 Rate`, `LFO2 Wave`, `LFO2 Phase`

**Cycling Env**: `CycEnv Rise`, `CycEnv Fall`, `CycEnv Hold`

**Voice**: `Glide`, `Vibrato Rate`, `Vibrato Depth`, `Unison Spread`

**FX**: `FX1 Time`, `FX1 Intensity`, `FX1 Amount`, `FX1 Opt1` (same for FX2, FX3)

**Macros**: `Macro1`, `Macro2`

**Pitch**: `Pitch 1+2` (hardwired column in mod matrix)

### Hardwired vs Assignable Mod Columns

The mod matrix has 4 hardwired destinations that are always connected:
- Column 0: **Pitch 1+2** — pitch bend both oscillators
- Column 1: **Osc1 Wave** — morph Osc1 waveform
- Column 2: **Osc1 Timbre** — morph Osc1 timbre
- Column 3: **Cutoff** — filter frequency

The remaining 9 columns per source are freely assignable. The recipe system auto-detects hardwired destinations and routes them correctly.

---

## 3. Recipe Examples

### Acid Bass

```json
{
  "name": "Squelch Acid",
  "voice": { "mode": "Mono", "glide": 0.15 },
  "osc1": { "engine": "BasicWaves", "wave": 0.75, "mod_quantize": "Chromatic" },
  "osc2": { "engine": "Multi Filter", "volume": 0.7 },
  "filter": { "mode": "LPF", "cutoff": 0.20, "resonance": 0.65, "env_amount": 0.72 },
  "envelope": { "attack": 0.0, "decay": 0.35, "sustain": 0.0, "release": 0.15 },
  "cycling_env": { "mode": "Loop", "rise": 0.2, "fall": 0.3 },
  "fx": [
    { "algo": "Distortion", "opt1": "Germanium", "time": 0.55, "intensity": 0.4, "amount": 0.6 },
    { "algo": "Delay", "opt1": "Mono Sync", "time": 0.5, "intensity": 0.3, "amount": 0.25 },
    null
  ],
  "mod": [
    { "src": "CycEnv", "dest": "Cutoff", "amount": "+25%" },
    { "src": "Velocity", "dest": "Cutoff", "amount": "+40%" }
  ],
  "sequence": {
    "mode": "Seq", "tempo": 138, "time_div": "1/16",
    "steps": [
      { "step": 0,  "notes": ["C2"],  "vel": 120, "gate": 0.8 },
      { "step": 2,  "notes": ["C2"],  "vel": 90,  "gate": 0.5 },
      { "step": 4,  "notes": ["Eb2"], "vel": 110, "gate": 0.7 },
      { "step": 6,  "notes": ["C2"],  "vel": 80,  "gate": 0.4 },
      { "step": 8,  "notes": ["F2"],  "vel": 127, "gate": 0.9 },
      { "step": 10, "notes": ["C2"],  "vel": 70,  "gate": 0.3 },
      { "step": 12, "notes": ["G2"],  "vel": 100, "gate": 0.6 },
      { "step": 14, "notes": ["C2"],  "vel": 85,  "gate": 0.5 }
    ]
  }
}
```

### Lush Pad

```json
{
  "name": "Cloud Drift",
  "voice": { "mode": "Poly" },
  "osc1": { "engine": "Harmo", "wave": 0.3, "timbre": 0.6 },
  "osc2": { "engine": "BasicWaves", "wave": 0.5, "tune": 0.507 },
  "filter": { "mode": "LPF", "cutoff": 0.55, "resonance": 0.15, "env_amount": 0.2 },
  "envelope": { "attack": 0.45, "decay": 0.6, "sustain": 0.7, "release": 0.65 },
  "lfo1": { "rate": 0.08, "wave": "Triangle", "retrig": "Free" },
  "lfo2": { "rate": 0.03, "wave": "Sine", "retrig": "Free" },
  "cycling_env": { "mode": "Loop", "rise": 0.5, "fall": 0.5 },
  "fx": [
    { "algo": "Chorus", "opt1": "Lush", "time": 0.4, "intensity": 0.5, "amount": 0.5 },
    { "algo": "Reverb", "opt1": "Long", "time": 0.7, "intensity": 0.3, "amount": 0.45 },
    { "algo": "Phaser", "opt1": "Space", "time": 0.2, "intensity": 0.3, "amount": 0.2 }
  ],
  "mod": [
    { "src": "LFO1", "dest": "Cutoff", "amount": "+20%" },
    { "src": "LFO2", "dest": "Osc1 Timbre", "amount": "+15%" },
    { "src": "CycEnv", "dest": "Osc1 Wave", "amount": "+25%" },
    { "src": "Keyboard", "dest": "Cutoff", "amount": "+30%" }
  ]
}
```

### Arp Lead

```json
{
  "name": "Night Runner",
  "voice": { "mode": "Unison", "unison_voices": 4, "unison_mode": "Uni Poly" },
  "osc1": { "engine": "SuperWave", "wave": 0.8, "timbre": 0.6 },
  "osc2": { "engine": "VAnalog", "wave": 0.5, "fine_tune": 0.52 },
  "filter": { "mode": "LPF", "cutoff": 0.30, "resonance": 0.25, "env_amount": 0.45 },
  "envelope": { "attack": 0.02, "decay": 0.55, "sustain": 0.4, "release": 0.5 },
  "lfo1": { "wave": "Triangle", "sync": true, "rate_sync": "1/4", "retrig": "Poly Kbd" },
  "fx": [
    { "algo": "Super Unison", "opt1": "Ravey", "time": 0.5, "intensity": 0.4, "amount": 0.4 },
    { "algo": "Delay", "opt1": "Stereo Sync", "time": 0.5, "intensity": 0.35, "amount": 0.3 },
    { "algo": "Reverb", "opt1": "Hall", "time": 0.6, "intensity": 0.4, "amount": 0.3 }
  ],
  "mod": [
    { "src": "LFO1", "dest": "Cutoff", "amount": "+35%" },
    { "src": "Wheel", "dest": "FX2 Amount", "amount": "+60%" }
  ],
  "arp": { "mode": "Up/Down", "octaves": 2 }
}
```

More complete examples live in `examples/*.json` (acid-bass.json, wet-cathedral.json, bloodline-303.json, sprinkler-mist.json, vampire-siren.json, midnight-runner.json, rave-stab-minor7.json).

---

## 4. The Build Pipeline

### How `minifreak-tool build` Works

```
recipe.json  +  base-preset.mnfx  ──►  minifreak-tool build  ──►  output.mnfx
(~80 fields)    (~2485 params)                                     (complete preset)
```

1. **Load base preset**: Use `--base` if provided, otherwise the default base; parse the .mnfx file (either bare text or ZIP archive)
2. **Apply defaults**: Reset commonly-inherited params to neutral values (prevents bleed from base)
3. **Apply recipe sections**: Voice → Osc1 → Osc2 → Filter → Envelope → LFOs → CycEnv → FX → Mod Matrix → Macros → Sequence → Arp → VeloAt
4. **Apply raw_params**: Override any parameter by raw name (last, highest priority)
5. **Serialize**: Write to Boost.Serialization text format
6. **Package as ZIP**: Create MiniFreak V-compatible ZIP archive

### Base Preset Selection

By default, `minifreak-tool build` uses the repo's **safe default base**:
- **Path**: `presets/minifreak-default-base.mnfx`
- **Behavior**: the tool sanitizes this base (clears mod matrix/macros/sequence, disables FX, resets core voice/filter/envelope values) before applying your recipe.
- **Why**: consistent, neutral defaults that don't leak random characteristics.

If you need a custom base, pass `--base <exported.mnfx>` (recommended: an Init preset exported from MiniFreak V). Always use an **exported** preset (not a factory preset):
- Factory presets use firmware ~3.x parameter counts (2368 params)
- Exported presets use firmware 4.x counts (2485 params)
- **Engine float values differ between firmware versions** — a recipe built against a factory base will produce wrong engine selections

### Bundle Command

```bash
minifreak-tool bundle preset1.mnfx preset2.mnfx preset3.mnfx --output bank.mnfx --pack "My Bank"
```

Creates a multi-preset bank that MiniFreak V imports as a pack. Each preset appears in the pack with its embedded name.

---

## 5. Rust API Reference

### Key Types and Files

| File | Purpose |
|------|---------|
| `src/minifreak/mod.rs` | Module declarations |
| `src/minifreak/parser.rs` | .mnfx format parser (tokenizer, header, parameters) |
| `src/minifreak/preset.rs` | `MiniFreakPreset` — load, modify, serialize presets |
| `src/minifreak/constants.rs` | All enums, mod matrix encoding, parameter names |
| `src/minifreak/recipe.rs` | `Recipe` — JSON recipe parsing and preset building |
| `src/bin/minifreak_tool.rs` | CLI tool (show, dump, diff, build, bundle, etc.) |

### MiniFreakPreset (preset.rs)

```rust
// Load
let preset = MiniFreakPreset::from_file("patch.mnfx")?;

// Query
let engine = preset.get_osc1_engine();      // -> Option<Osc1Engine>
let algo = preset.get_fx_algorithm(1);       // -> Option<FxAlgorithm> (slot 1-3)
let mode = preset.get_filter_mode();         // -> Option<FilterMode>
let diff = preset.diff(&other_preset);       // -> Vec<(String, f64, f64)>

// Modify oscillators
preset.set_osc1_engine(Osc1Engine::SuperWave);
preset.set_osc2_engine(Osc2Engine::FmRm);

// Modify filter
preset.set_filter_mode(FilterMode::LPF);
preset.params.insert("Vcf_Cutoff".into(), 0.5);
preset.params.insert("Vcf_Resonance".into(), 0.3);

// Modify FX
preset.set_fx_algorithm(1, FxAlgorithm::Reverb);  // Slot 1
preset.params.insert("FX1_Time".into(), 0.6);

// Mod matrix
use crate::minifreak::constants::*;
preset.set_mod_dest(ModSource::Lfo1, 4, DEST_CUTOFF);   // Assignable col 4
preset.set_mod_amount(ModSource::Lfo1, 4, 0.65);        // +30% (0.5 = center)

// Macros
preset.set_macro_dest(1, 0, DEST_CUTOFF);    // Macro 1, slot 0
preset.set_macro_amount(1, 0, 0.8);          // +60%

// Sequencer
preset.set_step_pitch(0, 0, 48);             // Step 0, voice 0, MIDI note 48
preset.set_step_velocity(0, 100);
preset.set_step_state(0, true);
preset.set_step_gate(0, 0.5);

// Serialize and write
let text = preset.to_mnfx();                 // Boost.Serialization text
preset.write_zip("output.mnfx")?;            // ZIP for MiniFreak V import
```

### Recipe (recipe.rs)

```rust
let recipe = Recipe::load_recipe("patch.json")?;
let base = MiniFreakPreset::from_file("presets/minifreak-default-base.mnfx")?;
let preset = recipe.build(base)?;
preset.write_zip("output.mnfx")?;
```

### Constants (constants.rs)

All enums implement `to_value() -> f64` and `from_value(f64) -> Option<Self>` for converting between the JSON-friendly enum names and the internal float encoding.

Mod destination constants: `DEST_OSC1_TYPE`, `DEST_CUTOFF`, `DEST_RESO`, `DEST_ATTACK`, `DEST_DECAY`, `DEST_SUSTAIN`, `DEST_RELEASE`, `DEST_LFO1_RATE`, `DEST_FX1_TIME`, `DEST_FX1_INTENSITY`, `DEST_FX1_AMOUNT`, etc.

---

## 6. The .mnfx Binary Format (Low-Level Reference)

You rarely need this — the recipe system and `MiniFreakPreset` API abstract it away. But for debugging or extending the parser:

### Structure

```
"22 serialization::archive 10 0 7 0 7"       ← Magic header
<name> <pack> <author> <original_author>      ← Length-prefixed strings
66                                            ← Marker
0 0 0 0 0 0                                  ← Six zeros padding
<description>                                 ← Empty for factory, non-empty for exported
[timestamp fw_version 0 0 0 0 0 0 0 0 0 0]   ← Exported only: extra padding
<metadata_count>                              ← Number of key-value pairs
  <key> <value>                               ← Repeated metadata entries
0 0 0 7 0 0 0 0 0 0                          ← Trailing header
<param_count>                                 ← Number of parameters (2368 or 2485)
  <param_name> <float_value>                  ← Repeated parameter entries
0 0                                           ← End marker
```

### String Encoding

```
5 Hello          ← "Hello" (5 chars)
12 Acid Machine  ← "Acid Machine" (12 chars, space counts)
0                ← Empty string (0 chars)
```

### Firmware Version Differences

| Property | Factory (~3.x) | Exported (4.x) |
|----------|----------------|-----------------|
| Param count | 2368 | 2485 |
| Osc1 engines | 14 (1/13 spacing) | 24 (1/23 spacing) |
| Osc2 engines | 15 (1/14 spacing) | 21 (1/29 spacing) |
| FX algorithms | 10 (1/9 spacing) | 13 (1/12 spacing) |
| Padding | 12 ints (incl. -1 marker) | timestamp + fw_version + 10 ints |

**Always use firmware 4.x values when building presets.**

---

## 7. Common Patterns and Pitfalls

### Do

- **Start from an exported Init preset** as the base for `build`
- **Use enum names** in recipes, not raw float values (`"SuperWave"` not `0.0435`)
- **Specify Opt1 sub-modes** when setting FX algorithms — the default may not be what you want
- **Use mod matrix for movement** — static patches sound lifeless
- **Think about Osc2 as processor** when using filter/FM/Destroy engines
- **Use `minifreak-tool diff`** to verify your recipe produces the expected changes
- **Check `examples/*.json`** for battle-tested recipe patterns

### Don't

- **Don't use shell zip tools** to create .mnfx files — MiniFreak V requires specific ZIP format (version 1.0, no extra fields, stored/uncompressed)
- **Don't mix factory and exported parameter encodings** — engine floats are firmware-version-dependent
- **Don't exceed 4 macro destinations** per macro or 9 assignable mod columns per source
- **Don't forget the filter** — it's the only analog stage and makes or breaks the sound
- **Don't set all FX amounts to 1.0** — subtlety usually sounds better than maximum wet
- **Don't ignore velocity** in sequences — dynamic velocity patterns are key to musical feel

### Sound Design Tips

**Making it fat**: Mono/Unison mode + SuperWave + slight Osc2 detune + low filter cutoff with resonance

**Making it move**: Loop cycling envelope → Cutoff + LFO1 → Osc1 Wave + LFO2 (slow) → FX amounts

**Making it expressive**: Map Velocity → Cutoff and Envelope amount. Map Wheel → FX wet and filter. Use aftertouch for vibrato or brightness.

**Making it wide**: Chorus or Super Unison on FX1 + Stereo Delay on FX2 + Reverb on FX3. Or use Unison mode with spread.

**Making it dark**: Low cutoff, low resonance, Reverb with Dark Room opt1, reduce Osc high harmonics (low wave/timbre on most engines)

**Making it aggressive**: Distortion (Dual Fold or Germanium) + high resonance + Waveshaper or Raster engine + short decay envelope

---

## 8. CLI Command Reference

```bash
# Show preset summary (engines, FX, voice mode, key params)
minifreak-tool show <preset.mnfx>

# Dump full preset as JSON
minifreak-tool dump <preset.mnfx>

# Compare two presets (shows parameter differences)
minifreak-tool diff <a.mnfx> <b.mnfx>

# Build preset from recipe (uses the default base)
minifreak-tool build --output <out.mnfx> <recipe.json>

# Build from a custom exported base
minifreak-tool build --base <exported.mnfx> --output <out.mnfx> <recipe.json>

# Bundle presets into importable bank
minifreak-tool bundle <p1.mnfx> <p2.mnfx> ... --output <bank.mnfx> --pack "Pack Name"

# Catalog all presets in a directory
minifreak-tool catalog <directory>

# Index parameter values across preset collection
minifreak-tool index <directory> --param Osc1_Type

# Test roundtrip serialization
minifreak-tool roundtrip <preset.mnfx>
```

Build with: `cargo build --bin minifreak-tool`

---

## Cross-References

- **Engine technical details**: `docs/minifreak/engine-reference.md` — exact float encodings, spacing grids, all enum values
- **UI completeness audit**: `minifreak-ui-mnfx-audit.md` — every patch-level
  MiniFreak V control, nested menu, ownership classification, and evidence gate
- **Format specification**: `docs/minifreak/mnfx-format.md` — complete .mnfx format spec, ZIP requirements
- **MIDI CC control**: `docs/minifreak/midi-cc-mapping.md` — real-time CC modulation (41 params)
- **Control strategy**: `docs/minifreak/control-strategy.md` — human/AI collaboration workflow, Audio In hack
- **Hardware overview**: `docs/minifreak/overview.md` — architecture comparison with Rytm
