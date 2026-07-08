---
priority: medium
---

# Taskfile Structure

All repos use [Taskfile.yaml](https://taskfile.dev) with the `task` CLI. Always prefer `task` commands over raw tool invocations.

- **Discovery:** `task --list` shows all available tasks
- **Common tasks:** `task setup`, `task build`, `task test`, `task lint`, `task format`, `task cov:all`, `task bench`
- **Language-scoped:** `task rust:test`, `task python:lint`, `task node:build`, etc.
- **Core build:** `task build` is core-only. Use `task build:bindings` for language bindings and `task build:all` for core plus bindings.
- **Build profiles:** `BUILD_PROFILE` supports dev/release/ci variants — `BUILD_PROFILE=release task build`, `task build:release`, or matching explicit binding/all variants.
- **Alef regeneration:** `task alef:generate` runs `alef all --clean`; it regenerates Alef-managed files (with formatting) without compiling bindings.
- **Alef formatting:** `task alef:format` runs Alef post-generation formatters explicitly. `task format` excludes Alef formatting.
- **Alef build:** `task alef:build` and `task build:bindings` compile language bindings explicitly; `task build:all` includes core and bindings.
- **Alef verification:** `task alef:verify` checks generated output freshness when needed; do not hide verification inside fast regeneration.
- **E2E tasks:** repos with generated e2e suites expose `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all`. Do not add legacy aliases.
- **Lock files:** always commit lock files (uv.lock, pnpm-lock.yaml, go.sum, Cargo.lock, composer.lock) for reproducible builds.
- **Discipline:** never use manual commands instead of `task`, never hardcode paths, never skip lock-file commits.
