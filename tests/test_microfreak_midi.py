import unittest

from minifreak_patch.microfreak_midi import (
    ARTURIA_MICROFREAK_PREFIX,
    MICROFREAK_LIVE_WORD_SEMANTICS,
    MICROFREAK_GLOBAL_CODES,
    MICROFREAK_OSCILLATOR_ENGINE_NAMES,
    MicroFreakMidiTransport,
    decode_control_word_payload,
    encode_control_index_payload,
    encode_control_word_request_payload,
    encode_control_word_payload,
    encode_live_parameter_state_record_request,
    decode_sysex,
    encode_sysex,
    infer_oscillator_engine_index,
    microfreak_sample_checksum,
    pack_8bit_midi,
    pack_six_byte_state_record,
    unpack_8bit_midi,
)
from minifreak_patch.microfreak_live_map import (
    MICROFREAK_STRUCTURED_CORPUS_NONVARYING,
    MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED,
    MICROFREAK_STRUCTURED_GLOBAL_COUNTERPARTS,
    MICROFREAK_STRUCTURED_LIVE_AMBIGUOUS,
    MICROFREAK_STRUCTURED_NO_LIVE_TABLE_CC_EFFECT,
    MICROFREAK_STRUCTURED_LIVE_WORDS,
    MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE,
)


class FakeMessage:
    def __init__(self, message_type, data=(), **kwargs):
        self.type = message_type
        self.data = tuple(data)
        for name, value in kwargs.items():
            setattr(self, name, value)


class OscillatorEngineIndexTests(unittest.TestCase):
    def test_infers_observed_normalized_engine_grid(self):
        self.assertEqual(infer_oscillator_engine_index(0), 0)
        self.assertEqual(infer_oscillator_engine_index(1489), 1)
        self.assertEqual(infer_oscillator_engine_index(13405), 9)
        self.assertEqual(infer_oscillator_engine_index(25320), 17)
        self.assertEqual(infer_oscillator_engine_index(32767), 22)
        self.assertEqual(MICROFREAK_OSCILLATOR_ENGINE_NAMES[14], "Vocoder")
        self.assertEqual(MICROFREAK_OSCILLATOR_ENGINE_NAMES[18], "WaveUser")
        self.assertEqual(MICROFREAK_OSCILLATOR_ENGINE_NAMES[22], "Hit Grains")

    def test_rejects_off_grid_and_out_of_range_values(self):
        self.assertIsNone(infer_oscillator_engine_index(1000))
        self.assertIsNone(infer_oscillator_engine_index(-1))
        self.assertIsNone(infer_oscillator_engine_index(32768))


class FakeInput:
    def __init__(self, queue):
        self.queue = queue

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def poll(self):
        return self.queue.pop(0) if self.queue else None


