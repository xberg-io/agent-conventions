---
type: Playbook
title: Taskfile Structure
description: Standard Taskfile conventions across xberg-io repos — task discovery, common and language-scoped tasks, build profiles, the alef and e2e task families, lock-file discipline. Load when running or adding tasks, choosing between task commands, or deciding how to build/test/regenerate a repo.
x-ai-rulez:
  kind: skill
  id: taskfile-structure
  metadata:
    name: taskfile-structure
---

# Taskfile Structure

All repos use [Taskfile.yaml](https://taskfile.dev) with the `task` CLI. Always prefer `task` commands over raw tool invocations.

- **Discovery:** `task --list` shows all available tasks
- **Common tasks:** `task setup`, `task build`, `task test`, `task lint`, `task format`, `task cov:all`, and a repo-specific benchmark task (e.g. `benchmark:run`, `bench:run`, `rust:bench` — check `task --list`)
- **Language-scoped:** namespaced per language, but the set is NOT uniform -- only some
  languages expose a given verb. In xberg, `task rust:test`, `task swift:test`,
  `task dart:test` and `task zig:test` exist while `python:test`/`node:test` do not
  (those run under `task test:bindings`, which drives them via alef). Check
  `task --list` rather than assuming `<lang>:<verb>` resolves.
- **Core build:** `task build` is core-only. Use `task build:bindings` for language bindings and `task build:all` for core plus bindings.
- **Build profiles:** `BUILD_PROFILE` supports dev/release/ci variants — `BUILD_PROFILE=release task build`, `task build:release`, or matching explicit binding/all variants.
- **Alef regeneration:** `task alef:generate` runs `alef all --clean`; it regenerates Alef-managed files without compiling bindings. Formatting is handled solely by poly (`task format` / `poly fmt --fix .`) — there is no separate Alef formatting task.
- **Alef build:** `task alef:build` and `task build:bindings` compile language bindings explicitly; `task build:all` includes core and bindings.
- **Alef verification:** `task alef:verify` checks generated output freshness when needed; do not hide verification inside fast regeneration.
- **E2E tasks:** repos with generated e2e suites expose `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all`. Do not add legacy aliases.
- **Lock files:** always commit lock files (uv.lock, pnpm-lock.yaml, go.sum, Cargo.lock, composer.lock) for reproducible builds.
- **Discipline:** never use manual commands instead of `task`, never hardcode paths, never skip lock-file commits.
