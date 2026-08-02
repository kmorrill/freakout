# MiniFreak .mnfx Preset Format Specification

## Overview

The `.mnfx` format stores Arturia MiniFreak synthesizer presets. It uses the **Boost.Serialization C++ text archive format (version 10)** — a human-readable, space-delimited token stream with length-prefixed strings.

There are two container formats:
- **Bare text files** — Factory presets dumped from the device (~48-50KB for full presets, ~163 bytes for Init presets)
- **ZIP archives** — Presets exported from MiniFreak V software (contain the text data + embedded wavetable/sample binary data + PNG icon)

## Tokenization

All data is ASCII text. Tokens are separated by whitespace (spaces, tabs, newlines — the parser treats them identically). Two types of tokens:

### Length-Prefixed Strings
```
<char_count> <string_content>
```
The char count is the number of characters (bytes in ASCII) to read. The string may contain spaces.

Examples:
- `4 Init` → "Init"
- `12 Crusty Pluck` → "Crusty Pluck"
- `22 serialization::archive` → "serialization::archive"
- `0` → "" (empty string)

### Numeric Literals
Integers and floats are written as plain ASCII:
- Integers: `0`, `10`, `-1`, `66`, `2368`
- Floats: `0.71428573`, `0.49998474`, `-0.5`

## File Structure

### Archive Header

Every .mnfx file begins with:

```
22 serialization::archive 10 0 7 0 7
```

| Field | Value | Notes |
|-------|-------|-------|
| Magic string | `serialization::archive` | Length-prefixed (22 chars) |
| Archive version | `10` | Always 10 |
| Tracking flags | `0 7 0 7` | Boost.Serialization class tracking info |

### Preset Metadata

Immediately after the header:

```
<name_len> <name> <pack_len> <pack> 66 <author_len> <author> <orig_author_len> <orig_author>
```

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| Name | length-prefixed string | `12 Crusty Pluck` | Preset name |
| Pack | length-prefixed string | `4 User` or `7 Factory` | Preset pack/bank |
| Class info marker | integer | `66` | Always 66 |
| Author | length-prefixed string | `9 Matt Pike` | Sound designer name |
| Original author | length-prefixed string | `7 Unknown` | Original source |

### Padding and Optional Fields

After author fields:

```
0 0 0 0 0 0       ← six zeros (always present)
<description>      ← length-prefixed string (0 = empty)
```

#### Factory Format (no description)
When description is empty (length = 0), 12 padding integers follow:
```
0 0 0 0 0 0 -1 0 0 0 0 0
```
The `-1` appears to be a "no timestamp" marker.

#### Exported Format (has description)
When description is non-empty, timestamp and firmware version follow:
```
<unix_timestamp> <fw_version_len> <fw_version> 0 0 0 0 0 0 0 0 0 0
```

Example:
```
120 Supersaw poly lead. Macro 1 controls HPF frequency...
1665413644 10 4.0.2.6369 0 0 0 0 0 0 0 0 0 0
```

### Metadata Key-Value Pairs

```
<count> 0 0 0 <key1_len> <key1> <val1_len> <val1> <key2_len> <key2> <val2_len> <val2> ...
```

Common metadata keys:
| Key | Example Value | Notes |
|-----|---------------|-------|
| `Type` | `Bass`, `Lead`, `Keys`, `Pad`, `Sequence` | Preset category |
| `Subtype` | `Poly Lead`, `Mono Bass` | Subcategory |
| `Characteristics` | `Characteristics,Reverb;Genres,Trance;Styles,Classic;` | Tags (exported only) |
| `OriginalFactory` | `1` | Factory preset flag (exported only) |
| `OriginalPackName` | `Factory` | Source pack (exported only) |
| `OriginalPresetName` | `Zuper Sceau` | Original name (exported only) |

### Trailing Header

After metadata entries:

```
0 0 0 7 0 0 0 0 0 0
```

The `7` appears to be a format version marker.

### Parameter Section

```
<param_count> 0 0 0 <name1_len> <name1> <value1> <name2_len> <name2> <value2> ...
```

Parameters are ordered alphabetically by name. Each is a length-prefixed name followed by a numeric value (integer or float).

Factory presets have **2368** parameters. Exported presets from newer firmware have **2485** parameters.

### End Marker

Files end with:
```
0 0
```
followed by a newline. Exported files may have additional binary data (wavetable/sample) after this text section.