class FakeOutput(FakeInput):
    def __init__(self, backend):
        super().__init__(backend.queue)
        self.backend = backend
        self.part = 0

    def send(self, message):
        if message.type in {"control_change", "program_change"}:
            self.backend.channel_messages.append(message)
            if message.type == "control_change":
                for address, value in self.backend.cc_live_mutations.get(
                    (message.control, message.value), {}
                ).items():
                    self.backend.live_words[address] = value
            if (
                message.type == "program_change"
                and self.backend.preset_live_words is not None
            ):
                self.backend.live_words = list(self.backend.preset_live_words)
            return
        request = decode_sysex(message.data)
        self.backend.sent.append(request)
        if request.operation in (0x1C, 0x1D):
            return
        if request.operation == 0x42:
            code, value = request.payload
            self.backend.global_values[code] = value
            return
        if request.operation == 0x57:
            self.backend.wave_header_pending = True
            operation, payload = 0x15, b""
        elif request.operation == 0x5B and request.payload[2] == 1:
            self.backend.sample_finalize_slot = request.payload[0]
            self.backend.sample_finalize_packet = 0
            operation, payload = 0x15, b""
        elif request.operation == 0x5B:
            self.backend.sample_header_slot = request.payload[0]
            self.backend.sample_stream_offset = 0
            operation, payload = 0x15, b""
        elif request.operation == 0x59:
            self.backend.sample_read_slot = request.payload[0]
            self.backend.sample_part = request.payload[1]
            self.backend.sample_packet = 0
            operation, payload = 0x15, b""
        elif request.operation == 0x5D:
            self.backend.sample_allocation_slot = request.payload[0]
            operation, payload = 0x18, b""
        elif request.operation == 0x5A:
            self.backend.sample_reset_slot = request.payload[0]
            operation, payload = 0x18, b""
        elif request.operation == 0x58:
            self.backend.sample_upload_slot = request.payload[0]
            operation, payload = 0x18, b""
        elif request.operation == 0x47 and request.payload == b"\x0a":
            payload = bytes.fromhex("00000c000000011200")
            response = bytes.fromhex("f000206b077f450948") + payload + b"\xf7"
            self.queue.append(FakeMessage("sysex", response[1:-1]))
            return
        elif request.operation == 0x43:
            code = request.payload[0]
            value = self.backend.global_values.get(code, (code ^ 0x55) & 0x7F)
            response = bytes.fromhex("f000206b077f440242") + bytes(
                (code, value, 0xF7)
            )
            self.queue.append(FakeMessage("sysex", response[1:-1]))
            return
        elif request.operation == 0x41:
            flags, high, low = request.payload
            index = ((high | (0x80 if flags & 0x40 else 0)) << 8) | (
                low | (0x80 if flags & 0x20 else 0)
            )
            value = self.backend.live_words[index]
            parts = [
                (index >> 8) & 0xFF,
                index & 0xFF,
                (value >> 8) & 0xFF,
                value & 0xFF,
            ]
            flags = 0
            for bit, part in zip((0x40, 0x20, 0x10, 0x08), parts):
                if part & 0x80:
                    flags |= bit
            payload = bytes((flags, *(part & 0x7F for part in parts)))
            response = bytes.fromhex("f000206b077f550540") + payload + b"\xf7"
            self.queue.append(FakeMessage("sysex", response[1:-1]))
            return
        elif request.operation == 0x40:
            index, value = decode_control_word_payload(request.payload)
            self.backend.live_words[index] = value
            return
        elif request.operation == 0x49:
            self.assert_state_record_request(request.payload)
            packed = request.payload[2:]
            flags = packed[0]
            record = bytes(
                value | (0x80 if flags & bit else 0)
                for bit, value in zip(
                    (0x40, 0x20, 0x10, 0x08, 0x04, 0x02), packed[1:]
                )
            )
            index = int.from_bytes(record[2:4], "big")
            value = int.from_bytes(record[4:6], "big") >> 1
            self.backend.live_words[index] = value
            return
        elif request.operation == 0x55:
            self.backend.wave_part = request.payload[1]
            self.backend.wave_packet = 0
            operation, payload = 0x15, b""
        elif request.operation == 0x56:
            self.backend.wave_reset_pending = True
            operation, payload = 0x18, b""
        elif request.operation == 0x54:
            self.backend.wave_upload_part = request.payload[1]
            self.backend.wave_upload_bytes = bytearray()
            operation, payload = 0x18, b""
        elif request.operation == 0x19 and request.payload[-1] == 0:
            header = bytearray(0x23)
            if request.payload[:2] == b"\x04\x00":
                header[0:2] = request.payload[:2]
                header[3] = 0x08
                header[10] = 0
                header[11] = 0x33
                name = b"Init"
            else:
                header[10] = self.backend.category_id
                header[11] = self.backend.p1
                name = self.backend.name.encode()
            header[12 : 12 + len(name)] = name
            operation, payload = 0x52, bytes(header)
        elif request.operation == 0x19:
            operation, payload = 0x15, b""
        elif request.operation == 0x18 and self.backend.sample_header_slot is not None:
            slot = self.backend.sample_header_slot
            header = bytearray(28)
            state = self.backend.sample_uploaded.get(slot)
            if state is None:
                size = self.backend.sample_size_override or ((slot + 1) * 64000)
                checksum = 0x1200 + slot
                name = f"Sample {slot + 1}".encode()
            else:
                size = state["size"]
                checksum = state["checksum"]
                name = state["name"].encode()
            if size:
                header[0:4] = (0x00281000 + slot * 4096).to_bytes(4, "little")
            header[4:8] = size.to_bytes(4, "little")
            header[8:10] = checksum.to_bytes(2, "little")
            header[10 : 10 + len(name)] = name
            header[23] = slot
            self.backend.sample_header_slot = None
            operation, payload = 0x16, pack_8bit_midi(bytes(header))
        elif request.operation == 0x18 and self.backend.wave_header_pending:
            header = bytearray(28)
            header[0] = 0
            header[8] = 0
            header[10] = header[11] = 1
            header[3] = 0x08 if self.backend.wave_empty else 0
            name = self.backend.wave_name.encode()
            header[12 : 12 + len(name)] = name
            self.backend.wave_header_pending = False
            operation, payload = 0x16, pack_8bit_midi(bytes(header))
        elif request.operation == 0x18 and self.backend.wave_part is not None:
            packet = self.backend.wave_packet
            start = self.backend.wave_part * 4096 + packet * 28
            if packet == 146:
                raw = self.backend.wave_pcm[start : start + 8] + bytes(20)
                operation = 0x17
                self.backend.wave_part = None
            else:
                raw = self.backend.wave_pcm[start : start + 28]
                operation = 0x16
            self.backend.wave_packet += 1
            payload = pack_8bit_midi(raw)
        elif request.operation == 0x18 and self.backend.sample_part is not None:
            packet = self.backend.sample_packet
            start = self.backend.sample_part * 4096 + packet * 28
            state = self.backend.sample_uploaded.get(self.backend.sample_read_slot)
            source = self.backend.sample_pcm if state is None else bytes(state["audio"])
            if packet == 146:
                tail = source[start : start + 8]
                raw = tail + bytes(8 - len(tail)) + bytes(20)
                operation = 0x17
                self.backend.sample_part = None
            else:
                raw = source[start : start + 28]
                raw = raw + bytes(28 - len(raw))
                operation = 0x16
            self.backend.sample_packet += 1
            payload = pack_8bit_midi(raw)
        elif request.operation == 0x18 and self.backend.sample_finalize_slot is not None:
            packet = self.backend.sample_finalize_packet
            state = self.backend.sample_uploaded[self.backend.sample_finalize_slot]
            source = bytes(state["audio"]).ljust(4096, b"\0")
            if packet == 146:
                raw = source[packet * 28 : packet * 28 + 8] + bytes(20)
                operation = 0x17
                self.backend.sample_finalize_slot = None
            else:
                raw = source[packet * 28 : (packet + 1) * 28]
                operation = 0x16
            self.backend.sample_finalize_packet += 1
            payload = pack_8bit_midi(raw)
        elif request.operation == 0x18:
            operation = 0x17 if self.part == 145 else 0x16
            payload = self.backend.payload[self.part * 32 : (self.part + 1) * 32]
            self.part += 1
        elif request.operation == 0x52 and len(request.payload) == 0x23:
            self.backend.upload_header = request.payload
            self.backend.upload_parts = []
            operation, payload = 0x18, b""
        elif request.operation == 0x15:
            operation, payload = 0x18, b""
        elif request.operation == 0x17 and self.backend.sample_allocation_slot is not None:
            header = unpack_8bit_midi(request.payload)
            self.backend.sample_pending_header = header
            self.backend.sample_allocation_slot = None
            first = encode_sysex(request.sequence, 0x16, b"\x01")
            second = encode_sysex(request.sequence, 0x18, b"")
            self.queue.append(FakeMessage("sysex", first[1:-1]))
            self.queue.append(FakeMessage("sysex", second[1:-1]))
            return
        elif request.operation == 0x17 and self.backend.sample_reset_slot is not None:
            header = unpack_8bit_midi(request.payload)
            slot = self.backend.sample_reset_slot
            size = int.from_bytes(header[4:8], "little")
            name = header[10:23].split(b"\0", 1)[0].decode()
            self.backend.sample_uploaded[slot] = {
                "name": name,
                "size": size,
                "checksum": int.from_bytes(header[8:10], "little"),
                "audio": bytearray(),
            }
            self.backend.sample_reset_slot = None
            operation, payload = 0x18, b""
        elif (
            request.operation in (0x16, 0x17)
            and self.backend.sample_upload_slot is not None
        ):
            slot = self.backend.sample_upload_slot
            state = self.backend.sample_uploaded[slot]
            raw = unpack_8bit_midi(request.payload)
            state["audio"].extend(raw[:8] if request.operation == 0x17 else raw)
            if request.operation == 0x17:
                state["audio"] = state["audio"][: state["size"]]
                self.backend.sample_upload_slot = None
            operation, payload = 0x18, b""
        elif request.operation == 0x16 and self.backend.wave_reset_pending:
            header = unpack_8bit_midi(request.payload)
            self.backend.wave_name = header[12:28].split(b"\0", 1)[0].decode()
            self.backend.wave_empty = bool(header[3] & 0x08)
            self.backend.wave_reset_pending = False
            self.backend.wave_reset_tail = True
            operation, payload = 0x18, b""
        elif request.operation == 0x17 and self.backend.wave_reset_tail:
            self.backend.wave_reset_tail = False
            operation, payload = 0x18, b""
        elif (
            request.operation in (0x16, 0x17)
            and self.backend.wave_upload_part is not None
        ):
            raw = unpack_8bit_midi(request.payload)
            self.backend.wave_upload_bytes.extend(
                raw[:8] if request.operation == 0x17 else raw
            )
            if request.operation == 0x17:
                start = self.backend.wave_upload_part * 4096
                updated = bytearray(self.backend.wave_pcm)
                updated[start : start + 4096] = self.backend.wave_upload_bytes
                self.backend.wave_pcm = bytes(updated)
                self.backend.wave_upload_part = None
            operation, payload = 0x18, b""
        elif request.operation == 0x52:
            operation, payload = 0x18, b""
        elif request.operation in (0x16, 0x17):
            self.backend.upload_parts.append(request.payload)
            if request.operation == 0x17:
                self.backend.payload = b"".join(self.backend.upload_parts)
                self.backend.category_id = self.backend.upload_header[10]
                self.backend.p1 = self.backend.upload_header[11]
                self.backend.name = self.backend.upload_header[12:26].split(b"\0", 1)[0].decode()
            operation, payload = 0x18, b""
        else:
            raise AssertionError(request)
        response = encode_sysex(request.sequence, operation, payload)
        self.queue.append(FakeMessage("sysex", response[1:-1]))

    @staticmethod
    def assert_state_record_request(payload):
        if len(payload) != 9 or payload[:2] != bytes((0x06, 0x7D)):
            raise AssertionError(f"unexpected operation-49 payload: {payload.hex()}")


