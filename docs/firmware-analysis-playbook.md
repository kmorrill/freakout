# Firmware-to-SysEx analysis playbook

This document explains how Freakout used compiled MicroFreak firmware to focus
clean-room SysEx research, and how to repeat the method for MiniFreak. It is a
methodology and handoff guide; the address-level MicroFreak results remain in
[`microfreak-firmware-notes.md`](microfreak-firmware-notes.md).

## Legal and evidence boundary

Arturia has not published the firmware source. This project analyzed an
official compiled update obtained by the device owner. Firmware packages,
extracted images, application binaries, decompiler databases, captures, and
factory presets stay local and are ignored by Git. Freakout publishes only
independently derived protocol facts, addresses, labels, analysis tools, and
code written for this project.

Do not describe disassembly as source code. A decompiler produces a fallible
representation of machine code with invented names and types. Do not copy a
large decompiler listing into this repository. Reduce it to a reproducible
claim such as “this pinned image dispatches operations `0x15..0x5D` through a
table at this address,” then independently test any external meaning.

Use three evidence levels throughout:

- **Static confirmed:** reproducible from the pinned compiled image, but not
  necessarily reachable through the device's external protocol.
- **Wire correlated:** static behavior matches a passive capture from an
  official application or another independently implemented client.
- **Hardware verified:** a bounded device experiment produced the predicted
  behavior and the complete relevant state was read back and restored.

Anything else is a **candidate**. An acknowledged packet is not proof of an
edit, and an edit-buffer change is not proof of a saved preset.

## What made the MicroFreak analysis productive

### 1. Start with public work and known traffic

Before disassembling, review maintained public implementations and write down
their licenses. For MicroFreak, Elektroid supplied a mature GPL implementation
of saved-preset, sample, and wavetable transfers. Freakout invokes Elektroid as
an optional external program but does not copy its source. Archived or
unlicensed projects were used only for protocol facts and comparison.

Capture ordinary official-app traffic before searching firmware. Known wire
operations make far stronger anchors than guessed UI strings. The useful
MicroFreak anchors included:

- manufacturer/model envelope `00 20 6B 07`;
- saved-object flow `19`, `15`, `16`, `17`, `18`, and `52`;
- wavetable/sample operations `54..5D`;
- live/global control operations `40..49`.

Record requests and replies separately. Preserve sequence numbers, declared
payload length, MIDI 8-to-7-bit packing, timing, and unsolicited replies.

### 2. Pin the exact artifact

Write down the package filename, size, SHA-256, member filename, member size,
and member SHA-256 before interpreting any address. The MicroFreak analysis is
pinned in `microfreak-firmware-notes.md`. The analyzer fails closed for tables
that are known only for that fingerprint.

Never let results from one firmware version silently become claims about
another. Treat a new hash as a new target until anchors and layouts are
re-established.

### 3. Identify architecture and load address

The MicroFreak main member has a 64-byte wrapper followed by a Cortex-M vector
table. The initial stack pointer and reset vector established ARM Thumb and a
linked base near `0x08020000`. Validate these facts from the image itself;
do not start by guessing a processor in the disassembler.

For a raw member loaded at linked base `B` with wrapper size `H`, the simple
coordinate is initially:

```text
member offset = linked address - B + H
```

That formula is only a starting hypothesis. The MicroFreak image contains
overlapping stored code views.

### 4. Keep overlapping stored views separate

This was the most important trap. Coherent MicroFreak routines were found in
the direct view and at file displacements `+0x8000` and `+0x14000`. The same
nominal linked address can therefore decode to plausible but unrelated code if
the wrong stored bytes are selected.

Freakout's analyzer treats each displacement as a separate view and never
merges instructions between them:

```sh
python3 tools/analyze_microfreak_firmware_dispatch.py \
  /path/to/microfreak-firmware.mff \
  --file-shift 0 --file-shift 0x8000 --file-shift 0x14000 --json
```

Use the same discipline in Ghidra or another disassembler. When a candidate
looks convincing, verify its file offset and bytes in the selected view before
following callers or renaming anything.

### 5. Seed conservative whole-image reachability

The analyzer seeds the Cortex-M vector table and aligned in-range Thumb
function pointers, then follows direct calls, branches, and fallthroughs. It
does not pretend computed calls are resolved. This yielded two strong dispatch
families:

- a bulk object-transfer switch covering `0x15..0x5D`;
- a control switch covering `0x1C..0x53`.

Decode table bounds, default targets, and every branch target before assigning
operation names. Inspect each dispatch target independently so unrelated
switch branches are not combined into a false call graph.

### 6. Use structure before semantics

For each handler, record facts in this order:

1. minimum payload length and bounds checks;
2. selector/subcommand byte offsets;
3. reply operation and exact reply length;
4. reads versus writes to RAM or storage;
5. direct callees and unresolved indirect calls;
6. constants, tables, and short labels referenced by that path;
7. only then, a candidate external meaning.

This separated operation `41`'s grouped live-word reader from operation `40`'s
limited writer, exposed operation `49/6` as a six-byte internal-record bridge,
and kept dangerous operation `53` disabled even though its command table could
be decoded statically.

### 7. Correlate static paths with passive wire behavior

Static analysis becomes useful when it predicts a packet already seen on the
wire. Examples from this session:

