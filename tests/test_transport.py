import subprocess
import unittest

from minifreak_patch.schema import DeviceModel
from minifreak_patch.transport import DirectTransportDiscovery, ElektroidTransport


LISTING = """\
0: id: SYSTEM_ID; name: computer
1: id: Arturia MicroFreak :: Arturia MicroFreak; name: Arturia MicroFreak :: Arturia MicroFreak
2: id: Arturia MicroFreak :: MiniFreak MIDI; name: Arturia MicroFreak :: MiniFreak MIDI
3: id: MiniFreak MIDI :: MiniFreak MIDI; name: MiniFreak MIDI :: MiniFreak MIDI
"""


def fake_runner(args):
    command = list(args)
    if command[-1] == "ld":
        output = LISTING
    elif command[-2:] == ["info", "1"]:
        output = """Device name: Arturia MicroFreak
Device version: 5.0.0.36
Connector name: microfreak
Filesystems: preset, sample, wavetable
"""
    elif command[-2:] == ["info", "3"]:
        output = """Device name: MIDI device
Device version: 4.0.1.53
Connector name: default
Filesystems: program
"""
    else:
        raise AssertionError(command)
    return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")


class TransportTests(unittest.TestCase):
    def test_direct_discovery_finds_both_actual_patch_buses(self):
        class FakeMidi:
            @staticmethod
            def get_input_names():
                return ["Arturia MicroFreak", "MiniFreak MIDI", "Input only"]

            @staticmethod
            def get_output_names():
                return ["Arturia MicroFreak", "MiniFreak MIDI", "Output only"]

        class FakeUsbDevice:
            product = "MiniFreak"
            serial_number = "MF-TEST"
            bcdDevice = 0x0401

        class FakeUsbCore:
            @staticmethod
            def find(**kwargs):
                assert kwargs == {
                    "find_all": True,
                    "idVendor": 0x1C75,
                    "idProduct": 0x0602,
                }
                return (FakeUsbDevice(),)

        endpoints = DirectTransportDiscovery(
            midi_backend=FakeMidi(), usb_core=FakeUsbCore()
        ).discover()

        self.assertEqual(
            [item.device for item in endpoints],
            [DeviceModel.MICROFREAK, DeviceModel.MINIFREAK],
        )
        microfreak, minifreak = endpoints
        self.assertEqual(microfreak.connector, "arturia-microfreak-sysex")
        self.assertEqual(microfreak.input_name, "Arturia MicroFreak")
        self.assertEqual(minifreak.connector, "arturia-minifreak-collage-usb")
        self.assertEqual(minifreak.input_name, "MiniFreak MIDI")
        self.assertEqual(minifreak.usb_release_bcd, 0x0401)
        self.assertEqual(minifreak.serial_number, "MF-TEST")

    def test_direct_discovery_does_not_report_minifreak_midi_without_usb(self):
        class FakeMidi:
            @staticmethod
            def get_input_names():
                return ["MiniFreak MIDI"]

            @staticmethod
            def get_output_names():
                return ["MiniFreak MIDI"]

        class FakeUsbCore:
            @staticmethod
            def find(**kwargs):
                return ()

        endpoints = DirectTransportDiscovery(
            midi_backend=FakeMidi(), usb_core=FakeUsbCore()
        ).discover()
        self.assertEqual(endpoints, [])

    def test_discovery_pairs_matching_freak_endpoints(self):
        endpoints = ElektroidTransport(runner=fake_runner).discover()
        self.assertEqual([item.transport_id for item in endpoints], [1, 3])
        self.assertEqual(endpoints[0].device, DeviceModel.MICROFREAK)
        self.assertEqual(endpoints[1].device, DeviceModel.MINIFREAK)

    def test_resolve_only_probes_requested_endpoint(self):
        endpoint = ElektroidTransport(runner=fake_runner).resolve(1)
        self.assertEqual(endpoint.device, DeviceModel.MICROFREAK)

    def test_resolve_reports_microfreak_write_filesystems(self):
        endpoint = ElektroidTransport(runner=fake_runner).resolve(1)
        self.assertIn("preset", endpoint.filesystems)
        self.assertIn("wavetable", endpoint.filesystems)


if __name__ == "__main__":
    unittest.main()
