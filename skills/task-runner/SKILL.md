---
name: task-runner
description: "Use the repository's task runner (go-task Taskfile) instead of raw build, test, lint or format commands. Use when a Taskfile.yml exists at the root or before running a build or test command in an unfamiliar repo."
# Content-Hash: blake3:e595a1d788a518339ec85d2e22568cce848c6d2f4053d4fdefa1881d272a603b
---

- If the repository root has a `Taskfile.yaml` or `Taskfile.yml`, prefer `task <target>` over the raw toolchain command — the Taskfile carries the flags and env the raw command omits.
- `task --list` enumerates the available targets.
- Standard target names: `setup`, `build`, `test`, `lint`, `format`, `bench`. Follow them when adding targets.
- Commit lock files so builds are reproducible.
