# context-evals

The static layer of the context harness from
[issue #3](https://github.com/xberg-io/agent-conventions/issues/3): what a session in a consumer repository sees at
start, and which product terms leak into another product's start context. ai-rulez measures both natively
(`ai-rulez exposure`, [docs](https://goldziher.github.io/ai-rulez/exposure/)); this directory holds the shared
taxonomy it checks against.

```sh
# in a consumer checkout, after generating the outputs
npx -y ai-rulez@latest generate
python3 ../agent-conventions/tools/context-evals/areas.py --repo xberg --out /tmp/areas.toml
npx -y ai-rulez@latest exposure --areas /tmp/areas.toml                # Claude Code start tokens
npx -y ai-rulez@latest exposure --harness codex                         # Codex start tokens
npx -y ai-rulez@latest exposure leakage --areas /tmp/areas.toml        # foreign terms at session start
```

`domains.toml` is the taxonomy: `[domain.<name>]` with owner, owning paths and terms; `[repos.<name>].domains` lists the
domains a repository owns; `names` lists compounds that contain a term without naming its domain (`xberg-io`);
`[[accept]]` records an exception with a written `reason`. `areas.py --repo NAME [--harness claude|codex]` renders it
as an ai-rulez area map: owned domains are `shared`, `names` and the other domains' compound terms become each area's
`exclude`, and the acceptances that hold in that repository and harness become `[[accept]]` entries (ai-rulez fails
on one that accepts nothing). This repository commits its own rendering as `[exposure] areas_file`
(`exposure-areas.toml`, kept current by `test_areas.py`).

## CI gate

Consumers run `actions/context-exposure` after `validate-ai-rulez` has generated the outputs, with ai-rulez 5.11.0 or
later on `PATH` (the action refuses an older one):

```yaml
- uses: xberg-io/agent-conventions/actions/context-exposure@v1
```

The budgets live in the consumer's `.ai-rulez/config.toml`, about 5% above the last native measurement, so
`ai-rulez validate` (`AR9W3`) and the action read the same numbers. They are in ai-rulez's units, not the earlier
`budgets` input's: measure them with `ai-rulez exposure`, never copy the old values.

```toml
[exposure]
mcp_server_tokens = 1150  # the ai-rulez server restricted to find_skill and load_skill
start_budget = 5750
codex_start_budget = 6450
```

The action renders the repository's area map from `domains.toml`, runs `ai-rulez exposure` for Claude Code (fails over
`start_budget`, or when it is unset) and for Codex (fails over `codex_start_budget`, warns when it is unset), and
`ai-rulez exposure leakage`, and fails on an invocable skill or agent whose listed description is over 250 characters
(from `ai-rulez exposure inventory`, path-gated ones included because Codex lists them; the bound is the action's, not
the consumer's `[lint.description]`). It also checks the consumer's ai-rulez hook revision and lock against this
repository's pins. The deprecated `budgets` and `measure-mcp` inputs are accepted and ignored with a warning. Raising a
budget is a reviewed change to the consumer's configuration; the job summary carries the reports.

Native leakage reads the Claude Code inventory only, also for Codex
([Goldziher/ai-rulez#545](https://github.com/Goldziher/ai-rulez/issues/545)): Codex's AGENTS.md is the file Claude's
`@AGENTS.md` import scans, but the path-gated skills only Codex lists are not checked.

Tests: `mise run context:test` (supplies PyYAML). The gate tests also run the real ai-rulez on a fixture when it is on
`PATH`; CI installs it.

## Dynamic layer

Runs real headless sessions per case and scores them (issue #3, section 5.2). Never in per-commit CI: it costs model
calls and is nondeterministic. Needs `claude`, `ai-rulez`, PyYAML and `ANTHROPIC_API_KEY`; refuses to start inside
another agent session. `--model` has no default: pick one per study and keep it fixed. Scoring names what a session
loaded, and estimates its start tokens when a transcript has no usage, with `start_context.py`'s static model.

- Cases: `cases/<repo>/<domain>.yaml` (schema in `cases.py`), owned by the domain's owner. Split tune/holdout by
  `sha256(id) % 5`. `harness.py validate-cases [--repo-root CHECKOUT --repo NAME]` checks the schema, and against a
  checkout that every `cwd`, source and skill exists; CI runs the schema check.
- `harness.py run --repo CHECKOUT --ref REF --model M --out RUN_DIR [--split tune|holdout|all] [--repeats 3]`: a
  throwaway worktree at REF, `ai-rulez generate`, then one `claude -p` per case and repeat with a fresh config
  directory, project settings only, a strict empty MCP config and `--tools Read,Glob,Grep,Skill` plus the same
  permission allowlist. The advertised tool set and tool calls must match that profile; mismatches fail the
  session. Hard-budget mode adds the operating-system boundary described below. The tree is reset between
  sessions. `--jobs N` gives each worker its own worktree; `--resume` reuses only saved sessions with identical
  run parameters. Immutable context/configuration fingerprints and agent/generator binary hashes must match
  before reuse; existing snapshots are never overwritten. Legacy runs without identity are refused. Writes `run.json`, `transcripts/` and `sessions.jsonl` (`records.py`).
Paid execution requires an explicit policy. `--hard-budget --budget-ledger PATH --budget-usd 55` routes
agents and judges through the reserved egress gateway, caps output at 4,096 tokens and confines CLI network and
credential-file access. See [the price bound, offline proofs and limitations](hard-budget.md) before use.
`--allow-soft-budget` remains a separate prospective-accounting opt-in and cannot guarantee a dollar ceiling.
Never mix policies or reuse the historical invalid attempt's ledger; `study.toml` records each round's choices.

- `harness.py judge RUN_DIR --model M` grades criteria; `judge-validate RUN_DIR --model M --second-model M2` computes
  Cohen's kappa per criterion and the mutation-test TPR/TNR. Judges use `--tools ""` and must advertise an empty
  tool set. Only validated criteria count. Harness 5 rejects older tool and execution profiles for resume and paid judging;
  comparisons, verdicts and validity reports retain protocol provenance. Both judge prompts include their
  no-tools protocol versions so prompt-digest caches cannot reuse replies from the earlier tool-enabled profile.
- `harness.py report RUN_DIR`, `harness.py compare BASE_RUN ARM_RUN`: per-domain recall, precision, leak and
  answer-leak rates, over-/under-ask, criteria pass rate, start tokens and cost, with paired cluster-bootstrap
  intervals; "inconclusive" when an interval spans zero.

## Improvement loop

`loop.py triage | decide | ledger | holdout` (issue #3, section 6). The round, its arms and the decision rule are in
the repo-local `context-improvement` skill (`/context-improvement`, user-invoked). Every decision is appended to
`ledger.jsonl`.

## Probing a real session

`probe.py` measures loading in Claude Code and Codex themselves (issue #3, section 4.1). It creates an isolated consumer
worktree under `.worktrees/<repo>/`, plants a sentinel in the root `CLAUDE.md`, an unscoped and a glob-scoped rule, a
skill description and a nested `CLAUDE.md`, then runs `claude -p` with a fresh config directory and only project
settings: once with a trivial prompt (what loads at start, and its token cost) and once after reading a file in the
scoped directory (what loads on demand). Run it on your own machine with `ANTHROPIC_API_KEY` set, never inside
another agent session:

```sh
mise exec -- python tools/context-evals/probe.py ../xberg --scoped-file crates/xberg/src/lib.rs \
  --preset claude --model claude-sonnet-5-5 --repeats 3 --budget-ledger ../reports/study/budget.sqlite3 --json probe.json
```

Record the results with the Claude Code version in `docs/load-mechanics.md`.

## Baseline

[`baseline-2026-10-25.md`](baseline-2026-10-25.md): every consumer at agent-conventions `2011d3d` (sceptre `adb0caa`),
generated with `npx -y ai-rulez@latest generate` (5.6.3).

[`after-2026-10-25.md`](after-2026-10-25.md): the same consumers after the module restructure and the per-repo pass.

[`after-5.7.0-2026-10-26.md`](after-5.7.0-2026-10-26.md): the same consumers on ai-rulez 5.7.0 with
`scoped_fallback = "skill"`, which gives Codex the glob-scoped rules as path-gated skills.

[`after-mcp-2026-10-26.md`](after-mcp-2026-10-26.md): with the ai-rulez MCP server measured, before and after
restricting it to `find_skill` and `load_skill`.

[`baseline-2026-11-06.md`](baseline-2026-11-06.md): the first dynamic baseline (round zero), with per-consumer reports
and judge validity in `baseline-2026-11-06/`.

[`native-exposure-2026-11-04.md`](native-exposure-2026-11-04.md): ai-rulez 5.10.0's native `exposure` commands against
the retired bespoke classifier, and the gaps that kept it as the gate.

[`native-exposure-2026-11-06.md`](native-exposure-2026-11-06.md): the parity record for the switch to the native gate
on ai-rulez 5.11.0.
