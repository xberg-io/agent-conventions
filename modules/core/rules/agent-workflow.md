---
type: Decision
title: Agent Workflow
x-ai-rulez:
  kind: rule
  id: agent-workflow
  metadata:
    priority: critical
---

- Delegate non-trivial implementation, research and exploration to subagents, independent ones in one message, each with a self-contained brief: goal, files, worktree, constraints, what to verify and return.
- Keep subagents disjoint: each in its own worktree, on files no other agent touches.
- A subagent compiles or runs tests only when dispatched for it (a `test-writer` dispatch counts). Otherwise it writes tests but runs only `poly lint <paths>`, `poly fmt --check <paths>` and config validators (a bare `poly lint .` runs cargo clippy) and reports what remains; the orchestrator owns compiled verification.
- Iterate: implement, then a fresh reviewer critically reviews the real diff, then adjust, until a review finds nothing material.
- Never trust a delivery: read the diff and rerun the checks. Weigh each deviation from the brief, keep or revert it, and report why.
