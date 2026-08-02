import importlib.util
from pathlib import Path
import sys
import unittest


TOOL = Path(__file__).parents[1] / "tools" / "select_microfreak_saved_live_corpus.py"
SPEC = importlib.util.spec_from_file_location("saved_live_selection", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class SavedLiveSelectionTests(unittest.TestCase):
    def test_greedy_selection_honors_includes_and_adds_diversity(self):
        rows = [
            {"slot": 1, "name": "A", "values": {"x": 0, "y": 0}, "metadata": {"x": 1, "y": 1}},
            {"slot": 2, "name": "B", "values": {"x": 1, "y": 0}, "metadata": {"x": 1, "y": 1}},
            {"slot": 3, "name": "C", "values": {"x": 0, "y": 1}, "metadata": {"x": 1, "y": 1}},
            {"slot": 4, "name": "D", "values": {"x": 1, "y": 1}, "metadata": {"x": 1, "y": 1}},
        ]
        selected = MODULE.select_diverse_rows(
            rows, 2, include_slots=(1,), value_cap=2
        )
        self.assertEqual([row["slot"] for row in selected], [1, 4])

    def test_rejects_missing_included_slot(self):
        with self.assertRaisesRegex(ValueError, "absent"):
            MODULE.select_diverse_rows(
                [{"slot": 1, "name": "A", "values": {}, "metadata": {}}],
                1,
                include_slots=(2,),
            )


if __name__ == "__main__":
    unittest.main()
