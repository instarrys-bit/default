"""Run the existing deterministic V1 ruleset builder in an isolated V2 workspace.

The builder is copied from the checked-out source revision, its resource guard is
replaced with a temp-root-only guard, and all input files are hash-checked after
execution. The user-owned uu.conf is copied read-only and never written back.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_FILES = (
    "modules/uu.conf",
    "automation/production_control.json",
    "sources/domain_sources.json",
    "sources/protected_domains.json",
)
LOGICAL_DOCUMENTS = (
    "sources/domain_reviews.json",
    "sources/source_candidates.json",
    "data/candidates.json",
)
OPTIONAL_FILES = ("reports/source-lineage-audit.json",)
OUTPUT_PATHS = (
    "rulesets/direct.list",
    "rulesets/proxy.list",
    "rulesets/reject.list",
    "rulesets/manifest.json",
    "rulesets/pending_queue.json",
    "rulesets/reject_review_queue.json",
    "reports/reject-secondary-review.md",
)
SHA1_RE = re.compile(r"^[0-9a-f]{40}$")
MAX_OUTPUT_FILE_BYTES = 50 * 1024 * 1024
MAX_OUTPUT_TOTAL_BYTES = 200 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _reject_symlinks(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("symlinks are not allowed in production inputs: " + str(path))
    if path.is_dir():
        for child in path.iterdir():
            _reject_symlinks(child)


def _copy_file(source: Path, target: Path) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError("required production input is missing or unsafe: " + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_logical_document(repo_root: Path, workspace: Path, relative: str) -> None:
    source = repo_root / relative
    target = workspace / relative
    manifest_source = source.with_name(source.name + ".manifest.json")
    has_file = source.is_file()
    has_manifest = manifest_source.is_file()
    if not has_file and not has_manifest:
        raise ValueError("required logical document is missing: " + relative)
    if has_file:
        _copy_file(source, target)
    if has_manifest:
        _copy_file(manifest_source, target.with_name(target.name + ".manifest.json"))
        try:
            manifest = json.loads(manifest_source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("logical document manifest is invalid: " + relative) from exc
        shard_dir = manifest.get("shard_directory") if isinstance(manifest, dict) else None
        if not isinstance(shard_dir, str) or PurePosixPath(shard_dir).name != shard_dir or shard_dir in {"", ".", ".."}:
            raise ValueError("logical document shard directory is unsafe: " + relative)
        shard_source = manifest_source.parent / shard_dir
        if shard_source.exists():
            _reject_symlinks(shard_source)
            if not shard_source.is_dir():
                raise ValueError("logical document shard path is not a directory")
            shutil.copytree(shard_source, target.parent / shard_dir, dirs_exist_ok=True)


def _file_hashes(root: Path, *, exclude: set[str] | None = None) -> dict[str, str]:
    exclude = exclude or set()
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink appeared in sandbox: " + str(path.relative_to(root)))
        if path.is_file():
            relative = path.relative_to(root).as_posix()
            if relative in exclude:
                continue
            result[relative] = sha256(path.read_bytes())
    return result


def _bundle_digest(scripts_dir: Path) -> tuple[str, list[dict]]:
    files = []
    for path in sorted(scripts_dir.rglob("*.py")):
        relative = path.relative_to(scripts_dir).as_posix()
        digest = sha256(path.read_bytes())
        files.append({"path": relative, "sha256": digest, "size_bytes": path.stat().st_size})
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return sha256(encoded), files


def prepare_workspace(repo_root: str | Path, workspace: str | Path) -> dict:
    repo_root = Path(repo_root).resolve()
    workspace = Path(workspace).resolve()
    if workspace == repo_root or repo_root in workspace.parents:
        raise ValueError("sandbox workspace must be outside the repository checkout")
    workspace.mkdir(parents=True, exist_ok=True)
    scripts_source = repo_root / "scripts"
    _reject_symlinks(scripts_source)
    shutil.copytree(scripts_source, workspace / "scripts", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for relative in REQUIRED_FILES:
        _copy_file(repo_root / relative, workspace / relative)
    for relative in LOGICAL_DOCUMENTS:
        _copy_logical_document(repo_root, workspace, relative)
    for relative in OPTIONAL_FILES:
        source = repo_root / relative
        if source.exists():
            _copy_file(source, workspace / relative)
    rulesets_source = repo_root / "rulesets"
    if rulesets_source.exists():
        _reject_symlinks(rulesets_source)
        shutil.copytree(rulesets_source, workspace / "rulesets", dirs_exist_ok=True)
    else:
        (workspace / "rulesets").mkdir(parents=True, exist_ok=True)
    (workspace / "reports").mkdir(parents=True, exist_ok=True)
    readonly_paths = [
        "scripts", *REQUIRED_FILES, *LOGICAL_DOCUMENTS, *OPTIONAL_FILES,
    ]
    readonly_snapshot = {}
    for relative in readonly_paths:
        path = workspace / relative
        if path.is_file():
            readonly_snapshot[relative] = sha256(path.read_bytes())
        elif path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    readonly_snapshot[child.relative_to(workspace).as_posix()] = sha256(child.read_bytes())
        manifest_path = path.with_name(path.name + ".manifest.json")
        if manifest_path.is_file():
            readonly_snapshot[manifest_path.relative_to(workspace).as_posix()] = sha256(manifest_path.read_bytes())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            shard_dir = manifest.get("shard_directory")
            if isinstance(shard_dir, str):
                shard_root = manifest_path.parent / shard_dir
                if shard_root.is_dir():
                    for child in sorted(shard_root.rglob("*")):
                        if child.is_file():
                            readonly_snapshot[child.relative_to(workspace).as_posix()] = sha256(child.read_bytes())
    builder_sha, builder_files = _bundle_digest(workspace / "scripts")
    ruleset_baseline = _file_hashes(workspace / "rulesets")
    return {
        "workspace": workspace,
        "readonly_snapshot": readonly_snapshot,
        "ruleset_baseline_snapshot": ruleset_baseline,
        "builder_bundle_sha256": builder_sha,
        "builder_files": builder_files,
        "uu_conf_sha256": sha256((workspace / "modules/uu.conf").read_bytes()),
    }


def _runner_source() -> str:
    return r'''import importlib.util
import os
import sys
from datetime import datetime as BaseDateTime
from pathlib import Path

workspace = Path(__file__).resolve().parent
scripts = workspace / "scripts"
sys.path.insert(0, str(scripts))

class FixedDateTime(BaseDateTime):
    @classmethod
    def now(cls, tz=None):
        value = BaseDateTime.fromisoformat(os.environ["V2_COMPAT_AS_OF"].replace("Z", "+00:00"))
        return value.astimezone(tz) if tz else value.replace(tzinfo=None)

def sandbox_guard(root, relative):
    root = Path(root).resolve()
    target = (root / relative).resolve()
    if root not in target.parents:
        raise PermissionError("builder attempted a path outside the isolated workspace")
    rel = target.relative_to(root).as_posix()
    if not (rel.startswith("rulesets/") or rel.startswith("reports/")):
        raise PermissionError("builder attempted to write outside rulesets/ and reports/: " + rel)

spec = importlib.util.spec_from_file_location("v2_sandbox_build_rulesets", scripts / "build_rulesets.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.datetime = FixedDateTime
module.assert_resource_lease_for_repository_path = sandbox_guard
module.main()
'''


def run_builder(repo_root: str | Path, *, as_of: str, source_revision: str) -> dict:
    if not SHA1_RE.fullmatch(source_revision):
        raise ValueError("source_revision must be a 40-character Git commit SHA")
    fixed = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
    if fixed.tzinfo is None or fixed.utcoffset() is None:
        raise ValueError("as_of must include a timezone")
    with tempfile.TemporaryDirectory(prefix="v2-ruleset-builder-") as temporary:
        workspace = Path(temporary).resolve()
        prepared = prepare_workspace(repo_root, workspace)
        runner = workspace / ".v2_compat_runner.py"
        runner.write_text(_runner_source(), encoding="utf-8")
        before = _file_hashes(workspace, exclude={".v2_compat_runner.py"})
        env = os.environ.copy()
        env["PYTHONPATH"] = str(workspace / "scripts")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["V2_COMPAT_AS_OF"] = fixed.isoformat()
        completed = subprocess.run(
            [sys.executable, str(runner)],
            cwd=workspace,
            env=env,
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        runner.unlink(missing_ok=True)
        if completed.returncode != 0:
            raise RuntimeError("isolated V1 ruleset builder failed: " + completed.stderr[-5000:])
        after = _file_hashes(workspace)
        allowed = set(OUTPUT_PATHS)
        changed = {
            path for path in set(before) | set(after)
            if before.get(path) != after.get(path)
        }
        unexpected = sorted(changed - allowed)
        if unexpected:
            raise PermissionError("builder changed files outside its output allowlist: " + ", ".join(unexpected[:20]))
        for relative, digest in prepared["readonly_snapshot"].items():
            path = workspace / relative
            if not path.is_file() or sha256(path.read_bytes()) != digest:
                raise PermissionError("read-only production input changed in sandbox: " + relative)
        if sha256((workspace / "modules/uu.conf").read_bytes()) != prepared["uu_conf_sha256"]:
            raise PermissionError("uu.conf changed inside the isolated builder workspace")
        outputs = []
        total = 0
        for relative in OUTPUT_PATHS:
            path = workspace / relative
            if not path.is_file():
                raise ValueError("builder did not produce required output: " + relative)
            content = path.read_bytes()
            if len(content) > MAX_OUTPUT_FILE_BYTES:
                raise ValueError("builder output exceeds 50 MiB: " + relative)
            total += len(content)
            outputs.append({
                "path": relative,
                "content": content,
                "sha256": sha256(content),
                "size_bytes": len(content),
            })
        if total > MAX_OUTPUT_TOTAL_BYTES:
            raise ValueError("combined builder outputs exceed 200 MiB")
        return {
            "schema_version": 1,
            "candidate_status": "VALIDATED_NOT_PUBLISHED",
            "source_revision": source_revision,
            "as_of": fixed.isoformat(),
            "builder_entrypoint": "scripts/build_rulesets.py",
            "builder_bundle_sha256": prepared["builder_bundle_sha256"],
            "builder_files": prepared["builder_files"],
            "input_snapshot": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(prepared["readonly_snapshot"].items())
            ],
            "ruleset_baseline_snapshot": [
                {"path": path, "sha256": digest}
                for path, digest in sorted(prepared["ruleset_baseline_snapshot"].items())
            ],
            "uu_conf_sha256": prepared["uu_conf_sha256"],
            "uu_conf_modified": False,
            "output_files": outputs,
            "output_file_count": len(outputs),
            "output_total_bytes": total,
            "builder_stdout_summary": completed.stdout[-2000:],
            "publication_status": "NOT_PUBLISHED",
            "activation_count": 0,
        }


def stage_candidate(candidate: dict, store, *, task_id: str, lease_guard) -> dict:
    if not task_id or not task_id.startswith("task_"):
        raise ValueError("task_id must be a canonical V2 task ID")
    staged = []
    lease_proof = None
    for item in candidate["output_files"]:
        lease_proof = lease_guard()
        artifact = store.stage(
            item["content"],
            artifact_type="ruleset_candidate_file",
            provenance={
                "source_id": "v1-builder-compat:" + item["path"],
                "source_revision": candidate["source_revision"],
                "task_id": task_id,
                "producer": "v2-production-compat/1",
            },
            schema_version=1,
            producer_version="v2-production-compat/1",
        )
        staged.append({
            "path": item["path"],
            "artifact_id": artifact["artifact_id"],
            "record_id": artifact["record_id"],
            "content_sha256": artifact["content_sha256"],
            "size_bytes": artifact["size_bytes"],
        })
    lease_proof = lease_guard()
    manifest = {
        key: value for key, value in candidate.items()
        if key not in {"output_files", "builder_stdout_summary"}
    }
    manifest["output_files"] = staged
    manifest["task_id"] = task_id
    manifest["storage_lease_proof"] = lease_proof
    encoded = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    artifact = store.stage(
        encoded,
        artifact_type="production_candidate",
        provenance={
            "source_id": "production-candidate:" + task_id,
            "source_revision": candidate["source_revision"],
            "task_id": task_id,
            "producer": "v2-production-compat/1",
        },
        schema_version=1,
        producer_version="v2-production-compat/1",
    )
    return {
        "candidate_artifact_id": artifact["artifact_id"],
        "candidate_record_id": artifact["record_id"],
        "output_file_count": len(staged),
        "output_total_bytes": candidate["output_total_bytes"],
        "publication_status": "NOT_PUBLISHED",
        "activation_count": 0,
        "staged_outputs": staged,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=str(ROOT))
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--source-revision", default=os.environ.get("GITHUB_SHA"))
    parser.add_argument("--task-id", default=os.environ.get("V2_PRODUCTION_TASK_ID"))
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--branch", default="main")
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.source_revision:
        raise SystemExit("source revision is required")
    candidate = run_builder(args.repo_root, as_of=args.as_of, source_revision=args.source_revision)
    if not args.execute:
        print(json.dumps({
            "valid": True,
            "dry_run": True,
            "candidate_status": candidate["candidate_status"],
            "source_revision": candidate["source_revision"],
            "builder_bundle_sha256": candidate["builder_bundle_sha256"],
            "output_file_count": candidate["output_file_count"],
            "output_total_bytes": candidate["output_total_bytes"],
            "uu_conf_sha256": candidate["uu_conf_sha256"],
            "uu_conf_modified": False,
            "publication_status": "NOT_PUBLISHED",
            "activation_count": 0,
        }, ensure_ascii=False, sort_keys=True))
        return 0
    token = os.environ.get("STORAGE_MANAGEMENT_TOKEN")
    epoch_id = os.environ.get("V2_STORAGE_EPOCH_ID")
    if not token or not epoch_id or not args.repository or not args.task_id:
        raise SystemExit("--execute requires Storage Management token, V2 epoch, repository and task ID")
    from runtime import (
        GitHubContentsBackend, project, validate_active_storage_write_context,
    )
    backend = GitHubContentsBackend(args.repository, args.branch, token)
    state, _ = backend.read()
    if state is None or state.get("epoch_id") != epoch_id:
        raise SystemExit("V2 storage epoch is not initialized or does not match the approved epoch ID")
    project(state)
    def lease_guard():
        current_state, _ = backend.read()
        if current_state is None or current_state.get("epoch_id") != epoch_id:
            raise RuntimeError("V2 storage epoch changed during artifact staging")
        return validate_active_storage_write_context(
            current_state,
            task_id=args.task_id,
            resource_key="storage/v2/artifacts",
            observed_at=datetime.now(timezone.utc).isoformat(),
        )
    from artifact_store import GitHubContentsArtifactStore
    store = GitHubContentsArtifactStore(args.repository, args.branch, token)
    result = stage_candidate(candidate, store, task_id=args.task_id, lease_guard=lease_guard)
    print(json.dumps({"valid": True, "dry_run": False, **result}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
