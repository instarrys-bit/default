# Quick Start

## Purpose

This repository independently collects, reviews, builds, validates, and publishes three Shadowrocket domain-rule policies:

- **DIRECT** — connect directly.
- **PROXY** — use a proxy.
- **REJECT** — block the domain.

No additional routing policy may be introduced by this automation.

## Rule lists

| Policy | Published file |
|---|---|
| DIRECT | [direct.list](../rulesets/direct.list) |
| PROXY | [proxy.list](../rulesets/proxy.list) |
| REJECT | [reject.list](../rulesets/reject.list) |

See the [manifest](../rulesets/manifest.json) for publication metadata.

## Main configuration

The authoritative user-owned configuration is [shadowrocket/ss.conf](../shadowrocket/ss.conf).

Subscription URL:

`https://raw.githubusercontent.com/instarrys-bit/default/main/shadowrocket/ss.conf`

Automation may read the file for integrity and conflict checks. It must not modify, stage, or commit it. Moving scripts or modules into this repository does not enable them or change DNS, routing, or MITM settings.

## Optional modules

Assets under `modules/` are optional and are not automatically enabled. Repository presence does not prove compatibility or device-side effectiveness. Review [Security and Permissions](07-security-and-permissions.md) before enabling them.

## Before relying on a ruleset

Static validation is not a substitute for testing on the target device. Subscribe separately, observe essential apps and system services, and confirm behavior before long-term use.

## Status

- [Project status](../reports/project-status.md)
- [Latest lifecycle report](../reports/lifecycle/latest.md)
- [Configuration conflict report](../reports/ruleset-config-conflict-sync.md)