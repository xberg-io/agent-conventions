---
status: accepted
date: 2026-10-30
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0004", "0007"]
---

# ai-rulez runs at latest through npx

## Context and Problem Statement

ADR-0004 pins every tool exactly in `mise.toml` and `mise.lock`, and ADR-0007 has every repository render its agent
files with ai-rulez. Governance CI never followed the pin: `xberg-io/actions/setup-ai-rulez` installs the `latest`
release, while local runs used mise's exact pin. On 2026-10-30 the pins were the toolchains baseline and 17 repository
`mise.toml` files at 5.9.3, the release paths of sceptre (5.9.2 in `plugin-artifacts.yaml`) and xberg, the poly hook
source at `revision = "v5.9.2"`, and guard tests in xberg, html-to-markdown and liter-llm that assert a pin. A laptop
and CI could therefore run different generators, and every release needed a pin bump in each repository. The npm
package `ai-rulez` is a shim (Node 22 or later) that downloads the matching release binary and verifies it against
the release's `checksums.txt`.

## Considered Options

* Never pin ai-rulez, and run the latest release through `npx -y ai-rulez@latest` in tasks
* mise `"latest"` with an automated bump of the lock
* mise `"latest"` with no lock entry
* Keep the exact pins

## Decision Outcome

Chosen option: "Never pin ai-rulez, and run the latest release through `npx -y ai-rulez@latest` in tasks",
because every run then uses the newest release and no release needs a pin bump.

ai-rulez is the one exception to ADR-0004: it is never pinned and is in no baseline, `mise.toml` or `mise.lock`. It
always runs the latest release, by one of three paths:

* Tasks call `npx -y ai-rulez@latest <args>`.
* CI uses `xberg-io/actions/setup-ai-rulez`, which runs `Goldziher/ai-rulez@v5` with `version: latest` and ignores any
  `ai-rulez-version` input.
* The poly hooks run `ai-rulez` from PATH, installed with `npm install -g ai-rulez@latest`, until
  Goldziher/ai-rulez#526 adds an npm channel. The hook source follows the floating `v5` tag.

ADR-0007's module includes by version range are unchanged; this record covers only the generator's own version.

### Consequences

* Good, because every run uses the current release, with its fixes, without anyone moving a pin.
* Good, because a laptop, CI and a release job no longer run different pinned generators.
* Bad, because each release that changes output can turn `generate --check`, `lock --check`, the context budgets and
  `verify --plugin` red in every repository on the same day. On 2026-10-30 both 5.9.3 (xberg-io/agent-conventions run
  41025653712) and 5.9.4 (the managed `.gitignore` block) changed generated output; one sweep then regenerates and
  re-measures.
* Bad, because release jobs that hold publish credentials run unreviewed `@latest` code, and every run needs registry
  access. The shim's `checksums.txt` check protects the download in transit, not against a bad release.
* Bad, because an old tag can no longer be re-validated with the generator that produced it.
* Bad, because Node 22 or later is needed wherever ai-rulez runs.

### Confirmation

In xberg-io/toolchains, `task-sets/governance-check.toml` and `task-sets/plugin.toml` run `npx -y ai-rulez@latest`,
`governance:hooks:install` fails with the `npm install -g ai-rulez@latest` hint when `ai-rulez` is not on PATH,
`baseline.toml` carries no ai-rulez entry, and `toolchains.py check` refuses an ai-rulez pin in a consumer's
`mise.toml`. `xberg-io/actions/setup-ai-rulez` installs the latest release. The `toolchain-management` rule
(`modules/core/rules/toolchain-management.md`) names the exception, and the `mise-toolchains` and
`github-workflow-conventions` skills give the procedure.
