import base64
import importlib.util
from pathlib import Path
import sys
import unittest

from minifreak_patch.microfreak_midi import pack_8bit_midi


TOOL = (
    Path(__file__).parents[1]
    / "tools"
    / "analyze_microfreak_oscillator_type_corpus.py"
)
SPEC = importlib.util.spec_from_file_location("oscillator_type_corpus", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def payload(engine: int, maximum: int = 17) -> str:
    raw = round(engine * 32767 / maximum)
    prefix = b"#VCO" + b"DTypec" + bytes((maximum,)) + raw.to_bytes(2, "little")
    prefix += b"@ \xff"
    unpacked = (prefix + bytes((0xFF,)) * 4088)[:4088]
    return base64.b64encode(pack_8bit_midi(unpacked)).decode("ascii")


class OscillatorTypeCorpusTests(unittest.TestCase):
    def test_tagged_saved_engine_matches_normalized_live_grid(self):
        report = MODULE.analyze_oscillator_type_corpus(
            {
                "rows": [
                    {
                        "slot": 1,
                        "name": "One",
                        "saved_legacy_osc_type": 75,
                        "live_word_0000": 14894,
                        "payload_base64": payload(10),
                    },
                    {
                        "slot": 2,
                        "name": "Two",
                        "saved_legacy_osc_type": 127,
                        "live_word_0000": 25320,
                        "payload_base64": payload(17),
                    },
                ],
                "final_live_differences": [],
            }
        )
        self.assertEqual(report["engine_indices"], [10, 17])
        self.assertTrue(report["all_saved_vco_types_match_live_engine"])
        self.assertTrue(report["restoration_verified"])

    def test_reports_saved_live_mismatch(self):
        report = MODULE.analyze_oscillator_type_corpus(
            {
                "rows": [
                    {
                        "slot": 3,
                        "live_word_0000": 14894,
                        "payload_base64": payload(9),
                    }
                ]
            }
        )
        self.assertFalse(report["all_saved_vco_types_match_live_engine"])
        self.assertEqual(report["mismatches"][0]["saved_engine_index"], 9)


if __name__ == "__main__":
    unittest.main()
