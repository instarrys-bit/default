# Shadowrocket Automation Core

This repository contains four maintained components:

1. **Unattended automation** — GitHub Actions, Watchdog, source collection, deterministic review, human-approval gates, task scheduling, audit, validation, recovery, and tests.
2. **User configuration** — `modules/uu.conf`. This is user-owned and must remain unchanged by automation.
3. **Modules and mapped scripts** — `modules/AdBlock.sgmodule` and its mapped script at `modules/adblock/scripts/Clean_Pro.js`.
4. **Published rule sets** — `rulesets/direct.list`, `rulesets/proxy.list`, `rulesets/reject.list`, and `rulesets/manifest.json`.

## Subscription

Configuration:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/uu.conf`

Module:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/AdBlock.sgmodule`

Rule sets are built and validated by the automation system. The automation must not modify the user-owned configuration, module, or mapped script. Production rule publication is limited to the authorized rule-set paths.

Operational source catalogs, review state, reports, and dashboard artifacts are retained only where required by the unattended automation workflows.
