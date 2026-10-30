# Load mechanics

Measured on 2026-10-30 with probe version 2, Claude Code 2.1.314 (`claude-sonnet-5-5`) and
Codex CLI 0.165.0-alpha.1.2 (`gpt-6.1-sol`). Consumer worktrees were generated with the published ai-rulez 5.9.2
binary recorded in `tools/context-evals/study.toml`. No consumer main checkout was modified.

Claude measurements use three repeats of start, search, read, skill invocation and nested-directory start.
Codex uses one bounded run of those five phases, plus deterministic prompt-input controls and two bounded
agent-registration runs. A marker appearing in an answer is evidence of visibility; it does not prove a feature
cannot load through a different configuration.

## Claude Code

| Artifact | Observed behavior |
|---|---|
| Root `CLAUDE.md` | Visible at start, including from the nested start directory. |
| Root `AGENTS.md` imported by `CLAUDE.md` | Visible in all three root starts. The root import marker was absent from all three nested starts; do not assume identical import resolution from every working directory. |
| Nested `CLAUDE.md` | Absent at root start and after search; visible after reading a file in its directory, or starting there. |
| Unscoped `.claude/rules/*.md` | Visible at start. |
| Glob-scoped rule | Absent at start and after search; visible after a matching read. |
| Skill description | Visible at start. |
| Skill with `paths:` | Absent at root start and after search; visible after a matching read. |
| Skill with `disable-model-invocation: true` | Absent from the start listing. |
| Skill body | Absent at start; visible after explicit invocation. |
| Agent description | Visible at start. |
| MCP schemas | Excluded from the instruction probes through a strict empty MCP config; real-server startup deferral was measured separately below. |

The initial input of the root-start probes ranged from 25,536 to 25,537 tokens, including Claude Code's own
instructions and tool definitions. This is not the same quantity as repository instruction-text tokens.

## Codex

| Artifact | Observed behavior |
|---|---|
| Root `AGENTS.md` | Visible at start. |
| Nested `AGENTS.md` | Absent on a later read; visible when the session starts in its directory. |
| Instruction size limit | A 50,000-byte instruction control retained its first marker and dropped its last marker under the default 32 KiB limit. |
| Skill description with `paths:` | Listed at root start; paths did not gate its listing. |
| Skill with `disable-model-invocation: true` | Also listed at start; do not assume Claude's frontmatter gate applies to Codex. |
| Skill body | Absent at start; visible after explicit invocation. |
| `.codex/agents/*.toml` | A directory-only agent was not visible. With multi-agent enabled and the agent explicitly registered through `agents.<name>.description` and `config_file`, its marker was visible. |
| MCP schemas | Outside the instruction probe; a separate [offline code-mode probe](codex-mcp-mechanics.md) measures startup omission and runtime definition retrieval. |

