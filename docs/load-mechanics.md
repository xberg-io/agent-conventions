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
| MCP schemas | Deliberately excluded from these hermetic runs through a strict empty MCP config. Production tool-search deferral is outside this measurement. |

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
| MCP schemas | Outside the isolated instruction/skill probe; no production schema-cost claim is made. |

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
and enabling a browser would introduce network and external-state effects outside the case fixtures. The ai-rulez
server's static schema cost can still be measured with `exposure.py --measure-mcp ai-rulez`; it is an upper bound
until production Claude tool-search deferral is measured. No MCP upper bound is presented as measured runtime
input cost. That remaining limitation keeps issue 5 open.

## Re-probing

Run `probe.py CHECKOUT --preset claude|codex --model MODEL --scoped-file TRACKED_FILE --repeats 3
--budget-ledger SHARED_LEDGER --json REPORT.json` through `mise exec` whenever either CLI changes.
Claude paid execution refuses a hard dollar ceiling because its CLI limit is soft; `--allow-soft-budget` is an
explicit opt-in to prospective accounting only. No opt-in is needed for existing Codex subscription auth. Compare each
phase's `loaded` marker map and initial token range with the recorded measurements, keeping the same consumer
commit, probe version and model. Preserve raw outputs in the ignored workspace reports directory; publish only
reviewed summaries. Do not reuse a calibration silently after a model or probe-version change.
