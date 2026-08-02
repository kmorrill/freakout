# MicroFreak MIDI Control Center static analysis

This note records clean-room analysis of Arturia's compiled desktop software.
It is a separate evidence stream from the
[MicroFreak hardware firmware analysis](microfreak-firmware-notes.md): MIDI
Control Center shows what the host constructs and expects, but it does not
prove how the device firmware implements a request.

No Arturia executable, data table, preset, or other proprietary asset is
redistributed by this project. Version-specific addresses below are included
only to make the independently derived results reproducible.

Findings use the same evidence labels as the firmware work:

- **confirmed** means the instruction/data relationship is reproducible in the
  fingerprinted desktop binary;
- **correlated** means the desktop behavior also matches a passive hardware
  capture or independently working transport;
- **candidate** means the interpretation still needs runtime or wire evidence.

## Analyzed host artifact

- application: MIDI Control Center
- application version: `1.23.0.134`
- executable SHA-256:
  `9e75f7db046f939fc81f16f5243b0ed6bed4f5649c95145f3ab6adbb182a1f59`
- executable format: stripped x86-64 Mach-O

The installed `MicroFreak.json` identifies manufacturer `00206B`, family
`0600`, project ID `29`, and protocol `mbrute`. Its action and field lists are
empty, so the useful protocol behavior lives in compiled code rather than that
declarative file.

## SysEx construction

**Confirmed:** the generic sender around `0x1004B5B1F` constructs an Arturia
message beginning with `F0 00 20 6B`, appends dynamic product/device,
transaction, length, operation, and payload fields, and terminates it with
`F7`.

**Correlated:** this is the same framing implemented by
`src/minifreak_patch/microfreak_midi.py` and observed in passive MicroFreak
captures. The exact working device envelope remains
`F0 00 20 6B 07 01 <sequence> <length> <operation> ... F7`.

## Wavetable sender

**Confirmed:** a wavetable send path near `0x1004C2840` invokes the generic
transfer machinery with operation `0x54`, three bytes of per-block metadata,
and a `0x1000`-byte source block.

**Correlated:** operation `54` and 4,096-byte parts agree with passive Arturia
captures and the independently verified wavetable read/write implementation.
This is useful corroboration, not a newly enabled write path.

## MicroFreak subcommand dictionary

The executable contains this diagnostic string:

> must be added in MidiManager::DictionnaryMicroFreakSubCommandCode enum. Make
> sure it matches the value expected on FW side.

**Confirmed:** the string is referenced at `0x1004C6ECA`; the diagnostic helper
starts at `0x1004C6DC0` and has one identified call at `0x1004BBE04`.

The caller searches a contiguous table from `0x10163CA00` to `0x10163D300` in
24-byte steps. That is 96 libc++ `std::string` objects. When a name matches, it
emits outer operation `0x42` and computes the subcommand as:

```text
subcommand = 0x20 + table_index
```

**Correlated:** the shape matches global-setting replies already seen on the
wire: operation `42` followed by parameter codes beginning at `20`.

**Confirmed:** `tools/analyze_mcc_microfreak_commands.py` now reproduces the
runtime table from the fingerprinted executable's constant initializer. Codes
`20..4D` contain 43 named settings, two reserved entries, and one empty entry;
`4E..7F` are all `kEmpty`. This is the global-setting dictionary, not the full
preset/wavetable/storage operation dictionary. The tool fails closed on an
unknown executable fingerprint and publishes only the derived names.

### Newly recovered and hardware-confirmed reads

The original startup capture requested 31 settings. A read-only operation-`43`
probe of the twelve additional named codes on MicroFreak firmware `5.0.0.36`
received a valid matching operation-`42` reply for every code:

| Code | MCC identifier | Shared raw setting | Observed value |
|---:|---|---|---:|
| `22` | `kOptMidiAutomationIn` | `midi.automation_in` | 1 |
| `23` | `kOptMidiAutomationOut` | `midi.automation_out` | 1 |
| `29` | `kOptPauseExitMode` | `control.pause_exit_mode` | 0 |
| `2A` | `kOptXProgChgEnable` | `midi.program_change_enable` | 1 |
| `2F` | `kOptDeviceID` | `device.id` | 1 |
| `30` | `kOpt14bitAutomation` | `midi.automation_14bit` | 0 |
| `32` | `kOptSyncPortStart` | `clock.sync_port_start` | 1 |
| `33` | `kOptAftertouchComp` | `keyboard.aftertouch_compensation` | 20 |
| `34` | `kOptAftertouchOffset` | `keyboard.aftertouch_offset` | 12 |
| `35` | `kOptMidiChannelInLower` | `midi.channel_in_lower` | 126 |
| `40` | `kOptHelpScreen` | `control.help_screen` | 1 |
| `43` | `kOptUsbToDin` | `midi.usb_to_din` | 0 |

