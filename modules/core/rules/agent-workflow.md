---
type: Decision
title: Agent Workflow
x-ai-rulez:
  kind: rule
  id: agent-workflow
  metadata:
    priority: critical
---

- Delegate non-trivial implementation, research and exploration to subagents, launching independent ones in one message. Give each a self-contained brief: goal, files, worktree, constraints, what to verify, what to return.
- Keep subagents disjoint: each works in its own worktree (in the polyrepo, `.worktrees/<repo>/<branch>`) on files no other agent touches.
- Subagents stay lightweight. Unless dispatched explicitly for build or test work, a subagent never compiles or runs heavy checks (`cargo build`/`check`/`clippy`/`test`, `go build`/`test`, Gradle, Maven, `dotnet`, `swift build`, package builds, full test suites). The orchestrating agent integrates the changes and runs compilation, compiling lints and tests.
- Work iteratively: an implementation pass, then a critical review pass against the actual diff (a fresh reviewer, not the author's summary), then adjustments. Repeat until a review finds nothing material.
- Never trust a delivery: read the diff and rerun the checks before accepting it.
- Never accept a deviation from the brief silently: weigh it, keep or revert it, and report it with the reason either way.
