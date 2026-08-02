"""Small, reversible live edits over the devices' documented MIDI CC layer.

This is deliberately separate from patch storage transport. MIDI CC changes
the active sound, but does not prove that a preset was saved to flash and does
not provide parameter readback.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from minifreak_patch.schema import DeviceModel


class LiveControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class MidiControl:
    cc: int
    minimum: int = 0
    maximum: int = 127
    note: str = ""


# Arturia's published MIDI implementation tables. Names are intentionally
# stable JSON-style paths rather than the labels chosen by a MIDI monitor.
MIDI_CONTROLS: dict[DeviceModel, dict[str, MidiControl]] = {
    DeviceModel.MINIFREAK: {
        "filter.cutoff": MidiControl(74),
        "filter.resonance": MidiControl(71),
        "filter.env_amount": MidiControl(24),
        "osc1.type": MidiControl(9),
        "osc1.wave": MidiControl(10),
        "osc1.timbre": MidiControl(12),
        "osc1.shape": MidiControl(13),
    },
    DeviceModel.MICROFREAK: {
        "glide": MidiControl(5),
        "osc.type": MidiControl(9, 10, 127),
        "osc.wave": MidiControl(10),
        "osc.timbre": MidiControl(12),
        "osc.shape": MidiControl(13),
        "filter.cutoff": MidiControl(23),
        "filter.resonance": MidiControl(83),
        "cycling_env.amount": MidiControl(24),
        "filter.env_amount": MidiControl(26),
        "cycling_env.rise": MidiControl(102),
        "cycling_env.fall": MidiControl(103),
        "cycling_env.hold": MidiControl(28),
        "arp.rate_free": MidiControl(91),
        "arp.rate_sync": MidiControl(92),
        "lfo.rate_free": MidiControl(93),
        "lfo.rate_sync": MidiControl(94),
        "envelope.attack": MidiControl(105),
        "envelope.decay": MidiControl(106),
        "envelope.sustain": MidiControl(29),
        "keyboard.hold": MidiControl(64),
        "spice": MidiControl(2),
    },
}


# Collision-resistant values for one saved-preset correlation experiment.
# Every documented MicroFreak CC receives a distinct value. The values avoid
# 0 and 127 so ignored updates remain easy to distinguish from boundaries.
MICROFREAK_SENTINEL_VALUES: dict[str, int] = {
    "spice": 7,
    "glide": 14,
    "osc.type": 21,
    "osc.wave": 28,
    "osc.timbre": 35,
    "osc.shape": 42,
    "filter.cutoff": 49,
    "cycling_env.amount": 56,
    "filter.env_amount": 63,
    "cycling_env.hold": 70,
    "envelope.sustain": 77,
    "filter.resonance": 84,
    "arp.rate_free": 91,
    "arp.rate_sync": 98,
    "lfo.rate_free": 105,
    "lfo.rate_sync": 112,
    "cycling_env.rise": 119,
    "cycling_env.fall": 126,
    "envelope.attack": 16,
    "envelope.decay": 23,
}


def controls_for(device: DeviceModel) -> Mapping[str, MidiControl]:
    return MIDI_CONTROLS[device]


def _mido_backend(backend: Any | None = None) -> Any:
    if backend is not None:
        return backend
    try:
        import mido
    except ImportError as exc:  # pragma: no cover - installation error
        raise LiveControlError(
            "live MIDI control requires the 'mido' and 'python-rtmidi' packages"
        ) from exc
    return mido


def list_output_ports(backend: Any | None = None) -> list[str]:
    return list(_mido_backend(backend).get_output_names())


def default_port_name(
    device: DeviceModel, ports: list[str] | None = None, backend: Any | None = None
) -> str:
    names = ports if ports is not None else list_output_ports(backend)
    needle = "minifreak" if device == DeviceModel.MINIFREAK else "microfreak"
    matches = [name for name in names if needle in name.lower()]
    if not matches:
        raise LiveControlError(f"no connected {device.value} MIDI output was found")
    if len(matches) > 1:
        raise LiveControlError(
            f"multiple {device.value} outputs found; choose one with --port: "
            + ", ".join(matches)
        )
    return matches[0]


def send_control(
    device: DeviceModel,
    parameter: str,
    value: int,
    *,
    channel: int = 1,
    port: str | None = None,
    backend: Any | None = None,
) -> tuple[str, MidiControl]:
    """Send one documented live CC. This does not save or read back a patch."""
    if not 1 <= channel <= 16:
        raise LiveControlError("MIDI channel must be 1..16")
    try:
        control = MIDI_CONTROLS[device][parameter]
    except KeyError as exc:
        choices = ", ".join(sorted(MIDI_CONTROLS[device]))
        raise LiveControlError(
            f"unknown {device.value} parameter {parameter!r}; supported: {choices}"
        ) from exc
    if not control.minimum <= value <= control.maximum:
        raise LiveControlError(
            f"{parameter} must be {control.minimum}..{control.maximum}"
        )

    midi = _mido_backend(backend)
    selected = port or default_port_name(device, backend=midi)
    if selected not in list_output_ports(midi):
        raise LiveControlError(f"MIDI output not found: {selected}")
    message = midi.Message(
        "control_change", channel=channel - 1, control=control.cc, value=value
    )
    with midi.open_output(selected) as output:
        output.send(message)
    return selected, control


def send_control_batch(
    device: DeviceModel,
    values: Mapping[str, int],
    *,
    channel: int = 1,
    port: str | None = None,
    backend: Any | None = None,
    delay_seconds: float = 0.02,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[str, list[tuple[str, MidiControl, int]]]:
    """Send validated live CC values in one MIDI output session.

    This deliberately sends no Program Change and no save/store command.
    """
    if not 1 <= channel <= 16:
        raise LiveControlError("MIDI channel must be 1..16")
    if delay_seconds < 0:
        raise LiveControlError("delay_seconds cannot be negative")
    if not values:
        raise LiveControlError("a live-control batch cannot be empty")

    resolved: list[tuple[str, MidiControl, int]] = []
    for parameter, value in values.items():
        try:
            control = MIDI_CONTROLS[device][parameter]
        except KeyError as exc:
            choices = ", ".join(sorted(MIDI_CONTROLS[device]))
            raise LiveControlError(
                f"unknown {device.value} parameter {parameter!r}; "
                f"supported: {choices}"
            ) from exc
        if isinstance(value, bool) or not isinstance(value, int):
            raise LiveControlError(f"{parameter} must be an integer")
        if not control.minimum <= value <= control.maximum:
            raise LiveControlError(
                f"{parameter} must be {control.minimum}..{control.maximum}"
            )
        resolved.append((parameter, control, value))

    midi = _mido_backend(backend)
    selected = port or default_port_name(device, backend=midi)
    if selected not in list_output_ports(midi):
        raise LiveControlError(f"MIDI output not found: {selected}")
    with midi.open_output(selected) as output:
        for index, (_, control, value) in enumerate(resolved):
            output.send(
                midi.Message(
                    "control_change",
                    channel=channel - 1,
                    control=control.cc,
                    value=value,
                )
            )
            if delay_seconds and index + 1 < len(resolved):
                sleep_fn(delay_seconds)
    return selected, resolved


def trigger_note(
    device: DeviceModel,
    note: int = 60,
    *,
    velocity: int = 80,
    duration_seconds: float = 0.5,
    channel: int = 1,
    port: str | None = None,
    backend: Any | None = None,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """Play one bounded MIDI note and always send note-off before returning."""
    if not 0 <= note <= 127:
        raise LiveControlError("MIDI note must be 0..127")
    if not 1 <= velocity <= 127:
        raise LiveControlError("MIDI velocity must be 1..127")
    if not 1 <= channel <= 16:
        raise LiveControlError("MIDI channel must be 1..16")
    if duration_seconds < 0:
        raise LiveControlError("note duration cannot be negative")

    midi = _mido_backend(backend)
    selected = port or default_port_name(device, backend=midi)
    if selected not in list_output_ports(midi):
        raise LiveControlError(f"MIDI output not found: {selected}")

    note_on = midi.Message(
        "note_on", channel=channel - 1, note=note, velocity=velocity
    )
    note_off = midi.Message(
        "note_off", channel=channel - 1, note=note, velocity=0
    )
    with midi.open_output(selected) as output:
        output.send(note_on)
        try:
            sleep_fn(duration_seconds)
        finally:
            output.send(note_off)
    return selected
