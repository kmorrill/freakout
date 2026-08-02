"""Device-specific wavetable documents and offline validation."""

from __future__ import annotations

import base64
import wave
from dataclasses import dataclass
from pathlib import Path

from minifreak_patch.microfreak import MicroFreakObject
from minifreak_patch.parser import ParseError
from minifreak_patch.schema import DeviceModel
from minifreak_patch.zipwriter import create_zip


MICROFREAK_WAVETABLE_TAG = "DEVBUILD"
MICROFREAK_SAMPLE_RATE = 32_000
MICROFREAK_CYCLES = 32
MICROFREAK_SAMPLES_PER_CYCLE = 256
MICROFREAK_PCM_BYTES = MICROFREAK_CYCLES * MICROFREAK_SAMPLES_PER_CYCLE * 2

MINIFREAK_FRAMES = 189
MINIFREAK_SAMPLES_PER_FRAME = 512
MINIFREAK_BYTES_PER_SAMPLE = 3
MINIFREAK_RAW_BYTES = (
    MINIFREAK_FRAMES * MINIFREAK_SAMPLES_PER_FRAME * MINIFREAK_BYTES_PER_SAMPLE
)


@dataclass
class WavetableDocument:
    device: DeviceModel
    name: str
    sample_rate: int
    frames: int
    samples_per_frame: int
    sample_format: str
    audio_base64: str
    archive: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "arturia-freak-wavetable/1",
            "device": self.device.value,
            "name": self.name,
            "sample_rate": self.sample_rate,
            "frames": self.frames,
            "samples_per_frame": self.samples_per_frame,
            "sample_format": self.sample_format,
            "audio_base64": self.audio_base64,
        }
        if self.archive is not None:
            result["archive"] = self.archive
        return result


@dataclass
class MicroFreakWavetable:
    name: str
    pcm16le: bytes
    version_tag: str = MICROFREAK_WAVETABLE_TAG
    p0: int = 1
    p3: int = 0
    p5: int = 1
    characteristics_bits: str = "000000000000000000"

    def __post_init__(self) -> None:
        if len(self.name.encode("utf-8")) > 15:
            raise ValueError("MicroFreak wavetable names are at most 15 bytes")
        if len(self.pcm16le) != MICROFREAK_PCM_BYTES:
            raise ValueError(
                f"MicroFreak wavetable must be {MICROFREAK_PCM_BYTES} bytes"
            )
        if not self.version_tag or len(self.version_tag.encode("utf-8")) > 64:
            raise ValueError("MicroFreak wavetable archive tag must be 1..64 bytes")
        if any(not 0 <= value <= 255 for value in (self.p0, self.p3, self.p5)):
            raise ValueError("MicroFreak wavetable archive fields must be 0..255")
        if len(self.characteristics_bits) != 18 or any(
            char not in "01" for char in self.characteristics_bits
        ):
            raise ValueError(
                "MicroFreak wavetable characteristics_bits must be 18 binary characters"
            )

    @classmethod
    def from_mfw(cls, data: bytes) -> "MicroFreakWavetable":
        obj = MicroFreakObject.from_bytes(data)
        if len(obj.payload) != MICROFREAK_PCM_BYTES or obj.p0 != 1 or obj.p5 != 1:
            raise ParseError("not a MicroFreak wavetable archive")
        return cls(
            name=obj.name,
            pcm16le=obj.payload,
            version_tag=obj.version_tag,
            p0=obj.p0,
            p3=obj.p3,
            p5=obj.p5,
            characteristics_bits=obj.characteristics_bits,
        )

    @classmethod
    def from_document(cls, document: dict[str, object]) -> "MicroFreakWavetable":
        expected = {
            "schema_version": "arturia-freak-wavetable/1",
            "device": DeviceModel.MICROFREAK.value,
            "sample_rate": MICROFREAK_SAMPLE_RATE,
            "frames": MICROFREAK_CYCLES,
            "samples_per_frame": MICROFREAK_SAMPLES_PER_CYCLE,
            "sample_format": "pcm_s16le",
        }
        for key, value in expected.items():
            if document.get(key) != value:
                raise ValueError(f"MicroFreak wavetable {key} must be {value!r}")
        name = document.get("name")
        audio = document.get("audio_base64")
        if not isinstance(name, str) or not isinstance(audio, str):
            raise ValueError("MicroFreak wavetable requires string name and audio_base64")
        try:
            pcm = base64.b64decode(audio, validate=True)
        except Exception as exc:
            raise ValueError("invalid MicroFreak wavetable audio_base64") from exc
        archive = document.get("archive", {})
        if not isinstance(archive, dict):
            raise ValueError("MicroFreak wavetable archive must be an object")
        return cls(
            name=name,
            pcm16le=pcm,
            version_tag=str(archive.get("version_tag", MICROFREAK_WAVETABLE_TAG)),
            p0=int(archive.get("p0", 1)),
            p3=int(archive.get("p3", 0)),
            p5=int(archive.get("p5", 1)),
            characteristics_bits=str(
                archive.get("characteristics_bits", "000000000000000000")
            ),
        )

    @classmethod
    def from_wav(cls, path: str | Path, name: str | None = None) -> "MicroFreakWavetable":
        with wave.open(str(path), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                raise ValueError("MicroFreak input WAV must be mono PCM16")
            if wav.getframerate() != MICROFREAK_SAMPLE_RATE:
                raise ValueError("MicroFreak input WAV must be 32000 Hz")
            if wav.getnframes() != MICROFREAK_CYCLES * MICROFREAK_SAMPLES_PER_CYCLE:
                raise ValueError("MicroFreak input WAV must contain 8192 samples")
            pcm = wav.readframes(wav.getnframes())
        return cls(name=name or Path(path).stem[:15], pcm16le=pcm)

    def to_mfw(self) -> bytes:
        return MicroFreakObject(
            version_tag=self.version_tag,
            name=self.name,
            p0=self.p0,
            p3=self.p3,
            p5=self.p5,
            payload=self.pcm16le,
            characteristics_bits=self.characteristics_bits,
        ).to_bytes()

    def to_mfwz(self) -> bytes:
        """Serialize the official one-entry .mfwz wavetable container."""
        return create_zip([("0_sample", self.to_mfw())])

    def to_document(self) -> WavetableDocument:
        return WavetableDocument(
            device=DeviceModel.MICROFREAK,
            name=self.name,
            sample_rate=MICROFREAK_SAMPLE_RATE,
            frames=MICROFREAK_CYCLES,
            samples_per_frame=MICROFREAK_SAMPLES_PER_CYCLE,
            sample_format="pcm_s16le",
            audio_base64=base64.b64encode(self.pcm16le).decode("ascii"),
            archive={
                "version_tag": self.version_tag,
                "p0": self.p0,
                "p3": self.p3,
                "p5": self.p5,
                "characteristics_bits": self.characteristics_bits,
            },
        )


def validate_minifreak_raw(data: bytes) -> WavetableDocument:
    if len(data) != MINIFREAK_RAW_BYTES:
        raise ValueError(
            f"MiniFreak raw wavetable must be {MINIFREAK_RAW_BYTES} bytes "
            f"({MINIFREAK_FRAMES}x{MINIFREAK_SAMPLES_PER_FRAME}x24-bit)"
        )
    return WavetableDocument(
        device=DeviceModel.MINIFREAK,
        name="Wavetable",
        sample_rate=48_000,
        frames=MINIFREAK_FRAMES,
        samples_per_frame=MINIFREAK_SAMPLES_PER_FRAME,
        sample_format="pcm_s24le_raw",
        audio_base64=base64.b64encode(data).decode("ascii"),
    )
