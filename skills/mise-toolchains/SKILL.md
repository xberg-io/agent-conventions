---
name: mise-toolchains
description: "mise procedures: locked install, adding a tool, moving to a new baseline, matrix version legs, lock and rate-limit failures. Use when installing or changing a tool version."
# Content-Hash: blake3:a6974090b6363efab0d3e23148b5fae77c01178bb1738c1169fe006106cbc8f0
---

# Mise toolchains

The toolchain-management rule (core) states the policy. These are the procedures.

## Install

```sh
mise trust          # once per checkout or worktree; mise ignores an untrusted mise.toml
mise install --locked
```

`--locked` installs only what `mise.lock` pins for this platform, as CI does.

## Add a tool

1. Use the baseline's exact key, version and table options from `xberg-io/toolchains` `baseline.toml`
   (`uv = "0.13.6"`, `"github:Goldziher/poly" = "0.29.0"`). An alias (`nodejs`, `core:node`, `aqua:…`) is drift.
   A tool the baseline does not list is repository-owned; pin it exactly.
2. Lock every platform: `mise lock --platform linux-x64,linux-arm64,macos-arm64,windows-x64` (the
   `lockfile_platforms` setting, where set, supplies the same list).
3. Commit `mise.toml` and `mise.lock` together.

## Move to a new baseline

```sh
git clone --depth 1 --branch v1.1.0 https://github.com/xberg-io/toolchains /tmp/toolchains
python3 /tmp/toolchains/scripts/toolchains.py sync --baseline /tmp/toolchains/baseline.toml --ref v1.1.0
mise lock
python3 /tmp/toolchains/scripts/toolchains.py check --baseline /tmp/toolchains/baseline.toml
```

`check` exits 1 on drift and 2 when it checked nothing (no `mise.toml`, or no tool the baseline covers). `sync`
writes nothing when a pin cannot be rewritten (a `[tools.node]` subtable, differing table options); fix those by hand.

## ai-rulez

ai-rulez is in no baseline, `mise.toml` or `mise.lock`, and always runs the latest release by one of three paths:

- Tasks: `npx -y` at the npm `latest` tag, the command the toolchain-management rule gives. It needs Node 22 or
  later (in the baseline); the shim downloads the release binary and verifies its checksum.
- CI: `xberg-io/actions/setup-ai-rulez@v1`, which installs latest whatever `ai-rulez-version` says.
- Hooks: the poly hooks run `ai-rulez` from PATH (`npm install -g ai-rulez@latest`, rerun to update) until
  Goldziher/ai-rulez#526 adds an npm channel.

A release that changes output turns `generate --check`, `lock --check` and the context budgets red; regenerate,
re-lock and re-measure in one sweep.

## Matrix version legs

Declare the extra versions in `mise.ci.toml` so they are locked too, run with `MISE_ENV=ci`, and select each leg's
version with `MISE_<TOOL>_VERSION` (`MISE_NODE_VERSION=22.20.0`). `check` reads only `mise.toml`.

## Troubleshooting

- GitHub API rate limits (`403`, `rate limit exceeded`): export `GITHUB_TOKEN`; `setup-mise` passes it in CI.
- A fresh release that mise will not resolve: `minimum_release_age` hides versions younger than the window. Wait,
  or add the tool to `minimum_release_age_excludes` with a reason.
- `--locked` fails (missing URL or platform, checksum mismatch): the lock is stale. Rerun `mise lock` for all four
  platforms and commit it; never edit `mise.lock` by hand.
