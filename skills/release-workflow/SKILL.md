---
name: release-workflow
description: "Release/publish a Rust core crate or CLI in an xberg-io polyglot repo (crawlberg, html-to-markdown, xberg, tree-sitter-language-pack, liter-llm). Load when releasing or publishing a Rust crate or CLI — cutting a new version, tagging, running `gh release create`, installing the released build locally, and cleaning up. Repo-agnostic; for repo-specific task names check the repo's own release-workflow skill and Taskfile."
# Content-Hash: blake3:640970bdba54ac65dee65601fc52195076a7020cd47edd745964a9a45f2cea10
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

If the repo carries a coding-agent plugin with its own version pin
(`plugin/.ai-rulez/config.plugins.toml` `[plugin].version`, checked by its
version-sync script), run its `--check` mode here too,
against the version set in step 1:

```bash
python3 scripts/sync_plugin_version.py --check   # or the repo's equivalent
```

Step 1's version task (`version:set` / `version:sync` / `version:bump:*`) already
chains this sync — but a narrower, similarly-named task (e.g. an `alef:sync` that
only runs `alef sync-versions`, without the plugin step) is an easy trap, and
running it instead silently leaves the plugin pin behind. This is not
hypothetical: it produced a real drift (`[plugin].version` vs `Cargo.toml`) in two
sibling repos on the same release day. Whatever CI runs post-tag as
`--expect <version>` to gate `publish.yaml`, run here as `--check` before you tag —
a gate that can only fire after the tag is cut turns every drift into a full
re-run of the publish flow.

## 4. Commit, tag, and publish the GitHub release

Push `main` before creating the tag, not after — tagging first and pushing
second risks the tag pointing at a commit `origin/main` never contains if the
push is rejected or rebased in between, and `--force-with-lease` does not work
on tags.

```bash
git add -A
git commit -m "chore(release): X.Y.Z"
git push origin main
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

Add `--prerelease` for RC/beta tags. Prefer `--notes-file` built from the new
CHANGELOG section when the entry is rich. A bare `git tag` is not a release —
always run `gh release create`.

**Do not assume what triggers your repo's publish workflow — check it.** These
repos are not uniform: some publish on the GitHub release (`on: release:
types: [published]`), some require an explicit `workflow_dispatch` with no
automatic trigger at all, and at least one fires on a tag push
(`on: push: tags:`). Read your own `.github/workflows/publish*.yaml` `on:`
block before relying on any one of these — assuming the wrong mechanism is how
a tagged, pushed release silently never reaches its registry.

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
