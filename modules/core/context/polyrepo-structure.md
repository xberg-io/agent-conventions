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
- Worktrees: every git worktree lives at `<polyrepo root>/.worktrees/<repo>/<name>` (from a subrepo, `../.worktrees/<repo>/<name>`; the root ignores `/.worktrees/`), `<name>` being the branch with each character outside `A-Za-z0-9_-` replaced by `-`. Create it only from the root with `mise run worktree:add <repo> <branch> [--base <ref>]`; remove it with `mise run worktree:remove <repo> <branch>`. Never inside a repo, in `/tmp` or in a sibling directory. Not Claude Code's built-in worktrees (EnterWorktree, `claude --worktree`, Agent `isolation: "worktree"`), which use `.claude/worktrees/` in the repo. Dispatching agents: the `agent-coordination` skill.
