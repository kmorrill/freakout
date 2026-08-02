"""Minimal ZIP 1.0 writer for MiniFreak .mnfx files.

MiniFreak V rejects ZIP files with:
- Version > 1.0 (e.g., Python zipfile writes 2.0)
- Extra fields (Unix timestamps, UT, ux)
- Directory entries (0-byte folder entries)
- Any compression method other than Stored

This module writes raw ZIP bytes with struct.pack to produce
exactly the format MiniFreak V requires.
"""

from __future__ import annotations

import struct
import zlib


def create_zip(entries: list[tuple[str, bytes]]) -> bytes:
    """Create a ZIP 1.0 archive with Stored compression.

    Args:
        entries: List of (filename, data) pairs. Filenames should use
                 forward slashes (e.g., "MiniFreak/User/MyPack/MyPreset").

    Returns:
        Raw ZIP bytes compatible with MiniFreak V.
    """
    body = bytearray()
    central_dir = bytearray()
    offsets: list[int] = []

    for filename, data in entries:
        fname_bytes = filename.encode("utf-8")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        size = len(data)

        offsets.append(len(body))

        # Local file header (30 bytes + filename, no extra field)
        body += struct.pack(
            "<4sHHHHHIIIHH",
            b"PK\x03\x04",  # Local file header signature
            10,              # Version needed to extract (1.0)
            0,               # General purpose bit flag
            0,               # Compression method: Stored
            0,               # Last mod file time
            0,               # Last mod file date
            crc,             # CRC-32
            size,            # Compressed size
            size,            # Uncompressed size
            len(fname_bytes),  # File name length
            0,               # Extra field length
        )
        body += fname_bytes
        body += data

    cd_offset = len(body)

    for i, (filename, data) in enumerate(entries):
        fname_bytes = filename.encode("utf-8")
        crc = zlib.crc32(data) & 0xFFFFFFFF
        size = len(data)

        # Central directory file header (46 bytes + filename, no extra/comment)
        central_dir += struct.pack(
            "<4sHHHHHHIIIHHHHHII",
            b"PK\x01\x02",  # Central directory header signature
            10,              # Version made by (1.0)
            10,              # Version needed to extract (1.0)
            0,               # General purpose bit flag
            0,               # Compression method: Stored
            0,               # Last mod file time
            0,               # Last mod file date
            crc,             # CRC-32
            size,            # Compressed size
            size,            # Uncompressed size
            len(fname_bytes),  # File name length
            0,               # Extra field length
            0,               # File comment length
            0,               # Disk number start
            0,               # Internal file attributes
            0,               # External file attributes
            offsets[i],      # Relative offset of local header
        )
        central_dir += fname_bytes

    cd_size = len(central_dir)

    # End of central directory record (22 bytes)
    eocd = struct.pack(
        "<4sHHHHIIH",
        b"PK\x05\x06",     # End of central directory signature
        0,                   # Number of this disk
        0,                   # Disk where central directory starts
        len(entries),        # Number of central directory records on this disk
        len(entries),        # Total number of central directory records
        cd_size,             # Size of central directory
        cd_offset,           # Offset of start of central directory
        0,                   # Comment length
    )

    return bytes(body) + bytes(central_dir) + eocd
