# MicroFreak MIDI SysEx transport

This document records protocol facts used by the independent MIT-licensed
backend. It does not copy Arturia or GPL implementation code.

Evidence used:

- passive CoreMIDI capture of MIDI Control Center 1.23.0 recalling preset 1
  from a MicroFreak running firmware 5.0.0.36;
- comparison with the public protocol notes in
  [microfreak-reverse](https://github.com/francoisgeorgy/microfreak-reverse);
- comparison with the maintained
  [Elektroid MicroFreak connector](https://github.com/dagargo/elektroid);
- independent hardware read, write, exact readback, and restoration.

Static analysis of the official compiled firmware is tracked separately in
[MicroFreak firmware research notes](microfreak-firmware-notes.md). Those notes
distinguish confirmed binary structure, wire-correlated behavior, and candidate
control flow; firmware guesses are not promoted into this protocol document.

## File and project containers

MIDI Control Center uses the same Boost text object at several boundaries:

- `.mfp` and `.mbp` are plain single-preset objects;
- `.mfpz` is a ZIP containing one `0_preset` member;
- `.mfprojz` is a ZIP containing `project/bank/numbered-file.mbp` members.

Official and public projects contain explicit project and bank directory
entries. Preset files may be deflated, but standard stored/deflated ZIP 2.0
members are accepted by the parser. The writer emits both directories and
deflated preset members. Twenty-five public Arturia/community project archives
with 8,832 total objects round-tripped through JSON and back to the same
project model.

Control Center's directory scanner accepted an extracted generated project and
showed its two intended preset names. A direct archive-picker check remains
inconclusive because this installation cannot create a new local project:
File > New reports `Couldn't write file /New Template`, the existing 512-slot
user project leaves Import disabled, and opening the associated `.mfprojz`
from Finder produces no visible library entry. That app-local state is not
treated as evidence against the archive topology.

The first length-prefixed object string after the Boost header is opaque, not
a format-version enum. Observed values include `134`, `174`, `DEVBUILD`, and
many numeric identifiers. Empty slot objects may use a long project-derived
label where occupied presets use the hardware's 14-byte display name.

The 18-character binary field is the Control Center characteristics bitset.
The rightmost bit is `Acid`, followed by `Aggressive`, `Ambient`, `Bizarre`,
`Bright`, `Complex`, `Dark`, `Digital`, `Ensemble`, `Funky`, `Hard`, `Long`,
`Noise`, `Quiet`, `Short`, `Simple`, `Soft`, and `Soundtrack` at the leftmost
bit. JSON exposes both the exact bit string and the named list, and validates
that they agree.

## Official startup synchronization boundary

A second passive capture covered two complete, read-only MIDI Control Center
startup synchronizations against firmware 5.0.0.36. Each synchronization did
the following:

| Object family | Requests per synchronization |
|---|---:|
| Global-setting queries | 31 |
| Preset headers | 512 |
| Preset bodies | 0 |
| Wavetable headers | 16 |
| Wavetable parts | 64 |
| Sample objects | 128 |

The 208 started data transfers are accounted for exactly by 16 wavetable
headers, 64 wavetable parts, and 128 sample objects. No operation-`19` preset
body start appeared, and no unexplained bulk transfer remained that could be a
current/edit buffer. This proves the boundary of normal Control Center startup:
it inventories preset names and fully synchronizes sample/wavetable storage,
but it does not fetch saved preset bodies or the unsaved active patch. It does
not prove that the firmware lacks a separate undiscovered current-buffer
command.

A renewed August 2026 review of public implementations found no current-buffer
request. `microfreak-reader`, `microfreak-reverse`, Elektroid, and
`mcp-patchwork` all address saved bank/program slots. `mcp-patchwork`'s newer
reader is another implementation of the same operation-`19` start followed by
146 operation-`18` parts, while its MicroFreak writer remains explicitly
unimplemented. This independently narrows the search, but is not treated as
evidence that a private firmware operation cannot exist.

The public
[MicroFreak Reader](https://github.com/francoisgeorgy/microfreak-reader)
states the same boundary explicitly: it reads only saved presets, cannot read
current unsaved controller values, and does not read sequences. Its protocol
does not contain an alternate current/sequence request. Firmware tracing now
goes further by locating the active sequence object and showing no direct
reference from either known incoming SysEx handler range; unresolved indirect
calls are still being audited.

`tools/analyze_midi_capture.py` reproduces these counts from a passive log and
keeps incoming and outgoing operations separate.

An explicit `Recall to Computer` capture went further: Control Center issued
512 mode-`00` header reads and then mode-`01` body starts for all 320 occupied
saved slots. ASLR-normalized host call stacks and exact packet timestamps tie
the body requests to a wrapper that passes operation `19`, mode `1`, bank, and
program into the generic bulk sender. The only sibling direct caller passes
mode `2` while retaining bank/program and then serializes a preset to a local
file. Neither path is an unaddressed working-memory read.

## Sample directory

The independent backend can inventory all 128 sample slots without changing
sample memory. For each zero-based sample ID, operation `5B` with payload
`id 00 00` starts a directory-entry read and receives an empty operation `15`.
Operation `18` with payload `00` then receives operation `16` containing a
32-byte, 7-bit-packed header. Unpacking yields 28 bytes: little-endian address
and byte length, a little-endian 16-bit checksum, a 13-byte NUL-terminated
name, the device ID, and four trailing bytes. JSON preserves the complete raw
header as well as decoded fields.

### Sample-body download

Firmware analysis identified operation `59` as the missing read half of the
sample-body transfer, and a bounded read-only hardware experiment confirmed
it. Operation `5B` selects the zero-based sample ID and resets its stream.
For each sequential 4 KiB block, operation `59` with payload `id block` returns
an empty operation `15`; 147 operation-`18` requests then receive 146
operation-`16` packets and one operation-`17` packet. Each 32-byte MIDI packet
unpacks to 28 raw bytes, except that only eight bytes from the final packet
belong to the 4 KiB block. The assembled stream is truncated to the exact byte
length in the directory header.

Sample 1 (`Ney`) contains 384,000 bytes across 94 blocks. Two complete reads
matched exactly at SHA-256
`1e762b9202002fd7f418a9508db83985b1eb76dd279ae2ca69f759422991fb6c`,
and repeated directory headers were unchanged. The independent backend exposes
this as a lossless read.

### Sample-body upload and clear

The public Elektroid connector supplied an open-source transaction reference;
the implementation here was written independently around the already shared
wire protocol and verified against hardware. The guarded upload sequence is:

1. Read the target header twice; if occupied, download the complete body twice.
2. Read operation-`47` sample-memory statistics and reject insufficient space.
3. Send operation `5D` with `id 00 00`, then operation `15`.
4. Send the packed 28-byte header as operation `17`; operation `16 01`
   accepts allocation, followed by an empty operation-`18` completion reply.
5. Reset/install the directory entry with `5A id 00 00`, `15`, and the packed
   header in operation `17`.
6. For each padded 4 KiB block, send `58 id 00 01`, `15`, then 146 operation-
   `16` packets and one operation-`17` packet. Each packet carries the same
   28-to-32-byte MIDI packing used by downloads.
7. Complete the public/official flow with `5B id 00 01` and one 147-packet
   stream pass.
8. Independently download the stored header and complete body through `5B`,
   `59`, and `18`; compare name, exact byte length, checksum, and all PCM bytes.

The upload header stores a zero allocation address, little-endian byte length,
the modulo-65536 sum of little-endian PCM16 words, a maximum 12-byte ASCII
name plus NUL, and the zero-based slot ID. Firmware chooses the physical sample
address independently of slot number.

On firmware `5.0.0.36`, empty slot 2 accepted a 384,000-byte copy of `Ney`
named `CodexProbe`. Exact post-write readback matched SHA-256
`7b2e4f0e05534259a71afe3e542f7c75b6985be7640bb8aaa3148667b78775b0`.
The firmware allocated it at address `0x00281000`, while slot 1 remained at
`0x00A19000`, directly demonstrating the directory/allocation separation.
Clearing uses the same `5A` header-reset transaction with a zero-length header;
slot 2 returned to empty. A final complete download of neighboring slot 1
reproduced its original 384,000-byte SHA-256 exactly.

The guard writes a lossless local recovery artifact before mutation: the exact
28-byte original directory header followed by its exact PCM body. Failed write
or readback triggers upload of the saved body, or an empty-header reset when
the original slot was empty, followed by verification.

## Framing

All messages use 7-bit MIDI SysEx bytes:

```text
F0 00 20 6B 07 01 SS LL OP [LL payload bytes] F7
```

- `00 20 6B` is Arturia's manufacturer ID.
- `07 01` identifies the MicroFreak protocol family.
- `SS` is a sequence counter from `00` through `7F`; replies echo it.
- `LL` is the payload byte count.
- `OP` is the operation.

The official preset-1 header request captured from MIDI Control Center was:

```text
F0 00 20 6B 07 01 60 03 19 00 00 00 F7
```

## Bulk-operation catalog

Firmware 5's bulk-object dispatcher implements exactly the following cases.
An operation may be sent by the computer, returned by the device, or used in
both directions depending on the active transfer state.

| Operation | Role | Evidence |
|---:|---|---|
| `15` | transfer start / flow control | wire-correlated |
| `16` | data packet | wire-correlated |
| `17` | final data packet | wire-correlated |
| `18` | acknowledgement / next-packet request | wire-correlated |
| `19` | saved-preset read start | hardware verified |
| `52` | preset header reply / preset write start | hardware verified |
| `54` | wavetable-part write start | hardware verified |
| `55` | wavetable-part read start | hardware verified |
| `56` | wavetable-header write/reset | hardware verified |
| `57` | wavetable-header read | hardware verified |
| `58` | sample-body write block | hardware verified |
| `59` | sample-body read block | hardware verified |
| `5A` | sample-header write/reset | hardware verified |
| `5B` | sample-header read / sample selection | hardware verified |
| `5C` | swap/reorder two sample slots | firmware confirmed; deliberately unprobed |
| `5D` | sample-upload allocation/preflight | hardware verified |

All other table entries from `1A` through `51`, plus `53`, route to the same
bulk default branch. This does not mean those byte values are globally unused:
global settings and maintenance commands use separate dispatch paths.

## Global, storage, and device-control catalog

A second firmware dispatcher accepts these incoming operations independently
of the bulk-object state machine:

| Operation | Role | Evidence and safety status |
|---:|---|---|
| `1C` | device-control session setup | hardware verified as sufficient; necessity unresolved |
| `1D` | device-control session cleanup | hardware verified as sufficient; necessity unresolved |
| `40` | live indexed 16-bit parameter write/reply | hardware verified with MIDI-clean-byte guard |
| `41` | live grouped 16-bit parameter query | all 24 x 16 addresses hardware verified |
| `42` | global-setting write | hardware verified |
| `43` | global-setting read | hardware verified |
| `47` | sample-storage statistics request | firmware/public-flow correlated |
| `49` | maintenance subcommand | firmware confirmed; deliberately disabled |
| `4C` | `clock`/`start`/`gate`/`midi` runtime Boolean control | firmware confirmed; write disabled |
| `53` | hidden 43-byte debug-console bridge | firmware confirmed; deliberately disabled |

Operation `47` with payload `0A` returns operation `48` with nine payload
bytes. The independent backend preserves the complete raw payload and decodes
the same packed used-time counter as Elektroid into estimated used/free sample
time and bytes. This is a read-only query.

The independent backend uses a conservative session boundary: send empty operation `1C`,
send `47 0A`, receive the operation-`48` reply in the alternate
`00 20 6B 07 7F` frame family, then send empty operation `1D`. The alternate
reply uses a device-side sequence counter rather than echoing the request
counter. This complete flow is hardware verified and the backend always sends
`1D` in a cleanup path, including after a timeout. A passive Control Center
capture also received operation-`47` replies without visible `1C`/`1D` frames,
so the pair is not claimed to be universally necessary.

Operation `41` uses payload `flags group word`; the current value is returned
as operation `40` payload `flags group word value-hi value-lo`. Each high bit
stripped for MIDI is restored from flag bits `40`, `20`, `10`, and `08`,
respectively. Static analysis bounds the active synth object to 24 group
pointers with 16 words per group. Hardware returned all 384 addresses from
`0000..000F` through `1700..170F`; the next address after `000F` is `0100`.
The backend can export the complete table as lossless JSON. Mapping those raw
words to named patch fields is the next correlation step. Operation `40`
enters the engine's setter/notification path and operation `49/6` kind `02`
reaches the same live setter through a fully packed internal record. Both now
have narrow guarded write/readback/restore proofs at semantically known
addresses; neither is a general unmapped-address write API.

A collision-resistant batch then sent 20 documented MIDI CCs with distinct
values, read the table once, and reselected saved slot 320. Forty-five words
changed and all 384 returned exactly to baseline after recall. The JSON export
now labels these hardware-correlated addresses:

| Parameter | Live-table addresses |
|---|---|
| `osc.type` | `0000`, dependent words `0B0D`, `0C07`, `0D01` |
| `osc.wave`, `osc.timbre`, `osc.shape` | `0001`, `0003`, `0005` |
| `envelope.attack`, `.decay`, `.sustain` | `000B/0601`, `000C/0602`, `000D/0603` |
| `filter.env_amount` | `000F`, `0605` |
| `filter.cutoff` | `0101`, `0F0E`, `1008` |
| `filter.resonance` | `0102`, `0F0F`, `1009` |
| `cycling_env.rise` | `0104`, `0201`, `100B` |
| `cycling_env.rise_shape` | `0105`, `0202`, `100C` |
| `cycling_env.fall` | `0106`, `0203`, `100D` |
| `cycling_env.hold` | `0107`, `0204`, `100E` |
| `cycling_env.fall_shape` | `0108`, `0205`, `100F` |
| `cycling_env.amount` | `0109`, `0206` |
| `glide` | `010A`, `0207`, `0300` |
| `arp.rate_sync`, `.rate_free` | `030A/0402`, `030B/0403` |
| `spice` | `030E`, `0406` |
| `lfo.rate_sync`, `.rate_free` | `040B/0501`, `040C/0502` |

The continuous controls normally appear as identical aliases; oscillator type
instead changes a packed word plus three derived signed values. These labels
prove live-engine correlation.

A second, independent bulk correlation paired 13 saved presets with their
complete selected live tables. Twelve of 13 published saved-patch fields
matched live-word vectors exactly across 4 to 13 distinct values apiece and
slot 320 restored with zero differences. This reconfirmed the CC-derived map
and added the menu-only cycling-envelope shape fields at
`0105/0202/100C` and `0108/0205/100F`. Oscillator type was the sole non-exact
field, consistent with its already observed packed word plus dependent-state
representation. `tools/analyze_microfreak_saved_live_corpus.py` reproduces the
vector comparison from a captured corpus without requiring firmware files.

### Diversity-optimized full structured/live correlation

The 13-preset pass covered the original fixed-offset fields. A second-stage
optimizer instead decoded all 107 self-named structured fields across the 320
saved presets, then greedily chose 40 presets that maximize distinct
metadata/value pairs. Reading every chosen preset's complete 384-word live
table produced these stronger results:

- all 40 preset selections completed without a hardware button press;
- the final slot-320 recall reproduced all 384 baseline words exactly;
- 95 structured fields varied and matched one or more live-word vectors
  exactly;
- 92 fields have unambiguous addresses;
- `Gen.ChOffs1`, `Gen.ChOffs2`, and `Gen.ChOffs3` always covaried in natural
  presets, leaving six candidate words for a controlled sentinel;
- `VCO.Type` is the only varying field without raw equality because live word
  `0000` uses the separately proven index-normalized-to-22 encoding;
- 11 UI/runtime tags never varied in the connected 320-preset corpus, so this
  pass alone assigned none of them to coincident zero words.

The unambiguous map includes filter type, bend range, arp modes/range/swing,
LFO shape/retrigger, keyboard octave/glide/scale/velocity, all seven modulation
rows and their sources, assignable destinations, sequence length/gate/smooth
flags, preset volume/polyphony/unison fields, and vocoder hiss controls. The
The initial map therefore exposed 93 named fields including oscillator type.

This correlation was independently exercised as a setter. Guarded
operation-`49`/subcommand-`6` kind `02` changed `VCF.Type` at primary address
`0100` from `32767` to `0`; aliases `0F0D` and `1007` changed to the same target.
Writing the original value back restored all three, and the final complete
table had zero differences. This proves mapped menu-style fields are actionable
through the same internal event bridge.

### Bulk sentinel for constant tagged fields

One guarded saved-preset probe assigned collision-resistant target values to
four fields that were zero in all 320 factory presets: `Kbd.Hold = 1`,
`Kbd.Root = 5`, `Arp.Dice = 0.314`, and `Seq.XiceRst = 1`. The target payload
read back exactly, selecting it changed only nine live words, and restoring the
original Munks payload reproduced both saved and complete active state:

| Field | Live addresses | Target raw value |
|---|---|---:|
| `Kbd.Hold` | `010D`, `020A`, `0303` | 32767 |
| `Kbd.Root` | `020E`, `0307` | 14894 |
| `Arp.Dice` | `030F`, `0407` | 10289 |
| `Seq.XiceRst` | `070D`, `1201` | 32767 |

Four independent operation-`49/6` probes then wrote each primary address. Each
changed exactly the listed aliases, read back its target through operation
`41`, restored the original through the same setter, and finished with zero
differences across all 384 words.

A second guarded saved-preset sentinel used raw values `12000`, `20000`, and
`28000` to separate the three chord-offset tags that natural presets kept
equal. Slot 208 `Boarding` produced the exact mapping below:

| Field | Live addresses | Target raw value |
|---|---|---:|
| `Gen.ChOffs1` | `050D`, `0708` | 12000 |
| `Gen.ChOffs2` | `050E`, `0709` | 20000 |
| `Gen.ChOffs3` | `050F`, `070A` | 28000 |

The sentinel preset and original preset each read back exactly, and the final
live table had zero differences. Three independent operation-`49/6` probes
then changed exactly each field's two aliases and restored them through the
same setter. The structured command now emits 100 named fields: 99 tagged
fields plus oscillator type. The seven still-constant tags
are `Gen.Panel`, `Mat.MatBtn`, `Mat.MatEnc`, `Sys.PrsetBt`, `Sys.PrsetID`,
`Sys.Save`, and `Sys.Utility`. JSON classifies the six `Mat`/`Sys` tags as
`ui_action_placeholder_candidate` and `Gen.Panel` as
`legacy_panel_state_candidate`. This is deliberately a candidate role, based
on their names and groups, all-zero values across 320 saved presets, and lack
of an operation-41 mapping—not firmware-confirmed behavior. The interpreted
editor refuses them; exact raw preservation and the explicit raw research
editor remain available.

Static firmware analysis also resolves the chord-offset number encoding. The
three descriptor records use metadata byte `F7`, and the firmware converts
their stored value with `(raw - 0x4000) >> 7`. Thus `0000`, `4000`, and `7F80`
decode to `-128`, `0`, and `127`. No other tag in the 320-preset corpus uses
metadata `F7`. JSON therefore exposes these as bounded
`signed_offset_shift7` integers while leaving their musical unit unnamed;
neither the formatter path nor the factory corpus proves whether `127` has a
special inactive meaning.

This does not yet authorize negative signed values, those seven action-like
tags, or sequence-body
mutation through the live-word setter.

### Direct MIDI CC versus operation 41

`microfreak-live-cc-probe` generalizes the earlier sentinel experiment. It
captures all 384 words, sends one documented CC, captures all words again,
sends a caller-supplied inverse, and compares the complete baseline. A saved
slot recall is the guarded fallback when the inverse CC cannot reconstruct the
preset's exact value.

Two hardware controls establish both outcomes on firmware `5.0.0.36`:

- cutoff CC `23`, value `49`, changed `0101`, `0F0E`, and `1008` from `13186`
  to `12642`; an intentionally nonmatching inverse caused slot 320 recall, and
  all 384 words then matched the baseline;
- Hold CC `64`, value `127`, changed no operation-`41` word; value `0` returned
  an already identical table without preset recall.

The second result proves documented CC `64`, with no notes held during this
probe, is not the saved `Kbd.Hold` setter. The later saved-preset sentinel and
operation-`49` probe mapped `Kbd.Hold` independently at `010D/020A/0303`.

### Oscillator engine encoding

The old published fixed byte is only an encoded Type-control position. It is
not a firmware-5 engine ID: in the connected bank, byte value `127` represented
runtime engine indices 12, 13, 14, and 17. The authoritative saved field is the
self-describing `VCO.Type` record. Its metadata byte records the maximum engine
index available when the preset was written, and its 16-bit value is
`round(engine_index * 32767 / metadata)`. The normal structured-field decoder
therefore recovers the integer engine index without guessing the preset's
firmware generation.

`collect-microfreak-oscillator-types-direct` read all 320 occupied saved
payloads, selected each preset, and read only live word `0000`. Every live word
landed on `round(engine_index * 32767 / 22)`, and all 320 tagged `VCO.Type`
values decoded to the same engine index. The sweep observed indices 1 through
17 and restored the complete 384-word slot-320 baseline with zero differences.
`tools/analyze_microfreak_oscillator_type_corpus.py` independently reproduces
those checks from the lossless capture.

Firmware's 22-record oscillator table is contiguous at control-view file
offsets `0x4251C..0x42768`, with a `0x1C` stride. Its name pointers establish
the runtime order. A complete hardware CC 9 sweep independently activated all
22 entries and read each resulting value through operation `41` word `0000`:

| Index | Engine | CC 9 values | Live word `0000` |
|---:|---|---:|---:|
| 1 | BasicWaves | 10–11 | 1489 |
| 2 | SuperWave | 12–16 | 2979 |
| 3 | Wavetable | 17–22 | 4468 |
| 4 | Harmo | 23–27 | 5958 |
| 5 | KarplusStr | 28–33 | 7447 |
| 6 | V.Analog | 34–38 | 8936 |
| 7 | Waveshaper | 39–44 | 10426 |
| 8 | Two Op. FM | 45–49 | 11915 |
| 9 | Formant | 50–55 | 13405 |
| 10 | Chords | 56–60 | 14894 |
| 11 | Speech | 61–66 | 16384 |
| 12 | Modal | 67–71 | 17873 |
| 13 | Noise | 72–77 | 19362 |
| 14 | Vocoder | 122–127 | 20852 |
| 15 | Bass | 78–82 | 22341 |
| 16 | SawX | 83–88 | 23831 |
| 17 | Harm | 89–93 | 25320 |
| 18 | WaveUser | 94–99 | 26809 |
| 19 | Sample | 100–104 | 28299 |
| 20 | Scan Grains | 105–110 | 29788 |
| 21 | Cloud Grains | 111–115 | 31278 |
| 22 | Hit Grains | 116–121 | 32767 |

Vocoder is runtime index 14 but occupies the final knob/CC range. The CC sweep
therefore proves both the firmware runtime index and the user-control ordering;
they are intentionally not the same sequence. The collector retained every
operation-`41` reply and recalled slot 320 afterward with no differences in
the complete 384-word table. Guarded operation-`49`/kind-`6` probes separately
set indices 18 through 22 and restored the original Vocoder value exactly.

Canonical JSON `osc.type` now uses `VCO.Type` and accepts the integer index.
The legacy byte remains available only as corpus evidence. Historical payloads
advertise a maximum engine index of 12, 13, 14, or 17 in
`VCO.Type.metadata`; changing that maximum to 22 is not a valid layout
migration. A guarded attempt loaded the wrong runtime engine and was restored,
so cross-layout migration remains disabled.

The installed Control Center `New Presets 5.0` set provides genuine 22-engine
payloads. Its 64 occupied presets all use `VCO.Type.metadata = 22` and a
110-field structured layout, adding sample, unison, chord, snapshot, and
keyboard-mode records to the older 100-field layout. Starting from one such
payload, a guarded JSON edit from engine 19 Sample to engine 20 Scan Grains was
written to slot 320, read back with the exact transmitted header and 4,672-byte
payload, selected, and observed as live word `0000 = 29788`. The original
Munks payload was then restored byte-for-byte and all 384 live words matched
the baseline.

The archive's leading version tag is not transmitted by operation `52` and the
device reconstructs it with its default value on download. Direct-write
verification consequently compares the actual wire projection—name, category,
`p1`, and full payload—and reports archive-wrapper normalization separately.

### Guarded live-word write

Operation `40` is now hardware-proven as a live setter. A bounded probe wrote
cutoff address `0101` from `3382` to the previously CC-correlated target
`254A`; operation `41` read back `254A`, and aliases `0F0E` and `1008` changed
with it.

The request encoding is asymmetric with the reply. Replies use the flag byte
to preserve the high bit of each address/value byte. The incoming firmware
handler skips that flag byte and consumes the following four bytes directly,
so every request byte must already be 7-bit clean. `254A` is representable;
the original `3382` is not because its low byte is `82`. Treating reply packing
as a write inverse produced `3302`, and the complete-table verifier caught the
three incorrect cutoff aliases. Saved slot 320 was recalled and all 384 words
returned exactly to baseline.

The guarded probe now rejects non-representable targets before sending, reads
the whole table after the target, restores through operation `40` when the
original is representable, otherwise recalls an explicitly supplied recovery
slot, and requires an exact 384-word final comparison. This establishes useful
live editing but not arbitrary 16-bit operation-`40` writes.

Selector `0A` is not the only operation-`47` statistic. Firmware and hardware
both confirm selectors `0B` and `0C`; they return the same nine-byte
operation-`48` shape and appear to describe contiguous and fragmented sample
space. Their exact units remain deliberately unlabeled. Raw hardware payloads
are preserved in the firmware notes.

Operation `49` contains ten nested subcommands. Correctly decoding its targets
requires the firmware's `+0x14000` stored view. Static analysis now classifies
all ten structurally: `0`/`1` toggle hidden global selector `2`, `2`/`3`
write hidden global selectors `0x13`/`0x14`, `4`/`5` are no-ops, `6` applies a
flag-packed six-byte state record, `7` returns a diagnostic bitmask, `8`
rebinds and reinitializes synth-runtime state, and `9` is sample-memory
defragmentation. Only subcommand 9 has an externally correlated public meaning:
Elektroid uses payload `09 7F 00`. The command may run for a long time and
rewrites sample storage. This project exposes only guarded subcommand `49/6`
for already hardware-correlated live addresses, with complete-table readback
and exact restoration. The other branches remain disabled: several definitely
mutate state, and even subcommand 7 exercises hardware while calculating its
nominally read-only result.

The operation payload is byte-oriented: payload byte 0 selects subcommand
`0..9`, and the handler requires at least one following byte. Subcommands 2
and 3 use payload byte 1 directly as the value for hidden global selectors
`0x13` and `0x14`. Subcommand 0 also sends and resets a compact event through
a central runtime state object after enabling hidden selector 2; its external
meaning remains unknown. A passive MIDI Control Center startup/preset-listing
capture sent no operation `49`, so routine enumeration does not identify it.

Further firmware tracing narrows subcommand `8`: it rebuilds runtime mirrors
from the same active parameter-descriptor object used by operation `41` and
the save serializer, then runs two reinitialization helpers. It does not read
or serialize the active Sequence A/B object and exposes no reply path. It is
not the missing current-buffer command and remains disabled.

Read-only operation `43` successfully exports raw hidden selectors `00..1F`.
Selectors `13` and `14` both read `126` on the test device. Automated preset
selection and separate CC0/CC32 sentinel tests did not change them; exact
384-word comparisons also proved the live patch was restored or remained
unchanged. They are consequently documented as readable hidden global state,
not guessed to be preset IDs or bank-select latches. The CLI command
`microfreak-global-codes-direct` provides this bounded raw read without adding
unsupported names.

### Guarded global-setting write

Operation `42` consumes exactly two payload bytes, setting code followed by raw
value, and returns no acknowledgement. The guarded implementation therefore
uses operation `43` as the independent verifier after both the target and
inverse writes, and compares the complete operation-`41` table around the
experiment.

On firmware `5.0.0.36`, `keyboard.root_note` code `46` read `0`, operation
`42 46 01` changed it to `1`, and operation `43 46` read back `1`. The inverse
`42 46 00` restored the original and a final operation-`43` read returned `0`.
Neither target nor restore changed any of the 384 live patch words. This proves
computer control of the named global setting; it does not collapse the global
into the constant saved tag `Kbd.Root`.

The installed device description supplies explicit display labels and wire
domains for 34 of the 43 named globals. Firmware's shared setter supplies the
remaining bounds: six booleans, Device ID `0..126`, Aftertouch Offset `0..100`,
and Lower MIDI Channel `0..15` or `126`. All are represented in
`microfreak-globals/1` JSON without a runtime dependency on Arturia artifacts;
unknown display units retain raw labels. The durable
`set-microfreak-global-direct` path writes a JSON before-state backup and
requires exact operation-`43` readback. A mismatch triggers an inverse
operation-`42` write and verifies the original before reporting failure.

Hidden Automation Out independently exercised this path: code `23` changed
from `1` to `0`, operation `43` returned `0`, the inverse restored `1`, and a
final read returned `1`. Neither state changed any operation-`41` patch word.

Subcommand `49/6` is a generic bridge into the firmware's six-byte internal
event bus. Its full operation payload is `06 scope flags d0 d1 d2 d3 d4 d5`.
Flag bits `40 20 10 08 04 02` restore the high bits of `d0..d5`. Scopes `00`,
`01`, and `02` enqueue the decoded record on three internal routes, `7D`
invokes the control handler, and `7F` does both. The record contains a
source/header byte, a dispatch-kind byte, and four kind-specific bytes; common
parameter kinds use the latter as big-endian address and value. Because the
same handler also reaches globals, routing, diagnostics, and runtime modes,
this command is documented and offline-decodable but deliberately not exposed
as a general hardware write API.

One narrow record kind is now hardware proven. Kind `02` calls the same live
synth setter as operation `40`, using the operation-`41` address and a doubled
16-bit record value. The guarded cutoff probe sent payload
`06 7D 42 75 02 01 01 4A 14`, changed `0101` from `3382` to `254A`, observed
the established `0F0E` and `1008` aliases, and restored `3382` through the same
record path. All 384 words matched the baseline afterward. This removes
operation `40`'s per-byte 7-bit limitation for nonnegative 15-bit live values,
but does not authorize other record kinds or unmapped addresses.

Operation `53` is not an undiscovered patch-body transport. Static analysis
proves it copies at most 43 bytes into the internal developer command parser.
The firmware's third stored view (`+0x14000`) exposes 14 top-level commands:
`gpio`, `codec`, `cvout`, `help`, `flag`, `audio`, `filter`, `ioc`, `synth`,
`boot`, `sync`, `oled`, `emc`, and `mixer`. Because this surface includes
reboot, peripheral, calibration, and flash-adjacent diagnostics, it is
documented but deliberately not exposed or hardware-probed.

Operation `4C` is likewise separate from patch storage. Its first byte selects
`clock`, `start`, `gate`, or `midi`; its second byte is false below `40` and
true at or above `40`. The selector names come from the same internal `sync`
command table used by the debug console. Writes remain disabled because these
runtime booleans do not yet have an independent readback/restore path.

## Saved-preset read

Slots are one-based in the UI and API, then converted to zero-based bank and
program bytes (`bank, program = divmod(slot - 1, 128)`).

The same mapping selects any of the 512 saved slots without a hardware-button
press: send MIDI CC 0 (bank select) with `bank`, followed by program change
`program` on channel 1. This changes the unsaved active patch but does not
write storage. Standard MIDI provides no acknowledgement, so selection is
reported as sent rather than falsely described as read-back verified.

1. Send operation `19` with `bank program 00`.
2. Receive operation `52` with a 35-byte header.
3. If header byte 3 has bit `08`, the slot is an empty Init and has no body.
4. Send operation `19` with `bank program 01` and receive empty `15`.
5. Send operation `18` with payload `00` exactly 146 times.
6. Receive 145 operation-`16` parts and one final operation-`17` part. Each
   part contains 32 bytes, producing the exact 4,672-byte preset payload.

The third operation-`19` payload byte is a selector, not an arbitrary resource
number. Firmware 5 answers selector `0` with the header and selector `1` with a
saved-body transfer start. Read-only probes of selectors `2..15`, shortened
payload forms, and pseudo-slot `7F 7F` received no reply. Earlier probes of
banks `7E`/`7F` also timed out, while bank 4 returned ordinary empty headers
that did not track program changes. These results rule out the simplest
current-buffer aliases while leaving a distinct operation undiscovered.

Header fields used by the lossless archive are:

| Header bytes | Meaning |
|---|---|
| `0`, `1` | bank and program |
| `3 & 08` | empty Init flag |
| `8` | program within bank |
| `10` | category ID |
| `11` | archive field `p1` |
| `12..25` | NUL-padded UTF-8 name, maximum 14 bytes |

The direct reader's slot-1 JSON was byte-for-byte identical to the same slot
downloaded through Elektroid.

## Saved-preset write

Only full 4,672-byte presets are uploadable. The guarded backend refuses empty
Init targets because that empty representation cannot be recreated by the same
upload transaction.

1. Send operation `52` with the constructed 35-byte header; expect empty `18`.
2. Send operation `52` with `bank program 01`; expect empty `18`.
3. Send empty operation `15`; expect empty `18`.
4. Send the first 145 raw 32-byte parts with operation `16`.
5. Send the final raw 32-byte part with operation `17`.
6. Read the slot again and require exact decoded and raw equality.

The public command reads the target twice, writes a local `.mfp` backup, and
automatically restores and verifies that backup after an error or mismatched
readback. On firmware 5.0.0.36, slot 320 was written with a changed mapped
cutoff value, independently read back, restored, and re-read at its original
shared-JSON SHA-256.

## Named payload fields

### Firmware-tagged structure

The transferred 4,672-byte body is itself 8-to-7-bit MIDI packed. Unpacking
each eight-byte block to seven bytes produces a 4,088-byte serialization with
a self-describing named prefix. Firmware 5 groups use `@#XYZ` markers and
fields use this layout:

```text
(0x40 + name length)  ASCII name  0x63  metadata  uint16-le value
```

This was verified directly against preset 320 (`Munks`), which exposes 100
named fields including `VCO.Type`, `VCF.Cutoff`, `EG2.Attack`, modulation
matrix rows, sequencer controls, scale/root, and vocoder controls. Parsing by
tag avoids the absolute-offset shifts seen in older public firmware tables.
The JSON retains each field's group, name, metadata byte, unsigned and signed
raw interpretations, and every packed byte that represents its value.

`set-microfreak-structured-json` edits the exact 16-bit value offline, repacks
the full body, and preserves every other byte. A no-op edit of live `Munks`
reproduced its original payload SHA-256 exactly. A one-unit `VCF.Cutoff` edit
was then written to slot 320, read back exactly, and the original `Munks`
payload was restored and verified at SHA-256
`d9e3a9a80634d0cb8a44439d23281f00dab937db7281a6666bb120ff7a28e777`.
Semantic scaling is kept
separate: metadata appears to describe discrete ranges for many fields, but
only independently established conversions should receive friendly values.

The named prefix ends before two fixed firmware-5 sequence blocks. Across the
five observed tagged layouts, Sequence A begins at unpacked offset 1,980 and
Sequence B at 3,022. Each contains 64 records of 16 bytes. The first four bytes
are exposed as MIDI note slots. Firmware-5 factory payloads use several bytes
above the MIDI note range as non-note tokens. JSON presents their interpreted
pitch as `null`, exposes the exact value as `note_bytes`, and preserves it when
rebuilding. `0xFB` and `0xFF` are common empty-note forms, but the full bank
also contains `0xE7`, `0xF6`, `0xFA`, `0xFC`, and `0xFD`; their distinct rest,
tie, or continuation meanings are not guessed. This is consistent with the
four-voice sequencer and factory sequence data. Bytes `4..7` are exposed as
velocities. The exact final eight bytes remain available as
`unclassified_bytes` alongside the stronger decoded projection below.
Firmware strings independently name “Sequence A” and “Sequence B.”

A read-only full-bank corpus pass over all 320 occupied presets produced
40,960 step records and found strong
positional evidence that bytes `4..7` are the four corresponding velocity
slots: all values are `0..127`, polyphonic rows align notes and values by
voice, and unused voices normally carry zero or the initialized default 100.
Together with the firmware's own `Velocity` label, this is now exposed as four
raw 0..127 `velocities` in each JSON step. The same corpus corrects an earlier
16-bit-lane hypothesis: bytes `8..11` are four separate 8-bit automation values
and byte `13` is their four-bit presence mask. Each mask bit strongly aligns
with the corresponding value byte and distinguishes active automation whose
value is zero; the small number of inactive nonzero outliers remain preserved.
Byte `12` has only values 0, 1, and 2. The Arturia manual establishes that a
step stores note, tie, or silence status. A host-only hardware correlation then
selected sequence-enabled factory presets, temporarily changed Clock Source
from Internal to USB with verified inverse restoration, sent MIDI Start and
Clock, and recorded the MicroFreak's own USB MIDI output. Normal `1` steps
retriggered Note On/Off pairs; consecutive `2` steps sustained one note across
the run; `0` steps emitted silence. A leading `2` started and then held its
note when there was no preceding event. JSON therefore exposes byte 12 as
`note_status` with `0 = rest`, `1 = trigger`, and `2 = tie`, while retaining
`note_event_code` as the exact raw byte. The experiment restored Clock Source
to Internal and recalled slot 320 with all 384 live words matching baseline.
See Arturia's
[MicroFreak 5 manual](https://downloads.arturia.net/products/microfreak/manual/microfreak_Manual_5_0_0_EN.pdf).
Bytes `14..15` are reserved and were zero in 40,957 records; the three
exceptions are retained exactly.

JSON can edit the four note slots directly while retaining every unclassified
byte. The convenience command is:

```sh
freak-patch set-microfreak-sequence-note \
  input.json A 1 1 60 output.json
freak-patch set-microfreak-sequence-velocity \
  input.json A 1 1 100 output.json
freak-patch set-microfreak-sequence-status \
  input.json A 1 tie output.json
freak-patch set-microfreak-sequence-automation \
  input.json A 1 1 64 output.json
```

Use `clear` instead of a MIDI note number to write a non-note slot. Velocity is
validated from 0 through 127. Automation values are 0 through 255; `clear`
also clears that lane's presence bit. Status accepts `rest`, `trigger`, or
`tie`. These are offline structural edits; hardware
persistence still uses the guarded preset writer and readback contract.

A read-only scan of all 512 slots on the firmware-5 device found 320 occupied
presets, 107 distinct tagged fields, and five layouts containing 96, 97, 98,
100, or 106 fields. Ninety-six fields are the shared core. Optional/versioned
groups account for the remainder:

- `Kbd.Scale` and `Kbd.Root` occur in 177 presets;
- unison/chord fields occur together in 96 presets;
- `Voc.HissMod` and `Voc.HissVol` occur in 115 presets;
- the older `Gen.Panel` tag occurs in 38 presets.

Metadata is stable for almost every tag. `VCO.Type` varies as the firmware's
engine count evolves, while `VCO.Param1` varies with the selected engine's
parameter domain. This supports interpreting metadata as field-specific range
information rather than treating it as an opaque byte.

### Interpreted tagged values

The JSON now labels each tagged field with one of six explicit value kinds:

- `metadata_scaled_integer`: an integer from zero through the field's own
  metadata byte, used for engine types, switches, enumerations, divisions, and
  bounded integer controls;
- `unsigned_normalized`: a continuous value from 0.0 through 1.0 for named
  oscillator, filter, envelope, rate, and volume controls;
- `bipolar_normalized`: a modulation amount from -1.0 through 1.0 for the 35
  `Co1` through `Co7` matrix cells;
- `signed_offset_shift7`: the firmware-proven `-128..127` integer encoding
  used only by the three chord offsets;
- `live_destination_id`: an assignable modulation destination whose 16-bit ID
  is an independently mapped operation-41 address, accompanied by its named
  `value_label`;
- `raw_u16`: retained without a semantic guess.

Across the 107-field corpus, 101 tags have one of the first five bounded
interpretations. Six remain raw-only: four internal `Sys` controls and two
matrix UI controls.
`set-microfreak-structured-value` edits interpreted values with range
validation; the raw setter remains available for research.

The three `Mat.Assign` tags store the destination as a two-byte group/control
identifier. The historical open-source reader established that shape; every
identifier observed in the firmware-5 320-preset corpus independently equals
one of this project's hardware-mapped operation-41 addresses. JSON therefore
retains the exact numeric ID and adds labels such as `VCF.Cutoff`,
`Gen.UniSprd`, or `Co4.EG2`. The interpreted setter accepts only IDs already in
the hardware map rather than inventing destinations.

Three guarded operation-`49/6` probes then changed `Mat.Assign1`, `Assign2`,
and `Assign3` to other known destination IDs. Each changed exactly its two
mapped aliases (`0609/0902`, `060A/0903`, or `060B/0904`), read back the target,
restored the original ID through the same setter, and left the final 100 named
live fields byte-for-byte identical with all aliases matching.

### Legacy fixed-offset semantic fields

Thirteen older JSON fields remain as clean-room transcriptions of public
row/column facts whose offsets are identical in the published FW1 and FW2
layouts. They are retained for compatibility, but new work should use the
self-describing tagged view above. The tagged parser covers shifted firmware-5
arp, LFO, and envelope fields without guessing an old absolute layout.

The earlier `live microfreak-sentinel` workflow remains available for research,
but it depends on a physical save and is no longer the primary mapping path.
Read-only full-bank tagged corpus analysis plus guarded tagged write/readback is
both broader and independent of manual device interaction.

`filter.cutoff` in the legacy view still carries its conservative historical
evidence label. Separately, tagged `VCF.Cutoff` has exact one-unit write,
readback, restore, and final-payload-hash proof on firmware 5.

## Wavetable boundary

Offline `.mfw` objects use the same Boost text envelope as presets but carry a
16,384-byte PCM payload. `.mfwz` is a one-entry ZIP named `0_sample`; this was
cross-checked against Elektroid's public fixture. Control Center's 65 installed
factory, synchronized, and Init objects use opaque archive tags `134`, `209`,
and `DEVBUILD`, plus differing `p3` values. JSON now preserves every archive
field, and all 65 installed `.mfw` files round-trip byte-for-byte.

The synchronized 16-slot wavetable directory also round-trips losslessly as a
bank JSON document. `.mfwbz` read/write uses the corresponding
`project/bank/numbered-file.mfw` ZIP topology and is intentionally reported as
research until a generated archive completes a Control Center import test.

MIDI Control Center was passively captured recalling the 16-slot wavetable
bank. Each table contains four 4,096-byte parts. Each part is transferred as
146 packets carrying 28 raw bytes plus a final packet carrying eight useful
bytes. Every raw 28-byte block is encoded into 32 7-bit-clean MIDI bytes: one
high-bit bitmap followed by seven low-7-bit bytes, repeated four times.

### Read

1. Read the 28-byte slot header with operation `57`, then `18`.
2. For each part `0..3`, send operation `55` with `slot part 00`.
3. Send 147 operation-`18` requests and unpack the `16`/final-`17` replies.
4. Concatenate the four parts into exactly 16,384 PCM16LE bytes.

MIDI Control Center uses `01` in the final operation-`55` payload byte and
sends one additional operation-`18` request; firmware 5 accepts the smaller
transaction above. The independent slot-1 `Ney` JSON matched Elektroid exactly.

### Upload and clear

1. Reset the slot with operation `56`, followed by empty `15`.
2. Send the packed 28-byte entry header with operation `16` and an eight-byte
   zero tail with operation `17`. Header status bit `08` marks an empty slot.
3. For each part, send operation `54` with `slot part 01`, then empty `15`.
4. Pack and send 146 operation-`16` blocks plus the final operation-`17` block.
5. Read back the whole table and require exact name and PCM equality.

The direct backend wrote `CodexProbe` to previously empty slot 2, reproduced
the target archive SHA-256 on readback, then cleared the slot by writing an
empty entry plus four zero parts. A final header read confirmed slot 2 empty;
slot 1 remained `Ney`.

## Reserved firmware Init template

### Why operation 19 does not read unsaved current state

Firmware tracing now proves that operation `19` always calls the 4,096-byte
flash-slot reader at `(slot + 0x81) * 0x1000`. The physical-save workflow has
a separate inverse serializer that walks the active descriptor/value arrays,
copies the `0x824`-byte Sequence A/B body, builds the tagged preset image, and
then commits that image through the flash-slot writer. There is no call from
the operation-`19` handler to this serializer and no direct incoming SysEx
caller to it.

Accordingly, operation `41` is the verified current *parameter-object* read,
while operation `19` is the verified complete *saved-slot* read. A fully
lossless unsaved-current read still needs a route to the active sequence/header
regions or to the serializer before its flash write. The backend does not
mislabel a saved-slot download as current-buffer state.

The operation-41 reader can also be interleaved with externally clocked
sequence playback. `microfreak-sequence-playback-direct --live-snapshot-every`
pauses external clock at each boundary, reads either all 384 words or selected
named fields, and retains outgoing MIDI encountered during the SysEx replies.
On `MotivSeq`, Pattern A's post-step trailer identifies lane destinations
`0101` cutoff, `0102` resonance, and `0602` envelope decay. Those fields moved
in operation 41 alongside outgoing CC 23, 83, and 106. The command then
recalled slot 320, restored Clock Source, and verified all 384 baseline words.
Follow-up guarded slot-320 sentinels proved trailer byte 8 is per-pattern gate
percentage. Trailer byte 9 correlates with length but is only a mirror: the
tagged `Seq.Length` field, not byte 9 alone, controlled a four-step loop. A
candidate Pattern-A/B flag interpretation for bytes 10/11 failed on hardware
and is retained as negative evidence, not a field mapping.

`microfreak-current-overlay-json-direct` exposes the useful intersection now:
it reads the complete saved base and all 384 current words in one pass, applies
every named live field present in that base's tagged layout, and carries any
engine-layout fields absent from the base as explicit unapplied live values.
The JSON separately labels current-read regions and saved-base-only regions.
On slot 320 `Munks`, 94 current fields applied and reproduced the base payload
exactly; six valid runtime fields were absent from the Vocoder saved layout and
were retained in the report rather than forcing an unproved layout migration.
A second run sent cutoff CC `23` value `49`: operation `41` reported only
`VCF.Cutoff` changing from `13186` to `12642`, and the overlay changed exactly
the field's two unpacked little-endian value bytes at offsets `81` and `82`.
Recalling slot 320 afterward returned all 384 live words to the exact baseline.

Firmware `5.0.0.36` accepts the normal preset-read transaction at the first
address beyond saved storage:

```text
header:  operation 19, payload 04 00 00 -> operation 52, 35 bytes
body:    operation 19, payload 04 00 01 -> operation 15
parts:   146 operation-18 requests -> 145 x operation 16, final operation 17
```

The header names the object `Init` and marks its Init bit; unlike an empty
saved slot, the address supplies a complete 4,672-byte body. Its hardware hash
is `96e28f7618407491fc479624facf642e7ce198cd7d0b4c944d8cfd2f47e8a1b8`.
An exhaustive read-only boundary sweep found no other valid address: every
bank-4 program from 1 through 127 timed out, as did program 0 in every bank
from 5 through 127. Slot 1 was re-read as a safety fence every 32 probes and
after the sweep, with no failure or change.

A reversible CC experiment proved this pseudo-slot does not mirror working
memory: its header and body were identical before and after changing the live
filter cutoff, and the selected saved preset was restored afterward. The
transport exposes it only as `firmware_initializer_template`; it is not an
active-patch read command.
