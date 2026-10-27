---
name: agent-coordination
description: "Dispatch, monitor, recover and verify subagents and worktree peers in a shared repo. Use when spawning a subagent, checking a quiet one, merging an agent's branch, or writing a brief for another agent."
# Content-Hash: blake3:dde27f6f2b449107ebcc9425f92aa8e17ee50667252145768a171ea0fecd34ba
---

# Agent Coordination

Multi-agent work in a shared repo fails in specific, recurring ways. Each one below has cost real
work; the fix is procedural, not a matter of being more careful.

## Who compiles, and how agents stay out of each other's way

The orchestrating agent owns integration: it merges subagent branches, then runs compilation, compiling lints
(`cargo clippy`, `go vet`), and tests, once, on the integrated tree. A subagent edits, runs only cheap static
checks on its own files (`poly lint <files>`, `poly fmt --check <files>`, config validators), and reports. Concurrent
compiles from several agents fill the disk, contend for a shared target directory, and reuse each other's
half-edited artifacts; a subagent's green build proves little about the integrated result anyway. Dispatch a
subagent for build or test work only explicitly, and then give it its own target directory.

Split work so scopes do not overlap: one worktree per subagent, cut from the target repo's default branch, and a
file set no sibling touches. Work that must edit the same files is sequenced, not parallelised.

Each round has three passes: implement; review critically against the real diff, by a reviewer that did not write
it and is given the code, not the author's conclusion; adjust. Rerun the round until the review comes back clean.
Treat every delivery as a claim to check: read the diff, rerun the checks, and compare against the brief. A
deviation is a decision for the orchestrator: evaluate it, keep or revert it, and report it with the reason.

## Worktree isolation is repo-local, not target-local

`isolation: "worktree"` forks **the session's own repo** (the current working directory), not
whatever repo the agent is told to operate on. An agent dispatched to work in a *different* repo
than the one the session is rooted in gets an isolated checkout of the wrong repo and edits the
target repo's single shared checkout directly — worktree isolation buys it nothing. Enforce
**one writer per repo** by scheduling, not by assuming isolation covers it, and say so explicitly
in the brief. Stating "you have your own worktree" in a prompt does not create one — only the
`isolation` parameter does.

## Stash, checkout, reset, and clean are shared, not worktree-local

`git stash` lives in the shared `.git` and is visible from **every** worktree of a repo — it is
not worktree-local, unlike the working tree and index. Concurrent agents running
stash/test/pop cycles in separate worktrees can and do hand each other their uncommitted changes.
Never run `git stash` when sibling agents may be active; to compare against a baseline, use
`git show HEAD:<path>` or copy to a scratch directory outside the repo instead. The same standing
ban covers `git checkout -- <path>`, `git reset`, and `git clean` — restore a single file with
`git show HEAD:<path> > <path>`. If a stash collision does happen, the files are not lost, they
are sitting in the other worktree's stash list — read them from there and reapply, never try to
"un-pop" a stash. Put these bans in every subagent brief explicitly; the agents that collided were
each doing the locally sensible thing.

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
(`git rev-parse --git-dir`), then running a plain `git commit --no-verify -m "<subject>"` directly
— that completes the operation without invoking the editor. Interactive flags (`-i`) may be
unavailable entirely; cherry-pick the commits you want onto a new base instead of trying to drop
commits during a rebase.

## A gitignored directory can still hold tracked files

Git tracks files, not directories. Bulk-deleting by ignore status, or by a directory-name pattern
(`-name vendor`, `-name bin`), deletes real committed content sitting inside an otherwise-ignored
directory — a name like `vendor/` is a disposable cache in one repo and a source directory in
another. After any bulk delete, verify per-path rather than trusting `git status`:

```bash
git ls-files | while read -r f; do [ -e "$f" ] || echo "MISSING: $f"; done
```

Prefer an allowlist of known-safe artifact names over a denylist, and preview with `-print` before
`rm -rf`.

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
works**, before running tests, not at the end — a `git commit --no-verify` after formatting costs
seconds and is the only thing that survives a hard failure (a worktree agent that dies loses
everything uncommitted). Brief long-running verification as narrow, scoped commands run in the
foreground with a generous timeout, not a full sweep — the coordinator runs the full sweep after
merging.

When checking on an agent, inspect the worktree **before** reading its summary:
`git log --oneline main..HEAD` plus `git status --porcelain`. A parked agent shows uncommitted
files and zero commits; recover by naming its exact dirty files, giving one narrow next command,
saying explicitly "do not open a new line of investigation," and confirming main has moved so it
must not rebase or merge itself.

## An agent's branch is not always the notification's branch

The branch name surfaced in a completion notification can differ from the branch the agent
actually committed to. Merging the notification's name can print "already up to date" and merge
nothing — indistinguishable from real success. After merging any agent branch, prove it landed:
`git merge-base --is-ancestor <sha> main && echo MERGED`. A second cause of the same false
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
