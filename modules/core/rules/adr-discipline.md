---
type: Decision
title: ADR Discipline
x-ai-rulez:
  kind: rule
  id: adr-discipline
  metadata:
    priority: high
---

- Record a lasting choice between real alternatives (dependency, architecture, public API, build, release or tooling policy) as an ADR with `adrlint new`: in the repo's `adrs/`, or in `agent-conventions/adrs/` if org-wide, which repo ADRs cite instead of restating.
- Never edit an accepted ADR. Add one that amends it (`amends:`) or supersedes it (`adrlint unlock <old> --reason`, set `status: superseded` and `superseded-by`, `adrlint lock`). Shape, index, seeds: the `adr-authoring` skill.