class FakeMido:
    def __init__(self, payload):
        self.queue = []
        self.payload = payload
        self.name = "DirectProbe"
        self.category_id = 2
        self.p1 = 16
        self.sent = []
        self.upload_parts = []
        self.upload_header = b""
        self.wave_name = "WaveProbe"
        self.wave_pcm = bytes((index % 256 for index in range(16384)))
        self.wave_empty = False
        self.wave_header_pending = False
        self.wave_part = None
        self.wave_packet = 0
        self.wave_reset_pending = False
        self.wave_reset_tail = False
        self.wave_upload_part = None
        self.wave_upload_bytes = bytearray()
        self.sample_header_slot = None
        self.sample_read_slot = 0
        self.sample_part = None
        self.sample_packet = 0
        self.sample_pcm = bytes((index * 17 % 256 for index in range(64000)))
        self.sample_size_override = None
        self.sample_stream_offset = 0
        self.sample_allocation_slot = None
        self.sample_reset_slot = None
        self.sample_upload_slot = None
        self.sample_pending_header = None
        self.sample_finalize_slot = None
        self.sample_finalize_packet = 0
        self.sample_uploaded = {}
        self.channel_messages = []
        self.cc_live_mutations = {}
        self.global_values = {}
        self.live_words = [0x5174, 0, 0, 0x7FFF] + [0] * (0x1710 - 4)
        self.preset_live_words = None

    Message = FakeMessage

    def get_input_names(self):
        return ["Arturia MicroFreak"]

    def get_output_names(self):
        return ["Arturia MicroFreak"]

    def open_input(self, name):
        return FakeInput(self.queue)

    def open_output(self, name):
        return FakeOutput(self)


