# Round-zero attempt: 2026-10-30

**Incomplete.** This attempt is not a recorded baseline, and no round-zero ledger entry was appended.
Protocol choices and review owners are in [study.toml](study.toml); machine-readable counts and costs are in
[baseline-attempt-2026-10-30.json](baseline-attempt-2026-10-30.json).

| Consumer | Expected tune sessions | Collected | Failed |
|---|---:|---:|---:|
| Xberg | 138 | 128 | 2 |
| Sceptre | 48 | 48 | 0 |

Both consumers used three repeats, `claude-sonnet-5-5`, eight turns and a 180-second timeout. The Xberg failures
hit the turn limit. Separate detached worktrees protected both main checkouts. Resumption reuses saved sessions
only when the recorded parameters match; an incomplete session set cannot pass scoring.

## Spending stop

The round limit was $25. Claude reported $23.4157297 across all attempted agent, probe and judge calls. Interrupted
calls whose final cost was unavailable retain $1.10 in conservative reservations, for $24.5157297 charged or
reserved. The remaining amount cannot accommodate another $0.50 agent-call reservation, so the runner stopped.
These are CLI-reported estimates and retained reservations, not a reconciled provider invoice.

Costs include discarded pilot runs: the shell's locally built ai-rulez binary and the mise release binary both
said 5.9.2 but generated different output. The pinned baseline attempt was restarted with the published binary;
only those pinned runs contribute to the table above. Codex mechanics probes used the existing CLI subscription
and are separate from the Anthropic dollar ledger.

One judge call requested a $0.05 CLI limit but returned `error_max_budget_usd` at $0.0734915. The wrapper retained
that actual cost and stopped that caller. A CLI per-call flag is not a provider-side prepaid spending limit. After review, harness version 3 refuses paid
hard-ceiling execution by default; prospective accounting needs explicit `--allow-soft-budget` consent, and any
overrun or uncertain billing stops the whole shared round. A new allowance alone does not establish a hard
provider budget.

## Tool-profile limitation

The historical runner passed `--allowedTools`, which grants permissions but does not restrict available tools.
All 248 saved initialization records across pilot and baseline runs advertised Bash, Edit and Write alongside
the intended four tools. There were 178 Bash attempts and 62 successful Bash tool results: 43 in pinned runs
(33 Xberg, 10 Sceptre), and 19 in discarded runs. No Edit or Write calls were observed.

The 62 successful command strings use read/search utilities and Git inspection (`status`, `branch`, `worktree
list`, `log`, `diff`, `show`, `rev-parse`). Their seven explicit output redirections target `/dev/null`; no explicit
file mutation, network command or target outside a session worktree was found. This is a transcript audit, not
an operating-system trace; Git inspection may refresh its own metadata. It does not establish filesystem
isolation or validate the original read-only-profile claim.

The judge likewise omitted an explicit empty tool list. Harness 4 now sets the runner's available tools and
validates its initialization records; judges explicitly disable tools and validate an empty advertised profile.
Older sessions cannot resume or enter new paid judging under that protocol. New prompt versions and explicit
judge-profile provenance invalidate the earlier cached replies and validity artifacts. Historical raw transcripts,
case snapshots and caches remain unchanged and are observational evidence only.

## Validation diagnosis

There are 378 cached judge replies from distinct Sonnet 5.5 and Sonnet 5 models. The cache is not a completed
judge-validity report. A [cached-only diagnostic](judge-validation-partial-2026-10-30.json) covers every reference
and available mutation for 15 of 16 Sceptre cases and 4 of 46 Xberg cases, with no sampled session answers:

| Selected reference/mutation subset | TPR | TNR | Overall judge valid |
|---|---:|---:|---|
| Sceptre | 0.467 | 0.905 | No |
| Xberg | 0.250 | 0.700 | No |

This coverage is selected and incomplete. Do not interpret it as an unbiased validity estimate for either corpus.
No criteria scores count when global mutation validation fails, even if individual criteria have kappa >= 0.6.

The failures expose a corpus construction problem. `reference_answer()` joins `reference.facts`, but many facts
are pointers rather than answers satisfying the criteria. For example, `sceptre-code-style-config-precedence`
requires the exact defaults/config/environment/flags order, while its reference says only that `config/mod.rs`
documents the precedence. `sceptre-mcp-add-parameter` requires a five-step change order and backward-compatible
optional parameter, while its reference merely names three files. The judge correctly rejects these purported
positive controls.

Before further paid judging, curate complete canonical reference answers against each frozen consumer commit.
Keep the original collection hashes, record the revised scoring corpus/rubric version, collect fresh sessions
under the enforced tool profile, and rerun validation plus session grading. A continuation needs a new explicit spending allowance;
this attempt does not silently increase its cap or weaken the validity thresholds. Version 3 also refuses legacy
resumption without an immutable context identity; review the original context/toolchain provenance before any
migration. The historical collection used harness 2/rubric 1. Nine Sceptre tune references have since been
curated from frozen source and two contradictory/overbroad checks corrected under rubric 2; original prompts
and holdout cases are unchanged. These revised controls have not been model-validated.

Raw transcripts, model-catalog verification, cache databases and probe output remain in the ignored polyrepo
`reports/context-evals-2026-10-30/` directory. No raw context or transcript is published by these summary files.
