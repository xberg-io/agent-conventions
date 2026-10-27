---
name: basemind-tools
description: "basemind MCP tools and CLI by mode for code structure, references, call graphs, git history, documents and agent coordination. Use when navigating code or history in a repo where basemind is available."
# Content-Hash: blake3:9251435ed284ba5ce87e6fd04eff49a0e601821f926f84e881aba099fb408113
---

# basemind tools

Every basemind MCP tool takes a required `mode`; the CLI has the same subcommands
(`basemind code outline <path>`, `basemind git recent`, ...). Parameters that belong to another
mode are rejected, not ignored. Paths are repository-relative with forward slashes; page with the
`next_cursor` a response returns.

## Code map (`code`)

| Question | Mode |
|---|---|
| Shape of one file | `outline` (`l2: true` adds calls and doc comments), then `expand` one symbol's body |
| Where is X defined | `symbols` (case-sensitive substring of the name, optional `kind`) |
| Which definition does this reference bind to | `definition` (`path`, `line`, `column`) |
| What calls X | `references` (name-only, complete) or `callers` (one definition; `resolved` marks proven hits) |
| What implements a trait or interface | `implementations` |
| Who imports a module | `dependents` |
| Pattern or string literal | `grep` (Rust regex; prefer `symbols` for an identifier) |
| A file by name | `find` (fuzzy), or `files` to enumerate |
| Code by meaning | `semantic`, then `chunk` for the source |

The code map holds code only. Markdown, JSON, YAML, TOML, CSV, PDFs and other documents are
searched with `memory` mode `documents`.

## Graph (`graph`)

`calls` (callers or callees of one function), `neighbors` (blast radius before a change), `path`
(how two symbols connect), `map` (whole-repo hubs and cycles; start here in an unfamiliar repo).

## History (`git`)

`status`, `recent` (newest commits, a window not a search), `search` (full-text over all history:
author, summary, body), `show`, `touching` (commits that changed one path), `by_path`, `churn`,
`diff`, `diff_outline` (symbols a branch added or removed), `blame`, `blame_symbol`,
`symbol_history` (commits where one symbol's body changed). A shallow clone sets `truncated`, so a
missing commit is inconclusive.

## Documents, web and memory

- `memory` mode `documents`: semantic search over indexed documents; read the matching chunks
  instead of opening the file.
- `web` modes `scrape` (one page), `crawl` (a docs section) and `map` (a site's URLs) pull pages
  into the documents store under scope `web:<host>`.
- `memory` modes `put` / `get` / `search` keep notes shared across sessions and agents.

## Keeping the index fresh

Run `admin` mode `rescan` after edits (`paths` for an incremental pass). When a query returns
"no index" or nothing where something should exist, check `admin` mode `status`, then run
`basemind scan` from the CLI. Do not re-read a file basemind already mapped.

## Coordinating with other agents (`agents`)

Coordination runs over threads addressed by at least two of `subject`, `path` and `members`;
there is no global channel and no auto-join.

1. At start: `inbox`, then `thread_list`. Both return front matter only; read a body with `message`.
2. `thread_start` or `join` the thread for the area you work in; `post` when you begin, finish or
   hit a decision, with `reply_to` when answering.
3. `wait` long-polls for a reply instead of looping `inbox`; `ack` what you handled so it is not
   re-read.
4. One orchestrator driving several identities passes `as_agent` on every call.

`workspace` modes `worktrees` and `claim` show and record (advisory only) who works which
worktree.
