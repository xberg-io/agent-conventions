---
type: Decision
title: Toolchain Management
x-ai-rulez:
  kind: rule
  id: toolchain-management
  metadata:
    priority: high
---

- `mise.toml` and the committed `mise.lock` pin every tool and language; install with `mise install`, never ad hoc (`brew`, `apt`, `cargo install`, `go install`, `rustup`, sdkman) in setup tasks or CI.
- The one exception is ai-rulez: never pinned, always the latest release (org ADR-0015, ADR-0017): `npx -y ai-rulez@latest` in tasks and hooks (poly's `npm` channel), `setup-ai-rulez@v1` in CI.
- Rust's channel, components and targets stay in `rust-toolchain.toml`; `rust` is never in `mise.toml`.
- Follow the `xberg-io/toolchains` baseline tag in `toolchains.toml`, deviating only by a reasoned override there. Change versions with `toolchains.py sync` and `mise lock`; never hand-edit `mise.lock`.
- CI: `xberg-io/actions/setup-mise@v1` and the `check-toolchain@v1` gate. Kept on their setup actions: PHP, Swift, R, Android SDK/NDK, Dart/Flutter, BEAM (until evaluated) and the lock gaps (`dotnet`, `rust`; `aws-cli`, `bats`, `ruby` on Windows; `cargo-sort` on linux-arm64). Procedures: the `mise-toolchains` skill.
