# Transport and safe-write roadmap

## Current transport boundary

### MiniFreak

- Verified on firmware 4.0.1.53: USB identity, interface 0, bulk OUT `0x04`,
  bulk IN `0x83`, Collage flow control, and protobuf resource retrieval.
- Verified: standard notes, channel aftertouch, pitch bend, bank/program
  changes, MIDI clock/transport, and Arturia's documented CC surface.
- Verified live-session transport: linked MiniFreak V emits 17-byte Collage
  frame type `0x13` deltas containing a parameter ID and signed 16-bit value.
  Independent replay changes the physical active buffer without MiniFreak V.
- Verified: exported `.mnfx` file parsing and writing.
- Verified: independent lossless reads of the 3,328-byte active edit buffer and
  all 512 saved preset resources; 128-byte slot metadata format identified.
- Verified active-buffer resource store: MiniFreak V uses 203-byte chunks and
  a fresh incrementing Collage message ID for every chunk; the device
  acknowledges the final ID. Reusing one ID explains the earlier acknowledged
  no-op. Changed sound data now activates with exact canonical readback.
- Verified: payload checksum byte 4 is the complement of the XOR of every other
  byte; all captured payloads XOR to `0xff`.
- Verified from 48 naturally varied `.mnfx`/hardware pairs: 158 parameters
  have unique exact payload mappings. Forty use live-session deltas; the other
  118 are exposed with explicit `corpus_48_exact` evidence and use activating
  resource store. A newly promoted `Tempo` field was hardware-written, read
  back exactly, and restored exactly.
- Verified for 40 fields: the live-session parameter ID maps to
  hardware offset `128 + 2 * ID`, including multi-byte IDs. Twenty-seven
  additional mapped FX, keyboard, sequencer, and arpeggiator fields ignored
  session messages but are now writable through activating resource store.
  Shared JSON can push any combination while rejecting every unsupported byte
  difference.
- Verified persistence boundary: documented MIDI CC edits changed only the
  live buffer and disappeared after a hardware power cycle.
- Verified occupied saved-slot write: slot 256 was backed up, changed through
  activating resource store, read back exactly, restored, and read back at its
  original SHA. Empty-slot creation remains disabled because remove requests
  return `RESOURCE_RESULT_IO_ERROR` and an Init-like empty payload becomes an
  occupied Init slot when stored.
- Partial: raw preset bytes are retained in JSON, while friendly named offsets
  and conversion between the hardware payload and `.mnfx` parameter dictionary
  remain incomplete.
- Research: sample and wavetable resource naming/store behavior. The device
  reports 32 `fwt` entries, but firmware 4.0.1 does not advertise user
  wavetable import.

### MicroFreak

- Verified on firmware 5.0.0.36 through Elektroid: discovery, identity, preset
  listing/download, wavetable listing/download, sample and storage filesystems.
- Verified here: lossless plain `.mfp` and `.mfw` parsing/serialization.
- Verified project containers: `.mbp`, one-entry `.mfpz`, and complete
  `.mfprojz` project/bank archives round-trip through device-demarcated JSON.
  Twenty-five public project files comprising 8,832 preset objects validate
  the topology and historical filename variants. MIDI Control Center 1.23.0's
  library scanner also accepted an extracted generated project and displayed
  its two intended preset names. The archive-picker check is blocked by the
  current Control Center library state rather than a parser rejection: the
  only user project contains all 512 slots, Import is disabled, toolbar New
  Project creates nothing, and File > New reports `Couldn't write file /New
  Template`. Opening the associated `.mfprojz` from Finder reaches Control
  Center but does not add a visible library entry.
- Hardware fixture: preset slot 1 read as a 4,672-byte payload; wavetable slot
  1 read as 16,384 PCM bytes (32 frames x 256 samples).
- Verified structural decoding: after MIDI unpacking, firmware 5 exposes a
  self-named prefix with exact 16-bit values. A full 512-slot read found 320
  occupied presets, 107 distinct tags, a 96-field common core, and five clean
  version/feature layouts.
  The parser does not depend on absolute offsets and preserves the remaining
  sequencer body losslessly.
