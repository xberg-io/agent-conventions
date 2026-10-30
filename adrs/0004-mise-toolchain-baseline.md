---
status: accepted
date: 2026-10-27
decision-makers: ["Na'aman Hirschfeld"]
---

# Mise toolchain baseline

## Context and Problem Statement

Repositories installed their languages and CLIs in their own way: setup actions per language in CI, Homebrew, `cargo
install` or `rustup` locally. Versions differed between repositories and between a laptop and CI, so the same task
could pass in one place and fail in another.

## Considered Options

* mise with a committed lock in every repository that installs tools, following one org baseline in
  xberg-io/toolchains
* Per-language setup actions and local installs, versioned per repository

## Decision Outcome

Chosen option: "mise with a committed lock in every repository that installs tools, following one org baseline in
xberg-io/toolchains", because one version set, installed the same way locally and in CI, removes the version drift.

`baseline.toml` in xberg-io/toolchains holds the canonical versions. A repository's `mise.toml` uses them exactly,
except for an override with a reason in its `toolchains.toml`, which also names the baseline tag it follows.
`toolchains.py sync` moves a repository to a new baseline and `toolchains.py check` fails on drift. Rust stays in
`rust-toolchain.toml`, checked against the baseline's `rust`.

### Consequences

* Good, because a version moves once, in the baseline, and every repository follows by tag.
* Good, because CI and local runs install the same locked versions.
* Bad, because some tools cannot yet be locked on every platform and stay on their setup actions.

### Confirmation

xberg-io/toolchains `baseline.toml`, `scripts/toolchains.py` and `README.md`; the `check-toolchain` action in
xberg-io/actions gates drift in CI. The `toolchain-management` rule (`modules/core/rules/toolchain-management.md`)
applies it in every consumer. Introduced in `xberg-io/toolchains@61f3852`.
