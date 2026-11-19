import unittest

ROOT = __import__("pathlib").Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0, str(ROOT / "scripts"))
from build_rulesets import reject_rule_authorized, reject_queue_entry_authorized


class RejectAutomaticPublicationTests(unittest.TestCase):
    def test_new_rule_passes_when_automated_secondary_gate_passes(self):
        line = "DOMAIN,new-ad.example"
        self.assertTrue(reject_rule_authorized(line, set(), {line}))

    def test_new_rule_is_held_when_secondary_gate_does_not_pass(self):
        line = "DOMAIN,new-ad.example"
        self.assertFalse(reject_rule_authorized(line, set(), set()))

    def test_existing_published_rule_is_preserved(self):
        line = "DOMAIN,existing-ad.example"
        self.assertTrue(reject_rule_authorized(line, {line}, set()))

    def test_pending_queue_requires_current_secondary_pass(self):
        line = "DOMAIN,queued-ad.example"
        self.assertFalse(reject_queue_entry_authorized(line, set(), set()))
        self.assertTrue(reject_queue_entry_authorized(line, set(), {line}))

    def test_previously_published_queue_item_is_preserved(self):
        line = "DOMAIN,existing-ad.example"
        self.assertTrue(reject_queue_entry_authorized(line, {line}, set()))


if __name__ == "__main__":
    unittest.main()
