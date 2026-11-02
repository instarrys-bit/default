import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from assess_sources import assess_payload


class LeadingDotAssessmentTests(unittest.TestCase):
    def test_leading_dot_domains_are_counted_and_double_dot_entries_rejected(self):
        lines = [f".d{i}.example" for i in range(25)] + ["..invalid.example"]
        result = assess_payload("\n".join(lines).encode(), "https://raw.githubusercontent.com/example/rules/main/list", ["PROXY"])
        self.assertEqual(result["parser_candidate"], "domain-only")
        self.assertEqual(result["leading_dot_domain_count"], 25)
        self.assertEqual(result["domain_only_count"], 25)


if __name__ == "__main__":
    unittest.main()
