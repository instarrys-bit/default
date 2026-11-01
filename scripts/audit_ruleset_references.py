#!/usr/bin/env python3
"""Read-only consistency audit for RULE-SET references in the user config."""
from __future__ import annotations
import json
import re
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "shadowrocket" / "ss.conf"
RULESETS = ROOT / "rulesets"
MANIFEST = RULESETS / "manifest.json"
REPORT_JSON = ROOT / "reports" / "ruleset-reference-audit.json"
REPORT_MD = ROOT / "reports" / "ruleset-reference-audit.md"
EXPECTED_REPO_PATH = "/instarrys-bit/default/main/rulesets/"
POLICY_BY_FILE = {"direct.list": "DIRECT", "proxy.list": "PROXY", "reject.list": "REJECT"}
DOMAIN_LINE = re.compile(r"^(DOMAIN|DOMAIN-SUFFIX),([A-Za-z0-9.-]+)$", re.IGNORECASE)
DOMAIN_RE = re.compile(r"^(?=.{1,253}$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)(?:\.(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?))+$")


REQUIRED_RULESET_PAIRS = {
    ("reject.list", "REJECT"),
    ("proxy.list", "PROXY"),
    ("direct.list", "DIRECT"),
}
LAYOUT_MARKERS = {
    "layer_1": "# === Layer 1:",
    "layer_2": "# === Layer 2:",
    "layer_3": "# === Layer 3:",
    "layer_4": "# === Layer 4:",
    "layer_5": "# === Layer 5:",
    "original_rules_end": "# --- 5E.",
    "external_rulesets": "# --- External Rule Sets:",
    "geoip_asn_start": "# --- 5F-1.",
    "geoip_asn_cn": "# --- 5F-2.",
    "geoip_cn_rule": "GEOIP,CN,DIRECT",
    "layer_6": "# === Layer 6:",
    "final_rule": "FINAL,PROXY",
}


def inspect_rule_layout(config_text: str, observed: list[dict]) -> tuple[dict, list[str]]:
    """Enforce original rules -> config-ordered RULE-SETs -> ASN/GeoIP -> FINAL."""
    lines = config_text.splitlines()
    positions: dict[str, int] = {}
    errors: list[str] = []

    for key, marker in LAYOUT_MARKERS.items():
        matches = [
            index + 1 for index, raw in enumerate(lines)
            if raw.strip().startswith(marker)
        ]
        if len(matches) != 1:
            errors.append(f"layout marker {key!r} must appear exactly once; found {len(matches)}")
        else:
            positions[key] = matches[0]

    expected_marker_order = [
        "layer_1", "layer_2", "layer_3", "layer_4", "layer_5",
        "original_rules_end", "external_rulesets", "geoip_asn_start",
        "geoip_asn_cn", "geoip_cn_rule", "layer_6", "final_rule",
    ]
    if all(key in positions for key in expected_marker_order):
        ordered_positions = [positions[key] for key in expected_marker_order]
        if ordered_positions != sorted(ordered_positions):
            errors.append("routing layer markers are not in original-rules -> rule-sets -> ASN/GeoIP -> FINAL order")

    observed_order = [(item["file"], item["policy"]) for item in sorted(observed, key=lambda x: x["line"])]
    if len(observed_order) != 3 or set(observed_order) != REQUIRED_RULESET_PAIRS:
        errors.append(
            "external RULE-SET references must contain each managed file/policy pair exactly once; "
            f"observed={observed_order}"
        )
    # The actual order in ss.conf is authoritative. It is recorded and used
    # for precedence checks below; the validator must not impose a second order.

    ref_lines = [item["line"] for item in sorted(observed, key=lambda x: x["line"])]
    if all(key in positions for key in ("original_rules_end", "external_rulesets", "geoip_asn_start")):
        if not (
            positions["original_rules_end"] < positions["external_rulesets"]
            < (ref_lines[0] if ref_lines else 10**12)
            <= (ref_lines[-1] if ref_lines else -1)
            < positions["geoip_asn_start"]
        ):
            errors.append(
                "all original explicit rules must precede the external RULE-SET block, "
                "and all three external sets must precede the ASN/GeoIP fallback"
            )

        if ref_lines:
            between = [
                (index + 1, raw.strip())
                for index, raw in enumerate(lines)
                if ref_lines[-1] < index + 1 < positions["geoip_asn_start"]
                and raw.strip()
                and not raw.strip().startswith("#")
                and not raw.strip().startswith("[")
            ]
            if between:
                errors.append(
                    "active routing rules appear between external RULE-SETs and ASN/GeoIP fallback: "
                    + repr(between[:5])
                )

    active_rules = []
    in_rule_section = False
    active_prefixes = (
        "DOMAIN,", "DOMAIN-SUFFIX,", "DOMAIN-KEYWORD,", "IP-CIDR,",
        "IP-CIDR6,", "IP-ASN,", "GEOIP,", "RULE-SET,", "FINAL,",
        "AND,", "OR,", "NOT,", "URL-REGEX,",
    )
    for index, raw in enumerate(lines):
        stripped = raw.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_rule_section = stripped[1:-1].strip().lower() == "rule"
            continue
        if in_rule_section and stripped and not stripped.startswith("#") and stripped.upper().startswith(active_prefixes):
            active_rules.append((index + 1, stripped))
    final_lines = [line for line, raw in active_rules if raw.upper() == "FINAL,PROXY"]
    if len(final_lines) != 1:
        errors.append(f"FINAL,PROXY must appear exactly once; found {len(final_lines)}")
    elif active_rules and active_rules[-1][0] != final_lines[0]:
        errors.append("FINAL,PROXY must be the last active routing rule")

    layout = {
        "expected_ruleset_order": "authoritative order from shadowrocket/ss.conf",
        "observed_ruleset_order": [f"{file}:{policy}" for file, policy in observed_order],
        "marker_lines": positions,
        "passed": not errors,
    }
    return layout, errors