- Verified arbitrary wavetable upload: occupied slot 1 (`Ney`) was preserved;
  empty slot 2 accepted a renamed full 16,384-byte table, read back exactly,
  and was cleared back to empty.
- Verified saved-preset upload: slot 320 (`Munks`) was backed up, renamed,
  read back exactly, restored, and re-read at the original JSON SHA-256.
- Verified button-free saved-slot activation: slot 320 maps to MIDI bank 2,
  program 63 and was selected from the independent backend after `Munks` had
  been explicitly saved. Program change has no protocol acknowledgement, so
  the backend distinguishes a sent selection from a verified storage read.
- Verified official-app trace: an ad-hoc-signed disposable copy of MIDI Control
  Center 1.23.0 was passively instrumented, connected to firmware 5.0.0.36,
  and completed a read-only `Recall to Computer`. The action enumerated all 512
  headers and fetched all 320 occupied saved bodies. Timestamp-correlated call
  stacks prove that its header packets are `bank program 00` and its body
  starts are `bank program 01`; the body-start wrapper passes operation `19`
  and mode `1` into the generic bulk sender.
- Verified official startup boundary across two complete passive traces: each
  startup read 31 globals, all 512 preset headers, 16 wavetable headers, 64
  wavetable parts, and 128 sample objects, but zero preset bodies. All 208 bulk
  objects are accounted for, leaving no current/edit-buffer transfer hidden in
  normal Control Center synchronization.
- Verified hidden global reads: static recovery of MIDI Control Center's
  operation-`42` name table found twelve meaningful codes omitted from normal
  startup. Firmware 5.0.0.36 replied correctly to read-only operation-`43`
  requests for every one, raising the independent global inventory from 31 to
  43 raw-valued settings.
- Guarded global writes: operation `42` has no acknowledgement, so the new
  probe verifies target and inverse through operation `43` and compares all
  384 patch words. Keyboard Root Note code `46` was proven `0 -> 1 -> 0` with
  exact recovery and no live-table change. Hidden Automation Out code `23` was
  separately proven `1 -> 0 -> 1`. The installed description supplies 34
  domains and firmware clamps bound the other nine, so all 43 now support
  backup/readback-guarded writes while unknown display units remain raw.
- Verified firmware Init pseudo-slot: operation `19` at reserved bank 4,
  program 0 returns a normal 35-byte `Init` header and full 4,672-byte body.
  An exhaustive read-only sweep of bank 4/programs 1..127 and banks 5..127 at
  program 0 found no second response, while known slot 1 read identically at
  periodic fences and afterward. Selecting slot 320, applying documented live
  cutoff CC 23, and restoring slot 320 left the pseudo-slot header and body
  byte-identical at SHA-256
  `96e28f7618407491fc479624facf642e7ce198cd7d0b4c944d8cfd2f47e8a1b8`.
  It is now exposed as editable Init-template JSON and explicitly not claimed
  as current-buffer state.
- Verified independent transport: the new CoreMIDI reader produced slot-1 JSON
  byte-for-byte identical to Elektroid. The independent writer changed mapped
  cutoff bytes in slot 320, read them back exactly, restored `Munks`, and
  reproduced the original final JSON hash without Elektroid or an Arturia app.
- Verified self-describing editing: all firmware-5 preset tags are parsed by
  name instead of absolute offset. Across the full device corpus, 101 of 107
  tags have bounded integer, unsigned-normalized, bipolar-normalized,
  signed-offset, or live-destination interpretations; six intentionally remain
  raw-only. A one-unit tagged
  `VCF.Cutoff` edit was written, read back, and immediately restored with the
  original slot-320 payload hash reproduced exactly.
- Verified structured current-state projection: a diversity optimizer selected
  40 saved presets across all 107 structured tags, then paired each with the
  complete 384-word live table. Ninety-two varying tags initially had
  unambiguous exact live addresses. One saved sentinel mapped `Kbd.Hold`,
  `Kbd.Root`, `Arp.Dice`, and `Seq.XiceRst`; a second raw sentinel separated
  the three covarying chord offsets. Independent operation-49 writes confirmed
  all 15 newly assigned aliases. With normalized oscillator type, one read now
  returns 100 named current fields. Every experiment restored the chosen saved
  preset and complete live table exactly.
