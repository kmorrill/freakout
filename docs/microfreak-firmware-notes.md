# MicroFreak firmware research notes

These are clean-room static-analysis notes for the official compiled
MicroFreak 5 firmware. Arturia has not published the firmware source code.
Nothing extracted from the firmware is redistributed by this project.

The purpose of this work is to focus wire experiments, not to turn plausible
disassembly into protocol claims. Findings are labelled as **confirmed**,
**correlated**, or **candidate**:

- **confirmed** means an exact byte, address relationship, or control-flow
  behavior can be reproduced from the named firmware image;
- **correlated** means the static behavior also matches a passive hardware
  capture;
- **candidate** means it still needs a wire or device experiment.

## Analyzed artifact

- package: `microfreak_Firmware_Update_5.0.0.2084.mff`
- package SHA-256:
  `c2b405e3c8565b7b73b4dd06522559458190082a8ba633cc5f1bcc43dc64332c`
- main member: `nanowave_main__fw5_0_0_2084__2023_05_30.bin`
- main-member size: 473,760 bytes
- main-member SHA-256:
  `bfffd66e89bda4ca9b6e36bdc832703c177b82bed7015a1cf7dcb7e5f1493c14`

The `.mff` is a ZIP package containing the main image, three I/O-controller
images, a factory-wavetable image, and `info.json`. This agrees with the
independent package description in
[mf-utils](https://github.com/dcower/mf-utils). Its 64-byte wrapper is followed
by a Cortex-M vector table. The initial stack pointer is `0x20020000` and the
reset vector is `0x0805F849` (Thumb).

## Whole-image disassembly scope

The complete main member can be decoded as ARM Cortex-M Thumb machine code.
That is not the same as recovering source: this release is stripped, contains
code and data in overlapping stored views, and supplies no Arturia function or
variable names. Ghidra, radare2/Cutter, Binary Ninja, and IDA can all support a
whole-image project; Ghidra and radare2/Cutter are open source.

The repository's existing analyzer already performs a conservative form of
whole-image discovery. It seeds the Cortex-M vector table plus every aligned
in-range Thumb function pointer, follows direct control flow, and keeps the
direct, `+0x8000`, and `+0x14000` stored views separate. A Ghidra project must
use the same three-view discipline; importing the package as one flat binary would
silently attach convincing pseudocode to the wrong bytes. Firmware packages,
extracted members, and analysis databases remain local artifacts and must not
be committed. Only independently derived addresses, labels, call graphs, and
protocol facts belong in the open-source repository.

## Stored code views

**Confirmed:** the main member cannot be treated as one flat mapping from file
offset to linked address. Some coherent executable paths use the direct
mapping, the MIDI parser/envelope evidence uses bytes stored at a `+0x8000`
displacement, and the operation-`49`, runtime-control, and debug-console code
and data use a third `+0x14000` displacement. The
same nominal linked address can therefore produce unrelated, superficially
valid instructions or data when decoded from the wrong stored view.

`tools/analyze_microfreak_firmware_dispatch.py` now accepts repeated
`--file-shift` values and reports each view independently. It never merges
candidate instructions across views. It also reports every candidate as
`static_candidate_unconfirmed` until separate behavior proves it.

For firmware 5, a reproducible starting command is:

```sh
PYTHONPATH=work/vendor/python python3 \
  tools/analyze_microfreak_firmware_dispatch.py \
  microfreak_Firmware_Update_5.0.0.2084.mff \
  --file-shift 0 --file-shift 0x8000 --file-shift 0x14000 --json
```

## Arturia/MicroFreak envelope anchor

**Confirmed:** the exact four-byte protocol prefix `00 20 6B 07` occurs at
main-member file offsets `0x411E0` and `0x41924`.

**Confirmed:** in a coherent `+0x8000` code view:

- the first prefix is linked at `0x080591A0` and loaded at `0x08058F32`;
- the second is linked at `0x080598E4` and loaded at `0x08059868`;
- the routine beginning at `0x08058E18` explicitly constructs at least one
  message whose first five bytes are `00 20 6B 07 7F`.

Passive MIDI Control Center captures contain the same
`F0 00 20 6B 07 7F ... F7` envelope in MicroFreak global-setting replies, so
the byte pattern is **correlated** with real traffic.

**Correction:** full disassembly shows that `0x08058E18` constructs a series of
canned-looking frames, including values that do not match the observed private
storage protocol. No direct call or stored Thumb-function pointer to the
routine has been found. It may be dormant test/library code and is **not**
claimed as the live MicroFreak reply serializer or dispatcher. The finding
proves an exact prefix and a coherent shifted code view, but does not by itself
establish a firmware-to-wire execution path or identify a current-buffer
operation.

## MIDI parser and callbacks

**Confirmed:** the same shifted subsystem contains a byte-oriented MIDI parser:

- the routine at `0x080540A8` consumes individual MIDI bytes and distinguishes
  channel status, system-common, real-time, `F0`, and `F7` paths;
- the branch at `0x080541D2` compares the incoming byte with `0xF7`, converts
  equality to a Boolean, and passes it to the parser finalizer at
  `0x080598E8`;
- the setup routine at `0x08053BE4` initializes two parser objects and installs
  callbacks through `0x08054090`/`0x08059248`;
- one installed callback is `0x08047D4C`, which switches over eight internal
  parsed-event kinds.

The callback registration is useful control-flow evidence, but internal event
kind numbers are not SysEx operation bytes. In particular, a neighboring helper
stores the immediate `0x16`; that is **not** currently claimed to be the
operation-`16` transfer-part reply seen on the wire.

## Rejected candidate

A flat-view scan around `0x08026600` appeared to contain several known storage
operation values. Full disassembly shows a regular arithmetic/jump-table region
with byte comparisons spaced by four, shifts, and bit extraction. It is not a
trustworthy SysEx dispatcher and is deliberately excluded from protocol docs.

## Bulk object-transfer dispatcher

**Confirmed:** firmware 5 contains one table-based dispatcher beginning at
`0x0805ECC8`. It reads the operation byte from message offset 7, subtracts
`0x15`, bounds-checks the result against `0x48`, and executes a 73-entry Thumb
`TBH` table at `0x0805ED20`. The table covers operations `15` through `5D`
inclusive. All unimplemented entries share the default target `0x0805EE60`.

This is the authoritative switch for the bulk object-transfer subsystem, not
the top-level switch for every MicroFreak SysEx family. In particular, global
operations `42`/`43` and storage-maintenance operations have separate paths.
The implemented bulk cases are:

| Operation | Firmware target | Correlated role |
|---:|---:|---|
| `15` | `0x0805F0B0` | transfer start / flow control |
| `16` | `0x0805EF60` | data packet |
| `17` | `0x0805EF9E` | final data packet |
| `18` | `0x0805EFFC` | acknowledgement / next-packet request |
| `19` | `0x0805F018` | saved-preset read start |
| `52` | `0x0805F290` | preset header reply / write start |
| `54` | `0x0805EEB2` | wavetable-part write start |
| `55` | `0x0805F2FA` | wavetable-part read start |
| `56` | `0x0805EED0` | wavetable-header write/reset |
| `57` | `0x0805F190` | wavetable-header read |
| `58` | `0x0805EF0A` | sample-body write block |
| `59` | `0x0805F206` | sample-body read block |
| `5A` | `0x0805EF28` | sample-header write/reset |
| `5B` | `0x0805F116` | sample-header read / object selection |
| `5C` | `0x0805EF32` | swap/reorder two sample slots |
| `5D` | `0x0805EE66` | sample-upload allocation/preflight |

`tools/analyze_microfreak_firmware_dispatch.py` deterministically decodes this
table only when the extracted main member matches the pinned firmware-5 SHA.
Its JSON report labels this switch `bulk_object_transfer_only` and includes all
73 targets so implemented and default cases remain independently auditable.

### State-machine consequences

**Confirmed:** operation `19` combines its first two payload bytes as
`second + (first << 7)` and rejects values greater than `0x200`. Modes `0` and
`1` select header and body reads. This proves 512 saved addresses `0x000` to
`0x1FF` plus exactly one accepted address `0x200`, which is the observed
bank-4/program-0 firmware Init template. It also proves there is no second
pseudo-slot within this operation.

**Confirmed and hardware-correlated:** operation `59` reads two payload bytes,
fills a `0x1000`-byte buffer, emits operation `15`, and enters state `0x0A`.
Operation `18` permits exactly the read states selected by bit mask `0x2492`:
states 1, 4, 7, 10, and 13. Those are the preset, wavetable-part,
wavetable-header, sample-body, and sample-header read paths. On hardware,
operation `5B` selects a sample and resets its stream; successive `59` starts
then return successive 4 KiB blocks through `18`/`16`/`17`. Re-selecting with
`5B` resets the stream. Sample 1 (`Ney`, 384,000 bytes, 94 blocks) produced the
same complete SHA-256 before and after a neighboring-slot upload/clear cycle:
`1e762b9202002fd7f418a9508db83985b1eb76dd279ae2ca69f759422991fb6c`.

**Confirmed and hardware-correlated:** the complementary write state machine
uses `5D` for allocation, `5A` for directory-header reset/install, and `58` for
sequential 4 KiB body blocks. The 28-byte upload header contains a zero address,
little-endian size, a modulo-65536 little-endian PCM16 word sum, a 12-byte
maximum ASCII name plus NUL, the zero-based slot ID, and four trailing zeros.
Each body block is padded to 4 KiB and transferred as 146 operation-`16`
packets plus one operation-`17` packet after a `58 id 00 01` / `15` start.

Empty slot 2 accepted a 384,000-byte body named `CodexProbe`; the independent
operation-`59` reader returned the exact target name, size, checksum, and body.
The firmware allocated address `0x00281000` even though the source slot lived
at `0x00A19000`, confirming that physical placement is not derived from the
directory slot. A `5A` zero-length header then cleared slot 2 back to empty,
and a final full slot-1 read reproduced the original SHA-256. This promotes
operations `58`, `5A`, and `5D` from static/public-flow evidence to guarded
hardware proof while leaving `5C` swap/reorder deliberately unprobed.

**Confirmed statically:** operation `5C` accepts two indices from 0 through
127. For each occupied side, its helper copies the corresponding 4 KiB-backed
storage through a temporary buffer, rewrites the sample's embedded slot ID,
and swaps the two 24-byte directory records. It is the sample-slot
swap/reorder operation. It returns an operation-`18` acknowledgement without
entering a streaming state. Because this mutates both sample slots, it was not
sent to hardware and is not exposed by the independent backend.

## Global, storage, and device-control dispatcher

**Confirmed:** firmware 5 contains a second table-based SysEx dispatcher at
`0x0805AF74`. It reads the operation at message offset 7, subtracts `0x1C`,
bounds-checks through `0x53`, and uses the 56-entry Thumb `TBH` table at
`0x0805AFA0`. Unimplemented cases share target `0x0805B060`. Exactly ten
incoming operations have distinct handlers:

| Operation | Firmware target | Role or current best boundary |
|---:|---:|---|
| `1C` | `0x0805B18A` | enable private device-control reply session |
| `1D` | `0x0805B066` | disable private device-control reply session |
| `40` | `0x0805B16A` | live indexed 16-bit write/reply; write deliberately disabled |
| `41` | `0x0805B146` | three-byte indexed 16-bit query; returns operation `40` |
| `42` | `0x0805B0D2` | global-setting write |
| `43` | `0x0805B120` | global-setting read |
| `47` | `0x0805B010` | sample-storage statistics request |
| `49` | `0x0805B0E2` | maintenance subcommand dispatcher |
| `4C` | `0x0805B12E` | four-selector runtime sync control |
| `53` | `0x0805B072` | bounded hidden debug-console command input |

Operation `41` treats its second payload byte as a group and its third as a
word within that group, reads an unsigned 16-bit value from the active synth
parameter object, and returns the address/value pair as a five-byte
operation-`40` frame. The first payload byte carries the pair's 7-bit packing
flags. The paired operation `40` accepts the same address plus a 16-bit target
value and calls the engine's scaled parameter setter and notification path.

The object's pointer-table layout statically bounds this surface to 24 groups,
and a 16-bit validity mask per group bounds each group to 16 words. Hardware
confirmed the addressing discontinuity: the word after `000F` is `0100`, not
`0010` or `0080`. A single read-only session then returned all 384 addresses
from `0000..000F` through `1700..170F`, with every reply echoing its requested
address. The snapshot contained 139 nonzero words and 32 distinct raw values.
Several groups are identical or shifted copies, revealing internal pointer
aliasing that will help correlate engine fields with preset JSON. Semantic
names were then correlated in one 20-CC sentinel batch: 45 words changed,
covering the documented oscillator, filter, envelope, cycling envelope,
glide, arp, LFO, and spice controls. Reselecting saved slot 320 restored all
384 words exactly. The detailed address map is kept in the SysEx protocol
document and emitted in live-table JSON.

Operation `42` was then hardware-proven as the write half of the named global
dictionary. Its handler reads payload bytes 0 and 1 as code and value and emits
no acknowledgement. A guarded Root Note probe sent code `46` from `0` to `1`;
operation `43` independently returned `1`. The inverse write restored `0`, a
second read confirmed it, and both 384-word live snapshots matched the initial
table. This places Root Note in global state rather than operation-`41` patch
state on firmware `5.0.0.36`.

Arturia's installed MicroFreak device description was separately audited for
value domains. It covers 34 of the 43 recovered setting names, including
irregular MIDI routing values, all note/root/scale options, tuning, CV modes,
keyboard curves, microphone gain, and noise gate. The same firmware setter
function bounds the nine hidden settings: six boolean fields, Device ID
`0..126`, Aftertouch Offset `0..100`, and Lower MIDI Channel `0..15` or `126`.
All 43 are now domain-checked; values with unknown UI units retain raw labels.
The persistent setter writes a before-state JSON backup and requires
operation-`43` target readback, with verified inverse restoration on failure.
A reversible hidden Automation Out probe changed code `23` from `1` to `0`,
read it back, restored `1`, and left all 384 patch words unchanged.

An automated 13-preset saved/live corpus then compared each known saved-patch
raw field against every operation-`41` word vector. Twelve of thirteen fields
matched exactly across multiple distinct values. In addition to independently
confirming the CC map, it identified cycling-envelope rise shape at
`0105/0202/100C` and fall shape at `0108/0205/100F`. Oscillator type alone did
not match a raw word, agreeing with its packed/dependent representation. The
final slot-320 recall matched the starting 384-word table exactly, and the
offline correlation tool makes the evidence reproducible.

The oscillator-type exception is now resolved. A dedicated collector paired
all 320 occupied saved payloads with operation-`41` word `0000`; the final
slot-320 recall reproduced all 384 baseline words exactly. Runtime word `0000`
is the normalized engine index `round(index * 32767 / 22)`. All observed words
decoded to indices 1 through 17.

The saved payload's authoritative field is the firmware-tagged `VCO.Type`, not
the historical fixed byte at packed offset 14. `VCO.Type.metadata` records the
maximum engine index of the preset's originating layout (observed 12, 13, 14,
or 17), while `raw_u16` is the engine index normalized to that maximum. All 320
metadata-scaled saved indices matched the live runtime index. This explains why
the legacy byte saturated at `127` for several distinct engines.

