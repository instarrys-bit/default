# Adapter activation readiness policy

## Purpose

`scripts/audit_adapter_activation.py` is a read-only gate before any execution adapter is enabled. It cross-checks the program registry, execution adapter inventory, workflow dispatch correlation contracts, and the effective job-level permissions of the Watchdog queue supervisor.

It does not enable adapters, change caller allowlists, enqueue tasks, dispatch workflows, or modify repository files.

## Required conditions

A program is not eligible for orchestration unless:
- its program and adapter registrations match;
- its interface is reviewed for the correct adapter type;
- orchestration and adapter activation agree;
- caller allowlists are explicit and identical;
- the caller's effective job-level token has the scopes required for queue storage and dispatch;
- workflow targets are active, dispatchable, main-ref allowlisted, and uniquely correlated by task ID and attempt;
- Python targets have reviewed input/output contracts and an exact no-shell entrypoint.

The Watchdog queue job must explicitly declare `actions: write` and `contents: write`. Workflow-level permissions do not substitute for job-level permissions when a job declares its own permission block.

## Canary selection

The audit separately identifies workflows that are dispatchable, have correlation support, have a caller with the required scopes, and declare no write permissions or repository-publishing/downstream-dispatch side effects.

The approved low-privilege canary is `workflow_self_healing_tests`. Its target workflow token is read-only and its job runs deterministic tests. The only permitted caller is `workflow_automation_watchdog`, through the `task-queue-supervision` job, whose job-level permissions are limited to `actions:write` and `contents:write` for dispatch and queue persistence. The canary has a single attempt and no automatic retry. This activation does not enable any repair worker or the self-healing agent workflow.

## Current activation policy

All adapters remain disabled by default. By explicit user approval, exactly one canary is activated: `workflow_self_healing_tests`. All other adapters remain disabled. The read-only audit does not itself activate or trigger adapters; it only reports the configured state.
