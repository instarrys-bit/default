#!/usr/bin/env python3
"""Lightweight structural checks for the canonical Shadowrocket config.

This is not a full Shadowrocket parser and does not replace device testing.
"""
from pathlib import Path
import sys

path = Path("sources/baseline/ss.conf")
if not path.is_file():
    sys.exit("ERROR: shadowrocket/ss.conf is missing")

text = path.read_text(encoding="utf-8")
if not text.strip():
    sys.exit("ERROR: config is empty")

required_sections = ("[General]", "[Rule]", "[Host]")
positions = {}
for section in required_sections:
    if section not in text:
        sys.exit(f"ERROR: required section missing: {section}")
    positions[section] = text.index(section)

if positions["[General]"] > positions["[Rule]"] or positions["[Rule]"] > positions["[Host]"]:
    sys.exit("ERROR: expected section order is [General], [Rule], [Host]")

rule_block = text.split("[Rule]", 1)[1].split("[Host]", 1)[0]
rule_lines = [
    line.strip() for line in rule_block.splitlines()
    if line.strip() and not line.lstrip().startswith("#")
]
if not rule_lines:
    sys.exit("ERROR: [Rule] section has no active rules")

malformed = [
    (number, line)
    for number, line in enumerate(rule_block.splitlines(), 1)
    if line.strip() and not line.lstrip().startswith("#") and "," not in line
]
if malformed:
    sample = "\n".join(f"  Rule-section line {n}: {line}" for n, line in malformed[:10])
    sys.exit("ERROR: rule lines must contain comma-separated fields:\n" + sample)

print(f"OK: structural checks passed; {len(rule_lines)} active rules.")
print("NOTE: this does not validate Shadowrocket-specific semantics or live traffic.")
