#!/usr/bin/env python3
"""Read-only audit using the user's managed Shadowrocket config as the sole authority."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "sources" / "policy.json"
REPORT_JSON = ROOT / "reports" / "config-drift-audit.json"
REPORT_MD = ROOT / "reports" / "config-drift-audit.md"
DNS_KEYS = (
    "dns-server", "fallback-dns-server", "direct-dns-server",
    "proxy-dns-server", "dns-direct-system",
    "dns-direct-fallback-proxy", "hijack-dns",
)


def parse_config(text: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            sections.setdefault(current, {})
            continue
        if current in {"Rule", "URL Rewrite"}:
            sections.setdefault(current, {}).setdefault("__raw_lines__", []).append(line)
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            sections.setdefault(current, {}).setdefault(key.strip().lower(), []).append(value.strip())
    return sections


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def build_report(config_bytes: bytes, expected_blob_sha: str, config_path: str) -> dict:
    text = config_bytes.decode("utf-8-sig")
    sections = parse_config(text)
    general = sections.get("General", {})
    dns_snapshot = {key: general[key] for key in DNS_KEYS if key in general}
    mitm_enabled = any(value.lower() == "true" for value in sections.get("MITM", {}).get("enable", []))
    actual_blob_sha = git_blob_sha(config_bytes)
    return {
        "schema_version": 2,
        "mode": "read_only_user_config_baseline",
        "baseline_path": config_path,
        "baseline_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "baseline_git_blob_sha": actual_blob_sha,
        "registered_baseline_git_blob_sha": expected_blob_sha,
        "baseline_matches_registered_blob": actual_blob_sha == expected_blob_sha,
        "section_names": list(sections),
        "section_count": len(sections),
        "rule_line_count": len(sections.get("Rule", {}).get("__raw_lines__", [])),
        "url_rewrite_line_count": len(sections.get("URL Rewrite", {}).get("__raw_lines__", [])),
        "dns_snapshot": dns_snapshot,
        "mitm_section_present": "MITM" in sections,
        "mitm_enabled": mitm_enabled,
        "limitations": [
            "The current shadowrocket/ss.conf is the sole policy and configuration reference for this audit.",
            "The automation reads this file and does not modify it.",
            "DNS values and MITM state are reported as observed facts, not rewritten or inferred.",
            "Static checks cannot verify runtime behavior inside the Shadowrocket app."
        ]
    }


def main() -> int:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    guard = policy["managed_config_guard"]
    config_path = guard["path"]
    config_bytes = (ROOT / config_path).read_bytes()
    result = build_report(config_bytes, guard["approved_git_blob_sha"], config_path)
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Shadowrocket user-config baseline audit", "",
        "- Mode: read-only; user-managed config is authoritative",
        f"- Baseline file: `{config_path}`",
        f"- Baseline Git blob SHA: `{result['baseline_git_blob_sha']}`",
        f"- Registered baseline SHA matches: **{result['baseline_matches_registered_blob']}**",
        f"- Sections: **{result['section_count']}**",
        f"- Rule lines: **{result['rule_line_count']}**",
        f"- URL Rewrite lines: **{result['url_rewrite_line_count']}**",
        f"- MITM section present: **{result['mitm_section_present']}**",
        f"- MITM enabled: **{result['mitm_enabled']}**", "",
        "## DNS snapshot (observed; not changed)", ""
    ]
    if result["dns_snapshot"]:
        for key, values in result["dns_snapshot"].items():
            lines.append(f"- `{key}`: " + " | ".join(f"`{value}`" for value in values))
    else:
        lines.append("No recognized DNS settings found in [General].")
    lines.extend(["", "## Interpretation", "",
        "All checks use the current user-managed config as the authority. The historical uploaded baseline is not used to judge whether this config is correct.",
        "A registered-hash mismatch means the config changed without its baseline record being updated; it does not authorize the automation to rewrite the config.",
        "DNS and MITM are reported only. No settings are added, removed, or changed.", ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({
        "baseline_matches_registered_blob": result["baseline_matches_registered_blob"],
        "section_count": result["section_count"],
        "rule_line_count": result["rule_line_count"],
        "dns_keys_present": list(result["dns_snapshot"]),
        "mitm_section_present": result["mitm_section_present"],
        "mitm_enabled": result["mitm_enabled"]
    }, ensure_ascii=False))
    return 0 if result["baseline_matches_registered_blob"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
