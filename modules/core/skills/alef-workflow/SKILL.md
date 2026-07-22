---
name: alef-workflow
description: How to work with Alef-generated binding files and the task commands that regenerate, build, format, and verify them. Load when editing bindings, running task alef:*, or regenerating generated packages/e2e suites.
---

# Alef Workflow

- Treat Alef-managed binding files as generated output. Change Rust source, README templates, fixtures, or `alef.toml` instead of hand-editing generated packages.
- Use `task alef:generate` for fast regeneration. It must run `alef all --clean`.
- Do not compile bindings or run verification from `task alef:generate`.
- Use `task alef:build` or `task build:bindings` when binding compilation is needed; use `task build:all` for core plus bindings.
- Use `task format` or `poly fmt --fix .` for repository formatting; formatting is handled solely by poly (there is no separate Alef formatting task).
- Generated e2e suites use canonical tasks: `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all`. Do not add legacy aliases.
- Commit generator inputs and regenerated output together.
