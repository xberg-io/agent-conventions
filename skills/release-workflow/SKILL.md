---
name: release-workflow
description: "Cut a release: version task, CHANGELOG, clean-tree gate, push then tag, gh release create, check the publish trigger, install the released build. Use when cutting or publishing a version."
# Content-Hash: blake3:198c45b949a791d898be1ec139040cdc6ca859c094bdb5c9b42ca6595023c5a9
---

# Release Workflow (shared)

Canonical publish sequence for a repo that tags versioned releases. One manifest
(`Cargo.toml` in a Rust repo) is the single source of truth for the version, and
the repo's version task syncs it to every other manifest. Task names differ per
repo: find it with `mise tasks | grep -i version`.

## 1. Set the version

Run the repo's version task. Some take the version as a `--` positional argument
(`mise run <version-task> -- X.Y.Z`), others bump one part (`major`, `minor`,
`patch`); read its description in `mise tasks`. The task rewrites the
source manifest, syncs the version to every other manifest and pinned version
constant, and refreshes lock files. Never hand-edit a manifest's `version` — use
the task so everything stays in lockstep. Verify with
`grep -m1 '^version' Cargo.toml` (or the repo's source manifest).

## 2. Update the CHANGELOG

`CHANGELOG.md` follows Keep a Changelog. Entries land under `## [Unreleased]`
between releases, never under an already-released section. At release, move
every `[Unreleased]` bullet into a new `## [X.Y.Z] - YYYY-MM-DD` section (grouped
Added / Changed / Deprecated / Removed / Fixed / Security), highlight breaking
changes, and re-create an empty `[Unreleased]`. Never tag an empty section.

## 3. Clean-tree precondition (hard gate)

Never release a dirty or failing tree.

```bash
poly lint .            # lint clean (mise run lint)
poly fmt --check .     # formatting clean (mise run format:check)
mise run test          # tests pass
```

Apply formatting with `poly fmt --fix .` (or `mise run format`) and re-stage. Fix any
lint or test failure at its source — do not release past a failure.

If the repo carries a coding-agent plugin with its own version pin
(`plugin/.ai-rulez/config.plugins.toml` `[plugin].version`, checked by its
version-sync script), run its `--check` mode here too,
against the version set in step 1:

```bash
python3 scripts/sync_plugin_version.py --check   # or the repo's equivalent
```

Step 1's version task already
chains this sync — but a narrower, similarly-named task that syncs only some
manifests is an easy trap, and running it instead silently leaves the plugin pin
behind. This is not hypothetical: it produced a real drift (`[plugin].version` vs
`Cargo.toml`) in two sibling repos on the same release day. Whatever CI runs post-tag as
`--expect <version>` to gate `publish.yaml`, run here as `--check` before you tag —
a gate that can only fire after the tag is cut turns every drift into a full
re-run of the publish flow.

## 4. Commit, tag, and publish the GitHub release

Push the default branch before creating the tag, not after — tagging first and
pushing second risks the tag pointing at a commit the default branch never
contains if the push is rejected or rebased in between. The default branch is not
always `main`:

```bash
default=$(git symbolic-ref --short refs/remotes/origin/HEAD | sed 's|^origin/||')
git add CHANGELOG.md <each manifest and lock file the version task changed>
git commit -m "chore(release): X.Y.Z"
git push origin "HEAD:$default"
git tag -a vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
gh release create vX.Y.Z --title "vX.Y.Z" --generate-notes
```

Add `--prerelease` for RC/beta tags. Prefer `--notes-file` built from the new
CHANGELOG section when the entry is rich. A bare `git tag` is not a release —
always run `gh release create`.

Stage the paths the version task reported (`git status --porcelain` lists them),
never `git add -A`: another agent's work in the tree would ship in the release commit.

**Do not assume what triggers your repo's publish workflow — check it.** Repos
are not uniform: some publish on the GitHub release (`on: release:
types: [published]`), some require an explicit `workflow_dispatch` with no
automatic trigger at all, and at least one fires on a tag push
(`on: push: tags:`). Read your own `.github/workflows/publish*.yaml` `on:`
block before relying on any one of these — assuming the wrong mechanism is how
a tagged, pushed release silently never reaches its registry.

## 5. Install the released build locally

For a repo that ships a Rust CLI:

```bash
cargo install --path .            # CLI crate at a subpath: cargo install --path crates/<cli-crate>
```

Installs the released binary from the workspace so it shadows any crates.io copy
on `$PATH`. Confirm `which <binary>` and `<binary> --version` reflect X.Y.Z.

## 6. Clean up build artifacts

```bash
mise run clean    # runs cargo clean (removes target/) plus repo-specific cleanup
```

Reclaims disk by removing build output and generated caches (`target/`, `dist/`).
Where no `clean` task exists, run the toolchain's own clean (`cargo clean`).

## Anti-patterns

- Hand-editing a manifest's `version` instead of the version task.
- `git add -A` in the release commit.
- Releasing a dirty or lint/test-failing tree.
- Tagging without `gh release create`.
- AI attribution in commit/tag/release text.
