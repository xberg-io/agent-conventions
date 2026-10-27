---
name: taskfile-structure
description: "Org Taskfile conventions: task discovery, common and per-language task names, build profiles, setup, lock files, toolchain. Use when running, adding or choosing task commands, or setting up a repo."
# Content-Hash: blake3:6b0946117926091754717b56bd5ed707f036d6ecdcb2a13ade0b7adbdbc28204
---

# Taskfile Structure

Repos use [Taskfile](https://taskfile.dev) with the `task` CLI; prefer a `task` command over the raw
tool it wraps.

- **Discovery:** `task --list` shows what exists. Task sets are not uniform across repos, so check it
  rather than assuming a `<lang>:<verb>` task resolves.
- **Common tasks:** `task setup`, `task build`, `task test`, `task lint`, `task format`, `task cov:all`,
  and a repo-specific benchmark task (`benchmark:run`, `bench:run`, `rust:bench`).
- **Build profiles:** `BUILD_PROFILE` selects `dev`, `release` or `ci` (`BUILD_PROFILE=release task build`,
  or `task build:release`).
- **Maintenance:** `task update`, `task clean`, and the repo's version-sync task.
- **Lock files:** commit them (`uv.lock`, `pnpm-lock.yaml`, `go.sum`, `Cargo.lock`, `composer.lock`).
- **Before committing:** `task format` / `poly fmt --fix .` and `task lint` / `poly lint .`. Skip hooks
  with `--no-verify` only after running those checks yourself.
- **Toolchain:** `task` and `poly`, plus the toolchains of the languages you touch (Rust stable, Python
  3.10+ with uv, Node with pnpm). `task setup` installs the rest.