Static firmware evidence independently establishes the complete 22-engine
runtime order. The control-view table begins with the BasicWaves name pointer
at file offset `0x4251C`; 22 records follow at a `0x1C` stride through the Hit
Grains pointer at `0x42768`. The order is BasicWaves, SuperWave, Wavetable,
Harmo, KarplusStr, V.Analog, Waveshaper, Two Op. FM, Formant, Chords, Speech,
Modal, Noise, Vocoder, Bass, SawX, Harm, WaveUser, Sample, Scan Grains, Cloud
Grains, and Hit Grains. The device corpus directly exercised only the first 17;
the connected saved bank simply contained no presets using indices 18 through
22. A complete CC 9 sweep subsequently activated every engine on hardware and
operation `41` returned the exact normalized runtime value at word `0000`.
CC values 94–99 selected WaveUser, 100–104 Sample, 105–110 Scan Grains,
111–115 Cloud Grains, and 116–121 Hit Grains. Vocoder, runtime index 14,
occupies the final CC range 122–127. Guarded operation-`49`/kind-`6` probes
also selected indices 18 through 22 directly and restored Vocoder with zero
differences in the 384-word live table.

Saved-preset support for the new engines requires the firmware-5 payload
layout, not merely a larger `VCO.Type.metadata` value. Arturia's installed
`New Presets 5.0` library has 64 occupied presets, all with maximum index 22
and a 110-field layout. Ten additional records cover sample selection/hash,
unison, chord offsets, snapshots, and keyboard mode. A guarded old-layout
metadata-only migration selected the wrong engine and was immediately
restored, so the JSON setter rejects that transformation.

