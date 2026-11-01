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
DOMAIN_LINE = re.compile(r"^DOMAIN,([A-Za-z0-9.-]+)$", re.IGNORECASE)

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

    expected_files = set(POLICY_BY_FILE)
    if seen_files != expected_files:
        errors.append(f"configured RULE-SET files differ: missing={sorted(expected_files-seen_files)}, extra={sorted(seen_files-expected_files)}")
    if {str(x).lower() for x in manifest.get("outputs", [])} != expected_files:
        errors.append("manifest outputs do not match the three managed RULE-SET files")

    file_stats = {}
    manifest_counts = manifest.get("rule_count", {})
    for filename, policy in POLICY_BY_FILE.items():
        path = ruleset_dir / filename
        if not path.is_file():
            errors.append(f"missing generated ruleset file: {filename}")
            continue
        lines = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        domains = [DOMAIN_LINE.fullmatch(x).group(1).lower() for x in lines if DOMAIN_LINE.fullmatch(x)]
        if len(domains) != len(lines):
            errors.append(f"{filename} contains {len(lines)-len(domains)} non-exact DOMAIN entries")
        if len(domains) != len(set(domains)):
            errors.append(f"{filename} contains duplicate domains")
        if len(lines) != int(manifest_counts.get(policy, -1)):
            errors.append(f"{filename} line count {len(lines)} differs from manifest {policy} count {manifest_counts.get(policy)}")
        file_stats[filename] = {"policy": policy, "line_count": len(lines), "valid_domain_lines": len(domains)}

    return {
        "schema_version": 1, "config_path": "shadowrocket/ss.conf",
        "config_rule_set_reference_count": len(refs), "references": observed,
        "managed_output_files": sorted(expected_files), "file_stats": file_stats,
        "errors": errors, "passed": not errors,
        "scope": "read-only; does not edit config, DNS, MITM, or RULE-SET references"
    }

def main() -> int:
    report = inspect(CONFIG.read_text(encoding="utf-8-sig"), json.loads(MANIFEST.read_text(encoding="utf-8")))
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lines = [
        "# RULE-SET reference audit", "",
        "- Config authority: shadowrocket/ss.conf",
        f"- RULE-SET references: {report['config_rule_set_reference_count']}",
        f"- Result: {'PASS' if report['passed'] else 'FAIL'}", "", "## References", ""
    ]
    lines += [f"- line {x['line']}: {x['file']} -> {x['policy']}" for x in report["references"]]
    lines += ["", "## Generated file counts", ""]
    lines += [f"- {name}: {stats['line_count']} lines; policy {stats['policy']}" for name, stats in sorted(report["file_stats"].items())]
    lines += ["", "## Findings", ""]
    lines += [f"- {x}" for x in report["errors"]] or ["- No inconsistencies detected."]
    lines += ["", "Read-only audit; no config or RULE-SET references were changed.", ""]
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"passed": report["passed"], "reference_count": report["config_rule_set_reference_count"], "errors": report["errors"]}, ensure_ascii=False))
    return 0 if report["passed"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
