---
type: Decision
title: Generated Code Policy
x-ai-rulez:
  kind: rule
  id: generated-code-policy
  metadata:
    priority: critical
---

- All files in e2e/ are generated — DO NOT EDIT, they include a generated-code header
- To change: modify fixtures or generator source, run task e2e:generate, run task e2e:test, commit together
- CI validates freshness with task e2e:verify (runs alef e2e generate, then git diff --exit-code e2e/)
