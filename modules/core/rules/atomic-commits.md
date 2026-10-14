---
type: Decision
title: Atomic Commits
x-ai-rulez:
  kind: rule
  id: atomic-commits
  metadata:
    priority: high
---

Each commit represents one logical change. Do not mix unrelated changes. Keep commits small and focused for easier review and bisection.
