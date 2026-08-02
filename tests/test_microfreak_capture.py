import unittest

from minifreak_patch.microfreak_capture import parse_capture_lines, summarize_capture
from minifreak_patch.microfreak_midi import encode_sysex


def line(direction: str, operation: int, payload: bytes = b"") -> str:
    return f"{direction} timestamp=1 data={encode_sysex(0, operation, payload).hex()}"


class MicroFreakCaptureTests(unittest.TestCase):
    def test_ignores_identity_and_preserves_direction(self):
        messages = parse_capture_lines(
            ["out timestamp=1 data=f07e7f0601f7", line("out", 0x43, b"\x20")]
        )
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].direction, "out")
        self.assertEqual(messages[0].message.operation, 0x43)

    def test_classifies_inventory_without_mistaking_it_for_presets(self):
        lines = []
        for slot in range(512):
            bank, program = divmod(slot, 128)
            lines.append(line("out", 0x19, bytes((bank, program, 0))))
            lines.append(line("in", 0x52, bytes(35)))
        lines.extend(line("out", 0x57, bytes((slot, 0, 0))) for slot in range(16))
        lines.extend(line("out", 0x55, b"\x00\x00\x00") for _ in range(64))
        lines.extend(line("out", 0x5B, b"\x00") for _ in range(128))
        summary = summarize_capture(parse_capture_lines(lines))
        self.assertEqual(summary["startup_inventory_shape"], "full")
        self.assertEqual(summary["complete_startup_inventory_cycles"], 1)
        self.assertEqual(summary["preset_header_queries"], 512)
        self.assertEqual(summary["preset_body_starts"], 0)
        self.assertFalse(summary["observed_current_buffer_request"])

    def test_recognizes_repeated_complete_startup_scans(self):
        lines = []
        for _ in range(2):
            lines.extend(
                line("out", 0x19, bytes((*divmod(slot, 128), 0)))
                for slot in range(512)
            )
            lines.extend(line("out", 0x57, b"\x00") for _ in range(16))
            lines.extend(line("out", 0x55, b"\x00") for _ in range(64))
            lines.extend(line("out", 0x5B, b"\x00") for _ in range(128))
        summary = summarize_capture(parse_capture_lines(lines))
        self.assertEqual(summary["complete_startup_inventory_cycles"], 2)
        self.assertEqual(summary["startup_inventory_shape"], "full")

    def test_counts_saved_preset_body_start_separately(self):
        summary = summarize_capture(
            parse_capture_lines([line("out", 0x19, b"\x02\x3f\x01")])
        )
        self.assertEqual(summary["preset_body_starts"], 1)
        self.assertEqual(summary["preset_header_queries"], 0)


if __name__ == "__main__":
    unittest.main()