The explicit-model root-start run used 20,074 input tokens. Codex usage after tool calls is cumulative over model
requests, so its read/search totals must not be interpreted as initial context size. These observations agree with
the [instruction-chain documentation](https://learn.chatgpt.com/docs/agent-configuration/agents-md) and
[skill discovery documentation](https://learn.chatgpt.com/docs/build-skills) for the measured configuration.

## Calibration and budgets

`tools/context-evals/calibration.json` records ten instruction-text samples, their byte counts, native Anthropic
token counts and SHA256 values, using Anthropic's [free token-counting endpoint](https://platform.claude.com/docs/en/build-with-claude/token-counting). The weighted ratio is **2.660531 bytes per token** for `claude-sonnet-5-5`, replacing
the previous 3.9 rule of thumb. Message-envelope overhead is included conservatively. This calibrates text
estimates; it does not remove CLI runtime overhead or establish the tokenizer used by every Codex model.

Reproduce the calibration with `calibrate.py --root WORKSPACE --model claude-sonnet-5-5 --out calibration.json`
and the sample paths in the JSON, with `ANTHROPIC_API_KEY` in the environment. The key is never written to output.

The shared exposure action continues evaluating existing budget inputs in their original byte/3.9 units through
`--budget-estimator legacy`. It reports calibrated totals separately. This preserves the exact previous byte
threshold rather than changing consumer gates merely because the estimator improved. Direct CLI budgets use
calibrated units by default.

## MCP scope

Playwright is deliberately excluded: these cases measure read-only repository guidance, not browser operation,
and enabling a browser would introduce network and external-state effects outside the case fixtures. Basemind was
also absent from the MCP probe; no indexing or source tool invocation was performed.

An additional 2026-10-30 probe connected the actual published **ai-rulez 5.9.3** stdio server to Claude Code
**2.1.314**, requesting `claude-sonnet-5-5`. `exposure.py --measure-mcp ai-rulez` measured the repository's configured
two-tool server; separate controlled configurations measured the full and read-only catalogs. Initialize replies
identified version 5.9.3, and nonempty `tools/list` responses were retained.

| Actual server configuration | Tools | Compact catalog + instructions bytes | Calibrated static estimate |
|---|---:|---:|---:|
| This repository: `find_skill`, `load_skill` | 2 | 4,465 | 1,678 tokens |
| Full read-only catalog control | 38 | 78,427 | 29,478 tokens |
| Full catalog control | 71 | 157,974 | 59,377 tokens |

These estimates reuse the instruction-text byte calibration; they are not native MCP token counts. The catalog
includes output schemas, annotations and titles, not just model-facing input schemas. The eager CLI control
contained MCP tool-definition objects totaling 73,954 compact JSON bytes, rather than the full 157,974-byte catalog.

The real CLI used isolated settings, no `--tools` restriction and a strict MCP config containing only ai-rulez.
An SSE loopback fixture supplied responses, with a dummy API key and remote network access denied by
`sandbox-exec`; an explicit connection to `1.1.1.1:443` failed with `EPERM`. No hosted completion or token-count
endpoint was called. The fixture's usage and cost fields are synthetic and are excluded from measurements.

| CLI tool-search setting | Connected MCP tools advertised at init | MCP schemas in first Messages request | First request bytes |
|---|---:|---:|---:|
| Default/unset, configured server | 2 | 0 | 47,946 |
| Default/unset, full catalog | 71 | 0 | 49,905 |
| `ENABLE_TOOL_SEARCH=false`, full catalog | 71 | 71 | 151,320 |

With the default setting, both real catalogs appeared by tool name in the startup reminder, while `ToolSearch`
and a `DeferredToolPlaceholder` carrying `defer_loading: true` replaced the MCP parameter schemas. Explicitly
enabling search gave the same schema-deferral shape; disabling it supplied all 71 actual MCP schemas. This
negative control rules out an empty or failed MCP connection masquerading as deferral.

A further fixture response requested the real CLI's built-in `ToolSearch` for
`select:mcp__ai-rulez__find_skill`. The following Messages request contained exactly that MCP schema and a
`tool_reference` for it; the initial request contained none. The actual ai-rulez protocol log still contained
zero `tools/call` requests. This observes client-side on-demand schema loading without executing an MCP source
tool or asking a hosted model to select one.

This resolves the startup transport question for the measured CLI/server configurations. It does **not** measure
native model input tokens, provider billing, natural model tool choices, account-specific production settings or
Codex MCP behavior beyond the separate [code-mode probe](codex-mcp-mechanics.md). Request byte totals also
include built-ins, instructions and message wrappers; their difference must not be reported as an MCP token saving. Static exposure remains an upper-bound inventory, not runtime input
cost, and the historical instruction-probe usage measurements above remain unchanged.

Controlled raw MCP exchanges, CLI initialization records, API request bodies, capture scripts and SHA256 evidence
index are retained under the ignored polyrepo `reports/mcp-ai-rulez-5.9.3-2026-10-30/`. Replay their consistency with
`tools/context-evals/mcp_probe.py --catalog CATALOG.jsonl --rpc RPC.jsonl --startup STARTUP.jsonl
--requests REQUESTS.json --out SUMMARY.json`. The analyzer requires matching nonempty catalogs, an actually
connected server, matching advertised names and a captured startup request; its tests reject missing tools,
missing search support, changed catalogs and metadata-only probes that invoked `tools/call`.

## Re-probing

Run `probe.py CHECKOUT --preset claude|codex --model MODEL --scoped-file TRACKED_FILE --repeats 3
--budget-ledger SHARED_LEDGER --json REPORT.json` through `mise exec` whenever either CLI changes.
Claude paid execution refuses a hard dollar ceiling because its CLI limit is soft; `--allow-soft-budget` is an
explicit opt-in to prospective accounting only. No opt-in is needed for existing Codex subscription auth. Compare each
phase's `loaded` marker map and initial token range with the recorded measurements, keeping the same consumer
commit, probe version and model. Preserve raw outputs in the ignored workspace reports directory; publish only
reviewed summaries. Do not reuse a calibration silently after a model or probe-version change.
