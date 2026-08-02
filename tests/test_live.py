import unittest

from minifreak_patch.live import (
    LiveControlError,
    MICROFREAK_SENTINEL_VALUES,
    default_port_name,
    send_control,
    send_control_batch,
    trigger_note,
)
from minifreak_patch.schema import DeviceModel


class FakeOutput:
    def __init__(self, backend, name):
        self.backend = backend
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def send(self, message):
        self.backend.sent.append((self.name, message))


class FakeMidi:
    def __init__(self):
        self.ports = ["Arturia MicroFreak", "MiniFreak MIDI"]
        self.sent = []

    def get_output_names(self):
        return self.ports

    def Message(self, kind, **values):
        return (kind, values)

    def open_output(self, name):
        return FakeOutput(self, name)


class LiveControlTests(unittest.TestCase):
    def test_device_specific_cutoff_cc(self):
        midi = FakeMidi()
        port, control = send_control(
            DeviceModel.MINIFREAK, "filter.cutoff", 42, backend=midi
        )
        self.assertEqual(port, "MiniFreak MIDI")
        self.assertEqual(control.cc, 74)
        self.assertEqual(
            midi.sent,
            [("MiniFreak MIDI", ("control_change", {
                "channel": 0, "control": 74, "value": 42
            }))],
        )

        send_control(DeviceModel.MICROFREAK, "filter.cutoff", 64, backend=midi)
        self.assertEqual(midi.sent[-1][1][1]["control"], 23)

    def test_range_and_channel_are_guarded(self):
        midi = FakeMidi()
        with self.assertRaises(LiveControlError):
            send_control(DeviceModel.MINIFREAK, "filter.cutoff", 128, backend=midi)
        with self.assertRaises(LiveControlError):
            send_control(
                DeviceModel.MINIFREAK, "filter.cutoff", 1, channel=0, backend=midi
            )

    def test_ambiguous_auto_discovery_requires_explicit_port(self):
        midi = FakeMidi()
        midi.ports.append("MiniFreak MIDI 2")
        with self.assertRaises(LiveControlError):
            default_port_name(DeviceModel.MINIFREAK, backend=midi)

    def test_microfreak_sentinel_is_complete_unique_and_batched(self):
        midi = FakeMidi()
        sleeps = []
        port, sent = send_control_batch(
            DeviceModel.MICROFREAK,
            MICROFREAK_SENTINEL_VALUES,
            backend=midi,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(port, "Arturia MicroFreak")
        self.assertEqual(len(sent), 20)
        self.assertEqual(len({value for _, _, value in sent}), 20)
        self.assertEqual(len(midi.sent), 20)
        self.assertEqual(len(sleeps), 19)
        by_name = {name: control.cc for name, control, _ in sent}
        self.assertEqual(by_name["cycling_env.amount"], 24)
        self.assertEqual(by_name["filter.env_amount"], 26)
        self.assertEqual(by_name["lfo.rate_sync"], 94)

    def test_batch_validates_everything_before_opening_port(self):
        midi = FakeMidi()
        with self.assertRaises(LiveControlError):
            send_control_batch(
                DeviceModel.MICROFREAK,
                {"filter.cutoff": 64, "not.real": 12},
                backend=midi,
            )
        self.assertEqual(midi.sent, [])

    def test_note_trigger_is_bounded_and_sends_note_off(self):
        midi = FakeMidi()
        sleeps = []
        port = trigger_note(
            DeviceModel.MICROFREAK,
            48,
            velocity=73,
            duration_seconds=0.25,
            channel=3,
            backend=midi,
            sleep_fn=sleeps.append,
        )
        self.assertEqual(port, "Arturia MicroFreak")
        self.assertEqual(sleeps, [0.25])
        self.assertEqual(
            midi.sent,
            [
                ("Arturia MicroFreak", ("note_on", {
                    "channel": 2, "note": 48, "velocity": 73
                })),
                ("Arturia MicroFreak", ("note_off", {
                    "channel": 2, "note": 48, "velocity": 0
                })),
            ],
        )

    def test_note_trigger_rejects_invalid_values_before_opening_port(self):
        midi = FakeMidi()
        with self.assertRaises(LiveControlError):
            trigger_note(DeviceModel.MICROFREAK, 128, backend=midi)
        with self.assertRaises(LiveControlError):
            trigger_note(DeviceModel.MICROFREAK, 60, velocity=0, backend=midi)
        self.assertEqual(midi.sent, [])


if __name__ == "__main__":
    unittest.main()
