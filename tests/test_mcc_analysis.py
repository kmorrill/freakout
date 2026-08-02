import importlib.util
from pathlib import Path
import struct
import sys
import unittest


TOOL = Path(__file__).parents[1] / "tools" / "analyze_mcc_microfreak_commands.py"
SPEC = importlib.util.spec_from_file_location("mcc_microfreak_analysis", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class MccAnalysisTests(unittest.TestCase):
    def test_decodes_libcxx_short_string_table(self):
        table = bytearray(48)
        for index, value in enumerate((b"kOptMidiChannelIn", b"kEmpty")):
            offset = index * 24
            table[offset] = len(value) * 2
            table[offset + 1 : offset + 1 + len(value)] = value

        self.assertEqual(
            MODULE.decode_libcxx_short_strings(table),
            {0x20: "kOptMidiChannelIn", 0x21: "kEmpty"},
        )

    def test_rejects_long_string_storage(self):
        with self.assertRaisesRegex(ValueError, "long-string"):
            MODULE.decode_libcxx_short_strings(bytes([1]) + bytes(23))

    def test_parses_and_maps_macho_segment(self):
        command = struct.pack(
            "<II16sQQQQIIII",
            MODULE.LC_SEGMENT_64,
            72,
            b"__TEXT" + bytes(10),
            0x100000000,
            0x2000,
            0,
            0x1800,
            5,
            5,
            0,
            0,
        )
        header = struct.pack(
            "<IIIIIIII",
            MODULE.MACHO_MAGIC_64,
            0,
            0,
            0,
            1,
            len(command),
            0,
            0,
        )
        segments = MODULE.parse_macho_segments(header + command)
        self.assertEqual(segments[0].name, "__TEXT")
        self.assertEqual(MODULE.vma_to_file_offset(0x100000123, segments), 0x123)

    def test_normalizes_and_filters_passive_call_stacks(self):
        segments = [
            MODULE.MachOSegment("__TEXT", 0x100000000, 0x2000000, 0, 0x1000)
        ]
        lines = [
            "capture-loaded duplex-v2 image-base=0x100a96000",
            (
                "trace timestamp=1 op=0x19 frames="
                "0x10c309a7d,0x100f5b6fd,0x10100020d,0x7ff812d9708e"
            ),
            (
                "trace timestamp=2 op=0x19 frames="
                "0x10c309a7d,0x100f5b6fd,0x10100020d"
            ),
        ]
        stacks = MODULE.parse_normalized_call_stacks(lines, segments)
        self.assertEqual(
            stacks[0x19],
            {(0x1004C56FD, 0x10056A20D): 2},
        )

    def test_rejects_conflicting_capture_image_bases(self):
        segments = [MODULE.MachOSegment("__TEXT", 0x100000000, 1, 0, 1)]
        with self.assertRaisesRegex(ValueError, "conflicting"):
            MODULE.parse_normalized_call_stacks(
                [
                    "capture-loaded duplex-v2 image-base=0x100a96000",
                    "capture-loaded duplex-v2 image-base=0x100b96000",
                ],
                segments,
            )

    def test_correlates_stack_with_outbound_payload_shape(self):
        segments = [
            MODULE.MachOSegment("__TEXT", 0x100000000, 0x2000000, 0, 0x1000)
        ]
        lines = [
            "capture-loaded duplex-v2 image-base=0x100a96000",
            "out timestamp=1 data=f000206b0701000319000000f7",
            "trace timestamp=1 op=0x19 frames=0x100f5b6fd",
            "out timestamp=2 data=f000206b0701010319000100f7",
            "trace timestamp=2 op=0x19 frames=0x100f5b6fd",
            "out timestamp=3 data=f000206b0701020319000001f7",
            "trace timestamp=3 op=0x19 frames=0x100f5b6fd,0x10100020d",
        ]
        report = MODULE.call_stack_report(lines, segments)["0x19"]
        self.assertEqual(report["trace_count"], 3)
        self.assertEqual(report["unmatched_trace_count"], 0)
        self.assertEqual(
            report["unique_stacks"][0]["payload_shapes"],
            [
                {
                    "payload_length": 3,
                    "final_byte": "0x00",
                    "count": 2,
                    "distinct_payloads": 2,
                }
            ],
        )
        self.assertEqual(
            report["unique_stacks"][1]["payload_shapes"][0]["final_byte"],
            "0x01",
        )

    def test_rejects_trace_operation_mismatch(self):
        segments = [MODULE.MachOSegment("__TEXT", 0x100000000, 1, 0, 1)]
        with self.assertRaisesRegex(ValueError, "does not match"):
            MODULE.call_stack_report(
                [
                    "capture-loaded duplex-v2 image-base=0x100000000",
                    "out timestamp=1 data=f000206b0701000319000000f7",
                    "trace timestamp=1 op=0x18 frames=0x100000000",
                ],
                segments,
            )


if __name__ == "__main__":
    unittest.main()
