import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import json_document_store as store


class JsonDocumentStoreTests(unittest.TestCase):
    def test_legacy_json_remains_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            payload = {"schema_version": 2, "reviews": [{"domain": "example.com"}]}
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(store.read_document(path, "reviews"), payload)

    def test_small_document_stays_legacy_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            payload = {"schema_version": 1, "reviews": [{"domain": "example.com"}]}
            result = store.write_document(path, payload, "reviews")
            self.assertEqual(result["storage"], "json")
            self.assertTrue(path.exists())
            self.assertFalse(store.manifest_path(path).exists())
            self.assertEqual(store.read_document(path, "reviews"), payload)

    def test_oversized_document_migrates_to_verified_jsonl_shards(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            original = {"schema_version": 1, "reviews": [{"id": i, "payload": "x" * 800} for i in range(8)]}
            path.write_text(json.dumps({"schema_version": 1, "reviews": []}), encoding="utf-8")
            with patch.object(store, "MAX_FILE_BYTES", 4096), patch.object(store, "SHARD_TARGET_BYTES", 2000):
                result = store.write_document(path, original, "reviews")
                self.assertEqual(result["storage"], "jsonl-shards-v1")
                self.assertGreater(result["shards"], 1)
                self.assertFalse(path.exists())
                restored = store.read_document(path, "reviews")
                self.assertEqual(restored, original)
                manifest = json.loads(store.manifest_path(path).read_text(encoding="utf-8"))
                shard_dir = path.parent / manifest["shard_directory"]
                self.assertTrue(shard_dir.is_dir())
                self.assertTrue(all(p.stat().st_size <= 4096 for p in shard_dir.glob("*.jsonl")))

    def test_sharded_document_writes_recheck_logical_lease_at_each_mutation(self):
        import resource_lease_runtime
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path = Path(tmp) / "ledger.json"
            payload = {"reviews": [{"id": i, "payload": "x" * 800} for i in range(8)]}
            checked = []
            with patch.object(store, "MAX_FILE_BYTES", 4096), \
                 patch.object(store, "SHARD_TARGET_BYTES", 2000), \
                 patch.object(resource_lease_runtime, "assert_resource_lease_from_environment",
                              side_effect=lambda key: checked.append(key) or True):
                result = store.write_document(path, payload, "reviews", lease_required=True)
            self.assertEqual(result["storage"], "jsonl-shards-v1")
            expected = path.relative_to(ROOT).as_posix()
            self.assertGreater(len(checked), 5)
            self.assertTrue(all(key == expected for key in checked))
            self.assertEqual(store.read_document(path, "reviews"), payload)

    def test_shard_checksum_failure_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            payload = {"reviews": [{"id": i, "payload": "z" * 900} for i in range(6)]}
            with patch.object(store, "MAX_FILE_BYTES", 4096), patch.object(store, "SHARD_TARGET_BYTES", 1000):
                store.write_document(path, payload, "reviews")
                manifest = json.loads(store.manifest_path(path).read_text(encoding="utf-8"))
                shard = path.parent / manifest["shard_directory"] / manifest["shards"][0]["file"]
                shard.write_bytes(shard.read_bytes() + b"corruption")
                with self.assertRaisesRegex(ValueError, "checksum mismatch"):
                    store.read_document(path, "reviews")

    def test_failed_manifest_swap_keeps_previous_version_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            first = {"reviews": [{"id": i, "payload": "a" * 900} for i in range(6)]}
            second = {"reviews": [{"id": i, "payload": "b" * 900} for i in range(6)]}
            with patch.object(store, "MAX_FILE_BYTES", 4096), patch.object(store, "SHARD_TARGET_BYTES", 1000):
                store.write_document(path, first, "reviews")
                with patch.object(store, "_atomic_write", side_effect=OSError("simulated manifest failure")):
                    with self.assertRaisesRegex(OSError, "simulated"):
                        store.write_document(path, second, "reviews")
                self.assertEqual(store.read_document(path, "reviews"), first)

    def test_iter_document_records_streams_shards_and_matches_read_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            payload = {"schema_version": 1, "reviews": [{"id": i, "payload": "q" * 900} for i in range(7)]}
            with patch.object(store, "MAX_FILE_BYTES", 4096), patch.object(store, "SHARD_TARGET_BYTES", 1200):
                store.write_document(path, payload, "reviews")
                streamed = list(store.iter_document_records(path, "reviews"))
                self.assertEqual(streamed, payload["reviews"])
                self.assertEqual(len(streamed), len(store.read_document(path, "reviews")["reviews"]))

    def test_iter_document_records_reads_legacy_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "ledger.json"
            records = [{"domain": "one.example"}, {"domain": "two.example"}]
            path.write_text(json.dumps({"reviews": records}), encoding="utf-8")
            self.assertEqual(list(store.iter_document_records(path, "reviews")), records)


if __name__ == "__main__":
    unittest.main(verbosity=2)