A genuine firmware-5 Sample preset was instead edited to Scan Grains, written
to saved slot 320, downloaded with an exact wire-state match, selected, and
confirmed as live word `0000 = 29788`. The original saved payload and all 384
live words were restored exactly. This also exposed an archive/wire boundary:
the `.mfp` version tag is not carried by operation `52`, so the hardware
normalizes it when reconstructing a file. Verification compares the transmitted
name, category, `p1`, and all 4,672 payload bytes while reporting the local
wrapper difference separately.

A guarded operation-`40` hardware probe then set cutoff address `0101` from
`3382` to `254A`, with exact operation-`41` readback and matching changes at
aliases `0F0E` and `1008`. The direct handler confirms the write asymmetry: it
skips the first flag byte and combines the next four bytes without restoring
their high bits. Therefore requests can express only values whose high and low
bytes are both MIDI-clean. The probe detects this boundary and uses a named
saved-slot recall plus an exact 384-word comparison when the original value
cannot be restored through operation `40` itself.

A reusable CC/readback probe now performs the same complete-table comparison
around any documented control. Cutoff CC `23` value `49` changed exactly the
three mapped aliases `0101`, `0F0E`, and `1008` from `13186` to `12642`; slot
320 restored the original 384-word table exactly. Hold CC `64` value `127`
changed no operation-`41` word, and value `0` left the baseline exact. This is
evidence that the documented Hold performance CC is not a direct route to the
saved firmware tag `Kbd.Hold`. A later saved sentinel and operation-`49` probe
mapped that distinct tag at `010D/020A/0303` with exact restoration.

