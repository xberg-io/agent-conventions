---
type: Decision
title: Targeted Verification
x-ai-rulez:
  kind: rule
  id: targeted-verification
  metadata:
    priority: high
---

When behavior changes, write or update a focused test next to it (bug fixes and public APIs first) and run the checks that exercise the change, not the whole suite by default.
