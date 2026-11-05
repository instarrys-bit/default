import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from production_intent import classify_paths, compute_fingerprint, compute_output_fingerprint, decide, load_manifest, register_unclassified_paths, merge_request_observations, active_production_fingerprints, UNFINGERPRINTED_ACTIVE_PRODUCTION


class ProductionIntentTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        (self.root / "automation").mkdir()
        self.manifest_path = self.root / "automation" / "production_inputs.json"
        self.manifest_path.write_text(json.dumps({
            "schema_version": 1,
            "production_input_paths": ["sources/policy.json", "modules/uu.conf"],
            "non_production_path_patterns": ["reports/**", "rulesets/**", "automation/**", "tests/**"],
            "monitoring_path_patterns": ["dashboard/**", ".github/workflows/dashboard-pages.yml", "scripts/build_dashboard_snapshot.py"],
            "documentation_path_patterns": ["docs/**", "dashboard/README.md"]
        }), encoding="utf-8")
        (self.root / "sources").mkdir()
        (self.root / "sources" / "policy.json").write_text('{"policy":1}', encoding="utf-8")
        (self.root / "modules").mkdir()
        (self.root / "modules" / "uu.conf").write_text("[General]", encoding="utf-8")
        self.manifest = load_manifest(self.manifest_path)
        self.now = datetime(2026, 11, 3, tzinfo=timezone.utc)
        self.fp = compute_fingerprint(self.root, self.manifest)
        (self.root / "rulesets").mkdir()
        for name, body in (("direct.list", "DIRECT\\n"), ("proxy.list", "PROXY\\n"), ("reject.list", "REJECT\\n")):
            (self.root / "rulesets" / name).write_text(body, encoding="utf-8")

    def test_input_change_is_classified_as_production_input(self):
        result = classify_paths(["sources/policy.json"], self.manifest)
        self.assertEqual(result["status"], "INPUT_CHANGED")

    def test_generated_outputs_do_not_create_production_demand(self):
        result = classify_paths(["reports/status.json", "rulesets/direct.list", "automation/task_queue.json"], self.manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")

    def test_monitoring_paths_are_classified_without_production_demand(self):
        result = classify_paths(["dashboard/index.html", "scripts/build_dashboard_snapshot.py"], self.manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertEqual(result["monitoring_changes"], ["dashboard/index.html", "scripts/build_dashboard_snapshot.py"])
        self.assertEqual(result["unknown_changes"], [])
    def test_documentation_paths_are_classified_without_production_demand(self):
        result = classify_paths(["dashboard/README.md"], self.manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertEqual(result["documentation_changes"], ["dashboard/README.md"])

    def test_unknown_paths_require_review_instead_of_triggering_production(self):
        result = classify_paths(["new/unregistered.py"], self.manifest)
        self.assertEqual(result["status"], "REVIEW_REQUIRED")

    def test_read_only_user_config_is_a_production_input(self):
        self.assertIn("modules/uu.conf", self.manifest["production_input_paths"])
        result = classify_paths(["modules/uu.conf"], self.manifest)
        self.assertEqual(result["status"], "INPUT_CHANGED")

    def test_repository_manifest_classifies_owner_config_as_production_input(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        result = classify_paths(["modules/uu.conf"], manifest)
        self.assertEqual(result["status"], "INPUT_CHANGED")
        self.assertEqual(result["production_input_changes"], ["modules/uu.conf"])

    def test_repository_manifest_classifies_removed_historical_config_candidates_as_non_production(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            "candidates/ss.conf.oiu-fusion-candidate",
            "candidates/ss.conf.oiu-merged",
        ]
        result = classify_paths(paths, manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertCountEqual(result["non_production_changes"], paths)
        self.assertEqual(result["unknown_changes"], [])
        ledger = json.loads((ROOT / "automation" / "unregistered_path_registry.json").read_text(encoding="utf-8"))
        entries = {item["path"]: item for item in ledger["entries"]}
        for path in paths:
            self.assertEqual(entries[path]["status"], "CLASSIFIED_DOCUMENTATION")
            self.assertTrue(entries[path]["classification_reason"])
            self.assertTrue(entries[path]["classification_basis"])

    def test_repository_manifest_classifies_governance_metadata_as_non_production(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            "automation/release_manifest.json",
            "automation/production_workflow_map.json",
            "automation/resource_write_sets.json",
            "automation/capability_contract_inventory.json",
            "automation/resource_ownership_audit.json",
        ]
        for path in paths:
            with self.subTest(path=path):
                result = classify_paths([path], manifest)
                self.assertEqual(result["status"], "NO_INPUT_CHANGE")
                self.assertEqual(result["non_production_changes"], [path])

    def test_completion_and_workflow_run_events_never_create_demand(self):
        for event in ("repository_dispatch", "workflow_run"):
            result = decide(event=event, current_fingerprint=self.fp,
                last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
                last_success_at=None, now=self.now)
            self.assertFalse(result["should_produce"])
            self.assertEqual(result["decision"], "OBSERVE_ONLY")

    def test_same_fingerprint_active_task_suppresses_duplicate(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, active_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["decision"], "IN_PROGRESS")
        self.assertFalse(result["should_produce"])

    def test_same_successful_fingerprint_is_satisfied(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["decision"], "ALREADY_SATISFIED")

    def test_schedule_is_due_only_after_explicit_refresh_interval(self):
        due = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=(self.now - timedelta(days=9)).isoformat(), now=self.now)
        not_due = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=(self.now - timedelta(days=2)).isoformat(), now=self.now)
        self.assertEqual(due["decision"], "SCHEDULE_DUE")
        self.assertTrue(due["should_produce"])
        self.assertEqual(not_due["decision"], "ALREADY_SATISFIED")

    def test_unknown_path_blocks_production_even_when_fingerprint_differs(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"REVIEW_REQUIRED"},
            last_success_at=None, now=self.now)
        self.assertEqual(result["decision"], "REVIEW_REQUIRED")
        self.assertFalse(result["should_produce"])

    def test_input_change_uses_stable_fingerprint_idempotency_key(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, revision="commit-a", now=self.now)
        self.assertEqual(result["idempotency_key"], f"production:input:{self.fp}:commit-a")

    def test_scheduled_refresh_key_is_scoped_to_last_success_generation(self):
        stamp = (self.now - timedelta(days=9)).isoformat()
        result = decide(event="schedule", current_fingerprint=self.fp,
            last_success_fingerprint=self.fp, path_classification={"status":"NO_INPUT_CHANGE"},
            last_success_at=stamp, successful_fingerprints={self.fp}, now=self.now)
        self.assertEqual(result["idempotency_key"], f"production:schedule:{self.fp}:{stamp}")

    def test_reverted_to_previously_successful_fingerprint_rebuilds_on_input_change(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="different", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp},
            revision="commit-a", now=self.now)
        self.assertEqual(result["decision"], "INPUT_CHANGED")
        self.assertTrue(result["should_produce"])
        self.assertEqual(result["idempotency_key"], f"production:input:{self.fp}:commit-a")

    def test_config_a_to_b_to_a_reconciles_even_when_a_was_previously_successful(self):
        config = self.root / "modules" / "uu.conf"
        config.write_text("[Rule]\\nDOMAIN,alpha.example,DIRECT\\n", encoding="utf-8")
        fingerprint_a = compute_fingerprint(self.root, self.manifest)
        config.write_text("[Rule]\\nDOMAIN,beta.example,PROXY\\n", encoding="utf-8")
        fingerprint_b = compute_fingerprint(self.root, self.manifest)
        self.assertNotEqual(fingerprint_a, fingerprint_b)

        # Revert to A after B was the last successful generation.
        config.write_text("[Rule]\\nDOMAIN,alpha.example,DIRECT\\n", encoding="utf-8")
        fingerprint_reverted = compute_fingerprint(self.root, self.manifest)
        self.assertEqual(fingerprint_reverted, fingerprint_a)
        classification = classify_paths(["modules/uu.conf"], self.manifest)
        result = decide(
            event="push", current_fingerprint=fingerprint_reverted,
            last_success_fingerprint=fingerprint_b,
            path_classification=classification, last_success_at=self.now.isoformat(),
            successful_fingerprints={fingerprint_a, fingerprint_b},
            revision="revert-commit", now=self.now,
        )
        self.assertEqual(result["decision"], "INPUT_CHANGED")
        self.assertTrue(result["should_produce"])
        self.assertEqual(
            result["idempotency_key"],
            f"production:input:{fingerprint_a}:revert-commit",
        )

    def test_same_revert_revision_is_idempotent_but_later_revert_is_new_work(self):
        args = dict(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="different", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=self.now.isoformat(), successful_fingerprints={self.fp}, now=self.now)
        first = decide(**args, revision="commit-a")
        replay = decide(**args, revision="commit-a")
        later = decide(**args, revision="commit-b")
        self.assertEqual(first["idempotency_key"], replay["idempotency_key"])
        self.assertNotEqual(first["idempotency_key"], later["idempotency_key"])

    def test_output_fingerprint_covers_all_three_policy_rule_sets(self):
        first = compute_output_fingerprint(self.root)
        (self.root / "rulesets" / "direct.list").write_text("DIRECT\\nexample.com\\n", encoding="utf-8")
        second = compute_output_fingerprint(self.root)
        self.assertNotEqual(first, second)

    def test_manifest_rejects_paths_classified_as_both_input_and_output(self):
        path = self.root / "automation" / "overlap.json"
        path.write_text(json.dumps({
            "schema_version": 1,
            "production_input_paths": ["reports/important.json"],
            "non_production_path_patterns": ["reports/**"],
            "monitoring_path_patterns": ["dashboard/**"],
            "documentation_path_patterns": []
        }), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "also match"):
            load_manifest(path)

    def test_different_active_fingerprint_blocks_a_second_production_task(self):
        result = decide(event="push", current_fingerprint=self.fp,
            last_success_fingerprint="old", path_classification={"status":"INPUT_CHANGED"},
            last_success_at=None, active_fingerprints={"older-active-fingerprint"}, now=self.now)
        self.assertEqual(result["decision"], "WAIT_FOR_ACTIVE")
        self.assertFalse(result["should_produce"])


    def test_adblock_assets_are_explicitly_non_production_inputs(self):
        manifest = load_manifest(ROOT / "automation" / "production_inputs.json")
        paths = [
            "modules/AdBlock.sgmodule",
            "modules/adblock/dev/Clean_Pro.js",
            "modules/adblock/scripts/Clean_Pro.js",
            "modules/adblock/scripts/Social_Adblock.js",
            "modules/adblock/scripts/youtube_initplayback_observer.js",
            "modules/adblock/backups/Clean_Pro.pre-rollback-20261105.js",
            "modules/adblock/scripts/AdBlock_Original.sgmodule",
            "modules/adblock/scripts/Clean_Pro_Request.js",
            "modules/adblock/scripts/youtube_protobuf_response_filter.js",
            "modules/temp-test/Sr_Youtube_Clean.js",
        ]
        result = classify_paths(paths, manifest)
        self.assertEqual(result["status"], "NO_INPUT_CHANGE")
        self.assertCountEqual(result["non_production_changes"], paths)
        self.assertEqual(result["unknown_changes"], [])
        self.assertIn("modules/uu.conf", manifest["production_input_paths"])
        ledger = json.loads((ROOT / "automation" / "unregistered_path_registry.json").read_text(encoding="utf-8"))
        entries = {item["path"]: item for item in ledger["entries"]}
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(entries[path]["status"], "NON_PRODUCTION")
                self.assertTrue(entries[path].get("classification_reason"))
                self.assertTrue(entries[path].get("classification_basis"))



    def test_owner_baseline_bookkeeping_does_not_change_fingerprint(self):
        policy_path = self.root / "sources" / "policy.json"
        policy_path.write_text(json.dumps({
            "policy_revision": 1,
            "dns_invariants": {"direct": "resolver-a"},
            "managed_config_guard": {
                "path": "modules/uu.conf",
                "approved_git_blob_sha": "a" * 40,
                "immutable": True,
                "last_user_approved_baseline_update": {
                    "previous_blob_sha": "b" * 40,
                    "new_blob_sha": "a" * 40,
                    "registered_at": "2026-11-04T00:00:00Z",
                },
            },
        }), encoding="utf-8")
        baseline = compute_fingerprint(self.root, self.manifest)

        policy = json.loads(policy_path.read_text(encoding="utf-8"))
        policy["managed_config_guard"]["approved_git_blob_sha"] = "c" * 40
        policy["managed_config_guard"]["last_user_approved_baseline_update"] = {
            "previous_blob_sha": "a" * 40,
            "new_blob_sha": "c" * 40,
            "registered_at": "2026-11-05T00:00:00Z",
        }
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertEqual(compute_fingerprint(self.root, self.manifest), baseline)

        policy["dns_invariants"]["direct"] = "resolver-b"
        policy_path.write_text(json.dumps(policy), encoding="utf-8")
        self.assertNotEqual(compute_fingerprint(self.root, self.manifest), baseline)


    def test_watchdog_registry_registration_is_idempotent_across_interleaved_cas_retries(self):
        ledger = {"schema_version": 1, "entries": []}
        first = register_unclassified_paths(
            ["new/path.py"], ledger, "push", "sha-a", "run-a", "https://example/run-a",
            now="2026-11-04T00:00:00Z",
        )
        self.assertEqual(first["entries"][0]["seen_count"], 1)

        second = register_unclassified_paths(
            ["new/path.py"], first, "push", "sha-b", "run-b", "https://example/run-b",
            now="2026-11-04T00:00:01Z",
        )
        self.assertEqual(second["entries"][0]["seen_count"], 2)

        # Simulate run A losing its first CAS update, then retrying after run B
        # has successfully published. The replay must not count run A twice.
        replay = register_unclassified_paths(
            ["new/path.py"], second, "push", "sha-a", "run-a", "https://example/run-a",
            now="2026-11-04T00:00:02Z",
        )
        entry = replay["entries"][0]
        self.assertEqual(entry["seen_count"], 2)
        self.assertEqual(entry["observed_run_ids"], ["run-a", "run-b"])
        self.assertEqual(entry["last_seen_run_id"], "run-a")

    def test_watchdog_registry_registration_preserves_concurrent_distinct_paths(self):
        ledger = {"schema_version": 1, "entries": []}
        left = register_unclassified_paths(
            ["alpha/path.py"], ledger, "push", "sha-a", "run-a", "https://example/run-a",
            now="2026-11-04T00:00:00Z",
        )
        merged = register_unclassified_paths(
            ["beta/path.py"], left, "push", "sha-b", "run-b", "https://example/run-b",
            now="2026-11-04T00:00:01Z",
        )
        self.assertEqual([item["path"] for item in merged["entries"]], ["alpha/path.py", "beta/path.py"])
        self.assertEqual([item["seen_count"] for item in merged["entries"]], [1, 1])


    def test_request_observation_merge_is_idempotent_by_run_and_preserves_counts(self):
        empty = {"schema_version": 1, "observations": []}
        first = merge_request_observations(
            ["shared.example", "shared.example", "alpha.example"], empty, "run-a",
            now="2026-11-04T00:00:00Z",
        )
        self.assertEqual(
            next(item for item in first["observations"] if item["domain"] == "shared.example")["observations"],
            2,
        )
        second = merge_request_observations(
            ["shared.example", "beta.example"], first, "run-b",
            now="2026-11-04T00:00:01Z",
        )
        replay = merge_request_observations(
            ["shared.example", "shared.example", "alpha.example"], second, "run-a",
            now="2026-11-04T00:00:02Z",
        )
        shared = next(item for item in replay["observations"] if item["domain"] == "shared.example")
        self.assertEqual(shared["observations"], 3)
        self.assertEqual(shared["observed_run_ids"], ["run-a", "run-b"])
        self.assertEqual(
            [item["domain"] for item in replay["observations"]],
            ["alpha.example", "beta.example", "shared.example"],
        )

    def test_request_observation_merge_rejects_invalid_hosts_and_schema(self):
        with self.assertRaisesRegex(ValueError, "invalid hostname"):
            merge_request_observations(["https://bad.example/path"], {"schema_version": 1, "observations": []}, "run-x")
        with self.assertRaisesRegex(ValueError, "unsupported observation ledger schema"):
            merge_request_observations(["good.example"], {"schema_version": 2, "observations": []}, "run-x")

    def test_two_runner_git_ref_cas_retry_replays_batch_without_losing_observations(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bare = root / "remote.git"
            seed = root / "seed"
            runner_a = root / "runner-a"
            runner_b = root / "runner-b"

            def git(cwd, *args, check=True):
                return subprocess.run(
                    ["git", *args], cwd=cwd, check=check,
                    capture_output=True, text=True,
                )

            git(root, "init", "--bare", "--initial-branch=main", str(bare))
            git(root, "init", "--initial-branch=main", str(seed))
            git(seed, "config", "user.name", "test")
            git(seed, "config", "user.email", "test@example.invalid")
            ledger_path = seed / "sources" / "request_domain_observations.json"
            ledger_path.parent.mkdir(parents=True)
            ledger_path.write_text(json.dumps({"schema_version": 1, "observations": []}), encoding="utf-8")
            git(seed, "add", "sources/request_domain_observations.json")
            git(seed, "commit", "-m", "initial observation ledger")
            git(seed, "remote", "add", "origin", str(bare))
            git(seed, "push", "-u", "origin", "main")

            git(root, "clone", str(bare), str(runner_a))
            git(root, "clone", str(bare), str(runner_b))
            for runner in (runner_a, runner_b):
                git(runner, "config", "user.name", "intake-bot")
                git(runner, "config", "user.email", "intake@example.invalid")

            batches = {
                runner_a: (["alpha.example", "shared.example"], "run-a"),
                runner_b: (["beta.example", "shared.example"], "run-b"),
            }
            for runner, (domains, run_id) in batches.items():
                git(runner, "fetch", "origin", "main")
                git(runner, "reset", "--hard", "origin/main")
                path = runner / "sources" / "request_domain_observations.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                merged = merge_request_observations(domains, payload, run_id, now="2026-11-04T00:00:00Z")
                path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                git(runner, "add", "sources/request_domain_observations.json")
                git(runner, "commit", "-m", "intake " + run_id)

            git(runner_a, "push", "origin", "HEAD:main")
            first_b_push = git(runner_b, "push", "origin", "HEAD:main", check=False)
            self.assertNotEqual(first_b_push.returncode, 0, "stale runner must not overwrite the advanced main ref")

            # Workflow retry: re-read main, discard only the stale runner workspace
            # commit, then reapply the immutable submitted batch with the same run ID.
            git(runner_b, "fetch", "origin", "main")
            git(runner_b, "reset", "--hard", "origin/main")
            path_b = runner_b / "sources" / "request_domain_observations.json"
            latest = json.loads(path_b.read_text(encoding="utf-8"))
            merged_b = merge_request_observations(
                batches[runner_b][0], latest, batches[runner_b][1], now="2026-11-04T00:00:01Z"
            )
            path_b.write_text(json.dumps(merged_b, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            git(runner_b, "add", "sources/request_domain_observations.json")
            git(runner_b, "commit", "-m", "retry intake run-b against latest main")
            git(runner_b, "push", "origin", "HEAD:main")

            final_raw = git(root, "--git-dir", str(bare), "show", "main:sources/request_domain_observations.json").stdout
            final = json.loads(final_raw)
            rows = {item["domain"]: item for item in final["observations"]}
            self.assertEqual(set(rows), {"alpha.example", "beta.example", "shared.example"})
            self.assertEqual(rows["shared.example"]["observations"], 2)
            self.assertEqual(rows["shared.example"]["observed_run_ids"], ["run-a", "run-b"])

    def test_stale_queued_production_task_does_not_block_current_input(self):
        old = "a" * 64
        queue = {"tasks": [
            {"target_program_id": "workflow_auto_sync", "status": "QUEUED", "input": {"production_fingerprint": old}},
            {"target_program_id": "workflow_auto_sync", "status": "QUEUED", "input": {"production_fingerprint": old}, "dispatch_intent": {"correlation_id": "persisted"}},
            {"target_program_id": "workflow_auto_sync", "status": "QUEUED", "input": {"production_fingerprint": self.fp}},
            {"target_program_id": "workflow_auto_sync", "status": "CLAIMED", "input": {"production_fingerprint": old}},
            {"target_program_id": "workflow_auto_sync", "status": "VERIFYING", "input": {}},
            {"target_program_id": "workflow_source_discovery", "status": "CLAIMED", "input": {"production_fingerprint": "b" * 64}},
        ]}
        self.assertEqual(
            active_production_fingerprints(queue, self.fp),
            sorted([self.fp, old, UNFINGERPRINTED_ACTIVE_PRODUCTION]),
        )

    def test_stale_queued_production_task_with_missing_fingerprint_does_not_block_replacement(self):
        queue = {"tasks": [
            {"target_program_id": "workflow_auto_sync", "status": "QUEUED", "input": {}},
        ]}
        self.assertEqual(active_production_fingerprints(queue, self.fp), [])

    def test_active_fingerprint_reader_rejects_invalid_queue_or_current_digest(self):
        with self.assertRaisesRegex(ValueError, "tasks array"):
            active_production_fingerprints({}, self.fp)
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            active_production_fingerprints({"tasks": []}, "not-a-digest")

if __name__ == "__main__":
    unittest.main()