Operations `42` and `43` call the common global-setting implementation with a
two-byte selector/value pair or one-byte selector respectively. Operation
`47` recognizes payload `0A`, reads the storage statistic, and serializes a
nine-byte operation-`48` reply. This exactly matches the public Elektroid
read-only storage-statistics transaction.

Operation `47` recognizes selectors `0A`, `0B`, and `0C`, which call three
different storage-accounting routines before sharing the same operation-`48`
serializer. All three selectors were hardware-read under the bounded session:

| Selector | Hardware payload | Current interpretation |
|---:|---|---|
| `0A` | `47 7D 48 7F 19 00 60 05 00` | allocated sample time/space; 6,016 ms |
| `0B` | `47 7D 48 7F 19 00 00 79 00` | trailing contiguous space candidate |
| `0C` | `47 7D 50 7F 19 75 07 00 00` | fragmentation/reclaimable-page candidate |

Selector `0A` iterates the 128 sample directory records and sums the occupied
4 KiB allocation extents. Selector `0B` finds the highest-address occupied
record and compares its end with total allocation. Selector `0C` scans the
underlying storage and returns a page-based metric. The latter two labels stay
candidate until their units and UI meanings are correlated.

**Hardware verified:** in the initial bounded probe, operation `47` sent alone
produced no reply. Sending an empty operation `1C` first preceded a successful
response, after which `47 0A` returned
the nine-byte operation-`48` statistic in the alternate `00 20 6B 07 7F`
frame family. Sending empty operation `1D` then cleaned up the session. Neither
`1C` nor `1D` returned a frame. A later passive MIDI Control Center capture
obtained operation-`47` replies without visible `1C`/`1D` frames, so these are
documented conservatively as device-control session setup/cleanup: sufficient
for the independent backend, but not yet proven universally necessary.

