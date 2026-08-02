# Freakout session handoff — 2026-08-02

This document is the restart point for the overall Freakout goal. It records
what the repository and connected hardware have actually proved, the most
recent MicroFreak findings, and the questions that remain open. Claims below
use the repository's capability vocabulary: **verified**, **guarded**,
**partial**, **research**, and **unsupported**.

## Overall goal

Build one MIT-licensed, clean-room toolkit that can:

1. discover an attached Arturia MiniFreak or MicroFreak automatically;
2. read a complete patch from files and hardware;
3. represent it losslessly as versioned JSON with explicit device-specific
   fields and evidence levels;
4. edit supported fields and write them back with backup, independent readback,
   and recovery;
5. expose current/unsaved patch state, not merely saved slots;
6. support MicroFreak user-wavetable preparation, download, and upload;
7. determine honestly whether MiniFreak hardware has a user-wavetable upload
   path; and
8. document enough of both transports that independent software can implement
   them without copying Arturia code or redistributing firmware.

Repository: <https://github.com/kmorrill/freakout>

Branch: `main`

Implementation baseline immediately before this handoff: `c04166d` (`Decode
MicroFreak status record selectors`).

## Current high-level status

| Area | MiniFreak | MicroFreak |
|---|---|---|
| Direct discovery | Verified USB/Collage discovery | Verified paired CoreMIDI discovery |
| Lossless file/JSON round trip | Verified `.mnfx` | Verified `.mfp`, `.mbp`, `.mfpz`; project-bank support partial |
| Saved-patch read | Verified, all 512 slots | Verified, all 512 slots |
| Unsaved/current read | Verified complete 3,328-byte active resource | Partial: all 384 parameter words, but not sequence/header/non-word state |
| Active editing | Verified for 158 mapped fields | Guarded for mapped live words; not a complete patch write |
| Saved-patch write | Partial; occupied slots only | Verified with backup/readback/rollback; empty Init slots refused |
| Named field coverage | Partial, 158 exact mapped fields | Partial, 107 structured tags; 101 semantically bounded |
| Sequence JSON | MiniFreak format coverage remains part of its separate audit | Both 64-step saved patterns are lossless and substantially editable; a few bytes remain raw |
| Wavetable files | Validation partial | Plain/archive/bank representations implemented |
| Device wavetable transport | Unsupported by current firmware evidence | Read and arbitrary guarded upload verified for all 16 slots |
| Samples | Not a current MiniFreak goal | Inventory, download, and guarded upload verified for 128 slots |

The generated capability report in `src/minifreak_patch/schema.py` is the
authoritative fine-grained status. Run `freak-patch capabilities minifreak` or
`freak-patch capabilities microfreak` rather than inferring support from a
device merely appearing in a MIDI list.

## Most recent MicroFreak result

### Operation `49/6`, kind `0x13` is now a decoded read-only status family

Firmware analysis identified seven getter selectors: `0`, `1`, `2`, `3`, `4`,
`5`, and `7`. The first hardware attempt returned operation `48` but contradicted
the assumed decoder. Preserving the raw frame revealed the missing layer:

```text
operation-48 payload = 06 7D + <flag byte + six MIDI-clean record bytes>
```

With that correction, live firmware 5.0.0.36 returned:

| Selector | Unpacked record | Structural result |
|---:|---|---|
| `0` | `FF1900000000` | kind `19`, selector `0`, value `0` |
| `1` | `FF1901000180` | kind `19`, selector `1`, value `384` |
| `2` | `FF1A50000824` | fixed kind-`1A` signature |
| `3` | `FF1B0027001D` | kind `1B`, raw word `0x0027001D` |
| `4` | `FF1C34325116` | kind `1C`, raw word `0x34325116` |
| `5` | `FF1D36363238` | kind `1D`, raw word `0x36363238` |
| `7` | `FF1907000CDE` | kind `19`, selector `7`, value `3294` |

