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
- Polyrepo-level orchestration: `mise.toml`, `mise-tasks/`, `repos.txt` (the repository registry), `poly.toml`
- Each subrepo is an independent git repo with its own `.ai-rulez/config.toml`
- Worktrees: every git worktree goes under the polyrepo root at `.worktrees/<repo>/<name>`, where `<name>` is the branch with each character outside `A-Za-z0-9_-` replaced by `-`, never inside a repository or in `/tmp`; create it from the root with `mise run worktree:add <repo> <branch> [--base <ref>]`, remove it with `mise run worktree:remove <repo> <branch>` (dispatching agents: the `agent-coordination` skill).
