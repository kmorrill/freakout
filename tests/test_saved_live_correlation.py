import importlib.util
from pathlib import Path
import sys
import unittest


TOOL = Path(__file__).parents[1] / "tools" / "analyze_microfreak_saved_live_corpus.py"
SPEC = importlib.util.spec_from_file_location("saved_live_correlation", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SavedLiveCorrelationTests(unittest.TestCase):
    def test_exact_vector_matches_and_constants_remain_explicit(self):
        report = MODULE.correlate_saved_live_corpus(
            {
                "rows": [
                    {
                        "parameters": {"cutoff": 100, "constant": 7},
                        "live_words": {"0101": 100, "0102": 9, "0103": 7},
                    },
                    {
                        "parameters": {"cutoff": 200, "constant": 7},
                        "live_words": {"0101": 200, "0102": 8, "0103": 7},
                    },
                ],
                "final_live_differences": [],
            }
        )
        self.assertEqual(
            report["parameters"]["cutoff"]["exact_live_addresses"], ["0101"]
        )
        self.assertEqual(
            report["parameters"]["constant"]["unique_saved_values"], 1
        )
        self.assertTrue(report["restoration_verified"])

    def test_requires_multiple_rows(self):
        with self.assertRaisesRegex(ValueError, "at least two"):
            MODULE.correlate_saved_live_corpus({"rows": []})

    def test_structured_fields_find_deterministic_and_affine_live_words(self):
        rows = []
        for value in (10, 20, 30, 40):
            rows.append(
                {
                    "parameters": {"canonical": value},
                    "structured_parameters": {"VCO.Test": value},
                    "live_words": {
                        "0001": value * 2 + 3,
                        "0002": value if value != 30 else 31,
                    },
                }
            )
        report = MODULE.correlate_saved_live_corpus(
            {"rows": rows, "final_live_differences": []}
        )
        evidence = report["structured_parameters"]["VCO.Test"]
        self.assertIn("0001", evidence["deterministic_live_addresses"])
        self.assertEqual(
            evidence["exact_affine_live_addresses"]["0001"],
            {
                "scale_numerator": 2,
                "scale_denominator": 1,
                "offset_numerator": 3,
                "offset_denominator": 1,
            },
        )
        self.assertNotIn("0002", evidence["exact_affine_live_addresses"])


if __name__ == "__main__":
    unittest.main()
