---
type: Playbook
title: Alef Workflow
description: How to work with alef-generated binding files and the task commands that regenerate, build, verify and version them. Load when editing bindings, running task alef:*, or regenerating generated packages or e2e suites.
paths:
  - "alef.toml"
  - "crates/*-ffi/**"
  - "crates/*-py/**"
  - "crates/*-node/**"
  - "crates/*-php/**"
  - "crates/*-jni/**"
  - "crates/*-wasm/**"
  - "packages/**"
x-ai-rulez:
  kind: skill
  id: alef-workflow
  metadata:
    name: alef-workflow
---

# Alef Workflow

## Generated files

- Treat alef-managed binding files as generated output. Change Rust source, README templates, fixtures or `alef.toml` instead of hand-editing generated packages.
- Commit generator inputs and regenerated output together.

## Tasks

- `task alef:generate` regenerates fast: it runs `alef all --clean` and does not compile bindings or verify.
- `task alef:build` or `task build:bindings` compiles the bindings; `task build:all` builds core plus bindings. `task build` is core-only.
- `task alef:verify` checks generated output freshness; do not hide verification inside fast regeneration.
- Binding tests run under `task test:bindings`; a `<lang>:test` task exists only for some languages, so check `task --list`.
- Formatting is handled solely by poly (`task format` / `poly fmt --fix .`); there is no alef formatting task.
- Generated e2e suites use `task e2e:generate`, `task e2e:build`, `task e2e:test` and `task e2e:all`. Do not add legacy aliases.

## Versions

`Cargo.toml` is the single source of the version; the repo's version task (`task version:set` / `task set-version`) runs `alef sync-versions` to rewrite every binding manifest and pinned constant. Never hand-edit a binding manifest's version. A narrower task that only runs `alef sync-versions` (for example `alef:sync`) skips the repo's other version pins, such as a coding-agent plugin's `[plugin].version`; use the full version task. Clean generated caches (`.alef/`) with `task clean`.
