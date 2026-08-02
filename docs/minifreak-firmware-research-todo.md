# MiniFreak firmware research TODO

The MiniFreak transport is already better understood at the wire than the
MicroFreak transport: the independent backend can use Collage over USB to read
the active edit buffer and all 512 saved slots, replay verified live deltas,
and store mapped changes with exact readback. Static analysis of the device
firmware may reveal more about resource ownership, parameter layout, empty-slot
behavior, wavetable capabilities, and the synth's internal architecture.

This is a deliberate follow-up to the evidence-ranked
[MicroFreak firmware notes](microfreak-firmware-notes.md). MiniFreak V's
compiled desktop binary and schemas are useful host-side evidence, but they are
not the MiniFreak hardware firmware and must not be described as such.

It also includes a host-side pass parallel to the
[MicroFreak MIDI Control Center analysis](microfreak-mcc-static-analysis.md).
The two tracks should meet only at a capture or independently reproduced
behavior:

```text
desktop host analysis -> expected request/validation
hardware firmware     -> candidate parser/resource behavior
USB capture/readback   -> promoted protocol fact
```

## Desktop host analysis

- [ ] Fingerprint the installed MIDI Control Center and MiniFreak V binaries by
  exact version, architecture, size, and SHA-256; never commit either binary.
- [ ] Inspect MIDI Control Center's MiniFreak product metadata and compiled
  dictionaries for protocol names, operation/subcommand mappings, validation
  errors, and user-invoked transfer paths.
- [ ] Locate the MiniFreak V Collage client, resource-name tables, framing and
  result-code dictionaries, and any runtime-initialized string tables. Do not
  assume raw on-disk C++ objects contain their final runtime values.
- [ ] Correlate host call sites with the already verified bulk endpoints,
  active-preset reads, saved-slot reads/writes, live frame-`0x13` deltas, and
  exact store acknowledgement.
- [ ] Trace any sample or wavetable UI/actions to establish whether current
  software contains a disabled, factory-only, or future-facing user-import
  path. Do not enable a writer from static evidence alone.
- [ ] Compare compiled host dictionaries with Collage schemas, the 917-control
  UI audit, and the `.mnfx` dictionary to identify fields that exist in only
  one layer.
- [ ] Build a fingerprinted, read-only extractor for durable findings. It must
  fail closed on unknown versions and publish derived names/mappings only, not
  proprietary executable bytes or assets.

## Artifact and architecture

- [ ] Locate an official MiniFreak hardware firmware/update artifact from the
  installed Arturia software or an official update package.
- [ ] Record the exact product version, member names, sizes, and SHA-256 hashes;
  do not commit or redistribute Arturia binaries.
- [ ] Identify the container, CPU architecture, load addresses, vector table,
  compression, signatures, and any independently stored or overlapping views.
- [ ] Make the static-analysis tooling section/view aware before trusting
  cross-references or nearby constants.

## Transport anchors

- [ ] Search for exact behavior already confirmed on hardware: Collage framing,
  vendor interface 0, bulk OUT `0x04`, bulk IN `0x83`, flow control, resource
  retrieval, resource store, and result/error codes.
- [ ] Find firmware-side references to the active-preset resource, saved-preset
  namespace, 128-byte slot metadata, 203-byte store chunks, and final-message-ID
  acknowledgement.
- [ ] Correlate every candidate with an existing passive MiniFreak V capture or
  a new read-only capture before promoting it to the transport documentation.
- [ ] Trace the frame-`0x13` live-delta path and determine whether the verified
  `offset = 128 + 2 * parameter_id` family is generated from one central table.

## Patch and resource internals

- [ ] Locate the active-buffer and saved-preset structures and compare them to
  the 3,328-byte hardware payload and the `.mnfx` parameter dictionary.
- [ ] Use the existing 158 exact mappings and the complete 917-control UI audit
  as anchors for discovering additional parameter IDs, encodings, and bounds.
- [ ] Find the firmware implementation of the payload XOR/complement checksum
  and document its call sites.
- [ ] Trace empty-slot create/remove behavior and explain why the observed
  resource-remove request returns `RESOURCE_RESULT_IO_ERROR`.
- [ ] Identify sample/wavetable resource handling and determine whether the 32
  observed `fwt` resources are factory-only on current firmware or whether a
  guarded user-import path exists.

## How the synth works

- [ ] Inventory readable engine, filter, effect, modulation, sequencer, arp,
  voice-allocation, and DSP strings/tables without redistributing proprietary
  data.
- [ ] Trace patch-load order: storage read, validation/migration, active-buffer
  activation, parameter fan-out, and DSP update.
- [ ] Distinguish control-rate models and metadata from audio DSP code; label
  inferred behavior separately from hardware-confirmed behavior.
- [ ] Compare firmware tables with the installed MiniFreak V UI-to-MNFX audit
  to catch any menu-diving or runtime fields still absent from file mapping.

## Evidence rules

- [ ] Give each finding one of the same labels used for MicroFreak:
  **confirmed**, **correlated**, or **candidate**.
- [ ] Reject flat scans or disassembly regions that do not have coherent call
  flow, data references, and a matching device or wire observation.
- [ ] Keep Arturia binaries, factory presets, schemas, and extracted proprietary
  assets out of the open-source repository; publish only independently derived
  facts, tooling, tests, and documentation.
- [ ] Use the normal reversible hardware contract for any mutation: fresh
  backup, smallest target, exact readback, restore, and restoration proof.
- [ ] Keep host and device claims separate: desktop disassembly proves what the
  official app constructs or expects; only firmware control flow plus USB
  behavior/readback can establish what the hardware accepts and does.
