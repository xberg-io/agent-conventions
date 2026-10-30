# Codex MCP startup transport

An offline 2026-10-30 probe (`codex-mcp-1`) measured Codex CLI **0.165.0-alpha.1.2**, requesting **gpt-6.1-sol**, against the
published **ai-rulez 5.9.3** server. This is pinned historical evidence, not a claim about the latest ai-rulez
release. A two-tool control exposes `find_skill` and `load_skill`; a separate full-catalog control exposes 71 tools.
Both configurations use the real server, with successful `initialize` and `tools/list` exchanges.

The probe keeps the built-in `openai` provider and its bundled model capabilities, changing only its endpoint
through the documented user-level [`openai_base_url`](https://learn.chatgpt.com/docs/config-file/config-advanced).
It does not substitute a custom provider or override tool-search features. The installed client's
`codex debug models --bundled` identifies `gpt-6.1-sol` as `tool_mode = "code_mode_only"` with
`supports_search_tool = true`. The stdio server uses the documented
[MCP configuration](https://learn.chatgpt.com/docs/extend/mcp).

| Control | Actual server tools | MCP definitions in initial request | Runtime metadata roster | Definition returned by metadata lookup |
|---|---:|---:|---:|---|
| Two-tool control | 2 | 0 | 2 | `mcp__ai_rulez__find_skill` |
| Full catalog | 71 | 0 | 71 | `mcp__ai_rulez__add_include` |

Code mode sends tool definitions through `input` items with `type = "additional_tools"`, including the
`functions` namespace and `exec` custom tool. Inspecting only a top-level `tools` array would incorrectly describe
this request as having no tools. Neither initial payload contains the ai-rulez names or callable definitions.

A scripted fixture response calls only `functions.exec`, reading `ALL_TOOLS` metadata. Its output enumerates the
complete matching runtime roster and selects one entry containing its callable TypeScript parameter declaration.
The next Responses request includes that output. Selecting the `add_include` **definition** does not invoke the
authoring tool. Both actual MCP protocol logs contain **zero `tools/call` or other source-data requests**. This
establishes startup omission plus client-side availability and selective definition retrieval for these code-mode
configurations; it does not establish that Codex uses Claude's `ToolSearch` protocol.

The client runs with fresh `HOME` and `CODEX_HOME`, file-only dummy API-key authentication, no copied credentials,
and a loopback Responses SSE fixture. An outer `sandbox-exec` policy denies network access except to that exact
local port; an external `1.1.1.1:443` negative control fails with `EPERM`. The client attempts its default WebSocket
transport against the fixture before falling back to HTTP/SSE. No hosted completion, subscription request or native
token-count endpoint is used. The MCP proxy permits controlled metadata methods only and records rejected calls.

The fixture's answer, usage and cost are synthetic. They cannot establish native input-token costs, billing,
natural model choices, production WebSocket behavior, ChatGPT subscription capabilities, workspace-managed
configuration, other model defaults or later CLI/server versions. No schema-byte difference is reported as a token
saving. Earlier paid instruction-loading observations remain separate and unchanged.

## Evidence and replay

Raw requests, stdio exchanges, CLI events, bundled model metadata, isolated configs, capture scripts and a SHA256
index are retained under the ignored polyrepo directory `reports/codex-mcp-ai-rulez-5.9.3-2026-10-30/`. The accepted
trials are `two-tool-verified` and `full-verified`; exploratory failures and truncated captures are not evidence of
successful schema retrieval. The index records the exact CLI and server binary hashes and observed exit statuses.

From this repository, replay each accepted trial with the following command, substituting its artifact paths:

```sh
mise exec -- python3 tools/context-evals/codex_mcp_probe.py \
  --rpc TRIAL.mcp.jsonl --requests TRIAL.api-requests.json \
  --events TRIAL.stdout.jsonl --models bundled-models.json \
  --model gpt-6.1-sol --out SUMMARY.json
```

The analyzer requires correlated successful initialization/catalog replies, a nonempty complete catalog, matching
bundled code-mode capabilities, nonempty startup tool definitions, the exact metadata-only JavaScript program,
matching call/output identities, a complete matching runtime roster, a selected callable declaration and a completed
fixture turn. Its offline tests reject absent or paginated catalogs, source calls, missing/truncated output,
incompatible capabilities and replacement programs that could execute source tools. No client, server or model is
started during replay.