- Verified generic CC/live-table correlation: a guarded cutoff CC `23` probe
  changed exactly the three known live aliases, while Hold CC `64` changed no
  operation-`41` word. Both returned to an exact 384-word baseline. The later
   saved sentinel proved the distinct `Kbd.Hold` setter at `010D/020A/0303`, so
   the documented performance CC and saved field remain correctly separated.
- Verified sequence automation destinations and live motion: the first eight
  bytes of each 18-byte post-pattern trailer are four little-endian
  operation-41 addresses. All 320 occupied presets used only 17 mapped live
  addresses plus `FFFF`. `MotivSeq` hardware playback matched its first three
  Pattern-A destinations to outgoing CC 23/83/106 and changing cutoff,
  resonance, and envelope-decay live words. JSON now labels and edits these
  destinations while retaining the entire trailer.
- Verified sequence gate/length UI semantics: trailer byte 8 directly controls
  gate percentage, while byte 9 mirrors but does not independently control the
  tagged length. The structured JSON domains are now the device-facing
  `10..90%` gate and `4..64` steps, and normal edits synchronize both patterns'
  mirrors. A guarded byte-10/11 Pattern-B selection hypothesis failed and those
  bytes remain raw.
- Verified assignable-destination editing: the early public reader's two-byte
  group/control shape matches the firmware-5 tags, and every ID in the
  320-preset corpus equals a hardware-mapped operation-41 address. JSON labels
  the exact IDs; three independent operation-49 probes changed and restored
  Assign 1/2/3 with only their two aliases moving each time.
- Verified independent wavetable transport: an official read-only bank recall
  was captured; the CoreMIDI implementation reconstructed slot-1 `Ney` exactly,
  wrote `CodexProbe` to empty slot 2, read back the target archive hash, cleared
  slot 2, and confirmed slot 1 was unchanged.
- Verified independent sample transport: all 128 headers can be read
  without Control Center or Elektroid. Hardware slot 1 decoded as `Ney`,
  384,000 bytes at address 10,588,160 with checksum 170. The operation-59
  body reader reproduced all bytes. A guarded 384,000-byte upload to empty slot
  2 matched its complete independent readback, then `5A` cleared it back to
  empty. A final full slot-1 read retained the original SHA-256. Upload, clear,
  backup, exact readback, and empty-slot rollback are now independently
  hardware-verified.
- Verified offline wavetable containers: plain `.mfw` and one-entry `.mfwz`
  preserve archive metadata and PCM exactly. All 65 installed Control Center
  `.mfw` objects and Elektroid's public `.mfwz` fixture round-trip. A 16-slot
  wavetable-bank JSON model is byte-exact for the local factory bank;
  generated `.mfwbz` archive-picker import remains behind the same broken
  Control Center local-project state.
- Guardrail: empty Init preset archives have no 4,672-byte payload and Elektroid
  rejects their upload. Writes to those slots are refused because their empty
  state cannot be recreated by the same restoration path.

## Safe write contract

Any write command added to this project must perform this sequence:

1. Resolve exactly one device model, firmware, and transport endpoint.
2. Read the target slot and save a timestamped local backup.
3. Validate the incoming JSON or wavetable against that device's limits.
4. Write one explicit user slot; never infer a factory or broad range target.
5. Read the same slot back and compare decoded state and raw content.
6. On mismatch or timeout, restore the backup and verify restoration.
7. Report backup, write, readback, comparison, and restore status separately.

An accepted MIDI packet is not proof of persistent device state.

## Next MiniFreak protocol work

1. Extend the 158-field hardware map toward the complete audited `.mnfx`
   surface using installed parameter metadata plus coded corpus/sentinel
   families. The installed-version static audit now resolves all 917
   interactive Synth/Sequencer parameters: 852 are direct `.mnfx` fields and
   65 are Arturia-declared UI/runtime helpers, with zero unresolved patch
   controls.
2. Identify the empty-slot clear/create operation; occupied saved-slot writes
   are already guarded and verified, while firmware resource-remove returns an
   I/O error.
