# Load mechanics

What Claude Code and Codex put in a session's context, and when (issue #3, section 4.1). Each fact is marked by
how it is known:

- **measured**: by a tool in `tools/context-evals/` against the consumer checkouts, with the version stated.
- **documented**: from the harness's own documentation, as collected in ai-rulez `docs/agents-md.md`
  (research pass of 2026-10-03/04) and ai-rulez `docs/rules.md`. Not yet confirmed by our probe.
- **to probe**: open until `probe.py` runs on a maintainer machine (it cannot run inside a hosted agent session,
  whose identity the child `claude -p` would inherit).

Re-check on every harness upgrade; record the version next to the result.

## Claude Code

| Artifact | When it loads | Known by |
|---|---|---|
| `CLAUDE.md` in the start directory and its ancestors | at start | documented |
| `AGENTS.md` | only through an `@AGENTS.md` import in `CLAUDE.md` once any `CLAUDE.md` exists (v2.1.277+); an import never loads twice | documented |
| Nested `CLAUDE.md` below the start directory | on the first read of a file in its directory | documented; to probe |
| `.claude/rules/*.md` without `paths:` | at start | documented |
| `.claude/rules/*.md` with `paths:` | when a read or edit touches a matching file; search tools (Grep, Glob) do not trigger it | documented; the search-tool part to probe |
| Skill name and description | listed at start | documented |
| Skill with `paths:` | listed only after a matching file is read | documented; to probe |
| Skill with `disable-model-invocation: true` | never listed for the model; the user runs it as a slash command | documented |
| Skill body | when the model invokes the skill | documented |
| Agent name and description (`.claude/agents/*.md`) | listed at start | documented |
| MCP server tool schemas (`.mcp.json`) | at start once the server is approved; large tool sets may be deferred behind tool search | first part documented; deferral to probe |

## Codex

| Artifact | When it loads | Known by |
|---|---|---|
| `AGENTS.md` (or `AGENTS.override.md`) in each directory from the project root down to the start directory | at start, concatenated root first; nothing below the start directory loads lazily | documented |
| Project instructions past `project_doc_max_bytes` (default 32 KiB) | dropped | documented |
| `.agents/skills/*/SKILL.md` name, description, path | listed at start, whatever the skill's `paths:` (no path gating) | documented |
| `.codex/agents/*.toml` | written by ai-rulez; whether Codex reads them is unverified | to probe |
| MCP servers in `.codex/config.toml` | tool schemas at start | documented |

## What this means for the modules

- Glob-scoped rules are free at start in Claude Code and cost their full text in Codex if inlined into
  `AGENTS.md`. Consumers set `[rules] scoped_fallback = "skill"` (ai-rulez 5.7.0+): Codex gets each scoped rule as a
  skill (description listed, body on demand) instead.
- A path-gated skill is free at start in Claude Code and costs its listing line in Codex. Keep descriptions short;
  the 250-character limit is enforced by the CI gate.
- MCP tool schemas are the largest start cost when a server is unrestricted (below).

## Measured start cost (2026-10-26, ai-rulez 5.7.0, agent-conventions `923818e`)

Static estimate, bytes / 3.9 per token, from `exposure.py --measure-mcp ai-rulez`; to be calibrated against a probe.

| Artifact | Tools | Schema + instructions | Tokens |
|---|---:|---:|---:|
| `ai-rulez mcp`, default (all tools) | 67 | 148,844 B + 444 B | ~38,300 |
| `ai-rulez mcp` with `[mcp] serve_skills, read_only, discover_skills = "repo", tools = ["find_skill", "load_skill"]` | 2 | 3,990 B + 475 B | ~1,150 |
| `@playwright/mcp@0.0.83` | not measured (needs a package download) | | |

Every consumer registered the unrestricted ai-rulez server for Claude Code (sceptre and liter-llm also for Codex),
so before the restriction it was about 38k of each session's start tokens, roughly seven times everything else
combined. Per-consumer totals are in `tools/context-evals/after-mcp-2026-10-26.md` and the job summary of each
consumer's `AI-Rulez validation` run.

`find_skill` with `path` ranks only the skills that apply to that path, honouring `paths:` and hiding user-only
skills (checked on xberg: `crates/xberg/src/ocr/mod.rs` returns the OCR, PDF and pipeline skills first;
`crates/xberg-py/src/lib.rs` returns the binding skills).

## Probing

`tools/context-evals/probe.py` plants a sentinel in the root `CLAUDE.md`, an unscoped and a glob-scoped rule, a
skill description and a nested `CLAUDE.md`, runs `claude -p` with a fresh config directory and only project
settings, and reports which sentinels the model sees at start and after a read in the scoped directory, plus the
usage of a trivial prompt. Run it with `ANTHROPIC_API_KEY` set, outside any agent session, and replace each
"to probe" above with the result and the Claude Code version. Codex needs an equivalent probe (not written yet).
