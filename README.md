# Shadowrocket Ruleset Automation

A lightweight, deterministic project that collects, filters, and publishes three Shadowrocket rule sets: **DIRECT**, **PROXY**, and **REJECT**.

## Rule Set Pipeline

1. **Collect** — discover approved sources and gather domain candidates.
2. **Filter** — normalize candidates, compare evidence, resolve conflicts, and apply policy checks.
3. **Publish** — build, validate, and publish the three rule sets.

Published rule sets:

- [DIRECT](rulesets/direct.list)
- [PROXY](rulesets/proxy.list)
- [REJECT](rulesets/reject.list)

Manifest: [rulesets/manifest.json](rulesets/manifest.json).

## Shadowrocket Components

| Component | File | Description |
|---|---|---|
| Configuration | [modules/uu.conf](modules/uu.conf) | The main Shadowrocket configuration. It references and uses the published DIRECT, PROXY, and REJECT rule sets. |
| Module | [modules/AdBlock.sgmodule](modules/AdBlock.sgmodule) | The Shadowrocket ad-blocking module. It defines request rules and maps the cleaning script below. |
| Script | [modules/adblock/scripts/Clean_Pro.js](modules/adblock/scripts/Clean_Pro.js) | The script loaded by the module to process supported application and web responses. |

The configuration consumes the published rule sets. The module loads its associated script. These are separate functions: the rule-set automation publishes rule data and does not rewrite the configuration, module, or script.

Configuration subscription URL:

`https://raw.githubusercontent.com/instarrys-bit/default/main/modules/uu.conf`

## Automation and Documentation

GitHub Actions workflows and Python scripts manage source discovery, collection, deterministic review, rule building, validation, and publication.

- [Documentation](docs/README.md)
- [Project status](reports/project-status.md)
- [Latest lifecycle report](reports/lifecycle/latest.md)
- [Configuration conflict report](reports/ruleset-config-conflict-sync.md)

## Safety Boundaries

- Exactly three published policies: DIRECT, PROXY, and REJECT.
- Rule review is deterministic and has no AI/LLM classification dependency.
- The combined publication limit is 30,000 unique rules; qualified overflow remains queued.
- New REJECT rules require human approval.
- The main configuration is user-owned. Automation may audit it but must never modify it.
- Static validation does not replace testing in Shadowrocket on the target device.
