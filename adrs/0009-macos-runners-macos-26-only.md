---
status: accepted
date: 2026-10-28
decision-makers: ["Na'aman Hirschfeld"]
---

# macOS runners macos-26 only

## Context and Problem Statement

GitHub deprecated the macOS 14 runner image. Workflows used `macos-latest` and `macos-15-intel`, so the
architecture and OS a darwin job ran on depended on the label and on when GitHub moved `latest`.

## Considered Options

* `macos-26` for Apple silicon and `macos-26-intel` for Intel, explicitly
* `macos-latest`
* Keep the per-workflow labels

## Decision Outcome

Chosen option: "`macos-26` for Apple silicon and `macos-26-intel` for Intel, explicitly", because a fixed label pins
both the OS and the architecture, and the move off macOS 14 was required anyway.

Darwin CI and builds run on `macos-26` and `macos-26-intel` only; `aarch64-apple-darwin` builds on `macos-26`.

### Consequences

* Good, because every darwin job states its architecture and OS.
* Bad, because the labels move by hand when GitHub retires the image.

### Confirmation

xberg-io/actions `CHANGELOG.md` (1.32.0) and its reusable workflows (`reusable-cli-release.yml`,
`reusable-binstall-verify.yml`), which build `aarch64-apple-darwin` on `macos-26`. The change landed in
`xberg-io/actions@d29bbbc` ("move macOS runners to macos-26 and macos-26-intel").
