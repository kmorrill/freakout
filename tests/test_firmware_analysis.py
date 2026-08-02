import importlib.util
from pathlib import Path
import struct
import sys
import unittest


TOOL = Path(__file__).parents[1] / "tools" / "analyze_microfreak_firmware_dispatch.py"
SPEC = importlib.util.spec_from_file_location("firmware_dispatch_analysis", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class FirmwareAnalysisTests(unittest.TestCase):
    def test_file_views_map_same_vma_to_independent_stored_offsets(self):
        arguments = {
            "address": 0x08047D4C,
            "base": 0x08020000,
            "header_size": 0x40,
        }
        direct = MODULE.file_offset_for_address(**arguments, file_shift=0)
        overlay = MODULE.file_offset_for_address(**arguments, file_shift=0x8000)

        self.assertEqual(direct, 0x27D8C)
        self.assertEqual(overlay, 0x2FD8C)
        self.assertEqual(overlay - direct, 0x8000)

    def test_byte_anchor_finder_reports_all_overlapping_occurrences(self):
        self.assertEqual(
            MODULE.find_byte_offsets(b"ABABA", b"ABA"),
            [0, 2],
        )

    def test_byte_anchor_finder_rejects_empty_anchor(self):
        with self.assertRaisesRegex(ValueError, "must not be empty"):
            MODULE.find_byte_offsets(b"firmware", b"")

    def test_tbh_dispatch_decoder_distinguishes_default_branch(self):
        image = bytearray(0x80)
        table_address = 0x1020
        table_offset = 0x20
        targets = (0x1040, 0x1030, 0x1048)
        for index, target in enumerate(targets):
            struct.pack_into(
                "<H", image, table_offset + index * 2, (target - table_address) // 2
            )

        entries = MODULE.decode_thumb_tbh_table(
            bytes(image),
            table_address=table_address,
            first_operation=0x15,
            last_operation=0x17,
            default_target=0x1030,
            base=0x1000,
            header_size=0,
        )

        self.assertEqual([item.operation for item in entries], [0x15, 0x16, 0x17])
        self.assertEqual([item.target_address for item in entries], list(targets))
        self.assertEqual([item.implemented for item in entries], [True, False, True])

    def test_fw5_decoder_rejects_an_unpinned_image(self):
        with self.assertRaisesRegex(ValueError, "pinned to MicroFreak FW5"):
            MODULE.decode_fw5_bulk_dispatch(b"not the firmware")

        with self.assertRaisesRegex(ValueError, "pinned to MicroFreak FW5"):
            MODULE.decode_fw5_control_dispatch(b"not the firmware")

        with self.assertRaisesRegex(ValueError, "pinned to MicroFreak FW5"):
            MODULE.decode_fw5_maintenance_subcommands(b"not the firmware")

        with self.assertRaisesRegex(ValueError, "pinned to MicroFreak FW5"):
            MODULE.decode_fw5_debug_commands(b"not the firmware")

        with self.assertRaisesRegex(ValueError, "pinned to MicroFreak FW5"):
            MODULE.decode_fw5_runtime_controls(b"not the firmware")

    def test_function_pointer_table_decodes_thumb_targets(self):
        image = bytearray(0x40)
        struct.pack_into("<III", image, 0x10, 0x08047001, 0x08047100, 0x080472F5)

        entries = MODULE.decode_function_pointer_table(
            bytes(image),
            table_address=0x1010,
            count=3,
            base=0x1000,
            header_size=0,
        )

        self.assertEqual([item.index for item in entries], [0, 1, 2])
        self.assertEqual(
            [item.target_address for item in entries],
            [0x08047000, 0x08047100, 0x080472F4],
        )
        self.assertEqual([item.thumb for item in entries], [True, False, True])

    def test_operation_49_metadata_keeps_structure_and_meaning_distinct(self):
        self.assertEqual(
            MODULE.MAINTENANCE_TARGET_STORED_VIEW_FILE_SHIFT,
            0x14000,
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[4]["role"],
            "no_op_unimplemented",
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[7]["role"],
            "diagnostic_bitmask_read",
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[2]["role"],
            "hidden_global_selector_0x13_write",
        )
        self.assertEqual(MODULE.CONTROL_INCOMING_HANDLER_ADDRESS, 0x08046F74)
        self.assertEqual(MODULE.MAINTENANCE_MINIMUM_OPERATION_PAYLOAD_BYTES, 2)
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[2]["payload_shape"],
            "subcommand_u8_value_u8",
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[2][
                "value_payload_byte_offset"
            ],
            1,
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[0][
                "runtime_event_object_ram_address"
            ],
            0x200035A4,
        )
        self.assertIn(
            "candidate",
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[8]["evidence_status"],
        )
        self.assertEqual(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[8][
                "source_active_parameter_object_ram_address"
            ],
            0x2001C898,
        )
        self.assertFalse(
            MODULE.MAINTENANCE_SUBCOMMAND_METADATA[8][
                "active_sequence_object_direct_reference"
            ]
        )

    def test_debug_command_table_decodes_pointer_index_records(self):
        image = bytearray(0x80)
        image[0x40:0x45] = b"gpio\0"
        image[0x48:0x4d] = b"boot\0"
        struct.pack_into("<IiIi", image, 0x10, 0x1040, 0, 0x1048, 1)
        entries = MODULE.decode_debug_command_table(
            bytes(image),
            table_address=0x1010,
            count=2,
            base=0x1000,
            header_size=0,
            file_shift=0,
        )
        self.assertEqual([item.name for item in entries], ["gpio", "boot"])
        self.assertEqual([item.index for item in entries], [0, 1])

    def test_operation_49_state_record_decoder_restores_all_six_high_bits(self):
        decoded = MODULE.decode_flag_packed_six_byte_record(
            bytes.fromhex("6a 75 02 03 04 05 06")
        )
        self.assertEqual(decoded, bytes.fromhex("f5 82 03 84 05 86"))
        described = MODULE.describe_six_byte_state_record(
            bytes.fromhex("f5 02 11 0a 12 34")
        )
        self.assertEqual(described["source_nibble"], 0x0F)
        self.assertEqual(described["header_nibble"], 0x05)
        self.assertEqual(described["kind"], 0x02)
        self.assertEqual(described["address_be"], 0x110A)
        self.assertEqual(described["value_be"], 0x1234)
        with self.assertRaisesRegex(ValueError, "seven 7-bit bytes"):
            MODULE.decode_flag_packed_six_byte_record(b"too short")

    def test_preset_save_path_coordinates_and_sizes_are_explicit(self):
        self.assertEqual(
            MODULE.PRESET_SERIALIZER_LINKED_ADDRESS - 0x08020000,
            MODULE.PRESET_SERIALIZER_RAW_FILE_OFFSET,
        )
        self.assertEqual(
            MODULE.PRESET_SLOT_WRITER_LINKED_ADDRESS - 0x08020000,
            MODULE.PRESET_SLOT_WRITER_RAW_FILE_OFFSET,
        )
        self.assertEqual(MODULE.PRESET_FLASH_SLOT_BYTES, 4096)
        self.assertEqual(MODULE.PRESET_SEQUENCE_BYTES, 0x824)
        self.assertEqual(len(MODULE.PRESET_SERIALIZER_CALLERS_LINKED), 2)
        self.assertEqual(MODULE.ACTIVE_SEQUENCE_OBJECT_RAM_ADDRESS, 0x20000EEC)
        self.assertEqual(
            MODULE.ACTIVE_SEQUENCE_DIRECT_KNOWN_SYSEX_HANDLER_REFERENCES, 0
        )
        self.assertNotIn(
            MODULE.PRESET_SEQUENCE_SERIALIZER_LINKED_ADDRESS,
            MODULE.ACTIVE_SEQUENCE_ACCESSOR_FUNCTIONS,
        )


if __name__ == "__main__":
    unittest.main()
