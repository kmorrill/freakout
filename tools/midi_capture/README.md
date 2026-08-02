# MiniFreak V passive MIDI capture

This small fishhook-based shim records packets that the disposable MiniFreak V
copy sends through CoreMIDI. It does not open endpoints or generate messages.
Build products and traffic logs belong under ignored `work/` paths.

```sh
mkdir -p work/midi-capture
clang -dynamiclib -arch arm64 \
  -Iwork/vendor/fishhook \
  tools/midi_capture/freak_midi_capture.c \
  work/vendor/fishhook/fishhook.c \
  -framework CoreMIDI -framework CoreFoundation \
  -o work/midi-capture/freak_midi_capture.dylib
codesign --force --sign - work/midi-capture/freak_midi_capture.dylib
```

Launch only a disposable application copy with `DYLD_INSERT_LIBRARIES` and set
`FREAK_MIDI_CAPTURE_FILE` to an ignored log path. The installed Arturia app and
libraries are not modified.

## Duplex MicroFreak capture with selected call stacks

`freak_midi_duplex_capture.c` additionally records CoreMIDI input and can emit
host call stacks for selected outgoing MicroFreak operations. This is useful
when a stripped host executable routes protocol calls indirectly. Backtraces
are opt-in and filtered so high-volume continuation packets do not create huge
logs:

```sh
clang -dynamiclib -arch x86_64 \
  -Iwork/vendor/fishhook \
  tools/midi_capture/freak_midi_duplex_capture.c \
  work/vendor/fishhook/fishhook.c \
  -framework CoreMIDI -framework CoreFoundation \
  -o work/mcc-capture/freak_midi_duplex_capture-v2.dylib
codesign --force --sign - work/mcc-capture/freak_midi_duplex_capture-v2.dylib

FREAK_MIDI_CAPTURE_FILE="$PWD/work/mcc-capture/trace.log" \
FREAK_MIDI_CAPTURE_BACKTRACE_OPS="0x19,0x43" \
DYLD_INSERT_LIBRARIES="$PWD/work/mcc-capture/freak_midi_duplex_capture-v2.dylib" \
  "/path/to/disposable/MIDI Control Center.app/Contents/MacOS/MIDI Control Center"
```

The log records the executable's runtime image base once and raw frame
addresses on separate `trace` lines. Normalize only frames inside the
fingerprinted executable; dylib addresses belong to their own images. Never
inject the shim into the installed application or claim a call stack proves
device behavior without matching wire traffic.

Normalize a completed capture with the fingerprint-pinned analyzer:

```sh
python3 tools/analyze_mcc_microfreak_commands.py \
  "/Applications/Arturia/MIDI Control Center.app/Contents/MacOS/MIDI Control Center" \
  --capture work/mcc-capture/microfreak-stack-trace.log --json
```

The analyzer retains only frames that map into the main MCC Mach-O image.
Reported addresses are return sites in the static executable, with the runtime
ASLR slide removed.
