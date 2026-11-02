import sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from review_cursor import snapshot_digest,resume_index,checkpoint

class ReviewCursorTests(unittest.TestCase):
    def test_resume_uses_saved_offset_for_identical_snapshot(self):
        digest=snapshot_digest([{"id":"a","sha256":"1"}],[{"domain":"a.example"},{"domain":"b.example"}])
        self.assertEqual(resume_index(checkpoint(digest,2,1,1),digest,2),1)
    def test_changed_snapshot_resets_cursor(self):
        old=snapshot_digest([], [{"domain":"a.example"}]); new=snapshot_digest([], [{"domain":"b.example"}])
        self.assertEqual(resume_index(checkpoint(old,1,1,1),new,1),0)
    def test_completed_cursor_does_not_resume_midstream(self):
        digest=snapshot_digest([], [{"domain":"a.example"}])
        self.assertEqual(resume_index(checkpoint(digest,1,1,1,status="complete"),digest,1),0)
    def test_cursor_bounds_fail_closed(self):
        with self.assertRaises(ValueError): checkpoint("a"*64,2,3,1)
        with self.assertRaises(ValueError): checkpoint("a"*64,2,1,1,status="complete")
    def test_digest_is_order_independent_for_object_keys(self):
        self.assertEqual(snapshot_digest([{"id":"a","sha256":"1"}],[{"domain":"x"}]),snapshot_digest([{"sha256":"1","id":"a"}],[{"domain":"x"}]))

if __name__=="__main__": unittest.main()