**Confirmed:** the incoming handler at `0x08046F74` requires operation `49` to
carry at least two payload bytes. Payload byte 0 is the subcommand (`0..9`).
Subcommands 2 and 3 consume payload byte 1 as their value; this is clearer and
more exact than treating the two bytes as a semantic little-endian selector.
The dispatch uses the absolute-pointer table at `0x0805B0F8`. Its targets are:

| Subcommand | Thumb target | Role |
|---:|---:|---|
| `0` | `0x080474F4` | sets hidden global selector `2` to `1`, then sends and resets a compact event through the runtime object at `0x200035A4`; external meaning candidate |
| `1` | `0x08047066` | sets hidden global selector `2` to `0`; paired with subcommand 0, external meaning candidate |
| `2` | `0x080474E6` | writes payload byte 1 through hidden global selector `0x13`; external meaning unknown |
| `3` | `0x08047506` | writes payload byte 1 through hidden global selector `0x14`; external meaning unknown |
| `4` | `0x08047060` | no-op/unimplemented; jumps directly to the shared epilogue |
| `5` | `0x08047060` | no-op/unimplemented; jumps directly to the shared epilogue |
| `6` | `0x080471F0` | decodes a flag-packed six-byte state record and routes it by scope; kind `02` is the hardware-verified live-parameter setter |
| `7` | `0x08047196` | computes a diagnostic bitmask and returns an operation-`48` seven-byte record |
| `8` | `0x080472B4` | rebuilds runtime mirrors/pointers from the active parameter-descriptor object, then reinitializes dependent state; external trigger meaning candidate |
| `9` | `0x080474D8` | sample-memory defragmentation; public-flow correlated |

Those targets must be decoded from the firmware's `+0x14000` stored view;
decoding the same linked addresses from the direct or `+0x8000` view produces
unrelated but superficially plausible code. Elektroid sends operation `49`
payload `09 7F 00` and waits as long
as one hour for defragmentation, correlating subcommand 9's role. No operation
`49` branch other than subcommand `6`, kind `02`, has been sent by this project;
that narrow path is guarded by complete live-table readback and exact inverse
restoration. Every other branch remains presumed mutating until its boundary
and recovery behavior are established. Subcommand 7 is structurally read-only,
but its diagnostic routine actively exercises
hardware and internal state while constructing the bitmask, so it is not yet
treated as a safe probe.

Subcommand `8` is now bounded more precisely. Its source is the active
parameter-descriptor object at RAM `0x2001C898`, the same object walked by the
preset serializer. It copies numerous descriptor/configuration blocks into
their runtime mirrors, rebuilds a 6-byte-entry table, then calls helpers
`0x0802C928(..., 2)` and `0x0803DF60(...)`. It neither serializes a preset nor
references the active sequence object at `0x20000EEC`; a resolved-call walk of
29 functions also reaches no known sequence accessor. It is therefore a
mutating runtime rebuild, not a current-buffer read candidate, and remains
disabled because its external purpose and complete rollback boundary are not
established.

The deterministic analyzer now emits both dispatch tables and all ten
operation-`49` function pointers when the main image matches the pinned SHA.
Candidate labels stay explicitly marked where static control flow has not yet
established an external meaning.

A passive MIDI Control Center startup and preset-enumeration capture produced
31,536 outbound Arturia frames and no operation-`49` request. This is negative
evidence only: normal connection and preset listing do not appear to require
these maintenance branches, but their external meanings cannot be inferred
from absence alone.

**Hardware verified read boundary:** ordinary read-only operation `43` also
accepts the firmware's hidden selectors below the MIDI Control Center-visible
range. A complete `00..1F` snapshot succeeded. In the observed state selector
`02` was `0`, while selectors `13` and `14` were both `126`; this proves the
operation-`49` setters target readable bytes in the same global-state object.
Programmatically selecting preset 1 changed 87 of 384 live words but none of
the hidden selectors, and recalling slot 320 restored all 384 words exactly.
Separate reversible CC0 and CC32 sentinel probes also left every hidden
selector and live word unchanged. Therefore `13`/`14` are neither active-preset
identifiers nor MIDI bank-select latches. Their external meaning remains open,
and no operation-`49` write was sent.

#### Operation 49 subcommand 6 internal-event bridge

