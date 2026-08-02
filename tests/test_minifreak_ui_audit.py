import importlib.util
from pathlib import Path
import unittest


TOOL = Path(__file__).resolve().parents[1] / "tools/audit_minifreak_ui.py"
SPEC = importlib.util.spec_from_file_location("audit_minifreak_ui", TOOL)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class MiniFreakUiAuditTests(unittest.TestCase):
    def test_check_requires_zero_unresolved_patch_surface_items(self):
        report = {
            "summary": {
                "unresolved_patch_surface_templates": 0,
                "classification_counts": {},
            }
        }
        self.assertTrue(MODULE.audit_passes(report))
        report["summary"]["classification_counts"]["patch_surface_unresolved"] = 1
        self.assertFalse(MODULE.audit_passes(report))

    def test_check_rejects_unresolved_patch_template(self):
        report = {
            "summary": {
                "unresolved_patch_surface_templates": 1,
                "classification_counts": {},
            }
        }
        self.assertFalse(MODULE.audit_passes(report))


if __name__ == "__main__":
    unittest.main()
