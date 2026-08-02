# Contributing to Freakout

Contributions are welcome, especially captures reduced to protocol facts,
device-version verification, lossless format tests, and guarded transport
improvements.

By submitting a contribution, you agree that you authored it or have the right
to license it under this repository's MIT license.

## Clean-room requirements

- Do not commit Arturia firmware, application binaries, installed resource
  files, factory presets, proprietary schemas, packet captures containing
  unrelated personal data, decompiler databases, or generated decompiler
  listings.
- Do not copy code or data from projects without a compatible license.
- Keep GPL implementations such as Elektroid external to the MIT codebase.
- Protocol facts may be independently reimplemented, but document the public
  reference and the independent device or capture evidence.
- Label firmware-only hypotheses as static candidates until wire or device
  behavior confirms them.

## Hardware evidence

For any write path, include a fresh baseline, stable preflight, bounded target,
readback, restoration, and final equality check. Report an accepted packet,
active edit, saved slot, and power-cycle persistence as separate claims.

Never use an empty saved slot for a write test until the same device and
firmware have a proven way to recreate the empty state.

## Before opening a change

Run:

```sh
python3 -m pytest -q
python3 -m compileall -q src tools
```

Keep firmware, captures, exported presets, and local analysis under ignored
paths such as `work/`.
