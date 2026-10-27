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

- Mark every line comment worth keeping with `~keep`; `poly`'s uncomment pass removes comments without it (or a preserved marker such as `SAFETY`, `TODO`, or a license header). Details: the uncomment-pass section of the `poly-lint-format` skill.
- Doc comments (`///`, `//!`, docstrings) need no `~keep` where the repo's `poly.toml` sets `[lint.uncomment] remove_docs = false`.
- No session numbers, milestone tags or progress notes ("Session 1", "M1", "wired later") in comments or `todo!()` messages: say what the code does or what behavior is missing.
