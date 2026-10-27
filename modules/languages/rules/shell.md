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
- A new or changed script ships with its Bats tests in the same change. Run them through the repo's Bats task; CI installs Bats with `xberg-io/actions/install-bats` and runs suites with `xberg-io/actions/run-bats`.
- Vendor `xberg-io/actions` `bats-lib/xberg-bats/` as `tests/lib/xberg-bats` under the suites' directory (for example `scripts/tests/lib/xberg-bats`) and load it with `bats_load_library xberg-bats`; do not add a local helper set. Set `BATS_LIB_PATH` in the Bats task and `lib-path` in CI, or a suite passes locally and fails in CI.
- A test never depends on what the host has installed: stub commands on `PATH` instead.
