"""Boost.Serialization text archive parser for .mnfx preset files.

The .mnfx format is a space-delimited token stream with length-prefixed strings.
Tokens are separated by whitespace, and strings are preceded by their character count.

Example: ``22 serialization::archive 10 0 7 0 7 12 Crusty Pluck``
- ``22 serialization::archive`` = 22-char string "serialization::archive"
- ``10`` = archive version number
- ``12 Crusty Pluck`` = 12-char string "Crusty Pluck"
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from io import BytesIO
from typing import Optional


class ParseError(Exception):
    """Raised when parsing an .mnfx file fails."""


class Tokenizer:
    """Tokenizer for Boost.Serialization text archives.

    The format is tricky because a number token might be either:
    1. A standalone numeric value (int or float)
    2. A length prefix for the next string

    We read tokens greedily and let the caller decide interpretation.
    """

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    @property
    def is_empty(self) -> bool:
        return self.text[self.pos:].strip() == ""

    def _skip_whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t\n\r":
            self.pos += 1

    def _next_word(self) -> Optional[str]:
        self._skip_whitespace()
        if self.pos >= len(self.text):
            return None
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in " \t\n\r":
            self.pos += 1
        if self.pos == start:
            return None
        return self.text[start:self.pos]

    def _peek_word(self) -> Optional[str]:
        saved = self.pos
        word = self._next_word()
        self.pos = saved
        return word

    def read_length_prefixed_string(self) -> str:
        """Read a length-prefixed string: ``<len> <chars>``.

        The length is the number of characters (bytes in ASCII) to read.
        The string may contain spaces, so we read exactly ``len`` chars.
        """
        word = self._next_word()
        if word is None:
            raise ParseError("expected string length, got EOF")
        try:
            length = int(word)
        except ValueError:
            raise ParseError(f"expected string length, got '{word}'")

        if length == 0:
            return ""

        # Skip exactly one space after the length
        if self.pos < len(self.text) and self.text[self.pos] == " ":
            self.pos += 1

        # Read exactly `length` bytes
        if self.pos + length > len(self.text):
            raise ParseError(
                f"string length {length} exceeds remaining input "
                f"({len(self.text) - self.pos} bytes left)"
            )

        s = self.text[self.pos:self.pos + length]
        self.pos += length
        return s

    def read_number(self) -> int | float:
        """Read a numeric token (int or float)."""
        word = self._next_word()
        if word is None:
            raise ParseError("expected number, got EOF")
        return _parse_number(word)

    def read_int(self) -> int:
        """Read an integer token."""
        word = self._next_word()
        if word is None:
            raise ParseError("expected integer, got EOF")
        try:
            return int(word)
        except ValueError:
            raise ParseError(f"expected integer, got '{word}'")

    def read_f64(self) -> float:
        """Read a numeric value as float (accepts both int and float tokens)."""
        v = self.read_number()
        return float(v)

    def peek_is_number(self) -> bool:
        """Peek at the next word to see if it looks like a number."""
        word = self._peek_word()
        if word is None:
            return False
        try:
            _parse_number(word)
            return True
        except (ValueError, ParseError):
            return False


def _parse_number(word: str) -> int | float:
    """Parse a word as a number (int or float)."""
    if "." in word:
        try:
            return float(word)
        except ValueError:
            raise ParseError(f"not a number: '{word}'")
    try:
        return int(word)
    except ValueError:
        pass
    try:
        return float(word)
    except ValueError:
        raise ParseError(f"not a number: '{word}'")


# ── Header Parsing ─────────────────────────────────────────────────────────

@dataclass
class PresetHeader:
    """Parsed preset header (metadata before the parameter list)."""
    name: str
    pack: str
    author: str
    original_author: str
    description: str
    timestamp: Optional[int] = None
    firmware_version: Optional[str] = None
    metadata: list[tuple[str, str]] = field(default_factory=list)
    param_count: int = 0

    def get_metadata(self, key: str) -> Optional[str]:
        for k, v in self.metadata:
            if k == key:
                return v
        return None

    @property
    def preset_type(self) -> Optional[str]:
        return self.get_metadata("Type")

    @property
    def subtype(self) -> Optional[str]:
        return self.get_metadata("Subtype")


def parse_header(text: str) -> tuple[PresetHeader, int]:
    """Parse the complete header of an .mnfx preset file.

    Returns (header, byte_position) where byte_position is where
    the parameter data begins.
    """
    tok = Tokenizer(text)

    # Archive magic: "22 serialization::archive"
    magic = tok.read_length_prefixed_string()
    if magic != "serialization::archive":
        raise ParseError(
            f"invalid archive magic: expected 'serialization::archive', got '{magic}'"
        )

    # Archive version: 10
    version = tok.read_int()
    if version != 10:
        raise ParseError(f"unsupported archive version: {version}")

    # Class tracking info: 0 7 0 7
    for _ in range(4):
        tok.read_int()

    # Preset name and pack
    name = tok.read_length_prefixed_string()
    pack = tok.read_length_prefixed_string()

    # Class info marker (always 66) then author
    tok.read_int()  # 66
    author = tok.read_length_prefixed_string()
    original_author = tok.read_length_prefixed_string()

    # Six zero fields
    for _ in range(6):
        tok.read_int()

    # Description (length-prefixed string, 0 = empty)
    description = tok.read_length_prefixed_string()

    # Format diverges based on whether description is present
    timestamp = None
    firmware_version = None

    if description:
        # Exported format: timestamp + firmware version + 10 padding zeros
        timestamp = tok.read_int()
        firmware_version = tok.read_length_prefixed_string()
        for _ in range(10):
            tok.read_int()
    else:
        # Factory format: 12 integers of padding (includes -1 timestamp marker)
        for _ in range(12):
            tok.read_int()

    # Metadata key-value pairs
    metadata_count = tok.read_int()
    for _ in range(3):
        tok.read_int()

    metadata = []
    for _ in range(metadata_count):
        key = tok.read_length_prefixed_string()
        value = tok.read_length_prefixed_string()
        metadata.append((key, value))

    # Trailing header: 0 0 0 7 0 0 0 0 0 0
    for _ in range(10):
        tok.read_int()

    # Parameter count + 3 zeros
    param_count = tok.read_int()
    for _ in range(3):
        tok.read_int()

    header = PresetHeader(
        name=name,
        pack=pack,
        author=author,
        original_author=original_author,
        description=description,
        timestamp=timestamp,
        firmware_version=firmware_version,
        metadata=metadata,
        param_count=param_count,
    )
    return header, tok.pos


def parse_parameters(text: str, expected_count: int) -> list[tuple[str, float]]:
    """Parse parameters from the parameter section.

    Each parameter is: ``<name_len> <name> <value>``
    """
    tok = Tokenizer(text)
    params = []
    for i in range(expected_count):
        if tok.is_empty:
            raise ParseError(
                f"unexpected end of input at parameter {i} of {expected_count}"
            )
        name = tok.read_length_prefixed_string()
        value = tok.read_f64()
        params.append((name, value))
    return params


# ── File Extraction ────────────────────────────────────────────────────────

def extract_mnfx_text(data: bytes) -> str:
    """Extract the text content from .mnfx file bytes.

    Handles both bare text files and ZIP archives.
    """
    # Check for ZIP magic (PK\x03\x04)
    if len(data) >= 4 and data[:4] == b"PK\x03\x04":
        return _extract_from_zip(data)

    # Plain text — handle possible trailing binary data
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as e:
        if e.start > 0:
            text = data[:e.start].decode("utf-8")
        else:
            raise ParseError("file is not valid UTF-8 text")
    return text.strip()


def _extract_from_zip(data: bytes) -> str:
    """Extract preset text from a ZIP archive."""
    with zipfile.ZipFile(BytesIO(data)) as zf:
        for name in zf.namelist():
            # Skip PNG thumbnails
            if name.endswith(".png"):
                continue
            # The preset data is under MiniFreak/...
            if name.startswith("MiniFreak/"):
                buf = zf.read(name)
                try:
                    text = buf.decode("utf-8")
                except UnicodeDecodeError as e:
                    text = buf[:e.start].decode("utf-8")
                return text.strip()

    raise ParseError("no preset data found in ZIP archive")
