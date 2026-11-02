import gzip
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from sharded_candidate_store import append_records, iter_records, load_manifest, verify_store


class ShardedCandidateStoreTests(unittest.TestCase):
    def test_append_deduplicates_across_runs_and_shards(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            first = append_records(root, ({"domain": f"d{i}.example"} for i in range(5)), shard_records=2)
            second = append_records(root, iter([{"domain": "d1.example"}, {"domain": "new.example"}]), shard_records=2)
            self.assertEqual(first["added"], 5)
            self.assertEqual(second["added"], 1)
            self.assertEqual(verify_store(root), {"candidate_count": 6, "shard_count": 3, "verified": True})

    def test_cap_fails_closed_without_manifest_promotion(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            append_records(root, [{"domain": "a.example"}], max_candidates=2)
            before = load_manifest(root)
            with self.assertRaises(ValueError):
                append_records(root, [{"domain": "b.example"}, {"domain": "c.example"}], max_candidates=2)
            self.assertEqual(load_manifest(root), before)

    def test_corrupt_shard_fails_verification(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            append_records(root, [{"domain": "a.example"}])
            shard = root / load_manifest(root)["shards"][0]["path"]
            shard.write_bytes(b"broken")
            with self.assertRaises((ValueError, OSError, EOFError)):
                verify_store(root)

    def test_manifest_count_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            append_records(root, [{"domain": "a.example"}])
            manifest_path = root / "manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["candidate_count"] = 2
            manifest_path.write_text(json.dumps(manifest))
            with self.assertRaises(ValueError):
                load_manifest(root)


if __name__ == "__main__":
    unittest.main()
