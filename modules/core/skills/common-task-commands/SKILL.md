---
type: Playbook
title: Common Task Commands
description: Common Taskfile commands across xberg-io repos — setup, build, test, lint, format, coverage, and bench. Load when running or discovering task commands, or unsure which task drives a build/test/lint step.
x-ai-rulez:
  kind: skill
  id: common-task-commands
  metadata:
    name: common-task-commands
---

# Common Task Commands

| Category | Commands |
|----------|----------|
| **Setup** | `task setup` |
| **Build** | `task build` (core-only), `task build:bindings`, `task build:all`, `task rust:build`, `task php:build` |
| **Test** | `task test` (Rust core), `task test:bindings` (all bindings via alef), `task test:all`, `task rust:test`, `task swift:test`, `task dart:test`, `task zig:test`, `task e2e:test`, `task e2e:all` |
| **Lint** | `task lint`, `task lint:check` (CI), `task rust:lint`, `task csharp:lint`, `task swift:lint`, `task zig:lint` |
| **Format** | `task format`, `task format:check`, `task rust:format`, `task csharp:format`, `task swift:format`, `task dart:format`, `task zig:format` |
| **Alef** | `task alef:generate`, `task alef:verify`, `task alef:build`, `task build:bindings`, `task build:all`, `task alef:sync`, `task alef:docs` |
| **Utils** | `task clean`, `task versions:sync`, `task check`, `task test-apps:smoke` |

Build commands respect `BUILD_PROFILE` (dev/release/ci). Append `:dev` or `:release` for explicit mode.

**Alef Generation**: `task alef:generate` runs `alef all --clean` for fast regeneration. It does not build bindings. Formatting is handled solely by poly (`task format` / `poly fmt --fix .`) — there is no separate Alef formatting task.

**E2E Tasks**: `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all` are canonical. Do not add legacy aliases.