This confirms the read transport and raw values, not each value's enum or unit.
The normal backend now reads all 43 named settings while preserving that raw
boundary.

The installed `MicroFreakCenter.xml` supplies value labels for three of the
twelve hidden reads: MIDI automation input and program-change input are
`Off`/`On`, while aftertouch compensation is `0%..100%` in steps of ten. The
GUI XML contains controls for these three settings only inside comments, which
explains why normal startup does not request them. It supplies no value model
for the other nine. Firmware's central setter closes that range gap: six clamp
to boolean, Device ID to `0..126`, Aftertouch Offset to `0..100`, and Lower
MIDI Channel to `0..15` or `126`. Unknown display units remain raw.

## Disabled working-memory actions

**Confirmed host/UI behavior:** with firmware `5.0.0.36` connected, MIDI
Control Center's generic Device menu contains `Store To > Working Memory` and
`Recall From > Working Memory`, but both actions are disabled. The
MicroFreak-specific GUI XML exposes only saved-preset `Send to MicroFreak` and
`Recall to Computer` actions and contains no working/current-buffer binding.

**Correlated:** three full passive UI/startup captures contain only global,
saved-preset-header, wavetable, and sample traffic, and report no current-buffer
request. The disabled menu is therefore a generic cross-device affordance, not
evidence that the MicroFreak host backend implements working-memory transfer.
It remains useful as a static-analysis signpost: a future candidate must be
shown to enter MicroFreak-specific code before it is tested on hardware.

## Passive call-stack correlation

The duplex capture shim can optionally record return-address stacks for
selected outbound operations. `tools/analyze_mcc_microfreak_commands.py
--capture` now makes those captures reproducible: it verifies the exact MCC
executable SHA-256, reads the main-image runtime base recorded by the shim,
removes ASLR, and discards every frame outside the fingerprinted executable.
Frames belonging to the shim, CoreMIDI, and macOS frameworks are therefore not
mistaken for Arturia control flow.

**Correlated:** one passive startup capture on firmware `5.0.0.36` produced 512
operation-`19` traces and 31 operation-`43` traces. Every trace in each family
had one identical normalized main-image stack:

```text
19: 100EF1EB8 -> 1004C56FD -> 1004B1318 -> 1004B3E01
    -> 1004BDE07 -> 10056A20D -> 100571F9F -> 1005717E1
    -> 100567922 -> 1004BCFED -> 10047FE06 -> 101039467
    -> 100F45619 -> 100F41727

43: 100EF1EB8 -> 1004C56FD -> 1004B1318 -> 1004B11FD
    -> 1004BC484 -> 10047FE06 -> 101039467 -> 100F45619
    -> 100F41727
```

These are return sites, not inferred function starts. The common
`0x1004B1318` site follows the virtual send call in the small request/reply
helper at `0x1004B1280`; `0x1004C56FD` follows MCC's eventual CoreMIDI send.

**Confirmed and correlated:** the operation-`19` branch reaches the routine at
`0x1004B3C80`. It constructs the exact 13-byte saved-slot header request,
including operation `19`, bank, program, and mode `00`, and asks the shared
exchange helper to accept operation `52` as the reply. Its observed caller at
`0x1004BDCF0` is reached through MCC's preset-inventory model. The 512 traces
are therefore direct runtime proof for saved-slot header enumeration, not
merely a nearby static constant and not a current-buffer transfer.

**Confirmed and correlated:** operation `43` instead returns through
`0x1004B11FD` after the same shared exchange helper. The higher
`0x1004BC484` return site sits inside the startup setting-model loop. This
independently ties the recovered global dictionary to physical traffic.

Reproduce the normalization without launching MCC or contacting hardware:

