#!/usr/bin/env python3
"""Read-only structural and whitespace validation for Shadowrocket configs.

This checks common syntax invariants; it is not the official Shadowrocket parser
and cannot prove how an already-imported profile is displayed by the app.
"""
from pathlib import Path
import re
import sys

# The user's current managed config is the only authoritative validation target.
CONFIGS = (Path("shadowrocket/ss.conf"),)
POLICIES = {"DIRECT", "PROXY", "REJECT"}
KNOWN_TYPES = {
    "AND", "OR", "NOT", "DOMAIN", "DOMAIN-SUFFIX", "DOMAIN-KEYWORD",
    "IP-CIDR", "IP-CIDR6", "IP-ASN", "GEOIP", "RULE-SET",
    "USER-AGENT", "URL-REGEX", "FINAL", "DST-PORT",
}
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*$"
)
CONDITIONAL_RE = re.compile(
    r"^(?:AND|OR|NOT),\(\(.+\)\),(?:DIRECT|PROXY|REJECT)(?:,.*)?$",
    re.IGNORECASE,
)
BAD_SPACE_RE = re.compile(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000\uFEFF]")


def fail(path, errors):
    if errors:
        print(f"ERROR: {path}")
        for line_no, message, raw in errors[:30]:
            print(f"  line {line_no}: {message}: {raw!r}")
        if len(errors) > 30:
            print(f"  ... and {len(errors) - 30} more")
        return 1
    return 0


def validate(path):
    if not path.is_file():
        return [(0, "required config is missing", str(path))]

    content = path.read_text(encoding="utf-8")
    if not content.strip():
        return [(0, "config is empty", "")]

    lines = content.splitlines()
    section_positions = {}
    for i, raw in enumerate(lines):
        section = raw.strip()
        if re.fullmatch(r"\[[^\]]+\]", section):
            if section in section_positions:
                return [(i + 1, f"duplicate section {section}", raw)]
            section_positions[section] = i

    for required in ("[General]", "[Rule]", "[Host]"):
        if required not in section_positions:
            return [(0, f"required section missing: {required}", "")]

    if not (
        section_positions["[General]"] < section_positions["[Rule]"]
        < section_positions["[Host]"]
    ):
        return [(0, "expected section order is [General], [Rule], [Host]", "")]

    start = section_positions["[Rule]"] + 1
    end = next(
        (i for i in range(start, len(lines))
         if re.fullmatch(r"\s*\[[^\]]+\]\s*", lines[i])),
        len(lines),
    )
    errors = []
    seen = {}

    for index in range(start, end):
        raw = lines[index]
        stripped = raw.strip()
        line_no = index + 1
        if not stripped or stripped.startswith("#"):
            continue

        if raw != stripped:
            errors.append((line_no, "leading/trailing whitespace in rule", raw))
        if BAD_SPACE_RE.search(raw):
            errors.append((line_no, "non-standard/invisible whitespace", raw))
        if re.search(r"\s,|,\s", raw):
            errors.append((line_no, "whitespace adjacent to comma", raw))

        fields = [part.strip() for part in stripped.split(",")]
        rule_type = fields[0].upper()

        if rule_type not in KNOWN_TYPES:
            errors.append((line_no, "unknown rule type", raw))
            continue

        if stripped in seen:
            # Duplicate rules are redundant, but not a syntax failure: Shadowrocket
            # applies first-match order and the user-owned config is not auto-edited.
            print(f"WARNING: {path}:{line_no}: duplicate rule; first occurrence at line {seen[stripped]}")
        else:
            seen[stripped] = line_no

        if rule_type in {"AND", "OR", "NOT"}:
            if not CONDITIONAL_RE.fullmatch(stripped):
                errors.append((line_no, "invalid conditional-rule structure", raw))
            continue

        if rule_type == "URL-REGEX":
            if len(fields) != 3:
                errors.append((line_no, "URL-REGEX must have pattern and policy fields", raw))
            else:
                try:
                    re.compile(fields[1])
                except re.error as exc:
                    errors.append((line_no, f"invalid URL-REGEX pattern: {exc}", raw))
                if fields[2].upper() not in POLICIES:
                    errors.append((line_no, "invalid URL-REGEX policy", raw))
            continue

        if rule_type == "FINAL":
            if len(fields) != 2 or fields[1].upper() not in POLICIES:
                errors.append((line_no, "FINAL must be FINAL,DIRECT|PROXY|REJECT", raw))
            continue

        if rule_type == "DST-PORT":
            if len(fields) < 3:
                errors.append((line_no, "DST-PORT must include port and policy", raw))
            else:
                try:
                    port = int(fields[1])
                    if not 1 <= port <= 65535:
                        raise ValueError
                except ValueError:
                    errors.append((line_no, "DST-PORT port must be an integer from 1 to 65535", raw))
                if fields[2].upper() not in POLICIES:
                    errors.append((line_no, "invalid DST-PORT policy", raw))
            continue

        if len(fields) < 3:
            errors.append((line_no, "rule has fewer than three fields", raw))
            continue

        if rule_type in {"DOMAIN", "DOMAIN-SUFFIX"}:
            if not DOMAIN_RE.fullmatch(fields[1].lstrip(".")):
                errors.append((line_no, "invalid domain field", raw))
            if fields[2].upper() not in POLICIES:
                errors.append((line_no, "invalid domain policy", raw))

    return errors


def main():
    failures = 0
    for config in CONFIGS:
        errors = validate(config)
        failures += fail(config, errors)
        if not errors:
            print(f"OK: {config}; rule whitespace and structural checks passed.")
    if failures:
        sys.exit(1)
    print("NOTE: static checks do not replace Shadowrocket app/device validation.")


if __name__ == "__main__":
    main()
