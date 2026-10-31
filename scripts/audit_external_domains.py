#!/usr/bin/env python3
"""Read-only audit of the pinned sr-adblock lite domain dataset.

This script never executes downloaded content and never edits Shadowrocket config.
A changed upstream Git blob is treated as a review event, not auto-accepted.
"""
from __future__ import annotations

import hashlib
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SOURCE_URL = (
    "https://raw.githubusercontent.com/ithtelab/sr-adblock/"
    "release/ruleset/ad-domain-lite.list"
)
EXPECTED_GIT_BLOB_SHA1 = "ec23c2d1280ea4a59717816716b8ccb569dac624"
EXPECTED_ENTRIES = 56516
MAX_BYTES = 2_000_000
OUTPUT = Path("reports/external-domain-audit.md")
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+$"
)


def git_blob_sha1(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "Shadowrocket-domain-audit/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final = urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise SystemExit(f"ERROR: unexpected download destination: {response.geturl()}")
        data = response.read(MAX_BYTES + 1)

    if len(data) > MAX_BYTES:
        raise SystemExit("ERROR: source exceeds the 2 MB safety limit")

    actual_sha = git_blob_sha1(data)
    text = data.decode("utf-8")
    active: list[tuple[int, str]] = []
    invalid: list[tuple[int, str]] = []
    seen: set[str] = set()
    duplicates: list[tuple[int, str]] = []
    lines = text.splitlines()

    for number, raw in enumerate(lines, 1):
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if value != raw or any(ch.isspace() for ch in value):
            invalid.append((number, raw))
            continue
        domain = value[1:] if value.startswith(".") else value
        if not DOMAIN_RE.fullmatch(domain):
            invalid.append((number, raw))
            continue
        key = value.lower()
        if key in seen:
            duplicates.append((number, raw))
        seen.add(key)
        active.append((number, value))

    drift = actual_sha != EXPECTED_GIT_BLOB_SHA1
    count_changed = len(active) != EXPECTED_ENTRIES
    status = "REVIEW REQUIRED" if drift or count_changed or invalid or duplicates else "PASS"
    report = [
        "# External domain source audit",
        "",
        f"- Audit time: {datetime.now(timezone.utc).isoformat()}",
        f"- Source: {SOURCE_URL}",
        f"- Expected Git blob SHA-1: `{EXPECTED_GIT_BLOB_SHA1}`",
        f"- Observed Git blob SHA-1: `{actual_sha}`",
        f"- Result: **{status}**",
        f"- File bytes: {len(data)}",
        f"- Physical lines: {len(lines)}",
        f"- Valid domain entries: {len(active)}",
        f"- Expected domain entries: {EXPECTED_ENTRIES}",
        f"- Duplicate entries: {len(duplicates)}",
        f"- Invalid entries: {len(invalid)}",
        "",
        "## Invalid entry sample",
        "",
    ]
    report.extend(
        f"- Line {number}: `{value[:180]}`"
        for number, value in invalid[:50]
    ) or report.append("- None")
    report.extend(["", "## Duplicate entry sample", ""])
    report.extend(
        f"- Line {number}: `{value[:180]}`"
        for number, value in duplicates[:50]
    ) or report.append("- None")
    report.extend([
        "",
        "## Policy boundary",
        "",
        "- This is a candidate-data audit only; no policy is inferred.",
        "- No DIRECT, PROXY, or REJECT rules are generated.",
        "- No DNS, proxy, node, subscription, script, module, MITM, or rewrite content is imported.",
        "- The canonical `shadowrocket/ss.conf` is not read or modified by this script.",
        "- A source hash change requires manual review and an explicit pin update.",
        "",
    ])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(report), encoding="utf-8")
    print("\n".join(report))
    return 1 if drift or count_changed or invalid or duplicates else 0


if __name__ == "__main__":
    raise SystemExit(main())
