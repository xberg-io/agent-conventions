---
type: Decision
title: Basemind Usage
x-ai-rulez:
  kind: rule
  id: basemind-usage
  metadata:
    priority: high
---

When the basemind MCP server (or the `basemind` CLI) is available, use it first for code structure and history; shell, grep and raw `git` are the fallback. It returns paths, lines and signatures instead of file bodies.

- Code: `code` mode `outline` before opening a file, then read only the span you need; `symbols` for a definition; `references` / `callers` for call sites; `grep` and `find` instead of `rg` and `find`. `graph` modes `calls` / `neighbors` / `map` show what reaches what.
- History: `git` modes `recent` / `touching` / `blame` / `blame_symbol` / `diff` instead of `git log`, `git blame`, `git diff`.
- Markdown, config, data and PDFs are not in the code map: search them with `memory` mode `documents`.
- Run `admin` mode `rescan` after edits; on "no indexed files" run `basemind scan`.
- Other agents may share the repo: read `agents` modes `inbox` and `thread_list` at start, `post` when you begin, finish or hit a decision. Details: the `basemind-tools` skill.
