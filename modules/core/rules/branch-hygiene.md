---
type: Decision
title: Branch Hygiene
x-ai-rulez:
  kind: rule
  id: branch-hygiene
  metadata:
    priority: medium
---

Use descriptive branch names. Keep branches short-lived and delete merged branches. Check upstream state with `git fetch` before pushing; do not rebase or merge after committing unless the user explicitly asks for it.
