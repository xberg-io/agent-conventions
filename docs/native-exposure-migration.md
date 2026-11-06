# Native exposure migration

Status on 2026-11-06. `actions/context-exposure` runs ai-rulez's native exposure checks; the bespoke classifier is
gone. The parity record is [`native-exposure-2026-11-06.md`](../tools/context-evals/native-exposure-2026-11-06.md),
the earlier one [`native-exposure-2026-11-04.md`](../tools/context-evals/native-exposure-2026-11-04.md).

## Needs ai-rulez 5.11.0

The gate depends on [PR 541](https://github.com/Goldziher/ai-rulez/pull/541) (leakage scans `@path` imports;
areas-file `exclude` and `[[accept]]`), [PR 542](https://github.com/Goldziher/ai-rulez/pull/542) (`--harness codex`,
`codex_start_budget`, `mcp_server_tokens`) and [#546](https://github.com/Goldziher/ai-rulez/issues/546) (a Git-ignored
root `.mcp.json` counts), all in 5.11.0. 5.10.0 rejects `exclude` (`AR9W5`) and the new `[exposure]` keys, and
CI runs the latest release (org ADR-0015), so this change ships only after 5.11.0 is released.

## Consumer steps

After 5.11.0 and before the agent-conventions release that moves `v1`, each consumer adds to `.ai-rulez/config.toml`
(the figures from its own `ai-rulez exposure` runs, about 5% headroom):

```toml
[exposure]
mcp_server_tokens = 1150
start_budget = <claude start tokens x 1.05>
codex_start_budget = <codex start tokens x 1.05>

[lint.description]
max_length = 250
```

and drops the `budgets` input from its workflow, or from its `reusable-ai-rulez-validation.yml` call, once
xberg-io/actions makes that input optional. `ai-rulez:update` alone does not do this: includes carry rules,
context and skills, not `[exposure]` tables. The area map needs no consumer change; the action renders it from
`domains.toml`.

## Open

- **Codex leakage** ([#545](https://github.com/Goldziher/ai-rulez/issues/545)): `exposure leakage` and `AR9W0` read
  the Claude Code inventory under either harness. AGENTS.md is covered through Claude's `@AGENTS.md` import; the
  path-gated skills Codex lists at start are not. The one known Codex-only occurrence is the brand skill's accepted
  `xberg`.
- **Codex skill policy**: native counts skills whose `agents/openai.yaml` sets `allow_implicit_invocation: false`
  in the Codex start listing (not modelled upstream), so Codex figures run high by those listing lines.
