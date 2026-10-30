---
status: accepted
date: 2026-07-02
decision-makers: ["Na'aman Hirschfeld"]
---

# Poly as the single lint and format gate

## Context and Problem Statement

Repositories ran linters and formatters through pre-commit hook managers (pre-commit, then prek), each with its own
long hook list, and no shared CI workflow was in use: `reusable-python-lint.yml` existed but had no callers.

## Considered Options

* poly, one linter and formatter configured by `poly.toml`, as both the hook and the CI gate
* prek or pre-commit hooks with a per-tool configuration

## Decision Outcome

Chosen option: "poly, one linter and formatter configured by `poly.toml`, as both the hook and the CI gate", because
the same binary and configuration decide the result in the hook and in CI.

### Consequences

* Good, because one `poly.toml` configures lint, format and hooks for every language in a repository.
* Good, because the hook and CI share the `poly.toml` configuration, and the reusable workflow's `poly-version`
  default is kept equal to the toolchain baseline.
* Bad, because a defect in poly blocks commits and CI in every repository at once.

### Confirmation

Each code repository commits a `poly.toml`. xberg-io/actions `reusable-validate.yml` runs `poly fmt --check .` and
`poly lint .` (`xberg-io/actions@7c202a9`), and the `poly-lint-format` skill documents it. The governance modules
replaced prek with poly in `xberg-io/agent-conventions@4b836b0`.
