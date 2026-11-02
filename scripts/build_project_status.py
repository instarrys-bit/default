#!/usr/bin/env python3
"""Build a deterministic one-page operational status for the Shadowrocket ruleset project."""
from __future__ import annotations
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ("DIRECT", "PROXY", "REJECT")
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?))+$")


def valid_rule_line(line: str) -> bool:
    fields = line.split(",", 1)
    return len(fields) == 2 and fields[0] in {"DOMAIN", "DOMAIN-SUFFIX"} and bool(DOMAIN_RE.fullmatch(fields[1].lower().rstrip(".")))


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def build_status(root: Path = ROOT, now: str | None = None) -> dict:
    rules_dir = root / "rulesets"
    manifest = read_json(rules_dir / "manifest.json", {})
    lifecycle = read_json(rules_dir / "lifecycle_state.json", {})
    queue = read_json(rules_dir / "pending_queue.json", {"items": []})
    registry = read_json(root / "sources/domain_sources.json", {"sources": []})
    snapshot = read_json(root / "data/candidates.json", {"candidates": [], "sources": {}})
    activation = read_json(root / "sources/source_activation_log.json", {"activations": [], "last_decisions": []})
    discovered = read_json(root / "sources/discovered_sources.json", {"candidates": []})
    assessments = read_json(root / "sources/source_assessments.json", {"assessments": []})
    source_matrix = read_json(root / "sources/source_candidates.json", {"candidates": []})
    lineage = read_json(root / "reports/source-lineage-audit.json", {})
    policy = read_json(root / "sources/policy.json", {})
    conflict_archive = read_json(rules_dir / "config_conflict_archive.json", {"items": []})
    conflict_report = read_json(root / "reports/ruleset-config-conflict-sync.json", {})
    deletion_archive = read_json(rules_dir / "deletion_archive.json", {"items": []})
    lifecycle_report = read_json(root / "reports/lifecycle/latest.json", {"status": "not_available"})

    rules = {}
    invalid_lines = []
    for name in POLICIES:
        path = rules_dir / (name.lower() + ".list")
        values = {x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.lstrip().startswith("#")} if path.exists() else set()
        rules[name] = values
        for line in values:
            if not valid_rule_line(line):
                invalid_lines.append({"policy": name, "line": line})

    counts = {name: len(rules[name]) for name in POLICIES}
    total = sum(counts.values())
    list_files = sorted(x.name for x in rules_dir.glob("*.list"))
    expected_files = sorted(x.lower() + ".list" for x in POLICIES)
    policy_invariant = list_files == expected_files and not invalid_lines
    manifest_match = counts == manifest.get("rule_count", {}) and total == int(manifest.get("published_rule_total", -1))
    maximum = int(lifecycle.get("max_published_rules", manifest.get("max_published_rules", 30000)))
    headroom = max(0, maximum - total)
    queued = len(queue.get("items", []))

    guard = policy.get("managed_config_guard", {})
    config_path = root / str(guard.get("path", "shadowrocket/ss.conf"))
    actual_config_sha = git_blob_sha(config_path.read_bytes()) if config_path.exists() else None
    approved_config_sha = guard.get("approved_git_blob_sha")
    config_match = bool(actual_config_sha and approved_config_sha and actual_config_sha == approved_config_sha)

    source_rows = registry.get("sources", [])
    source_groups = {
        name: len({
            str(x.get("independence_group") or x.get("publisher") or x.get("id"))
            for x in source_rows if str(x.get("classification", "")).upper() == name
        })
        for name in POLICIES
    }
    source_snapshots = snapshot.get("sources", {})
    source_snapshot_rows = list(source_snapshots.values()) if isinstance(source_snapshots, dict) else list(source_snapshots or [])
    current_sources = sum(1 for x in source_snapshot_rows if x.get("status") == "CURRENT")
    degraded_sources = [x for x in source_snapshot_rows if x.get("status") != "CURRENT"]
    activated_last_run = sum(1 for x in activation.get("last_decisions", []) if x.get("decision") == "activated")
    candidates = snapshot.get("candidates", [])
    candidate_count = len(candidates) if isinstance(candidates, list) else int(snapshot.get("candidate_count", 0))
    status_counts = manifest.get("status_count", manifest.get("deterministic_review_progress", {}).get("status_count", {}))
    approved = int(manifest.get("approved_total", manifest.get("deterministic_review_progress", {}).get("approved_total", 0)))
    ledger_approved = int(status_counts.get("APPROVED", approved))
    approved_not_published = max(0, ledger_approved - approved)
    held = int(manifest.get("held_total", manifest.get("deterministic_review_progress", {}).get("held_total", 0)))

    conflict_items = conflict_archive.get("items", [])
    conflict_restorable = sum(1 for x in conflict_items if not x.get("restored_at"))
    conflict_active = sum(1 for x in conflict_items if not x.get("restored_at") and not x.get("superseded_at"))
    deletion_items = deletion_archive.get("items", [])
    deletion_restorable = sum(1 for x in deletion_items if not x.get("restored_at"))

    next_milestone = int(lifecycle.get("next_milestone", 5000))
    high_water = int(lifecycle.get("published_high_water_mark", total))
    remaining_to_milestone = max(0, next_milestone - high_water)
    due = bool(lifecycle.get("due_milestones") or lifecycle.get("monthly_review_due"))
    minimum_groups = int(manifest.get("minimum_independent_sources", 2))
    group_gaps = {name: max(0, minimum_groups - source_groups[name]) for name in POLICIES}

    integrity_ok = config_match and manifest_match and policy_invariant and total <= maximum
    health = "PASS" if integrity_ok and not degraded_sources and not any(group_gaps.values()) and not due else ("CHECK" if integrity_ok else "FAIL")
    generated_at = now or datetime.now(timezone.utc).isoformat()

    result = {
        "generated_at": generated_at,
        "health": health,
        "integrity": {
            "config_baseline_match": config_match,
            "config_blob_sha": actual_config_sha,
            "approved_config_blob_sha": approved_config_sha,
            "manifest_matches_files": manifest_match,
            "only_three_policy_outputs": policy_invariant,
            "invalid_rule_line_count": len(invalid_lines),
            "published_count_within_cap": total <= maximum,
        },
        "rulesets": {
            "counts": counts, "published_total": total, "maximum": maximum,
            "headroom": headroom, "queue_count": queued,
            "queue_mode": bool(lifecycle.get("queue_mode")), "policies": list(POLICIES),
        },
        "lifecycle": {
            "next_milestone": next_milestone,
            "published_high_water_mark": high_water,
            "additional_published_rules_to_next_milestone": remaining_to_milestone,
            "due": due, "due_milestones": lifecycle.get("due_milestones", []),
            "monthly_review_due": bool(lifecycle.get("monthly_review_due")),
            "last_successful_review_at": lifecycle.get("last_successful_review_at"),
            "last_monthly_review_at": lifecycle.get("last_monthly_review_at"),
            "deletion_archive_count": len(deletion_items),
            "deletion_restorable_count": deletion_restorable,
            "latest_report_status": lifecycle_report.get("status"),
        },
        "sources": {
            "enabled_count": len(source_rows), "current_count": current_sources,
            "degraded_count": len(degraded_sources),
            "degraded_ids": [x.get("id") for x in degraded_sources],
            "groups_by_policy": source_groups, "missing_independent_groups": group_gaps,
            "discovered_repository_count": int(discovered.get("candidate_count", len(discovered.get("candidates", [])))),
            "assessed_file_count": len(assessments.get("assessments", [])),
            "source_candidate_count": len(source_matrix.get("candidates", [])),
            "activated_this_run": activated_last_run,
            "cumulative_auto_activations": len(activation.get("activations", [])),
            "lineage_audited_count": int(lineage.get("audited_source_count", 0)),
            "lineage_partial_count": int(lineage.get("lineage_partial_count", 0)),
            "lineage_unverified_count": int(lineage.get("lineage_unverified_count", 0)),
            "lineage_verified_count": int(lineage.get("lineage_verified_count", 0)),
        },
        "review": {
            "candidate_count": candidate_count, "approved_count": approved,
            "ledger_approved_count": ledger_approved,
            "approved_not_published_count": approved_not_published,
            "held_count": held, "status_counts": status_counts,
        },
        "recovery": {
            "config_conflict_archive_total": len(conflict_items),
            "config_conflict_active_count": conflict_active,
            "config_conflict_restorable_count": conflict_restorable,
            "config_conflict_report_options": int(conflict_report.get("restoration_option_count", conflict_restorable)),
            "lifecycle_deletion_archive_total": len(deletion_items),
            "lifecycle_deletion_restorable_count": deletion_restorable,
        },
    }

    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "project-status.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Shadowrocket 项目自动化总览", "",
        f"- 生成时间：{generated_at}",
        f"- 完整性状态：**{health}**", "",
        "## 1. 已发布规则集", "",
        "| 类别 | 当前条目 |", "|---|---:|",
        f"| DIRECT | {counts['DIRECT']} |",
        f"| PROXY | {counts['PROXY']} |",
        f"| REJECT | {counts['REJECT']} |",
        f"| **合计** | **{total} / {maximum}** |", "",
        f"- 剩余容量：{headroom}", f"- 待发布队列：{queued}",
        f"- 规则输出约束：{'通过（仅三类）' if policy_invariant else '异常'}",
        f"- Manifest 与实际文件一致：{'是' if manifest_match else '否'}", "",
        "## 2. 来源与审核", "",
        f"- 已启用来源：{len(source_rows)}",
        f"- 本轮正常来源：{current_sources}",
        f"- 本轮降级/隔离来源：{len(degraded_sources)}",
        f"- 累计自动激活来源：{len(activation.get('activations', []))}；本轮新增：{activated_last_run}",
        f"- 自动发现仓库：{result['sources']['discovered_repository_count']}；评估文件：{result['sources']['assessed_file_count']}",
        f"- 候选域名：{candidate_count}；审核账本 APPROVED：{ledger_approved}；实际发布：{approved}；未发布差额：{approved_not_published}；暂缓/拒绝：{held}",
        f"- 各策略独立来源组：DIRECT {source_groups['DIRECT']}，PROXY {source_groups['PROXY']}，REJECT {source_groups['REJECT']}（最低要求 {minimum_groups}）",
        f"- 血缘审计：已审计 {result['sources']['lineage_audited_count']}；已验证 {result['sources']['lineage_verified_count']}；部分 {result['sources']['lineage_partial_count']}；未验证 {result['sources']['lineage_unverified_count']}。血缘不确定性是来源说明，不作为一票否决。", "",
        "## 3. 生命周期与容量管理", "",
        f"- 下一个生命周期节点：{next_milestone} 条；距离节点还差 {remaining_to_milestone} 条",
        f"- 生命周期审核当前状态：{'待执行' if due else '未到触发条件'}",
        f"- 30,000 条月度审核：{'到期' if lifecycle.get('monthly_review_due') else '未到期'}",
        f"- 上次成功生命周期审核：{lifecycle.get('last_successful_review_at') or '尚无'}",
        f"- 生命周期删除归档：{len(deletion_items)} 条；可恢复 {deletion_restorable} 条", "",
        "## 4. 恢复与配置保护", "",
        f"- ss.conf 基线匹配：{'通过' if config_match else '不匹配'}",
        f"- ss.conf Git Blob SHA：{actual_config_sha or 'missing'}",
        f"- 配置冲突归档：{len(conflict_items)} 条；仍有效 {conflict_active} 条；可选恢复 {conflict_restorable} 条",
        f"- 配置冲突报告恢复选项：{int(conflict_report.get('restoration_option_count', conflict_restorable))}",
        "- 主配置始终只读；规则集与主配置的冲突由独立同步程序处理。", "",
        "## 5. 需要持续关注", "",
        "- 静态审计通过不等于 iPhone / Shadowrocket 设备端实测通过。",
        "- DNS 超时、来源暂时失联、证据不足或血缘变化都不能单独触发生命周期删除。",
        "- 生命周期自动删除仅针对满足严格 NXDOMAIN 条件的精确 DOMAIN 主机；DOMAIN-SUFFIX 自动保留。",
        "- REJECT 新来源仍需达到独立来源组门槛，单一来源候选不会自动发布。", "",
    ]
    (report_dir / "project-status.md").write_text("\n".join(lines), encoding="utf-8")
    return result


def main():
    result = build_status()
    print(json.dumps({
        "health": result["health"],
        "published_total": result["rulesets"]["published_total"],
        "queue_count": result["rulesets"]["queue_count"],
        "source_count": result["sources"]["enabled_count"],
        "degraded_source_count": result["sources"]["degraded_count"],
        "config_baseline_match": result["integrity"]["config_baseline_match"],
    }, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
