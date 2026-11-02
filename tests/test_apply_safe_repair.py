import json
import tempfile
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from apply_safe_repair import apply, REPAIR_ID


class ApplySafeRepairTests(unittest.TestCase):
    def make_root(self):
        root = Path(tempfile.mkdtemp())
        (root / "scripts").mkdir()
        (root / "scripts/refresh_ruleset_manifest.py").write_text("# allowlisted helper\n", encoding="utf-8")
        (root / ".github/workflows").mkdir(parents=True)
        workflow = (
            "      - name: Compile and run deterministic review tests\n"
            "        run: |\n"
            "          python3 -m py_compile scripts/build_rule_provenance.py\n"
            "      - name: Build append-only rule-level provenance ledger\n"
            "        run: python3 scripts/build_rule_provenance.py\n"
        )
        (root / ".github/workflows/auto_sync.yml").write_text(workflow, encoding="utf-8")
        return root

    def test_allowlisted_repair_is_idempotent(self):
        root = self.make_root()
        diagnosis = {"repair_id": REPAIR_ID, "automatic_code_change_allowed": True}
        first = apply(root, diagnosis)
        second = apply(root, diagnosis)
        self.assertEqual(first, [".github/workflows/auto_sync.yml"])
        self.assertEqual(second, [])
        text = (root / ".github/workflows/auto_sync.yml").read_text(encoding="utf-8")
        self.assertEqual(text.count("python3 scripts/refresh_ruleset_manifest.py"), 1)
        self.assertIn("scripts/refresh_ruleset_manifest.py", text.split("python3 -m py_compile ", 1)[1])

    def test_unknown_diagnosis_is_rejected(self):
        root = self.make_root()
        with self.assertRaises(ValueError):
            apply(root, {"repair_id": None, "automatic_code_change_allowed": False})


if __name__ == "__main__":
    unittest.main()
