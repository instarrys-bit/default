import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from persist_review_cursor import persist_cursor


class PersistReviewCursorTests(unittest.TestCase):
    def cursor(self, **overrides):
        data = {
            "schema_version": 1, "snapshot_sha256": "a" * 64,
            "candidate_count": 5, "next_index": 2, "batch_size": 2,
            "status": "in_progress",
        }
        data.update(overrides)
        return data

    def test_persists_valid_in_progress_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); artifact = root / "artifact.json"
            destination = root / "repo/sources/review_cursor.json"
            artifact.write_text(json.dumps(self.cursor()), encoding="utf-8")
            self.assertEqual(persist_cursor(artifact, destination), "in_progress")
            self.assertEqual(json.loads(destination.read_text())["next_index"], 2)

    def test_missing_artifact_is_successful_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); destination = root / "repo/sources/review_cursor.json"
            destination.parent.mkdir(parents=True); destination.write_text("previous")
            self.assertEqual(persist_cursor(root / "missing.json", destination), "missing")
            self.assertEqual(destination.read_text(), "previous")

    def test_complete_cursor_removes_stale_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); artifact = root / "artifact.json"
            destination = root / "repo/sources/review_cursor.json"
            destination.parent.mkdir(parents=True); destination.write_text("stale")
            artifact.write_text(json.dumps(self.cursor(status="complete", next_index=5)))
            self.assertEqual(persist_cursor(artifact, destination), "complete")
            self.assertFalse(destination.exists())

    def test_invalid_cursor_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); artifact = root / "artifact.json"
            artifact.write_text(json.dumps(self.cursor(next_index=0)))
            with self.assertRaisesRegex(ValueError, "checkpoint"):
                persist_cursor(artifact, root / "repo/sources/review_cursor.json")


    def test_invalid_complete_cursor_does_not_remove_existing_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); artifact = root / "artifact.json"
            destination = root / "repo/sources/review_cursor.json"
            destination.parent.mkdir(parents=True); destination.write_text("keep")
            artifact.write_text(json.dumps(self.cursor(status="complete", next_index=4)))
            with self.assertRaisesRegex(ValueError, "completed cursor"):
                persist_cursor(artifact, destination)
            self.assertEqual(destination.read_text(), "keep")

if __name__ == "__main__":
    unittest.main()
