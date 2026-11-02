# Development and Maintenance

## Change discipline

Before changing runtime behavior:

1. Inspect the current workflows, scripts, registries, state files, and tests.
2. Identify the exact behavior and data boundary affected.
3. Preserve the three-policy limit and protected main configuration.
4. Add or update deterministic regression tests.
5. Run relevant tests and static validation.
6. Review generated diffs and reports before publication.
7. Update the relevant documentation after behavior is verified.

Do not use documentation cleanup as an opportunity to refactor runtime code.

## Script responsibilities

The `scripts/` directory contains separate components for source discovery and assessment, registry handling, collection and parsing, deterministic review, policy/configuration overlap audits, lifecycle evaluation, ruleset building, status reporting, and validation.

Prefer the narrowest relevant script and test. Avoid duplicating policy logic in documentation or creating a second implementation of business rules in the README.

## Test coverage areas

The repository's test suite has covered source lineage, source admission, project status, capacity, baseline registration, configuration drift, deterministic review, lifecycle audit and gating, policy overlap, ruleset/configuration conflict synchronization, reference validation, suffix-scope safety, retry behavior, and workflow permission ordering.

A documentation-only change should not require runtime test changes. If a statement cannot be supported by current code or tests, label it as a design requirement rather than claiming it is verified production behavior.

## Documentation conventions

- Maintained project documentation is written in English.
- Use concise filenames in lowercase kebab-case.
- Keep the root README as a short landing page.
- Put design details and operating procedures in the relevant topic document.
- Keep generated reports under `reports/`; do not present generated output as normative policy.
- Preserve third-party source documents and license files.
- Update relative links when documents move.
- Avoid duplicating detailed specifications across multiple files.

## Completion checklist

- Root README is a concise English entry point.
- Every topic guide is linked from `docs/README.md`.
- Relative links resolve against the repository tree.
- Runtime files, rule lists, registries, generated state, and the main configuration remain untouched by documentation-only work.
- Documentation claims are consistent with inspected implementation and tests.