---
type: Decision
title: Basemind Usage
x-ai-rulez:
  kind: rule
  id: basemind-usage
  metadata:
    priority: high
---

When basemind is available (MCP server or `basemind` CLI), use it before shell, grep and raw `git`: `code` modes `outline`/`symbols`/`references`/`grep`/`find`, `git` modes `recent`/`touching`/`blame`/`diff`, `memory` mode `documents` for Markdown, config and PDFs; `admin` mode `rescan` after edits. Agent coordination: the `basemind-tools` skill.
