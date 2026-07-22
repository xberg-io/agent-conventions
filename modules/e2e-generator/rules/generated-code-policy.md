---
priority: critical
---

- All files in e2e/ are generated — DO NOT EDIT, they include a generated-code header
- To change: modify fixtures or generator source, run task generate:e2e, run task test:e2e, commit together
- CI validates freshness: task generate:e2e && git diff --exit-code e2e/
