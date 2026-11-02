# Shadowrocket Ruleset Automation

A deterministic project for collecting, reviewing, building, validating, and publishing three Shadowrocket domain-rule policies: **DIRECT**, **PROXY**, and **REJECT**.

## Documentation

- [Documentation index](docs/README.md)
- [Quick Start](docs/01-quick-start.md)
- [Project Architecture](docs/02-project-architecture.md)
- [Automation Pipeline](docs/03-automation-pipeline.md)
- [Rule Review](docs/04-rule-review.md)
- [Source Governance](docs/05-source-governance.md)
- [Capacity and Lifecycle](docs/06-capacity-and-lifecycle.md)
- [Security and Permissions](docs/07-security-and-permissions.md)
- [Operations](docs/08-operations.md)
- [Development and Maintenance](docs/09-development-and-maintenance.md)

## Published rulesets

| Policy | File |
|---|---|
| DIRECT | [rulesets/direct.list](rulesets/direct.list) |
| PROXY | [rulesets/proxy.list](rulesets/proxy.list) |
| REJECT | [rulesets/reject.list](rulesets/reject.list) |

Manifest: [rulesets/manifest.json](rulesets/manifest.json).

## Main configuration

[shadowrocket/ss.conf](shadowrocket/ss.conf) is the user-owned authoritative configuration.

Subscription URL:

`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

Automation may read this file for integrity and conflict checks. It must never modify, stage, or commit it.

## Operational status

- [Project status](reports/project-status.md)
- [Latest lifecycle report](reports/lifecycle/latest.md)
- [Configuration conflict report](reports/ruleset-config-conflict-sync.md)

## Non-negotiable boundaries

- Exactly three policies: DIRECT, PROXY, and REJECT.
- Deterministic review with no AI/LLM dependency.
- A combined publication ceiling of 30,000 unique rules; eligible overflow remains queued.
- Conservative lifecycle deletion with auditable recovery.
- The main configuration remains user-controlled and read-only to automation.
- Static validation does not replace target-device testing.
