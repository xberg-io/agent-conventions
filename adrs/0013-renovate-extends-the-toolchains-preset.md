---
status: accepted
date: 2026-10-27
decision-makers: ["Na'aman Hirschfeld"]
---

# Renovate extends the toolchains preset

## Context and Problem Statement

The toolchain baseline (ADR-0004) moves tool versions only in xberg-io/toolchains. A dependency bot that bumps a
baseline tool in one repository from its upstream release creates drift that `toolchains.py check` then fails.

## Considered Options

* Renovate, extending the `github>xberg-io/toolchains` preset
* Renovate or Dependabot with per-repository rules

## Decision Outcome

Chosen option: "Renovate, extending the `github>xberg-io/toolchains` preset", because the preset turns off upstream
bumps for exactly the baseline tools, so the bot updates only what the repository owns.

A repository that runs a dependency bot runs Renovate and extends the preset. The preset (`default.json`) disables
`mise` updates for every tool in `baseline.toml` and groups the repository-owned mise tools. Baseline bumps happen in
xberg-io/toolchains, whose own Renovate config updates `baseline.toml`.

### Consequences

* Good, because the bot never proposes a baseline bump that the toolchain check would reject.
* Bad, because the preset must list exactly the baseline tools; a tool added to one and not the other drifts.
* Bad, because xberg-enterprise also runs Dependabot (`.github/dependabot.yml`), which the preset does not govern;
  that deviation is recorded or removed in its own log.

### Confirmation

xberg-io/toolchains `default.json`, with `tests/test_toolchains.py`
(`test_renovate_preset_disables_exactly_the_baseline_tools`) and the `renovate-config-validator` step in its CI. The
`renovate.json` of xberg-io/actions, xberg-io/alef and xberg-io/xberg-enterprise extend it. Introduced in
`xberg-io/toolchains@61f3852`.