This matches the firmware branch byte-for-byte. Selector `1` calls
`FUN_08022f88` and returns `384`, which equals the complete operation-`41` live
table size. That is a strong correlation, not yet a proven public name.
Selectors `3..5` serialize three separate 32-bit globals; their meanings are
still unknown and intentionally remain raw.

The corrected implementation was tested twice against hardware. Each seven-
selector session compared all 384 live words and all 43 named global settings
before and after. Both comparisons were exact, with zero changed addresses or
settings. The command is:

```sh
freak-patch microfreak-status-records-direct status-records.json
```

The JSON retains the complete raw frame, envelope fields, unpacked record,
structural 16/32-bit values, and state-verification results. Raw captures in
`/tmp` are not committed.

Implementation and evidence are in:

- `src/minifreak_patch/microfreak_midi.py`
- `src/minifreak_patch/cli.py`
- `tests/test_microfreak_midi.py`
- `docs/microfreak-sysex.md`
- `docs/microfreak-firmware-notes.md`

## MicroFreak transport model currently proved

- Standard Arturia SysEx prefix `00 20 6B 07 01` carries saved preset,
  wavetable, sample, and several bulk transfers.
- Alternate reply prefix `00 20 6B 07 7F` carries global, live-word, storage,
  and status replies with its own device-side sequence counter.
- Operation `19` reads saved preset headers/bodies. Firmware tracing rules it
  out as an unsaved-current reader.
- Operation `41` losslessly exports the complete 24-by-16 live parameter-word
  table.
- Operations `40` and `49/6` can change known live words within guarded encoding
  and recovery boundaries.
- Operations `42`/`43` write/read all 43 named firmware-5 global settings;
  writes use inverse readback because operation `42` has no acknowledgement.
- Saved preset, wavetable, and sample writes use fresh backup, exact readback,
  and rollback or verified cleanup.
- Host-driven USB clock can behaviorally observe the active pattern's emitted
  notes, velocities, automation CCs, and boundaries without audio or panel
  input. This is useful but not a lossless current sequence dump.

## Ranked MicroFreak open questions

### 1. Complete unsaved/current patch transfer

This is the largest gap. Operation `41` covers the live parameter object, but
the active Sequence A/B bytes, active header/metadata, and other non-word state
are missing. A complete result needs either:

- a direct serializer/dump route to the active object;
- a safe way to invoke the existing save serializer without committing flash;
  or
- a well-specified composite read that joins operation `41` with lossless
  sequence/header sources.

All statically resolved top-level dispatch paths have been checked without
finding a direct route to active Sequence A/B RAM at `0x20000EEC`. Computed
indirect dispatch targets remain the strongest direct-dump avenue. Do not call
the gap closed merely because direct references were exhausted.

### 2. Trace packed-record kinds `0x1E` and `0x18`

The kind-`0x1E` branch writes a three-state runtime field (`0`, `2`, or `4`)
and calls runtime update helpers. Kind `0x18` invokes `FUN_0802ECC0`. Neither
has a demonstrated reply or rollback contract. Trace callers, object ownership,
and relationship to active sequence/preset state before sending either one.

### 3. Resolve computed indirect calls

Resolve function-pointer targets reachable from bulk operations `16`, `17`,
`59`, and `5C`, plus control operations `1C`, `1D`, `40`, `42`, `47`, `49`, and
`53`. Test any promising target against the known active-sequence RAM object
and serializer call graph.

### 4. Finish saved-format semantics

- Six of 107 self-named structured fields remain raw-only.
- Seven legacy/UI-action candidates were constant across the observed bank and
  are not yet mapped to current words.
- Sequence step bytes `14..15` and trailer bytes `10..17` remain raw.
- Historical preset layouts are not automatically migrated to firmware 5.

Use corpus variation, firmware metadata, and reversible sentinel batches. Do
not assign names from covariance alone.

### 5. Lower-priority SysEx completeness

- operation-`49` subcommands `0..3`;
- operation-`47` selectors `0B` and `0C` semantic units;
- operation `5C` sample swap/reorder;
- operation `4C` clock/start/gate/MIDI Boolean controls.

