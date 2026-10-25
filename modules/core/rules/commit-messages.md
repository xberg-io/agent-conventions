---
type: Decision
title: Commit Messages
x-ai-rulez:
  kind: rule
  id: commit-messages
  metadata:
    priority: high
---

One logical change per commit; never mix unrelated changes. Conventional commits (`feat:`, `fix:`, `chore:`, `refactor:`, `docs:`, `test:`) with an optional scope (`fix(api): handle empty input`). First line under 72 characters, imperative mood; the body says why.
