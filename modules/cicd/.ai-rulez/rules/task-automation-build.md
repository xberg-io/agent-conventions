---
priority: medium
---

- Taskfile.yaml is the primary interface for all development tasks
- task setup / task build / task test / task lint / task format / task cov:all / task bench
- `task build` is core-only; use `task build:bindings` for language bindings and `task build:all` for core plus bindings
- `task alef:generate` runs `alef all --clean`; formatting is always applied during generation
- `task format` excludes Alef post-generation formatting
- Generated e2e suites must expose `task e2e:generate`, `task e2e:build`, `task e2e:test`, and `task e2e:all`; do not add legacy aliases
- Lock files always committed: uv.lock, pnpm-lock.yaml, go.sum, Cargo.lock, composer.lock
- BUILD_PROFILE supports dev/release/ci variants
- Never use manual commands instead of task, never hardcode paths, never skip lock file commits