Operation `53` remains static-only and unsafe. It must not be hardware-probed
until target, mutation scope, readback, and recovery are independently known.

### 6. Firmware-version compatibility

The strongest live evidence is firmware `5.0.0.36`. Preserve firmware identity
in reports and fail closed when packet shapes or field layouts differ. A device
acknowledgement is not enough; compare the intended object through its
independent read path.

## MiniFreak coordination boundary

This task was explicitly narrowed to MicroFreak because a separate agent and
computer were working on MiniFreak firmware. Do not duplicate or overwrite
that work when restarting. Reconcile its commits and evidence before changing
shared JSON or capability declarations.

The MiniFreak work still owes the overall goal:

- the final MiniFreak V UI-to-`.mnfx` coverage pass for menu-only or deeply
  nested fields;
- safe empty-slot creation/restore, or a clearly documented unsupported result;
- firmware-backed confirmation of Collage resource behavior;
- a definitive user-wavetable capability result rather than assuming the 32
  factory `fwt` resources are writable user slots; and
- preservation of explicit MiniFreak-only versus MicroFreak-only JSON fields.

Start with `docs/minifreak-firmware-research-todo.md` and
`docs/minifreak-ui-mnfx-audit.md` after incorporating the parallel agent's work.

## Evidence and publication boundaries

- This is clean-room work based on public implementations/documentation,
  passive captures, installed tool behavior, device experiments, and compiled
  firmware analysis—not Arturia source code.
- Firmware packages, extracted binaries, proprietary XML, captures, factory
  presets, decompiler databases, and local analysis dumps stay ignored and
  untracked.
- Derived protocol descriptions, original implementation, tests, and small
  structural examples are published under MIT.
- Elektroid is GPL-3.0 and remains an optional external command-line backend;
  its source is not copied into this MIT project.
- Every hardware mutation should use: fresh baseline, bounded target, explicit
  backup, independent readback, exact comparison, restore, and final comparison.
- Enumeration, packet acceptance, or audible change alone never proves a
  correct or persistent write.

See `NOTICE.md`, `CONTRIBUTING.md`, and
`docs/firmware-analysis-playbook.md` before publishing new reverse-engineering
artifacts.

## Restart checklist

1. Open `/Users/kevinmorrill/Documents/freakout` and verify `main` is clean.
2. Pull `origin/main`, then incorporate the separate MiniFreak agent's work
   deliberately rather than staging the entire worktree.
3. Enumerate connected hardware afresh; the last verified state for this task
   had MicroFreak directly connected and MiniFreak assigned elsewhere.
4. Run the full suite:

   ```sh
   PYTHONPATH=src python3 -m pytest -q -p no:cacheprovider
   PYTHONPYCACHEPREFIX=/tmp/freakout-pycache python3 -m compileall -q src tools
   git diff --check
   ```

5. Confirm capabilities:

   ```sh
   PYTHONPATH=src python3 -m minifreak_patch.cli devices
   PYTHONPATH=src python3 -m minifreak_patch.cli capabilities microfreak
   PYTHONPATH=src python3 -m minifreak_patch.cli capabilities minifreak
   ```

6. Resume MicroFreak with static analysis of kind `0x1E`, kind `0x18`, and
   computed indirect dispatches before considering another hardware mutation.
7. Re-run the read-only status capture only when useful; it is already proved
   and should not displace work on the current-buffer gap.

## Environment note

The prior session's repeated prompts were imposed by the managed macOS/Codex
sandbox for CoreMIDI, vendor USB, files outside the initially opened workspace,
and GitHub network writes. They were not uncertainty about user authorization.
Starting the new session directly in the Freakout repository and using a
full-access execution profile, if available, should reduce filesystem prompts.
CoreMIDI or USB may still require an operating-system approval that repository
code cannot bypass.

At this handoff point the full test suite passes: **176 tests**. The status-
record command was then re-run against the connected MicroFreak and again
verified exact live/global state.
