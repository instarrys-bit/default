# Shadowrocket Ruleset Automation

A lightweight, deterministic project for producing and publishing three Shadowrocket rule sets: **DIRECT**, **PROXY**, and **REJECT**.

## How it works

1. **Collect** — discover approved rule sources and collect domain candidates.
2. **Filter** — normalize candidates, compare evidence, resolve conflicts, and apply policy checks.
3. **Publish** — build, validate, and publish the three rule lists.

Published lists:

- [DIRECT](rulesets/direct.list)
- [PROXY](rulesets/proxy.list)
- [REJECT](rulesets/reject.list)

Manifest: [rulesets/manifest.json](rulesets/manifest.json).

## Components

| Component | File | Purpose |
|---|---|---|
| Module | [modules/AdBlock.sgmodule](modules/AdBlock.sgmodule) | Shadowrocket ad-block module; maps the cleaning script |
| Script | [modules/adblock/scripts/Clean_Pro.js](modules/adblock/scripts/Clean_Pro.js) | Handles supported app/web request and response filtering |
| Configuration | [modules/uu.conf](modules/uu.conf) | User-owned Shadowrocket configuration; consumes rulesets and remains read-only to automation |

The ruleset pipeline and the ad-block module/script are separate parts of the project. The pipeline maintains the published rule data; it does not rewrite the module, script, or user configuration.

Configuration subscription URL:

`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/uu.conf`

## Automation

The GitHub Actions workflows and Python scripts handle source discovery, collection, deterministic review, rule building, validation, and publication.

- [Documentation](docs/README.md)
- [Project status](reports/project-status.md)
- [Latest lifecycle report](reports/lifecycle/latest.md)
- [Configuration conflict report](reports/ruleset-config-conflict-sync.md)

## Safety boundaries

- Exactly three published policies: DIRECT, PROXY, and REJECT.
- Rule review is deterministic; no AI/LLM classification dependency.
- The combined publication limit is 30,000 unique rules; qualified overflow remains queued.
- New REJECT rules require human approval.
- `modules/uu.conf` is a user-owned file: automation may audit it but must never modify it.
- Static validation does not replace testing in Shadowrocket on the target device.
