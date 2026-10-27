---
name: taskfile-structure
description: "Org Taskfile conventions on top of the task-runner skill: namespaced task discovery, common task names, build profiles, maintenance tasks, toolchain. Use when adding or choosing task commands, or setting up a repo."
# Content-Hash: blake3:b7e97550b7bb11d49040d1afa3f58f8f9281f1a5bc3e49cc4fb99a1f633f9630
---

# Taskfile Structure

The builtin task-runner skill covers preferring `task` over the raw tool, `task --list` and
committing lock files. These are the org's additions.

- **Discovery:** task sets are not uniform across repos, so check `task --list` rather than assuming a
  `<lang>:<verb>` task resolves. Tasks from included taskfiles are namespaced (`version:sync`).
- **Common tasks:** `task setup`, `task build`, `task test`, `task lint`, `task format`, `task cov:all`
  where present, and a repo-specific benchmark task (`benchmark:run`, `bench:run`, `rust:bench`; the
  builtin task-runner's plain `bench` exists only in some repos).
- **Build profiles:** where the Taskfile defines `BUILD_PROFILE` (most alef binding repos), it selects
  `dev`, `release` or `ci` (`BUILD_PROFILE=release task build`, or `task build:release`).
- **Maintenance:** `task update`, `task clean`, and the repo's version-sync task.
- **Toolchain:** `task` and `poly`, plus the toolchains of the languages you touch (Rust stable, Python
  3.10+ with uv, Node with pnpm). `task setup` installs the rest.