```sh
python3 tools/analyze_mcc_microfreak_commands.py \
  "/Applications/Arturia/MIDI Control Center.app/Contents/MacOS/MIDI Control Center" \
  --capture work/mcc-capture/microfreak-stack-trace.log --json
```

The JSON report also correlates every trace timestamp with the exact outbound
packet. It groups payloads by length and final byte, so a call stack cannot be
mistakenly labelled from its operation byte alone.

### Explicit Recall to Computer state machine

**Confirmed and correlated:** a passive click on `Recall to Computer` produced
1,344 operation-`19` traces with three—and only three—normalized stacks:

| Phase | Count | Payload shape | Distinct payloads |
|---|---:|---|---:|
| Startup inventory headers | 512 | `bank program 00` | 512 |
| Explicit-recall headers | 512 | `bank program 00` | 512 |
| Explicit-recall bodies | 320 | `bank program 01` | 320 |

The 320 body requests correspond exactly to the occupied saved slots. The body
stack leaves the generic sender at `0x1004B64E9`, the bulk-transfer helper at
`0x1004BF6CB`, and the saved-preset read wrapper at `0x1004BF4BD`. The explicit
header stack instead leaves the small request/reply helper at `0x1004B1318`,
the header constructor at `0x1004B3E01`, the inventory wrapper at
`0x1004BDE07`, and the saved-preset read wrapper at `0x1004BF48E`.

**Confirmed statically:** the wrapper beginning at `0x1004BF420` first calls
the saved-slot header routine with its bank and program. When the slot is valid
and non-Init, it calls `0x1004BF650` with operation `19` and mode `1`. That
helper places `bank`, `program`, and `mode` in a three-byte payload and calls
the generic SysEx sender at `0x1004B6250`. The runtime packet correlation above
proves that this exact branch emits `bank program 01`.

The only other direct caller of `0x1004BF650` is a bank/program-addressed
export path beginning at `0x1004C0EB0`; it passes operation `19`, mode `2`, and
then enters a local preset serializer containing the diagnostic `could not
save preset`. This is a saved-object/file variant, not evidence for an
unaddressed working-memory request. No direct caller passes a third mode or
omits bank/program.

## What this does and does not establish

This analysis strengthens three existing conclusions:

1. The independent SysEx envelope matches Arturia's host implementation.
2. Wavetable operation `54` and 4,096-byte transfer parts are not accidental
   capture artifacts.
3. Operation `42` is a named MicroFreak subcommand response family whose code
   space starts at `20`.

It does **not** identify an unsaved/current-preset read operation, prove the
meaning of all 96 reserved subcommands, or substitute for device readback.

## Next host-analysis steps

- [x] Locate the static initializer that populates the 96 runtime strings and
  derive the names without dumping or redistributing the host binary.
- [x] Compare recovered names and codes with the 31 startup-observed globals
  and issue read-only probes for all twelve meaningful gaps.
- [x] Recover value domains for all twelve new settings. Three are labelled by
  installed XML; firmware clamps bound the other nine. A reversible Automation
  Out write/readback proved one hidden boolean and restored it exactly. Units
  not present in the UI description remain raw rather than guessed.
- [x] Follow the read callers for preset operations `18`/`19`; explicit recall
  is now tied to header mode `00` and saved-body mode `01`, while the only
  sibling direct caller is a bank/program-addressed mode-`02` export path.
- [ ] Follow wavetable operations
  `54`/`55`/`57`, and sample-directory operation `5B` to recover host-side
  transaction state machines and validation rules.
- [ ] Search explicit user actions, rather than normal startup, for a current
  edit-buffer request; two passive startup captures already prove that startup
  reads headers and inventories but no preset bodies. The generic working-memory
  actions are disabled and absent from MicroFreak-specific GUI bindings, so
  trace them statically before attempting any forced invocation.
- [ ] Turn the version-pinned address work into a fingerprinted read-only tool
  that fails closed when the installed binary changes. The global dictionary
  and passive call-stack normalizer are complete; preset state-machine
  extraction remains.

## Parallel MiniFreak follow-up

Repeat this host-side pass for both MIDI Control Center's MiniFreak support and
the installed MiniFreak V executable. The concrete checklist lives in the
[MiniFreak firmware research TODO](minifreak-firmware-research-todo.md), where
host evidence and actual hardware-firmware evidence remain explicitly
separated.