**Confirmed statically:** subcommand `6` requires a two-byte selector/scope
prefix followed by one flag byte and six MIDI-clean data bytes. Flag bits
`40 20 10 08 04 02` restore the high bits of the six data bytes respectively.
The resulting six-byte internal record is routed as follows:

| Scope | Behavior |
|---:|---|
| `00` | enqueue on internal route 0 |
| `01` | enqueue on internal route 1 |
| `02` | enqueue on internal route 2 |
| `7D` | invoke the control-record handler directly |
| `7F` | invoke the handler and enqueue the same record |

The record's first byte combines a source nibble and a low header nibble; byte
1 is the dispatch kind. For common kinds `00` and `02`, bytes 2/3 are a
big-endian address and bytes 4/5 are a big-endian value. Firmware constructors
prove that this exact six-byte object is the synth's internal event currency,
not merely a SysEx-specific wrapper. The direct handler recognizes kinds `00`,
`02`, `07`, `08`, `09`, `0A`, `13`, `18`, and `1E`, spanning indexed controls,
synth parameters, global bits, routing/matrix-like state, status replies, and
runtime modes. Several names remain functional candidates because the image is
stripped, but the payload packing and routing are exact.

This makes `49/6` potentially powerful but unsafe as a generic patch editor:
it can inject more than patch parameters and has no single rollback boundary.
The deterministic analyzer includes the unpacker, common record fields, route
table, and evidence-qualified kind roles. Hardware writes remain disabled
except for the following guarded known-parameter probe, which first had to be
backed up, read back through an independent path, and restored exactly.

**Hardware verified narrow write:** record kind `02` targets the same synth
object and scaled setter as operation `40`. A guarded request encoded cutoff
address `0101` and target `254A` as the doubled record value `4A94`, producing
the operation-`49` payload `06 7D 42 75 02 01 01 4A 14`. Operation `41`
readback returned `254A` at `0101` and matching changes at aliases `0F0E` and
`1008`. A second record restored the original `3382`, including its otherwise
inexpressible low byte `82`; the final comparison found zero differences in
all 384 words. The successful path did not need saved-slot recovery.

This proves kind `02` can set any nonnegative 15-bit target at a known live
address despite operation `40`'s request-byte limitation. The repository now
exposes only a guarded probe restricted to hardware-correlated addresses, with
complete-table readback, same-path restoration where representable, and saved
slot recovery as a fallback. Negative signed values, unnamed addresses, and
the other internal record kinds remain disabled.

The same guarded setter has now also exercised all three `Mat.Assign` fields.
The open-source reader's historical two-byte group/control destination shape
matches firmware 5: every destination ID observed across 320 presets is an
operation-41 address already named by the saved/live map. Writes to Assign
1/2/3 changed only their respective two aliases and restored the original IDs
with no final live-table differences.

### Operation 53 hidden debug console

**Confirmed statically:** operation `53` copies at most 43 payload bytes into
a bounded local buffer and passes the resulting text to the firmware's command
parser. Its exact top-level pointer/index table is linked at `0x08073CD8` and
stored in the `+0x14000` view. The 14 command names are:

| Index | Command |
|---:|---|
| 0 | `gpio` |
| 1 | `codec` |
| 2 | `cvout` |
| 3 | `help` |
| 4 | `flag` |
| 5 | `audio` |
| 6 | `filter` |
| 7 | `ioc` |
| 8 | `synth` |
| 9 | `boot` |
| 10 | `sync` |
| 11 | `oled` |
| 12 | `emc` |
| 13 | `mixer` |

Neighboring command strings include low-level peripheral, MIDI, DFU, audio,
calibration, and flash-test actions. This identifies operation `53` as a
developer/service console bridge, not a patch-transfer command. It is not sent
to hardware: commands such as `boot`, `gpio`, codec configuration, or flash
tests can reboot or mutate device state, and the handler exposes no general
rollback transaction. The version-pinned analyzer emits the table, addresses,
stored view, 43-byte bound, and this deliberate safety boundary.

### Operation 4C runtime sync controls

**Confirmed statically:** operation `4C` requires two payload bytes. The first
is a selector from 0 through 3. The second is reduced to a Boolean: values
`00..3F` become false and `40..7F` become true. The selected switch is shared
with a four-record command table at `0x08073D64` in the `+0x14000` view:

| Selector | Runtime control |
|---:|---|
| 0 | `clock` |
| 1 | `start` |
| 2 | `gate` |
| 3 | `midi` |

These names and the shared control flow identify this as low-level runtime sync
control rather than preset data. It remains unexposed because the corresponding
Boolean state has no independent readback yet; an operation-`4C` write could
not currently be restored with the same standard used for patch experiments.

## Next static targets

### Active-preset serializer and the operation-19 boundary

**Confirmed statically:** the physical-save path contains the inverse of the
tagged-preset loader. The active serializer is at linked address `0x08068A68`.
It constructs one bounded `0x1000`-byte preset image from:

- a 32-byte preset/header record;
- exactly `0x824` bytes of active Sequence A/B state, copied by the helper at
  linked `0x0803C4BC`; and
