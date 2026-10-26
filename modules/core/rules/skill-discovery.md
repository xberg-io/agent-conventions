---
type: Decision
title: Skill Discovery
x-ai-rulez:
  kind: rule
  id: skill-discovery
  metadata:
    priority: high
---

Rules and skills are scoped to paths: reading or editing a file loads the ones that apply to it. To find the skill for a task before touching files, call `find_skill` on the `ai-rulez` MCP server with `path` set to the file or directory the task concerns, then `load_skill` on the match. Take the area from the paths and product terms in the request. When the request names a path or a term unique to one area, answer; ask which area only when the answer depends on it and nothing in the request identifies it.