class FakePlaybackOutput:
    def __init__(self, backend):
        self.backend = backend

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def send(self, message):
        self.backend.host_messages.append(message)
        if message.type in {"start", "stop", "clock"}:
            self.backend.queue.append(FakeMessage(message.type))
        if message.type == "clock":
            self.backend.clock_count += 1
            if self.backend.clock_count == 1:
                self.backend.queue.extend(
                    [
                        FakeMessage(
                            "note_on", channel=0, note=48, velocity=91
                        ),
                        FakeMessage(
                            "control_change", channel=0, control=23, value=64
                        ),
                    ]
                )
            elif self.backend.clock_count == 3:
                self.backend.queue.append(
                    FakeMessage("note_off", channel=0, note=48, velocity=64)
                )


class FakePlaybackMido:
    Message = FakeMessage

    def __init__(self):
        self.queue = []
        self.host_messages = []
        self.clock_count = 0

    def get_input_names(self):
        return ["Arturia MicroFreak"]

    def get_output_names(self):
        return ["Arturia MicroFreak"]

    def open_input(self, name):
        return FakeInput(self.queue)

    def open_output(self, name):
        return FakePlaybackOutput(self)


class FakeLiveTraceOutput(FakeOutput):
    def send(self, message):
        if message.type in {"start", "stop", "note_on", "note_off"}:
            self.backend.channel_messages.append(message)
            return
        if message.type == "clock":
            self.backend.clock_count += 1
            value = 100 + self.backend.clock_count
            self.backend.live_words[0x0101] = value
            self.backend.queue.append(
                FakeMessage(
                    "control_change", channel=0, control=23, value=value & 0x7F
                )
            )
            return
        super().send(message)


class FakeLiveTraceMido(FakeMido):
    def __init__(self):
        super().__init__(bytes(4672))
        self.clock_count = 0
        self.live_words[0x0101] = 100

    def open_output(self, name):
        return FakeLiveTraceOutput(self)


