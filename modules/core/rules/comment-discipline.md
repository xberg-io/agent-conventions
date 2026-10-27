---
type: Decision
title: Comment Discipline
x-ai-rulez:
  kind: rule
  id: comment-discipline
  metadata:
    priority: high
---

Write a comment only when it carries what the code cannot: a non-obvious reason, a workaround and its cause, a cross-boundary invariant, a spec or issue reference.

- Delete commented-out code; poly's uncomment pass flags it. Where `poly.toml` sets `[lint.uncomment] code_only = false`, it strips every non-doc comment without `~keep`, a default marker (`TODO`, `FIXME`, `HACK`, `NOTE`, a license header, a linter directive) or a `preserve_patterns` entry. Details: the `poly-lint-format` skill.
- No session numbers, milestone tags or progress notes ("Session 1", "M1", "wired later") in comments or `todo!()` messages: say what the code does or what behavior is missing.