- the alternate `07 7F` reply envelope matched global-setting captures;
- bulk transfer operation roles matched official-app and Elektroid flows;
- operation `41` returned the firmware-described 24 groups by 16 words;
- operation `49/6`, record kind `02`, wrote a live address that operation `41`
  could read back;
- firmware-tagged preset metadata explained a signed chord-offset transform.

Negative evidence matters too. A full branch-specific scan found no statically
resolved path from the known dispatch targets to active Sequence A/B RAM.
Computed indirect targets remain open; the result is not proof that a private
dump command does not exist.

### 8. Replace serial knob experiments with coded sentinels

Once a lossless saved format and a live readback existed, use many unique,
valid sentinel values in one patch rather than changing controls one at a
time. The MicroFreak workflow combined:

- diversity-selected saved presets;
- vectors of firmware-tagged saved values;
- complete 384-word operation-`41` snapshots;
- documented MIDI CC batches with collision-resistant values;
- exact preset recall and full-table recovery checks.

Vector correlation mapped many fields at once and exposed aliases. A mapping
was promoted only after an exact multi-preset match or a guarded sentinel with
restore—not merely because two values moved together once.

### 9. Make every hardware experiment reversible

Use this sequence for any mutation:

1. Read and save a fresh baseline.
2. Read it again and require stability.
3. Choose one bounded change that differs from baseline.
4. Send the smallest request supported by current evidence.
5. Read back the exact target state.
6. Restore by the independently established inverse or saved resource.
7. Read back the complete relevant state and require byte/word equality.
8. Report target success and restoration success separately.

For saved resources, also preserve slot metadata and refuse empty slots unless
empty-state recreation is proven. For globals, read through the getter after
both target and inverse writes. For sequence playback, restore Clock Source
and recall the recovery preset, then compare all 384 live words.

### 10. Use behavioral observation when object dumps stay hidden

The active sequence object was not found through resolved SysEx paths. A safe
fallback temporarily selected USB clock, sent MIDI Start/Clock and a held
transposition note, and captured the MicroFreak's own outgoing notes,
velocities, automation CCs, and clock boundaries. Optional operation-`41`
snapshots at exact clocks correlated automation lanes without listening to
audio or pressing the panel.

This proved selected-pattern behavior, not a lossless sequence dump. Keep that
boundary explicit in the JSON capabilities.

## Reproducible MicroFreak breadcrumbs

The main code and documents to inspect are:

- `tools/analyze_microfreak_firmware_dispatch.py` — fingerprinted, multi-view
  static analyzer and dispatch/call-graph inventory;
- `docs/microfreak-firmware-notes.md` — addresses, corrected hypotheses,
  hardware correlations, and remaining branches;
- `docs/microfreak-sysex.md` — wire protocol promoted from captures and device
  proof;
- `docs/microfreak-mcc-static-analysis.md` — host-side application findings,
  kept separate from device-firmware claims;
- `src/minifreak_patch/microfreak_midi.py` — independent framing, readback,
  write guardrails, and recovery implementations;
- `tests/test_firmware_analysis.py` and `tests/test_microfreak_midi.py` —
  fingerprint, packet, boundary, and recovery invariants.

The remaining firmware-backed SysEx queue is:

1. Trace callers and ownership for kinds `0x1E` and `0x18` before sending them.
2. Establish readback and rollback for operation `4C` runtime controls.
3. Resolve computed indirect dispatches that may reach active Sequence A/B
   RAM.
4. Finish lower-priority operation-`49` subcommands `0..3`, operation-`47`
   subcommands `0B/0C`, and operation `5C`.
5. Keep operation `53` static-only until its mutation scope and recovery path
   are independently known.

The kind-`0x13` follow-up is a worked example of preserving contradiction. Raw
frames showed that the operation-`48` payload was not a bare seven-byte packed
record but `06 7D` plus that record. After correcting only that framing layer,
all seven selectors decoded byte-for-byte to the six-byte records constructed
by firmware. The session preserved exact before/after snapshots of all 384
live words and all 43 globals. External names for the returned runtime words
remain withheld because framing proof is not semantic proof.

## Applying the method to MiniFreak

The MiniFreak transport is different: patch resources use Arturia's Collage
protocol over vendor USB rather than the MicroFreak storage SysEx family.
Still, the firmware method transfers directly:

1. Locate an official MiniFreak hardware firmware artifact; do not confuse the
   MiniFreak V desktop executable with device firmware.
2. Record package/member hashes and keep every binary and analysis database in
   ignored local storage.
3. Identify architecture, vector table, wrapper, linked base, and any copied or
   overlaid stored views before trusting pseudocode.
4. Anchor searches with the independently observed Collage USB envelope,
   resource location values, active name `FF FF`, 203-byte store chunks,
   incrementing message IDs, and the final acknowledgement.
5. Find resource retrieve/store/remove dispatchers and trace their location,
   name, size, checksum, allocation, and persistence branches.
6. Correlate each static claim with existing passive USB captures and the
   independent active/saved readback implementation.
7. Prioritize the unresolved product goals: safe empty-slot recreation,
   additional current-field/session mappings, and whether hardware firmware
   exposes user wavetable storage or upload at all.
8. Re-run the MiniFreak V UI-to-MNFX audit after any new format finding so
   menu-only and sequencer fields are not silently missed.

Start with `docs/minifreak-firmware-research-todo.md`, then reuse the evidence
labels and experiment template above. Do not import MicroFreak operation
numbers into the MiniFreak investigation merely because both products are from
Arturia.
