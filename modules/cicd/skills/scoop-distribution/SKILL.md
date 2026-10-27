---
type: Playbook
title: Scoop Distribution
description: "Windows Scoop channel: manifest templates in scripts/publish, the publish-scoop-manifest job, the shared bucket, adding a release target. Use when editing Scoop manifests, adding a CLI or release target, or debugging a Scoop install."
paths:
  - "scripts/publish/**"
x-ai-rulez:
  kind: skill
  id: scoop-distribution
  metadata:
    license: MIT
    name: scoop-distribution
---

# Scoop Distribution

Scoop is the Windows counterpart of the Homebrew tap. Each publishing repo owns one manifest
template; the release pipeline renders it and pushes the result into `xberg-io/scoop-bucket`.
The bucket is generated output — never hand-edit `bucket/*.json` there, because the next
release of the owning repo overwrites it wholesale.

Per repo:

<!-- ~keep The example manifest is supplied by the consuming product repository. -->
<!-- ai-rulez-lint-ignore: AR402 ~keep -->
- `scripts/publish/scoop.json` — which manifests to render, and which release asset each SHA
  placeholder binds to
- `scripts/publish/<app>.json.tmpl` — the manifest template
- a `publish-scoop-manifest` job, mirroring `publish-homebrew-formula` in the same workflow

<!-- ai-rulez-lint-ignore: AR402 ~keep -->
alef differs: `scripts/publish/scoop-manifests.json` with its own `commit-scoop-manifest.sh` and
`compute-scoop-gate.sh`, and `scoop` is an opt-in release target. Read its `publish.yaml`.

## The two escaping traps

Templates are rendered with Python `string.Template.substitute`, so **every literal `$` in the
manifest must be doubled**. Two of them appear in every template:

- `"$$schema"` — a bare `"$schema"` is read as the placeholder `$schema` and raises `KeyError`,
  failing the render. Loud, so you find it immediately.
- `$$version` inside `autoupdate` — this is Scoop's own placeholder, expanded by Scoop when it
  detects a new release. A bare `$version` there is **not** an error: it renders to the current
  release's version and silently freezes `autoupdate` on it forever.

The second is the one that bites, because a frozen `autoupdate` looks correct in review and in
the rendered manifest. Assert on it: the published `autoupdate` block must still contain a
literal `$version`, while the top-level `architecture` URLs must contain a concrete number.

## `extract_dir` cannot be derived

The repos do not package their Windows zips identically, and there is no rule that maps an asset
name to its inner layout. Get this wrong and `bin` resolves to nothing — the manifest hashes and
validates perfectly and installs a broken shim.

Each repo records its own app's layout next to its template. The shapes seen so far: nested in a
directory named after the asset (`<app>-cli-x86_64-pc-windows-msvc`), nested with the **version in
the directory name** (`<app>-${version}-x86_64-pc-windows-msvc`), and **flat**, with the `.exe` at
the zip root, where `extract_dir` is omitted entirely.

Confirm with `unzip -l <asset>` against the actual release before trusting any of these; a repo
can change its packaging without anyone noticing the manifest went stale.

## Render locally instead of waiting for CI

A template change is cheap to verify end to end. This downloads the real asset, hashes it, and
writes the manifest exactly as the release job would:

```bash
git -C ../actions show origin/main:publish-scoop-manifests/scripts/render.py > /tmp/render.py
mkdir -p /tmp/bkt/bucket
GITHUB_WORKSPACE="$PWD" \
INPUT_BUCKET_DIR=/tmp/bkt \
INPUT_CONFIG_FILE="$PWD/scripts/publish/scoop.json" \
INPUT_TAG=v1.2.3 INPUT_VERSION=1.2.3 \
INPUT_GITHUB_REPO=xberg-io/<repo> INPUT_DRY_RUN=false \
python3 /tmp/render.py
```

Diff the result against the manifest currently in the bucket: for a released version it should
come out byte-identical, and for a new one the only change should be the version and hashes.
Set `INPUT_DRY_RUN=true` to render against a tag that does not exist yet — assets are replaced
with a zero-SHA placeholder and the run still succeeds, which is what the dry-run pipeline does.

## Adding a release target (`scoop` or any other)

A repo's release targets (for example `release_scoop`) come from `alef release-metadata`, not from
the workflow YAML. alef's `ALL_RELEASE_TARGETS` must already contain the target, **and an alef
release carrying it must be published**, before any repo can name it: `parse_targets` hard-fails on
an unknown name, so adding it to an explicit `available-targets:` list too early breaks that repo's
release. Repos that pass no `available-targets` default to all targets and need no edit. Until then
the wiring is inert: the target resolves to an empty string and its job's gate is false.

## Job shape

Copy the repo's own `publish-homebrew-formula` rather than inventing one — in particular its
five-attempt rebase/push loop. Six release pipelines push to the single shared bucket, so a
concurrent release can land between checkout and push and reject it as non-fast-forward. Each
repo touches only its own manifest, so rebasing onto the new tip and retrying is safe.

Two deliberate differences from the Homebrew job:

- **No `check-scoop` idempotency gate.** The render rewrites the manifest in place and the commit
  is guarded by `git diff --quiet bucket/`, so re-running a release is already a no-op. Pass no
  fourth argument to `require_publish` — there is no "already published" probe to consult.
- **The job runs on dry runs; only the commit step is skipped.** Dry-run renders are the only
  pre-release exercise the template gets. Gating the whole job on `dry_run != 'true'` removes
  that safety net.

## Native dependencies

Every CLI is a native MSVC build importing `VCRUNTIME140.dll`, so every manifest carries
`"suggest": {"vcredist": "extras/vcredist2022"}`.

Check the import table before adding an app — `llvm-objdump -p <exe> | grep 'DLL Name'`. A
third-party hard import that is not bundled in the zip produces a binary that cannot start at
all, and no amount of manifest correctness fixes it. A hard-imported third-party DLL must be vendored
into the archive by the publish job; Scoop's shim resolves DLLs from the app directory, so
bundling is sufficient and no `depends` entry is needed. A runtime lookup on `PATH` (an external
tool the CLI shells out to) belongs in `notes`, not in `depends`.

## What actually proves an install works

Nothing on macOS or Linux does. Schema validation, a correct hash, and a byte-identical render
all pass on a manifest that installs a binary which cannot launch. The only real proof is the
`windows-latest` job in the bucket's `validate-manifests.yml`, which adds the checkout as a
bucket, installs each changed app, and runs `<app> --version`. Treat a green local check as
"nothing is obviously wrong", not as "this installs".
