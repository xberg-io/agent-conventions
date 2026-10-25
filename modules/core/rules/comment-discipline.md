---
type: Decision
title: Comment Discipline
x-ai-rulez:
  kind: rule
  id: comment-discipline
  metadata:
    priority: high
---

Write a comment only when it carries what the code cannot: a non-obvious reason, a workaround and its cause, a cross-boundary invariant, a spec or issue reference. Mark every comment worth keeping with `~keep`; `poly`'s uncomment pass removes comments without it (or a built-in marker such as `SAFETY`, `TODO`, or a license header). See the `poly-lint-format` skill.
