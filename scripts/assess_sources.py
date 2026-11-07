#!/usr/bin/env python3
"""Assess discovered rule-list URLs for parser compatibility and explicit policy semantics.

This is a non-activating gate: it never edits the trusted source registry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from json_document_store import read_document, write_document
from resource_lease_runtime import assert_resource_lease_from_environment
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = Path(os.environ.get("AUTOMATION_ARTIFACT_ROOT", ROOT)).resolve()
INDEPENDENT_ARTIFACT_MODE = os.environ.get("AUTOMATION_TASK_PROCESS") == "1" and bool(os.environ.get("AUTOMATION_ARTIFACT_ROOT"))
PREDECESSOR_ROOT = Path(os.environ.get("AUTOMATION_PREDECESSOR_ARTIFACT_ROOT", ROOT)).resolve()
INPUT = PREDECESSOR_ROOT / "sources/discovered_sources.json"
BASELINE_OUTPUT = ROOT / "sources/source_assessments.json"
OUTPUT = ARTIFACT_ROOT / "sources/source_assessments.json" if INDEPENDENT_ARTIFACT_MODE else BASELINE_OUTPUT
RUNTIME_OUTPUT = ARTIFACT_ROOT / "data/source_assessments_runtime.json" if INDEPENDENT_ARTIFACT_MODE else ROOT / "data/source_assessments_runtime.json"
REPORT = ARTIFACT_ROOT / "reports/source-assessment.md" if INDEPENDENT_ARTIFACT_MODE else ROOT / "reports/source-assessment.md"
MAX_BYTES = 1_000_000
# Keep the monolithic fallback bounded; repeated runs rotate through the full source inventory.
MAX_TOTAL_BYTES = 10_000_000
MAX_URLS = 20
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")
DOMAIN_RULE_RE = re.compile(r"^(DOMAIN|DOMAIN-SUFFIX),([^,\s]+)(?:,([^,\s]+))?$", re.I)
QX_DOMAIN_RULE_RE = re.compile(r"^(HOST|HOST-SUFFIX),([^,\s]+),([^,\s]+)$", re.I)
ADBLOCK_RE = re.compile(r"^\|\|([a-z0-9.-]+)\^")
SENSITIVE_PATH_RE = re.compile(r"(?:porn|adult|nsfw|xxx|sex[-_]?content)", re.I)

class AssessmentBudgetExceeded(Exception):
    pass


def fetch_raw(url: str, repository: str, max_allowed_bytes: int | None = None, max_file_bytes: int = MAX_BYTES) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("assessment accepts only HTTPS raw.githubusercontent.com URLs")
    parts = [x for x in parsed.path.split("/") if x]
    if len(parts) < 4 or "/".join(parts[:2]).lower() != repository.lower():
        raise ValueError("rule-list URL does not belong to the declared repository")
    if SENSITIVE_PATH_RE.search(parsed.path):
        raise ValueError("sensitive path is excluded from assessment")
    request = urllib.request.Request(url, headers={"User-Agent": "Shadowrocket-Source-Assessor/1.0"})
    if isinstance(max_file_bytes, bool) or not isinstance(max_file_bytes, int) or max_file_bytes < 1 or max_file_bytes > MAX_BYTES:
        raise ValueError("max_file_bytes is outside the allowed assessment limit")
    limit = max_file_bytes if max_allowed_bytes is None else min(max_file_bytes, max(0, int(max_allowed_bytes)))
    if limit <= 0:
        raise AssessmentBudgetExceeded("aggregate assessment byte budget exhausted")
    with urllib.request.urlopen(request, timeout=10) as response:
        final = urllib.parse.urlparse(response.geturl())
        if response.status != 200 or final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise ValueError("unexpected rule-list response")
        data = response.read(limit + 1)
    if len(data) > limit:
        if max_allowed_bytes is not None and limit < max_file_bytes:
            raise AssessmentBudgetExceeded("source file deferred because it exceeds remaining aggregate byte budget")
        raise ValueError("rule-list exceeds assessment size limit")
    return data

def readme_policy_claim(readme: str, url: str) -> list[str]:
    actions = set()
    escaped = re.escape(url)
    for match in re.finditer(r"RULE-SET\s*,\s*" + escaped + r"\s*,\s*(DIRECT|PROXY|REJECT)\b", readme, re.I):
        actions.add(match.group(1).upper())
    return sorted(actions)

def assess_payload(payload: bytes, url: str, policy_claims: list[str]) -> dict:
    lines = payload.decode("utf-8-sig", errors="replace").splitlines()
    substantive = [line.split("#", 1)[0].strip() for line in lines]
    substantive = [line for line in substantive if line and not line.startswith(("!", "#", "["))]
    exact = set()
    suffix = set()
    actions = {}
    keyword_count = 0
    ip_count = 0
    domain_rule_lines = 0
    action_line_count = 0
    qx_domain_rule_lines = 0
    duplicate_domain_lines = 0
    adblock = set()
    domain_only = set()
    leading_dot_domain_count = 0
    for line in substantive:
        match = DOMAIN_RULE_RE.fullmatch(line)
        if match:
            kind, domain, action = match.groups()
            domain = domain.lower().rstrip(".")
            if not DOMAIN_RE.fullmatch(domain):
                continue
            target = exact if kind.upper() == "DOMAIN" else suffix
            if domain in exact or domain in suffix:
                duplicate_domain_lines += 1
            target.add(domain)
            domain_rule_lines += 1
            if action:
                action = action.upper()
                if action in {"DIRECT", "PROXY", "REJECT"}:
                    action_line_count += 1
                    actions[action] = actions.get(action, 0) + 1
                else:
                    actions["UNSUPPORTED"] = actions.get("UNSUPPORTED", 0) + 1
            continue
        qx = QX_DOMAIN_RULE_RE.fullmatch(line)
        if qx:
            kind, domain, action = qx.groups()
            domain = domain.lower().rstrip(".")
            if DOMAIN_RE.fullmatch(domain):
                target = exact if kind.upper() == "HOST" else suffix
                if domain in exact or domain in suffix:
                    duplicate_domain_lines += 1
                target.add(domain)
                domain_rule_lines += 1
                qx_domain_rule_lines += 1
                action = action.upper()
                if action == "OUTSIDE":
                    action = "PROXY"
                if action in {"DIRECT", "PROXY", "REJECT"}:
                    action_line_count += 1
                    actions[action] = actions.get(action, 0) + 1
                else:
                    actions["UNSUPPORTED"] = actions.get("UNSUPPORTED", 0) + 1
            continue
        if line.upper().startswith(("DOMAIN-KEYWORD,", "HOST-KEYWORD,")):
            keyword_count += 1
            continue
        if line.upper().startswith(("IP-CIDR,", "IP-CIDR6,", "IP-ASN,")):
            ip_count += 1
            continue
        ad = ADBLOCK_RE.match(line.lower())
        if ad and DOMAIN_RE.fullmatch(ad.group(1).rstrip(".")):
            adblock.add(ad.group(1).rstrip("."))
            continue
        normalized = line.lower()
        if normalized.startswith("."):
            domain = normalized[1:].rstrip(".")
            if not domain.startswith(".") and DOMAIN_RE.fullmatch(domain):
                domain_only.add(domain)
                leading_dot_domain_count += 1
        else:
            domain = normalized.rstrip(".")
            if DOMAIN_RE.fullmatch(domain):
                domain_only.add(domain)
    domain_rule_count = len(exact) + len(suffix)
    explicit_actions = {x for x in actions if x in {"DIRECT", "PROXY", "REJECT"}}
    complete_explicit_action = (
        domain_rule_lines > 0
        and action_line_count == domain_rule_lines
        and len(explicit_actions) == 1
        and "UNSUPPORTED" not in actions
    )
    header = " ".join(lines[:12]).lower()
    header_claims = set()
    if "代理列表" in header or "proxy list" in header:
        header_claims.add("PROXY")
    if "直连列表" in header or "direct list" in header:
        header_claims.add("DIRECT")
    if "拦截列表" in header or "blocklist" in header or "block list" in header:
        header_claims.add("REJECT")
    all_policy_claims = set(policy_claims) | header_claims
    if complete_explicit_action:
        all_policy_claims.add(next(iter(explicit_actions)))
    policy = None
    policy_evidence = "none"
    if len(all_policy_claims) == 1:
        policy = next(iter(all_policy_claims))
        if complete_explicit_action:
            policy_evidence = "explicit_third_field"
        elif policy_claims:
            policy_evidence = "README_policy_reference"
        elif header_claims:
            policy_evidence = "source_header_claim"
    elif len(all_policy_claims) > 1 or explicit_actions or "UNSUPPORTED" in actions:
        policy_evidence = "ambiguous"
    if len(adblock) >= 20 and len(adblock) >= len(exact) + len(suffix):
        parser = "adblock-domain-rules"
    elif qx_domain_rule_lines >= 20:
        parser = "quantumult-domain-rules"
    elif domain_rule_count >= 20:
        parser = "shadowrocket-domain-rules"
    elif len(domain_only) >= 20 and len(domain_only) >= len(substantive) * 0.8:
        parser = "domain-only"
    else:
        parser = "unsupported_or_too_small"
    return {
        "url": url,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "substantive_lines": len(substantive),
        "parser_candidate": parser,
        "exact_domain_count": len(exact),
        "suffix_domain_count": len(suffix),
        "adblock_domain_count": len(adblock),
        "domain_only_count": len(domain_only),
        "leading_dot_domain_count": leading_dot_domain_count,
        "domain_fingerprints": sorted(
            hashlib.sha256(domain.encode("utf-8")).hexdigest()[:32]
            for domain in (exact | suffix | adblock | domain_only)
        ),
        "duplicate_domain_lines": duplicate_domain_lines,
        "domain_keyword_rules_ignored": keyword_count,
        "ip_asn_rules_ignored": ip_count,
        "explicit_action_counts": actions,
        "readme_policy_claims": policy_claims,
        "policy_candidate": policy,
        "policy_evidence": policy_evidence,
        "activation_eligible": False,
    }

def compare_drift(current: dict, previous: dict | None) -> dict:
    if current.get("error"):
        return {"status": "unavailable", "added_domain_count": 0, "removed_domain_count": 0, "policy_changed": False}
    if not previous:
        return {"status": "baseline_initialized", "added_domain_count": len(current.get("domain_fingerprints", [])), "removed_domain_count": 0, "policy_changed": False}
    old_sha = previous.get("sha256")
    new_sha = current.get("sha256")
    policy_changed = (
        previous.get("policy_candidate") != current.get("policy_candidate")
        or previous.get("policy_evidence") != current.get("policy_evidence")
    )
    if old_sha == new_sha:
        return {
            "status": "policy_metadata_changed" if policy_changed else "unchanged",
            "added_domain_count": 0,
            "removed_domain_count": 0,
            "policy_changed": policy_changed,
        }
    old_domains = set(previous.get("domain_fingerprints", []))
    new_domains = set(current.get("domain_fingerprints", []))
    if not old_domains:
        return {
            "status": "content_changed_baseline_schema_unavailable",
            "added_domain_count": None,
            "removed_domain_count": None,
            "policy_changed": policy_changed,
        }
    added = len(new_domains - old_domains)
    removed = len(old_domains - new_domains)
    status = "domain_set_changed" if added or removed else "content_changed_no_domain_change"
    if policy_changed:
        status += "_and_policy_changed"
    return {
        "status": status,
        "added_domain_count": added,
        "removed_domain_count": removed,
        "policy_changed": policy_changed,
        "previous_sha256": old_sha,
        "current_sha256": new_sha,
    }

def render_report(assessments: list[dict], drift_summary: dict | None = None) -> str:
    rows = [
        "# Automated source assessment",
        "",
        f"- Rule-list files assessed: **{len(assessments)}**",
        "- This stage checks syntax and explicit policy claims only. It never activates sources.",
        "- Keyword, IP/CIDR and ASN rules are counted as ignored; they are never converted into domains.",
        "",
        "| Repository | Parser candidate | Policy candidate | Domain entries | Drift | Evidence |",
        "|---|---|---|---:|---|---|",
    ]
    for item in assessments:
        rows.append(
            f"| {item['repository']} | {item['parser_candidate']} | "
            f"{item.get('policy_candidate') or '—'} | "
            f"{item['exact_domain_count'] + item['suffix_domain_count'] + item['adblock_domain_count'] + item['domain_only_count']} | "
            f"{item.get('drift', {}).get('status', 'not_compared')} | {item['policy_evidence']} |"
        )
    drift_summary = drift_summary or {}
    rows.extend([
        "",
        "## Source update drift",
        "",
        f"- New source files: {drift_summary.get('new_source_files', 0)}",
        f"- Changed source files: {drift_summary.get('changed_source_files', 0)}",
        f"- Added domain entries: {drift_summary.get('added_domain_count', 0)}",
        f"- Removed domain entries: {drift_summary.get('removed_domain_count', 0)}",
        f"- Policy changes: {drift_summary.get('policy_changes', 0)}",
        "",
        "## Assessment details",
        "",
    ])
    for item in assessments:
        rows.extend([
            f"### {item['repository']}",
            "",
            f"- URL: {item['url']}",
            f"- SHA-256: {item.get('sha256', 'unavailable')}",
            f"- Exact DOMAIN: {item['exact_domain_count']}; DOMAIN-SUFFIX: {item['suffix_domain_count']}; Adblock: {item['adblock_domain_count']}; domain-only: {item['domain_only_count']}; duplicate lines: {item.get('duplicate_domain_lines', 0)}",
            f"- Ignored non-domain rules: DOMAIN-KEYWORD {item['domain_keyword_rules_ignored']}; IP/CIDR/ASN {item['ip_asn_rules_ignored']}",
            f"- Explicit action counts: {json.dumps(item['explicit_action_counts'], sort_keys=True)}",
            f"- Policy evidence: {item['policy_evidence']}; candidate: {item.get('policy_candidate') or 'none'}",
            "",
        ])
    rows.extend([
        "## Activation gate",
        "",
        "A parser candidate is not a trusted source. Activation still requires declared policy semantics, independent publishers, lineage checks, parser tests, stable update history, and all per-policy confidence gates. This report is advisory and cannot alter sources/domain_sources.json.",
        "",
    ])
    return "\n".join(rows)

def flatten_candidate_urls(candidates: list[dict]) -> list[dict]:
    flattened = []
    seen = set()
    for candidate in sorted(candidates, key=lambda item: (not bool(item.get('seeded_source_urls')), -int(item.get('stars', 0)), str(item.get('repository', '')))):
        repository = str(candidate.get('repository', ''))
        if not repository or '/' not in repository:
            continue
        seeded = set(candidate.get('seeded_source_urls', []))
        for url in sorted(candidate.get('rule_list_urls', []), key=lambda value: (value not in seeded, value)):
            if url in seen or SENSITIVE_PATH_RE.search(urllib.parse.urlparse(url).path):
                continue
            seen.add(url)
            flattened.append({'repository': repository, 'url': url, 'seeded': url in seeded, 'stars': int(candidate.get('stars', 0)), 'archived': bool(candidate.get('archived', False)), 'policy_claims': candidate.get('readme_policy_claims', {}).get(url, [])})
    return flattened


def rotate_assessment_urls(items: list[dict], cursor_url: str | None, limit: int = MAX_URLS) -> list[dict]:
    if not items:
        return []
    start = 0
    if cursor_url:
        for index, item in enumerate(items):
            if item.get('url') == cursor_url:
                start = (index + 1) % len(items)
                break
    return (items[start:] + items[:start])[:max(0, int(limit))]


def rotate_assessment_urls_for_task(items: list[dict], predecessor: dict, limit: int = MAX_URLS) -> list[dict]:
    """Choose a stable batch for a producer run so queue retries cannot advance the cursor."""
    if not items:
        return []
    if not isinstance(predecessor, dict):
        raise ValueError("task assessment requires a predecessor proof")
    run_id = predecessor.get("workflow_run_id")
    artifact_sha = predecessor.get("artifact_sha256")
    if not isinstance(run_id, str) or not run_id.isdigit():
        raise ValueError("task predecessor workflow_run_id must be numeric")
    if not isinstance(artifact_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", artifact_sha):
        raise ValueError("task predecessor artifact digest must be a full SHA-256")
    seed = hashlib.sha256((run_id + ":" + artifact_sha).encode("ascii")).digest()
    start = int.from_bytes(seed[:8], "big") % len(items)
    return (items[start:] + items[:start])[:max(0, int(limit))]

def compact_assessment_result(result: dict) -> dict:
    """Persist metadata only; keep per-domain fingerprints ephemeral for same-run analysis."""
    compact = dict(result)
    compact["assessments"] = [
        {key: value for key, value in item.items() if key != "domain_fingerprints"}
        for item in result.get("assessments", [])
    ]
    compact["fingerprints_storage"] = "ephemeral data/source_assessments_runtime.json; excluded from Git publication"
    return compact


def assessment_cache_hit(previous: dict | None, content_sha256: str, policy_claims: list[str]) -> bool:
    """Reuse parser output only when exact source bytes and README policy claims are unchanged."""
    return bool(
        previous
        and previous.get("sha256") == content_sha256
        and sorted(previous.get("readme_policy_claims", [])) == sorted(policy_claims)
        and not previous.get("error")
    )

def load_task_options(path: Path | None) -> dict:
    defaults = {"max_urls": MAX_URLS, "max_file_bytes": MAX_BYTES, "max_total_bytes": MAX_TOTAL_BYTES}
    if path is None:
        return defaults
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read assessment task input: {exc}") from exc
    allowed = set(defaults) | {"predecessor"}
    if not isinstance(value, dict) or set(value) != allowed:
        raise ValueError("assessment task input must contain the three bounded options and a typed predecessor proof")
    predecessor = value.get("predecessor")
    required_predecessor_fields = {"program_id", "workflow_name", "workflow_run_id", "workflow_head_sha", "artifact_path", "artifact_sha256"}
    if not isinstance(predecessor, dict) or set(predecessor) != required_predecessor_fields:
        raise ValueError("assessment predecessor proof is malformed")
    if (predecessor.get("program_id") != "script_discover_sources"
            or predecessor.get("workflow_name") != "Shadowrocket Source Discovery (Watchdog)"
            or predecessor.get("artifact_path") != "sources/discovered_sources.json"):
        raise ValueError("assessment predecessor must identify the dedicated discovery workflow and allowlisted artifact")
    bounds = {"max_urls": (1, 20), "max_file_bytes": (1, 1_000_000), "max_total_bytes": (1, 10_000_000)}
    for key, (minimum, maximum) in bounds.items():
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int) or not minimum <= item <= maximum:
            raise ValueError(f"{key} must be an integer from {minimum} to {maximum}")
    if value["max_total_bytes"] < value["max_file_bytes"]:
        raise ValueError("max_total_bytes must be at least max_file_bytes")
    return value


def assert_optional_write_lease(path: Path, *, required: bool = False) -> None:
    """Repository writes require their exact lease; isolated task artifacts are runner-local."""
    resolved = path.resolve()
    if resolved.is_relative_to(ROOT.resolve()):
        if required and not os.environ.get("AUTOMATION_RESOURCE_LEASE_PROOF"):
            raise ValueError("independent assessment requires an active resource lease proof")
        if required or os.environ.get("AUTOMATION_RESOURCE_LEASE_PROOF"):
            assert_resource_lease_from_environment(resolved.relative_to(ROOT.resolve()).as_posix())
        return
    if not INDEPENDENT_ARTIFACT_MODE or not resolved.is_relative_to(ARTIFACT_ROOT):
        raise ValueError("assessment output must remain inside the isolated runner-local artifact root")
    runner_temp = Path(os.environ.get("RUNNER_TEMP", "/tmp")).resolve()
    if not ARTIFACT_ROOT.is_relative_to(runner_temp) or ARTIFACT_ROOT == ROOT.resolve():
        raise ValueError("assessment artifact root must be isolated under RUNNER_TEMP")


def _checkpoint_runtime(store=None, registry=None):
    """Resolve the queue CAS client used for durable per-URL progress."""
    if store is None:
        from remote_task_queue_runtime import make_store
        store = make_store(
            os.environ.get("AUTOMATION_QUEUE_REPOSITORY"),
            os.environ.get("AUTOMATION_QUEUE_BRANCH"),
            os.environ.get("AUTOMATION_QUEUE_PATH", "automation/task_queue.json"),
            token=os.environ.get("AUTOMATION_QUEUE_TOKEN"),
        )
    if registry is None:
        registry = json.loads((ROOT / "automation/program_registry.json").read_text(encoding="utf-8"))
    return store, registry


def _validate_checkpoint_writer(queue: dict, batch_id: str, predecessor: dict):
    """Bind checkpoint mutation to the current task, task lease and every live fence."""
    from datetime import datetime, timezone
    task_id = os.environ.get("AUTOMATION_TASK_ID", "")
    worker_id = os.environ.get("AUTOMATION_WORKER_ID", "")
    task_token = os.environ.get("AUTOMATION_TASK_LEASE_TOKEN", "")
    try:
        proof = json.loads(os.environ.get("AUTOMATION_RESOURCE_LEASE_PROOF", "{}"))
    except json.JSONDecodeError as exc:
        raise ValueError("assessment checkpoint resource proof is malformed") from exc
    task = next((item for item in queue.get("tasks", []) if item.get("task_id") == task_id), None)
    if not isinstance(task, dict) or task.get("target_program_id") != "script_assess_sources" or task.get("status") != "CLAIMED":
        raise ValueError("assessment checkpoint requires the active claimed source-assessment task")
    task_predecessor = (task.get("input") or {}).get("predecessor")
    expected_batch_id = "discovery-run:" + str(predecessor.get("workflow_run_id")) + ":" + str(predecessor.get("artifact_sha256", ""))[:12]
    if task_predecessor != predecessor or batch_id != expected_batch_id:
        raise ValueError("assessment checkpoint is not bound to this task's immutable predecessor")
    lease = task.get("lease") or {}
    now = datetime.now(timezone.utc)
    if lease.get("owner") != worker_id or lease.get("token") != task_token:
        raise ValueError("assessment checkpoint task lease identity changed")
    if datetime.fromisoformat(lease["expires_at"].replace("Z", "+00:00")) <= now:
        raise ValueError("assessment checkpoint task lease expired")
    resource_lease = task.get("resource_lease") or {}
    declared = resource_lease.get("resources")
    if resource_lease.get("status") != "ACTIVE" or not isinstance(declared, dict) or declared != proof:
        raise ValueError("assessment checkpoint resource proof is no longer active")
    leases = queue.get("resource_leases")
    if not isinstance(leases, dict):
        raise ValueError("assessment checkpoint resource lease registry is missing")
    for key, item in proof.items():
        record = leases.get(key)
        if (not isinstance(record, dict) or record.get("status") != "ACTIVE"
                or record.get("task_id") != task_id
                or record.get("worker_id") != worker_id
                or record.get("task_lease_token") != task_token
                or record.get("lease_id") != item.get("lease_id")
                or record.get("fencing_token") != item.get("fencing_token")
                or datetime.fromisoformat(record["expires_at"].replace("Z", "+00:00")) <= now):
            raise ValueError("assessment checkpoint fencing proof is stale: " + str(key))
    if "logical/source-assessment-checkpoints" not in proof or "logical/production-pipeline" not in proof:
        raise ValueError("assessment checkpoint requires both checkpoint-state and production-pipeline leases")
    checkpoint = task.get("assessment_checkpoint")
    if checkpoint is not None:
        if (not isinstance(checkpoint, dict) or checkpoint.get("schema_version") != 1
                or checkpoint.get("batch_id") != batch_id
                or checkpoint.get("predecessor_artifact_sha256") != predecessor.get("artifact_sha256")
                or not isinstance(checkpoint.get("completed"), dict)):
            raise ValueError("existing assessment checkpoint belongs to a different immutable batch")
    return task, checkpoint


def load_assessment_checkpoint(batch_id: str, predecessor: dict, *, store=None, registry=None) -> dict:
    """Read completed URL results from the durable queue checkpoint for this task."""
    assert_resource_lease_from_environment("logical/source-assessment-checkpoints")
    store, registry = _checkpoint_runtime(store, registry)
    from remote_task_queue_runtime import validate_candidate, validate_envelope
    queue = store.read().document
    validate_envelope(queue)
    validate_candidate(queue, registry)
    _, checkpoint = _validate_checkpoint_writer(queue, batch_id, predecessor)
    if checkpoint is None:
        return {}
    completed = checkpoint["completed"]
    if len(completed) > 20:
        raise ValueError("assessment checkpoint exceeds the bounded 20-URL batch")
    restored = {}
    for url, record in completed.items():
        if (not isinstance(url, str) or not isinstance(record, dict)
                or not isinstance(record.get("result"), dict)
                or record.get("result", {}).get("url") != url):
            raise ValueError("assessment checkpoint contains a malformed URL result")
        expected = hashlib.sha256(json.dumps(record["result"], sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest()
        if record.get("result_sha256") != expected:
            raise ValueError("assessment checkpoint result digest mismatch")
        restored[url] = dict(record["result"])
    return restored


def persist_assessment_checkpoint(batch_id: str, predecessor: dict, result: dict, *, store=None, registry=None) -> None:
    """CAS-persist one completed URL result under the live task/resource fencing proof."""
    if not isinstance(result, dict) or not isinstance(result.get("url"), str):
        raise ValueError("assessment checkpoint result requires a URL")
    assert_resource_lease_from_environment("logical/source-assessment-checkpoints")
    store, registry = _checkpoint_runtime(store, registry)
    from remote_task_queue_runtime import validate_candidate, validate_envelope
    from task_queue_runtime import stamp, now_utc
    result_json = json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    result_sha = hashlib.sha256(result_json.encode("utf-8")).hexdigest()

    def mutate(queue):
        validate_envelope(queue)
        validate_candidate(queue, registry)
        task, checkpoint = _validate_checkpoint_writer(queue, batch_id, predecessor)
        if checkpoint is None:
            checkpoint = {
                "schema_version": 1,
                "batch_id": batch_id,
                "predecessor_artifact_sha256": predecessor["artifact_sha256"],
                "completed": {},
                "last_successful_url": None,
                "updated_at": stamp(now_utc()),
            }
            task["assessment_checkpoint"] = checkpoint
        existing = checkpoint["completed"].get(result["url"])
        if existing is not None:
            if existing.get("result_sha256") != result_sha:
                raise ValueError("assessment checkpoint URL already has a different completed result")
            return queue, {"stored": False, "url": result["url"]}
        if len(checkpoint["completed"]) >= 20:
            raise ValueError("assessment checkpoint reached the bounded 20-URL limit")
        checkpoint["completed"][result["url"]] = {"result": json.loads(result_json), "result_sha256": result_sha}
        checkpoint["last_successful_url"] = result["url"]
        checkpoint["updated_at"] = stamp(now_utc())
        queue["revision"] += 1
        validate_candidate(queue, registry)
        return queue, {"stored": True, "url": result["url"]}

    store.mutate(mutate)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-input", type=Path)
    args = parser.parse_args(argv)
    options = load_task_options(args.task_input)
    if args.task_input is not None and os.environ.get("AUTOMATION_TASK_PROCESS") == "1":
        if not INDEPENDENT_ARTIFACT_MODE or not os.environ.get("AUTOMATION_PREDECESSOR_ARTIFACT_ROOT"):
            raise ValueError("independent assessment requires verified predecessor and isolated artifact roots")
        assert_optional_write_lease(RUNTIME_OUTPUT, required=True)
        assert_optional_write_lease(OUTPUT, required=True)
        assert_optional_write_lease(REPORT, required=True)
    max_urls = options["max_urls"]
    max_file_bytes = options["max_file_bytes"]
    max_total_bytes = options["max_total_bytes"]
    discovery = read_document(INPUT, "candidates", {"candidates": []})
    previous_data = read_document(BASELINE_OUTPUT, "assessments", {"assessments": []})
    previous_by_url = {x.get("url"): x for x in previous_data.get("assessments", []) if x.get("url")}
    previous_cursor = previous_data.get("next_cursor_url")
    candidate_urls = flatten_candidate_urls(discovery.get("candidates", []))
    predecessor = options.get("predecessor") if args.task_input is not None else None
    if predecessor is not None:
        batch = rotate_assessment_urls_for_task(candidate_urls, predecessor, max_urls)
        batch_id = "discovery-run:" + predecessor["workflow_run_id"] + ":" + predecessor["artifact_sha256"][:12]
    else:
        batch = rotate_assessment_urls(candidate_urls, previous_cursor, max_urls)
        batch_id = datetime.now(timezone.utc).isoformat()
    completed_checkpoint = (
        load_assessment_checkpoint(batch_id, predecessor)
        if predecessor is not None else {}
    )
    assessments = []
    total_bytes_read = 0
    budget_exhausted = False
    for candidate in batch:
        repository = candidate["repository"]
        url = candidate["url"]
        if url in completed_checkpoint:
            item = dict(completed_checkpoint[url])
            restored_bytes = item.get("bytes", 0)
            if isinstance(restored_bytes, int) and not isinstance(restored_bytes, bool) and restored_bytes >= 0:
                total_bytes_read += restored_bytes
            item["drift"] = compare_drift(item, previous_by_url.get(url))
            assessments.append(item)
            continue
        try:
            payload = fetch_raw(url, repository, max_total_bytes - total_bytes_read, max_file_bytes=max_file_bytes)
            total_bytes_read += len(payload)
            content_hash = hashlib.sha256(payload).hexdigest()
            previous = previous_by_url.get(url)
            if assessment_cache_hit(previous, content_hash, candidate["policy_claims"]):
                item = dict(previous)
                item["readme_policy_claims"] = sorted(candidate["policy_claims"])
                item["assessed_at"] = batch_id
            else:
                item = assess_payload(payload, url, candidate["policy_claims"])
            item["repository"] = repository
            item["stars"] = candidate["stars"]
            item["archived"] = candidate["archived"]
            item["assessed_at"] = batch_id
        except AssessmentBudgetExceeded:
            budget_exhausted = True
            break
        except (OSError, urllib.error.URLError, ValueError) as exc:
            assessments.append({
                "repository": repository, "url": url,
                "parser_candidate": "fetch_or_validation_error",
                "policy_candidate": None, "policy_evidence": "none",
                "error": str(exc), "activation_eligible": False,
                "exact_domain_count": 0, "suffix_domain_count": 0,
                "adblock_domain_count": 0, "domain_only_count": 0,
                "duplicate_domain_lines": 0,
                "domain_fingerprints": [],
                "domain_keyword_rules_ignored": 0, "ip_asn_rules_ignored": 0,
                "explicit_action_counts": {}, "assessed_at": batch_id,
            })
            continue
        # Persist outside the network-error handler: a stale fencing proof or
        # queue CAS failure must abort the task, never masquerade as a bad URL.
        if predecessor is not None:
            persist_assessment_checkpoint(batch_id, predecessor, item)
        assessments.append(item)
    for item in assessments:
        if "drift" not in item:
            item["drift"] = compare_drift(item, previous_by_url.get(item.get("url")))
    drift_summary = {
        "new_source_files": sum(1 for x in assessments if x.get("drift", {}).get("status") == "baseline_initialized"),
        "changed_source_files": sum(1 for x in assessments if x.get("drift", {}).get("status", "").startswith(("domain_set_changed", "content_changed"))),
        "added_domain_count": sum(x["drift"].get("added_domain_count") or 0 for x in assessments),
        "removed_domain_count": sum(x["drift"].get("removed_domain_count") or 0 for x in assessments),
        "policy_changes": sum(1 for x in assessments if x["drift"].get("policy_changed")),
    }
    next_cursor = assessments[-1]["url"] if assessments else previous_cursor
    history = dict(previous_by_url)
    for item in assessments:
        url = item.get("url")
        prior = history.get(url, {})
        if item.get("error") and prior.get("sha256"):
            prior = dict(prior)
            prior["last_fetch_error"] = item.get("error")
            prior["last_attempt_at"] = batch_id
            history[url] = prior
        else:
            history[url] = item
    result = {
        "schema_version": 1,
        "assessment_count": len(assessments),
        "assessed_this_run_count": len(assessments),
        "historical_assessment_count": len(history),
        "candidate_url_count": len(candidate_urls),
        "deferred_this_run_count": max(0, len(candidate_urls) - len(assessments)),
        "budget_exhausted": budget_exhausted,
        "batch_id": batch_id,
        "next_cursor_url": next_cursor,
        "total_bytes_read": total_bytes_read,
        "assessment_capacity": {"max_urls": max_urls, "max_file_bytes": max_file_bytes, "max_total_bytes": max_total_bytes},
        "drift_summary": drift_summary,
        "activation_count": 0,
        "assessments": assessments,
        "activation_policy": "Assessment never edits or enables sources/domain_sources.json.",
    }
    persistent = dict(result)
    persistent["assessments"] = list(history.values())
    persistent["assessment_count"] = len(history)
    assert_optional_write_lease(RUNTIME_OUTPUT, required=args.task_input is not None)
    write_document(RUNTIME_OUTPUT, result, "assessments", lease_required=False)
    assert_optional_write_lease(OUTPUT, required=args.task_input is not None)
    write_document(OUTPUT, compact_assessment_result(persistent), "assessments", lease_required=False)
    assert_optional_write_lease(REPORT, required=args.task_input is not None)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    assert_optional_write_lease(REPORT, required=args.task_input is not None)
    REPORT.write_text(render_report(assessments, drift_summary), encoding="utf-8")
    print(json.dumps({
        "assessed": len(assessments),
        "bytes_read": total_bytes_read,
        "parser_candidates": sum(1 for x in assessments if x.get("parser_candidate") in {"domain-only", "adblock-domain-rules", "shadowrocket-domain-rules", "quantumult-domain-rules"}),
        "policy_candidates": sum(1 for x in assessments if x.get("policy_candidate")),
        "activated": 0,
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
