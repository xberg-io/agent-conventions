---
status: proposed
date: 2026-11-06
decision-makers: ["Na'aman Hirschfeld"]
consulted: []
informed: []
---

# Gate the start context with native ai-rulez exposure

## Context and Problem Statement

Every consumer's AI-rulez validation ran `actions/context-exposure`, which classified the generated start context with
this repository's own `exposure.py`: start tokens per harness, leaked product terms and long descriptions. ai-rulez
5.11.0 measures the same things natively (`ai-rulez exposure`, `exposure leakage`, `exposure inventory`, validate rules
`AR9W0` and `AR9W3`), including what the bespoke classifier could not see (frontmatter gate state, imported files,
plugin listings). Two classifiers of one thing drift. Where does the gate run, and where do its budgets and taxonomy
live? ([issue #4](https://github.com/xberg-io/agent-conventions/issues/4))

## Decision Drivers

* One classifier of the start context, the one ai-rulez ships.
* One taxonomy: `tools/context-evals/domains.toml`.
* Consumers keep calling the gate they call today.
* A gate that cannot measure fails instead of passing.

## Considered Options

* Keep `actions/context-exposure` as a thin wrapper over native ai-rulez, budgets in each consumer's `[exposure]`
* Deprecate the action; each consumer calls ai-rulez directly with a committed `areas_file`
* Keep `exposure.py` as the gate

## Decision Outcome

Chosen option: "Keep `actions/context-exposure` as a thin wrapper over native ai-rulez, budgets in each consumer's
`[exposure]`", because ai-rulez includes cannot carry an `[exposure]` table, so a shared taxonomy needs a step that
renders it, and the action is already that step in every consumer.

The action renders the repository's area map from `domains.toml` with `areas.py` at run time and passes it with
`--areas`; nothing is committed in a consumer. It runs `ai-rulez exposure` for Claude Code and Codex, `exposure leakage`,
and a 250-character check on the listed descriptions that `exposure inventory` reports. Budgets are the consumer's
`[exposure] start_budget` and `codex_start_budget`, so `ai-rulez validate` (`AR9W3`) and the action read the same
numbers. The action refuses ai-rulez below 5.11.0 and fails when `start_budget` is unset. ai-rulez stays unpinned
(org [ADR-0015](0015-ai-rulez-runs-at-latest-through-npx.md)).

### Consequences

* Good, because the start context is classified once, by the tool that generates it.
* Good, because a change to `domains.toml` reaches every consumer with the next agent-conventions release, without a
  re-rendered file in each.
* Good, because consumers keep the action's path and inputs; the retired inputs warn instead of failing.
* Bad, because every consumer must add an `[exposure]` table, measured in native units, before the release that moves
  `v1`.
* Bad, because the gate inherits ai-rulez's gaps: Codex leakage reads the Claude Code inventory
  ([Goldziher/ai-rulez#545](https://github.com/Goldziher/ai-rulez/issues/545)), and MCP schemas are a fixed estimate per
  server.
* Bad, because a consumer's local `ai-rulez validate` runs no leakage check without the rendered map; CI does.

### Confirmation

`tools/context-evals/test_context_exposure_gate.py` checks each failure of `actions/context-exposure/gate.sh` against a
stub and, when ai-rulez is on `PATH`, against the real binary on a fixture; the context-harness job installs it.
`tools/context-evals/native-exposure-2026-11-06.md` records the parity with the retired classifier.

## Pros and Cons of the Options

### Keep `actions/context-exposure` as a thin wrapper over native ai-rulez

* Good, because the taxonomy and the gate ship together and consumers change no workflow.
* Bad, because the action keeps a small amount of shell and Python glue.

### Deprecate the action; consumers call ai-rulez directly

* Good, because there is nothing between a consumer and ai-rulez.
* Bad, because each consumer would commit a rendered area map that drifts from `domains.toml`, and lose the hook-pin
  check the action also runs.

### Keep `exposure.py` as the gate

* Good, because nothing changes for consumers.
* Bad, because it duplicates ai-rulez's classifier and cannot see what ai-rulez knows.

## More Information

* [`docs/native-exposure-migration.md`](../docs/native-exposure-migration.md): the rollout order.
