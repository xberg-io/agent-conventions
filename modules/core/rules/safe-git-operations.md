---
type: Decision
title: Safe Git Operations
x-ai-rulez:
  kind: rule
  id: safe-git-operations
  metadata:
    priority: critical
---

Never force-push to shared branches. Use `--force-with-lease` instead of `--force` when a force push is explicitly approved. Confirm destructive operations with the user.

Never run `git stash` when sibling agents may be active in the same repo — the stash stack is repo-global, not worktree-local, so a concurrent `stash`/`stash pop` can hand one agent's changes to another. Never discard changes in a path you did not write (`git checkout --`, `git restore`, `git reset`, `git clean`); to restore your own file, use `git restore --source=HEAD -- <path>`. Stage explicit paths only — never `git add -A` or `git add .` while any other agent may have in-progress edits. Git tracks files, not directories: never bulk-delete by ignore status or by directory `-name` match, since a gitignored directory can still contain tracked files.
