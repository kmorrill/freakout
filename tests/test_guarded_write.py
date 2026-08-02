import tempfile
import unittest
from pathlib import Path

from minifreak_patch.collage import RetrievedResource
from minifreak_patch.minifreak_payload import (
    VERIFIED_PARAMETERS,
    set_verified_parameter,
    with_updated_checksum,
)
from minifreak_patch.minifreak_usb import MiniFreakUsbTransport
from minifreak_patch.schema import DeviceModel
from minifreak_patch.microfreak import MicroFreakPreset
from minifreak_patch.transport import DeviceEndpoint, DeviceItem, ElektroidTransport
from minifreak_patch.wavetable import MicroFreakWavetable, MICROFREAK_PCM_BYTES


class ProbeTransport(ElektroidTransport):
    def __init__(self, table):
        super().__init__(runner=lambda args: None)
        self.table = table
        self.commands = []
        self.reads = 0

    def _run(self, *args):
        self.commands.append(args)

    def read_wavetable(self, endpoint, slot):
        self.reads += 1
        return self.table


class StatefulMicroFreakTransport(ElektroidTransport):
    def __init__(self, preset, tables=None, corrupt_readback=False):
        super().__init__(runner=lambda args: None)
        self.preset = preset
        self.tables = dict(tables or {})
        self.corrupt_readback = corrupt_readback
        self.uploads = []

    def read_preset(self, endpoint, slot):
        return self.preset

    def read_wavetable(self, endpoint, slot):
        return self.tables[slot]

    def list_wavetables(self, endpoint):
        return [
            DeviceItem(slot=slot, name=self.tables[slot].name, size=MICROFREAK_PCM_BYTES)
            if slot in self.tables
            else DeviceItem(slot=slot, name="", size=0)
            for slot in range(1, 17)
        ]

    def _upload_bytes(self, endpoint, slot, data, *, filesystem, suffix):
        self.uploads.append((filesystem, slot, data))
        if filesystem == "ppreset":
            self.preset = MicroFreakPreset.from_bytes(data)
            if self.corrupt_readback and len(self.uploads) == 1:
                self.preset = MicroFreakPreset(
                    name="Mismatch",
                    category_id=self.preset.category_id,
                    init=self.preset.init,
                    p1=self.preset.p1,
                    payload=self.preset.payload,
                )
        else:
            self.tables[slot] = MicroFreakWavetable.from_mfw(data)
            if self.corrupt_readback and len(self.uploads) == 1:
                self.tables[slot] = MicroFreakWavetable(
                    "Mismatch", self.tables[slot].pcm16le
                )

    def _run(self, *args):
        if args[0] == "microfreak:wavetable:rm":
            self.tables.pop(int(args[1].rsplit("/", 1)[1]), None)
            return None
        raise AssertionError(args)


class ProbeMiniFreakSessionTransport(MiniFreakUsbTransport):
    def __init__(self, payload):
        self.current = payload
        self.session_writes = []

    def read_current_preset(self, *, timeout=10.0):
        return RetrievedResource(
            message_id=1,
            name=b"\xff\xff",
            location="RESOURCE_LOCATION_PRESET",
            data=self.current,
            total_size=len(self.current),
            complete=True,
        )

    def _send_session_parameter(self, parameter_id, raw_value, *, timeout):
        self.session_writes.append((parameter_id, raw_value))
        spec = next(
            value
            for value in VERIFIED_PARAMETERS.values()
            if value.session_parameter_id == parameter_id
        )
        updated = bytearray(self.current)
        updated[spec.offset : spec.offset + 2] = raw_value.to_bytes(
            2, "little", signed=True
        )
        self.current = with_updated_checksum(bytes(updated))

    def _store_current_preset(self, content, *, timeout):
        self.current = content
        return True


class ProbeMiniFreakSavedTransport(ProbeMiniFreakSessionTransport):
    def __init__(self, payload, slot=256):
        super().__init__(payload)
        self.slot = slot
        self.saved = payload

    def read_saved_preset(self, slot, *, timeout=10.0):
        self.assert_slot(slot)
        return RetrievedResource(
            message_id=1,
            name=(slot - 1).to_bytes(2, "little"),
            location="RESOURCE_LOCATION_PRESET",
            data=self.saved,
            total_size=len(self.saved),
            complete=True,
        )

    def _store_saved_preset(self, slot, content, *, timeout):
        self.assert_slot(slot)
        self.saved = content
        return True

    def assert_slot(self, slot):
        if slot != self.slot:
            raise AssertionError(f"unexpected slot {slot}")


