---
status: accepted
date: 2026-10-27
decision-makers: ["Na'aman Hirschfeld"]
---

# Language tooling policy

## Context and Problem Statement

Repositories used different tools for the same job: several Python type checkers, several ways to test shell scripts,
and different pnpm versions. Shared CI, shared tasks and reviews had to handle every combination.

## Considered Options

* One tool per job across the org: Pyrefly for Python types, Bats for shell tests, pnpm 12 for Node packages
* Each repository chooses its own tools

## Decision Outcome

Chosen option: "One tool per job across the org: Pyrefly for Python types, Bats for shell tests, pnpm 12 for Node
packages", because shared CI actions, task sets and rules can then assume one tool.

Pyrefly (`pyrefly check`) is the only Python type checker; mypy and pyright are not added. Bats (bats-core) is the only
shell test framework, run through the shared `install-bats` and `run-bats` actions. pnpm, at the 12.x version the
toolchain baseline pins, manages Node packages with a committed lockfile. The policy was settled in steps between
October 22 and October 27, 2026; this record is dated to the last.

### Consequences

* Good, because shared actions and task sets support one tool per job.
* Bad, because a repository that used another tool has to migrate.

### Confirmation

`modules/languages/rules/python.md` (Pyrefly, from `xberg-io/agent-conventions@395b17f`),
`modules/languages/rules/shell.md` (Bats, from `xberg-io/agent-conventions@4798e26`),
`modules/languages/rules/typescript.md` (pnpm), and `pnpm = "12.15.0"` in xberg-io/toolchains `baseline.toml`
(from `xberg-io/toolchains@61f3852`).
