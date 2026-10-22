---
type: Decision
title: Python Type Checking
x-ai-rulez:
  kind: rule
  id: python-type-checking
  metadata:
    priority: critical
---

Pyrefly is the only supported Python static type checker across the organization. CI, local tasks, generated
scaffolds, development dependencies, and documentation must use `pyrefly check`. Keep Ruff for lint and format,
and pytest for runtime tests. Do not introduce another Python type checker or its configuration.
