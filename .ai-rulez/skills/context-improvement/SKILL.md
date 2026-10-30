---
type: Playbook
title: Context Improvement
name: context-improvement
description: "Run one round of the context improvement loop over eval runs: triage failures, one delta patch per hypothesis with placebo and deletion arms, the pre-registered accept rule, the ledger, holdout checkpoints."
disable-model-invocation: true
targets: ["claude", "codex", "opencode"]
x-ai-rulez:
  kind: skill
  id: context-improvement
---

## Context improvement round

Procedure from issue #3, section 6, for maintainers of this repository. Tools live in `tools/context-evals/`; run
them from the repository root. A run directory holds `run.json` (repo, ref, model, judge_version, rubric_version) and
`sessions.jsonl` (one `records.SessionRecord` per case and repeat), written by the dynamic harness.

`L=python3 tools/context-evals/loop.py`

## The round

1. **Baseline.** Run the current ref on the tune split, 3 repeats. Give every `harness.py run`, `judge` and
   `judge-validate` invocation the same `--budget-ledger PATH --budget-usd 25 --per-call-usd 0.2` before the
   subcommand. Claude CLI dollar limits are soft: hard-ceiling execution is refused unless a provider-enforced
   limit exists; `--allow-soft-budget` explicitly accepts prospective accounting only. Missing billing data keeps
   its reservation and stops the whole shared round. Validate the judge before trusting scores, and record a
   completed control as round zero with `arm_kind` and `decision` both `baseline`.
2. **Diagnose.** `$L triage RUN_DIR --json triage.json --markdown triage.md [--sandbox sandbox.json]`.
   Pre-labels: `harness`, `sandbox_limit`, `answer_leak`, `wrong_skill`, `not_found`, `over_ask`, `under_ask`; the rest
   is `unlabelled` and is coded against the taxonomy in `triage.TAXONOMY` (version `TAXONOMY_VERSION`): `missing`,
   `wrong`, `ignored`, `noise`, `case`. Artifacts are ranked per domain by Ochiai suspiciousness; clusters are
   (cause, artifact). `harness` and `case` failures go to the harness or the case, not to a context patch.
3. **Propose.** One cluster, one hypothesis, one small delta patch on its own branch. Never regenerate a whole file.
   Before writing, read `$L ledger history KIND:NAME` for the artifact and do not retry a rejected idea. The proposer
   sees the failing transcripts, judge reasons, the inventory and that history.
4. **Arms.** Every round also runs a **placebo** arm (a harmless no-op edit; measures false accepts) and a
   **deletion** arm (remove the most suspicious artifact).
5. **Static gate** before any spend: `poly lint .`, structure guards, leakage (`exposure.py --fail-on-leak`), case
   validation, start-token delta, and every new fact or path checked against the code.
6. **Screen.** Target-cluster cases, 3 repeats. Stop arms whose paired mean difference is <= 0 (ledger decision
   `stopped`).
7. **Test.** All tune cases, 2+ repeats; surviving arms share the control runs.
8. **Decide.** `$L decide CONTROL_RUN ARM_RUN... --targets SPEC... [--token-cap N] --json decide.json`, one SPEC per
   arm (`cluster:NAME`, `domain:NAME` or `cases:ID,ID`). Runs with different judge or rubric versions are refused.
   Accept iff the target lower bound > 0 after Holm across arms, overall primary and every guardrail (leak, answer
   leak, recall in other domains, over-ask, under-ask) non-inferior at -0.02, and start tokens within +5%.
   Report every regressed case. `inconclusive` means more repeats, not a soft accept: report it with the repeats
   needed, never as a win.
9. **Record.** `$L ledger append ENTRY.json` for every arm, accepted or not. The ledger is append-only and chained;
   an edited line blocks further appends. Fields: round, cluster, hypothesis, arm_kind (change, placebo, deletion),
   artifacts, patch_ref, base_ref, stages (screen, test with intervals), decision, cost_usd, model, harness_version,
   judge_version, rubric_version, taxonomy_version.

## Placebo calibration

`decide.calibrate_placebo([...])` over the placebo decisions of past rounds reports the false-accept rate. Above 5% the
rule is too loose: widen the margin or add repeats before accepting anything else.

## Holdout

- `$L holdout status --harness-version V` shows reads, the cap (5 per harness version), whether a checkpoint is due
  (every 3 accepted changes) and the stop condition.
- `$L holdout checkpoint TIP_RUN CANDIDATE_RUN --harness-version V` compares holdout sessions with the last verified
  tip and counts a read. `progress` needs an improvement of at least the MDE; `revert` means go back to the tip;
  otherwise `plateau`.
- Never read the holdout outside a checkpoint and never tune on it. A new harness version starts a new budget.

## Stop

Stop after two rounds with nothing accepted, or on a holdout plateau (`holdout status` prints `stop`).