def extract_rule_set_references(config_text: str) -> list[dict]:
    refs, in_rules = [], False
    for line_no, raw in enumerate(config_text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            in_rules = line[1:-1].strip().lower() == "rule"
            continue
        if not in_rules or not line.upper().startswith("RULE-SET,"):
            continue
        fields = [part.strip() for part in line.split(",")]
        if len(fields) < 3:
            refs.append({"line": line_no, "raw": line, "error": "RULE-SET requires URL and policy"})
        else:
            refs.append({"line": line_no, "url": fields[1], "policy": fields[2].upper(), "raw": line})
    return refs

def inspect(config_text: str, manifest: dict, ruleset_dir: Path = RULESETS) -> dict:
    refs = extract_rule_set_references(config_text)
    errors, observed, seen_urls, seen_files = [], [], set(), set()
    for ref in refs:
        if "error" in ref:
            errors.append(f"line {ref['line']}: {ref['error']}")
            continue
        url = urlparse(ref["url"])
        filename = url.path.rsplit("/", 1)[-1].lower()
        expected_policy = POLICY_BY_FILE.get(filename)
        if url.scheme != "https" or url.netloc.lower() != "raw.githubusercontent.com":
            errors.append(f"line {ref['line']}: RULE-SET host must be raw.githubusercontent.com")
        if not url.path.startswith(EXPECTED_REPO_PATH):
            errors.append(f"line {ref['line']}: RULE-SET path is outside this repository's rulesets directory")
        if expected_policy is None:
            errors.append(f"line {ref['line']}: unknown managed ruleset filename {filename!r}")
        elif ref["policy"] != expected_policy:
            errors.append(f"line {ref['line']}: {filename} is paired with {ref['policy']}, expected {expected_policy}")
        if ref["url"] in seen_urls:
            errors.append(f"line {ref['line']}: duplicate RULE-SET URL")
        if filename in seen_files:
            errors.append(f"line {ref['line']}: duplicate RULE-SET file reference")
        seen_urls.add(ref["url"])
        seen_files.add(filename)
        observed.append({"line": ref["line"], "url": ref["url"], "file": filename, "policy": ref["policy"]})

    layout, layout_errors = inspect_rule_layout(config_text, observed)
    errors.extend(layout_errors)

    expected_files = set(POLICY_BY_FILE)
    if seen_files != expected_files:
        errors.append(f"configured RULE-SET files differ: missing={sorted(expected_files-seen_files)}, extra={sorted(seen_files-expected_files)}")
    if {str(x).lower() for x in manifest.get("outputs", [])} != expected_files:
        errors.append("manifest outputs do not match the three managed RULE-SET files")

    file_stats = {}
    domain_owners = {}
    manifest_counts = manifest.get("rule_count", {})
    for filename, policy in POLICY_BY_FILE.items():
        path = ruleset_dir / filename
        if not path.is_file():
            errors.append(f"missing generated ruleset file: {filename}")
            continue
        lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        parsed = [DOMAIN_LINE.fullmatch(x) for x in lines]
        valid = [(m.group(1).upper(), m.group(2).lower()) for m in parsed if m]
        invalid_count = len(lines) - len(valid)
        if invalid_count:
            errors.append(f"{filename} contains {invalid_count} unsupported or malformed domain-scope entries")
        for kind, domain in valid:
            if not DOMAIN_RE.fullmatch(domain):
                errors.append(f"{filename} contains invalid domain: {domain}")
        if len(valid) != len(set(valid)):
            errors.append(f"{filename} contains duplicate domain scopes")
        for kind, domain in sorted(set(valid)):
            domain_owners.setdefault((kind, domain), []).append(policy)
        if len(lines) != int(manifest_counts.get(policy, -1)):
            errors.append(f"{filename} line count {len(lines)} differs from manifest {policy} count {manifest_counts.get(policy)}")
        file_stats[filename] = {
            "policy": policy, "line_count": len(lines),
            "valid_domain_lines": len(valid),
            "exact_domain_lines": sum(1 for kind, _ in valid if kind == "DOMAIN"),
            "suffix_domain_lines": sum(1 for kind, _ in valid if kind == "DOMAIN-SUFFIX"),
        }

    cross_file_duplicates = []
    cross_policy_conflicts = []
    precedence_resolved_overlaps = []
    entries = [
        {"kind": kind, "domain": domain, "policy": policy}
        for (kind, domain), policies in domain_owners.items()
        for policy in policies
    ]
    for key, policies in sorted(domain_owners.items()):
        if len(policies) > 1:
            cross_file_duplicates.append({"kind": key[0], "domain": key[1], "policies": policies})
    policy_order = {
        item["policy"]: index
        for index, item in enumerate(sorted(observed, key=lambda x: x["line"]))
    }

    def intersects(left, right):
        a, b = left["domain"], right["domain"]
        if left["kind"] == "DOMAIN" and right["kind"] == "DOMAIN":
            return a == b
        if left["kind"] == "DOMAIN":
            return a == b or a.endswith("." + b)
        if right["kind"] == "DOMAIN":
            return b == a or b.endswith("." + a)
        return a == b or a.endswith("." + b) or b.endswith("." + a)

    def contains(outer, inner):
        if outer["kind"] == "DOMAIN":
            return inner["kind"] == "DOMAIN" and outer["domain"] == inner["domain"]
        return inner["domain"] == outer["domain"] or inner["domain"].endswith("." + outer["domain"])

    for i, left in enumerate(entries):
        for right in entries[i+1:]:
            if left["policy"] == right["policy"] or not intersects(left, right):
                continue
            left_first = policy_order.get(left["policy"], 999) <= policy_order.get(right["policy"], 999)
            earlier, later = (left, right) if left_first else (right, left)
            if contains(earlier, later):
                conflict = {"earlier": earlier, "later": later}
                if conflict not in cross_policy_conflicts:
                    cross_policy_conflicts.append(conflict)
            else:
                resolved = {"earlier": earlier, "later": later}
                if resolved not in precedence_resolved_overlaps:
                    precedence_resolved_overlaps.append(resolved)
    for item in cross_file_duplicates:
        if len(set(item["policies"])) == 1:
            errors.append("cross-file duplicate domain scope under same policy: " + item["kind"] + "," + item["domain"])
    for item in cross_policy_conflicts:
        errors.append(
            "cross-file scope conflict: earlier " + item["earlier"]["kind"] + "," + item["earlier"]["domain"]
            + " (" + item["earlier"]["policy"] + ") contains later "
            + item["later"]["kind"] + "," + item["later"]["domain"]
            + " (" + item["later"]["policy"] + "); later rule cannot override first-match precedence"
        )

    return {
        "schema_version": 2, "config_path": "shadowrocket/ss.conf",
        "config_rule_set_reference_count": len(refs), "references": observed,
        "managed_output_files": sorted(expected_files), "file_stats": file_stats,
        "cross_file_duplicates": cross_file_duplicates,
        "cross_policy_conflicts": cross_policy_conflicts,
        "precedence_resolved_overlaps": precedence_resolved_overlaps,
        "layout": layout,
        "errors": errors, "passed": not errors,
        "scope": "read-only; validates DOMAIN and DOMAIN-SUFFIX scopes, cross-policy scope intersections, and does not edit config, DNS, MITM, or RULE-SET references"
    }

def main() -> int:
    report = inspect(CONFIG.read_text(encoding="utf-8-sig"), json.loads(MANIFEST.read_text(encoding="utf-8")))
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# RULE-SET reference audit", "",
        "- Config authority: shadowrocket/ss.conf",
        f"- RULE-SET references: {report['config_rule_set_reference_count']}",
        f"- Result: {'PASS' if report['passed'] else 'FAIL'}",
        f"- External RULE-SET order: {' -> '.join(item.split(':', 1)[1] for item in report['layout']['observed_ruleset_order'])}",
        f"- Placement audit: {'PASS' if report['layout']['passed'] else 'FAIL'}", "", "## References", ""
    ]
    lines += [f"- line {x['line']}: {x['file']} -> {x['policy']}" for x in report["references"]]
    lines += ["", "## Generated file counts", ""]
    lines += [f"- {name}: {stats['line_count']} lines; policy {stats['policy']}" for name, stats in sorted(report["file_stats"].items())]
    lines += ["", "## Cross-file duplicates", ""]
    lines += ["- " + x["domain"] + ": " + ", ".join(x["policies"]) for x in report["cross_file_duplicates"]] or ["- None"]
    lines += ["", "## Precedence-resolved overlaps", ""]
    lines += [
        f"- {x['earlier']['kind']},{x['earlier']['domain']} ({x['earlier']['policy']}) precedes "
        f"{x['later']['kind']},{x['later']['domain']} ({x['later']['policy']})"
        for x in report["precedence_resolved_overlaps"]
    ] or ["- None"]
    lines += ["", "## Findings", ""]
    lines += [f"- {x}" for x in report["errors"]] or ["- No inconsistencies detected."]
    lines += ["", "Read-only audit; no config or RULE-SET references were changed.", ""]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "reference_count": report["config_rule_set_reference_count"], "layout": report["layout"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
