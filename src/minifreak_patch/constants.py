"""MiniFreak parameter constants, enums, and mod matrix encoding.

All values use firmware 4.x encoding. Factory presets (firmware 3.x)
use different spacing — see parameter-analysis.md for the mapping.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


# ── Helper: grid-based enum base class ──────────────────────────────────────
# Python Enum reserves _sunder_ names, so we store grid sizes in a registry.

_GRID_SIZES: dict[type, int] = {}


class GridEnum(Enum):
    """Base for enums encoded as index / grid_size.

    Subclasses pass grid_size as a keyword: ``class Foo(GridEnum, grid_size=N)``.
    Each member's value is the grid index (0-based).
    """

    def __init_subclass__(cls, grid_size: Optional[int] = None, **kwargs):
        super().__init_subclass__(**kwargs)
        if grid_size is not None:
            _GRID_SIZES[cls] = grid_size

    def to_value(self) -> float:
        return self.value / _GRID_SIZES[type(self)]

    @classmethod
    def from_value(cls, v: float) -> Optional["GridEnum"]:
        gs = _GRID_SIZES[cls]
        idx = round(v * gs)
        for member in cls:
            if member.value == idx:
                return member
        return None

    @classmethod
    def from_name(cls, name: str) -> Optional["GridEnum"]:
        lower = name.lower()
        for member in cls:
            if member.label.lower() == lower:
                return member
        compact = re.sub(r"[\s./]", "", lower)
        for member in cls:
            if re.sub(r"[\s./]", "", member.label.lower()) == compact:
                return member
        return None

    def __str__(self) -> str:
        return self.label


# ── Oscillator 1 Engines (24 engines, spacing 1/23) ────────────────────────

class Osc1Engine(GridEnum, grid_size=23):
    BASIC_WAVES = 0
    SUPER_WAVE = 1
    HARMO = 2
    KARPLUS = 3
    V_ANALOG = 4
    WAVESHAPER = 5
    TWO_OP_FM = 6
    FORMANT = 7
    SPEECH = 8
    MODAL = 9
    NOISE = 10
    BASS = 11
    SAW_X = 12
    HARM = 13
    AUDIO_IN = 14
    WAVETABLE = 15
    SAMPLE = 16
    CLOUD_GRAINS = 17
    HIT_GRAINS = 18
    FROZEN = 19
    SKAN = 20
    PARTICLE = 21
    LICK = 22
    RASTER = 23

    @property
    def label(self) -> str:
        return _OSC1_LABELS[self.value]


_OSC1_LABELS = {
    0: "Basic Waves", 1: "SuperWave", 2: "Harmo", 3: "Karplus",
    4: "VAnalog", 5: "Waveshaper", 6: "Two Op. FM", 7: "Formant",
    8: "Speech", 9: "Modal", 10: "Noise", 11: "Bass",
    12: "SawX", 13: "Harm", 14: "Audio In", 15: "Wavetable",
    16: "Sample", 17: "Cloud Grains", 18: "Hit Grains", 19: "Frozen",
    20: "Skan", 21: "Particle", 22: "Lick", 23: "Raster",
}


# ── Oscillator 2 Engines (21 engines, spacing 1/29, 30-slot grid) ──────────

class Osc2Engine(GridEnum, grid_size=29):

    BASIC_WAVES = 0
    SUPER_WAVE = 1
    HARMO = 2
    KARPLUS = 3
    V_ANALOG = 4
    WAVESHAPER = 5
    TWO_OP_FM = 6
    FORMANT = 7
    CHORDS = 8
    SPEECH = 9
    MODAL = 10
    NOISE = 11
    BASS = 12
    SAW_X = 13
    HARM = 14
    FM_RM = 15
    MULTI_FILTER = 16
    SURGEON_FILTER = 17
    COMB_FILTER = 18
    PHASER_FILTER = 19
    DESTROY = 20

    @property
    def label(self) -> str:
        return _OSC2_LABELS[self.value]

    @classmethod
    def from_value(cls, v: float) -> Optional["Osc2Engine"]:
        idx = round(v * 29)
        if idx > 20:
            return None  # indices 21-29 are dummy slots
        for member in cls:
            if member.value == idx:
                return member
        return None


_OSC2_LABELS = {
    0: "Basic Waves", 1: "SuperWave", 2: "Harmo", 3: "Karplus",
    4: "VAnalog", 5: "Waveshaper", 6: "Two Op. FM", 7: "Formant",
    8: "Chords", 9: "Speech", 10: "Modal", 11: "Noise",
    12: "Bass", 13: "SawX", 14: "Harm", 15: "FM/RM",
    16: "Multi Filter", 17: "Surgeon Filter", 18: "Comb Filter",
    19: "Phaser Filter", 20: "Destroy",
}


# ── FX Algorithms (13 algorithms, spacing 1/12) ────────────────────────────

class FxAlgorithm(GridEnum, grid_size=12):

    CHORUS = 0
    PHASER = 1
    FLANGER = 2
    REVERB = 3
    DELAY = 4
    DISTORTION = 5
    BIT_CRUSHER = 6
    THREE_BAND_EQ = 7
    PEAK_EQ = 8
    MULTI_COMP = 9
    SUPER_UNISON = 10
    VOCODER_SELF = 11
    VOCODER_EXT = 12

    @property
    def label(self) -> str:
        return _FX_LABELS[self.value]


_FX_LABELS = {
    0: "Chorus", 1: "Phaser", 2: "Flanger", 3: "Reverb",
    4: "Delay", 5: "Distortion", 6: "Bit Crusher", 7: "3 Band EQ",
    8: "Peak EQ", 9: "Multi Comp", 10: "Super Unison",
    11: "Vocoder Self", 12: "Vocoder Ext",
}


# ── FX Opt1 per-algorithm enums ────────────────────────────────────────────

def _make_opt1_enum(name: str, grid_size: int, labels: list[str]) -> type:
    """Create an FX Opt1 enum dynamically."""
    members = {label.upper().replace(" ", "_").replace("-", "_"): i
               for i, label in enumerate(labels)}
    cls = GridEnum(name, members)
    _GRID_SIZES[cls] = grid_size
    label_map = dict(enumerate(labels))
    cls.label = property(lambda self: label_map[self.value])
    return cls


ChorusOpt1 = _make_opt1_enum("ChorusOpt1", 4,
    ["Default", "Lush", "Dark", "Shaded", "Single"])

PhaserOpt1 = _make_opt1_enum("PhaserOpt1", 5,
    ["Default", "Default Sync", "Space", "Space Sync", "SnH", "SnH Sync"])

FlangerOpt1 = _make_opt1_enum("FlangerOpt1", 3,
    ["Default", "Default Sync", "Silly", "Silly Sync"])

ReverbOpt1 = _make_opt1_enum("ReverbOpt1", 5,
    ["Default", "Long", "Hall", "Echoes", "Room", "Dark Room"])

DelayOpt1 = _make_opt1_enum("DelayOpt1", 11,
    ["Digital", "Digital Sync", "Stereo", "Stereo Sync",
     "Ping-Pong", "Ping-Pong Sync", "Mono", "Mono Sync",
     "Filtered", "Filtered Sync", "Filtered Ping-Pong", "Filtered P-P Sync"])

DistortionOpt1 = _make_opt1_enum("DistortionOpt1", 5,
    ["Classic", "Soft Clip", "Germanium", "Dual Fold", "Climb", "Tape"])

PeakEQOpt1 = _make_opt1_enum("PeakEQOpt1", 2,
    ["Default", "Wide", "Mid 1K"])

SuperUnisonOpt1 = _make_opt1_enum("SuperUnisonOpt1", 7,
    ["Classic", "Ravey", "Soli", "Slow", "Slow Trig", "Wide Trig",
     "Mono Trig", "Wavy"])

VocoderSelfOpt1 = _make_opt1_enum("VocoderSelfOpt1", 3,
    ["Clean", "Vintage", "Narrow", "Gated"])

VocoderExtOpt1 = _make_opt1_enum("VocoderExtOpt1", 3,
    ["Clean", "Vintage", "Narrow", "Gated"])

# Dispatch table: algorithm → Opt1 enum class
FX_OPT1_ENUMS: dict[FxAlgorithm, type] = {
    FxAlgorithm.CHORUS: ChorusOpt1,
    FxAlgorithm.PHASER: PhaserOpt1,
    FxAlgorithm.FLANGER: FlangerOpt1,
    FxAlgorithm.REVERB: ReverbOpt1,
    FxAlgorithm.DELAY: DelayOpt1,
    FxAlgorithm.DISTORTION: DistortionOpt1,
    FxAlgorithm.PEAK_EQ: PeakEQOpt1,
    FxAlgorithm.SUPER_UNISON: SuperUnisonOpt1,
    FxAlgorithm.VOCODER_SELF: VocoderSelfOpt1,
    FxAlgorithm.VOCODER_EXT: VocoderExtOpt1,
}


def fx_opt1_label(algo: FxAlgorithm, value: float) -> Optional[str]:
    """Look up FX Opt1 label by algorithm and float value."""
    enum_cls = FX_OPT1_ENUMS.get(algo)
    if enum_cls is None:
        return None
    member = enum_cls.from_value(value)
    return member.label if member else None


def fx_opt1_from_name(algo: FxAlgorithm, name: str) -> Optional[float]:
    """Look up FX Opt1 value by algorithm and sub-mode name."""
    enum_cls = FX_OPT1_ENUMS.get(algo)
    if enum_cls is None:
        return None
    member = enum_cls.from_name(name)
    return member.to_value() if member else None


# ── Filter Mode (3 modes, non-standard spacing) ────────────────────────────

class FilterMode(Enum):
    LOW_PASS = "LPF"
    BAND_PASS = "BPF"
    HIGH_PASS = "HPF"

    @property
    def label(self) -> str:
        return self.value

    def to_value(self) -> float:
        return {
            FilterMode.LOW_PASS: 0.0,
            FilterMode.BAND_PASS: 1.0 / 6.0,
            FilterMode.HIGH_PASS: 2.0 / 6.0,
        }[self]

    @classmethod
    def from_value(cls, v: float) -> Optional["FilterMode"]:
        if v < 0.083:
            return cls.LOW_PASS
        elif v < 0.25:
            return cls.BAND_PASS
        elif v < 0.5:
            return cls.HIGH_PASS
        return None

    @classmethod
    def from_name(cls, name: str) -> Optional["FilterMode"]:
        lower = name.lower()
        if lower in ("lpf", "lowpass", "low pass", "lp"):
            return cls.LOW_PASS
        if lower in ("bpf", "bandpass", "band pass", "bp"):
            return cls.BAND_PASS
        if lower in ("hpf", "highpass", "high pass", "hp"):
            return cls.HIGH_PASS
        return None

    def __str__(self) -> str:
        return self.label


# ── Tune Mod Quantize (11 options, spacing 1/10) ───────────────────────────

class TuneModQuantize(GridEnum, grid_size=10):

    CONTINUOUS = 0
    CHROMATIC = 1
    OCTAVES = 2
    FIFTHS = 3
    MINOR = 4
    MAJOR = 5
    PHRYGIAN_DOM = 6
    MINOR_9TH = 7
    MAJOR_9TH = 8
    MINOR_PENTA = 9
    MAJOR_PENTA = 10

    @property
    def label(self) -> str:
        return _TUNE_MOD_LABELS[self.value]


_TUNE_MOD_LABELS = {
    0: "Continuous", 1: "Chromatic", 2: "Octaves", 3: "Fifths",
    4: "Minor", 5: "Major", 6: "Phrygian Dom", 7: "Minor 9th",
    8: "Major 9th", 9: "Minor Penta", 10: "Major Penta",
}


# ── LFO Waveform (9 types, spacing 1/8) ────────────────────────────────────

class LfoWaveform(GridEnum, grid_size=8):

    SINE = 0
    TRIANGLE = 1
    SAW = 2
    SQUARE = 3
    SAMPLE_AND_HOLD = 4
    SLEW_SH = 5
    EXP_SAW = 6
    EXP_RAMP = 7
    SHAPER = 8

    @property
    def label(self) -> str:
        return _LFO_WAVE_LABELS[self.value]

    @classmethod
    def from_name(cls, name: str) -> Optional["LfoWaveform"]:
        lower = name.lower()
        _map = {
            "sine": cls.SINE, "sin": cls.SINE,
            "tri": cls.TRIANGLE, "triangle": cls.TRIANGLE,
            "saw": cls.SAW, "sawtooth": cls.SAW,
            "sqr": cls.SQUARE, "square": cls.SQUARE,
            "s&h": cls.SAMPLE_AND_HOLD, "snh": cls.SAMPLE_AND_HOLD,
            "sampleandhold": cls.SAMPLE_AND_HOLD,
            "sample and hold": cls.SAMPLE_AND_HOLD,
            "sh": cls.SAMPLE_AND_HOLD, "s+h": cls.SAMPLE_AND_HOLD,
            "slew s&h": cls.SLEW_SH, "slewsh": cls.SLEW_SH,
            "slewsnh": cls.SLEW_SH, "slew sh": cls.SLEW_SH,
            "slew s+h": cls.SLEW_SH,
            "exp saw": cls.EXP_SAW, "expsaw": cls.EXP_SAW,
            "exp ramp": cls.EXP_RAMP, "expramp": cls.EXP_RAMP,
            "shaper": cls.SHAPER,
        }
        return _map.get(lower)


_LFO_WAVE_LABELS = {
    0: "Sine", 1: "Tri", 2: "Saw", 3: "Sqr",
    4: "S&H", 5: "Slew S&H", 6: "Exp Saw", 7: "Exp Ramp", 8: "Shaper",
}


# ── LFO Retrig Mode (8 modes, spacing 1/7) ─────────────────────────────────

class LfoRetrigMode(GridEnum, grid_size=7):

    FREE = 0
    POLY_KBD = 1
    MONO_KBD = 2
    LEGATO_KBD = 3
    ONE = 4
    OTHER_LFO = 5  # LFO2 when on LFO1, LFO1 when on LFO2
    CYC_ENV = 6
    SEQ_START = 7

    @property
    def label(self) -> str:
        return _LFO_RETRIG_LABELS[self.value]


_LFO_RETRIG_LABELS = {
    0: "Free", 1: "Poly Kbd", 2: "Mono Kbd", 3: "Legato Kbd",
    4: "One", 5: "Other LFO", 6: "CycEnv", 7: "Seq Start",
}


# ── LFO Rate Sync (27 divisions, spacing 1/26) ─────────────────────────────

class LfoRateSync(GridEnum, grid_size=26):

    BARS_8_DOT = 0
    BARS_8 = 1
    BARS_4_DOT = 2
    BARS_4_TRI = 3
    BARS_4 = 4
    BARS_2_DOT = 5
    BARS_2_TRI = 6
    BARS_2 = 7
    BARS_1_DOT = 8
    BARS_1_TRI = 9
    BARS_1 = 10
    HALF_DOT = 11
    WHOLE_TRI = 12
    HALF = 13
    QUARTER_DOT = 14
    HALF_TRI = 15
    QUARTER = 16
    EIGHTH_DOT = 17
    QUARTER_TRI = 18
    EIGHTH = 19
    SIXTEENTH_DOT = 20
    EIGHTH_TRI = 21
    SIXTEENTH = 22
    THIRTY_SECOND_DOT = 23
    SIXTEENTH_TRI = 24
    THIRTY_SECOND = 25
    THIRTY_SECOND_TRI = 26

    @property
    def label(self) -> str:
        return _LFO_SYNC_LABELS[self.value]

    @classmethod
    def from_name(cls, name: str) -> Optional["LfoRateSync"]:
        upper = name.upper()
        for member in cls:
            if member.label.upper() == upper:
                return member
        return None


_LFO_SYNC_LABELS = {
    0: "8d", 1: "8", 2: "4d", 3: "4t", 4: "4", 5: "2d", 6: "2t", 7: "2",
    8: "1d", 9: "1t", 10: "1", 11: "1/2d", 12: "1t", 13: "1/2",
    14: "1/4d", 15: "1/2t", 16: "1/4", 17: "1/8d", 18: "1/4t", 19: "1/8",
    20: "1/16d", 21: "1/8t", 22: "1/16", 23: "1/32d", 24: "1/16t",
    25: "1/32", 26: "1/32t",
}


# ── LFO Sync Filter (5 options, spacing 1/4) ───────────────────────────────

class LfoSyncFilter(GridEnum, grid_size=4):

    ALL = 0
    STRAIGHT = 1
    TRIPLET = 2
    DOTTED = 3
    FREE = 4

    @property
    def label(self) -> str:
        return _LFO_SYNC_FILTER_LABELS[self.value]


_LFO_SYNC_FILTER_LABELS = {
    0: "All", 1: "Straight", 2: "Triplet", 3: "Dotted", 4: "Free",
}


# ── Voice / Note Mode (4 modes, spacing 1/3) ───────────────────────────────

class NoteMode(GridEnum, grid_size=3):

    MONO = 0
    UNISON = 1
    POLY = 2
    PARA = 3

    @property
    def label(self) -> str:
        return _NOTE_MODE_LABELS[self.value]


_NOTE_MODE_LABELS = {0: "Mono", 1: "Unison", 2: "Poly", 3: "Para"}


# ── Unison Count (4 values, non-standard spacing) ──────────────────────────

class UnisonCount(Enum):
    TWO = 2
    THREE = 3
    FOUR = 4
    SIX = 6

    @property
    def label(self) -> str:
        return str(self.value)

    def to_value(self) -> float:
        return {2: 0.0, 3: 0.25, 4: 0.5, 6: 1.0}[self.value]

    @classmethod
    def from_value(cls, v: float) -> Optional["UnisonCount"]:
        if v < 0.125:
            return cls.TWO
        elif v < 0.375:
            return cls.THREE
        elif v < 0.75:
            return cls.FOUR
        else:
            return cls.SIX

    @classmethod
    def from_name(cls, name: str) -> Optional["UnisonCount"]:
        return {
            "2": cls.TWO, "3": cls.THREE, "4": cls.FOUR, "6": cls.SIX,
        }.get(name.strip())

    def __str__(self) -> str:
        return self.label


# ── Poly Voice Allocation (3 modes, spacing 1/2) ───────────────────────────

class PolyAlloc(GridEnum, grid_size=2):

    CYCLE = 0
    REASSIGN = 1
    RESET = 2

    @property
    def label(self) -> str:
        return _POLY_ALLOC_LABELS[self.value]


_POLY_ALLOC_LABELS = {0: "Cycle", 1: "Reassign", 2: "Reset"}


# ── Poly Voice Stealing (3 modes, spacing 1/2) ─────────────────────────────

class PolySteal(GridEnum, grid_size=2):

    OLDEST = 0
    LOWEST = 1
    NONE = 2

    @property
    def label(self) -> str:
        return _POLY_STEAL_LABELS[self.value]


_POLY_STEAL_LABELS = {0: "Oldest", 1: "Lowest", 2: "None"}


# ── Unison Mode (3 modes, spacing 1/2) ─────────────────────────────────────

class UnisonMode(GridEnum, grid_size=2):

    UNISON = 0
    UNI_POLY = 1
    UNI_PARA = 2

    @property
    def label(self) -> str:
        return _UNISON_MODE_LABELS[self.value]


_UNISON_MODE_LABELS = {0: "Unison", 1: "Uni Poly", 2: "Uni Para"}


# ── Retrig Mode (2 modes, boolean) ─────────────────────────────────────────

class RetrigMode(Enum):
    ENV_RESET = 0
    ENV_CONTINUE = 1

    @property
    def label(self) -> str:
        return "Env Reset" if self == RetrigMode.ENV_RESET else "Env Continue"

    def to_value(self) -> float:
        return float(self.value)

    @classmethod
    def from_value(cls, v: float) -> "RetrigMode":
        return cls.ENV_CONTINUE if v >= 0.5 else cls.ENV_RESET

    @classmethod
    def from_name(cls, name: str) -> Optional["RetrigMode"]:
        compact = re.sub(r"\s", "", name.lower())
        if compact in ("envreset", "reset"):
            return cls.ENV_RESET
        if compact in ("envcontinue", "continue"):
            return cls.ENV_CONTINUE
        return None

    def __str__(self) -> str:
        return self.label


# ── Seq Mode (3 modes, spacing 1/2) ────────────────────────────────────────

class SeqMode(GridEnum, grid_size=2):

    OFF = 0
    ARP = 1
    SEQ = 2

    @property
    def label(self) -> str:
        return _SEQ_MODE_LABELS[self.value]

    @classmethod
    def from_value(cls, v: float) -> Optional["SeqMode"]:
        if v < 0.25:
            return cls.OFF
        elif v < 0.75:
            return cls.ARP
        else:
            return cls.SEQ


_SEQ_MODE_LABELS = {0: "Off", 1: "Arp", 2: "Seq"}


# ── Arp Mode (7 modes + gap at index 4, spacing 1/7) ──────────────────────

class ArpMode(Enum):
    UP = 0
    DOWN = 1
    UP_DOWN = 2
    RANDOM = 3
    PATTERN = 5
    ORDER = 6
    POLY = 7

    @property
    def label(self) -> str:
        return _ARP_MODE_LABELS[self.value]

    def to_value(self) -> float:
        return self.value / 7.0

    @classmethod
    def from_value(cls, v: float) -> Optional["ArpMode"]:
        idx = round(v * 7)
        for member in cls:
            if member.value == idx:
                return member
        return None

    @classmethod
    def from_name(cls, name: str) -> Optional["ArpMode"]:
        lower = name.lower()
        _map = {
            "up": cls.UP, "down": cls.DOWN,
            "up/down": cls.UP_DOWN, "updown": cls.UP_DOWN, "up down": cls.UP_DOWN,
            "random": cls.RANDOM, "rand": cls.RANDOM,
            "pattern": cls.PATTERN, "order": cls.ORDER, "poly": cls.POLY,
        }
        return _map.get(lower)

    def __str__(self) -> str:
        return self.label


_ARP_MODE_LABELS = {
    0: "Up", 1: "Down", 2: "Up/Down", 3: "Random",
    5: "Pattern", 6: "Order", 7: "Poly",
}


# ── Arp Octave (4 values, spacing 1/3) ─────────────────────────────────────

class ArpOct(GridEnum, grid_size=3):

    OCT1 = 0
    OCT2 = 1
    OCT3 = 2
    OCT4 = 3

    @property
    def label(self) -> str:
        return f"Oct{self.value + 1}"

    @classmethod
    def from_name(cls, name: str) -> Optional["ArpOct"]:
        s = name.strip().lower()
        _map = {
            "1": cls.OCT1, "oct1": cls.OCT1,
            "2": cls.OCT2, "oct2": cls.OCT2,
            "3": cls.OCT3, "oct3": cls.OCT3,
            "4": cls.OCT4, "oct4": cls.OCT4,
        }
        return _map.get(s)


# ── CycEnv Mode (3 modes, spacing 1/2) ─────────────────────────────────────

class CycEnvMode(GridEnum, grid_size=2):

    ENV = 0
    RUN = 1
    LOOP = 2

    @property
    def label(self) -> str:
        return _CYCENV_MODE_LABELS[self.value]


_CYCENV_MODE_LABELS = {0: "Env", 1: "Run", 2: "Loop"}


# ── CycEnv Retrig Source (5 options, spacing 1/4) ──────────────────────────

class CycEnvRetrigSrc(GridEnum, grid_size=4):

    POLY_KBD = 0
    MONO_KBD = 1
    LEGATO_KBD = 2
    LFO1 = 3
    LFO2 = 4

    @property
    def label(self) -> str:
        return _CYCENV_RETRIG_LABELS[self.value]


_CYCENV_RETRIG_LABELS = {
    0: "Poly Kbd", 1: "Mono Kbd", 2: "Legato Kbd", 3: "LFO1", 4: "LFO2",
}


# ── CycEnv Stage Order (3 options, spacing 1/2) ───────────────────────────

class CycEnvStageOrder(GridEnum, grid_size=2):

    RISE_HOLD_FALL = 0
    RISE_FALL_HOLD = 1
    HOLD_RISE_FALL = 2

    @property
    def label(self) -> str:
        return _CYCENV_ORDER_LABELS[self.value]


_CYCENV_ORDER_LABELS = {
    0: "Rise Hold Fall", 1: "Rise Fall Hold", 2: "Hold Rise Fall",
}


# ── Velocity/Aftertouch Mode ───────────────────────────────────────────────

class VeloAtMode(Enum):
    VELOCITY = "Velocity"
    AFTERTOUCH = "Aftertouch"
    VELO_PLUS_AT = "Velo + AT"

    @property
    def label(self) -> str:
        return self.value

    def to_value(self) -> float:
        return {
            VeloAtMode.VELOCITY: 0.0,
            VeloAtMode.AFTERTOUCH: 0.5,
            VeloAtMode.VELO_PLUS_AT: 1.0,
        }[self]

    @classmethod
    def from_value(cls, v: float) -> Optional["VeloAtMode"]:
        if v < 0.25:
            return cls.VELOCITY
        elif v < 0.75:
            return cls.AFTERTOUCH
        else:
            return cls.VELO_PLUS_AT

    @classmethod
    def from_name(cls, name: str) -> Optional["VeloAtMode"]:
        compact = name.lower().replace(" ", "").replace("+", "")
        if compact in ("velocity",):
            return cls.VELOCITY
        if compact in ("aftertouch", "at"):
            return cls.AFTERTOUCH
        if compact in ("veloplusat", "veloat", "velocityaftertouch"):
            return cls.VELO_PLUS_AT
        return None

    def __str__(self) -> str:
        return self.label


# ── Sequencer Time Division (15 values, spacing 1/14) ──────────────────────

class SeqTimeDiv(GridEnum, grid_size=14):

    HALF_DOTTED = 0
    HALF = 1
    QUARTER_DOTTED = 2
    HALF_TRIPLET = 3
    QUARTER = 4
    EIGHTH_DOTTED = 5
    QUARTER_TRIPLET = 6
    EIGHTH = 7
    SIXTEENTH_DOTTED = 8
    EIGHTH_TRIPLET = 9
    SIXTEENTH = 10
    THIRTY_SECOND_DOTTED = 11
    SIXTEENTH_TRIPLET = 12
    THIRTY_SECOND = 13
    THIRTY_SECOND_TRIPLET = 14

    @property
    def label(self) -> str:
        return _SEQ_TIME_DIV_LABELS[self.value]

    @classmethod
    def from_name(cls, name: str) -> Optional["SeqTimeDiv"]:
        upper = name.upper()
        for member in cls:
            if member.label.upper() == upper:
                return member
        return None


_SEQ_TIME_DIV_LABELS = {
    0: "1/2D", 1: "1/2", 2: "1/4D", 3: "1/2T", 4: "1/4",
    5: "1/8D", 6: "1/4T", 7: "1/8", 8: "1/16D", 9: "1/8T",
    10: "1/16", 11: "1/32D", 12: "1/16T", 13: "1/32", 14: "1/32T",
}


# ── Mod Matrix Types ───────────────────────────────────────────────────────

class ModSource(Enum):
    CYC_ENV = 0
    ENVELOPE = 1
    LFO1 = 2
    LFO2 = 3
    VELO_AT = 4
    WHEEL = 5
    KBD = 6

    @property
    def label(self) -> str:
        return _MOD_SRC_LABELS[self.value]

    @classmethod
    def from_name(cls, name: str) -> Optional["ModSource"]:
        lower = name.lower()
        _map = {
            "cycenv": cls.CYC_ENV, "cycling env": cls.CYC_ENV,
            "cycling envelope": cls.CYC_ENV,
            "envelope": cls.ENVELOPE, "env": cls.ENVELOPE,
            "lfo 1": cls.LFO1, "lfo1": cls.LFO1,
            "lfo 2": cls.LFO2, "lfo2": cls.LFO2,
            "velo/at": cls.VELO_AT, "velocity": cls.VELO_AT,
            "aftertouch": cls.VELO_AT, "velo": cls.VELO_AT,
            "veloat": cls.VELO_AT,
            "wheel": cls.WHEEL, "mod wheel": cls.WHEEL, "modwheel": cls.WHEEL,
            "kbd": cls.KBD, "keyboard": cls.KBD,
        }
        return _map.get(lower)

    def __str__(self) -> str:
        return self.label


_MOD_SRC_LABELS = {
    0: "CycEnv", 1: "Envelope", 2: "LFO 1", 3: "LFO 2",
    4: "Velo/AT", 5: "Wheel", 6: "Kbd",
}


class ModCluster(Enum):
    """Mod destination address cluster."""
    A = 0x9000  # Synth engine parameters
    B = 0xA000  # FX parameters

    def __str__(self) -> str:
        return self.name


# ── Mod Destination Encoding/Decoding ──────────────────────────────────────

MOD_DEST_NONE: float = 32769.0 / 65536.0


def encode_mod_dest(cluster: ModCluster, offset: int) -> float:
    return (cluster.value + offset) / 65536.0


def decode_mod_dest(value: float) -> Optional[tuple[ModCluster, int]]:
    raw = round(value * 65536)
    if raw == 32769:
        return None
    if 0x9000 <= raw < 0xA000:
        return (ModCluster.A, raw - 0x9000)
    if 0xA000 <= raw < 0xB000:
        return (ModCluster.B, raw - 0xA000)
    return None


# ── Mod Destination Name Tables ────────────────────────────────────────────

_MOD_DEST_A: dict[int, str] = {
    4: "Osc1 Type", 5: "Osc1 Wave", 6: "Osc1 Timbre", 7: "Osc1 Shape",
    11: "Osc1 Volume",
    14: "Osc2 Type", 15: "Osc2 Wave", 16: "Osc2 Timbre", 17: "Osc2 Shape",
    21: "Osc2 Volume", 22: "Glide",
    26: "Cutoff", 27: "Reso", 28: "Env Amt", 29: "VCA",
    30: "Attack", 31: "Decay", 32: "Sustain", 33: "Release",
    40: "Rise", 41: "Fall", 42: "Hold",
    49: "LFO1 Rate", 50: "LFO1 Rate (Sync)", 51: "LFO1 Wave",
    55: "LFO2 Wave", 56: "LFO2 Rate", 57: "LFO2 Rate (Sync)",
    62: "Macro 1", 63: "Macro 2",
    83: "Uni Spread",
    193: "Vib AM",
    197: "Pitch 1", 198: "Pitch 2",
    201: "LFO2 AM", 202: "CycEnv AM", 203: "LFO1 AM",
    204: "Vibrato Rate",
}

_MOD_DEST_B: dict[int, str] = {
    3: "FX1 Time", 4: "FX1 Intensity", 5: "FX1 Amount",
    12: "FX2 Time", 13: "FX2 Intensity", 14: "FX2 Amount",
    21: "FX3 Time", 22: "FX3 Intensity", 23: "FX3 Amount",
}


def mod_dest_name(cluster: ModCluster, offset: int) -> Optional[str]:
    table = _MOD_DEST_A if cluster == ModCluster.A else _MOD_DEST_B
    return table.get(offset)


def mod_dest_label(cluster: ModCluster, offset: int) -> str:
    return f"{cluster}+{offset}"


def decode_meta_mod(offset: int) -> Optional[tuple[int, int]]:
    """Decode a meta-mod destination offset to (row 1-7, col 1-13)."""
    if 97 <= offset <= 124:
        rel = offset - 97
        return (rel // 4 + 1, rel % 4 + 1)
    if 125 <= offset <= 187:
        rel = offset - 125
        return (rel // 9 + 1, rel % 9 + 5)
    return None


def mod_dest_description(cluster: ModCluster, offset: int) -> str:
    name = mod_dest_name(cluster, offset)
    if name:
        return name
    if cluster == ModCluster.A:
        rc = decode_meta_mod(offset)
        if rc:
            return f"Mod {rc[0]}:{rc[1]}"
    return mod_dest_label(cluster, offset)


# ── Named Mod Destination Constants ────────────────────────────────────────

DEST_OSC1_TYPE = (ModCluster.A, 4)
DEST_OSC1_WAVE = (ModCluster.A, 5)
DEST_OSC1_TIMBRE = (ModCluster.A, 6)
DEST_OSC1_SHAPE = (ModCluster.A, 7)
DEST_OSC1_VOLUME = (ModCluster.A, 11)
DEST_OSC2_TYPE = (ModCluster.A, 14)
DEST_OSC2_WAVE = (ModCluster.A, 15)
DEST_OSC2_TIMBRE = (ModCluster.A, 16)
DEST_OSC2_SHAPE = (ModCluster.A, 17)
DEST_OSC2_VOLUME = (ModCluster.A, 21)
DEST_GLIDE = (ModCluster.A, 22)
DEST_CUTOFF = (ModCluster.A, 26)
DEST_RESO = (ModCluster.A, 27)
DEST_ENV_AMT = (ModCluster.A, 28)
DEST_VCA = (ModCluster.A, 29)
DEST_ATTACK = (ModCluster.A, 30)
DEST_DECAY = (ModCluster.A, 31)
DEST_SUSTAIN = (ModCluster.A, 32)
DEST_RELEASE = (ModCluster.A, 33)
DEST_RISE = (ModCluster.A, 40)
DEST_FALL = (ModCluster.A, 41)
DEST_HOLD = (ModCluster.A, 42)
DEST_LFO1_RATE = (ModCluster.A, 49)
DEST_LFO1_RATE_SYNC = (ModCluster.A, 50)
DEST_LFO1_WAVE = (ModCluster.A, 51)
DEST_LFO2_WAVE = (ModCluster.A, 55)
DEST_LFO2_RATE = (ModCluster.A, 56)
DEST_LFO2_RATE_SYNC = (ModCluster.A, 57)
DEST_MACRO1 = (ModCluster.A, 62)
DEST_MACRO2 = (ModCluster.A, 63)
DEST_UNI_SPREAD = (ModCluster.A, 83)
DEST_VIB_AM = (ModCluster.A, 193)
DEST_PITCH1 = (ModCluster.A, 197)
DEST_PITCH2 = (ModCluster.A, 198)
DEST_LFO2_AM = (ModCluster.A, 201)
DEST_CYCENV_AM = (ModCluster.A, 202)
DEST_LFO1_AM = (ModCluster.A, 203)
DEST_VIBRATO_RATE = (ModCluster.A, 204)

DEST_FX1_TIME = (ModCluster.B, 3)
DEST_FX1_INTENSITY = (ModCluster.B, 4)
DEST_FX1_AMOUNT = (ModCluster.B, 5)
DEST_FX2_TIME = (ModCluster.B, 12)
DEST_FX2_INTENSITY = (ModCluster.B, 13)
DEST_FX2_AMOUNT = (ModCluster.B, 14)
DEST_FX3_TIME = (ModCluster.B, 21)
DEST_FX3_INTENSITY = (ModCluster.B, 22)
DEST_FX3_AMOUNT = (ModCluster.B, 23)


# ── Mod Matrix Layout Constants ────────────────────────────────────────────

HARDWIRED_COLS = 4
ASSIGNABLE_COLS = 9
MOD_ROWS = 7
HARDWIRED_DEST_NAMES = ["Pitch 1+2", "Osc1 Wave", "Osc1 Timbre", "Cutoff"]


# ── Mod Destination Name Lookup ────────────────────────────────────────────

_DEST_NAME_TABLE: dict[str, tuple[ModCluster, int]] = {
    "osc1type": DEST_OSC1_TYPE, "osc1wave": DEST_OSC1_WAVE,
    "osc1timbre": DEST_OSC1_TIMBRE, "osc1shape": DEST_OSC1_SHAPE,
    "osc1volume": DEST_OSC1_VOLUME,
    "osc2type": DEST_OSC2_TYPE, "osc2wave": DEST_OSC2_WAVE,
    "osc2timbre": DEST_OSC2_TIMBRE, "osc2shape": DEST_OSC2_SHAPE,
    "osc2volume": DEST_OSC2_VOLUME,
    "glide": DEST_GLIDE,
    "cutoff": DEST_CUTOFF, "reso": DEST_RESO, "resonance": DEST_RESO,
    "envamt": DEST_ENV_AMT, "envamount": DEST_ENV_AMT,
    "filterenvamount": DEST_ENV_AMT,
    "vca": DEST_VCA,
    "attack": DEST_ATTACK, "decay": DEST_DECAY,
    "sustain": DEST_SUSTAIN, "release": DEST_RELEASE,
    "rise": DEST_RISE, "fall": DEST_FALL, "hold": DEST_HOLD,
    "lfo1rate": DEST_LFO1_RATE, "lfo1wave": DEST_LFO1_WAVE,
    "lfo2wave": DEST_LFO2_WAVE, "lfo2rate": DEST_LFO2_RATE,
    "macro1": DEST_MACRO1, "macro2": DEST_MACRO2,
    "unispread": DEST_UNI_SPREAD, "unisonspread": DEST_UNI_SPREAD,
    "pitch1": DEST_PITCH1, "pitch2": DEST_PITCH2,
    "fx1time": DEST_FX1_TIME, "fx1intensity": DEST_FX1_INTENSITY,
    "fx1amount": DEST_FX1_AMOUNT,
    "fx2time": DEST_FX2_TIME, "fx2intensity": DEST_FX2_INTENSITY,
    "fx2amount": DEST_FX2_AMOUNT,
    "fx3time": DEST_FX3_TIME, "fx3intensity": DEST_FX3_INTENSITY,
    "fx3amount": DEST_FX3_AMOUNT,
    "lfo1am": DEST_LFO1_AM, "lfo2am": DEST_LFO2_AM,
    "cycenvam": DEST_CYCENV_AM,
    "vibratorate": DEST_VIBRATO_RATE,
    "vibratoam": DEST_VIB_AM, "vibam": DEST_VIB_AM,
}


def _meta_mod_dest_from_name(spec: str) -> Optional[tuple[ModCluster, int]]:
    """Resolve meta-modulation destination from '<src>:<dest>' string."""
    parts = spec.split(":", 1)
    if len(parts) != 2:
        return None
    src_str, dest_str = parts[0].strip(), parts[1].strip()

    # Try numeric row:col
    try:
        row, col = int(src_str), int(dest_str)
        if 1 <= row <= 7 and 1 <= col <= 13:
            if col <= 4:
                offset = 97 + 4 * (row - 1) + (col - 1)
            else:
                offset = 125 + 9 * (row - 1) + (col - 5)
            return (ModCluster.A, offset)
        return None
    except ValueError:
        pass

    # Named source → row
    src = ModSource.from_name(src_str)
    if src is None:
        return None
    row = src.value + 1

    # Named dest → hardwired column
    col = _hardwired_dest_col(dest_str)
    if col is None:
        return None

    offset = 97 + 4 * (row - 1) + (col - 1)
    return (ModCluster.A, offset)


def _hardwired_dest_col(name: str) -> Optional[int]:
    """Resolve hardwired destination name to 1-based column (1-4)."""
    compact = re.sub(r"\s", "", name.lower())
    _map = {
        "pitch1+2": 1, "pitch": 1, "pitch1": 1, "pitch2": 1,
        "osc1wave": 2, "wave": 2,
        "osc1timbre": 3, "timbre": 3,
        "cutoff": 4,
    }
    return _map.get(compact)


def mod_dest_from_name(name: str) -> Optional[tuple[ModCluster, int]]:
    """Look up a mod destination by human-readable name.

    Accepts names like "Cutoff", "Osc1 Wave", "FX2 Time".
    Also supports meta-mod syntax: "Mod CycEnv:Cutoff" or "Mod 3:7".
    """
    trimmed = name.strip()
    if len(trimmed) > 4 and trimmed[:4].lower() == "mod ":
        return _meta_mod_dest_from_name(trimmed[4:])

    compact = re.sub(r"\s", "", trimmed.lower())
    return _DEST_NAME_TABLE.get(compact)


# ── Note Name Parsing ──────────────────────────────────────────────────────

_NOTE_RE = re.compile(r"^([A-Ga-g])([#b]?)(-?\d+)$")


def parse_note_name(name: str) -> Optional[int]:
    """Parse a note name to MIDI note number. C4 = 60."""
    m = _NOTE_RE.match(name.strip())
    if not m:
        return None

    base_semitones = {
        "C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11,
    }
    base = base_semitones[m.group(1).upper()]
    accidental = {"#": 1, "b": -1, "": 0}[m.group(2)]
    octave = int(m.group(3))

    note = (octave + 1) * 12 + base + accidental
    if 0 <= note <= 127:
        return note
    return None
