# MiniFreak V UI to `.mnfx` completeness audit

This is the completion ledger for the installed MiniFreak V patch surface. It
separates controls stored in a preset from UI proxies, transport state, global
settings, visual feedback, and application chrome.

## Reproducible inventory

Run:

```sh
python tools/audit_minifreak_ui.py --check \
  --output work/minifreak-ui-audit.json
```

The audit reads Arturia's installed XML definitions without launching the app
or contacting hardware. For MiniFreak V 4.0.2.6369 it recursively scans 36 UI
files, including `screens/synth.xml`, `screens/sequencer.xml`, the main GUI,
popups, toolbar, browser, and side-panel definitions. It expands simple XML
loops and resolves string constants before comparing every `param` reference
with `presets/minifreak-default-base.mnfx` and the verified hardware map.

Nine conditional includes named by shared Arturia GUI templates are not shipped
with this product build. They are Analog Lab/FX/shared-shell variants plus the
runtime hardware-settings fragment. Their absence is reported explicitly and
does not hide any parameter reference in the installed Synth or Sequencer
screens.

## Installed-version result

| Layer | Distinct parameter names | Result |
|---|---:|---|
| Losslessly retained by baseline `.mnfx` | 2,486 | all round-trip in raw JSON |
| Official Arturia processor/internal definitions | 2,896 | attributes, choices, and ownership flags inventoried |
| References across all recursively loaded UI XML | 4,391 | patch screens and application shell separated |
| Interactive parameters on Synth/Sequencer screens | 917 | no unresolved template expressions |
| Direct interactive patch parameters present in `.mnfx` | 852 | losslessly readable/editable by exact name |
| Interactive Arturia UI/runtime helpers | 65 | deliberately absent from `.mnfx`; grouped below |
| Exact `.mnfx` fields mapped to MiniFreak hardware | 158 | 104 are direct interactive controls |
| Unresolved interactive patch controls | **0** | static installed-UI coverage gate passes |

The 852 count is intentionally large. It includes individual modulation-matrix
cells, sequencer notes/velocities, and automation-lane values rather than
collapsing each grid into one vague feature.

## Direct patch surface by family

| Family | Interactive `.mnfx` names | Hardware-mapped now | Static UI inventory |
|---|---:|---:|---|
| Oscillators | 16 | 12 | complete |
| Filter | 4 | 3 | complete |
| Envelope/VCA | 11 | 8 | complete |
| Cycling envelope | 9 | 7 | complete |
| LFO and shaper | 12 | 9 | complete |
| Voice allocation | 8 | 3 | complete |
| Keyboard, scale, chord | 16 | 1 | complete |
| Modulation matrix | 348 | 43 | complete |
| Macros/performance | 14 | 5 | complete |
| Arpeggiator/sequencer | 398 | 4 | complete |
| Effects 1-3 | 15 | 9 | complete |
| Audio input | 1 | 0 | complete |

“Complete” here means that every installed control has an ownership and exact
parameter-name classification. It does not claim that every enum label or every
hardware byte has been promoted to the friendly high-level recipe API.

## The 65 non-preset interactive helpers

Arturia marks these `notsetmodified=1`, `transmittedtoprocessor=0`, or both.
They are UI projections or commands, not missing `.mnfx` fields:

- Coarse/fine and derived selectors: `GUI_OSC1Coarse`, `GUI_OSC1Fine`,
  `GUI_OSC2Coarse`, `GUI_OSC2Fine`, `FilterType`, `Glide_Sync`, the two
  `LFO*_RateType` and two `LFO*_RateSyncedSpecific` controls, oscillator
  engine-specific display controls, and cycling-envelope curve proxies.
- Effect presentation: six synced-rate proxies and 33 `Opt1_*` through
  `Opt3_*` effect-preset selectors. Arturia's action XML links the rate proxies
  to `FX1_Param1` through `FX3_Param1`; preset choices expand into the normal
  effect parameters.
- Editors and selection context: chord-octave selection and
  `LFOShaperWaveAmplitude`; the actual chord offsets and shaper step arrays are
  serialized in `.mnfx`.
- Runtime/transport: `Seq_AutoPlay`, `Seq_IsRunning`, `Seq_LaunchDice`,
  `Seq_Record`, `VST3_CtrlSustainOnOff`, and `VST3_PitchBend`.

The machine-readable report retains every source file, element type, title,
definition flag, mapping attribute, inline choice, and referenced item list so
these classifications can be re-audited after an Arturia update.

## What remains

The installed-UI discovery pass is complete, but the wider reverse-engineering
goal is not:

1. Promote official mapping ranges and versioned item lists from the 852 direct
   names into friendlier device-aware JSON fields where that is useful.
2. Extend the current 158-field MiniFreak hardware map, prioritizing the compact
   non-grid controls before sequencer and modulation arrays.
3. Correlate sample/wavetable object/path metadata and any embedded archive
   members with device transfer operations.
4. Re-run this audit after a MiniFreak V update; version-dependent engine and
   effect item lists must remain explicitly versioned.

## Completion rule

The `.mnfx` UI-discovery gate passes when the generated report has zero
`patch_surface_unresolved` classifications and zero unresolved patch-surface
templates. Full project completion additionally requires tested friendly
encodings, hardware mappings, guarded read/write, and wavetable transfer; this
document does not collapse those separate evidence levels.

The current installed-source fingerprint is
`9888c33c0e294ea556b7e627d589a8a059a519b3a5f7da8758d8213b49f1ae6e`.
It covers every scanned Arturia UI/definition file, the baseline `.mnfx`, and
the repository hardware map. `--check` exits nonzero if either an interactive
patch control or a patch-surface template becomes unresolved after an update.
