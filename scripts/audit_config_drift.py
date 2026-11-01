#!/usr/bin/env python3
"""Read-only comparison of the user-managed Shadowrocket config against the canonical baseline."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "sources" / "policy.json"
REPORT_JSON = ROOT / "reports" / "config-drift-audit.json"
REPORT_MD = ROOT / "reports" / "config-drift-audit.md"


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
            key = key.strip().lower()
            sections.setdefault(current, {}).setdefault(key, []).append(value.strip())
    return sections


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + bytes([0]) + data).hexdigest()


def compare_sections(baseline: dict, managed: dict) -> list[dict]:
    differences = []
    for section in sorted(set(baseline) | set(managed)):
        if section not in baseline:
            differences.append({"section": section, "key": "*", "kind": "added_section",
                                "baseline": None, "managed": None})
            continue
        if section not in managed:
            differences.append({"section": section, "key": "*", "kind": "removed_section",
                                "baseline": None, "managed": None})
            continue
        for key in sorted(set(baseline[section]) | set(managed[section])):
            before = baseline[section].get(key)
            after = managed[section].get(key)
            if before != after:
                kind = "added_key" if before is None else "removed_key" if after is None else "changed_value"
                differences.append({"section": section, "key": key, "kind": kind,
                                    "baseline": before, "managed": after})
    return differences


def main() -> int:
    policy = json.loads(POLICY_PATH.read_text(encoding="utf-8"))
    baseline_path = ROOT / policy["canonical_config"]["path"]
    managed_path = ROOT / policy["managed_config_guard"]["path"]
    baseline_bytes = baseline_path.read_bytes()
    managed_bytes = managed_path.read_bytes()
    baseline = parse_config(baseline_bytes.decode("utf-8-sig"))
    managed = parse_config(managed_bytes.decode("utf-8-sig"))
    differences = compare_sections(baseline, managed)
    mitm_enabled = any(v.lower() == "true" for v in managed.get("MITM", {}).get("enable", []))
    dns_keys = {"dns-server", "fallback-dns-server", "direct-dns-server", "proxy-dns-server",
                "dns-direct-system", "dns-direct-fallback-proxy", "hijack-dns"}
    dns_differences = [d for d in differences if d["section"].lower() == "general" and d["key"] in dns_keys]
    result = {
        "schema_version": 1,
        "mode": "read_only",
        "baseline_path": str(baseline_path.relative_to(ROOT)),
        "managed_path": str(managed_path.relative_to(ROOT)),
        "baseline_sha256": hashlib.sha256(baseline_bytes).hexdigest(),
        "managed_sha256": hashlib.sha256(managed_bytes).hexdigest(),
        "baseline_git_blob_sha": policy["canonical_config"]["approved_git_blob_sha"],
        "managed_git_blob_sha": git_blob_sha(managed_bytes),
        "managed_matches_registered_blob": git_blob_sha(managed_bytes) == policy["managed_config_guard"]["approved_git_blob_sha"],
        "managed_config_differs_from_baseline": bool(differences),
        "difference_count": len(differences),
        "dns_difference_count": len(dns_differences),
        "mitm_section_present": "MITM" in managed,
        "mitm_enabled": mitm_enabled,
        "differences": differences,
        "limitations": [
            "This report detects file-level configuration drift; it does not change the managed config.",
            "Differences are observations, not automatic proof that a setting is wrong.",
            "Static checks cannot verify runtime behavior inside Shadowrocket."
        ]
    }
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# Shadowrocket configuration drift audit", "",
        "- Mode: read-only",
        f"- Managed config SHA-256: `{result['managed_sha256']}`",
        f"- Canonical baseline SHA-256: `{result['baseline_sha256']}`",
        f"- Differences from baseline: **{len(differences)}**",
        f"- DNS-related differences: **{len(dns_differences)}**",
        f"- MITM section present: **{result['mitm_section_present']}**",
        f"- MITM enabled: **{mitm_enabled}**", "",
        "## Detected differences", ""
    ]
    if not differences:
        lines.append("No differences detected.")
    else:
        lines.extend(["| Section | Key | Change | Baseline | Managed |", "|---|---|---|---|---|"])
        for item in differences:
            before = json.dumps(item["baseline"], ensure_ascii=False)
            after = json.dumps(item["managed"], ensure_ascii=False)
            lines.append(f"| {item['section']} | {item['key']} | {item['kind']} | {before} | {after} |")
    lines.extend(["", "## Interpretation", "",
        "This is an automatic, read-only drift report. It does not edit the user's config or rewrite DNS/MITM settings.",
        "A difference is flagged for inspection; the automation does not assume the canonical baseline is the desired current runtime config.",
        ""])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("difference_count", "dns_difference_count",
                                               "mitm_section_present", "mitm_enabled")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
