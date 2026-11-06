# Shadowrocket Automation Core

This repository maintains four functional areas:

1. **Unattended automation** — Watchdog, task queue, source discovery and collection, deterministic filtering, human-approval gates, rule production, validation, publication, recovery, audit, dashboard, and tests.
2. **User configuration** — `modules/uu.conf`. Its user-defined rules, code, and original functions are protected from automation changes.
3. **Modules and mapped scripts** — `modules/AdBlock.sgmodule` and its mapped script, `modules/adblock/scripts/Clean_Pro.js`.
4. **Rule sets** — `rulesets/direct.list`, `rulesets/proxy.list`, `rulesets/reject.list`, and their required manifests and lifecycle state.

## Subscription

Configuration:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/uu.conf`

Module:
`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/AdBlock.sgmodule`

Automation may audit the user configuration but must not modify its user-defined rules, code, or original functions. Module and script files are maintained separately from rule-set production. Production publication must validate its exact output allowlist and independently verify the remote rule sets.
