---
name: common-task-commands
description: Common Taskfile commands across xberg-io repos — setup, build, test, lint, format, coverage, and bench. Load when running or discovering task commands, or unsure which task drives a build/test/lint step.
---

# Common Task Commands

| Category | Commands |
|----------|----------|
| **Setup** | `task setup` |
| **Build** | `task build` (core-only), `task build:bindings`, `task build:all`, `task rust:build`, `task python:build`, `task node:build`, `task go:build`, `task java:build`, `task ruby:build`, `task csharp:build`, `task wasm:build` |
| **Test** | `task test`, `task rust:test`, `task python:test`, `task node:test`, `task go:test`, `task java:test`, `task ruby:test`, `task e2e:test`, `task e2e:all` |
| **Lint** | `task lint:all`, `task lint:check` (CI), `task rust:clippy`, `task python:lint`, `task node:lint` |
| **Format** | `task format`, `task format:check`, `task rust:fmt`, `task python:format`, `task node:format` |
| **Alef** | `task alef:generate`, `task alef:verify`, `task alef:build`, `task build:bindings`, `task build:all`, `task alef:sync`, `task alef:docs` |
| **Utils** | `task clean`, `task version:sync`, `task smoke` |

Build commands respect `BUILD_PROFILE` (dev/release/ci). Append `:dev` or `:release` for explicit mode.

**Alef Generation**: `task alef:generate` runs `alef all --clean` for fast regeneration. It does not build bindings. Formatting is handled solely by poly (`task format` / `poly fmt --fix .`) — there is no separate Alef formatting task.

**E2E Tasks**: `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all` are canonical. Do not add legacy aliases.