- every active named group/field descriptor and its current `uint16` value.

The field loop emits the same self-describing grammar already parsed by the
project: group marker/name, field marker/name, metadata byte, and little-endian
value. It reads values from the same group/field arrays used by operation `41`.
This independently confirms that the saved tagged fields and the live 384-word
table are two views of the same active parameter object. It also explains why
CC changes appear immediately in operation `41` before a preset is saved.

The serializer then unconditionally calls the slot writer at linked
`0x08059238`. That writer erases and writes exactly 4,096 bytes at
`(slot + 0x81) * 0x1000`. The complementary reader at linked `0x080594D4`
reads the same 4,096-byte flash slot; operation `19` calls this reader and has
no route to the active serializer. The serializer itself has two direct
callers (`0x0805053C` and `0x08052644`), both in save/UI workflows, and no
incoming SysEx-dispatch caller.

This narrows the current-buffer problem substantially: operation `19` cannot
be extended with a hidden slot number to obtain unsaved state. A complete
unsaved patch consists of the operation-`41` word object plus the active
`0x824`-byte sequence body and header/runtime state. We must either find a
separate read route for those non-word regions or a safely invocable serializer
path that does not commit its output to flash. Merely issuing operation `19`
after MIDI CC edits will continue to return the last saved slot.

The active Sequence A/B object is at RAM address `0x20000EEC`. A complete
whole-image pointer scan found 20 literal occurrences feeding 12 statically
recognized accessor functions in UI, sequencer, preset-load, and preset-save
regions. None of the literal references are in either known incoming SysEx
handler range. A resolved-call traversal from the operation-`19` handler
visited 16 functions and reached none of those accessors, the active preset
serializer, or the `0x824`-byte sequence-copy helper. This strengthens the
flash-only conclusion for operation `19` and shows that no known handler reads
the sequence object directly. It does not rule out an unresolved indirect
call, so the broader private-command search remains open.

A later branch-specific control-flow pass widened this from operation `19` to
every implemented top-level dispatch target: 16 bulk operations and 10
control operations. In the direct firmware view, no statically resolved path
reached any of the 12 known active-sequence accessors or directly referenced
RAM `0x20000EEC`. The scan followed calls, conditional branches, and
fallthroughs from each individual dispatch-table target so unrelated switch
branches were not merged. It still found computed flows that cannot be
resolved statically in bulk operations `16`, `17`, `59`, and `5C`, and control
operations `1C`, `1D`, `40`, `42`, `47`, `49`, and `53`. Operation `49`'s
nested table is analyzed separately; its runtime-rebind branch `49/8` also
does not reach the sequence object. This is strong negative evidence against
an ordinary direct dump command, not proof that an indirect private route is
impossible.

There is now a behavioral fallback for sequence research. With Clock Source
temporarily set to USB, a host can send MIDI Start/Clock plus a transposition
note and record the MicroFreak's own outgoing notes, velocities, automation
CCs, and note boundaries. This required no audio and no device-panel action.
It hardware-verified the saved sequence status byte and demonstrates that at
least the currently selected pattern can be observed programmatically even if
no direct sequence-object SysEx dump is found. Both probe runs restored Clock
Source to Internal and recalled slot 320 with all 384 live words exact.

That fallback now supports operation-41 snapshots at caller-selected clock
boundaries. On saved slot 5 `MotivSeq`, the 18-byte trailer immediately after
Pattern A begins `01 01 02 01 02 06 FF FF`: four little-endian live-word
destinations `0101`, `0102`, `0602`, and unused. During hardware playback the
device emitted cutoff CC 23, resonance CC 83, and envelope-decay CC 106 while
those exact live fields moved. A read-only sweep of all 320 occupied presets
found only `FFFF` plus 17 already mapped operation-41 addresses in these
destination words. This establishes the first eight trailer bytes as four
automation-lane destinations.

Corpus correlation then identified trailer byte 8 as gate percentage and byte
9 as a mirror of sequence length. Guarded saved-slot playback separated their
authority: changing byte 8 from 50 to 10 shortened every gate to the Note On
clock, but changing byte 9 from 64 to 4 did not change sequence length. Changing
the tagged `Seq.Length` value to its minimum while leaving byte 9 untouched
produced a four-step loop. The JSON/UI projection now applies the missing
minimum offsets (`Seq.GateLen` 10..90 and `Seq.Length` 4..64) and synchronizes
both mirrors during normal edits. A separate attempt to swap trailer bytes
10/11 did not select Pattern B; recall still played Pattern A, so bytes 10..17
remain explicitly raw rather than receiving a corpus-only guessed label. Every
probe restored the original slot-320 archive, Clock Source, and all 384 live
words exactly.

## Remaining firmware-backed SysEx avenues

The remaining queue is deliberately separated by evidence and risk:

