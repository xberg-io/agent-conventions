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
- Do not rebase or merge after committing unless the user asks. Before pushing, `git fetch` and inspect divergence; if the branch has diverged, ask how to reconcile.
- Use descriptive branch names; keep branches short-lived.
