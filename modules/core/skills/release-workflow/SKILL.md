---
name: release-workflow
description: >-
  Release/publish a Rust core crate or CLI in an xberg-io polyglot repo
  (crawlberg, html-to-markdown, xberg, tree-sitter-language-pack, liter-llm).
  Load when releasing or publishing a Rust crate or CLI — cutting a new version,
  tagging, running `gh release create`, installing the released build locally,
  and cleaning up. Repo-agnostic; for repo-specific task names check the repo's
  own release-workflow skill and Taskfile.
---

# Rust Crate / CLI Release Workflow (shared)

Canonical publish sequence for xberg-io repos that ship a Rust core crate and CLI
with polyglot bindings. `Cargo.toml` is the single source of truth for the
version, synced to every binding manifest. Confirm exact task names with
`task --list` — a repo may expose `task set-version` or `task version:set`.

## 1. Set the version

```bash
task set-version -- X.Y.Z         # some repos: task version:set -- X.Y.Z
```

The version is passed as a `--` positional argument. The task rewrites
`Cargo.toml` and syncs the version to all binding manifests (and any pinned
version constants), then runs `cargo update`. Never hand-edit `version` in
`Cargo.toml` or in binding manifests — use the task so everything stays in
lockstep. Verify with `grep -m1 '^version' Cargo.toml`.

## 2. Update the CHANGELOG

Move every `[Unreleased]` bullet in `CHANGELOG.md` into a new
`## [X.Y.Z] - YYYY-MM-DD` section (grouped Added / Changed / Fixed / Removed).
Re-create an empty `[Unreleased]`. Never tag an empty section.

## 3. Clean-tree precondition (hard gate)

Never release a dirty or failing tree.

```bash
poly lint .           # lint clean (task lint)
poly fmt --check .     # formatting clean (task format:check)
task test             # tests pass
```

Apply formatting with `poly fmt --fix .` (or `task format`) and re-stage. Fix any
lint or test failure at its source — do not release past a failure.

## 4. Commit, tag, and publish the GitHub release

```bash
git add -A
git commit -m "chore(release): X.Y.Z"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin main
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

Add `--prerelease` for RC/beta tags. Prefer `--notes-file` built from the new
CHANGELOG section when the entry is rich. A bare `git tag` is not a release —
always run `gh release create`. The tag push triggers the repo's publish
workflow (`cargo publish` and multi-registry binding publishes).

## 5. Install the released build locally

```bash
cargo install --path .            # CLI crate at a subpath: cargo install --path crates/<cli-crate>
```

Installs the released binary from the workspace so it shadows any crates.io copy
on `$PATH`. Confirm `which <binary>` and `<binary> --version` reflect X.Y.Z.

## 6. Clean up build artifacts

```bash
task clean        # runs cargo clean (removes target/) plus repo-specific cleanup
```

Reclaims disk by removing the `target/` directory (and any generated caches such
as `.alef/`, `dist/`). Where no `clean` task exists, run `cargo clean` directly.

## Anti-patterns

- Hand-editing `version` in `Cargo.toml` or a binding manifest instead of the
  version task.
- Releasing a dirty or lint/test-failing tree.
- Tagging without `gh release create`.
- AI attribution in commit/tag/release text.
