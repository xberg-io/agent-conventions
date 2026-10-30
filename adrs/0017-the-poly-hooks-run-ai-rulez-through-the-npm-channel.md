---
status: accepted
date: 2026-10-30
decision-makers: ["Na'aman Hirschfeld"]
amends: ["0015"]
---

# The poly hooks run ai-rulez through the npm channel

## Context and Problem Statement

ADR-0015 runs ai-rulez at its latest release everywhere, but left the poly hooks on an `ai-rulez` binary from PATH,
installed with `npm install -g ai-rulez@latest`, because the reviewed hook catalog had no npm channel. A global
install goes stale until someone reruns it, so a laptop's hooks could check generated files with an older generator
than tasks and CI. ai-rulez 5.9.5 added an `npm` channel to every hook in its `poly-hooks.toml`
(Goldziher/ai-rulez#526): it checks `command -v npx` and runs `npx -y ai-rulez@latest`. poly picks a hook's channel
from `hook_preferences.channels` in the machine's untracked `poly.local.toml`, which `governance:hooks:install`
writes.

## Considered Options

* Prefer the `npm` channel, and fall back to `system`
* Keep the `system` channel and the global install
* Allow only the `npm` channel

## Decision Outcome

Chosen option: "Prefer the `npm` channel, and fall back to `system`", because the hooks then follow the latest
release like tasks and CI, and a machine without Node on PATH at commit time still runs a global `ai-rulez`.

`governance:hooks:install` writes `channels = ["npm", "system"]` when `poly.local.toml` has no `[hook_preferences]`,
accepts existing preferences that allow either channel, and needs only `npx` or `ai-rulez` on PATH. The hook source
stays on the floating `v5` tag. This replaces ADR-0015's hook path; its task and CI paths are unchanged.

### Consequences

* Good, because no global install is needed, and the hooks never run a stale generator.
* Good, because the hooks, tasks and CI resolve the same `latest` release.
* Bad, because each hook run asks the npm registry for `latest`, which adds latency and needs network access at
  commit time.
* Neutral, because machines whose existing preferences list only `system` keep the global install until their owner
  puts `npm` first.

### Confirmation

In xberg-io/toolchains, `task-sets/governance/hooks-install.sh` writes `["npm", "system"]` and its tests in
`tests/test_tasks.py` cover both channels. The `toolchain-management` rule and the `mise-toolchains` and
`github-workflow-conventions` skills name the npm channel.