## Parameter Reference

### Parameter Groups (2487 unique names across all presets)

| Group | Count | Description |
|-------|-------|-------------|
| Pitch | 385 | Per-step pitch data (`Pitch_S<0-63>_I<0-5>`) |
| Length | 384 | Per-step note length (`Length_S<0-63>_I<0-5>`) |
| Velo | 384 | Per-step velocity (`Velo_S<0-63>_I<0-5>`) |
| Mod | 257 | Per-step modulation (`Mod_S<0-63>_I<0-3>`) |
| Mx | 101 | Modulation matrix (`Mx_AssignDot_*`, `Mx_ColId_*`, `Mx_Dot_*`) |
| Shp1/Shp2 | 66 each | Shaper 1/2 per-step data |
| Gate | 64 | Per-step gate state (`Gate_S<0-63>`) |
| StepState | 64 | Per-step on/off state |
| Favorite/ModState/Reserved | 64 each | Sequencer state arrays |
| Kbd | 30 | Keyboard settings |
| Seq | 23 | Sequencer global settings |
| Macro1/Macro2 | 13 each | Macro assignments and values |
| Glob | 12 | Global settings |
| Osc1/Osc2 | 11 each | Oscillator parameters |
| CycEnv | 9 | Cycling envelope |
| Gen | 9 | Voice/generator settings |
| FX1/FX2/FX3 | 8 each | Effects slots |
| Arp | 7 | Arpeggiator |
| Env | 7 | Envelope (ADSR) |
| LFO1/LFO2 | 7 each | LFO settings |
| Osc (shared) | 6 | Shared oscillator params |
| Vcf | 4 | Filter |
| Vibrato | 4 | Vibrato |

### Key Sound Design Parameters

#### Oscillator Types (`Osc1_Type`, `Osc2_Type`)

Values are normalized floats. The MiniFreak has 22+ oscillator engine types. Observed values from factory presets:

| Value | Engine (estimated) |
|-------|-------------------|
| 0.0 | BasicWaves |
| ~0.0714 | SuperWave |
| ~0.1429 | Wavetable |
| ~0.1739 | (variant) |
| ~0.2143 | HarmoOsc |
| ~0.2857 | KarplusStr |
| ~0.3000 | (variant) |
| ~0.3571 | V.Analog |
| ~0.4286 | Waveshaper |
| ~0.5000 | Two Op.FM |
| ~0.5714 | Granular |
| ~0.6429 | Noise |
| ~0.7143 | (engine) |
| ~0.7857 | (engine) |
| ~0.8571 | (engine) |
| ~0.9000 | (variant) |
| ~0.9286 | (engine) |

*Note: Exact engine-to-value mapping requires cross-referencing with known preset characteristics. The unusual values (~0.1739, ~0.3000, ~0.9000) may be from firmware version differences.*

#### FX Types (`FX1_Type`, `FX2_Type`, `FX3_Type`)

10 algorithms on a 1/9 grid (all confirmed via hardware cross-reference):

| Value | Index | Algorithm |
|-------|-------|-----------|
| 0.0 | 0/9 | Chorus |
| ~0.1111 | 1/9 | Phaser |
| ~0.2222 | 2/9 | Flanger |
| ~0.3333 | 3/9 | Reverb |
| ~0.4444 | 4/9 | Delay |
| ~0.5556 | 5/9 | Distortion |
| ~0.6667 | 6/9 | Bit Crusher |
| ~0.7778 | 7/9 | 3 Band EQ |
| ~0.8889 | 8/9 | Peak EQ |
| 1.0 | 9/9 | Multi Comp |

Off-grid values (0.25, 0.6363, 0.75, 0.9) appear in some presets due to firmware updates changing the algorithm count and re-encoding positions.

#### Filter (`Vcf_*`)

| Parameter | Range | Notes |
|-----------|-------|-------|
| `Vcf_Cutoff` | 0.0-1.0 | Filter cutoff frequency |
| `Vcf_Resonance` | 0.0-1.0 | Resonance |
| `Vcf_Type` | discrete | LP/BP/HP mode |
| `Vcf_EnvAmount` | 0.0-1.0 | Envelope modulation amount |

#### Voice Mode (`Gen_NoteMode`)

Controls polyphony mode. Values observed: discrete set mapping to Mono/Poly/Unison/Paraphonic modes.

#### Envelope (`Env_*`)

