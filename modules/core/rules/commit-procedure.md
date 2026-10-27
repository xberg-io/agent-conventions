---
type: Decision
title: Commit Procedure
x-ai-rulez:
  kind: rule
  id: commit-procedure
  metadata:
    priority: high
---

- Before committing, run `poly lint .` and `poly fmt --check .`; re-stage files a hook rewrote. A full build or test suite is not a commit step unless the user or a release procedure asks for it.
- Hooks run on commit. Skip them with `--no-verify` only when the user asks, or in a subagent when a hook would compile; then run `poly lint` and `poly fmt --check` on the staged files yourself first.
- Do not rebase or merge after committing unless the user asks. Before pushing, `git fetch` and inspect divergence; if the branch has diverged, ask how to reconcile.
- Use descriptive branch names; keep branches short-lived.
