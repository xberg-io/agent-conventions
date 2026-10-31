---
status: accepted
date: 2026-10-31
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0008"]
---

# gh-actions-updater owns action pin updates

## Context and Problem Statement

ADR-0008 pins every `uses:` reference to the action's shortest major tag, but names no tool that keeps the pins
there. Renovate's and Dependabot's `github-actions` managers propose full-version or SHA bumps, which move a
reference off its major tag, and ADR-0013 left Dependabot running in xberg-enterprise. gh-actions-updater (gau)
rewrites references to their latest major tag (`--latest-tag --pin-style major`) and checks offline that every
remote reference is a bare major (`--lint-pins`).

## Considered Options

* gau alone, through a poly hook and a scheduled bump workflow
* Renovate's `github-actions` manager, configured to keep major tags
* Dependabot's `github-actions` ecosystem

## Decision Outcome

Chosen option: "gau alone, through a poly hook and a scheduled bump workflow", because it is built for the major-tag
form and enforces it offline, while the bots treat a major tag as a version to bump.

Every `uses:` reference is the latest bare major `@vN`; a full version tag stays only where the upstream publishes no
major, and a SHA or branch is never used. gau owns the updates: repositories enable the `gh-actions-updater-lint-pins`
poly hook from a `gh-actions-updater` hook source on the floating `v0` tag, and xberg-io/actions
`reusable-actions-bump.yml` moves references to their latest major. Renovate and Dependabot do not manage
`github-actions`: the toolchains preset disables that manager, and a Dependabot config drops that ecosystem.

Poly hook sources take the same form: ai-rulez, gh-actions-updater and adrlint each float on their bare major tag
(`v5`, `v0`, `v0`), and the lock records the commit it resolved to.

### Consequences

* Good, because one tool writes and checks action references, so a bot never proposes a pin the hook rejects.
* Good, because the hook needs no token or network.
* Bad, because gau is one more hook source every repository declares and locks.
* Bad, because xberg-enterprise's `.github/dependabot.yml` still lists the `github-actions` ecosystem until its own
  change drops it.

### Confirmation

xberg-io/toolchains `default.json` disables Renovate's `github-actions` manager (`xberg-io/toolchains@04e2041`).
`tools/context-evals/hook-pins.toml` floats every hook source on its bare major, and `hook_pins.py`, run by
`actions/context-exposure`, rejects a consumer that pins one otherwise (`test_hook_pins.py`). The
`github-workflow-conventions` skill and the `toolchain-management` rule state the policy.
