---
type: Decision
title: Shell Conventions
paths:
  - "**/*.sh"
  - "**/*.bash"
  - "**/*.bats"
x-ai-rulez:
  kind: rule
  id: shell
  metadata:
    priority: high
---

- Bats (bats-core) is the only test framework for shell scripts. Do not add shunit2, ShellSpec, bash_unit, or a hand-rolled test script; a shell test is a `*.bats` file.
- A new or changed script ships with its Bats tests in the same change. Run them through the repo's Bats task (for example `task test:bats`); CI installs Bats with `xberg-io/actions/install-bats` and runs suites with `xberg-io/actions/run-bats`.
- Suites load the shared helpers with `bats_load_library xberg-bats` from the repo's committed copy of `xberg-io/actions` `bats-lib/` (`tests/lib/xberg-bats`), not a local helper set. Set `BATS_LIB_PATH` in the Taskfile and `lib-path` in CI, or a suite passes locally and fails in CI.
- A test never depends on what the host has installed: stub commands on `PATH` instead.
