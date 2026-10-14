---
type: Decision
title: Basemind Tools
x-ai-rulez:
  kind: rule
  id: basemind-tools
  metadata:
    priority: high
---

When basemind is available (its MCP tools or the `basemind` CLI), prefer it over grep, file reads, and naked `git` for structural and historical questions. Its tools return paths, line numbers, and signatures — a fraction of the tokens of reading source. Fall back to shell/grep/git only when basemind cannot answer.

- Outline a file before opening it, then read only the span you need (`outline`; add `l2: true` for calls and docstrings).
- Find a definition with `search_symbols` instead of grep.
- Find call sites with `find_references` (any name) or `find_callers` (a specific definition) instead of grepping; map structure with `call_graph`, `dependents`, `find_implementations`.
- Search the tree with `workspace_grep` instead of shelling out to ripgrep.
- Use the git tools — `recent_changes`, `commits_touching`, `symbol_history`, `blame_file` / `blame_symbol`, `diff_file` / `diff_outline`, `hot_files` — instead of `git log` / `git blame`.
- Use `search_documents` and the document pipeline for RAG, extraction, and NER over PDFs/docs; use `web_scrape` / `web_crawl` / `web_map` for web content.
- After making edits, run `rescan` to refresh the index instead of reconnecting. Do not re-read a file basemind already mapped.
- When collaborating with other agents in the repo, coordinate through the `agents` surface, addressed by MODE:
  `register`, `list`, `thread-start`, `thread-list`, `join`, `leave`, `members`, `post`, `history`,
  `message`, `inbox`, `ack`, `wait`. Pass `--as-agent <name>` on every call — identity is per-transport,
  and a reconnect otherwise gives you a new identity with an empty inbox. `history`/`inbox` return front
  matter only; fetch bodies with `message <id>`. Ack what you read, or a polling loop re-reads it forever.
