# MiniFreak V passive USB capture

MiniFreak V 4 uses a vendor-specific USB interface for high-bandwidth hardware
link and preset/storage operations. It dynamically loads a bundled libusb
library. `freak_usb_capture.c` is a passive shim that records the control and
bulk calls made by the official application without generating device traffic
itself.

The capture must be run against a copied real libusb library, because the shim
loads that copy to forward every intercepted call. Build artifacts and captures
belong under `work/` and are intentionally excluded from source control.

Example build on macOS/Apple Silicon:

```sh
mkdir -p work/usb-capture
cp /Library/Arturia/Shared/liblibusb.dylib work/usb-capture/liblibusb_real.dylib
install_name_tool -id @rpath/liblibusb_real.dylib work/usb-capture/liblibusb_real.dylib
codesign --force --sign - work/usb-capture/liblibusb_real.dylib
clang -dynamiclib -arch arm64 \
  -I/opt/homebrew/include/libusb-1.0 \
  tools/usb_capture/freak_usb_capture.c \
  -Wl,-reexport_library,work/usb-capture/liblibusb_real.dylib \
  -Wl,-rpath,@loader_path \
  -o work/usb-capture/liblibusb.dylib
codesign --force --sign - work/usb-capture/liblibusb.dylib
```

The application currently opens Arturia's libusb by absolute path and resolves
its functions with `dlsym`. The reliable live-capture build therefore uses
Meta's BSD-licensed [fishhook](https://github.com/facebook/fishhook) to replace
only the application's `dlsym` import. The original transfer pointer returned
by libusb is retained before the passive wrapper is substituted.

```sh
git clone --depth 1 https://github.com/facebook/fishhook.git work/vendor/fishhook
clang -dynamiclib -arch arm64 -DFREAK_USB_FISHHOOK \
  -I/opt/homebrew/include/libusb-1.0 \
  -Iwork/vendor/fishhook \
  tools/usb_capture/freak_usb_capture.c \
  work/vendor/fishhook/fishhook.c \
  -o work/usb-capture/freak_usb_capture.dylib
codesign --force --sign - work/usb-capture/freak_usb_capture.dylib
```

Launch the official application with these environment variables:

```sh
FREAK_USB_REAL_LIBUSB="$PWD/work/usb-capture/liblibusb_real.dylib" \
FREAK_USB_CAPTURE_FILE="$PWD/work/usb-capture/traffic.log" \
DYLD_INSERT_LIBRARIES="$PWD/work/usb-capture/freak_usb_capture.dylib" \
  "/Applications/Arturia/MiniFreak V.app/Contents/MacOS/MiniFreak V"
```

Each line records the transfer type, endpoint or control-request fields, return
status, lengths, and a hexadecimal payload. The default payload limit is 1 MiB
per transfer and can be changed with `FREAK_USB_CAPTURE_MAX_BYTES`. Five-byte
flow-control keepalives are omitted by default; set
`FREAK_USB_CAPTURE_KEEPALIVES=1` to retain them.

Decode a capture using the protobuf schemas embedded in the installed plug-in:

```sh
freak-patch capture analyze work/usb-capture/traffic.log \
  --arturia-binary "/Library/Arturia/MiniFreak V/MiniFreak V.vst3/Contents/MacOS/MiniFreak V" \
  --output work/usb-capture/decoded.json
```

Safety boundary: this tool only observes calls from MiniFreak V. The risk and
meaning of an operation still come from the action performed in the official
application. Start with link, browse, and backup/recall operations before any
send, replace, delete, firmware, sample, or wavetable action.