3. Capture a future official MiniFreak wavetable transfer if Arturia firmware
   exposes user import; until then, do not treat the 32 factory `fwt` entries as
   safe user slots.
4. Perform the evidence-ranked static-analysis pass described in the
   [MiniFreak firmware research TODO](minifreak-firmware-research-todo.md): find
   the official hardware artifact, map sections/views, anchor known Collage
   behavior, and correlate every promoted finding with USB or device evidence.

## Next MicroFreak work

1. Continue promoting the six raw-only tagged fields only where semantics
   are supported by firmware metadata, official documentation, or controlled
   host-driven evidence; 101 of 107 tags now have bounded editable values.
2. Finish the two reserved sequence bytes. Sequence A and B are exposed as
   two fixed 64 x 16-byte blocks. Bytes 0..3 are four editable note tokens,
   bytes 4..7 are their editable velocities, bytes 8..11 are four editable
   automation values, and byte 13 is their four-bit presence mask. Hardware
   MIDI-clock playback maps byte 12 to `0 = rest`, `1 = trigger`, and
   `2 = tie`; it is now typed and editable in JSON. Bytes 14..15 remain
   reserved/raw. High-byte non-note tokens remain explicit and lossless.
3. Find and document a current/edit-buffer request so live edits need not be
   routed through a saved slot. Normal Control Center startup is now ruled out
   as a source: it inventories headers and storage objects only. Operation-19
   selector probes `2..15`, shortened request forms, reserved banks, and the
   `7F/7F` pseudo-slot are also ruled out. The next safe candidate is an
   explicitly invoked official-app action. Firmware 5 contains overlapping
   stored code views (including a confirmed direct view and a `+0x8000` file
   displacement), so static candidates must be analyzed per view and matched
   to wire behavior before they are promoted to protocol facts.
   MIDI Control Center's generic Device menu does show working-memory store and
   recall entries, but both are disabled for MicroFreak and the product GUI XML
   has no binding for them; do not force-invoke those generic actions until a
   MicroFreak-specific code path is established.
   A branch-specific firmware pass over all 26 implemented top-level dispatch
   targets found no statically resolved path to the active Sequence A/B object;
   computed indirect flows remain open. As a fallback, host-driven USB-clock
   playback now proves the active pattern can expose notes, velocities,
   trigger/tie/rest timing, and emitted automation over MIDI without audio or
   panel input. The guarded `microfreak-sequence-playback-direct` command now
   writes those clock-relative events to JSON, backs up/restores Clock Source,
   and verifies all 384 live words after optional saved-slot recovery. Turn
   that verified behavioral capture into a lossless current-pattern projection
   if the remaining indirect firmware paths do not yield a direct dump.
4. Keep the independent preset and wavetable backends cross-checked against
   official-app traces and Elektroid as firmware evolves.
5. Continue the fingerprinted
   [MIDI Control Center static analysis](microfreak-mcc-static-analysis.md):
   the runtime-initialized `0x20..0x7F` operation-`42` names and all twelve
   meaningful read gaps are now recovered and hardware-confirmed; next recover
   value labels/ranges and follow the preset state machines.

### Remaining firmware SysEx queue

1. Capture the raw operation-`48` reply to the statically read-only
   operation-`49/6` kind-`0x13` selector family before changing the decoder.
   Selectors `0`, `1`, `2`, `3`, `4`, `5`, and `7` are visible in firmware;
   the first hardware reply contradicted the assumed alternate framing but was
   followed by cleanup and exact baseline recovery.
2. Trace callers for operation-`49/6` kinds `0x1E` and `0x18` before deciding
   whether their apparent runtime-mode/action behavior is safe to exercise.
3. Keep the named operation-`4C` clock/start/gate/MIDI boolean controls
   disabled until they have readback and rollback contracts.
4. Resolve the remaining computed indirect dispatch targets that could reach
   active Sequence A/B RAM; this is the strongest remaining direct-dump avenue.
5. Complete lower-priority operation-`49` subcommands `0..3`, operation-`47`
   subcommands `0B/0C`, and operation `5C` only after the routes above.

Operation `53` remains an unsafe, static-only mutation surface. Do not probe it
until its target, scope, and recovery path are independently established.
