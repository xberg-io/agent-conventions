---
type: Decision
title: Prove The Check Fired
x-ai-rulez:
  kind: rule
  id: prove-the-check-fired
  metadata:
    priority: critical
---

The dominant defect shape is a check that passes because it examined nothing. Before trusting a green result, make it fail on purpose once. Read the count or the diff, not the word "ok": `0 files`, an empty match set and a real pass can render identically. Check the artifact in effect (generated output, committed content, a pushed ref), not only the source you edited, and confirm a path- or diff-scoped gate's filter matches the change it exists to catch. Assert the expected job count and compare it with the rows produced. Observed zero-work passes and harness guards: the `verification-harness` skill.