class MicroFreakMidiTests(unittest.TestCase):
    def test_behavioral_sequence_capture_preserves_clock_relative_midi(self):
        backend = FakePlaybackMido()
        events = MicroFreakMidiTransport(
            midi_backend=backend, sleep_fn=lambda _: None
        ).capture_sequence_playback_events(
            clock_count=3,
            clock_interval_seconds=0,
            settle_seconds=0,
        )
        note_on = next(event for event in events if event.message_type == "note_on")
        note_off = next(event for event in events if event.message_type == "note_off")
        automation = next(
            event for event in events if event.message_type == "control_change"
        )
        self.assertEqual((note_on.clock_sent, note_on.note, note_on.velocity), (1, 48, 91))
        self.assertEqual((note_off.clock_sent, note_off.note), (3, 48))
        self.assertEqual((automation.control, automation.value), (23, 64))
        self.assertFalse(note_on.host_echo_candidate)
        self.assertTrue(next(event for event in events if event.message_type == "clock").host_echo_candidate)
        self.assertEqual(
            [message.type for message in backend.host_messages],
            [
                "start",
                "note_on",
                "clock",
                "clock",
                "clock",
                "note_off",
                "stop",
            ],
        )

    def test_sequence_live_trace_samples_complete_table_at_clock_boundaries(self):
        backend = FakeLiveTraceMido()
        trace = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).capture_sequence_live_trace(
            clock_count=2,
            snapshot_every_clocks=1,
            clock_interval_seconds=0,
            settle_seconds=0,
        )
        self.assertEqual(
            [snapshot.clock_sent for snapshot in trace.snapshots], [0, 1, 2]
        )
        self.assertEqual(
            [
                next(
                    word.raw_u16
                    for word in snapshot.words
                    if word.index == 0x0101
                )
                for snapshot in trace.snapshots
            ],
            [100, 101, 102],
        )
        self.assertTrue(all(len(snapshot.words) == 384 for snapshot in trace.snapshots))
        automation = [
            event for event in trace.events if event.message_type == "control_change"
        ]
        self.assertEqual(
            [(event.clock_sent, event.control, event.value) for event in automation],
            [(1, 23, 101), (2, 23, 102)],
        )
        self.assertEqual(
            [item.operation for item in backend.sent].count(0x41), 3 * 384
        )
        self.assertEqual(backend.sent[0].operation, 0x1C)
        self.assertEqual(backend.sent[-1].operation, 0x1D)

        targeted_backend = FakeLiveTraceMido()
        targeted = MicroFreakMidiTransport(
            midi_backend=targeted_backend, timeout=0.01, sleep_fn=lambda _: None
        ).capture_sequence_live_trace(
            clock_count=2,
            snapshot_every_clocks=1,
            clock_interval_seconds=0,
            settle_seconds=0,
            snapshot_addresses=(0x0101, 0x0101, 0x0602),
        )
        self.assertTrue(
            all(len(snapshot.words) == 2 for snapshot in targeted.snapshots)
        )
        self.assertEqual(
            [item.operation for item in targeted_backend.sent].count(0x41), 6
        )

    def test_sequence_live_trace_bounds_snapshot_count(self):
        with self.assertRaisesRegex(ValueError, "128 snapshots"):
            MicroFreakMidiTransport(
                midi_backend=FakeLiveTraceMido(), sleep_fn=lambda _: None
            ).capture_sequence_live_trace(
                clock_count=129,
                snapshot_every_clocks=1,
            )
        with self.assertRaisesRegex(ValueError, "invalid operation-41"):
            MicroFreakMidiTransport(
                midi_backend=FakeLiveTraceMido(), sleep_fn=lambda _: None
            ).capture_sequence_live_trace(
                clock_count=1,
                snapshot_every_clocks=1,
                snapshot_addresses=(0x1800,),
            )

    def test_global_dictionary_includes_hardware_confirmed_hidden_codes(self):
        self.assertEqual(len(MICROFREAK_GLOBAL_CODES), 43)
        self.assertEqual(MICROFREAK_GLOBAL_CODES["midi.automation_in"], 0x22)
        self.assertEqual(MICROFREAK_GLOBAL_CODES["midi.usb_to_din"], 0x43)

    def test_global_reply_uses_alternate_frame_family(self):
        reply = bytes.fromhex("00206b077f5f02422000")
        self.assertEqual(MicroFreakMidiTransport._decode_global_reply(reply, 0x20), 0)
        with self.assertRaises(Exception):
            MicroFreakMidiTransport._decode_global_reply(reply, 0x21)

    def test_raw_global_code_reads_are_bounded_and_read_only(self):
        backend = FakeMido(bytes(4672))
        values = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_global_codes((0x02, 0x13, 0x14, 0x13))
        self.assertEqual(values, {0x02: 0x57, 0x13: 0x46, 0x14: 0x41})
        self.assertEqual(
            [(item.operation, item.payload) for item in backend.sent],
            [(0x43, b"\x02"), (0x43, b"\x13"), (0x43, b"\x14")],
        )
        with self.assertRaisesRegex(ValueError, "at least one"):
            MicroFreakMidiTransport(midi_backend=backend).read_global_codes(())
        with self.assertRaisesRegex(ValueError, "0..127"):
            MicroFreakMidiTransport(midi_backend=backend).read_global_codes((128,))

    def test_guarded_global_write_reads_back_and_restores_setting_and_live_table(self):
        backend = FakeMido(bytes(4672))
        backend.global_values[0x46] = 0
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        report = transport.probe_global_setting_write(
            "keyboard.root_note", 1, 320
        )
        self.assertTrue(report.target_verified)
        self.assertTrue(report.restore_verified)
        self.assertEqual((report.before_value, report.readback_value), (0, 1))
        self.assertEqual(report.restored_value, 0)
        self.assertEqual(report.changes, ())
        self.assertEqual(backend.global_values[0x46], 0)
        self.assertEqual(
            [(item.operation, item.payload) for item in backend.sent if item.operation == 0x42],
            [(0x42, b"\x46\x01"), (0x42, b"\x46\x00")],
        )

    def test_domain_checked_global_write_backs_up_and_reads_back(self):
        import json
        import tempfile
        from pathlib import Path

        backend = FakeMido(bytes(4672))
        backend.global_values[0x46] = 0
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        with tempfile.TemporaryDirectory() as temp:
            backup = Path(temp) / "root-before.json"
            report = transport.write_global_setting(
                "keyboard.root_note", 1, backup
            )
            document = json.loads(backup.read_text())
        self.assertTrue(report.exact_readback)
        self.assertEqual((report.before_value, report.readback_value), (0, 1))
        self.assertEqual(document["before"]["label"], "C")
        self.assertEqual(document["target"]["label"], "C#")
        self.assertEqual(backend.global_values[0x46], 1)

    def test_domain_checked_global_write_refuses_invalid_values(self):
        backend = FakeMido(bytes(4672))
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        with self.assertRaisesRegex(ValueError, "target must be one of"):
            transport.write_global_setting("keyboard.root_note", 12, "unused.json")

    def test_control_reply_uses_device_originated_alternate_frame(self):
        reply = bytes.fromhex("00206b077f45094800000c000000011200")
        self.assertEqual(
            MicroFreakMidiTransport._decode_alt_reply(reply, 0x48, 9).hex(),
            "00000c000000011200",
        )

    def test_control_word_payload_restores_flagged_high_bits(self):
        self.assertEqual(
            decode_control_word_payload(bytes.fromhex("18000a7f7f")),
            (0x000A, 0xFFFF),
        )

    def test_codec_matches_official_header_request(self):
        encoded = encode_sysex(0x60, 0x19, b"\x00\x00\x00")
        self.assertEqual(encoded.hex(), "f000206b0701600319000000f7")
        decoded = decode_sysex(encoded)
        self.assertEqual(decoded.operation, 0x19)
        self.assertEqual(decoded.payload, b"\x00\x00\x00")

    def test_midi_8bit_pack_round_trip(self):
        raw = bytes(range(28))
        self.assertEqual(unpack_8bit_midi(pack_8bit_midi(raw)), raw)

    def test_direct_reader_reassembles_all_146_parts(self):
        payload = bytes((index % 128 for index in range(4672)))
        preset = MicroFreakMidiTransport(
            midi_backend=FakeMido(payload),
            timeout=0.01,
            sleep_fn=lambda _: None,
        ).read_preset(1)
        self.assertEqual(preset.name, "DirectProbe")
        self.assertEqual(preset.category_id, 2)
        self.assertEqual(preset.payload, payload)

    def test_reads_reserved_initializer_as_full_editable_template(self):
        payload = bytes((127 - index % 2 for index in range(4672)))
        backend = FakeMido(payload)
        preset = MicroFreakMidiTransport(
            midi_backend=backend,
            timeout=0.01,
            sleep_fn=lambda _: None,
        ).read_initializer_template()
        self.assertEqual((preset.name, preset.category_id, preset.init, preset.p1),
                         ("Init", 0, 1, 0x33))
        self.assertEqual(preset.payload, payload)
        starts = [
            message.payload
            for message in backend.sent
            if message.operation == 0x19
        ]
        self.assertEqual(starts, [b"\x04\x00\x00", b"\x04\x00\x01"])

    def test_direct_writer_uses_store_handshake_and_reads_back(self):
        import tempfile
        from pathlib import Path
        from minifreak_patch.microfreak import MicroFreakPreset

        backend = FakeMido(bytes(4672))
        target = MicroFreakPreset(
            "Written", 5, 0, 7, b"\x01" * 4672, version_tag="48"
        )
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_preset(
                320, target, Path(temp) / "slot-320.mfp"
            )
        self.assertTrue(report.exact_readback)
        self.assertTrue(report.archive_wrapper_normalized)
        self.assertEqual(report.target_sha256, report.readback_sha256)
        self.assertNotEqual(
            report.target_archive_sha256, report.readback_archive_sha256
        )
        self.assertEqual(backend.name, "Written")
        write_ops = [message.operation for message in backend.sent]
        self.assertIn(0x52, write_ops)
        self.assertEqual(write_ops.count(0x16), 145)
        self.assertEqual(write_ops.count(0x17), 1)

    def test_direct_selector_uses_four_bank_slot_mapping(self):
        backend = FakeMido(bytes(4672))
        bank, program = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).select_preset(320)
        self.assertEqual((bank, program), (2, 63))
        control, change = backend.channel_messages
        self.assertEqual(
            (control.type, control.channel, control.control, control.value),
            ("control_change", 0, 0, 2),
        )
        self.assertEqual(
            (change.type, change.channel, change.program),
            ("program_change", 0, 63),
        )

    def test_direct_wavetable_reader_reassembles_four_parts(self):
        backend = FakeMido(bytes(4672))
        table = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_wavetable(1)
        self.assertEqual(table.name, "WaveProbe")
        self.assertEqual(table.pcm16le, backend.wave_pcm)

    def test_direct_sample_inventory_decodes_lossless_headers(self):
        backend = FakeMido(bytes(4672))
        headers = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_sample_inventory()
        self.assertEqual(len(headers), 128)
        self.assertEqual(headers[0].name, "Sample 1")
        self.assertEqual(headers[0].address, 0x00281000)
        self.assertEqual(headers[0].size_bytes, 64000)
        self.assertEqual(headers[0].checksum, 0x1200)
        self.assertEqual(headers[0].device_id, 0)
        self.assertFalse(headers[0].empty)
        self.assertEqual(len(bytes.fromhex(headers[0].raw_header_hex)), 28)

    def test_direct_sample_storage_stats_preserve_raw_and_decode_usage(self):
        backend = FakeMido(bytes(4672))
        stats = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_sample_storage_stats()
        self.assertEqual(stats.used_milliseconds, 0x9281 * 4)
        self.assertEqual(stats.free_milliseconds, 209_920 - 0x9281 * 4)
        self.assertEqual(stats.estimated_free_bytes, stats.free_milliseconds * 64)
        self.assertEqual(stats.capacity_bytes, 209_920 * 64)
        self.assertEqual(stats.raw_payload_hex, "00000c000000011200")
        self.assertEqual(
            [item.operation for item in backend.sent], [0x1C, 0x47, 0x1D]
        )

    def test_direct_live_parameter_word_uses_bounded_read_session(self):
        backend = FakeMido(bytes(4672))
        word = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_live_parameter_word(3)
        self.assertEqual(
            (word.index, word.raw_u16, word.signed_i16),
            (3, 0x7FFF, 0x7FFF),
        )
        self.assertEqual(
            [item.operation for item in backend.sent], [0x1C, 0x41, 0x1D]
        )
        with self.assertRaisesRegex(ValueError, "group 0x00..0x17"):
            MicroFreakMidiTransport(
                midi_backend=backend
            ).read_live_parameter_word(0x1800)

    def test_control_index_encoder_preserves_high_bits(self):
        self.assertEqual(encode_control_index_payload(0x007F), bytes.fromhex("00007f"))
        self.assertEqual(encode_control_index_payload(0x0080), bytes.fromhex("200000"))
        self.assertEqual(encode_control_index_payload(0x017F), bytes.fromhex("00017f"))

    def test_control_word_encoder_round_trips_all_high_bits(self):
        payload = encode_control_word_payload(0x81A2, 0xB3C4)
        self.assertEqual(payload, bytes.fromhex("7801223344"))
        self.assertEqual(decode_control_word_payload(payload), (0x81A2, 0xB3C4))

    def test_control_word_request_rejects_reply_style_high_bits(self):
        self.assertEqual(
            encode_control_word_request_payload(0x0101, 0x254A),
            bytes.fromhex("000101254a"),
        )
        with self.assertRaisesRegex(ValueError, "7-bit clean"):
            encode_control_word_request_payload(0x0101, 0x3382)

    def test_internal_state_record_request_packs_arbitrary_live_target(self):
        self.assertEqual(
            pack_six_byte_state_record(bytes.fromhex("f5 02 01 01 4a 94")),
            bytes.fromhex("42 75 02 01 01 4a 14"),
        )
        self.assertEqual(
            encode_live_parameter_state_record_request(0x0101, 0x254A),
            bytes.fromhex("06 7d 42 75 02 01 01 4a 14"),
        )
        with self.assertRaisesRegex(ValueError, "six bytes"):
            pack_six_byte_state_record(b"short")
        with self.assertRaisesRegex(ValueError, "0..32767"):
            encode_live_parameter_state_record_request(0x0101, 0x8000)

    def test_live_word_semantics_preserve_known_aliases_and_dependents(self):
        cutoff = [
            address
            for address, item in MICROFREAK_LIVE_WORD_SEMANTICS.items()
            if item["parameter"] == "filter.cutoff"
        ]
        self.assertEqual(cutoff, [0x0101, 0x0F0E, 0x1008])
        self.assertEqual(
            MICROFREAK_LIVE_WORD_SEMANTICS[0x0B0D],
            {"parameter": "osc.type", "relationship": "dependent"},
        )
        self.assertEqual(
            [
                address
                for address, item in MICROFREAK_LIVE_WORD_SEMANTICS.items()
                if item["parameter"] == "cycling_env.rise_shape"
            ],
            [0x0105, 0x0202, 0x100C],
        )
        self.assertEqual(
            MICROFREAK_LIVE_WORD_SEMANTICS[0x0105]["evidence"],
            "saved_live_13_preset_exact_match_restore",
        )

    def test_direct_live_parameter_range_uses_one_bounded_session(self):
        backend = FakeMido(bytes(4672))
        backend.live_words[0x000F] = 0x1234
        backend.live_words.extend([0] * (0x0102 - len(backend.live_words)))
        backend.live_words[0x0100:0x0102] = [0xABCD, 0x8000]
        words = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_live_parameter_words(15, 3)
        self.assertEqual([word.raw_u16 for word in words], [0x1234, 0xABCD, 0x8000])
        self.assertEqual([word.signed_i16 for word in words], [0x1234, -0x5433, -0x8000])
        self.assertEqual(
            [item.operation for item in backend.sent],
            [0x1C, 0x41, 0x41, 0x41, 0x1D],
        )

    def test_live_structured_map_reads_99_unambiguous_tagged_fields(self):
        backend = FakeMido(bytes(4672))
        for address in MICROFREAK_STRUCTURED_LIVE_WORDS["VCF.Type"]:
            backend.live_words[address] = 0x1234
        fields = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_live_structured_fields()
        by_name = {field.name: field for field in fields}
        self.assertEqual(len(fields), 99)
        self.assertEqual(by_name["VCF.Type"].raw_u16, 0x1234)
        self.assertTrue(by_name["VCF.Type"].aliases_match)
        self.assertEqual(MICROFREAK_STRUCTURED_LIVE_AMBIGUOUS, ())
        self.assertEqual(
            MICROFREAK_STRUCTURED_LIVE_WORDS["Gen.ChOffs1"],
            (0x050D, 0x0708),
        )
        self.assertIn("Kbd.Root", MICROFREAK_STRUCTURED_CORPUS_NONVARYING)
        self.assertEqual(
            MICROFREAK_STRUCTURED_CORPUS_NONVARYING_UNRESOLVED,
            (
                "Gen.Panel", "Mat.MatBtn", "Mat.MatEnc", "Sys.PrsetBt",
                "Sys.PrsetID", "Sys.Save", "Sys.Utility",
            ),
        )
        self.assertEqual(
            MICROFREAK_STRUCTURED_NO_LIVE_TABLE_CC_EFFECT, ("Kbd.Hold",)
        )
        self.assertEqual(
            MICROFREAK_STRUCTURED_GLOBAL_COUNTERPARTS,
            {"Kbd.Root": "keyboard.root_note"},
        )
        self.assertEqual(by_name["Kbd.Hold"].addresses, (0x010D, 0x020A, 0x0303))
        self.assertEqual(by_name["Kbd.Root"].addresses, (0x020E, 0x0307))
        self.assertEqual(by_name["Arp.Dice"].addresses, (0x030F, 0x0407))
        self.assertEqual(by_name["Seq.XiceRst"].addresses, (0x070D, 0x1201))
        self.assertEqual(
            by_name["Kbd.Hold"].evidence,
            MICROFREAK_STRUCTURED_LIVE_FIELD_EVIDENCE["Kbd.Hold"],
        )
        self.assertEqual(
            [item.operation for item in backend.sent].count(0x41), 384
        )

    def test_guarded_live_write_reads_target_and_restores_complete_table(self):
        backend = FakeMido(bytes(4672))
        backend.live_words[0x0101] = 0x3382
        backend.preset_live_words = list(backend.live_words)
        report = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).probe_live_parameter_word_write(0x0101, 0x254A, 320)
        self.assertTrue(report.target_verified)
        self.assertTrue(report.restore_verified)
        self.assertEqual(report.before_raw_u16, 0x3382)
        self.assertEqual(report.readback_raw_u16, 0x254A)
        self.assertEqual(report.restored_raw_u16, 0x3382)
        self.assertEqual(report.changed_after_addresses, (0x0101,))
        self.assertEqual(report.changed_after_restore_addresses, ())
        self.assertEqual(backend.live_words[0x0101], 0x3382)
        self.assertEqual(report.restoration_method, "saved_slot_recall")

    def test_guarded_cc_probe_reports_all_changes_and_restores_by_inverse_cc(self):
        backend = FakeMido(bytes(4672))
        backend.live_words[0x0705] = 0
        backend.live_words[0x1104] = 0
        backend.cc_live_mutations = {
            (64, 127): {0x0705: 0x7FFF, 0x1104: 0x7FFF},
            (64, 0): {0x0705: 0, 0x1104: 0},
        }
        report = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).probe_live_control_change("keyboard.hold", 64, 127, 0, 320)
        self.assertTrue(report.target_effect_observed)
        self.assertTrue(report.restore_verified)
        self.assertEqual(report.restoration_method, "inverse_midi_cc")
        self.assertEqual(
            [change.index for change in report.changes], [0x0705, 0x1104]
        )
        self.assertEqual(report.changed_after_restore_addresses, ())
        self.assertEqual(
            [(message.control, message.value) for message in backend.channel_messages],
            [(64, 127), (64, 0)],
        )

    def test_guarded_cc_probe_records_no_live_table_effect(self):
        backend = FakeMido(bytes(4672))
        report = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).probe_live_control_change("keyboard.hold", 64, 127, 0, 320)
        self.assertFalse(report.target_effect_observed)
        self.assertTrue(report.restore_verified)
        self.assertEqual(report.changes, ())

    def test_guarded_internal_record_write_restores_without_slot_recall(self):
        backend = FakeMido(bytes(4672))
        backend.live_words[0x0101] = 0x3382
        backend.preset_live_words = list(backend.live_words)
        report = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).probe_live_parameter_state_record_write(0x0101, 0x254A, 320)
        self.assertTrue(report.target_verified)
        self.assertTrue(report.restore_verified)
        self.assertEqual(report.readback_raw_u16, 0x254A)
        self.assertEqual(report.restored_raw_u16, 0x3382)
        self.assertEqual(report.changed_after_addresses, (0x0101,))
        self.assertEqual(report.changed_after_restore_addresses, ())
        self.assertEqual(report.restoration_method, "operation_49_internal_record")
        self.assertEqual(
            [item.operation for item in backend.sent].count(0x49),
            2,
        )

    def test_direct_sample_reader_reassembles_and_truncates_sequential_blocks(self):
        backend = FakeMido(bytes(4672))
        backend.sample_pcm = bytes((index * 17 % 256 for index in range(5000)))
        backend.sample_size_override = len(backend.sample_pcm)
        sample = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        ).read_sample(1)
        self.assertEqual(sample.header.name, "Sample 1")
        self.assertEqual(sample.audio_bytes, backend.sample_pcm)
        starts = [item.payload for item in backend.sent if item.operation == 0x59]
        self.assertEqual(starts, [b"\x00\x00", b"\x00\x01"])

    def test_sample_checksum_is_little_endian_u16_sum(self):
        self.assertEqual(
            microfreak_sample_checksum(bytes.fromhex("0100 ffff 3412")),
            0x1234,
        )
        with self.assertRaisesRegex(ValueError, "complete 16-bit"):
            microfreak_sample_checksum(b"\x00")

    def test_direct_sample_upload_readback_and_clear(self):
        import tempfile
        from pathlib import Path

        backend = FakeMido(bytes(4672))
        backend.sample_uploaded[1] = {
            "name": "",
            "size": 0,
            "checksum": 0,
            "audio": bytearray(),
        }
        target = bytes((index * 29) % 256 for index in range(5000))
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_sample(
                2, "CodexProbe", target, Path(temp) / "slot-2.mfsample"
            )
            cleared = transport.clear_sample(
                2, Path(temp) / "slot-2-uploaded.mfsample"
            )
        self.assertTrue(report.before_empty)
        self.assertTrue(report.exact_readback)
        self.assertEqual(report.target_sha256, report.readback_sha256)
        self.assertTrue(cleared.empty_verified)
        self.assertTrue(
            MicroFreakMidiTransport(
                midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
            ).read_sample_header(2).empty
        )
        self.assertEqual(
            [item.operation for item in backend.sent].count(0x58), 2
        )

    def test_direct_wavetable_upload_and_clear(self):
        import tempfile
        from pathlib import Path
        from minifreak_patch.wavetable import MicroFreakWavetable

        backend = FakeMido(bytes(4672))
        backend.wave_empty = True
        backend.wave_name = ""
        transport = MicroFreakMidiTransport(
            midi_backend=backend, timeout=0.01, sleep_fn=lambda _: None
        )
        target = MicroFreakWavetable("Uploaded", b"\x34\x12" * 8192)
        with tempfile.TemporaryDirectory() as temp:
            report = transport.write_wavetable(
                2, target, Path(temp) / "slot-2.mfw"
            )
            cleared = transport.clear_wavetable(
                2, Path(temp) / "slot-2-uploaded.mfw"
            )
        self.assertTrue(report.before_empty)
        self.assertTrue(report.exact_readback)
        self.assertTrue(cleared.empty_verified)
        self.assertTrue(backend.wave_empty)


if __name__ == "__main__":
    unittest.main()