1. **Operation `49/6`, record kinds `0x1E` (30) and `0x18` (24): runtime
   mode/action candidates.** The firmware suggests a three-state runtime value
   and a separate action-like path. They are plausible control surfaces, not
   hardware-proven protocol. Analyze their callers and state ownership before
   sending either record.
2. **Operation `4C`: clock/start/gate/MIDI boolean controls.** Firmware strings
   and branches provide useful names, but the operation has no demonstrated
   reply or rollback contract. Keep it disabled until each control has a
   bounded, reversible experiment and independent readback.
3. **Computed indirect dispatch flows:** these are the remaining plausible
   firmware route to the active Sequence A/B object at RAM `0x20000EEC` after
   all statically resolved paths were ruled out. Resolve indirect targets for
   bulk operations `16`, `17`, `59`, and `5C`, and control operations `1C`,
   `1D`, `40`, `42`, `47`, `49`, and `53`, before concluding there is no direct
   current-sequence dump.
4. **Lower-priority completeness work:** operation-`49` subcommands `0..3`,
   operation-`47` subcommands `0B/0C`, and operation `5C`. These may close
   framing or lifecycle gaps but currently have less direct evidence of
   unlocking patch editing.

Operation `53` remains static-analysis-only and unsafe to probe. Its mutation
and rollback boundaries must be established before any hardware experiment.

### Completed kind-`0x13` status-selector capture

The full selector set `0, 1, 2, 3, 4, 5, 7` is now hardware-correlated. The
earlier decoder expected a bare seven-byte packed record, but the actual
operation-`48` payload is nine bytes: `06 7D` followed by the flag byte and six
MIDI-clean record bytes. The unpacked records are respectively
`FF1900000000`, `FF1901000180`, `FF1A50000824`, `FF1B0027001D`,
`FF1C34325116`, `FF1D36363238`, and `FF1907000CDE`.

This exactly matches `FUN_08046C60`: selectors `0`, `1`, and `7` emit kind
`19` with a selector plus big-endian 16-bit value; selector `2` emits the fixed
kind-`1A` record; selectors `3..5` emit kinds `1B..1D` with three big-endian
32-bit globals. Selector `1` returned `384`, the exact number of words exported
by operation `41`. That correspondence is strong but does not by itself prove
a public semantic name for the getter. The other runtime words likewise stay
raw until caller or state correlation establishes their meaning.

The seven requests ran in one `1C`/`1D` session. Complete before/after reads of
all 384 live words and all 43 named globals were exact. The public
`microfreak-status-records-direct` command retains each raw frame, decoded
record, structural integer, and both state comparisons in JSON.

Address-coordinate rule: the header-stripped raw file is loaded at the real
`0x08020000` linked base, so raw offset is `address - 0x08020000`; the packaged
member adds its `0x40`-byte header. The Ghidra addresses are already linked
addresses. `tools/analyze_microfreak_firmware_dispatch.py --json` now emits
both address and file offset, the exact sizes, the slot formula, and the
current-buffer boundary, including this direct-reference/call-graph limit.

1. Resolve the remaining operation-`41` boundary. A diversity-optimized
   40-preset hardware corpus maps 92 varying structured tags exactly. Two bulk
   saved sentinels add four formerly constant tags and separate three naturally
   covarying chord offsets; normalized oscillator type yields 100 named current
   fields. Seven candidate legacy/UI-action tags remain constant in the
   320-preset bank, and the fixed sequence body is outside this word object.
   Guarded operation-`49` writes have independently exercised the sentinel
   mappings and restored the complete table exactly.
   The descriptor metadata `0xF7` is unique to those three chord offsets, and
   the firmware decodes it as `(raw - 0x4000) >> 7`, establishing the bounded
   integer range `-128..127` without guessing a display unit.
2. Resolve the remaining external meanings of operation-`49` subcommands
   `0`, `1`, `2`, `3`, `6`, and `8` without sending them; operations `4C` and
   `53` are already structurally classified and remain deliberately disabled.
3. Trace the sample allocation, defragmentation, and delete paths far enough to
   label their mutation and rollback boundaries without sending them.
4. Use storage and UI strings (`Preset saved`, `Current :`, `Save Preset`,
   `Sequence A`, and `Sequence B`) to trace internal active-preset ownership
   separately from the transport entry point.

The bulk switch establishes saved presets, globals, wavetables, sample headers,
and sample-body downloads. Operation `41` now supplies a complete raw snapshot
of the active synth parameter object, although the semantic mapping and any
additional non-word current-buffer state remain open. The bulk operation-`19`
bounds prove this is separate from the saved-preset body path.

## Parallel MiniFreak follow-up

The same style of static research is intentionally queued for the MiniFreak.
Its artifact discovery, transport anchors, patch/DSP questions, and evidence
rules are listed in the
[MiniFreak firmware research TODO](minifreak-firmware-research-todo.md).

The separate
[MIDI Control Center static-analysis note](microfreak-mcc-static-analysis.md)
records host-side framing, wavetable, and global-subcommand findings. Those
compiled desktop findings are useful correlates, but are not hardware firmware
source or proof of device-side implementation.