Standard ADSR with curve controls:

| Parameter | Range | Notes |
|-----------|-------|-------|
| `Env_Attack` | 0.0-1.0 | Attack time |
| `Env_AttackCurve` | 0.0-1.0 | Attack curve shape |
| `Env_Decay` | 0.0-1.0 | Decay time |
| `Env_DecayCurve` | 0.0-1.0 | Decay curve shape |
| `Env_Sustain` | 0.0-1.0 | Sustain level |
| `Env_Release` | 0.0-1.0 | Release time |
| `Env_ReleaseCurve` | 0.0-1.0 | Release curve shape |

### Modulation Matrix (`Mx_*`)

The mod matrix is encoded with three parameter families:

- `Mx_AssignDot_<0-N>` — Mod amount (0.5 = center/no mod, 0.0-1.0 = full range)
- `Mx_ColId_<0-N>` — Destination column identifier
- `Mx_Dot_<0-N>` — Source-destination intersection state

Additional:
- `MxDst_<name>` — Destination-specific parameters

## ZIP Container Format (Exported Presets)

Exported presets are ZIP archives with the naming pattern:
```
MiniFreak_Preset_<name>_<YYYYMMDD>_<HHhMM>.mnfx
```

Contents:
```
MiniFreak/User/<pack>/<preset_name>   ← text archive (may have trailing binary data)
<pack>.png                             ← thumbnail image (optional)
```

The text archive within the ZIP uses the same format as bare text files but may include additional binary data after the `0 0` end marker (wavetable or sample data).

### Critical ZIP Format Requirements

MiniFreak V is **very strict** about the ZIP format. Files created with standard tools like macOS `zip` or Python's `zipfile` will fail to import. Required format:

| Requirement | Correct | Broken |
|-------------|---------|--------|
| ZIP version | 1.0 (`0x0a00`) | 2.0 (`0x1400`) |
| Extra fields | None | Unix timestamps (UT, ux) |
| Directory entries | None (files only) | 0-byte folder entries |
| Compression | Stored (`0x00`) | Any |

**Always use `minifreak-tool build` or `minifreak-tool bundle`** to create presets and banks. These use the Rust `zip` crate with `SimpleFileOptions::default()` which produces the correct format.

**Do NOT use:**
- Shell `zip` command (adds extra fields and directory entries)
- Python `zipfile` module (uses ZIP version 2.0)
- macOS Finder compression (wrong format)

To verify a file's format:
```bash
# Check ZIP version (should be 0a00, not 1400)
xxd <file.mnfx> | head -1

# Check for extra fields (bytes 28-29 should be 0000)
xxd -s 28 -l 2 <file.mnfx>

# List contents (should have NO directory entries)
unzip -l <file.mnfx>
```

## Init Preset

The Init preset is the minimal default state (163 bytes):
```
22 serialization::archive 10 0 7 0 7 4 Init 4 User 66 4 User 7 Unknown
0 0 0 0 0 0 0 0 0 0 0 0 0 -1 0 0 0 0 0
1 0 0 0 4 Type 4 Bass
0 0 0 7 0 0 0 0 0 0 0 0 0 0
```

- 0 parameters (param count = 0)
- Single metadata entry: Type = Bass
- No sound data — all parameters use synth defaults

## Tools

### minifreak-tool

```bash
# Build a preset from a recipe JSON file (outputs importable ZIP)
# Uses the repo's safe default base unless --base is provided.
minifreak-tool build --output <new.mnfx> <recipe.json>

# Bundle multiple presets into a single bank
minifreak-tool bundle <preset1.mnfx> <preset2.mnfx> ... --output <bank.mnfx> --pack MyBank

# Show preset summary
minifreak-tool show <file.mnfx>

# Dump all parameters as JSON
minifreak-tool dump <file.mnfx>
minifreak-tool dump <file.mnfx> --prefix Osc1_

# Compare two presets
minifreak-tool diff <a.mnfx> <b.mnfx>
minifreak-tool diff <a.mnfx> <b.mnfx> --prefix FX

# Catalog all presets in a directory
minifreak-tool catalog <dir>                    # Summary
minifreak-tool catalog <dir> --format json      # Full JSON
minifreak-tool catalog <dir> --format groups    # Group counts
minifreak-tool catalog <dir> --group Osc1       # Filter by group
minifreak-tool catalog <dir> --discrete-only    # Enum parameters only
```
