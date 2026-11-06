# Native exposure migration

Status on 2026-11-06. `actions/context-exposure` runs ai-rulez's native exposure checks; the bespoke classifier is
gone ([ADR-0022](../adrs/0022-gate-the-start-context-with-native-ai-rulez-exposure.md)). The parity record is
[`native-exposure-2026-11-06.md`](../tools/context-evals/native-exposure-2026-11-06.md), the earlier one
[`native-exposure-2026-11-04.md`](../tools/context-evals/native-exposure-2026-11-04.md).

## Needs ai-rulez 5.11.0

The gate depends on [PR 541](https://github.com/Goldziher/ai-rulez/pull/541) (leakage scans `@path` imports;
areas-file `exclude` and `[[accept]]`), [PR 542](https://github.com/Goldziher/ai-rulez/pull/542) (`--harness codex`,
`codex_start_budget`, `mcp_server_tokens`) and [#546](https://github.com/Goldziher/ai-rulez/issues/546) (a Git-ignored
root `.mcp.json` counts), all released in 5.11.0. 5.10.0 rejects `exclude` (`AR9W5`) and the new `[exposure]` keys;
the action refuses any ai-rulez below 5.11.0.

## Rollout order

The action fails closed when a consumer's `[exposure] start_budget` is unset, so the order matters:

1. ai-rulez 5.11.0 is released (done; CI and the hooks run the latest release, org ADR-0015).
2. Every consumer lands an `[exposure]` table in `.ai-rulez/config.toml`. The budgets are in ai-rulez's native units:
   generate, run `ai-rulez exposure` and `ai-rulez exposure --harness codex` with `mcp_server_tokens` set, and add
   about 5%. Never copy the values of the old `budgets` input; native counts differ (comment banners, Codex listing
   paths, every MCP server charged).

   ```toml
   [exposure]
   mcp_server_tokens = 1150
   start_budget = <Claude start tokens x 1.05>
   codex_start_budget = <Codex start tokens x 1.05>
   ```

3. A consumer whose listed skill or agent description is over 250 characters fixes it first: the action checks the
   listings itself, whatever the consumer's `[lint.description]` says. crawlberg's and liter-llm's checkouts carry a
   254-character `alef` skill (exposure.py flags it too); alef's current one is 231, so regenerating fixes it.
4. agent-conventions releases and moves `v1`.
5. Consumers drop the `budgets` input from their workflow, or from their `reusable-ai-rulez-validation.yml` call once
   xberg-io/actions makes it optional. Until then it is ignored with a warning.

`ai-rulez:update` alone does not do step 2: includes carry rules, context and skills, not `[exposure]` tables. The
area map needs no consumer change; the action renders it from `domains.toml`.

## Open

- **Codex leakage** ([#545](https://github.com/Goldziher/ai-rulez/issues/545)): `exposure leakage` and `AR9W0` read
  the Claude Code inventory under either harness. AGENTS.md is covered through Claude's `@AGENTS.md` import; the
  path-gated skills Codex lists at start are not. The one known Codex-only occurrence is the brand skill's accepted
  `xberg`.
- **Codex skill policy**: native counts skills whose `agents/openai.yaml` sets `allow_implicit_invocation: false`
  in the Codex start listing (not modelled upstream), so Codex figures run high by those listing lines.
