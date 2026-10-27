---
type: Decision
title: Skill Discovery
x-ai-rulez:
  kind: rule
  id: skill-discovery
  metadata:
    priority: high
---

Path-scoped rules and skills load when you read or edit a matching file. Before touching files, call `find_skill` with `path` set to the file or directory the task concerns, then `load_skill` on the match. Ask which area only when the request names no path or area term and the answer depends on it.
