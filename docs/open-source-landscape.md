# Open-source Freak landscape

Reviewed 2026-08-01. Repository activity and capabilities change; verify before
depending on them.

## MiniFreak

| Project | License | What it provides | Relationship to this project |
|---|---|---|---|
| [mini-freak-preset-viewer](https://github.com/vOROn200/mini-freak-preset-viewer) | No declared license | `.mnfx` viewing and bundled Arturia-derived parameter XML | Useful comparison only; code and copied XML are not reused |
| [minifreak-converter](https://github.com/negligible-mass/minifreak-converter) | MIT | Browser conversion to MiniFreak V sample and 189x512x24-bit wavetable files | Format behavior is cited; future conversion code may be independently implemented or reused with attribution |
| [minifreak_sample_conv](https://github.com/mtizim/minifreak_sample_conv) | No declared license | Audio to `.raw12b`, synchronized through MiniFreak V | Workflow evidence only |
| [minifreak-presets](https://github.com/negligible-mass/minifreak-presets) | No declared license | Experimental presets exposing hidden filters | Test inspiration only; preset files are not redistributed |

No established public project found in this review implements direct
MiniFreak hardware preset enumeration, download, editing, and upload. Most
tools operate on `.mnfx` files or place content where MiniFreak V will sync it.

This project now independently implements the previously missing read side.
Passive observation of MiniFreak V revealed Arturia's Collage transport: raw
USB bulk endpoints, a small flow-control exchange, protobuf requests, and
resource chunks. The open-source reader claims only vendor interface 0 and can
retrieve the active edit buffer, saved presets, and 128-byte saved-slot
metadata. A staged store transaction is now independently implemented with a
fresh message ID per chunk; changed content activates and occupied-slot writes
have exact readback and restoration. It extracts message descriptors from the user's installed MiniFreak
V binary rather than redistributing Arturia schemas or generated code.

## MicroFreak

| Project | License | What it provides | Relationship to this project |
|---|---|---|---|
| [Elektroid](https://github.com/dagargo/elektroid) | GPL-3.0 | Maintained SysEx transport for 512 presets, 128 samples, 16 wavetables, storage, rename, and transfer | Optional external compatibility backend; GPL source is not copied into this MIT library |
| [microfreak-reader](https://github.com/francoisgeorgy/microfreak-reader) | No declared license; archived | WebMIDI saved-preset reader and early decoded controls | Historical protocol reference only |
| [microfreak-reverse](https://github.com/francoisgeorgy/microfreak-reverse) | No declared license; archived | Packet captures and early SysEx notes | Historical evidence only; implementation is not copied |
| [mf-utils](https://github.com/dcower/mf-utils) | MIT | MicroFreak firmware and factory-wavetable extraction/replacement | Firmware research reference, not the preferred live transport |
| [OrganizedFreak](https://github.com/OrionDreams/OrganizedFreak) | GPL-3.0 | Early offline `.mbp` bank organizer | Useful UX comparison; no direct device transport |
| [MicroFreakEditor](https://github.com/athompson36/MicroFreakEditor) | No declared license | SwiftUI CC editor prototype; its README says mappings are placeholders and SysEx is future work | No reusable transport at present |
| [mcp-patchwork](https://github.com/truthanb/mcp-patchwork) | MIT | MIDI/LLM control layer with a MicroFreak saved-slot reader and documented-CC live control | Its August 2026 source still uses the established `0x19` saved-slot plus 146-chunk reader, labels preset writing `TODO`, and contains no MicroFreak current/edit-buffer request; useful independent boundary check, not a transport dependency |
| [microfreak-patches](https://github.com/Zatfer17/microfreak-patches) | No declared license | Public `.mfprojz` corpus and documented ZIP/project/bank/`.mbp` topology | Format facts and interoperability corpus only; code and presets are not redistributed |

The maintained sources were refreshed at their 2026-08-01 heads before the
host state-machine work: Elektroid `a782b28e` and `mf-utils` `42fd325b`.
Elektroid still implements saved slots by operation `19` with explicit
bank/program addressing and contains no current/edit-buffer request.

The passive macOS capture helper uses Meta's BSD-licensed
[`fishhook`](https://github.com/facebook/fishhook) at build time. Fishhook is
not vendored in this repository.

This project now also has an independent CoreMIDI implementation of the
MicroFreak SysEx framing and preset/wavetable transactions. On firmware 5.0.0,
direct and Elektroid reads produced byte-identical shared JSON for preset 1 and
wavetable 1. Guarded direct writes were verified on preset 320 and wavetable 2,
including exact readback and restoration/clear back to their prior states.

A renewed public-code search found no implementation that reads the
MicroFreak's unsaved edit buffer. In particular, `microfreak-reader`,
`microfreak-reverse`, Elektroid, and `mcp-patchwork` address saved slots. The
latter's nominal preset-dump support reproduces the same slot-addressed
`0x19`/`0x18` transaction and leaves preset writing unimplemented. This is
corroboration of the current research boundary, not proof that firmware lacks
an undiscovered edit-buffer operation.

The `.mfprojz` implementation was cross-checked against 25 public projects
containing 8,832 `.mbp` objects. It preserves the project/bank/member topology,
opaque Boost archive tag, empty-slot labels, raw category byte, and the 18-bit
characteristics field. The characteristic labels and bit order were verified
against MIDI Control Center's installed label table and an independent public
preset-list parser; no third-party source code or preset payload is included.

## Clean-room and license boundary

- Public protocol facts, independently observed device traffic, and behavior
  verified on personally owned hardware may be documented and tested.
- Arturia application resources and factory presets are not copied into the
  repository.
- Projects without a license are treated as all-rights-reserved: compare
  behavior and facts, but do not copy their code or data.
- Elektroid remains a separate GPL program. A subprocess adapter avoids
  incorporating GPL code into this MIT package.
