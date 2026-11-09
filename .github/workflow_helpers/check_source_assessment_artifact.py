#!/usr/bin/env python3
"""Find and verify the immutable Assessment artifact for an exact Discovery predecessor."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import urllib.request
import zipfile
from pathlib import PurePosixPath

API_ROOT = "https://api.github.com"
ASSESSMENT_ARTIFACT_NAME = "source-assessment-output"
ASSESSMENT_WORKFLOW_PATH = ".github/workflows/automation-watchdog.yml"
EXPECTED_FILES = {
    "data/source_assessments_runtime.json",
    "sources/source_assessments.json",
    "reports/source-assessment.md",
}


def _headers(token: str) -> dict:
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "Shadowrocket-Assessment-Artifact-Verifier/1.0",
    }


def _get_bytes(url: str, token: str) -> bytes:
    request = urllib.request.Request(url, headers=_headers(token))
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _get_json(url: str, token: str) -> dict:
    payload = json.loads(_get_bytes(url, token).decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("GitHub API returned a non-object response")
    return payload


def _proof_from_archive(archive_bytes: bytes) -> tuple[str, dict]:
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            names = [name for name in archive.namelist() if name.endswith("source-assessment-proof.json")]
            if len(names) != 1:
                raise ValueError("Assessment artifact must contain exactly one source-assessment-proof.json")
            proof_name = names[0]
            proof = json.loads(archive.read(proof_name).decode("utf-8"))
    except (zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"Assessment artifact proof is unreadable: {exc}") from exc
    if not isinstance(proof, dict):
        raise ValueError("Assessment artifact proof must be a JSON object")
    return proof_name, proof


def verify_assessment_archive(
    archive_bytes: bytes,
    artifact: dict,
    producer_run: dict,
    expected: dict,
) -> dict:
    """Verify archive digest, producer identity, predecessor identity, files, and non-activation."""
    if artifact.get("name") != ASSESSMENT_ARTIFACT_NAME or artifact.get("expired") is not False:
        raise ValueError("Artifact is not the unexpired source-assessment-output artifact")
    artifact_run = artifact.get("workflow_run") or {}
    artifact_run_id = str(artifact_run.get("id", ""))
    producer_run_id = str(producer_run.get("id", ""))
    if not artifact_run_id or artifact_run_id != producer_run_id:
        raise ValueError("Assessment artifact does not belong to its declared producer workflow run")
    if producer_run.get("path") != ASSESSMENT_WORKFLOW_PATH:
        raise ValueError("Assessment artifact producer workflow path is incorrect")
    if producer_run.get("head_branch") != "main" or producer_run.get("status") != "completed" or producer_run.get("conclusion") != "success":
        raise ValueError("Assessment artifact producer run is not a successful completed main-branch Watchdog run")
    if artifact_run.get("head_sha") != producer_run.get("head_sha"):
        raise ValueError("Assessment artifact run head SHA does not match producer run metadata")
    if artifact_run.get("head_branch") != producer_run.get("head_branch"):
        raise ValueError("Assessment artifact run branch does not match producer run metadata")
    digest = artifact.get("digest")
    actual_zip_digest = hashlib.sha256(archive_bytes).hexdigest()
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError("GitHub artifact metadata is missing a valid ZIP SHA-256 digest")
    if digest[7:] != actual_zip_digest:
        raise ValueError("Downloaded Assessment artifact ZIP SHA-256 does not match GitHub artifact metadata")

    proof_name, proof = _proof_from_archive(archive_bytes)
    predecessor = proof.get("predecessor")
    expected_predecessor = {
        "program_id": "script_discover_sources",
        "workflow_name": "Shadowrocket Source Discovery (Watchdog)",
        "workflow_run_id": str(expected["workflow_run_id"]),
        "workflow_head_sha": expected["workflow_head_sha"],
        "artifact_path": "sources/discovered_sources.json",
        "artifact_sha256": expected["artifact_sha256"],
    }
    if predecessor != expected_predecessor:
        raise ValueError("Assessment proof does not reference the exact verified Discovery predecessor")
    if proof.get("task_status") != "SUCCEEDED" or proof.get("verification_status") != "passed":
        raise ValueError("Assessment proof does not establish independently verified task success")
    artifact_verification = proof.get("artifact_verification")
    if not isinstance(artifact_verification, dict) or artifact_verification.get("valid") is not True or artifact_verification.get("activation_count") != 0:
        raise ValueError("Assessment proof is invalid or records source activation")
    if proof.get("producer_workflow_path") != ASSESSMENT_WORKFLOW_PATH:
        raise ValueError("Assessment proof producer workflow path is incorrect")
    if str(proof.get("producer_workflow_run_id", "")) != producer_run_id:
        raise ValueError("Assessment proof producer run ID does not match the Artifact owner run")
    if proof.get("producer_workflow_head_sha") != producer_run.get("head_sha"):
        raise ValueError("Assessment proof producer head SHA does not match the Artifact owner run")

    files = proof.get("files")
    if not isinstance(files, list) or not files:
        raise ValueError("Assessment proof file manifest is empty")
    paths = [item.get("path") for item in files if isinstance(item, dict)]
    if len(paths) != len(files) or set(paths) != EXPECTED_FILES or len(paths) != len(EXPECTED_FILES):
        raise ValueError("Assessment artifact does not contain the three expected output documents")
    if paths != sorted(paths):
        raise ValueError("Assessment proof file manifest is not in canonical path order")

    prefix = PurePosixPath(proof_name).parent
    expected_members = {proof_name}
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
            archive_members = {name for name in archive.namelist() if not name.endswith("/")}
            for item in files:
                relative = item["path"]
                expected_members.add((prefix / relative).as_posix() if str(prefix) != "." else relative)
                if not isinstance(item.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
                    raise ValueError(f"Assessment proof has an invalid SHA-256 for {relative}")
                member = (prefix / relative).as_posix() if str(prefix) != "." else relative
                content = archive.read(member)
                if hashlib.sha256(content).hexdigest() != item["sha256"]:
                    raise ValueError(f"Assessment output SHA-256 mismatch for {relative}")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"Assessment output file is missing from its ZIP: {exc}") from exc
    if archive_members != expected_members:
        raise ValueError("Assessment artifact contains unexpected or missing files")

    manifest_sha = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if proof.get("artifact_sha256") != manifest_sha:
        raise ValueError("Assessment proof manifest SHA-256 is inconsistent")
    return {
        "artifact_id": artifact.get("id"),
        "producer_workflow_run_id": producer_run_id,
        "producer_workflow_head_sha": producer_run.get("head_sha"),
        "artifact_sha256": manifest_sha,
    }


def find_matching_assessment_artifact(repository: str, token: str, expected: dict) -> dict:
    matches = []
    page = 1
    while page <= 100:
        listing = _get_json(
            f"{API_ROOT}/repos/{repository}/actions/artifacts?per_page=100&page={page}",
            token,
        )
        artifacts = listing.get("artifacts", [])
        if not isinstance(artifacts, list):
            raise ValueError("GitHub artifact listing is malformed")
        for artifact in artifacts:
            if artifact.get("name") != ASSESSMENT_ARTIFACT_NAME or artifact.get("expired") is not False:
                continue
            workflow_run = artifact.get("workflow_run") or {}
            producer_run_id = workflow_run.get("id")
            if not isinstance(producer_run_id, int) or isinstance(producer_run_id, bool):
                continue
            # The archive is private and expensive to download. Reject non-main,
            # failed, incomplete, or wrong-workflow producers from artifact metadata
            # and the authenticated run record before following the ZIP redirect.
            if workflow_run.get("head_branch") != "main":
                continue
            producer_run = _get_json(
                f"{API_ROOT}/repos/{repository}/actions/runs/{producer_run_id}",
                token,
            )
            if (
                str(producer_run.get("id", "")) != str(producer_run_id)
                or producer_run.get("path") != ASSESSMENT_WORKFLOW_PATH
                or producer_run.get("head_branch") != "main"
                or producer_run.get("status") != "completed"
                or producer_run.get("conclusion") != "success"
                or workflow_run.get("head_sha") != producer_run.get("head_sha")
                or workflow_run.get("head_branch") != producer_run.get("head_branch")
            ):
                continue
            archive_bytes = _get_bytes(
                f"{API_ROOT}/repos/{repository}/actions/artifacts/{artifact['id']}/zip",
                token,
            )
            try:
                proof_name, proof = _proof_from_archive(archive_bytes)
            except ValueError:
                # Historical artifacts without a usable proof are not evidence.
                continue
            predecessor = proof.get("predecessor") or {}
            if str(predecessor.get("workflow_run_id", "")) != str(expected["workflow_run_id"]):
                continue
            verified = verify_assessment_archive(archive_bytes, artifact, producer_run, expected)
            matches.append(verified)
        if len(artifacts) < 100:
            break
        page += 1
    if page > 100:
        raise ValueError("GitHub artifact history exceeded the bounded 10,000-artifact verification window")
    if len(matches) > 1:
        raise ValueError("More than one valid Assessment artifact references the same Discovery predecessor")
    if not matches:
        return {"found": False, "artifact_id": None}
    return {"found": True, **matches[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--workflow-run-id", required=True)
    parser.add_argument("--workflow-head-sha", required=True)
    parser.add_argument("--artifact-sha256", required=True)
    args = parser.parse_args()
    if not args.workflow_run_id.isdigit() or not re.fullmatch(r"[0-9a-f]{40}", args.workflow_head_sha) or not re.fullmatch(r"[0-9a-f]{64}", args.artifact_sha256):
        raise SystemExit("Invalid Discovery predecessor identity")
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required to verify immutable Actions artifacts")
    result = find_matching_assessment_artifact(
        args.repository,
        token,
        {
            "workflow_run_id": args.workflow_run_id,
            "workflow_head_sha": args.workflow_head_sha,
            "artifact_sha256": args.artifact_sha256,
        },
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
