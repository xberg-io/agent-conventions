---
type: Concept
title: Area Map
x-ai-rulez:
  kind: context
  id: area-map
  metadata:
    priority: high
---

- `modules/<name>/` — shared modules; consumers include them by `version = "^1"`, so a change reaches them only after a
  `vX.Y.Z` release (README "Releasing") and the polyrepo root's `ai-rulez:update` task.
- Every module item must be true in each includer (`grep -l 'modules/<name>' ../*/.ai-rulez/config.toml`). AR101 and
  AR403 are off in the modules, so check each `paths:` glob against the includers' `git ls-files`, and each tool or
  task named against their Taskfile and CI.
- `skills/` — generated public export: `task skills:generate`, then `task skills:check` (CI fails on drift).
- `tools/context-evals/`, `actions/context-exposure/` — start-context harness and the consumer CI gate
  (`task context:test`).
