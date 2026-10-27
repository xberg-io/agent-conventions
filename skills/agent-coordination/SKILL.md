---
name: agent-coordination
description: "Dispatch, monitor, recover and verify subagents and worktree peers in a shared repo. Use when spawning a subagent, checking a quiet one, merging an agent's branch, or writing a brief for another agent."
# Content-Hash: blake3:3d4e8cabb4e7413e8cca7bccbfe0daefff11921d6d9f495a78340eb792354927
---

# Agent Coordination

Multi-agent work in a shared repo fails in specific, recurring ways. Each one below has cost real
work; the fix is procedural, not a matter of being more careful.

## Who compiles, and how agents stay out of each other's way

The split (subagents edit and run static checks, the orchestrator integrates, compiles and tests;
disjoint worktrees; implement-review-adjust rounds) is the agent-workflow rule. The reason it is
strict: concurrent compiles fill the disk, contend for a shared target directory and reuse each
other's half-edited artifacts, and a subagent's green build proves little about the integrated
result. A subagent dispatched for build or test work gets its own target directory.

## Worktree isolation is repo-local, not target-local

`isolation: "worktree"` forks the session's own repo, not the repo the agent is told to work on, so
an agent sent to another repo edits that repo's shared checkout directly. In the polyrepo, create
the worktree with `task worktree:add` (the layout is in the polyrepo-structure context) and name its
path in the brief; elsewhere, enforce one writer per repo by scheduling. Saying "you have your own
worktree" in a prompt does not create one.

## Stash, checkout, reset, and clean are shared, not worktree-local

The bans are in `safe-git-operations`; this is why they hold across worktrees and how to recover.
The stash lives in the shared `.git`, so agents running stash/test/pop cycles in separate worktrees
hand each other their uncommitted changes. To compare against a baseline, use `git show HEAD:<path>`
or a scratch copy outside the repo. If a stash collision does happen, the files are not lost: they
sit in the other worktree's stash list; read them from there and reapply, never try to "un-pop" a
stash. Put the bans in every subagent brief explicitly; the agents that collided were each doing
the locally sensible thing.

Also shared: a `~/.cargo/bin/<tool>`-style install path, and — treat this as probabilistic, not
guaranteed — the working tree itself. A sibling agent has been observed operating directly inside
what looked like another agent's own isolated worktree. Before trusting a "clean baseline," check
`git log` for commits you did not make.

## Rebase silently drops merge-conflict resolutions

Edits made while resolving a merge conflict live only in the merge commit. `git rebase` (without
`--rebase-merges`) discards merge commits, so those edits vanish with no warning and no conflict.
Never let real work enter a merge commit — resolve the conflict, then commit the change
separately. After any rebase, verify with a tree comparison against a tag or branch of the
pre-rebase HEAD (`git diff <backup> HEAD --stat`), not by re-reading commit messages.

## `git cherry-pick --continue` (and `rebase`/`merge --continue`) can hang

If `--continue` blocks indefinitely regardless of `GIT_EDITOR`/`core.editor` overrides in this
environment, resolve conflicts by staging the files, confirming the sequencer state file exists
(`git rev-parse --git-dir`), then running a plain `git commit -m "<subject>"` directly
— that completes the operation without invoking the editor. Interactive flags (`-i`) may be
unavailable entirely; cherry-pick the commits you want onto a new base instead of trying to drop
commits during a rebase.

## After a bulk delete, verify per path

`safe-git-operations` forbids deleting by ignore status or directory name. If a bulk delete has run,
check every tracked path rather than trusting `git status`, and preview future deletes with
`-print` before `rm -rf`:

```bash
git ls-files | while read -r f; do [ -e "$f" ] || echo "MISSING: $f"; done
```

## A sibling agent can write into a shared main tree

A peer reached through cross-session messaging, not spawned by you, can edit the same main working
tree you are releasing from or relying on as a baseline — worktree isolation only covers agents
*you* spawn. Check `git status --porcelain` before every merge and before every tag; foreign dirt
is not hypothetical. If you find it: preserve first (`git diff > rescue.patch` plus byte copies),
tell the peer explicitly where their work is safe, then reconcile — never `stash`/`checkout --`
/`reset`/`clean` over it. Publish a file-ownership map (locked/free by path) early when multiple
agents may touch the same repo.

## A parked agent is never automatically resumed

An agent that ends its turn to "wait for a background run" strands finished, uncommitted work that
nobody reads — a stopped subagent is not resumed on its own. An in-prompt warning against
backgrounding does not reliably prevent this. Brief every agent to **commit as soon as each piece
works**, before running tests, not at the end — a commit costs seconds and is the only thing that
survives a hard failure (a worktree agent that dies loses everything uncommitted). When to skip
hooks with `--no-verify` is in `commit-procedure`. Brief long-running verification as narrow, scoped commands run in the
foreground with a generous timeout, not a full sweep — the coordinator runs the full sweep after
merging.

When checking on an agent, inspect the worktree **before** reading its summary:
`git log --oneline <default>..HEAD` (`<default>`: the branch `git symbolic-ref --short
refs/remotes/origin/HEAD` names, not always `main`) plus `git status --porcelain`. A parked agent shows uncommitted
files and zero commits; recover by naming its exact dirty files, giving one narrow next command,
saying explicitly "do not open a new line of investigation," and confirming `<default>` has moved so it
must not rebase or merge itself.

## An agent's branch is not always the notification's branch

The branch name surfaced in a completion notification can differ from the branch the agent
actually committed to. Merging the notification's name can print "already up to date" and merge
nothing — indistinguishable from real success. After merging any agent branch, prove it landed:
`git merge-base --is-ancestor <sha> <default> && echo MERGED`. A second cause of the same false
"already up to date": the merge command ran from inside the agent's own worktree because a prior
backgrounded command silently moved the shell's working directory — check
`git rev-parse --show-toplevel` before merging. Re-run the project's real lint/build gate after
merging, too; a fast linter and the CI-authoritative one can disagree.

## Verify a subagent's claim before acting on it

Re-run a subagent's tests yourself before trusting its diagnosis, and rebuild first — a stale build
can make a passing test look like a failure. Check whether the claimed root cause survives one
cheap empirical probe. When an agent blames "someone else's uncommitted work," check the blame
before accepting it. "I ran the tool" is not the same claim as "I fed it the real artifact" —
confirm exactly what was tested, not just that a command executed.

## Verify your own premise before it goes in a brief

A detailed brief propagates the coordinator's own errors at full confidence, and a compliant agent
will act on them without question. Before a factual claim goes into a brief, run the command that
would falsify it — a listing tool can lie about what's tracked, a remembered commit subject can
miss a since-reworded fix, an inferred cause can be a fragment result rather than the real
artifact. State evidence as evidence ("`git ls-files` shows X") rather than as settled fact, and
add "if this diagnosis is wrong, say so and fix the real cause" to every brief — it is what lets
an agent that finds you wrong push back instead of complying with a false premise. When one does
refute you, verify the refutation yourself, correct the brief, and say plainly you were wrong.

## Concurrent runs make transient failures look real

With several agents active, a full test sweep can report a spurious failure from resource
contention (shared temp directories, parallel installs of the same binary) and pass clean on a
quiet re-run. A red result while agents are in flight is not evidence of a regression until it
reproduces quietly.

## Pass prose to a CLI through a file

Any flag carrying prose with code identifiers (a `--body`, a commit message, a comment posted
through a tool) comes from a file or a quoted heredoc, not an inline double-quoted string: the
shell substitutes `` ` ``, `$(...)`, `${...}` and `!` inside double quotes, silently mangling every
backticked identifier in the text.
