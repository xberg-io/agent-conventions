---
type: Concept
title: Polyrepo Structure
x-ai-rulez:
  kind: context
  id: polyrepo-structure
  metadata:
    priority: high
---

# Polyrepo Structure

This repo is part of the `xberg-io` polyrepo. From a subrepo checkout, `../` is the polyrepo root; from a worktree under `.worktrees/<repo>/<name>`, it is `../../..`. Prefer absolute paths.

- Paths below are relative to the root. Shared AI governance config: `agent-conventions/` (shared ai-rulez modules)
- Polyrepo-level orchestration: `Taskfile.yml`, `poly.toml`
- Each subrepo is an independent git repo with its own `.ai-rulez/config.toml`
- Worktrees: every git worktree goes under the polyrepo root at `.worktrees/<repo>/<name>`, where `<name>` is the branch with each character outside `A-Za-z0-9_-` replaced by `-`, never inside a repository; create it from the root with `task worktree:add REPO=<repo> BRANCH=<branch>` (dispatching agents: the `agent-coordination` skill).