class GuardedWriteTests(unittest.TestCase):
    def test_microfreak_preset_write_backs_up_and_reads_target_exactly(self):
        before = MicroFreakPreset("Init", 0, 0, 0, bytes(4672))
        target = MicroFreakPreset("CodexProbe", 0, 0, 0, bytes(4672))
        transport = StatefulMicroFreakTransport(before)
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "slot-512.mfp"
            report = transport.write_preset(endpoint, 512, target, backup)
            self.assertEqual(MicroFreakPreset.from_file(backup), before)
        self.assertTrue(report.exact_readback)
        self.assertEqual(transport.preset, target)

    def test_microfreak_preset_mismatch_restores_backup(self):
        before = MicroFreakPreset("Init", 0, 0, 0, bytes(4672))
        target = MicroFreakPreset("CodexProbe", 0, 0, 0, bytes(4672))
        transport = StatefulMicroFreakTransport(before, corrupt_readback=True)
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception, "restoration verified"):
                transport.write_preset(
                    endpoint, 512, target, Path(temp) / "slot-512.mfp"
                )
        self.assertEqual(transport.preset, before)

    def test_microfreak_preset_write_refuses_empty_init_slot(self):
        before = MicroFreakPreset("Init", 0, 1, 51, b"")
        target = MicroFreakPreset("CodexProbe", 0, 0, 0, bytes(4672))
        transport = StatefulMicroFreakTransport(before)
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception, "empty Init slot"):
                transport.write_preset(
                    endpoint, 512, target, Path(temp) / "slot-512.mfp"
                )
        self.assertEqual(transport.uploads, [])

    def test_microfreak_wavetable_upload_to_empty_slot_reads_exactly(self):
        table = MicroFreakWavetable("CodexProbe", b"\x01\x00" * 8192)
        transport = StatefulMicroFreakTransport(
            MicroFreakPreset("Init", 0, 0, 0, bytes(4672))
        )
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "slot-2.mfw"
            report = transport.write_wavetable(endpoint, 2, table, backup)
            self.assertEqual(backup.read_bytes(), b"")
        self.assertTrue(report.before_empty)
        self.assertEqual(transport.tables[2], table)

    def test_microfreak_empty_wavetable_mismatch_is_cleared(self):
        table = MicroFreakWavetable("CodexProbe", b"\x01\x00" * 8192)
        transport = StatefulMicroFreakTransport(
            MicroFreakPreset("Init", 0, 0, 0, bytes(4672)),
            corrupt_readback=True,
        )
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception, "restoration verified"):
                transport.write_wavetable(
                    endpoint, 2, table, Path(temp) / "slot-2.mfw"
                )
        self.assertNotIn(2, transport.tables)

    def test_same_content_probe_backs_up_verifies_and_restores(self):
        table = MicroFreakWavetable("Fixture", b"\x00" * MICROFREAK_PCM_BYTES)
        transport = ProbeTransport(table)
        endpoint = DeviceEndpoint(
            1, "Arturia MicroFreak", "Arturia MicroFreak", DeviceModel.MICROFREAK
        )
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "slot-1.mfw"
            report = transport.verify_wavetable_write_transport(
                endpoint, 1, backup
            )
            self.assertTrue(backup.exists())
        self.assertTrue(report.write_verified)
        self.assertTrue(report.restore_verified)
        self.assertEqual(transport.reads, 3)
        self.assertEqual(len(transport.commands), 2)

    def test_minifreak_active_probe_reads_target_and_restores_exactly(self):
        initial = with_updated_checksum(bytes(3328))
        transport = ProbeMiniFreakSessionTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "active.bin"
            report = transport.verify_active_parameter_transport(
                "filter.cutoff", 0.5, backup
            )
            self.assertEqual(backup.read_bytes(), initial)
        self.assertTrue(report.exact_readback)
        self.assertTrue(report.restored)
        self.assertEqual(transport.current, initial)
        self.assertEqual(
            transport.session_writes,
            [(0x19, round(0.5 * 32767)), (0x19, 0)],
        )

    def test_minifreak_corpus_only_field_uses_resource_store(self):
        initial = with_updated_checksum(bytes(3328))
        target = set_verified_parameter(initial, "fx1.param1", 0.25)
        transport = ProbeMiniFreakSessionTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_active_payload(
                target, Path(temp) / "active.bin"
            )
        self.assertEqual(report.transport, "resource-store")
        self.assertTrue(report.exact_readback)
        self.assertEqual(transport.current, target)
        self.assertEqual(transport.session_writes, [])

    def test_minifreak_saved_write_requires_occupied_slot_and_reads_back(self):
        initial = bytearray(3328)
        initial[:2] = (255).to_bytes(2, "little")
        initial[3] = 0x41
        initial = with_updated_checksum(bytes(initial))
        target = set_verified_parameter(initial, "fx1.param1", 0.25)
        transport = ProbeMiniFreakSavedTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_saved_payload(
                256, target, Path(temp) / "slot-256.bin"
            )
        self.assertTrue(report.exact_readback)
        self.assertEqual(transport.saved, target)

    def test_minifreak_saved_write_refuses_empty_slot(self):
        empty = with_updated_checksum(bytes(3328))
        target = set_verified_parameter(empty, "fx1.param1", 0.25)
        transport = ProbeMiniFreakSavedTransport(empty)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception, "is empty"):
                transport.write_saved_payload(
                    256, target, Path(temp) / "slot-256.bin"
                )

    def test_minifreak_active_write_leaves_verified_target_live(self):
        initial = with_updated_checksum(bytes(3328))
        transport = ProbeMiniFreakSessionTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_active_parameter(
                "filter.env_amount", -0.25, Path(temp) / "active.bin"
            )
        self.assertTrue(report.exact_readback)
        raw = int.from_bytes(transport.current[182:184], "little", signed=True)
        self.assertEqual(raw, round(-0.25 * 32767))

    def test_minifreak_json_payload_applies_multiple_verified_fields(self):
        initial = with_updated_checksum(bytes(3328))
        target = set_verified_parameter(initial, "filter.cutoff", 0.5)
        target = set_verified_parameter(target, "filter.resonance", 0.25)
        transport = ProbeMiniFreakSessionTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "active.bin"
            report = transport.write_active_payload(target, backup)
            self.assertEqual(backup.read_bytes(), initial)
        self.assertTrue(report.exact_readback)
        self.assertEqual(transport.current, target)
        self.assertEqual(set(report.parameters), {"filter.cutoff", "filter.resonance"})
        self.assertEqual(
            transport.session_writes,
            [(0x19, round(0.5 * 32767)), (0x1A, round(0.25 * 32767))],
        )

    def test_minifreak_json_payload_rejects_unknown_byte_changes_before_write(self):
        initial = with_updated_checksum(bytes(3328))
        changed = bytearray(initial)
        changed[400] = 1
        target = with_updated_checksum(bytes(changed))
        transport = ProbeMiniFreakSessionTransport(initial)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaisesRegex(Exception, "unsupported byte changes"):
                transport.write_active_payload(target, Path(temp) / "active.bin")
        self.assertEqual(transport.session_writes, [])
        self.assertEqual(transport.current, initial)

    def test_minifreak_bulk_session_map_uses_unique_sentinels_and_restores(self):
        initial = with_updated_checksum(bytes(3328))
        transport = ProbeMiniFreakSessionTransport(initial)
        keys = ("oscillator1.coarse_tune", "filter.cutoff", "lfo2.rate")
        with tempfile.TemporaryDirectory() as temp:
            report = transport.verify_session_parameter_map(
                keys, Path(temp) / "active.bin"
            )
        self.assertTrue(report.exact_restore)
        self.assertEqual(transport.current, initial)
        self.assertTrue(
            all(item["formula_verified"] for item in report.mappings.values())
        )
        self.assertEqual(
            {item["observed_offset"] for item in report.mappings.values()},
            {130, 178, 238},
        )


if __name__ == "__main__":
    unittest.main()
