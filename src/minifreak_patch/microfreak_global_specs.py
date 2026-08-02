"""Audited value domains for MicroFreak global settings.

The names/codes come from the fingerprinted MIDI Control Center command table.
Value domains and display labels were independently transcribed from Arturia's
installed MicroFreak device description. Settings absent from that description
remain raw-only and are deliberately not assigned guessed domains.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MicroFreakGlobalValueSpec:
    allowed_values: tuple[int, ...]
    labels: dict[int, str]
    evidence: str = "installed_microfreak_device_description_audited"

    def label(self, raw_value: int) -> str | None:
        return self.labels.get(raw_value)


def _spec(
    labels: dict[int, str],
    *,
    evidence: str = "installed_microfreak_device_description_audited",
) -> MicroFreakGlobalValueSpec:
    return MicroFreakGlobalValueSpec(tuple(labels), labels, evidence)


def _sequential(*labels: str) -> MicroFreakGlobalValueSpec:
    return _spec(dict(enumerate(labels)))


def _on_off() -> MicroFreakGlobalValueSpec:
    return _sequential("Off", "On")


def _firmware_spec(labels: dict[int, str]) -> MicroFreakGlobalValueSpec:
    return _spec(labels, evidence="firmware_5_global_setter_clamp_static")


def _firmware_on_off() -> MicroFreakGlobalValueSpec:
    return _firmware_spec({0: "Off", 1: "On"})


_NOTES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _midi_note_label(value: int) -> str:
    return f"{_NOTES[value % 12]}{value // 12 - 2}"


MICROFREAK_GLOBAL_VALUE_SPECS: dict[str, MicroFreakGlobalValueSpec] = {
    "midi.channel_in": _spec(
        {**{value: str(value + 1) for value in range(16)}, 126: "None", 127: "All"}
    ),
    "midi.channel_out": _spec({value: str(value + 1) for value in range(16)}),
    "clock.source": _sequential("Internal", "USB", "MIDI", "Clock", "Auto"),
    "midi.knob_send_cc": _on_off(),
    "midi.automation_in": _on_off(),
    "midi.automation_out": _firmware_on_off(),
    "midi.output_destination": _spec(
        {0: "None", 1: "USB", 4: "MIDI", 5: "Both"}
    ),
    "midi.local_control": _on_off(),
    "control.knob_catch": _sequential("Jump", "Hook", "Scaled"),
    "control.pause_exit_mode": _firmware_on_off(),
    "control.click_to_load": _on_off(),
    "midi.arp_seq_notes_out": _on_off(),
    "midi.thru": _on_off(),
    "midi.merge": _spec(
        {1: "USB+KBD", 2: "MIDI+KBD", 3: "MIDI+USB+KBD"}
    ),
    "keyboard.velocity_curve": _sequential("Lin", "Log", "Exp"),
    "keyboard.aftertouch_curve": _sequential("Lin", "Log", "Exp"),
    "midi.program_change_enable": _on_off(),
    "device.id": _firmware_spec(
        {value: str(value) for value in range(127)}
    ),
    "midi.automation_14bit": _firmware_on_off(),
    "keyboard.aftertouch_compensation": _spec(
        {value: f"{value}%" for value in range(0, 101, 10)}
    ),
    "clock.sync_port_timing": _spec(
        {1: "1step (Clock)", 2: "1pulse (Korg)", 3: "24ppq", 4: "48ppq"}
    ),
    "clock.sync_port_start": _firmware_on_off(),
    "clock.global_tempo": _on_off(),
    "cv.pitch_format": _sequential("1V/Oct", "Hz/V", "1.2V/Oct"),
    "cv.gate_format": _sequential("S-trig", "V-trig 5V", "V-trig 12V"),
    "cv.press_range": _spec({value: f"{value + 1} V" for value in range(10)}),
    "cv.zero_volt_reference": _spec(
        {value: _midi_note_label(value) for value in range(128)}
    ),
    "cv.one_volt_reference": _spec(
        {value: _midi_note_label(value) for value in range(128)}
    ),
    "tuning.master": _spec(
        {
            value: f"{value - 64} cent" + ("" if abs(value - 64) == 1 else "s")
            for value in range(14, 115)
        }
    ),
    "memory.protection": _sequential("Off", "Factory only", "All"),
    "keyboard.sensitivity": _spec(
        {value: f"{value + 10}%" for value in range(91)}
    ),
    "keyboard.aftertouch_offset": _firmware_spec(
        {value: str(value) for value in range(101)}
    ),
    "midi.channel_in_lower": _firmware_spec(
        {**{value: str(value + 1) for value in range(16)}, 126: "None"}
    ),
    "keyboard.relative_bend": _on_off(),
    "keyboard.scale": _sequential(
        "Off", "Major", "Minor", "HarmoMinor", "Dorian", "Mixolydian",
        "Blues", "Pentatonic"
    ),
    "keyboard.root_note": _sequential(*_NOTES),
    "microphone.gain": _spec(
        {**{value: f"{value - 12} dB" for value in range(72)}, 72: "Auto Gain"}
    ),
    "microphone.noise_gate": _spec(
        {0: "Off", **{value: f"-{28 + 2 * value} dB" for value in range(1, 32)}}
    ),
    "microphone.detect": _on_off(),
    "control.osc_knob_speed": _sequential("Slow", "Fast"),
    "control.octave_led_blink": _on_off(),
    "control.help_screen": _firmware_on_off(),
    "midi.usb_to_din": _firmware_on_off(),
}


def decode_microfreak_global(name: str, raw_value: int) -> dict[str, object]:
    spec = MICROFREAK_GLOBAL_VALUE_SPECS.get(name)
    if spec is None:
        return {
            "raw_value": raw_value,
            "label": None,
            "value_domain_status": "raw_only_unresolved",
            "allowed_values": None,
        }
    return {
        "raw_value": raw_value,
        "label": spec.label(raw_value),
        "value_domain_status": spec.evidence,
        "allowed_values": list(spec.allowed_values),
    }
