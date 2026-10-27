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
- Keep subagents disjoint: each in its own worktree (see polyrepo-structure), on files no other agent touches.
- A subagent compiles or runs tests only when dispatched for it. Otherwise it still writes tests but runs only static checks (`poly lint`, `poly fmt --check`, config validators) and reports what remains; the orchestrator owns compiled verification.
- Iterate: implement, then a critical review of the actual diff by a fresh reviewer, then adjust, until a review finds nothing material.
- Never trust a delivery: read the diff and rerun the checks. Weigh every deviation from the brief, keep or revert it, and report it with the reason.
